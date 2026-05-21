import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import review_web
from review_web import ReviewWebApp


class FakeSession:
    def __init__(self) -> None:
        self.digits = "01234567890123456789"
        self.max_digits = 0

    def set_max_digits(self, max_digits: int) -> None:
        self.max_digits = max_digits


def test_refresh_available_digits_uses_digit_file_length() -> None:
    session = FakeSession()
    app = ReviewWebApp(
        session=session,
        scale=4,
        run_name="missing-test-run",
        digits_per_input=2,
        frames_per_input=3,
        hard_max_digits=None,
        rom_path=Path("roms/test.gb"),
        digits_path=Path("data/test.txt"),
        digits=session.digits,
        config_path=Path("config/statistical_walk.json"),
        session_factory=lambda: session,
    )

    app.refresh_available_digits()

    assert session.max_digits == 20


def test_refresh_available_digits_honors_hard_limit() -> None:
    session = FakeSession()
    app = ReviewWebApp(
        session=session,
        scale=4,
        run_name="missing-test-run",
        digits_per_input=2,
        frames_per_input=3,
        hard_max_digits=11,
        rom_path=Path("roms/test.gb"),
        digits_path=Path("data/test.txt"),
        digits=session.digits,
        config_path=Path("config/statistical_walk.json"),
        session_factory=lambda: session,
    )

    app.refresh_available_digits()

    assert session.max_digits == 10


def test_start_chart_simulation_can_disable_progression_distance_logging(monkeypatch) -> None:
    session = FakeSession()
    commands: list[list[str]] = []

    class FakeProcess:
        def poll(self) -> int | None:
            return None

    def fake_popen(command, **_kwargs):
        commands.append(list(command))
        return FakeProcess()

    monkeypatch.setattr(review_web.subprocess, "Popen", fake_popen)
    app = ReviewWebApp(
        session=session,
        scale=4,
        run_name="statistical_walk",
        digits_per_input=2,
        frames_per_input=3,
        hard_max_digits=None,
        rom_path=Path("roms/test.gb"),
        digits_path=Path("data/test.txt"),
        digits=session.digits,
        config_path=Path("config/statistical_walk.json"),
        session_factory=lambda: session,
    )

    target_digits = app.start_chart_simulation(20, 10, log_progression_distance=False)

    assert target_digits == 20
    assert commands
    assert "--no-progression-distance" in commands[0]
