import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from review_pi_checkpoint import (
    EVO_NEW_SPECIES_ADDR,
    EVO_OLD_SPECIES_ADDR,
    EVOLUTION_OCCURRED_ADDR,
    PARTY_COUNT_ADDR,
    PARTY_SPECIES_ADDR,
    evolution_marker,
    has_evolution_started,
    is_evolution_active,
)


class Memory:
    def __init__(self) -> None:
        self.values: dict[int, int] = {}

    def __getitem__(self, address: int) -> int:
        return self.values.get(address, 0)


class FakePyBoy:
    def __init__(self) -> None:
        self.memory = Memory()


def test_evolution_active_from_evolution_flag() -> None:
    pyboy = FakePyBoy()
    pyboy.memory.values[EVOLUTION_OCCURRED_ADDR] = 1

    assert is_evolution_active(pyboy)
    assert evolution_marker(pyboy) == (1, 0, 0)


def test_evolution_started_from_old_and_new_species() -> None:
    pyboy = FakePyBoy()
    starting_marker = evolution_marker(pyboy)
    pyboy.memory.values[EVO_OLD_SPECIES_ADDR] = 153
    pyboy.memory.values[EVO_NEW_SPECIES_ADDR] = 9

    assert has_evolution_started(pyboy, starting_marker, ())


def test_evolution_started_from_party_species_change() -> None:
    pyboy = FakePyBoy()
    pyboy.memory.values[PARTY_COUNT_ADDR] = 1
    pyboy.memory.values[PARTY_SPECIES_ADDR] = 9

    assert has_evolution_started(pyboy, evolution_marker(pyboy), (153,))
