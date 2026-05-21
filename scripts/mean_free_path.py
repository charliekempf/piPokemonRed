from __future__ import annotations

import argparse
import json
import math
import random
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DIRECTIONS: tuple[tuple[str, int, int], ...] = (
    ("Up", 0, -1),
    ("Down", 0, 1),
    ("Left", -1, 0),
    ("Right", 1, 0),
)


@dataclass(frozen=True)
class MapData:
    map_id: int
    name: str
    width: int
    height: int
    walkable: frozenset[tuple[int, int]]


@dataclass(frozen=True)
class StepResult:
    map_id: int
    x: int
    y: int


def load_database(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_maps(database: dict[str, Any]) -> dict[int, MapData]:
    maps: dict[int, MapData] = {}
    for raw_id, raw_map in database.get("maps", {}).items():
        map_id = int(raw_id)
        maps[map_id] = MapData(
            map_id=map_id,
            name=str(raw_map.get("name", f"MAP_{map_id:02X}")),
            width=int(raw_map["width"]),
            height=int(raw_map["height"]),
            walkable=frozenset((int(x), int(y)) for x, y in raw_map.get("walkable", [])),
        )
    return maps


def connection_lookup(database: dict[str, Any], maps: dict[int, MapData]) -> dict[tuple[int, int, int, int, int], StepResult]:
    """Return only straight-through outdoor connection warps keyed by source edge and direction."""
    lookup: dict[tuple[int, int, int, int, int], StepResult] = {}
    for raw_warp in database.get("warps", []):
        source_map, source_x, source_y = (int(value) for value in raw_warp["source"])
        dest_map, dest_x, dest_y = (int(value) for value in raw_warp["destination"])
        source = maps.get(source_map)
        dest = maps.get(dest_map)
        if source is None or dest is None:
            continue

        if source_y == 0 and dest_y == dest.height - 1:
            lookup[(source_map, source_x, source_y, 0, -1)] = StepResult(dest_map, dest_x, dest_y)
        elif source_y == source.height - 1 and dest_y == 0:
            lookup[(source_map, source_x, source_y, 0, 1)] = StepResult(dest_map, dest_x, dest_y)
        elif source_x == 0 and dest_x == dest.width - 1:
            lookup[(source_map, source_x, source_y, -1, 0)] = StepResult(dest_map, dest_x, dest_y)
        elif source_x == source.width - 1 and dest_x == 0:
            lookup[(source_map, source_x, source_y, 1, 0)] = StepResult(dest_map, dest_x, dest_y)
    return lookup


def all_walkable_tiles(maps: dict[int, MapData]) -> list[StepResult]:
    return [
        StepResult(map_id, x, y)
        for map_id, map_data in maps.items()
        for x, y in map_data.walkable
    ]


def next_step(
    maps: dict[int, MapData],
    connections: dict[tuple[int, int, int, int, int], StepResult],
    state: StepResult,
    dx: int,
    dy: int,
) -> StepResult | None:
    map_data = maps[state.map_id]
    next_x = state.x + dx
    next_y = state.y + dy
    if 0 <= next_x < map_data.width and 0 <= next_y < map_data.height:
        return StepResult(state.map_id, next_x, next_y) if (next_x, next_y) in map_data.walkable else None
    connection = connections.get((state.map_id, state.x, state.y, dx, dy))
    if connection is None:
        return None
    dest = maps.get(connection.map_id)
    if dest is None or (connection.x, connection.y) not in dest.walkable:
        return None
    return connection


def free_path_length(
    maps: dict[int, MapData],
    connections: dict[tuple[int, int, int, int, int], StepResult],
    start: StepResult,
    dx: int,
    dy: int,
) -> int:
    steps = 0
    state = start
    seen = {(state.map_id, state.x, state.y)}
    while True:
        candidate = next_step(maps, connections, state, dx, dy)
        if candidate is None:
            return steps
        key = (candidate.map_id, candidate.x, candidate.y)
        if key in seen:
            raise RuntimeError(f"Straight-line path looped at map {candidate.map_id} tile ({candidate.x}, {candidate.y}).")
        seen.add(key)
        steps += 1
        state = candidate


def online_stats(samples: Iterable[int]) -> tuple[int, float, float, int, int]:
    count = 0
    mean = 0.0
    m2 = 0.0
    minimum: int | None = None
    maximum: int | None = None
    for sample in samples:
        count += 1
        delta = sample - mean
        mean += delta / count
        m2 += delta * (sample - mean)
        minimum = sample if minimum is None else min(minimum, sample)
        maximum = sample if maximum is None else max(maximum, sample)
    variance = m2 / (count - 1) if count > 1 else 0.0
    return count, mean, variance, int(minimum or 0), int(maximum or 0)


def exact_lengths(
    maps: dict[int, MapData],
    connections: dict[tuple[int, int, int, int, int], StepResult],
    tiles: list[StepResult],
) -> list[int]:
    return [
        free_path_length(maps, connections, tile, dx, dy)
        for tile in tiles
        for _, dx, dy in DIRECTIONS
    ]


def sample_until_stable(
    maps: dict[int, MapData],
    connections: dict[tuple[int, int, int, int, int], StepResult],
    tiles: list[StepResult],
    *,
    relative_three_sigma: float,
    absolute_three_sigma: float | None,
    min_samples: int,
    batch_size: int,
    max_samples: int,
    seed: int,
) -> tuple[int, float, float, float, int, int]:
    rng = random.Random(seed)
    count = 0
    mean = 0.0
    m2 = 0.0
    minimum: int | None = None
    maximum: int | None = None

    while count < max_samples:
        for _ in range(min(batch_size, max_samples - count)):
            tile = rng.choice(tiles)
            _, dx, dy = rng.choice(DIRECTIONS)
            sample = free_path_length(maps, connections, tile, dx, dy)
            count += 1
            delta = sample - mean
            mean += delta / count
            m2 += delta * (sample - mean)
            minimum = sample if minimum is None else min(minimum, sample)
            maximum = sample if maximum is None else max(maximum, sample)

        if count < max(2, min_samples):
            continue
        variance = m2 / (count - 1)
        three_sigma_error = 3 * math.sqrt(variance / count)
        relative_limit = abs(mean) * relative_three_sigma
        limit = relative_limit if absolute_three_sigma is None else min(relative_limit, absolute_three_sigma)
        if three_sigma_error <= limit:
            return count, mean, variance, three_sigma_error, int(minimum or 0), int(maximum or 0)

    variance = m2 / (count - 1) if count > 1 else 0.0
    three_sigma_error = 3 * math.sqrt(variance / count) if count else 0.0
    return count, mean, variance, three_sigma_error, int(minimum or 0), int(maximum or 0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Estimate Pokemon Red map mean free path from walkable collision tiles.")
    parser.add_argument("--database", type=Path, default=Path("results") / "progression_world.json")
    parser.add_argument("--relative-three-sigma", type=float, default=0.01, help="Stop when 3*SEM is below this fraction of the mean.")
    parser.add_argument("--absolute-three-sigma", type=float, default=None, help="Optional absolute 3*SEM stopping bound in steps.")
    parser.add_argument("--min-samples", type=int, default=10_000)
    parser.add_argument("--batch-size", type=int, default=10_000)
    parser.add_argument("--max-samples", type=int, default=10_000_000)
    parser.add_argument("--seed", type=int, default=314159)
    parser.add_argument("--exact", action="store_true", help="Also compute the exact mean over every walkable tile and direction.")
    args = parser.parse_args()

    database = load_database(args.database)
    maps = load_maps(database)
    connections = connection_lookup(database, maps)
    tiles = all_walkable_tiles(maps)
    if not tiles:
        raise SystemExit("No walkable tiles found in progression database.")

    count, mean, variance, error, minimum, maximum = sample_until_stable(
        maps,
        connections,
        tiles,
        relative_three_sigma=args.relative_three_sigma,
        absolute_three_sigma=args.absolute_three_sigma,
        min_samples=args.min_samples,
        batch_size=args.batch_size,
        max_samples=args.max_samples,
        seed=args.seed,
    )
    print(f"Walkable tiles: {len(tiles):,}")
    print(f"Straight-through map connections: {len(connections):,}")
    print(f"Samples: {count:,}")
    print(f"Mean free path: {mean:.4f} steps")
    print(f"3-sigma standard-error bound: +/- {error:.4f} steps ({(error / mean * 100) if mean else 0:.3f}%)")
    print(f"Sample standard deviation: {math.sqrt(variance):.4f} steps")
    print(f"Observed range: {minimum:,} to {maximum:,} steps")

    if args.exact:
        exact_count, exact_mean, exact_variance, exact_min, exact_max = online_stats(exact_lengths(maps, connections, tiles))
        exact_error = 3 * math.sqrt(exact_variance / exact_count) if exact_count else 0.0
        print()
        print("Exact finite-population check:")
        print(f"Tile-direction states: {exact_count:,}")
        print(f"Mean free path: {exact_mean:.4f} steps")
        print(f"Population tile-direction SD: {math.sqrt(exact_variance):.4f} steps")
        print(f"3-sigma standard-error if sampled once per state: +/- {exact_error:.4f} steps")
        print(f"Exact range: {exact_min:,} to {exact_max:,} steps")


if __name__ == "__main__":
    main()
