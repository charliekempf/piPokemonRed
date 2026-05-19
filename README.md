# piPokemon

Experiments for mapping digits of pi to Game Boy inputs and testing whether the resulting input stream can progress through Pokemon Red.

## What This Is

`piPokemon` is a local research toy for deterministic Pokemon Red input experiments. It maps digits of pi into Game Boy button presses, runs the game through PyBoy, saves periodic checkpoints, and provides a review UI for replaying checkpoints with graphics, sound, speed control, and rewind.

The project is designed so the public repository contains only source code and documentation. You bring your own legally obtained ROM and local data files.

**Highest digit reached:** 10,000,000 digits consumed in the `pi_10m_two_digit` run.

![piPokemon web review player with local ROM preview hidden](docs/review-player.png)

The README screenshot masks the gameplay preview so the public repo does not include ROM-derived imagery.

## Layout

- `roms/` - local ROM files, ignored by git
- `saves/` - emulator RAM/save state files, ignored by git
- `data/` - downloaded pi digit files, ignored by git
- `tas/` - downloaded TAS/movie files, ignored by git
- `tools/` - downloaded emulator cores and local tools, ignored by git
- `src/` - project code
- `scripts/` - local benchmark and utility scripts
- `results/` - generated benchmark/output files, ignored by git

## Publishing / Asset Policy

This repository intentionally does not include Pokemon ROMs, save files, savestates, screenshots, downloaded TAS movies, pi digit dumps, emulator core binaries, or other generated/local assets.

To run the experiments, provide your own legally obtained Pokemon Red ROM in `roms/` and download or generate pi digit files into `data/`. Those folders are kept in the repo only with `.gitkeep` placeholders.

Before publishing or pushing changes, check:

```powershell
git status --short --ignored
git ls-files
```

Only source code, documentation, and placeholder files should appear in `git ls-files`.

## Setup

```powershell
py -m pip install -r requirements.txt
```

Expected local files:

- `roms/Pokemon - Red Version (USA, Europe) (SGB Enhanced).gb`
- `data/pi_10m_digits.txt`

The scripts assume those default paths, but most commands accept `--rom` and `--digits` overrides.

## Current Benchmark Baseline

On this machine, PyBoy in headless unlimited mode measured roughly:

- single stream with one digit mapped to one button per frame: about 33,000 frames/sec, or about 550x real time
- 16 parallel streams: about 295,000 aggregate frames/sec, or about 4,900x real time

Native emulator cores such as Gambatte should be benchmarked next for a higher ceiling.

## Pi Input Run

The active input scheme consumes two decimal digits at a time and presses the mapped button for two frames, followed by one blank frame:

- `00-53` -> A
- `54-63` -> Up
- `64-73` -> Down
- `74-83` -> Left
- `84-93` -> Right
- `94-98` -> B
- `99` -> Start

Run or resume the 10 million digit PyBoy test with:

```powershell
py scripts\run_pi_pyboy.py --run-name pi_10m_two_digit --digits data\pi_10m_digits.txt --checkpoint-digits 1000000 --hold-frames 2 --release-frames 1
```

Add `--fresh` to ignore existing checkpoints and restart from reset.

Checkpoints are saved in `saves/pi_10m_two_digit/`, screenshots in `results/pi_10m_two_digit/screenshots/`, and progress metadata in `results/pi_10m_two_digit/progress.json`. These generated files are intentionally ignored by git.

The current verified run uses the first million digits with checkpoints every 100k:

```powershell
py scripts\run_pi_pyboy.py --run-name pi_1m_hold2_release1 --digits data\pi_10m_digits.txt --max-digits 1000000 --checkpoint-digits 100000 --hold-frames 2 --release-frames 1
```

Generated savestates go under `saves/<run-name>/`, screenshots under `results/<run-name>/screenshots/`, and progress metadata under `results/<run-name>/progress.json`.

Review a checkpoint in the local web UI:

```powershell
.\scripts\open_review.ps1
```

The launcher closes older web or Tk reviewer instances before opening a new browser tab.

By default, the reviewer is limited only by the local pi digit file. Pass `-MaxDigits 1000000` to the PowerShell launcher, or `--max-digits 1000000` to `review_web.py`, when you want to cap playback for a shorter review.
Audio is most reliable at `--speed 1`; higher speeds may outrun PyBoy's SDL audio queue.
The reviewer opens paused by default. Press `Pause/Resume` to start playback, or pass `--start-running` when launching directly. During playback, pausing is applied at the next input boundary: after the current held/released input cycle finishes and before the next pi-derived button is sent. It applies its own frame limiter, so `1x` targets normal Game Boy speed even though the emulator loop is driven manually.

Open a specific checkpoint by digit count:

```powershell
py scripts\review_web.py --checkpoint 5000000 --speed 1 --open-browser
```

The web reviewer continues the same pi input stream from the checkpoint. It serves the Game Boy screen and controls from a local web app, with a labeled logarithmic speed slider from `1x` to `1000x`, a checkbox to enable or bypass the speed limiter, an `inputs sent` counter, the last pi-derived button sent, a Tetris-style preview of upcoming inputs, and a digit-based rewind dropdown (`10`, `100`, `1000`, etc.) backed by in-memory savestate snapshots.

## TAS Button Tally

The TAS helper parses BizHawk `.bk2` movie files and counts button press frequency:

```powershell
py scripts\tally_tas_buttons.py path\to\movie.bk2
```

Downloaded TAS files and generated tally outputs are ignored by git.

## Status

This is experimental tooling, not a packaged emulator frontend. The current practical path is PyBoy for simulation and review; native libretro benchmark code is kept under `src/LibretroBench/` for comparison work.
