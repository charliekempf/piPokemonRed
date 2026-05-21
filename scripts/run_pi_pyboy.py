from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from pyboy import PyBoy


ROM = Path("roms/Pokemon - Red Version (USA, Europe) (SGB Enhanced).gb")
PI_DIGITS = Path("data/pi_10m_digits.txt")
RUN_NAME = "statistical_walk"
GAMEBOY_FPS = 4194304 / 70224
INPUT_CONFIG = Path("config/statistical_walk.json")
VALID_BUTTONS = {"a", "b", "start", "select", "up", "down", "left", "right"}
RUN_CONFIG_FILENAME = "input_config.json"
PROGRESSION_DISTANCE_FILENAME = "progression_distance.h5"


@dataclass(frozen=True)
class ButtonRange:
    minimum: int
    maximum: int
    button: str


@dataclass(frozen=True)
class PiInputAction:
    button: str
    repetitions: int = 1


@dataclass(frozen=True)
class PiInputConfig:
    on_frames: int
    off_frames: int
    digits_per_input: int
    mapping: tuple[ButtonRange, ...]
    mapping_mode: str = "range"
    direction_step_min: int = 1
    direction_step_max: int = 1
    start_value: int | None = None


@dataclass(frozen=True)
class AdvanceResult:
    digits_consumed: int
    inputs_sent: int
    last_button: str
    frames_advanced: int

    def __iter__(self):
        yield self.digits_consumed
        yield self.inputs_sent
        yield self.last_button


@dataclass
class Progress:
    run_name: str
    digits_path: str
    rom_path: str
    digits_consumed: int
    input_pairs_consumed: int
    frames_elapsed: int
    checkpoints_completed: int
    elapsed_seconds: float
    effective_digits_per_second: float
    effective_fps: float
    effective_realtime_x: float
    last_state: str | None


def load_input_config(config_path: Path = INPUT_CONFIG) -> PiInputConfig:
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    digits_per_input = int(raw["digits_per_input"])
    if digits_per_input < 1:
        raise ValueError("digits_per_input must be at least 1")

    on_frames = int(raw["on_frames"])
    off_frames = int(raw["off_frames"])
    if on_frames < 1:
        raise ValueError("on_frames must be at least 1")
    if off_frames < 0:
        raise ValueError("off_frames must be at least 0")

    mapping_mode = str(raw.get("mapping_mode", "range")).lower()
    if mapping_mode not in {"range", "digit_stride"}:
        raise ValueError(f"Unsupported mapping mode: {mapping_mode}")

    max_value = (10**digits_per_input) - 1
    mapping_key = "first_digit_mapping" if mapping_mode == "digit_stride" else "mapping"
    mapping_max_value = 9 if mapping_mode == "digit_stride" else max_value
    seen: set[int] = set()
    ranges: list[ButtonRange] = []
    for entry in raw[mapping_key]:
        minimum = int(entry["min"])
        maximum = int(entry["max"])
        button = str(entry["button"]).lower()
        if button not in VALID_BUTTONS:
            raise ValueError(f"Unsupported button in config: {button}")
        if minimum < 0 or maximum > mapping_max_value or minimum > maximum:
            raise ValueError(f"Invalid mapping range: {minimum}-{maximum}")
        for value in range(minimum, maximum + 1):
            if value in seen:
                raise ValueError(f"Overlapping mapping value: {value}")
            seen.add(value)
        ranges.append(ButtonRange(minimum=minimum, maximum=maximum, button=button))

    missing = set(range(mapping_max_value + 1)) - seen
    if missing:
        raise ValueError(f"Mapping does not cover {len(missing)} values for {digits_per_input} digits per input")

    direction_step_min = 1
    direction_step_max = 1
    start_value = None
    if mapping_mode == "digit_stride":
        if digits_per_input != 2:
            raise ValueError("digit_stride mapping currently requires digits_per_input to be 2")
        step_digit = raw.get("step_digit", {})
        if not isinstance(step_digit, dict):
            raise ValueError("digit_stride config requires a step_digit object")
        direction_step_min = int(step_digit.get("min_steps", 1))
        direction_step_max = int(step_digit.get("max_steps", 10))
        if direction_step_min < 1 or direction_step_max < direction_step_min:
            raise ValueError("Invalid digit_stride step range")
        start_combo = str(raw.get("start_combo", "")).strip()
        if start_combo:
            if len(start_combo) != digits_per_input or not start_combo.isdigit():
                raise ValueError("start_combo must be a digit string matching digits_per_input")
            start_value = int(start_combo)

    return PiInputConfig(
        on_frames=on_frames,
        off_frames=off_frames,
        digits_per_input=digits_per_input,
        mapping=tuple(ranges),
        mapping_mode=mapping_mode,
        direction_step_min=direction_step_min,
        direction_step_max=direction_step_max,
        start_value=start_value,
    )


def canonical_config_text(config_path: Path) -> str:
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    return json.dumps(raw, indent=2, sort_keys=True) + "\n"


def compatibility_config_text(config_path: Path) -> str:
    raw = compatibility_config_payload(config_path)
    return json.dumps(raw, indent=2, sort_keys=True) + "\n"


def compatibility_config_payload(config_path: Path) -> dict[str, object]:
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw.pop("name", None)
    return raw


def configs_are_compatible(stored_config_path: Path, requested_config_path: Path) -> bool:
    stored = compatibility_config_payload(stored_config_path)
    requested = compatibility_config_payload(requested_config_path)
    if stored == requested:
        return True

    if "game" not in stored:
        requested_without_game = dict(requested)
        requested_without_game.pop("game", None)
        return stored == requested_without_game

    return False


def config_display_name(config_path: Path) -> str:
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    name = str(raw.get("name", "")).strip()
    return name or config_path.parent.name or config_path.stem


def slug_for_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value.lower()).strip("_") or "config"


def config_run_suffix(config_path: Path) -> str:
    digest = hashlib.sha1(compatibility_config_text(config_path).encode("utf-8")).hexdigest()[:10]
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", config_path.stem).strip("_") or "config"
    return f"{stem}_{digest}"


def resolve_configured_run_name(
    run_name: str,
    config_path: Path,
    checkpoint_root: Path = Path("saves"),
    results_root: Path = Path("results"),
) -> str:
    config_text = canonical_config_text(config_path)
    configured_run_name = slug_for_name(config_display_name(config_path) or run_name)
    run_config_path = checkpoint_root / configured_run_name / RUN_CONFIG_FILENAME
    if run_config_path.exists() and not configs_are_compatible(run_config_path, config_path):
        configured_run_name = config_run_suffix(config_path)
        run_config_path = checkpoint_root / configured_run_name / RUN_CONFIG_FILENAME

    run_config_path.parent.mkdir(parents=True, exist_ok=True)
    if not run_config_path.exists() or run_config_path.read_text(encoding="utf-8") != config_text:
        run_config_path.write_text(config_text, encoding="utf-8")

    results_config_path = results_root / configured_run_name / RUN_CONFIG_FILENAME
    results_config_path.parent.mkdir(parents=True, exist_ok=True)
    if not results_config_path.exists() or results_config_path.read_text(encoding="utf-8") != config_text:
        results_config_path.write_text(config_text, encoding="utf-8")

    return configured_run_name


def button_for_value(value: int, input_config: PiInputConfig) -> str:
    return action_for_value(value, input_config).button


def action_for_value(value: int, input_config: PiInputConfig) -> PiInputAction:
    if input_config.mapping_mode == "digit_stride":
        if input_config.start_value is not None and value == input_config.start_value:
            return PiInputAction("start")
        first_digit = value // 10
        second_digit = value % 10
        for button_range in input_config.mapping:
            if button_range.minimum <= first_digit <= button_range.maximum:
                if button_range.button in {"up", "down", "left", "right"}:
                    steps = input_config.direction_step_min + second_digit
                    steps = min(steps, input_config.direction_step_max)
                    return PiInputAction(button_range.button, steps)
                return PiInputAction(button_range.button)
        raise ValueError(f"No first-digit mapping for value {value}")

    for button_range in input_config.mapping:
        if button_range.minimum <= value <= button_range.maximum:
            return PiInputAction(button_range.button)
    raise ValueError(f"No button mapping for value {value}")


def frames_for_action(action: PiInputAction, hold_frames: int, release_frames: int) -> int:
    return action.repetitions * (hold_frames + release_frames)


def frames_for_digit_value(value: int, input_config: PiInputConfig, hold_frames: int, release_frames: int) -> int:
    return frames_for_action(action_for_value(value, input_config), hold_frames, release_frames)


def average_frames_per_input(input_config: PiInputConfig, hold_frames: int | None = None, release_frames: int | None = None) -> float:
    hold = input_config.on_frames if hold_frames is None else hold_frames
    release = input_config.off_frames if release_frames is None else release_frames
    max_value = (10**input_config.digits_per_input) - 1
    return sum(
        frames_for_action(action_for_value(value, input_config), hold, release)
        for value in range(max_value + 1)
    ) / (max_value + 1)


def frames_for_digit_range(
    digits: str,
    start_digits: int,
    end_digits: int,
    input_config: PiInputConfig,
    hold_frames: int | None = None,
    release_frames: int | None = None,
) -> int:
    digits_per_input = input_config.digits_per_input
    start_digits = max(0, int(start_digits))
    end_digits = max(start_digits, min(int(end_digits), len(digits)))
    if start_digits % digits_per_input or end_digits % digits_per_input:
        raise ValueError("Digit range must align to digits_per_input")

    hold = input_config.on_frames if hold_frames is None else hold_frames
    release = input_config.off_frames if release_frames is None else release_frames
    if input_config.mapping_mode == "range":
        return ((end_digits - start_digits) // digits_per_input) * (hold + release)

    return sum(
        frames_for_digit_value(int(digits[index : index + digits_per_input]), input_config, hold, release)
        for index in range(start_digits, end_digits, digits_per_input)
    )


def button_for_pair(value: int) -> str:
    return button_for_value(value, load_input_config())


def advance_pi_inputs(
    pyboy: PyBoy,
    digits: str,
    start_digits: int,
    target_digits: int,
    hold_frames: int,
    release_frames: int,
    render_final: bool = False,
    input_config: PiInputConfig | None = None,
    sound: bool = True,
    after_input: Callable[[int, int, str, int], None] | None = None,
) -> AdvanceResult:
    config = input_config or load_input_config()
    digits_per_input = config.digits_per_input
    digits_consumed = start_digits
    inputs_sent = 0
    frames_advanced = 0
    last_button = "-"
    while digits_consumed < target_digits:
        value = int(digits[digits_consumed : digits_consumed + digits_per_input])
        action = action_for_value(value, config)
        button = action.button
        finishing = digits_consumed + digits_per_input >= target_digits
        for repetition in range(action.repetitions):
            pyboy.button_press(button)
            pyboy.tick(hold_frames, False, sound)
            pyboy.button_release(button)
            if release_frames:
                is_last_repetition = repetition == action.repetitions - 1
                pyboy.tick(release_frames, render_final and finishing and is_last_repetition, sound)
            frames_advanced += hold_frames + release_frames
        digits_consumed += digits_per_input
        inputs_sent += 1
        last_button = button
        if after_input is not None:
            after_input(digits_consumed, inputs_sent, last_button, frames_advanced)
    return AdvanceResult(digits_consumed, inputs_sent, last_button, frames_advanced)


class ProgressionDistanceRecorder:
    STRING_FIELDS = ("gate_id", "gate_label", "objective_location")
    INT_FIELDS = (
        "digit",
        "input_index",
        "frames_elapsed",
        "map_id",
        "x",
        "y",
        "respawn_map_id",
        "respawn_x",
        "respawn_y",
        "remaining_steps",
        "total_steps_from_respawn",
        "nearest_closer_checkpoint_steps",
    )
    BOOL_FIELDS = ("reachable", "in_battle")

    def __init__(self, path: Path, run_name: str, config_path: Path, digits_path: Path, rom_path: Path) -> None:
        try:
            import h5py
        except ImportError as error:
            raise RuntimeError("Install h5py to record progression distance: py -m pip install -r requirements.txt") from error

        self.h5py = h5py
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = h5py.File(path, "a")
        self.file.attrs["run_name"] = run_name
        self.file.attrs["config_path"] = str(config_path)
        self.file.attrs["digits_path"] = str(digits_path)
        self.file.attrs["rom_path"] = str(rom_path)
        self.file.attrs["schema"] = "pi_pokemon_progression_distance_v1"
        self.datasets = self._open_datasets()
        self.buffer: list[dict[str, object]] = []

    def _open_datasets(self):
        string_dtype = self.h5py.string_dtype(encoding="utf-8")
        datasets = {}
        for field in self.INT_FIELDS:
            dtype = "i8" if field in {"digit", "input_index", "frames_elapsed"} else "i4"
            datasets[field] = self._dataset(field, dtype)
        for field in self.BOOL_FIELDS:
            datasets[field] = self._dataset(field, "?")
        for field in self.STRING_FIELDS:
            datasets[field] = self._dataset(field, string_dtype)
        return datasets

    def _dataset(self, name: str, dtype):
        if name in self.file:
            return self.file[name]
        return self.file.create_dataset(name, shape=(0,), maxshape=(None,), chunks=True, dtype=dtype)

    def trim_after(self, digits_consumed: int) -> None:
        digit_dataset = self.datasets["digit"]
        keep_count = 0
        for value in digit_dataset:
            if int(value) <= digits_consumed:
                keep_count += 1
            else:
                break
        for dataset in self.datasets.values():
            if len(dataset) != keep_count:
                dataset.resize((keep_count,))
        self.file.flush()

    def append(self, sample: dict[str, object]) -> None:
        self.buffer.append(sample)
        if len(self.buffer) >= 8192:
            self._write_buffer()

    def _write_buffer(self) -> None:
        if not self.buffer:
            return
        row = len(self.datasets["digit"])
        count = len(self.buffer)
        for dataset in self.datasets.values():
            dataset.resize((row + count,))
        for offset, sample in enumerate(self.buffer):
            self._write_sample(row + offset, sample)
        self.buffer.clear()

    def _write_sample(self, row: int, sample: dict[str, object]) -> None:
        for field in self.INT_FIELDS:
            self.datasets[field][row] = int(sample.get(field, -1) if sample.get(field) is not None else -1)
        for field in self.BOOL_FIELDS:
            self.datasets[field][row] = bool(sample.get(field, False))
        for field in self.STRING_FIELDS:
            self.datasets[field][row] = str(sample.get(field, ""))

    def flush(self) -> None:
        self._write_buffer()
        self.file.flush()

    def close(self) -> None:
        self.flush()
        self.file.close()


def progression_distance_sample(pyboy: PyBoy, digits_consumed: int, frames_elapsed: int, input_config: PiInputConfig) -> dict[str, object]:
    from progression_pathfinding import Tile
    from progression_world import progression_state_for_tile
    from review_pi_checkpoint import current_blackout_checkpoint_tile, current_player_tile, is_in_battle

    tile = current_player_tile(pyboy)
    respawn = current_blackout_checkpoint_tile(pyboy)
    base: dict[str, object] = {
        "digit": digits_consumed,
        "input_index": digits_consumed // input_config.digits_per_input,
        "frames_elapsed": frames_elapsed,
        "map_id": tile["map_id"],
        "x": tile["x"],
        "y": tile["y"],
        "respawn_map_id": respawn["map_id"] if respawn is not None else -1,
        "respawn_x": respawn["x"] if respawn is not None else -1,
        "respawn_y": respawn["y"] if respawn is not None else -1,
        "remaining_steps": None,
        "total_steps_from_respawn": None,
        "nearest_closer_checkpoint_steps": None,
        "gate_id": "",
        "gate_label": "",
        "objective_location": "",
        "reachable": False,
        "in_battle": is_in_battle(pyboy),
    }
    if base["in_battle"]:
        return base

    progression = progression_state_for_tile(
        pyboy,
        Tile(tile["map_id"], tile["x"], tile["y"]),
        Tile(respawn["map_id"], respawn["x"], respawn["y"]) if respawn is not None else None,
    )
    nearest = progression.get("nearest_closer_checkpoint")
    if isinstance(nearest, dict):
        base["nearest_closer_checkpoint_steps"] = nearest.get("steps")
    base.update(
        {
            "remaining_steps": progression.get("remaining_steps"),
            "total_steps_from_respawn": progression.get("total_steps_from_respawn"),
            "gate_id": progression.get("id", ""),
            "gate_label": progression.get("label", ""),
            "objective_location": progression.get("objective_location", ""),
            "reachable": bool(progression.get("reachable", False)),
        }
    )
    return base


def latest_checkpoint(checkpoint_dir: Path) -> tuple[int, Path] | None:
    pattern = re.compile(r"checkpoint_(\d+)_digits\.state$")
    candidates: list[tuple[int, Path]] = []
    for path in checkpoint_dir.glob("checkpoint_*_digits.state"):
        match = pattern.match(path.name)
        if match:
            candidates.append((int(match.group(1)), path))
    return max(candidates) if candidates else None


def save_checkpoint(
    pyboy: PyBoy,
    checkpoint_dir: Path,
    screenshot_dir: Path,
    digits_consumed: int,
    save_screenshot: bool,
) -> Path:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    state_path = checkpoint_dir / f"checkpoint_{digits_consumed}_digits.state"
    with state_path.open("wb") as state_file:
        pyboy.save_state(state_file)

    if save_screenshot:
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        restore_buffer = io.BytesIO()
        pyboy.save_state(restore_buffer)
        restore_buffer.seek(0)
        pyboy.tick(1, True)
        pyboy.screen.image.save(screenshot_dir / f"checkpoint_{digits_consumed}_digits.png")
        restore_buffer.seek(0)
        pyboy.load_state(restore_buffer)

    return state_path


def write_progress(progress_path: Path, progress: Progress) -> None:
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = progress_path.with_suffix(progress_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(asdict(progress), indent=2), encoding="utf-8")
    temp_path.replace(progress_path)


def progress_snapshot(
    run_name: str,
    digits_path: Path,
    rom_path: Path,
    digits_consumed: int,
    start_digits: int,
    frames_elapsed: int,
    start_frames_elapsed: int,
    checkpoint_digits: int,
    started_at: float,
    last_state: Path | None,
    input_config: PiInputConfig,
) -> Progress:
    elapsed = time.perf_counter() - started_at
    effective_digits_per_second = (digits_consumed - start_digits) / elapsed if elapsed else 0
    effective_fps = (frames_elapsed - start_frames_elapsed) / elapsed if elapsed else 0
    return Progress(
        run_name=run_name,
        digits_path=str(digits_path),
        rom_path=str(rom_path),
        digits_consumed=digits_consumed,
        input_pairs_consumed=digits_consumed // input_config.digits_per_input,
        frames_elapsed=frames_elapsed,
        checkpoints_completed=digits_consumed // checkpoint_digits,
        elapsed_seconds=elapsed,
        effective_digits_per_second=effective_digits_per_second,
        effective_fps=effective_fps,
        effective_realtime_x=effective_fps / GAMEBOY_FPS,
        last_state=str(last_state) if last_state else None,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Pokemon Red with pi-derived inputs in PyBoy.")
    parser.add_argument("--rom", type=Path, default=ROM)
    parser.add_argument("--digits", type=Path, default=PI_DIGITS)
    parser.add_argument("--config", type=Path, default=INPUT_CONFIG)
    parser.add_argument("--run-name", default=RUN_NAME)
    parser.add_argument("--checkpoint-digits", type=int, default=1_000_000)
    parser.add_argument("--hold-frames", type=int, default=None)
    parser.add_argument("--release-frames", type=int, default=None)
    parser.add_argument("--max-digits", type=int, default=None)
    parser.add_argument("--sound-sample-rate", type=int, default=48000)
    parser.add_argument("--fresh", action="store_true", help="Ignore existing checkpoints and start from reset.")
    parser.add_argument("--no-screenshots", action="store_true")
    parser.add_argument(
        "--no-progression-distance",
        action="store_true",
        help="Do not append per-input progression distance samples to the run HDF5 dataset.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_config = load_input_config(args.config)
    args.run_name = resolve_configured_run_name(args.run_name, args.config)
    hold_frames = input_config.on_frames if args.hold_frames is None else args.hold_frames
    release_frames = input_config.off_frames if args.release_frames is None else args.release_frames
    if hold_frames < 1:
        raise ValueError("--hold-frames must be at least 1")
    if release_frames < 0:
        raise ValueError("--release-frames must be at least 0")

    digits = args.digits.read_text(encoding="ascii").strip()
    max_digits = min(args.max_digits or len(digits), len(digits))
    if max_digits % input_config.digits_per_input:
        max_digits -= max_digits % input_config.digits_per_input

    checkpoint_dir = Path("saves") / args.run_name
    screenshot_dir = Path("results") / args.run_name / "screenshots"
    progress_path = Path("results") / args.run_name / "progress.json"
    progression_distance_path = Path("results") / args.run_name / PROGRESSION_DISTANCE_FILENAME

    start_digits = 0
    state_to_load: Path | None = None
    if not args.fresh:
        checkpoint = latest_checkpoint(checkpoint_dir)
        if checkpoint is not None:
            start_digits, state_to_load = checkpoint

    if start_digits >= max_digits:
        print(f"Already complete through {start_digits:,} digits.")
        return

    # Use an in-memory RAM file so an old .ram beside the ROM cannot change a fresh run.
    pyboy = PyBoy(
        str(args.rom),
        window="null",
        sound_emulated=True,
        sound_sample_rate=args.sound_sample_rate,
        no_input=False,
        ram_file=io.BytesIO(bytes(32768)),
        log_level="CRITICAL",
    )
    pyboy.set_emulation_speed(0)

    if state_to_load:
        with state_to_load.open("rb") as state_file:
            pyboy.load_state(state_file)
        print(f"Resumed from {state_to_load} at {start_digits:,} digits.")
    else:
        print("Starting fresh from reset.")

    next_checkpoint = ((start_digits // args.checkpoint_digits) + 1) * args.checkpoint_digits
    next_checkpoint = min(next_checkpoint, max_digits)
    progress_chunk_digits = min(args.checkpoint_digits, 10_000)
    if progress_chunk_digits % input_config.digits_per_input:
        progress_chunk_digits -= progress_chunk_digits % input_config.digits_per_input
    progress_chunk_digits = max(input_config.digits_per_input, progress_chunk_digits)
    digits_consumed = start_digits
    frames_elapsed = frames_for_digit_range(digits, 0, digits_consumed, input_config, hold_frames, release_frames)
    start_frames_elapsed = frames_elapsed
    started_at = time.perf_counter()
    last_state: Path | None = state_to_load
    recorder: ProgressionDistanceRecorder | None = None
    if not args.no_progression_distance:
        if args.fresh and progression_distance_path.exists():
            progression_distance_path.unlink()
        recorder = ProgressionDistanceRecorder(
            progression_distance_path,
            args.run_name,
            args.config,
            args.digits,
            args.rom,
        )
        recorder.trim_after(start_digits)

    try:
        while digits_consumed < max_digits:
            chunk_target = min(next_checkpoint, digits_consumed + progress_chunk_digits, max_digits)
            chunk_start_frames_elapsed = frames_elapsed

            def record_progression_distance(
                sample_digits_consumed: int,
                _inputs_sent: int,
                _last_button: str,
                sample_frames_advanced: int,
            ) -> None:
                if recorder is None:
                    return
                recorder.append(
                    progression_distance_sample(
                        pyboy,
                        sample_digits_consumed,
                        chunk_start_frames_elapsed + sample_frames_advanced,
                        input_config,
                    )
                )

            advance_result = advance_pi_inputs(
                pyboy,
                digits,
                digits_consumed,
                chunk_target,
                hold_frames,
                release_frames,
                input_config=input_config,
                after_input=record_progression_distance,
            )
            digits_consumed, _, _ = advance_result
            frames_elapsed += advance_result.frames_advanced

            if digits_consumed >= next_checkpoint:
                last_state = save_checkpoint(
                    pyboy,
                    checkpoint_dir,
                    screenshot_dir,
                    digits_consumed,
                    save_screenshot=not args.no_screenshots,
                )
                progress = progress_snapshot(
                    args.run_name,
                    args.digits,
                    args.rom,
                    digits_consumed,
                    start_digits,
                    frames_elapsed,
                    start_frames_elapsed,
                    args.checkpoint_digits,
                    started_at,
                    last_state,
                    input_config,
                )
                write_progress(progress_path, progress)
                if recorder is not None:
                    recorder.flush()
                print(
                    f"checkpoint {digits_consumed:,}/{max_digits:,} digits "
                    f"({progress.effective_digits_per_second:,.0f} digits/s, "
                    f"{progress.effective_fps:,.0f} fps, {progress.effective_realtime_x:,.0f}x)"
                )
                next_checkpoint = min(next_checkpoint + args.checkpoint_digits, max_digits)
            else:
                write_progress(
                    progress_path,
                    progress_snapshot(
                        args.run_name,
                        args.digits,
                        args.rom,
                        digits_consumed,
                        start_digits,
                        frames_elapsed,
                        start_frames_elapsed,
                        args.checkpoint_digits,
                        started_at,
                        last_state,
                        input_config,
                    ),
                )
                if recorder is not None:
                    recorder.flush()
    finally:
        if recorder is not None:
            recorder.close()
        pyboy.stop()


if __name__ == "__main__":
    main()
