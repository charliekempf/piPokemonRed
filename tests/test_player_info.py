import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from review_pi_checkpoint import (
    GAMEBOY_FPS,
    CURRENT_MAP_ADDR,
    PLAYER_X_ADDR,
    PLAYER_Y_ADDR,
    PLAYER_MONEY_ADDR,
    PLAY_TIME_HOURS_ADDR,
    PLAY_TIME_MINUTES_ADDR,
    PLAY_TIME_SECONDS_ADDR,
    POKEDEX_OWNED_ADDR,
    POKEDEX_SEEN_ADDR,
    count_pokedex_flags,
    elapsed_play_time,
    current_player_tile,
    play_time,
    record_low_distance_checks_to_skip,
    progression_record_low_skip_count,
    progression_state,
    read_bcd_money,
)


class Memory:
    def __init__(self) -> None:
        self.values: dict[int, int] = {}

    def __getitem__(self, address: int) -> int:
        return self.values.get(address, 0)


class FakePyBoy:
    def __init__(self) -> None:
        self.memory = Memory()


def test_read_bcd_money() -> None:
    pyboy = FakePyBoy()
    pyboy.memory.values[PLAYER_MONEY_ADDR] = 0x12
    pyboy.memory.values[PLAYER_MONEY_ADDR + 1] = 0x34
    pyboy.memory.values[PLAYER_MONEY_ADDR + 2] = 0x56

    assert read_bcd_money(pyboy) == 123456


def test_count_pokedex_flags() -> None:
    pyboy = FakePyBoy()
    pyboy.memory.values[POKEDEX_SEEN_ADDR] = 0b10101101
    pyboy.memory.values[POKEDEX_OWNED_ADDR] = 0b00000011

    assert count_pokedex_flags(pyboy, POKEDEX_SEEN_ADDR) == 5
    assert count_pokedex_flags(pyboy, POKEDEX_OWNED_ADDR) == 2


def test_play_time_uses_display_bytes() -> None:
    pyboy = FakePyBoy()
    pyboy.memory.values[PLAY_TIME_HOURS_ADDR] = 0x99
    pyboy.memory.values[PLAY_TIME_HOURS_ADDR + 1] = 12
    pyboy.memory.values[PLAY_TIME_MINUTES_ADDR] = 0x99
    pyboy.memory.values[PLAY_TIME_MINUTES_ADDR + 1] = 34
    pyboy.memory.values[PLAY_TIME_SECONDS_ADDR] = 56

    assert play_time(pyboy) == {"hours": 12, "minutes": 34, "seconds": 56}


def test_elapsed_play_time_uses_frames_not_capped_display_clock() -> None:
    frames = int(((300 * 3600) + (12 * 60) + 34) * GAMEBOY_FPS) + 1

    assert elapsed_play_time(frames) == {
        "hours": 300,
        "minutes": 12,
        "seconds": 34,
        "total_seconds": 1_080_754,
    }


def test_current_player_tile_reads_map_and_coordinates() -> None:
    pyboy = FakePyBoy()
    pyboy.memory.values[CURRENT_MAP_ADDR] = 0x01
    pyboy.memory.values[PLAYER_X_ADDR] = 7
    pyboy.memory.values[PLAYER_Y_ADDR] = 9

    assert current_player_tile(pyboy) == {"map_id": 1, "x": 7, "y": 9}


def test_progression_state_exposes_current_tile() -> None:
    pyboy = FakePyBoy()
    pyboy.memory.values[CURRENT_MAP_ADDR] = 0x02
    pyboy.memory.values[PLAYER_X_ADDR] = 4
    pyboy.memory.values[PLAYER_Y_ADDR] = 6

    state = progression_state(pyboy)

    assert state["label"]
    assert state["current_tile"] == {"map_id": 2, "x": 4, "y": 6}
    assert "remaining_steps" in state
    assert "total_steps_from_respawn" in state


def test_progression_record_low_skip_count_scales_by_tens() -> None:
    assert progression_record_low_skip_count(100, 100) == 0
    assert progression_record_low_skip_count(110, 100) == 0
    assert progression_record_low_skip_count(111, 100) == 1
    assert progression_record_low_skip_count(120, 100) == 1
    assert progression_record_low_skip_count(121, 100) == 2


def test_record_low_distance_checks_to_skip_scales_when_far_from_record() -> None:
    assert record_low_distance_checks_to_skip(100, 100) == 0
    assert record_low_distance_checks_to_skip(110, 100) == 0
    assert record_low_distance_checks_to_skip(111, 100) == 1
    assert record_low_distance_checks_to_skip(120, 100) == 1
    assert record_low_distance_checks_to_skip(121, 100) == 2
    assert record_low_distance_checks_to_skip(250, 100) == 14
