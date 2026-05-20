from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


MAP_CONST_RE = re.compile(r"map_const\s+([A-Z0-9_]+),\s+(\d+),\s+(\d+)\s+;\s+\$(?P<hex>[0-9A-Fa-f]+)")
HEADER_RE = re.compile(r"map_header\s+(\w+),\s+([A-Z0-9_]+),\s+([A-Z0-9_]+),")
CONNECTION_RE = re.compile(r"connection\s+(north|south|east|west),\s+(\w+),\s+([A-Z0-9_]+),\s+(-?\d+)")
WARP_RE = re.compile(r"warp_event\s+(\d+),\s+(\d+),\s+([A-Z0-9_]+|LAST_MAP),\s+(\d+)")
INCBIN_RE = re.compile(r"([A-Za-z0-9]+)_Block::.*?INCBIN\s+\"([^\"]+)\"")
COLL_LABEL_RE = re.compile(r"([A-Za-z0-9]+)_Coll::")
HEX_RE = re.compile(r"\$([0-9A-Fa-f]+)")


def parse_map_constants(root: Path) -> dict[str, dict[str, int]]:
    maps: dict[str, dict[str, int]] = {}
    for line in (root / "constants" / "map_constants.asm").read_text(encoding="utf-8").splitlines():
        match = MAP_CONST_RE.search(line)
        if match:
            name, width, height = match.group(1), int(match.group(2)), int(match.group(3))
            maps[name] = {"id": int(match.group("hex"), 16), "width_blocks": width, "height_blocks": height}
    return maps


def parse_tileset_blocksets(root: Path) -> dict[str, str]:
    text = (root / "gfx" / "tilesets.asm").read_text(encoding="utf-8")
    mapping: dict[str, str] = {}
    pending: list[str] = []
    for line in text.splitlines():
        labels = re.findall(r"([A-Za-z0-9]+)_Block::", line)
        pending.extend(labels)
        include = re.search(r"INCBIN\s+\"([^\"]+)\"", line)
        if include:
            for label in pending:
                mapping[label.upper()] = include.group(1)
            pending = []
    return mapping


def parse_collision_tiles(root: Path) -> dict[str, set[int]]:
    collisions: dict[str, set[int]] = {}
    labels: list[str] = []
    for line in (root / "data" / "tilesets" / "collision_tile_ids.asm").read_text(encoding="utf-8").splitlines():
        found_labels = COLL_LABEL_RE.findall(line)
        if found_labels:
            labels.extend(label.upper() for label in found_labels)
            continue
        if "coll_tiles" not in line or not labels:
            continue
        values = {int(value, 16) for value in HEX_RE.findall(line)}
        for label in labels:
            collisions[label] = values
        labels = []
    return collisions


def parse_headers(root: Path) -> dict[str, dict[str, Any]]:
    headers: dict[str, dict[str, Any]] = {}
    for path in (root / "data" / "maps" / "headers").glob("*.asm"):
        text = path.read_text(encoding="utf-8")
        header = HEADER_RE.search(text)
        if not header:
            continue
        symbol, const_name, tileset = header.group(1), header.group(2), header.group(3)
        connections = [
            {
                "direction": match.group(1),
                "target_symbol": match.group(2),
                "target": match.group(3),
                "offset": int(match.group(4)),
            }
            for match in CONNECTION_RE.finditer(text)
        ]
        headers[const_name] = {"symbol": symbol, "tileset": tileset, "connections": connections}
    return headers


def parse_objects(root: Path) -> dict[str, list[dict[str, Any]]]:
    objects: dict[str, list[dict[str, Any]]] = {}
    for path in (root / "data" / "maps" / "objects").glob("*.asm"):
        warps = [
            {"x": int(match.group(1)), "y": int(match.group(2)), "target": match.group(3), "target_warp": int(match.group(4))}
            for match in WARP_RE.finditer(path.read_text(encoding="utf-8"))
        ]
        if warps:
            objects[path.stem] = warps
    return objects


def block_tile(blockset: bytes, block_id: int, x: int, y: int) -> int:
    index = (block_id * 16) + (y * 4) + x
    if index >= len(blockset):
        return -1
    return blockset[index]


def build_walkable_tiles(root: Path, map_symbol: str, dimensions: dict[str, int], blockset_path: str, collision: set[int]) -> list[list[int]]:
    width_blocks = dimensions["width_blocks"]
    height_blocks = dimensions["height_blocks"]
    map_path = root / "maps" / f"{map_symbol}.blk"
    if not map_path.exists() or width_blocks <= 0 or height_blocks <= 0:
        return []
    blocks = map_path.read_bytes()
    blockset = (root / blockset_path).read_bytes()
    width_tiles = width_blocks * 2
    height_tiles = height_blocks * 2
    walkable: list[list[int]] = []
    for y in range(height_tiles):
        for x in range(width_tiles):
            block_x = x // 2
            block_y = y // 2
            block_index = block_y * width_blocks + block_x
            if block_index >= len(blocks):
                continue
            block_id = blocks[block_index]
            subtile_x = (x % 2) * 2
            subtile_y = (y % 2) * 2
            tile_ids = {
                block_tile(blockset, block_id, subtile_x + dx, subtile_y + dy)
                for dy in range(2)
                for dx in range(2)
            }
            if tile_ids & collision:
                walkable.append([x, y])
    return walkable


def warp_destinations(map_ids: dict[str, int], headers: dict[str, dict[str, Any]], objects: dict[str, list[dict[str, Any]]]) -> list[dict[str, list[int]]]:
    warps: list[dict[str, list[int]]] = []
    for const_name, header in headers.items():
        source_id = map_ids.get(const_name)
        source_symbol = header["symbol"]
        if source_id is None:
            continue
        source_warps = objects.get(source_symbol, [])
        for index, warp in enumerate(source_warps, start=1):
            if warp["target"] == "LAST_MAP":
                continue
            target_id = map_ids.get(warp["target"])
            target_symbol = headers.get(warp["target"], {}).get("symbol")
            target_warps = objects.get(target_symbol or "", [])
            if target_id is None or not (1 <= warp["target_warp"] <= len(target_warps)):
                continue
            target = target_warps[warp["target_warp"] - 1]
            edge = {"source": [source_id, warp["x"], warp["y"]], "destination": [target_id, target["x"], target["y"]]}
            reverse = {"source": edge["destination"], "destination": edge["source"]}
            warps.append(edge)
            warps.append(reverse)
    return warps


def connection_warps(map_ids: dict[str, int], constants: dict[str, dict[str, int]], headers: dict[str, dict[str, Any]]) -> list[dict[str, list[int]]]:
    warps: list[dict[str, list[int]]] = []
    for const_name, header in headers.items():
        source_id = map_ids.get(const_name)
        source_dims = constants.get(const_name)
        if source_id is None or source_dims is None:
            continue
        width = source_dims["width_blocks"] * 2
        height = source_dims["height_blocks"] * 2
        for connection in header["connections"]:
            target_name = connection["target"]
            target_id = map_ids.get(target_name)
            target_dims = constants.get(target_name)
            if target_id is None or target_dims is None:
                continue
            target_width = target_dims["width_blocks"] * 2
            target_height = target_dims["height_blocks"] * 2
            offset = connection["offset"] * 2
            if connection["direction"] in {"north", "south"}:
                for x in range(width):
                    tx = x - offset
                    if 0 <= tx < target_width:
                        sy = 0 if connection["direction"] == "north" else height - 1
                        ty = target_height - 1 if connection["direction"] == "north" else 0
                        warps.append({"source": [source_id, x, sy], "destination": [target_id, tx, ty]})
            else:
                for y in range(height):
                    ty = y - offset
                    if 0 <= ty < target_height:
                        sx = 0 if connection["direction"] == "west" else width - 1
                        tx = target_width - 1 if connection["direction"] == "west" else 0
                        warps.append({"source": [source_id, sx, y], "destination": [target_id, tx, ty]})
    return warps


def build_database(root: Path) -> dict[str, Any]:
    constants = parse_map_constants(root)
    headers = parse_headers(root)
    blocksets = parse_tileset_blocksets(root)
    collisions = parse_collision_tiles(root)
    objects = parse_objects(root)
    map_ids = {name: dimensions["id"] for name, dimensions in constants.items()}

    maps: dict[str, dict[str, Any]] = {}
    for const_name, dimensions in constants.items():
        header = headers.get(const_name)
        if not header:
            continue
        tileset = header["tileset"]
        blockset_path = blocksets.get(tileset)
        collision = collisions.get(tileset, set())
        if not blockset_path or not collision:
            continue
        width = dimensions["width_blocks"] * 2
        height = dimensions["height_blocks"] * 2
        walkable = build_walkable_tiles(root, header["symbol"], dimensions, blockset_path, collision)
        maps[str(dimensions["id"])] = {
            "name": const_name,
            "width": width,
            "height": height,
            "tileset": tileset,
            "walkable": walkable,
        }

    warps = warp_destinations(map_ids, headers, objects) + connection_warps(map_ids, constants, headers)
    return {"source": "pret/pokered", "maps": maps, "warps": warps}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local progression pathfinding database from pret/pokered.")
    parser.add_argument("--pokered", type=Path, default=Path("tools") / "pokered")
    parser.add_argument("--output", type=Path, default=Path("results") / "progression_world.json")
    args = parser.parse_args()

    database = build_database(args.pokered)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(database, handle, separators=(",", ":"))
    print(f"Wrote {len(database['maps'])} maps and {len(database['warps'])} warps to {args.output}")


if __name__ == "__main__":
    main()
