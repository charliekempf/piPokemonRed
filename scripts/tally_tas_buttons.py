from __future__ import annotations

import argparse
import csv
import json
import zipfile
from collections import Counter
from pathlib import Path


def read_input_log(movie_path: Path) -> str:
    """Read Input Log.txt from a BizHawk .bk2 or a TASVideos wrapper archive."""
    with zipfile.ZipFile(movie_path) as archive:
        names = archive.namelist()
        if "Input Log.txt" in names:
            return archive.read("Input Log.txt").decode("utf-8", errors="replace")

        nested_bk2 = next((name for name in names if name.lower().endswith(".bk2")), None)
        if nested_bk2 is None:
            raise ValueError(f"{movie_path} does not contain Input Log.txt or a nested .bk2")

        nested_bytes = archive.read(nested_bk2)

    nested_path = movie_path.with_suffix(movie_path.suffix + ".nested")
    nested_path.write_bytes(nested_bytes)
    try:
        with zipfile.ZipFile(nested_path) as nested:
            return nested.read("Input Log.txt").decode("utf-8", errors="replace")
    finally:
        nested_path.unlink(missing_ok=True)


def parse_log_key(line: str) -> list[str]:
    key = line.split(":", 1)[1]
    if key.startswith("#"):
        key = key[1:]
    return [part for part in key.split("|") if part]


def tally(input_log: str) -> tuple[list[str], int, Counter[str], Counter[str]]:
    buttons: list[str] | None = None
    held_frames: Counter[str] = Counter()
    press_events: Counter[str] = Counter()
    previous: list[bool] | None = None
    total_frames = 0

    for raw_line in input_log.splitlines():
        line = raw_line.strip()
        if line.startswith("LogKey:"):
            buttons = parse_log_key(line)
            previous = [False] * len(buttons)
            continue
        if buttons is None or not line.startswith("|"):
            continue

        fields = line.strip("|").split("|")
        if not fields or len(fields[0]) != len(buttons):
            continue

        state = [char != "." for char in fields[0]]
        total_frames += 1
        for index, pressed in enumerate(state):
            if pressed:
                held_frames[buttons[index]] += 1
            if pressed and previous is not None and not previous[index]:
                press_events[buttons[index]] += 1
        previous = state

    if buttons is None:
        raise ValueError("No LogKey line found in input log")

    return buttons, total_frames, held_frames, press_events


def main() -> None:
    parser = argparse.ArgumentParser(description="Tally button frequency in a BizHawk .bk2 TAS movie.")
    parser.add_argument("movie", type=Path)
    parser.add_argument("--json", type=Path, default=Path("results/tas_button_tally.json"))
    parser.add_argument("--csv", type=Path, default=Path("results/tas_button_tally.csv"))
    args = parser.parse_args()

    buttons, total_frames, held_frames, press_events = tally(read_input_log(args.movie))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.csv.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for button in buttons:
        rows.append(
            {
                "button": button,
                "held_frames": held_frames[button],
                "held_frame_percent": held_frames[button] / total_frames if total_frames else 0,
                "press_events": press_events[button],
                "press_events_per_1000_frames": press_events[button] * 1000 / total_frames
                if total_frames
                else 0,
            }
        )

    args.json.write_text(
        json.dumps({"total_frames": total_frames, "buttons": rows}, indent=2),
        encoding="utf-8",
    )
    with args.csv.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"frames: {total_frames}")
    for row in rows:
        print(
            f"{row['button']:>6}: "
            f"held={row['held_frames']:>6} "
            f"({row['held_frame_percent'] * 100:6.2f}%), "
            f"presses={row['press_events']:>5} "
            f"({row['press_events_per_1000_frames']:6.2f}/1000f)"
        )


if __name__ == "__main__":
    main()
