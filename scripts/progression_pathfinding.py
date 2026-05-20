from __future__ import annotations

import heapq
from collections.abc import Iterable
from dataclasses import dataclass, field


Direction = str


@dataclass(frozen=True, order=True)
class Tile:
    map_id: int | str
    x: int
    y: int


@dataclass(frozen=True)
class Warp:
    source: Tile
    destination: Tile
    cost: int = 1
    required_flags: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Ledge:
    source: Tile
    destination: Tile
    cost: int = 1
    required_flags: frozenset[str] = frozenset()


@dataclass
class MapGrid:
    map_id: int | str
    width: int
    height: int
    blocked: set[tuple[int, int]] = field(default_factory=set)
    blocked_edges: set[tuple[Tile, Tile]] = field(default_factory=set)
    ledges: list[Ledge] = field(default_factory=list)

    def contains(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def is_walkable(self, x: int, y: int) -> bool:
        return self.contains(x, y) and (x, y) not in self.blocked

    def tile(self, x: int, y: int) -> Tile:
        return Tile(self.map_id, x, y)

    def blocks_edge(self, source: Tile, destination: Tile) -> bool:
        return (source, destination) in self.blocked_edges


@dataclass
class WorldGraph:
    maps: dict[int | str, MapGrid]
    warps: list[Warp] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._warps_by_source: dict[Tile, list[Warp]] = {}
        self._ledges_by_source: dict[Tile, list[Ledge]] = {}
        for warp in self.warps:
            self._warps_by_source.setdefault(warp.source, []).append(warp)
        for grid in self.maps.values():
            for ledge in grid.ledges:
                self._ledges_by_source.setdefault(ledge.source, []).append(ledge)

    def has_tile(self, tile: Tile) -> bool:
        grid = self.maps.get(tile.map_id)
        return grid is not None and grid.is_walkable(tile.x, tile.y)

    def neighbors(self, tile: Tile, flags: set[str] | frozenset[str] | None = None) -> Iterable[tuple[Tile, int]]:
        if not self.has_tile(tile):
            return

        active_flags = set(flags or ())
        grid = self.maps[tile.map_id]
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            neighbor = grid.tile(tile.x + dx, tile.y + dy)
            if grid.is_walkable(neighbor.x, neighbor.y) and not grid.blocks_edge(tile, neighbor):
                yield neighbor, 1

        for ledge in self._ledges_by_source.get(tile, ()):
            if ledge.required_flags.issubset(active_flags) and self.has_tile(ledge.destination):
                yield ledge.destination, ledge.cost

        for warp in self._warps_by_source.get(tile, ()):
            if warp.required_flags.issubset(active_flags) and self.has_tile(warp.destination):
                yield warp.destination, warp.cost


@dataclass(frozen=True)
class PathResult:
    steps: int
    path: tuple[Tile, ...]


def shortest_path(
    world: WorldGraph,
    start: Tile,
    targets: Iterable[Tile],
    flags: set[str] | frozenset[str] | None = None,
) -> PathResult | None:
    target_set = {target for target in targets if world.has_tile(target)}
    if not world.has_tile(start) or not target_set:
        return None

    frontier: list[tuple[int, Tile]] = [(0, start)]
    best: dict[Tile, int] = {start: 0}
    previous: dict[Tile, Tile | None] = {start: None}

    while frontier:
        steps, tile = heapq.heappop(frontier)
        if steps != best[tile]:
            continue
        if tile in target_set:
            return PathResult(steps=steps, path=reconstruct_path(previous, tile))

        for neighbor, cost in world.neighbors(tile, flags):
            if cost < 0:
                raise ValueError("Path costs must be non-negative.")
            next_steps = steps + cost
            if next_steps < best.get(neighbor, 1_000_000_000):
                best[neighbor] = next_steps
                previous[neighbor] = tile
                heapq.heappush(frontier, (next_steps, neighbor))

    return None


def reconstruct_path(previous: dict[Tile, Tile | None], end: Tile) -> tuple[Tile, ...]:
    path = [end]
    while previous[path[-1]] is not None:
        path.append(previous[path[-1]])
    return tuple(reversed(path))


def progression_distance(
    world: WorldGraph,
    respawn: Tile,
    current: Tile,
    objective_tiles: Iterable[Tile],
    flags: set[str] | frozenset[str] | None = None,
) -> dict[str, object]:
    objectives = tuple(objective_tiles)
    total = shortest_path(world, respawn, objectives, flags)
    remaining = shortest_path(world, current, objectives, flags)
    if total is None or remaining is None:
        return {
            "reachable": False,
            "total_steps": None,
            "remaining_steps": None,
            "progress": 0.0,
            "path": (),
        }

    progress = 1 - (remaining.steps / max(total.steps, 1))
    return {
        "reachable": True,
        "total_steps": total.steps,
        "remaining_steps": remaining.steps,
        "progress": max(0.0, min(1.0, progress)),
        "path": remaining.path,
    }
