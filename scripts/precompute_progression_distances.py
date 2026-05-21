from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from progression_pathfinding import Tile, WorldGraph, distances_to_targets
from progression_world import CHECKPOINT_TILES, PROGRESSION_GATES, load_world


DEFAULT_OUTPUT = Path("results") / "progression_distance_cache.json"


def tile_from_triplet(raw_tile: tuple[int, int, int]) -> Tile:
    map_id, x, y = raw_tile
    return Tile(map_id, x, y)


def encode_distances_by_map(distances: dict[Tile, int]) -> dict[str, list[list[int]]]:
    by_map: dict[str, list[list[int]]] = {}
    for tile, steps in sorted(distances.items(), key=lambda item: (int(item[0].map_id), item[0].y, item[0].x)):
        by_map.setdefault(str(tile.map_id), []).append([tile.x, tile.y, steps])
    return by_map


def distance_summary(distances: dict[Tile, int]) -> dict[str, int | None]:
    values = list(distances.values())
    return {
        "reachable_tiles": len(values),
        "min_distance": min(values) if values else None,
        "max_distance": max(values) if values else None,
    }


def precompute_target_distances(world: WorldGraph, targets: list[Tile]) -> dict[str, Any]:
    distances = distances_to_targets(world, targets)
    return {
        **distance_summary(distances),
        "distances": encode_distances_by_map(distances),
    }


def build_cache(world_path: Path) -> dict[str, Any]:
    world = load_world(str(world_path))
    if world is None:
        raise FileNotFoundError(f"Progression world database not found: {world_path}")

    walkable_tiles = list(world.walkable_tiles())
    gates: dict[str, dict[str, Any]] = {}
    for gate in PROGRESSION_GATES:
        targets = [tile_from_triplet(tuple(raw_target)) for raw_target in gate["targets"]]
        gates[str(gate["id"])] = {
            "label": gate["label"],
            "targets": [[int(tile.map_id), tile.x, tile.y] for tile in targets],
            **precompute_target_distances(world, targets),
        }

    checkpoints: dict[str, dict[str, Any]] = {}
    for checkpoint in CHECKPOINT_TILES:
        tile = tile_from_triplet(tuple(checkpoint["tile"]))
        checkpoints[str(checkpoint["id"])] = {
            "label": checkpoint["label"],
            "tile": [int(tile.map_id), tile.x, tile.y],
            **precompute_target_distances(world, [tile]),
        }

    return {
        "schema_version": 1,
        "source": str(world_path),
        "generated_at": datetime.now(UTC).isoformat(),
        "walkable_tiles": len(walkable_tiles),
        "progression_gate_count": len(gates),
        "checkpoint_count": len(checkpoints),
        "progression_gates": gates,
        "checkpoints": checkpoints,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Precompute Pokemon Red progression and checkpoint distances for every walkable tile."
    )
    parser.add_argument("--world", type=Path, default=Path("results") / "progression_world.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    cache = build_cache(args.world)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(cache, handle, separators=(",", ":"))
    print(
        "Wrote "
        f"{cache['progression_gate_count']} progression gates and "
        f"{cache['checkpoint_count']} checkpoints across "
        f"{cache['walkable_tiles']} walkable tiles to {args.output}"
    )


if __name__ == "__main__":
    main()
