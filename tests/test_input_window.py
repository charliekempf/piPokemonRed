import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from review_pi_checkpoint import ReviewSession
from run_pi_pyboy import load_input_config


def test_input_window_uses_available_digits_beyond_max_digits() -> None:
    session = object.__new__(ReviewSession)
    session._lock = None
    session.digits_consumed = 8
    session.max_digits = 10
    session.digits = "01234567890123456789"
    session.input_config = load_input_config()

    class NoopLock:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *args: object) -> None:
            return None

    session._lock = NoopLock()

    items = session.input_window(previous_count=1, next_count=4)

    assert [item["digit_index"] for item in items] == [6, 8, 10, 12, 14, 16]
    assert items[1]["role"] == "current"
    assert items[2]["role"] == "future"
