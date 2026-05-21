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


def write_distribution_svg(lengths: list[int], output: Path) -> None:
    if not lengths:
        raise ValueError("Cannot graph an empty distribution.")

    count, mean, variance, minimum, maximum = online_stats(lengths)
    standard_deviation = math.sqrt(variance)
    frequencies: dict[int, int] = {}
    for length in lengths:
        frequencies[length] = frequencies.get(length, 0) + 1

    width = 1200
    height = 720
    margin_left = 88
    margin_right = 38
    margin_top = 76
    margin_bottom = 82
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    max_frequency = max(frequencies.values())
    max_probability = max_frequency / count
    max_x = max(maximum, 1)

    def x_pos(value: float) -> float:
        return margin_left + (value / max_x) * plot_width

    def y_pos(probability: float) -> float:
        return margin_top + plot_height - (probability / max_probability) * plot_height

    bar_gap = 0.55
    bar_width = max(1.0, plot_width / (max_x + 1) - bar_gap)
    bars: list[str] = []
    for length in range(minimum, maximum + 1):
        frequency = frequencies.get(length, 0)
        if frequency <= 0:
            continue
        probability = frequency / count
        x = x_pos(length)
        y = y_pos(probability)
        bar_height = margin_top + plot_height - y
        bars.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{bar_height:.2f}" '
            f'rx="1.5" fill="#4f9cff"><title>{length} steps: {probability:.5%}</title></rect>'
        )

    grid_lines: list[str] = []
    for index in range(6):
        probability = max_probability * index / 5
        y = y_pos(probability)
        grid_lines.append(f'<line x1="{margin_left}" y1="{y:.2f}" x2="{width - margin_right}" y2="{y:.2f}" stroke="#233041" stroke-width="1"/>')
        grid_lines.append(
            f'<text x="{margin_left - 12}" y="{y + 5:.2f}" text-anchor="end" fill="#9fb0c4" font-size="14">{probability:.1%}</text>'
        )

    x_ticks: list[str] = []
    tick_count = 10
    for index in range(tick_count + 1):
        value = round(max_x * index / tick_count)
        x = x_pos(value)
        x_ticks.append(f'<line x1="{x:.2f}" y1="{margin_top + plot_height}" x2="{x:.2f}" y2="{margin_top + plot_height + 8}" stroke="#9fb0c4" stroke-width="1"/>')
        x_ticks.append(f'<text x="{x:.2f}" y="{height - 42}" text-anchor="middle" fill="#9fb0c4" font-size="14">{value}</text>')

    mean_x = x_pos(mean)
    minus_sigma_x = x_pos(max(0, mean - standard_deviation))
    plus_sigma_x = x_pos(min(max_x, mean + standard_deviation))
    annotation_top = margin_top + 8

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#0f1722"/>
  <text x="{margin_left}" y="38" fill="#f5f7fb" font-size="26" font-family="Segoe UI, Arial, sans-serif" font-weight="700">Pokemon Red Map Mean Free Path Distribution</text>
  <text x="{margin_left}" y="62" fill="#9fb0c4" font-size="15" font-family="Segoe UI, Arial, sans-serif">Exact distribution across {count:,} walkable tile-direction states</text>
  <g font-family="Segoe UI, Arial, sans-serif">
    {''.join(grid_lines)}
    <line x1="{margin_left}" y1="{margin_top + plot_height}" x2="{width - margin_right}" y2="{margin_top + plot_height}" stroke="#d8e2ef" stroke-width="1.5"/>
    <line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_height}" stroke="#d8e2ef" stroke-width="1.5"/>
    {''.join(bars)}
    <rect x="{minus_sigma_x:.2f}" y="{annotation_top}" width="{plus_sigma_x - minus_sigma_x:.2f}" height="{plot_height - 12}" fill="#26c485" opacity="0.13"/>
    <line x1="{mean_x:.2f}" y1="{margin_top}" x2="{mean_x:.2f}" y2="{margin_top + plot_height}" stroke="#ffe066" stroke-width="3"/>
    <text x="{mean_x + 8:.2f}" y="{margin_top + 24}" fill="#ffe066" font-size="15">mean {mean:.2f}</text>
    <line x1="{minus_sigma_x:.2f}" y1="{margin_top}" x2="{minus_sigma_x:.2f}" y2="{margin_top + plot_height}" stroke="#26c485" stroke-width="2" stroke-dasharray="7 7"/>
    <line x1="{plus_sigma_x:.2f}" y1="{margin_top}" x2="{plus_sigma_x:.2f}" y2="{margin_top + plot_height}" stroke="#26c485" stroke-width="2" stroke-dasharray="7 7"/>
    <text x="{plus_sigma_x + 8:.2f}" y="{margin_top + 48}" fill="#26c485" font-size="15">±1 SD {standard_deviation:.2f}</text>
    {''.join(x_ticks)}
    <text x="{margin_left + plot_width / 2:.2f}" y="{height - 12}" text-anchor="middle" fill="#d8e2ef" font-size="16">free path length before collision (steps)</text>
    <text x="24" y="{margin_top + plot_height / 2:.2f}" transform="rotate(-90 24 {margin_top + plot_height / 2:.2f})" text-anchor="middle" fill="#d8e2ef" font-size="16">probability</text>
    <g transform="translate({width - 390} 32)">
      <rect x="0" y="0" width="350" height="92" rx="8" fill="#151f2c" stroke="#26364a"/>
      <text x="18" y="28" fill="#f5f7fb" font-size="16" font-weight="700">Summary</text>
      <text x="18" y="52" fill="#c7d4e5" font-size="14">Mean: {mean:.4f} steps</text>
      <text x="18" y="73" fill="#c7d4e5" font-size="14">Standard deviation: {standard_deviation:.4f} steps</text>
    </g>
  </g>
</svg>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")


def write_percentile_svg(lengths: list[int], output: Path) -> None:
    if not lengths:
        raise ValueError("Cannot graph an empty distribution.")

    count, mean, variance, minimum, maximum = online_stats(lengths)
    standard_deviation = math.sqrt(variance)
    frequencies: dict[int, int] = {}
    for length in lengths:
        frequencies[length] = frequencies.get(length, 0) + 1

    width = 1200
    height = 720
    margin_left = 88
    margin_right = 42
    margin_top = 76
    margin_bottom = 82
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    max_x = max(maximum + 1, 1)

    def x_pos(value: float) -> float:
        return margin_left + (value / max_x) * plot_width

    def y_pos(percent: float) -> float:
        return margin_top + plot_height - (percent / 100) * plot_height

    grid_lines: list[str] = []
    for percent in range(0, 101, 10):
        y = y_pos(percent)
        grid_lines.append(f'<line x1="{margin_left}" y1="{y:.2f}" x2="{width - margin_right}" y2="{y:.2f}" stroke="#233041" stroke-width="1"/>')
        grid_lines.append(
            f'<text x="{margin_left - 12}" y="{y + 5:.2f}" text-anchor="end" fill="#9fb0c4" font-size="14">{percent}%</text>'
        )

    x_ticks: list[str] = []
    tick_count = 10
    for index in range(tick_count + 1):
        value = round(max_x * index / tick_count)
        x = x_pos(value)
        x_ticks.append(f'<line x1="{x:.2f}" y1="{margin_top + plot_height}" x2="{x:.2f}" y2="{margin_top + plot_height + 8}" stroke="#9fb0c4" stroke-width="1"/>')
        x_ticks.append(f'<text x="{x:.2f}" y="{height - 42}" text-anchor="middle" fill="#9fb0c4" font-size="14">{value}</text>')

    points: list[str] = []
    cumulative_less_than = 0
    points.append(f"{x_pos(0):.2f},{y_pos(0):.2f}")
    for step_threshold in range(1, max_x + 1):
        cumulative_less_than += frequencies.get(step_threshold - 1, 0)
        percent_less_than = cumulative_less_than / count * 100
        points.append(f"{x_pos(step_threshold):.2f},{y_pos(percent_less_than):.2f}")

    percentile_marks = []
    cumulative = 0
    sorted_lengths = sorted(frequencies)
    for target in (50, 75, 90, 95, 99):
        threshold = maximum + 1
        for length in sorted_lengths:
            cumulative += frequencies[length]
            if cumulative / count * 100 >= target:
                threshold = length + 1
                break
        cumulative = 0
        x = x_pos(threshold)
        y = y_pos(target)
        percentile_marks.append(f'<line x1="{x:.2f}" y1="{y:.2f}" x2="{x:.2f}" y2="{margin_top + plot_height}" stroke="#26c485" stroke-width="1.5" stroke-dasharray="6 6"/>')
        percentile_marks.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4.5" fill="#26c485"/>')
        percentile_marks.append(f'<text x="{x + 7:.2f}" y="{y - 7:.2f}" fill="#26c485" font-size="13">P{target}: &lt; {threshold}</text>')

    mean_x = x_pos(mean)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#0f1722"/>
  <text x="{margin_left}" y="38" fill="#f5f7fb" font-size="26" font-family="Segoe UI, Arial, sans-serif" font-weight="700">Pokemon Red Map Mean Free Path Percentiles</text>
  <text x="{margin_left}" y="62" fill="#9fb0c4" font-size="15" font-family="Segoe UI, Arial, sans-serif">Y axis is the percentage of path samples with fewer steps than X</text>
  <g font-family="Segoe UI, Arial, sans-serif">
    {''.join(grid_lines)}
    <line x1="{margin_left}" y1="{margin_top + plot_height}" x2="{width - margin_right}" y2="{margin_top + plot_height}" stroke="#d8e2ef" stroke-width="1.5"/>
    <line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_height}" stroke="#d8e2ef" stroke-width="1.5"/>
    <polyline points="{' '.join(points)}" fill="none" stroke="#4f9cff" stroke-width="4" stroke-linejoin="round" stroke-linecap="round"/>
    <line x1="{mean_x:.2f}" y1="{margin_top}" x2="{mean_x:.2f}" y2="{margin_top + plot_height}" stroke="#ffe066" stroke-width="2.5"/>
    <text x="{mean_x + 8:.2f}" y="{margin_top + 24}" fill="#ffe066" font-size="15">mean {mean:.2f}</text>
    {''.join(percentile_marks)}
    {''.join(x_ticks)}
    <text x="{margin_left + plot_width / 2:.2f}" y="{height - 12}" text-anchor="middle" fill="#d8e2ef" font-size="16">free path threshold X (steps)</text>
    <text x="24" y="{margin_top + plot_height / 2:.2f}" transform="rotate(-90 24 {margin_top + plot_height / 2:.2f})" text-anchor="middle" fill="#d8e2ef" font-size="16">paths with fewer than X steps</text>
    <g transform="translate({width - 390} 32)">
      <rect x="0" y="0" width="350" height="92" rx="8" fill="#151f2c" stroke="#26364a"/>
      <text x="18" y="28" fill="#f5f7fb" font-size="16" font-weight="700">Summary</text>
      <text x="18" y="52" fill="#c7d4e5" font-size="14">Mean: {mean:.4f} steps</text>
      <text x="18" y="73" fill="#c7d4e5" font-size="14">Standard deviation: {standard_deviation:.4f} steps</text>
    </g>
  </g>
</svg>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")


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
    parser.add_argument("--distribution-svg", type=Path, help="Write an exact probability distribution histogram as an SVG.")
    parser.add_argument("--percentile-svg", type=Path, help="Write an exact cumulative percentile graph as an SVG.")
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
        lengths = exact_lengths(maps, connections, tiles)
        exact_count, exact_mean, exact_variance, exact_min, exact_max = online_stats(lengths)
        exact_error = 3 * math.sqrt(exact_variance / exact_count) if exact_count else 0.0
        print()
        print("Exact finite-population check:")
        print(f"Tile-direction states: {exact_count:,}")
        print(f"Mean free path: {exact_mean:.4f} steps")
        print(f"Population tile-direction SD: {math.sqrt(exact_variance):.4f} steps")
        print(f"3-sigma standard-error if sampled once per state: +/- {exact_error:.4f} steps")
        print(f"Exact range: {exact_min:,} to {exact_max:,} steps")
        if args.distribution_svg:
            write_distribution_svg(lengths, args.distribution_svg)
            print(f"Wrote distribution graph to {args.distribution_svg}")
        if args.percentile_svg:
            write_percentile_svg(lengths, args.percentile_svg)
            print(f"Wrote percentile graph to {args.percentile_svg}")
    elif args.distribution_svg or args.percentile_svg:
        lengths = exact_lengths(maps, connections, tiles)
        if args.distribution_svg:
            write_distribution_svg(lengths, args.distribution_svg)
            print(f"Wrote distribution graph to {args.distribution_svg}")
        if args.percentile_svg:
            write_percentile_svg(lengths, args.percentile_svg)
            print(f"Wrote percentile graph to {args.percentile_svg}")


if __name__ == "__main__":
    main()
