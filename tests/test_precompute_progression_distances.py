import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from precompute_progression_distances import build_cache, encode_distances_by_map
from progression_pathfinding import Tile
from progression_world import progression_state_for_gate


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


def test_progression_state_uses_cached_distance_when_available() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_path = Path(temp_dir) / "cache.json"
        cache_path.write_text(
            json.dumps(
                {
                    "progression_gates": {
                        "test_gate": {
                            "distances": {
                                "0": [[5, 6, 100]],
                                "1": [[2, 3, 17], [4, 5, 41], [23, 26, 30]],
                            }
                        }
                    },
                    "checkpoints": {
                        "pallet_home": {
                            "distances": {
                                "1": [[2, 3, 12]],
                            }
                        },
                        "viridian_pokecenter": {
                            "distances": {
                                "1": [[2, 3, 8]],
                            }
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        state = progression_state_for_gate(
            {"id": "test_gate", "label": "Test gate", "targets": [(1, 0, 0)]},
            Tile(1, 2, 3),
            Tile(1, 4, 5),
            distance_cache_path=str(cache_path),
        )

        assert state["distance_source"] == "cache"
        assert state["remaining_steps"] == 17
        assert state["total_steps_from_respawn"] == 41
        assert state["graph_max_steps"] == 82
        assert state["nearest_closer_checkpoint"]["id"] == "viridian_pokecenter"
        assert state["nearest_closer_checkpoint"]["steps"] == 8
        assert state["nearest_closer_checkpoint"]["checkpoint_progression_steps"] == 30


def test_progression_state_allows_no_nearest_closer_checkpoint() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_path = Path(temp_dir) / "cache.json"
        cache_path.write_text(
            json.dumps(
                {
                    "progression_gates": {
                        "test_gate": {
                            "distances": {
                                "1": [[2, 3, 17], [4, 5, 30], [23, 26, 30]],
                            }
                        }
                    },
                    "checkpoints": {
                        "viridian_pokecenter": {
                            "distances": {
                                "1": [[2, 3, 8]],
                            }
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        state = progression_state_for_gate(
            {"id": "test_gate", "label": "Test gate", "targets": [(1, 0, 0)]},
            Tile(1, 2, 3),
            Tile(1, 4, 5),
            distance_cache_path=str(cache_path),
        )

        assert state["nearest_closer_checkpoint"] is None


def test_progression_state_falls_back_when_cache_misses() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        world_path = Path(temp_dir) / "world.json"
        cache_path = Path(temp_dir) / "cache.json"
        world_path.write_text(
            json.dumps(
                {
                    "maps": {
                        "1": {
                            "width": 3,
                            "height": 1,
                            "walkable": [[0, 0], [1, 0], [2, 0]],
                        }
                    },
                    "warps": [],
                }
            ),
            encoding="utf-8",
        )
        cache_path.write_text(json.dumps({"progression_gates": {"test_gate": {"distances": {}}}}), encoding="utf-8")
        state = progression_state_for_gate(
            {"id": "test_gate", "label": "Test gate", "targets": [(1, 2, 0)]},
            Tile(1, 0, 0),
            world_path=str(world_path),
            distance_cache_path=str(cache_path),
        )

        assert "distance_source" not in state
        assert state["remaining_steps"] == 2
        assert state["reachable"] is True
