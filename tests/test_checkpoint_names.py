import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from review_pi_checkpoint import checkpoint_digits
from run_pi_pyboy import checkpoint_at_or_before, first_missing_progression_distance_digit, latest_checkpoint


def test_checkpoint_digits_accepts_nine_digit_counts() -> None:
    assert checkpoint_digits(Path("checkpoint_100000000_digits.state"), None) == 100_000_000


def test_latest_checkpoint_accepts_nine_digit_counts(tmp_path: Path) -> None:
    (tmp_path / "checkpoint_99000000_digits.state").write_bytes(b"old")
    newest = tmp_path / "checkpoint_100000000_digits.state"
    newest.write_bytes(b"new")

    assert latest_checkpoint(tmp_path) == (100_000_000, newest)


def test_checkpoint_at_or_before_uses_nearest_checkpoint(tmp_path: Path) -> None:
    (tmp_path / "checkpoint_10000_digits.state").write_bytes(b"10k")
    nearest = tmp_path / "checkpoint_20000_digits.state"
    nearest.write_bytes(b"20k")
    (tmp_path / "checkpoint_30000_digits.state").write_bytes(b"30k")

    assert checkpoint_at_or_before(tmp_path, 25_000) == (20_000, nearest)


def test_first_missing_progression_distance_digit(tmp_path: Path) -> None:
    import h5py

    archive_path = tmp_path / "progression_distance.h5"
    with h5py.File(archive_path, "w") as handle:
        handle.create_dataset("digit", data=[2, 4, 8])

    assert first_missing_progression_distance_digit(archive_path, 10, 2) == 6
    assert first_missing_progression_distance_digit(archive_path, 4, 2) is None
    assert first_missing_progression_distance_digit(tmp_path / "missing.h5", 10, 2) == 2
