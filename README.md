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

The active input scheme consumes two decimal digits at a time and presses the mapped button for one frame, followed by one blank frame:

- `00-53` -> A
- `54-63` -> Up
- `64-73` -> Down
- `74-83` -> Left
- `84-93` -> Right
- `94-98` -> B
- `99` -> Start

Run or resume the 10 million digit PyBoy test with:

```powershell
py scripts\run_pi_pyboy.py --run-name pi_10m_two_digit --digits data\pi_10m_digits.txt --checkpoint-digits 1000000
```

Add `--fresh` to ignore existing checkpoints and restart from reset.

Checkpoints are saved in `saves/pi_10m_two_digit/`, screenshots in `results/pi_10m_two_digit/screenshots/`, and progress metadata in `results/pi_10m_two_digit/progress.json`. These generated files are intentionally ignored by git.
