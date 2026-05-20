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
    resolve_configured_run_name,
    save_checkpoint,
    write_progress,
)


CHECKPOINT_RE = re.compile(r"checkpoint_(\d+)_digits\.state$")
REVIEW_CACHE_DIRNAME = "review_cache"
REVIEW_CACHE_INTERVAL_DIGITS = 10_000
PARTY_COUNT_ADDR = 0xD163
PARTY_SPECIES_ADDR = 0xD164
PARTY_MONS_ADDR = 0xD16B
PARTY_MON_SIZE = 44
PARTY_NICKS_ADDR = 0xD2B5
PARTY_NAME_LENGTH = 11
PARTY_SIZE = 6
BAG_COUNT_ADDR = 0xD31D
BAG_ITEMS_ADDR = 0xD31E
BAG_CAPACITY = 20
BATTLE_FLAG_ADDR = 0xD057
BATTLE_TRAINER_VALUE = 2
OBTAINED_BADGES_ADDR = 0xD356
CURRENT_MAP_ADDR = 0xD35E
PLAYER_Y_ADDR = 0xD361
PLAYER_X_ADDR = 0xD362
EVO_OLD_SPECIES_ADDR = 0xCEE9
EVO_NEW_SPECIES_ADDR = 0xCEEA
EVOLUTION_OCCURRED_ADDR = 0xD121
POKEDEX_OWNED_ADDR = 0xD2F7
POKEDEX_SEEN_ADDR = 0xD30A
POKEDEX_FLAG_BYTES = 19
PLAYER_MONEY_ADDR = 0xD347
PLAY_TIME_HOURS_ADDR = 0xDA40
PLAY_TIME_MINUTES_ADDR = 0xDA42
PLAY_TIME_SECONDS_ADDR = 0xDA44
NUM_POKEMON = 151
BADGE_NAMES = [
    "Boulder",
    "Cascade",
    "Thunder",
    "Rainbow",
    "Soul",
    "Marsh",
    "Volcano",
    "Earth",
]
ITEM_NAMES = {
    0x01: "Master Ball",
    0x02: "Ultra Ball",
    0x03: "Great Ball",
    0x04: "Poke Ball",
    0x05: "Town Map",
    0x06: "Bicycle",
    0x07: "Surfboard",
    0x08: "Safari Ball",
    0x09: "Pokedex",
    0x0A: "Moon Stone",
    0x0B: "Antidote",
    0x0C: "Burn Heal",
    0x0D: "Ice Heal",
    0x0E: "Awakening",
    0x0F: "Parlyz Heal",
    0x10: "Full Restore",
    0x11: "Max Potion",
    0x12: "Hyper Potion",
    0x13: "Super Potion",
    0x14: "Potion",
    0x15: "Boulderbadge",
    0x16: "Cascadebadge",
    0x17: "Thunderbadge",
    0x18: "Rainbowbadge",
    0x19: "Soulbadge",
    0x1A: "Marshbadge",
    0x1B: "Volcanobadge",
    0x1C: "Earthbadge",
    0x1D: "Escape Rope",
    0x1E: "Repel",
    0x1F: "Old Amber",
    0x20: "Fire Stone",
    0x21: "Thunder Stone",
    0x22: "Water Stone",
    0x23: "HP Up",
    0x24: "Protein",
    0x25: "Iron",
    0x26: "Carbos",
    0x27: "Calcium",
    0x28: "Rare Candy",
    0x29: "Dome Fossil",
    0x2A: "Helix Fossil",
    0x2B: "Secret Key",
    0x2D: "Bike Voucher",
    0x2E: "X Accuracy",
    0x2F: "Leaf Stone",
    0x30: "Card Key",
    0x31: "Nugget",
    0x33: "Poke Doll",
    0x34: "Full Heal",
    0x35: "Revive",
    0x36: "Max Revive",
    0x37: "Guard Spec.",
    0x38: "Super Repel",
    0x39: "Max Repel",
    0x3A: "Dire Hit",
    0x3B: "Coin",
    0x3C: "Fresh Water",
    0x3D: "Soda Pop",
    0x3E: "Lemonade",
    0x3F: "S.S. Ticket",
    0x40: "Gold Teeth",
    0x41: "X Attack",
    0x42: "X Defend",
    0x43: "X Speed",
    0x44: "X Special",
    0x45: "Coin Case",
    0x46: "Oak's Parcel",
    0x47: "Itemfinder",
    0x48: "Silph Scope",
    0x49: "Poke Flute",
    0x4A: "Lift Key",
    0x4B: "Exp. All",
    0x4C: "Old Rod",
    0x4D: "Good Rod",
    0x4E: "Super Rod",
    0x4F: "PP Up",
    0x50: "Ether",
    0x51: "Max Ether",
    0x52: "Elixer",
    0x53: "Max Elixer",
}
HM_ITEM_NAMES = ["Cut", "Fly", "Surf", "Strength", "Flash"]
TM_ITEM_NAMES = [
    "Mega Punch",
    "Razor Wind",
    "Swords Dance",
    "Whirlwind",
    "Mega Kick",
    "Toxic",
    "Horn Drill",
    "Body Slam",
    "Take Down",
    "Double-Edge",
    "Bubblebeam",
    "Water Gun",
    "Ice Beam",
    "Blizzard",
    "Hyper Beam",
    "Pay Day",
    "Submission",
    "Counter",
    "Seismic Toss",
    "Rage",
    "Mega Drain",
    "Solarbeam",
    "Dragon Rage",
    "Thunderbolt",
    "Thunder",
    "Earthquake",
    "Fissure",
    "Dig",
    "Psychic",
    "Teleport",
    "Mimic",
    "Double Team",
    "Reflect",
    "Bide",
    "Metronome",
    "Selfdestruct",
    "Egg Bomb",
    "Fire Blast",
    "Swift",
    "Skull Bash",
    "Softboiled",
    "Dream Eater",
    "Sky Attack",
    "Rest",
    "Thunder Wave",
    "Psywave",
    "Explosion",
    "Rock Slide",
    "Tri Attack",
    "Substitute",
]
WARP_STATE_LABELS = {
    "battle": "battle",
    "blackout": "blackout",
    "evolution": "evolution",
    "item_pickup": "item pickup",
    "level_up": "level up",
    "scene_change": "scene change",
    "trainer_battle": "trainer battle",
    "wild_battle": "wild Pokemon battle",
}
MAX_INTERACTIVE_REWIND_REPLAY_DIGITS = 100_000
MAP_NAMES = {
    0x00: "Pallet Town",
    0x01: "Viridian City",
    0x02: "Pewter City",
    0x03: "Cerulean City",
    0x04: "Lavender Town",
    0x05: "Vermilion City",
    0x06: "Celadon City",
    0x07: "Fuchsia City",
    0x08: "Cinnabar Island",
    0x09: "Indigo Plateau",
    0x0A: "Saffron City",
    0x0C: "Route 1",
    0x0D: "Route 2",
    0x0E: "Route 3",
    0x0F: "Route 4",
    0x10: "Route 5",
    0x11: "Route 6",
    0x12: "Route 7",
    0x13: "Route 8",
    0x14: "Route 9",
    0x15: "Route 10",
    0x16: "Route 11",
    0x17: "Route 12",
    0x18: "Route 13",
    0x19: "Route 14",
    0x1A: "Route 15",
    0x1B: "Route 16",
    0x1C: "Route 17",
    0x1D: "Route 18",
    0x1E: "Route 19",
    0x1F: "Route 20",
    0x20: "Route 21",
    0x21: "Route 22",
    0x22: "Route 23",
    0x23: "Route 24",
    0x24: "Route 25",
    0x25: "Red's House 1F",
    0x26: "Red's House 2F",
    0x27: "Blue's House",
    0x28: "Oak's Lab",
    0x29: "Viridian Pokecenter",
    0x2A: "Viridian Mart",
    0x2B: "Viridian School House",
    0x2C: "Viridian Nickname House",
    0x2D: "Viridian Gym",
    0x2E: "Diglett's Cave Route 2",
    0x2F: "Viridian Forest North Gate",
    0x30: "Route 2 Trade House",
    0x31: "Route 2 Gate",
    0x32: "Viridian Forest South Gate",
    0x33: "Viridian Forest",
    0x34: "Museum 1F",
    0x35: "Museum 2F",
    0x36: "Pewter Gym",
    0x37: "Pewter Nidoran House",
    0x38: "Pewter Mart",
    0x39: "Pewter Speech House",
    0x3A: "Pewter Pokecenter",
    0x3B: "Mt. Moon 1F",
    0x3C: "Mt. Moon B1F",
    0x3D: "Mt. Moon B2F",
    0x3E: "Cerulean Trashed House",
    0x3F: "Cerulean Trade House",
    0x40: "Cerulean Pokecenter",
    0x41: "Cerulean Gym",
    0x42: "Bike Shop",
    0x43: "Cerulean Mart",
    0x44: "Mt. Moon Pokecenter",
    0x45: "Cerulean Trashed House Copy",
    0x46: "Route 5 Gate",
    0x47: "Underground Path Route 5",
    0x48: "Daycare",
    0x49: "Route 6 Gate",
    0x4A: "Underground Path Route 6",
    0x4B: "Underground Path Route 6 Copy",
    0x4C: "Route 7 Gate",
    0x4D: "Underground Path Route 7",
    0x4E: "Underground Path Route 7 Copy",
    0x4F: "Route 8 Gate",
    0x50: "Underground Path Route 8",
    0x51: "Rock Tunnel Pokecenter",
    0x52: "Rock Tunnel 1F",
    0x53: "Power Plant",
    0x54: "Route 11 Gate 1F",
    0x55: "Diglett's Cave Route 11",
    0x56: "Route 11 Gate 2F",
    0x57: "Route 12 Gate 1F",
    0x58: "Bill's House",
    0x59: "Vermilion Pokecenter",
    0x5A: "Pokemon Fan Club",
    0x5B: "Vermilion Mart",
    0x5C: "Vermilion Gym",
    0x5D: "Vermilion Pidgey House",
    0x5E: "Vermilion Dock",
    0x5F: "S.S. Anne 1F",
    0x60: "S.S. Anne 2F",
    0x61: "S.S. Anne 3F",
    0x62: "S.S. Anne B1F",
    0x63: "S.S. Anne Bow",
    0x64: "S.S. Anne Kitchen",
    0x65: "S.S. Anne Captain's Room",
    0x66: "S.S. Anne 1F Rooms",
    0x67: "S.S. Anne 2F Rooms",
    0x68: "S.S. Anne B1F Rooms",
    0x6C: "Victory Road 1F",
    0x71: "Lance's Room",
    0x76: "Hall Of Fame",
    0x77: "Underground Path North South",
    0x78: "Champion's Room",
    0x79: "Underground Path West East",
    0x7A: "Celadon Mart 1F",
    0x7B: "Celadon Mart 2F",
    0x7C: "Celadon Mart 3F",
    0x7D: "Celadon Mart 4F",
    0x7E: "Celadon Mart Roof",
    0x7F: "Celadon Mart Elevator",
    0x80: "Celadon Mansion 1F",
    0x81: "Celadon Mansion 2F",
    0x82: "Celadon Mansion 3F",
    0x83: "Celadon Mansion Roof",
    0x84: "Celadon Mansion Roof House",
    0x85: "Celadon Pokecenter",
    0x86: "Celadon Gym",
    0x87: "Game Corner",
    0x88: "Celadon Mart 5F",
    0x89: "Game Corner Prize Room",
    0x8A: "Celadon Diner",
    0x8B: "Celadon Chief House",
    0x8C: "Celadon Hotel",
    0x8D: "Lavender Pokecenter",
    0x8E: "Pokemon Tower 1F",
    0x8F: "Pokemon Tower 2F",
    0x90: "Pokemon Tower 3F",
    0x91: "Pokemon Tower 4F",
    0x92: "Pokemon Tower 5F",
    0x93: "Pokemon Tower 6F",
    0x94: "Pokemon Tower 7F",
    0x95: "Mr. Fuji's House",
    0x96: "Lavender Mart",
    0x97: "Lavender Cubone House",
    0x98: "Fuchsia Mart",
    0x99: "Fuchsia Bill's Grandpa's House",
    0x9A: "Fuchsia Pokecenter",
    0x9B: "Warden's House",
    0x9C: "Safari Zone Gate",
    0x9D: "Fuchsia Gym",
    0x9E: "Fuchsia Meeting Room",
    0x9F: "Seafoam Islands B1F",
    0xA0: "Seafoam Islands B2F",
    0xA1: "Seafoam Islands B3F",
    0xA2: "Seafoam Islands B4F",
    0xA3: "Vermilion Old Rod House",
    0xA4: "Fuchsia Good Rod House",
    0xA5: "Pokemon Mansion 1F",
    0xA6: "Cinnabar Gym",
    0xA7: "Cinnabar Lab",
    0xA8: "Cinnabar Lab Trade Room",
    0xA9: "Cinnabar Lab Metronome Room",
    0xAA: "Cinnabar Lab Fossil Room",
    0xAB: "Cinnabar Pokecenter",
    0xAC: "Cinnabar Mart",
    0xAD: "Cinnabar Mart Copy",
    0xAE: "Indigo Plateau Lobby",
    0xAF: "Copycat's House 1F",
    0xB0: "Copycat's House 2F",
    0xB1: "Fighting Dojo",
    0xB2: "Saffron Gym",
    0xB3: "Saffron Pidgey House",
    0xB4: "Saffron Mart",
    0xB5: "Silph Co. 1F",
    0xB6: "Saffron Pokecenter",
    0xB7: "Mr. Psychic's House",
    0xB8: "Route 15 Gate 1F",
    0xB9: "Route 15 Gate 2F",
    0xBA: "Route 16 Gate 1F",
    0xBB: "Route 16 Gate 2F",
    0xBC: "Route 16 Fly House",
    0xBD: "Route 12 Super Rod House",
    0xBE: "Route 18 Gate 1F",
    0xBF: "Route 18 Gate 2F",
    0xC0: "Seafoam Islands 1F",
    0xC1: "Route 22 Gate",
    0xC2: "Victory Road 2F",
    0xC3: "Route 12 Gate 2F",
    0xC4: "Vermilion Trade House",
    0xC5: "Diglett's Cave",
    0xC6: "Victory Road 3F",
    0xC7: "Rocket Hideout B1F",
    0xC8: "Rocket Hideout B2F",
    0xC9: "Rocket Hideout B3F",
    0xCA: "Rocket Hideout B4F",
    0xCB: "Rocket Hideout Elevator",
    0xCF: "Silph Co. 2F",
    0xD0: "Silph Co. 3F",
    0xD1: "Silph Co. 4F",
    0xD2: "Silph Co. 5F",
    0xD3: "Silph Co. 6F",
    0xD4: "Silph Co. 7F",
    0xD5: "Silph Co. 8F",
    0xD6: "Pokemon Mansion 2F",
    0xD7: "Pokemon Mansion 3F",
    0xD8: "Pokemon Mansion B1F",
    0xD9: "Safari Zone East",
    0xDA: "Safari Zone North",
    0xDB: "Safari Zone West",
    0xDC: "Safari Zone Center",
    0xDD: "Safari Zone Center Rest House",
    0xDE: "Safari Zone Secret House",
    0xDF: "Safari Zone West Rest House",
    0xE0: "Safari Zone East Rest House",
    0xE1: "Safari Zone North Rest House",
    0xE2: "Cerulean Cave 2F",
    0xE3: "Cerulean Cave B1F",
    0xE4: "Cerulean Cave 1F",
    0xE5: "Name Rater's House",
    0xE6: "Cerulean Badge House",
    0xE8: "Rock Tunnel B1F",
    0xE9: "Silph Co. 9F",
    0xEA: "Silph Co. 10F",
    0xEB: "Silph Co. 11F",
    0xEC: "Silph Co. Elevator",
    0xEF: "Trade Center",
    0xF0: "Colosseum",
    0xF5: "Lorelei's Room",
    0xF6: "Bruno's Room",
    0xF7: "Agatha's Room",
}
MAP_CONTEXTS = {
    0x25: "Pallet Town",
    0x26: "Pallet Town",
    0x27: "Pallet Town",
    0x28: "Pallet Town",
    0x29: "Viridian City",
    0x2A: "Viridian City",
    0x2B: "Viridian City",
    0x2C: "Viridian City",
    0x2D: "Viridian City",
    0x2E: "Route 2",
    0x2F: "Viridian Forest",
    0x30: "Route 2",
    0x31: "Route 2",
    0x32: "Viridian Forest",
    0x34: "Pewter City",
    0x35: "Pewter City",
    0x36: "Pewter City",
    0x37: "Pewter City",
    0x38: "Pewter City",
    0x39: "Pewter City",
    0x3A: "Pewter City",
    0x3E: "Cerulean City",
    0x3F: "Cerulean City",
    0x40: "Cerulean City",
    0x41: "Cerulean City",
    0x42: "Cerulean City",
    0x43: "Cerulean City",
    0x44: "Route 4",
    0x45: "Cerulean City",
    0x46: "Route 5",
    0x47: "Route 5",
    0x48: "Route 5",
    0x49: "Route 6",
    0x4A: "Route 6",
    0x4B: "Route 6",
    0x4C: "Route 7",
    0x4D: "Route 7",
    0x4E: "Route 7",
    0x4F: "Route 8",
    0x50: "Route 8",
    0x51: "Route 10",
    0x58: "Route 25",
    0x59: "Vermilion City",
    0x5A: "Vermilion City",
    0x5B: "Vermilion City",
    0x5C: "Vermilion City",
    0x5D: "Vermilion City",
    0x5E: "Vermilion City",
    0x5F: "S.S. Anne",
    0x60: "S.S. Anne",
    0x61: "S.S. Anne",
    0x62: "S.S. Anne",
    0x63: "S.S. Anne",
    0x64: "S.S. Anne",
    0x65: "S.S. Anne",
    0x66: "S.S. Anne",
    0x67: "S.S. Anne",
    0x68: "S.S. Anne",
    0x7A: "Celadon City",
    0x7B: "Celadon City",
    0x7C: "Celadon City",
    0x7D: "Celadon City",
    0x7E: "Celadon City",
    0x7F: "Celadon City",
    0x80: "Celadon City",
    0x81: "Celadon City",
    0x82: "Celadon City",
    0x83: "Celadon City",
    0x84: "Celadon City",
    0x85: "Celadon City",
    0x86: "Celadon City",
    0x87: "Celadon City",
    0x88: "Celadon City",
    0x89: "Celadon City",
    0x8A: "Celadon City",
    0x8B: "Celadon City",
    0x8C: "Celadon City",
    0x8D: "Lavender Town",
    0x8E: "Lavender Town",
    0x8F: "Lavender Town",
    0x90: "Lavender Town",
    0x91: "Lavender Town",
    0x92: "Lavender Town",
    0x93: "Lavender Town",
    0x94: "Lavender Town",
    0x95: "Lavender Town",
    0x96: "Lavender Town",
    0x97: "Lavender Town",
    0x98: "Fuchsia City",
    0x99: "Fuchsia City",
    0x9A: "Fuchsia City",
    0x9B: "Fuchsia City",
    0x9C: "Fuchsia City",
    0x9D: "Fuchsia City",
    0x9E: "Fuchsia City",
    0xA3: "Vermilion City",
    0xA4: "Fuchsia City",
    0xA5: "Cinnabar Island",
    0xA6: "Cinnabar Island",
    0xA7: "Cinnabar Island",
    0xA8: "Cinnabar Island",
    0xA9: "Cinnabar Island",
    0xAA: "Cinnabar Island",
    0xAB: "Cinnabar Island",
    0xAC: "Cinnabar Island",
    0xAD: "Cinnabar Island",
    0xAE: "Indigo Plateau",
    0xAF: "Saffron City",
    0xB0: "Saffron City",
    0xB1: "Saffron City",
    0xB2: "Saffron City",
    0xB3: "Saffron City",
    0xB4: "Saffron City",
    0xB5: "Saffron City",
    0xB6: "Saffron City",
    0xB7: "Saffron City",
    0xB8: "Route 15",
    0xB9: "Route 15",
    0xBA: "Route 16",
    0xBB: "Route 16",
    0xBC: "Route 16",
    0xBD: "Route 12",
    0xBE: "Route 18",
    0xBF: "Route 18",
    0xC1: "Route 22",
    0xC3: "Route 12",
    0xC4: "Vermilion City",
    0xC7: "Celadon City",
    0xC8: "Celadon City",
    0xC9: "Celadon City",
    0xCA: "Celadon City",
    0xCB: "Celadon City",
    0xCF: "Saffron City",
    0xD0: "Saffron City",
    0xD1: "Saffron City",
    0xD2: "Saffron City",
    0xD3: "Saffron City",
    0xD4: "Saffron City",
    0xD5: "Saffron City",
    0xD6: "Cinnabar Island",
    0xD7: "Cinnabar Island",
    0xD8: "Cinnabar Island",
    0xDD: "Safari Zone",
    0xDE: "Safari Zone",
    0xDF: "Safari Zone",
    0xE0: "Safari Zone",
    0xE1: "Safari Zone",
    0xE5: "Lavender Town",
    0xE6: "Cerulean City",
    0xE9: "Saffron City",
    0xEA: "Saffron City",
    0xEB: "Saffron City",
    0xEC: "Saffron City",
    0xF5: "Indigo Plateau",
    0xF6: "Indigo Plateau",
    0xF7: "Indigo Plateau",
}
MOVE_NAMES = [
    "-",
    "Pound",
    "Karate Chop",
    "Double Slap",
    "Comet Punch",
    "Mega Punch",
    "Pay Day",
    "Fire Punch",
    "Ice Punch",
    "Thunder Punch",
    "Scratch",
    "Vice Grip",
    "Guillotine",
    "Razor Wind",
    "Swords Dance",
    "Cut",
    "Gust",
    "Wing Attack",
    "Whirlwind",
    "Fly",
    "Bind",
    "Slam",
    "Vine Whip",
    "Stomp",
    "Double Kick",
    "Mega Kick",
    "Jump Kick",
    "Rolling Kick",
    "Sand Attack",
    "Headbutt",
    "Horn Attack",
    "Fury Attack",
    "Horn Drill",
    "Tackle",
    "Body Slam",
    "Wrap",
    "Take Down",
    "Thrash",
    "Double-Edge",
    "Tail Whip",
    "Poison Sting",
    "Twineedle",
    "Pin Missile",
    "Leer",
    "Bite",
    "Growl",
    "Roar",
    "Sing",
    "Supersonic",
    "Sonic Boom",
    "Disable",
    "Acid",
    "Ember",
    "Flamethrower",
    "Mist",
    "Water Gun",
    "Hydro Pump",
    "Surf",
    "Ice Beam",
    "Blizzard",
    "Psybeam",
    "Bubble Beam",
    "Aurora Beam",
    "Hyper Beam",
    "Peck",
    "Drill Peck",
    "Submission",
    "Low Kick",
    "Counter",
    "Seismic Toss",
    "Strength",
    "Absorb",
    "Mega Drain",
    "Leech Seed",
    "Growth",
    "Razor Leaf",
    "Solar Beam",
    "Poison Powder",
    "Stun Spore",
    "Sleep Powder",
    "Petal Dance",
    "String Shot",
    "Dragon Rage",
    "Fire Spin",
    "Thunder Shock",
    "Thunderbolt",
    "Thunder Wave",
    "Thunder",
    "Rock Throw",
    "Earthquake",
    "Fissure",
    "Dig",
    "Toxic",
    "Confusion",
    "Psychic",
    "Hypnosis",
    "Meditate",
    "Agility",
    "Quick Attack",
    "Rage",
    "Teleport",
    "Night Shade",
    "Mimic",
    "Screech",
    "Double Team",
    "Recover",
    "Harden",
    "Minimize",
    "Smokescreen",
    "Confuse Ray",
    "Withdraw",
    "Defense Curl",
    "Barrier",
    "Light Screen",
    "Haze",
    "Reflect",
    "Focus Energy",
    "Bide",
    "Metronome",
    "Mirror Move",
    "Self-Destruct",
    "Egg Bomb",
    "Lick",
    "Smog",
    "Sludge",
    "Bone Club",
    "Fire Blast",
    "Waterfall",
    "Clamp",
    "Swift",
    "Skull Bash",
    "Spike Cannon",
    "Constrict",
    "Amnesia",
    "Kinesis",
    "Soft-Boiled",
    "High Jump Kick",
    "Glare",
    "Dream Eater",
    "Poison Gas",
    "Barrage",
    "Leech Life",
    "Lovely Kiss",
    "Sky Attack",
    "Transform",
    "Bubble",
    "Dizzy Punch",
    "Spore",
    "Flash",
    "Psywave",
    "Splash",
    "Acid Armor",
    "Crabhammer",
    "Explosion",
    "Fury Swipes",
    "Bonemerang",
    "Rest",
    "Rock Slide",
    "Hyper Fang",
    "Sharpen",
    "Conversion",
    "Tri Attack",
    "Super Fang",
    "Slash",
    "Substitute",
    "Struggle",
]
MOVE_BASE_PP = [
    0,
    35,
    25,
    10,
    15,
    20,
    20,
    15,
    15,
    15,
    35,
    30,
    5,
    10,
    30,
    30,
    35,
    35,
    20,
    15,
    20,
    20,
    10,
    20,
    30,
    5,
    25,
    15,
    15,
    15,
    25,
    20,
    5,
    35,
    15,
    20,
    20,
    20,
    15,
    30,
    35,
    20,
    20,
    30,
    25,
    40,
    20,
    15,
    20,
    20,
    20,
    30,
    25,
    15,
    30,
    25,
    5,
    15,
    10,
    5,
    20,
    20,
    20,
    5,
    35,
    20,
    20,
    30,
    10,
    20,
    15,
    20,
    10,
    10,
    40,
    30,
    10,
    35,
    30,
    15,
    20,
    40,
    10,
    15,
    30,
    15,
    20,
    10,
    10,
    20,
    10,
    10,
    15,
    10,
    30,
    10,
    20,
    40,
    30,
    30,
    20,
    20,
    15,
    10,
    40,
    15,
    10,
    20,
    30,
    30,
    20,
    15,
    10,
    20,
    30,
    10,
    10,
    40,
    10,
    10,
    10,
    15,
    20,
    20,
    20,
    5,
    15,
    35,
    20,
    15,
    10,
    30,
    15,
    10,
    40,
    20,
    30,
    10,
    15,
    10,
    20,
    15,
    10,
    5,
    10,
    30,
    10,
    15,
    20,
    15,
    40,
    20,
    15,
    10,
    5,
    15,
    10,
    10,
    10,
    15,
    30,
    30,
    10,
    10,
    20,
    20,
    10,
    1,
]
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
        self.max_queued_bytes = max(4096, int(sample_rate * 2 * 0.18))
        self._audio_chunk_credit = 0.0
        if sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_AUDIO) != 0:
            return

        want = sdl2.SDL_AudioSpec(sample_rate, sdl2.AUDIO_S8, 2, 128)
        have = sdl2.SDL_AudioSpec(0, 0, 0, 0)
        self.device = sdl2.SDL_OpenAudioDevice(None, 0, want, have, 0)
        if self.device:
            sdl2.SDL_PauseAudioDevice(self.device, 0)

    def queue(self, pyboy: PyBoy, volume: int, playback_speed: float = 1.0) -> None:
        if not self.device:
            return

        if volume <= 0:
            self.clear()
            return

        head = pyboy.sound.raw_buffer_head
        if head <= 0:
            return

        data = self._sync_playback_speed(bytes(pyboy.sound.raw_buffer[:head]), playback_speed)
        if not data:
            return
        if volume < 100:
            scale = max(0, min(100, volume)) / 100
            data = bytes(max(-128, min(127, int(int.from_bytes(bytes([sample]), "little", signed=True) * scale))) & 0xFF for sample in data)
        if sdl2.SDL_GetQueuedAudioSize(self.device) > self.max_queued_bytes:
            sdl2.SDL_ClearQueuedAudio(self.device)
        sdl2.SDL_QueueAudio(self.device, data, len(data))

    def clear(self) -> None:
        if self.device:
            sdl2.SDL_ClearQueuedAudio(self.device)

    def _sync_playback_speed(self, data: bytes, playback_speed: float) -> bytes:
        speed = max(0.1, min(1000.0, float(playback_speed or 1.0)))
        if 0.995 <= speed <= 1.005:
            self._audio_chunk_credit = 0.0
            return data

        self._audio_chunk_credit += 1 / speed
        chunk_count = int(self._audio_chunk_credit)
        if chunk_count <= 0:
            return b""
        self._audio_chunk_credit -= chunk_count
        return data * min(chunk_count, 12)

    def close(self) -> None:
        if self.device:
            sdl2.SDL_CloseAudioDevice(self.device)
            self.device = 0


POKEMON_TEXT_CHARS = {
    0x4A: "ᴾᴷᴹᴺ",
    0x54: "POKé",
    0x56: "……",
    0x5B: "PC",
    0x5C: "TM",
    0x5D: "TRAINER",
    0x5E: "ROCKET",
    0x5F: ".",
    0x6D: ":",
    0x70: "‘",
    0x71: "’",
    0x72: "“",
    0x73: "”",
    0x74: "・",
    0x75: "…",
    0x79: "╔",
    0x7A: "═",
    0x7B: "╗",
    0x7C: "║",
    0x7D: "╚",
    0x7E: "╝",
    0x7F: " ",
    0x9A: "(",
    0x9B: ")",
    0x9C: ":",
    0x9D: ";",
    0x9E: "[",
    0x9F: "]",
    0xBA: "é",
    0xBB: "'d",
    0xBC: "'l",
    0xBD: "'s",
    0xBE: "'t",
    0xBF: "'v",
    0xE0: "'",
    0xE1: "ᴾᴷ",
    0xE2: "ᴹᴺ",
    0xE3: "-",
    0xE4: "'r",
    0xE5: "'m",
    0xE6: "?",
    0xE7: "!",
    0xE8: ".",
    0xEC: "▷",
    0xED: "▶",
    0xEE: "▼",
    0xEF: "♂",
    0xF1: "×",
    0xF2: ".",
    0xF3: "/",
    0xF4: ",",
    0xF5: "♀",
}


def decode_pokemon_text(values: list[int]) -> str:
    chars: list[str] = []
    for value in values:
        if value == 0x50:
            break
        if 0x80 <= value <= 0x99:
            chars.append(chr(ord("A") + value - 0x80))
        elif 0xA0 <= value <= 0xB9:
            chars.append(chr(ord("a") + value - 0xA0))
        elif 0xF6 <= value <= 0xFF:
            chars.append(chr(ord("0") + value - 0xF6))
        elif value in POKEMON_TEXT_CHARS:
            chars.append(POKEMON_TEXT_CHARS[value])
    return "".join(chars).strip()


def read_u16_be(pyboy: PyBoy, address: int) -> int:
    return (int(pyboy.memory[address]) << 8) | int(pyboy.memory[address + 1])


def read_bcd_money(pyboy: PyBoy) -> int:
    value = 0
    for offset in range(3):
        byte = int(pyboy.memory[PLAYER_MONEY_ADDR + offset])
        value = (value * 100) + (((byte >> 4) & 0x0F) * 10) + (byte & 0x0F)
    return value


def count_pokedex_flags(pyboy: PyBoy, start_address: int) -> int:
    count = 0
    bits_seen = 0
    for offset in range(POKEDEX_FLAG_BYTES):
        byte = int(pyboy.memory[start_address + offset])
        for bit in range(8):
            if bits_seen >= NUM_POKEMON:
                return count
            if byte & (1 << bit):
                count += 1
            bits_seen += 1
    return count


def play_time(pyboy: PyBoy) -> dict[str, int]:
    return {
        "hours": int(pyboy.memory[PLAY_TIME_HOURS_ADDR + 1]),
        "minutes": int(pyboy.memory[PLAY_TIME_MINUTES_ADDR + 1]),
        "seconds": int(pyboy.memory[PLAY_TIME_SECONDS_ADDR]),
    }


def elapsed_play_time(frames_elapsed: int) -> dict[str, int]:
    total_seconds = max(0, int(frames_elapsed / GAMEBOY_FPS))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return {
        "hours": hours,
        "minutes": minutes,
        "seconds": seconds,
        "total_seconds": total_seconds,
    }


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


def is_in_trainer_battle(pyboy: PyBoy) -> bool:
    return int(pyboy.memory[BATTLE_FLAG_ADDR]) == BATTLE_TRAINER_VALUE


def is_in_wild_battle(pyboy: PyBoy) -> bool:
    battle_flag = int(pyboy.memory[BATTLE_FLAG_ADDR])
    return battle_flag != 0 and battle_flag != BATTLE_TRAINER_VALUE


def current_map_id(pyboy: PyBoy) -> int:
    return int(pyboy.memory[CURRENT_MAP_ADDR])


def current_player_tile(pyboy: PyBoy) -> dict[str, int]:
    return {
        "map_id": current_map_id(pyboy),
        "x": int(pyboy.memory[PLAYER_X_ADDR]),
        "y": int(pyboy.memory[PLAYER_Y_ADDR]),
    }


def map_name(map_id: int) -> str:
    name = MAP_NAMES.get(map_id, f"Map ${map_id:02X}")
    context = MAP_CONTEXTS.get(map_id)
    if context is None:
        return name

    for prefix in context.removesuffix(" City").removesuffix(" Town").removesuffix(" Island"), context:
        if name.startswith(f"{prefix} "):
            name = name[len(prefix) + 1 :]
            break
    return f"{context} | {name}"


def progression_state(pyboy: PyBoy) -> dict[str, object]:
    return {
        "label": "Progression route data pending",
        "objective_location": "",
        "current_tile": current_player_tile(pyboy),
        "remaining_steps": None,
        "total_steps_from_respawn": None,
        "graph_max_steps": None,
        "reachable": False,
    }


def move_name(move_id: int) -> str:
    if 0 <= move_id < len(MOVE_NAMES):
        return MOVE_NAMES[move_id]
    return f"Move {move_id:03d}"


def item_name(item_id: int) -> str:
    if item_id in ITEM_NAMES:
        return ITEM_NAMES[item_id]
    if 0xC4 <= item_id < 0xC4 + len(HM_ITEM_NAMES):
        return f"HM{item_id - 0xC3:02d} {HM_ITEM_NAMES[item_id - 0xC4]}"
    if 0xC9 <= item_id < 0xC9 + len(TM_ITEM_NAMES):
        return f"TM{item_id - 0xC8:02d} {TM_ITEM_NAMES[item_id - 0xC9]}"
    return f"Item ${item_id:02X}"


def move_max_pp(move_id: int, pp_byte: int) -> int:
    if 0 <= move_id < len(MOVE_BASE_PP):
        base_pp = MOVE_BASE_PP[move_id]
    else:
        base_pp = pp_byte & 0x3F
    pp_ups = (pp_byte & 0xC0) >> 6
    return base_pp + ((base_pp * pp_ups) // 5)


def is_party_blackout(pyboy: PyBoy) -> bool:
    count = int(pyboy.memory[PARTY_COUNT_ADDR])
    if count <= 0 or count > PARTY_SIZE:
        return False
    for index in range(count):
        mon_addr = PARTY_MONS_ADDR + (index * PARTY_MON_SIZE)
        if read_u16_be(pyboy, mon_addr + 1) > 0:
            return False
    return True


def party_levels(pyboy: PyBoy) -> tuple[int, ...]:
    count = int(pyboy.memory[PARTY_COUNT_ADDR])
    if count <= 0 or count > PARTY_SIZE:
        return ()
    return tuple(int(pyboy.memory[PARTY_MONS_ADDR + (index * PARTY_MON_SIZE) + 33]) for index in range(count))


def has_party_level_up(pyboy: PyBoy, starting_levels: tuple[int, ...]) -> bool:
    levels = party_levels(pyboy)
    return any(level > starting_levels[index] for index, level in enumerate(levels[: len(starting_levels)]))


def party_species(pyboy: PyBoy) -> tuple[int, ...]:
    count = int(pyboy.memory[PARTY_COUNT_ADDR])
    if count <= 0 or count > PARTY_SIZE:
        return ()
    return tuple(int(pyboy.memory[PARTY_SPECIES_ADDR + index]) for index in range(count))


def has_party_evolution(pyboy: PyBoy, starting_species: tuple[int, ...]) -> bool:
    species = party_species(pyboy)
    return any(value != starting_species[index] for index, value in enumerate(species[: len(starting_species)]))


def evolution_marker(pyboy: PyBoy) -> tuple[int, int, int]:
    return (
        int(pyboy.memory[EVOLUTION_OCCURRED_ADDR]),
        int(pyboy.memory[EVO_OLD_SPECIES_ADDR]),
        int(pyboy.memory[EVO_NEW_SPECIES_ADDR]),
    )


def is_evolution_active(pyboy: PyBoy) -> bool:
    occurred, old_species, new_species = evolution_marker(pyboy)
    return occurred != 0 or (old_species != 0 and new_species != 0 and old_species != new_species)


def has_evolution_started(pyboy: PyBoy, starting_marker: tuple[int, int, int], starting_species: tuple[int, ...]) -> bool:
    return (evolution_marker(pyboy) != starting_marker and is_evolution_active(pyboy)) or has_party_evolution(
        pyboy,
        starting_species,
    )


def bag_quantities(pyboy: PyBoy) -> dict[int, int]:
    count = max(0, min(BAG_CAPACITY, int(pyboy.memory[BAG_COUNT_ADDR])))
    items: dict[int, int] = {}
    for index in range(count):
        item_id = int(pyboy.memory[BAG_ITEMS_ADDR + (index * 2)])
        quantity = int(pyboy.memory[BAG_ITEMS_ADDR + (index * 2) + 1])
        if item_id in {0x00, 0xFF}:
            break
        items[item_id] = items.get(item_id, 0) + quantity
    return items


def has_bag_item_gain(pyboy: PyBoy, starting_items: dict[int, int]) -> bool:
    current_items = bag_quantities(pyboy)
    return any(quantity > starting_items.get(item_id, 0) for item_id, quantity in current_items.items())


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
        self.current_input_frame = 0
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
        self._simulate_checkpoint_interval_digits = 1_000_000
        self._jump_target_digits: int | None = None
        self._warp_target_state: str | None = None
        self._warp_limit_digits = 1_000_000
        self._simulation_started_at: float | None = None
        self._last_simulation: dict[str, int | float | str] | None = None
        self._auto_snapshots_enabled = True
        self._last_snapshot_digits = digits_consumed - rewind_interval_digits
        self._actual_speed_x = 0.0
        self._speed_sample_started_at = time.perf_counter()
        self._speed_sample_frames = 0
        self._seek_active = False
        self._seek_label = ""
        self._seek_start_digits = digits_consumed
        self._seek_current_digits = digits_consumed
        self._seek_target_digits = digits_consumed
        self._take_snapshot()
        if self.latest_image is None:
            self._capture_frame()

    def set_speed(self, speed: float) -> None:
        with self._lock:
            requested_speed = max(0.1, min(1000, float(speed)))
            self.speed = requested_speed if requested_speed < 1 else round(requested_speed)
            if (
                self._fast_forward_target_digits is None
                and self._simulate_target_digits is None
                and self._jump_target_digits is None
                and self._warp_target_state is None
            ):
                self._restore_playback_speed_unlocked()

    def set_speed_limiter_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.speed_limiter_enabled = enabled
            if (
                self._fast_forward_target_digits is None
                and self._simulate_target_digits is None
                and self._jump_target_digits is None
                and self._warp_target_state is None
            ):
                self._restore_playback_speed_unlocked()
            else:
                self._next_frame_time = time.perf_counter()

    def set_sound_volume(self, volume: int) -> None:
        with self._lock:
            self.sound_volume = max(0, min(100, int(volume)))
            audio_sink = self.audio_sink
        if audio_sink:
            audio_sink.clear()

    def set_max_digits(self, max_digits: int) -> None:
        with self._lock:
            if self._simulate_target_digits is not None:
                return
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
                self._restore_playback_speed_unlocked()
                self.status = "pause pending"

    def request_rewind(self, digits: int) -> None:
        digits = self._normalize_digit_distance(digits)
        with self._lock:
            target = max(0, self.digits_consumed - digits)
            if target % self.input_config.digits_per_input:
                target -= target % self.input_config.digits_per_input
            self._rewind_digits_requested = max(self._rewind_digits_requested, digits)
            self._fast_forward_target_digits = None
            self._simulate_target_digits = None
            self._jump_target_digits = None
            self._warp_target_state = None
            self.pause_requested = False
            self._set_seek_emulation_speed_unlocked()
            self.status = f"rewinding {digits:,} digits"
            self._begin_seek_unlocked("Rewinding", self.digits_consumed, target)

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
            self._set_seek_emulation_speed_unlocked()
            self.paused = False
            self.pause_requested = False
            self.status = f"fast forwarding to {target:,} digits"
            self._begin_seek_unlocked("Fast-forwarding", self.digits_consumed, target)

    def request_simulate(self, target_digits: int, checkpoint_interval_digits: int = 1_000_000) -> int:
        target = max(0, min(len(self.digits), int(target_digits)))
        if target % self.input_config.digits_per_input:
            target -= target % self.input_config.digits_per_input
        checkpoint_interval_digits = self._normalize_digit_distance(checkpoint_interval_digits)
        with self._lock:
            if self._simulate_target_digits is not None:
                return self._simulate_target_digits
            if target <= self.digits_consumed:
                self.status = "complete" if self.digits_consumed >= self.max_digits else "paused"
                return self.digits_consumed
            self._simulate_target_digits = target
            self._simulate_checkpoint_interval_digits = checkpoint_interval_digits
            self.max_digits = max(self.max_digits, target)
            self._simulation_started_at = time.perf_counter()
            self._fast_forward_target_digits = None
            self._jump_target_digits = None
            self._warp_target_state = None
            self.paused = False
            self.pause_requested = False
            self._set_seek_emulation_speed_unlocked()
            self.status = f"simulating to {target:,} digits"
            self._begin_seek_unlocked("Simulating", self.digits_consumed, target)
        return target

    def request_jump(self, digits: int) -> int:
        target = max(0, min(len(self.digits), int(digits)))
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
            self._set_seek_emulation_speed_unlocked()
            self.status = f"jumping to {target:,} digits"
            self._begin_seek_unlocked("Jumping", self.digits_consumed, target)
        return target

    def request_warp_state(self, target_state: str, limit_digits: int = 1_000_000) -> str:
        target_state = target_state.lower().strip()
        if target_state not in WARP_STATE_LABELS:
            raise ValueError(f"Unsupported warp state: {target_state}")
        label = WARP_STATE_LABELS[target_state]
        limit_digits = self._normalize_digit_distance(limit_digits)
        with self._lock:
            self._warp_target_state = target_state
            self._warp_limit_digits = limit_digits
            self._rewind_digits_requested = 0
            self._fast_forward_target_digits = None
            self._simulate_target_digits = None
            self._jump_target_digits = None
            self.paused = False
            self.pause_requested = False
            self._set_seek_emulation_speed_unlocked()
            self.status = f"finding next {label} within {limit_digits:,} digits"
            self._begin_seek_unlocked(f"Finding next {label}", self.digits_consumed, self.digits_consumed + limit_digits)
        return target_state

    def _set_seek_emulation_speed_unlocked(self) -> None:
        self.pyboy.set_emulation_speed(0)

    def _restore_playback_speed_unlocked(self) -> None:
        self.pyboy.set_emulation_speed(self.speed if self.speed_limiter_enabled else 0)
        self._next_frame_time = time.perf_counter()

    def stop(self) -> None:
        with self._lock:
            self.running = False

    def info(self) -> dict[str, int | float | str]:
        with self._lock:
            map_id = current_map_id(self.pyboy)
            return {
                "digits_consumed": self.digits_consumed,
                "max_digits": self.max_digits,
                "frames_elapsed": self.frames_elapsed,
                "frames_per_input": self.frames_per_input,
                "current_input_frame": self.current_input_frame,
                "map_id": map_id,
                "location": map_name(map_id),
                "progression": progression_state(self.pyboy),
                "speed": self.speed,
                "actual_speed_x": round(self._actual_speed_x, 1),
                "actual_digits_per_second": self._actual_speed_x
                * GAMEBOY_FPS
                * self.input_config.digits_per_input
                / self.frames_per_input,
                "speed_limiter_enabled": "on" if self.speed_limiter_enabled else "off",
                "sound_volume": self.sound_volume,
                "status": self.status,
                "snapshots": len(self.snapshots),
                "inputs_sent": self.inputs_sent,
                "last_button": self.last_button,
                "last_simulation": self._last_simulation or {},
                "seek": self._seek_info_unlocked(),
            }

    def _begin_seek_unlocked(self, label: str, start_digits: int, target_digits: int) -> None:
        self._seek_active = True
        self._seek_label = label
        self._seek_start_digits = int(start_digits)
        self._seek_current_digits = int(start_digits)
        self._seek_target_digits = int(target_digits)

    def _update_seek(self, current_digits: int) -> None:
        with self._lock:
            if self._seek_active:
                self._seek_current_digits = int(current_digits)

    def _end_seek_unlocked(self) -> None:
        self._seek_active = False
        self._seek_current_digits = self.digits_consumed
        self._seek_target_digits = self.digits_consumed

    def _seek_info_unlocked(self) -> dict[str, bool | int | float | str]:
        distance = self._seek_target_digits - self._seek_start_digits
        if distance:
            progress = ((self._seek_current_digits - self._seek_start_digits) / distance) * 100
        else:
            progress = 100 if self._seek_active else 0
        return {
            "active": self._seek_active,
            "label": self._seek_label,
            "start_digits": self._seek_start_digits,
            "current_digits": self._seek_current_digits,
            "target_digits": self._seek_target_digits,
            "progress": max(0.0, min(100.0, progress)),
        }

    def party(self) -> list[dict[str, object]]:
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
                moves = []
                for move_index in range(4):
                    move_id = int(self.pyboy.memory[mon_addr + 8 + move_index])
                    pp_byte = int(self.pyboy.memory[mon_addr + 29 + move_index])
                    if move_id == 0:
                        continue
                    moves.append(
                        {
                            "slot": move_index + 1,
                            "id": move_id,
                            "name": move_name(move_id),
                            "pp": pp_byte & 0x3F,
                            "max_pp": move_max_pp(move_id, pp_byte),
                        }
                    )
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
                        "moves": moves,
                    }
                )
            return members

    def badges(self) -> list[dict[str, object]]:
        with self._lock:
            mask = int(self.pyboy.memory[OBTAINED_BADGES_ADDR])
        return [
            {
                "slot": index + 1,
                "name": name,
                "earned": bool(mask & (1 << index)),
            }
            for index, name in enumerate(BADGE_NAMES)
        ]

    def player_info(self) -> dict[str, object]:
        with self._lock:
            return {
                "money": read_bcd_money(self.pyboy),
                "pokedex_seen": count_pokedex_flags(self.pyboy, POKEDEX_SEEN_ADDR),
                "pokedex_caught": count_pokedex_flags(self.pyboy, POKEDEX_OWNED_ADDR),
                "pokedex_total": NUM_POKEMON,
                "time": elapsed_play_time(self.frames_elapsed),
            }

    def bag(self) -> list[dict[str, int | str]]:
        with self._lock:
            count = max(0, min(BAG_CAPACITY, int(self.pyboy.memory[BAG_COUNT_ADDR])))
            items: list[dict[str, int | str]] = []
            for index in range(count):
                item_id = int(self.pyboy.memory[BAG_ITEMS_ADDR + (index * 2)])
                quantity = int(self.pyboy.memory[BAG_ITEMS_ADDR + (index * 2) + 1])
                if item_id in {0x00, 0xFF}:
                    break
                items.append(
                    {
                        "slot": index + 1,
                        "id": item_id,
                        "name": item_name(item_id),
                        "quantity": quantity,
                    }
                )
        return items

    def run(self) -> None:
        self._restore_playback_speed_unlocked()
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
                    simulate_checkpoint_interval = self._simulate_checkpoint_interval_digits
                    jump_target = self._jump_target_digits
                    warp_target_state = self._warp_target_state
                    warp_limit_digits = self._warp_limit_digits

                if rewind_digits:
                    self._rewind(rewind_digits)
                    continue

                if jump_target is not None:
                    self._jump_to(jump_target)
                    continue

                if warp_target_state is not None:
                    self._find_next_warp_state_with_backend(warp_target_state, warp_limit_digits)
                    continue

                if paused or pause_requested:
                    with self._lock:
                        if pause_requested:
                            self.paused = True
                            self.pause_requested = False
                            self.status = "paused"
                        self._actual_speed_x = 0.0
                        self._speed_sample_started_at = time.perf_counter()
                        self._speed_sample_frames = 0
                    time.sleep(1 / 30)
                    continue

                if self.digits_consumed >= self.max_digits:
                    with self._lock:
                        self.status = "complete"
                        self._actual_speed_x = 0.0
                        self._speed_sample_started_at = time.perf_counter()
                        self._speed_sample_frames = 0
                    self.pyboy.tick(1, True)
                    time.sleep(1 / 30)
                    continue

                if fast_forward_target is not None:
                    self._fast_forward_with_backend(fast_forward_target)
                    continue

                if simulate_target is not None:
                    self._simulate_with_backend(simulate_target, simulate_checkpoint_interval)
                    continue

                will_finish_fast_forward = (
                    fast_forward_target is not None
                    and self.digits_consumed + self.input_config.digits_per_input >= fast_forward_target
                )
                value = int(self.digits[self.digits_consumed : self.digits_consumed + self.input_config.digits_per_input])
                button = button_for_value(value, self.input_config)
                with self._lock:
                    self.current_input_frame = 0
                self.pyboy.button_press(button)
                self._tick_frames(self.hold_frames)
                self.pyboy.button_release(button)
                self._tick_frames(self.release_frames, force_final_render=will_finish_fast_forward)
                with self._lock:
                    self.digits_consumed += self.input_config.digits_per_input
                    self.frames_elapsed += self.frames_per_input
                    self.current_input_frame = 0
                    self.inputs_sent += 1
                    self.last_button = button
                    if fast_forward_target is not None and self.digits_consumed >= fast_forward_target:
                        self.paused = True
                        self._fast_forward_target_digits = None
                        self._restore_playback_speed_unlocked()
                        self.status = "complete" if self.digits_consumed >= self.max_digits else "paused"

                if (
                    self._auto_snapshots_enabled
                    and self.digits_consumed - self._last_snapshot_digits >= self.rewind_interval_digits
                ):
                    self._take_snapshot()
                self._cache_review_checkpoint_if_needed(self.pyboy, self.digits_consumed)
        finally:
            if self.audio_sink:
                self.audio_sink.close()
            self.pyboy.stop()

    def _tick_frames(self, frames: int, force_final_render: bool = False) -> None:
        for frame_index in range(frames):
            with self._lock:
                fast_forwarding = self._fast_forward_target_digits is not None
            render_frame = not fast_forwarding or (force_final_render and frame_index == frames - 1)
            self._limit_frame_rate()
            self.pyboy.tick(1, render_frame, not fast_forwarding)
            with self._lock:
                playback_speed = self.speed
                audio_enabled = self.speed_limiter_enabled
            if self.audio_sink and not fast_forwarding and audio_enabled:
                self.audio_sink.queue(self.pyboy, self.sound_volume, playback_speed)
            if render_frame:
                self._capture_frame()
            with self._lock:
                self.current_input_frame = min(self.frames_per_input, self.current_input_frame + 1)
            self._record_playback_frame()

    def _record_playback_frame(self) -> None:
        now = time.perf_counter()
        with self._lock:
            self._speed_sample_frames += 1
            elapsed = now - self._speed_sample_started_at
            if elapsed < 0.5:
                return
            self._actual_speed_x = (self._speed_sample_frames / elapsed) / GAMEBOY_FPS
            self._speed_sample_started_at = now
            self._speed_sample_frames = 0

    def _checkpoint_at_or_before(self, target_digits: int, minimum_digits: int = 0) -> tuple[int, Path] | None:
        checkpoint_dir = Path("saves") / self.run_name
        candidates: list[tuple[int, Path]] = []
        cache_dir = checkpoint_dir / REVIEW_CACHE_DIRNAME
        for source_dir in (checkpoint_dir, cache_dir):
            for candidate in source_dir.glob("checkpoint_*_digits.state"):
                match = CHECKPOINT_RE.match(candidate.name)
                if match:
                    digits_consumed = int(match.group(1))
                    if minimum_digits <= digits_consumed <= target_digits:
                        candidates.append((digits_consumed, candidate))
        return max(candidates, key=lambda candidate: candidate[0]) if candidates else None

    def _review_cache_dir(self) -> Path:
        return Path("saves") / self.run_name / REVIEW_CACHE_DIRNAME

    def _cache_review_checkpoint_if_needed(self, pyboy: PyBoy, digits_consumed: int) -> Path | None:
        if digits_consumed <= 0 or digits_consumed % REVIEW_CACHE_INTERVAL_DIGITS:
            return None

        cache_dir = self._review_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"checkpoint_{digits_consumed}_digits.state"
        if cache_path.exists():
            return cache_path

        temp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
        with temp_path.open("wb") as state_file:
            pyboy.save_state(state_file)
        temp_path.replace(cache_path)
        return cache_path

    def _next_review_cache_boundary(self, digits_consumed: int) -> int:
        next_boundary = ((digits_consumed // REVIEW_CACHE_INTERVAL_DIGITS) + 1) * REVIEW_CACHE_INTERVAL_DIGITS
        if next_boundary % self.input_config.digits_per_input:
            next_boundary += self.input_config.digits_per_input - (next_boundary % self.input_config.digits_per_input)
        return next_boundary

    def _advance_with_seek_progress(
        self,
        pyboy: PyBoy,
        start_digits: int,
        target_digits: int,
        chunk_digits: int = 10_000,
    ) -> tuple[int, int, str]:
        chunk_digits = self._normalize_digit_distance(chunk_digits)
        digits_consumed = start_digits
        total_inputs = 0
        last_button = "-"
        self._update_seek(digits_consumed)
        while digits_consumed < target_digits:
            next_cache_boundary = self._next_review_cache_boundary(digits_consumed)
            chunk_target = min(target_digits, digits_consumed + chunk_digits, next_cache_boundary)
            digits_consumed, inputs_sent, last_button = advance_pi_inputs(
                pyboy,
                self.digits,
                digits_consumed,
                chunk_target,
                self.hold_frames,
                self.release_frames,
                input_config=self.input_config,
            )
            total_inputs += inputs_sent
            self._cache_review_checkpoint_if_needed(pyboy, digits_consumed)
            self._update_seek(digits_consumed)
        return digits_consumed, total_inputs, last_button

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
            sound_emulated=True,
            sound_sample_rate=getattr(self.pyboy.sound, "sample_rate", 48000),
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
            digits_consumed, inputs_sent, last_button = self._advance_with_seek_progress(
                simulator,
                start_digits,
                target_digits,
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
            self.current_input_frame = 0
            self.frames_elapsed += inputs_sent * self.frames_per_input
            self.inputs_sent += inputs_sent
            self.last_button = last_button
            self.paused = True
            self._fast_forward_target_digits = None
            self._restore_playback_speed_unlocked()
            self.status = "complete" if self.digits_consumed >= self.max_digits else "paused"
            self.latest_image = image
            self._auto_snapshots_enabled = False
            self._end_seek_unlocked()

    def _simulate_with_backend(self, target_digits: int, checkpoint_interval_digits: int) -> None:
        with self._lock:
            start_digits = self.digits_consumed
            requested_start_digits = start_digits
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
            sound_emulated=True,
            sound_sample_rate=getattr(self.pyboy.sound, "sample_rate", 48000),
            no_input=False,
            ram_file=io.BytesIO(bytes(32768)),
            log_level="CRITICAL",
        )
        simulator.set_emulation_speed(0)
        checkpoint_dir = Path("saves") / self.run_name
        screenshot_dir = Path("results") / self.run_name / "screenshots"
        progress_path = Path("results") / self.run_name / "progress.json"
        digits_consumed = start_digits
        inputs_sent = 0
        last_button = self.last_button
        last_state: Path | None = None
        resume_start_digits = start_digits
        checkpoint = self._checkpoint_at_or_before(target_digits, minimum_digits=start_digits + self.input_config.digits_per_input)
        try:
            if checkpoint is not None:
                digits_consumed, checkpoint_path = checkpoint
                resume_start_digits = digits_consumed
                with checkpoint_path.open("rb") as state_file:
                    simulator.load_state(state_file)
                last_state = checkpoint_path
            else:
                state_buffer.seek(0)
                simulator.load_state(state_buffer)
            next_checkpoint = ((digits_consumed // checkpoint_interval_digits) + 1) * checkpoint_interval_digits
            next_checkpoint = min(next_checkpoint, target_digits)
            while digits_consumed < target_digits:
                chunk_target = min(next_checkpoint, target_digits)
                digits_consumed, chunk_inputs, last_button = advance_pi_inputs(
                    simulator,
                    self.digits,
                    digits_consumed,
                    chunk_target,
                    self.hold_frames,
                    self.release_frames,
                    input_config=self.input_config,
                )
                inputs_sent += chunk_inputs
                self._update_seek(digits_consumed)
                if digits_consumed >= next_checkpoint or digits_consumed >= target_digits:
                    last_state = save_checkpoint(
                        simulator,
                        checkpoint_dir,
                        screenshot_dir,
                        digits_consumed,
                        save_screenshot=True,
                    )
                    elapsed_so_far = max(time.perf_counter() - started_at, 0.000001)
                    frames_advanced_so_far = inputs_sent * self.frames_per_input
                    effective_fps_so_far = frames_advanced_so_far / elapsed_so_far
                    progress = Progress(
                        run_name=self.run_name,
                        digits_path=str(self.digits_path),
                        rom_path=str(self.rom_path or ROM),
                        digits_consumed=digits_consumed,
                        input_pairs_consumed=digits_consumed // self.input_config.digits_per_input,
                        frames_elapsed=(digits_consumed // self.input_config.digits_per_input) * self.frames_per_input,
                        checkpoints_completed=len(list(checkpoint_dir.glob("checkpoint_*_digits.state"))),
                        elapsed_seconds=elapsed_so_far,
                        effective_fps=effective_fps_so_far,
                        effective_realtime_x=effective_fps_so_far / GAMEBOY_FPS,
                        last_state=str(last_state),
                    )
                    write_progress(progress_path, progress)
                    next_checkpoint = min(next_checkpoint + checkpoint_interval_digits, target_digits)
            final_state = io.BytesIO()
            simulator.save_state(final_state)
        finally:
            simulator.stop()

        elapsed = max(time.perf_counter() - started_at, 0.000001)
        effective_digits_per_second = (digits_consumed - resume_start_digits) / elapsed
        frames_advanced = inputs_sent * self.frames_per_input
        effective_fps = frames_advanced / elapsed
        total_digits_advanced = digits_consumed - requested_start_digits
        last_button = self._button_before_digits(digits_consumed, fallback=last_button)
        final_state.seek(0)
        self.pyboy.load_state(final_state)
        image = render_loaded_state(self.pyboy)
        with self._lock:
            self.digits_consumed = digits_consumed
            self.current_input_frame = 0
            self.frames_elapsed = (digits_consumed // self.input_config.digits_per_input) * self.frames_per_input
            self.inputs_sent += max(0, total_digits_advanced // self.input_config.digits_per_input)
            self.last_button = last_button
            self.paused = True
            self._simulate_target_digits = None
            self._simulation_started_at = None
            self._restore_playback_speed_unlocked()
            self.status = "complete" if self.digits_consumed >= self.max_digits else "paused"
            self.latest_image = image
            self._auto_snapshots_enabled = False
            self._last_simulation = {
                "digits": digits_consumed - resume_start_digits,
                "resumed_from_digits": resume_start_digits,
                "skipped_digits": max(0, resume_start_digits - requested_start_digits),
                "elapsed_seconds": elapsed,
                "digits_per_second": effective_digits_per_second,
                "last_state": str(last_state),
            }
            self._end_seek_unlocked()

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
            snapshot = candidates[-1] if candidates else None
            self._fast_forward_target_digits = None
            self._set_seek_emulation_speed_unlocked()

        checkpoint: tuple[int, Path] | None = None
        if snapshot is None:
            checkpoint = self._checkpoint_at_or_before(target)
            if checkpoint is None:
                with self._lock:
                    self.paused = True
                    self.status = "no rewind source before target"
                    self._restore_playback_speed_unlocked()
                    self._end_seek_unlocked()
                return
            checkpoint_digits, _ = checkpoint
            if target - checkpoint_digits > MAX_INTERACTIVE_REWIND_REPLAY_DIGITS:
                with self._lock:
                    self.paused = True
                    self.status = "rewind history unavailable before checkpoint"
                    self._restore_playback_speed_unlocked()
                    self._end_seek_unlocked()
                return

        if snapshot is not None:
            self.pyboy.load_state(io.BytesIO(snapshot.state))
            source_digits = snapshot.digits_consumed
            source_frames = snapshot.frames_elapsed
            with self._lock:
                self._begin_seek_unlocked("Rewinding", source_digits, target)
            digits_consumed, inputs_sent, last_button = self._advance_with_seek_progress(
                self.pyboy,
                source_digits,
                target,
            )
            image = render_loaded_state(self.pyboy)
            state_buffer = io.BytesIO()
            self.pyboy.save_state(state_buffer)
        else:
            source_digits, checkpoint_path = checkpoint
            source_frames = (source_digits // self.input_config.digits_per_input) * self.frames_per_input
            with self._lock:
                self._begin_seek_unlocked("Rewinding", source_digits, target)
            simulator = PyBoy(
                str(self.rom_path or ROM),
                window="null",
                sound_emulated=True,
                sound_sample_rate=getattr(self.pyboy.sound, "sample_rate", 48000),
                no_input=False,
                ram_file=io.BytesIO(bytes(32768)),
                log_level="CRITICAL",
            )
            simulator.set_emulation_speed(0)
            try:
                with checkpoint_path.open("rb") as state_file:
                    simulator.load_state(state_file)
                digits_consumed, inputs_sent, last_button = self._advance_with_seek_progress(
                    simulator,
                    source_digits,
                    target,
                )
                state_buffer = io.BytesIO()
                simulator.save_state(state_buffer)
            finally:
                simulator.stop()
            state_buffer.seek(0)
            self.pyboy.load_state(state_buffer)
            image = render_loaded_state(self.pyboy)
            state_buffer.seek(0)
        with self._lock:
            self.digits_consumed = digits_consumed
            self.current_input_frame = 0
            self.frames_elapsed = source_frames + inputs_sent * self.frames_per_input
            if inputs_sent:
                self.last_button = last_button
            self.paused = True
            self.pause_requested = False
            self.status = f"rewound to {digits_consumed:,} digits"
            self.latest_image = image
            self.snapshots.append(
                Snapshot(
                    digits_consumed=self.digits_consumed,
                    frames_elapsed=self.frames_elapsed,
                    state=state_buffer.getvalue(),
                )
            )
            self._last_snapshot_digits = self.digits_consumed
            self._restore_playback_speed_unlocked()
            self._end_seek_unlocked()

    def _jump_to(self, target: int) -> None:
        target = max(0, min(len(self.digits), target))
        if target % self.input_config.digits_per_input:
            target -= target % self.input_config.digits_per_input

        checkpoint = self._checkpoint_at_or_before(target)
        if checkpoint is None:
            with self._lock:
                self.paused = True
                self._jump_target_digits = None
                self._restore_playback_speed_unlocked()
                self.status = "no checkpoint before target"
                self._end_seek_unlocked()
            return

        checkpoint_digits_consumed, checkpoint_path = checkpoint
        with self._lock:
            self._begin_seek_unlocked("Jumping", checkpoint_digits_consumed, target)

        simulator = PyBoy(
            str(self.rom_path or ROM),
            window="null",
            sound_emulated=True,
            sound_sample_rate=getattr(self.pyboy.sound, "sample_rate", 48000),
            no_input=False,
            ram_file=io.BytesIO(bytes(32768)),
            log_level="CRITICAL",
        )
        simulator.set_emulation_speed(0)
        try:
            with checkpoint_path.open("rb") as state_file:
                simulator.load_state(state_file)
            digits_consumed, inputs_sent, last_button = self._advance_with_seek_progress(
                simulator,
                checkpoint_digits_consumed,
                target,
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
            self.current_input_frame = 0
            self.max_digits = max(self.max_digits, digits_consumed)
            self.frames_elapsed = (digits_consumed // self.input_config.digits_per_input) * self.frames_per_input
            self.inputs_sent = inputs_sent
            if inputs_sent:
                self.last_button = last_button
            self.paused = True
            self._jump_target_digits = None
            self._restore_playback_speed_unlocked()
            self.status = "paused"
            self.latest_image = image
            self._auto_snapshots_enabled = False
            self._end_seek_unlocked()

    def _find_next_warp_state_with_backend(self, target_state: str, limit_digits: int) -> None:
        with self._lock:
            start_digits = self.digits_consumed
            if self.paused or self.pause_requested or self._warp_target_state is None:
                return
            end_digits = min(self.max_digits, start_digits + limit_digits)
            if end_digits % self.input_config.digits_per_input:
                end_digits -= end_digits % self.input_config.digits_per_input
            state_buffer = io.BytesIO()
            self.pyboy.save_state(state_buffer)

        state_buffer.seek(0)
        simulator = PyBoy(
            str(self.rom_path or ROM),
            window="null",
            sound_emulated=True,
            sound_sample_rate=getattr(self.pyboy.sound, "sample_rate", 48000),
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
            trainer_battle_seen = is_in_trainer_battle(simulator)
            wild_battle_seen = is_in_wild_battle(simulator)
            blackout_seen = is_party_blackout(simulator)
            starting_map = current_map_id(simulator)
            starting_levels = party_levels(simulator)
            starting_species = party_species(simulator)
            starting_evolution_marker = evolution_marker(simulator)
            starting_bag_items = bag_quantities(simulator)
            evolution_seen = is_evolution_active(simulator)
            while digits_consumed < end_digits:
                value = int(self.digits[digits_consumed : digits_consumed + self.input_config.digits_per_input])
                button = button_for_value(value, self.input_config)
                simulator.button_press(button)
                simulator.tick(self.hold_frames, False, True)
                simulator.button_release(button)
                if self.release_frames:
                    simulator.tick(self.release_frames, False, True)
                digits_consumed += self.input_config.digits_per_input
                inputs_sent += 1
                last_button = button
                if inputs_sent % 5000 == 0:
                    self._update_seek(digits_consumed)

                in_battle = is_in_battle(simulator)
                in_trainer_battle = is_in_trainer_battle(simulator)
                in_wild_battle = is_in_wild_battle(simulator)
                blackout = is_party_blackout(simulator)
                if target_state == "battle":
                    if battle_seen:
                        if not in_battle:
                            battle_seen = False
                    elif in_battle:
                        found = True
                        break
                elif target_state == "trainer_battle":
                    if trainer_battle_seen:
                        if not in_trainer_battle:
                            trainer_battle_seen = False
                    elif in_trainer_battle:
                        found = True
                        break
                elif target_state == "wild_battle":
                    if wild_battle_seen:
                        if not in_wild_battle:
                            wild_battle_seen = False
                    elif in_wild_battle:
                        found = True
                        break
                elif target_state == "blackout":
                    if blackout_seen:
                        if not blackout:
                            blackout_seen = False
                    elif blackout:
                        found = True
                        break
                elif target_state == "level_up" and has_party_level_up(simulator, starting_levels):
                    found = True
                    break
                elif target_state == "evolution":
                    in_evolution = is_evolution_active(simulator)
                    if evolution_seen:
                        if not in_evolution:
                            evolution_seen = False
                            starting_evolution_marker = evolution_marker(simulator)
                            starting_species = party_species(simulator)
                    elif has_evolution_started(simulator, starting_evolution_marker, starting_species):
                        found = True
                        break
                elif target_state == "item_pickup" and has_bag_item_gain(simulator, starting_bag_items):
                    found = True
                    break
                elif target_state == "scene_change" and current_map_id(simulator) != starting_map:
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
                self._restore_playback_speed_unlocked()
                self.status = f"no {WARP_STATE_LABELS[target_state]} within {limit_digits:,} digits"
                self._end_seek_unlocked()
            return

        final_state.seek(0)
        self.pyboy.load_state(final_state)
        image = render_loaded_state(self.pyboy)
        with self._lock:
            self.digits_consumed = digits_consumed
            self.current_input_frame = 0
            self.frames_elapsed += inputs_sent * self.frames_per_input
            self.inputs_sent += inputs_sent
            self.last_button = last_button
            self.paused = True
            self._warp_target_state = None
            self._restore_playback_speed_unlocked()
            self.status = "paused"
            self.latest_image = image
            self._auto_snapshots_enabled = False
            self._end_seek_unlocked()

    def _normalize_digit_distance(self, digits: int) -> int:
        digits_per_input = self.input_config.digits_per_input
        digits = max(digits_per_input, int(digits))
        if digits % digits_per_input:
            digits -= digits % digits_per_input
        return digits

    def _button_before_digits(self, digits_consumed: int, fallback: str = "-") -> str:
        digits_per_input = self.input_config.digits_per_input
        if digits_consumed < digits_per_input:
            return fallback
        start = digits_consumed - digits_per_input
        try:
            value = int(self.digits[start:digits_consumed])
            return button_for_value(value, self.input_config)
        except ValueError:
            return fallback

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
        digits_available = len(self.digits)
        for offset in range(0, count * digits_per_input, digits_per_input):
            digit_index = start + offset
            if digit_index + digits_per_input > digits_available:
                break
            digits_slice = self.digits[digit_index : digit_index + digits_per_input]
            buttons.append((digit_index, digits_slice, button_for_value(int(digits_slice), self.input_config)))
        return buttons

    def input_window(self, previous_count: int = 3, next_count: int = 11) -> list[dict[str, int | str]]:
        with self._lock:
            current = self.digits_consumed

        items: list[dict[str, int | str]] = []
        digits_per_input = self.input_config.digits_per_input
        digits_available = len(self.digits)
        first = max(0, current - (previous_count * digits_per_input))
        last = min(digits_available, current + ((next_count + 1) * digits_per_input))
        for digit_index in range(first, last, digits_per_input):
            if digit_index + digits_per_input > digits_available:
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
        candidate = checkpoint_dir / f"checkpoint_{int(checkpoint)}_digits.state"
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
    args.run_name = resolve_configured_run_name(args.run_name, args.config)
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
