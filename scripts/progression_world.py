from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from progression_pathfinding import Ledge, MapGrid, Tile, Warp, WorldGraph, progression_distance, shortest_path


DATABASE_PATH = Path("results") / "progression_world.json"
DISTANCE_CACHE_PATH = Path("results") / "progression_distance_cache.json"

PROGRESSION_GATES: tuple[dict[str, Any], ...] = (
    {"id": "choose_starter", "label": "Choose starter", "targets": [(0x28, 6, 4), (0x28, 7, 4), (0x28, 8, 4)]},
    {"id": "rival_battle_1", "label": "Rival battle 1", "targets": [(0x28, 5, 5)]},
    {"id": "receive_oaks_parcel", "label": "Receive Oak's Parcel", "targets": [(0x2A, 3, 5)]},
    {"id": "deliver_oaks_parcel", "label": "Deliver Oak's Parcel / receive Pokedex", "targets": [(0x28, 5, 3)]},
    {"id": "brock", "label": "Brock / Boulder Badge", "targets": [(0x36, 4, 3)]},
    {"id": "mt_moon_fossil", "label": "Mt. Moon fossil / Super Nerd", "targets": [(0x3D, 13, 7)]},
    {"id": "misty", "label": "Misty / Cascade Badge", "targets": [(0x41, 4, 2)]},
    {"id": "nugget_bridge_rival", "label": "Nugget Bridge rival", "targets": [(0x23, 5, 15)]},
    {"id": "bill_ticket", "label": "Bill / S.S. Ticket", "targets": [(0x58, 4, 4)]},
    {"id": "ss_anne_rival", "label": "S.S. Anne rival", "targets": [(0x60, 14, 5)]},
    {"id": "hm01_cut", "label": "Captain / HM01 Cut", "targets": [(0x65, 4, 2)]},
    {"id": "lt_surge", "label": "Lt. Surge / Thunder Badge", "targets": [(0x5C, 5, 3)]},
    {"id": "route_9_cut_tree", "label": "Route 9 Cut tree", "targets": [(0x14, 7, 5)]},
    {"id": "rock_tunnel", "label": "Rock Tunnel traversal", "targets": [(0x52, 15, 33)]},
    {"id": "saffron_drink", "label": "Celadon drink for Saffron guards", "targets": [(0x7B, 13, 3)]},
    {"id": "erika", "label": "Erika / Rainbow Badge", "targets": [(0x87, 5, 3)]},
    {"id": "silph_scope", "label": "Rocket Hideout Giovanni / Silph Scope", "targets": [(0xC7, 25, 14)]},
    {"id": "tower_marowak", "label": "Pokemon Tower Marowak", "targets": [(0x97, 10, 9)]},
    {"id": "poke_flute", "label": "Mr. Fuji / Poke Flute", "targets": [(0xA1, 3, 4)]},
    {"id": "snorlax", "label": "Snorlax roadblock", "targets": [(0x17, 9, 35), (0x1B, 27, 7)]},
    {"id": "card_key", "label": "Silph Co. card key", "targets": [(0xCD, 3, 3)]},
    {"id": "silph_rival", "label": "Silph Co. rival", "targets": [(0xCF, 5, 5)]},
    {"id": "silph_giovanni", "label": "Silph Co. Giovanni", "targets": [(0xD3, 9, 5)]},
    {"id": "sabrina", "label": "Sabrina / Marsh Badge", "targets": [(0xA3, 9, 5)]},
    {"id": "koga", "label": "Koga / Soul Badge", "targets": [(0xB4, 5, 3)]},
    {"id": "gold_teeth", "label": "Safari Zone Gold Teeth", "targets": [(0xD9, 19, 24)]},
    {"id": "surf", "label": "Safari Zone HM03 Surf", "targets": [(0xDA, 3, 4)]},
    {"id": "strength", "label": "Warden / HM04 Strength", "targets": [(0xB3, 4, 3)]},
    {"id": "cinnabar_access", "label": "Cinnabar Island access", "targets": [(0x08, 5, 6)]},
    {"id": "secret_key", "label": "Pokemon Mansion Secret Key", "targets": [(0xCC, 19, 17)]},
    {"id": "blaine", "label": "Blaine / Volcano Badge", "targets": [(0xC5, 5, 3)]},
    {"id": "viridian_gym_unlock", "label": "Viridian Gym unlock", "targets": [(0x2D, 5, 8)]},
    {"id": "giovanni", "label": "Giovanni / Earth Badge", "targets": [(0x2D, 5, 3)]},
    {"id": "route_23_badge_gates", "label": "Route 23 badge gates", "targets": [(0x22, 5, 60)]},
    {"id": "victory_road", "label": "Victory Road Strength boulders", "targets": [(0x6C, 5, 1)]},
    {"id": "elite_four", "label": "Elite Four + Champion", "targets": [(0x76, 5, 5)]},
)

CHECKPOINT_TILES: tuple[dict[str, Any], ...] = (
    {"id": "pallet_home", "label": "Pallet Town home", "tile": (0x00, 5, 6)},
    {"id": "viridian_pokecenter", "label": "Viridian Pokecenter", "tile": (0x01, 23, 26)},
    {"id": "pewter_pokecenter", "label": "Pewter Pokecenter", "tile": (0x02, 13, 26)},
    {"id": "cerulean_pokecenter", "label": "Cerulean Pokecenter", "tile": (0x03, 19, 18)},
    {"id": "lavender_pokecenter", "label": "Lavender Pokecenter", "tile": (0x04, 3, 6)},
    {"id": "vermilion_pokecenter", "label": "Vermilion Pokecenter", "tile": (0x05, 11, 4)},
    {"id": "celadon_pokecenter", "label": "Celadon Pokecenter", "tile": (0x06, 41, 10)},
    {"id": "fuchsia_pokecenter", "label": "Fuchsia Pokecenter", "tile": (0x07, 19, 28)},
    {"id": "cinnabar_pokecenter", "label": "Cinnabar Pokecenter", "tile": (0x08, 11, 12)},
    {"id": "indigo_plateau_pokecenter", "label": "Indigo Plateau Pokecenter", "tile": (0x09, 9, 6)},
    {"id": "saffron_pokecenter", "label": "Saffron Pokecenter", "tile": (0x0A, 9, 30)},
    {"id": "mt_moon_pokecenter", "label": "Mt. Moon Pokecenter", "tile": (0x0F, 11, 6)},
    {"id": "rock_tunnel_pokecenter", "label": "Rock Tunnel Pokecenter", "tile": (0x15, 11, 20)},
)


def map_display_name(map_id: int) -> str:
    try:
        from review_pi_checkpoint import map_name

        return map_name(map_id)
    except Exception:
        return f"Map ${map_id:02X}"


@lru_cache(maxsize=4)
def load_progression_database(path: str = str(DATABASE_PATH)) -> dict[str, Any] | None:
    database_path = Path(path)
    if not database_path.exists():
        return None
    with database_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=4)
def load_world(path: str = str(DATABASE_PATH)) -> WorldGraph | None:
    database = load_progression_database(path)
    if not database:
        return None

    maps: dict[int | str, MapGrid] = {}
    for raw_id, raw_map in database["maps"].items():
        map_id = int(raw_id)
        width = int(raw_map["width"])
        height = int(raw_map["height"])
        walkable = {tuple(tile) for tile in raw_map.get("walkable", [])}
        blocked = {
            (x, y)
            for y in range(height)
            for x in range(width)
            if (x, y) not in walkable
        }
        blocked_edges = {
            (
                Tile(int(raw_edge["source"][0]), int(raw_edge["source"][1]), int(raw_edge["source"][2])),
                Tile(
                    int(raw_edge["destination"][0]),
                    int(raw_edge["destination"][1]),
                    int(raw_edge["destination"][2]),
                ),
            )
            for raw_edge in raw_map.get("blocked_edges", [])
        }
        ledges = [
            Ledge(
                Tile(int(raw_ledge["source"][0]), int(raw_ledge["source"][1]), int(raw_ledge["source"][2])),
                Tile(
                    int(raw_ledge["destination"][0]),
                    int(raw_ledge["destination"][1]),
                    int(raw_ledge["destination"][2]),
                ),
            )
            for raw_ledge in raw_map.get("ledges", [])
        ]
        maps[map_id] = MapGrid(map_id, width, height, blocked=blocked, blocked_edges=blocked_edges, ledges=ledges)

    warps = [
        Warp(
            Tile(int(raw_warp["source"][0]), int(raw_warp["source"][1]), int(raw_warp["source"][2])),
            Tile(
                int(raw_warp["destination"][0]),
                int(raw_warp["destination"][1]),
                int(raw_warp["destination"][2]),
            ),
        )
        for raw_warp in database.get("warps", [])
    ]
    return WorldGraph(maps, warps)


@lru_cache(maxsize=4)
def load_distance_cache(path: str = str(DISTANCE_CACHE_PATH)) -> dict[str, Any] | None:
    cache_path = Path(path)
    if not cache_path.exists():
        return None
    with cache_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=64)
def cached_distance_index(
    category: str,
    target_id: str,
    path: str = str(DISTANCE_CACHE_PATH),
) -> dict[Tile, int]:
    cache = load_distance_cache(path)
    if not cache:
        return {}
    raw_target = cache.get(category, {}).get(target_id, {})
    distances: dict[Tile, int] = {}
    for raw_map_id, raw_tiles in raw_target.get("distances", {}).items():
        map_id = int(raw_map_id)
        for x, y, steps in raw_tiles:
            distances[Tile(map_id, int(x), int(y))] = int(steps)
    return distances


def cached_progression_distance(
    gate_id: str,
    tile: Tile,
    path: str = str(DISTANCE_CACHE_PATH),
) -> int | None:
    try:
        map_id = int(tile.map_id)
    except (TypeError, ValueError):
        return None
    return cached_distance_index("progression_gates", gate_id, path).get(Tile(map_id, tile.x, tile.y))


def cached_checkpoint_distance(
    checkpoint_id: str,
    tile: Tile,
    path: str = str(DISTANCE_CACHE_PATH),
) -> int | None:
    try:
        map_id = int(tile.map_id)
    except (TypeError, ValueError):
        return None
    return cached_distance_index("checkpoints", checkpoint_id, path).get(Tile(map_id, tile.x, tile.y))


def checkpoint_tile_for_blackout_map(map_id: int) -> dict[str, Any] | None:
    for checkpoint in CHECKPOINT_TILES:
        if int(checkpoint["tile"][0]) == map_id:
            return checkpoint
    return None


def tile_dict(tile: Tile) -> dict[str, int | str]:
    return {"map_id": tile.map_id, "x": tile.x, "y": tile.y}


def nearest_closer_checkpoint(
    gate_id: str,
    current_tile: Tile,
    current_checkpoint_tile: Tile | None,
    distance_cache_path: str = str(DISTANCE_CACHE_PATH),
) -> dict[str, Any] | None:
    if current_checkpoint_tile is None:
        return None
    current_checkpoint_progression = cached_progression_distance(gate_id, current_checkpoint_tile, distance_cache_path)
    if current_checkpoint_progression is None:
        return None

    best: dict[str, Any] | None = None
    for checkpoint in CHECKPOINT_TILES:
        checkpoint_tile = Tile(*checkpoint["tile"])
        checkpoint_progression = cached_progression_distance(gate_id, checkpoint_tile, distance_cache_path)
        if checkpoint_progression is None or checkpoint_progression >= current_checkpoint_progression:
            continue
        distance_to_checkpoint = cached_checkpoint_distance(str(checkpoint["id"]), current_tile, distance_cache_path)
        if distance_to_checkpoint is None:
            continue
        candidate = {
            "id": checkpoint["id"],
            "label": checkpoint["label"],
            "tile": tile_dict(checkpoint_tile),
            "steps": distance_to_checkpoint,
            "checkpoint_progression_steps": checkpoint_progression,
            "current_checkpoint_progression_steps": current_checkpoint_progression,
        }
        if best is None or distance_to_checkpoint < int(best["steps"]):
            best = candidate
    return best


def active_progression_gate(pyboy: object) -> dict[str, Any]:
    from review_pi_checkpoint import (
        BAG_ITEMS_ADDR,
        OBTAINED_BADGES_ADDR,
        PARTY_COUNT_ADDR,
        POKEDEX_OWNED_ADDR,
        bag_quantities,
    )

    memory = pyboy.memory
    party_count = int(memory[PARTY_COUNT_ADDR])
    bag_items = bag_quantities(pyboy)
    badges = int(memory[OBTAINED_BADGES_ADDR])
    pokedex_enabled = int(memory[POKEDEX_OWNED_ADDR]) != 0

    if party_count <= 0:
        return PROGRESSION_GATES[0]
    if 0x46 not in bag_items and not pokedex_enabled:
        return PROGRESSION_GATES[2]
    if not pokedex_enabled:
        return PROGRESSION_GATES[3]

    badge_gate_ids = [
        "brock",
        "misty",
        "lt_surge",
        "erika",
        "koga",
        "sabrina",
        "blaine",
        "giovanni",
    ]
    badge_bits = {
        "brock": 0,
        "misty": 1,
        "lt_surge": 2,
        "erika": 3,
        "koga": 4,
        "sabrina": 5,
        "blaine": 6,
        "giovanni": 7,
    }
    gates_by_id = {gate["id"]: gate for gate in PROGRESSION_GATES}
    for gate_id in badge_gate_ids:
        if not badges & (1 << badge_bits[gate_id]):
            return gates_by_id[gate_id]
    return PROGRESSION_GATES[-1]


def progression_state_for_tile(
    pyboy: object,
    current_tile: Tile,
    respawn_tile: Tile | None = None,
) -> dict[str, object]:
    gate = active_progression_gate(pyboy)
    return progression_state_for_gate(gate, current_tile, respawn_tile)


def progression_state_for_gate(
    gate: dict[str, Any],
    current_tile: Tile,
    respawn_tile: Tile | None = None,
    world_path: str = str(DATABASE_PATH),
    distance_cache_path: str = str(DISTANCE_CACHE_PATH),
) -> dict[str, object]:
    target_tiles = [Tile(map_id, x, y) for map_id, x, y in gate["targets"]]
    target_map_id = int(gate["targets"][0][0])

    base = {
        "label": gate["label"],
        "objective_location": map_display_name(target_map_id),
        "current_tile": {"map_id": current_tile.map_id, "x": current_tile.x, "y": current_tile.y},
        "remaining_steps": None,
        "total_steps_from_respawn": None,
        "graph_max_steps": None,
        "reachable": False,
    }

    cached_remaining = cached_progression_distance(str(gate["id"]), current_tile, distance_cache_path)
    if cached_remaining is not None:
        respawn_tile = respawn_tile or current_tile
        cached_total = cached_progression_distance(str(gate["id"]), respawn_tile, distance_cache_path)
        total_steps = cached_total if cached_total is not None else cached_remaining
        closer_checkpoint = nearest_closer_checkpoint(str(gate["id"]), current_tile, respawn_tile, distance_cache_path)
        return {
            **base,
            "remaining_steps": cached_remaining,
            "total_steps_from_respawn": total_steps,
            "graph_max_steps": max(1, int(total_steps or cached_remaining) * 2),
            "reachable": True,
            "distance_source": "cache",
            "current_checkpoint_tile": tile_dict(respawn_tile),
            "nearest_closer_checkpoint": closer_checkpoint,
        }

    world = load_world(world_path)
    if world is None:
        return {**base, "label": f"{gate['label']} (database missing)"}

    remaining = shortest_path(world, current_tile, target_tiles)
    if remaining is None:
        return base

    respawn_tile = respawn_tile or current_tile
    total = progression_distance(world, respawn_tile, current_tile, target_tiles)
    total_steps = total["total_steps"] if total["reachable"] else remaining.steps
    return {
        **base,
        "remaining_steps": remaining.steps,
        "total_steps_from_respawn": total_steps,
        "graph_max_steps": max(1, int(total_steps or remaining.steps) * 2),
        "reachable": True,
    }
