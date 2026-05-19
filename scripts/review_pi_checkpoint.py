from __future__ import annotations

import argparse
import io
import math
import re
import threading
import time
import tkinter as tk
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk

from pyboy import PyBoy

from run_pi_pyboy import PI_DIGITS, ROM, RUN_NAME, button_for_pair, latest_checkpoint


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
        hold_frames: int,
        release_frames: int,
        rewind_interval_digits: int,
        rewind_history_digits: int,
    ) -> None:
        self.pyboy = pyboy
        self.digits = digits
        self.digits_consumed = digits_consumed
        self.max_digits = max_digits
        self.hold_frames = hold_frames
        self.release_frames = release_frames
        self.frames_per_input = hold_frames + release_frames
        self.frames_elapsed = (digits_consumed // 2) * self.frames_per_input
        self.rewind_interval_digits = rewind_interval_digits
        self.max_snapshots = max(2, rewind_history_digits // rewind_interval_digits)
        self.snapshots: deque[Snapshot] = deque(maxlen=self.max_snapshots)
        self.running = True
        self.paused = False
        self.speed = 1
        self.status = "running"
        self.inputs_sent = 0
        self.last_button = "-"
        self._next_frame_time = time.perf_counter()
        self._lock = threading.Lock()
        self._rewind_digits_requested = 0
        self._last_snapshot_digits = digits_consumed - rewind_interval_digits
        self._take_snapshot()

    def set_speed(self, speed: float) -> None:
        with self._lock:
            self.speed = max(1, min(100, int(round(speed))))
            self.pyboy.set_emulation_speed(self.speed)

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self.paused = paused
            self.status = "paused" if paused else "running"

    def request_rewind(self, digits: int) -> None:
        with self._lock:
            self._rewind_digits_requested = max(self._rewind_digits_requested, digits)

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
                "inputs_sent": self.inputs_sent,
                "last_button": self.last_button,
            }

    def run(self) -> None:
        self.pyboy.set_emulation_speed(self.speed)
        try:
            while True:
                with self._lock:
                    if not self.running:
                        break
                    paused = self.paused
                    rewind_digits = self._rewind_digits_requested
                    self._rewind_digits_requested = 0

                if rewind_digits:
                    self._rewind(rewind_digits)
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
                button = button_for_pair(pair)
                self.pyboy.button_press(button)
                self._tick_frames(self.hold_frames)
                self.pyboy.button_release(button)
                self._tick_frames(self.release_frames)
                with self._lock:
                    self.digits_consumed += 2
                    self.frames_elapsed += self.frames_per_input
                    self.inputs_sent += 1
                    self.last_button = button

                if self.digits_consumed - self._last_snapshot_digits >= self.rewind_interval_digits:
                    self._take_snapshot()
        finally:
            self.pyboy.stop()

    def _tick_frames(self, frames: int) -> None:
        for _ in range(frames):
            self.pyboy.tick(1, True, True)
            self._limit_frame_rate()

    def _limit_frame_rate(self) -> None:
        with self._lock:
            speed = self.speed
        if speed <= 0:
            return

        now = time.perf_counter()
        if self._next_frame_time < now - 0.25:
            self._next_frame_time = now
        self._next_frame_time += 1 / (60 * speed)
        delay = self._next_frame_time - time.perf_counter()
        if delay > 0:
            time.sleep(delay)

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
            self._last_snapshot_digits = self.digits_consumed

    def _rewind(self, digits: int) -> None:
        with self._lock:
            target = max(0, self.digits_consumed - digits)
            candidates = [snapshot for snapshot in self.snapshots if snapshot.digits_consumed <= target]
            snapshot = candidates[-1] if candidates else self.snapshots[0]
            self.pyboy.load_state(io.BytesIO(snapshot.state))
            self.digits_consumed = snapshot.digits_consumed
            self.frames_elapsed = snapshot.frames_elapsed
            self.status = f"rewound to {snapshot.digits_consumed:,} digits"
            self._last_snapshot_digits = snapshot.digits_consumed


def checkpoint_digits(path: Path, explicit_digits: int | None) -> int:
    if explicit_digits is not None:
        return explicit_digits
    match = CHECKPOINT_RE.match(path.name)
    if not match:
        raise ValueError("Could not infer digit count from checkpoint name. Pass --digits-consumed.")
    return int(match.group(1))


def resolve_checkpoint(run_name: str, checkpoint: str, max_digits: int | None = None) -> Path:
    checkpoint_dir = Path("saves") / run_name
    if checkpoint == "latest":
        candidates = []
        for candidate in checkpoint_dir.glob("checkpoint_*_digits.state"):
            match = CHECKPOINT_RE.match(candidate.name)
            if match:
                digits_consumed = int(match.group(1))
                if max_digits is None or digits_consumed < max_digits:
                    candidates.append((digits_consumed, candidate))
        if not candidates:
            raise FileNotFoundError(f"No checkpoints found in {checkpoint_dir}")
        return max(candidates)[1]

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
    speed_var = tk.DoubleVar(value=math.log10(max(1, session.speed)))

    ttk.Label(root, textvariable=status_var, width=52).grid(row=0, column=0, columnspan=4, padx=10, pady=(10, 4))

    def speed_changed(value: str) -> None:
        session.set_speed(10 ** float(value))

    ttk.Label(root, text="Speed").grid(row=1, column=0, padx=(10, 4), sticky="w")
    speed_slider = ttk.Scale(root, from_=0, to=2, variable=speed_var, command=speed_changed, length=320)
    speed_slider.grid(row=1, column=1, columnspan=3, padx=(0, 10), pady=4, sticky="ew")
    rewind_digits_var = tk.StringVar(value="1000")

    def toggle_pause() -> None:
        info = session.info()
        session.set_paused(info["status"] != "paused")

    ttk.Button(root, text="Pause/Resume", command=toggle_pause).grid(row=2, column=0, padx=10, pady=8)
    rewind_menu = ttk.Combobox(
        root,
        textvariable=rewind_digits_var,
        values=("10", "100", "1000", "10000", "100000", "1000000"),
        width=10,
        state="readonly",
    )
    rewind_menu.grid(row=2, column=1, padx=4, pady=8)
    ttk.Button(root, text="Rewind Digits", command=lambda: session.request_rewind(int(rewind_digits_var.get()))).grid(
        row=2, column=2, padx=4, pady=8
    )
    ttk.Button(root, text="Quit", command=lambda: (session.stop(), root.destroy())).grid(row=2, column=3, padx=10, pady=8)

    def refresh_status() -> None:
        info = session.info()
        status_var.set(
            f"{info['status']} | {info['digits_consumed']:,}/{info['max_digits']:,} digits | "
            f"{info['speed']}x | inputs sent: {info['inputs_sent']:,} | "
            f"last: {info['last_button']} | rewind snapshots: {info['snapshots']}"
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
    parser.add_argument("--hold-frames", type=int, default=2)
    parser.add_argument("--release-frames", type=int, default=1)
    parser.add_argument("--scale", type=int, default=4)
    parser.add_argument("--sound-volume", type=int, default=100)
    parser.add_argument("--sound-sample-rate", type=int, default=48000)
    parser.add_argument("--rewind-history-digits", type=int, default=1_000_000)
    parser.add_argument("--rewind-interval-digits", type=int, default=100)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.hold_frames < 1:
        raise ValueError("--hold-frames must be at least 1")
    if args.release_frames < 0:
        raise ValueError("--release-frames must be at least 0")
    if args.rewind_interval_digits < 2:
        raise ValueError("--rewind-interval-digits must be at least 2")
    if args.rewind_history_digits < args.rewind_interval_digits:
        raise ValueError("--rewind-history-digits must be at least --rewind-interval-digits")

    digits = args.digits.read_text(encoding="ascii").strip()
    max_digits = min(args.max_digits or len(digits), len(digits))
    if max_digits % 2:
        max_digits -= 1
    checkpoint = resolve_checkpoint(args.run_name, args.checkpoint, max_digits=max_digits)
    start_digits = checkpoint_digits(checkpoint, args.digits_consumed)
    if start_digits >= max_digits:
        raise ValueError(
            f"Checkpoint is already at {start_digits:,} digits, but max is {max_digits:,}. "
            "Choose an earlier checkpoint or provide a larger digit file."
        )
    print(f"Reviewing {checkpoint} from {start_digits:,} to {max_digits:,} digits.")

    pyboy = PyBoy(
        str(args.rom),
        window="SDL2",
        scale=args.scale,
        sound_emulated=True,
        sound_volume=args.sound_volume,
        sound_sample_rate=args.sound_sample_rate,
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
        hold_frames=args.hold_frames,
        release_frames=args.release_frames,
        rewind_interval_digits=args.rewind_interval_digits,
        rewind_history_digits=args.rewind_history_digits,
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
