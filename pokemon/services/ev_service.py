# -*- coding: utf-8 -*-
"""
pokemon/services/ev_service.py
══════════════════════════════════════════════════════════════════════════════
Sistema de Effort Values (EVs) para combate y captura.

Reglas oficiales (Gen 3+):
  • Cada stat puede acumular máximo 252 EVs
  • Total máximo: 510 EVs por Pokémon
  • Cada 4 EVs = +1 al stat en la fórmula
  • Los EVs se ganan al DERROTAR (o capturar) a un Pokémon
  • Solo el Pokémon ACTIVO que participó gana los EVs

Integración:
  • Llamar `EVService.otorgar_evs(pokemon_id, wild_pokemon_id)` en
    _handle_victory y _handle_capture_success de wild_battle_system.py
  • Llamar `EVService.otorgar_evs_pvp(pokemon_id, rival_pokemon_id)` en
    PvP al procesar victoria
══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES OFICIALES
# ─────────────────────────────────────────────────────────────────────────────

EV_MAX_POR_STAT  = 252   # máximo por estadística individual
EV_MAX_TOTAL     = 510   # máximo total por Pokémon

# Mapa de clave interna → columna BD
_STAT_COLUMNA: Dict[str, str] = {
    "hp":     "ev_hp",
    "atq":    "ev_atq",
    "def":    "ev_def",
    "atq_sp": "ev_atq_sp",
    "def_sp": "ev_def_sp",
    "vel":    "ev_vel",
}

POWER_ITEM_EV_MAP: Dict[str, str] = {
    "powerweight": "hp",    "pesa recia":   "hp",
    "powerbracer": "atq",   "brazal recio": "atq",
    "powerbelt":   "def",   "cinto recio":  "def",
    "powerlens":   "atq_sp","lente recia":  "atq_sp",
    "powerband":   "def_sp","banda recia":  "def_sp",
    "poweranklet": "vel",   "franja recia": "vel",
}
POWER_ITEM_EV_BONUS: int = 8

# ─────────────────────────────────────────────────────────────────────────────
# TABLA DE EV YIELDS — todos los Pokémon Gen 1–9
#
# Formato: {pokemonID: {stat_key: cantidad}}
# Fuentes: Bulbapedia / Serebii / datos oficiales de los juegos
# ─────────────────────────────────────────────────────────────────────────────

EV_YIELDS: Dict[int, Dict[str, int]] = {
    # ══════════ GEN 1 (1–151) ══════════
    1:   {"atq_sp": 1},           # Bulbasaur
    2:   {"atq_sp": 1, "def_sp": 1},  # Ivysaur
    3:   {"atq_sp": 2, "def_sp": 1},  # Venusaur
    4:   {"atq_sp": 1},           # Charmander
    5:   {"atq_sp": 1, "vel": 1}, # Charmeleon
    6:   {"atq_sp": 3},           # Charizard
    7:   {"def": 1},              # Squirtle
    8:   {"def": 2},              # Wartortle
    9:   {"def": 3},              # Blastoise
    10:  {"hp": 1},               # Caterpie
    11:  {"def": 2},              # Metapod
    12:  {"atq_sp": 1, "vel": 1}, # Butterfree
    13:  {"vel": 1},              # Weedle
    14:  {"def": 2},              # Kakuna
    15:  {"atq": 2, "vel": 1},    # Beedrill
    16:  {"vel": 1},              # Pidgey
    17:  {"vel": 2},              # Pidgeotto
    18:  {"vel": 3},              # Pidgeot
    19:  {"vel": 1},              # Rattata
    20:  {"vel": 2},              # Raticate
    21:  {"vel": 1},              # Spearow
    22:  {"vel": 2},              # Fearow
    23:  {"atq": 1},              # Ekans
    24:  {"atq": 2},              # Arbok
    25:  {"vel": 2},              # Pikachu
    26:  {"vel": 3},              # Raichu
    27:  {"def": 1},              # Sandshrew
    28:  {"def": 2},              # Sandslash
    29:  {"hp": 1},               # Nidoran♀
    30:  {"hp": 2},               # Nidorina
    31:  {"def": 2, "atq": 1},    # Nidoqueen
    32:  {"atq": 1},              # Nidoran♂
    33:  {"atq": 2},              # Nidorino
    34:  {"atq": 2, "def": 1},    # Nidoking
    35:  {"hp": 2},               # Clefairy
    36:  {"hp": 3},               # Clefable
    37:  {"atq_sp": 1},           # Vulpix
    38:  {"atq_sp": 1, "vel": 1}, # Ninetales
    39:  {"hp": 2},               # Jigglypuff
    40:  {"hp": 3},               # Wigglytuff
    41:  {"vel": 1},              # Zubat
    42:  {"vel": 2},              # Golbat
    43:  {"atq_sp": 1},           # Oddish
    44:  {"atq_sp": 2},           # Gloom
    45:  {"atq_sp": 2, "def_sp": 1},  # Vileplume
    46:  {"atq": 1},              # Paras
    47:  {"atq": 2, "def": 1},    # Parasect
    48:  {"def_sp": 1},           # Venonat
    49:  {"atq_sp": 2, "vel": 1}, # Venomoth
    50:  {"vel": 1},              # Diglett
    51:  {"vel": 2},              # Dugtrio
    52:  {"vel": 1},              # Meowth
    53:  {"vel": 2},              # Persian
    54:  {"atq_sp": 1},           # Psyduck
    55:  {"atq_sp": 2},           # Golduck
    56:  {"atq": 1},              # Mankey
    57:  {"atq": 2},              # Primeape
    58:  {"atq": 1},              # Growlithe
    59:  {"atq": 2},              # Arcanine
    60:  {"vel": 1},              # Poliwag
    61:  {"vel": 2},              # Poliwhirl
    62:  {"atq": 3},              # Poliwrath
    63:  {"atq_sp": 1},           # Abra
    64:  {"atq_sp": 2},           # Kadabra
    65:  {"atq_sp": 3},           # Alakazam
    66:  {"atq": 1},              # Machop
    67:  {"atq": 2},              # Machoke
    68:  {"atq": 3},              # Machamp
    69:  {"atq": 1},              # Bellsprout
    70:  {"atq": 2},              # Weepinbell
    71:  {"atq": 2, "atq_sp": 1}, # Victreebel
    72:  {"def_sp": 1},           # Tentacool
    73:  {"def_sp": 2},           # Tentacruel
    74:  {"def": 1},              # Geodude
    75:  {"def": 2},              # Graveler
    76:  {"def": 3},              # Golem
    77:  {"vel": 1},              # Ponyta
    78:  {"vel": 2},              # Rapidash
    79:  {"hp": 1},               # Slowpoke
    80:  {"def": 2},              # Slowbro
    81:  {"def_sp": 1},           # Magnemite
    82:  {"def_sp": 2},           # Magneton
    83:  {"atq": 1},              # Farfetch'd
    84:  {"vel": 1},              # Doduo
    85:  {"vel": 3},              # Dodrio
    86:  {"def_sp": 1},           # Seel
    87:  {"def_sp": 2},           # Dewgong
    88:  {"hp": 1},               # Grimer
    89:  {"hp": 2},               # Muk
    90:  {"def": 1},              # Shellder
    91:  {"def": 2},              # Cloyster
    92:  {"atq_sp": 1},           # Gastly
    93:  {"atq_sp": 2},           # Haunter
    94:  {"atq_sp": 3},           # Gengar
    95:  {"def": 1},              # Onix
    96:  {"def_sp": 1},           # Drowzee
    97:  {"def_sp": 2},           # Hypno
    98:  {"atq": 1},              # Krabby
    99:  {"atq": 2},              # Kingler
    100: {"vel": 1},              # Voltorb
    101: {"vel": 2},              # Electrode
    102: {"atq_sp": 1},           # Exeggcute
    103: {"atq_sp": 2},           # Exeggutor
    104: {"def": 1},              # Cubone
    105: {"def": 2},              # Marowak
    106: {"atq": 2},              # Hitmonlee
    107: {"atq": 1, "def_sp": 1}, # Hitmonchan
    108: {"hp": 2},               # Lickitung
    109: {"def": 1},              # Koffing
    110: {"def": 2},              # Weezing
    111: {"def": 1},              # Rhyhorn
    112: {"atq": 2},              # Rhydon
    113: {"hp": 2},               # Chansey
    114: {"def_sp": 1},           # Tangela
    115: {"hp": 2},               # Kangaskhan
    116: {"atq_sp": 1},           # Horsea
    117: {"atq_sp": 2},           # Seadra
    118: {"atq": 1},              # Goldeen
    119: {"atq": 2},              # Seaking
    120: {"vel": 1},              # Staryu
    121: {"atq_sp": 2},           # Starmie
    122: {"def_sp": 2},           # Mr. Mime
    123: {"atq": 1},              # Scyther
    124: {"atq_sp": 2},           # Jynx
    125: {"vel": 2},              # Electabuzz
    126: {"atq_sp": 2},           # Magmar
    127: {"atq": 2},              # Pinsir
    128: {"vel": 3},              # Tauros
    129: {"vel": 1},              # Magikarp
    130: {"atq": 2},              # Gyarados
    131: {"hp": 2},               # Lapras
    132: {"hp": 1},               # Ditto
    133: {"hp": 1},               # Eevee
    134: {"hp": 2},               # Vaporeon
    135: {"vel": 2},              # Jolteon
    136: {"atq": 2},              # Flareon
    137: {"atq_sp": 1},           # Porygon
    138: {"def": 1},              # Omanyte
    139: {"atq_sp": 1, "def": 1}, # Omastar
    140: {"def": 1},              # Kabuto
    141: {"atq": 2},              # Kabutops
    142: {"vel": 2},              # Aerodactyl
    143: {"hp": 2},               # Snorlax
    144: {"def_sp": 3},           # Articuno
    145: {"atq_sp": 3},           # Zapdos
    146: {"atq_sp": 3},           # Moltres
    147: {"atq": 1},              # Dratini
    148: {"atq": 2},              # Dragonair
    149: {"atq": 3},              # Dragonite
    150: {"atq_sp": 3},           # Mewtwo
    151: {"hp": 3},               # Mew

    # ══════════ GEN 2 (152–251) ══════════
    152: {"def_sp": 1},           # Chikorita
    153: {"def_sp": 2},           # Bayleef
    154: {"def": 1, "def_sp": 2}, # Meganium
    155: {"vel": 1},              # Cyndaquil
    156: {"vel": 2},              # Quilava
    157: {"atq_sp": 3},           # Typhlosion
    158: {"atq": 1},              # Totodile
    159: {"atq": 2},              # Croconaw
    160: {"atq": 3},              # Feraligatr
    161: {"vel": 1},              # Sentret
    162: {"vel": 2},              # Furret
    163: {"def_sp": 1},           # Hoothoot
    164: {"def_sp": 2},           # Noctowl
    165: {"def_sp": 1},           # Ledyba
    166: {"def_sp": 2},           # Ledian
    167: {"atq": 1},              # Spinarak
    168: {"atq": 2},              # Ariados
    169: {"vel": 3},              # Crobat
    170: {"def_sp": 1},           # Chinchou
    171: {"hp": 2},               # Lanturn
    172: {"vel": 1},              # Pichu
    173: {"hp": 1},               # Cleffa
    174: {"hp": 1},               # Igglybuff
    175: {"def_sp": 1},           # Togepi
    176: {"def_sp": 2},           # Togetic
    177: {"atq_sp": 1},           # Natu
    178: {"atq_sp": 2},           # Xatu
    179: {"atq_sp": 1},           # Mareep
    180: {"atq_sp": 2},           # Flaaffy
    181: {"atq_sp": 3},           # Ampharos
    182: {"atq_sp": 3},           # Bellossom
    183: {"hp": 2},               # Marill
    184: {"hp": 3},               # Azumarill
    185: {"def": 2},              # Sudowoodo
    186: {"def_sp": 3},           # Politoed
    187: {"vel": 1},              # Hoppip
    188: {"vel": 2},              # Skiploom
    189: {"vel": 3},              # Jumpluff
    190: {"vel": 1},              # Aipom
    191: {"atq_sp": 1},           # Sunkern
    192: {"atq_sp": 2},           # Sunflora
    193: {"vel": 1},              # Yanma
    194: {"hp": 1},               # Wooper
    195: {"hp": 2},               # Quagsire
    196: {"atq_sp": 2},           # Espeon
    197: {"def_sp": 2},           # Umbreon
    198: {"atq": 1},              # Murkrow
    199: {"def_sp": 3},           # Slowking
    200: {"atq_sp": 1},           # Misdreavus
    201: {"atq_sp": 1},           # Unown
    202: {"hp": 2},               # Wobbuffet
    203: {"atq_sp": 1},           # Girafarig
    204: {"def": 1},              # Pineco
    205: {"def": 2},              # Forretress
    206: {"hp": 1},               # Dunsparce
    207: {"def": 1},              # Gligar
    208: {"def": 3},              # Steelix
    209: {"atq": 1},              # Snubbull
    210: {"atq": 2},              # Granbull
    211: {"vel": 1},              # Qwilfish
    212: {"atq": 2},              # Scizor
    213: {"def": 1, "def_sp": 1}, # Shuckle
    214: {"atq": 2},              # Heracross
    215: {"vel": 1},              # Sneasel
    216: {"atq": 1},              # Teddiursa
    217: {"atq": 2},              # Ursaring
    218: {"atq_sp": 1},           # Slugma
    219: {"def": 1, "atq_sp": 1}, # Magcargo
    220: {"hp": 1},               # Swinub
    221: {"hp": 2},               # Piloswine
    222: {"def": 1, "def_sp": 1}, # Corsola
    223: {"atq_sp": 1},           # Remoraid
    224: {"atq_sp": 2},           # Octillery
    225: {"vel": 1},              # Delibird
    226: {"def_sp": 2},           # Mantine
    227: {"def": 2},              # Skarmory
    228: {"atq_sp": 1},           # Houndour
    229: {"atq_sp": 2},           # Houndoom
    230: {"atq_sp": 3},           # Kingdra
    231: {"hp": 1},               # Phanpy
    232: {"def": 2},              # Donphan
    233: {"atq_sp": 2},           # Porygon2
    234: {"atq_sp": 1},           # Stantler
    235: {"vel": 1},              # Smeargle
    236: {"hp": 1},               # Tyrogue
    237: {"hp": 1, "def": 1},     # Hitmontop
    238: {"atq_sp": 1},           # Smoochum
    239: {"vel": 1},              # Elekid
    240: {"atq_sp": 1},           # Magby
    241: {"hp": 2},               # Miltank
    242: {"hp": 3},               # Blissey
    243: {"atq_sp": 3},           # Raikou
    244: {"atq": 3},              # Entei
    245: {"def_sp": 3},           # Suicune
    246: {"atq": 1},              # Larvitar
    247: {"atq": 2},              # Pupitar
    248: {"atq": 3},              # Tyranitar
    249: {"def_sp": 3},           # Lugia
    250: {"atq_sp": 3},           # Ho-Oh
    251: {"hp": 3},               # Celebi

    # ══════════ GEN 3 (252–386) ══════════
    252: {"vel": 1},              # Treecko
    253: {"vel": 2},              # Grovyle
    254: {"vel": 3},              # Sceptile
    255: {"atq_sp": 1},           # Torchic
    256: {"atq": 1, "atq_sp": 1}, # Combusken
    257: {"atq": 2, "vel": 1},    # Blaziken
    258: {"atq": 1},              # Mudkip
    259: {"atq": 2},              # Marshtomp
    260: {"atq": 2, "def": 1},    # Swampert
    261: {"atq": 1},              # Poochyena
    262: {"atq": 2},              # Mightyena
    263: {"vel": 1},              # Zigzagoon
    264: {"vel": 2},              # Linoone
    265: {"hp": 1},               # Wurmple
    266: {"def": 2},              # Silcoon
    267: {"atq_sp": 2, "vel": 1}, # Beautifly
    268: {"def": 2},              # Cascoon
    269: {"def_sp": 3},           # Dustox
    270: {"atq_sp": 1},           # Lotad
    271: {"atq_sp": 2},           # Lombre
    272: {"def_sp": 2},           # Ludicolo
    273: {"def": 1},              # Seedot
    274: {"atq": 2},              # Nuzleaf
    275: {"atq": 3},              # Shiftry
    276: {"vel": 1},              # Taillow
    277: {"vel": 3},              # Swellow
    278: {"vel": 1},              # Wingull
    279: {"def": 1, "def_sp": 1}, # Pelipper
    280: {"atq_sp": 1},           # Ralts
    281: {"atq_sp": 2},           # Kirlia
    282: {"atq_sp": 3},           # Gardevoir
    283: {"vel": 1},              # Surskit
    284: {"vel": 1, "atq_sp": 1}, # Masquerain
    285: {"hp": 1},               # Shroomish
    286: {"atq": 2},              # Breloom
    287: {"hp": 1},               # Slakoth
    288: {"vel": 2},              # Vigoroth
    289: {"atq": 3},              # Slaking
    290: {"def": 1},              # Nincada
    291: {"vel": 2},              # Ninjask
    292: {"hp": 1},               # Shedinja
    293: {"hp": 1},               # Whismur
    294: {"hp": 2},               # Loudred
    295: {"hp": 3},               # Exploud
    296: {"hp": 1},               # Makuhita
    297: {"hp": 2},               # Hariyama
    298: {"hp": 1},               # Azurill
    299: {"def": 1},              # Nosepass
    300: {"vel": 1},              # Skitty
    301: {"vel": 2},              # Delcatty
    302: {"atq_sp": 1},           # Sableye
    303: {"atq": 1},              # Mawile
    304: {"def": 1},              # Aron
    305: {"def": 2},              # Lairon
    306: {"def": 3},              # Aggron
    307: {"vel": 1},              # Meditite
    308: {"vel": 2},              # Medicham
    309: {"atq_sp": 1},           # Electrike
    310: {"atq_sp": 2},           # Manectric
    311: {"atq_sp": 1},           # Plusle
    312: {"atq_sp": 1},           # Minun
    313: {"def": 1},              # Volbeat
    314: {"def_sp": 1},           # Illumise
    315: {"atq_sp": 1, "def_sp": 1}, # Roselia
    316: {"hp": 1},               # Gulpin
    317: {"hp": 2},               # Swalot
    318: {"atq": 1},              # Carvanha
    319: {"atq": 2},              # Sharpedo
    320: {"hp": 1},               # Wailmer
    321: {"hp": 2},               # Wailord
    322: {"atq_sp": 1},           # Numel
    323: {"atq_sp": 2},           # Camerupt
    324: {"def": 2},              # Torkoal
    325: {"def_sp": 1},           # Spoink
    326: {"def_sp": 2},           # Grumpig
    327: {"def_sp": 1},           # Spinda
    328: {"atq": 1},              # Trapinch
    329: {"vel": 1},              # Vibrava
    330: {"atq": 1, "vel": 1},    # Flygon
    331: {"atq_sp": 1},           # Cacnea
    332: {"atq_sp": 2},           # Cacturne
    333: {"def_sp": 1},           # Swablu
    334: {"atq_sp": 1, "def_sp": 1}, # Altaria
    335: {"atq": 2},              # Zangoose
    336: {"atq_sp": 2},           # Seviper
    337: {"atq_sp": 2},           # Lunatone
    338: {"atq": 2},              # Solrock
    339: {"hp": 1},               # Barboach
    340: {"hp": 2},               # Whiscash
    341: {"atq": 1},              # Corphish
    342: {"atq": 2},              # Crawdaunt
    343: {"def": 1},              # Baltoy
    344: {"def": 2},              # Claydol
    345: {"def_sp": 1},           # Lileep
    346: {"hp": 1, "def_sp": 1},  # Cradily
    347: {"atq": 1},              # Anorith
    348: {"atq": 2},              # Armaldo
    349: {"hp": 1},               # Feebas
    350: {"def_sp": 2},           # Milotic
    351: {"atq_sp": 1},           # Castform
    352: {"def_sp": 1},           # Kecleon
    353: {"atq": 1},              # Shuppet
    354: {"atq": 2},              # Banette
    355: {"def_sp": 1},           # Duskull
    356: {"def_sp": 2},           # Dusclops
    357: {"def_sp": 1},           # Tropius
    358: {"def_sp": 1},           # Chimecho
    359: {"atq": 2},              # Absol
    360: {"hp": 1},               # Wynaut
    361: {"vel": 1},              # Snorunt
    362: {"vel": 2},              # Glalie
    363: {"hp": 1},               # Spheal
    364: {"hp": 2},               # Sealeo
    365: {"hp": 3},               # Walrein
    366: {"def_sp": 1},           # Clamperl
    367: {"atq": 2},              # Huntail
    368: {"atq_sp": 2},           # Gorebyss
    369: {"hp": 1, "def": 1},     # Relicanth
    370: {"def_sp": 1},           # Luvdisc
    371: {"atq": 1},              # Bagon
    372: {"def": 2},              # Shelgon
    373: {"atq": 3},              # Salamence
    374: {"def": 1},              # Beldum
    375: {"def": 2},              # Metang
    376: {"atq": 3},              # Metagross
    377: {"def": 3},              # Regirock
    378: {"def_sp": 3},           # Regice
    379: {"def": 3},              # Registeel
    380: {"atq_sp": 3},           # Latias
    381: {"atq_sp": 3},           # Latios
    382: {"atq_sp": 3},           # Kyogre
    383: {"atq": 3},              # Groudon
    384: {"atq_sp": 3},           # Rayquaza
    385: {"hp": 3},               # Jirachi
    386: {"atq_sp": 3},           # Deoxys

    # ══════════ GEN 4 (387–493) ══════════
    387: {"atq": 1},              # Turtwig
    388: {"atq": 2},              # Grotle
    389: {"atq": 2, "def": 1},    # Torterra
    390: {"vel": 1},              # Chimchar
    391: {"atq": 1, "vel": 1},    # Monferno
    392: {"atq": 2, "vel": 1},    # Infernape
    393: {"def": 1},              # Piplup
    394: {"def": 1, "atq_sp": 1}, # Prinplup
    395: {"atq_sp": 3},           # Empoleon
    396: {"vel": 1},              # Starly
    397: {"vel": 2},              # Staravia
    398: {"vel": 3},              # Staraptor
    399: {"hp": 1},               # Bidoof
    400: {"hp": 2},               # Bibarel
    401: {"atq_sp": 1},           # Kricketot
    402: {"atq_sp": 2},           # Kricketune
    403: {"atq": 1},              # Shinx
    404: {"atq": 2},              # Luxio
    405: {"atq": 3},              # Luxray
    406: {"atq_sp": 1, "def_sp": 1}, # Budew
    407: {"atq_sp": 2, "def_sp": 1}, # Roserade
    408: {"atq": 1},              # Cranidos
    409: {"atq": 2},              # Rampardos
    410: {"def": 1},              # Shieldon
    411: {"def": 2},              # Bastiodon
    412: {"def": 1},              # Burmy
    413: {"def": 2},              # Wormadam (planta)
    414: {"vel": 2},              # Mothim
    415: {"vel": 1},              # Combee
    416: {"atq": 2},              # Vespiquen
    417: {"vel": 2},              # Pachirisu
    418: {"vel": 1},              # Buizel
    419: {"vel": 2},              # Floatzel
    420: {"atq_sp": 1},           # Cherubi
    421: {"atq_sp": 2},           # Cherrim
    422: {"def_sp": 1},           # Shellos
    423: {"def_sp": 2},           # Gastrodon
    424: {"vel": 2},              # Ambipom
    425: {"atq_sp": 1},           # Drifloon
    426: {"atq_sp": 2},           # Drifblim
    427: {"vel": 1},              # Buneary
    428: {"vel": 2},              # Lopunny
    429: {"atq_sp": 2},           # Mismagius
    430: {"vel": 2},              # Honchkrow
    431: {"vel": 1},              # Glameow
    432: {"vel": 2},              # Purugly
    433: {"def_sp": 1},           # Chingling
    434: {"atq": 1},              # Stunky
    435: {"atq": 2},              # Skuntank
    436: {"def": 1},              # Bronzor
    437: {"def": 2},              # Bronzong
    438: {"def": 2},              # Bonsly
    439: {"def_sp": 2},           # Mime Jr.
    440: {"hp": 1},               # Happiny
    441: {"atq_sp": 2},           # Chatot
    442: {"def_sp": 2},           # Spiritomb
    443: {"atq": 1},              # Gible
    444: {"atq": 2},              # Gabite
    445: {"atq": 3},              # Garchomp
    446: {"hp": 1},               # Munchlax
    447: {"atq": 1},              # Riolu
    448: {"atq": 2},              # Lucario
    449: {"def": 1},              # Hippopotas
    450: {"def": 2},              # Hippowdon
    451: {"vel": 1},              # Skorupi
    452: {"vel": 2},              # Drapion
    453: {"atq": 1},              # Croagunk
    454: {"atq": 2},              # Toxicroak
    455: {"atq_sp": 2},           # Carnivine
    456: {"def_sp": 1},           # Finneon
    457: {"def_sp": 2},           # Lumineon
    458: {"def_sp": 2},           # Mantyke
    459: {"def_sp": 1},           # Snover
    460: {"def_sp": 2},           # Abomasnow
    461: {"atq": 2},              # Weavile
    462: {"def_sp": 3},           # Magnezone
    463: {"hp": 2},               # Lickilicky
    464: {"atq": 2},              # Rhyperior
    465: {"def_sp": 2},           # Tangrowth
    466: {"vel": 3},              # Electivire
    467: {"atq_sp": 3},           # Magmortar
    468: {"def_sp": 3},           # Togekiss
    469: {"vel": 2},              # Yanmega
    470: {"def": 2},              # Leafeon
    471: {"def_sp": 2},           # Glaceon
    472: {"def": 2},              # Gliscor
    473: {"hp": 3},               # Mamoswine
    474: {"atq_sp": 3},           # Porygon-Z
    475: {"atq_sp": 2, "def_sp": 1}, # Gallade
    476: {"def": 3},              # Probopass
    477: {"def_sp": 3},           # Dusknoir
    478: {"atq_sp": 2},           # Froslass
    479: {"atq_sp": 1},           # Rotom
    480: {"hp": 3},               # Uxie
    481: {"atq_sp": 3},           # Mesprit
    482: {"vel": 3},              # Azelf
    483: {"atq": 3},              # Dialga
    484: {"atq_sp": 3},           # Palkia
    485: {"atq": 3},              # Heatran
    486: {"hp": 3},               # Regigigas
    487: {"atq_sp": 3},           # Giratina
    488: {"def_sp": 3},           # Cresselia
    489: {"hp": 1},               # Phione
    490: {"hp": 3},               # Manaphy
    491: {"atq_sp": 3},           # Darkrai
    492: {"atq_sp": 3},           # Shaymin
    493: {"hp": 3},               # Arceus

    # ══════════ GEN 5 (494–649) ══════════
    494: {"vel": 3},              # Victini
    495: {"def_sp": 1},           # Snivy
    496: {"def_sp": 2},           # Servine
    497: {"def_sp": 3},           # Serperior
    498: {"atq": 1},              # Tepig
    499: {"atq": 2},              # Pignite
    500: {"atq": 3},              # Emboar
    501: {"def_sp": 1},           # Oshawott
    502: {"def_sp": 2},           # Dewott
    503: {"def_sp": 3},           # Samurott
    504: {"vel": 1},              # Patrat
    505: {"vel": 2},              # Watchog
    506: {"vel": 1},              # Lillipup
    507: {"vel": 2},              # Herdier
    508: {"vel": 3},              # Stoutland
    509: {"vel": 1},              # Purrloin
    510: {"vel": 2},              # Liepard
    511: {"atq_sp": 1},           # Pansage
    512: {"atq_sp": 2},           # Simisage
    513: {"atq_sp": 1},           # Pansear
    514: {"atq_sp": 2},           # Simisear
    515: {"atq_sp": 1},           # Panpour
    516: {"atq_sp": 2},           # Simipour
    517: {"def_sp": 1},           # Munna
    518: {"def_sp": 2},           # Musharna
    519: {"vel": 1},              # Pidove
    520: {"vel": 2},              # Tranquill
    521: {"vel": 3},              # Unfezant
    522: {"vel": 1},              # Blitzle
    523: {"vel": 2},              # Zebstrika
    524: {"def": 1},              # Roggenrola
    525: {"def": 2},              # Boldore
    526: {"def": 3},              # Gigalith
    527: {"vel": 1},              # Woobat
    528: {"atq_sp": 2},           # Swoobat
    529: {"atq": 1},              # Drilbur
    530: {"atq": 2},              # Excadrill
    531: {"def_sp": 2},           # Audino
    532: {"atq": 1},              # Timburr
    533: {"atq": 2},              # Gurdurr
    534: {"atq": 3},              # Conkeldurr
    535: {"vel": 1},              # Tympole
    536: {"atq_sp": 2},           # Palpitoad
    537: {"hp": 2, "atq_sp": 1},  # Seismitoad
    538: {"atq": 2},              # Throh
    539: {"vel": 2},              # Sawk
    540: {"atq_sp": 1},           # Sewaddle
    541: {"atq_sp": 2},           # Swadloon
    542: {"atq_sp": 2, "def_sp": 1}, # Leavanny
    543: {"vel": 1},              # Venipede
    544: {"def": 2},              # Whirlipede
    545: {"vel": 2},              # Scolipede
    546: {"def_sp": 1},           # Cottonee
    547: {"def_sp": 2},           # Whimsicott
    548: {"atq_sp": 1},           # Petilil
    549: {"atq_sp": 2},           # Lilligant
    550: {"atq": 2},              # Basculin
    551: {"atq": 1},              # Sandile
    552: {"atq": 2},              # Krokorok
    553: {"atq": 3},              # Krookodile
    554: {"atq_sp": 1},           # Darumaka
    555: {"atq": 2},              # Darmanitan
    556: {"atq_sp": 1},           # Maractus
    557: {"def": 1},              # Dwebble
    558: {"def": 2},              # Crustle
    559: {"atq": 1},              # Scraggy
    560: {"atq": 2},              # Scrafty
    561: {"atq_sp": 2},           # Sigilyph
    562: {"def_sp": 1},           # Yamask
    563: {"def_sp": 2},           # Cofagrigus
    564: {"def": 1},              # Tirtouga
    565: {"def": 2},              # Carracosta
    566: {"vel": 1},              # Archen
    567: {"vel": 2},              # Archeops
    568: {"hp": 1},               # Trubbish
    569: {"hp": 2},               # Garbodor
    570: {"vel": 1},              # Zorua
    571: {"atq_sp": 2},           # Zoroark
    572: {"vel": 1},              # Minccino
    573: {"vel": 2},              # Cinccino
    574: {"def_sp": 1},           # Gothita
    575: {"def_sp": 2},           # Gothorita
    576: {"def_sp": 3},           # Gothitelle
    577: {"atq_sp": 1},           # Solosis
    578: {"atq_sp": 2},           # Duosion
    579: {"atq_sp": 3},           # Reuniclus
    580: {"vel": 1},              # Ducklett
    581: {"vel": 2},              # Swanna
    582: {"atq_sp": 1},           # Vanillite
    583: {"atq_sp": 2},           # Vanillish
    584: {"atq_sp": 3},           # Vanilluxe
    585: {"def_sp": 1},           # Deerling
    586: {"def_sp": 2},           # Sawsbuck
    587: {"vel": 2},              # Emolga
    588: {"def": 1},              # Karrablast
    589: {"atq": 2},              # Escavalier
    590: {"def_sp": 1},           # Foongus
    591: {"def_sp": 2},           # Amoonguss
    592: {"def_sp": 1},           # Frillish
    593: {"def_sp": 2},           # Jellicent
    594: {"hp": 2},               # Alomomola
    595: {"vel": 1},              # Joltik
    596: {"atq_sp": 2},           # Galvantula
    597: {"def": 1},              # Ferroseed
    598: {"def": 2},              # Ferrothorn
    599: {"atq_sp": 1},           # Klink
    600: {"atq_sp": 2},           # Klang
    601: {"atq_sp": 3},           # Klinklang
    602: {"atq_sp": 1},           # Tynamo
    603: {"atq_sp": 2},           # Eelektrik
    604: {"atq_sp": 3},           # Eelektross
    605: {"atq_sp": 1},           # Elgyem
    606: {"atq_sp": 3},           # Beheeyem
    607: {"atq_sp": 1},           # Litwick
    608: {"atq_sp": 2},           # Lampent
    609: {"atq_sp": 3},           # Chandelure
    610: {"atq": 1},              # Axew
    611: {"atq": 2},              # Fraxure
    612: {"atq": 3},              # Haxorus
    613: {"def_sp": 1},           # Cubchoo
    614: {"def_sp": 3},           # Beartic
    615: {"def_sp": 3},           # Cryogonal
    616: {"def": 1},              # Shelmet
    617: {"vel": 2},              # Accelgor
    618: {"def": 2},              # Stunfisk
    619: {"atq": 1},              # Mienfoo
    620: {"atq": 2},              # Mienshao
    621: {"atq": 2},              # Druddigon
    622: {"def": 1},              # Golett
    623: {"atq": 2},              # Golurk
    624: {"atq": 1},              # Pawniard
    625: {"atq": 2},              # Bisharp
    626: {"hp": 2},               # Bouffalant
    627: {"atq": 1},              # Rufflet
    628: {"atq": 3},              # Braviary
    629: {"atq": 1},              # Vullaby
    630: {"def": 2},              # Mandibuzz
    631: {"atq": 2},              # Heatmor
    632: {"def": 2},              # Durant
    633: {"atq_sp": 1},           # Deino
    634: {"atq_sp": 2},           # Zweilous
    635: {"atq_sp": 3},           # Hydreigon
    636: {"atq_sp": 1},           # Larvesta
    637: {"atq_sp": 3},           # Volcarona
    638: {"def": 3},              # Cobalion
    639: {"atq": 3},              # Terrakion
    640: {"vel": 3},              # Virizion
    641: {"atq_sp": 3},           # Tornadus
    642: {"atq_sp": 3},           # Thundurus
    643: {"atq_sp": 3},           # Reshiram
    644: {"atq": 3},              # Zekrom
    645: {"atq": 3},              # Landorus
    646: {"atq_sp": 3},           # Kyurem
    647: {"vel": 3},              # Keldeo
    648: {"atq_sp": 3},           # Meloetta
    649: {"atq": 3},              # Genesect

    # ══════════ GEN 6 (650–721) ══════════
    650: {"def": 1},              # Chespin
    651: {"def": 2},              # Quilladin
    652: {"def": 2, "atq": 1},    # Chesnaught
    653: {"atq_sp": 1},           # Fennekin
    654: {"atq_sp": 2},           # Braixen
    655: {"atq_sp": 3},           # Delphox
    656: {"vel": 1},              # Froakie
    657: {"vel": 2},              # Frogadier
    658: {"vel": 3},              # Greninja
    659: {"atq": 1},              # Bunnelby
    660: {"atq": 2},              # Diggersby
    661: {"vel": 1},              # Fletchling
    662: {"vel": 2},              # Fletchinder
    663: {"vel": 3},              # Talonflame
    664: {"def": 1},              # Scatterbug
    665: {"def": 2},              # Spewpa
    666: {"atq_sp": 2},           # Vivillon
    667: {"atq": 1},              # Litleo
    668: {"atq_sp": 2},           # Pyroar
    669: {"atq_sp": 1},           # Flabébé
    670: {"atq_sp": 2},           # Floette
    671: {"atq_sp": 3},           # Florges
    672: {"def": 1},              # Skiddo
    673: {"def": 2},              # Gogoat
    674: {"atq": 1},              # Pancham
    675: {"atq": 2},              # Pangoro
    676: {"vel": 2},              # Furfrou
    677: {"atq_sp": 1},           # Espurr
    678: {"atq_sp": 2},           # Meowstic
    679: {"atq": 1},              # Honedge
    680: {"atq": 2},              # Doublade
    681: {"atq": 3},              # Aegislash
    682: {"def_sp": 1},           # Spritzee
    683: {"def_sp": 2},           # Aromatisse
    684: {"atq_sp": 1},           # Swirlix
    685: {"atq_sp": 2},           # Slurpuff
    686: {"atq_sp": 1},           # Inkay
    687: {"atq_sp": 2},           # Malamar
    688: {"def": 1},              # Binacle
    689: {"atq": 2},              # Barbaracle
    690: {"def_sp": 1},           # Skrelp
    691: {"atq_sp": 2},           # Dragalge
    692: {"atq": 1},              # Clauncher
    693: {"atq_sp": 2},           # Clawitzer
    694: {"vel": 1},              # Helioptile
    695: {"vel": 2},              # Heliolisk
    696: {"atq": 1},              # Tyrunt
    697: {"atq": 2},              # Tyrantrum
    698: {"def_sp": 1},           # Amaura
    699: {"def_sp": 2},           # Aurorus
    700: {"def_sp": 2},           # Sylveon
    701: {"vel": 2},              # Hawlucha
    702: {"vel": 2},              # Dedenne
    703: {"def": 1, "def_sp": 1}, # Carbink
    704: {"atq_sp": 1},           # Goomy
    705: {"def_sp": 2},           # Sliggoo
    706: {"def_sp": 3},           # Goodra
    707: {"def": 2},              # Klefki
    708: {"def_sp": 1},           # Phantump
    709: {"def_sp": 2},           # Trevenant
    710: {"atq_sp": 1},           # Pumpkaboo
    711: {"atq_sp": 2},           # Gourgeist
    712: {"def": 1},              # Bergmite
    713: {"def": 2},              # Avalugg
    714: {"vel": 1},              # Noibat
    715: {"atq_sp": 3},           # Noivern
    716: {"def_sp": 3},           # Xerneas
    717: {"atq": 3},              # Yveltal
    718: {"def": 3},              # Zygarde
    719: {"def": 3},              # Diancie
    720: {"atq_sp": 3},           # Hoopa
    721: {"vel": 3},              # Volcanion

    # ══════════ GEN 7 (722–809) ══════════
    722: {"vel": 1},              # Rowlet
    723: {"vel": 2},              # Dartrix
    724: {"vel": 3},              # Decidueye
    725: {"atq": 1},              # Litten
    726: {"atq": 2},              # Torracat
    727: {"atq": 3},              # Incineroar
    728: {"def_sp": 1},           # Popplio
    729: {"def_sp": 2},           # Brionne
    730: {"def_sp": 3},           # Primarina
    731: {"vel": 1},              # Pikipek
    732: {"vel": 2},              # Trumbeak
    733: {"vel": 3},              # Toucannon
    734: {"hp": 1},               # Yungoos
    735: {"hp": 2},               # Gumshoos
    736: {"vel": 1},              # Grubbin
    737: {"vel": 2},              # Charjabug
    738: {"atq_sp": 3},           # Vikavolt
    739: {"def": 1},              # Crabrawler
    740: {"def": 2},              # Crabominable
    741: {"vel": 2},              # Oricorio
    742: {"vel": 1},              # Cutiefly
    743: {"atq_sp": 2},           # Ribombee
    744: {"atq": 1},              # Rockruff
    745: {"atq": 2},              # Lycanroc
    746: {"vel": 2},              # Wishiwashi
    747: {"vel": 1},              # Mareanie
    748: {"def_sp": 2},           # Toxapex
    749: {"atq": 1},              # Mudbray
    750: {"atq": 2},              # Mudsdale
    751: {"def": 1},              # Dewpider
    752: {"def": 2},              # Araquanid
    753: {"atq_sp": 1},           # Fomantis
    754: {"atq_sp": 2},           # Lurantis
    755: {"atq_sp": 1},           # Morelull
    756: {"atq_sp": 2},           # Shiinotic
    757: {"atq_sp": 1},           # Salandit
    758: {"atq_sp": 2},           # Salazzle
    759: {"def": 1},              # Stufful
    760: {"atq": 2},              # Bewear
    761: {"hp": 1},               # Bounsweet
    762: {"hp": 2},               # Steenee
    763: {"hp": 3},               # Tsareena
    764: {"atq_sp": 2},           # Comfey
    765: {"def": 2},              # Oranguru
    766: {"vel": 2},              # Passimian
    767: {"def": 1},              # Wimpod
    768: {"def": 2},              # Golisopod
    769: {"def": 1},              # Sandygast
    770: {"def": 2},              # Palossand
    771: {"def_sp": 1},           # Pyukumuku
    772: {"def_sp": 1},           # Type: Null
    773: {"def_sp": 3},           # Silvally
    774: {"vel": 2},              # Minior
    775: {"def": 2},              # Komala
    776: {"atq_sp": 2},           # Turtonator
    777: {"vel": 2},              # Togedemaru
    778: {"atq_sp": 2},           # Mimikyu
    779: {"atq": 2},              # Bruxish
    780: {"atq_sp": 2},           # Drampa
    781: {"def": 2},              # Dhelmise
    782: {"atq": 1},              # Jangmo-o
    783: {"atq": 2},              # Hakamo-o
    784: {"atq": 3},              # Kommo-o
    785: {"vel": 3},              # Tapu Koko
    786: {"def_sp": 3},           # Tapu Lele
    787: {"def": 3},              # Tapu Bulu
    788: {"def_sp": 3},           # Tapu Fini
    789: {"atq_sp": 3},           # Cosmog
    790: {"atq_sp": 3},           # Cosmoem
    791: {"atq_sp": 3},           # Solgaleo
    792: {"def_sp": 3},           # Lunala
    793: {"hp": 3},               # Nihilego
    794: {"atq": 3},              # Buzzwole
    795: {"atq_sp": 3},           # Pheromosa
    796: {"atq_sp": 3},           # Xurkitree
    797: {"atq": 3},              # Celesteela
    798: {"atq": 3},              # Kartana
    799: {"atq": 3},              # Guzzlord
    800: {"atq_sp": 3},           # Necrozma
    801: {"hp": 3},               # Magearna
    802: {"atq": 3},              # Marshadow
    803: {"vel": 1},              # Poipole
    804: {"atq_sp": 3},           # Naganadel
    805: {"def": 3},              # Stakataka
    806: {"vel": 3},              # Blacephalon
    807: {"vel": 3},              # Zeraora
    808: {"hp": 1},               # Meltan
    809: {"hp": 3},               # Melmetal

    # ══════════ GEN 8 (810–905) ══════════
    810: {"vel": 1},              # Grookey
    811: {"vel": 2},              # Thwackey
    812: {"atq": 3},              # Rillaboom
    813: {"atq_sp": 1},           # Scorbunny
    814: {"vel": 2},              # Raboot
    815: {"vel": 3},              # Cinderace
    816: {"def_sp": 1},           # Sobble
    817: {"atq_sp": 2},           # Drizzile
    818: {"atq_sp": 3},           # Inteleon
    819: {"vel": 1},              # Skwovet
    820: {"hp": 2},               # Greedent
    821: {"vel": 1},              # Rookidee
    822: {"vel": 2},              # Corvisquire
    823: {"vel": 3},              # Corviknight
    824: {"def": 1},              # Blipbug
    825: {"atq_sp": 1},           # Dottler
    826: {"atq_sp": 2},           # Orbeetle
    827: {"vel": 1},              # Nickit
    828: {"vel": 2},              # Thievul
    829: {"atq_sp": 1},           # Gossifleur
    830: {"atq_sp": 2},           # Eldegoss
    831: {"hp": 1},               # Wooloo
    832: {"hp": 2},               # Dubwool
    833: {"atq": 1},              # Chewtle
    834: {"atq": 2},              # Drednaw
    835: {"vel": 1},              # Yamper
    836: {"vel": 2},              # Boltund
    837: {"def": 1},              # Rolycoly
    838: {"def": 2},              # Carkol
    839: {"def": 3},              # Coalossal
    840: {"def_sp": 1},           # Applin
    841: {"def_sp": 2},           # Flapple
    842: {"def_sp": 2},           # Appletun
    843: {"def_sp": 1},           # Silicobra
    844: {"def_sp": 2},           # Sandaconda
    845: {"vel": 2},              # Cramorant
    846: {"vel": 1},              # Arrokuda
    847: {"vel": 3},              # Barraskewda
    848: {"atq": 1},              # Toxel
    849: {"atq_sp": 2},           # Toxtricity
    850: {"atq": 1},              # Sizzlipede
    851: {"vel": 3},              # Centiskorch
    852: {"def": 1},              # Clobbopus
    853: {"def": 2},              # Grapploct
    854: {"def_sp": 1},           # Sinistea
    855: {"def_sp": 2},           # Polteageist
    856: {"atq_sp": 1},           # Hatenna
    857: {"atq_sp": 2},           # Hattrem
    858: {"atq_sp": 3},           # Hatterene
    859: {"atq": 1},              # Impidimp
    860: {"atq": 2},              # Morgrem
    861: {"atq": 3},              # Grimmsnarl
    862: {"def": 3},              # Obstagoon
    863: {"vel": 3},              # Perrserker
    864: {"def_sp": 3},           # Cursola
    865: {"atq": 2},              # Sirfetch'd
    866: {"def_sp": 2},           # Mr. Rime
    867: {"def_sp": 2},           # Runerigus
    868: {"atq_sp": 1},           # Milcery
    869: {"atq_sp": 2},           # Alcremie
    870: {"atq": 2},              # Falinks
    871: {"vel": 2},              # Pincurchin
    872: {"def_sp": 1},           # Snom
    873: {"def_sp": 2},           # Frosmoth
    874: {"def": 2},              # Stonjourner
    875: {"def": 2},              # Eiscue
    876: {"atq_sp": 2},           # Indeedee
    877: {"vel": 2},              # Morpeko
    878: {"def": 1},              # Cufant
    879: {"def": 2},              # Copperajah
    880: {"atq": 3},              # Dracozolt
    881: {"def": 3},              # Arctozolt
    882: {"atq_sp": 3},           # Dracovish
    883: {"hp": 3},               # Arctovish
    884: {"atq": 3},              # Duraludon
    885: {"vel": 1},              # Dreepy
    886: {"vel": 2},              # Drakloak
    887: {"vel": 3},              # Dragapult
    888: {"def": 3},              # Zacian
    889: {"atq": 3},              # Zamazenta
    890: {"hp": 3},               # Eternatus
    891: {"atq": 3},              # Kubfu
    892: {"atq": 3},              # Urshifu
    893: {"hp": 3},               # Zarude
    894: {"atq": 3},              # Regieleki
    895: {"def_sp": 3},           # Regidrago
    896: {"vel": 3},              # Glastrier
    897: {"def_sp": 3},           # Spectrier
    898: {"def_sp": 3},           # Calyrex
    899: {"hp": 2},               # Wyrdeer
    900: {"atq": 2},              # Kleavor
    901: {"def_sp": 3},           # Ursaluna
    902: {"vel": 3},              # Basculegion
    903: {"atq": 3},              # Sneasler
    904: {"def": 3},              # Overqwil
    905: {"atq_sp": 3},           # Enamorus

    # ══════════ GEN 9 (906–1025) ══════════
    906: {"def_sp": 1},           # Sprigatito
    907: {"def_sp": 2},           # Floragato
    908: {"def_sp": 3},           # Meowscarada
    909: {"atq": 1},              # Fuecoco
    910: {"atq": 2},              # Crocalor
    911: {"atq_sp": 3},           # Skeledirge
    912: {"vel": 1},              # Quaxly
    913: {"vel": 2},              # Quaxwell
    914: {"vel": 3},              # Quaquaval
    915: {"vel": 1},              # Lechonk
    916: {"hp": 2},               # Oinkologne
    917: {"def": 1},              # Tarountula
    918: {"def": 2},              # Spidops
    919: {"atq": 1},              # Nymble
    920: {"vel": 2},              # Lokix
    921: {"def_sp": 1},           # Pawmi
    922: {"vel": 2},              # Pawmo
    923: {"vel": 3},              # Pawmot
    924: {"def_sp": 1},           # Tandemaus
    925: {"def_sp": 2},           # Maushold
    926: {"vel": 1},              # Fidough
    927: {"vel": 2},              # Dachsbun
    928: {"atq_sp": 1},           # Smoliv
    929: {"atq_sp": 2},           # Dolliv
    930: {"atq_sp": 3},           # Arboliva
    931: {"vel": 2},              # Squawkabilly
    932: {"atq": 1},              # Nacli
    933: {"atq": 2},              # Naclstack
    934: {"def": 3},              # Garganacl
    935: {"atq_sp": 1},           # Charcadet
    936: {"atq_sp": 3},           # Armarouge
    937: {"atq": 3},              # Ceruledge
    938: {"def_sp": 1},           # Tadbulb
    939: {"atq_sp": 2},           # Bellibolt
    940: {"vel": 1},              # Wattrel
    941: {"vel": 2},              # Kilowattrel
    942: {"def": 1},              # Maschiff
    943: {"atq": 2},              # Mabosstiff
    944: {"def_sp": 1},           # Shroodle
    945: {"atq_sp": 2},           # Grafaiai
    946: {"vel": 1},              # Bramblin
    947: {"vel": 2},              # Brambleghast
    948: {"atq_sp": 1},           # Toedscool
    949: {"atq_sp": 2},           # Toedscruel
    950: {"atq": 1},              # Klawf
    951: {"atq": 2},              # Capsakid
    952: {"atq_sp": 3},           # Scovillain
    953: {"vel": 1},              # Rellor
    954: {"vel": 2},              # Rabsca
    955: {"def_sp": 1},           # Flittle
    956: {"def_sp": 2},           # Espathra
    957: {"def": 1},              # Tinkatink
    958: {"def": 2},              # Tinkatuff
    959: {"def": 3},              # Tinkaton
    960: {"vel": 2},              # Wiglett
    961: {"vel": 3},              # Wugtrio
    962: {"atq": 2},              # Bombirdier
    963: {"def": 1},              # Finizen
    964: {"hp": 3},               # Palafin
    965: {"atq": 2},              # Varoom
    966: {"atq": 3},              # Revavroom
    967: {"vel": 2},              # Cyclizar
    968: {"def_sp": 2},           # Orthworm
    969: {"hp": 2},               # Glimmet
    970: {"atq_sp": 3},           # Glimmora
    971: {"atq": 2},              # Greavard
    972: {"atq": 3},              # Houndstone
    973: {"vel": 2},              # Flamigo
    974: {"def": 1},              # Cetoddle
    975: {"hp": 3},               # Cetitan
    976: {"vel": 2},              # Veluza
    977: {"atq_sp": 3},           # Dondozo
    978: {"vel": 3},              # Tatsugiri
    979: {"atq": 3},              # Annihilape
    980: {"def": 3},              # Clodsire
    981: {"atq_sp": 3},           # Farigiraf
    982: {"def": 2},              # Dudunsparce
    983: {"def": 3},              # Kingambit
    984: {"hp": 3},               # Great Tusk
    985: {"atq": 3},              # Scream Tail
    986: {"def_sp": 3},           # Brute Bonnet
    987: {"vel": 3},              # Flutter Mane
    988: {"def_sp": 3},           # Slither Wing
    989: {"atq": 3},              # Sandy Shocks
    990: {"def": 3},              # Iron Treads
    991: {"vel": 3},              # Iron Bundle
    992: {"atq": 3},              # Iron Hands
    993: {"atq_sp": 3},           # Iron Jugulis
    994: {"atq_sp": 3},           # Iron Moth
    995: {"def": 3},              # Iron Thorns
    996: {"atq_sp": 3},           # Frigibax
    997: {"atq_sp": 3},           # Arctibax
    998: {"atq_sp": 3},           # Baxcalibur
    999: {"def_sp": 3},           # Gimmighoul
    1000: {"hp": 3},              # Gholdengo
    1001: {"atq_sp": 3},          # Wo-Chien
    1002: {"def_sp": 3},          # Chien-Pao
    1003: {"atq": 3},             # Ting-Lu
    1004: {"vel": 3},             # Chi-Yu
    1005: {"atq": 3},             # Roaring Moon
    1006: {"vel": 3},             # Iron Valiant
    1007: {"hp": 3},              # Koraidon
    1008: {"vel": 3},             # Miraidon
    1009: {"vel": 2},             # Walking Wake
    1010: {"atq_sp": 2},          # Iron Leaves
    1011: {"hp": 1},              # Dipplin
    1012: {"vel": 1},             # Poltchageist
    1013: {"vel": 2},             # Sinistcha
    1014: {"atq": 1},             # Okidogi
    1015: {"def_sp": 1},          # Munkidori
    1016: {"atq_sp": 1},          # Fezandipiti
    1017: {"hp": 3},              # Ogerpon
    1018: {"atq": 3},             # Archaludon
    1019: {"hp": 3},              # Hydrapple
    1020: {"def": 3},             # Gouging Fire
    1021: {"vel": 3},             # Raging Bolt
    1022: {"atq": 3},             # Iron Boulder
    1023: {"vel": 3},             # Iron Crown
    1024: {"hp": 3},              # Terapagos
    1025: {"atq_sp": 3},          # Pecharunt
}


# ─────────────────────────────────────────────────────────────────────────────
# SERVICIO DE EVS
# ─────────────────────────────────────────────────────────────────────────────

class EVService:
    """Servicio para gestionar la ganancia y aplicación de EVs en batalla."""

    @staticmethod
    def obtener_yield(pokemon_id: int) -> Dict[str, int]:
        """
        Retorna los EVs que otorga un Pokémon al ser derrotado.
        Retorna dict vacío si no hay datos (no crashea).
        """
        return EV_YIELDS.get(int(pokemon_id), {})

    @staticmethod
    def otorgar_evs(
        ganador_id: int,
        derrotado_pokemon_id: int,
    ) -> Tuple[Dict[str, int], str]:
        """
        Aplica los EVs del Pokémon derrotado al Pokémon ganador.
        Respeta los caps: 252 por stat, 510 total.

        Args:
            ganador_id:          id_unico del Pokémon que ganó (activo en batalla).
            derrotado_pokemon_id: pokemonID (especie) del Pokémon derrotado.

        Returns:
            (evs_ganados, texto_log)
            evs_ganados: {stat: cantidad_real_ganada}
            texto_log:   cadena para mostrar al usuario ("" si no ganó nada)
        """
        from database import db_manager

        yield_data = EVService.obtener_yield(derrotado_pokemon_id)
        # No se hace early-return si yield_data está vacío: el objeto recio
        # garantiza sus 8 EVs independientemente del yield del enemigo.

        try:
            # Leer EVs actuales del ganador
            result = db_manager.execute_query(
                """SELECT ev_hp, ev_atq, ev_def, ev_atq_sp, ev_def_sp, ev_vel
                   FROM POKEMON_USUARIO WHERE id_unico = ?""",
                (ganador_id,),
            )
            if not result:
                return {}, ""

            row = dict(result[0])
            evs_actuales = {
                "hp":     int(row.get("ev_hp",     0) or 0),
                "atq":    int(row.get("ev_atq",    0) or 0),
                "def":    int(row.get("ev_def",    0) or 0),
                "atq_sp": int(row.get("ev_atq_sp", 0) or 0),
                "def_sp": int(row.get("ev_def_sp", 0) or 0),
                "vel":    int(row.get("ev_vel",    0) or 0),
            }
            total_actual = sum(evs_actuales.values())

            if total_actual >= EV_MAX_TOTAL:
                return {}, ""  # Pokémon ya tiene los EVs llenos

            evs_ganados: Dict[str, int] = {}

            # ── Yield del Pokémon derrotado ──────────────────────────────────
            for stat, cantidad in yield_data.items():
                if stat not in _STAT_COLUMNA:
                    continue
                espacio_stat  = EV_MAX_POR_STAT - evs_actuales.get(stat, 0)
                espacio_total = EV_MAX_TOTAL    - total_actual
                real = min(cantidad, espacio_stat, espacio_total)

                if real > 0:
                    evs_actuales[stat]  = evs_actuales.get(stat, 0) + real
                    total_actual       += real
                    evs_ganados[stat]   = evs_ganados.get(stat, 0) + real

                if total_actual >= EV_MAX_TOTAL:
                    break

            # ── Bonus garantizado de Objetos Recios ──────────────────────────
            # Se aplica SIEMPRE que el total no esté al máximo, incluso si el
            # enemigo no otorgó EVs en ese stat (o no otorgó EVs en absoluto).
            try:
                obj_row = db_manager.execute_query(
                    "SELECT objeto FROM POKEMON_USUARIO WHERE id_unico = ?",
                    (ganador_id,),
                )
                if obj_row and obj_row[0].get("objeto"):
                    obj_key    = str(obj_row[0]["objeto"]).lower().replace("_", " ")
                    bonus_stat = POWER_ITEM_EV_MAP.get(obj_key)
                    if bonus_stat:
                        # Objeto recio: cancela TODOS los EVs naturales ganados
                        # y otorga solo los 8 fijos del objeto en su stat
                        for s in list(evs_ganados.keys()):
                            if s != bonus_stat:
                                evs_actuales[s] = evs_actuales.get(s, 0) - evs_ganados[s]
                                total_actual   -= evs_ganados[s]
                        evs_ganados = {k: v for k, v in evs_ganados.items() if k == bonus_stat}

                        espacio_s = EV_MAX_POR_STAT - evs_actuales.get(bonus_stat, 0)
                        espacio_t = EV_MAX_TOTAL    - total_actual
                        real_b    = min(POWER_ITEM_EV_BONUS, espacio_s, espacio_t)
                        if real_b > 0:
                            evs_actuales[bonus_stat]  = evs_actuales.get(bonus_stat, 0) + real_b
                            total_actual             += real_b
                            evs_ganados[bonus_stat]   = evs_ganados.get(bonus_stat, 0) + real_b
            except Exception as _pi_err:
                logger.debug(f"[EV] Bonus objeto recio: {_pi_err}")

            if not evs_ganados:
                return {}, ""

            # Persistir en BD
            updates = {_STAT_COLUMNA[s]: evs_actuales[s] for s in evs_actuales}
            set_clause = ", ".join(f"{col} = ?" for col in updates)
            db_manager.execute_update(
                f"UPDATE POKEMON_USUARIO SET {set_clause} WHERE id_unico = ?",
                (*updates.values(), ganador_id),
            )

            # Recalcular stats cacheadas (los EVs afectan la fórmula)
            EVService._recalcular_stats_con_evs(ganador_id)

            # Construir texto de log
            _NOMBRES = {
                "hp": "PS", "atq": "Ataque", "def": "Defensa",
                "atq_sp": "At.Esp.", "def_sp": "Def.Esp.", "vel": "Velocidad",
            }
            partes = [f"+{v} {_NOMBRES.get(s, s)}" for s, v in evs_ganados.items()]
            texto = "  📈 EVs: " + ", ".join(partes) + "\n"

            logger.info(
                f"[EV] Pokémon {ganador_id} ganó EVs: {evs_ganados} "
                f"(total: {total_actual}/{EV_MAX_TOTAL})"
            )
            return evs_ganados, texto

        except Exception as e:
            logger.error(f"[EV] Error otorgando EVs: {e}", exc_info=True)
            return {}, ""

    @staticmethod
    def _recalcular_stats_con_evs(pokemon_id: int) -> None:
        """Recalcula y persiste las stats cacheadas cuando cambian los EVs."""
        try:
            from database import db_manager
            from pokemon.services.pokemon_service import pokemon_service
            from pokemon.services.pokedex_service import pokedex_service as pdx

            p = pokemon_service.obtener_pokemon(pokemon_id)
            if not p:
                return

            stats = pdx.calcular_stats(
                p.pokemonID, p.nivel, p.ivs, p.evs, p.naturaleza
            )
            db_manager.execute_update(
                """UPDATE POKEMON_USUARIO
                   SET ps = ?, atq = ?, def = ?, atq_sp = ?, def_sp = ?, vel = ?
                   WHERE id_unico = ?""",
                (
                    stats["hp"],   stats["atq"], stats["def"],
                    stats["atq_sp"], stats["def_sp"], stats["vel"],
                    pokemon_id,
                ),
            )
        except Exception as e:
            logger.error(f"[EV] Error recalculando stats: {e}")


# Instancia global
ev_service = EVService()
