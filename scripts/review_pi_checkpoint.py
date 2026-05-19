from __future__ import annotations

import argparse
import io
import math
import re
import threading
import time
import tkinter as tk
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk

import sdl2
from PIL import Image, ImageTk
from pyboy import PyBoy

from run_pi_pyboy import (
    GAMEBOY_FPS,
    INPUT_CONFIG,
    PI_DIGITS,
    ROM,
    RUN_NAME,
    PiInputConfig,
    Progress,
    advance_pi_inputs,
    button_for_value,
    latest_checkpoint,
    load_input_config,
    save_checkpoint,
    write_progress,
)


CHECKPOINT_RE = re.compile(r"checkpoint_(\d{8})_digits\.state$")
PARTY_COUNT_ADDR = 0xD163
PARTY_SPECIES_ADDR = 0xD164
PARTY_MONS_ADDR = 0xD16B
PARTY_MON_SIZE = 44
PARTY_NICKS_ADDR = 0xD2B5
PARTY_NAME_LENGTH = 11
PARTY_SIZE = 6
BATTLE_FLAG_ADDR = 0xD057
SPECIES_NAMES = {
    0x01: "Rhydon",
    0x02: "Kangaskhan",
    0x03: "Nidoran M",
    0x04: "Clefairy",
    0x05: "Spearow",
    0x06: "Voltorb",
    0x07: "Nidoking",
    0x08: "Slowbro",
    0x09: "Ivysaur",
    0x0A: "Exeggutor",
    0x0B: "Lickitung",
    0x0C: "Exeggcute",
    0x0D: "Grimer",
    0x0E: "Gengar",
    0x0F: "Nidoran F",
    0x10: "Nidoqueen",
    0x11: "Cubone",
    0x12: "Rhyhorn",
    0x13: "Lapras",
    0x14: "Arcanine",
    0x15: "Mew",
    0x16: "Gyarados",
    0x17: "Shellder",
    0x18: "Tentacool",
    0x19: "Gastly",
    0x1A: "Scyther",
    0x1B: "Staryu",
    0x1C: "Blastoise",
    0x1D: "Pinsir",
    0x1E: "Tangela",
    0x21: "Growlithe",
    0x22: "Onix",
    0x23: "Fearow",
    0x24: "Pidgey",
    0x25: "Slowpoke",
    0x26: "Kadabra",
    0x27: "Graveler",
    0x28: "Chansey",
    0x29: "Machoke",
    0x2A: "Mr. Mime",
    0x2B: "Hitmonlee",
    0x2C: "Hitmonchan",
    0x2D: "Arbok",
    0x2E: "Parasect",
    0x2F: "Psyduck",
    0x30: "Drowzee",
    0x31: "Golem",
    0x33: "Magmar",
    0x35: "Electabuzz",
    0x36: "Magneton",
    0x37: "Koffing",
    0x39: "Mankey",
    0x3A: "Seel",
    0x3B: "Diglett",
    0x3C: "Tauros",
    0x40: "Farfetch'd",
    0x41: "Venonat",
    0x42: "Dragonite",
    0x46: "Doduo",
    0x47: "Poliwag",
    0x48: "Jynx",
    0x49: "Moltres",
    0x4A: "Articuno",
    0x4B: "Zapdos",
    0x4C: "Ditto",
    0x4D: "Meowth",
    0x4E: "Krabby",
    0x52: "Vulpix",
    0x53: "Ninetales",
    0x54: "Pikachu",
    0x55: "Raichu",
    0x58: "Dratini",
    0x59: "Dragonair",
    0x5A: "Kabuto",
    0x5B: "Kabutops",
    0x5C: "Horsea",
    0x5D: "Seadra",
    0x60: "Sandshrew",
    0x61: "Sandslash",
    0x62: "Omanyte",
    0x63: "Omastar",
    0x64: "Jigglypuff",
    0x65: "Wigglytuff",
    0x66: "Eevee",
    0x67: "Flareon",
    0x68: "Jolteon",
    0x69: "Vaporeon",
    0x6A: "Machop",
    0x6B: "Zubat",
    0x6C: "Ekans",
    0x6D: "Paras",
    0x6E: "Poliwhirl",
    0x6F: "Poliwrath",
    0x70: "Weedle",
    0x71: "Kakuna",
    0x72: "Beedrill",
    0x74: "Dodrio",
    0x75: "Primeape",
    0x76: "Dugtrio",
    0x77: "Venomoth",
    0x78: "Dewgong",
    0x7B: "Caterpie",
    0x7C: "Metapod",
    0x7D: "Butterfree",
    0x7E: "Machamp",
    0x80: "Golduck",
    0x81: "Hypno",
    0x82: "Golbat",
    0x83: "Mewtwo",
    0x84: "Snorlax",
    0x85: "Magikarp",
    0x88: "Muk",
    0x8A: "Kingler",
    0x8B: "Cloyster",
    0x8D: "Electrode",
    0x8E: "Clefable",
    0x8F: "Weezing",
    0x90: "Persian",
    0x91: "Marowak",
    0x93: "Haunter",
    0x94: "Abra",
    0x95: "Alakazam",
    0x96: "Pidgeotto",
    0x97: "Pidgeot",
    0x98: "Starmie",
    0x99: "Bulbasaur",
    0x9A: "Venusaur",
    0x9B: "Tentacruel",
    0x9D: "Goldeen",
    0x9E: "Seaking",
    0xA3: "Ponyta",
    0xA4: "Rapidash",
    0xA5: "Rattata",
    0xA6: "Raticate",
    0xA7: "Nidorino",
    0xA8: "Nidorina",
    0xA9: "Geodude",
    0xAA: "Porygon",
    0xAB: "Aerodactyl",
    0xAD: "Magnemite",
    0xB0: "Charmander",
    0xB1: "Squirtle",
    0xB2: "Charmeleon",
    0xB3: "Wartortle",
    0xB4: "Charizard",
    0xB9: "Oddish",
    0xBA: "Gloom",
    0xBB: "Vileplume",
    0xBC: "Bellsprout",
    0xBD: "Weepinbell",
    0xBE: "Victreebel",
}


@dataclass
class Snapshot:
    digits_consumed: int
    frames_elapsed: int
    state: bytes


class AudioSink:
    def __init__(self, sample_rate: int) -> None:
        self.device = 0
        if sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_AUDIO) != 0:
            return

        want = sdl2.SDL_AudioSpec(sample_rate, sdl2.AUDIO_S8, 2, 128)
        have = sdl2.SDL_AudioSpec(0, 0, 0, 0)
        self.device = sdl2.SDL_OpenAudioDevice(None, 0, want, have, 0)
        if self.device:
            sdl2.SDL_PauseAudioDevice(self.device, 0)

    def queue(self, pyboy: PyBoy, volume: int) -> None:
        if not self.device:
            return

        head = pyboy.sound.raw_buffer_head
        if head <= 0:
            return

        data = bytes(pyboy.sound.raw_buffer[:head])
        if volume < 100:
            scale = max(0, min(100, volume)) / 100
            data = bytes(max(-128, min(127, int(int.from_bytes(bytes([sample]), "little", signed=True) * scale))) & 0xFF for sample in data)
        sdl2.SDL_QueueAudio(self.device, data, len(data))

    def close(self) -> None:
        if self.device:
            sdl2.SDL_CloseAudioDevice(self.device)
            self.device = 0


def decode_pokemon_text(values: list[int]) -> str:
    chars: list[str] = []
    for value in values:
        if value == 0x50:
            break
        if value == 0x7F:
            chars.append(" ")
        elif 0x80 <= value <= 0x99:
            chars.append(chr(ord("A") + value - 0x80))
        elif 0xA0 <= value <= 0xB9:
            chars.append(chr(ord("a") + value - 0xA0))
        elif 0xF6 <= value <= 0xFF:
            chars.append(chr(ord("0") + value - 0xF6))
        elif value == 0xE0:
            chars.append("'")
        elif value == 0xE3:
            chars.append("-")
        elif value == 0xE6:
            chars.append("?")
        elif value == 0xE7:
            chars.append("!")
    return "".join(chars).strip()


def read_u16_be(pyboy: PyBoy, address: int) -> int:
    return (int(pyboy.memory[address]) << 8) | int(pyboy.memory[address + 1])


def status_label(value: int) -> str:
    if value == 0:
        return "OK"
    if value & 0x08:
        return "PSN"
    if value & 0x10:
        return "BRN"
    if value & 0x20:
        return "FRZ"
    if value & 0x40:
        return "PAR"
    if value & 0x07:
        return "SLP"
    return "OK"


def is_in_battle(pyboy: PyBoy) -> bool:
    return int(pyboy.memory[BATTLE_FLAG_ADDR]) != 0


def is_party_blackout(pyboy: PyBoy) -> bool:
    count = int(pyboy.memory[PARTY_COUNT_ADDR])
    if count <= 0 or count > PARTY_SIZE:
        return False
    for index in range(count):
        mon_addr = PARTY_MONS_ADDR + (index * PARTY_MON_SIZE)
        if read_u16_be(pyboy, mon_addr + 1) > 0:
            return False
    return True


class ReviewSession:
    def __init__(
        self,
        pyboy: PyBoy,
        digits: str,
        digits_consumed: int,
        max_digits: int,
        hold_frames: int,
        release_frames: int,
        rewind_interval_digits: int,
        rewind_history_digits: int,
        sound_volume: int,
        audio_sink: AudioSink | None,
        initial_image: Image.Image | None = None,
        rom_path: Path | None = None,
        run_name: str = RUN_NAME,
        digits_path: Path = PI_DIGITS,
        input_config: PiInputConfig | None = None,
    ) -> None:
        self.pyboy = pyboy
        self.rom_path = rom_path
        self.run_name = run_name
        self.digits_path = digits_path
        self.input_config = input_config or load_input_config()
        self.digits = digits
        self.digits_consumed = digits_consumed
        self.max_digits = max_digits
        self.hold_frames = hold_frames
        self.release_frames = release_frames
        self.frames_per_input = hold_frames + release_frames
        self.frames_elapsed = (digits_consumed // self.input_config.digits_per_input) * self.frames_per_input
        self.rewind_interval_digits = rewind_interval_digits
        self.max_snapshots = max(2, rewind_history_digits // rewind_interval_digits)
        self.snapshots: deque[Snapshot] = deque(maxlen=self.max_snapshots)
        self.running = True
        self.paused = True
        self.pause_requested = False
        self.speed = 1
        self.speed_limiter_enabled = True
        self.status = "paused"
        self.inputs_sent = 0
        self.last_button = "-"
        self.latest_image = initial_image.copy() if initial_image is not None else None
        self.sound_volume = sound_volume
        self.audio_sink = audio_sink
        self._next_frame_time = time.perf_counter()
        self._lock = threading.Lock()
        self._rewind_digits_requested = 0
        self._fast_forward_target_digits: int | None = None
        self._simulate_target_digits: int | None = None
        self._jump_target_digits: int | None = None
        self._warp_target_state: str | None = None
        self._simulation_started_at: float | None = None
        self._last_simulation: dict[str, int | float | str] | None = None
        self._auto_snapshots_enabled = True
        self._last_snapshot_digits = digits_consumed - rewind_interval_digits
        self._take_snapshot()
        if self.latest_image is None:
            self._capture_frame()

    def set_speed(self, speed: float) -> None:
        with self._lock:
            self.speed = max(1, min(1000, int(round(speed))))
            if (
                self._fast_forward_target_digits is None
                and self._simulate_target_digits is None
                and self._jump_target_digits is None
                and self._warp_target_state is None
            ):
                self.pyboy.set_emulation_speed(self.speed)

    def set_speed_limiter_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.speed_limiter_enabled = enabled
            self._next_frame_time = time.perf_counter()

    def set_max_digits(self, max_digits: int) -> None:
        with self._lock:
            self.max_digits = max(self.digits_consumed, max_digits)

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self.paused = paused
            if not paused:
                self.pause_requested = False
            self.status = "paused" if paused else "running"

    def toggle_pause_at_boundary(self) -> None:
        with self._lock:
            if self.paused:
                self.paused = False
                self.pause_requested = False
                self.status = "running"
            else:
                self.pause_requested = True
                self._fast_forward_target_digits = None
                self._simulate_target_digits = None
                self._jump_target_digits = None
                self._warp_target_state = None
                self.pyboy.set_emulation_speed(self.speed)
                self.status = "pause pending"

    def request_rewind(self, digits: int) -> None:
        with self._lock:
            self._rewind_digits_requested = max(self._rewind_digits_requested, digits)
            self._fast_forward_target_digits = None
            self._simulate_target_digits = None
            self._jump_target_digits = None
            self._warp_target_state = None
            self.pyboy.set_emulation_speed(self.speed)

    def request_fast_forward(self, digits: int) -> None:
        digits = self._normalize_digit_distance(digits)
        with self._lock:
            target = min(self.max_digits, self.digits_consumed + digits)
            if target % self.input_config.digits_per_input:
                target -= target % self.input_config.digits_per_input
            if target <= self.digits_consumed:
                self.status = "complete" if self.digits_consumed >= self.max_digits else "paused"
                return
            self._fast_forward_target_digits = target
            self._simulate_target_digits = None
            self._jump_target_digits = None
            self._warp_target_state = None
            self.pyboy.set_emulation_speed(0)
            self.paused = False
            self.pause_requested = False
            self.status = f"fast forwarding to {target:,} digits"

    def request_simulate(self, digits: int) -> None:
        digits = self._normalize_digit_distance(digits)
        with self._lock:
            if self._simulate_target_digits is not None:
                return
            target = min(self.max_digits, self.digits_consumed + digits)
            if target % self.input_config.digits_per_input:
                target -= target % self.input_config.digits_per_input
            if target <= self.digits_consumed:
                self.status = "complete" if self.digits_consumed >= self.max_digits else "paused"
                return
            self._simulate_target_digits = target
            self._simulation_started_at = time.perf_counter()
            self._fast_forward_target_digits = None
            self._jump_target_digits = None
            self._warp_target_state = None
            self.paused = False
            self.pause_requested = False
            self.pyboy.set_emulation_speed(0)
            self.status = f"simulating to {target:,} digits"

    def request_jump(self, digits: int) -> int:
        target = max(0, min(self.max_digits, int(digits)))
        if target % self.input_config.digits_per_input:
            target -= target % self.input_config.digits_per_input
        with self._lock:
            self._jump_target_digits = target
            self._rewind_digits_requested = 0
            self._fast_forward_target_digits = None
            self._simulate_target_digits = None
            self._warp_target_state = None
            self.paused = False
            self.pause_requested = False
            self.pyboy.set_emulation_speed(0)
            self.status = f"jumping to {target:,} digits"
        return target

    def request_warp_state(self, target_state: str) -> str:
        target_state = target_state.lower().strip()
        if target_state not in {"battle", "blackout"}:
            raise ValueError(f"Unsupported warp state: {target_state}")
        with self._lock:
            self._warp_target_state = target_state
            self._rewind_digits_requested = 0
            self._fast_forward_target_digits = None
            self._simulate_target_digits = None
            self._jump_target_digits = None
            self.paused = False
            self.pause_requested = False
            self.pyboy.set_emulation_speed(0)
            self.status = f"finding next {target_state}"
        return target_state

    def stop(self) -> None:
        with self._lock:
            self.running = False

    def info(self) -> dict[str, int | str]:
        with self._lock:
            return {
                "digits_consumed": self.digits_consumed,
                "max_digits": self.max_digits,
                "frames_elapsed": self.frames_elapsed,
                "speed": self.speed,
                "speed_limiter_enabled": "on" if self.speed_limiter_enabled else "off",
                "status": self.status,
                "snapshots": len(self.snapshots),
                "inputs_sent": self.inputs_sent,
                "last_button": self.last_button,
                "last_simulation": self._last_simulation or {},
            }

    def party(self) -> list[dict[str, int | str]]:
        with self._lock:
            count = int(self.pyboy.memory[PARTY_COUNT_ADDR])
            if count < 0 or count > PARTY_SIZE:
                return []

            members: list[dict[str, int | str]] = []
            for index in range(count):
                species = int(self.pyboy.memory[PARTY_SPECIES_ADDR + index])
                mon_addr = PARTY_MONS_ADDR + (index * PARTY_MON_SIZE)
                nick_addr = PARTY_NICKS_ADDR + (index * PARTY_NAME_LENGTH)
                name_bytes = [int(self.pyboy.memory[nick_addr + offset]) for offset in range(PARTY_NAME_LENGTH)]
                name = decode_pokemon_text(name_bytes) or f"MON {species:03d}"
                species_name = SPECIES_NAMES.get(species, f"Species {species:03d}")
                level = int(self.pyboy.memory[mon_addr + 33])
                current_hp = read_u16_be(self.pyboy, mon_addr + 1)
                max_hp = read_u16_be(self.pyboy, mon_addr + 34)
                status = int(self.pyboy.memory[mon_addr + 4])
                members.append(
                    {
                        "slot": index + 1,
                        "species": species,
                        "species_name": species_name,
                        "name": name,
                        "level": level,
                        "hp": current_hp,
                        "max_hp": max_hp,
                        "status": status_label(status),
                    }
                )
            return members

    def run(self) -> None:
        self.pyboy.set_emulation_speed(self.speed)
        try:
            while True:
                with self._lock:
                    if not self.running:
                        break
                    paused = self.paused
                    pause_requested = self.pause_requested
                    rewind_digits = self._rewind_digits_requested
                    self._rewind_digits_requested = 0
                    fast_forward_target = self._fast_forward_target_digits
                    simulate_target = self._simulate_target_digits
                    jump_target = self._jump_target_digits
                    warp_target_state = self._warp_target_state

                if rewind_digits:
                    self._rewind(rewind_digits)
                    continue

                if jump_target is not None:
                    self._jump_to(jump_target)
                    continue

                if warp_target_state is not None:
                    self._find_next_warp_state_with_backend(warp_target_state)
                    continue

                if paused or pause_requested:
                    with self._lock:
                        if pause_requested:
                            self.paused = True
                            self.pause_requested = False
                            self.status = "paused"
                    time.sleep(1 / 30)
                    continue

                if self.digits_consumed >= self.max_digits:
                    with self._lock:
                        self.status = "complete"
                    self.pyboy.tick(1, True)
                    time.sleep(1 / 30)
                    continue

                if fast_forward_target is not None:
                    self._fast_forward_with_backend(fast_forward_target)
                    continue

                if simulate_target is not None:
                    self._simulate_with_backend(simulate_target)
                    continue

                will_finish_fast_forward = (
                    fast_forward_target is not None
                    and self.digits_consumed + self.input_config.digits_per_input >= fast_forward_target
                )
                value = int(self.digits[self.digits_consumed : self.digits_consumed + self.input_config.digits_per_input])
                button = button_for_value(value, self.input_config)
                self.pyboy.button_press(button)
                self._tick_frames(self.hold_frames)
                self.pyboy.button_release(button)
                self._tick_frames(self.release_frames, force_final_render=will_finish_fast_forward)
                with self._lock:
                    self.digits_consumed += self.input_config.digits_per_input
                    self.frames_elapsed += self.frames_per_input
                    self.inputs_sent += 1
                    self.last_button = button
                    if fast_forward_target is not None and self.digits_consumed >= fast_forward_target:
                        self.paused = True
                        self._fast_forward_target_digits = None
                        self.pyboy.set_emulation_speed(self.speed)
                        self.status = "complete" if self.digits_consumed >= self.max_digits else "paused"
                        self._next_frame_time = time.perf_counter()

                if (
                    self._auto_snapshots_enabled
                    and self.digits_consumed - self._last_snapshot_digits >= self.rewind_interval_digits
                ):
                    self._take_snapshot()
        finally:
            if self.audio_sink:
                self.audio_sink.close()
            self.pyboy.stop()

    def _tick_frames(self, frames: int, force_final_render: bool = False) -> None:
        for frame_index in range(frames):
            with self._lock:
                fast_forwarding = self._fast_forward_target_digits is not None
            render_frame = not fast_forwarding or (force_final_render and frame_index == frames - 1)
            self.pyboy.tick(1, render_frame, not fast_forwarding)
            if self.audio_sink and not fast_forwarding:
                self.audio_sink.queue(self.pyboy, self.sound_volume)
            if render_frame:
                self._capture_frame()
            self._limit_frame_rate()

    def _checkpoint_at_or_before(self, target_digits: int, minimum_digits: int = 0) -> tuple[int, Path] | None:
        checkpoint_dir = Path("saves") / self.run_name
        candidates: list[tuple[int, Path]] = []
        for candidate in checkpoint_dir.glob("checkpoint_*_digits.state"):
            match = CHECKPOINT_RE.match(candidate.name)
            if match:
                digits_consumed = int(match.group(1))
                if minimum_digits <= digits_consumed <= target_digits:
                    candidates.append((digits_consumed, candidate))
        return max(candidates) if candidates else None

    def _fast_forward_with_backend(self, target_digits: int) -> None:
        with self._lock:
            start_digits = self.digits_consumed
            if self.paused or self.pause_requested or self._fast_forward_target_digits is None:
                return
            state_buffer = io.BytesIO()
            self.pyboy.save_state(state_buffer)

        target_digits = min(target_digits, self.max_digits)
        checkpoint = self._checkpoint_at_or_before(target_digits, minimum_digits=start_digits + self.input_config.digits_per_input)
        simulator = PyBoy(
            str(self.rom_path or ROM),
            window="null",
            sound_emulated=False,
            no_input=False,
            ram_file=io.BytesIO(bytes(32768)),
            log_level="CRITICAL",
        )
        simulator.set_emulation_speed(0)
        try:
            if checkpoint is not None:
                start_digits, checkpoint_path = checkpoint
                with checkpoint_path.open("rb") as state_file:
                    simulator.load_state(state_file)
            else:
                state_buffer.seek(0)
                simulator.load_state(state_buffer)
            digits_consumed, inputs_sent, last_button = advance_pi_inputs(
                simulator,
                self.digits,
                start_digits,
                target_digits,
                self.hold_frames,
                self.release_frames,
                input_config=self.input_config,
            )
            final_state = io.BytesIO()
            simulator.save_state(final_state)
        finally:
            simulator.stop()

        final_state.seek(0)
        self.pyboy.load_state(final_state)
        image = render_loaded_state(self.pyboy)
        with self._lock:
            self.digits_consumed = digits_consumed
            self.frames_elapsed += inputs_sent * self.frames_per_input
            self.inputs_sent += inputs_sent
            self.last_button = last_button
            self.paused = True
            self._fast_forward_target_digits = None
            self.pyboy.set_emulation_speed(self.speed)
            self.status = "complete" if self.digits_consumed >= self.max_digits else "paused"
            self._next_frame_time = time.perf_counter()
            self.latest_image = image
            self._auto_snapshots_enabled = False

    def _simulate_with_backend(self, target_digits: int) -> None:
        with self._lock:
            start_digits = self.digits_consumed
            started_at = self._simulation_started_at or time.perf_counter()
            if self.paused or self.pause_requested or self._simulate_target_digits is None:
                return
            state_buffer = io.BytesIO()
            self.pyboy.save_state(state_buffer)

        target_digits = min(target_digits, self.max_digits)
        state_buffer.seek(0)
        simulator = PyBoy(
            str(self.rom_path or ROM),
            window="null",
            sound_emulated=False,
            no_input=False,
            ram_file=io.BytesIO(bytes(32768)),
            log_level="CRITICAL",
        )
        simulator.set_emulation_speed(0)
        try:
            simulator.load_state(state_buffer)
            digits_consumed, inputs_sent, last_button = advance_pi_inputs(
                simulator,
                self.digits,
                start_digits,
                target_digits,
                self.hold_frames,
                self.release_frames,
                input_config=self.input_config,
            )
            checkpoint_dir = Path("saves") / self.run_name
            screenshot_dir = Path("results") / self.run_name / "screenshots"
            last_state = save_checkpoint(
                simulator,
                checkpoint_dir,
                screenshot_dir,
                digits_consumed,
                save_screenshot=True,
            )
            final_state = io.BytesIO()
            simulator.save_state(final_state)
        finally:
            simulator.stop()

        elapsed = max(time.perf_counter() - started_at, 0.000001)
        effective_digits_per_second = (digits_consumed - start_digits) / elapsed
        frames_advanced = inputs_sent * self.frames_per_input
        effective_fps = frames_advanced / elapsed
        progress = Progress(
            run_name=self.run_name,
            digits_path=str(self.digits_path),
            rom_path=str(self.rom_path or ROM),
            digits_consumed=digits_consumed,
            input_pairs_consumed=digits_consumed // self.input_config.digits_per_input,
            frames_elapsed=(digits_consumed // self.input_config.digits_per_input) * self.frames_per_input,
            checkpoints_completed=len(list(checkpoint_dir.glob("checkpoint_*_digits.state"))),
            elapsed_seconds=elapsed,
            effective_fps=effective_fps,
            effective_realtime_x=effective_fps / GAMEBOY_FPS,
            last_state=str(last_state),
        )
        write_progress(Path("results") / self.run_name / "progress.json", progress)

        final_state.seek(0)
        self.pyboy.load_state(final_state)
        image = render_loaded_state(self.pyboy)
        with self._lock:
            self.digits_consumed = digits_consumed
            self.frames_elapsed += inputs_sent * self.frames_per_input
            self.inputs_sent += inputs_sent
            self.last_button = last_button
            self.paused = True
            self._simulate_target_digits = None
            self._simulation_started_at = None
            self.pyboy.set_emulation_speed(self.speed)
            self.status = "complete" if self.digits_consumed >= self.max_digits else "paused"
            self._next_frame_time = time.perf_counter()
            self.latest_image = image
            self._auto_snapshots_enabled = False
            self._last_simulation = {
                "digits": digits_consumed - start_digits,
                "elapsed_seconds": elapsed,
                "digits_per_second": effective_digits_per_second,
                "last_state": str(last_state),
            }

    def _limit_frame_rate(self) -> None:
        with self._lock:
            speed = self.speed
            enabled = self.speed_limiter_enabled
            fast_forwarding = self._fast_forward_target_digits is not None
        if speed <= 0 or not enabled or fast_forwarding:
            return

        now = time.perf_counter()
        if self._next_frame_time < now - 0.25:
            self._next_frame_time = now
        self._next_frame_time += 1 / (60 * speed)
        delay = self._next_frame_time - time.perf_counter()
        if delay > 0:
            time.sleep(delay)

    def _take_snapshot(self) -> None:
        buffer = io.BytesIO()
        self.pyboy.save_state(buffer)
        with self._lock:
            self.snapshots.append(
                Snapshot(
                    digits_consumed=self.digits_consumed,
                    frames_elapsed=self.frames_elapsed,
                    state=buffer.getvalue(),
                )
            )
            self._last_snapshot_digits = self.digits_consumed

    def _rewind(self, digits: int) -> None:
        with self._lock:
            target = max(0, self.digits_consumed - digits)
            if target % self.input_config.digits_per_input:
                target -= target % self.input_config.digits_per_input
            candidates = [snapshot for snapshot in self.snapshots if snapshot.digits_consumed <= target]
            snapshot = candidates[-1] if candidates else self.snapshots[0]
            self.pyboy.load_state(io.BytesIO(snapshot.state))
            snapshot_digits = snapshot.digits_consumed
            snapshot_frames = snapshot.frames_elapsed
            self._last_snapshot_digits = snapshot.digits_consumed
            self._fast_forward_target_digits = None
            self.pyboy.set_emulation_speed(self.speed)
        digits_consumed, inputs_sent, last_button = advance_pi_inputs(
            self.pyboy,
            self.digits,
            snapshot_digits,
            target,
            self.hold_frames,
            self.release_frames,
            input_config=self.input_config,
        )
        image = render_loaded_state(self.pyboy)
        with self._lock:
            self.digits_consumed = digits_consumed
            self.frames_elapsed = snapshot_frames + inputs_sent * self.frames_per_input
            if inputs_sent:
                self.last_button = last_button
            self.status = f"rewound to {digits_consumed:,} digits"
            self.latest_image = image

    def _jump_to(self, target: int) -> None:
        target = max(0, min(self.max_digits, target))
        if target % self.input_config.digits_per_input:
            target -= target % self.input_config.digits_per_input

        checkpoint = self._checkpoint_at_or_before(target)
        if checkpoint is None:
            with self._lock:
                self.paused = True
                self._jump_target_digits = None
                self.pyboy.set_emulation_speed(self.speed)
                self.status = "no checkpoint before target"
            return

        checkpoint_digits_consumed, checkpoint_path = checkpoint
        with checkpoint_path.open("rb") as state_file:
            self.pyboy.load_state(state_file)

        digits_consumed, inputs_sent, last_button = advance_pi_inputs(
            self.pyboy,
            self.digits,
            checkpoint_digits_consumed,
            target,
            self.hold_frames,
            self.release_frames,
            input_config=self.input_config,
        )
        image = render_loaded_state(self.pyboy)
        with self._lock:
            self.digits_consumed = digits_consumed
            self.frames_elapsed = (digits_consumed // self.input_config.digits_per_input) * self.frames_per_input
            self.inputs_sent = inputs_sent
            if inputs_sent:
                self.last_button = last_button
            self.paused = True
            self._jump_target_digits = None
            self.pyboy.set_emulation_speed(self.speed)
            self.status = "paused"
            self._next_frame_time = time.perf_counter()
            self.latest_image = image
            self._auto_snapshots_enabled = False

    def _find_next_warp_state_with_backend(self, target_state: str) -> None:
        with self._lock:
            start_digits = self.digits_consumed
            if self.paused or self.pause_requested or self._warp_target_state is None:
                return
            state_buffer = io.BytesIO()
            self.pyboy.save_state(state_buffer)

        state_buffer.seek(0)
        simulator = PyBoy(
            str(self.rom_path or ROM),
            window="null",
            sound_emulated=False,
            no_input=False,
            ram_file=io.BytesIO(bytes(32768)),
            log_level="CRITICAL",
        )
        simulator.set_emulation_speed(0)
        digits_consumed = start_digits
        inputs_sent = 0
        last_button = self.last_button
        found = False
        try:
            simulator.load_state(state_buffer)
            battle_seen = is_in_battle(simulator)
            blackout_seen = is_party_blackout(simulator)
            while digits_consumed < self.max_digits:
                value = int(self.digits[digits_consumed : digits_consumed + self.input_config.digits_per_input])
                button = button_for_value(value, self.input_config)
                simulator.button_press(button)
                simulator.tick(self.hold_frames, False, False)
                simulator.button_release(button)
                if self.release_frames:
                    simulator.tick(self.release_frames, False, False)
                digits_consumed += self.input_config.digits_per_input
                inputs_sent += 1
                last_button = button

                in_battle = is_in_battle(simulator)
                blackout = is_party_blackout(simulator)
                if target_state == "battle":
                    if battle_seen:
                        if not in_battle:
                            battle_seen = False
                    elif in_battle:
                        found = True
                        break
                else:
                    if blackout_seen:
                        if not blackout:
                            blackout_seen = False
                    elif blackout:
                        found = True
                        break

            final_state = io.BytesIO()
            if found:
                simulator.save_state(final_state)
        finally:
            simulator.stop()

        if not found:
            with self._lock:
                self.paused = True
                self._warp_target_state = None
                self.pyboy.set_emulation_speed(self.speed)
                self.status = f"no {target_state} before limit"
            return

        final_state.seek(0)
        self.pyboy.load_state(final_state)
        image = render_loaded_state(self.pyboy)
        with self._lock:
            self.digits_consumed = digits_consumed
            self.frames_elapsed += inputs_sent * self.frames_per_input
            self.inputs_sent += inputs_sent
            self.last_button = last_button
            self.paused = True
            self._warp_target_state = None
            self.pyboy.set_emulation_speed(self.speed)
            self.status = "paused"
            self._next_frame_time = time.perf_counter()
            self.latest_image = image
            self._auto_snapshots_enabled = False

    def _normalize_digit_distance(self, digits: int) -> int:
        digits_per_input = self.input_config.digits_per_input
        digits = max(digits_per_input, int(digits))
        if digits % digits_per_input:
            digits -= digits % digits_per_input
        return digits

    def _capture_frame(self) -> None:
        image = self.pyboy.screen.image.copy()
        with self._lock:
            self.latest_image = image

    def frame_image(self) -> Image.Image | None:
        with self._lock:
            return self.latest_image.copy() if self.latest_image is not None else None

    def upcoming_buttons(self, count: int = 12) -> list[tuple[int, str, str]]:
        with self._lock:
            start = self.digits_consumed

        buttons = []
        digits_per_input = self.input_config.digits_per_input
        for offset in range(0, count * digits_per_input, digits_per_input):
            digit_index = start + offset
            if digit_index + digits_per_input > self.max_digits:
                break
            digits_slice = self.digits[digit_index : digit_index + digits_per_input]
            buttons.append((digit_index, digits_slice, button_for_value(int(digits_slice), self.input_config)))
        return buttons

    def input_window(self, previous_count: int = 3, next_count: int = 11) -> list[dict[str, int | str]]:
        with self._lock:
            current = self.digits_consumed
            max_digits = self.max_digits

        items: list[dict[str, int | str]] = []
        digits_per_input = self.input_config.digits_per_input
        first = max(0, current - (previous_count * digits_per_input))
        last = min(max_digits, current + ((next_count + 1) * digits_per_input))
        for digit_index in range(first, last, digits_per_input):
            if digit_index + digits_per_input > max_digits:
                break
            digits_slice = self.digits[digit_index : digit_index + digits_per_input]
            if digit_index < current:
                role = "past"
            elif digit_index == current:
                role = "current"
            else:
                role = "future"
            items.append(
                {
                    "digit_index": digit_index,
                    "pair": digits_slice,
                    "button": button_for_value(int(digits_slice), self.input_config),
                    "role": role,
                }
            )
        return items


def checkpoint_digits(path: Path, explicit_digits: int | None) -> int:
    if explicit_digits is not None:
        return explicit_digits
    match = CHECKPOINT_RE.match(path.name)
    if not match:
        raise ValueError("Could not infer digit count from checkpoint name. Pass --digits-consumed.")
    return int(match.group(1))


def resolve_checkpoint(run_name: str, checkpoint: str, max_digits: int | None = None) -> Path:
    checkpoint_dir = Path("saves") / run_name
    if checkpoint in {"latest", "penultimate"}:
        candidates = []
        for candidate in checkpoint_dir.glob("checkpoint_*_digits.state"):
            match = CHECKPOINT_RE.match(candidate.name)
            if match:
                digits_consumed = int(match.group(1))
                if max_digits is None or digits_consumed < max_digits:
                    candidates.append((digits_consumed, candidate))
        if not candidates:
            raise FileNotFoundError(f"No checkpoints found in {checkpoint_dir}")
        if checkpoint == "penultimate" and len(candidates) >= 2:
            return sorted(candidates)[-2][1]
        return max(candidates)[1]

    candidate = Path(checkpoint)
    if candidate.exists():
        return candidate

    if checkpoint.isdigit():
        candidate = checkpoint_dir / f"checkpoint_{int(checkpoint):08d}_digits.state"
        if candidate.exists():
            return candidate

    raise FileNotFoundError(f"Checkpoint not found: {checkpoint}")


def build_control_panel(session: ReviewSession, scale: int) -> tk.Tk:
    root = tk.Tk()
    root.title("piPokemon review")
    root.resizable(False, False)

    status_var = tk.StringVar()
    speed_var = tk.DoubleVar(value=math.log10(max(1, session.speed)))
    speed_limiter_var = tk.BooleanVar(value=True)

    screen_label = ttk.Label(root)
    screen_label.grid(row=0, column=0, columnspan=4, padx=10, pady=(10, 6))

    preview_frame = ttk.LabelFrame(root, text="Next")
    preview_frame.grid(row=0, column=4, rowspan=6, padx=(0, 10), pady=10, sticky="ns")
    preview_labels = []
    for index in range(12):
        label = ttk.Label(preview_frame, width=16, anchor="w")
        label.grid(row=index, column=0, padx=8, pady=2, sticky="w")
        preview_labels.append(label)

    ttk.Label(root, textvariable=status_var, width=62).grid(row=1, column=0, columnspan=4, padx=10, pady=(0, 4))

    def speed_changed(value: str) -> None:
        session.set_speed(10 ** float(value))

    def speed_limiter_changed() -> None:
        session.set_speed_limiter_enabled(speed_limiter_var.get())

    ttk.Label(root, text="Speed").grid(row=2, column=0, padx=(10, 4), sticky="w")
    speed_slider = ttk.Scale(root, from_=0, to=3, variable=speed_var, command=speed_changed, length=320)
    speed_slider.grid(row=2, column=1, columnspan=3, padx=(0, 10), pady=4, sticky="ew")
    for column, label in enumerate(("1x", "10x", "100x", "1000x"), start=1):
        ttk.Label(root, text=label).grid(row=3, column=column - 1, padx=4, pady=(0, 4))
    rewind_digits_var = tk.StringVar(value="1000")

    def toggle_pause() -> None:
        session.toggle_pause_at_boundary()

    ttk.Checkbutton(root, text="Use speed slider", variable=speed_limiter_var, command=speed_limiter_changed).grid(
        row=4, column=0, columnspan=2, padx=10, pady=(2, 4), sticky="w"
    )

    ttk.Button(root, text="Pause/Resume", command=toggle_pause).grid(row=5, column=0, padx=10, pady=8)
    rewind_menu = ttk.Combobox(
        root,
        textvariable=rewind_digits_var,
        values=("10", "100", "1000", "10000", "100000", "1000000"),
        width=10,
        state="readonly",
    )
    rewind_menu.grid(row=5, column=1, padx=4, pady=8)
    ttk.Button(root, text="Rewind Digits", command=lambda: session.request_rewind(int(rewind_digits_var.get()))).grid(
        row=5, column=2, padx=4, pady=8
    )
    ttk.Button(root, text="Quit", command=lambda: (session.stop(), root.destroy())).grid(row=5, column=3, padx=10, pady=8)

    def refresh_screen() -> None:
        image = session.frame_image()
        if image is not None:
            scaled = image.resize((160 * scale, 144 * scale), Image.Resampling.NEAREST)
            photo = ImageTk.PhotoImage(scaled)
            screen_label.configure(image=photo)
            screen_label.image = photo
        root.after(33, refresh_screen)

    def refresh_status() -> None:
        info = session.info()
        status_var.set(
            f"{info['status']} | {info['digits_consumed']:,}/{info['max_digits']:,} digits | "
            f"{info['speed']}x ({info['speed_limiter_enabled']}) | inputs sent: {info['inputs_sent']:,} | "
            f"last: {info['last_button']} | rewind snapshots: {info['snapshots']}"
        )
        root.after(250, refresh_status)

    def refresh_preview() -> None:
        upcoming = session.upcoming_buttons(len(preview_labels))
        for index, label in enumerate(preview_labels):
            if index < len(upcoming):
                digit_index, pair, button = upcoming[index]
                prefix = ">" if index == 0 else " "
                label.configure(text=f"{prefix} {digit_index:07d}  {pair} -> {button.upper()}")
            else:
                label.configure(text="")
        root.after(250, refresh_preview)

    root.protocol("WM_DELETE_WINDOW", lambda: (session.stop(), root.destroy()))
    refresh_status()
    refresh_screen()
    refresh_preview()
    return root


def render_loaded_state(pyboy: PyBoy) -> Image.Image:
    restore_buffer = io.BytesIO()
    pyboy.save_state(restore_buffer)
    restore_buffer.seek(0)
    pyboy.tick(1, True, True)
    image = pyboy.screen.image.copy()
    restore_buffer.seek(0)
    pyboy.load_state(restore_buffer)
    return image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review a piPokemon PyBoy checkpoint with graphics, sound, speed, and rewind.")
    parser.add_argument("--rom", type=Path, default=ROM)
    parser.add_argument("--digits", type=Path, default=PI_DIGITS)
    parser.add_argument("--config", type=Path, default=INPUT_CONFIG)
    parser.add_argument("--run-name", default=RUN_NAME)
    parser.add_argument("--checkpoint", default="penultimate", help="penultimate, latest, a state path, or a digit count such as 5000000")
    parser.add_argument("--digits-consumed", type=int, default=None)
    parser.add_argument("--max-digits", type=int, default=None)
    parser.add_argument("--speed", type=int, default=10)
    parser.add_argument("--hold-frames", type=int, default=None)
    parser.add_argument("--release-frames", type=int, default=None)
    parser.add_argument("--scale", type=int, default=4)
    parser.add_argument("--sound-volume", type=int, default=100)
    parser.add_argument("--sound-sample-rate", type=int, default=48000)
    parser.add_argument("--rewind-history-digits", type=int, default=1_000_000)
    parser.add_argument("--rewind-interval-digits", type=int, default=100)
    parser.add_argument("--start-running", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_config = load_input_config(args.config)
    hold_frames = input_config.on_frames if args.hold_frames is None else args.hold_frames
    release_frames = input_config.off_frames if args.release_frames is None else args.release_frames
    if hold_frames < 1:
        raise ValueError("--hold-frames must be at least 1")
    if release_frames < 0:
        raise ValueError("--release-frames must be at least 0")
    if args.rewind_interval_digits < 2:
        raise ValueError("--rewind-interval-digits must be at least 2")
    if args.rewind_history_digits < args.rewind_interval_digits:
        raise ValueError("--rewind-history-digits must be at least --rewind-interval-digits")

    digits = args.digits.read_text(encoding="ascii").strip()
    max_digits = min(args.max_digits or len(digits), len(digits))
    if max_digits % input_config.digits_per_input:
        max_digits -= max_digits % input_config.digits_per_input
    checkpoint = resolve_checkpoint(args.run_name, args.checkpoint, max_digits=max_digits)
    start_digits = checkpoint_digits(checkpoint, args.digits_consumed)
    if start_digits >= max_digits:
        raise ValueError(
            f"Checkpoint is already at {start_digits:,} digits, but max is {max_digits:,}. "
            "Choose an earlier checkpoint or provide a larger digit file."
        )
    print(f"Reviewing {checkpoint} from {start_digits:,} to {max_digits:,} digits.")

    pyboy = PyBoy(
        str(args.rom),
        window="null",
        sound_emulated=True,
        sound_volume=args.sound_volume,
        sound_sample_rate=args.sound_sample_rate,
        no_input=False,
        ram_file=io.BytesIO(bytes(32768)),
        log_level="CRITICAL",
    )
    with checkpoint.open("rb") as state_file:
        pyboy.load_state(state_file)
    initial_image = render_loaded_state(pyboy)

    session = ReviewSession(
        pyboy=pyboy,
        digits=digits,
        digits_consumed=start_digits,
        max_digits=max_digits,
        hold_frames=hold_frames,
        release_frames=release_frames,
        rewind_interval_digits=args.rewind_interval_digits,
        rewind_history_digits=args.rewind_history_digits,
        sound_volume=args.sound_volume,
        audio_sink=AudioSink(args.sound_sample_rate),
        initial_image=initial_image,
        rom_path=args.rom,
        run_name=args.run_name,
        digits_path=args.digits,
        input_config=input_config,
    )
    session.set_speed(args.speed)
    if args.start_running:
        session.set_paused(False)

    emulator_thread = threading.Thread(target=session.run, name="pyboy-review", daemon=True)
    emulator_thread.start()

    control_panel = build_control_panel(session, args.scale)
    control_panel.mainloop()
    session.stop()
    emulator_thread.join(timeout=5)


if __name__ == "__main__":
    main()
