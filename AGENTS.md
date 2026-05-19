# Agent Instructions

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
