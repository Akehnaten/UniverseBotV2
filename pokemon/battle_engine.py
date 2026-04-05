# -*- coding: utf-8 -*-
"""
pokemon/battle_engine.py
═══════════════════════════════════════════════════════════════════════════════
Motor de combate central — sin estado, sin Telegram, sin base de datos.

Toda la física de batalla (daño, efectividad, etapas de stats, orden de turno)
vive aquí. Wild, PvP y VGC importan de este módulo; cada uno sólo aporta su
contexto específico (captura, IA del salvaje, MMR, formato dobles, etc.).

Importado por:
  • pokemon/wild_battle_system.py   → combate contra salvajes
  • pokemon/pvp_system.py           → PvP 1v1 / 3v3 / 6v6
  • pokemon/services/batalla_vgc_service.py → VGC 2v2 y Alto Mando
═══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# TABLA DE ETAPAS DE STATS
# ─────────────────────────────────────────────────────────────────────────────

_STAGE_TABLE: dict[int, float] = {
    -6: 2 / 8, -5: 2 / 7, -4: 2 / 6, -3: 2 / 5, -2: 2 / 4, -1: 2 / 3,
     0: 1.0,
     1: 3 / 2,  2: 4 / 2,  3: 5 / 2,  4: 6 / 2,  5: 7 / 2,  6: 8 / 2,
}

_STAT_NAMES: dict[str, str] = {
    "atq":    "Ataque",
    "def":    "Defensa",
    "atq_sp": "At. Esp.",
    "def_sp": "Def. Esp.",
    "vel":    "Velocidad",
}


def stage_multiplier(stage: int) -> float:
    """Multiplicador de etapa de stat para el rango [-6, +6]."""
    return _STAGE_TABLE.get(max(-6, min(6, stage)), 1.0)

TWO_TURN_MOVES: dict[str, dict] = {
    # Planta
    "solarbeam":     {"skip_weather": "sun",  "msg_carga": "¡{nombre} absorbió la luz solar!"},
    "solarblade":    {"skip_weather": "sun",  "msg_carga": "¡{nombre} absorbió la luz solar!"},
    # Normal
    "skullbash":     {"skip_weather": None,   "msg_carga": "¡{nombre} escondió la cabeza!"},
    "razorwind":     {"skip_weather": None,   "msg_carga": "¡{nombre} creó un vendaval!"},
    # Lucha
    "skyuppercut":   {"skip_weather": None,   "msg_carga": "¡{nombre} se concentró!"},
    # Volador
    "bounce":        {"skip_weather": None,   "msg_carga": "¡{nombre} saltó muy alto!"},
    "fly":           {"skip_weather": None,   "msg_carga": "¡{nombre} voló alto en el cielo!"},
    # Tierra
    "dig":           {"skip_weather": None,   "msg_carga": "¡{nombre} cavó un agujero!"},
    # Agua
    "dive":          {"skip_weather": None,   "msg_carga": "¡{nombre} se sumergió bajo el agua!"},
    # Fantasma
    "phantomforce":  {"skip_weather": None,   "msg_carga": "¡{nombre} desapareció!"},
    "shadowforce":   {"skip_weather": None,   "msg_carga": "¡{nombre} desapareció!"},
    # Hada
    "geomancy":      {"skip_weather": None,   "msg_carga": "¡{nombre} absorbió la energía!"},
    # Psíquico
    "meteormash":    {"skip_weather": None,   "msg_carga": "¡{nombre} se concentró!"},
    # Hielo
    "freezeshock":   {"skip_weather": None,   "msg_carga": "¡{nombre} acumuló energía helada!"},
    "iciclecrash":   {"skip_weather": None,   "msg_carga": "¡{nombre} acumuló hielo!"},
    # Lucha falla si recibe daño en el turno de carga
    "focuspunch": {"skip_weather":None,"msg_carga":"¡{nombre} está concentrando su fuerza!","interrupt_on_hit": True,},
}

DELAYED_MOVES: dict[str, dict] = {
    "futuresight": {
        "turns":       2,
        "power":       120,
        "msg_uso":     "¡{nombre} concentró su poder psíquico!",
        "msg_impacto": "¡El poder psíquico de {attacker} golpeó a {defender}!",
    },
    "doomdesire": {
        "turns":       2,
        "power":       140,
        "msg_uso":     "¡{nombre} eligió el Deseo Fatídico!",
        "msg_impacto": "¡El Deseo Fatídico de {attacker} golpeó a {defender}!",
    },
}

# Movimientos de daño fijo (ignoran stats, etapas y clima)
FIXED_DAMAGE_MOVES: dict[str, dict] = {
    # Daño = nivel del atacante. Inmune: tipo Normal
    "nightshade":  {"damage_fn": "level", "immune_types": ["Normal"]},
    # Daño = nivel del atacante. Inmune: tipo Fantasma
    "seismictoss": {"damage_fn": "level", "immune_types": ["Ghost", "Fantasma"]},
    # Siempre 40 HP. Inmune: Normal y Hada
    "dragonrage":  {"damage_fn": "fixed", "damage": 40,
                    "immune_types": ["Normal", "Fairy", "Hada"]},
}

# Movimientos que disparan en turno 1 y requieren recarga en turno 2.
# Valor: mensaje que se muestra durante el turno de recarga.
RECHARGE_MOVES: dict[str, str] = {
    "hyperbeam":      "¡{nombre} necesita recargarse!",
    "gigaimpact":     "¡{nombre} necesita recargarse!",
    "frenzyplant":    "¡{nombre} necesita recargarse!",
    "blastburn":      "¡{nombre} necesita recargarse!",
    "hydrocannon":    "¡{nombre} necesita recargarse!",
    "rockwrecker":    "¡{nombre} necesita recargarse!",
    "roaroftime":     "¡{nombre} necesita recargarse!",
    "eternabeam":     "¡{nombre} necesita recargarse!",
    "prismaticlaser": "¡{nombre} necesita recargarse!",
    "metronome":      "¡{nombre} necesita recargarse!",   # solo si lanza hyperbeam
}

# ─────────────────────────────────────────────────────────────────────────────
# BATTLE UTILS  (idéntico a la clase homónima de wild_battle_system; se
# mantiene aquí como fuente de verdad; wild_battle_system reexporta el alias)
# ─────────────────────────────────────────────────────────────────────────────

class BattleUtils:
    """Utilidades de cálculo de combate. Todos los métodos son estáticos."""

    @staticmethod
    def calculate_damage(
        attacker_level: int,
        attacker_stat: int,
        defender_stat: int,
        move_power: int,
        type_effectiveness: float = 1.0,
        is_critical: bool = False,
    ) -> int:
        """
        Fórmula oficial Pokémon:
        ((2·Nivel/5 + 2) · Poder · Ataque/Defensa / 50 + 2) · Mods

        Variación aleatoria 0.85–1.00 incluida.
        Retorna mínimo 1.
        """
        if move_power <= 0:
            return 0

        damage = (2 * attacker_level / 5 + 2)
        damage *= move_power * (attacker_stat / max(defender_stat, 1))
        damage = damage / 50 + 2

        if is_critical:
            damage *= 1.5

        damage *= type_effectiveness
        damage *= random.uniform(0.85, 1.0)

        return max(1, int(damage))
    
#   Stage 1 →  1/8   = 12.50 %   (Focus Energy, Scope Lens, etc.)
#   Stage 2 →  1/2   = 50.00 %
#   Stage 3+ → 1/1   = 100  %    (garantizado)
#
# El motor actualmente no trackea crit_stage, así que se trabaja con stage=0
# por defecto y se expone el parámetro para cuando se quiera implementar
# movimientos como Focus Energy o ítems como Scope Lens.

    @staticmethod
    def check_critical_hit(speed: int = 0, crit_stage: int = 0) -> bool:
        """
        Probabilidad de golpe crítico — fórmula Gen 6+ / Gen 9.

        Stage 0  →  1/24  ≈  4.17 %   (base, sin modificadores)
        Stage 1  →  1/8   = 12.50 %   (Focus Energy, Scope Lens, Lucky Punch…)
        Stage 2  →  1/2   = 50.00 %   (Focus Energy + Scope Lens acumulados)
        Stage 3+ →  100 % (garantizado)

        `speed` se conserva en la firma para no romper llamadas existentes
        pero ya no afecta al resultado.
        """
        if crit_stage >= 3:
            return True  # ← agregar este guard
        _CRIT_CHANCES = {0: 1/24, 1: 1/8, 2: 1/2}
        return random.random() < _CRIT_CHANCES.get(crit_stage, 1.0)

    @staticmethod
    def effective_stat(base_stat: int, stage: int) -> int:
        """Aplica el multiplicador de etapa a un stat base. Mínimo 1."""
        return max(1, int(base_stat * stage_multiplier(stage)))

    @staticmethod
    def effective_speed(base_speed: int, stage: int, status: Optional[str] = None) -> float:
        """
        Velocidad efectiva con etapa aplicada y penalización de parálisis.
        Parálisis (Gen 7+): -50% sobre la velocidad ya modificada por stages.
        """
        vel = base_speed * stage_multiplier(stage)
        if status == "par":
            vel *= 0.5
        return vel
    
    @staticmethod
    def calculate_flee_chance(
        player_speed: int,
        wild_speed: int,
        flee_attempts: int
    ) -> float:
        """
        Calcula la probabilidad de huir con éxito.
        Fórmula oficial Gen 3+: ((Vel_jugador * 128) // Vel_salvaje + 30 * intentos) / 256
        División entera en el numerador, como en los juegos reales.
        """
        if wild_speed == 0:
            return 1.0

        base   = (player_speed * 128) // max(wild_speed, 1)  # división ENTERA ← fix
        bonus  = 30 * flee_attempts
        chance = (base + bonus) / 256
        return min(1.0, max(0.0, chance))


# ─────────────────────────────────────────────────────────────────────────────
# RESULTADO DE UN MOVIMIENTO DE DAÑO
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DamageResult:
    """Resultado inmutable del cálculo de un movimiento de daño."""

    damage: int = 0
    is_critical: bool = False
    type_effectiveness: float = 1.0
    stab: float = 1.0
    drained_hp: int = 0          # HP que el atacante recupera (absorción)
    fainted: bool = False
    log: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# RESOLUCIÓN DE MOVIMIENTO DE DAÑO
# ─────────────────────────────────────────────────────────────────────────────

def resolve_damage_move(
    *,
    attacker_name: str,
    defender_name: str,
    attacker_level: int,
    attacker_stats: dict,
    attacker_types: list,
    attacker_stages: dict,
    defender_hp: int,
    defender_stats: dict,
    defender_types: list,
    defender_stages: dict,
    move_name: str,
    move_power: int,
    move_category: str,             # "Físico" | "Especial"
    move_type: str,
    type_effectiveness_fn: Callable[[str, list], float],
    drain_ratio: float = 0.0,       # 0.5 → Drenadora/Absorber, 0.0 si no aplica
    crit_stage:  int   = 0,
    defender_ability: str   = "",   # habilidad del defensor (e.g. "Multiescamas")
    defender_hp_max:  int   = 0,    # HP máximo del defensor para Multiescamas
    attacker_ability: str   = "",
) -> DamageResult:
    """
    Resuelve un movimiento de daño entre dos bandos.

    Puramente funcional: no modifica ningún objeto, no toca la BD, no
    envía mensajes. El llamador lee `result.damage`, aplica el daño a su
    modelo y muestra `result.log`.

    Args:
        attacker_name / defender_name: Nombres para el log.
        attacker_level: Nivel del atacante.
        attacker_stats / defender_stats: Dict con claves "atq", "def",
            "atq_sp", "def_sp", "vel".
        attacker_types / defender_types: Lista de tipos del Pokémon.
        attacker_stages / defender_stages: Dict de etapas de stats.
        defender_hp: HP actual del defensor (para calcular `fainted`).
        move_name: Nombre del movimiento (usado sólo en logs).
        move_power: Poder base del movimiento.
        move_category: "Físico" o "Especial".
        move_type: Tipo del movimiento (ej. "Fuego").
        type_effectiveness_fn: Callable(move_type, defender_types) → float.
        drain_ratio: Fracción del daño que el atacante recupera.

    Returns:
        DamageResult con todo el resultado y las líneas de log.
    """
    result = DamageResult()

    if move_power <= 0:
        return result

    # ── STAB ─────────────────────────────────────────────────────────────────
    _tiene_stab = move_type in attacker_types
    _hab_norm   = attacker_ability.lower().replace(" ", "").replace("-", "")
    if _tiene_stab:
        stab = 2.0 if _hab_norm in ("adaptabilidad", "adaptability") else 1.5
    else:
        stab = 1.0
    result.stab = stab

    # ── Efectividad de tipo ───────────────────────────────────────────────────
    type_eff: float = type_effectiveness_fn(move_type, defender_types)
    result.type_effectiveness = type_eff

    if type_eff == 0.0:
        result.log.append(f"  🚫 ¡No afecta a {defender_name}!\n")
        return result

    # ── Golpe crítico ─────────────────────────────────────────────────────────
    # Se calcula ANTES de los stats para aplicar el bypass correcto (Gen 6+):
    # en crítico → ignorar stages negativos del atacante y positivos del defensor.
    is_crit: bool = BattleUtils.check_critical_hit(crit_stage=crit_stage)
    result.is_critical = is_crit

    # ── Stats efectivos ───────────────────────────────────────────────────────
    if move_category == "Físico":
        _atk_stage = max(0, attacker_stages.get("atq", 0)) if is_crit \
                     else attacker_stages.get("atq", 0)
        _def_stage = min(0, defender_stages.get("def", 0)) if is_crit \
                     else defender_stages.get("def", 0)
        atk  = BattleUtils.effective_stat(attacker_stats.get("atq", 50),  _atk_stage)
        def_ = BattleUtils.effective_stat(defender_stats.get("def", 50),  _def_stage)
    else:   # Especial
        _atk_stage = max(0, attacker_stages.get("atq_sp", 0)) if is_crit \
                     else attacker_stages.get("atq_sp", 0)
        _def_stage = min(0, defender_stages.get("def_sp", 0)) if is_crit \
                     else defender_stages.get("def_sp", 0)
        atk  = BattleUtils.effective_stat(attacker_stats.get("atq_sp", 50), _atk_stage)
        def_ = BattleUtils.effective_stat(
            defender_stats.get("def_sp", defender_stats.get("def", 50)), _def_stage
        )

    # ── Daño ──────────────────────────────────────────────────────────────────
    damage: int = BattleUtils.calculate_damage(
        attacker_level=attacker_level,
        attacker_stat=atk,
        defender_stat=def_,
        move_power=move_power,
        type_effectiveness=stab * type_eff,
        is_critical=is_crit,
    )
    # ── Habilidad: Multiescamas ───────────────────────────────────────────
    # A HP lleno, reduce el daño del primer golpe recibido a la mitad.
    # La condición "defender_hp >= defender_hp_max" se cumple únicamente
    # antes del primer impacto; en golpes multi-hit posteriores
    # defender_hp ya habrá descendido, por lo que no se activa de nuevo.
    if (
        defender_ability in ["Multiescamas", "Multiscale"]
        and defender_hp_max > 0
        and defender_hp >= defender_hp_max
        and damage > 0
    ):
        damage = max(1, damage // 2)
        result.log.append("  🐉 ¡<b>Multiescamas</b> redujo el daño a la mitad!\n")


    # El daño no puede superar el HP actual del defensor
    damage = min(damage, max(0, defender_hp))
    result.damage = damage

    # ── Log de efectividad ────────────────────────────────────────────────────
    if is_crit:           result.log.append("  ✨ ¡Golpe crítico!\n")
    if type_eff > 1.0:    result.log.append("  🔥 ¡Es muy efectivo!\n")
    elif type_eff < 1.0:  result.log.append("  😐 No es muy efectivo...\n")
    if stab > 1.0:        result.log.append("  💪 ¡Bono STAB!\n")
    result.log.append(f"  💥 Causó <b>{damage}</b> de daño\n\n")

    # ── Drenaje ───────────────────────────────────────────────────────────────
    if drain_ratio > 0 and damage > 0:
        drained = max(1, int(damage * drain_ratio))
        result.drained_hp = drained
        result.log.append(f"  🌿 {attacker_name} absorbió {drained} HP.\n")

    # ── ¿Debilitado? ─────────────────────────────────────────────────────────
    if max(0, defender_hp - damage) <= 0:
        result.fainted = True
        result.log.append(f"  💀 ¡{defender_name} se debilitó!\n")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# CAMBIO DE ETAPAS DE STAT (movimientos de estado)
# ─────────────────────────────────────────────────────────────────────────────

def apply_stage_change(
    stat: str,
    delta: int,
    stages: dict,
    pokemon_name: str,
    log: list,
) -> None:
    """
    Aplica un cambio de etapa a un stat (in-place) y añade líneas al log.

    Usable para cualquier bando sin distinción (jugador, rival, salvaje).

    Args:
        stat: Clave del stat ("atq", "def", "atq_sp", "def_sp", "vel").
        delta: Cantidad de etapas a subir (+) o bajar (-).
        stages: Dict mutable de etapas del Pokémon objetivo.
        pokemon_name: Nombre para el mensaje de log.
        log: Lista a la que se añaden las líneas de resultado.
    """
    old = stages.get(stat, 0)
    new = max(-6, min(6, old + delta))

    if new == old:
        direction = "no puede bajar más" if delta < 0 else "no puede subir más"
        log.append(
            f"  ⚠️ El {_STAT_NAMES.get(stat, stat)} de {pokemon_name} {direction}!\n"
        )
    else:
        stages[stat] = new
        verb = "bajó" if delta < 0 else "subió"
        adv  = "bastante" if abs(delta) >= 2 else "un poco"
        log.append(
            f"  📊 El {_STAT_NAMES.get(stat, stat)} de {pokemon_name} {verb} {adv}!\n"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ORDEN DE TURNO
# ─────────────────────────────────────────────────────────────────────────────

def determine_turn_order(
    speed_a: int,
    stages_a: int,
    speed_b: int,
    stages_b: int,
    priority_a: int = 0,
    priority_b: int = 0,
    status_a: Optional[str] = None,
    status_b: Optional[str] = None,
) -> bool:
    """
    Determina si el bando A actúa primero en el turno.

    Considera:
      1. Prioridad del movimiento (Ataque Rápido = 1, etc.).
      2. Velocidad efectiva con etapas aplicadas y parálisis (-50%).
      3. Empate exacto → aleatorio (50 / 50).
    """
    if priority_a != priority_b:
        return priority_a > priority_b

    eff_a = BattleUtils.effective_speed(speed_a, stages_a, status_a)
    eff_b = BattleUtils.effective_speed(speed_b, stages_b, status_b)

    if eff_a == eff_b:
        return random.random() < 0.5

    return eff_a > eff_b

# ─────────────────────────────────────────────────────────────────────────────
# CLIMAS
# ─────────────────────────────────────────────────────────────────────────────

WEATHER_INFO: dict[str, tuple] = {
    "sun":  ("☀️",  "Sol Intenso",      5),
    "rain": ("🌧️", "Lluvia",            5),
    "sand": ("🌪️", "Tormenta de Arena", 5),
    "snow": ("❄️",  "Nevada",            5),
    "fog":  ("🌫️", "Niebla",            5),
}

# Multiplicadores de tipo por clima  {clima: {tipo_move: mult}}
WEATHER_TYPE_MULT: dict[str, dict] = {
    "sun":  {"Fuego": 1.5, "Agua": 0.5},
    "rain": {"Agua": 1.5, "Fuego": 0.5},
    "sand": {},
    "snow": {},
    "fog":  {},
}

# Tipos que son inmunes al daño residual de ese clima
WEATHER_IMMUNE_TYPES: dict[str, set] = {
    "sand": {"Roca", "Tierra", "Acero"},
    "snow": {"Hielo"},
    "fog":  set(),
}

# Precisión especial de ciertos movimientos en ciertos climas (999 = nunca falla)
WEATHER_MOVE_PRECISION: dict[str, dict] = {
    "sun":  {"thunder": 50, "hurricane": 50, "solarbeam": 0},
    "rain": {"thunder": 999, "hurricane": 999},
    "snow": {"blizzard": 999},
    "sand": {},
    "fog":  {},
}

# Rocas meteorológicas: item_key → clima que extienden a 8 turnos
WEATHER_ROCKS: dict[str, str] = {
    "heatrock":   "sun",
    "damprock":   "rain",
    "smoothrock": "sand",
    "icyrock":    "snow",
}

WEATHER_ROCK_NAMES_ES: dict[str, str] = {
    "heatrock":   "Roca Calorífica",
    "damprock":   "Roca Húmeda",
    "smoothrock": "Roca Lisa",
    "icyrock":    "Roca Helada",
}

# ─────────────────────────────────────────────────────────────────────────────
# TERRENOS
# ─────────────────────────────────────────────────────────────────────────────

TERRAIN_INFO: dict[str, tuple] = {
    "electric": ("⚡", "Campo Eléctrico", 5),
    "grassy":   ("🌿", "Campo de Hierba",  5),
    "misty":    ("🌸", "Campo de Niebla",  5),
    "psychic":  ("🔮", "Campo Psíquico",   5),
}

TERRAIN_TYPE_MULT: dict[str, dict] = {
    "electric": {"Electrico": 1.3},
    "grassy":   {"Planta": 1.3, "Tierra": 0.5},
    "misty":    {"Dragón": 0.5},
    "psychic":  {"Psíquico": 1.3},
}

GRASSY_TERRAIN_HEAL: float = 1 / 16

# Ailments que cada terreno bloquea en Pokémon en suelo
TERRAIN_BLOCKS_AILMENT: dict[str, set] = {
    "electric": {"slp"},
    "misty":    {"par", "brn", "frz", "slp", "psn", "tox"},
    "psychic":  set(),
    "grassy":   set(),
}

# ─────────────────────────────────────────────────────────────────────────────
# ESPACIOS (pseudo-climas que no solapan con weather)
# ─────────────────────────────────────────────────────────────────────────────

ROOM_INFO: dict[str, tuple] = {
    "trick_room":  ("🔄", "Sala Trampa",    5),
    "gravity":     ("🌌", "Gravedad",       5),
    "magic_room":  ("✨", "Sala Mágica",    5),
    "wonder_room": ("💫", "Sala Asombrosa", 5),
}

# ─────────────────────────────────────────────────────────────────────────────
# ICONOS DE STATUS (UI)
# ─────────────────────────────────────────────────────────────────────────────

STATUS_ICONS: dict[str, str] = {
    "par": "⚡PAR",
    "brn": "🔥QMD",
    "frz": "🧊CON",
    "slp": "💤DOR",
    "psn": "☠️ENV",
    "tox": "☠️TOX",
    "cnf": "😵CNF",
}

# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES DE CAMPO — multiplicadores
# ─────────────────────────────────────────────────────────────────────────────

def apply_weather_boost(weather: Optional[str], move_type: str) -> float:
    """Multiplicador de tipo por clima. Retorna 1.0 si no aplica."""
    if not weather:
        return 1.0
    return WEATHER_TYPE_MULT.get(weather, {}).get(move_type, 1.0)


def apply_terrain_boost(
    terrain: Optional[str],
    move_type: str,
    attacker_is_grounded: bool = True,
) -> float:
    """
    Multiplicador de tipo por terreno.
    Solo aplica si el atacante está en el suelo.
    """
    if not terrain or not attacker_is_grounded:
        return 1.0
    return TERRAIN_TYPE_MULT.get(terrain, {}).get(move_type, 1.0)


def is_grounded(pokemon_types: list, battle) -> bool:
    """
    True si el Pokémon está en el suelo.
    Gravedad fuerza a todos al suelo aunque sean tipo Volador.
    """
    if getattr(battle, "gravity", False):
        return True
    return "Volador" not in pokemon_types


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES DE CAMPO — activación y tick
# ─────────────────────────────────────────────────────────────────────────────

def activate_weather(
    battle,
    weather: str,
    base_turns: int,
    activator_name: str,
    log: list,
    attacker_item: Optional[str] = None,
) -> None:
    """
    Activa un clima. Si el activador lleva la roca meteorológica correcta,
    la duración pasa de base_turns (5) a 8 turnos.
    """
    if battle.weather == weather:
        log.append(f"  💫 ¡El {WEATHER_INFO[weather][1]} ya estaba activo!\n")
        return

    turns = base_turns
    if attacker_item:
        item_key = attacker_item.lower().replace(" ", "").replace("_", "")
        if WEATHER_ROCKS.get(item_key) == weather:
            turns = 8
            rock_name = WEATHER_ROCK_NAMES_ES.get(item_key, attacker_item.title())
            log.append(
                f"  🪨 ¡La <b>{rock_name}</b> de {activator_name} "
                f"extendió el clima a 8 turnos!\n"
            )

    battle.weather = weather
    battle.weather_turns = turns
    emoji, nombre, _ = WEATHER_INFO[weather]
    log.append(f"\n  {emoji} ¡<b>{nombre}</b> comenzó!\n")


def activate_terrain(
    battle,
    terrain: str,
    turns: int,
    activator_name: str,
    log: list,
) -> None:
    """Activa un terreno de campo."""
    battle.terrain = terrain
    battle.terrain_turns = turns
    emoji, nombre, _ = TERRAIN_INFO[terrain]
    log.append(f"\n  {emoji} ¡<b>{nombre}</b> cubrió el campo de batalla!\n")


def tick_field_turns(battle, log: list) -> None:
    """
    Decrementa los contadores de clima, terreno y salas al final de cada turno.
    Cuando llegan a 0 el efecto se disipa.
    """
    # Clima
    if battle.weather and battle.weather_turns > 0:
        battle.weather_turns -= 1
        if battle.weather_turns == 0:
            emoji, nombre, _ = WEATHER_INFO.get(battle.weather, ("🌤️", battle.weather, 0))
            battle.weather = None
            log.append(f"\n🌤️ <i>El {nombre} se disipó.</i>\n")

    # Terreno
    if battle.terrain and battle.terrain_turns > 0:
        battle.terrain_turns -= 1
        if battle.terrain_turns == 0:
            emoji, nombre, _ = TERRAIN_INFO.get(battle.terrain, ("", battle.terrain, 0))
            battle.terrain = None
            log.append(f"\n{emoji} <i>El {nombre} se disipó.</i>\n")

    # Salas
    for room_attr, turns_attr, room_key in [
        ("trick_room",  "trick_room_turns",  "trick_room"),
        ("gravity",     "gravity_turns",     "gravity"),
        ("magic_room",  "magic_room_turns",  "magic_room"),
        ("wonder_room", "wonder_room_turns", "wonder_room"),
    ]:
        if getattr(battle, room_attr, False):
            remaining = getattr(battle, turns_attr, 0)
            if remaining > 0:
                setattr(battle, turns_attr, remaining - 1)
                if remaining - 1 == 0:
                    setattr(battle, room_attr, False)
                    emoji, nombre, _ = ROOM_INFO.get(room_key, ("", room_key, 0))
                    log.append(f"\n{emoji} <i>{nombre} terminó.</i>\n")


# ─────────────────────────────────────────────────────────────────────────────
# AILMENTS — aplicación y verificación
# ─────────────────────────────────────────────────────────────────────────────

def can_apply_ailment_in_field(battle, ailment: str) -> bool:
    """
    Verifica si el terreno activo bloquea la aplicación de un ailment.
    Siempre asume que el objetivo está en el suelo (worst case).
    """
    terrain = battle.terrain
    if not terrain:
        return True
    return ailment not in TERRAIN_BLOCKS_AILMENT.get(terrain, set())


def apply_ailment(
    battle,
    ailment: str,
    target_is_wild: bool,
    target_name: str,
    log: list,
) -> None:
    """
    Aplica un ailment al wild (target_is_wild=True) o al jugador.
    Respeta bloqueos de terreno.
    """
    _MSG = {
        "par": f"  ⚡ ¡{target_name} quedó paralizado!\n",
        "brn": f"  🔥 ¡{target_name} quedó quemado!\n",
        "frz": f"  🧊 ¡{target_name} quedó congelado!\n",
        "slp": f"  💤 ¡{target_name} se quedó dormido!\n",
        "psn": f"  ☠️ ¡{target_name} quedó envenenado!\n",
        "tox": f"  ☠️ ¡{target_name} quedó gravemente envenenado!\n",
    }

    if not can_apply_ailment_in_field(battle, ailment):
        campo = battle.terrain
        emoji, nombre, _ = TERRAIN_INFO.get(campo, ("", campo, 0))
        log.append(f"  {emoji} ¡El {nombre} protege a {target_name}!\n")
        return

    if ailment == "slp":
        turns = random.randint(2, 4)
        if target_is_wild:
            battle.wild_status = "slp"
            battle.wild_sleep_turns = turns
        else:
            battle.player_status = "slp"
            battle.player_sleep_turns = turns
    elif ailment == "tox":
        if target_is_wild:
            battle.wild_status = "tox"
            battle.wild_toxic_counter = 1
        else:
            battle.player_status = "tox"
            battle.player_toxic_counter = 1
    elif ailment == "cnf":
        turns = random.randint(2, 5)
        if target_is_wild:
            battle.wild_confusion_turns  = turns
        else:
            battle.player_confusion_turns = turns
        # La confusión NO ocupa el slot de status principal — es separada
        log.append(f"  😵 ¡{target_name} quedó confundido!\n")
        return  # salir sin tocar wild_status / player_status

    else:
        if target_is_wild:
            battle.wild_status = ailment
        else:
            battle.player_status = ailment

    log.append(_MSG.get(ailment, f"  💫 {target_name} fue afectado.\n"))

    # ── Primer tick inmediato de veneno / quemadura ───────────────────────────
    # En los juegos principales el daño de status ocurre al FINAL del turno
    # en que se aplica, no a partir del siguiente.  Lo calculamos aquí para
    # respetar ese comportamiento.
    if ailment in ("psn", "tox", "brn"):
        _apply_status_first_tick(battle, ailment, target_is_wild, target_name, log)

def _apply_status_first_tick(
    battle,
    ailment:        str,
    target_is_wild: bool,
    target_name:    str,
    log:            list,
) -> None:
    """
    Aplica el primer tick de daño de veneno, tóxico o quemadura en el mismo
    turno en que se aplicó el status.

    Fórmulas oficiales (Gen 6+):
      • psn  → 1/8 del HP máximo
      • tox  → 1/16 × contador (el primer tick el contador es 1 → 1/16)
      • brn  → 1/16 del HP máximo
    """
    from pokemon.services import pokemon_service as _ps
    from database import db_manager as _db

    if target_is_wild:
        wild = getattr(battle, "wild_pokemon", None)
        if not wild:
            return
        hp_max = wild.hp_max
        if ailment == "psn":
            dmg = max(1, hp_max // 8)
        elif ailment == "tox":
            counter = getattr(battle, "wild_toxic_counter", 1)
            dmg = max(1, hp_max * counter // 16)
        else:  # brn
            dmg = max(1, hp_max // 16)
        wild.hp_actual = max(0, wild.hp_actual - dmg)
        _ICON = {"psn": "☠️", "tox": "☠️", "brn": "🔥"}
        log.append(f"  {_ICON[ailment]} {target_name} sufrió {dmg} de daño por {_get_status_name(ailment)}.\n")
    else:
        p = _ps.obtener_pokemon(battle.player_pokemon_id)
        if not p:
            return
        hp_max = p.stats.get("hp", p.hp_actual) or p.hp_actual
        if ailment == "psn":
            dmg = max(1, hp_max // 8)
        elif ailment == "tox":
            counter = getattr(battle, "player_toxic_counter", 1)
            dmg = max(1, hp_max * counter // 16)
        else:  # brn
            dmg = max(1, hp_max // 16)
        new_hp = max(0, p.hp_actual - dmg)
        p.hp_actual = new_hp
        try:
            _db.execute_update(
                "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                (new_hp, battle.player_pokemon_id),
            )
        except Exception:
            pass
        _ICON = {"psn": "☠️", "tox": "☠️", "brn": "🔥"}
        log.append(f"  {_ICON[ailment]} {target_name} sufrió {dmg} de daño por {_get_status_name(ailment)}.\n")


def _get_status_name(ailment: str) -> str:
    return {"psn": "Veneno", "tox": "Tóxico", "brn": "Quemadura"}.get(ailment, ailment)

def check_can_move(
    battle,
    is_player: bool,
    actor_name: str,
    log: list,
) -> bool:
    """
    Verifica si el actor puede actuar según su status.
    Retorna True si PUEDE moverse.
    Modifica battle in-place (reduce sleep_turns, puede curar frz).
    """
    status = battle.player_status if is_player else battle.wild_status

    if status is None:
        return True

    if status == "par":
        if random.random() < 0.25:
            log.append(f"  ⚡ ¡{actor_name} está paralizado y no puede moverse!\n")
            return False
        return True

    if status == "frz":
        if random.random() < 0.20:
            if is_player:
                battle.player_status = None
            else:
                battle.wild_status = None
            log.append(f"  🌡️ ¡{actor_name} se descongeló!\n")
            return True
        log.append(f"  🧊 ¡{actor_name} está congelado y no puede moverse!\n")
        return False

    if status == "slp":
        if is_player:
            battle.player_sleep_turns -= 1
            turns_left = battle.player_sleep_turns
        else:
            battle.wild_sleep_turns -= 1
            turns_left = battle.wild_sleep_turns
        if turns_left <= 0:
            if is_player:
                battle.player_status = None
            else:
                battle.wild_status = None
            log.append(f"  ☀️ ¡{actor_name} se despertó!\n")
            return True
        log.append(f"  💤 ¡{actor_name} está dormido!\n")
        return False

    # brn / psn / tox → puede moverse, daño al final del turno
    return True


def check_confusion(
    battle,
    is_player: bool,
    actor_name: str,
    actor_level: int,
    actor_atq: int,
    log: list,
) -> bool:
    """
    Verifica y aplica el efecto de confusión.
    Debe llamarse DESPUÉS de check_can_move (si ese retornó True).
    Retorna True si el Pokémon se golpeó a sí mismo (pierde el turno).
    Modifica battle in-place (reduce confusion_turns, puede curar).
    """
    turns_attr = "player_confusion_turns" if is_player else "wild_confusion_turns"
    turns = getattr(battle, turns_attr, 0)

    if turns <= 0:
        return False  # no está confundido

    # Reducir contador
    turns -= 1
    setattr(battle, turns_attr, turns)

    if turns <= 0:
        log.append(f"  😵 ¡{actor_name} salió de su confusión!\n")
        return False

    log.append(f"  😵 ¡{actor_name} está confundido!\n")

    # 50% de probabilidad de golpearse a sí mismo
    if random.random() < 0.5:
        # Daño de autoataque: nivel 50, poder 40, sin tipo, sin stages
        # Fórmula oficial: mismo cálculo que un movimiento físico de poder 40
        self_dmg = max(1, int(
            (2 * actor_level / 5 + 2) * 40 * (actor_atq / max(actor_atq, 1)) / 50 + 2
        ))
        hp_attr = "player_pokemon_id" if is_player else None  # wild usa objeto directo

        if is_player:
            from pokemon.services import pokemon_service as _ps
            p = _ps.obtener_pokemon(battle.player_pokemon_id)
            if p:
                new_hp = max(0, p.hp_actual - self_dmg)
                p.hp_actual = new_hp
                from database import db_manager as _db
                try:
                    _db.execute_update(
                        "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                        (new_hp, battle.player_pokemon_id),
                    )
                except Exception:
                    pass
        else:
            wild = getattr(battle, "wild_pokemon", None)
            if wild:
                wild.hp_actual = max(0, wild.hp_actual - self_dmg)

        log.append(f"  💥 ¡{actor_name} se golpeó en su confusión! ({self_dmg} daño)\n")
        return True  # perdió el turno

    return False  # confundido pero logró actuar

# ─────────────────────────────────────────────────────────────────────────────
# RESULTADO DE EFECTOS RESIDUALES DE FIN DE TURNO
# ─────────────────────────────────────────────────────────────────────────────

from dataclasses import dataclass as _dc, field as _f
from typing import Optional as _Opt

@_dc
class ResidualParticipant:
    """
    Datos de entrada para un participante en el cálculo residual.
    El llamador debe construir esto desde su propio modelo de datos.
    """
    name:         str             # nombre para el log
    hp_actual:    int
    hp_max:       int
    tipos:        list            # lista de tipos en español
    status:       _Opt[str]       # "brn"|"psn"|"tox"|None
    toxic_counter: int = 0        # sólo relevante cuando status == "tox"
    yawn_counter:  int = 0        # 1 → duerme al final del turno


@_dc
class ResidualEffect:
    """Efecto calculado para un participante. Sin BD."""
    hp_delta:          int = 0     # negativo = daño, positivo = curación
    new_toxic_counter: int = 0     # valor actualizado del contador tóxico
    trigger_sleep:     bool = False  # True → el Bostezo activa Sueño ahora
    log:               list = _f(default_factory=list)


@_dc
class ResidualResult:
    """
    Resultado inmutable del cálculo de efectos residuales para DOS participantes
    (side_a = salvaje/rival; side_b = jugador/aliado).
    También incluye el tick del campo (clima, terreno).
    """
    side_a: ResidualEffect = _f(default_factory=ResidualEffect)
    side_b: ResidualEffect = _f(default_factory=ResidualEffect)
    log:    list           = _f(default_factory=list)   # log compartido (campo)


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN PURA: calculate_residual_effects
# ─────────────────────────────────────────────────────────────────────────────

def calculate_residual_effects(
    side_a: "ResidualParticipant",
    side_b: "ResidualParticipant",
    weather: _Opt[str],
    terrain: _Opt[str],
    *,
    weather_immune_types: dict,     # WEATHER_IMMUNE_TYPES de battle_engine
    weather_info: dict,             # WEATHER_INFO de battle_engine
    grassy_terrain_heal: float = 1 / 16,
) -> "ResidualResult":
    """
    Calcula todos los efectos residuales de fin de turno de forma **pura**.

    No lee ni escribe en BD.  No modifica ningún objeto.
    El llamador aplica el resultado (hp_delta, trigger_sleep, etc.) a su
    modelo y persiste los cambios.

    Args:
        side_a: Participante A (normalmente el salvaje / rival PvP).
        side_b: Participante B (normalmente el jugador).
        weather: clima activo o None.
        terrain: terreno activo o None.
        weather_immune_types: dict {weather_key: set_of_tipos_inmunes}.
        weather_info: dict {weather_key: (emoji, nombre, …)}.
        grassy_terrain_heal: fracción de hp_max que cura el campo de hierba.

    Returns:
        ResidualResult con side_a, side_b y log de campo.
    """

    def _calc_status(p: ResidualParticipant) -> ResidualEffect:
        fx = ResidualEffect(new_toxic_counter=p.toxic_counter)
        log: list = []

        if p.hp_actual <= 0:
            return fx

        # ── Alteraciones de estado ────────────────────────────────────────
        if p.status == "brn":
            dmg = max(1, p.hp_max // 16)
            fx.hp_delta -= dmg
            log.append(f"  🔥 {p.name} sufre {dmg} daño por quemadura.\n")

        elif p.status == "psn":
            dmg = max(1, p.hp_max // 8)
            fx.hp_delta -= dmg
            log.append(f"  ☠️ {p.name} sufre {dmg} daño por veneno.\n")

        elif p.status == "tox":
            counter = p.toxic_counter if p.toxic_counter > 0 else 1
            dmg = max(1, (p.hp_max * counter) // 16)
            fx.hp_delta -= dmg
            fx.new_toxic_counter = counter + 1
            log.append(f"  ☠️ {p.name} sufre {dmg} daño por Tóxico.\n")

        # ── Bostezo ───────────────────────────────────────────────────────
        if p.yawn_counter > 0:
            # El caller decrementará yawn_counter; aquí sólo señalamos
            # si este turno activa el sueño (counter llega a 0 → trigger)
            if p.yawn_counter == 1 and p.status is None:
                fx.trigger_sleep = True

        fx.log = log
        return fx

    def _calc_weather(p: ResidualParticipant) -> tuple[int, list]:
        """Retorna (hp_delta, log_lines) para el daño/curación de clima."""
        log: list = []
        delta = 0
        if weather not in ("sand", "snow"):
            return delta, log
        if p.hp_actual <= 0:
            return delta, log

        immune = weather_immune_types.get(weather, set())
        if any(t in immune for t in p.tipos):
            return delta, log

        dmg = max(1, p.hp_max // 16)
        delta -= dmg
        emoji = "🌪️" if weather == "sand" else "❄️"
        w_name = weather_info.get(weather, ("", weather))[1]
        log.append(f"  {emoji} {p.name} recibe {dmg} daño por {w_name}.\n")
        return delta, log

    def _calc_grassy(p: ResidualParticipant) -> tuple[int, list]:
        """Campo de Hierba: cura 1/16 si está vivo y no está lleno."""
        log: list = []
        if terrain != "grassy" or p.hp_actual <= 0 or p.hp_actual >= p.hp_max:
            return 0, log
        cure = max(1, int(p.hp_max * grassy_terrain_heal))
        log.append(f"  🌿 {p.name} recupera {cure} HP por el Campo de Hierba.\n")
        return cure, log

    # ── Calcular lado a lado ──────────────────────────────────────────────────
    fx_a = _calc_status(side_a)
    fx_b = _calc_status(side_b)

    # Clima
    w_delta_a, w_log_a = _calc_weather(side_a)
    w_delta_b, w_log_b = _calc_weather(side_b)
    fx_a.hp_delta += w_delta_a
    fx_b.hp_delta += w_delta_b
    fx_a.log.extend(w_log_a)
    fx_b.log.extend(w_log_b)

    # Campo de Hierba
    g_delta_a, g_log_a = _calc_grassy(side_a)
    g_delta_b, g_log_b = _calc_grassy(side_b)
    fx_a.hp_delta += g_delta_a
    fx_b.hp_delta += g_delta_b
    fx_a.log.extend(g_log_a)
    fx_b.log.extend(g_log_b)

    return ResidualResult(side_a=fx_a, side_b=fx_b, log=[])

# ── Efectos de movimientos de estado ─────────────────────────────────────────
# Formato por entrada:
#   "stages"  : [(target, stat, delta), ...]   target: "self" | "foe"
#   "ailment" : "par" | "brn" | "frz" | "slp" | "psn" | "tox"
#   "heal"    : float  (fracción del HP máx, ej. 0.5)
#   "yawn"    : True
MOVE_EFFECTS: dict = {
    # ── Bajan stat del rival ─────────────────────────────────────────────────
    "tailwhip":       {"stages": [("foe",  "def",    -1)]},
    "growl":          {"stages": [("foe",  "atq",    -1)]},
    "screech":        {"stages": [("foe",  "def",    -2)]},
    "leer":           {"stages": [("foe",  "def",    -1)]},
    "stringshot":     {"stages": [("foe",  "vel",    -2)]},
    "charm":          {"stages": [("foe",  "atq",    -2)]},
    "featherdance":   {"stages": [("foe",  "atq",    -2)]},
    "tickle":         {"stages": [("foe",  "atq",    -1), ("foe", "def", -1)]},
    "smokescreen":    {"stages": [("foe",  "acc",    -1)]},
    "sweetscent":     {"stages": [("foe",  "acc",    -2)]},
    "flash":          {"stages": [("foe",  "acc",    -1)]},
    "kinesis":        {"stages": [("foe",  "acc",    -1)]},
    "sandattack":     {"stages": [("foe",  "acc",    -1)]},
    "cottonspore":    {"stages": [("foe",  "vel",    -2)]},
    "captivate":      {"stages": [("foe",  "atq_sp", -2)]},
    "spiritbreak":    {"stages": [("foe",  "atq_sp", -1)]},
    "mysticalfire":   {"stages": [("foe",  "atq_sp", -1)]},
    "playrough":        {},   # daño puro + 10 % de -1 Atq (secondary ailment en SECONDARY_AILMENTS)
    # ── Suben stat propio ────────────────────────────────────────────────────
    "swordsdance":    {"stages": [("self", "atq",    +2)]},
    "agility":        {"stages": [("self", "vel",    +2)]},
    "rockpolish":     {"stages": [("self", "vel",    +2)]},
    "acidarmor":      {"stages": [("self", "def",    +2)]},
    "amnesia":        {"stages": [("self", "def_sp", +2)]},
    "nastyplot":      {"stages": [("self", "atq_sp", +2)]},
    "calmmind":       {"stages": [("self", "atq_sp", +1), ("self", "def_sp", +1)]},
    "bulkup":         {"stages": [("self", "atq",    +1), ("self", "def",    +1)]},
    "growth":         {"stages": [("self", "atq",    +1), ("self", "atq_sp", +1)]},
    "sharpen":        {"stages": [("self", "atq",    +1)]},
    "defensecurl":    {"stages": [("self", "def",    +1)]},
    "harden":         {"stages": [("self", "def",    +1)]},
    "withdraw":       {"stages": [("self", "def",    +1)]},
    "meditate":       {"stages": [("self", "atq",    +1)]},
    "howl":           {"stages": [("self", "atq",    +1)]},
    "workup":         {"stages": [("self", "atq",    +1), ("self", "atq_sp", +1)]},
    "quiverdance":    {"stages": [("self", "atq_sp", +1), ("self", "def_sp", +1), ("self", "vel", +1)]},
    "dragondance":    {"stages": [("self", "atq",    +1), ("self", "vel",    +1)]},
    "shellsmash":     {"stages": [("self", "atq",    +2), ("self", "atq_sp", +2), ("self", "vel", +2),
                                  ("self", "def",    -1), ("self", "def_sp", -1)]},
    "victorydance":   {"stages": [("self", "atq",    +1), ("self", "def",    +1), ("self", "vel", +1)]},
    "coil":           {"stages": [("self", "atq",    +1), ("self", "def",    +1)]},
    "irondefense":    {"stages": [("self", "def",    +2)]},
    "cosmicpower":    {"stages": [("self", "def",    +1), ("self", "def_sp", +1)]},
    "stockpile":      {"stages": [("self", "def",    +1), ("self", "def_sp", +1)]},
    "minimize":       {"stages": [("self", "acc",    +2)]},
    "doubleteam":     {"stages": [("self", "acc",    +1)]},
    "barrier":        {"stages": [("self", "def",    +2)]},
    "flatter":        {"stages": [("foe", "atq_sp", +1)], "ailment": "cnf"},
    "swagger":        {"stages": [("foe", "atq", +2)], "ailment": "cnf"},
    "honeclaws":      {"stages": [("self", "atq",    +1)]},
    "geomancy":       {"stages": [("self", "atq_sp", +2), ("self", "def_sp", +2), ("self", "vel", +2)]},
    # ── Modificadores de golpe crítico ────────────────────────────────────────
    "focusenergy":    {"crit_stage": ("self", +2)},   # Concentración
    "laserfocus":     {"crit_stage": ("self", +2)},   # Laser Focus (garantiza crit siguiente turno, simplificamos a +2)
    "scopelens":      {"crit_stage": ("self", +1)},   # Ítem — si se trackea equipado
    "razorclaw":      {"crit_stage": ("self", +1)},   # Ítem
    # Movimientos de alta probabilidad de crítico (ratio elevado en los juegos)
    # Se modelan como +1 al calcular el daño (ver execute_move)
    # "slash", "crabhammer", "karatechop", "razorwind", "aeroblast", "crosschop"
    # → se manejan en _HIGH_CRIT_MOVES más abajo, no aquí
    # ── Ailments directos ────────────────────────────────────────────────────
    "confuseray":     {"ailment": "cnf"},
    "supersonic":     {"ailment": "cnf"},
    "dynamicpunch":   {},   # se maneja como secondary ailment
    "stomp":          {},
    "thunderwave":    {"ailment": "par"},
    "glare":          {"ailment": "par"},
    "stunspore":      {"ailment": "par"},
    "toxic":          {"ailment": "tox"},
    "poisonpowder":   {"ailment": "psn"},
    "poisongas":      {"ailment": "psn"},
    "willowisp":      {"ailment": "brn"},
    "sleeppowder":    {"ailment": "slp"},
    "hypnosis":       {"ailment": "slp"},
    "lovelykiss":     {"ailment": "slp"},
    "sing":           {"ailment": "slp"},
    "spore":          {"ailment": "slp"},
    "darkvoid":       {"ailment": "slp"},
    "grasswhistle":   {"ailment": "slp"},
    "yawn":           {"yawn": True},
    "leechseed":      {"leechseed": True},
    # ── Curación propia ──────────────────────────────────────────────────────
    "recover":        {"heal": 0.50},
    "softboiled":     {"heal": 0.50},
    "milkdrink":      {"heal": 0.50},
    "slackoff":       {"heal": 0.50},
    "roost":          {"heal": 0.50},
    "moonlight":      {"heal": 0.50},
    "morningsun":     {"heal": 0.50},
    "synthesis":      {"heal": 0.50},
    "healorder":      {"heal": 0.50},
    "shoreup":        {"heal": 0.50},
    "lifedew":        {"heal": 0.25},
    "rest":           {"heal": 1.00, "ailment": "slp"},
    # ── Clima ─────────────────────────────────────────────────────────────────
    "sunnyday":       {"weather": ("sun",  5)},
    "raindance":      {"weather": ("rain", 5)},
    "sandstorm":      {"weather": ("sand", 5)},
    "snowscape":      {"weather": ("snow", 5)},
    "hail":           {"weather": ("snow", 5)},   # alias antiguo → nevada en Gen 9
    "fog":            {"weather": ("fog",  5)},
    # ── Terreno ───────────────────────────────────────────────────────────────
    "electricterrain": {"terrain": ("electric", 5)},
    "grassyterrain":   {"terrain": ("grassy",   5)},
    "mistyterrain":    {"terrain": ("misty",    5)},
    "psychicterrain":  {"terrain": ("psychic",  5)},
    # ── Salas ─────────────────────────────────────────────────────────────────
    "trickroom":      {"room": "trick_room"},
    "gravity":        {"room": "gravity"},
    "magicroom":      {"room": "magic_room"},
    "wonderroom":     {"room": "wonder_room"},
    # ── Neblina (resetea etapas) ──────────────────────────────────────────────
    "haze":           {"haze": True},
    # ── Huida / Teletransporte ────────────────────────────────────────────────
    "teleport":       {"flee": True},           # huida garantizada Gen 1–7; 
                                                # en Gen 8+ cambia de Pokémon activo
                                                # aquí lo tratamos como huida 100%
    "uturn":          {"pivot": True},          # daño → jugador elige reemplazo
    "voltswitch":     {"pivot": True},
    "flipturn":       {"pivot": True},
    "partingshot":    {"pivot": True, "stages": [("foe", "atq", -1), ("foe", "atq_sp", -1)]},
    # ── Switch forzado (salvaje obliga al rival a cambiar) ────────────────────
    "whirlwind":      {"forced_switch": True},
    "roar":           {"forced_switch": True},
    "circlethrow":    {"forced_switch": True},   # daño + fuerza switch
    "dragontail":     {"forced_switch": True},   # daño + fuerza switch
    # ── Trampa (impide huir al rival) ─────────────────────────────────────────
    "meanlook":       {"trap": True},
    "block":          {"trap": True},
    "spiderweb":      {"trap": True},
    # ── Transformar ───────────────────────────────────────────────────────────
    "transform":      {"transform": True},
    # ── Intercambio de stats (Wonder Room simplificado) ───────────────────────
}

# Efectos secundarios en movimientos de daño: move_key → (ailment, chance_%)
SECONDARY_AILMENTS: dict = {
    "flamethrower":   ("brn", 10),
    "fireblast":      ("brn", 10),
    "flamewheel":     ("brn", 10),
    "lavaplume":      ("brn", 30),
    "scald":          ("brn", 30),
    "steameruption":  ("brn", 30),
    "flareblitz":     ("brn", 10),
    "firepunch":      ("brn", 10),
    "sacredfire":     ("brn", 50),
    "blueflare":      ("brn", 20),
    "thunderbolt":    ("par", 10),
    "thunder":        ("par", 30),
    "thunderpunch":   ("par", 10),
    "zapcannon":      ("par", 100),
    "nuzzle":         ("par", 100),
    "discharge":      ("par", 30),
    "spark":          ("par", 30),
    "volttackle":     ("par", 10),
    "icebeam":        ("frz", 10),
    "blizzard":       ("frz", 10),
    "icepunch":       ("frz", 10),
    "powdersnow":     ("frz", 10),
    "freezedry":      ("frz", 10),
    "sludge":         ("psn", 30),
    "sludgebomb":     ("psn", 30),
    "poisonjab":      ("psn", 30),
    "poisonsting":    ("psn", 30),
    "poisontail":     ("psn", 10),
    "gunkshot":       ("psn", 30),
    "mortalspin":     ("psn", 100),
    "twineedle":      ("psn", 20),
    "bodyslam":       ("par", 30),
    "lick":           ("par", 30),
    "playrough":  ("atq_stage_foe_-1", 10),   # 10 % baja Atk del rival
}

# Movimientos de drenaje: move_key → fracción del daño que recupera el atacante
DRAIN_MOVES: dict = {
    "absorb":           0.50,
    "megadrain":        0.50,
    "gigadrain":        0.50,
    "leechlife":        0.50,
    "drainingkiss":     0.75,
    "hornleech":        0.50,
    "oblivionwing":     0.75,
    "paraboliccharge":  0.50,
    "strengthsap":      0.50,
    "drainpunch":       0.50,
    "gastroacid":       0.50,  # nope — es estado; se queda por compatibilidad
    # Gen 9
    "trailblaze":       0.00,  # no drena, está aquí solo para referencia
}
# Drain real solo los que tienen ratio > 0
DRAIN_MOVES = {k: v for k, v in DRAIN_MOVES.items() if v > 0}

# Movimientos con retroceso: move_key → fracción del daño que recibe el atacante
RECOIL_MOVES: dict = {
    "bravebird":   0.33,
    "doubleedge":  0.33,
    "flareblitz":  0.33,
    "volttackle":  0.33,
    "headsmash":   0.50,
    "submission":  0.25,
    "takedown":    0.25,
    "wildcharge":  0.25,
}
RECOIL_MOVES = {k: v for k, v in RECOIL_MOVES.items() if v > 0}

# Movimientos de puño (para Puño de Hierro / Iron Fist)
_PUNCH_MOVES: frozenset[str] = frozenset({
    "icepunch", "firepunch", "thunderpunch", "focuspunch", "drainpunch",
    "bulletpunch", "shadowpunch", "hammerarm", "megapunch", "corebuster",
    "meteormash", "poweruppunch", "plasmafists", "surgingstrikes",
    "doubleironbash", "wickedblow", "cometpunch",
})

# Movimientos de contacto (para Garras Duras / Tough Claws)
# Lista de los más comunes; los ranged/indirect NO están aquí.
_CONTACT_MOVES: frozenset[str] = frozenset({
    "tackle", "scratch", "slash", "bite", "crunch", "bodyslam", "doubleedge",
    "takedown", "headbutt", "return", "frustration", "aquatail", "waterfall",
    "leafblade", "woodhammer", "swordsdance",  # no, swords dance no hace daño
    "outrage", "dracometeor", "dragonclaw", "dragontail", "extremespeed",
    "quickattack", "shadowsneak", "shadowclaw", "nightslash", "bravebird",
    "flareblitz", "volttackle", "wildcharge", "closecombat", "highjumpkick",
    "jumpkick", "karatechop", "lowkick", "superpower", "armthrust",
    "bulletpunch", "icepunch", "firepunch", "thunderpunch", "focuspunch",
    "drainpunch", "hammerarm", "vcreate", "xscissor", "bugbite", "uturn",
    "poisonjab", "gunkshot", "crosspoison", "aquajet", "icebeam",  # no, ranged
    "poisonfang", "suckerpunch", "payback", "pursuit", "knockoff",
    "stoneedge",  # no, ranged; quitar si se necesita precisión
    "ironhead", "meteormash", "gyroball", "heavyslam", "heatcrash",
    "bodypress", "playrough", "dazzlinggleam",  # no, ranged
    "flipturn", "liquidation", "wavecrash", "aquastep",
    "acrobatics", "aerialace", "bravebird", "wingattack",
    "crunch", "bite", "hyperspace",
    # Movimientos de contacto para Garras Duras (Gen 9)
    "ragefist", "wringout", "stompingtantrum", "bulldoze",
    "doublekick", "triplekick", "tripleaxel",
})

def calcular_mult_habilidad(
    hab_raw:    str,
    mk:         str,       # move key normalizado (minúsculas, sin espacios)
    tipo_mv:    str,       # tipo del movimiento en español
    categoria:  str,       # "Físico" | "Especial" | "Estado"
    poder:      int,
    hp_ratio:   float = 1.0,   # hp_actual / hp_max del atacante
) -> tuple[float, bool]:
    """
    Retorna (multiplicador_poder, quitar_efecto_secundario).

    El multiplicador se aplica sobre `move_power` ANTES de llamar a
    resolve_damage_move.  quitar_efecto_secundario=True indica Fuerza Bruta.
    """
    if not hab_raw or poder <= 0:
        return 1.0, False

    hab = hab_raw.lower().replace(" ", "").replace("-", "")

    # ── Técnico / Technician: 1.5× si poder base ≤ 60 ──────────────────────
    if hab in ("tecnico", "technician") and 0 < poder <= 60:
        return 1.5, False

    # ── Puño de Hierro / Iron Fist: 1.2× en movimientos de puño ────────────
    if hab in ("punodehierro", "ironfist") and mk in _PUNCH_MOVES:
        return 1.2, False

    # ── Fuerza Bruta / Sheer Force: 1.3× si el move tiene efecto secundario ─
    # Quita el efecto secundario para compensar el boost.
    if hab in ("fuerzabruta", "sheerforce"):
        tiene_secundario = (
            mk in SECONDARY_AILMENTS
            or mk in SECONDARY_SELF_STAT_DROPS
            or bool(MOVE_EFFECTS.get(mk, {}).get("ailment"))
            or bool(MOVE_EFFECTS.get(mk, {}).get("stages"))
        )
        if tiene_secundario:
            return 1.3, True

    # ── Garras Duras / Tough Claws: 1.3× en movimientos de contacto ─────────
    if hab in ("garrasduras", "toughclaws") and mk in _CONTACT_MOVES:
        return 1.3, False

    # ── Metalúrgico / Steelworker: 1.5× en movimientos de tipo Acero ────────
    if hab in ("metalurgico", "steelworker") and tipo_mv == "Acero":
        return 1.5, False

    # ── Transistor: 1.5× en movimientos de tipo Eléctrico ───────────────────
    if hab == "transistor" and tipo_mv == "Eléctrico":
        return 1.5, False

    # ── Mandíbula Dragón / Dragon's Maw: 1.5× en tipo Dragón ────────────────
    if hab in ("mandibuladedragon", "mandíbuladedragon", "dragonsmaw") and tipo_mv == "Dragón":
        return 1.5, False

    # ── Llamarada / Blaze (≤1/3 HP): 1.5× Fuego ────────────────────────────
    if hp_ratio <= 1 / 3:
        _HP_ABI: dict[str, str] = {
            "llamarada": "Fuego",  "blaze": "Fuego",
            "torrente":  "Agua",   "torrent": "Agua",
            "espesura":  "Planta", "overgrow": "Planta",
            "enjambre":  "Bicho",  "swarm": "Bicho",
        }
        if hab in _HP_ABI and tipo_mv == _HP_ABI[hab]:
            return 1.5, False

    # ── Temerario / Reckless: 1.2× en movimientos con retroceso ─────────────
    if hab in ("temerario", "reckless") and mk in RECOIL_MOVES:
        return 1.2, False

    # ── Flecha de Lava / Liquid Ooze y Pureza Suprema: no afectan daño ──────

    return 1.0, False


# ─────────────────────────────────────────────────────────────────────────────
# TABLA DE PESOS (kg) por pokemonID — usada por Low Kick y Heavy Slam/Heat Crash
# Solo se incluyen los más comunes; los que no aparecen usan un valor
# genérico de 40 kg (rango medio en la fórmula oficial).
# ─────────────────────────────────────────────────────────────────────────────
_PESOS_POKEMON: dict[int, float] = {
    # Gen 1
    1: 6.9,   2: 13.0,  3: 100.0, 4: 8.5,   5: 19.0,  6: 90.5,
    7: 9.0,   8: 22.5,  9: 85.5,  10: 2.9,  11: 9.9,  12: 32.0,
    13: 3.4,  14: 10.0, 15: 65.0, 16: 1.8,  17: 30.0, 18: 39.5,
    19: 3.5,  20: 18.5, 25: 6.0,  26: 30.0, 39: 10.0, 40: 40.0,
    52: 4.2,  53: 32.0, 74: 20.0, 75: 105.0,76: 400.0,
    79: 36.0, 80: 175.0,81: 5.5,  82: 60.0, 95: 210.0,96: 36.0,
    97: 76.5, 104:6.5,  105:45.0, 106:50.6, 107:50.2, 108:115.0,
    109:1.0,  110:9.5,  111:100.0,112:180.0,113:76.0, 114:3.3,
    115:80.0, 116:0.9,  117:8.0,  118:15.0, 119:39.0, 120:76.0,
    121:80.0, 122:28.0, 123:56.0, 124:48.0, 125:30.0, 126:28.0,
    127:55.0, 128:88.4, 129:10.0, 130:235.0,131:220.0,132:4.0,
    133:6.5,  134:29.0, 135:24.5, 136:25.0, 137:36.5, 138:35.0,
    139:77.5, 140:40.0, 141:25.0, 142:59.0, 143:460.0,144:55.4,
    145:52.6, 146:60.0, 147:2.1,  148:16.5, 149:210.0,150:122.0,
    # Gen 2
    152:9.0,  153:13.0, 154:70.0, 155:7.9,  156:19.0, 157:79.5,
    158:8.8,  159:17.0, 160:87.0, 161:5.0,  162:24.5, 163:2.1,
    164:21.2, 172:2.0,  173:8.8,  174:13.2, 175:4.3,  176:28.0,
    179:13.3, 180:41.5, 181:121.0,183:9.0,  184:65.0, 185:35.0,
    186:78.5, 194:29.0, 195:75.0, 196:26.5, 197:27.0, 199:79.5,
    200:1.5,  201:4.8,  202:33.3, 206:31.5, 213:77.0, 214:120.0,
    215:28.0, 216:19.6, 217:125.0,241:275.0,242:45.5, 243:178.0,
    244:198.0,245:187.0,248:202.0,249:216.0,250:199.0,
    # Gen 3 (selección)
    258:7.8,  259:19.0, 260:101.6,277:30.4, 279:23.8, 282:48.4,
    289:25.0, 290:2.5,  291:3.4,  292:1.2,  294:24.9, 295:39.5,
    302:1.8,  303:14.3, 306:640.0,315:5.6,  319:48.5, 323:220.0,
    324:360.0,330:97.5, 334:19.0, 335:35.0, 336:69.5, 337:168.0,
    338:163.0,344:11.5, 348:141.0,350:96.4, 351:4.0,  352:28.0,
    357:11.5, 358:51.4, 359:46.4, 362:98.8, 368:14.4, 373:110.0,
    374:60.0, 375:97.0, 376:600.0,377:280.0,378:267.0,379:346.0,
    382:352.0,383:950.0,384:206.5,385:1.1,  386:30.8,
    # Gen 4 (selección)
    398:26.0, 400:27.0, 401:2.5,  402:6.4,  411:72.5, 423:29.5,
    424:12.5, 427:17.0, 428:55.0, 445:95.0, 446:12.8, 448:64.0,
    453:3.4,  454:53.5, 460:296.0,461:56.8, 464:282.8,465:71.0,
    466:138.0,467:37.5, 469:52.0, 471:25.9, 473:450.5,474:30.5,
    476:30.0, 477:47.5, 478:30.5, 479:3.0,  480:0.3,  481:0.3,
    482:0.3,  483:683.0,484:336.0,485:430.0,486:420.0,487:750.0,
    # Gen 5 (selección)
    495:8.1,  496:24.5, 497:63.0, 501:13.7, 502:36.0, 503:63.5,
    519:2.1,  520:3.0,  521:17.5, 559:9.3,  560:34.0, 561:12.5,
    554:9.4,  555:33.0, 596:3.5,  597:6.6,  598:50.5, 612:50.5,
    614:100.0,618:11.5, 620:34.0, 621:80.0, 622:44.5, 623:248.0,
    624:18.8, 625:73.0, 631:3.0,  632:58.5, 633:17.3, 634:50.0,
    635:160.0,638:300.0,639:187.5,640:52.5, 641:63.0, 642:61.0,
    643:249.5,644:345.0,646:325.0,
    # Gen 6 (selección)
    650:8.2,  651:22.0, 652:78.5, 654:11.5, 655:38.5, 656:7.0,
    657:17.5, 658:62.0, 699:26.0, 700:23.5, 701:54.0, 702:8.0,
    703:6.8,  704:7.5,  706:88.0, 707:12.8, 710:0.5,  711:5.0,
    712:0.8,  713:131.0,716:215.0,717:203.0,718:305.0,
    # Gen 7 (selección)
    722:2.6,  723:11.0, 724:29.5, 725:4.4,  726:19.0, 727:90.0,
    728:7.0,  729:44.0, 730:98.0, 741:13.2, 750:100.0,751:0.8,
    752:17.5, 753:0.8,  754:15.5, 770:1.0,  771:16.0, 774:0.3,
    775:50.0, 776:10.0, 777:0.6,  779:8.0,  781:33.0, 782:7.8,
    783:22.0, 784:120.5,785:18.5, 786:19.4, 787:14.5, 788:15.5,
    791:230.0,792:120.0,793:4.0,  800:230.0,
    # Gen 8 (selección)
    813:11.0, 814:21.0, 815:64.0, 816:9.5,  817:17.5, 818:101.0,
    819:2.0,  820:32.0, 821:1.5,  822:6.0,  823:75.0, 831:6.0,
    832:92.5, 833:11.5, 834:115.0,835:3.0,  836:14.0, 837:6.5,
    838:132.0,839:698.0,840:0.2,  841:2.0,  842:65.0, 843:30.0,
    844:210.0,845:10.0, 847:100.0,849:17.0, 850:2.0,  851:10.0,
    858:57.5, 860:2.1,  861:2.5,  862:157.5,863:92.0, 864:1.0,
    867:0.5,  869:0.5,  873:20.0, 874:40.0, 879:880.0,880:792.0,
    881:236.0,882:246.0,883:242.0,884:255.0,886:10.2, 887:92.0,
    888:110.0,889:130.0,890:950.0,892:97.5,
    # Gen 9 (selección)
    906:10.2, 907:29.2, 908:60.0, 909:15.8, 910:56.0, 911:112.0,
    912:2.7,  913:52.0, 916:48.0, 917:35.0, 918:160.0,920:9.1,
    921:3.1,  922:2.1,  923:33.0, 924:1.4,  925:75.0, 926:52.0,
    927:15.4, 928:12.0, 929:1.7,  930:2.9,  931:6.2,  932:110.0,
    935:6.0,  936:37.0, 937:2.8,  938:10.4, 941:0.2,  942:1.6,
    943:8.5,  944:1.5,  945:3.7,  946:28.0, 947:11.0, 948:0.6,
    949:15.0, 950:1.0,  951:1.0,  952:3.5,  953:9.1,  954:18.2,
    955:0.9,  956:6.5,  957:11.2, 958:49.0, 959:50.5, 960:115.0,
    961:9.0,  962:34.5, 963:6.5,  964:14.0, 965:33.8, 966:70.0,
    967:3.0,  968:1.0,  969:27.0, 970:0.5,  971:7.0,  972:45.0,
    1001:72.0,1002:320.0,1003:122.0,1004:62.0,1007:303.0,1008:1054.0,
}
_PESO_GENERICO: float = 40.0   # fallback si el ID no está en la tabla


def get_peso_pokemon(pokemon_id: int) -> float:
    """Devuelve el peso en kg del Pokémon. Usa 40 kg como fallback."""
    return _PESOS_POKEMON.get(pokemon_id, _PESO_GENERICO)


def calcular_poder_lowkick(peso_defensor_kg: float) -> int:
    """
    Poder de Low Kick / Grass Knot según el peso del defensor (fórmula oficial).
      < 10 kg  → 20
      < 25 kg  → 40
      < 50 kg  → 60
      < 100 kg → 80
      < 200 kg → 100
      ≥ 200 kg → 120
    """
    if peso_defensor_kg < 10:   return 20
    if peso_defensor_kg < 25:   return 40
    if peso_defensor_kg < 50:   return 60
    if peso_defensor_kg < 100:  return 80
    if peso_defensor_kg < 200:  return 100
    return 120


def calcular_poder_heavyslam(peso_atacante_kg: float, peso_defensor_kg: float) -> int:
    """
    Poder de Heavy Slam / Heat Crash según la relación de pesos (fórmula oficial).
    ratio = peso_atacante / peso_defensor
      ≥ 5   → 120
      ≥ 4   → 100
      ≥ 3   → 80
      ≥ 2   → 60
      < 2   → 40
    """
    if peso_defensor_kg <= 0:
        return 40
    ratio = peso_atacante_kg / peso_defensor_kg
    if ratio >= 5: return 120
    if ratio >= 4: return 100
    if ratio >= 3: return 80
    if ratio >= 2: return 60
    return 40


# Movimientos cuyo poder depende del peso del defensor
_LOWKICK_MOVES:    frozenset[str] = frozenset({"lowkick", "grassknot"})
# Movimientos cuyo poder depende de la relación de pesos atacante/defensor
_HEAVYSLAM_MOVES:  frozenset[str] = frozenset({"heavyslam", "heatcrash"})

# ─────────────────────────────────────────────────────────────────────────────
# MAGIC GUARD — habilidades que anulan daño indirecto
# ─────────────────────────────────────────────────────────────────────────────
_MAGIC_GUARD_ALIASES: frozenset[str] = frozenset({
    "magicguard", "guardiamágica", "guardiamagica", "magicguard",
})


def tiene_magic_guard(ability_raw: str) -> bool:
    """True si la habilidad es Magic Guard (inmune a daño indirecto)."""
    if not ability_raw:
        return False
    return ability_raw.lower().replace(" ", "").replace("-", "") in _MAGIC_GUARD_ALIASES

# Potenciadores de tipo: {item_key_normalizado: tipo_en_español}
_TIPO_BOOST_ITEMS: dict[str, str] = {
    "silkscarf":       "Normal",
    "charcoal":        "Fuego",
    "carbon":          "Fuego",
    "mysticwater":     "Agua",
    "aguamistetica":   "Agua",   # nombre alternativo español
    "magnet":          "Eléctrico",
    "iman":            "Eléctrico",
    "miracleseed":     "Planta",
    "semillamilagro":  "Planta",
    "nevermeltice":    "Hielo",
    "antiderretir":    "Hielo",
    "blackbelt":       "Lucha",
    "cinturnegro":     "Lucha",
    "poisonbarb":      "Veneno",
    "flechavenenosa":  "Veneno",
    "softsand":        "Tierra",
    "arenafina":       "Tierra",
    "sharpbeak":       "Volador",
    "picoafilado":     "Volador",
    "twistedspoon":    "Psíquico",
    "cucharatorcida":  "Psíquico",
    "silverpowder":    "Bicho",
    "polvoplata":      "Bicho",
    "hardstone":       "Roca",
    "pEDRAdura":       "Roca",
    "piedradura":      "Roca",
    "spelltag":        "Fantasma",
    "hechizo":         "Fantasma",
    "dragonfang":      "Dragón",
    "colmillodragon":  "Dragón",
    "blackglasses":    "Siniestro",
    "gafasdesol":      "Siniestro",
    "metalcoat":       "Acero",
    "revestimientometalico": "Acero",
    "fairyfeather":    "Hada",
    "plumahada":       "Hada",
    # Inciensos que también potencian tipo
    "oddincense":      "Psíquico",
    "inciensoRaro":    "Psíquico",
    "inciensoRaro":    "Psíquico",
    "rockincense":     "Roca",
    "inciensoRoca":    "Roca",
    "roseincense":     "Planta",
    "inciensoFlor":    "Planta",
    "seaincense":      "Agua",
    "inciensoMarino":  "Agua",
    "waveincense":     "Agua",
}

def calcular_mult_objeto(
    obj_raw:   str,
    tipo_mv:   str,
    categoria: str,
    type_eff:  float = 1.0,   # efectividad de tipo, para Cinto Experto
) -> tuple[float, float]:
    """
    Retorna (multiplicador_poder, recoil_ratio_hp_max).

    multiplicador_poder   → se aplica sobre move_power antes de calcular daño.
    recoil_ratio_hp_max   → fracción del HP MÁXIMO del portador que pierde
                            después del ataque (solo Life Orb: 0.1).
    """
    if not obj_raw:
        return 1.0, 0.0

    obj = obj_raw.lower().replace(" ", "").replace("-", "").replace("_", "")

    # ── Vida Esfera / Life Orb: 1.3×, recoil 10% HP max ────────────────────
    if obj in ("vidasfera", "lifeorb"):
        return 1.3, 0.1

    # ── Elección ─────────────────────────────────────────────────────────────
    # Choice Band → solo Físico
    if obj in ("cintaeleccion", "cintatornado", "choiceband"):
        if categoria == "Físico":
            return 1.5, 0.0

    # Choice Specs → solo Especial
    if obj in ("gafaseleccion", "choicespecs"):
        if categoria == "Especial":
            return 1.5, 0.0

    # ── Cinto Experto / Expert Belt: 1.2× solo si es muy efectivo ───────────
    if obj in ("cintoexperto", "expertbelt") and type_eff > 1.0:
        return 1.2, 0.0

    # ── Potenciadores de tipo: 1.2× ──────────────────────────────────────────
    _boost_tipo = _TIPO_BOOST_ITEMS.get(obj)
    if _boost_tipo and _boost_tipo == tipo_mv:
        return 1.2, 0.0

    return 1.0, 0.0

# Movimientos que debilitan al USUARIO después de ejecutarse
SELF_KO_MOVES: frozenset[str] = frozenset({
    "explosion",
    "selfdestruct",
    "mistyexplosion",
})

# Movimientos que bajan stat del ATACANTE tras hacer daño (solo si daño > 0).
# Formato: move_key → [(stat, delta), ...]  — target siempre es "self".
SECONDARY_SELF_STAT_DROPS: dict[str, list] = {
    "hammerarm":   [("vel",    -1)],
    "superpower":  [("atq",    -1), ("def",    -1)],
    "closecombat": [("def",    -1), ("def_sp", -1)],
    "dracometeor": [("atq_sp", -2)],
    "leafstorm":   [("atq_sp", -2)],
    "overheat":    [("atq_sp", -2)],
    "psychoboost": [("atq_sp", -2)],
    "vcreate":     [("vel",    -1), ("def",    -1), ("def_sp", -1)],
}

MULTI_HIT_MOVES: dict[str, tuple[int, int]] = {
    # 2 golpes exactos
    "doubleslap":      (2, 2),
    "doublekick":      (2, 2),
    "doublehit":       (2, 2),
    "twineedle":       (2, 2),
    "bonemerang":      (2, 2),
    "doubleironfist":  (2, 2),
    # 3 golpes exactos
    "triplekick":      (3, 3),   # el poder se incrementa por golpe (25/50/75) —
    "tripleaxel":      (3, 3),   # lo mismo que Triple Kick
    "tripledive":      (3, 3),
    "surgingstrikes":  (3, 3),   # siempre 3 y siempre crítico
    # 2–5 golpes (distribución Gen 5+: 35.2 / 35.2 / 14.8 / 14.8 %)
    "furyattack":      (2, 5),
    "furyswipes":      (2, 5),
    "spikecannon":     (2, 5),
    "barrage":         (2, 5),
    "cometpunch":      (2, 5),
    "armthrust":       (2, 5),
    "bulletseed":      (2, 5),
    "rockblast":       (2, 5),
    "tailslap":        (2, 5),
    "watershuriken":   (2, 5),
    "bonerush":        (2, 5),
    "populationbomb":  (1, 10),  # Skill Link lo lleva a 10
    # ── Movimientos añadidos ─────────────────────────────────────────────────
    "dualwingbeat":    (2, 2),   # Ala Bis
    "dualchop":        (2, 2),   # Golpe Bis
    "geargrind":       (2, 2),   # Piñón Auxilio
    "iciclespear":     (2, 5),   # Carámbano
    "pinmissile":      (2, 5),   # Lanzapin
    "scaleshot":       (2, 5),   # Escama
}

TRAPPING_MOVES: dict[str, dict] = {
    "wrap":        {"turns": (4, 5), "dmg_ratio": 1 / 8, "nombre_es": "Constricción"},
    "firespin":    {"turns": (4, 5), "dmg_ratio": 1 / 8, "nombre_es": "Rueda de Fuego"},
    "whirlpool":   {"turns": (4, 5), "dmg_ratio": 1 / 8, "nombre_es": "Torbellino"},
    "clamp":       {"turns": (4, 5), "dmg_ratio": 1 / 8, "nombre_es": "Cangrejación"},
    "sandtomb":    {"turns": (4, 5), "dmg_ratio": 1 / 8, "nombre_es": "Tumba de Arena"},
    "magmastorm":  {"turns": (4, 5), "dmg_ratio": 1 / 8, "nombre_es": "Tormenta de Magma"},
    "infestation": {"turns": (4, 5), "dmg_ratio": 1 / 8, "nombre_es": "Infestación"},
    "snaptrap":    {"turns": (4, 5), "dmg_ratio": 1 / 8, "nombre_es": "Trampa de Cepo"},
    "thundercage": {"turns": (4, 5), "dmg_ratio": 1 / 8, "nombre_es": "Jaula Eléctrica"},
}

TRAPPING_ABILITIES: frozenset[str] = frozenset({
    "Sombra Trampa",   # Shadow Tag  — bloquea a cualquier rival que no tenga
                       #               la misma habilidad
    "Trampa Arena",    # Arena Trap  — bloquea a Pokémon no voladores (no volador,
                       #               no Levitación, no tipo Fantasma)
})

MOVE_NAMES_ES: dict = {
    # ── A ────────────────────────────────────────────────────────────────────
    "absorb":               "Absorber",
    "accelerock":           "Roca Veloz",
    "acid":                 "Ácido",
    "acidarmor":            "Armadura Ácida",
    "acidmalic":            "Ácido Málico",
    "acidspray":            "Bomba Ácida",
    "acrobatics":           "Acrobacia",
    "acupressure":          "Acupresión",
    "aerialace":            "Golpe Aéreo",
    "aeroblast":            "Aerochorro",
    "aircutter":            "Aire Afilado",
    "airslash":             "Tajo Aéreo",
    "agility":              "Agilidad",
    "allyswitch":           "Cambio Aliado",
    "anchorshot":           "Anclaje",
    "ancientpower":         "Poder Pasado",
    "appleacid":            "Ácido Málico",
    "aquacutter":           "Tajo Acuático",
    "aquajet":              "Acua Jet",
    "aquaring":             "Acua Aro",
    "aquastep":             "Danza Acuática",
    "aquatail":             "Acua Cola",
    "armorcannon":          "Cañón Coraza",
    "aromatherapy":         "Aromaterapia",
    "aromaticmist":         "Niebla Aromática",
    "assist":               "Ayuda",
    "assurance":            "Buena Baza",
    "astonish":             "Impresionar",
    "attackorder":          "Al Ataque",
    "attract":              "Atracción",
    "aurasphere":           "Esfera Aural",
    "aurawheel":            "Rueda Aural",
    "aurorabeam":           "Rayo Aurora",
    "auroraveil":           "Velo Aurora",
    "autotomize":           "Autotomía",
    "avalanche":            "Alud",
    "axekick":              "Patada Hacha",
    # ── B ────────────────────────────────────────────────────────────────────
    "babydolleyes":         "Ojos Tiernos",
    "baddybad":             "Vaho Espectral",
    "banefulbunker":        "Refugio Nocivo",
    "barbbarrage":          "Bombardeo Espinas",
    "barrage":              "Presa",
    "barrier":              "Barrera",
    "batonpass":            "Relevo",
    "beakblast":            "Pico Cañón",
    "beatup":               "Paliza",
    "behemothbash":         "Embate Dinamax",
    "behemothblade":        "Tajo Supremo",
    "belch":                "Eructo",
    "bellydrum":            "Tambor",
    "bestow":               "Ofrenda",
    "bide":                 "Venganza",
    "bind":                 "Atadura",
    "bite":                 "Mordisco",
    "bittermalice":         "Rencor",
    "blastburn":            "Anillo Ígneo",
    "blazekick":            "Patada Ígnea",
    "blazingtorque":        "Pirochoque",
    "blizzard":             "Ventisca",
    "block":                "Bloqueo",
    "bloomdoom":            "Megatón Floral",
    "blueflare":            "Llama Azul",
    "bodypress":            "Plancha Corporal",
    "bodyslam":             "Golpe Cuerpo",
    "boltbeak":             "Pico Voltio",
    "boltstrike":           "Ataque Fulgor",
    "bonemerang":           "Huesomerang",
    "bonerush":             "Ataque Óseo",
    "boomburst":            "Estruendo",
    "bounce":               "Bote",
    "bravebird":            "Pájaro Osado",
    "breakingswipe":        "Vasto Impacto",
    "brickbreak":           "Demolición",
    "brine":                "Salmuera",
    "bubble":               "Burbuja",
    "bubblebeam":           "Rayo Burbuja",
    "bugbite":              "Picadura",
    "bugbuzz":              "Zumbido",
    "bulkup":               "Corpulencia",
    "bulldoze":             "Terratemblor",
    "bulletpunch":          "Puño Bala",
    "bulletseed":           "Recurrente",
    "burningjealousy":      "Envidia Ardiente",
    "burningbulwark":       "Baluarte Ígneo",
    # ── C ────────────────────────────────────────────────────────────────────
    "calmmind":             "Paz Mental",
    "camouflage":           "Camuflaje",
    "captivate":            "Seducción",
    "catastropika":         "Arrojo Intempestivo",
    "ceaselessedge":        "Tajo Sombrío",
    "celebrate":            "Celebración",
    "charge":               "Carga",
    "chargebeam":           "Rayo Carga",
    "charm":                "Encanto",
    "chatter":              "Parloteo",
    "chillingwater":        "Agua Fría",
    "chillyreception":      "Fría Acogida",
    "chipaway":             "Guardia Baja",
    "circlethrow":          "Tiro Vital",
    "clamp":                "Tenaza",
    "clangingscales":       "Fragor Escamas",
    "clangoroussoul":       "Estruendo Escamoso",
    "clearsmog":            "Niebla Clara",
    "closecombat":          "A Bocajarro",
    "coaching":             "Motivación",
    "coil":                 "Enrosque",
    "collisioncourse":      "Nitrochoque",
    "combattorque":         "Pujo Pugnaz",
    "cometpunch":           "Puño Cometa",
    "confide":              "Confidencia",
    "confuseray":           "Rayo Confuso",
    "confusion":            "Confusión",
    "constrict":            "Restricción",
    "conversion":           "Conversión",
    "conversion2":          "Conversión 2",
    "copycat":              "Copión",
    "coreenforcer":         "Núcleo Silogismo",
    "corrosivegas":         "Gas Corrosivo",
    "cosmicpower":          "Masa Cósmica",
    "cottonguard":          "Rizo Algodón",
    "cottonspore":          "Espora Algodón",
    "counter":              "Contraataque",
    "courtchange":          "Cambio de Cancha",
    "covet":                "Antojo",
    "crabhammer":           "Martillo Cangrejo",
    "craftyshield":         "Truco Defensa",
    "crosschop":            "Tajo Cruzado",
    "crosspoison":          "Veneno X",
    "crunch":               "Triturar",
    "crushclaw":            "Garra Brutal",
    "crushgrip":            "Agarre Férreo",
    "curse":                "Maldición",
    "cut":                  "Corte",
    # ── D ────────────────────────────────────────────────────────────────────
    "darkpulse":            "Pulso Umbrío",
    "darkvoid":             "Brecha Negra",
    "darkestlariat":        "Lariat Oscuro",
    "dazzlinggleam":        "Brillo Mágico",
    "decorate":             "Decoración",
    "defendorder":          "Al rincón",
    "defensecurl":          "Rizo Defensa",
    "defog":                "Despejar",
    "destinybond":          "Mismo Destino",
    "detect":               "Detección",
    "devastatingdrake":     "Dracoaliento Devastador",
    "dig":                  "Excavar",
    "direclaw":             "Garra Nociva",
    "disable":              "Anulación",
    "disarmingvoice":       "Voz Cautivadora",
    "discharge":            "Chispazo",
    "dive":                 "Buceo",
    "dizzypunch":           "Puño Mareo",
    "doodle":               "Grafiti",
    "doubleedge":           "Doble Filo",
    "doublehit":            "Doble Golpe",
    "doublekick":           "Doble Patada",
    "doubleironbash":       "Puño Doble",
    "doubleslap":           "Doblebofetón",
    "doubleironbash":       "Puño Doble",
    "dracometeor":          "Cometa Draco",
    "dragonascent":         "Ascenso Draco",
    "dragonbreath":         "Dragoaliento",
    "dragoncheer":          "Bramido Dragón",
    "dragonclaw":           "Garra Dragón",
    "dragondance":          "Danza Dragón",
    "dragondarts":          "Draco Flechas",
    "dragonenergy":         "Energía Dragón",
    "dragonhammer":         "Martillo Dragón",
    "dragonpulse":          "Pulso Dragón",
    "dragonrage":           "Furia Dragón",
    "dragonrush":           "Carga Dragón",
    "dragontail":           "Cola Dragón",
    "drainpunch":           "Puño Drenaje",
    "dreameater":           "Comesueños",
    "drillpeck":            "Pico Taladro",
    "drillrun":             "Taladradora",
    "drumbeating":          "Ataque de Tambor",
    "dualchop":             "Golpe Bis",
    "dualwingbeat":         "Ala Bis",
    "dynamicpunch":         "Puño Dinámico",
    # ── E ────────────────────────────────────────────────────────────────────
    "earthpower":           "Tierra Viva",
    "earthquake":           "Terremoto",
    "echovoice":            "Eco Voz",
    "eerieimpulse":         "Onda Anómala",
    "eeriespell":           "Conjuro Inquietante",
    "eggbomb":              "Bomba Huevo",
    "electricdrift":        "Electroderrape",
    "electricterrain":      "Campo Eléctrico",
    "electroball":          "Bola Voltio",
    "electroshot":          "Electroacelerador",
    "electroweb":           "Electrotela",
    "ember":                "Ascuas",
    "encore":               "Otra Vez",
    "endeavor":             "Esfuerzo",
    "endure":               "Aguante",
    "energyball":           "Energibola",
    "entrainment":          "Danza Amiga",
    "eruption":             "Erupción",
    "eternabeam":           "Rayo Infinito",
    "expandingforce":       "Vasta Fuerza",
    "explosion":            "Explosión",
    "extrasensory":         "Extrasensorial",
    "extremeevoboost":      "Novena Potencia",
    "extremespeed":         "Velocidad Extrema",
    # ── F ────────────────────────────────────────────────────────────────────
    "facade":               "Imagen",
    "fakeout":              "Sorpresa",
    "faketears":            "Llanto Fingido",
    "falsesurrender":       "Irreverencia",
    "falseswipe":           "Falsotortazo",
    "featherdance":         "Danza Pluma",
    "feint":                "Amago",
    "feintattack":          "Finta",
    "fellstinger":          "Aguijón Letal",
    "fierydance":           "Danza Llama",
    "fierywrath":           "Furia Candente",
    "filletaway":           "Filetear",
    "finalgambit":          "Sacrificio",
    "firelash":             "Látigo Ígneo",
    "firepledge":           "Voto Fuego",
    "firepunch":            "Puño Fuego",
    "firespin":             "Giro Fuego",
    "firstimpression":      "Escaramuza",
    "fissure":              "Fisura",
    "flamecharge":          "Nitrocarga",
    "flamethrower":         "Lanzallamas",
    "flamewheel":           "Rueda Fuego",
    "flareblitz":           "Envite Ígneo",
    "flash":                "Destello",
    "flashcannon":          "Foco Resplandor",
    "flatter":              "Camelo",
    "fling":                "Lanzamiento",
    "flipturn":             "Viraje",
    "floatyfall":           "Flotabofetón",
    "floralhealing":        "Cura Floral",
    "flowertrick":          "Truco Flor",
    "flowershield":         "Escudo Floral",
    "fly":                  "Vuelo",
    "flyingpress":          "Plancha Voladora",
    "focusblast":           "Onda Certera",
    "focusenergy":          "Foco Energía",
    "focuspunch":           "Puño Certero",
    "followme":             "Señuelo",
    "forcepalm":            "Palmeo",
    "foresight":            "Profecía",
    "forestscurse":         "Maldición Forestal",
    "freezedry":            "Liofilización",
    "freezeshock":          "Rayo Gélido",
    "freezingglare":        "Mirada Gélida",
    "frenzyplant":          "Planta Feroz",
    "frostbreath":          "Vaho Gélido",
    "frustration":          "Frustración",
    "furyattack":           "Ataque Furia",
    "furycutter":           "Corte Furia",
    "furyswipes":           "Arañazo Furia",
    "fusionbolt":           "Ataque Fulgor",
    "fusionflare":          "Llama Fusión",
    "futuresight":          "Premonición",
    # ── G ────────────────────────────────────────────────────────────────────
    "gastroacid":           "Bilis",
    "geargrind":            "Rueda Doble",
    "gearup":               "Piñón Auxiliar",
    "geomancy":             "Geomancia",
    "gigadrain":            "Gigadrenado",
    "gigaimpact":           "Giga Impacto",
    "gigavolttackle":       "Gigavoltio Destructor",
    "glaciallance":         "Lanza Glacial",
    "glaciate":             "Mundo Gélido",
    "glaiverush":           "Asalto Espadachín",
    "glare":                "Mirada Serpiente",
    "glitzygleam":          "Esplendor Estelar",
    "grassknot":            "Hierba Lazo",
    "grasspledge":          "Voto Planta",
    "grasswhistle":         "Silbato",
    "grassyglide":          "Fitoimpulso",
    "grassyterrain":        "Campo de Hierba",
    "gravapple":            "Fuerza G",
    "gravity":              "Gravedad",
    "growl":                "Gruñido",
    "growth":               "Desarrollo",
    "grudge":               "Rabia",
    "guardsplit":           "Isoguardia",
    "guardswap":            "Cambio Defensa",
    "guillotine":           "Guillotina",
    "gunkshot":             "Lanza Mugre",
    "gust":                 "Tornado",
    "gyroball":             "Giro Bola",
    # ── H ────────────────────────────────────────────────────────────────────
    "hail":                 "Granizo",
    "hammerarm":            "Machada",
    "happyhour":            "Hora Feliz",
    "harden":               "Fortaleza",
    "hardpress":            "Presión Total",
    "haze":                 "Niebla",
    "headbutt":             "Cabezazo",
    "headcharge":           "Ariete",
    "headlongrush":         "Arremetida",
    "headsmash":            "Testarazo",
    "healbell":             "Campana Cura",
    "healblock":            "Anticura",
    "healorder":            "Auxilio",
    "healpulse":            "Pulso Cura",
    "heartstamp":           "Arrullo",
    "heartswap":            "Cambio Almas",
    "heatcrash":            "Calor Estratosférico",
    "heatwave":             "Onda Ígnea",
    "heavyslam":            "Cuerpo Pesado",
    "helpinghand":          "Refuerzo",
    "hex":                  "Infortunio",
    "hiddenpower":          "Poder Oculto",
    "highhorsepower":       "Fuerza Equina",
    "highjumpkick":         "Patada Salto Alta",
    "holdback":             "Clemencia",
    "holdhands":            "Celebración",
    "honeclaws":            "Afilagarras",
    "hornattack":           "Cornada",
    "horndrill":            "Perforador",
    "hornleech":            "Astadrenaje",
    "howl":                 "Aullido",
    "hurricane":            "Vendaval",
    "hydrocannon":          "Hidrocañón",
    "hydropump":            "Hidrobomba",
    "hydrosteam":           "Hidrovapor",
    "hyperbeam":            "Hiperrayo",
    "hyperdrill":           "Hipertaladro",
    "hyperfang":            "Hipercolmillo",
    "hyperspacefury":       "Cerco Dimensió",
    "hyperspacehole":       "Paso Dimensional",
    "hypervoice":           "Vozarrón",
    "hypnosis":             "Hipnosis",
    # ── I ────────────────────────────────────────────────────────────────────
    "iceball":              "Bola Hielo",
    "icebeam":              "Rayo Hielo",
    "iceburn":              "Llama Gélida",
    "icefang":              "Colmillo Hielo",
    "icehammer":            "Martillo Hielo",
    "icepunch":             "Puño Hielo",
    "iceshard":             "Canto Helado",
    "icespinner":           "Pirueta Helada",
    "iciclecrash":          "Chuzos",
    "iciclespear":          "Carámbano",
    "icywind":              "Viento Hielo",
    "imprison":             "Sello",
    "incinerate":           "Calcinación",
    "infernalparade":       "Procesión Infernal",
    "inferno":              "Infierno",
    "infestation":          "Acoso",
    "ingrain":              "Arraigo",
    "instruct":             "Mandato",
    "iondeluge":            "Cortina Plasma",
    "irondefense":          "Defensa Férrea",
    "ironhead":             "Cabeza de Hierro",
    "irontail":             "Cola Férrea",
    # ── J ────────────────────────────────────────────────────────────────────
    "jawlock":              "Presa Maxilar",
    "jetpunch":             "Puño Jet",
    "judgment":             "Sentencia",
    "jumpkick":             "Patada Salto",
    "junglehealing":        "Cura Selvática",
    # ── K ────────────────────────────────────────────────────────────────────
    "karatechop":           "Golpe Kárate",
    "kinesis":              "Kinético",
    "knockoff":             "Desarme",
    "kowtowcleave":         "Genuflexión",
    # ── L ────────────────────────────────────────────────────────────────────
    "landswrath":           "Fuerza Telúrica",
    "laserfocus":           "Aguzar",
    "lastresort":           "Último Recurso",
    "lavaplume":            "Estallido Lava",
    "leafage":              "Follaje",
    "leafblade":            "Hoja Aguda",
    "leafstorm":            "Llave de Hoja",
    "leaftornado":          "Ciclón de Hojas",
    "leer":                 "Malicioso",
    "leechlife":            "Chupavidas",
    "leechseed":            "Drenadoras",
    "letssnuggleforever":   "Presa Emocional",
    "lick":                 "Lengüetazo",
    "lifedew":              "Rocío Vital",
    "lightofruin":          "Luz Aniquiladora",
    "lightscreen":          "Pantalla de Luz",
    "lightthatburnsthesky": "Fotodestrucción Apocalíptica",
    "liquidation":          "Hidroariete",
    "lockon":               "Fijar Blanco",
    "lovelykiss":           "Beso Amoroso",
    "lowkick":              "Patada Baja",
    "lowsweep":             "Puntapié",
    "luminacrash":          "Fotocolisión",
    "lunardance":           "Danza Lunar",
    "lunge":                "Planchazo",
    "lusterpurge":          "Resplandor",
    # ── M ────────────────────────────────────────────────────────────────────
    "magicalleaf":          "Hoja Mágica",
    "magicaltorque":        "Falla Mágica",
    "magiccoat":            "Capa Mágica",
    "magicpowder":          "Polvo Estelar",
    "magicroom":            "Zona Mágica",
    "magmastorm":           "Lluvia Ígnea",
    "magnetbomb":           "Bomba Imán",
    "magneticflux":         "Flujo Magnético",
    "magnitude":            "Magnitud",
    "makeitrain":           "Fiebre Dorada",
    "maliciousmoonsault":   "Hiperplancha Oscura",
    "matblock":             "Escudo Tatami",
    "maxairstream":         "Maxiciclón",
    "maxdarkness":          "Maxisombra",
    "maxflare":             "Maxignición",
    "maxflutterby":         "Maxinsecto",
    "maxgeyser":            "Maxichorro",
    "maxguard":             "Maxibarrera",
    "maxhailstorm":         "Maxihielo",
    "maxknuckle":           "Maxipuño",
    "maxlightning":         "Maxitormenta",
    "maxmindstorm":         "Maxipsique",
    "maxooze":              "Maxiacidez",
    "maxovergrowth":        "Maxiflora",
    "maxphantasm":          "Maxiespectro",
    "maxquake":             "Maxilito",
    "maxrockfall":          "Maxilito",
    "maxstarfall":          "Maxiestela",
    "maxsteelspike":        "Maxisiderurgia",
    "maxstrike":            "Maxiataque",
    "maxwyrmwind":          "Maxidraco",
    "meanlook":             "Mal de Ojo",
    "meditate":             "Meditación",
    "megadrain":            "Megaagotar",
    "megahorn":             "Megacuerno",
    "megakick":             "Megapatada",
    "megapunch":            "Megapuño",
    "memento":              "Legado",
    "menacingmoonrazemaelstrom": "Deflagración Lunar",
    "metalburst":           "Represión Metal",
    "metalclaw":            "Garra Metal",
    "metalsound":           "Eco Metálico",
    "meteorassault":        "Asalto Meteoro",
    "meteorbeam":           "Rayo Meteoro",
    "meteormash":           "Puño Meteoro",
    "milkdrink":            "Batido",
    "mimic":                "Mimético",
    "mindblown":            "Cabeza Sorpresa",
    "mindreader":           "Telépata",
    "minimize":             "Minimizar",
    "mirrorcoat":           "Manto Espejo",
    "mirrormove":           "Movimiento Espejo",
    "mirrorshot":           "Disparo Espejo",
    "mist":                 "Neblina",
    "mistball":             "Bola Neblina",
    "mistyexplosion":       "Explosión Bruma",
    "mistyterrain":         "Campo de Niebla",
    "moonblast":            "Fuerza Lunar",
    "moongeistbeam":        "Rayo Umbrío",
    "moonlight":            "Luz de Luna",
    "morningsun":           "Sol Matinal",
    "mortalspin":           "Giro Mortal",
    "mountaingale":         "Viento del Norte",
    "mudbomb":              "Bomba Lodo",
    "mudshot":              "Disparo Lodo",
    "mudsport":             "Chapoteolodo",
    "mudslap":              "Bofetón Lodo",
    "muddywater":           "Agua Lodosa",
    "multiattack":          "Multiataque",
    "mysticalfire":         "Llama Mística",
    "mysticalpower":        "Poder Místico",
    # ── N ────────────────────────────────────────────────────────────────────
    "nastyplot":            "Maquinación",
    "naturalgift":          "Don Natural",
    "naturepower":          "Adaptación",
    "naturesmadness":       "Furia Natural",
    "needlearm":            "Brazo Pincho",
    "nightdaze":            "Pulso Noche",
    "nightshade":           "Tinieblas",
    "nightslash":           "Tajo Umbrío",
    "nightmare":            "Pesadilla",
    "nobleroar":            "Rugido de Guerra",
    "noretreat":            "Sin Escapatoria",
    "nuzzle":               "Moflete Estático",
    # ── O ────────────────────────────────────────────────────────────────────
    "oblivionwing":         "Ala Mortífera",
    "oceanicoperetta":      "Sinfonía del Mar",
    "octazooka":            "Octocañón",
    "odorsleuth":           "Rastreo",
    "ominouswind":          "Viento Funesto",
    "orderup":              "Pedir la Vez",
    "originpulse":          "Pulso Primigenio",
    "outrage":              "Enfado",
    "overdrive":            "Amplificador",
    "overheat":             "Sofoco",
    # ── P ────────────────────────────────────────────────────────────────────
    "painsplit":            "Divide Dolor",
    "paleowave":            "Onda Primitiva",
    "paraboliccharge":      "Parabrisas",
    "partingshot":          "Última Palabra",
    "payback":              "Vendetta",
    "payday":               "Día de Pago",
    "peck":                 "Picotazo",
    "perishsong":           "Canto Mortal",
    "petalblizzard":        "Tormenta Floral",
    "petaldance":           "Danza Pétalo",
    "phantomforce":         "Golpe Fantasma",
    "photongeyser":         "Géiser Fotónico",
    "pikapapow":            "Pika-Papow",
    "pinmissile":           "Pin Misil",
    "playnice":             "Camaradería",
    "playrough":            "Carantoña",
    "pluck":                "Picoteo",
    "poisonfang":           "Colmillo Veneno",
    "poisongas":            "Gas Venenoso",
    "poisonjab":            "Puya Nociva",
    "poisonpowder":         "Polvo Veneno",
    "poisonsting":          "Picotazo Venenoso",
    "poisontail":           "Cola Veneno",
    "pollenpuff":           "Polen Auxiliar",
    "poltergeist":          "Poltergeist",
    "populationbomb":       "Prole Bombardeo",
    "pounce":               "Abalanzarse",
    "pound":                "Destructor",
    "powder":               "Polvo Explosivo",
    "powdersnow":           "Nieve Polvo",
    "powergem":             "Joya de Luz",
    "powershift":           "Cambio de Potencia",
    "powersplit":           "Isofuerza",
    "powerswap":            "Cambio Fuerza",
    "powertrick":           "Truco Fuerza",
    "powertrip":            "Chulería",
    "powerwhip":            "Latigazo",
    "precipiceblades":      "Filo del Abismo",
    "present":              "Presente",
    "prismaticlaser":       "Láser Prismático",
    "protect":              "Protección",
    "psybeam":              "Psicarrayo",
    "psychic":              "Psíquico",
    "psychicfangs":         "Psicocolmillo",
    "psychicterrain":       "Campo Psíquico",
    "psychoboost":          "Psicoimpulso",
    "psychocut":            "Psicocorte",
    "psychoshift":          "Psicotraslado",
    "psychup":              "Autosugestión",
    "psystrike":            "Onda Mental",
    "psywave":              "Psicoonda",
    "punishment":           "Castigo",
    "purify":               "Purificación",
    "pursuit":              "Persecución",
    # ── Q ────────────────────────────────────────────────────────────────────
    "quash":                "Último Lugar",
    "quickattack":          "Ataque Rápido",
    "quickguard":           "Anticipo",
    "quiverdance":          "Danza Aleteo",
    # ── R ────────────────────────────────────────────────────────────────────
    "ragefist":             "Puño Furia",
    "ragepowder":           "Polvo Ira",
    "raindance":            "Danza Lluvia",
    "rapidspin":            "Giro Rápido",
    "razorleaf":            "Hoja Afilada",
    "razorshell":           "Concha Filo",
    "razorwind":            "Viento Cortante",
    "recover":              "Recuperación",
    "recycle":              "Reciclaje",
    "reflect":              "Reflejo",
    "reflecttype":          "Copiatipo",
    "relicsong":            "Canto Ancestral",
    "rest":                 "Descanso",
    "retaliate":            "Represalia",
    "return":               "Retribución",
    "revelationdance":      "Danza Revelación",
    "revenge":              "Venganza",
    "reversal":             "Inversión",
    "revivalblessing":      "Plegaria Vital",
    "risingvoltage":        "Voltaje Elevado",
    "roar":                 "Rugido",
    "roaroftime":           "Distorsión",
    "rockblast":            "Pedrada",
    "rockclimb":            "Treparrocas",
    "rockpolish":           "Pulimento",
    "rockslide":            "Avalancha",
    "rocktomb":             "Tumba Rocas",
    "rockwrecker":          "Romperrocas",
    "roleplay":             "Imitación",
    "rollout":              "Desenrollar",
    "roost":                "Respiro",
    "round":                "Canon",
    "ruination":            "Cataclismo",
    # ── S ────────────────────────────────────────────────────────────────────
    "sacredsword":          "Espada Santa",
    "saltcure":             "Salazón",
    "sandattack":           "Ataque Arena",
    "sandstorm":            "Tormenta de Arena",
    "sandspit":             "Escupearena",
    "sandtomb":             "Bucle Arena",
    "savagespinout":        "Guadaña Sedosa",
    "scald":                "Escaldar",
    "scaryface":            "Cara Susto",
    "scratch":              "Arañazo",
    "screech":              "Chirrido",
    "searingshot":          "Bomba Ígnea",
    "secretpower":          "Daño Secreto",
    "secretsword":          "Sable Místico",
    "seedbomb":             "Bomba Germen",
    "seedflare":            "Fogonazo",
    "seismictoss":          "Movimiento Sísmico",
    "selfdestruct":         "Autodestrucción",
    "shadowball":           "Bola Sombra",
    "shadowbone":           "Hueso Sombrío",
    "shadowclaw":           "Garra Umbría",
    "shadowforce":          "Golpe Umbrío",
    "shadowpunch":          "Puño Sombra",
    "shadowsneak":          "Sombra Furtiva",
    "sharpen":              "Afilar",
    "shedtail":             "Autotomía",
    "shelter":              "Refugio",
    "shiftgear":            "Cambio de Marcha",
    "shockwave":            "Onda Voltio",
    "signalbeam":           "Rayo Señal",
    "silverwind":           "Viento Plata",
    "simplebeam":           "Rayo Simple",
    "sizzlyslide":          "Irrupción Fogosa",
    "skillswap":            "Intercambio",
    "skittersmack":         "Escaramuza Escurridiza",
    "skullbash":            "Cabezazo",
    "skyattack":            "Ataque Aéreo",
    "skydrop":              "Caída Libre",
    "skyuppercut":          "Gancho Alto",
    "slam":                 "Atizar",
    "slash":                "Cuchillada",
    "sleeppowder":          "Somnífero",
    "sleeptalk":            "Sonámbulo",
    "sludge":               "Residuos",
    "sludgebomb":           "Bomba Lodo",
    "sludgewave":           "Onda Tóxica",
    "smackdown":            "Antiaéreo",
    "smellingsalts":        "Estímulo",
    "smokescreen":          "Pantalla de Humo",
    "snarl":                "Alarido",
    "snatch":               "Robo",
    "snore":                "Ronquido",
    "snowscape":            "Paisaje Níveo",
    "softboiled":           "Amortiguador",
    "solarbeam":            "Rayo Solar",
    "solarblade":           "Cuchilla Solar",
    "sonicboom":            "Bomba Sónica",
    "spatialrend":          "Corte Vacío",
    "sparklingaria":        "Aria Burbujeante",
    "spectralthief":        "Robasombra",
    "speedswap":            "Isovelocidad",
    "spikes":               "Púas",
    "spikyshield":          "Escudo Pincho",
    "spinout":              "Giro Derrape",
    "spite":                "Rencor",
    "spitup":               "Escupir",
    "splash":               "Salpicadura",
    "spore":                "Espora",
    "spotlight":            "Foco",
    "springtidestorm":      "Tormenta Primaveral",
    "stealthrock":          "Trampa Rocas",
    "steameruption":        "Chorro de Vapor",
    "steamroller":          "Rodillo de Púas",
    "steelbeam":            "Rayo Acerado",
    "steelroller":          "Rodillo Acerado",
    "steelwing":            "Ala de Acero",
    "stickyweb":            "Red Viscosa",
    "stockpile":            "Reserva",
    "stokedsparksurfer":    "Surfeo Eléctrico",
    "stomp":                "Pisotón",
    "stompingtantrum":      "Pataleta",
    "stoneaxe":             "Hacha Pétrea",
    "stoneedge":            "Roca Afilada",
    "storedpower":          "Poder Reserva",
    "strangesteam":         "Vapor Extraño",
    "strengthsap":          "Absorberfuerza",
    "stringshot":           "Disparo Demora",
    "struggle":             "Combate",
    "stuffcheeks":          "Atiborramiento",
    "stunspore":            "Paralizador",
    "submission":           "Sumisión",
    "substitute":           "Sustituto",
    "subzeroslammer":       "Crioembestida Explosiva",
    "suckerpunch":          "Golpe Bajo",
    "sunnyday":             "Día Soleado",
    "sunsteelstrike":       "Meteoimpacto",
    "supercellslam":        "Impacto Supertormenta",
    "superfang":            "Superdiente",
    "superpower":           "Fuerza Bruta",
    "supersonic":           "Supersónico",
    "surf":                 "Surf",
    "surgingstrikes":       "Azote Torrencial",
    "swagger":              "Contoneo",
    "swallow":              "Tragar",
    "sweetkiss":            "Beso Dulce",
    "sweetscent":           "Dulce Aroma",
    "swift":                "Rapidez",
    "switcheroo":           "Trapicheo",
    "swordsdance":          "Danza Espada",
    "syrupbomb":            "Bomba Jarabe",
    # ── T ────────────────────────────────────────────────────────────────────
    "tackle":               "Placaje",
    "tailglow":             "Ráfaga",
    "tailslap":             "Plumerazo",
    "tailwhip":             "Látigo",
    "tailwind":             "Viento Afín",
    "takedown":             "Derribo",
    "tarshot":              "Alquitranazo",
    "taunt":                "Mofa",
    "tearfullook":          "Ojos Llorosos",
    "teatime":              "Hora del Té",
    "technoblast":          "Tecno Shock",
    "telekinesis":          "Telequinesis",
    "teleport":             "Teletransporte",
    "temperflare":          "Arrebato Ígneo",
    "terablast":            "Teraexplosión",
    "terrainpulse":         "Pulso Terreno",
    "thief":                "Ladrón",
    "thousandarrows":       "Mil Flechas",
    "thousandwaves":        "Mil Temblores",
    "throatchop":           "Golpe Mordaza",
    "thunder":              "Trueno",
    "thunderbolt":          "Rayo",
    "thundercage":          "Electroprisión",
    "thunderclap":          "Clamor Tronante",
    "thunderfang":          "Colmillo Rayo",
    "thunderouskick":       "Patada Trueno",
    "thunderpunch":         "Puño Trueno",
    "thundershock":         "Impactrueno",
    "thunderwave":          "Onda Trueno",
    "tickle":               "Cosquillas",
    "tidyup":               "Orden y Limpieza",
    "topsyturvy":           "Reversión",
    "torchsong":            "Canto Ardiente",
    "torment":              "Tormento",
    "toxic":                "Tóxico",
    "toxicspikes":          "Púas Tóxicas",
    "toxicthread":          "Hilo Tóxico",
    "trailblaze":           "Abrecaminos",
    "transform":            "Transformación",
    "triattack":            "Triataque",
    "trick":                "Truco",
    "trickroom":            "Espacio Raro",
    "triplearrows":         "Triple Flecha",
    "tripleaxel":           "Triple Axel",
    "tropkick":             "Patada Tropical",
    "trumpcard":            "As Oculto",
    "twineedle":            "Doble Ataque",
    "twinbeam":             "Doble Rayo",
    "twister":              "Ciclón",
    # ── U ────────────────────────────────────────────────────────────────────
    "uproar":               "Alboroto",
    "uturn":                "Ida y Vuelta",
    # ── V ────────────────────────────────────────────────────────────────────
    "vcreate":              "V de Fuego",
    "vacuumwave":           "Onda Vacío",
    "venomdrench":          "Trampa Venenosa",
    "venoshock":            "Carga Tóxica",
    "victorydance":         "Danza Victoria",
    "vinewhip":             "Látigo Cepa",
    "visegrip":             "Agarre",
    "vitalthrow":           "Tiro Vital",
    "voltswitch":           "Voltiocambio",
    "volttackle":           "Placaje Eléctrico",
    # ── W ────────────────────────────────────────────────────────────────────
    "wakeupslap":           "Espabilabofetón",
    "waterfall":            "Cascada",
    "watergun":             "Pistola Agua",
    "waterpledge":          "Voto Agua",
    "waterpulse":           "Hidropulso",
    "watershuriken":        "Shuriken de Agua",
    "watersport":           "Hidrochorro",
    "waterspout":           "Salpicar",
    "wavecrash":            "Envite Acuático",
    "weatherball":          "Meteorobola",
    "whirlpool":            "Torbellino",
    "whirlwind":            "Remolino",
    "wickedblow":           "Golpe Crítico",
    "wickedtorque":         "Vaho Ocre",
    "wideguard":            "Vastaguardia",
    "wildcharge":           "Voltio Cruel",
    "wildboltstorm":        "Erosión Electricista",
    "willowisp":            "Fuego Fatuo",
    "wingattack":           "Ataque Ala",
    "wish":                 "Deseo",
    "withdraw":             "Refugio",
    "wonderroom":           "Zona Extraña",
    "woodhammer":           "Mazazo",
    "workup":               "Avivar",
    "worryseed":            "Abatidoras",
    "wrap":                 "Constricción",
    "wringout":             "Estrujón",
    # ── X ────────────────────────────────────────────────────────────────────
    "xscissor":             "Tijera X",
    # ── Y ────────────────────────────────────────────────────────────────────
    "yawn":                 "Bostezo",
    # ── Z ────────────────────────────────────────────────────────────────────
    "zapcannon":            "Electrocañón",
    "zenheadbutt":          "Cabezazo Zen",
    "zingzap":              "Electropunzada",
    "zippyzap":             "Pispás Chispeante",
}

# Movimientos con alta probabilidad intrínseca de golpe crítico (Stage +1 al calcular)
# Fuente: Bulbapedia — "high critical-hit ratio moves"
_HIGH_CRIT_MOVES: frozenset[str] = frozenset({
    "slash",        "crabhammer",   "karatechop",    "razorwind",
    "aeroblast",    "crosschop",    "skyattack",     "leafblade",
    "bladestrife",  "poisontail",   "spacialrend",   "stoneedge",
    "stormthrow",   "frostbreath",  "zipzap",        "wickedblow",
    "surgingstrikes",
})

# ─────────────────────────────────────────────────────────────────────────────
# EXPORTS
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    # ── Core ────────────────────────────────────────────────────────────────
    "BattleUtils",
    "DamageResult",
    "stage_multiplier",
    "resolve_damage_move",
    "apply_stage_change",
    "determine_turn_order",
    "UniversalSide",
    "apply_move",
    "apply_end_of_turn",
    "apply_entry_ability",
    "check_confusion", 
    # ── Campo ────────────────────────────────────────────────────────────────
    "WEATHER_INFO",
    "WEATHER_TYPE_MULT",
    "WEATHER_IMMUNE_TYPES",
    "WEATHER_MOVE_PRECISION",
    "WEATHER_ROCKS",
    "WEATHER_ROCK_NAMES_ES",
    "TERRAIN_INFO",
    "TERRAIN_TYPE_MULT",
    "GRASSY_TERRAIN_HEAL",
    "TERRAIN_BLOCKS_AILMENT",
    "ROOM_INFO",
    "STATUS_ICONS",
    "apply_entry_abilities_ordered",
    # ── Funciones de campo ───────────────────────────────────────────────────
    "apply_weather_boost",
    "apply_terrain_boost",
    "is_grounded",
    "activate_weather",
    "activate_terrain",
    "tick_field_turns",
    # ── Ailments y turn flow ─────────────────────────────────────────────────
    "can_apply_ailment_in_field",
    "apply_ailment",
    "check_can_move",
    # ── Datos de movimientos ─────────────────────────────────────────────────
    "MOVE_EFFECTS",
    "SECONDARY_AILMENTS",
    "DRAIN_MOVES",
    "RECOIL_MOVES",
    "MOVE_NAMES_ES",
    "MULTI_HIT_MOVES",
    "TRAPPING_MOVES",
    "TRAPPING_ABILITIES",
    "_roll_num_hits",
    # ── HIGH_CRIT_MOVES ─────────────────────────────────────────────────
    "MOVE_EFFECTS",
    "_HIGH_CRIT_MOVES",
    "SELF_KO_MOVES",
    "calcular_mult_habilidad",
    "calcular_mult_objeto",
    "_PUNCH_MOVES",
    "_CONTACT_MOVES",
    "_TIPO_BOOST_ITEMS",
    # ── Pesos y movimientos de peso ──────────────────────────────────────
    "get_peso_pokemon",
    "calcular_poder_lowkick",
    "calcular_poder_heavyslam",
    "_LOWKICK_MOVES",
    "_HEAVYSLAM_MOVES",
    # ── Magic Guard ──────────────────────────────────────────────────────
    "tiene_magic_guard",
    "_MAGIC_GUARD_ALIASES",
]

# ─────────────────────────────────────────────────────────────────────────────
# UniversalSide — representa el estado de UN combatiente
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class UniversalSide:
    """
    Instantánea mutable del estado de un Pokémon en combate.
    Cada sistema crea un UniversalSide a partir de su modelo nativo,
    pasa los dos lados a las funciones del motor y luego sincroniza
    los campos de vuelta a su modelo.

    NO contiene lógica de Telegram ni de base de datos.
    """
    # Identidad
    name:           str
    pokemon_db_id:  int          # id_unico en POKEMON_USUARIO
    species_id:     int          # pokemonID (para tipos)
    level:          int
    ability:        str          # nombre en español, ej. "Impostor"

    # Stats
    hp_actual:      int
    hp_max:         int
    stats:          dict         # {"atq","def","atq_sp","def_sp","vel"}
    types:          list         # tipos en español
    moves:          list         # move_keys
    stat_stages:    dict = field(default_factory=lambda: {
        "atq": 0, "def": 0, "atq_sp": 0, "def_sp": 0, "vel": 0
    })
    crit_stage:     int = 0

    # Status
    status:          Optional[str] = None
    sleep_turns:     int = 0
    toxic_counter:   int = 0
    yawn_counter:    int = 0
    confusion_turns: int = 0
    leechseeded:     bool = False
    # ── Atrapado (Constricción, Rueda de Fuego, etc.) ─────────────────────────
    trapped:         bool  = False
    trap_turns:      int   = 0         # turnos restantes de atrapamiento
    trap_dmg_ratio:  float = 0.0       # daño / turno como fracción del HP máximo
    trap_source:     str   = ""        # nombre del movimiento que atrapó (para log)
    teleport_flee:   bool = False   # Teleport / huida forzada por movimiento
    # ── Mecánicas de 2 turnos ─────────────────────────────────────────────────
    charging_move:    Optional[str] = None   # Move en carga (turno 1)
    recharge_pending: bool          = False  # Necesita recarga (post Hiper Rayo)
    delayed_attacks: list = field(default_factory=list)
    # Formato: [{"move": str, "turns_left": int, "atq_sp": int,
    #             "level": int, "attacker_name": str, "power": int}]
    # Objeto equipado (para bayas automáticas en combate)
    objeto:          Optional[str] = None
    # Campo interno: baya consumida en este turno (para que el adapter la detecte)
    baya_consumida:  Optional[str] = field(default=None, init=False, repr=False)
    berry_eaten:     bool = False   # True si ya consumió alguna baya en esta batalla
# ─────────────────────────────────────────────────────────────────────────────
# _BattleShim — adapta dos UniversalSide al protocolo "wild/player" del motor
# ─────────────────────────────────────────────────────────────────────────────

class _BattleShim:
    """
    Objeto liviano que expone la interfaz que esperan check_can_move,
    apply_ailment, check_confusion, activate_weather, etc.
    Mapea: attacker → "player", defender → "wild".
    """
    __slots__ = ("_f", "_a", "_d")

    def __init__(self, field, attacker: "UniversalSide", defender: "UniversalSide"):
        self._f = field
        self._a = attacker
        self._d = defender

    # ── Campo (redirige al objeto field) ──────────────────────────────────────
    @property
    def weather(self):          return self._f.weather
    @weather.setter
    def weather(self, v):       self._f.weather = v
    @property
    def weather_turns(self):    return self._f.weather_turns
    @weather_turns.setter
    def weather_turns(self, v): self._f.weather_turns = v
    @property
    def terrain(self):          return self._f.terrain
    @terrain.setter
    def terrain(self, v):       self._f.terrain = v
    @property
    def terrain_turns(self):    return self._f.terrain_turns
    @terrain_turns.setter
    def terrain_turns(self, v): self._f.terrain_turns = v

    # Salas
    @property
    def trick_room(self):             return getattr(self._f, "trick_room", False)
    @trick_room.setter
    def trick_room(self, v):          self._f.trick_room = v
    @property
    def trick_room_turns(self):       return getattr(self._f, "trick_room_turns", 0)
    @trick_room_turns.setter
    def trick_room_turns(self, v):    self._f.trick_room_turns = v
    @property
    def gravity(self):                return getattr(self._f, "gravity", False)
    @gravity.setter
    def gravity(self, v):             self._f.gravity = v
    @property
    def gravity_turns(self):          return getattr(self._f, "gravity_turns", 0)
    @gravity_turns.setter
    def gravity_turns(self, v):       self._f.gravity_turns = v
    @property
    def magic_room(self):             return getattr(self._f, "magic_room", False)
    @magic_room.setter
    def magic_room(self, v):          self._f.magic_room = v
    @property
    def magic_room_turns(self):       return getattr(self._f, "magic_room_turns", 0)
    @magic_room_turns.setter
    def magic_room_turns(self, v):    self._f.magic_room_turns = v
    @property
    def wonder_room(self):            return getattr(self._f, "wonder_room", False)
    @wonder_room.setter
    def wonder_room(self, v):         self._f.wonder_room = v
    @property
    def wonder_room_turns(self):      return getattr(self._f, "wonder_room_turns", 0)
    @wonder_room_turns.setter
    def wonder_room_turns(self, v):   self._f.wonder_room_turns = v

    # ── Atacante → "player" ───────────────────────────────────────────────────
    @property
    def player_status(self):              return self._a.status
    @player_status.setter
    def player_status(self, v):           self._a.status = v
    @property
    def player_sleep_turns(self):         return self._a.sleep_turns
    @player_sleep_turns.setter
    def player_sleep_turns(self, v):      self._a.sleep_turns = v
    @property
    def player_toxic_counter(self):       return self._a.toxic_counter
    @player_toxic_counter.setter
    def player_toxic_counter(self, v):    self._a.toxic_counter = v
    @property
    def player_yawn_counter(self):        return self._a.yawn_counter
    @player_yawn_counter.setter
    def player_yawn_counter(self, v):     self._a.yawn_counter = v
    @property
    def player_confusion_turns(self):     return self._a.confusion_turns
    @player_confusion_turns.setter
    def player_confusion_turns(self, v):  self._a.confusion_turns = v
    @property
    def player_leechseeded(self):         return self._a.leechseeded
    @player_leechseeded.setter
    def player_leechseeded(self, v):      self._a.leechseeded = v
    @property
    def player_stat_stages(self):         return self._a.stat_stages
    @property
    def player_pokemon_id(self):          return self._a.pokemon_db_id

    # ── Defensor → "wild" ─────────────────────────────────────────────────────
    @property
    def wild_status(self):                return self._d.status
    @wild_status.setter
    def wild_status(self, v):             self._d.status = v
    @property
    def wild_sleep_turns(self):           return self._d.sleep_turns
    @wild_sleep_turns.setter
    def wild_sleep_turns(self, v):        self._d.sleep_turns = v
    @property
    def wild_toxic_counter(self):         return self._d.toxic_counter
    @wild_toxic_counter.setter
    def wild_toxic_counter(self, v):      self._d.toxic_counter = v
    @property
    def wild_yawn_counter(self):          return self._d.yawn_counter
    @wild_yawn_counter.setter
    def wild_yawn_counter(self, v):       self._d.yawn_counter = v
    @property
    def wild_confusion_turns(self):       return self._d.confusion_turns
    @wild_confusion_turns.setter
    def wild_confusion_turns(self, v):    self._d.confusion_turns = v
    @property
    def wild_leechseeded(self):           return self._d.leechseeded
    @wild_leechseeded.setter
    def wild_leechseeded(self, v):        self._d.leechseeded = v
    @property
    def wild_stat_stages(self):           return self._d.stat_stages
    @property
    def wild_pokemon(self):               return self._d   # tiene hp_actual directamente

def _roll_num_hits(move_key: str, ability: str = "") -> int:
    """
    Determina cuántos golpes lanza un movimiento multi-hit.

    Distribución canónica Gen 5+:
      35.2 % → 2 golpes
      35.2 % → 3 golpes
      14.8 % → 4 golpes
      14.8 % → 5 golpes

    Si el atacante tiene Skill Link (Encadenado), siempre golpea el máximo.
    Movimientos con rango fijo (ej. 2–2, 3–3) siempre devuelven ese valor.
    """
    import random as _random
    cfg = MULTI_HIT_MOVES.get(move_key)
    if cfg is None:
        return 1
    lo, hi = cfg
    if lo == hi:
        return lo                         # golpes fijos (doublekick, surgingstrikes…)

    # ── Skill Link: siempre el máximo de golpes ──────────────────────────────
    # Acepta el nombre en español e inglés, con o sin espacios/guiones.
    _hab = ability.lower().replace(" ", "").replace("-", "") if ability else ""
    if _hab in ("encadenado", "skilllink"):
        return hi

    # Distribución Gen 5+
    if lo == 2 and hi == 5:
        roll = _random.random()
        if roll < 0.352:   return 2
        if roll < 0.704:   return 3
        if roll < 0.852:   return 4
        return 5
    # Fallback para rangos especiales (ej. 1–10)
    return _random.randint(lo, hi)

# ─────────────────────────────────────────────────────────────────────────────
# apply_move  — movimiento completo (status + daño + efectos secundarios)
# ─────────────────────────────────────────────────────────────────────────────

def apply_move(
    attacker:  "UniversalSide",
    defender:  "UniversalSide",
    field,
    move_key:  str,
    move_data: dict,
    log:       list,
    *,
    type_effectiveness_fn,
) -> bool:
    mk = move_key.lower().replace(" ", "").replace("-", "")
    
    # ── 1. Movimientos Diferidos ─────────────────────────────────────────────
    if mk in DELAYED_MOVES:
        cfg = DELAYED_MOVES[mk]
        attacker.delayed_attacks.append({
            "move": mk, "turns_left": cfg["turns"],
            "atq_sp": attacker.stats.get("atq_sp", 50),
            "level": attacker.level, "attacker_name": attacker.name,
            "power": cfg["power"],
        })
        log.append(f"  🔮 {cfg['msg_uso'].format(nombre=attacker.name)}\n")
        return False
    
    # ── 2. Daño Fijo ─────────────────────────────────────────────────────────
    if mk in FIXED_DAMAGE_MOVES:
        cfg_fd = FIXED_DAMAGE_MOVES[mk]
        if any(t in cfg_fd.get("immune_types", []) for t in defender.types):
            log.append(f"  💫 ¡No le afecta a <b>{defender.name}</b>!\n")
            return False
        dmg = attacker.level if cfg_fd["damage_fn"] == "level" else cfg_fd.get("damage", 40)
        defender.hp_actual = max(0, defender.hp_actual - dmg)
        move_nombre = MOVE_NAMES_ES.get(mk, move_key.title())
        log.append(f"  ⚡ <b>{attacker.name}</b> usó <b>{move_nombre}</b> e infligió <b>{dmg}</b> de daño.\n")
        return defender.hp_actual <= 0
    
    if handle_two_turn(attacker, field, mk, log):
        return False

    # ── 3. Validación de Eructo ──────────────────────────────────────────────
    if mk == "belch" and not getattr(attacker, "berry_eaten", False):
        log.append(f"  💫 ¡{attacker.name} usó Eructo... pero falló! (Requiere haber comido una Baya)\n")
        return False

    shim = _BattleShim(field, attacker, defender)
    if not check_can_move(shim, is_player=True, actor_name=attacker.name, log=log):
        return False

    if check_confusion(shim, is_player=True, actor_name=attacker.name, actor_level=attacker.level,
                       actor_atq=attacker.stats.get("atq", 50), log=log):
        return False

    # ── 4. Datos y Precisión ─────────────────────────────────────────────────
    _CAT = {"Physical": "Físico", "Special": "Especial", "Status": "Estado"}
    categoria = move_data.get("categoria") or _CAT.get(move_data.get("category", ""), "Estado")
    tipo_mov  = move_data.get("tipo") or move_data.get("type", "Normal")
    poder     = int(move_data.get("poder") or move_data.get("basePower") or 0)
    move_es   = MOVE_NAMES_ES.get(mk, move_data.get("nombre", move_key.title()))
    
    _prec_raw = move_data.get("precision", move_data.get("accuracy", 100))
    precision = 999 if (_prec_raw is True or _prec_raw is None) else int(_prec_raw or 100)

    # Clima afecta precisión
    weather_now = getattr(field, "weather", None)
    if weather_now:
        weather_prec = WEATHER_MOVE_PRECISION.get(weather_now, {}).get(mk)
        if weather_prec is not None: precision = weather_prec

    if precision < 100 and random.randint(1, 100) > precision:
        log.append(f"  💨 ¡{attacker.name} usó {move_es} pero falló!\n")
        return False

    log.append(f"\n  ⚔️ ¡<b>{attacker.name}</b> usó <b>{move_es}</b>!\n")

    if poder == 0:
        _apply_status_effect(attacker, defender, field, shim, mk, log)
        return False

    # ── 5. Cálculo de Daño y Bayas de Mitigación ─────────────────────────────
    type_eff = type_effectiveness_fn(tipo_mov, defender.types)
    
    _BAYA_REDUCCION = {
        "baya yatay": "Fuego", "baya anjiro": "Agua", "baya magua": "Eléctrico",
        "baya rindo": "Planta", "baya yecana": "Hielo", "baya aricoc": "Lucha",
        "baya kebia": "Veneno", "baya shuca": "Tierra", "baya coba": "Volador",
        "baya payapa": "Psíquico", "baya tanga": "Bicho", "baya charti": "Roca",
        "baya kasib": "Fantasma", "baya draco": "Dragón", "baya colbur": "Siniestro",
        "baya babiri": "Acero", "baya chilan": "Normal", "baya hibis": "Hada"
    }
    
    if (defender.objeto and defender.objeto in _BAYA_REDUCCION and 
        _BAYA_REDUCCION[defender.objeto] == tipo_mov and type_eff > 1.0):
        type_eff *= 0.5
        log.append(f"  🍓 ¡La {defender.objeto.title()} de <b>{defender.name}</b> redujo el daño!\n")

        defender.baya_consumida = defender.objeto
        defender.objeto = None
        defender.berry_eaten = True

    if type_eff == 0.0:
        log.append(f"  🚫 ¡No afecta a {defender.name}!\n")
        return False

    weather_mult = apply_weather_boost(weather_now, tipo_mov)
    terrain_mult = apply_terrain_boost(getattr(field, "terrain", None), tipo_mov, is_grounded(attacker.types, shim))

    # ── Poder variable por peso (Low Kick / Grass Knot / Heavy Slam / Heat Crash) ──
    if mk in _LOWKICK_MOVES:
        _def_pid  = getattr(defender, "species_id", getattr(defender, "pokemon_db_id", 0))
        poder     = calcular_poder_lowkick(get_peso_pokemon(_def_pid))
    elif mk in _HEAVYSLAM_MOVES:
        _atk_pid  = getattr(attacker, "species_id", getattr(attacker, "pokemon_db_id", 0))
        _def_pid  = getattr(defender, "species_id", getattr(defender, "pokemon_db_id", 0))
        poder     = calcular_poder_heavyslam(get_peso_pokemon(_atk_pid), get_peso_pokemon(_def_pid))

    # ── 6. Multi-hit y Resolución de Daño ───────────────────────────────────
    num_hits = _roll_num_hits(mk, attacker.ability)
    total_dmg = 0

    _hab_mult, _quitar_secundario = calcular_mult_habilidad(
        attacker.ability, mk, tipo_mov, categoria, poder,
        hp_ratio=(attacker.hp_actual / max(attacker.hp_max, 1)),
    )
    _type_eff_pre = type_effectiveness_fn(tipo_mov, defender.types)
    _obj_mult, _obj_recoil = calcular_mult_objeto(
        attacker.objeto or "", tipo_mov, categoria, _type_eff_pre
    )
    _poder_base_con_hab = max(1, int(poder * _hab_mult * _obj_mult))
    _obj_recoil_ratio   = _obj_recoil
    _atk_magic_guard    = tiene_magic_guard(attacker.ability)

    if _hab_mult > 1.0 and attacker.ability:
        log.append(f"  ✨ ¡La habilidad <b>{attacker.ability}</b> potenció el ataque!\n")
    if _obj_mult > 1.0 and attacker.objeto:
        log.append(f"  🎒 ¡<b>{attacker.objeto.title()}</b> potenció el ataque!\n")

    for hit_idx in range(num_hits):
        if defender.hp_actual <= 0: break

        hit_power = _poder_base_con_hab * (hit_idx + 1) if mk in {"triplekick", "tripleaxel"} else _poder_base_con_hab

        res: DamageResult = resolve_damage_move(
            attacker_name         = attacker.name,
            defender_name         = defender.name,
            attacker_level        = attacker.level,
            attacker_stats        = attacker.stats,
            attacker_types        = attacker.types,
            attacker_stages       = attacker.stat_stages,
            defender_hp           = defender.hp_actual,
            defender_stats        = defender.stats,
            defender_types        = defender.types,
            defender_stages       = defender.stat_stages,
            move_name             = move_es if hit_idx == 0 else f"{move_es} (golpe {hit_idx + 1})",
            move_power            = max(1, int(hit_power * weather_mult * terrain_mult)),
            move_category         = categoria,
            move_type             = tipo_mov,
            type_effectiveness_fn = type_effectiveness_fn,
            drain_ratio           = DRAIN_MOVES.get(mk, 0.0),
            crit_stage            = attacker.crit_stage + (1 if mk in _HIGH_CRIT_MOVES else 0),
            defender_ability      = defender.ability,
            defender_hp_max       = defender.hp_max,
            attacker_ability      = attacker.ability,
        )

        log.extend(res.log)
        total_dmg += res.damage
        defender.hp_actual = max(0, defender.hp_actual - res.damage)

        if res.drained_hp > 0:
            attacker.hp_actual = min(attacker.hp_max, attacker.hp_actual + res.drained_hp)
            log.append(f"  💚 ¡{attacker.name} absorbió {res.drained_hp} HP!\n")

        # Retroceso — bloqueado por Magic Guard
        if RECOIL_MOVES.get(mk, 0.0) and res.damage > 0 and not _atk_magic_guard:
            rdmg = max(1, int(res.damage * RECOIL_MOVES[mk]))
            attacker.hp_actual = max(0, attacker.hp_actual - rdmg)
            log.append(f"  💢 ¡{attacker.name} sufrió {rdmg} de retroceso!\n")

    if num_hits > 1 and total_dmg > 0:
        log.append(f"  🔢 ¡{num_hits} golpes! Daño total: <b>{total_dmg}</b>\n")

    # Life Orb recoil — bloqueado por Magic Guard
    if _obj_recoil_ratio > 0 and total_dmg > 0 and not _atk_magic_guard:
        _lo_recoil = max(1, int(attacker.hp_max * _obj_recoil_ratio))
        attacker.hp_actual = max(0, attacker.hp_actual - _lo_recoil)
        log.append(f"  🔴 ¡<b>{attacker.name}</b> perdió {_lo_recoil} HP por la Vida Esfera!\n")

        if type_eff > 1.0: log.append("  💥 ¡Es muy eficaz!\n")
    elif 0 < type_eff < 1.0: log.append("  😐 No es muy eficaz…\n")

    # ── 7. Efectos de Atrapado y Secundarios ─────────────────────────────────
    trap_cfg = TRAPPING_MOVES.get(mk)
    if trap_cfg and total_dmg > 0 and not defender.trapped:
        defender.trapped = True
        defender.trap_turns = random.randint(*trap_cfg["turns"])
        defender.trap_source = trap_cfg["nombre_es"]
        log.append(f"  🔗 ¡{defender.name} fue atrapado por {defender.trap_source}!\n")

    if defender.hp_actual > 0 and defender.status is None:
        sec = SECONDARY_AILMENTS.get(mk)
        if sec and random.randint(1, 100) <= sec[1]:
            apply_ailment(shim, sec[0], target_is_wild=True, target_name=defender.name, log=log)
            defender.status = shim.wild_status
            defender.sleep_turns = shim.wild_sleep_turns

    # ── 8. ACTIVACIÓN DE BAYAS (Curación/Estado) ─────────────────────────────
    if defender.hp_actual > 0:
        # Baya Aranja (Vida < 50%)
        if defender.hp_actual <= (defender.hp_max * 0.5) and defender.objeto == "baya aranja":
            recuperado = 10
            defender.hp_actual = min(defender.hp_max, defender.hp_actual + recuperado)
            log.append(f"  🍒 ¡<b>{defender.name}</b> usó su Baya Aranja y recuperó PS!\n")
            defender.baya_consumida, defender.objeto = defender.objeto, None
            defender.berry_eaten = True # Esto habilita Eructo para el futuro
        
        # Baya Ziuela (Cura estado)
        if defender.status and defender.objeto == "baya ziuela":
            log.append(f"  ✨ ¡La Baya Ziuela de <b>{defender.name}</b> curó su estado!\n")
            defender.status = None
            defender.baya_consumida, defender.objeto = defender.objeto, None
            defender.berry_eaten = True

    fainted = defender.hp_actual <= 0
    if fainted:
        log.append(f"  💀 ¡<b>{defender.name}</b> se debilitó!\n")
    
    # ── Self-KO: el atacante se debilita tras usar el movimiento ─────────────
    if mk in SELF_KO_MOVES and total_dmg > 0:
        attacker.hp_actual = 0
        log.append(f"  💥 ¡<b>{attacker.name}</b> se debilitó por el esfuerzo!\n")

    # Bajada de stats propia (ej: Sofoco)
    if total_dmg > 0 and mk in SECONDARY_SELF_STAT_DROPS:
        for _stat, _delta in SECONDARY_SELF_STAT_DROPS[mk]:
            apply_stage_change(_stat, _delta, attacker.stat_stages, attacker.name, log)

    register_recharge(attacker, mk)
    return fainted


# ─────────────────────────────────────────────────────────────────────────────
# _apply_status_effect  — efectos de movimientos con poder 0
# ─────────────────────────────────────────────────────────────────────────────

def _apply_status_effect(
    attacker: "UniversalSide",
    defender: "UniversalSide",
    field,
    shim:     "_BattleShim",
    mk:       str,
    log:      list,
) -> None:
    """
    Aplica el efecto completo de un movimiento de estado.
    Cubre: etapas, ailments, clima, terreno, salas, curación, drenadoras,
    golpe crítico, Rest, Bostezo, Neblina, Teleport, pivot.
    """
    effect  = MOVE_EFFECTS.get(mk)
    move_es = MOVE_NAMES_ES.get(mk, mk.title())
    if not effect:
        log.append(f"  💫 ¡{attacker.name} usó {move_es}! (Sin efecto registrado)\n")
        return

    # Etapas de stat
    for target, stat, delta in effect.get("stages", []):
        stages = attacker.stat_stages if target == "self" else defender.stat_stages
        quien  = attacker.name        if target == "self" else defender.name
        apply_stage_change(stat, delta, stages, quien, log)

    # Bostezo
    if effect.get("yawn") and defender.yawn_counter == 0:
        defender.yawn_counter = 1
        log.append(f"  😪 ¡{defender.name} comenzó a adormilarse!\n")

    # Ailment
    if "ailment" in effect:
        ail = effect["ailment"]
        if mk == "rest":
            # Rest: cura HP al máximo y duerme al ATACANTE (independiente de status previo).
            if attacker.hp_actual <= 0:
                log.append(f"  💫 ¡{attacker.name} no puede usar Descanso estando debilitado!\n")
                return
            attacker.hp_actual = attacker.hp_max
            # Rest cura cualquier status previo antes de aplicar sueño
            attacker.status        = None
            attacker.toxic_counter = 0
            # Aplicar sueño al atacante (2–3 turnos, estándar Gen 5+)
            attacker.status      = "slp"
            attacker.sleep_turns = random.randint(2, 3)
            log.append(
                f"  💚 ¡<b>{attacker.name}</b> se curó completamente "
                f"y se quedó dormido!\n"
            )
        else:
            if defender.status is None:
                apply_ailment(shim, ail, target_is_wild=True,
                            target_name=defender.name, log=log)
                defender.status      = shim.wild_status
                defender.sleep_turns = shim.wild_sleep_turns

    # Clima
    if "weather" in effect:
        w_key, w_turns = effect["weather"]
        activate_weather(shim, w_key, w_turns, attacker.name, log)

    # Terreno
    if "terrain" in effect:
        t_key, t_turns = effect["terrain"]
        activate_terrain(shim, t_key, t_turns, attacker.name, log)

    # Salas (Trick Room, Gravity, etc.)
    if "room" in effect:
        room_attr  = effect["room"]
        turns_attr = room_attr + "_turns"
        emoji, nombre, default_turns = ROOM_INFO.get(room_attr, ("", room_attr, 5))
        if getattr(field, room_attr, False):
            setattr(field, room_attr, False)
            setattr(field, turns_attr, 0)
            log.append(f"  {emoji} <i>{nombre} terminó antes de tiempo.</i>\n")
        else:
            setattr(field, room_attr, True)
            setattr(field, turns_attr, default_turns)
            log.append(f"  {emoji} ¡<b>{nombre}</b> entró en efecto por {default_turns} turnos!\n")

    # Neblina (Haze): resetea todas las etapas
    if effect.get("haze"):
        for side in (attacker, defender):
            side.stat_stages = {"atq": 0, "def": 0, "atq_sp": 0, "def_sp": 0, "vel": 0}
        log.append("  🌫️ ¡Las etapas de todos fueron reseteadas!\n")

    # Curación (Recover, Roost, Moonlight…)
    # Un Pokémon debilitado (hp == 0) no puede curarse con movimientos.
    if "heal" in effect and attacker.hp_actual > 0 and mk != "rest":
        # Síntesis, Sol Matinal y Luz Lunar dependen del clima (Gen 2+)
        if mk in {"synthesis", "morningsun", "moonlight"}:
            weather = getattr(field, "weather", None)
            if weather == "sun":
                ratio = 2 / 3
            elif weather in {"rain", "sand", "snow", "fog"}:
                ratio = 1 / 4
            else:
                ratio = 0.50
        else:
            ratio = effect["heal"]
        healed = max(1, int(attacker.hp_max * ratio))
        attacker.hp_actual = min(attacker.hp_max, attacker.hp_actual + healed)
        log.append(f"  💚 {attacker.name} recuperó {healed} HP.\n")

    # Drenadoras (Leech Seed)
    if effect.get("leechseed"):
        if "Planta" in defender.types:
            log.append(f"  🌿 ¡Las Drenadoras no afectan a tipos Planta!\n")
        elif defender.leechseeded:
            log.append(f"  🌿 ¡{defender.name} ya está sembrado!\n")
        else:
            defender.leechseeded = True
            log.append(f"  🌱 ¡{defender.name} fue sembrado con Drenadoras!\n")

    # Focus Energy / Laser Focus
    if "crit_stage" in effect:
        crit_target, crit_delta = effect["crit_stage"]
        side   = attacker if crit_target == "self" else defender
        nombre = attacker.name if crit_target == "self" else defender.name
        side.crit_stage = min(3, side.crit_stage + crit_delta)
        msg = "garantiza críticos" if side.crit_stage >= 3 else "se concentra para críticos"
        log.append(f"  🎯 ¡{nombre} {msg}!\n")

    # Transformación: el atacante copia al defensor
    if effect.get("transform"):
        _apply_impostor(attacker, defender, log)

    # Teleport / huida garantizada (el llamador detecta battle.state == FLED)
    if effect.get("flee"):
        attacker.teleport_flee = True


# ─────────────────────────────────────────────────────────────────────────────
# apply_end_of_turn  — efectos residuales de fin de turno
# ─────────────────────────────────────────────────────────────────────────────

def apply_end_of_turn(
    side_a: "UniversalSide",
    side_b: "UniversalSide",
    field,
    log:    list,
) -> None:
    """
    Aplica todos los efectos de fin de turno en orden canónico (Showdown):
      1. Drenadoras (Leech Seed)
      2. Veneno / Tóxico / Quemadura
      3. Campo de Hierba (curación)
      4. Clima (daño de arena/granizo)
      5. Bostezo → sueño
      6. tick_field_turns (clima/terreno/salas)

    Modifica side_a, side_b y field in-place.  NO toca la BD.
    """
   # 0. Bayas de combate (activación automática)
    _BAYA_BOOST_STAT = {
        "baya latano":  ("atq",    1),
        "baya gonlan":  ("def",    1),
        "baya yapati":  ("vel",    1),
        "baya actania": ("atq_sp", 1),
        "baya algama":  ("def_sp", 1),
    }
    for side in (side_a, side_b):
        if not side.objeto or side.hp_actual <= 0:
            continue
        obj = side.objeto
        hp_ratio = side.hp_actual / max(side.hp_max, 1)

        # Baya Zanama (Sitrus) → cura 25% HP si < 50%
        if obj == "baya zanama" and hp_ratio < 0.50:
            healed = max(1, side.hp_max // 4)
            side.hp_actual = min(side.hp_max, side.hp_actual + healed)
            side.baya_consumida = obj 
            side.objeto = None
            log.append(f"  🍓 ¡La Baya Zanama de <b>{side.name}</b> restauró {healed} HP!\n")

        # Baya Ligaya (Oran) → cura 10 HP si < 50%
        elif obj == "baya ligaya" and hp_ratio < 0.50:
            healed = min(10, side.hp_max - side.hp_actual)
            side.hp_actual = min(side.hp_max, side.hp_actual + healed)
            side.baya_consumida = obj 
            side.objeto = None
            log.append(f"  🍓 ¡La Baya Ligaya de <b>{side.name}</b> restauró {healed} HP!\n")

        # Bayas de boost de stat al 25% HP
        elif obj in _BAYA_BOOST_STAT and hp_ratio < 0.25:
            stat, delta = _BAYA_BOOST_STAT[obj]
            side.stat_stages[stat] = min(6, side.stat_stages.get(stat, 0) + delta)
            side.baya_consumida = obj 
            side.objeto = None
            log.append(
                f"  🍓 ¡La {obj.title()} de <b>{side.name}</b>"
                f" subió su {stat.upper()}!\n"
            )

    # 0b. Objetos de curación pasiva por turno: Restos y Lodo Negro
    # Orden canónico: antes de drenadoras (Showdown server order).
    for side in (side_a, side_b):
        if side.hp_actual <= 0 or side.hp_actual >= side.hp_max:
            continue
        obj = (side.objeto or "").lower().replace(" ", "").replace("_", "")
        if obj == "leftovers" or obj == "restos":
            # Leftovers: cura 1/16 HP máximo siempre, sin condición de tipo
            healed = max(1, side.hp_max // 16)
            side.hp_actual = min(side.hp_max, side.hp_actual + healed)
            log.append(
                f"  🍃 Los <b>Restos</b> de <b>{side.name}</b>"
                f" restauraron {healed} HP.\n"
            )
        elif obj == "blacksludge" or obj == "lodo negro" or obj == "lodonegro":
            # Lodo Negro: cura 1/16 si es tipo Veneno; daña 1/8 si no lo es
            es_veneno = any(t in ("Veneno", "Poison") for t in side.types)
            if es_veneno:
                healed = max(1, side.hp_max // 16)
                side.hp_actual = min(side.hp_max, side.hp_actual + healed)
                log.append(
                    f"  🟣 El <b>Lodo Negro</b> de <b>{side.name}</b>"
                    f" restauró {healed} HP.\n"
                )
            else:
                dmg = max(1, side.hp_max // 8)
                side.hp_actual = max(0, side.hp_actual - dmg)
                log.append(
                    f"  🟣 ¡El <b>Lodo Negro</b> dañó a <b>{side.name}</b>"
                    f" en {dmg} HP!\n"
                )

   # 1. Drenadoras (Leech Seed)
    for seeded, other in ((side_a, side_b), (side_b, side_a)):
        if seeded.leechseeded and seeded.hp_actual > 0:
            drain = max(1, seeded.hp_max // 8)
            seeded.hp_actual = max(0, seeded.hp_actual - drain)
            log.append(
                f"  🌿 Drenadoras quitaron <b>{drain}</b> HP a <b>{seeded.name}</b>.\\n"
            )
            # Solo curar al receptor si está vivo — no revivir Pokémon KO.
            if other.hp_actual > 0:
                healed = min(drain, other.hp_max - other.hp_actual)
                if healed > 0:
                    other.hp_actual += healed
                    log.append(
                        f"  💚 <b>{other.name}</b> absorbió {healed} HP de Drenadoras.\\n"
                    )

    # 1b. Daño de trampa / atadura (Constricción, Rueda de Fuego, etc.)
    for trapped_side, _other in ((side_a, side_b), (side_b, side_a)):
        if trapped_side.trapped and trapped_side.hp_actual > 0:
            trap_dmg = max(1, int(trapped_side.hp_max * trapped_side.trap_dmg_ratio))
            trapped_side.hp_actual = max(0, trapped_side.hp_actual - trap_dmg)
            log.append(
                f"  🔗 <b>{trapped_side.name}</b> sufrió <b>{trap_dmg}</b> HP "
                f"de daño por <b>{trapped_side.trap_source}</b>.\\n"
            )
            trapped_side.trap_turns -= 1
            if trapped_side.trap_turns <= 0:
                trapped_side.trapped        = False
                trapped_side.trap_turns     = 0
                trapped_side.trap_dmg_ratio = 0.0
                trapped_side.trap_source    = ""
                log.append(
                    f"  🔓 <b>{trapped_side.name}</b> ya no está atrapado.\\n"
                )

    # 2. Status residual
    for side in (side_a, side_b):
        if side.hp_actual <= 0:
            continue
        # Magic Guard: inmune a daño indirecto (veneno, quemadura, tóxico)
        if tiene_magic_guard(getattr(side, "ability", "") or ""):
            continue
        if side.status in ("psn", "brn"):
            dmg = max(1, side.hp_max // 8)
            side.hp_actual = max(0, side.hp_actual - dmg)
            icon  = STATUS_ICONS.get(side.status, "")
            label = "quemadura" if side.status == "brn" else "veneno"
            log.append(f"  {icon} {side.name} sufre {dmg} HP por {label}.\n")
        elif side.status == "tox":
            side.toxic_counter += 1
            dmg = max(1, (side.hp_max * side.toxic_counter) // 16)
            side.hp_actual = max(0, side.hp_actual - dmg)
            log.append(f"  ☠️ {side.name} sufre {dmg} HP por tóxico (×{side.toxic_counter}).\n")

    # 3. Campo de Hierba
    if getattr(field, "terrain", None) == "grassy":
        for side in (side_a, side_b):
            if side.hp_actual > 0:
                heal = max(1, side.hp_max // 16)
                side.hp_actual = min(side.hp_max, side.hp_actual + heal)
                log.append(f"  🌿 {side.name} recuperó {heal} HP (Campo de Hierba).\n")

    # 4. Clima dañino
    weather = getattr(field, "weather", None)
    if weather in ("sand", "snow"):
        immune = WEATHER_IMMUNE_TYPES.get(weather, set())
        emoji, wname, _ = WEATHER_INFO.get(weather, ("🌀", weather, 0))
        for side in (side_a, side_b):
            if side.hp_actual <= 0:
                continue
            # Magic Guard: también bloquea el daño de clima
            if tiene_magic_guard(getattr(side, "ability", "") or ""):
                continue
            if not any(t in immune for t in side.types):
                dmg = max(1, side.hp_max // 16)
                side.hp_actual = max(0, side.hp_actual - dmg)
                log.append(f"  {emoji} {side.name} sufre {dmg} HP por {wname}.\n")

    # 5. Bostezo → sueño
    for sleepy, other in ((side_a, side_b), (side_b, side_a)):
        if sleepy.yawn_counter > 0:
            sleepy.yawn_counter -= 1
            if sleepy.yawn_counter == 0 and sleepy.status is None:
                shim = _BattleShim(field, other, sleepy)
                apply_ailment(shim, "slp", target_is_wild=True,
                              target_name=sleepy.name, log=log)
                sleepy.status      = shim.wild_status
                sleepy.sleep_turns = shim.wild_sleep_turns

    # 6. Tick de campo (decrementar clima/terreno/salas)
    tick_field_turns(field, log)

    # ── Ataques diferidos: tick y disparo ────────────────────────────────────
    import random as _rnd
    for att_side, def_side in ((side_a, side_b), (side_b, side_a)):
        remaining = []
        for da in att_side.delayed_attacks:
            da["turns_left"] -= 1
            if da["turns_left"] <= 0:
                if def_side.hp_actual > 0:
                    cfg    = DELAYED_MOVES.get(da["move"], {})
                    power  = da.get("power", cfg.get("power", 120))
                    atq_sp = da["atq_sp"]
                    def_sp = max(1, def_side.stats.get("def_sp", 50))
                    level  = da["level"]
                    raw    = ((2 * level / 5 + 2) * power * atq_sp / def_sp) / 50 + 2
                    dmg    = max(1, int(raw * _rnd.uniform(0.85, 1.0)))
                    def_side.hp_actual = max(0, def_side.hp_actual - dmg)
                    hit = cfg.get("msg_impacto", "¡El ataque llegó!")
                    log.append(
                        f"  🔮 {hit.format(attacker=da['attacker_name'], defender=def_side.name)} "
                        f"({dmg} daño)\n"
                    )
            else:
                remaining.append(da)
        att_side.delayed_attacks = remaining
    
    # 7. Bayas de combate que se activan automáticamente ──────────────────────
    for side in (side_a, side_b):
        obj = getattr(side, "objeto", None) or ""
        if not obj:
            continue
        hp_ratio = side.hp_actual / max(side.hp_max, 1)

        # Baya Zanama (Sitrus) → cura 25% HP si < 50%
        if obj == "baya zanama" and hp_ratio < 0.50:
            healed = max(1, side.hp_max // 4)
            side.hp_actual = min(side.hp_max, side.hp_actual + healed)
            side.objeto = None
            side.baya_consumida = obj
            log.append(f"  🍓 ¡La Baya Zanama de <b>{side.name}</b> restauró {healed} HP!\n")

        # Baya Ligaya (Oran) → cura 10 HP si < 50%
        elif obj == "baya ligaya" and hp_ratio < 0.50:
            healed = min(10, side.hp_max - side.hp_actual)
            side.hp_actual = min(side.hp_max, side.hp_actual + healed)
            side.objeto = None
            side.baya_consumida = obj
            log.append(f"  🍓 ¡La Baya Ligaya de <b>{side.name}</b> restauró {healed} HP!\n")

        # Bayas de boost de stat al 25% HP
        _BAYA_BOOST = {
            "baya latano":  ("atq",    1),
            "baya gonlan":  ("def",    1),
            "baya yapati":  ("vel",    1),
            "baya actania": ("atq_sp", 1),
            "baya algama":  ("def_sp", 1),
        }
        if obj in _BAYA_BOOST and hp_ratio < 0.25:
            stat, delta = _BAYA_BOOST[obj]
            side.stat_stages[stat] = min(6, side.stat_stages.get(stat, 0) + delta)
            side.objeto = None
            side.baya_consumida = obj
            log.append(
                f"  🍓 ¡La {obj.title()} de <b>{side.name}</b>"
                f" subió su {stat.upper()}!\n"
            )


# ─────────────────────────────────────────────────────────────────────────────
# apply_entry_ability  — habilidades al entrar en combate
# ─────────────────────────────────────────────────────────────────────────────

def apply_entry_ability(
    entering:  "UniversalSide",
    opponent:  "UniversalSide",
    field,
    log:       list,
) -> None:
    """
    Dispara la habilidad de entrada del Pokémon que acaba de salir a combatir.
    Cubre: Impostor, Intimidación, climas (Sequía, Llovizna, Chorro Arena, Nevada),
    terrenos (Electrogénesis, Herbogénesis, Psicogénesis, Nebulogénesis),
    Rastreo, Mimetismo.

    Modifica entering / opponent / field in-place.
    NO toca la BD (el llamador persiste cambios si hace falta).
    """
    if not entering.ability:
        return
    hab  = entering.ability.lower().replace(" ", "").replace("-", "")
    shim = _BattleShim(field, entering, opponent)

    # ── Impostor (Ditto) ──────────────────────────────────────────────────────
    if hab == "impostor":
        _apply_impostor(entering, opponent, log)
        return

    # ── Intimidación ──────────────────────────────────────────────────────────
    if hab in ("intimidacion", "intimidation"):
        apply_stage_change("atq", -1, opponent.stat_stages, opponent.name, log)
        log.append(
            f"  😤 ¡La Intimidación de {entering.name} bajó el Ataque de {opponent.name}!\n"
        )
        return

    # ── Climas de entrada ─────────────────────────────────────────────────────
    _CLIMAS = {
        "sequia":      ("sun",  5), "drought":     ("sun",  5),
        "llovizna":    ("rain", 5), "drizzle":     ("rain", 5),
        "chorroarena": ("sand", 5), "sandstream":  ("sand", 5),
        "nevada":      ("snow", 5), "snowwarning": ("snow", 5),
    }
    if hab in _CLIMAS:
        w_key, w_turns = _CLIMAS[hab]
        activate_weather(shim, w_key, w_turns, entering.name, log)
        return

    # ── Terrenos de entrada ───────────────────────────────────────────────────
    _TERRENOS = {
        "electrogénesis": ("electric", 5), "electricsurge": ("electric", 5),
        "herbogénesis":   ("grassy",   5), "grassysurge":   ("grassy",   5),
        "psicogénesis":   ("psychic",  5), "psychicsurge":  ("psychic",  5),
        "nebulogénesis":  ("misty",    5), "mistysurge":    ("misty",    5),
    }
    if hab in _TERRENOS:
        t_key, t_turns = _TERRENOS[hab]
        activate_terrain(shim, t_key, t_turns, entering.name, log)
        return

    # ── Rastreo (copia habilidad del rival) ───────────────────────────────────
    if hab in ("rastreo", "trace"):
        entering.ability = opponent.ability
        log.append(
            f"  🔍 ¡{entering.name} copió la habilidad «{opponent.ability}» "
            f"de {opponent.name}!\n"
        )
        return

    # ── Mimetismo (tipo según terreno activo) ─────────────────────────────────
    if hab in ("mimetismo", "mimicry"):
        _T = {"electric": "Eléctrico", "grassy": "Planta",
              "misty": "Hada", "psychic": "Psíquico"}
        new_type = _T.get(getattr(field, "terrain", None) or "", "Normal")
        entering.types = [new_type]
        log.append(f"  🎭 {entering.name} cambió su tipo a {new_type} (Mimetismo).\n")
        return

def apply_entry_abilities_ordered(
    side_a:  "UniversalSide",
    side_b:  "UniversalSide",
    field,
    log:     list,
) -> None:
    """
    Dispara las habilidades de entrada de ambos bandos en orden de velocidad.
    El más rápido aplica primero → el más lento sobreescribe al final.
    Resultado: el Pokémon más LENTO impone su clima (comportamiento oficial).
    """
    vel_a = BattleUtils.effective_speed(
        side_a.stats.get("vel", 50), side_a.stat_stages.get("vel", 0)
    )
    vel_b = BattleUtils.effective_speed(
        side_b.stats.get("vel", 50), side_b.stat_stages.get("vel", 0)
    )

    if vel_a >= vel_b:
        apply_entry_ability(side_a, side_b, field, log)
        apply_entry_ability(side_b, side_a, field, log)
    else:
        apply_entry_ability(side_b, side_a, field, log)
        apply_entry_ability(side_a, side_b, field, log)

def _apply_impostor(ditto, target, log):
    """
    Impostor / Transformación:
    - Copia stats ofensivas/defensivas (NO la stat HP).
    - Copia tipos, movimientos, etapas de stat y habilidad del rival.
    - Conserva el HP actual y hp_max originales (regla oficial).
    - El objeto equipado no cambia (lo gestiona el adaptador).
    """
    hp_actual_orig = ditto.hp_actual
    hp_max_orig    = ditto.hp_max

    # Stats: copiar todo excepto HP, luego restaurar el HP stat original
    new_stats       = {k: v for k, v in target.stats.items() if k != "hp"}
    new_stats["hp"] = hp_max_orig
    ditto.stats       = new_stats

    ditto.types       = list(target.types)
    ditto.moves       = list(target.moves)
    ditto.stat_stages = dict(target.stat_stages)
    ditto.ability     = target.ability      # también se copia la habilidad

    # HP intacto — no cambia al transformarse
    ditto.hp_actual = hp_actual_orig
    ditto.hp_max    = hp_max_orig

    log.append(
        f"  🔄 ¡<b>{ditto.name}</b> se transformó en "
        f"<b>{target.name}</b>!\n"
    )

def handle_two_turn(attacker, field, mk: str, log: list) -> bool:
    """
    Gestiona carga y recarga ANTES de ejecutar el movimiento.
    Retorna True si el turno debe ser SALTADO (no ejecutar el movimiento).

    Llamar al INICIO de apply_move(), justo después de calcular `mk`.
    """
    nombre = f"<b>{getattr(attacker, 'name', 'Pokémon')}</b>"

    # ── El atacante está en turno de RECARGA (post Hiper Rayo) ───────────────
    if getattr(attacker, "recharge_pending", False):
        attacker.recharge_pending = False
        log.append(f"  ⚡ ¡{nombre} necesita recargarse!\n")
        return True   # turno perdido

    # ── El atacante tiene carga PENDIENTE de un turno anterior ───────────────
    charged = getattr(attacker, "charging_move", None)
    if charged is not None:
        if charged == mk:
            # Es el segundo turno: limpiar y dejar ejecutar
            attacker.charging_move = None
            return False  # ejecutar normalmente
        else:
            # Cambió de movimiento: cancelar carga
            attacker.charging_move = None
            log.append(f"  ❌ {nombre} interrumpió su carga.\n")
            return True

    # ── El movimiento es de 2 turnos y este es el PRIMER TURNO ───────────────
    if mk in TWO_TURN_MOVES:
        cfg = TWO_TURN_MOVES[mk]
        weather = getattr(field, "weather", None)
        # Bajo sol, solarbeam/solarblade se ejecutan sin carga
        if cfg["skip_weather"] and weather == cfg["skip_weather"]:
            return False  # ejecutar directamente
        # Iniciar carga
        attacker.charging_move = mk
        msg_carga = cfg.get("msg_carga", f"¡{nombre} está cargando!")
        log.append(f"  ⚡ {msg_carga.format(nombre=nombre)}\n")
        return True   # turno de carga, no ejecutar aún

    return False  # movimiento normal


def register_recharge(attacker, mk: str) -> None:
    """
    Marca al atacante para perder el siguiente turno si el movimiento
    es de recarga (Hiper Rayo, etc.).
    Llamar al FINAL de apply_move(), justo antes del return.
    """
    if mk in RECHARGE_MOVES:
        attacker.recharge_pending = True
