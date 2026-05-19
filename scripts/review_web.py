from __future__ import annotations

import argparse
import hashlib
import io
import json
import mimetypes
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
from run_pi_pyboy import PI_DIGITS, ROM, RUN_NAME


WEB_ROOT = Path("web/review")


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


class ReviewWebApp:
    def __init__(self, session: ReviewSession, scale: int) -> None:
        self.session = session
        self.scale = scale
        self.frame_version = 0
        self._last_frame_digest = ""

    def state(self) -> dict[str, object]:
        info = self.session.info()
        status = str(info["status"])
        if not (status.startswith("fast forwarding") or status.startswith("simulating")):
            image = self.session.frame_image()
            frame_digest = hashlib.blake2s(image.tobytes(), digest_size=8).hexdigest() if image else ""
            if frame_digest != self._last_frame_digest:
                self.frame_version += 1
                self._last_frame_digest = frame_digest
        return {
            **info,
            "frame_version": self.frame_version,
            "upcoming": [
                {"digit_index": digit_index, "pair": pair, "button": button}
                for digit_index, pair, button in self.session.upcoming_buttons(12)
            ],
        }

    def frame_png(self) -> bytes:
        return image_to_png(self.session.frame_image(), self.scale)

    def frame_rgba(self) -> bytes:
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
            body = self._read_json()
            if path == "/api/pause":
                app.session.toggle_pause_at_boundary()
                self._send_json({"ok": True})
            elif path == "/api/speed":
                app.session.set_speed(float(body.get("speed", 1)))
                self._send_json({"ok": True})
            elif path == "/api/limiter":
                app.session.set_speed_limiter_enabled(bool(body.get("enabled", True)))
                self._send_json({"ok": True})
            elif path == "/api/rewind":
                app.session.request_rewind(int(body.get("digits", 1000)))
                self._send_json({"ok": True})
            elif path == "/api/fast-forward":
                app.session.request_fast_forward(int(body.get("digits", 1000)))
                self._send_json({"ok": True})
            elif path == "/api/simulate":
                app.session.request_simulate(int(body.get("digits", 1000)))
                self._send_json({"ok": True})
            else:
                self.send_error(404)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _read_json(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0"))
            if not length:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

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
    parser.add_argument("--run-name", default=RUN_NAME)
    parser.add_argument("--checkpoint", default="latest")
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
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open-browser", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    digits = args.digits.read_text(encoding="ascii").strip()
    max_digits = min(args.max_digits or len(digits), len(digits))
    if max_digits % 2:
        max_digits -= 1

    checkpoint = resolve_checkpoint(args.run_name, args.checkpoint, max_digits=max_digits)
    start_digits = checkpoint_digits(checkpoint, args.digits_consumed)
    if start_digits >= max_digits:
        raise ValueError(f"Checkpoint is already at {start_digits:,} digits, but max is {max_digits:,}.")

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
        hold_frames=args.hold_frames,
        release_frames=args.release_frames,
        rewind_interval_digits=args.rewind_interval_digits,
        rewind_history_digits=args.rewind_history_digits,
        sound_volume=args.sound_volume,
        audio_sink=AudioSink(args.sound_sample_rate),
        initial_image=initial_image,
        rom_path=args.rom,
        run_name=args.run_name,
        digits_path=args.digits,
    )
    session.set_speed(args.speed)
    if args.start_running:
        session.set_paused(False)

    emulator_thread = threading.Thread(target=session.run, name="pyboy-web-review", daemon=True)
    emulator_thread.start()

    server = ThreadingHTTPServer((args.host, args.port), make_handler(ReviewWebApp(session, args.scale)))
    url = f"http://{args.host}:{args.port}/"
    print(f"piPokemon reviewer running at {url}")
    if args.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        session.stop()
        server.server_close()
        emulator_thread.join(timeout=5)


if __name__ == "__main__":
    main()
