import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from review_pi_checkpoint import (
    GAMEBOY_FPS,
    PLAYER_MONEY_ADDR,
    PLAY_TIME_HOURS_ADDR,
    PLAY_TIME_MINUTES_ADDR,
    PLAY_TIME_SECONDS_ADDR,
    POKEDEX_OWNED_ADDR,
    POKEDEX_SEEN_ADDR,
    count_pokedex_flags,
    elapsed_play_time,
    play_time,
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
    frames = int(((300 * 3600) + (12 * 60) + 34) * GAMEBOY_FPS)

    assert elapsed_play_time(frames) == {
        "hours": 300,
        "minutes": 12,
        "seconds": 34,
        "total_seconds": 1_080_754,
    }
