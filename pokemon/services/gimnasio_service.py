# -*- coding: utf-8 -*-
"""
Servicio de Gimnasios y Alto Mando
===================================
Cubre las 9 regiones del juego principal: Kanto, Johto, Hoenn, Sinnoh,
Teselia, Kalos, Alola, Galar y Paldea.

Características:
  - Movesets oficiales de cada líder (referencia: FRLG/HGSS/RSE/DPPt/BW/XY/SUMO/SWSH/SV)
  - Desbloqueo secuencial: sólo se puede retar al siguiente líder tras derrotar al anterior
  - Recompensas: cosmos + MT (igual a juegos oficiales)
  - Alto Mando accesible únicamente tras las 8 medallas de la región
  - IA por líder: estrategia que guía el motor de batalla al tomar decisiones

Estructura de lider_id en BD:
  - Kanto (compat. histórica): "brock", "misty", … "giovanni"
  - Demás regiones:            "{region}_{lider}"  ej. "johto_falkner"
  - Elite Four:                "{region}_e4_{nombre}"  ej. "kanto_e4_lorelei"
  - Campeón:                   "{region}_champion"

NOTA: gimnasio_system.py es OBSOLETO — toda la lógica vive aquí.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple, Type

from database import db_manager

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constante interna — userID reservado para NPCs
# ─────────────────────────────────────────────────────────────────────────────
_NPC_USER_ID = 999_999


# ═════════════════════════════════════════════════════════════════════════════
# DATOS POR REGIÓN
# Formato de cada gimnasio / líder:
#   id          → lider_id que se graba en MEDALLAS_USUARIOS
#   nombre      → nombre visible
#   titulo      → subtítulo del líder
#   tipo        → tipo especialidad (español)
#   medalla     → nombre de la medalla / insignia
#   emoji       → emoji representativo
#   ciudad      → ciudad del gimnasio
#   recompensa  → cosmos al ganar
#   mt_recompensa → {"nombre_es": str, "move_key": str, "mt_num": int}
#   equipo      → lista de {"pokemon_id": int, "nivel": int, "moves": [str]}
#                   (moves: 1-4 claves de movimiento tal como las maneja battle_engine)
#   ia_config   → {"estrategia": str, "notas": str}
#                   estrategias: "aggressive" | "status_first" | "defensive" |
#                                "trap_damage" | "setup_sweep" | "mixed"
# ═════════════════════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────────────────
# KANTO  (referencia FireRed / LeafGreen)
# ──────────────────────────────────────────────────────────────
_KANTO_GYMS: List[Dict] = [
    {
        "id": "brock",
        "nombre": "Brock",
        "titulo": "El Titán de Roca",
        "tipo": "Roca",
        "medalla": "Medalla Roca",
        "emoji": "🪨",
        "ciudad": "Ciudad Plateada",
        "recompensa": 1386,
        "mt_recompensa": {"nombre_es": "Tumba Rocas", "move_key": "rocktomb", "mt_num": 39},
        "equipo": [
            {"pokemon_id": 74, "nivel": 12, "moves": ["tackle", "defensecurl", "rockthrow"]},
            {"pokemon_id": 95, "nivel": 14, "moves": ["tackle", "screech", "bind", "rockthrow"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Screech primero con Onix, luego atacar"},
    },
    {
        "id": "misty",
        "nombre": "Misty",
        "titulo": "La Sirena de Cascada",
        "tipo": "Agua",
        "medalla": "Medalla Cascada",
        "emoji": "💧",
        "ciudad": "Ciudad Celeste",
        "recompensa": 2016,
        "mt_recompensa": {"nombre_es": "Pulso Agua", "move_key": "waterpulse", "mt_num": 3},
        "equipo": [
            {"pokemon_id": 120, "nivel": 18, "moves": ["watergun", "harden", "rapidspins", "tackle"]},
            {"pokemon_id": 121, "nivel": 21, "moves": ["watergun", "swift", "confuseray", "recover"]},
        ],
        "ia_config": {"estrategia": "mixed", "notas": "Confuse Ray con Starmie, recover al 40% HP"},
    },
    {
        "id": "surge",
        "nombre": "Lt. Surge",
        "titulo": "El Americano Relámpago",
        "tipo": "Eléctrico",
        "medalla": "Medalla Trueno",
        "emoji": "⚡",
        "ciudad": "Ciudad Carmín",
        "recompensa": 2310,
        "mt_recompensa": {"nombre_es": "Onda Trueno", "move_key": "shockwave", "mt_num": 34},
        "equipo": [
            {"pokemon_id": 100, "nivel": 21, "moves": ["tackle", "sonicboom", "spark", "screech"]},
            {"pokemon_id": 25,  "nivel": 24, "moves": ["thundershock", "quickattack", "doubleteam", "thunderwave"]},
            {"pokemon_id": 26,  "nivel": 24, "moves": ["thunderbolt", "quickattack", "thunderwave", "swift"]},
        ],
        "ia_config": {"estrategia": "status_first", "notas": "Thunder Wave rápido, luego Thunderbolt / Spark"},
    },
    {
        "id": "erika",
        "nombre": "Erika",
        "titulo": "La Princesa de la Naturaleza",
        "tipo": "Planta",
        "medalla": "Medalla Arcoíris",
        "emoji": "🌿",
        "ciudad": "Ciudad Azafrán",
        "recompensa": 3360,
        "mt_recompensa": {"nombre_es": "Drenadora", "move_key": "gigadrain", "mt_num": 57},
        "equipo": [
            {"pokemon_id": 114, "nivel": 29, "moves": ["vinewhip", "constrict", "megadrain", "sleeppowder"]},
            {"pokemon_id": 70,  "nivel": 30, "moves": ["wrap", "poisonpowder", "razorleaf", "sleeppowder"]},
            {"pokemon_id": 45,  "nivel": 32, "moves": ["stunspore", "megadrain", "razorleaf", "sweetscent"]},
        ],
        "ia_config": {"estrategia": "status_first", "notas": "Sleep Powder primero; Mega Drain para recuperar HP"},
    },
    {
        "id": "koga",
        "nombre": "Koga",
        "titulo": "El Ninja Venenoso",
        "tipo": "Veneno",
        "medalla": "Medalla Alma",
        "emoji": "☠️",
        "ciudad": "Ciudad Fucsia",
        "recompensa": 4140,
        "mt_recompensa": {"nombre_es": "Tóxico", "move_key": "toxic", "mt_num": 6},
        "equipo": [
            {"pokemon_id": 109, "nivel": 37, "moves": ["smokescreen", "smog", "selfdestruct", "tackle"]},
            {"pokemon_id": 89,  "nivel": 39, "moves": ["minimize", "screech", "smog", "pound"]},
            {"pokemon_id": 109, "nivel": 37, "moves": ["smokescreen", "haze", "smog", "selfdestruct"]},
            {"pokemon_id": 110, "nivel": 43, "moves": ["toxic", "smokescreen", "haze", "selfdestruct"]},
        ],
        "ia_config": {"estrategia": "trap_damage", "notas": "Toxic + Smokescreen; Selfdestruct cuando HP bajo"},
    },
    {
        "id": "sabrina",
        "nombre": "Sabrina",
        "titulo": "La Amo Psíquica",
        "tipo": "Psíquico",
        "medalla": "Medalla Pantano",
        "emoji": "🔮",
        "ciudad": "Ciudad Azulona",
        "recompensa": 4140,
        "mt_recompensa": {"nombre_es": "Calma Mental", "move_key": "calmmind", "mt_num": 129},
        "equipo": [
            {"pokemon_id": 64,  "nivel": 38, "moves": ["psybeam", "kinesis", "recover", "confusion"]},
            {"pokemon_id": 122, "nivel": 37, "moves": ["confusion", "psywave", "barrier", "meditate"]},
            {"pokemon_id": 49,  "nivel": 38, "moves": ["psybeam", "confusion", "silverpowder", "stunspore"]},
            {"pokemon_id": 65,  "nivel": 43, "moves": ["psychic", "calmmind", "recover", "futuresight"]},
        ],
        "ia_config": {"estrategia": "setup_sweep", "notas": "Calm Mind con Alakazam antes de atacar; Recover al 40%"},
    },
    {
        "id": "blaine",
        "nombre": "Blaine",
        "titulo": "El Hombre Llama",
        "tipo": "Fuego",
        "medalla": "Medalla Volcán",
        "emoji": "🔥",
        "ciudad": "Isla Canela",
        "recompensa": 4512,
        "mt_recompensa": {"nombre_es": "Lanzallamas", "move_key": "flamethrower", "mt_num": 109},
        "equipo": [
            {"pokemon_id": 58,  "nivel": 42, "moves": ["ember", "roar", "leer", "flamethrower"]},
            {"pokemon_id": 77,  "nivel": 40, "moves": ["ember", "stomp", "fireblast", "agility"]},
            {"pokemon_id": 78,  "nivel": 42, "moves": ["flamethrower", "stomp", "fireblast", "agility"]},
            {"pokemon_id": 59,  "nivel": 47, "moves": ["flamethrower", "extremespeed", "fireblast", "roar"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Fire Blast en cuanto puede; Agility para speed"},
    },
    {
        "id": "giovanni",
        "nombre": "Giovanni",
        "titulo": "El Jefe del Team Rocket",
        "tipo": "Tierra",
        "medalla": "Medalla Tierra",
        "emoji": "🌍",
        "ciudad": "Ciudad Verde",
        "recompensa": 9000,
        "mt_recompensa": {"nombre_es": "Terremoto", "move_key": "earthquake", "mt_num": 96},
        "equipo": [
            {"pokemon_id": 111, "nivel": 45, "moves": ["horn drill", "stomp", "earthquake", "furyattack"]},
            {"pokemon_id": 51,  "nivel": 42, "moves": ["slash", "earthquake", "sandattack", "dig"]},
            {"pokemon_id": 34,  "nivel": 44, "moves": ["earthquake", "poisonsting", "thunderbolt", "doubleattack"]},
            {"pokemon_id": 31,  "nivel": 45, "moves": ["earthquake", "blizzard", "poisonsting", "bodyslam"]},
            {"pokemon_id": 112, "nivel": 50, "moves": ["earthquake", "hornattack", "stomp", "rocktomb"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Earthquake spam; Rhydon cierra la batalla"},
    },
]

# ──────────────────────────────────────────────────────────────
# JOHTO  (referencia HeartGold / SoulSilver)
# ──────────────────────────────────────────────────────────────
_JOHTO_GYMS: List[Dict] = [
    {
        "id": "johto_falkner",
        "nombre": "Falkner",
        "titulo": "El Chico del Viento",
        "tipo": "Volador",
        "medalla": "Medalla Zeta",
        "emoji": "🦅",
        "ciudad": "Ciudad Violeta",
        "recompensa": 672,
        "mt_recompensa": {"nombre_es": "Vuelo", "move_key": "roost", "mt_num": 51},
        "equipo": [
            {"pokemon_id": 21, "nivel": 9,  "moves": ["tackle", "mudsport", "gust"]},
            {"pokemon_id": 22, "nivel": 13, "moves": ["tackle", "gust", "wingattack", "mudsport"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Wing Attack directo"},
    },
    {
        "id": "johto_bugsy",
        "nombre": "Bugsy",
        "titulo": "El Experto en Bichos",
        "tipo": "Bicho",
        "medalla": "Medalla Colmena",
        "emoji": "🐛",
        "ciudad": "Ciudad Azalea",
        "recompensa": 1050,
        "mt_recompensa": {"nombre_es": "Zumbido", "move_key": "uturn", "mt_num": 56},
        "equipo": [
            {"pokemon_id": 14,  "nivel": 15, "moves": ["harden", "constrict", "poisonsting"]},
            {"pokemon_id": 13,  "nivel": 15, "moves": ["tackle", "stringshot", "poisonsting"]},
            {"pokemon_id": 123, "nivel": 17, "moves": ["quickattack", "leechlife", "furyattack", "focusenergy"]},
        ],
        "ia_config": {"estrategia": "mixed", "notas": "Scyther con Quick Attack y Fury Attack"},
    },
    {
        "id": "johto_whitney",
        "nombre": "Whitney",
        "titulo": "La Chica del Millón",
        "tipo": "Normal",
        "medalla": "Medalla Llanura",
        "emoji": "⭐",
        "ciudad": "Ciudad Rosa",
        "recompensa": 1680,
        "mt_recompensa": {"nombre_es": "Atracción", "move_key": "attract", "mt_num": 45},
        "equipo": [
            {"pokemon_id": 35,  "nivel": 18, "moves": ["pound", "encore", "doubleslap", "metronome"]},
            {"pokemon_id": 241, "nivel": 20, "moves": ["stomp", "rollout", "attract", "milkdrink"]},
        ],
        "ia_config": {"estrategia": "status_first", "notas": "Attract primero; Rollout con Miltank"},
    },
    {
        "id": "johto_morty",
        "nombre": "Morty",
        "titulo": "El Que Ve el Futuro",
        "tipo": "Fantasma",
        "medalla": "Medalla Niebla",
        "emoji": "👻",
        "ciudad": "Ciudad Caoba",
        "recompensa": 2352,
        "mt_recompensa": {"nombre_es": "Bola Sombra", "move_key": "shadowball", "mt_num": 92},
        "equipo": [
            {"pokemon_id": 92,  "nivel": 21, "moves": ["lick", "spite", "confuseray", "nightshade"]},
            {"pokemon_id": 92,  "nivel": 21, "moves": ["lick", "spite", "confuseray", "nightshade"]},
            {"pokemon_id": 93,  "nivel": 23, "moves": ["lick", "spite", "confuseray", "meanlook"]},
            {"pokemon_id": 94,  "nivel": 25, "moves": ["nightshade", "confuseray", "meanlook", "shadowball"]},
        ],
        "ia_config": {"estrategia": "trap_damage", "notas": "Mean Look + Confuse Ray + Night Shade"},
    },
    {
        "id": "johto_chuck",
        "nombre": "Chuck",
        "titulo": "El Guerrero del Fuerzo",
        "tipo": "Lucha",
        "medalla": "Medalla Torbellino",
        "emoji": "🥊",
        "ciudad": "Ciudad Malva",
        "recompensa": 3024,
        "mt_recompensa": {"nombre_es": "Dinamopuño", "move_key": "dynamicpunch", "mt_num": 1},
        "equipo": [
            {"pokemon_id": 62,  "nivel": 27, "moves": ["hypnosis", "lowkick", "karatechop", "submission"]},
            {"pokemon_id": 107, "nivel": 30, "moves": ["dynamicpunch", "thunderpunch", "icepunch", "firepunch"]},
        ],
        "ia_config": {"estrategia": "status_first", "notas": "Hypnosis con Poliwrath; Dynamic Punch con Hitmonchan"},
    },
    {
        "id": "johto_jasmine",
        "nombre": "Jasmine",
        "titulo": "La Chica del Acero",
        "tipo": "Acero",
        "medalla": "Medalla Mineral",
        "emoji": "⚙️",
        "ciudad": "Ciudad Olivina",
        "recompensa": 3360,
        "mt_recompensa": {"nombre_es": "Garra Metal", "move_key": "irondefense", "mt_num": 66},
        "equipo": [
            {"pokemon_id": 81,  "nivel": 30, "moves": ["thundershock", "sonicboom", "spark", "magnetbomb"]},
            {"pokemon_id": 81,  "nivel": 30, "moves": ["thundershock", "sonicboom", "spark", "magnetbomb"]},
            {"pokemon_id": 208, "nivel": 35, "moves": ["irondefense", "screech", "irontail", "earthquake"]},
        ],
        "ia_config": {"estrategia": "defensive", "notas": "Iron Defense con Steelix; Iron Tail en ataques"},
    },
    {
        "id": "johto_pryce",
        "nombre": "Pryce",
        "titulo": "El Maestro del Invierno",
        "tipo": "Hielo",
        "medalla": "Medalla Glaciar",
        "emoji": "🧊",
        "ciudad": "Ciudad Fría",
        "recompensa": 3696,
        "mt_recompensa": {"nombre_es": "Ventisca", "move_key": "blizzard", "mt_num": 141},
        "equipo": [
            {"pokemon_id": 86,  "nivel": 27, "moves": ["powdersnow", "growl", "surf", "icy wind"]},
            {"pokemon_id": 87,  "nivel": 29, "moves": ["aurorabeam", "icywind", "growl", "surf"]},
            {"pokemon_id": 221, "nivel": 31, "moves": ["blizzard", "icy wind", "amnesia", "earthquake"]},
        ],
        "ia_config": {"estrategia": "mixed", "notas": "Icy Wind para bajar velocidad; Amnesia con Piloswine"},
    },
    {
        "id": "johto_clair",
        "nombre": "Clair",
        "titulo": "La Dragón Reina",
        "tipo": "Dragón",
        "medalla": "Medalla Ascenso",
        "emoji": "🐉",
        "ciudad": "Ciudad Caoba",
        "recompensa": 7560,
        "mt_recompensa": {"nombre_es": "Pulso Dragón", "move_key": "dragonpulse", "mt_num": 87},
        "equipo": [
            {"pokemon_id": 148, "nivel": 37, "moves": ["twister", "slam", "dragondance", "surf"]},
            {"pokemon_id": 148, "nivel": 37, "moves": ["twister", "slam", "dragondance", "surf"]},
            {"pokemon_id": 148, "nivel": 37, "moves": ["twister", "slam", "dragondance", "surf"]},
            {"pokemon_id": 230, "nivel": 40, "moves": ["dragonpulse", "surf", "thunder", "twister"]},
        ],
        "ia_config": {"estrategia": "setup_sweep", "notas": "Dragon Dance con Dragonair antes de atacar"},
    },
]

# ──────────────────────────────────────────────────────────────
# HOENN  (referencia Rubí / Zafiro / Esmeralda)
# ──────────────────────────────────────────────────────────────
_HOENN_GYMS: List[Dict] = [
    {
        "id": "hoenn_roxanne",
        "nombre": "Roxanne",
        "titulo": "La Estudiante de Roca",
        "tipo": "Roca",
        "medalla": "Medalla Piedra",
        "emoji": "🪨",
        "ciudad": "Ciudad Piedra",
        "recompensa": 880,
        "mt_recompensa": {"nombre_es": "Tumba Rocas", "move_key": "rocktomb", "mt_num": 39},
        "equipo": [
            {"pokemon_id": 273, "nivel": 10, "moves": ["tackle", "harden", "rockthrow"]},
            {"pokemon_id": 273, "nivel": 10, "moves": ["tackle", "harden", "rockthrow"]},
            {"pokemon_id": 408, "nivel": 15, "moves": ["tackle", "headbutt", "rocktomb", "harden"]},  # Nosepass → 299
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Rock Tomb siempre; Nosepass cierra"},
    },
    {
        "id": "hoenn_brawly",
        "nombre": "Brawly",
        "titulo": "El Luchador de la Playa",
        "tipo": "Lucha",
        "medalla": "Medalla Nudillo",
        "emoji": "🥊",
        "ciudad": "Ciudad Gata",
        "recompensa": 1188,
        "mt_recompensa": {"nombre_es": "Foco Energía", "move_key": "bulkup", "mt_num": 64},
        "equipo": [
            {"pokemon_id": 296, "nivel": 16, "moves": ["tackle", "focusenergy", "karatechop", "lowkick"]},
            {"pokemon_id": 297, "nivel": 19, "moves": ["bulkup", "karatechop", "lowkick", "submission"]},
        ],
        "ia_config": {"estrategia": "setup_sweep", "notas": "Bulk Up con Hariyama antes de atacar"},
    },
    {
        "id": "hoenn_wattson",
        "nombre": "Wattson",
        "titulo": "El Alegre Señor Rayo",
        "tipo": "Eléctrico",
        "medalla": "Medalla Dínamo",
        "emoji": "⚡",
        "ciudad": "Mauville",
        "recompensa": 1680,
        "mt_recompensa": {"nombre_es": "Onda Trueno", "move_key": "shockwave", "mt_num": 34},
        "equipo": [
            {"pokemon_id": 100, "nivel": 20, "moves": ["sonicboom", "spark", "screech", "rollout"]},
            {"pokemon_id": 81,  "nivel": 20, "moves": ["thundershock", "sonicboom", "supersonic", "spark"]},
            {"pokemon_id": 101, "nivel": 22, "moves": ["spark", "sonicboom", "rollout", "selfdestruct"]},
            {"pokemon_id": 82,  "nivel": 22, "moves": ["thunderbolt", "spark", "sonicboom", "supersonic"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Shock Wave no falla; Electrode con Self-Destruct si pierde"},
    },
    {
        "id": "hoenn_flannery",
        "nombre": "Flannery",
        "titulo": "La Apasionada de Fuego",
        "tipo": "Fuego",
        "medalla": "Medalla Calor",
        "emoji": "🔥",
        "ciudad": "Ciudad Lava",
        "recompensa": 2016,
        "mt_recompensa": {"nombre_es": "Templanza", "move_key": "overheat", "mt_num": 50},
        "equipo": [
            {"pokemon_id": 322, "nivel": 24, "moves": ["ember", "yawn", "stomp", "overheat"]},
            {"pokemon_id": 322, "nivel": 24, "moves": ["ember", "yawn", "stomp", "overheat"]},
            {"pokemon_id": 323, "nivel": 26, "moves": ["overheat", "attract", "yawn", "flamethrower"]},
            {"pokemon_id": 218, "nivel": 26, "moves": ["overheat", "yawn", "flamewheel", "ember"]},
        ],
        "ia_config": {"estrategia": "status_first", "notas": "Yawn para dormir; Overheat como golpe de cierre"},
    },
    {
        "id": "hoenn_norman",
        "nombre": "Norman",
        "titulo": "El Orgulloso Papá",
        "tipo": "Normal",
        "medalla": "Medalla Equilibrio",
        "emoji": "⭐",
        "ciudad": "Ciudad Petalburg",
        "recompensa": 2880,
        "mt_recompensa": {"nombre_es": "Fachada", "move_key": "facade", "mt_num": 31},
        "equipo": [
            {"pokemon_id": 288, "nivel": 27, "moves": ["yawn", "encore", "facade", "slash"]},
            {"pokemon_id": 288, "nivel": 27, "moves": ["yawn", "encore", "facade", "slash"]},
            {"pokemon_id": 289, "nivel": 31, "moves": ["facade", "slash", "bulkup", "retaliate"]},
        ],
        "ia_config": {"estrategia": "status_first", "notas": "Yawn + Encore; Facade con estado propio"},
    },
    {
        "id": "hoenn_winona",
        "nombre": "Winona",
        "titulo": "La Chica con Alas",
        "tipo": "Volador",
        "medalla": "Medalla Pluma",
        "emoji": "🦅",
        "ciudad": "Ciudad Fortree",
        "recompensa": 3276,
        "mt_recompensa": {"nombre_es": "Acrobatismo", "move_key": "aerialace", "mt_num": 27},
        "equipo": [
            {"pokemon_id": 278, "nivel": 29, "moves": ["wingattack", "growl", "watergun", "quickattack"]},
            {"pokemon_id": 333, "nivel": 30, "moves": ["wingattack", "doubleteam", "pluck", "aerialace"]},
            {"pokemon_id": 334, "nivel": 33, "moves": ["aerialace", "dragonbreath", "doubleteam", "recover"]},
            {"pokemon_id": 279, "nivel": 33, "moves": ["wingattack", "watergun", "aerialace", "endeavor"]},
        ],
        "ia_config": {"estrategia": "mixed", "notas": "Double Team + Aerial Ace; Altaria con Dragon Breath"},
    },
    {
        "id": "hoenn_tate_liza",
        "nombre": "Liana y Vito",
        "titulo": "Los Gemelos Psíquicos",
        "tipo": "Psíquico",
        "medalla": "Medalla Mente",
        "emoji": "🔮",
        "ciudad": "Ciudad Mossdeep",
        "recompensa": 4416,
        "mt_recompensa": {"nombre_es": "Calma Mental", "move_key": "calmmind", "mt_num": 129},
        "equipo": [
            {"pokemon_id": 338, "nivel": 41, "moves": ["calmmind", "psybeam", "cosmicpower", "solarbeam"]},
            {"pokemon_id": 337, "nivel": 41, "moves": ["calmmind", "psybeam", "cosmicpower", "earthquake"]},
            {"pokemon_id": 203, "nivel": 42, "moves": ["psychic", "stomp", "doublehit", "lightscreen"]},
            {"pokemon_id": 202, "nivel": 45, "moves": ["calmmind", "psychic", "encore", "shadowball"]},
        ],
        "ia_config": {"estrategia": "setup_sweep", "notas": "Calm Mind + Cosmic Power; Wobbuffet con Encore"},
    },
    {
        "id": "hoenn_juan",
        "nombre": "Juan",
        "titulo": "El Artista del Agua",
        "tipo": "Agua",
        "medalla": "Medalla Lluvia",
        "emoji": "💧",
        "ciudad": "Ciudad Sootopolis",
        "recompensa": 9360,
        "mt_recompensa": {"nombre_es": "Cascada", "move_key": "waterfall", "mt_num": 106},
        "equipo": [
            {"pokemon_id": 116, "nivel": 41, "moves": ["twister", "watergun", "smokescreen", "leer"]},
            {"pokemon_id": 186, "nivel": 41, "moves": ["watergun", "doubleslap", "raindance", "bodyslam"]},
            {"pokemon_id": 117, "nivel": 43, "moves": ["waterfall", "twister", "dragonbreath", "surf"]},
            {"pokemon_id": 368, "nivel": 43, "moves": ["surf", "icebeam", "attract", "waterfall"]},
            {"pokemon_id": 130, "nivel": 46, "moves": ["surf", "dragonbreath", "leer", "hyper beam"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Rain Dance para empoderar Surf; Gyarados cierra"},
    },
]

# ──────────────────────────────────────────────────────────────
# SINNOH  (referencia Diamante / Perla / Platino)
# ──────────────────────────────────────────────────────────────
_SINNOH_GYMS: List[Dict] = [
    {
        "id": "sinnoh_roark",
        "nombre": "Roark",
        "titulo": "El Joven Excavador",
        "tipo": "Roca",
        "medalla": "Medalla Carbón",
        "emoji": "🪨",
        "ciudad": "Ciudad Oreburgh",
        "recompensa": 1050,
        "mt_recompensa": {"nombre_es": "Golpe Roca", "move_key": "stealthrock", "mt_num": 76},
        "equipo": [
            {"pokemon_id": 408, "nivel": 12, "moves": ["tackle", "leer", "headbutt"]},
            {"pokemon_id": 293, "nivel": 11, "moves": ["growl", "supersonic", "bulldoze"]},
            {"pokemon_id": 409, "nivel": 14, "moves": ["tackle", "leer", "headbutt", "rockblast"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Stealth Rock y Rock Blast con Rampardos"},
    },
    {
        "id": "sinnoh_gardenia",
        "nombre": "Gardenia",
        "titulo": "La Maestra del Bosque",
        "tipo": "Planta",
        "medalla": "Medalla Bosque",
        "emoji": "🌿",
        "ciudad": "Eterna City",
        "recompensa": 2016,
        "mt_recompensa": {"nombre_es": "Drenadora", "move_key": "gigadrain", "mt_num": 57},
        "equipo": [
            {"pokemon_id": 187, "nivel": 19, "moves": ["vinewhip", "stunspore", "poisonpowder", "sleeppowder"]},
            {"pokemon_id": 421, "nivel": 19, "moves": ["razorleaf", "leechseed", "synthesis", "worryseed"]},
            {"pokemon_id": 407, "nivel": 22, "moves": ["leafstorm", "poisonpowder", "stunspore", "gigadrain"]},
        ],
        "ia_config": {"estrategia": "status_first", "notas": "Sleep Powder + Leech Seed; Roserade cierra con Leaf Storm"},
    },
    {
        "id": "sinnoh_maylene",
        "nombre": "Maylene",
        "titulo": "La Guerrera Descalza",
        "tipo": "Lucha",
        "medalla": "Medalla Cobalt",
        "emoji": "🥊",
        "ciudad": "Ciudad Veilstone",
        "recompensa": 2688,
        "mt_recompensa": {"nombre_es": "Drenaje Puño", "move_key": "drainpunch", "mt_num": 120},
        "equipo": [
            {"pokemon_id": 307, "nivel": 27, "moves": ["meditite", "confusion", "detect", "drainpunch"]},
            {"pokemon_id": 308, "nivel": 27, "moves": ["detect", "drainpunch", "confusion", "forcepalm"]},
            {"pokemon_id": 448, "nivel": 30, "moves": ["forcepalm", "drainpunch", "swordsdance", "quickattack"]},
        ],
        "ia_config": {"estrategia": "setup_sweep", "notas": "Swords Dance con Lucario; Drain Punch para recuperar HP"},
    },
    {
        "id": "sinnoh_crasher_wake",
        "nombre": "Crasher Wake",
        "titulo": "El Maestro del Mar",
        "tipo": "Agua",
        "medalla": "Medalla Fen",
        "emoji": "💧",
        "ciudad": "Ciudad Pastoria",
        "recompensa": 3360,
        "mt_recompensa": {"nombre_es": "Cascada", "move_key": "waterfall", "mt_num": 106},
        "equipo": [
            {"pokemon_id": 418, "nivel": 27, "moves": ["watergun", "agility", "aquajet", "swift"]},
            {"pokemon_id": 419, "nivel": 30, "moves": ["crunch", "aquajet", "swift", "waterfall"]},
            {"pokemon_id": 130, "nivel": 33, "moves": ["waterfall", "twister", "earthquake", "icefang"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Aqua Jet prioridad; Gyarados cierra con Waterfall"},
    },
    {
        "id": "sinnoh_fantina",
        "nombre": "Fantina",
        "titulo": "La Bailarina de Fantasmas",
        "tipo": "Fantasma",
        "medalla": "Medalla Niebla",
        "emoji": "👻",
        "ciudad": "Hearthome City",
        "recompensa": 4032,
        "mt_recompensa": {"nombre_es": "Bola Sombra", "move_key": "shadowball", "mt_num": 92},
        "equipo": [
            {"pokemon_id": 200, "nivel": 32, "moves": ["psywave", "confuseray", "meanlook", "hex"]},
            {"pokemon_id": 355, "nivel": 32, "moves": ["shadowball", "confuseray", "shadowsneak", "destinybond"]},
            {"pokemon_id": 356, "nivel": 36, "moves": ["shadowball", "shadowsneak", "hex", "destinybond"]},
            {"pokemon_id": 429, "nivel": 38, "moves": ["shadowball", "calmmind", "confuseray", "hex"]},
        ],
        "ia_config": {"estrategia": "trap_damage", "notas": "Confuse Ray + Mean Look; Mismagius con Calm Mind"},
    },
    {
        "id": "sinnoh_byron",
        "nombre": "Byron",
        "titulo": "El Fortaleza de Acero",
        "tipo": "Acero",
        "medalla": "Medalla Mine",
        "emoji": "⚙️",
        "ciudad": "Canalave City",
        "recompensa": 4704,
        "mt_recompensa": {"nombre_es": "Pulso Flash", "move_key": "flashcannon", "mt_num": 104},
        "equipo": [
            {"pokemon_id": 436, "nivel": 36, "moves": ["tackle", "irondefense", "confuseray", "flashcannon"]},
            {"pokemon_id": 82,  "nivel": 36, "moves": ["thunderbolt", "flashcannon", "magnetrise", "explosion"]},
            {"pokemon_id": 437, "nivel": 39, "moves": ["irondefense", "flashcannon", "payback", "curse"]},
            {"pokemon_id": 208, "nivel": 41, "moves": ["earthquake", "irontail", "irondefense", "crunch"]},
        ],
        "ia_config": {"estrategia": "defensive", "notas": "Iron Defense + status; Steelix con Earthquake"},
    },
    {
        "id": "sinnoh_candice",
        "nombre": "Candice",
        "titulo": "La Dama del Hielo",
        "tipo": "Hielo",
        "medalla": "Medalla Icicle",
        "emoji": "🧊",
        "ciudad": "Snowpoint City",
        "recompensa": 5376,
        "mt_recompensa": {"nombre_es": "Avalancha", "move_key": "avalanche", "mt_num": 51},
        "equipo": [
            {"pokemon_id": 361, "nivel": 38, "moves": ["powdersnow", "encore", "iceball", "icyshard"]},
            {"pokemon_id": 478, "nivel": 40, "moves": ["hailstorm", "blizzard", "shadowball", "hypnosis"]},
            {"pokemon_id": 220, "nivel": 40, "moves": ["iceshard", "mist", "earthquake", "blizzard"]},
            {"pokemon_id": 473, "nivel": 44, "moves": ["blizzard", "earthquake", "iceshard", "stoneedge"]},
        ],
        "ia_config": {"estrategia": "status_first", "notas": "Hail + Blizzard; Hypnosis con Froslass"},
    },
    {
        "id": "sinnoh_volkner",
        "nombre": "Volkner",
        "titulo": "El Genio Eléctrico",
        "tipo": "Eléctrico",
        "medalla": "Medalla Beacon",
        "emoji": "⚡",
        "ciudad": "Ciudad Sunyshore",
        "recompensa": 9360,
        "mt_recompensa": {"nombre_es": "Voltio Cruel", "move_key": "chargebeam", "mt_num": 57},
        "equipo": [
            {"pokemon_id": 405, "nivel": 46, "moves": ["thunderbolt", "thunder", "icefang", "firepunch"]},
            {"pokemon_id": 82,  "nivel": 46, "moves": ["thunderbolt", "explosion", "lightscreen", "flashcannon"]},
            {"pokemon_id": 419, "nivel": 47, "moves": ["waterfall", "aquajet", "crunch", "thunderwave"]},
            {"pokemon_id": 466, "nivel": 50, "moves": ["thunder", "thunderpunch", "firepunch", "icepunch"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Thunder Wave para paralizar; Electivire cierra"},
    },
]

# ──────────────────────────────────────────────────────────────
# TESELIA / UNOVA  (referencia Black / White)
# ──────────────────────────────────────────────────────────────
_TESELIA_GYMS: List[Dict] = [
    {
        "id": "teselia_cilan",
        "nombre": "Cilan",
        "titulo": "El Somelier Planta",
        "tipo": "Planta",
        "medalla": "Medalla Trébol",
        "emoji": "🌿",
        "ciudad": "Striaton City",
        "recompensa": 840,
        "mt_recompensa": {"nombre_es": "Vinculo Hierba", "move_key": "workup", "mt_num": 83},
        "equipo": [
            {"pokemon_id": 511, "nivel": 12, "moves": ["leer", "lick", "vinewhip", "growth"]},
            {"pokemon_id": 512, "nivel": 14, "moves": ["growth", "vinewhip", "synthesis", "leechseed"]},
        ],
        "ia_config": {"estrategia": "mixed", "notas": "Growth + Vine Whip; Leech Seed para desgaste"},
    },
    {
        "id": "teselia_lenora",
        "nombre": "Lenora",
        "titulo": "La Guardiana del Museo",
        "tipo": "Normal",
        "medalla": "Medalla Básica",
        "emoji": "⭐",
        "ciudad": "Nacrene City",
        "recompensa": 1680,
        "mt_recompensa": {"nombre_es": "Retaliar", "move_key": "retaliate", "mt_num": 67},
        "equipo": [
            {"pokemon_id": 505, "nivel": 18, "moves": ["tackle", "bite", "doubleteam", "hypnosis"]},
            {"pokemon_id": 542, "nivel": 20, "moves": ["retaliate", "hypnosis", "crunch", "headbutt"]},
        ],
        "ia_config": {"estrategia": "status_first", "notas": "Hypnosis con Watchog; Retaliate como respuesta"},
    },
    {
        "id": "teselia_burgh",
        "nombre": "Burgh",
        "titulo": "El Artista de Bichos",
        "tipo": "Bicho",
        "medalla": "Medalla Insecta",
        "emoji": "🐛",
        "ciudad": "Castelia City",
        "recompensa": 2268,
        "mt_recompensa": {"nombre_es": "Vuelta en U", "move_key": "uturn", "mt_num": 56},
        "equipo": [
            {"pokemon_id": 540, "nivel": 21, "moves": ["stringshot", "megadrain", "leechseed", "ingrain"]},
            {"pokemon_id": 545, "nivel": 22, "moves": ["poison sting", "bug bite", "pursuit", "rollout"]},
            {"pokemon_id": 543, "nivel": 22, "moves": ["uturn", "poisonsting", "stringshot", "bug bite"]},
            {"pokemon_id": 546, "nivel": 24, "moves": ["uturn", "hyper beam", "bug bite", "solar beam"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "U-Turn para pivotear; Leavanny con Hyper Beam"},
    },
    {
        "id": "teselia_elesa",
        "nombre": "Elesa",
        "titulo": "La Modelo Eléctrica",
        "tipo": "Eléctrico",
        "medalla": "Medalla Dinamo",
        "emoji": "⚡",
        "ciudad": "Nimbasa City",
        "recompensa": 3024,
        "mt_recompensa": {"nombre_es": "Voltio Cruel", "move_key": "voltswitch", "mt_num": 48},
        "equipo": [
            {"pokemon_id": 602, "nivel": 25, "moves": ["thundershock", "thunderwave", "charge", "electro ball"]},
            {"pokemon_id": 602, "nivel": 25, "moves": ["thundershock", "thunderwave", "charge", "electro ball"]},
            {"pokemon_id": 604, "nivel": 28, "moves": ["voltswitch", "thunderbolt", "thunderwave", "discharge"]},
        ],
        "ia_config": {"estrategia": "status_first", "notas": "Thunder Wave + Volt Switch para desgaste"},
    },
    {
        "id": "teselia_clay",
        "nombre": "Clay",
        "titulo": "El Minero de Tierra",
        "tipo": "Tierra",
        "medalla": "Medalla Polvo",
        "emoji": "🌍",
        "ciudad": "Driftveil City",
        "recompensa": 3696,
        "mt_recompensa": {"nombre_es": "Excavar", "move_key": "dig", "mt_num": 15},
        "equipo": [
            {"pokemon_id": 536, "nivel": 29, "moves": ["bulldoze", "mud bomb", "mud sport", "mudshot"]},
            {"pokemon_id": 530, "nivel": 31, "moves": ["earthquake", "rockslide", "stoneedge", "bulldoze"]},
            {"pokemon_id": 553, "nivel": 33, "moves": ["earthquake", "dig", "rockslide", "bulldoze"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Earthquake spam; Krookodile cierra"},
    },
    {
        "id": "teselia_skyla",
        "nombre": "Skyla",
        "titulo": "La Piloto del Viento",
        "tipo": "Volador",
        "medalla": "Medalla Jet",
        "emoji": "🦅",
        "ciudad": "Mistralton City",
        "recompensa": 4368,
        "mt_recompensa": {"nombre_es": "Acrobatismo", "move_key": "acrobatics", "mt_num": 128},
        "equipo": [
            {"pokemon_id": 561, "nivel": 33, "moves": ["acrobatics", "uproar", "ominouswind", "tailwind"]},
            {"pokemon_id": 580, "nivel": 33, "moves": ["acrobatics", "tailwind", "featherdance", "razorwind"]},
            {"pokemon_id": 581, "nivel": 35, "moves": ["acrobatics", "tailwind", "hurricane", "razorwind"]},
            {"pokemon_id": 528, "nivel": 37, "moves": ["acrobatics", "tailwind", "heartst amp", "supersonic"]},
        ],
        "ia_config": {"estrategia": "mixed", "notas": "Tailwind para velocidad; Acrobatics si sin item"},
    },
    {
        "id": "teselia_brycen",
        "nombre": "Brycen",
        "titulo": "El Actor del Hielo",
        "tipo": "Hielo",
        "medalla": "Medalla Glacial",
        "emoji": "🧊",
        "ciudad": "Icirrus City",
        "recompensa": 5040,
        "mt_recompensa": {"nombre_es": "Avalancha", "move_key": "avalanche", "mt_num": 51},
        "equipo": [
            {"pokemon_id": 615, "nivel": 37, "moves": ["blizzard", "iceshard", "hailstorm", "mirrorcoa t"]},
            {"pokemon_id": 460, "nivel": 37, "moves": ["blizzard", "ingrain", "iceshard", "woodhammer"]},
            {"pokemon_id": 614, "nivel": 39, "moves": ["blizzard", "earthquake", "iceshard", "flail"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Hail + Blizzard; Beartic cierra con Earthquake"},
    },
    {
        "id": "teselia_iris",
        "nombre": "Iris",
        "titulo": "La Hija del Dragón",
        "tipo": "Dragón",
        "medalla": "Medalla Leyenda",
        "emoji": "🐉",
        "ciudad": "Opelucid City",
        "recompensa": 9240,
        "mt_recompensa": {"nombre_es": "Garra Dragón", "move_key": "dragonclaw", "mt_num": 116},
        "equipo": [
            {"pokemon_id": 611, "nivel": 41, "moves": ["dragondance", "dragonclaw", "crunch", "ember"]},
            {"pokemon_id": 612, "nivel": 43, "moves": ["dragondance", "outrage", "crunch", "stoneedge"]},
            {"pokemon_id": 621, "nivel": 46, "moves": ["earthquake", "dragonclaw", "stoneedge", "crunch"]},
        ],
        "ia_config": {"estrategia": "setup_sweep", "notas": "Dragon Dance antes de atacar; Outrage con Fraxure"},
    },
]

# ──────────────────────────────────────────────────────────────
# KALOS  (referencia X / Y)
# ──────────────────────────────────────────────────────────────
_KALOS_GYMS: List[Dict] = [
    {
        "id": "kalos_viola",
        "nombre": "Viola",
        "titulo": "La Fotógrafa de Insectos",
        "tipo": "Bicho",
        "medalla": "Medalla Ovillo",
        "emoji": "🐛",
        "ciudad": "Ciudad Santalune",
        "recompensa": 1008,
        "mt_recompensa": {"nombre_es": "Vuelta en U", "move_key": "uturn", "mt_num": 56},
        "equipo": [
            {"pokemon_id": 290, "nivel": 10, "moves": ["tackle", "harden", "absorb", "string shot"]},
            {"pokemon_id": 291, "nivel": 12, "moves": ["tackle", "bug bite", "absorb", "water sport"]},
            {"pokemon_id": 14,  "nivel": 14, "moves": ["sticky web", "supersonic", "bug bite", "string shot"]},
        ],
        "ia_config": {"estrategia": "status_first", "notas": "Sticky Web para bajar velocidad; Vivillon cierra"},
    },
    {
        "id": "kalos_grant",
        "nombre": "Grant",
        "titulo": "El Escalador de Roca",
        "tipo": "Roca",
        "medalla": "Medalla Acantilado",
        "emoji": "🪨",
        "ciudad": "Ciudad Cyllage",
        "recompensa": 1890,
        "mt_recompensa": {"nombre_es": "Trampa Rocas", "move_key": "stealthrock", "mt_num": 76},
        "equipo": [
            {"pokemon_id": 345, "nivel": 25, "moves": ["ancient power", "acid", "harden", "water gun"]},
            {"pokemon_id": 346, "nivel": 25, "moves": ["ancient power", "acid", "leer", "earth power"]},
            {"pokemon_id": 139, "nivel": 28, "moves": ["ancient power", "body slam", "protect", "stealth rock"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Stealth Rock al inicio; Ancient Power para STAB"},
    },
    {
        "id": "kalos_korrina",
        "nombre": "Korrina",
        "titulo": "La Luchadora Patinadora",
        "tipo": "Lucha",
        "medalla": "Medalla Rumble",
        "emoji": "🥊",
        "ciudad": "Ciudad Shalour",
        "recompensa": 2646,
        "mt_recompensa": {"nombre_es": "Golpe Bajo", "move_key": "lowsweep", "mt_num": 60},
        "equipo": [
            {"pokemon_id": 237, "nivel": 29, "moves": ["foresight", "lowkick", "detect", "rolling kick"]},
            {"pokemon_id": 237, "nivel": 29, "moves": ["foresight", "lowkick", "detect", "fake out"]},
            {"pokemon_id": 448, "nivel": 32, "moves": ["swords dance", "bone rush", "power-up punch", "quick attack"]},
        ],
        "ia_config": {"estrategia": "setup_sweep", "notas": "Lucario Mega (en juego oficial) con Swords Dance"},
    },
    {
        "id": "kalos_ramos",
        "nombre": "Ramos",
        "titulo": "El Anciano Jardinero",
        "tipo": "Planta",
        "medalla": "Medalla Plantas",
        "emoji": "🌿",
        "ciudad": "Ciudad Coumarine",
        "recompensa": 3444,
        "mt_recompensa": {"nombre_es": "Drenadora", "move_key": "gigadrain", "mt_num": 57},
        "equipo": [
            {"pokemon_id": 101, "nivel": 30, "moves": ["mega drain", "worry seed", "leech seed", "cotton spore"]},
            {"pokemon_id": 192, "nivel": 34, "moves": ["sunny day", "solar beam", "synthesis", "petal dance"]},
            {"pokemon_id": 189, "nivel": 34, "moves": ["solar beam", "cotton spore", "giga drain", "fly"]},
        ],
        "ia_config": {"estrategia": "mixed", "notas": "Sunny Day + Solarbeam; Leech Seed para desgaste"},
    },
    {
        "id": "kalos_clemont",
        "nombre": "Clemont",
        "titulo": "El Chico Inventor",
        "tipo": "Eléctrico",
        "medalla": "Medalla Voltio",
        "emoji": "⚡",
        "ciudad": "Ciudad Lumiose",
        "recompensa": 4284,
        "mt_recompensa": {"nombre_es": "Señuelo", "move_key": "thunderbolt", "mt_num": 85},
        "equipo": [
            {"pokemon_id": 135, "nivel": 35, "moves": ["thunder fang", "discharge", "agility", "swift"]},
            {"pokemon_id": 417, "nivel": 35, "moves": ["discharge", "nuzzle", "encore", "quick attack"]},
            {"pokemon_id": 101, "nivel": 37, "moves": ["thunder", "discharge", "charge", "explosion"]},
            {"pokemon_id": 523, "nivel": 40, "moves": ["thunderbolt", "discharge", "flame charge", "bulldoze"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Nuzzle parálisis; Manectric con Discharge"},
    },
    {
        "id": "kalos_valerie",
        "nombre": "Valerie",
        "titulo": "La Dama del Hada",
        "tipo": "Hada",
        "medalla": "Medalla Hada",
        "emoji": "🌸",
        "ciudad": "Ciudad Laverre",
        "recompensa": 5124,
        "mt_recompensa": {"nombre_es": "Encantamiento", "move_key": "dazzlinggleam", "mt_num": 79},
        "equipo": [
            {"pokemon_id": 35,  "nivel": 38, "moves": ["stored power", "metronome", "doubleslap", "sing"]},
            {"pokemon_id": 281, "nivel": 39, "moves": ["charm", "dazzling gleam", "draining kiss", "disarming voice"]},
            {"pokemon_id": 282, "nivel": 42, "moves": ["moonblast", "calm mind", "dazzling gleam", "psyshock"]},
        ],
        "ia_config": {"estrategia": "setup_sweep", "notas": "Calm Mind con Gardevoir; Moonblast como STAB"},
    },
    {
        "id": "kalos_olympia",
        "nombre": "Olympia",
        "titulo": "La Astro-Adivina",
        "tipo": "Psíquico",
        "medalla": "Medalla Lunar",
        "emoji": "🔮",
        "ciudad": "Ciudad Anistar",
        "recompensa": 5964,
        "mt_recompensa": {"nombre_es": "Psíquico", "move_key": "psychic", "mt_num": 63},
        "equipo": [
            {"pokemon_id": 338, "nivel": 44, "moves": ["solar beam", "cosmic power", "psychic", "light screen"]},
            {"pokemon_id": 337, "nivel": 44, "moves": ["cosmic power", "psychic", "earthquake", "moonblast"]},
            {"pokemon_id": 477, "nivel": 48, "moves": ["psychic", "shadow ball", "calm mind", "thunder wave"]},
        ],
        "ia_config": {"estrategia": "setup_sweep", "notas": "Cosmic Power + Calm Mind; Dusknoir con Shadow Ball"},
    },
    {
        "id": "kalos_wulfric",
        "nombre": "Wulfric",
        "titulo": "El Oso del Hielo",
        "tipo": "Hielo",
        "medalla": "Medalla Iceberg",
        "emoji": "🧊",
        "ciudad": "Ciudad Snowbelle",
        "recompensa": 9240,
        "mt_recompensa": {"nombre_es": "Ventisca", "move_key": "blizzard", "mt_num": 141},
        "equipo": [
            {"pokemon_id": 460, "nivel": 56, "moves": ["blizzard", "ice shard", "ingrain", "wood hammer"]},
            {"pokemon_id": 478, "nivel": 55, "moves": ["blizzard", "shadow ball", "hypnosis", "hail"]},
            {"pokemon_id": 699, "nivel": 59, "moves": ["blizzard", "bulldoze", "rock tomb", "hyper voice"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Hail + Blizzard; Aurorus cierra con Hyper Voice"},
    },
]

# ──────────────────────────────────────────────────────────────
# ALOLA  (referencia Sun / Moon — Grand Trials de los Kahunas)
# Los 4 Kahunas son el equivalente a 4 Líderes + 4 pruebas de capitán
# como los otros 4 "gimnasios". Medallas = Sello Z de cada isla.
# ──────────────────────────────────────────────────────────────
_ALOLA_GYMS: List[Dict] = [
    # Isla Melemele
    {
        "id": "alola_ilima",
        "nombre": "Ilima",
        "titulo": "Capitán de la Isla Melemele",
        "tipo": "Normal",
        "medalla": "Sello Z Normal",
        "emoji": "⭐",
        "ciudad": "Iki Town",
        "recompensa": 1800,
        "mt_recompensa": {"nombre_es": "Fachada", "move_key": "facade", "mt_num": 31},
        "equipo": [
            {"pokemon_id": 17,  "nivel": 11, "moves": ["tackle", "growl", "quick attack", "mud slap"]},
            {"pokemon_id": 20,  "nivel": 13, "moves": ["tackle", "tail whip", "quick attack", "hyper fang"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Quick Attack para prioridad"},
    },
    {
        "id": "alola_hala",
        "nombre": "Hala",
        "titulo": "Kahuna de Melemele",
        "tipo": "Lucha",
        "medalla": "Gran Sello Z Lucha",
        "emoji": "🥊",
        "ciudad": "Iki Town",
        "recompensa": 3360,
        "mt_recompensa": {"nombre_es": "Puñetazo Drenaje", "move_key": "drainpunch", "mt_num": 120},
        "equipo": [
            {"pokemon_id": 296, "nivel": 20, "moves": ["bullet punch", "arm thrust", "fake out", "belly drum"]},
            {"pokemon_id": 107, "nivel": 20, "moves": ["fire punch", "ice punch", "thunder punch", "mach punch"]},
            {"pokemon_id": 62,  "nivel": 22, "moves": ["hypnosis", "belly drum", "waterfall", "double-edge"]},
        ],
        "ia_config": {"estrategia": "setup_sweep", "notas": "Belly Drum con Poliwrath; Hitmonchan con punches"},
    },
    # Isla Akala
    {
        "id": "alola_lana",
        "nombre": "Lana",
        "titulo": "Capitana de la Isla Akala",
        "tipo": "Agua",
        "medalla": "Sello Z Agua",
        "emoji": "💧",
        "ciudad": "Konikoni City",
        "recompensa": 2880,
        "mt_recompensa": {"nombre_es": "Surf", "move_key": "surf", "mt_num": 90},
        "equipo": [
            {"pokemon_id": 747, "nivel": 18, "moves": ["liquidation", "poison sting", "venoshock", "submission"]},
            {"pokemon_id": 422, "nivel": 18, "moves": ["brine", "water pulse", "mud bomb", "recover"]},
            {"pokemon_id": 746, "nivel": 20, "moves": ["water gun", "brine", "water pulse", "soak"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Wishiwashi en School Form es poderoso"},
    },
    {
        "id": "alola_olivia",
        "nombre": "Olivia",
        "titulo": "Kahuna de Akala",
        "tipo": "Roca",
        "medalla": "Gran Sello Z Roca",
        "emoji": "🪨",
        "ciudad": "Konikoni City",
        "recompensa": 4368,
        "mt_recompensa": {"nombre_es": "Rocas Trampa", "move_key": "stealthrock", "mt_num": 76},
        "equipo": [
            {"pokemon_id": 524, "nivel": 26, "moves": ["rock blast", "mud-slap", "smack down", "stealth rock"]},
            {"pokemon_id": 525, "nivel": 26, "moves": ["rock blast", "rock slide", "bulldoze", "stealth rock"]},
            {"pokemon_id": 764, "nivel": 27, "moves": ["rock throw", "leer", "bite", "take down"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Stealth Rock al inicio; Lycanroc cierra"},
    },
    # Isla Ula'ula
    {
        "id": "alola_sophocles",
        "nombre": "Sophocles",
        "titulo": "Capitán de la Isla Ula'ula",
        "tipo": "Eléctrico",
        "medalla": "Sello Z Eléctrico",
        "emoji": "⚡",
        "ciudad": "Hokulani Observatory",
        "recompensa": 3696,
        "mt_recompensa": {"nombre_es": "Trueno", "move_key": "thunderbolt", "mt_num": 85},
        "equipo": [
            {"pokemon_id": 81,  "nivel": 29, "moves": ["thunder wave", "spark", "flash cannon", "sonic boom"]},
            {"pokemon_id": 82,  "nivel": 30, "moves": ["thunderbolt", "discharge", "sonic boom", "explosion"]},
            {"pokemon_id": 462, "nivel": 33, "moves": ["thunderbolt", "flash cannon", "thunder wave", "magnet rise"]},
        ],
        "ia_config": {"estrategia": "status_first", "notas": "Thunder Wave + Thunderbolt; Magnezone cierra"},
    },
    {
        "id": "alola_nanu",
        "nombre": "Nanu",
        "titulo": "Kahuna de Ula'ula",
        "tipo": "Siniestro",
        "medalla": "Gran Sello Z Siniestro",
        "emoji": "🌑",
        "ciudad": "Po Town",
        "recompensa": 5376,
        "mt_recompensa": {"nombre_es": "Golpe Feo", "move_key": "darkpulse", "mt_num": 78},
        "equipo": [
            {"pokemon_id": 197, "nivel": 33, "moves": ["night slash", "shadow ball", "quick attack", "screech"]},
            {"pokemon_id": 53,  "nivel": 33, "moves": ["night slash", "fake out", "taunt", "torment"]},
            {"pokemon_id": 53,  "nivel": 33, "moves": ["night slash", "fake out", "taunt", "torment"]},
            {"pokemon_id": 765, "nivel": 35, "moves": ["dark pulse", "night slash", "crunch", "taunt"]},
        ],
        "ia_config": {"estrategia": "trap_damage", "notas": "Taunt + Torment; Alolan Persian cierra"},
    },
    # Isla Poni
    {
        "id": "alola_mina",
        "nombre": "Mina",
        "titulo": "Capitana de la Isla Poni",
        "tipo": "Hada",
        "medalla": "Sello Z Hada",
        "emoji": "🌸",
        "ciudad": "Seafolk Village",
        "recompensa": 4704,
        "mt_recompensa": {"nombre_es": "Destello Deslumbrador", "move_key": "dazzlinggleam", "mt_num": 79},
        "equipo": [
            {"pokemon_id": 303, "nivel": 51, "moves": ["fairy wind", "tackle", "fake tears", "astonish"]},
            {"pokemon_id": 35,  "nivel": 51, "moves": ["doubleslap", "sing", "moonblast", "metronome"]},
            {"pokemon_id": 468, "nivel": 53, "moves": ["moonblast", "swift", "air slash", "dazzling gleam"]},
        ],
        "ia_config": {"estrategia": "mixed", "notas": "Sing para dormir; Togekiss con Moonblast"},
    },
    {
        "id": "alola_hapu",
        "nombre": "Hapu",
        "titulo": "Kahuna de Poni",
        "tipo": "Tierra",
        "medalla": "Gran Sello Z Tierra",
        "emoji": "🌍",
        "ciudad": "Exeggutor Island",
        "recompensa": 9360,
        "mt_recompensa": {"nombre_es": "Terremoto", "move_key": "earthquake", "mt_num": 96},
        "equipo": [
            {"pokemon_id": 50,  "nivel": 53, "moves": ["earthquake", "mud bomb", "shadow claw", "bulldoze"]},
            {"pokemon_id": 340, "nivel": 53, "moves": ["earthquake", "muddy water", "yawn", "amnesia"]},
            {"pokemon_id": 105, "nivel": 54, "moves": ["earthquake", "bone rush", "rock slide", "double-edge"]},
            {"pokemon_id": 770, "nivel": 57, "moves": ["earthquake", "shore up", "rock blast", "bulldoze"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Earthquake todo el día; Mudsdale cierra"},
    },
]

# ──────────────────────────────────────────────────────────────
# GALAR  (referencia Sword / Shield)
# ──────────────────────────────────────────────────────────────
_GALAR_GYMS: List[Dict] = [
    {
        "id": "galar_milo",
        "nombre": "Milo",
        "titulo": "El Pastor Planta",
        "tipo": "Planta",
        "medalla": "Medalla Planta",
        "emoji": "🌿",
        "ciudad": "Turffield",
        "recompensa": 1680,
        "mt_recompensa": {"nombre_es": "Vendetta", "move_key": "trailblaze", "mt_num": 20},
        "equipo": [
            {"pokemon_id": 829, "nivel": 19, "moves": ["cotton guard", "round", "mega drain", "cotton spore"]},
            {"pokemon_id": 830, "nivel": 20, "moves": ["cotton guard", "cotton spore", "round", "giga drain"]},
        ],
        "ia_config": {"estrategia": "defensive", "notas": "Cotton Guard para subir defensa; desgaste con Giga Drain"},
    },
    {
        "id": "galar_nessa",
        "nombre": "Nessa",
        "titulo": "La Modelo del Océano",
        "tipo": "Agua",
        "medalla": "Medalla Agua",
        "emoji": "💧",
        "ciudad": "Hulbury",
        "recompensa": 2520,
        "mt_recompensa": {"nombre_es": "Buceo", "move_key": "dive", "mt_num": 6},
        "equipo": [
            {"pokemon_id": 833, "nivel": 22, "moves": ["water gun", "bite", "mud shot", "bulldoze"]},
            {"pokemon_id": 747, "nivel": 23, "moves": ["liquidation", "poison sting", "venoshock", "spite"]},
            {"pokemon_id": 834, "nivel": 24, "moves": ["liquidation", "crunch", "bulldoze", "rain dance"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Rain Dance + Liquidation; Drednaw cierra"},
    },
    {
        "id": "galar_kabu",
        "nombre": "Kabu",
        "titulo": "El Veterano del Fuego",
        "tipo": "Fuego",
        "medalla": "Medalla Fuego",
        "emoji": "🔥",
        "ciudad": "Motostoke",
        "recompensa": 3360,
        "mt_recompensa": {"nombre_es": "Carga Fuego", "move_key": "flamecharge", "mt_num": 38},
        "equipo": [
            {"pokemon_id": 828, "nivel": 25, "moves": ["burning jealousy", "fake out", "torment", "u-turn"]},
            {"pokemon_id": 219, "nivel": 25, "moves": ["fire spin", "smog", "ember", "rock throw"]},
            {"pokemon_id": 219, "nivel": 25, "moves": ["fire spin", "smog", "ember", "rock throw"]},
            {"pokemon_id": 338, "nivel": 27, "moves": ["fire spin", "flame charge", "solar beam", "cosmic power"]},
        ],
        "ia_config": {"estrategia": "trap_damage", "notas": "Fire Spin para atrapar; Flame Charge sube velocidad"},
    },
    {
        "id": "galar_bea",
        "nombre": "Bea",
        "titulo": "La Luchadora Invicta",
        "tipo": "Lucha",
        "medalla": "Medalla Lucha",
        "emoji": "🥊",
        "ciudad": "Stow-on-Side",
        "recompensa": 4200,
        "mt_recompensa": {"nombre_es": "Inversión", "move_key": "reversal", "mt_num": 18},
        "equipo": [
            {"pokemon_id": 870, "nivel": 34, "moves": ["revenge", "detect", "bulldoze", "focus energy"]},
            {"pokemon_id": 68,  "nivel": 34, "moves": ["focus punch", "bullet punch", "mega punch", "leer"]},
            {"pokemon_id": 448, "nivel": 35, "moves": ["close combat", "swords dance", "quick attack", "metal claw"]},
            {"pokemon_id": 308, "nivel": 36, "moves": ["close combat", "drain punch", "detect", "bulk up"]},
        ],
        "ia_config": {"estrategia": "setup_sweep", "notas": "Bulk Up con Medicham; Close Combat con Falinks"},
    },
    {
        "id": "galar_opal",
        "nombre": "Opal",
        "titulo": "La Veterana del Hada",
        "tipo": "Hada",
        "medalla": "Medalla Hada",
        "emoji": "🌸",
        "ciudad": "Ballonlea",
        "recompensa": 5040,
        "mt_recompensa": {"nombre_es": "Velo Sagrado", "move_key": "mistyterrain", "mt_num": 86},
        "equipo": [
            {"pokemon_id": 303, "nivel": 36, "moves": ["charm", "fake tears", "fairy wind", "iron head"]},
            {"pokemon_id": 707, "nivel": 36, "moves": ["dazzling gleam", "charm", "thunder wave", "flash"]},
            {"pokemon_id": 282, "nivel": 38, "moves": ["moonblast", "calm mind", "psychic", "dazzling gleam"]},
            {"pokemon_id": 869, "nivel": 40, "moves": ["misty terrain", "dazzling gleam", "sweet kiss", "attract"]},
        ],
        "ia_config": {"estrategia": "setup_sweep", "notas": "Misty Terrain + Calm Mind; Alcremie cierra"},
    },
    {
        "id": "galar_gordie",
        "nombre": "Gordie",
        "titulo": "El Chico de la Roca",
        "tipo": "Roca",
        "medalla": "Medalla Roca",
        "emoji": "🪨",
        "ciudad": "Circhester",
        "recompensa": 5880,
        "mt_recompensa": {"nombre_es": "Roca Afilada", "move_key": "stoneedge", "mt_num": 150},
        "equipo": [
            {"pokemon_id": 557, "nivel": 40, "moves": ["rock blast", "smack down", "stealth rock", "protect"]},
            {"pokemon_id": 524, "nivel": 40, "moves": ["rock blast", "stealth rock", "headbutt", "bulldoze"]},
            {"pokemon_id": 208, "nivel": 41, "moves": ["iron tail", "rock slide", "stealth rock", "earthquake"]},
            {"pokemon_id": 185, "nivel": 42, "moves": ["rock slide", "stealth rock", "smack down", "wood hammer"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Stealth Rock y Rock Blast; Coalossal cierra"},
    },
    {
        "id": "galar_melony",
        "nombre": "Melony",
        "titulo": "La Mamá del Hielo",
        "tipo": "Hielo",
        "medalla": "Medalla Hielo",
        "emoji": "🧊",
        "ciudad": "Circhester",
        "recompensa": 6720,
        "mt_recompensa": {"nombre_es": "Ventisca", "move_key": "blizzard", "mt_num": 141},
        "equipo": [
            {"pokemon_id": 873, "nivel": 40, "moves": ["icicle crash", "icy wind", "freeze-dry", "hail"]},
            {"pokemon_id": 460, "nivel": 40, "moves": ["blizzard", "icy wind", "wood hammer", "ingrain"]},
            {"pokemon_id": 362, "nivel": 42, "moves": ["blizzard", "icy wind", "hail", "iron defense"]},
            {"pokemon_id": 875, "nivel": 44, "moves": ["freeze-dry", "blizzard", "explosion", "brick break"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Hail + Blizzard; Eiscue cierra con Icicle Crash"},
    },
    {
        "id": "galar_raihan",
        "nombre": "Raihan",
        "titulo": "El Campeón de las Tempestades",
        "tipo": "Dragón",
        "medalla": "Medalla Dragón",
        "emoji": "🐉",
        "ciudad": "Hammerlocke",
        "recompensa": 9360,
        "mt_recompensa": {"nombre_es": "Meteoro Dragón", "move_key": "dracometeor", "mt_num": 113},
        "equipo": [
            {"pokemon_id": 530, "nivel": 46, "moves": ["earthquake", "rock slide", "iron head", "bulldoze"]},
            {"pokemon_id": 330, "nivel": 47, "moves": ["dragon claw", "earthquake", "air slash", "agility"]},
            {"pokemon_id": 350, "nivel": 46, "moves": ["scald", "ice beam", "dragon pulse", "attract"]},
            {"pokemon_id": 887, "nivel": 48, "moves": ["draco meteor", "shadow ball", "u-turn", "thunderbolt"]},
        ],
        "ia_config": {"estrategia": "mixed", "notas": "Dragapult cierra con Draco Meteor"},
    },
]

# ──────────────────────────────────────────────────────────────
# PALDEA  (referencia Scarlet / Violet)
# ──────────────────────────────────────────────────────────────
_PALDEA_GYMS: List[Dict] = [
    {
        "id": "paldea_katy",
        "nombre": "Katy",
        "titulo": "La Repostera de Bichos",
        "tipo": "Bicho",
        "medalla": "Medalla Bicho",
        "emoji": "🐛",
        "ciudad": "Ciudad Cortondo",
        "recompensa": 1680,
        "mt_recompensa": {"nombre_es": "Picadura", "move_key": "bugbite", "mt_num": 21},
        "equipo": [
            {"pokemon_id": 915, "nivel": 14, "moves": ["bug bite", "bite", "acupressure", "tail whip"]},
            {"pokemon_id": 165, "nivel": 14, "moves": ["bug bite", "baton pass", "string shot", "leech life"]},
            {"pokemon_id": 632, "nivel": 15, "moves": ["bug bite", "iron head", "metal sound", "false swipe"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Bug Bite para STAB; Durant con Iron Head"},
    },
    {
        "id": "paldea_brassius",
        "nombre": "Brasus",
        "titulo": "El Artista Planta",
        "tipo": "Planta",
        "medalla": "Medalla Planta",
        "emoji": "🌿",
        "ciudad": "Ciudad Artazon",
        "recompensa": 2520,
        "mt_recompensa": {"nombre_es": "Drenadora", "move_key": "gigadrain", "mt_num": 57},
        "equipo": [
            {"pokemon_id": 192, "nivel": 16, "moves": ["petal blizzard", "sunny day", "growth", "mega drain"]},
            {"pokemon_id": 192, "nivel": 16, "moves": ["petal blizzard", "sunny day", "growth", "mega drain"]},
            {"pokemon_id": 960, "nivel": 17, "moves": ["giga drain", "ingrain", "solar beam", "sunny day"]},
        ],
        "ia_config": {"estrategia": "mixed", "notas": "Sunny Day + Solar Beam; Sudowoodo Tera Planta"},
    },
    {
        "id": "paldea_iono",
        "nombre": "Iolanda",
        "titulo": "La Streamear Eléctrica",
        "tipo": "Eléctrico",
        "medalla": "Medalla Eléctrico",
        "emoji": "⚡",
        "ciudad": "Ciudad Levonia",
        "recompensa": 3360,
        "mt_recompensa": {"nombre_es": "Bola Voltio", "move_key": "electroball", "mt_num": 72},
        "equipo": [
            {"pokemon_id": 877, "nivel": 23, "moves": ["thunder wave", "thunderbolt", "nuzzle", "discharge"]},
            {"pokemon_id": 877, "nivel": 23, "moves": ["thunder wave", "thunderbolt", "nuzzle", "discharge"]},
            {"pokemon_id": 602, "nivel": 23, "moves": ["thunderbolt", "charge", "electro ball", "thunder wave"]},
            {"pokemon_id": 936, "nivel": 24, "moves": ["thunderbolt", "thunder wave", "electro ball", "volt switch"]},
        ],
        "ia_config": {"estrategia": "status_first", "notas": "Thunder Wave + Volt Switch; Bellibolt cierra"},
    },
    {
        "id": "paldea_kofu",
        "nombre": "Kofu",
        "titulo": "El Chef del Agua",
        "tipo": "Agua",
        "medalla": "Medalla Agua",
        "emoji": "💧",
        "ciudad": "Ciudad Cascarrafa",
        "recompensa": 4200,
        "mt_recompensa": {"nombre_es": "Surf", "move_key": "surf", "mt_num": 90},
        "equipo": [
            {"pokemon_id": 422, "nivel": 29, "moves": ["water pulse", "mud bomb", "recover", "brine"]},
            {"pokemon_id": 980, "nivel": 29, "moves": ["scald", "recover", "lunge", "surf"]},
            {"pokemon_id": 550, "nivel": 30, "moves": ["surf", "scald", "ice beam", "waterfall"]},
        ],
        "ia_config": {"estrategia": "mixed", "notas": "Crabominable cierra con Ice Hammer; recover para aguantar"},
    },
    {
        "id": "paldea_larry",
        "nombre": "Larry",
        "titulo": "El Funcionario Normal",
        "tipo": "Normal",
        "medalla": "Medalla Normal",
        "emoji": "⭐",
        "ciudad": "Ciudad Medali",
        "recompensa": 5040,
        "mt_recompensa": {"nombre_es": "Agilidad", "move_key": "agility", "mt_num": 3},
        "equipo": [
            {"pokemon_id": 17,  "nivel": 35, "moves": ["facade", "hyper voice", "feather dance", "quick attack"]},
            {"pokemon_id": 18,  "nivel": 35, "moves": ["hyper voice", "facade", "feather dance", "tailwind"]},
            {"pokemon_id": 983, "nivel": 36, "moves": ["hyper voice", "facade", "roost", "tailwind"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Staraptor con Hyper Voice; Facade con estado"},
    },
    {
        "id": "paldea_ryme",
        "nombre": "Ryme",
        "titulo": "La Rapera Fantasma",
        "tipo": "Fantasma",
        "medalla": "Medalla Fantasma",
        "emoji": "👻",
        "ciudad": "Ciudad Alfornada",
        "recompensa": 5880,
        "mt_recompensa": {"nombre_es": "Bola Sombra", "move_key": "shadowball", "mt_num": 92},
        "equipo": [
            {"pokemon_id": 562, "nivel": 41, "moves": ["shadow ball", "will-o-wisp", "hex", "memento"]},
            {"pokemon_id": 592, "nivel": 41, "moves": ["shadow ball", "hex", "minimize", "recover"]},
            {"pokemon_id": 593, "nivel": 42, "moves": ["hex", "shadow ball", "hydro pump", "rain dance"]},
            {"pokemon_id": 778, "nivel": 42, "moves": ["shadow sneak", "shadow claw", "shadow ball", "wood hammer"]},
        ],
        "ia_config": {"estrategia": "trap_damage", "notas": "Will-O-Wisp + Hex; Mimikyu con Shadow Sneak prioridad"},
    },
    {
        "id": "paldea_tulip",
        "nombre": "Tulipa",
        "titulo": "La Maquilladora Psíquica",
        "tipo": "Psíquico",
        "medalla": "Medalla Psíquico",
        "emoji": "🔮",
        "ciudad": "Ciudad Alfornada",
        "recompensa": 6720,
        "mt_recompensa": {"nombre_es": "Psíquico", "move_key": "psychic", "mt_num": 63},
        "equipo": [
            {"pokemon_id": 561, "nivel": 44, "moves": ["psychic", "air slash", "light screen", "calm mind"]},
            {"pokemon_id": 579, "nivel": 44, "moves": ["psychic", "thunder wave", "calm mind", "psyshock"]},
            {"pokemon_id": 866, "nivel": 45, "moves": ["psychic", "dazzling gleam", "calm mind", "light screen"]},
            {"pokemon_id": 956, "nivel": 45, "moves": ["psychic", "moonblast", "calm mind", "reflect"]},
        ],
        "ia_config": {"estrategia": "setup_sweep", "notas": "Calm Mind masivo; Gardevoir Tera Psíquico cierra"},
    },
    {
        "id": "paldea_grusha",
        "nombre": "Grusha",
        "titulo": "El Snowboarder del Hielo",
        "tipo": "Hielo",
        "medalla": "Medalla Hielo",
        "emoji": "🧊",
        "ciudad": "Ciudad Glaseado",
        "recompensa": 9360,
        "mt_recompensa": {"nombre_es": "Avalancha", "move_key": "avalanche", "mt_num": 51},
        "equipo": [
            {"pokemon_id": 478, "nivel": 47, "moves": ["blizzard", "shadow ball", "hypnosis", "will-o-wisp"]},
            {"pokemon_id": 713, "nivel": 47, "moves": ["avalanche", "rock slide", "earthquake", "icicle crash"]},
            {"pokemon_id": 362, "nivel": 48, "moves": ["blizzard", "flash cannon", "icicle crash", "iron defense"]},
            {"pokemon_id": 975, "nivel": 48, "moves": ["icicle crash", "earthquake", "ice shard", "dragon dance"]},
        ],
        "ia_config": {"estrategia": "aggressive", "notas": "Hail + Blizzard; Cetitan con Dragon Dance"},
    },
]


# ═════════════════════════════════════════════════════════════════════════════
# ALTO MANDO POR REGIÓN
# Misma estructura que gym, con orden secuencial (id: {region}_e4_{nombre},
# el campeón usa {region}_champion).
# Se desbloquea el primero cuando el jugador tiene las 8 medallas; los
# siguientes se desbloquean igual que las salas de gimnasio.
# ═════════════════════════════════════════════════════════════════════════════

_ALTO_MANDO: Dict[str, List[Dict]] = {
    "KANTO": [
        {
            "id": "kanto_e4_lorelei",
            "nombre": "Lorelei",
            "titulo": "La Dama del Hielo",
            "tipo": "Hielo",
            "medalla": "Victoria vs Lorelei",
            "emoji": "🧊",
            "ciudad": "Meseta Añil",
            "recompensa": 8000,
            "mt_recompensa": {"nombre_es": "Ventisca", "move_key": "blizzard", "mt_num": 141},
            "equipo": [
                {"pokemon_id": 87,  "nivel": 54, "moves": ["blizzard", "surf", "body slam", "aurora beam"]},
                {"pokemon_id": 91,  "nivel": 53, "moves": ["blizzard", "surf", "ice beam", "slash"]},
                {"pokemon_id": 80,  "nivel": 54, "moves": ["blizzard", "psychic", "amnesia", "body slam"]},
                {"pokemon_id": 124, "nivel": 54, "moves": ["blizzard", "psychic", "lovely kiss", "ice beam"]},
                {"pokemon_id": 131, "nivel": 56, "moves": ["blizzard", "surf", "body slam", "ice beam"]},
            ],
            "ia_config": {"estrategia": "mixed", "notas": "Lovely Kiss para dormir; Blizzard + Surf para daño"},
        },
        {
            "id": "kanto_e4_bruno",
            "nombre": "Bruno",
            "titulo": "El Guerrero del Músculo",
            "tipo": "Lucha",
            "medalla": "Victoria vs Bruno",
            "emoji": "🥊",
            "ciudad": "Meseta Añil",
            "recompensa": 8500,
            "mt_recompensa": {"nombre_es": "Terremoto", "move_key": "earthquake", "mt_num": 96},
            "equipo": [
                {"pokemon_id": 95,  "nivel": 53, "moves": ["rockthrow", "bind", "slam", "seismic toss"]},
                {"pokemon_id": 95,  "nivel": 55, "moves": ["rockthrow", "bind", "slam", "seismic toss"]},
                {"pokemon_id": 107, "nivel": 54, "moves": ["thunder punch", "ice punch", "fire punch", "submission"]},
                {"pokemon_id": 106, "nivel": 54, "moves": ["hi jump kick", "meditate", "karate chop", "seismic toss"]},
                {"pokemon_id": 68,  "nivel": 58, "moves": ["earthquake", "submission", "rock slide", "seismic toss"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Seismic Toss para daño fijo; Machamp con Earthquake"},
        },
        {
            "id": "kanto_e4_agatha",
            "nombre": "Agatha",
            "titulo": "La Anciana Malvada",
            "tipo": "Fantasma",
            "medalla": "Victoria vs Agatha",
            "emoji": "👻",
            "ciudad": "Meseta Añil",
            "recompensa": 9000,
            "mt_recompensa": {"nombre_es": "Bola Sombra", "move_key": "shadowball", "mt_num": 92},
            "equipo": [
                {"pokemon_id": 94,  "nivel": 54, "moves": ["night shade", "hypnosis", "confuse ray", "mean look"]},
                {"pokemon_id": 93,  "nivel": 53, "moves": ["night shade", "hypnosis", "confuse ray", "shadow ball"]},
                {"pokemon_id": 42,  "nivel": 56, "moves": ["leech life", "confuse ray", "super fang", "shadow ball"]},
                {"pokemon_id": 93,  "nivel": 55, "moves": ["night shade", "hypnosis", "mean look", "shadow ball"]},
                {"pokemon_id": 94,  "nivel": 58, "moves": ["shadow ball", "hypnosis", "confuse ray", "mean look"]},
            ],
            "ia_config": {"estrategia": "trap_damage", "notas": "Mean Look + Confuse Ray + Night Shade; Hypnosis para dormir"},
        },
        {
            "id": "kanto_e4_lance",
            "nombre": "Lance",
            "titulo": "El Maestro Dragón",
            "tipo": "Dragón",
            "medalla": "Victoria vs Lance",
            "emoji": "🐉",
            "ciudad": "Meseta Añil",
            "recompensa": 10000,
            "mt_recompensa": {"nombre_es": "Pulso Dragón", "move_key": "dragonpulse", "mt_num": 87},
            "equipo": [
                {"pokemon_id": 149, "nivel": 56, "moves": ["agility", "hyper beam", "slam", "blizzard"]},
                {"pokemon_id": 148, "nivel": 54, "moves": ["thunder wave", "agility", "slam", "hyper beam"]},
                {"pokemon_id": 148, "nivel": 54, "moves": ["thunder wave", "agility", "slam", "hyper beam"]},
                {"pokemon_id": 131, "nivel": 56, "moves": ["blizzard", "surf", "hydro pump", "body slam"]},
                {"pokemon_id": 149, "nivel": 60, "moves": ["agility", "hyper beam", "blizzard", "thunder"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Agility + Hyper Beam con Dragonite; Blizzard para coberturas"},
        },
        {
            "id": "kanto_champion",
            "nombre": "Blue",
            "titulo": "Campeón de Kanto",
            "tipo": "Mixto",
            "medalla": "Campeón de Kanto",
            "emoji": "👑",
            "ciudad": "Meseta Añil",
            "recompensa": 25000,
            "mt_recompensa": {"nombre_es": "Fuerza Oculta", "move_key": "hyperbeam", "mt_num": 117},
            "equipo": [
                {"pokemon_id": 18,  "nivel": 59, "moves": ["sky attack", "quick attack", "hyper beam", "razor wind"]},
                {"pokemon_id": 59,  "nivel": 58, "moves": ["fire blast", "flamethrower", "extreme speed", "body slam"]},
                {"pokemon_id": 65,  "nivel": 60, "moves": ["psychic", "recover", "reflect", "shadow ball"]},
                {"pokemon_id": 112, "nivel": 59, "moves": ["earthquake", "horn drill", "stone edge", "rock slide"]},
                {"pokemon_id": 130, "nivel": 61, "moves": ["hyper beam", "surf", "body slam", "thunder"]},
                {"pokemon_id": 9,   "nivel": 65, "moves": ["surf", "blizzard", "earthquake", "hyper beam"]},
            ],
            "ia_config": {"estrategia": "mixed", "notas": "Equipo variado; Blastoise como as bajo la manga"},
        },
    ],
    "JOHTO": [
        {
            "id": "johto_e4_will",
            "nombre": "Will",
            "titulo": "El Maestro Psíquico",
            "tipo": "Psíquico",
            "medalla": "Victoria vs Will",
            "emoji": "🔮",
            "ciudad": "Meseta Montoya",
            "recompensa": 9000,
            "mt_recompensa": {"nombre_es": "Calma Mental", "move_key": "calmmind", "mt_num": 129},
            "equipo": [
                {"pokemon_id": 178, "nivel": 40, "moves": ["psychic", "future sight", "shadow ball", "confuseray"]},
                {"pokemon_id": 124, "nivel": 41, "moves": ["psychic", "ice beam", "lovely kiss", "shadow ball"]},
                {"pokemon_id": 178, "nivel": 41, "moves": ["psychic", "future sight", "quick attack", "confuseray"]},
                {"pokemon_id": 196, "nivel": 41, "moves": ["psychic", "calm mind", "shadow ball", "bite"]},
                {"pokemon_id": 178, "nivel": 41, "moves": ["psychic", "future sight", "shadow ball", "confuseray"]},
                {"pokemon_id": 282, "nivel": 41, "moves": ["psychic", "calm mind", "shadow ball", "moonblast"]},
            ],
            "ia_config": {"estrategia": "setup_sweep", "notas": "Calm Mind masivo con Espeon/Gardevoir"},
        },
        {
            "id": "johto_e4_koga",
            "nombre": "Koga",
            "titulo": "El Ninja Venenoso",
            "tipo": "Veneno",
            "medalla": "Victoria vs Koga",
            "emoji": "☠️",
            "ciudad": "Meseta Montoya",
            "recompensa": 9500,
            "mt_recompensa": {"nombre_es": "Tóxico", "move_key": "toxic", "mt_num": 6},
            "equipo": [
                {"pokemon_id": 169, "nivel": 42, "moves": ["toxic", "confuseray", "mean look", "leech life"]},
                {"pokemon_id": 89,  "nivel": 42, "moves": ["toxic", "smokescreen", "minimize", "acid armor"]},
                {"pokemon_id": 110, "nivel": 43, "moves": ["toxic", "smokescreen", "haze", "explosion"]},
                {"pokemon_id": 168, "nivel": 41, "moves": ["toxic", "leech life", "night slash", "shadow ball"]},
                {"pokemon_id": 49,  "nivel": 43, "moves": ["toxic", "psybeam", "stun spore", "silver wind"]},
                {"pokemon_id": 195, "nivel": 46, "moves": ["toxic", "surf", "earthquake", "sludge bomb"]},
            ],
            "ia_config": {"estrategia": "trap_damage", "notas": "Toxic + Mean Look + Minimize; Quagsire cierra"},
        },
        {
            "id": "johto_e4_bruno",
            "nombre": "Bruno",
            "titulo": "El Guerrero del Músculo",
            "tipo": "Lucha",
            "medalla": "Victoria vs Bruno",
            "emoji": "🥊",
            "ciudad": "Meseta Montoya",
            "recompensa": 10000,
            "mt_recompensa": {"nombre_es": "Terremoto", "move_key": "earthquake", "mt_num": 96},
            "equipo": [
                {"pokemon_id": 106, "nivel": 42, "moves": ["hi jump kick", "meditate", "rolling kick", "seismic toss"]},
                {"pokemon_id": 107, "nivel": 42, "moves": ["fire punch", "ice punch", "thunder punch", "quick attack"]},
                {"pokemon_id": 237, "nivel": 42, "moves": ["hi jump kick", "triple kick", "focus energy", "rolling kick"]},
                {"pokemon_id": 68,  "nivel": 46, "moves": ["earthquake", "karate chop", "submission", "strength"]},
                {"pokemon_id": 212, "nivel": 42, "moves": ["swords dance", "slash", "focus energy", "quick attack"]},
                {"pokemon_id": 237, "nivel": 48, "moves": ["hi jump kick", "triple kick", "focus energy", "seismic toss"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Seismic Toss y High Jump Kick directo"},
        },
        {
            "id": "johto_e4_karen",
            "nombre": "Karen",
            "titulo": "La Dama Oscura",
            "tipo": "Siniestro",
            "medalla": "Victoria vs Karen",
            "emoji": "🌑",
            "ciudad": "Meseta Montoya",
            "recompensa": 11000,
            "mt_recompensa": {"nombre_es": "Golpe Feo", "move_key": "darkpulse", "mt_num": 78},
            "equipo": [
                {"pokemon_id": 197, "nivel": 42, "moves": ["night slash", "quick attack", "faint attack", "confuseray"]},
                {"pokemon_id": 45,  "nivel": 42, "moves": ["petal dance", "stun spore", "synthesis", "solar beam"]},
                {"pokemon_id": 121, "nivel": 42, "moves": ["night slash", "surf", "confuseray", "thunder wave"]},
                {"pokemon_id": 94,  "nivel": 42, "moves": ["shadow ball", "hypnosis", "mean look", "confuseray"]},
                {"pokemon_id": 248, "nivel": 47, "moves": ["crunch", "hyper beam", "earthquake", "rock slide"]},
            ],
            "ia_config": {"estrategia": "mixed", "notas": "Tyranitar cierra con Crunch + Earthquake"},
        },
        {
            "id": "johto_champion",
            "nombre": "Lance",
            "titulo": "Campeón de Johto",
            "tipo": "Dragón",
            "medalla": "Campeón de Johto",
            "emoji": "👑",
            "ciudad": "Meseta Montoya",
            "recompensa": 25000,
            "mt_recompensa": {"nombre_es": "Pulso Dragón", "move_key": "dragonpulse", "mt_num": 87},
            "equipo": [
                {"pokemon_id": 149, "nivel": 44, "moves": ["hyper beam", "thunder", "blizzard", "fire blast"]},
                {"pokemon_id": 149, "nivel": 49, "moves": ["hyper beam", "thunder", "blizzard", "earthquake"]},
                {"pokemon_id": 149, "nivel": 49, "moves": ["hyper beam", "thunder", "blizzard", "fire blast"]},
                {"pokemon_id": 245, "nivel": 50, "moves": ["surf", "blizzard", "hydro pump", "ice beam"]},
                {"pokemon_id": 244, "nivel": 50, "moves": ["flamethrower", "fire blast", "earthquake", "crunch"]},
                {"pokemon_id": 243, "nivel": 50, "moves": ["thunderbolt", "thunder", "rain dance", "crunch"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Dragonite x3 con Hyper Beam y cobertura elemental"},
        },
    ],
    "HOENN": [
        {
            "id": "hoenn_e4_sidney",
            "nombre": "Sidney",
            "titulo": "El Chico Malo",
            "tipo": "Siniestro",
            "medalla": "Victoria vs Sidney",
            "emoji": "🌑",
            "ciudad": "Ciudad Ever Grande",
            "recompensa": 10000,
            "mt_recompensa": {"nombre_es": "Golpe Feo", "move_key": "darkpulse", "mt_num": 78},
            "equipo": [
                {"pokemon_id": 262, "nivel": 46, "moves": ["swagger", "faint attack", "taunt", "thunder wave"]},
                {"pokemon_id": 261, "nivel": 48, "moves": ["hyper beam", "shadow ball", "strength", "taunt"]},
                {"pokemon_id": 197, "nivel": 46, "moves": ["faint attack", "swagger", "quick attack", "shadow ball"]},
                {"pokemon_id": 248, "nivel": 48, "moves": ["crunch", "earthquake", "rock slide", "scary face"]},
                {"pokemon_id": 359, "nivel": 49, "moves": ["crunch", "shadow ball", "ice beam", "fire blast"]},
            ],
            "ia_config": {"estrategia": "mixed", "notas": "Swagger + Taunt; Absol cierra con cobertura"},
        },
        {
            "id": "hoenn_e4_phoebe",
            "nombre": "Phoebe",
            "titulo": "La Bailarina Fantasma",
            "tipo": "Fantasma",
            "medalla": "Victoria vs Phoebe",
            "emoji": "👻",
            "ciudad": "Ciudad Ever Grande",
            "recompensa": 10500,
            "mt_recompensa": {"nombre_es": "Bola Sombra", "move_key": "shadowball", "mt_num": 92},
            "equipo": [
                {"pokemon_id": 356, "nivel": 48, "moves": ["shadow ball", "will-o-wisp", "ice beam", "psychic"]},
                {"pokemon_id": 355, "nivel": 49, "moves": ["shadow ball", "shadow sneak", "will-o-wisp", "destiny bond"]},
                {"pokemon_id": 353, "nivel": 50, "moves": ["shadow ball", "destiny bond", "confuseray", "shadow sneak"]},
                {"pokemon_id": 356, "nivel": 51, "moves": ["shadow ball", "will-o-wisp", "ice beam", "psychic"]},
                {"pokemon_id": 354, "nivel": 53, "moves": ["shadow ball", "will-o-wisp", "psychic", "shadow punch"]},
            ],
            "ia_config": {"estrategia": "trap_damage", "notas": "Will-O-Wisp + Destiny Bond; Shadow Ball para daño"},
        },
        {
            "id": "hoenn_e4_glacia",
            "nombre": "Glacia",
            "titulo": "La Diosa del Hielo",
            "tipo": "Hielo",
            "medalla": "Victoria vs Glacia",
            "emoji": "🧊",
            "ciudad": "Ciudad Ever Grande",
            "recompensa": 11000,
            "mt_recompensa": {"nombre_es": "Ventisca", "move_key": "blizzard", "mt_num": 141},
            "equipo": [
                {"pokemon_id": 361, "nivel": 50, "moves": ["blizzard", "hail", "ice beam", "icy wind"]},
                {"pokemon_id": 362, "nivel": 50, "moves": ["blizzard", "hail", "ice beam", "iron defense"]},
                {"pokemon_id": 87,  "nivel": 52, "moves": ["blizzard", "surf", "ice beam", "rain dance"]},
                {"pokemon_id": 362, "nivel": 52, "moves": ["blizzard", "iron defense", "ice beam", "hail"]},
                {"pokemon_id": 478, "nivel": 53, "moves": ["blizzard", "shadow ball", "hypnosis", "hail"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Hail + Blizzard sin fallo; Froslass hipnotiza"},
        },
        {
            "id": "hoenn_e4_drake",
            "nombre": "Drake",
            "titulo": "El Capitán Dragón",
            "tipo": "Dragón",
            "medalla": "Victoria vs Drake",
            "emoji": "🐉",
            "ciudad": "Ciudad Ever Grande",
            "recompensa": 12000,
            "mt_recompensa": {"nombre_es": "Garra Dragón", "move_key": "dragonclaw", "mt_num": 116},
            "equipo": [
                {"pokemon_id": 329, "nivel": 52, "moves": ["dragon claw", "earth power", "hyper beam", "scary face"]},
                {"pokemon_id": 330, "nivel": 54, "moves": ["dragon claw", "fly", "earthquake", "hyper beam"]},
                {"pokemon_id": 147, "nivel": 53, "moves": ["dragon rage", "twister", "body slam", "thunder wave"]},
                {"pokemon_id": 148, "nivel": 53, "moves": ["twister", "dragon dance", "slam", "hyper beam"]},
                {"pokemon_id": 149, "nivel": 55, "moves": ["outrage", "hyper beam", "blizzard", "thunder"]},
            ],
            "ia_config": {"estrategia": "setup_sweep", "notas": "Dragon Dance con Dragonair; Dragonite cierra"},
        },
        {
            "id": "hoenn_champion",
            "nombre": "Steven",
            "titulo": "Campeón de Hoenn",
            "tipo": "Acero",
            "medalla": "Campeón de Hoenn",
            "emoji": "👑",
            "ciudad": "Ciudad Ever Grande",
            "recompensa": 25000,
            "mt_recompensa": {"nombre_es": "Defensa Férrea", "move_key": "irondefense", "mt_num": 66},
            "equipo": [
                {"pokemon_id": 378, "nivel": 57, "moves": ["ice beam", "earthquake", "body slam", "iron defense"]},
                {"pokemon_id": 227, "nivel": 57, "moves": ["aerial ace", "steel wing", "rock slide", "hyper beam"]},
                {"pokemon_id": 302, "nivel": 57, "moves": ["shadow ball", "iron defense", "flatter", "crunch"]},
                {"pokemon_id": 376, "nivel": 57, "moves": ["meteor mash", "earthquake", "calm mind", "protect"]},
                {"pokemon_id": 383, "nivel": 58, "moves": ["ancient power", "earthquake", "body slam", "hyper beam"]},  # Nota: oficial es Groudon en "Victory Road" run
                {"pokemon_id": 384, "nivel": 58, "moves": ["dragon claw", "ancient power", "fly", "hyper beam"]},
            ],
            "ia_config": {"estrategia": "mixed", "notas": "Metagross cierra con Meteor Mash; cobertura amplia"},
        },
    ],
    "SINNOH": [
        {
            "id": "sinnoh_e4_aaron",
            "nombre": "Aaron",
            "titulo": "El Maestro de Bichos",
            "tipo": "Bicho",
            "medalla": "Victoria vs Aaron",
            "emoji": "🐛",
            "ciudad": "Meseta Victoria",
            "recompensa": 11000,
            "mt_recompensa": {"nombre_es": "Vuelta en U", "move_key": "uturn", "mt_num": 56},
            "equipo": [
                {"pokemon_id": 402, "nivel": 53, "moves": ["x-scissor", "rock smash", "roost", "close combat"]},
                {"pokemon_id": 413, "nivel": 54, "moves": ["x-scissor", "bug buzz", "rock blast", "earthquake"]},
                {"pokemon_id": 416, "nivel": 57, "moves": ["bug buzz", "psychic", "power gem", "shadow ball"]},
                {"pokemon_id": 214, "nivel": 54, "moves": ["earthquake", "x-scissor", "stone edge", "thrash"]},
                {"pokemon_id": 469, "nivel": 57, "moves": ["bug buzz", "aerial ace", "u-turn", "roost"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Bug Buzz y X-Scissor directo; Yanmega cierra"},
        },
        {
            "id": "sinnoh_e4_bertha",
            "nombre": "Bertha",
            "titulo": "La Abuela de Tierra",
            "tipo": "Tierra",
            "medalla": "Victoria vs Bertha",
            "emoji": "🌍",
            "ciudad": "Meseta Victoria",
            "recompensa": 11500,
            "mt_recompensa": {"nombre_es": "Terremoto", "move_key": "earthquake", "mt_num": 96},
            "equipo": [
                {"pokemon_id": 450, "nivel": 55, "moves": ["earthquake", "stone edge", "rock slide", "yawn"]},
                {"pokemon_id": 411, "nivel": 55, "moves": ["earthquake", "stone edge", "iron defense", "headbutt"]},
                {"pokemon_id": 340, "nivel": 55, "moves": ["earthquake", "muddy water", "yawn", "body slam"]},
                {"pokemon_id": 76,  "nivel": 56, "moves": ["earthquake", "stone edge", "explosion", "rock slide"]},
                {"pokemon_id": 208, "nivel": 59, "moves": ["earthquake", "stone edge", "iron tail", "crunch"]},
            ],
            "ia_config": {"estrategia": "mixed", "notas": "Yawn para dormir; Steelix cierra con Earthquake"},
        },
        {
            "id": "sinnoh_e4_flint",
            "nombre": "Flint",
            "titulo": "El Fuego en Persona",
            "tipo": "Fuego",
            "medalla": "Victoria vs Flint",
            "emoji": "🔥",
            "ciudad": "Meseta Victoria",
            "recompensa": 12000,
            "mt_recompensa": {"nombre_es": "Lanzallamas", "move_key": "flamethrower", "mt_num": 109},
            "equipo": [
                {"pokemon_id": 466, "nivel": 55, "moves": ["thunder punch", "fire punch", "ice punch", "cross chop"]},
                {"pokemon_id": 38,  "nivel": 58, "moves": ["flamethrower", "nasty plot", "energy ball", "psychic"]},
                {"pokemon_id": 126, "nivel": 54, "moves": ["flamethrower", "thunderbolt", "fire blast", "hyper beam"]},
                {"pokemon_id": 419, "nivel": 55, "moves": ["waterfall", "crunch", "aqua jet", "ice fang"]},
                {"pokemon_id": 392, "nivel": 61, "moves": ["flare blitz", "close combat", "stone edge", "earthquake"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Flare Blitz con Infernape; cobertura amplia"},
        },
        {
            "id": "sinnoh_e4_lucian",
            "nombre": "Lucian",
            "titulo": "El Lector Psíquico",
            "tipo": "Psíquico",
            "medalla": "Victoria vs Lucian",
            "emoji": "🔮",
            "ciudad": "Meseta Victoria",
            "recompensa": 13000,
            "mt_recompensa": {"nombre_es": "Calma Mental", "move_key": "calmmind", "mt_num": 129},
            "equipo": [
                {"pokemon_id": 203, "nivel": 55, "moves": ["psychic", "thunder wave", "shadow ball", "stomp"]},
                {"pokemon_id": 437, "nivel": 56, "moves": ["psychic", "shadow ball", "flash cannon", "iron defense"]},
                {"pokemon_id": 122, "nivel": 56, "moves": ["psychic", "nasty plot", "shadow ball", "thunderbolt"]},
                {"pokemon_id": 196, "nivel": 57, "moves": ["psychic", "calm mind", "shadow ball", "signal beam"]},
                {"pokemon_id": 475, "nivel": 61, "moves": ["psychic", "calm mind", "close combat", "stone edge"]},
            ],
            "ia_config": {"estrategia": "setup_sweep", "notas": "Calm Mind con Gallade y Espeon; Psychic como STAB"},
        },
        {
            "id": "sinnoh_champion",
            "nombre": "Cynthia",
            "titulo": "Campeona de Sinnoh",
            "tipo": "Mixto",
            "medalla": "Campeona de Sinnoh",
            "emoji": "👑",
            "ciudad": "Meseta Victoria",
            "recompensa": 25000,
            "mt_recompensa": {"nombre_es": "Meteoro Dragón", "move_key": "dracometeor", "mt_num": 113},
            "equipo": [
                {"pokemon_id": 472, "nivel": 61, "moves": ["earthquake", "ice fang", "poison jab", "stone edge"]},
                {"pokemon_id": 430, "nivel": 61, "moves": ["aerial ace", "dark pulse", "quick attack", "wing attack"]},
                {"pokemon_id": 426, "nivel": 61, "moves": ["ice beam", "thunderbolt", "aura sphere", "energy ball"]},
                {"pokemon_id": 448, "nivel": 63, "moves": ["close combat", "dragon pulse", "swords dance", "extreme speed"]},
                {"pokemon_id": 474, "nivel": 63, "moves": ["thunderbolt", "ice beam", "hyper beam", "nasty plot"]},
                {"pokemon_id": 445, "nivel": 66, "moves": ["outrage", "earthquake", "dragon rush", "giga impact"]},
            ],
            "ia_config": {"estrategia": "mixed", "notas": "Garchomp cierra con Outrage; Lucario con Close Combat"},
        },
    ],
    "TESELIA": [
        {
            "id": "teselia_e4_shauntal",
            "nombre": "Shauntal",
            "titulo": "La Escritora Fantasma",
            "tipo": "Fantasma",
            "medalla": "Victoria vs Shauntal",
            "emoji": "👻",
            "ciudad": "Ciudad Nimbasa",
            "recompensa": 10000,
            "mt_recompensa": {"nombre_es": "Bola Sombra", "move_key": "shadowball", "mt_num": 92},
            "equipo": [
                {"pokemon_id": 609, "nivel": 52, "moves": ["shadow ball", "will-o-wisp", "energy ball", "flamethrower"]},
                {"pokemon_id": 593, "nivel": 52, "moves": ["hex", "shadow ball", "surf", "rain dance"]},
                {"pokemon_id": 592, "nivel": 52, "moves": ["shadow ball", "hex", "minimize", "recover"]},
                {"pokemon_id": 477, "nivel": 54, "moves": ["shadow ball", "will-o-wisp", "earthquake", "ice punch"]},
                {"pokemon_id": 609, "nivel": 56, "moves": ["shadow ball", "will-o-wisp", "flamethrower", "energy ball"]},
            ],
            "ia_config": {"estrategia": "trap_damage", "notas": "Will-O-Wisp + Hex; Dusknoir con cobertura"},
        },
        {
            "id": "teselia_e4_grimsley",
            "nombre": "Grimsley",
            "titulo": "El Jugador Oscuro",
            "tipo": "Siniestro",
            "medalla": "Victoria vs Grimsley",
            "emoji": "🌑",
            "ciudad": "Ciudad Nimbasa",
            "recompensa": 10500,
            "mt_recompensa": {"nombre_es": "Golpe Feo", "move_key": "darkpulse", "mt_num": 78},
            "equipo": [
                {"pokemon_id": 430, "nivel": 52, "moves": ["aerial ace", "dark pulse", "sucker punch", "brave bird"]},
                {"pokemon_id": 635, "nivel": 56, "moves": ["dark pulse", "dragon pulse", "flamethrower", "surf"]},
                {"pokemon_id": 625, "nivel": 52, "moves": ["night slash", "iron head", "swords dance", "x-scissor"]},
                {"pokemon_id": 342, "nivel": 52, "moves": ["crunch", "superpower", "night slash", "aqua jet"]},
                {"pokemon_id": 508, "nivel": 52, "moves": ["crunch", "play rough", "drain punch", "seed bomb"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Hydreigon con cobertura triple; Bisharp con Swords Dance"},
        },
        {
            "id": "teselia_e4_caitlin",
            "nombre": "Caitlin",
            "titulo": "La Durmiente Psíquica",
            "tipo": "Psíquico",
            "medalla": "Victoria vs Caitlin",
            "emoji": "🔮",
            "ciudad": "Ciudad Nimbasa",
            "recompensa": 11000,
            "mt_recompensa": {"nombre_es": "Psíquico", "move_key": "psychic", "mt_num": 63},
            "equipo": [
                {"pokemon_id": 518, "nivel": 52, "moves": ["psychic", "calm mind", "shadow ball", "yawn"]},
                {"pokemon_id": 122, "nivel": 52, "moves": ["psychic", "nasty plot", "shadow ball", "thunder wave"]},
                {"pokemon_id": 338, "nivel": 52, "moves": ["psychic", "cosmic power", "solar beam", "hyper beam"]},
                {"pokemon_id": 337, "nivel": 52, "moves": ["psychic", "cosmic power", "earthquake", "hyper beam"]},
                {"pokemon_id": 282, "nivel": 55, "moves": ["psychic", "calm mind", "shadow ball", "moonblast"]},
            ],
            "ia_config": {"estrategia": "setup_sweep", "notas": "Calm Mind masivo; Gardevoir cierra"},
        },
        {
            "id": "teselia_e4_marshal",
            "nombre": "Marshal",
            "titulo": "El Maestro del Golpe",
            "tipo": "Lucha",
            "medalla": "Victoria vs Marshal",
            "emoji": "🥊",
            "ciudad": "Ciudad Nimbasa",
            "recompensa": 12000,
            "mt_recompensa": {"nombre_es": "Puñetazo Drenaje", "move_key": "drainpunch", "mt_num": 120},
            "equipo": [
                {"pokemon_id": 538, "nivel": 52, "moves": ["close combat", "stone edge", "superpower", "bulk up"]},
                {"pokemon_id": 539, "nivel": 52, "moves": ["hi jump kick", "mach punch", "bulk up", "stone edge"]},
                {"pokemon_id": 534, "nivel": 56, "moves": ["hammer arm", "stone edge", "earthquake", "bulk up"]},
                {"pokemon_id": 560, "nivel": 52, "moves": ["close combat", "stone edge", "aqua jet", "superpower"]},
                {"pokemon_id": 532, "nivel": 52, "moves": ["close combat", "earthquake", "stone edge", "bulk up"]},
            ],
            "ia_config": {"estrategia": "setup_sweep", "notas": "Bulk Up masivo; Conkeldurr cierra con Hammer Arm"},
        },
        {
            "id": "teselia_champion",
            "nombre": "Alder",
            "titulo": "Campeón de Teselia",
            "tipo": "Mixto",
            "medalla": "Campeón de Teselia",
            "emoji": "👑",
            "ciudad": "Ciudad Nimbasa",
            "recompensa": 25000,
            "mt_recompensa": {"nombre_es": "Hiperrayo", "move_key": "hyperbeam", "mt_num": 117},
            "equipo": [
                {"pokemon_id": 617, "nivel": 54, "moves": ["acrobatics", "toxic", "bug buzz", "aerial ace"]},
                {"pokemon_id": 637, "nivel": 54, "moves": ["flare blitz", "giga impact", "bug buzz", "aerial ace"]},
                {"pokemon_id": 635, "nivel": 57, "moves": ["dark pulse", "dragon pulse", "surf", "flamethrower"]},
                {"pokemon_id": 623, "nivel": 54, "moves": ["earthquake", "shadow ball", "iron head", "dragon claw"]},
                {"pokemon_id": 628, "nivel": 54, "moves": ["brave bird", "superpower", "retaliate", "quick attack"]},
                {"pokemon_id": 598, "nivel": 58, "moves": ["power whip", "heavy slam", "rock slide", "thunder"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Hydreigon y Volcarona como ases; cobertura amplia"},
        },
    ],
    "KALOS": [
        {
            "id": "kalos_e4_malva",
            "nombre": "Malva",
            "titulo": "La Reportera de Fuego",
            "tipo": "Fuego",
            "medalla": "Victoria vs Malva",
            "emoji": "🔥",
            "ciudad": "Ciudad Lumiose",
            "recompensa": 13000,
            "mt_recompensa": {"nombre_es": "Lanzallamas", "move_key": "flamethrower", "mt_num": 109},
            "equipo": [
                {"pokemon_id": 218, "nivel": 63, "moves": ["flamethrower", "overheat", "earth power", "fire spin"]},
                {"pokemon_id": 631, "nivel": 65, "moves": ["heat wave", "overheat", "clear smog", "coil"]},
                {"pokemon_id": 78,  "nivel": 63, "moves": ["flare blitz", "flame charge", "double kick", "hyper beam"]},
                {"pokemon_id": 663, "nivel": 65, "moves": ["flare blitz", "aerial ace", "hyper voice", "sky attack"]},
                {"pokemon_id": 59,  "nivel": 65, "moves": ["flare blitz", "extreme speed", "close combat", "wild charge"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Arcanine con Extreme Speed prioridad; Talonflame con Flare Blitz"},
        },
        {
            "id": "kalos_e4_siebold",
            "nombre": "Siebold",
            "titulo": "El Chef del Agua",
            "tipo": "Agua",
            "medalla": "Victoria vs Siebold",
            "emoji": "💧",
            "ciudad": "Ciudad Lumiose",
            "recompensa": 13500,
            "mt_recompensa": {"nombre_es": "Surf", "move_key": "surf", "mt_num": 90},
            "equipo": [
                {"pokemon_id": 119, "nivel": 63, "moves": ["waterfall", "agility", "megahorn", "double-edge"]},
                {"pokemon_id": 130, "nivel": 63, "moves": ["waterfall", "earthquake", "ice fang", "dragon dance"]},
                {"pokemon_id": 230, "nivel": 65, "moves": ["surf", "dragon pulse", "scald", "ice beam"]},
                {"pokemon_id": 131, "nivel": 65, "moves": ["surf", "ice beam", "thunder", "blizzard"]},
                {"pokemon_id": 319, "nivel": 68, "moves": ["waterfall", "crunch", "ice fang", "earthquake"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Dragon Dance con Gyarados; Sharpedo cierra"},
        },
        {
            "id": "kalos_e4_wikstrom",
            "nombre": "Wikstrom",
            "titulo": "El Caballero de Acero",
            "tipo": "Acero",
            "medalla": "Victoria vs Wikstrom",
            "emoji": "⚙️",
            "ciudad": "Ciudad Lumiose",
            "recompensa": 14000,
            "mt_recompensa": {"nombre_es": "Pulso Flash", "move_key": "flashcannon", "mt_num": 104},
            "equipo": [
                {"pokemon_id": 303, "nivel": 63, "moves": ["iron head", "iron defense", "crunch", "sucker punch"]},
                {"pokemon_id": 707, "nivel": 64, "moves": ["flash cannon", "thunder wave", "thunder", "power whip"]},
                {"pokemon_id": 306, "nivel": 65, "moves": ["iron defense", "iron head", "earthquake", "heavy slam"]},
                {"pokemon_id": 437, "nivel": 65, "moves": ["flash cannon", "iron defense", "confuse ray", "psychic"]},
                {"pokemon_id": 625, "nivel": 68, "moves": ["iron head", "night slash", "swords dance", "x-scissor"]},
            ],
            "ia_config": {"estrategia": "defensive", "notas": "Iron Defense + STAB; Bisharp con Swords Dance"},
        },
        {
            "id": "kalos_e4_drasna",
            "nombre": "Drasna",
            "titulo": "La Abuela Dragón",
            "tipo": "Dragón",
            "medalla": "Victoria vs Drasna",
            "emoji": "🐉",
            "ciudad": "Ciudad Lumiose",
            "recompensa": 15000,
            "mt_recompensa": {"nombre_es": "Pulso Dragón", "move_key": "dragonpulse", "mt_num": 87},
            "equipo": [
                {"pokemon_id": 334, "nivel": 63, "moves": ["dragon pulse", "cotton guard", "dragon dance", "outrage"]},
                {"pokemon_id": 691, "nivel": 65, "moves": ["dragon pulse", "flamethrower", "hyper voice", "water pulse"]},
                {"pokemon_id": 148, "nivel": 65, "moves": ["dragon dance", "aqua tail", "thunder wave", "outrage"]},
                {"pokemon_id": 373, "nivel": 66, "moves": ["dragon claw", "earthquake", "fly", "outrage"]},
                {"pokemon_id": 149, "nivel": 68, "moves": ["outrage", "hyper beam", "thunder", "blizzard"]},
            ],
            "ia_config": {"estrategia": "setup_sweep", "notas": "Dragon Dance con Dragonair y Altaria; Dragonite cierra"},
        },
        {
            "id": "kalos_champion",
            "nombre": "Diantha",
            "titulo": "Campeona de Kalos",
            "tipo": "Mixto",
            "medalla": "Campeona de Kalos",
            "emoji": "👑",
            "ciudad": "Ciudad Lumiose",
            "recompensa": 25000,
            "mt_recompensa": {"nombre_es": "Fuerza Lunar", "move_key": "moonblast", "mt_num": 79},
            "equipo": [
                {"pokemon_id": 719, "nivel": 64, "moves": ["stone edge", "dragon pulse", "flash cannon", "earthquake"]},
                {"pokemon_id": 711, "nivel": 65, "moves": ["shadow ball", "confuseray", "moonblast", "grass knot"]},
                {"pokemon_id": 306, "nivel": 65, "moves": ["iron defense", "iron head", "heavy slam", "earthquake"]},
                {"pokemon_id": 697, "nivel": 65, "moves": ["dragon tail", "crunch", "stomp", "aqua tail"]},
                {"pokemon_id": 214, "nivel": 66, "moves": ["earthquake", "close combat", "stone edge", "x-scissor"]},
                {"pokemon_id": 282, "nivel": 68, "moves": ["moonblast", "psychic", "shadow ball", "calm mind"]},  # Gardevoir Mega
            ],
            "ia_config": {"estrategia": "mixed", "notas": "Gardevoir Mega como as bajo la manga; cobertura amplia"},
        },
    ],
    "ALOLA": [
        {
            "id": "alola_e4_hala",
            "nombre": "Hala",
            "titulo": "Kahuna del Alto Mando",
            "tipo": "Lucha",
            "medalla": "Victoria vs Hala",
            "emoji": "🥊",
            "ciudad": "Liga Pokémon de Alola",
            "recompensa": 14000,
            "mt_recompensa": {"nombre_es": "Puñetazo Drenaje", "move_key": "drainpunch", "mt_num": 120},
            "equipo": [
                {"pokemon_id": 107, "nivel": 54, "moves": ["drain punch", "mach punch", "fire punch", "thunder punch"]},
                {"pokemon_id": 297, "nivel": 55, "moves": ["close combat", "fake out", "bullet punch", "heavy slam"]},
                {"pokemon_id": 701, "nivel": 55, "moves": ["close combat", "high jump kick", "sky uppercut", "mach punch"]},
                {"pokemon_id": 67,  "nivel": 57, "moves": ["focus blast", "shadow ball", "thunderpunch", "high jump kick"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Mach Punch para prioridad; Hariyama cierra"},
        },
        {
            "id": "alola_e4_olivia",
            "nombre": "Olivia",
            "titulo": "Kahuna del Alto Mando",
            "tipo": "Roca",
            "medalla": "Victoria vs Olivia",
            "emoji": "🪨",
            "ciudad": "Liga Pokémon de Alola",
            "recompensa": 14500,
            "mt_recompensa": {"nombre_es": "Trampa Rocas", "move_key": "stealthrock", "mt_num": 76},
            "equipo": [
                {"pokemon_id": 185, "nivel": 54, "moves": ["stone edge", "wood hammer", "gyro ball", "stealth rock"]},
                {"pokemon_id": 526, "nivel": 55, "moves": ["stone edge", "earthquake", "thunder punch", "dragon rush"]},
                {"pokemon_id": 764, "nivel": 56, "moves": ["stone edge", "rock slide", "crunch", "bite"]},
                {"pokemon_id": 248, "nivel": 57, "moves": ["stone edge", "earthquake", "crunch", "ice beam"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Stealth Rock + Stone Edge; Tyranitar cierra"},
        },
        {
            "id": "alola_e4_acerola",
            "nombre": "Acerola",
            "titulo": "La Fantasma de Alola",
            "tipo": "Fantasma",
            "medalla": "Victoria vs Acerola",
            "emoji": "👻",
            "ciudad": "Liga Pokémon de Alola",
            "recompensa": 15000,
            "mt_recompensa": {"nombre_es": "Bola Sombra", "move_key": "shadowball", "mt_num": 92},
            "equipo": [
                {"pokemon_id": 426, "nivel": 54, "moves": ["shadow ball", "ice beam", "thunderbolt", "energy ball"]},
                {"pokemon_id": 477, "nivel": 55, "moves": ["shadow ball", "earthquake", "will-o-wisp", "ice punch"]},
                {"pokemon_id": 778, "nivel": 56, "moves": ["shadow sneak", "shadow claw", "play rough", "wood hammer"]},
                {"pokemon_id": 711, "nivel": 57, "moves": ["shadow ball", "confuseray", "moonblast", "grass knot"]},
            ],
            "ia_config": {"estrategia": "mixed", "notas": "Will-O-Wisp + Shadow Ball; Mimikyu con Shadow Sneak prioridad"},
        },
        {
            "id": "alola_e4_kahili",
            "nombre": "Kahili",
            "titulo": "La Golfista del Viento",
            "tipo": "Volador",
            "medalla": "Victoria vs Kahili",
            "emoji": "🦅",
            "ciudad": "Liga Pokémon de Alola",
            "recompensa": 16000,
            "mt_recompensa": {"nombre_es": "Acrobatismo", "move_key": "acrobatics", "mt_num": 128},
            "equipo": [
                {"pokemon_id": 663, "nivel": 54, "moves": ["flare blitz", "aerial ace", "acrobatics", "roost"]},
                {"pokemon_id": 279, "nivel": 55, "moves": ["air slash", "waterfall", "ice beam", "acrobatics"]},
                {"pokemon_id": 277, "nivel": 55, "moves": ["brave bird", "close combat", "aerial ace", "u-turn"]},
                {"pokemon_id": 628, "nivel": 57, "moves": ["brave bird", "superpower", "aerial ace", "roost"]},
                {"pokemon_id": 227, "nivel": 57, "moves": ["brave bird", "aerial ace", "steel wing", "agility"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Brave Bird para daño masivo; Acrobatics si sin item"},
        },
        {
            "id": "alola_champion",
            "nombre": "Kukui",
            "titulo": "Profesor y Campeón de Alola",
            "tipo": "Mixto",
            "medalla": "Campeón de Alola",
            "emoji": "👑",
            "ciudad": "Liga Pokémon de Alola",
            "recompensa": 25000,
            "mt_recompensa": {"nombre_es": "Rayo de Hielo", "move_key": "icebeam", "mt_num": 67},
            "equipo": [
                {"pokemon_id": 730, "nivel": 57, "moves": ["surf", "icy wind", "sparkling aria", "bubble beam"]},
                {"pokemon_id": 745, "nivel": 57, "moves": ["stone edge", "crunch", "fire fang", "accelerock"]},
                {"pokemon_id": 784, "nivel": 58, "moves": ["close combat", "stone edge", "poison jab", "karate chop"]},
                {"pokemon_id": 758, "nivel": 58, "moves": ["flamethrower", "poison gas", "fire blast", "venoshock"]},
                {"pokemon_id": 38,  "nivel": 59, "moves": ["flamethrower", "nasty plot", "moonblast", "psyshock"]},  # Ninetales Alola
                {"pokemon_id": 727, "nivel": 60, "moves": ["flare blitz", "close combat", "earthquake", "stone edge"]},
            ],
            "ia_config": {"estrategia": "mixed", "notas": "Incineroar cierra con Flare Blitz; cobertura total"},
        },
    ],
    "GALAR": [
        {
            "id": "galar_e4_marnie",
            "nombre": "Marnie",
            "titulo": "La Rival Oscura",
            "tipo": "Siniestro",
            "medalla": "Victoria vs Marnie",
            "emoji": "🌑",
            "ciudad": "Wyndon Stadium",
            "recompensa": 15000,
            "mt_recompensa": {"nombre_es": "Golpe Feo", "move_key": "darkpulse", "mt_num": 78},
            "equipo": [
                {"pokemon_id": 853, "nivel": 56, "moves": ["hex", "will-o-wisp", "shadow ball", "fire blast"]},
                {"pokemon_id": 862, "nivel": 56, "moves": ["darkest lariat", "sucker punch", "shadow claw", "fake out"]},
                {"pokemon_id": 877, "nivel": 56, "moves": ["nuzzle", "thunder", "darkest lariat", "discharge"]},
                {"pokemon_id": 858, "nivel": 58, "moves": ["dark pulse", "dazzling gleam", "energy ball", "moonblast"]},
                {"pokemon_id": 884, "nivel": 59, "moves": ["dragon claw", "iron head", "dark pulse", "close combat"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Morpeko con Darkest Lariat; Grimmsnarl cierra"},
        },
        {
            "id": "galar_e4_bede",
            "nombre": "Bede",
            "titulo": "El Chico del Hada",
            "tipo": "Hada",
            "medalla": "Victoria vs Bede",
            "emoji": "🌸",
            "ciudad": "Wyndon Stadium",
            "recompensa": 15500,
            "mt_recompensa": {"nombre_es": "Encantamiento", "move_key": "dazzlinggleam", "mt_num": 79},
            "equipo": [
                {"pokemon_id": 303, "nivel": 56, "moves": ["iron head", "play rough", "fake tears", "ice beam"]},
                {"pokemon_id": 281, "nivel": 57, "moves": ["dazzling gleam", "calm mind", "draining kiss", "thunder wave"]},
                {"pokemon_id": 869, "nivel": 57, "moves": ["misty terrain", "dazzling gleam", "sweet kiss", "psychic"]},
                {"pokemon_id": 866, "nivel": 59, "moves": ["moonblast", "dazzling gleam", "calm mind", "psychic"]},
                {"pokemon_id": 474, "nivel": 59, "moves": ["moonblast", "thunderbolt", "ice beam", "calm mind"]},
            ],
            "ia_config": {"estrategia": "setup_sweep", "notas": "Calm Mind con Mr. Rime y Mister Mime Galar; Moonblast"},
        },
        {
            "id": "galar_e4_nessa",
            "nombre": "Nessa",
            "titulo": "La Modelo Campeona",
            "tipo": "Agua",
            "medalla": "Victoria vs Nessa",
            "emoji": "💧",
            "ciudad": "Wyndon Stadium",
            "recompensa": 16000,
            "mt_recompensa": {"nombre_es": "Cascada", "move_key": "waterfall", "mt_num": 106},
            "equipo": [
                {"pokemon_id": 834, "nivel": 57, "moves": ["liquidation", "earthquake", "ice fang", "stealth rock"]},
                {"pokemon_id": 226, "nivel": 57, "moves": ["waterfall", "air slash", "ice beam", "swift swim"]},
                {"pokemon_id": 131, "nivel": 58, "moves": ["waterfall", "blizzard", "ice beam", "thunder"]},
                {"pokemon_id": 130, "nivel": 58, "moves": ["waterfall", "earthquake", "ice fang", "dragon dance"]},
                {"pokemon_id": 906, "nivel": 60, "moves": ["wave crash", "flip turn", "close combat", "aqua jet"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Dragon Dance con Gyarados; Quaquaval cierra"},
        },
        {
            "id": "galar_e4_bea",
            "nombre": "Bea",
            "titulo": "La Guerrera Campeona",
            "tipo": "Lucha",
            "medalla": "Victoria vs Bea",
            "emoji": "🥊",
            "ciudad": "Wyndon Stadium",
            "recompensa": 17000,
            "mt_recompensa": {"nombre_es": "Inversión", "move_key": "reversal", "mt_num": 18},
            "equipo": [
                {"pokemon_id": 870, "nivel": 57, "moves": ["close combat", "detect", "bulldoze", "iron head"]},
                {"pokemon_id": 308, "nivel": 58, "moves": ["close combat", "drain punch", "bulk up", "zen headbutt"]},
                {"pokemon_id": 766, "nivel": 58, "moves": ["close combat", "bullet punch", "ice punch", "stone edge"]},
                {"pokemon_id": 68,  "nivel": 59, "moves": ["close combat", "earthquake", "stone edge", "thunderpunch"]},
                {"pokemon_id": 448, "nivel": 60, "moves": ["close combat", "dragon pulse", "swords dance", "extreme speed"]},
            ],
            "ia_config": {"estrategia": "setup_sweep", "notas": "Bulk Up con Medicham; Lucario cierra con E-Speed"},
        },
        {
            "id": "galar_champion",
            "nombre": "Leon",
            "titulo": "Campeón de Galar",
            "tipo": "Mixto",
            "medalla": "Campeón de Galar",
            "emoji": "👑",
            "ciudad": "Wyndon Stadium",
            "recompensa": 25000,
            "mt_recompensa": {"nombre_es": "Rayo Hielo", "move_key": "icebeam", "mt_num": 67},
            "equipo": [
                {"pokemon_id": 681, "nivel": 62, "moves": ["shadow sneak", "iron head", "kings shield", "sacred sword"]},
                {"pokemon_id": 537, "nivel": 63, "moves": ["surf", "earthquake", "poison jab", "hyper voice"]},
                {"pokemon_id": 612, "nivel": 63, "moves": ["dragon claw", "earthquake", "swords dance", "outrage"]},
                {"pokemon_id": 887, "nivel": 62, "moves": ["dragon darts", "shadow ball", "u-turn", "thunderbolt"]},
                {"pokemon_id": 464, "nivel": 64, "moves": ["earthquake", "stone edge", "rock wrecker", "megahorn"]},
                {"pokemon_id": 6,   "nivel": 65, "moves": ["flamethrower", "air slash", "hyper beam", "fire spin"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Charizard cierra con Flamethrower; Dragapult como ace"},
        },
    ],
    "PALDEA": [
        {
            "id": "paldea_e4_rika",
            "nombre": "Rika",
            "titulo": "La Tierra de Paldea",
            "tipo": "Tierra",
            "medalla": "Victoria vs Rika",
            "emoji": "🌍",
            "ciudad": "Academia de la Victoria",
            "recompensa": 16000,
            "mt_recompensa": {"nombre_es": "Terremoto", "move_key": "earthquake", "mt_num": 96},
            "equipo": [
                {"pokemon_id": 980, "nivel": 57, "moves": ["headlong rush", "crabhammer", "ice hammer", "earthquake"]},
                {"pokemon_id": 51,  "nivel": 57, "moves": ["earthquake", "stone edge", "mud bomb", "sucker punch"]},
                {"pokemon_id": 450, "nivel": 58, "moves": ["earthquake", "stone edge", "crunch", "ice fang"]},
                {"pokemon_id": 939, "nivel": 59, "moves": ["earthquake", "flip turn", "ice spinner", "aqua jet"]},
                {"pokemon_id": 956, "nivel": 61, "moves": ["earth power", "moonblast", "dazzling gleam", "calm mind"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Headlong Rush con Crabominable; Clodsire con Earth Power"},
        },
        {
            "id": "paldea_e4_poppy",
            "nombre": "Poppy",
            "titulo": "La Niña del Acero",
            "tipo": "Acero",
            "medalla": "Victoria vs Poppy",
            "emoji": "⚙️",
            "ciudad": "Academia de la Victoria",
            "recompensa": 16500,
            "mt_recompensa": {"nombre_es": "Pulso Flash", "move_key": "flashcannon", "mt_num": 104},
            "equipo": [
                {"pokemon_id": 303, "nivel": 58, "moves": ["iron head", "crunch", "fake tears", "sucker punch"]},
                {"pokemon_id": 437, "nivel": 58, "moves": ["flash cannon", "psychic", "confuseray", "iron defense"]},
                {"pokemon_id": 82,  "nivel": 59, "moves": ["flash cannon", "thunderbolt", "magnet rise", "explosion"]},
                {"pokemon_id": 976, "nivel": 60, "moves": ["flash cannon", "iron head", "earthquake", "smart strike"]},
                {"pokemon_id": 967, "nivel": 62, "moves": ["tachyon cutter", "flash cannon", "iron defense", "swift"]},
            ],
            "ia_config": {"estrategia": "defensive", "notas": "Iron Defense + Flash Cannon; Espathra cierra con Tachyon Cutter"},
        },
        {
            "id": "paldea_e4_larry",
            "nombre": "Larry",
            "titulo": "El Funcionario Volador",
            "tipo": "Volador",
            "medalla": "Victoria vs Larry",
            "emoji": "🦅",
            "ciudad": "Academia de la Victoria",
            "recompensa": 17000,
            "mt_recompensa": {"nombre_es": "Acrobatismo", "move_key": "acrobatics", "mt_num": 128},
            "equipo": [
                {"pokemon_id": 18,  "nivel": 59, "moves": ["brave bird", "close combat", "quick attack", "roost"]},
                {"pokemon_id": 521, "nivel": 59, "moves": ["brave bird", "close combat", "work up", "acrobatics"]},
                {"pokemon_id": 426, "nivel": 60, "moves": ["acrobatics", "shadow ball", "thunderbolt", "ice beam"]},
                {"pokemon_id": 663, "nivel": 61, "moves": ["flare blitz", "brave bird", "acrobatics", "roost"]},
                {"pokemon_id": 983, "nivel": 62, "moves": ["brave bird", "facade", "tailwind", "roost"]},
            ],
            "ia_config": {"estrategia": "aggressive", "notas": "Brave Bird masivo; Staraptor con Close Combat"},
        },
        {
            "id": "paldea_e4_hassel",
            "nombre": "Hassel",
            "titulo": "El Maestro Dragón de Arte",
            "tipo": "Dragón",
            "medalla": "Victoria vs Hassel",
            "emoji": "🐉",
            "ciudad": "Academia de la Victoria",
            "recompensa": 18000,
            "mt_recompensa": {"nombre_es": "Meteoro Dragón", "move_key": "dracometeor", "mt_num": 113},
            "equipo": [
                {"pokemon_id": 611, "nivel": 60, "moves": ["dragon claw", "dragon dance", "flamethrower", "shadow claw"]},
                {"pokemon_id": 691, "nivel": 60, "moves": ["dragon pulse", "flamethrower", "hydro pump", "sludge bomb"]},
                {"pokemon_id": 887, "nivel": 61, "moves": ["dragon darts", "shadow ball", "u-turn", "thunderbolt"]},
                {"pokemon_id": 148, "nivel": 61, "moves": ["dragon dance", "aqua tail", "outrage", "extreme speed"]},
                {"pokemon_id": 997, "nivel": 63, "moves": ["dragon claw", "flamethrower", "earthquake", "stone edge"]},
            ],
            "ia_config": {"estrategia": "setup_sweep", "notas": "Dragon Dance con Drakloak; Dragonite cierra"},
        },
        {
            "id": "paldea_champion",
            "nombre": "Geeta",
            "titulo": "Top Campeona de Paldea",
            "tipo": "Mixto",
            "medalla": "Top Campeona de Paldea",
            "emoji": "👑",
            "ciudad": "Academia de la Victoria",
            "recompensa": 25000,
            "mt_recompensa": {"nombre_es": "Psíquico", "move_key": "psychic", "mt_num": 63},
            "equipo": [
                {"pokemon_id": 952, "nivel": 61, "moves": ["earth power", "sludge bomb", "seed bomb", "explosion"]},
                {"pokemon_id": 879, "nivel": 62, "moves": ["gyro ball", "earthquake", "ice punch", "heavy slam"]},
                {"pokemon_id": 416, "nivel": 62, "moves": ["bug buzz", "psychic", "power gem", "energy ball"]},
                {"pokemon_id": 956, "nivel": 62, "moves": ["earth power", "moonblast", "dazzling gleam", "calm mind"]},
                {"pokemon_id": 960, "nivel": 62, "moves": ["giga drain", "pollen puff", "bug buzz", "sunny day"]},
                {"pokemon_id": 1000, "nivel": 66, "moves": ["bitter malice", "will-o-wisp", "hex", "shadow ball"]},
            ],
            "ia_config": {"estrategia": "mixed", "notas": "Glimmora cierra con Bitter Malice; Vespiquen para control"},
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════════════
# MAPA REGIÓN → GYMS
# ═════════════════════════════════════════════════════════════════════════════
_GYMS_POR_REGION: Dict[str, List[Dict]] = {
    "KANTO":   _KANTO_GYMS,
    "JOHTO":   _JOHTO_GYMS,
    "HOENN":   _HOENN_GYMS,
    "SINNOH":  _SINNOH_GYMS,
    "TESELIA": _TESELIA_GYMS,
    "KALOS":   _KALOS_GYMS,
    "ALOLA":   _ALOLA_GYMS,
    "GALAR":   _GALAR_GYMS,
    "PALDEA":  _PALDEA_GYMS,
}


# ═════════════════════════════════════════════════════════════════════════════
# IA DE BATALLA — SELECCIÓN DE MOVIMIENTO
# El motor de batalla llama a GymBattleAI.seleccionar_movimiento() en cada
# turno del líder/E4 para obtener el movimiento a usar.
# ═════════════════════════════════════════════════════════════════════════════
class GymBattleAI:
    """
    Inteligencia artificial para líderes de gimnasio y Alto Mando.

    La IA evalúa el estado actual de la batalla y elige el movimiento
    más adecuado según la estrategia configurada para cada líder.

    Estrategias:
      aggressive    → siempre el movimiento de mayor poder
      status_first  → aplica estado (paralizar/dormir/quemar) en el primer turno
                      si el rival no tiene estado; luego aggressive
      defensive     → usa stat boosts propios cuando la prioridad es sobrevivir,
                      ataca cuando está "preparado" (≥ +2 en stat clave)
      trap_damage   → aplica Toxic / Mean Look primero, luego moves de daño
      setup_sweep   → usa swords dance / calm mind mientras puede,
                      luego ataca con máximo poder
      mixed         → prioriza moves de estado si el rival no tiene,
                      recuperación si HP < 40 %, ataque en otro caso
    """

    # Claves de movimientos de estado (para detectar si un move es de status)
    _STATUS_MOVES = {
        "toxic", "thunderwave", "thunder wave", "sleeppowder", "sleep powder",
        "stunspore", "stun spore", "willowisp", "will-o-wisp", "confuseray",
        "confuse ray", "poisonpowder", "poison powder", "hypnosis", "sing",
        "lovelykins", "lovely kiss", "attract", "yawn", "nuzzle",
        "smokescreen", "haze", "meanlook", "mean look", "toxic",
    }
    _SETUP_MOVES = {
        "swordsdance", "swords dance", "calmmind", "calm mind", "nastyplot",
        "nasty plot", "bulkup", "bulk up", "dragondance", "dragon dance",
        "irondefense", "iron defense", "cosmicpower", "cosmic power",
        "amnesia", "agility", "rockpolish", "rock polish", "growth",
    }
    _RECOVERY_MOVES = {
        "recover", "roost", "softboiled", "morningsun", "morning sun",
        "moonlight", "synthesis", "milkdrink", "milk drink", "slackoff",
        "slack off", "healorder", "heal order", "aquaring", "aqua ring",
        "ingrain", "shore up", "drainpunch", "drain punch", "gigadrain",
        "giga drain", "leechlife", "leech life", "drainingkiss", "draining kiss",
    }

    @classmethod
    def seleccionar_movimiento(
        cls,
        movimientos: List[str],
        estrategia: str,
        hp_ratio: float,
        rival_tiene_status: bool,
        setup_aplicado: int = 0,
    ) -> str:
        """
        Selecciona el movimiento óptimo.

        Args:
            movimientos:         Lista de claves de movimientos disponibles (con PP > 0).
            estrategia:          Estrategia de la ia_config del líder.
            hp_ratio:            HP actual / HP máximo del Pokémon del líder (0.0-1.0).
            rival_tiene_status:  True si el rival ya tiene un estado negativo.
            setup_aplicado:      Número de veces que ya se usó un move de setup este combate.

        Returns:
            Clave del movimiento elegido. Si la lista está vacía devuelve "tackle".
        """
        if not movimientos:
            return "tackle"

        moves_set = set(m.lower().replace("-", "").replace(" ", "") for m in movimientos)

        # -- Recuperación de emergencia (todas las estrategias) ---------------
        if hp_ratio < 0.3:
            for mv in movimientos:
                if mv.lower().replace("-", "").replace(" ", "") in cls._RECOVERY_MOVES:
                    return mv

        # -- Estrategia: status_first -----------------------------------------
        if estrategia == "status_first" and not rival_tiene_status:
            for mv in movimientos:
                key = mv.lower().replace("-", "").replace(" ", "")
                if key in cls._STATUS_MOVES:
                    return mv

        # -- Estrategia: setup_sweep ------------------------------------------
        if estrategia == "setup_sweep" and setup_aplicado < 2 and hp_ratio > 0.5:
            for mv in movimientos:
                key = mv.lower().replace("-", "").replace(" ", "")
                if key in cls._SETUP_MOVES:
                    return mv

        # -- Estrategia: defensive --------------------------------------------
        if estrategia == "defensive" and setup_aplicado < 3 and hp_ratio > 0.6:
            for mv in movimientos:
                key = mv.lower().replace("-", "").replace(" ", "")
                if key in cls._SETUP_MOVES:
                    return mv

        # -- Estrategia: trap_damage ------------------------------------------
        if estrategia == "trap_damage" and not rival_tiene_status:
            for mv in movimientos:
                key = mv.lower().replace("-", "").replace(" ", "")
                if key in cls._STATUS_MOVES or key == "meanlook":
                    return mv

        # -- mixed / fallthrough: aplicar status si no lo tiene ---------------
        if not rival_tiene_status:
            for mv in movimientos:
                key = mv.lower().replace("-", "").replace(" ", "")
                if key in cls._STATUS_MOVES:
                    return mv

        # -- Atacar con el primer movimiento disponible (el más poderoso está
        #    primero en la lista por convención de los datos arriba) -----------
        return movimientos[0]


# ═════════════════════════════════════════════════════════════════════════════
# SERVICIO PRINCIPAL
# ═════════════════════════════════════════════════════════════════════════════
class GimnasioService:
    """
    Servicio central de gimnasios, Alto Mando y medallas.

    La región activa se toma de battle_config.REGION_SERVIDOR.
    El orden de los líderes es el del índice en la lista de cada región:
    sólo se puede retar al líder N+1 tras haber derrotado al líder N.
    """
    _region_logueada: bool = False
    
    def __init__(self):
        self.db = db_manager
        self._cargar_region()

    # ──────────────────────────────────────────────────────────
    # Inicialización
    # ──────────────────────────────────────────────────────────
    def _cargar_region(self) -> None:
        try:
            from pokemon.battle_config import REGION_SERVIDOR
            self.region = REGION_SERVIDOR.upper()
        except Exception:
            self.region = "KANTO"

        self.lideres: List[Dict] = _GYMS_POR_REGION.get(self.region, _KANTO_GYMS)
        self.elite_four: List[Dict] = _ALTO_MANDO.get(self.region, [])
        self.total_gimnasios: int = len(self.lideres)

        # Índice rápido lider_id → posición (0-based)
        self._idx_lider: Dict[str, int] = {
            lider["id"]: i for i, lider in enumerate(self.lideres)
        }
        self._idx_e4: Dict[str, int] = {
            miembro["id"]: i for i, miembro in enumerate(self.elite_four)
        }

        if not GimnasioService._region_logueada:
            logger.info(
                f"[GYM] Región cargada: {self.region} "
                f"({self.total_gimnasios} gimnasios, "
                f"{len(self.elite_four)} miembros E4)"
            )
            GimnasioService._region_logueada = True

    # ── helper interno ────────────────────────────────────────────────
    @staticmethod
    def _agregar_mt_inventario(user_id: int, mt_num: int) -> bool:
        """
        Agrega la MT al inventario del usuario directamente en BD,
        sin pasar por items_service.agregar_item (que valida contra items_db).
        Usa INSERT OR IGNORE + UPDATE para ser idempotente.
        """
        try:
            item_id = f"mt{mt_num:03d}"   # mt001, mt045, mt096 …
            result  = db_manager.execute_query(
                "SELECT cantidad FROM INVENTARIO_USUARIO WHERE userID = ? AND item_nombre = ?",
                (user_id, item_id),
            )
            if result:
                db_manager.execute_update(
                    "UPDATE INVENTARIO_USUARIO SET cantidad = cantidad + 1 WHERE userID = ? AND item_nombre = ?",
                    (user_id, item_id),
                )
            else:
                db_manager.execute_update(
                    "INSERT INTO INVENTARIO_USUARIO (userID, item_nombre, cantidad) VALUES (?, ?, 1)",
                    (user_id, item_id),
                )
            logger.info(f"[GYM] {item_id} agregada al inventario de {user_id}")
            return True
        except Exception as e:
            logger.error(f"[GYM] Error agregando MT al inventario: {e}")
            return False

    # ──────────────────────────────────────────────────────────
    # Medallas — gimnasios
    # ──────────────────────────────────────────────────────────
    def obtener_medallas(self, user_id: int) -> List[str]:
        """
        Devuelve la lista de lider_ids que el usuario ya ha derrotado
        en la región activa.
        """
        try:
            rows = self.db.execute_query(
                "SELECT lider_id FROM MEDALLAS_USUARIOS WHERE userID = ?",
                (user_id,),
            )
            todos_ids = {(row["lider_id"] or "").lower() for row in rows}

            # Filtrar por líderes de la región activa
            ids_region = {lider["id"] for lider in self.lideres}
            return [lid for lid in todos_ids if lid in ids_region]

        except Exception as e:
            logger.error(f"[GYM] Error obteniendo medallas usuario {user_id}: {e}")
            return []

    def tiene_medalla(self, user_id: int, lider_id: str) -> bool:
        return lider_id in self.obtener_medallas(user_id)

    def medallas_count(self, user_id: int) -> int:
        return len(self.obtener_medallas(user_id))

    def todas_las_medallas(self, user_id: int) -> bool:
        return self.medallas_count(user_id) >= self.total_gimnasios

    # ──────────────────────────────────────────────────────────
    # Siguiente líder a enfrentar (desbloqueo secuencial)
    # ──────────────────────────────────────────────────────────
    def obtener_siguiente_lider(self, user_id: int) -> Optional[Dict]:
        """
        Devuelve los datos del próximo líder que el usuario puede desafiar.
        El orden es estrictamente secuencial: líder 0 → 1 → 2 → … → N-1.

        Returns:
            Dict con los datos del líder, o None si completó todos los gimnasios.
        """
        medallas = set(self.obtener_medallas(user_id))
        for lider in self.lideres:
            if lider["id"] not in medallas:
                return lider
        return None  # completó la región

    def puede_desafiar_lider(self, user_id: int, lider_id: str) -> Tuple[bool, str]:
        """
        Verifica si el usuario puede desafiar a un líder específico.

        El usuario sólo puede enfrentar al SIGUIENTE líder no derrotado;
        no puede saltarse ninguno ni repetir uno ya vencido.
        """
        siguiente = self.obtener_siguiente_lider(user_id)
        if siguiente is None:
            return False, "✅ Ya completaste todos los gimnasios de esta región."

        if siguiente["id"] != lider_id:
            esperado_nombre = siguiente["nombre"]
            return (
                False,
                f"⚔️ Debes derrotar primero a **{esperado_nombre}** "
                f"antes de enfrentar a este líder.",
            )

        if self.tiene_medalla(user_id, lider_id):
            return False, "✅ Ya tienes la medalla de este gimnasio."

        return True, "OK"

    def obtener_lider(self, lider_id: str) -> Optional[Dict]:
        """Busca un líder por su ID en la región activa y en el Alto Mando."""
        for lider in self.lideres:
            if lider["id"] == lider_id:
                return lider
        for miembro in self.elite_four:
            if miembro["id"] == lider_id:
                return miembro
        return None

    # ──────────────────────────────────────────────────────────
    # Otorgar medalla de gimnasio
    # ──────────────────────────────────────────────────────────
    def otorgar_medalla(self, user_id: int, lider_id: str) -> Tuple[bool, str]:
        """
        Otorga la medalla, cosmos y MT al ganar un gimnasio.
        """
        try:
            lider = self.obtener_lider(lider_id)
            if not lider:
                return False, "❌ Líder no encontrado."

            if self.tiene_medalla(user_id, lider_id):
                return False, f"✅ Ya tienes la **{lider['medalla']}**."

            # Persistir medalla en BD
            self.db.execute_update(
                "INSERT OR IGNORE INTO MEDALLAS_USUARIOS (userID, lider_id) VALUES (?, ?)",
                (user_id, lider_id),
            )

            # Recompensa cosmos
            from funciones import economy_service
            economy_service.add_credits(
                user_id, lider["recompensa"],
                f"Victoria vs {lider['nombre']} ({self.region})",
            )

            # ── Recompensa MT ──────────────────────────────────────────────
            mt = lider.get("mt_recompensa", {})
            mt_texto = ""
            if mt and mt.get("move_key"):
                from pokemon.mt_system import MT_MAP
                from pokemon.services import items_service

                move_norm = mt["move_key"].lower().replace(" ", "").replace("-", "")
                # Buscar el item_id correcto según Gen 9 MT_MAP
                item_id = next(
                    (k for k, v in MT_MAP.items() if v == move_norm), None
                )
                if item_id:
                    items_service.agregar_item(user_id, item_id, 1)
                    mt_texto = (
                        f"📀 Recibiste <b>{item_id.upper()} — "
                        f"{mt.get('nombre_es', move_norm)}</b> en tu mochila\n"
                    )
                else:
                    logger.warning(f"[GYM] MT no encontrada para move_key={move_norm}")
                    mt_texto = (
                        f"📀 <b>{mt.get('nombre_es', move_norm)}</b> "
                        f"(MT no disponible en Gen 9)\n"
                    )

            total_medallas = self.medallas_count(user_id)
            progreso       = f"{total_medallas}/{self.total_gimnasios}"

            mensaje = (
                f"🏆 **¡VICTORIA!**\n\n"
                f"Derrotaste a **{lider['nombre']}** — {lider['titulo']}\n\n"
                f"{lider['emoji']} Medalla obtenida: **{lider['medalla']}**\n"
                f"💰 Recompensa: **{lider['recompensa']:,} cosmos**\n"
            )
            if mt_texto:
                mensaje += mt_texto
            mensaje += f"\n📊 Progreso: **{progreso}** medallas"

            if total_medallas >= self.total_gimnasios:
                mensaje += (
                    f"\n\n🌟 **¡Obtuviste las {self.total_gimnasios} medallas de {self.region}!**\n"
                    "⚔️ El **Alto Mando** ya está disponible."
                )

            logger.info(f"[GYM] Usuario {user_id} obtuvo medalla: {lider_id}")
            return True, mensaje

        except Exception as e:
            logger.error(f"[GYM] Error otorgando medalla: {e}")
            return False, "❌ Error al procesar la medalla."

    # ──────────────────────────────────────────────────────────
    # Creación del equipo del líder
    # ──────────────────────────────────────────────────────────
    def crear_equipo_lider(self, lider_id: str) -> List[int]:
        """
        Crea en BD los Pokémon del líder con los niveles y movesets oficiales.

        Returns:
            Lista de id_unico de los Pokémon creados (vacía si falla).
        """
        try:
            from pokemon.services import pokemon_service

            lider = self.obtener_lider(lider_id)
            if not lider:
                logger.error(f"[GYM] crear_equipo_lider: líder '{lider_id}' no encontrado")
                return []

            equipo_ids: List[int] = []
            for poke_data in lider["equipo"]:
                pid = pokemon_service.crear_pokemon(
                    user_id=_NPC_USER_ID,
                    pokemon_id=poke_data["pokemon_id"],
                    nivel=poke_data["nivel"],
                )
                if pid:
                    # Asignar moveset específico del líder en move1..move4
                    moves = (poke_data.get("moves", []) + [None, None, None, None])[:4]
                    self.db.execute_update(
                        "UPDATE POKEMON_USUARIO SET move1=?, move2=?, move3=?, move4=? WHERE id_unico=?",
                        (moves[0], moves[1], moves[2], moves[3], pid),
                    )
                    equipo_ids.append(pid)

            return equipo_ids

        except Exception as e:
            logger.error(f"[GYM] Error creando equipo de líder '{lider_id}': {e}")
            return []

    def limpiar_equipo_npc(self) -> None:
        """
        Elimina de BD TODOS los Pokémon NPC (userID = 999999).
        ⚠️  Solo usar en arranque/parada del bot o como fallback de emergencia.
        Para finalizar una batalla individual usar limpiar_equipo_npc_ids().
        """
        try:
            self.db.execute_update(
                "DELETE FROM POKEMON_USUARIO WHERE userID = ?",
                (_NPC_USER_ID,),
            )
        except Exception as e:
            logger.error(f"[GYM] Error limpiando equipo NPC global: {e}")

    def limpiar_equipo_npc_ids(self, ids: list) -> None:
        """
        Elimina de BD únicamente los Pokémon NPC con los id_unico dados.
        Usar siempre que se cierra UNA batalla de gimnasio, para no
        interferir con batallas concurrentes de otros jugadores.
        """
        if not ids:
            return
        try:
            placeholders = ",".join("?" * len(ids))
            self.db.execute_update(
                f"DELETE FROM POKEMON_USUARIO WHERE id_unico IN ({placeholders})",
                tuple(ids),
            )
        except Exception as e:
            logger.error(f"[GYM] Error limpiando equipo NPC por IDs {ids}: {e}")

    # ──────────────────────────────────────────────────────────
    # Alto Mando
    # ──────────────────────────────────────────────────────────
    def obtener_victorias_e4(self, user_id: int) -> List[str]:
        """Devuelve la lista de lider_ids del Alto Mando ya derrotados."""
        try:
            rows = self.db.execute_query(
                "SELECT lider_id FROM MEDALLAS_USUARIOS WHERE userID = ?",
                (user_id,),
            )
            ids_e4 = {m["id"] for m in self.elite_four}
            return [
                (row["lider_id"] or "").lower()
                for row in rows
                if (row["lider_id"] or "").lower() in ids_e4
            ]
        except Exception as e:
            logger.error(f"[GYM] Error obteniendo victorias E4 usuario {user_id}: {e}")
            return []

    def obtener_siguiente_e4(self, user_id: int) -> Optional[Dict]:
        """
        Devuelve el siguiente miembro del Alto Mando a enfrentar.

        Requiere que el usuario tenga todas las medallas de la región.
        Devuelve None si no tiene las medallas o si ya completó el Alto Mando.
        """
        if not self.todas_las_medallas(user_id):
            return None

        victorias = set(self.obtener_victorias_e4(user_id))
        for miembro in self.elite_four:
            if miembro["id"] not in victorias:
                return miembro
        return None  # ya es Campeón

    def puede_desafiar_e4(self, user_id: int, e4_id: str) -> Tuple[bool, str]:
        """Verifica si el usuario puede desafiar a un miembro del Alto Mando."""
        if not self.todas_las_medallas(user_id):
            return (
                False,
                f"❌ Necesitas las **{self.total_gimnasios} medallas** de "
                f"{self.region} para acceder al Alto Mando.",
            )

        siguiente = self.obtener_siguiente_e4(user_id)
        if siguiente is None:
            return False, "🏆 ¡Ya eres Campeón de esta región!"

        if siguiente["id"] != e4_id:
            return (
                False,
                f"⚔️ Debes derrotar primero a **{siguiente['nombre']}**.",
            )

        return True, "OK"

    def otorgar_victoria_e4(self, user_id: int, e4_id: str) -> Tuple[bool, str]:
        """Registra la victoria contra un miembro del Alto Mando y entrega recompensas."""
        try:
            miembro = self.obtener_lider(e4_id)
            if not miembro:
                return False, "❌ Miembro del Alto Mando no encontrado."

            self.db.execute_update(
                "INSERT OR IGNORE INTO MEDALLAS_USUARIOS (userID, lider_id) VALUES (?, ?)",
                (user_id, e4_id),
            )

            from funciones import economy_service
            economy_service.add_credits(
                user_id, miembro["recompensa"],
                f"Victoria vs E4 {miembro['nombre']} ({self.region})",
            )

            # Recompensa MT
            mt       = miembro.get("mt_recompensa", {})
            mt_texto = ""
            if mt and mt.get("mt_num"):
                agregada = self._agregar_mt_inventario(user_id, mt["mt_num"])
                item_id  = f"mt{mt['mt_num']:03d}"
                if agregada:
                    mt_texto = f"📀 Recibiste **{item_id.upper()} — {mt['nombre_es']}** en tu mochila\n"
                else:
                    mt_texto = f"📀 MT{mt['mt_num']:02d} **{mt['nombre_es']}** (error al entregar)\n"

            es_campeon = miembro["id"] == self.elite_four[-1]["id"]
            titulo     = "🏆 **¡CAMPEÓN DE LA REGIÓN!**" if es_campeon else "🏆 **¡VICTORIA!**"

            mensaje = (
                f"{titulo}\n\n"
                f"Derrotaste a **{miembro['nombre']}** — {miembro['titulo']}\n\n"
                f"💰 Recompensa: **{miembro['recompensa']:,} cosmos**\n"
            )
            if mt_texto:
                mensaje += mt_texto
            if es_campeon:
                mensaje += f"\n🌟 ¡Eres el nuevo **Campeón de {self.region}**! ¡Pasa al Salón de la Fama!"

            logger.info(f"[GYM] Usuario {user_id} derrotó E4: {e4_id}")
            return True, mensaje

        except Exception as e:
            logger.error(f"[GYM] Error registrando victoria E4: {e}")
            return False, "❌ Error al procesar la victoria."

    # ──────────────────────────────────────────────────────────
    # Progreso y utilidades
    # ──────────────────────────────────────────────────────────
    def obtener_progreso(self, user_id: int) -> Dict:
        """Devuelve un resumen del progreso del usuario en la región."""
        medallas = self.obtener_medallas(user_id)
        siguiente_gym = self.obtener_siguiente_lider(user_id)
        siguiente_e4 = self.obtener_siguiente_e4(user_id)
        victorias_e4 = self.obtener_victorias_e4(user_id)

        return {
            "region": self.region,
            "medallas": len(medallas),
            "total_gimnasios": self.total_gimnasios,
            "porcentaje": round((len(medallas) / self.total_gimnasios) * 100, 1),
            "lista_medallas": medallas,
            "siguiente_gym": siguiente_gym["nombre"] if siguiente_gym else None,
            "siguiente_e4": siguiente_e4["nombre"] if siguiente_e4 else None,
            "victorias_e4": len(victorias_e4),
            "total_e4": len(self.elite_four),
            "es_campeon": siguiente_e4 is None and self.todas_las_medallas(user_id),
        }

    def obtener_info_lider(self, lider_id: str) -> Optional[Dict]:
        """Devuelve los datos públicos de un líder (sin moves internos)."""
        lider = self.obtener_lider(lider_id)
        if not lider:
            return None
        return {k: v for k, v in lider.items() if k != "equipo"}

    def ai(self) -> Type[GymBattleAI]:
        """Devuelve la clase GymBattleAI para llamar seleccionar_movimiento()."""
        return GymBattleAI


# ─────────────────────────────────────────────────────────────────────────────
# Instancia global
# ─────────────────────────────────────────────────────────────────────────────
gimnasio_service = GimnasioService()
