# Progression Gate Model

This is the planning pass for a location progress bar in the reviewer. The goal is to identify the next action that can unlock meaningful game progress, then show how far the player is from that objective.

Sources used for the first gate tally:

- Bulbapedia Red/Blue walkthrough outline and route order.
- Bulbapedia walkthrough details for Oak's Parcel, Silph Scope, Poke Flute, Safari Zone rewards, Koga/Surf, and Secret Key.
- The local `MAP_NAMES`, item names, badge names, and map contexts in `scripts/review_pi_checkpoint.py`.

## Gate Types

Use these categories in code so the UI can explain why a target matters:

- `story_event`: required story flag or NPC script.
- `gym_battle`: gym leader defeat and badge acquisition.
- `rocket_event`: Team Rocket boss/area progression.
- `key_item`: required inventory pickup.
- `hm_unlock`: HM acquisition or badge permission needed for field use.
- `roadblock`: overworld blocker, locked door, or Snorlax-style obstacle.
- `league_gate`: badge/HM checks on the route to the Elite Four.

## Progression Gates

The table is intentionally gameplay-oriented rather than speedrun-route-specific. Some gates are technically reorderable, but each is a meaningful action that unlocks access, HM use, a mandatory badge, or a required dungeon path.

| Order | Gate | Type | Objective location | Completion signal | Unlock / why it matters |
|---:|---|---|---|---|---|
| 1 | Choose starter | `story_event` | Pallet Town, Oak's Lab | Starter species exists in party | Enables leaving Pallet and normal battles. |
| 2 | Rival battle 1 | `story_event` | Pallet Town, Oak's Lab | Intro rival battle resolved | Clears the lab opening sequence. |
| 3 | Receive Oak's Parcel | `key_item` | Viridian City, Poke Mart | Bag contains Oak's Parcel | Required delivery before Viridian north path opens. |
| 4 | Deliver Oak's Parcel / receive Pokedex | `story_event` | Pallet Town, Oak's Lab | Pokedex enabled, Parcel removed | Old man roadblock clears; Route 2/Viridian Forest progression opens. |
| 5 | Brock / Boulder Badge | `gym_battle` | Pewter City Gym | Boulder Badge bit set | Clears Pewter progression to Route 3; first required badge. |
| 6 | Mt. Moon fossil/Super Nerd | `story_event` | Mt. Moon B2F | Fossil choice made, exit path open | Clears Mt. Moon to Route 4 / Cerulean. |
| 7 | Misty / Cascade Badge | `gym_battle` | Cerulean City Gym | Cascade Badge bit set | Required for Cut field use in Gen 1; second required badge. |
| 8 | Nugget Bridge rival | `story_event` | Route 24 | Rival battle resolved | Opens practical path to Bill. |
| 9 | Bill / S.S. Ticket | `key_item` | Route 25, Sea Cottage | Bag contains S.S. Ticket | Required to board S.S. Anne. |
| 10 | S.S. Anne rival | `story_event` | S.S. Anne 2F | Rival battle resolved | Blocks route to captain. |
| 11 | Captain / HM01 Cut | `hm_unlock` | S.S. Anne captain's room | Bag contains HM01 | Required to enter Vermilion Gym and Route 9 path. |
| 12 | Lt. Surge / Thunder Badge | `gym_battle` | Vermilion City Gym | Thunder Badge bit set | Required badge; enables Fly field use. |
| 13 | Route 9 Cut tree | `roadblock` | Route 9 west entrance | Can pass Cut tree | Opens Rock Tunnel route from Cerulean side. |
| 14 | Rock Tunnel traversal | `story_event` | Rock Tunnel | Reaches Lavender / Route 10 south | Connects early Kanto to Lavender/Celadon path. |
| 15 | Celadon drink for Saffron guards | `key_item` | Celadon Dept. Store vending machines | Guard roadblock satisfied | Opens Saffron gates. |
| 16 | Erika / Rainbow Badge | `gym_battle` | Celadon City Gym | Rainbow Badge bit set | Required badge; enables Strength field use in Gen 1. |
| 17 | Rocket Hideout Giovanni / Silph Scope | `rocket_event` | Celadon Game Corner, Rocket Hideout B4F | Silph Scope obtained | Reveals Pokemon Tower ghost. |
| 18 | Pokemon Tower Marowak | `story_event` | Pokemon Tower 6F | Marowak ghost defeated | Opens upper tower rescue path. |
| 19 | Mr. Fuji / Poke Flute | `key_item` | Lavender Town, Mr. Fuji's house | Bag contains Poke Flute | Wakes Snorlax roadblocks to Fuchsia routes. |
| 20 | Silph Co. card key | `key_item` | Saffron City, Silph Co. 5F | Bag contains Card Key | Opens locked Silph rooms and Giovanni path. |
| 21 | Silph Co. rival | `story_event` | Silph Co. 7F | Rival battle resolved | Blocks Giovanni route. |
| 22 | Silph Co. Giovanni | `rocket_event` | Silph Co. 11F | Team Rocket cleared / Master Ball obtainable | Unlocks Saffron story state and final Rocket takeover. |
| 23 | Sabrina / Marsh Badge | `gym_battle` | Saffron City Gym | Marsh Badge bit set | Required badge. |
| 24 | Snorlax roadblock | `roadblock` | Route 12 or Route 16 | Snorlax battle resolved | Opens routes toward Fuchsia/Cycling Road. |
| 25 | Koga / Soul Badge | `gym_battle` | Fuchsia City Gym | Soul Badge bit set | Required for Surf field use in Gen 1. |
| 26 | Safari Zone Gold Teeth | `key_item` | Safari Zone Area 3 | Bag contains Gold Teeth | Required to obtain Strength. |
| 27 | Safari Zone HM03 Surf | `hm_unlock` | Safari Zone Secret House | Bag contains HM03 | Required to reach Cinnabar and later Victory Road. |
| 28 | Warden / HM04 Strength | `hm_unlock` | Fuchsia City, Warden's house | Bag contains HM04 | Required for Victory Road boulders. |
| 29 | Cinnabar Island access | `roadblock` | Surf route from Pallet/Fuchsia | Current map can reach Cinnabar | Requires Surf and Soul Badge. |
| 30 | Pokemon Mansion Secret Key | `key_item` | Cinnabar Island, Pokemon Mansion B1F | Bag contains Secret Key | Opens Cinnabar Gym. |
| 31 | Blaine / Volcano Badge | `gym_battle` | Cinnabar Island Gym | Volcano Badge bit set | Required badge. |
| 32 | Viridian Gym unlock | `roadblock` | Viridian City Gym | Seven non-Earth badges obtained | Opens final gym. |
| 33 | Giovanni / Earth Badge | `gym_battle` | Viridian City Gym | Earth Badge bit set | Eighth badge; unlocks Pokemon League route checks. |
| 34 | Route 23 badge gates | `league_gate` | Route 23 | Passes eight badge guards | Opens Victory Road. |
| 35 | Victory Road Strength boulders | `league_gate` | Victory Road | Reaches Indigo Plateau exit | Requires Strength/Rainbow Badge and all badge gates. |
| 36 | Elite Four + Champion | `story_event` | Indigo Plateau | Hall of Fame state | Game completion. |

## Runtime Gate Selection

The first implementation should use a linear ordered list with predicates. For each gate, define:

- `id`
- `label`
- `type`
- `objective`
- `is_complete(state)`
- `is_available(state)`
- `requires`
- `notes`

At runtime:

1. Read current state from WRAM: map ID, player tile, bag, badges, battle state, party, event flags once mapped.
2. Iterate gates in order.
3. Skip gates where `is_complete(state)` is true.
4. Prefer the first incomplete gate whose prerequisites are met.
5. If no exact flag predicate exists yet, fall back to a coarse signal, such as item possession, badge bit, map access, or whether an NPC/roadblock has disappeared.

This keeps the UI useful while we gradually replace coarse checks with exact event flags.

## Distance Model

The progress bar should not be based on raw map ID order. It should be based on shortest walkable player steps through the current accessible world.

The initial pathfinding core lives in `scripts/progression_pathfinding.py`. It uses Dijkstra shortest path over map tiles and can already sum distance across multiple maps through warp edges.

Represent the world as a graph:

- Node: `(map_id, x, y)`.
- Cost: one tile step.
- Edge types:
  - cardinal walking edges on passable tiles;
  - blocked directed edges for walls, ledge lips, and other one-way tile boundaries;
  - directed ledge edges that permit jumping only in the legal direction;
  - warp edges for doors, caves, stairs, ladders, and elevators;
  - scripted transition edges such as S.S. Anne boarding, Safari Zone entry, and elevator floor selection;
  - conditional edges for Cut, Surf, Strength, Snorlax, locked doors, card-key doors, guards, badge gates, and gym locks.

For each gate objective, define one or more target interaction tiles:

- NPC objective: tile adjacent to the NPC, facing the NPC.
- Item ball/key item: tile containing or adjacent to the item pickup.
- Gym leader: tile adjacent to leader, facing leader.
- Door/roadblock: tile at the blocked edge or first tile beyond it, depending on the UI copy.

Then compute:

```text
total_steps = shortest_path_steps(respawn_point, objective_tiles, world_state)
remaining_steps = shortest_path_steps(current_position, objective_tiles, world_state)
progress = clamp(1 - (remaining_steps / max(total_steps, 1)), 0, 1)
```

Display:

- gate label, e.g. `Next: Deliver Oak's Parcel`;
- current target location, e.g. `Pallet Town | Oak's Lab`;
- `remaining_steps`;
- progress bar from current respawn point to objective.

If the current position is off the shortest route, the formula still works as "how close are we now compared with starting from respawn." If `remaining_steps > total_steps`, clamp progress to `0%` and optionally show `Off route`.

## Current Respawn Point

For this project, "respawn point" means the location the game sends the player to after blackout. That is usually the last Pokemon Center or home/lab heal point.

Implementation options, in order of preference:

1. Exact WRAM variable: identify the Gen 1 saved heal/blackout destination variable from pokered symbols and read it directly.
2. Event tracking fallback: when the reviewer sees a Pokemon Center heal script complete, update an in-session `respawn_point` to that center's doorway/lobby tile.
3. Simulation fallback: fork the PyBoy state, force a controlled blackout, let the blackout script finish, then read the resulting map/x/y. This is slower but robust for unknown flags and can be cached per checkpoint.

The first version can use option 3 for checkpoints and cache:

```text
results/<run>/progression_cache/<checkpoint_digits>.json
```

Cache payload:

```json
{
  "checkpoint_digits": 123000000,
  "map_id": 0,
  "player": {"x": 10, "y": 7},
  "respawn": {"map_id": 2, "x": 4, "y": 6},
  "next_gate": "deliver_oaks_parcel",
  "remaining_steps": 142,
  "total_steps_from_respawn": 188
}
```

## Map Data Strategy

We should not hand-code all passable tiles in Python. Use one of these sources:

1. Preferred: add a local data extractor for the `pret/pokered` disassembly map headers, blocksets, warps, signs, objects, and collision permissions.
2. Acceptable first pass: maintain a small handcrafted graph for early-game Kanto/Pallet/Viridian/Pewter while proving the UI.
3. Fallback: dynamically explore reachable tiles in a PyBoy fork by issuing movement inputs and recording successful coordinate changes. This is slow but useful for validating static graph edges.

The static graph is the right long-term path because conditional gates need exact world logic, but the dynamic explorer can verify that our computed route is actually walkable in the current ROM state.

## First Implementation Slice

For the first UI slice, implement only:

1. Gate predicates for:
   - starter chosen;
   - Oak's Parcel obtained;
   - Oak's Parcel delivered / Pokedex;
   - Boulder Badge;
   - Cascade Badge;
   - Silph Scope;
   - Poke Flute;
   - Soul Badge;
   - Surf HM;
   - Secret Key;
   - eight badges.
2. Respawn point via cached blackout simulation or last known Pokemon Center if we can find the WRAM variable quickly.
3. Distance graph for Pallet, Route 1, Viridian, Route 2, Viridian Forest, Pewter, and Oak's Lab.

That gives us a useful early-game progress bar without overbuilding the entire Kanto routing engine in one shot.

