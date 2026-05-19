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

import sdl2
from PIL import Image, ImageTk
from pyboy import PyBoy

from run_pi_pyboy import PI_DIGITS, ROM, RUN_NAME, advance_pi_inputs, button_for_pair, latest_checkpoint


CHECKPOINT_RE = re.compile(r"checkpoint_(\d{8})_digits\.state$")


@dataclass
class Snapshot:
    digits_consumed: int
    frames_elapsed: int
    state: bytes


class AudioSink:
    def __init__(self, sample_rate: int) -> None:
        self.device = 0
        if sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_AUDIO) != 0:
            return

        want = sdl2.SDL_AudioSpec(sample_rate, sdl2.AUDIO_S8, 2, 128)
        have = sdl2.SDL_AudioSpec(0, 0, 0, 0)
        self.device = sdl2.SDL_OpenAudioDevice(None, 0, want, have, 0)
        if self.device:
            sdl2.SDL_PauseAudioDevice(self.device, 0)

    def queue(self, pyboy: PyBoy, volume: int) -> None:
        if not self.device:
            return

        head = pyboy.sound.raw_buffer_head
        if head <= 0:
            return

        data = bytes(pyboy.sound.raw_buffer[:head])
        if volume < 100:
            scale = max(0, min(100, volume)) / 100
            data = bytes(max(-128, min(127, int(int.from_bytes(bytes([sample]), "little", signed=True) * scale))) & 0xFF for sample in data)
        sdl2.SDL_QueueAudio(self.device, data, len(data))

    def close(self) -> None:
        if self.device:
            sdl2.SDL_CloseAudioDevice(self.device)
            self.device = 0


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
        sound_volume: int,
        audio_sink: AudioSink | None,
        initial_image: Image.Image | None = None,
        rom_path: Path | None = None,
    ) -> None:
        self.pyboy = pyboy
        self.rom_path = rom_path
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
        self.paused = True
        self.pause_requested = False
        self.speed = 1
        self.speed_limiter_enabled = True
        self.status = "paused"
        self.inputs_sent = 0
        self.last_button = "-"
        self.latest_image = initial_image.copy() if initial_image is not None else None
        self.sound_volume = sound_volume
        self.audio_sink = audio_sink
        self._next_frame_time = time.perf_counter()
        self._lock = threading.Lock()
        self._rewind_digits_requested = 0
        self._fast_forward_target_digits: int | None = None
        self._auto_snapshots_enabled = True
        self._last_snapshot_digits = digits_consumed - rewind_interval_digits
        self._take_snapshot()
        if self.latest_image is None:
            self._capture_frame()

    def set_speed(self, speed: float) -> None:
        with self._lock:
            self.speed = max(1, min(1000, int(round(speed))))
            if self._fast_forward_target_digits is None:
                self.pyboy.set_emulation_speed(self.speed)

    def set_speed_limiter_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.speed_limiter_enabled = enabled
            self._next_frame_time = time.perf_counter()

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self.paused = paused
            if not paused:
                self.pause_requested = False
            self.status = "paused" if paused else "running"

    def toggle_pause_at_boundary(self) -> None:
        with self._lock:
            if self.paused:
                self.paused = False
                self.pause_requested = False
                self.status = "running"
            else:
                self.pause_requested = True
                self._fast_forward_target_digits = None
                self.pyboy.set_emulation_speed(self.speed)
                self.status = "pause pending"

    def request_rewind(self, digits: int) -> None:
        with self._lock:
            self._rewind_digits_requested = max(self._rewind_digits_requested, digits)
            self._fast_forward_target_digits = None
            self.pyboy.set_emulation_speed(self.speed)

    def request_fast_forward(self, digits: int) -> None:
        digits = max(2, digits)
        if digits % 2:
            digits -= 1
        with self._lock:
            target = min(self.max_digits, self.digits_consumed + digits)
            if target % 2:
                target -= 1
            if target <= self.digits_consumed:
                self.status = "complete" if self.digits_consumed >= self.max_digits else "paused"
                return
            self._fast_forward_target_digits = target
            self.pyboy.set_emulation_speed(0)
            self.paused = False
            self.pause_requested = False
            self.status = f"fast forwarding to {target:,} digits"

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
                "speed_limiter_enabled": "on" if self.speed_limiter_enabled else "off",
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
                    pause_requested = self.pause_requested
                    rewind_digits = self._rewind_digits_requested
                    self._rewind_digits_requested = 0
                    fast_forward_target = self._fast_forward_target_digits

                if rewind_digits:
                    self._rewind(rewind_digits)
                    continue

                if paused or pause_requested:
                    with self._lock:
                        if pause_requested:
                            self.paused = True
                            self.pause_requested = False
                            self.status = "paused"
                    time.sleep(1 / 30)
                    continue

                if self.digits_consumed >= self.max_digits:
                    with self._lock:
                        self.status = "complete"
                    self.pyboy.tick(1, True)
                    time.sleep(1 / 30)
                    continue

                if fast_forward_target is not None:
                    self._fast_forward_with_backend(fast_forward_target)
                    continue

                will_finish_fast_forward = (
                    fast_forward_target is not None
                    and self.digits_consumed + 2 >= fast_forward_target
                )
                pair = int(self.digits[self.digits_consumed : self.digits_consumed + 2])
                button = button_for_pair(pair)
                self.pyboy.button_press(button)
                self._tick_frames(self.hold_frames)
                self.pyboy.button_release(button)
                self._tick_frames(self.release_frames, force_final_render=will_finish_fast_forward)
                with self._lock:
                    self.digits_consumed += 2
                    self.frames_elapsed += self.frames_per_input
                    self.inputs_sent += 1
                    self.last_button = button
                    if fast_forward_target is not None and self.digits_consumed >= fast_forward_target:
                        self.paused = True
                        self._fast_forward_target_digits = None
                        self.pyboy.set_emulation_speed(self.speed)
                        self.status = "complete" if self.digits_consumed >= self.max_digits else "paused"
                        self._next_frame_time = time.perf_counter()

                if (
                    self._auto_snapshots_enabled
                    and self.digits_consumed - self._last_snapshot_digits >= self.rewind_interval_digits
                ):
                    self._take_snapshot()
        finally:
            if self.audio_sink:
                self.audio_sink.close()
            self.pyboy.stop()

    def _tick_frames(self, frames: int, force_final_render: bool = False) -> None:
        for frame_index in range(frames):
            with self._lock:
                fast_forwarding = self._fast_forward_target_digits is not None
            render_frame = not fast_forwarding or (force_final_render and frame_index == frames - 1)
            self.pyboy.tick(1, render_frame, not fast_forwarding)
            if self.audio_sink and not fast_forwarding:
                self.audio_sink.queue(self.pyboy, self.sound_volume)
            if render_frame:
                self._capture_frame()
            self._limit_frame_rate()

    def _fast_forward_with_backend(self, target_digits: int) -> None:
        with self._lock:
            start_digits = self.digits_consumed
            if self.paused or self.pause_requested or self._fast_forward_target_digits is None:
                return
            state_buffer = io.BytesIO()
            self.pyboy.save_state(state_buffer)

        target_digits = min(target_digits, self.max_digits)
        state_buffer.seek(0)
        simulator = PyBoy(
            str(self.rom_path or ROM),
            window="null",
            sound_emulated=False,
            no_input=False,
            ram_file=io.BytesIO(bytes(32768)),
            log_level="CRITICAL",
        )
        simulator.set_emulation_speed(0)
        try:
            simulator.load_state(state_buffer)
            digits_consumed, inputs_sent, last_button = advance_pi_inputs(
                simulator,
                self.digits,
                start_digits,
                target_digits,
                self.hold_frames,
                self.release_frames,
            )
            final_state = io.BytesIO()
            simulator.save_state(final_state)
        finally:
            simulator.stop()

        final_state.seek(0)
        self.pyboy.load_state(final_state)
        image = render_loaded_state(self.pyboy)
        with self._lock:
            self.digits_consumed = digits_consumed
            self.frames_elapsed += inputs_sent * self.frames_per_input
            self.inputs_sent += inputs_sent
            self.last_button = last_button
            self.paused = True
            self._fast_forward_target_digits = None
            self.pyboy.set_emulation_speed(self.speed)
            self.status = "complete" if self.digits_consumed >= self.max_digits else "paused"
            self._next_frame_time = time.perf_counter()
            self.latest_image = image
            self._auto_snapshots_enabled = False

    def _limit_frame_rate(self) -> None:
        with self._lock:
            speed = self.speed
            enabled = self.speed_limiter_enabled
            fast_forwarding = self._fast_forward_target_digits is not None
        if speed <= 0 or not enabled or fast_forwarding:
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
            if target % 2:
                target -= 1
            candidates = [snapshot for snapshot in self.snapshots if snapshot.digits_consumed <= target]
            snapshot = candidates[-1] if candidates else self.snapshots[0]
            self.pyboy.load_state(io.BytesIO(snapshot.state))
            snapshot_digits = snapshot.digits_consumed
            snapshot_frames = snapshot.frames_elapsed
            self._last_snapshot_digits = snapshot.digits_consumed
            self._fast_forward_target_digits = None
            self.pyboy.set_emulation_speed(self.speed)
        digits_consumed, inputs_sent, last_button = advance_pi_inputs(
            self.pyboy,
            self.digits,
            snapshot_digits,
            target,
            self.hold_frames,
            self.release_frames,
        )
        image = render_loaded_state(self.pyboy)
        with self._lock:
            self.digits_consumed = digits_consumed
            self.frames_elapsed = snapshot_frames + inputs_sent * self.frames_per_input
            if inputs_sent:
                self.last_button = last_button
            self.status = f"rewound to {digits_consumed:,} digits"
            self.latest_image = image

    def _capture_frame(self) -> None:
        image = self.pyboy.screen.image.copy()
        with self._lock:
            self.latest_image = image

    def frame_image(self) -> Image.Image | None:
        with self._lock:
            return self.latest_image.copy() if self.latest_image is not None else None

    def upcoming_buttons(self, count: int = 12) -> list[tuple[int, str, str]]:
        with self._lock:
            start = self.digits_consumed

        buttons = []
        for offset in range(0, count * 2, 2):
            digit_index = start + offset
            if digit_index + 1 >= self.max_digits:
                break
            pair = self.digits[digit_index : digit_index + 2]
            buttons.append((digit_index, pair, button_for_pair(int(pair))))
        return buttons


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


def build_control_panel(session: ReviewSession, scale: int) -> tk.Tk:
    root = tk.Tk()
    root.title("piPokemon review")
    root.resizable(False, False)

    status_var = tk.StringVar()
    speed_var = tk.DoubleVar(value=math.log10(max(1, session.speed)))
    speed_limiter_var = tk.BooleanVar(value=True)

    screen_label = ttk.Label(root)
    screen_label.grid(row=0, column=0, columnspan=4, padx=10, pady=(10, 6))

    preview_frame = ttk.LabelFrame(root, text="Next")
    preview_frame.grid(row=0, column=4, rowspan=6, padx=(0, 10), pady=10, sticky="ns")
    preview_labels = []
    for index in range(12):
        label = ttk.Label(preview_frame, width=16, anchor="w")
        label.grid(row=index, column=0, padx=8, pady=2, sticky="w")
        preview_labels.append(label)

    ttk.Label(root, textvariable=status_var, width=62).grid(row=1, column=0, columnspan=4, padx=10, pady=(0, 4))

    def speed_changed(value: str) -> None:
        session.set_speed(10 ** float(value))

    def speed_limiter_changed() -> None:
        session.set_speed_limiter_enabled(speed_limiter_var.get())

    ttk.Label(root, text="Speed").grid(row=2, column=0, padx=(10, 4), sticky="w")
    speed_slider = ttk.Scale(root, from_=0, to=3, variable=speed_var, command=speed_changed, length=320)
    speed_slider.grid(row=2, column=1, columnspan=3, padx=(0, 10), pady=4, sticky="ew")
    for column, label in enumerate(("1x", "10x", "100x", "1000x"), start=1):
        ttk.Label(root, text=label).grid(row=3, column=column - 1, padx=4, pady=(0, 4))
    rewind_digits_var = tk.StringVar(value="1000")

    def toggle_pause() -> None:
        session.toggle_pause_at_boundary()

    ttk.Checkbutton(root, text="Use speed slider", variable=speed_limiter_var, command=speed_limiter_changed).grid(
        row=4, column=0, columnspan=2, padx=10, pady=(2, 4), sticky="w"
    )

    ttk.Button(root, text="Pause/Resume", command=toggle_pause).grid(row=5, column=0, padx=10, pady=8)
    rewind_menu = ttk.Combobox(
        root,
        textvariable=rewind_digits_var,
        values=("10", "100", "1000", "10000", "100000", "1000000"),
        width=10,
        state="readonly",
    )
    rewind_menu.grid(row=5, column=1, padx=4, pady=8)
    ttk.Button(root, text="Rewind Digits", command=lambda: session.request_rewind(int(rewind_digits_var.get()))).grid(
        row=5, column=2, padx=4, pady=8
    )
    ttk.Button(root, text="Quit", command=lambda: (session.stop(), root.destroy())).grid(row=5, column=3, padx=10, pady=8)

    def refresh_screen() -> None:
        image = session.frame_image()
        if image is not None:
            scaled = image.resize((160 * scale, 144 * scale), Image.Resampling.NEAREST)
            photo = ImageTk.PhotoImage(scaled)
            screen_label.configure(image=photo)
            screen_label.image = photo
        root.after(33, refresh_screen)

    def refresh_status() -> None:
        info = session.info()
        status_var.set(
            f"{info['status']} | {info['digits_consumed']:,}/{info['max_digits']:,} digits | "
            f"{info['speed']}x ({info['speed_limiter_enabled']}) | inputs sent: {info['inputs_sent']:,} | "
            f"last: {info['last_button']} | rewind snapshots: {info['snapshots']}"
        )
        root.after(250, refresh_status)

    def refresh_preview() -> None:
        upcoming = session.upcoming_buttons(len(preview_labels))
        for index, label in enumerate(preview_labels):
            if index < len(upcoming):
                digit_index, pair, button = upcoming[index]
                prefix = ">" if index == 0 else " "
                label.configure(text=f"{prefix} {digit_index:07d}  {pair} -> {button.upper()}")
            else:
                label.configure(text="")
        root.after(250, refresh_preview)

    root.protocol("WM_DELETE_WINDOW", lambda: (session.stop(), root.destroy()))
    refresh_status()
    refresh_screen()
    refresh_preview()
    return root


def render_loaded_state(pyboy: PyBoy) -> Image.Image:
    restore_buffer = io.BytesIO()
    pyboy.save_state(restore_buffer)
    restore_buffer.seek(0)
    pyboy.tick(1, True, True)
    image = pyboy.screen.image.copy()
    restore_buffer.seek(0)
    pyboy.load_state(restore_buffer)
    return image


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
    parser.add_argument("--start-running", action="store_true")
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
        window="null",
        sound_emulated=True,
        sound_volume=args.sound_volume,
        sound_sample_rate=args.sound_sample_rate,
        no_input=False,
        ram_file=io.BytesIO(bytes(32768)),
        log_level="CRITICAL",
    )
    with checkpoint.open("rb") as state_file:
        pyboy.load_state(state_file)
    initial_image = render_loaded_state(pyboy)

    session = ReviewSession(
        pyboy=pyboy,
        digits=digits,
        digits_consumed=start_digits,
        max_digits=max_digits,
        hold_frames=args.hold_frames,
        release_frames=args.release_frames,
        rewind_interval_digits=args.rewind_interval_digits,
        rewind_history_digits=args.rewind_history_digits,
        sound_volume=args.sound_volume,
        audio_sink=AudioSink(args.sound_sample_rate),
        initial_image=initial_image,
        rom_path=args.rom,
    )
    session.set_speed(args.speed)
    if args.start_running:
        session.set_paused(False)

    emulator_thread = threading.Thread(target=session.run, name="pyboy-review", daemon=True)
    emulator_thread.start()

    control_panel = build_control_panel(session, args.scale)
    control_panel.mainloop()
    session.stop()
    emulator_thread.join(timeout=5)


if __name__ == "__main__":
    main()
