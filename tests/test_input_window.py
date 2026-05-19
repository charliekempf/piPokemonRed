import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from review_pi_checkpoint import ReviewSession
from run_pi_pyboy import load_input_config


class NoopLock:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: object) -> None:
        return None


class DummyPyBoy:
    def set_emulation_speed(self, speed: float) -> None:
        self.speed = speed


def test_input_window_uses_available_digits_beyond_max_digits() -> None:
    session = object.__new__(ReviewSession)
    session.digits_consumed = 8
    session.max_digits = 10
    session.digits = "01234567890123456789"
    session.input_config = load_input_config()
    session._lock = NoopLock()

    items = session.input_window(previous_count=1, next_count=4)

    assert [item["digit_index"] for item in items] == [6, 8, 10, 12, 14, 16]
    assert items[1]["role"] == "current"
    assert items[2]["role"] == "future"


def test_request_jump_uses_available_digits_beyond_max_digits() -> None:
    session = object.__new__(ReviewSession)
    session._lock = NoopLock()
    session.pyboy = DummyPyBoy()
    session.digits_consumed = 8
    session.max_digits = 10
    session.digits = "01234567890123456789"
    session.input_config = load_input_config()
    session._rewind_digits_requested = 0
    session._fast_forward_target_digits = None
    session._simulate_target_digits = None
    session._warp_target_state = None
    session._seek_active = False

    rounded_digits = session.request_jump(16)

    assert rounded_digits == 16
    assert session._jump_target_digits == 16
    assert session.status == "jumping to 16 digits"
