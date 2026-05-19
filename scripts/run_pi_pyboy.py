from __future__ import annotations

import argparse
import io
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from pyboy import PyBoy


ROM = Path("roms/Pokemon - Red Version (USA, Europe) (SGB Enhanced).gb")
PI_DIGITS = Path("data/pi_10m_digits.txt")
RUN_NAME = "pi_10m_two_digit"
GAMEBOY_FPS = 4194304 / 70224
INPUT_CONFIG = Path("config/pi_input.json")
VALID_BUTTONS = {"a", "b", "start", "select", "up", "down", "left", "right"}


@dataclass(frozen=True)
class ButtonRange:
    minimum: int
    maximum: int
    button: str


@dataclass(frozen=True)
class PiInputConfig:
    on_frames: int
    off_frames: int
    digits_per_input: int
    mapping: tuple[ButtonRange, ...]


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

    max_value = (10**digits_per_input) - 1
    seen: set[int] = set()
    ranges: list[ButtonRange] = []
    for entry in raw["mapping"]:
        minimum = int(entry["min"])
        maximum = int(entry["max"])
        button = str(entry["button"]).lower()
        if button not in VALID_BUTTONS:
            raise ValueError(f"Unsupported button in config: {button}")
        if minimum < 0 or maximum > max_value or minimum > maximum:
            raise ValueError(f"Invalid mapping range: {minimum}-{maximum}")
        for value in range(minimum, maximum + 1):
            if value in seen:
                raise ValueError(f"Overlapping mapping value: {value}")
            seen.add(value)
        ranges.append(ButtonRange(minimum=minimum, maximum=maximum, button=button))

    missing = set(range(max_value + 1)) - seen
    if missing:
        raise ValueError(f"Mapping does not cover {len(missing)} values for {digits_per_input} digits per input")

    return PiInputConfig(
        on_frames=on_frames,
        off_frames=off_frames,
        digits_per_input=digits_per_input,
        mapping=tuple(ranges),
    )


def button_for_value(value: int, input_config: PiInputConfig) -> str:
    for button_range in input_config.mapping:
        if button_range.minimum <= value <= button_range.maximum:
            return button_range.button
    raise ValueError(f"No button mapping for value {value}")


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
) -> tuple[int, int, str]:
    config = input_config or load_input_config()
    digits_per_input = config.digits_per_input
    digits_consumed = start_digits
    inputs_sent = 0
    last_button = "-"
    while digits_consumed < target_digits:
        value = int(digits[digits_consumed : digits_consumed + digits_per_input])
        button = button_for_value(value, config)
        finishing = digits_consumed + digits_per_input >= target_digits
        pyboy.button_press(button)
        pyboy.tick(hold_frames, False, False)
        pyboy.button_release(button)
        if release_frames:
            pyboy.tick(release_frames, render_final and finishing, False)
        digits_consumed += digits_per_input
        inputs_sent += 1
        last_button = button
    return digits_consumed, inputs_sent, last_button


def latest_checkpoint(checkpoint_dir: Path) -> tuple[int, Path] | None:
    pattern = re.compile(r"checkpoint_(\d{8})_digits\.state$")
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
    state_path = checkpoint_dir / f"checkpoint_{digits_consumed:08d}_digits.state"
    with state_path.open("wb") as state_file:
        pyboy.save_state(state_file)

    if save_screenshot:
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        restore_buffer = io.BytesIO()
        pyboy.save_state(restore_buffer)
        restore_buffer.seek(0)
        pyboy.tick(1, True)
        pyboy.screen.image.save(screenshot_dir / f"checkpoint_{digits_consumed:08d}_digits.png")
        restore_buffer.seek(0)
        pyboy.load_state(restore_buffer)

    return state_path


def write_progress(progress_path: Path, progress: Progress) -> None:
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(json.dumps(asdict(progress), indent=2), encoding="utf-8")


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
    parser.add_argument("--fresh", action="store_true", help="Ignore existing checkpoints and start from reset.")
    parser.add_argument("--no-screenshots", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_config = load_input_config(args.config)
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
        sound_emulated=False,
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
    digits_consumed = start_digits
    frames_per_input = hold_frames + release_frames
    frames_elapsed = (digits_consumed // input_config.digits_per_input) * frames_per_input
    started_at = time.perf_counter()
    last_state: Path | None = state_to_load

    try:
        while digits_consumed < max_digits:
            chunk_target = min(next_checkpoint, max_digits)
            digits_consumed, inputs_sent, _ = advance_pi_inputs(
                pyboy,
                digits,
                digits_consumed,
                chunk_target,
                hold_frames,
                release_frames,
                input_config=input_config,
            )
            frames_elapsed += inputs_sent * frames_per_input

            if digits_consumed >= next_checkpoint:
                last_state = save_checkpoint(
                    pyboy,
                    checkpoint_dir,
                    screenshot_dir,
                    digits_consumed,
                    save_screenshot=not args.no_screenshots,
                )
                elapsed = time.perf_counter() - started_at
                effective_fps = (digits_consumed - start_digits) / elapsed if elapsed else 0
                progress = Progress(
                    run_name=args.run_name,
                    digits_path=str(args.digits),
                    rom_path=str(args.rom),
                    digits_consumed=digits_consumed,
                    input_pairs_consumed=digits_consumed // input_config.digits_per_input,
                    frames_elapsed=frames_elapsed,
                    checkpoints_completed=digits_consumed // args.checkpoint_digits,
                    elapsed_seconds=elapsed,
                    effective_fps=effective_fps,
                    effective_realtime_x=effective_fps / GAMEBOY_FPS,
                    last_state=str(last_state),
                )
                write_progress(progress_path, progress)
                print(
                    f"checkpoint {digits_consumed:,}/{max_digits:,} digits "
                    f"({effective_fps:,.0f} fps, {effective_fps / GAMEBOY_FPS:,.0f}x)"
                )
                next_checkpoint = min(next_checkpoint + args.checkpoint_digits, max_digits)
    finally:
        pyboy.stop()


if __name__ == "__main__":
    main()
