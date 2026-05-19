# Agent Instructions

## Project Summary

This repo is `piPokemonRed`, an experiment for feeding digits of pi into Pokemon Red as deterministic Game Boy inputs and checking whether the resulting stream can make game progress.

Current core approach:

- Use PyBoy for the main simulator and checkpoint reviewer.
- Use a legally obtained local Pokemon Red ROM in `roms/`; the ROM is ignored and must never be committed.
- Use local pi digit text files in `data/`; these are ignored and must not be committed.
- The active public/review run is `pi_10m_two_digit`; older `pi_1m_hold2_release1` and `smoke_hold2_release1` generated runs were removed locally.
- Current input mapping consumes two decimal digits at a time:
  - `00-53` -> A
  - `54-63` -> Up
  - `64-73` -> Down
  - `74-83` -> Left
  - `84-93` -> Right
  - `94-98` -> B
  - `99` -> Start
- Current verified timing is hold button for 2 frames, then release for 1 frame. One-frame taps were tested and often did not affect Pokemon Red gameplay.
- Input timing and digit-to-button ranges are configured in `config/pi_input.json`. The current config is `on_frames: 2`, `off_frames: 1`, `digits_per_input: 2`, with the two-digit mapping below.
- Current verified run is `pi_10m_two_digit`: first 10,000,000 digits, checkpoints/screenshots every 1,000,000 digits.
- Highest digit reached for README/status purposes is 10,000,000 digits consumed in `pi_10m_two_digit`.
- The current web reviewer normally starts from the latest playable checkpoint, which is 9,000,000/10,000,000 for the local 10M run.

Important scripts:

- `scripts/run_pi_pyboy.py` runs the headless deterministic simulation and writes savestates/screenshots/progress.
- `scripts/review_web.py` runs the local web reviewer/control surface with WebGL canvas rendering, speed control, digit-based rewind/fast-forward, backend simulation controls, and an upcoming-input preview.
- `scripts/review_pi_checkpoint.py` is the older Tk-based reviewer kept for reference.
- `scripts/open_review.ps1` safely closes older reviewer instances and opens a fresh web reviewer.
- `scripts/tally_tas_buttons.py` parses BizHawk `.bk2` TAS files to tally button usage.
- `src/LibretroBench/` is an optional native libretro benchmark harness kept for comparison; PyBoy is the practical path right now.

Typical commands:

```powershell
py scripts\run_pi_pyboy.py --run-name pi_10m_two_digit --digits data\pi_10m_digits.txt --checkpoint-digits 1000000
.\scripts\open_review.ps1
```

Current reviewer UI behavior:

- The browser UI is served locally, usually at `http://127.0.0.1:8765/`.
- The screen is a WebGL-backed canvas fed by raw RGBA frames from `scripts/review_web.py`; Canvas 2D is the fallback.
- The status under the emulator is a stat-card grid, not a pipe-separated status line.
- The right-hand `Next` panel shows upcoming pi digit pairs and buttons; if no pairs remain, it shows `Out of digits` / `Download more`.
- The transport controls are `Pause/Resume`, `<<`, a digit-distance dropdown, and `>>`.
- `<<` rewinds by the selected digit count using in-memory savestate snapshots.
- `>>` fast-forwards by the selected digit count by transferring the current state into a separate headless PyBoy backend simulator with sound/rendering disabled, running the real pi-derived input stream there, loading the resulting state back into the reviewer, darkening the emulator frame with a buffering spinner, then pausing at an input boundary.
- The `Headless simulator` panel advances the real run by the selected digit count using the same backend simulator path, then writes a checkpoint, screenshot, and `results/<run>/progress.json` so the headless run can continue from the new state.
- After backend fast-forward, automatic in-memory snapshot capture is disabled for that review session because PyBoy can hang when saving reviewer snapshots after loading the backend-simulated state.
- Checkpoint and rewind frame displays use a one-frame render/restore path so the screen is populated after loading state.

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
- The launcher and web reviewer default to `penultimate` checkpoint selection so review opens one checkpoint behind the newest available checkpoint while the digit limit follows the newest checkpoint.
- The launcher default run is `pi_10m_two_digit`; do not switch it back to removed old runs.
- Before opening a reviewer, close any older running reviewer process.
- Only target processes whose command line includes `review_web.py` or `review_pi_checkpoint.py`; do not stop unrelated Python processes.
