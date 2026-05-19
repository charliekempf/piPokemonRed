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


def button_for_pair(value: int) -> str:
    if value <= 53:
        return "a"
    if value <= 63:
        return "up"
    if value <= 73:
        return "down"
    if value <= 83:
        return "left"
    if value <= 93:
        return "right"
    if value <= 98:
        return "b"
    return "start"


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
    parser.add_argument("--run-name", default=RUN_NAME)
    parser.add_argument("--checkpoint-digits", type=int, default=1_000_000)
    parser.add_argument("--hold-frames", type=int, default=2)
    parser.add_argument("--release-frames", type=int, default=1)
    parser.add_argument("--max-digits", type=int, default=None)
    parser.add_argument("--fresh", action="store_true", help="Ignore existing checkpoints and start from reset.")
    parser.add_argument("--no-screenshots", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.hold_frames < 1:
        raise ValueError("--hold-frames must be at least 1")
    if args.release_frames < 0:
        raise ValueError("--release-frames must be at least 0")

    digits = args.digits.read_text(encoding="ascii").strip()
    max_digits = min(args.max_digits or len(digits), len(digits))
    if max_digits % 2:
        max_digits -= 1

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
    frames_per_input = args.hold_frames + args.release_frames
    frames_elapsed = (digits_consumed // 2) * frames_per_input
    started_at = time.perf_counter()
    last_state: Path | None = state_to_load

    try:
        while digits_consumed < max_digits:
            pair = int(digits[digits_consumed : digits_consumed + 2])
            button = button_for_pair(pair)
            pyboy.button_press(button)
            pyboy.tick(args.hold_frames, False)
            pyboy.button_release(button)
            if args.release_frames:
                pyboy.tick(args.release_frames, False)
            digits_consumed += 2
            frames_elapsed += frames_per_input

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
                    input_pairs_consumed=digits_consumed // 2,
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
