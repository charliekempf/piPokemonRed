import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import review_web
from review_web import ReviewWebApp, archived_progression_graph_samples


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
