import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_pi_pyboy import (
    action_for_value,
    advance_pi_inputs,
    average_frames_per_input,
    button_for_value,
    config_display_name,
    frames_for_digit_range,
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


def test_statistical_walk_config_spread() -> None:
    config_path = Path("config/statistical_walk.json")
    config = load_input_config(config_path)

    assert config_display_name(config_path) == "Statistical Walk"
    assert config.on_frames == 2
    assert config.off_frames == 1
    assert config.digits_per_input == 2

    counts: dict[str, int] = {}
    for value in range(100):
        button = button_for_value(value, config)
        counts[button] = counts.get(button, 0) + 1

    assert counts == {
        "a": 54,
        "up": 10,
        "down": 10,
        "left": 10,
        "right": 10,
        "b": 5,
        "start": 1,
    }


def test_super_walk_keeps_exploration_spread_with_step_timing() -> None:
    config_path = Path("config/super_walk.json")
    config = load_input_config(config_path)

    assert config_display_name(config_path) == "Super Walk"
    assert config.on_frames == 4
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


def test_super_stride_uses_stride_mapping() -> None:
    config_path = Path("config/super_stride.json")
    config = load_input_config(config_path)

    assert config_display_name(config_path) == "Super Stride"
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


def test_super_stride_repeats_directional_cycles() -> None:
    config = load_input_config(Path("config/super_stride.json"))
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


def test_super_stride_frame_count_is_digit_exact() -> None:
    config = load_input_config(Path("config/super_stride.json"))

    assert frames_for_digit_range("00098099", 0, 8, config) == (1 + 10 + 1 + 1) * (
        config.on_frames + config.off_frames
    )
    assert frames_for_digit_range("00098099", 2, 4, config) == 10 * (config.on_frames + config.off_frames)


def test_super_stride_input_window_marks_step_count() -> None:
    from review_pi_checkpoint import ReviewSession

    session = object.__new__(ReviewSession)
    session._lock = __import__("threading").Lock()
    session.digits_consumed = 0
    session.digits = "09798099"
    session.input_config = load_input_config(Path("config/super_stride.json"))

    items = session.input_window(previous_count=0, next_count=3)

    assert items[0]["button"] == "up"
    assert items[0]["step_count"] == 10
    assert items[1]["button"] == "right"
    assert items[1]["step_count"] == 10
    assert items[2]["button"] == "a"
    assert items[2]["step_count"] is None
    assert items[3]["button"] == "start"
    assert items[3]["step_count"] is None
