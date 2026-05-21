import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from precompute_progression_distances import build_cache, encode_distances_by_map
from progression_pathfinding import Tile


def test_encode_distances_by_map_sorts_tiles() -> None:
    distances = {
        Tile(2, 4, 1): 9,
        Tile(1, 3, 2): 5,
        Tile(1, 1, 0): 3,
    }

    assert encode_distances_by_map(distances) == {
        "1": [[1, 0, 3], [3, 2, 5]],
        "2": [[4, 1, 9]],
    }


def test_build_cache_includes_progression_gates_and_checkpoints() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        world_path = Path(temp_dir) / "world.json"
        world_path.write_text(
            json.dumps(
                {
                    "maps": {
                        "0": {
                            "width": 6,
                            "height": 7,
                            "walkable": [[x, y] for y in range(7) for x in range(6)],
                        },
                        "40": {
                            "width": 10,
                            "height": 8,
                            "walkable": [[x, y] for y in range(8) for x in range(10)],
                        },
                    },
                    "warps": [],
                }
            ),
            encoding="utf-8",
        )

        cache = build_cache(world_path)

        assert cache["walkable_tiles"] == 122
        assert cache["progression_gate_count"] == 36
        assert cache["checkpoint_count"] == 13
        assert cache["progression_gates"]["choose_starter"]["targets"] == [[40, 6, 4], [40, 7, 4], [40, 8, 4]]
        assert cache["checkpoints"]["pallet_home"]["tile"] == [0, 5, 6]
