# piPokemon

Experiments for mapping digits of pi to Game Boy inputs and testing whether the resulting input stream can progress through Pokemon Red.

## Layout

- `roms/` - local ROM files, ignored by git
- `saves/` - emulator RAM/save state files, ignored by git
- `src/` - project code
- `scripts/` - local benchmark and utility scripts
- `results/` - generated benchmark/output files, ignored by git

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

Review a checkpoint with full PyBoy graphics and sound:

```powershell
py scripts\review_pi_checkpoint.py --checkpoint latest --speed 1
```

`latest` selects the latest checkpoint that still has remaining pi digits to play. With the 10 million digit test data, that means the 9 million digit checkpoint rather than the completed 10 million digit checkpoint.
Audio is most reliable at `--speed 1`; higher speeds may outrun PyBoy's SDL audio queue.

Open a specific checkpoint by digit count:

```powershell
py scripts\review_pi_checkpoint.py --checkpoint 5000000 --speed 1
```

The review window continues the same pi input stream from the checkpoint. The control panel has a logarithmic speed slider from `1x` to `100x`, an `inputs sent` counter, the last pi-derived button sent, and rewind buttons backed by in-memory savestate snapshots.
