# Agent Instructions

## Project Summary

This repo is `piPokemonRed`, an experiment for feeding digits of pi into Pokemon Red as deterministic Game Boy inputs and checking whether the resulting stream can make game progress.

Current core approach:

- Use PyBoy for the main simulator and checkpoint reviewer.
- Use a legally obtained local Pokemon Red ROM in `roms/`; the ROM is ignored and must never be committed.
- Use local pi digit text files in `data/`; these are ignored and must not be committed.
- Current input mapping consumes two decimal digits at a time:
  - `00-53` -> A
  - `54-63` -> Up
  - `64-73` -> Down
  - `74-83` -> Left
  - `84-93` -> Right
  - `94-98` -> B
  - `99` -> Start
- Current verified timing is hold button for 2 frames, then release for 1 frame. One-frame taps were tested and often did not affect Pokemon Red gameplay.
- Current verified run is `pi_1m_hold2_release1`: first 1,000,000 digits, checkpoints/screenshots every 100,000 digits.

Important scripts:

- `scripts/run_pi_pyboy.py` runs the headless deterministic simulation and writes savestates/screenshots/progress.
- `scripts/review_pi_checkpoint.py` opens the single-window graphical reviewer with speed control and digit-based rewind.
- `scripts/open_review.ps1` safely closes older reviewer instances and opens a fresh reviewer.
- `scripts/tally_tas_buttons.py` parses BizHawk `.bk2` TAS files to tally button usage.
- `src/LibretroBench/` is an optional native libretro benchmark harness kept for comparison; PyBoy is the practical path right now.

Typical commands:

```powershell
py scripts\run_pi_pyboy.py --run-name pi_1m_hold2_release1 --digits data\pi_10m_digits.txt --max-digits 1000000 --checkpoint-digits 100000 --hold-frames 2 --release-frames 1
.\scripts\open_review.ps1
```

## Git Workflow

- Make frequent local git commits while working.
- Keep commits small, focused, and easy to review.
- Use clear imperative commit messages, for example `Add pi input mapper`.
- Before committing, run the most relevant quick verification for the change.
- Check `git status --short --ignored` before committing so generated files and local assets do not slip in.
- Do not commit ROMs, saves, downloaded TAS files, generated benchmark results, build outputs, or local tool binaries.
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

- Before opening `scripts/review_pi_checkpoint.py`, close any older running instances of that same reviewer script.
- Only target processes whose command line includes `review_pi_checkpoint.py`; do not stop unrelated Python processes.
