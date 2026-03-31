# -*- coding: utf-8 -*-
"""
pokemon/region_config.py
════════════════════════════════════════════════════════════════════════════════
Fuente de verdad central para todas las regiones Pokémon.
Cubre generaciones 1–9 (Kanto → Paldea).

Contiene:
  · REGION_STARTERS      — starters por región
  · REGION_LEADERS       — líderes, alto mando y campeón por región
  · REGION_WILD_IDS      — Pokémon válidos como salvajes por región
  · Helpers de acceso
════════════════════════════════════════════════════════════════════════════════
"""

# ── Legendarios/míticos excluidos de spawns salvajes ─────────────────────────
_LEGENDARIOS: set = {
    # Kanto
    144, 145, 146, 150, 151,
    # Johto
    243, 244, 245, 249, 250, 251,
    # Hoenn
    377, 378, 379, 380, 381, 382, 383, 384, 385, 386,
    # Sinnoh
    480, 481, 482, 483, 484, 485, 486, 487, 488,
    489, 490, 491, 492, 493,
    # Teselia
    494, 638, 639, 640, 641, 642, 643, 644, 645, 646, 647, 648, 649,
    # Kalos
    716, 717, 718, 719, 720, 721,
    # Alola
    785, 786, 787, 788, 789, 790, 791, 792,
    793, 794, 795, 796, 797, 798, 799, 800,
    801, 802, 803, 804, 805, 806, 807, 808, 809,
    # Galar
    888, 889, 890, 891, 892, 893, 894, 895, 896, 897, 898,
    # Hisui (DLC Sinnoh)
    905,
    # Paldea (Cuarteto + Singulares)
    1001, 1002, 1003, 1004, 1007, 1008,
    # Paradox legendarios (Tera Raids exclusivos)
    1009, 1010,
}

# ══════════════════════════════════════════════════════════════════════════════
# STARTERS POR REGIÓN
# ══════════════════════════════════════════════════════════════════════════════

REGION_STARTERS = {
    "KANTO": [
        {"nombre": "Bulbasaur",   "id": 1,   "emoji": "🌿", "callback": "starter_1"},
        {"nombre": "Charmander",  "id": 4,   "emoji": "🔥", "callback": "starter_4"},
        {"nombre": "Squirtle",    "id": 7,   "emoji": "💧", "callback": "starter_7"},
    ],
    "JOHTO": [
        {"nombre": "Chikorita",   "id": 152, "emoji": "🌿", "callback": "starter_152"},
        {"nombre": "Cyndaquil",   "id": 155, "emoji": "🔥", "callback": "starter_155"},
        {"nombre": "Totodile",    "id": 158, "emoji": "💧", "callback": "starter_158"},
    ],
    "HOENN": [
        {"nombre": "Treecko",     "id": 252, "emoji": "🌿", "callback": "starter_252"},
        {"nombre": "Torchic",     "id": 255, "emoji": "🔥", "callback": "starter_255"},
        {"nombre": "Mudkip",      "id": 258, "emoji": "💧", "callback": "starter_258"},
    ],
    "SINNOH": [
        {"nombre": "Turtwig",     "id": 387, "emoji": "🌿", "callback": "starter_387"},
        {"nombre": "Chimchar",    "id": 390, "emoji": "🔥", "callback": "starter_390"},
        {"nombre": "Piplup",      "id": 393, "emoji": "💧", "callback": "starter_393"},
    ],
    "TESELIA": [
        {"nombre": "Snivy",       "id": 495, "emoji": "🌿", "callback": "starter_495"},
        {"nombre": "Tepig",       "id": 498, "emoji": "🔥", "callback": "starter_498"},
        {"nombre": "Oshawott",    "id": 501, "emoji": "💧", "callback": "starter_501"},
    ],
    "KALOS": [
        {"nombre": "Chespin",     "id": 650, "emoji": "🌿", "callback": "starter_650"},
        {"nombre": "Fennekin",    "id": 653, "emoji": "🔥", "callback": "starter_653"},
        {"nombre": "Froakie",     "id": 656, "emoji": "💧", "callback": "starter_656"},
    ],
    "ALOLA": [
        {"nombre": "Rowlet",      "id": 722, "emoji": "🌿", "callback": "starter_722"},
        {"nombre": "Litten",      "id": 725, "emoji": "🔥", "callback": "starter_725"},
        {"nombre": "Popplio",     "id": 728, "emoji": "💧", "callback": "starter_728"},
    ],
    "GALAR": [
        {"nombre": "Grookey",     "id": 810, "emoji": "🌿", "callback": "starter_810"},
        {"nombre": "Scorbunny",   "id": 813, "emoji": "🔥", "callback": "starter_813"},
        {"nombre": "Sobble",      "id": 816, "emoji": "💧", "callback": "starter_816"},
    ],
    "PALDEA": [
        {"nombre": "Sprigatito",  "id": 906, "emoji": "🌿", "callback": "starter_906"},
        {"nombre": "Fuecoco",     "id": 909, "emoji": "🔥", "callback": "starter_909"},
        {"nombre": "Quaxly",      "id": 912, "emoji": "💧", "callback": "starter_912"},
    ],
}

# ══════════════════════════════════════════════════════════════════════════════
# LÍDERES, ALTO MANDO Y CAMPEÓN POR REGIÓN
# Formato: (lider_id, nombre, titulo, tipo, medalla, nivel_equipo,
#           recompensa_base, descripcion, activo)
# ══════════════════════════════════════════════════════════════════════════════

REGION_LEADERS = {

    # ── KANTO (FRLG) ─────────────────────────────────────────────────────────
    "KANTO": [
        ("brock",            "Brock",     "El Titán Roca",              "Roca",     "Medalla Roca",      14, 1400,  "Especialista en tipo Roca",      1),
        ("misty",            "Misty",     "La Sirena Cascada",           "Agua",     "Medalla Cascada",   21, 2100,  "Especialista en tipo Agua",      1),
        ("surge",            "Lt. Surge", "El Americano Relámpago",      "Eléctrico","Medalla Trueno",    24, 2400,  "Especialista en tipo Eléctrico", 1),
        ("erika",            "Erika",     "La Princesa de la Naturaleza","Planta",   "Medalla Arcoíris",  29, 2900,  "Especialista en tipo Planta",    1),
        ("koga",             "Koga",      "El Ninja Venenoso",            "Veneno",  "Medalla Alma",      43, 4300,  "Especialista en tipo Veneno",    1),
        ("sabrina",          "Sabrina",   "La Amo Psíquica",              "Psíquico","Medalla Pantano",   43, 4300,  "Especialista en tipo Psíquico",  1),
        ("blaine",           "Blaine",    "El Hombre Llama",              "Fuego",   "Medalla Volcán",    47, 4700,  "Especialista en tipo Fuego",     1),
        ("giovanni",         "Giovanni",  "El Jefe del Team Rocket",      "Tierra",  "Medalla Tierra",    50, 5000,  "Especialista en tipo Tierra",    1),
        # Alto Mando
        ("kanto_e4_lorelei", "Lorelei",   "Alto Mando Kanto",  "Hielo",    "—", 56,  7000, "Especialista en tipo Hielo",    1),
        ("kanto_e4_bruno",   "Bruno",     "Alto Mando Kanto",  "Lucha",    "—", 56,  7500, "Especialista en tipo Lucha",    1),
        ("kanto_e4_agatha",  "Agatha",    "Alto Mando Kanto",  "Fantasma", "—", 58,  8000, "Especialista en tipo Fantasma", 1),
        ("kanto_e4_lance",   "Lance",     "Alto Mando Kanto",  "Dragón",   "—", 60,  9000, "Especialista en tipo Dragón",   1),
        ("kanto_champion",   "Blue",      "Campeón de Kanto",  "Mixto",    "—", 65, 15000, "Campeón de la Liga de Kanto",   1),
    ],

    # ── JOHTO (HGSS) ─────────────────────────────────────────────────────────
    "JOHTO": [
        ("johto_falkner",    "Falkner",  "El Maestro del Viento",        "Volador", "Medalla Zafiro",    9,   900, "Especialista en tipo Volador",  1),
        ("johto_bugsy",      "Bugsy",    "El Investigador de Bichos",     "Bicho",   "Medalla Colmena",  16,  1600, "Especialista en tipo Bicho",    1),
        ("johto_whitney",    "Whitney",  "La Encantadora",                 "Normal",  "Medalla Pradera",  19,  1900, "Especialista en tipo Normal",   1),
        ("johto_morty",      "Morty",    "El Vidente Místico",             "Fantasma","Medalla Niebla",   25,  2500, "Especialista en tipo Fantasma", 1),
        ("johto_chuck",      "Chuck",    "El Maestro de Lucha",            "Lucha",   "Medalla Tormenta", 30,  3000, "Especialista en tipo Lucha",    1),
        ("johto_jasmine",    "Jasmine",  "La Chica de Acero",              "Acero",   "Medalla Mineral",  35,  3500, "Especialista en tipo Acero",    1),
        ("johto_pryce",      "Pryce",    "El Maestro del Hielo",           "Hielo",   "Medalla Glaciar",  31,  3100, "Especialista en tipo Hielo",    1),
        ("johto_clair",      "Clair",    "La Reina Dragón",                "Dragón",  "Medalla Ascenso",  41,  4100, "Especialista en tipo Dragón",   1),
        # Alto Mando
        ("johto_e4_will",    "Will",    "Alto Mando Johto",  "Psíquico",  "—", 42,  6000, "Especialista en tipo Psíquico",  1),
        ("johto_e4_koga",    "Koga",    "Alto Mando Johto",  "Veneno",    "—", 44,  6500, "Especialista en tipo Veneno",    1),
        ("johto_e4_bruno",   "Bruno",   "Alto Mando Johto",  "Lucha",     "—", 46,  7000, "Especialista en tipo Lucha",     1),
        ("johto_e4_karen",   "Karen",   "Alto Mando Johto",  "Siniestro", "—", 47,  7500, "Especialista en tipo Siniestro", 1),
        ("johto_champion",   "Lance",   "Campeón de Johto",  "Dragón",    "—", 50, 15000, "Campeón de la Liga de Johto",    1),
    ],

    # ── HOENN (ORAS) ──────────────────────────────────────────────────────────
    "HOENN": [
        ("hoenn_roxanne",    "Roxanne",   "La Chica Roca",               "Roca",     "Medalla Piedra",      15,  1500, "Especialista en tipo Roca",      1),
        ("hoenn_brawly",     "Brawly",    "El Tipo de Surf",              "Lucha",    "Medalla Nudillo",     18,  1800, "Especialista en tipo Lucha",     1),
        ("hoenn_wattson",    "Wattson",   "El Hombre Feliz",              "Eléctrico","Medalla Dínamo",      26,  2600, "Especialista en tipo Eléctrico", 1),
        ("hoenn_flannery",   "Flannery",  "La Chica de Fuego Ardiente",   "Fuego",    "Medalla Calor",       31,  3100, "Especialista en tipo Fuego",     1),
        ("hoenn_norman",     "Norman",    "El Hombre Tranquilo",          "Normal",   "Medalla Equilibrio",  31,  3100, "Especialista en tipo Normal",    1),
        ("hoenn_winona",     "Winona",    "La Maestra del Viento",        "Volador",  "Medalla Pluma",       33,  3300, "Especialista en tipo Volador",   1),
        ("hoenn_tate_liza",  "Tate y Liza","Los Gemelos Psíquicos",       "Psíquico", "Medalla Mente",       45,  4500, "Especialistas en tipo Psíquico", 1),
        ("hoenn_juan",       "Juan",      "El Maestro del Arte del Agua", "Agua",     "Medalla Lluvia",      46,  4600, "Especialista en tipo Agua",      1),
        # Alto Mando
        ("hoenn_e4_sidney",  "Sidney",  "Alto Mando Hoenn",  "Siniestro", "—", 49,  6500, "Especialista en tipo Siniestro", 1),
        ("hoenn_e4_phoebe",  "Phoebe",  "Alto Mando Hoenn",  "Fantasma",  "—", 51,  7000, "Especialista en tipo Fantasma",  1),
        ("hoenn_e4_glacia",  "Glacia",  "Alto Mando Hoenn",  "Hielo",     "—", 53,  7500, "Especialista en tipo Hielo",     1),
        ("hoenn_e4_drake",   "Drake",   "Alto Mando Hoenn",  "Dragón",    "—", 55,  8000, "Especialista en tipo Dragón",    1),
        ("hoenn_champion",   "Steven",  "Campeón de Hoenn",  "Acero",     "—", 58, 15000, "Campeón de la Liga de Hoenn",    1),
    ],

    # ── SINNOH (BDSP) ─────────────────────────────────────────────────────────
    "SINNOH": [
        ("sinnoh_roark",        "Roark",        "El Minero Rockero",           "Roca",      "Medalla Carbón",    14,  1400, "Especialista en tipo Roca",      1),
        ("sinnoh_gardenia",     "Gardenia",     "La Experta en Naturaleza",    "Planta",    "Medalla Bosque",    22,  2200, "Especialista en tipo Planta",    1),
        ("sinnoh_maylene",      "Maylene",      "La Chica Combate",            "Lucha",     "Medalla Cobijo",    30,  3000, "Especialista en tipo Lucha",     1),
        ("sinnoh_crasher_wake", "Crasher Wake", "El Defensor del Mar",         "Agua",      "Medalla Arrecife",  30,  3000, "Especialista en tipo Agua",      1),
        ("sinnoh_fantina",      "Fantina",      "La Danzarina Etérea",         "Fantasma",  "Medalla Espectro",  36,  3600, "Especialista en tipo Fantasma",  1),
        ("sinnoh_byron",        "Byron",        "El Guardián de la Fortaleza", "Acero",     "Medalla Mina",      41,  4100, "Especialista en tipo Acero",     1),
        ("sinnoh_candice",      "Candice",      "La Chica Esquiadora",         "Hielo",     "Medalla Carámbano", 42,  4200, "Especialista en tipo Hielo",     1),
        ("sinnoh_volkner",      "Volkner",      "El Más Fuerte de Funópolis",  "Eléctrico", "Medalla Faro",      50,  5000, "Especialista en tipo Eléctrico", 1),
        # Alto Mando
        ("sinnoh_e4_aaron",    "Aaron",   "Alto Mando Sinnoh",  "Bicho",    "—", 53,  7000, "Especialista en tipo Bicho",    1),
        ("sinnoh_e4_bertha",   "Bertha",  "Alto Mando Sinnoh",  "Tierra",   "—", 55,  7500, "Especialista en tipo Tierra",   1),
        ("sinnoh_e4_flint",    "Flint",   "Alto Mando Sinnoh",  "Fuego",    "—", 57,  8000, "Especialista en tipo Fuego",    1),
        ("sinnoh_e4_lucian",   "Lucian",  "Alto Mando Sinnoh",  "Psíquico", "—", 59,  9000, "Especialista en tipo Psíquico", 1),
        ("sinnoh_champion",    "Cynthia", "Campeón de Sinnoh",  "Mixto",    "—", 62, 15000, "Campeón de la Liga de Sinnoh",  1),
    ],

    # ── TESELIA / UNOVA (BW/B2W2) ─────────────────────────────────────────────
    "TESELIA": [
        ("teselia_striaton",  "Cilan/Chili/Cress", "Los Líderes Trío",       "Mixto",     "Medalla Tríada",    14,  1400, "Líderes del Gimnasio Trinita",  1),
        ("teselia_lenora",    "Lenora",    "La Directora del Museo",          "Normal",    "Medalla Básica",    20,  2000, "Especialista en tipo Normal",   1),
        ("teselia_burgh",     "Burgh",     "El Artista Pintor",               "Bicho",     "Medalla Insecto",   23,  2300, "Especialista en tipo Bicho",    1),
        ("teselia_elesa",     "Elesa",     "La Modelo Eléctrica",             "Eléctrico", "Medalla Voltio",    28,  2800, "Especialista en tipo Eléctrico",1),
        ("teselia_clay",      "Clay",      "El Rey del Subsuelo",             "Tierra",    "Medalla Quake",     31,  3100, "Especialista en tipo Tierra",   1),
        ("teselia_skyla",     "Skyla",     "La Piloto del Cielo",             "Volador",   "Medalla Jet",       37,  3700, "Especialista en tipo Volador",  1),
        ("teselia_brycen",    "Brycen",    "El Actor de Acción",              "Hielo",     "Medalla Glaciación",39,  3900, "Especialista en tipo Hielo",    1),
        ("teselia_drayden",   "Drayden",   "El Alcalde Dragón",               "Dragón",    "Medalla Baliza",    48,  4800, "Especialista en tipo Dragón",   1),
        # Alto Mando
        ("teselia_e4_shauntal","Shauntal", "Alto Mando Teselia", "Fantasma",  "—", 52,  7000, "Especialista en tipo Fantasma",  1),
        ("teselia_e4_marshal", "Marshal",  "Alto Mando Teselia", "Lucha",     "—", 52,  7000, "Especialista en tipo Lucha",     1),
        ("teselia_e4_grimsley","Grimsley", "Alto Mando Teselia", "Siniestro", "—", 52,  7000, "Especialista en tipo Siniestro", 1),
        ("teselia_e4_caitlin", "Caitlin",  "Alto Mando Teselia", "Psíquico",  "—", 52,  7000, "Especialista en tipo Psíquico",  1),
        ("teselia_champion",   "Alder",    "Campeón de Teselia", "Mixto",     "—", 58, 15000, "Campeón de la Liga de Teselia",  1),
    ],

    # ── KALOS (XY) ────────────────────────────────────────────────────────────
    "KALOS": [
        ("kalos_viola",    "Viola",    "La Fotógrafa Deportiva",    "Bicho",     "Medalla Coleóptero", 12,  1200, "Especialista en tipo Bicho",     1),
        ("kalos_grant",    "Grant",    "El Hombre de la Escalada",  "Roca",      "Medalla Acantilado", 25,  2500, "Especialista en tipo Roca",      1),
        ("kalos_korrina",  "Korrina",  "La Luchadora Patinadora",   "Lucha",     "Medalla Guante",     32,  3200, "Especialista en tipo Lucha",     1),
        ("kalos_ramos",    "Ramos",    "El Anciano del Jardín",     "Planta",    "Medalla Planta",     36,  3600, "Especialista en tipo Planta",    1),
        ("kalos_clemont",  "Clemont",  "El Inventor Eléctrico",     "Eléctrico", "Medalla Voltaje",    37,  3700, "Especialista en tipo Eléctrico", 1),
        ("kalos_valerie",  "Valerie",  "La Diseñadora de Moda",     "Hada",      "Medalla Hada",       42,  4200, "Especialista en tipo Hada",      1),
        ("kalos_olympia",  "Olympia",  "La Vidente del Cosmos",     "Psíquico",  "Medalla Psique",     48,  4800, "Especialista en tipo Psíquico",  1),
        ("kalos_wulfric",  "Wulfric",  "El Oso del Glaciar",        "Hielo",     "Medalla Iceberg",    59,  5900, "Especialista en tipo Hielo",     1),
        # Alto Mando
        ("kalos_e4_malva",    "Malva",    "Alto Mando Kalos", "Fuego",   "—", 55,  7000, "Especialista en tipo Fuego",   1),
        ("kalos_e4_siebold",  "Siebold",  "Alto Mando Kalos", "Agua",    "—", 55,  7500, "Especialista en tipo Agua",    1),
        ("kalos_e4_wikstrom", "Wikstrom", "Alto Mando Kalos", "Acero",   "—", 55,  8000, "Especialista en tipo Acero",   1),
        ("kalos_e4_drasna",   "Drasna",   "Alto Mando Kalos", "Dragón",  "—", 55,  8000, "Especialista en tipo Dragón",  1),
        ("kalos_champion",    "Diantha",  "Campeón de Kalos", "Mixto",   "—", 65, 15000, "Campeón de la Liga de Kalos",  1),
    ],

    # ── ALOLA (SM/USUM) ───────────────────────────────────────────────────────
    "ALOLA": [
        # Capitanes de Prueba / Island Kahunas
        ("alola_ilima",     "Ilima",    "Capitán de Prueba Melemele",   "Normal",    "Tótem Normal",    10,  1000, "Capitán del Melemele Meadow",     1),
        ("alola_hala",      "Hala",     "Kahuna de Melemele",            "Lucha",    "Gran Lazo",       24,  2400, "Kahuna de la Isla Melemele",      1),
        ("alola_lana",      "Lana",     "Capitán de Prueba Akala",       "Agua",     "Tótem Agua",      24,  2400, "Capitán de la Bahía Kala",        1),
        ("alola_kiawe",     "Kiawe",    "Capitán de Prueba Akala",       "Fuego",    "Tótem Fuego",     22,  2200, "Capitán de Wela Volcano Park",    1),
        ("alola_mallow",    "Mallow",   "Capitán de Prueba Akala",       "Planta",   "Tótem Planta",    24,  2400, "Capitán del Lush Jungle",         1),
        ("alola_olivia",    "Olivia",   "Kahuna de Akala",               "Roca",     "Gran Lazo",       27,  2700, "Kahuna de la Isla Akala",         1),
        ("alola_sophocles", "Sophocles","Capitán de Prueba Ula'ula",     "Eléctrico","Tótem Eléctrico", 29,  2900, "Capitán del Hokulani Observatory",1),
        ("alola_acerola",   "Acerola",  "Capitán de Prueba Ula'ula",     "Fantasma", "Tótem Fantasma",  33,  3300, "Capitán del Aether House",        1),
        ("alola_nanu",      "Nanu",     "Kahuna de Ula'ula",             "Siniestro","Gran Lazo",       35,  3500, "Kahuna de la Isla Ula'ula",       1),
        ("alola_mina",      "Mina",     "Capitán de Prueba Poni",        "Hada",     "Tótem Hada",      51,  5100, "Capitán de Poni Meadow",          1),
        ("alola_hapu",      "Hapu",     "Kahuna de Poni",                "Tierra",   "Gran Lazo",       53,  5300, "Kahuna de la Isla Poni",          1),
        # Alto Mando
        ("alola_e4_molayne","Molayne",  "Alto Mando Alola", "Acero",    "—", 55,  7000, "Especialista en tipo Acero",    1),
        ("alola_e4_olivia", "Olivia",   "Alto Mando Alola", "Roca",     "—", 56,  7500, "Especialista en tipo Roca",     1),
        ("alola_e4_acerola","Acerola",  "Alto Mando Alola", "Fantasma", "—", 56,  7500, "Especialista en tipo Fantasma", 1),
        ("alola_e4_kahili", "Kahili",   "Alto Mando Alola", "Volador",  "—", 57,  8000, "Especialista en tipo Volador",  1),
        ("alola_champion",  "Kukui",    "Campeón de Alola", "Mixto",    "—", 58, 15000, "Campeón de la Liga de Alola",   1),
    ],

    # ── GALAR (SwSh) ──────────────────────────────────────────────────────────
    "GALAR": [
        ("galar_milo",     "Milo",     "El Granjero Relajado",       "Planta",    "Medalla Planta",    20,  2000, "Especialista en tipo Planta",    1),
        ("galar_nessa",    "Nessa",    "La Modelo del Mar",           "Agua",      "Medalla Agua",      24,  2400, "Especialista en tipo Agua",      1),
        ("galar_kabu",     "Kabu",     "El Veterano Calmo",           "Fuego",     "Medalla Fuego",     27,  2700, "Especialista en tipo Fuego",     1),
        ("galar_bea",      "Bea",      "La Luchadora Imparable",      "Lucha",     "Medalla Lucha",     36,  3600, "Especialista en tipo Lucha",     1),
        ("galar_allister", "Allister", "El Niño Misterioso",          "Fantasma",  "Medalla Espectro",  36,  3600, "Especialista en tipo Fantasma",  1),
        ("galar_opal",     "Opal",     "La Anciana Hada",             "Hada",      "Medalla Hada",      38,  3800, "Especialista en tipo Hada",      1),
        ("galar_gordie",   "Gordie",   "El Hijo del Jefe Roca",       "Roca",      "Medalla Roca",      43,  4300, "Especialista en tipo Roca",      1),
        ("galar_melony",   "Melony",   "La Madre del Hielo",          "Hielo",     "Medalla Hielo",     43,  4300, "Especialista en tipo Hielo",     1),
        ("galar_piers",    "Piers",    "El Cantante Oscuro",          "Siniestro", "Medalla Oscuridad", 46,  4600, "Especialista en tipo Siniestro", 1),
        ("galar_raihan",   "Raihan",   "El Rival Invicto",            "Dragón",    "Medalla Tormenta",  48,  4800, "Especialista en tipo Dragón",    1),
        # Sin E4 tradicional en Galar — solo Campeón
        ("galar_champion", "Leon",     "Campeón Invicto de Galar",   "Mixto",     "—",                 65, 15000, "Campeón de la Liga de Galar",    1),
    ],

    # ── PALDEA (SV) ───────────────────────────────────────────────────────────
    "PALDEA": [
        ("paldea_katy",     "Katy",     "La Pastelera Entomóloga",    "Bicho",     "Medalla Bicho",     16,  1600, "Especialista en tipo Bicho",     1),
        ("paldea_brassius", "Brassius", "El Artista del Wabi-Sabi",   "Planta",    "Medalla Planta",    17,  1700, "Especialista en tipo Planta",    1),
        ("paldea_iono",     "Iono",     "La Streamear Eléctrica",     "Eléctrico", "Medalla Eléctrico", 24,  2400, "Especialista en tipo Eléctrico", 1),
        ("paldea_kofu",     "Kofu",     "El Chef del Mar",             "Agua",      "Medalla Agua",      30,  3000, "Especialista en tipo Agua",      1),
        ("paldea_larry",    "Larry",    "El Trabajador Ordinario",     "Normal",    "Medalla Normal",    36,  3600, "Especialista en tipo Normal",    1),
        ("paldea_ryme",     "Ryme",     "La Rapera del Más Allá",      "Fantasma",  "Medalla Fantasma",  44,  4400, "Especialista en tipo Fantasma",  1),
        ("paldea_tulip",    "Tulip",    "La Maquilladora de Estrellas","Psíquico",  "Medalla Psíquico",  45,  4500, "Especialista en tipo Psíquico",  1),
        ("paldea_grusha",   "Grusha",   "El Snowboarder Profesional",  "Hielo",     "Medalla Hielo",     48,  4800, "Especialista en tipo Hielo",     1),
        # Alto Mando (Top Champions)
        ("paldea_e4_rika",   "Rika",   "Top Champion Paldea", "Tierra",  "—", 61,  7500, "Especialista en tipo Tierra",    1),
        ("paldea_e4_poppy",  "Poppy",  "Top Champion Paldea", "Acero",   "—", 62,  8000, "Especialista en tipo Acero",     1),
        ("paldea_e4_larry",  "Larry",  "Top Champion Paldea", "Volador", "—", 63,  8500, "Especialista en tipo Volador",   1),
        ("paldea_e4_hassel", "Hassel", "Top Champion Paldea", "Dragón",  "—", 64,  9000, "Especialista en tipo Dragón",    1),
        ("paldea_champion",  "Geeta",  "Directora de la Academia",  "Mixto", "—", 62, 15000, "Campeón de la Liga de Paldea",  1),
        ("paldea_nemona",    "Nemona", "Top Champion Secreto",       "Mixto", "—", 66, 20000, "La Verdadera Campeona de Paldea",1),
    ],
}

# ══════════════════════════════════════════════════════════════════════════════
# POKÉMON VÁLIDOS COMO SALVAJES POR REGIÓN
# Basado en las Pokédex oficiales de cada juego.
# Excluye legendarios, míticos y singulares.
# ══════════════════════════════════════════════════════════════════════════════

# Pokémon de Kanto disponibles en Johto (HGSS)
_JOHTO_KANTO = {
    19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34,
    35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49,
    52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65,
    66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 79, 80, 81, 82, 83,
    84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 96, 97, 98, 99,
    100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112,
    113, 114, 115, 116, 117, 118, 119, 120, 121, 123, 124, 125, 126,
    127, 128, 129, 130, 131, 132, 133, 134, 135, 136, 137, 143,
    147, 148, 149,
}

# Pokémon adicionales de otras gens en Sinnoh (DPPt)
_SINNOH_EXTRAS = {
    # Gen 1
    19, 20, 39, 40, 41, 42, 54, 55, 60, 61, 62, 63, 64, 65,
    72, 73, 74, 75, 76, 81, 82, 92, 93, 94, 111, 112, 113,
    114, 115, 116, 117, 129, 130, 137, 143, 147, 148, 149,
    # Gen 2
    165, 166, 170, 171, 183, 184, 193, 194, 195, 198, 200,
    202, 203, 206, 207, 209, 210, 211, 212, 213, 214, 215,
    216, 217, 218, 219, 220, 221, 222, 223, 224, 225, 226,
    227, 228, 229, 230, 231, 232, 233, 234, 237, 241,
}

# Pokémon disponibles en Alola de otras generaciones (SM/USUM)
_ALOLA_EXTRAS = {
    # Gen 1 (incluyendo formas Alola)
    19, 20, 25, 26, 27, 28, 37, 38, 41, 42, 46, 47, 48, 49,
    50, 51, 52, 53, 54, 55, 60, 61, 62, 63, 64, 65, 66, 67, 68,
    74, 75, 76, 79, 80, 81, 82, 88, 89, 90, 91, 92, 93, 94,
    96, 97, 98, 99, 102, 103, 104, 105, 111, 112, 116, 117,
    118, 119, 120, 121, 129, 130, 131, 132, 133, 134, 135, 136, 137,
    # Gen 2
    163, 164, 165, 166, 167, 168, 170, 171, 183, 184, 185, 186,
    194, 195, 209, 210, 218, 219, 220, 221, 222, 223, 224,
    226, 227, 233, 234,
    # Gen 3
    278, 279, 280, 281, 282, 283, 284, 296, 297, 300, 301,
    303, 309, 310, 316, 317, 318, 319, 320, 321, 325, 326,
    327, 333, 334, 339, 340, 341, 342, 345, 346, 347, 348,
    357, 370, 371, 372, 373, 374, 375, 376,
    # Gen 4
    396, 397, 398, 399, 400, 403, 404, 405, 408, 409, 412,
    413, 414, 415, 416, 418, 419, 425, 426, 427, 428, 429,
    430, 431, 432, 433, 443, 444, 445, 447, 448, 456, 457,
    458, 459, 460, 468, 472, 478,
    # Gen 5
    504, 505, 506, 507, 508, 509, 510, 519, 520, 521, 524,
    525, 526, 529, 530, 532, 533, 534, 535, 536, 537, 551,
    552, 553, 557, 558, 566, 567, 568, 569, 570, 571, 577,
    578, 579, 587, 594, 599, 600, 601, 615, 619, 620, 621,
    624, 625, 627, 628, 629, 630, 633, 634, 635,
    # Gen 6
    659, 660, 661, 662, 663, 664, 665, 666, 674, 675, 676,
    677, 678, 679, 680, 681, 682, 683, 684, 685, 686, 687,
    688, 689, 690, 691, 692, 693, 694, 695, 696, 697, 698,
    699, 700, 702, 703, 706, 707, 708, 709, 710, 711, 712,
    713, 714, 715,
}

REGION_WILD_IDS: dict = {
    # Kanto: solo nativos (1-151) sin legendarios
    "KANTO": set(range(1, 152)) - _LEGENDARIOS,

    # Johto: nativos (152-251) + Kanto disponibles en HGSS, sin legendarios
    "JOHTO": ((set(range(152, 252)) | _JOHTO_KANTO) - _LEGENDARIOS),

    # Hoenn: nativos (252-376) + algunos de otras gens disponibles en ORAS
    "HOENN": (
        set(range(252, 377))
        | {72, 73, 81, 82, 116, 117, 118, 119, 120, 121, 129, 130, 131, 147, 148, 149}
    ) - _LEGENDARIOS,

    # Sinnoh: nativos (387-479) + extras de otras gens en DPPt
    "SINNOH": (set(range(387, 480)) | _SINNOH_EXTRAS) - _LEGENDARIOS,

    # Teselia: principalmente nativos (495-637), BW muy estricto
    "TESELIA": set(range(495, 638)) - _LEGENDARIOS,

    # Kalos: nativos (650-715) + casi todas las gens anteriores (XY muy amplio)
    "KALOS": (set(range(1, 638)) | set(range(650, 716))) - _LEGENDARIOS,

    # Alola: nativos (722-784) + selección de otras gens
    "ALOLA": (set(range(722, 785)) | _ALOLA_EXTRAS) - _LEGENDARIOS,

    # Galar: nativos (810-887) + mayoría de gens 1-7 (SwSh Pokédex amplia)
    "GALAR": (set(range(1, 810)) | set(range(810, 888))) - _LEGENDARIOS,

    # Paldea: nativos (906-1000, paradox incluidos como raros) + casi todo lo anterior
    "PALDEA": (set(range(1, 1001)) | set(range(906, 1001))) - _LEGENDARIOS,
}


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIONES DE ACCESO
# ══════════════════════════════════════════════════════════════════════════════

def get_wild_ids(region: str) -> list[int]:
    """Lista ordenada de IDs de Pokémon válidos como salvajes en la región."""
    region = region.upper()
    return sorted(REGION_WILD_IDS.get(region, REGION_WILD_IDS["KANTO"]))


def get_leaders(region: str) -> list[tuple]:
    """Tuplas de líderes/alto mando/campeón para la región."""
    return REGION_LEADERS.get(region.upper(), REGION_LEADERS["KANTO"])


def get_starters(region: str) -> list[dict]:
    """Datos de los starters para la región."""
    return REGION_STARTERS.get(region.upper(), REGION_STARTERS["KANTO"])


def get_all_leaders_flat() -> list[tuple]:
    """Todas las tuplas de líderes de todas las regiones (para INSERT en BD)."""
    result = []
    for leaders in REGION_LEADERS.values():
        result.extend(leaders)
    return result


def get_region_gym_leader_ids(region: str) -> set[str]:
    """IDs de líderes de gimnasio (sin E4 ni campeón) de la región."""
    leaders = REGION_LEADERS.get(region.upper(), [])
    return {
        lid for lid, *_ in leaders
        if "e4" not in lid and "champion" not in lid and "nemona" not in lid
    }
