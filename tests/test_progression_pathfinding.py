import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from progression_pathfinding import Ledge, MapGrid, Tile, Warp, WorldGraph, progression_distance, shortest_path


def test_shortest_path_routes_around_walls() -> None:
    grid = MapGrid("route", 5, 3, blocked={(2, 0), (2, 1)})
    world = WorldGraph({"route": grid})

    result = shortest_path(world, Tile("route", 0, 0), [Tile("route", 4, 0)])

    assert result is not None
    assert result.steps == 8
    assert Tile("route", 2, 0) not in result.path
    assert Tile("route", 2, 1) not in result.path


def test_shortest_path_sums_steps_across_warps() -> None:
    house = MapGrid("house", 3, 3)
    town = MapGrid("town", 5, 3, blocked={(1, 1), (2, 1), (3, 1)})
    world = WorldGraph(
        {"house": house, "town": town},
        warps=[
            Warp(Tile("house", 1, 2), Tile("town", 0, 1)),
            Warp(Tile("town", 0, 1), Tile("house", 1, 2)),
        ],
    )

    result = shortest_path(world, Tile("house", 1, 1), [Tile("town", 4, 1)])

    assert result is not None
    assert result.steps == 8
    assert result.path[0] == Tile("house", 1, 1)
    assert result.path[-1] == Tile("town", 4, 1)


def test_one_way_ledge_is_directional() -> None:
    upper = Tile("route", 1, 1)
    lower = Tile("route", 1, 2)
    grid = MapGrid(
        "route",
        3,
        4,
        blocked_edges={(upper, lower), (lower, upper)},
        ledges=[Ledge(upper, lower)],
    )
    world = WorldGraph({"route": grid})

    down = shortest_path(world, upper, [lower])
    up = shortest_path(world, lower, [upper])

    assert down is not None
    assert down.steps == 1
    assert up is not None
    assert up.steps > 1


def test_conditional_warp_requires_flag() -> None:
    outside = MapGrid("outside", 2, 1)
    gym = MapGrid("gym", 2, 1)
    world = WorldGraph(
        {"outside": outside, "gym": gym},
        warps=[Warp(Tile("outside", 1, 0), Tile("gym", 0, 0), required_flags=frozenset({"gym_unlocked"}))],
    )

    locked = shortest_path(world, Tile("outside", 0, 0), [Tile("gym", 1, 0)])
    unlocked = shortest_path(world, Tile("outside", 0, 0), [Tile("gym", 1, 0)], {"gym_unlocked"})

    assert locked is None
    assert unlocked is not None
    assert unlocked.steps == 3


def test_progression_distance_compares_current_to_respawn_route() -> None:
    grid = MapGrid("route", 6, 1)
    world = WorldGraph({"route": grid})

    distance = progression_distance(world, Tile("route", 0, 0), Tile("route", 2, 0), [Tile("route", 5, 0)])

    assert distance["reachable"] is True
    assert distance["total_steps"] == 5
    assert distance["remaining_steps"] == 3
    assert distance["progress"] == 0.4
