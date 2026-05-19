from __future__ import annotations

import argparse
import io
import re
import threading
import time
import tkinter as tk
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk

from pyboy import PyBoy

from run_pi_pyboy import GAMEBOY_FPS, PI_DIGITS, ROM, RUN_NAME, button_for_pair, latest_checkpoint


CHECKPOINT_RE = re.compile(r"checkpoint_(\d{8})_digits\.state$")


@dataclass
class Snapshot:
    digits_consumed: int
    frames_elapsed: int
    state: bytes


class ReviewSession:
    def __init__(
        self,
        pyboy: PyBoy,
        digits: str,
        digits_consumed: int,
        max_digits: int,
        rewind_interval_frames: int,
        rewind_history_frames: int,
    ) -> None:
        self.pyboy = pyboy
        self.digits = digits
        self.digits_consumed = digits_consumed
        self.max_digits = max_digits
        self.frames_elapsed = digits_consumed
        self.rewind_interval_frames = rewind_interval_frames
        self.max_snapshots = max(2, rewind_history_frames // rewind_interval_frames)
        self.snapshots: deque[Snapshot] = deque(maxlen=self.max_snapshots)
        self.running = True
        self.paused = False
        self.speed = 1
        self.status = "running"
        self._lock = threading.Lock()
        self._rewind_frames_requested = 0
        self._last_snapshot_frame = -rewind_interval_frames
        self._take_snapshot()

    def set_speed(self, speed: int) -> None:
        with self._lock:
            self.speed = max(0, speed)
            self.pyboy.set_emulation_speed(self.speed)

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self.paused = paused
            self.status = "paused" if paused else "running"

    def request_rewind(self, seconds: int) -> None:
        with self._lock:
            self._rewind_frames_requested = max(self._rewind_frames_requested, int(seconds * GAMEBOY_FPS))

    def stop(self) -> None:
        with self._lock:
            self.running = False

    def info(self) -> dict[str, int | str]:
        with self._lock:
            return {
                "digits_consumed": self.digits_consumed,
                "max_digits": self.max_digits,
                "frames_elapsed": self.frames_elapsed,
                "speed": self.speed,
                "status": self.status,
                "snapshots": len(self.snapshots),
            }

    def run(self) -> None:
        self.pyboy.set_emulation_speed(self.speed)
        try:
            while True:
                with self._lock:
                    if not self.running:
                        break
                    paused = self.paused
                    rewind_frames = self._rewind_frames_requested
                    self._rewind_frames_requested = 0

                if rewind_frames:
                    self._rewind(rewind_frames)
                    continue

                if paused:
                    self.pyboy.tick(1, True)
                    time.sleep(1 / 30)
                    continue

                if self.digits_consumed >= self.max_digits:
                    with self._lock:
                        self.status = "complete"
                    self.pyboy.tick(1, True)
                    time.sleep(1 / 30)
                    continue

                pair = int(self.digits[self.digits_consumed : self.digits_consumed + 2])
                self.pyboy.button(button_for_pair(pair))
                self.pyboy.tick(1, True)
                self.pyboy.tick(1, True)
                with self._lock:
                    self.digits_consumed += 2
                    self.frames_elapsed += 2

                if self.frames_elapsed - self._last_snapshot_frame >= self.rewind_interval_frames:
                    self._take_snapshot()
        finally:
            self.pyboy.stop()

    def _take_snapshot(self) -> None:
        buffer = io.BytesIO()
        self.pyboy.save_state(buffer)
        with self._lock:
            self.snapshots.append(
                Snapshot(
                    digits_consumed=self.digits_consumed,
                    frames_elapsed=self.frames_elapsed,
                    state=buffer.getvalue(),
                )
            )
            self._last_snapshot_frame = self.frames_elapsed

    def _rewind(self, frames: int) -> None:
        with self._lock:
            target = max(0, self.frames_elapsed - frames)
            candidates = [snapshot for snapshot in self.snapshots if snapshot.frames_elapsed <= target]
            snapshot = candidates[-1] if candidates else self.snapshots[0]
            self.pyboy.load_state(io.BytesIO(snapshot.state))
            self.digits_consumed = snapshot.digits_consumed
            self.frames_elapsed = snapshot.frames_elapsed
            self.status = f"rewound to {snapshot.digits_consumed:,} digits"
            self._last_snapshot_frame = snapshot.frames_elapsed


def checkpoint_digits(path: Path, explicit_digits: int | None) -> int:
    if explicit_digits is not None:
        return explicit_digits
    match = CHECKPOINT_RE.match(path.name)
    if not match:
        raise ValueError("Could not infer digit count from checkpoint name. Pass --digits-consumed.")
    return int(match.group(1))


def resolve_checkpoint(run_name: str, checkpoint: str) -> Path:
    checkpoint_dir = Path("saves") / run_name
    if checkpoint == "latest":
        latest = latest_checkpoint(checkpoint_dir)
        if latest is None:
            raise FileNotFoundError(f"No checkpoints found in {checkpoint_dir}")
        return latest[1]

    candidate = Path(checkpoint)
    if candidate.exists():
        return candidate

    if checkpoint.isdigit():
        candidate = checkpoint_dir / f"checkpoint_{int(checkpoint):08d}_digits.state"
        if candidate.exists():
            return candidate

    raise FileNotFoundError(f"Checkpoint not found: {checkpoint}")


def build_control_panel(session: ReviewSession) -> tk.Tk:
    root = tk.Tk()
    root.title("piPokemon review controls")
    root.resizable(False, False)

    status_var = tk.StringVar()
    speed_var = tk.IntVar(value=session.speed)

    ttk.Label(root, textvariable=status_var, width=52).grid(row=0, column=0, columnspan=4, padx=10, pady=(10, 4))

    def speed_changed(value: str) -> None:
        session.set_speed(int(float(value)))

    ttk.Label(root, text="Speed").grid(row=1, column=0, padx=(10, 4), sticky="w")
    speed_slider = ttk.Scale(root, from_=0, to=600, variable=speed_var, command=speed_changed, length=320)
    speed_slider.grid(row=1, column=1, columnspan=3, padx=(0, 10), pady=4, sticky="ew")

    def toggle_pause() -> None:
        info = session.info()
        session.set_paused(info["status"] != "paused")

    ttk.Button(root, text="Pause/Resume", command=toggle_pause).grid(row=2, column=0, padx=10, pady=8)
    ttk.Button(root, text="Rewind 5s", command=lambda: session.request_rewind(5)).grid(row=2, column=1, padx=4, pady=8)
    ttk.Button(root, text="Rewind 30s", command=lambda: session.request_rewind(30)).grid(row=2, column=2, padx=4, pady=8)
    ttk.Button(root, text="Quit", command=lambda: (session.stop(), root.destroy())).grid(row=2, column=3, padx=10, pady=8)

    def refresh_status() -> None:
        info = session.info()
        status_var.set(
            f"{info['status']} | {info['digits_consumed']:,}/{info['max_digits']:,} digits | "
            f"{info['speed']}x | rewind snapshots: {info['snapshots']}"
        )
        root.after(250, refresh_status)

    root.protocol("WM_DELETE_WINDOW", lambda: (session.stop(), root.destroy()))
    refresh_status()
    return root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review a piPokemon PyBoy checkpoint with graphics, sound, speed, and rewind.")
    parser.add_argument("--rom", type=Path, default=ROM)
    parser.add_argument("--digits", type=Path, default=PI_DIGITS)
    parser.add_argument("--run-name", default=RUN_NAME)
    parser.add_argument("--checkpoint", default="latest", help="latest, a state path, or a digit count such as 5000000")
    parser.add_argument("--digits-consumed", type=int, default=None)
    parser.add_argument("--max-digits", type=int, default=None)
    parser.add_argument("--speed", type=int, default=1)
    parser.add_argument("--scale", type=int, default=4)
    parser.add_argument("--sound-volume", type=int, default=50)
    parser.add_argument("--rewind-history-seconds", type=int, default=300)
    parser.add_argument("--rewind-interval-frames", type=int, default=60)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    checkpoint = resolve_checkpoint(args.run_name, args.checkpoint)
    start_digits = checkpoint_digits(checkpoint, args.digits_consumed)
    digits = args.digits.read_text(encoding="ascii").strip()
    max_digits = min(args.max_digits or len(digits), len(digits))
    if max_digits % 2:
        max_digits -= 1

    pyboy = PyBoy(
        str(args.rom),
        window="SDL2",
        scale=args.scale,
        sound_emulated=True,
        sound_volume=args.sound_volume,
        no_input=False,
        ram_file=io.BytesIO(bytes(32768)),
        log_level="CRITICAL",
    )
    with checkpoint.open("rb") as state_file:
        pyboy.load_state(state_file)

    session = ReviewSession(
        pyboy=pyboy,
        digits=digits,
        digits_consumed=start_digits,
        max_digits=max_digits,
        rewind_interval_frames=args.rewind_interval_frames,
        rewind_history_frames=int(args.rewind_history_seconds * GAMEBOY_FPS),
    )
    session.set_speed(args.speed)

    emulator_thread = threading.Thread(target=session.run, name="pyboy-review", daemon=True)
    emulator_thread.start()

    control_panel = build_control_panel(session)
    control_panel.mainloop()
    session.stop()
    emulator_thread.join(timeout=5)


if __name__ == "__main__":
    main()
