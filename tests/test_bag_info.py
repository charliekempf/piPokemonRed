import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from review_pi_checkpoint import BAG_COUNT_ADDR, BAG_ITEMS_ADDR, ReviewSession, has_bag_item_gain, item_name


class NoopLock:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: object) -> None:
        return None


class Memory:
    def __init__(self) -> None:
        self.values: dict[int, int] = {}

    def __getitem__(self, address: int) -> int:
        return self.values.get(address, 0)


class FakePyBoy:
    def __init__(self) -> None:
        self.memory = Memory()


def test_bag_reads_item_quantity_pairs() -> None:
    session = object.__new__(ReviewSession)
    session._lock = NoopLock()
    session.pyboy = FakePyBoy()
    session.pyboy.memory.values[BAG_COUNT_ADDR] = 2
    session.pyboy.memory.values[BAG_ITEMS_ADDR] = 0x14
    session.pyboy.memory.values[BAG_ITEMS_ADDR + 1] = 3
    session.pyboy.memory.values[BAG_ITEMS_ADDR + 2] = 0xC6
    session.pyboy.memory.values[BAG_ITEMS_ADDR + 3] = 1

    assert session.bag() == [
        {"slot": 1, "id": 0x14, "name": "Potion", "quantity": 3},
        {"slot": 2, "id": 0xC6, "name": "HM03 Surf", "quantity": 1},
    ]


def test_item_name_formats_unknown_ids() -> None:
    assert item_name(0xFA) == "TM50 Substitute"
    assert item_name(0xFE) == "Item $FE"


def test_has_bag_item_gain_detects_quantity_increase() -> None:
    pyboy = FakePyBoy()
    pyboy.memory.values[BAG_COUNT_ADDR] = 1
    pyboy.memory.values[BAG_ITEMS_ADDR] = 0x14
    pyboy.memory.values[BAG_ITEMS_ADDR + 1] = 3

    assert not has_bag_item_gain(pyboy, {0x14: 3})
    assert has_bag_item_gain(pyboy, {0x14: 2})
    assert has_bag_item_gain(pyboy, {})
