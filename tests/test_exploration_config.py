import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_pi_pyboy import button_for_value, config_display_name, load_input_config


def test_exploration_config_spread() -> None:
    config_path = Path("config/exploration.json")
    config = load_input_config(config_path)

    assert config_display_name(config_path) == "Exploration"
    assert config.on_frames == 2
    assert config.off_frames == 14
    assert config.digits_per_input == 2

    counts: dict[str, int] = {}
    for value in range(100):
        button = button_for_value(value, config)
        counts[button] = counts.get(button, 0) + 1

    assert counts == {
        "a": 14,
        "b": 13,
        "up": 18,
        "down": 18,
        "left": 18,
        "right": 18,
        "start": 1,
    }
