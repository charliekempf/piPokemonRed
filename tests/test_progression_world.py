import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from progression_pathfinding import Tile
from progression_world import (
    EVENT_BATTLED_RIVAL_IN_OAKS_LAB,
    EVENT_FLAGS_ADDR,
    EVENT_GOT_OAKS_PARCEL,
    EVENT_GOT_POKEDEX,
    EVENT_GOT_STARTER,
    active_progression_gate,
    progression_state_for_tile,
)
from review_pi_checkpoint import BAG_COUNT_ADDR, BAG_ITEMS_ADDR, PARTY_COUNT_ADDR


class Memory:
    def __init__(self) -> None:
        self.values: dict[int, int] = {}

    def __getitem__(self, address: int) -> int:
        return self.values.get(address, 0)


class FakePyBoy:
    def __init__(self) -> None:
        self.memory = Memory()


def set_event(pyboy: FakePyBoy, event_id: int) -> None:
    address = EVENT_FLAGS_ADDR + (event_id // 8)
    pyboy.memory.values[address] = pyboy.memory.values.get(address, 0) | (1 << (event_id % 8))


def test_active_progression_gate_starts_at_starter() -> None:
    pyboy = FakePyBoy()

    assert active_progression_gate(pyboy)["id"] == "choose_starter"


def test_active_progression_gate_tracks_lab_rival_after_starter() -> None:
    pyboy = FakePyBoy()
    pyboy.memory.values[PARTY_COUNT_ADDR] = 1
    set_event(pyboy, EVENT_GOT_STARTER)

    assert active_progression_gate(pyboy)["id"] == "rival_battle_1"


def test_active_progression_gate_finds_oaks_parcel_after_lab_rival() -> None:
    pyboy = FakePyBoy()
    pyboy.memory.values[PARTY_COUNT_ADDR] = 1
    set_event(pyboy, EVENT_GOT_STARTER)
    set_event(pyboy, EVENT_BATTLED_RIVAL_IN_OAKS_LAB)

    assert active_progression_gate(pyboy)["id"] == "receive_oaks_parcel"


def test_active_progression_gate_delivers_oaks_parcel_when_in_bag() -> None:
    pyboy = FakePyBoy()
    pyboy.memory.values[PARTY_COUNT_ADDR] = 1
    set_event(pyboy, EVENT_GOT_STARTER)
    set_event(pyboy, EVENT_BATTLED_RIVAL_IN_OAKS_LAB)
    set_event(pyboy, EVENT_GOT_OAKS_PARCEL)
    pyboy.memory.values[BAG_COUNT_ADDR] = 1
    pyboy.memory.values[BAG_ITEMS_ADDR] = 0x46
    pyboy.memory.values[BAG_ITEMS_ADDR + 1] = 1

    assert active_progression_gate(pyboy)["id"] == "deliver_oaks_parcel"


def test_active_progression_gate_does_not_treat_owned_starter_as_pokedex() -> None:
    pyboy = FakePyBoy()
    pyboy.memory.values[PARTY_COUNT_ADDR] = 1
    pyboy.memory.values[0xD2F7] = 1
    set_event(pyboy, EVENT_GOT_STARTER)
    set_event(pyboy, EVENT_BATTLED_RIVAL_IN_OAKS_LAB)

    assert active_progression_gate(pyboy)["id"] == "receive_oaks_parcel"


def test_active_progression_gate_advances_after_pokedex_event() -> None:
    pyboy = FakePyBoy()
    pyboy.memory.values[PARTY_COUNT_ADDR] = 1
    set_event(pyboy, EVENT_GOT_STARTER)
    set_event(pyboy, EVENT_BATTLED_RIVAL_IN_OAKS_LAB)
    set_event(pyboy, EVENT_GOT_OAKS_PARCEL)
    set_event(pyboy, EVENT_GOT_POKEDEX)

    assert active_progression_gate(pyboy)["id"] == "brock"


def test_progression_state_is_reachable_with_generated_database_when_available() -> None:
    if not (Path("results") / "progression_world.json").exists():
        return
    pyboy = FakePyBoy()
    pyboy.memory.values[PARTY_COUNT_ADDR] = 1
    set_event(pyboy, EVENT_GOT_STARTER)
    set_event(pyboy, EVENT_BATTLED_RIVAL_IN_OAKS_LAB)

    state = progression_state_for_tile(pyboy, Tile(0x0C, 8, 20))

    assert state["label"] == "Receive Oak's Parcel"
    assert state["remaining_steps"] == 61
    assert state["graph_max_steps"] == 122
    assert state["reachable"] is True
