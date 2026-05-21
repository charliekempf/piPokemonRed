import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_pi_pyboy import (
    action_for_value,
    advance_pi_inputs,
    average_frames_per_input,
    button_for_value,
    config_display_name,
    load_input_config,
)


class FakePyBoy:
    def __init__(self) -> None:
        self.events: list[tuple[str, str | int]] = []

    def button_press(self, button: str) -> None:
        self.events.append(("press", button))

    def button_release(self, button: str) -> None:
        self.events.append(("release", button))

    def tick(self, frames: int, render: bool, sound: bool = True) -> None:
        self.events.append(("tick", frames))


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


def test_exploration_fast_keeps_spread_with_short_offtime() -> None:
    config_path = Path("config/exploration_fast.json")
    config = load_input_config(config_path)

    assert config_display_name(config_path) == "Exploration Fast"
    assert config.on_frames == 2
    assert config.off_frames == 1
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


def test_exploration_medium_keeps_spread_with_medium_offtime() -> None:
    config_path = Path("config/exploration_medium.json")
    config = load_input_config(config_path)

    assert config_display_name(config_path) == "Exploration Medium"
    assert config.on_frames == 2
    assert config.off_frames == 13
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


def test_exploration_medium_fast_keeps_spread_with_shorter_offtime() -> None:
    config_path = Path("config/exploration_medium_fast.json")
    config = load_input_config(config_path)

    assert config_display_name(config_path) == "Exploration Medium Fast"
    assert config.on_frames == 2
    assert config.off_frames == 4
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


def test_exploration_medium_medium_fast_keeps_spread_with_mid_offtime() -> None:
    config_path = Path("config/exploration_medium_medium_fast.json")
    config = load_input_config(config_path)

    assert config_display_name(config_path) == "Exploration Medium Medium Fast"
    assert config.on_frames == 2
    assert config.off_frames == 8
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


def test_super_duper_exploration_uses_stride_mapping() -> None:
    config_path = Path("config/super_duper_exploration.json")
    config = load_input_config(config_path)

    assert config_display_name(config_path) == "Super Duper Exploration"
    assert config.mapping_mode == "digit_stride"
    assert config.on_frames == 4
    assert config.off_frames == 13
    assert config.digits_per_input == 2

    counts: dict[str, int] = {}
    for value in range(100):
        button = button_for_value(value, config)
        counts[button] = counts.get(button, 0) + 1

    assert counts == {
        "up": 20,
        "down": 20,
        "left": 20,
        "right": 20,
        "a": 10,
        "b": 9,
        "start": 1,
    }
    assert action_for_value(0, config).repetitions == 1
    assert action_for_value(9, config).repetitions == 10
    assert action_for_value(79, config).button == "right"
    assert action_for_value(79, config).repetitions == 10
    assert action_for_value(80, config).button == "a"
    assert action_for_value(89, config).repetitions == 1
    assert action_for_value(99, config).button == "start"
    assert action_for_value(99, config).repetitions == 1
    assert abs(average_frames_per_input(config) - 78.2) < 0.0001


def test_super_duper_exploration_repeats_directional_cycles() -> None:
    config = load_input_config(Path("config/super_duper_exploration.json"))
    pyboy = FakePyBoy()

    result = advance_pi_inputs(
        pyboy,  # type: ignore[arg-type]
        "090999",
        0,
        6,
        config.on_frames,
        config.off_frames,
        input_config=config,
    )

    assert result.digits_consumed == 6
    assert result.inputs_sent == 3
    assert result.last_button == "start"
    assert result.frames_advanced == (10 + 10 + 1) * (config.on_frames + config.off_frames)
    assert sum(1 for event in pyboy.events if event == ("press", "up")) == 20
    assert sum(1 for event in pyboy.events if event == ("press", "start")) == 1
