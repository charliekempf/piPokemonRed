from __future__ import annotations

import argparse
import hashlib
import io
import json
import mimetypes
import re
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image
from pyboy import PyBoy

from review_pi_checkpoint import (
    AudioSink,
    REVIEW_CACHE_DIRNAME,
    ReviewSession,
    checkpoint_digits,
    render_loaded_state,
    resolve_checkpoint,
)
from run_pi_pyboy import (
    GAMEBOY_FPS,
    INPUT_CONFIG,
    PI_DIGITS,
    ROM,
    RUN_NAME,
    RUN_CONFIG_FILENAME,
    advance_pi_inputs,
    button_for_value,
    config_display_name,
    latest_checkpoint,
    load_input_config,
    resolve_configured_run_name,
    save_checkpoint,
)


WEB_ROOT = Path("web/review")
REVIEW_SESSION_STATE = Path("results") / "review_session_state.json"
RUN_PI_RE = re.compile(r"run_pi_pyboy\.py")
MAX_DIGITS_RE = re.compile(r"--max-digits\s+(\d+)")
RUN_NAME_RE = re.compile(r"--run-name\s+([^\s]+)")
VIDEO_EXPORT_PRESETS = {
    "mp4": {
        "label": "MP4",
        "extension": ".mp4",
        "input_pix_fmt": "rgb24",
        "ffmpeg_args": [],
        "audio_args": ["-c:a", "aac"],
    },
    "av1": {
        "label": "AV1",
        "extension": ".mkv",
        "input_pix_fmt": "gray",
        "ffmpeg_args": ["-c:v", "libaom-av1", "-usage", "realtime", "-cpu-used", "8", "-threads", "1", "-pix_fmt", "gray"],
        "audio_args": ["-c:a", "flac"],
    },
    "av1_lossless": {
        "label": "AV1 lossless",
        "extension": ".mkv",
        "input_pix_fmt": "gray",
        "ffmpeg_args": [
            "-c:v",
            "libaom-av1",
            "-usage",
            "realtime",
            "-cpu-used",
            "8",
            "-threads",
            "1",
            "-crf",
            "0",
            "-b:v",
            "0",
            "-pix_fmt",
            "gray",
        ],
        "audio_args": ["-c:a", "flac"],
    },
    "ffv1": {
        "label": "FFV1",
        "extension": ".mkv",
        "input_pix_fmt": "gray",
        "ffmpeg_args": ["-c:v", "ffv1", "-level", "3", "-pix_fmt", "gray"],
        "audio_args": ["-c:a", "flac"],
    },
    "prores": {
        "label": "ProRes 422 HQ",
        "extension": ".mov",
        "input_pix_fmt": "rgb24",
        "ffmpeg_args": ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"],
        "audio_args": ["-c:a", "pcm_s16le"],
    },
}


class RomMissingError(RuntimeError):
    pass


def read_review_session_state() -> dict[str, object]:
    if not REVIEW_SESSION_STATE.exists():
        return {}
    try:
        return json.loads(REVIEW_SESSION_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_review_session_state(run_name: str, digits_consumed: int) -> None:
    REVIEW_SESSION_STATE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"run_name": run_name, "digits_consumed": int(digits_consumed)}
    temp_path = REVIEW_SESSION_STATE.with_suffix(REVIEW_SESSION_STATE.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp_path.replace(REVIEW_SESSION_STATE)


def list_checkpoints(run_name: str) -> list[dict[str, int | str]]:
    checkpoint_dir = Path("saves") / run_name
    checkpoints: list[dict[str, int | str]] = []
    for checkpoint_path in checkpoint_dir.glob("checkpoint_*_digits.state"):
        try:
            digits = checkpoint_digits(checkpoint_path, None)
        except ValueError:
            continue
        checkpoints.append({"digits": digits, "filename": checkpoint_path.name})
    return sorted(checkpoints, key=lambda checkpoint: int(checkpoint["digits"]))


def seek_checkpoints(run_name: str) -> list[tuple[int, Path]]:
    checkpoint_dir = Path("saves") / run_name
    candidates: list[tuple[int, Path]] = []
    for source_dir in (checkpoint_dir, checkpoint_dir / REVIEW_CACHE_DIRNAME):
        for checkpoint_path in source_dir.glob("checkpoint_*_digits.state"):
            try:
                candidates.append((checkpoint_digits(checkpoint_path, None), checkpoint_path))
            except ValueError:
                continue
    return sorted(candidates, key=lambda candidate: candidate[0])


def checkpoint_at_or_before(run_name: str, target_digits: int) -> tuple[int, Path] | None:
    candidates = [candidate for candidate in seek_checkpoints(run_name) if candidate[0] <= target_digits]
    return max(candidates, key=lambda candidate: candidate[0]) if candidates else None


def list_runs(active_run_name: str) -> list[dict[str, object]]:
    runs: list[dict[str, object]] = []
    saves_root = Path("saves")
    if not saves_root.exists():
        return runs
    for run_dir in saves_root.iterdir():
        if not run_dir.is_dir():
            continue
        checkpoints = list_checkpoints(run_dir.name)
        config_path = run_dir / RUN_CONFIG_FILENAME
        if not checkpoints and not config_path.exists():
            continue
        label = run_dir.name
        config_available = config_path.exists()
        if config_available:
            try:
                config = load_input_config(config_path)
                label = f"{config_display_name(config_path)} ({config.digits_per_input}d, {config.on_frames}/{config.off_frames})"
            except Exception:
                config_available = False
        highest_digits = max((int(checkpoint["digits"]) for checkpoint in checkpoints), default=0)
        runs.append(
            {
                "name": run_dir.name,
                "label": label,
                "checkpoint_count": len(checkpoints),
                "highest_digits": highest_digits,
                "config_available": config_available,
                "active": run_dir.name == active_run_name,
            }
        )
    return sorted(runs, key=lambda run: (str(run["label"]).casefold(), str(run["name"]).casefold()))


def config_info(config_path: Path) -> dict[str, object]:
    config = load_input_config(config_path)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    game = raw_config.get("game", {})
    if not isinstance(game, dict):
        game = {}
    total_values = 10**config.digits_per_input
    return {
        "name": config_display_name(config_path),
        "game": {
            "title": str(game.get("title", "")).strip(),
            "version": str(game.get("version", "")).strip(),
            "region": str(game.get("region", "")).strip(),
        },
        "digits_per_input": config.digits_per_input,
        "on_frames": config.on_frames,
        "off_frames": config.off_frames,
        "mapping": [
            {
                "min": button_range.minimum,
                "max": button_range.maximum,
                "button": button_range.button,
                "count": button_range.maximum - button_range.minimum + 1,
                "percent": ((button_range.maximum - button_range.minimum + 1) / total_values) * 100,
            }
            for button_range in config.mapping
        ],
    }


def load_checkpoint_screenshot(run_name: str, digits_consumed: int) -> Image.Image | None:
    screenshot_path = (
        Path("results")
        / run_name
        / "screenshots"
        / f"checkpoint_{digits_consumed}_digits.png"
    )
    if not screenshot_path.exists():
        return None
    with Image.open(screenshot_path) as image:
        return image.convert("RGB").copy()


def image_to_png(image: Image.Image | None, scale: int) -> bytes:
    if image is None:
        image = Image.new("RGB", (160, 144), "black")
    if scale != 1:
        image = image.resize((160 * scale, 144 * scale), Image.Resampling.NEAREST)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def image_to_rgba(image: Image.Image | None) -> bytes:
    if image is None:
        image = Image.new("RGBA", (160, 144), "black")
    elif image.mode != "RGBA":
        image = image.convert("RGBA")
    return image.tobytes()


def read_progress(run_name: str) -> dict[str, object]:
    progress_path = Path("results") / run_name / "progress.json"
    if not progress_path.exists():
        return {}
    try:
        return json.loads(progress_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def running_chart_target(run_name: str) -> int:
    if sys.platform != "win32":
        return 0
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | "
                "Where-Object { ($_.Name -in @('py.exe','python.exe','pythonw.exe')) -and "
                "($_.CommandLine -match 'run_pi_pyboy\\.py') } | "
                "Select-Object -ExpandProperty CommandLine",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    targets = []
    for command_line in result.stdout.splitlines():
        if not RUN_PI_RE.search(command_line):
            continue
        run_match = RUN_NAME_RE.search(command_line)
        if run_match and run_match.group(1) != run_name:
            continue
        max_match = MAX_DIGITS_RE.search(command_line)
        if max_match:
            targets.append(int(max_match.group(1)))
    return max(targets, default=0)


def stop_running_chart_processes(run_name: str) -> int:
    if sys.platform != "win32":
        return 0
    try:
        command = (
            "$stopped = 0; "
            "Get-CimInstance Win32_Process | "
            "Where-Object { ($_.Name -in @('py.exe','python.exe','pythonw.exe')) -and "
            "($_.CommandLine -match 'run_pi_pyboy\\.py') } | "
            f"Where-Object {{ $_.CommandLine -match '--run-name\\s+{re.escape(run_name)}(\\s|$)' }} | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $stopped++ }; "
            "Write-Output $stopped"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    try:
        return int((result.stdout.strip().splitlines() or ["0"])[-1])
    except ValueError:
        return 0


def safe_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return cleaned or "export"


def normalize_digit(value: int, digits_per_input: int) -> int:
    value = max(0, int(value))
    if value % digits_per_input:
        value -= value % digits_per_input
    return value


def image_bytes_for_pix_fmt(pyboy: PyBoy, pix_fmt: str) -> bytes:
    image = pyboy.screen.image
    if pix_fmt == "gray":
        return image.convert("L").tobytes()
    return image.convert("RGB").tobytes()


def audio_bytes_for_pyboy(pyboy: PyBoy, target_bytes: int) -> bytes:
    head = pyboy.sound.raw_buffer_head
    if head <= 0:
        return bytes(target_bytes)

    data = bytes(pyboy.sound.raw_buffer[:head])
    if len(data) < target_bytes:
        return data + bytes(target_bytes - len(data))
    if len(data) > target_bytes:
        return data[:target_bytes]
    return data


def tail_text(path: Path, limit: int = 4000) -> str:
    if not path.exists():
        return ""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return data[-limit:].decode("utf-8", errors="replace").strip()


def ffmpeg_failure_message(process: subprocess.Popen[bytes], stderr_path: Path, fallback: BaseException) -> str:
    try:
        return_code = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        return_code = process.poll()
    details = tail_text(stderr_path)
    if details:
        return f"ffmpeg pipe closed with return code {return_code}: {details}"
    return f"ffmpeg pipe closed with return code {return_code}: {fallback}"


def run_video_export(
    app: "ReviewWebApp",
    start_digits: int,
    end_digits: int,
    preset_name: str,
    output_path: Path,
) -> None:
    preset = VIDEO_EXPORT_PRESETS[preset_name]
    input_config = load_input_config(app.config_path)
    checkpoint = checkpoint_at_or_before(app.run_name, start_digits)
    if checkpoint is None:
        raise RuntimeError("No checkpoint before export start.")

    checkpoint_digits_consumed, checkpoint_path = checkpoint
    frame_count = ((end_digits - start_digits) // input_config.digits_per_input) * (
        input_config.on_frames + input_config.off_frames
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_video_path = output_path.with_suffix(".video" + output_path.suffix)
    temp_audio_path = output_path.with_suffix(".audio.s8")
    temp_stderr_path = output_path.with_suffix(".ffmpeg.log")
    temp_output_path = output_path.with_suffix(".tmp" + output_path.suffix)
    for temp_path in (temp_video_path, temp_audio_path, temp_stderr_path, temp_output_path):
        temp_path.unlink(missing_ok=True)

    command = [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-f",
        "rawvideo",
        "-pix_fmt",
        str(preset["input_pix_fmt"]),
        "-s",
        "160x144",
        "-r",
        f"{GAMEBOY_FPS:.6f}",
        "-i",
        "pipe:0",
        "-an",
        *list(preset["ffmpeg_args"]),
        str(temp_video_path),
    ]

    pyboy = PyBoy(
        str(app.rom_path),
        window="null",
        sound_emulated=True,
        sound_sample_rate=48000,
        no_input=False,
        ram_file=io.BytesIO(bytes(32768)),
        log_level="CRITICAL",
    )
    pyboy.set_emulation_speed(0)
    process: subprocess.Popen[bytes] | None = None
    stderr_file = None
    frames_written = 0
    digits_consumed = checkpoint_digits_consumed
    audio_sample_rate = 48000
    audio_channels = 2
    audio_sample_credit = 0.0
    try:
        with checkpoint_path.open("rb") as state_file:
            pyboy.load_state(state_file)

        if digits_consumed < start_digits:
            digits_consumed, _, _ = advance_pi_inputs(
                pyboy,
                app.digits,
                digits_consumed,
                start_digits,
                input_config.on_frames,
                input_config.off_frames,
                input_config=input_config,
            )

        stderr_file = temp_stderr_path.open("wb")
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=stderr_file,
            cwd=Path.cwd(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if process.stdin is None:
            raise RuntimeError("Could not open ffmpeg stdin.")

        with temp_audio_path.open("wb") as audio_file:
            while digits_consumed < end_digits:
                value = int(app.digits[digits_consumed : digits_consumed + input_config.digits_per_input])
                button = button_for_value(value, input_config)
                pyboy.button_press(button)
                for _ in range(input_config.on_frames):
                    pyboy.tick(1, True, True)
                    audio_sample_credit += audio_sample_rate / GAMEBOY_FPS
                    frame_samples = int(audio_sample_credit)
                    audio_sample_credit -= frame_samples
                    audio_file.write(audio_bytes_for_pyboy(pyboy, frame_samples * audio_channels))
                    try:
                        process.stdin.write(image_bytes_for_pix_fmt(pyboy, str(preset["input_pix_fmt"])))
                    except BrokenPipeError as error:
                        raise RuntimeError(ffmpeg_failure_message(process, temp_stderr_path, error)) from error
                    frames_written += 1
                pyboy.button_release(button)
                for _ in range(input_config.off_frames):
                    pyboy.tick(1, True, True)
                    audio_sample_credit += audio_sample_rate / GAMEBOY_FPS
                    frame_samples = int(audio_sample_credit)
                    audio_sample_credit -= frame_samples
                    audio_file.write(audio_bytes_for_pyboy(pyboy, frame_samples * audio_channels))
                    try:
                        process.stdin.write(image_bytes_for_pix_fmt(pyboy, str(preset["input_pix_fmt"])))
                    except BrokenPipeError as error:
                        raise RuntimeError(ffmpeg_failure_message(process, temp_stderr_path, error)) from error
                    frames_written += 1
                digits_consumed += input_config.digits_per_input
                if frames_written % 600 == 0:
                    app.update_video_export(
                        state="Exporting",
                        start_digits=start_digits,
                        end_digits=end_digits,
                        current_digits=digits_consumed,
                        frames_written=frames_written,
                        total_frames=frame_count,
                        output_path=str(output_path),
                        preset=preset_name,
                    )

        process.stdin.close()
        return_code = process.wait(timeout=30)
        if stderr_file is not None:
            stderr_file.close()
            stderr_file = None
        if return_code != 0:
            details = tail_text(temp_stderr_path)
            raise RuntimeError(f"ffmpeg failed with exit code {return_code}: {details}")
        if not temp_audio_path.exists() or temp_audio_path.stat().st_size <= 0:
            raise RuntimeError("Export completed without audio samples.")

        app.update_video_export(
            state="Muxing audio",
            start_digits=start_digits,
            end_digits=end_digits,
            current_digits=end_digits,
            frames_written=frames_written,
            total_frames=frame_count,
            output_path=str(output_path),
            preset=preset_name,
        )
        mux_command = [
            "ffmpeg",
            "-y",
            "-nostdin",
            "-i",
            str(temp_video_path),
            "-f",
            "s8",
            "-ar",
            str(audio_sample_rate),
            "-ac",
            str(audio_channels),
            "-i",
            str(temp_audio_path),
            "-c:v",
            "copy",
            *list(preset["audio_args"]),
            "-shortest",
            str(temp_output_path),
        ]
        mux_result = subprocess.run(
            mux_command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=Path.cwd(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            check=False,
        )
        if mux_result.returncode != 0:
            raise RuntimeError(f"ffmpeg audio mux failed with exit code {mux_result.returncode}")
        temp_output_path.replace(output_path)
        app.update_video_export(
            state="Complete",
            start_digits=start_digits,
            end_digits=end_digits,
            current_digits=end_digits,
            frames_written=frames_written,
            total_frames=frame_count,
            output_path=str(output_path),
            preset=preset_name,
        )
    finally:
        if process is not None and process.poll() is None:
            if process.stdin:
                try:
                    process.stdin.close()
                except OSError:
                    pass
            process.terminate()
        pyboy.stop()
        if stderr_file is not None:
            stderr_file.close()
        temp_video_path.unlink(missing_ok=True)
        temp_audio_path.unlink(missing_ok=True)
        temp_stderr_path.unlink(missing_ok=True)
        temp_output_path.unlink(missing_ok=True)


class ReviewWebApp:
    def __init__(
        self,
        session: ReviewSession | None,
        scale: int,
        run_name: str,
        digits_per_input: int,
        frames_per_input: int,
        hard_max_digits: int | None,
        rom_path: Path,
        digits_path: Path,
        digits: str,
        config_path: Path,
        session_factory,
    ) -> None:
        self.session = session
        self.scale = scale
        self.run_name = run_name
        self.digits_per_input = digits_per_input
        self.frames_per_input = frames_per_input
        self.hard_max_digits = hard_max_digits
        self.rom_path = rom_path
        self.digits_path = digits_path
        self.digits = digits
        self.config_path = config_path
        self.session_factory = session_factory
        self.emulator_thread: threading.Thread | None = None
        self.chart_simulation: subprocess.Popen[bytes] | None = None
        self.chart_target_digits = 0
        self.video_export_thread: threading.Thread | None = None
        self.video_export_status: dict[str, object] = {"state": "Ready"}
        self._last_saved_run_name = ""
        self._last_saved_digits = -1
        self.frame_version = 0
        self._last_frame_digest = ""
        self._lock = threading.Lock()

    @property
    def rom_missing(self) -> bool:
        return not self.rom_path.exists()

    def start_emulator_thread(self) -> None:
        if self.session is None:
            return
        if self.emulator_thread is not None and self.emulator_thread.is_alive():
            return
        self.emulator_thread = threading.Thread(target=self.session.run, name="pyboy-web-review", daemon=True)
        self.emulator_thread.start()

    def install_rom(self, rom_bytes: bytes) -> None:
        self.rom_path.parent.mkdir(parents=True, exist_ok=True)
        self.rom_path.write_bytes(rom_bytes)
        with self._lock:
            if self.session is None:
                try:
                    self.session = self.session_factory()
                except Exception:
                    self.rom_path.unlink(missing_ok=True)
                    raise
                self.start_emulator_thread()

    def select_run(self, run_name: str) -> None:
        run_name = str(run_name)
        config_path = Path("saves") / run_name / RUN_CONFIG_FILENAME
        if not config_path.exists():
            raise ValueError(f"Run {run_name} does not have {RUN_CONFIG_FILENAME}.")

        input_config = load_input_config(config_path)
        session = self.session_factory(run_name, config_path, input_config, "penultimate", None)
        old_session: ReviewSession | None = None
        old_thread: threading.Thread | None = None
        with self._lock:
            if run_name == self.run_name:
                session.stop()
                return
            old_session = self.session
            old_thread = self.emulator_thread
            self.run_name = run_name
            self.config_path = config_path
            self.digits_per_input = input_config.digits_per_input
            self.frames_per_input = input_config.on_frames + input_config.off_frames
            self.session = session
            self.emulator_thread = None
            self.chart_simulation = None
            self.chart_target_digits = 0
            self.video_export_thread = None
            self.video_export_status = {"state": "Ready"}
            self.frame_version = 0
            self._last_frame_digest = ""

        if old_session is not None:
            old_session.stop()
        if old_thread is not None and old_thread.is_alive():
            old_thread.join(timeout=2)
        self.start_emulator_thread()

    def start_chart_simulation(self, target_digits: int, checkpoint_interval_digits: int) -> int:
        target_digits = max(0, int(target_digits))
        checkpoint_interval_digits = max(self.digits_per_input, int(checkpoint_interval_digits))
        if checkpoint_interval_digits % self.digits_per_input:
            checkpoint_interval_digits -= checkpoint_interval_digits % self.digits_per_input
        if target_digits % self.digits_per_input:
            target_digits -= target_digits % self.digits_per_input
        with self._lock:
            if self.chart_simulation is not None and self.chart_simulation.poll() is None:
                return self.chart_target_digits
            command = [
                sys.executable,
                "scripts/run_pi_pyboy.py",
                "--rom",
                str(self.rom_path),
                "--run-name",
                self.run_name,
                "--digits",
                str(self.digits_path),
                "--config",
                str(self.config_path),
                "--checkpoint-digits",
                str(checkpoint_interval_digits),
                "--max-digits",
                str(target_digits),
            ]
            self.chart_simulation = subprocess.Popen(
                command,
                cwd=Path.cwd(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            self.chart_target_digits = target_digits
            return target_digits

    def stop_chart_simulation(self) -> int:
        stopped = 0
        with self._lock:
            process = self.chart_simulation
            self.chart_simulation = None
            self.chart_target_digits = 0

        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            stopped += 1

        stopped += stop_running_chart_processes(self.run_name)
        return stopped

    def chart_simulation_info(self) -> dict[str, object]:
        process = self.chart_simulation
        progress = read_progress(self.run_name)
        remembered_target = int(progress.get("digits_consumed", 0) or 0)
        running_target = running_chart_target(self.run_name)
        if running_target:
            self.chart_target_digits = max(self.chart_target_digits, running_target)
        running = (process.poll() is None if process is not None else False) or running_target > 0
        target_digits = self.chart_target_digits or running_target or remembered_target
        if not running and target_digits <= 0:
            return {"running": False, "target_digits": 0}
        digits_consumed = int(progress.get("digits_consumed", 0) or 0)
        digits_per_second = float(progress.get("effective_fps", 0) or 0)
        remaining_digits = max(0, target_digits - digits_consumed)
        eta_seconds = remaining_digits / digits_per_second if digits_per_second > 0 else None
        return {
            "running": running,
            "target_digits": target_digits,
            "digits_consumed": digits_consumed,
            "digits_per_second": digits_per_second,
            "eta_seconds": eta_seconds,
            "last_state": progress.get("last_state", ""),
        }

    def update_video_export(self, **status: object) -> None:
        with self._lock:
            self.video_export_status = {**self.video_export_status, **status}

    def video_export_info(self) -> dict[str, object]:
        with self._lock:
            status = dict(self.video_export_status)
            thread = self.video_export_thread
        running = thread is not None and thread.is_alive()
        status["running"] = running
        return status

    def persist_review_position(self, digits_consumed: int) -> None:
        digits_consumed = int(digits_consumed)
        if self.run_name == self._last_saved_run_name and digits_consumed == self._last_saved_digits:
            return
        write_review_session_state(self.run_name, digits_consumed)
        self._last_saved_run_name = self.run_name
        self._last_saved_digits = digits_consumed

    def start_video_export(self, start_digits: int, end_digits: int, preset_name: str) -> dict[str, object]:
        if preset_name not in VIDEO_EXPORT_PRESETS:
            raise ValueError(f"Unsupported video preset: {preset_name}")
        digits_per_input = self.digits_per_input
        start_digits = normalize_digit(start_digits, digits_per_input)
        end_digits = normalize_digit(end_digits, digits_per_input)
        max_digits = min(len(self.digits), self.hard_max_digits or len(self.digits))
        end_digits = min(end_digits, max_digits)
        if end_digits <= start_digits:
            raise ValueError("End digit must be greater than start digit.")
        if checkpoint_at_or_before(self.run_name, start_digits) is None:
            raise ValueError("No checkpoint before export start.")

        with self._lock:
            if self.video_export_thread is not None and self.video_export_thread.is_alive():
                return dict(self.video_export_status)

            preset = VIDEO_EXPORT_PRESETS[preset_name]
            output_dir = Path("results") / self.run_name / "videos"
            filename = (
                f"{safe_filename_part(self.run_name)}_{start_digits}_{end_digits}_{preset_name}"
                f"{preset['extension']}"
            )
            output_path = output_dir / filename
            self.video_export_status = {
                "state": "Starting",
                "running": True,
                "start_digits": start_digits,
                "end_digits": end_digits,
                "current_digits": start_digits,
                "frames_written": 0,
                "total_frames": ((end_digits - start_digits) // digits_per_input) * self.frames_per_input,
                "output_path": str(output_path),
                "preset": preset_name,
                "error": "",
            }

            def worker() -> None:
                try:
                    run_video_export(self, start_digits, end_digits, preset_name, output_path)
                except Exception as error:
                    self.update_video_export(state="Error", running=False, error=str(error))

            self.video_export_thread = threading.Thread(target=worker, name="pi-video-export", daemon=True)
            self.video_export_thread.start()
            return dict(self.video_export_status)

    def refresh_available_digits(self) -> None:
        if self.session is None:
            return
        available_digits = len(self.session.digits)
        if self.hard_max_digits is not None:
            available_digits = min(available_digits, self.hard_max_digits)
        if available_digits % self.digits_per_input:
            available_digits -= available_digits % self.digits_per_input
        self.session.set_max_digits(available_digits)

    def state(self) -> dict[str, object]:
        if self.session is None:
            checkpoints = list_checkpoints(self.run_name)
            max_digits = max((int(checkpoint["digits"]) for checkpoint in checkpoints), default=0)
            return {
                "rom_missing": self.rom_missing,
                "rom_path": str(self.rom_path),
                "status": "ROM required",
                "digits_consumed": 0,
                "max_digits": max_digits,
                "frames_elapsed": 0,
                "map_id": None,
                "location": "-",
                "speed": 10,
                "actual_speed_x": 0,
                "actual_digits_per_second": 0,
                "speed_limiter_enabled": "on",
                "sound_volume": 100,
                "snapshots": 0,
                "inputs_sent": 0,
                "last_button": "-",
                "last_simulation": {},
                "frame_version": self.frame_version,
                "inputs": [],
                "party": [],
                "bag": [],
                "player_info": {},
                "badges": [],
                "checkpoints": checkpoints,
                "runs": list_runs(self.run_name),
                "active_run": self.run_name,
                "digits_per_input": self.digits_per_input,
                "frames_per_input": self.frames_per_input,
                "config": config_info(self.config_path) if self.config_path.exists() else {},
                "chart_simulation": self.chart_simulation_info(),
                "video_export": self.video_export_info(),
            }
        self.refresh_available_digits()
        info = self.session.info()
        self.persist_review_position(int(info["digits_consumed"]))
        status = str(info["status"])
        if not (
            status.startswith("fast forwarding")
            or status.startswith("rewinding")
            or status.startswith("simulating")
            or status.startswith("jumping")
            or status.startswith("finding next")
        ):
            image = self.session.frame_image()
            frame_digest = hashlib.blake2s(image.tobytes(), digest_size=8).hexdigest() if image else ""
            if frame_digest != self._last_frame_digest:
                self.frame_version += 1
                self._last_frame_digest = frame_digest
        return {
            **info,
            "rom_missing": False,
            "rom_path": str(self.rom_path),
            "frame_version": self.frame_version,
            "inputs": self.session.input_window(previous_count=3, next_count=11),
            "party": self.session.party(),
            "bag": self.session.bag(),
            "player_info": self.session.player_info(),
            "badges": self.session.badges(),
            "checkpoints": list_checkpoints(self.run_name),
            "runs": list_runs(self.run_name),
            "active_run": self.run_name,
            "digits_per_input": self.digits_per_input,
            "frames_per_input": int(info.get("frames_per_input", self.frames_per_input)),
            "config": config_info(self.config_path) if self.config_path.exists() else {},
            "chart_simulation": self.chart_simulation_info(),
            "video_export": self.video_export_info(),
        }

    def input_state(self) -> dict[str, object]:
        if self.session is None:
            return {
                "rom_missing": self.rom_missing,
                "status": "ROM required",
                "digits_consumed": 0,
                "inputs": [],
            }
        info = self.session.info()
        return {
            "rom_missing": False,
            "status": info["status"],
            "digits_consumed": info["digits_consumed"],
            "frames_per_input": info.get("frames_per_input", self.frames_per_input),
            "current_input_frame": info.get("current_input_frame", 0),
            "inputs": self.session.input_window(previous_count=3, next_count=11),
        }

    def frame_png(self) -> bytes:
        if self.session is None:
            return image_to_png(None, self.scale)
        return image_to_png(self.session.frame_image(), self.scale)

    def frame_rgba(self) -> bytes:
        if self.session is None:
            return image_to_rgba(None)
        return image_to_rgba(self.session.frame_image())


def make_handler(app: ReviewWebApp):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/":
                self._serve_file(WEB_ROOT / "index.html")
            elif path == "/api/state":
                self._send_json(app.state())
            elif path == "/api/inputs":
                self._send_json(app.input_state())
            elif path == "/api/frame.png":
                self._send_bytes(app.frame_png(), "image/png")
            elif path == "/api/frame.rgba":
                self._send_bytes(app.frame_rgba(), "application/octet-stream")
            else:
                candidate = (WEB_ROOT / path.lstrip("/")).resolve()
                if WEB_ROOT.resolve() in candidate.parents and candidate.is_file():
                    self._serve_file(candidate)
                else:
                    self.send_error(404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/upload-rom":
                try:
                    rom_bytes = self._read_uploaded_file()
                    app.install_rom(rom_bytes)
                    self._send_json({"ok": True, "rom_path": str(app.rom_path)})
                except Exception as error:
                    self._send_json({"ok": False, "error": str(error)})
                return

            body = self._read_json()
            if path == "/api/select-run":
                try:
                    app.select_run(str(body.get("run_name", "")))
                    self._send_json({"ok": True, "run_name": app.run_name})
                except Exception as error:
                    self._send_json({"ok": False, "error": str(error)})
                return

            if path == "/api/stop-simulate":
                stopped = app.stop_chart_simulation()
                self._send_json({"ok": True, "stopped": stopped})
                return

            if path == "/api/export-video":
                try:
                    status = app.start_video_export(
                        int(body.get("start_digits", 0)),
                        int(body.get("end_digits", 0)),
                        str(body.get("preset", "mp4")),
                    )
                    self._send_json({"ok": True, "export": status})
                except Exception as error:
                    self._send_json({"ok": False, "error": str(error)})
                return

            if app.session is None:
                self._send_json({"ok": False, "error": "ROM required"})
            elif path == "/api/pause":
                app.session.toggle_pause_at_boundary()
                self._send_json({"ok": True})
            elif path == "/api/speed":
                app.session.set_speed(float(body.get("speed", 1)))
                self._send_json({"ok": True})
            elif path == "/api/limiter":
                app.session.set_speed_limiter_enabled(bool(body.get("enabled", True)))
                self._send_json({"ok": True})
            elif path == "/api/volume":
                app.session.set_sound_volume(int(body.get("volume", 100)))
                self._send_json({"ok": True})
            elif path == "/api/rewind":
                app.session.request_rewind(int(body.get("digits", 1000)))
                self._send_json({"ok": True})
            elif path == "/api/fast-forward":
                app.session.request_fast_forward(int(body.get("digits", 1000)))
                self._send_json({"ok": True})
            elif path == "/api/simulate":
                target_digits = app.start_chart_simulation(
                    int(body.get("target_digits", body.get("digits", 1000))),
                    int(body.get("checkpoint_interval_digits", 1_000_000)),
                )
                self._send_json({"ok": True, "target_digits": target_digits})
            elif path == "/api/jump":
                app.refresh_available_digits()
                rounded_digits = app.session.request_jump(int(body.get("digits", 0)))
                self._send_json({"ok": True, "digits": rounded_digits})
            elif path == "/api/next-battle":
                app.refresh_available_digits()
                app.session.request_warp_state("battle", int(body.get("limit_digits", 1_000_000)))
                self._send_json({"ok": True})
            elif path == "/api/warp-state":
                app.refresh_available_digits()
                target_state = app.session.request_warp_state(
                    str(body.get("state", "battle")),
                    int(body.get("limit_digits", 1_000_000)),
                )
                self._send_json({"ok": True, "state": target_state})
            else:
                self.send_error(404)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _read_json(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0"))
            if not length:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _read_uploaded_file(self) -> bytes:
            content_type = self.headers.get("Content-Type", "")
            boundary_marker = "boundary="
            if boundary_marker not in content_type:
                raise ValueError("ROM upload must use multipart/form-data.")
            boundary = content_type.split(boundary_marker, 1)[1].strip().strip('"').encode("utf-8")
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            delimiter = b"--" + boundary
            for part in body.split(delimiter):
                if b'name="rom"' not in part:
                    continue
                header_end = part.find(b"\r\n\r\n")
                if header_end < 0:
                    continue
                payload = part[header_end + 4 :]
                payload = payload.removesuffix(b"\r\n").removesuffix(b"--").removesuffix(b"\r\n")
                if payload:
                    return payload
            raise ValueError("No ROM file found in upload.")

        def _serve_file(self, path: Path) -> None:
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self._send_bytes(path.read_bytes(), content_type)

        def _send_json(self, payload: dict[str, object]) -> None:
            self._send_bytes(json.dumps(payload).encode("utf-8"), "application/json")

        def _send_bytes(self, payload: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the piPokemon web reviewer.")
    parser.add_argument("--rom", type=Path, default=ROM)
    parser.add_argument("--digits", type=Path, default=PI_DIGITS)
    parser.add_argument("--config", type=Path, default=INPUT_CONFIG)
    parser.add_argument("--run-name", default=RUN_NAME)
    parser.add_argument("--checkpoint", default="penultimate")
    parser.add_argument("--digits-consumed", type=int, default=None)
    parser.add_argument("--max-digits", type=int, default=None, help="Optional cap. Defaults to the highest available checkpoint.")
    parser.add_argument("--speed", type=int, default=10)
    parser.add_argument("--hold-frames", type=int, default=None)
    parser.add_argument("--release-frames", type=int, default=None)
    parser.add_argument("--scale", type=int, default=4)
    parser.add_argument("--sound-volume", type=int, default=100)
    parser.add_argument("--sound-sample-rate", type=int, default=48000)
    parser.add_argument("--rewind-history-digits", type=int, default=1_000_000)
    parser.add_argument("--rewind-interval-digits", type=int, default=100)
    parser.add_argument("--start-running", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open-browser", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.run_name = resolve_configured_run_name(args.run_name, args.config)
    remembered_state = read_review_session_state()
    restore_requested = args.checkpoint == "penultimate" and args.digits_consumed is None
    remembered_digits: int | None = None
    if restore_requested:
        remembered_run_name = str(remembered_state.get("run_name", "")).strip()
        remembered_config_path = Path("saves") / remembered_run_name / RUN_CONFIG_FILENAME
        if remembered_run_name and remembered_config_path.exists():
            try:
                remembered_digits = int(remembered_state["digits_consumed"])
            except (KeyError, TypeError, ValueError):
                remembered_digits = None
            if remembered_digits is not None:
                args.run_name = remembered_run_name
                args.config = remembered_config_path
    input_config = load_input_config(args.config)
    hold_frames = input_config.on_frames if args.hold_frames is None else args.hold_frames
    release_frames = input_config.off_frames if args.release_frames is None else args.release_frames
    if hold_frames < 1:
        raise ValueError("--hold-frames must be at least 1")
    if release_frames < 0:
        raise ValueError("--release-frames must be at least 0")

    digits = args.digits.read_text(encoding="ascii").strip()

    def create_session(
        run_name: str = args.run_name,
        config_path: Path = args.config,
        session_input_config=None,
        checkpoint_name: str = args.checkpoint,
        explicit_digits_consumed: int | None = args.digits_consumed if args.digits_consumed is not None else remembered_digits,
    ) -> ReviewSession:
        if not args.rom.exists():
            raise RomMissingError(f"ROM not found: {args.rom}")
        active_config = session_input_config or load_input_config(config_path)
        active_hold_frames = active_config.on_frames if args.hold_frames is None else args.hold_frames
        active_release_frames = active_config.off_frames if args.release_frames is None else args.release_frames
        checkpoint_dir = Path("saves") / run_name
        screenshot_dir = Path("results") / run_name / "screenshots"
        if latest_checkpoint(checkpoint_dir) is None:
            bootstrap = PyBoy(
                str(args.rom),
                window="null",
                sound_emulated=False,
                no_input=False,
                ram_file=io.BytesIO(bytes(32768)),
                log_level="CRITICAL",
            )
            try:
                bootstrap.set_emulation_speed(0)
                save_checkpoint(bootstrap, checkpoint_dir, screenshot_dir, 0, save_screenshot=True)
            finally:
                bootstrap.stop()
        newest_checkpoint = latest_checkpoint(Path("saves") / run_name)
        newest_checkpoint_digits = newest_checkpoint[0] if newest_checkpoint is not None else 0
        max_digits = min(args.max_digits or len(digits), len(digits))
        if max_digits % active_config.digits_per_input:
            max_digits -= max_digits % active_config.digits_per_input

        target_digits: int | None = None
        if explicit_digits_consumed is not None:
            target_digits = max(0, min(max_digits, explicit_digits_consumed))
            if target_digits % active_config.digits_per_input:
                target_digits -= target_digits % active_config.digits_per_input
            checkpoint_match = checkpoint_at_or_before(run_name, target_digits)
            if checkpoint_match is None:
                checkpoint = resolve_checkpoint(run_name, checkpoint_name, max_digits=max_digits + active_config.digits_per_input)
                start_digits = checkpoint_digits(checkpoint, None)
                target_digits = start_digits
            else:
                start_digits, checkpoint = checkpoint_match
        else:
            checkpoint = resolve_checkpoint(run_name, checkpoint_name, max_digits=max_digits + active_config.digits_per_input)
            start_digits = checkpoint_digits(checkpoint, None)
        if start_digits > max_digits:
            raise ValueError(f"Checkpoint is at {start_digits:,} digits, but max is {max_digits:,}.")

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
        if target_digits is not None and start_digits < target_digits:
            start_digits, _, _ = advance_pi_inputs(
                pyboy,
                digits,
                start_digits,
                target_digits,
                active_hold_frames,
                active_release_frames,
                input_config=active_config,
            )
        initial_image = load_checkpoint_screenshot(run_name, start_digits) or render_loaded_state(pyboy)

        session = ReviewSession(
            pyboy=pyboy,
            digits=digits,
            digits_consumed=start_digits,
            max_digits=max_digits,
            hold_frames=active_hold_frames,
            release_frames=active_release_frames,
            rewind_interval_digits=args.rewind_interval_digits,
            rewind_history_digits=args.rewind_history_digits,
            sound_volume=args.sound_volume,
            audio_sink=AudioSink(args.sound_sample_rate),
            initial_image=initial_image,
            rom_path=args.rom,
            run_name=run_name,
            digits_path=args.digits,
            input_config=active_config,
        )
        session.set_speed(args.speed)
        if args.start_running:
            session.set_paused(False)
        return session

    try:
        session: ReviewSession | None = create_session()
    except RomMissingError:
        session = None

    app = ReviewWebApp(
        session,
        args.scale,
        args.run_name,
        input_config.digits_per_input,
        input_config.on_frames + input_config.off_frames,
        args.max_digits,
        args.rom,
        args.digits,
        digits,
        args.config,
        create_session,
    )
    app.start_emulator_thread()

    server = ThreadingHTTPServer(
        (args.host, args.port),
        make_handler(app),
    )
    url = f"http://{args.host}:{args.port}/"
    print(f"piPokemon reviewer running at {url}")
    if args.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        if app.session is not None:
            try:
                app.persist_review_position(int(app.session.info()["digits_consumed"]))
            except Exception:
                pass
            app.session.stop()
        server.server_close()
        if app.emulator_thread is not None:
            app.emulator_thread.join(timeout=5)


if __name__ == "__main__":
    main()
