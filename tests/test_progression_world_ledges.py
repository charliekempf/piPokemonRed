import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_progression_world import build_ledge_edges, parse_ledge_tiles
from progression_pathfinding import Tile
from progression_world import load_world


def test_parse_ledge_tiles_reads_overworld_pairs() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "data" / "tilesets").mkdir(parents=True)
        (root / "data" / "tilesets" / "ledge_tiles.asm").write_text(
            "\n".join(
                [
                    "LedgeTiles:",
                    "\tdb SPRITE_FACING_DOWN,  $2C, $37, PAD_DOWN",
                    "\tdb SPRITE_FACING_RIGHT, $2C, $0D, PAD_RIGHT",
                    "\tdb -1 ; end",
                ]
            ),
            encoding="utf-8",
        )

        assert parse_ledge_tiles(root) == [
            {"direction": "down", "standing_tile": 0x2C, "ledge_tile": 0x37},
            {"direction": "right", "standing_tile": 0x2C, "ledge_tile": 0x0D},
        ]


def test_build_ledge_edges_blocks_normal_edge_and_adds_directed_hop() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "maps").mkdir()
        (root / "gfx").mkdir()
        (root / "maps" / "Route1.blk").write_bytes(bytes([0]))
        block = bytearray(16)
        block[0] = 0x2C
        block[1] = 0x2C
        block[4] = 0x2C
        block[5] = 0x2C
        block[2] = 0x0D
        block[3] = 0x0D
        block[6] = 0x0D
        block[7] = 0x0D
        (root / "gfx" / "overworld.bst").write_bytes(bytes(block))

        ledges = build_ledge_edges(
            root,
            "Route1",
            {"width_blocks": 1, "height_blocks": 1},
            "gfx/overworld.bst",
            [[0, 0], [1, 0]],
            0x0C,
            [{"direction": "right", "standing_tile": 0x2C, "ledge_tile": 0x0D}],
        )

        assert ledges["blocked_edges"] == [
            {"source": [12, 0, 0], "destination": [12, 1, 0]},
            {"source": [12, 1, 0], "destination": [12, 0, 0]},
        ]
        assert ledges["ledges"] == [
            {"source": [12, 0, 0], "destination": [12, 1, 0]},
        ]


def test_load_world_hydrates_ledge_edges() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "progression_world.json"
        database_path.write_text(
            json.dumps(
                {
                    "maps": {
                        "12": {
                            "width": 3,
                            "height": 1,
                            "walkable": [[0, 0], [1, 0], [2, 0]],
                            "blocked_edges": [
                                {"source": [12, 0, 0], "destination": [12, 1, 0]},
                                {"source": [12, 1, 0], "destination": [12, 0, 0]},
                            ],
                            "ledges": [
                                {"source": [12, 0, 0], "destination": [12, 1, 0]},
                            ],
                        }
                    },
                    "warps": [],
                }
            ),
            encoding="utf-8",
        )

        world = load_world(str(database_path))

        assert world is not None
        assert (Tile(12, 1, 0), 1) in list(world.neighbors(Tile(12, 0, 0)))
        assert (Tile(12, 0, 0), 1) not in list(world.neighbors(Tile(12, 1, 0)))
