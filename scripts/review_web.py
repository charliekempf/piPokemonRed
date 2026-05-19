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
    ReviewSession,
    checkpoint_digits,
    render_loaded_state,
    resolve_checkpoint,
)
from run_pi_pyboy import INPUT_CONFIG, PI_DIGITS, ROM, RUN_NAME, latest_checkpoint, load_input_config


WEB_ROOT = Path("web/review")
RUN_PI_RE = re.compile(r"run_pi_pyboy\.py")
MAX_DIGITS_RE = re.compile(r"--max-digits\s+(\d+)")
RUN_NAME_RE = re.compile(r"--run-name\s+([^\s]+)")


class RomMissingError(RuntimeError):
    pass


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


def load_checkpoint_screenshot(run_name: str, digits_consumed: int) -> Image.Image | None:
    screenshot_path = (
        Path("results")
        / run_name
        / "screenshots"
        / f"checkpoint_{digits_consumed:08d}_digits.png"
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


class ReviewWebApp:
    def __init__(
        self,
        session: ReviewSession | None,
        scale: int,
        run_name: str,
        digits_per_input: int,
        hard_max_digits: int | None,
        rom_path: Path,
        digits_path: Path,
        config_path: Path,
        session_factory,
    ) -> None:
        self.session = session
        self.scale = scale
        self.run_name = run_name
        self.digits_per_input = digits_per_input
        self.hard_max_digits = hard_max_digits
        self.rom_path = rom_path
        self.digits_path = digits_path
        self.config_path = config_path
        self.session_factory = session_factory
        self.emulator_thread: threading.Thread | None = None
        self.chart_simulation: subprocess.Popen[bytes] | None = None
        self.chart_target_digits = 0
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

    def refresh_available_digits(self) -> None:
        if self.session is None:
            return
        checkpoint = latest_checkpoint(Path("saves") / self.run_name)
        if checkpoint is None:
            return
        available_digits = checkpoint[0]
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
                "speed_limiter_enabled": "on",
                "sound_volume": 100,
                "snapshots": 0,
                "inputs_sent": 0,
                "last_button": "-",
                "last_simulation": {},
                "frame_version": self.frame_version,
                "inputs": [],
                "party": [],
                "badges": [],
                "checkpoints": checkpoints,
                "chart_simulation": self.chart_simulation_info(),
            }
        self.refresh_available_digits()
        info = self.session.info()
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
            "badges": self.session.badges(),
            "checkpoints": list_checkpoints(self.run_name),
            "chart_simulation": self.chart_simulation_info(),
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
                app.session.set_speed(1)
                app.session.set_speed_limiter_enabled(True)
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
    input_config = load_input_config(args.config)
    hold_frames = input_config.on_frames if args.hold_frames is None else args.hold_frames
    release_frames = input_config.off_frames if args.release_frames is None else args.release_frames
    if hold_frames < 1:
        raise ValueError("--hold-frames must be at least 1")
    if release_frames < 0:
        raise ValueError("--release-frames must be at least 0")

    digits = args.digits.read_text(encoding="ascii").strip()

    def create_session() -> ReviewSession:
        if not args.rom.exists():
            raise RomMissingError(f"ROM not found: {args.rom}")
        newest_checkpoint = latest_checkpoint(Path("saves") / args.run_name)
        newest_checkpoint_digits = newest_checkpoint[0] if newest_checkpoint is not None else 0
        max_digits = min(args.max_digits or newest_checkpoint_digits or len(digits), len(digits))
        if max_digits % input_config.digits_per_input:
            max_digits -= max_digits % input_config.digits_per_input

        checkpoint = resolve_checkpoint(args.run_name, args.checkpoint, max_digits=max_digits + input_config.digits_per_input)
        start_digits = checkpoint_digits(checkpoint, args.digits_consumed)
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
        initial_image = load_checkpoint_screenshot(args.run_name, start_digits) or render_loaded_state(pyboy)

        session = ReviewSession(
            pyboy=pyboy,
            digits=digits,
            digits_consumed=start_digits,
            max_digits=max_digits,
            hold_frames=hold_frames,
            release_frames=release_frames,
            rewind_interval_digits=args.rewind_interval_digits,
            rewind_history_digits=args.rewind_history_digits,
            sound_volume=args.sound_volume,
            audio_sink=AudioSink(args.sound_sample_rate),
            initial_image=initial_image,
            rom_path=args.rom,
            run_name=args.run_name,
            digits_path=args.digits,
            input_config=input_config,
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
        args.max_digits,
        args.rom,
        args.digits,
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
            app.session.stop()
        server.server_close()
        if app.emulator_thread is not None:
            app.emulator_thread.join(timeout=5)


if __name__ == "__main__":
    main()
