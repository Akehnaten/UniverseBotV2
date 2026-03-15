"""
pokemon/battle_ui.py
════════════════════
Función universal para construir la línea de HP de un Pokémon en batalla.
Usada por wild_battle_system, gym_battle_system y pvp_battle_system.

Formato:
  🔴 Onix ♂  Roca/Tierra  Nv.18
     HP: 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 17/17
     🔥 Quemado  +2Atk -1Vel
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pokemon.battle_engine import STATUS_ICONS


# ── Emojis de tipo (igual que pvp/wild) ──────────────────────────────────────
TYPE_EMOJI: Dict[str, str] = {
    "Normal":    "⚪", "Fuego":     "🔥", "Agua":      "💧",
    "Planta":    "🌿", "Eléctrico": "⚡", "Hielo":     "🧊",
    "Lucha":     "🥊", "Veneno":    "☠️", "Tierra":    "🌍",
    "Volador":   "🌪️", "Psíquico":  "🔮", "Bicho":     "🐛",
    "Roca":      "🪨", "Fantasma":  "👻", "Dragón":    "🐉",
    "Siniestro": "🌑", "Acero":     "⚙️", "Hada":      "🌸",
}

# Nombres legibles de status
STATUS_NOMBRES: Dict[str, str] = {
    "brn": "🔥 Quemado",
    "par": "⚡ Paralizado",
    "psn": "☠️ Envenenado",
    "tox": "☠️ Tóxico",
    "slp": "💤 Dormido",
    "frz": "🧊 Congelado",
}

# Etiquetas legibles de stat stages
_STAGE_LABELS: Dict[str, str] = {
    "atq":    "Atk",
    "def":    "Def",
    "atq_sp": "SpA",
    "def_sp": "SpD",
    "vel":    "Vel",
}


def hp_bar(hp_actual: int, hp_max: int, length: int = 10) -> str:
    """Genera barra de HP visual. Ejemplo: 🟩🟩🟩🟩🟩🟩⬛⬛⬛⬛"""
    pct    = int(hp_actual / max(1, hp_max) * 100)
    filled = max(0, min(length, int(pct / 100 * length)))
    color  = "🟩" if pct > 50 else ("🟨" if pct > 20 else "🟥")
    return color * filled + "⬛" * (length - filled)


def stages_str(stages: Optional[Dict[str, int]]) -> str:
    """'+2Atk -1Def' desde dict de stat stages. Vacío si todos son 0."""
    if not stages:
        return ""
    parts = []
    for stat, label in _STAGE_LABELS.items():
        val = stages.get(stat, 0)
        if val != 0:
            parts.append(f"{'+'if val>0 else ''}{val}{label}")
    return " ".join(parts)

# Iconos y nombres de hazards por lado
_HAZARD_PLAYER = [
    ("stealth_rock",  "🪨 T.Rocas"),
    ("spikes",        "📍 Púas"),
    ("toxic_spikes",  "☠️ P.Tóxicas"),
    ("sticky_web",    "🕸️ Telaraña"),
]
_HAZARD_WILD = [
    ("wild_stealth_rock",  "🪨 T.Rocas"),
    ("wild_spikes",        "📍 Púas"),
    ("wild_toxic_spikes",  "☠️ P.Tóxicas"),
    ("wild_sticky_web",    "🕸️ Telaraña"),
]


def build_field_status_line(battle) -> str:
    """
    Devuelve una línea con el estado del campo de batalla:
    clima (con turnos restantes), terreno, salas activas y trampas de entrada.

    Ejemplo:
        ☀️ Sol (3t)  🌿 C.Hierba (4t)  🔄 Sala Trampa
        🪨 T.Rocas [rival]  📍 Púas×2 [tuyo]
    """
    from pokemon.battle_engine import WEATHER_INFO, TERRAIN_INFO, ROOM_INFO

    partes: list[str] = []

    # ── Clima ──────────────────────────────────────────────────────────────
    weather = getattr(battle, "weather", None)
    if weather:
        emoji, nombre, _ = WEATHER_INFO.get(weather, ("🌀", weather, 0))
        turns = getattr(battle, "weather_turns", 0)
        t_str = f" ({turns}t)" if turns > 0 else " (∞)"
        partes.append(f"{emoji} {nombre}{t_str}")

    # ── Terreno ────────────────────────────────────────────────────────────
    terrain = getattr(battle, "terrain", None)
    if terrain:
        emoji, nombre, _ = TERRAIN_INFO.get(terrain, ("", terrain, 0))
        turns = getattr(battle, "terrain_turns", 0)
        t_str = f" ({turns}t)" if turns > 0 else " (∞)"
        partes.append(f"{emoji} {nombre}{t_str}")

    # ── Salas (Trick Room, Gravity, etc.) ──────────────────────────────────
    for room_key, (emoji, nombre, _) in ROOM_INFO.items():
        if getattr(battle, room_key, False):
            turns = getattr(battle, room_key + "_turns", 0)
            t_str = f" ({turns}t)" if turns > 0 else ""
            partes.append(f"{emoji} {nombre}{t_str}")

    linea1 = "  ".join(partes) if partes else ""

    # ── Trampas de entrada ─────────────────────────────────────────────────
    hazards: list[str] = []

    # Lado del wild/rival (donde aterrizan los Pokémon del jugador)
    if getattr(battle, "wild_stealth_rock", False):
        hazards.append("🪨T.R[rival]")
    spikes_w = getattr(battle, "wild_spikes", 0)
    if spikes_w:
        hazards.append(f"📍Púas×{spikes_w}[rival]")
    tspikes_w = getattr(battle, "wild_toxic_spikes", 0)
    if tspikes_w:
        hazards.append(f"☠️P.T×{tspikes_w}[rival]")
    if getattr(battle, "wild_sticky_web", False):
        hazards.append("🕸️Web[rival]")

    # Lado del jugador (donde aterrizan los Pokémon rivales)
    if getattr(battle, "player_stealth_rock", False):
        hazards.append("🪨T.R[tuyo]")
    spikes_p = getattr(battle, "player_spikes", 0)
    if spikes_p:
        hazards.append(f"📍Púas×{spikes_p}[tuyo]")
    tspikes_p = getattr(battle, "player_toxic_spikes", 0)
    if tspikes_p:
        hazards.append(f"☠️P.T×{tspikes_p}[tuyo]")
    if getattr(battle, "player_sticky_web", False):
        hazards.append("🕸️Web[tuyo]")

    linea2 = "  ".join(hazards) if hazards else ""

    resultado = "\n".join(l for l in [linea1, linea2] if l)
    return resultado

def build_pokemon_line(
    *,
    lado:      str,            # "🔴" o "🔵"
    nombre:    str,            # mote o nombre especie
    sexo:      Optional[str],  # "M", "F" o None
    tipos:     List[str],      # ["Roca", "Tierra"]
    nivel:     int,
    hp_actual: int,
    hp_max:    int,
    status:    Optional[str],  # "brn", "par", etc.
    stages:    Optional[Dict[str, int]] = None,
) -> str:
    """
    Devuelve el bloque de texto para un Pokémon en el panel de batalla.

    Ejemplo de salida (3 líneas):
        🔴 Onix ♂  Roca/Tierra  Nv.18
           HP: 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 17/17
           🔥 Quemado  +2Atk -1Vel
    """
    # Línea 1: identificación
    sexo_sym  = {"M": " ♂", "F": " ♀"}.get(sexo or "", "")
    tipos_str = "/".join(tipos) if tipos else "Normal"
    linea1    = f"{lado} <b>{nombre}</b>{sexo_sym}  {tipos_str}  Nv.{nivel}"

    # Línea 2: HP
    barra  = hp_bar(hp_actual, hp_max)
    linea2 = f"   HP: {barra} {hp_actual}/{hp_max}"

    # Línea 3: status + stages (solo si hay algo que mostrar)
    partes3 = []
    if status:
        partes3.append(STATUS_NOMBRES.get(status, status))
    boost = stages_str(stages)
    if boost:
        partes3.append(boost)
    linea3 = ("   " + "  ".join(partes3)) if partes3 else ""

    lines = [linea1, linea2]
    if linea3:
        lines.append(linea3)
    return "\n".join(lines)