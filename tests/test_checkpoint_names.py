import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from review_pi_checkpoint import checkpoint_digits
from run_pi_pyboy import latest_checkpoint


def test_checkpoint_digits_accepts_nine_digit_counts() -> None:
    assert checkpoint_digits(Path("checkpoint_100000000_digits.state"), None) == 100_000_000


def test_latest_checkpoint_accepts_nine_digit_counts(tmp_path: Path) -> None:
    (tmp_path / "checkpoint_99000000_digits.state").write_bytes(b"old")
    newest = tmp_path / "checkpoint_100000000_digits.state"
    newest.write_bytes(b"new")

    assert latest_checkpoint(tmp_path) == (100_000_000, newest)
