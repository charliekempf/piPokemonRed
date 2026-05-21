import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import review_web
from review_web import (
    ReviewWebApp,
    append_progression_graph_samples_to_archive,
    archived_progression_digit_bounds,
    archived_progression_graph_samples,
)


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


def test_start_chart_simulation_can_fill_missing_progression_distance(monkeypatch) -> None:
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

    app.start_chart_simulation(20, 10, log_progression_distance=True, fill_missing_progression_distance=True)

    assert commands
    assert "--fill-missing-progression-distance" in commands[0]
    assert "--no-progression-distance" not in commands[0]


def test_archived_progression_graph_samples_read_hdf5(tmp_path: Path, monkeypatch) -> None:
    import h5py

    monkeypatch.chdir(tmp_path)
    archive_path = Path("results/statistical_walk/progression_distance.h5")
    archive_path.parent.mkdir(parents=True)
    with h5py.File(archive_path, "w") as handle:
        string_dtype = h5py.string_dtype(encoding="utf-8")
        handle.create_dataset("digit", data=[2, 4, 6, 8, 10])
        handle.create_dataset("remaining_steps", data=[100, 90, -1, 80, 70])
        handle.create_dataset("total_steps_from_respawn", data=[120, 120, 120, 120, 120])
        handle.create_dataset("reachable", data=[True, True, False, True, True])
        handle.create_dataset("in_battle", data=[False, False, True, False, False])
        handle.create_dataset("gate_label", data=["Oak", "Oak", "Oak", "Oak", "Oak"], dtype=string_dtype)
        handle.create_dataset("objective_location", data=["Lab", "Lab", "Lab", "Lab", "Lab"], dtype=string_dtype)

    samples = archived_progression_graph_samples("statistical_walk", 2, 10, 4)

    assert [sample["digit"] for sample in samples] == [2, 6, 10]
    assert samples[0]["steps"] == 100
    assert samples[0]["baseline_steps"] == 120
    assert samples[1]["steps"] is None
    assert samples[1]["in_battle"] is True
    assert samples[2]["label"] == "Oak"
    assert samples[2]["objective_location"] == "Lab"
    assert all(sample["source"] == "hdf5" for sample in samples)


def test_archived_progression_digit_bounds_reads_hdf5(tmp_path: Path, monkeypatch) -> None:
    import h5py

    monkeypatch.chdir(tmp_path)
    archive_path = Path("results/statistical_walk/progression_distance.h5")
    archive_path.parent.mkdir(parents=True)
    with h5py.File(archive_path, "w") as handle:
        handle.create_dataset("digit", data=[18, 2, 10])

    assert archived_progression_digit_bounds("statistical_walk") == (2, 18)


def test_progression_graph_archive_range_centers_current_digit(tmp_path: Path, monkeypatch) -> None:
    import h5py

    monkeypatch.chdir(tmp_path)
    archive_path = Path("results/statistical_walk/progression_distance.h5")
    archive_path.parent.mkdir(parents=True)
    with h5py.File(archive_path, "w") as handle:
        handle.create_dataset("digit", data=[2, 4, 6, 8, 10, 12, 14, 16, 18])
        handle.create_dataset("remaining_steps", data=[9, 8, 7, 6, 5, 4, 3, 2, 1])
        handle.create_dataset("total_steps_from_respawn", data=[10] * 9)

    session = FakeSession()
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

    status = app.start_progression_graph_generation(center_digits=10, range_digits=8)

    assert status["state"] == "Archived"
    assert status["start_digits"] == 6
    assert status["end_digits"] == 14
    assert status["sample_digits"] == 2
    assert [sample["digit"] for sample in status["samples"]] == [6, 8, 10, 12, 14]


def test_progression_graph_full_range_uses_hdf5_bounds(tmp_path: Path, monkeypatch) -> None:
    import h5py

    monkeypatch.chdir(tmp_path)
    archive_path = Path("results/statistical_walk/progression_distance.h5")
    archive_path.parent.mkdir(parents=True)
    with h5py.File(archive_path, "w") as handle:
        handle.create_dataset("digit", data=[2, 4, 6, 8, 10, 12, 14, 16, 18])
        handle.create_dataset("remaining_steps", data=[9, 8, 7, 6, 5, 4, 3, 2, 1])
        handle.create_dataset("total_steps_from_respawn", data=[10] * 9)

    session = FakeSession()
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

    status = app.start_progression_graph_generation(center_digits=10, range_digits=8, full_range=True)

    assert status["state"] == "Archived"
    assert status["start_digits"] == 2
    assert status["end_digits"] == 18
    assert status["sample_digits"] == 2
    assert status["full_range"] is True
    assert [sample["digit"] for sample in status["samples"]] == [2, 4, 6, 8, 10, 12, 14, 16, 18]


def test_append_progression_graph_samples_skips_duplicate_digits(tmp_path: Path, monkeypatch) -> None:
    import h5py

    monkeypatch.chdir(tmp_path)
    archive_path = Path("results/statistical_walk/progression_distance.h5")
    archive_path.parent.mkdir(parents=True)
    with h5py.File(archive_path, "w") as handle:
        handle.create_dataset("digit", shape=(0,), maxshape=(None,), chunks=True, dtype="i8")
        handle.create_dataset("remaining_steps", shape=(0,), maxshape=(None,), chunks=True, dtype="i4")

    first_count = append_progression_graph_samples_to_archive(
        "statistical_walk",
        Path("config/statistical_walk.json"),
        Path("data/test.txt"),
        Path("roms/test.gb"),
        [
            {"digit": 6, "input_index": 3, "steps": 12, "label": "Oak", "reachable": True},
            {"digit": 4, "input_index": 2, "steps": 14, "label": "Oak", "reachable": True},
        ],
    )
    second_count = append_progression_graph_samples_to_archive(
        "statistical_walk",
        Path("config/statistical_walk.json"),
        Path("data/test.txt"),
        Path("roms/test.gb"),
        [
            {"digit": 4, "input_index": 2, "steps": 14, "label": "Oak", "reachable": True},
            {"digit": 8, "input_index": 4, "steps": 10, "label": "Oak", "reachable": True},
        ],
    )

    assert first_count == 2
    assert second_count == 1
    with h5py.File(archive_path, "r") as handle:
        assert handle["digit"][:].tolist() == [4, 6, 8]
        assert handle["remaining_steps"][:].tolist() == [14, 12, 10]
