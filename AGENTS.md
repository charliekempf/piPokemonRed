# Agent Instructions

## Project Summary

This repo is `piPokemonRed`, an experiment for feeding digits of pi into Pokemon Red as deterministic Game Boy inputs and checking whether the resulting stream can make game progress.

Current core approach:

- Use PyBoy for the main simulator and checkpoint reviewer.
- Use a legally obtained local Pokemon Red ROM in `roms/`; the ROM is ignored and must never be committed.
- Use local pi digit text files in `data/`; these are ignored and must not be committed.
- The active public/review run is `statistical_walk`; older exploratory config variants have been removed from tracked config.
- Current input mapping consumes two decimal digits at a time:
  - `00-53` -> A
  - `54-63` -> Up
  - `64-73` -> Down
  - `74-83` -> Left
  - `84-93` -> Right
  - `94-98` -> B
  - `99` -> Start
- Current verified timing is hold button for 2 frames, then release for 1 frame. One-frame taps were tested and often did not affect Pokemon Red gameplay.
- Input timing, digit-to-button ranges, config display name, and Pokemon game metadata are configured in `config/statistical_walk.json`. The default config is named `Statistical Walk` and targets `Pokemon Red` version `1.0`, region `USA/Europe`.
- Current config values are `on_frames: 2`, `off_frames: 1`, `digits_per_input: 2`, with the two-digit mapping below.
- Runs are config-scoped. `scripts/run_pi_pyboy.py`, `scripts/review_web.py`, and `scripts/review_pi_checkpoint.py` write a canonical `input_config.json` into the run's checkpoint folder. Folder names are derived from the config display name, for example `Statistical Walk` uses `statistical_walk`, so new folders and exported filenames stick to the config name. If a slug already exists with an incompatible config, the scripts use the config stem plus hash as a fallback.
- Current tracked configs are `Statistical Walk` (`config/statistical_walk.json`), `Super Walk` (`config/super_walk.json`), and `Super Stride` (`config/super_stride.json`). Do not re-add deleted exploratory variants unless Charlie asks.
- Current verified run is `statistical_walk`, using `data/pi_1b_digits.txt`, with checkpoints/screenshots every 1,000,000 digits.
- Highest digit reached for README/status purposes is 196,000,000 digits consumed in `statistical_walk`.
- The current web reviewer normally starts from the penultimate playable checkpoint, so it opens one checkpoint behind the newest available state while the digit limit follows the newest checkpoint.

Important scripts:

- `scripts/run_pi_pyboy.py` runs the headless deterministic simulation and writes savestates/screenshots/progress.
- `scripts/review_web.py` runs the local web reviewer/control surface with WebGL canvas rendering, speed control, digit-based rewind/fast-forward, backend simulation controls, and an upcoming-input preview.
- `scripts/review_pi_checkpoint.py` is the older Tk-based reviewer kept for reference.
- `scripts/open_review.ps1` safely closes older reviewer instances and opens a fresh web reviewer.
- `scripts/tally_tas_buttons.py` parses BizHawk `.bk2` TAS files to tally button usage.
- `scripts/build_progression_world.py` builds the local progression pathfinding database from a local `pret/pokered` checkout in `tools/pokered` and writes `results/progression_world.json`.
- `scripts/progression_world.py` loads that ignored local database, selects the active required progression point, and feeds step-distance data to the reviewer graph.
- `scripts/precompute_progression_distances.py` brute-forces ledge-aware reverse distances from every valid tile to each progression gate and each blackout checkpoint tile, writing the ignored cache `results/progression_distance_cache.json`. The reviewer uses this cache for progression-distance lookups and falls back to live pathfinding only if the cache is missing or does not contain the requested tile.
- `src/LibretroBench/` is an optional native libretro benchmark harness kept for comparison; PyBoy is the practical path right now.

Typical commands:

```powershell
py scripts\run_pi_pyboy.py --config config\statistical_walk.json --digits data\pi_1b_digits.txt --checkpoint-digits 1000000 --max-digits 50000000
py scripts\build_progression_world.py
.\scripts\open_review.ps1
```

Current reviewer UI behavior:

- The browser UI is served locally, usually at `http://127.0.0.1:8765/`.
- The screen is a WebGL-backed canvas fed by raw RGBA frames from `scripts/review_web.py`; Canvas 2D is the fallback.
- The status under the emulator is a stat-card grid, not a pipe-separated status line.
- The right-hand `Inputs` panel shows the last three inputs greyed out, the current input highlighted, and upcoming pi digit pairs/buttons. If no pairs remain but local pi digits are exhausted, it shows `Out of digits` / `Download more`.
- The main controls are a square Play/Pause button, a square mute/unmute audio button, a speed box, a Jump strip, and an Event Finder strip pinned to the bottom of the emulator pane.
- The speed slider ranges from `0.1x` through `1000x` to `Unlimited`, and the UI shows requested speed, actual measured playback speed, and digit rate.
- The Jump strip has `Jump`, `<<`, a digit-distance dropdown, `>>`, an arbitrary digit input, and a `Jump` button. The text labels are styled to match adjacent dropdown text for continuity.
- `<<` rewinds by the selected digit count using in-memory savestate snapshots.
- `>>` fast-forwards by the selected digit count by transferring the current state into a separate headless PyBoy backend simulator with sound/rendering disabled, running the real pi-derived input stream there, loading the resulting state back into the reviewer, darkening the emulator frame with a buffering spinner/progress bar, then pausing at an input boundary.
- Arbitrary jump uses the nearest checkpoint at or before the target when possible, then simulates the remaining gap.
- Event Finder is a matching strip below Jump with `Warp to next`, an alphabetized dropdown (`Battle`, `Blackout`, `Evolution`, `Item pickup`, `Level up`, `Location change`, `Trainer battle`, `Wild Pokemon battle`), `Warp`, `Timeout`, and a digit-limit dropdown.
- Clicking `Warp` sets reviewer playback to `1x` before searching.
- The `Headless simulator` panel in the checkpoint pane advances the real run to an absolute `Simulate up to` target with a configurable `Checkpoint every` interval, then writes checkpoints, screenshots, and `results/<run>/progress.json` so the headless run can continue from the new state.
- Headless charting simulation must be a separate PyBoy instance/process from the reviewer jump/seek backend. Killing the headless simulator means only processes whose command line includes `run_pi_pyboy.py`; do not kill the reviewer unless asked.
- The headless simulator UI reports charting status, progress, speed in digits/s, and ETA, and should remember a running chart operation instead of claiming `Ready`.
- After backend fast-forward, automatic in-memory snapshot capture is disabled for that review session because PyBoy can hang when saving reviewer snapshots after loading the backend-simulated state.
- Checkpoint and rewind frame displays use a one-frame render/restore path so the screen is populated after loading state.
- The Player panel combines money, Pokedex seen/caught, actual elapsed emulator time computed from frames (not the capped in-game 255-hour clock), elapsed days in brackets, bag contents, and badges.
- The Party panel shows Pokemon names, levels, HP bars with in-game health colors, expandable moves, and PP shown as current/max.
- The Config panel lives below the timeline and shows game/version/region, digits per input, button ranges, and a pie chart of the mapping spread.
- The timeline shows checkpoint-charted progress in blue and lets users click checkpointed regions to jump to the nearest checkpoint.
- The Progression Distance graph lives below the timeline. It uses `results/progression_world.json`, which is generated locally and ignored because it derives from Pokemon map data. If the graph says the database is missing, run `py scripts\build_progression_world.py` after cloning/updating `tools/pokered`.
- Progression distance is computed by a detached background worker in `scripts/review_web.py`; do not move Dijkstra/pathfinding back into `ReviewSession.info()` or `/api/state`, because that can slow emulator playback while the UI polls.
- The progression panel also shows the nearest closer blackout checkpoint: the closest home/Pokemon Center return tile whose cached objective distance is lower than the current `wLastBlackoutMap` checkpoint tile.

## Git Workflow

- Make frequent local git commits while working.
- Keep commits small, focused, and easy to review.
- Use clear imperative commit messages, for example `Add pi input mapper`.
- Before committing, run the most relevant quick verification for the change.
- Check `git status --short --ignored` before committing so generated files and local assets do not slip in.
- Do not commit ROMs, saves, downloaded TAS files, generated benchmark results, build outputs, or local tool binaries.
- Do not commit `data/`, `saves/`, `results/`, `roms/`, `tas/`, or `tools/` contents except tracked `.gitkeep` placeholders and explicitly approved docs assets.
- Prefer committing reusable source, scripts, documentation, and tracked placeholders for ignored workspace folders.
- Never rewrite or discard user changes unless explicitly asked.

## Workspace Organization

- Keep ROM files in `roms/`.
- Keep emulator RAM/save files in `saves/`.
- Keep downloaded input data in `data/`.
- Keep downloaded TAS/movie files in `tas/`.
- Keep generated benchmark outputs in `results/`.
- Keep reusable source code in `src/`.
- Keep utility scripts in `scripts/`.
- Keep downloaded external tools and emulator cores in `tools/`.

## Review Software

- Prefer the web reviewer (`scripts/review_web.py`) for UI work.
- Do not update `docs/review-player.png` or other README screenshots unless Charlie explicitly asks for a screenshot update.
- The launcher uses the full local pi digit file by default; pass `-MaxDigits <n>` only when a capped review is wanted.
- `scripts/open_review.ps1` should launch the local reviewer server for the Codex in-app browser by default. Do not open the system web browser unless Charlie explicitly asks; use `-OpenExternalBrowser` only for that opt-in case.
- After launching the reviewer, open or refresh `http://127.0.0.1:8765/` in the Codex in-app browser when visual verification is needed.
- The launcher and web reviewer default to `penultimate` checkpoint selection so review opens one checkpoint behind the newest available checkpoint while the digit limit follows the newest checkpoint.
- The reviewer default speed is `10x`; pass `-Speed 1` or `--speed 1` when audio fidelity matters.
- The launcher default run should be `statistical_walk`; do not switch it back to removed old runs or deleted exploratory config variants.
- Before opening a reviewer, close any older running reviewer process.
- Only target processes whose command line includes `review_web.py` or `review_pi_checkpoint.py`; do not stop unrelated Python processes.
