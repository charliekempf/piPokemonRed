import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_pi_pyboy import RUN_CONFIG_FILENAME, config_display_name, resolve_configured_run_name


def write_config(path: Path, a_max: int, name: str | None = None, version: str | None = None) -> None:
    payload = {
        "on_frames": 2,
        "off_frames": 1,
        "digits_per_input": 2,
        "mapping": [
            {"min": 0, "max": a_max, "button": "a"},
            {"min": a_max + 1, "max": 99, "button": "start"},
        ],
    }
    if name is not None:
        payload["name"] = name
    if version is not None:
        payload["game"] = {"title": "Pokemon Red", "version": version, "region": "USA/Europe"}
    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_same_config_reuses_base_run_folder(tmp_path: Path) -> None:
    config = tmp_path / "mapping.json"
    write_config(config, 53, name="Experiment")

    first = resolve_configured_run_name("experiment", config, tmp_path / "saves", tmp_path / "results")
    second = resolve_configured_run_name("experiment", config, tmp_path / "saves", tmp_path / "results")

    assert first == "experiment"
    assert second == "experiment"
    assert (tmp_path / "saves" / "experiment" / RUN_CONFIG_FILENAME).exists()
    assert (tmp_path / "results" / "experiment" / RUN_CONFIG_FILENAME).exists()


def test_different_config_gets_separate_run_folder(tmp_path: Path) -> None:
    first_config = tmp_path / "mapping.json"
    second_config = tmp_path / "alternate.json"
    write_config(first_config, 53, name="Experiment")
    write_config(second_config, 40, name="Experiment")

    first = resolve_configured_run_name("experiment", first_config, tmp_path / "saves", tmp_path / "results")
    second = resolve_configured_run_name("experiment", second_config, tmp_path / "saves", tmp_path / "results")

    assert first == "experiment"
    assert second.startswith("alternate_")
    assert second != first
    assert (tmp_path / "saves" / second / RUN_CONFIG_FILENAME).exists()


def test_config_name_controls_run_folder_slug(tmp_path: Path) -> None:
    first_config = tmp_path / "mapping.json"
    renamed_config = tmp_path / "renamed.json"
    write_config(first_config, 53, name="Experiment")
    write_config(renamed_config, 53, name="Statistical Walk")

    first = resolve_configured_run_name("experiment", first_config, tmp_path / "saves", tmp_path / "results")
    renamed = resolve_configured_run_name("experiment", renamed_config, tmp_path / "saves", tmp_path / "results")

    assert first == "experiment"
    assert renamed == "statistical_walk"
    assert config_display_name(tmp_path / "saves" / "statistical_walk" / RUN_CONFIG_FILENAME) == "Statistical Walk"


def test_game_version_change_gets_separate_run_folder(tmp_path: Path) -> None:
    first_config = tmp_path / "mapping.json"
    second_config = tmp_path / "alternate.json"
    write_config(first_config, 53, name="Experiment", version="1.0")
    write_config(second_config, 53, name="Experiment", version="1.1")

    first = resolve_configured_run_name("experiment", first_config, tmp_path / "saves", tmp_path / "results")
    second = resolve_configured_run_name("experiment", second_config, tmp_path / "saves", tmp_path / "results")

    assert first == "experiment"
    assert second.startswith("alternate_")
    assert second != first


def test_adding_game_metadata_keeps_existing_run_folder(tmp_path: Path) -> None:
    old_config = tmp_path / "mapping.json"
    updated_config = tmp_path / "mapping_with_game.json"
    write_config(old_config, 53, name="Experiment")
    write_config(updated_config, 53, name="Experiment", version="1.0")

    first = resolve_configured_run_name("experiment", old_config, tmp_path / "saves", tmp_path / "results")
    updated = resolve_configured_run_name("experiment", updated_config, tmp_path / "saves", tmp_path / "results")

    assert first == "experiment"
    assert updated == "experiment"
    assert '"game"' in (tmp_path / "saves" / "experiment" / RUN_CONFIG_FILENAME).read_text(encoding="utf-8")
