# -*- coding: utf-8 -*-
"""
Sistema de Combate contra Pokémon Salvajes - Versión Profesional
==================================================================

Características:
- Sprite animado desconocido al aparecer
- Validación completa antes de combatir
- Creación de Pokémon salvaje al iniciar combate
- Niveles consistentes con evoluciones
- Movimientos apropiados para el nivel
- Menú completo de combate (Combate/Mochila/Equipo/Huir)
- Gestión de mensajes y estados
"""

import logging
import random
import math
import time
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from telebot import types
import threading
import datetime
from pokemon.services import (
    pokemon_service, 
    spawn_service, 
    pokedex_service,
    movimientos_service,
    items_service,
    evolucion_service)
from pokemon.experience_system import ExperienceSystem
from funciones import user_service, economy_service
from database import db_manager
from pokemon.battle_engine import (
    # Core
    BattleUtils,
    DamageResult,
    stage_multiplier,
    resolve_damage_move,
    apply_stage_change,
    determine_turn_order,
    # Campo
    WEATHER_INFO,
    TERRAIN_INFO,
    ROOM_INFO,
    STATUS_ICONS,
    # Funciones de campo
    apply_weather_boost,
    apply_terrain_boost,
    is_grounded,
    activate_weather,
    activate_terrain,
    tick_field_turns,
    # Ailments y turn flow
    can_apply_ailment_in_field,
    apply_ailment,
    check_can_move,
     # ── Datos de movimientos (fuente de verdad) ──────────────────────────────
    MOVE_EFFECTS,
    _HIGH_CRIT_MOVES,
    SECONDARY_AILMENTS,
    DRAIN_MOVES,
    RECOIL_MOVES,
    MOVE_NAMES_ES,
    # Adaptación al nuevo sistema
    UniversalSide,
    # ── Peso, Magic Guard, Skill Link (añadidos en el fix de habilidades) ──
    get_peso_pokemon,
    calcular_poder_lowkick,
    calcular_poder_heavyslam,
    _LOWKICK_MOVES,
    _HEAVYSLAM_MOVES,
    tiene_magic_guard,
    apply_move, 
    apply_end_of_turn, 
    apply_entry_ability,
    check_confusion,
)
from pokemon.battle_adapter import (
          side_from_wild, side_from_player, sync_wild_side, sync_player_side,)
from pokemon.battle_ui import build_pokemon_line
from pokemon.services.pokedex_service import pokedex_service as _pdx_svc

# ── Modificadores de estado Gen 6+ ───────────────────────────────────────────
# Modificadores de estado — Gen 6+ / Gen 9
# Claves: los mismos códigos que usa battle.wild_status
_STATUS_CATCH_BONUS: dict[str, float] = {
    "slp": 2.5,   # Dormido   — mayor ventana para atrapar
    "frz": 2.5,   # Congelado
    "par": 1.5,   # Paralizado
    "brn": 1.5,   # Quemado
    "psn": 1.5,   # Envenenado
    "tox": 1.5,   # Tóxico
}

CATCH_RATE_LEGENDARIOS_OVERRIDE: dict[int, int] = {
    # Gen 1
    144: 3,   # Articuno
    145: 3,   # Zapdos
    146: 3,   # Moltres
    150: 3,   # Mewtwo
    151: 45,  # Mew (mítico, algo más fácil)
    # Gen 2
    243: 3, 244: 3, 245: 3,  # Perros legendarios
    249: 3,   # Lugia
    250: 3,   # Ho-Oh
    251: 45,  # Celebi
    # Gen 3
    377: 3, 378: 3, 379: 3,  # Regis
    380: 3, 381: 3,           # Lati@s
    382: 5, 383: 5, 384: 3,  # Kyogre/Groudon/Rayquaza
    385: 3,   # Jirachi
    386: 3,   # Deoxys
    # Gen 4
    480: 3, 481: 3, 482: 3,  # Uxie/Mesprit/Azelf
    483: 5, 484: 5,           # Dialga/Palkia
    485: 3,   # Heatran
    486: 3,   # Regigigas
    487: 3,   # Giratina
    488: 100, # Cresselia (más fácil, oficial)
    489: 3, 490: 3,           # Phione/Manaphy
    491: 3,   # Darkrai
    492: 45,  # Shaymin
    493: 3,   # Arceus
    # Gen 5
    638: 3, 639: 3, 640: 3,  # Espada/Cuerda/Hacha
    641: 3, 642: 3,           # Tornadus/Thundurus
    643: 3, 644: 3,           # Reshiram/Zekrom
    645: 3,   # Landorus
    646: 3,   # Kyurem
    647: 3,   # Keldeo
    649: 3,   # Genesect
    # Gen 6
    716: 3, 717: 3,           # Xerneas/Yveltal
    718: 3,   # Zygarde
    719: 3,   # Diancie
    720: 3,   # Hoopa
    721: 3,   # Volcanion
    # Gen 7
    785: 45, 786: 45, 787: 45, 788: 45,  # Tapus (algo más fácil)
    789: 45, 790: 45,                      # Cosmog línea
    791: 45, 792: 45,                      # Solgaleo/Lunala
    800: 3,   # Necrozma
    # Gen 8
    888: 3, 889: 3,           # Zacian/Zamazenta
    890: 3,   # Eternatus
    # Gen 9
    1001: 3, 1002: 3, 1003: 3, 1004: 3,  # Paradox
    1007: 3, 1008: 3,                      # Koraidon/Miraidon
}

# IDs de Ultra Entes (Gen 7). La Beast Ball da 5× a estos y 0.1× al resto.
# Fuente: Bulbapedia — "Ultra Beast"
_ULTRA_BEAST_IDS: frozenset[int] = frozenset({
    793, 794, 795, 796, 797, 798, 799, 800,  # Nihilego … Stakataka (Gen 7 originals)
    803, 804, 805, 806,                        # Poipole, Naganadel, Stakataka, Blacephalon
})

# ── Timer Ball: fórmula oficial Gen 6+ ───────────────────────────────────────
def _timer_ball_bonus(turn_number: int) -> float:
    """
    Timer Ball: +1229/4096 ≈ +0.3 por turno, cap 4.0.
    A partir del turno 30 el ratio ya es 4.0.
    """
    return min(4.0, 1.0 + turn_number * (1229 / 4096))

def _calcular_ball_ratio(
        pokeball_nombre: str,
        condicion:       str,
        item_data:       dict,
        wild,
        turn_number:     int,
        user_id:         int,
) -> float:
    """
    Calcula el multiplicador real de la Poké Ball para la fórmula de captura.

    Balls sin condición (pokeball/greatball/ultraball): devuelve base_ratio.
    Balls condicionales: evalúa la condición; si no se cumple devuelve 1.0.
    """
    base_ratio: float = float(item_data.get("ratio", 1.0))

    # ── Sin condición especial ────────────────────────────────────────────────
    # pokeball (1×), greatball (1.5×), ultraball (2×), premierball (1×), etc.
    if not condicion:
        return base_ratio

    # ── Quick Ball: 5× turno 1, 1× resto ─────────────────────────────────────
    if condicion == "primer_turno":
        return 5.0 if turn_number <= 1 else 1.0

    # ── Timer Ball: crece por turno, cap 4× ──────────────────────────────────
    if condicion == "turnos":
        return min(4.0, 1.0 + turn_number * (1229 / 4096))

    # ── Nest Ball: (41 − nivel) / 10, sin truncar, mínimo 1× ─────────────────
    # Fórmula oficial Gen 8+: valor float, no math.floor().
    # Nv 1→4.0  Nv 5→3.6  Nv10→3.1  Nv20→2.1  Nv30→1.1  Nv31+→1.0
    if condicion in ("nivel_bajo", "bajo_nivel"):
        nivel = getattr(wild, "nivel", 31)
        if nivel <= 30:
            return max(1.0, (41 - nivel) / 10)
        return 1.0

    # ── Net Ball: 3.5× vs Agua o Bicho ───────────────────────────────────────
    if condicion in ("agua_bicho", "bug_water"):
        if any(t in getattr(wild, "tipos", []) for t in ("Agua", "Bicho")):
            return 3.5
        return 1.0

    # ── Repeat Ball: 3.5× si el usuario ya capturó esa especie ───────────────
    if condicion == "capturado":
        try:
            result = db_manager.execute_query(
                "SELECT COUNT(*) as total FROM POKEMON_USUARIO "
                "WHERE userID = ? AND pokemonID = ?",
                (user_id, wild.pokemon_id),
            )
            ya_capturado = bool(result and result[0]["total"] > 0)
        except Exception:
            ya_capturado = False
        return 3.5 if ya_capturado else 1.0

    # ── Dusk Ball: 3.5× de noche (20h–6h), 1× de día ────────────────────────
    if condicion == "noche":
        hora = datetime.datetime.now().hour
        return 3.5 if (hora >= 20 or hora < 6) else 1.0

    # ── Beast Ball: 5× vs Ultra Entes, 0.1× vs cualquier otro ───────────────
    if condicion == "ultraente":
        if wild.pokemon_id in _ULTRA_BEAST_IDS:
            return 5.0
        return 0.1   # penalización oficial vs Pokémon normales
 
    # ── Cualquier otra condición: devolver base_ratio ─────────────────────────
    # Cubre diveball (agua), noche_cueva, etc.
    return base_ratio

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS Y TIPOS
# ============================================================================

class BattleState(Enum):
    """Estados posibles de una batalla"""
    WAITING = "waiting"
    ACTIVE = "active"
    PLAYER_WIN = "player_win"
    PLAYER_LOSE = "player_lose"
    POKEMON_CAPTURED = "pokemon_captured"
    FLED = "fled"


class BattleAction(Enum):
    """Acciones posibles en batalla"""
    ATTACK = "attack"
    USE_ITEM = "use_item"
    SWITCH_POKEMON = "switch"
    RUN = "run"


# ============================================================================
# MODELOS DE DATOS
# ============================================================================

@dataclass
class WildPokemon:
    """Representa un Pokémon salvaje en combate"""
    pokemon_id:   int
    nivel:        int
    nombre:       str
    hp_max:       int
    hp_actual:    int
    stats:        Dict[str, int]
    moves:        List[str]
    tipos:        List[str] = field(default_factory=lambda: ["Normal"])
    shiny:        bool = False
    sexo:         Optional[str] = None   # "M", "F" o None
    capture_rate: int = 45               # catch rate oficial de la especie
    charging_move:    Optional[str] = None
    recharge_pending: bool          = False

    def __post_init__(self):
        if self.hp_actual > self.hp_max:
            self.hp_actual = self.hp_max
        if not self.moves:
            self.moves = ["Tackle"]
    
    def nombre_display(self) -> str:
        """Retorna el nombre con emoji de género: 'Pikachu ♂'"""
        sexo_emoji = {"M": "♂", "F": "♀"}.get(self.sexo or "", "")
        return f"{self.nombre} {sexo_emoji}".strip()


@dataclass
class BattleData:
    user_id:           int
    thread_id:         int
    state:             "BattleState"
    wild_pokemon:      WildPokemon
    player_pokemon_id: int
    turn_number:       int = 0
    flee_attempts:     int = 0
    message_id:        Optional[int] = None   # mensaje de texto con menú y botones
    sprite_message_id: Optional[int] = None   # mensaje de foto/GIF (solo aparición)
    last_action:       Optional[str] = None
    created_at:        float = field(default_factory=time.time)
    battle_log:        list  = field(default_factory=list)
    # Pokémon que participaron en la batalla (para repartir EXP)
    participant_ids: set = field(default_factory=set)
    wild_stat_stages: Dict[str, int] = field(
         default_factory=lambda: {"atq": 0, "def": 0, "atq_sp": 0, "def_sp": 0, "vel": 0})
    player_stat_stages: Dict[str, int] = field(
        default_factory=lambda: {"atq": 0, "def": 0, "atq_sp": 0, "def_sp": 0, "vel": 0})
    turn_timer: Optional[object] = field(default=None, repr=False)
    # Entradas temporales de log por turno (no se muestran en repr)
    _last_player_entry: Optional[str] = field(default=None, repr=False)
    _last_enemy_entry:  Optional[str] = field(default=None, repr=False)
    # (threading.Timer — no serializable, excluir de repr)
    group_chat_id:     Optional[int] = None
    group_message_id:  Optional[int] = None
    # ── Estado de alteración (status conditions) ─────────────────────────────
    wild_status:          Optional[str] = None  # "par","brn","frz","slp","psn","tox"
    player_status:        Optional[str] = None
    wild_sleep_turns:     int = 0   # turnos restantes dormido
    player_sleep_turns:   int = 0
    wild_toxic_counter:   int = 0   # contador acumulativo de Tóxico
    player_toxic_counter: int = 0
    wild_yawn_counter:    int = 0   # 1 → duerme al final del turno
    player_yawn_counter:  int = 0
    wild_confusion_turns:   int = 0   # turnos restantes de confusión del salvaje
    player_confusion_turns: int = 0   # turnos restantes de confusión del jugador
    # ── Drenadoras (Leechseed) ────────────────────────────────────────────────
    wild_leechseeded:     bool = False  # True → el wild está sembrado
    player_leechseeded:   bool = False  # True → el jugador está sembrado
    # ── Estado de Transformar (temporal, solo dura la batalla) ───────────────────
    player_transformed:          bool              = False
    player_transform_stats:      Optional[dict]    = field(default=None)
    player_transform_moves:      Optional[list]    = field(default=None)
    player_transform_types:      Optional[list]    = field(default=None)
    player_transform_species_id: Optional[int]  = None
    player_transform_nombre:     Optional[str]  = None
    # ── Status persistente por Pokémon individual (clave = id_unico) ─────────────
    # Permite que veneno, sueño, drenadoras, etc. persistan al salir y volver.
    # Formato: { pokemon_id: {"status": ..., "sleep_turns": ...,
    #                          "toxic_counter": ..., "leechseeded": ...} }
    _pokemon_statuses: dict = field(default_factory=dict)
    # ── Faint switch ─────────────────────────────────────────────────────────
    # True  → jugador eligiendo reemplazo tras derrota; salvaje NO ataca.
    # False → switch voluntario (hard switch); salvaje SÍ ataca.
    awaiting_faint_switch: bool = False
    # ── Campo de batalla ─────────────────────────────────────────────────────
    weather:         Optional[str] = None   # "sun"|"rain"|"sand"|"snow"|"fog"
    weather_turns:   int = 0                # turnos restantes (0 = permanente)
    terrain:         Optional[str] = None   # "electric"|"grassy"|"misty"|"psychic"
    terrain_turns:   int = 0
    # Espacios (pseudo-climas que no se solapan con weather)
    trick_room:      bool = False
    trick_room_turns: int = 0
    gravity:         bool = False
    gravity_turns:   int = 0
    magic_room:      bool = False
    magic_room_turns: int = 0
    wonder_room:     bool = False
    wonder_room_turns: int = 0
    # ── Pivot pendiente (U-turn/Volt Switch: daño hecho, jugador debe elegir) ─
    awaiting_pivot_switch: bool = False
    # Snapshot de posiciones para restaurar al terminar la batalla
    # {pokemon_id (id_unico): posicion_equipo_original}
    posiciones_originales: dict = field(default_factory=dict)
    player_crit_stage: int = 0
    wild_crit_stage:   int = 0
    # ── Mecánicas de 2 turnos del jugador ────────────────────────────────────
    player_charging_move:    Optional[str] = None
    player_recharge_pending: bool          = False
    # ── Trampas de entrada ────────────────────────────────────────────────────
    player_stealth_rock: bool = False   # Trampa Rocas en el lado del jugador
    player_spikes:       int  = 0       # Púas (1-3 capas)
    player_toxic_spikes: int  = 0       # Púas Tóxicas (1-2 capas)
    player_sticky_web:   bool = False   # Telaraña
    wild_stealth_rock:   bool = False   # Trampa Rocas en el lado del wild
    wild_spikes:         int  = 0
    wild_toxic_spikes:   int  = 0
    wild_sticky_web:     bool = False

    
    def is_expired(self, timeout: int = 300) -> bool:
        """Verifica si la batalla ha expirado (5 min default)"""
        return time.time() - self.created_at > timeout

# ============================================================================
# GENERADOR DE POKÉMON SALVAJES
# ============================================================================

class WildPokemonGenerator:
    """Genera Pokémon salvajes con datos consistentes"""
    
    @staticmethod
    def get_evolution_stage(pokemon_id: int, level: int) -> int:
        """
        Devuelve el ID de la especie correcta para el nivel dado,
        recorriendo toda la cadena evolutiva de forma iterativa.

        Ejemplo: get_evolution_stage(4, 40)
          4 (Charmander) evoluciona en 16 → pasa a 5
          5 (Charmeleon) evoluciona en 36 → pasa a 6
          6 (Charizard)  sin evolución por nivel → devuelve 6  ✅

        Solo sigue evoluciones con metodo='nivel'. Piedras, amistad, etc.
        no se aplican a los salvajes y se ignoran.
        """
        try:
            current_id = pokemon_id
            # Protección contra bucles infinitos (cadenas raras en los datos)
            for _ in range(10):
                linea = evolucion_service.evoluciones.get(str(current_id), [])
                # Buscar la primera evolución por nivel cuyo umbral se haya alcanzado
                evolucionado = False
                for evo in linea:
                    if evo.get("metodo") == "nivel":
                        evo_level = int(evo.get("nivel", 999))
                        if level >= evo_level:
                            current_id = int(evo["evoluciona_a"])
                            evolucionado = True
                            break  # reiniciar con el nuevo eslabón
                if not evolucionado:
                    break  # forma final para este nivel
            return current_id
        except Exception as e:
            logger.error(f"Error obteniendo evolución para {pokemon_id} nivel {level}: {e}")
            return pokemon_id
    
    @staticmethod
    def get_appropriate_moves(pokemon_id: int, level: int, max_moves: int = 4) -> List[str]:
        """
        Obtiene los movimientos más fuertes que el Pokémon puede aprender hasta ese nivel
        ✅ CORREGIDO: Type hints explícitos
        """
        try:
            # Paso 1: Obtener learnset
            learnset = movimientos_service.obtener_learnset(pokemon_id)
            
            if not learnset:
                return ["Tackle"]
            
            # Paso 2: Construir lista de movimientos con metadata
            # ✅ Type hint explícito: Lista de dicts
            available_moves: List[Dict[str, Any]] = []
            
            for lvl, moves in learnset.items():
                if lvl <= level:
                    for move_name in moves:
                        available_moves.append({
                            'nombre': move_name,
                            'nivel': lvl
                        })
            
            if not available_moves:
                return ["Tackle"]
            
            # Paso 3: Función helper con type hints
            def get_move_power(move_dict: Dict[str, Any]) -> int:
                """
                ✅ Type hint explícito en parámetro
                """
                move_name: str = move_dict['nombre']
                move_data: Optional[Dict] = movimientos_service.obtener_movimiento(move_name)
                
                if move_data:
                    power = move_data.get('poder', move_data.get('basePower', 0))
                    return power if isinstance(power, int) else 0
                
                return 0
            
            # Ordenar por poder (descendente)
            available_moves.sort(key=get_move_power, reverse=True)
            
            # Paso 4: Tomar los N más fuertes
            strongest_moves: List[str] = [m['nombre'] for m in available_moves[:max_moves]]
            
            return strongest_moves if strongest_moves else ["Tackle"]
            
        except Exception as e:
            logger.error(f"Error obteniendo movimientos: {e}")
            return ["Tackle"]
    
    @staticmethod
    def generate(
        pokemon_id: int,
        user_medals: int,
        shiny: bool = False,
        level: Optional[int] = None  
    ) -> Optional[WildPokemon]:
        """
        Genera un Pokémon salvaje completo
        
        Args:
            pokemon_id: ID base del Pokémon
            level: Nivel sugerido (será ajustado por medallas)
            user_medals: Número de medallas del jugador
            shiny: Si es shiny o no
            ✅ CORREGIDO: Ahora obtiene nombre del pokemon
        
        Returns:
            WildPokemon generado o None si falla
        """
        try:            
            # Ajustar nivel por medallas (5 + 3*medallas)
            if level is not None:
                adjusted_level = max(1, min(100, level))
            else:
                adjusted_level = max(5, min(100, 5 + (user_medals * 3)))
            
            # Obtener evolución correcta para este nivel
            correct_pokemon_id = WildPokemonGenerator.get_evolution_stage(
                pokemon_id,
                adjusted_level
            )
            
            # Obtener datos de Pokédex
            pokemon_data = pokedex_service.obtener_pokemon(correct_pokemon_id)
            if not pokemon_data:
                logger.warning(f"Pokémon {correct_pokemon_id} no encontrado en Pokédex, usando datos genéricos")
                return None
            
            # ✅ EXTRAER NOMBRE
            nombre = pokemon_data.get('nombre', f"Pokemon #{correct_pokemon_id}")
            stats_base = pokemon_data.get('stats_base', {})
            
            # Generar IVs aleatorios (0-31)
            ivs = {stat: random.randint(0, 31) 
                   for stat in ['hp', 'atq', 'def', 'atq_sp', 'def_sp', 'vel']}
            
            # ✅ Generar naturaleza ALEATORIA (no siempre Hardy)
            naturalezas = [
                "Hardy", "Lonely", "Brave", "Adamant", "Naughty",
                "Bold", "Docile", "Relaxed", "Impish", "Lax",
                "Timid", "Hasty", "Serious", "Jolly", "Naive",
                "Modest", "Mild", "Quiet", "Bashful", "Rash",
                "Calm", "Gentle", "Sassy", "Careful", "Quirky"
            ]
            naturaleza = random.choice(naturalezas)

            # Calcular stats finales
            stats = pokedex_service.calcular_stats(
                correct_pokemon_id,
                adjusted_level,
                ivs,
                {stat: 0 for stat in ivs},  # EVs en 0
                naturaleza  # Naturaleza neutral
            )
            
            # Obtener movimientos
            moves = WildPokemonGenerator.get_appropriate_moves(
                correct_pokemon_id,
                adjusted_level
            )
            # Asegurar que tenga al menos 1 movimiento
            if not moves:
                moves = ["Tackle"]
            
            tipos = pokemon_data.get('tipos', ["Normal"])   # ← NUEVA línea antes del return

            from pokemon.services.crianza_service import determinar_sexo as _det_sexo
            _capture_rate = int(pokemon_data.get("ratio_captura", 45))
            return WildPokemon(
                pokemon_id=correct_pokemon_id,
                nivel=adjusted_level,
                nombre=nombre,
                hp_max=stats['hp'],
                hp_actual=stats['hp'],
                stats=stats,
                moves=moves,
                tipos=tipos,
                shiny=shiny,
                sexo=_det_sexo(correct_pokemon_id),
                capture_rate=_capture_rate,
            )
            
        except Exception as e:
            logger.error(f"Error generando Pokémon salvaje: {e}", exc_info=True)
            return None

# Emojis por tipo (el campo 'tipo' ya viene en español desde movimientos_service)
MOVE_TYPE_EMOJI = {
    "Normal":    "⚪",
    "Fuego":     "🔥",
    "Agua":      "💧",
    "Planta":    "🌿",
    "Eléctrico": "⚡",
    "Hielo":     "🧊",
    "Lucha":     "🥊",
    "Veneno":    "☠️",
    "Tierra":    "🌍",
    "Volador":   "🌪️",
    "Psíquico":  "🔮",
    "Bicho":     "🐛",
    "Roca":      "🪨",
    "Fantasma":  "👻",
    "Dragón":    "🐉",
    "Siniestro": "🌑",
    "Acero":     "⚙️",
    "Hada":      "🌸",
}

# Emojis por categoría
MOVE_CAT_EMOJI = {
    "Físico":   "⚔️",
    "Especial": "✨",
    "Estado":   "💫",
}

def _get_battle_item_tipo(item_nombre: str) -> tuple[str, dict]:
    """
    Devuelve (tipo, item_data) para la categorización de ítems en la mochila
    de batalla. Combina items_service (claves españolas/legacy) con
    items_database_complete (claves en inglés), e infiere el tipo por
    sub-diccionario cuando ninguno lo declara explícitamente.
 
    Args:
        item_nombre: clave del ítem tal como está almacenada en el inventario.
 
    Returns:
        Tupla (tipo_str, item_data_dict). tipo_str puede ser '' si no se pudo
        determinar, pero nunca lanza excepción.
    """
    from pokemon.services import items_service as _its
 
    # ── 1. items_service (base española/legacy) ──────────────────────────────
    item_data: dict = _its.obtener_item(item_nombre) or {}
    tipo: str = item_data.get('tipo', '') or ''
    if tipo:
        return tipo, item_data
 
    # ── 2. items_database_complete (base inglesa) ────────────────────────────
    try:
        from pokemon.items_database_complete import (
            obtener_item_info,
            POKEBALLS_DB,
            MEDICINAS_DB,
            BAYAS_DB,
        )
        complete: dict = obtener_item_info(item_nombre) or {}
        if complete:
            if not item_data:
                item_data = complete
            tipo = complete.get('tipo', '') or ''
 
        # ── 3. Inferencia por sub-diccionario ─────────────────────────────────
        if not tipo:
            key = item_nombre.lower()
            if key in POKEBALLS_DB:
                tipo = 'pokeball'
            elif key in BAYAS_DB:
                tipo = 'baya'
            elif key in MEDICINAS_DB:
                tipo = 'medicina'
    except Exception:
        pass
 
    return tipo, item_data

def _apply_residual_effects(battle, log: list) -> None:
    """
    Adaptador de fin de turno.

    Construye los ResidualParticipant, delega el cálculo a
    calculate_residual_effects (función pura en battle_engine),
    luego aplica los resultados y persiste en BD.
    """
    from pokemon.battle_engine import (
        calculate_residual_effects,
        ResidualParticipant,
        WEATHER_IMMUNE_TYPES,
        WEATHER_INFO,
    )

    wild   = battle.wild_pokemon
    player = pokemon_service.obtener_pokemon(battle.player_pokemon_id)

    # ── Construir participantes ───────────────────────────────────────────────
    p_name     = (player.mote or player.nombre) if player else "?"
    p_max_hp   = (player.stats.get("hp", player.hp_actual) or player.hp_actual) if player else 1
    p_tipos    = []
    if player:
        try:
            from pokemon.services.pokedex_service import pokedex_service as _pdx
            p_tipos = _pdx.obtener_tipos(player.pokemonID)
        except Exception:
            p_tipos = ["Normal"]

    # ── Drenadoras (Leechseed) — drenaje de fin de turno ─────────────────────
    # Se resuelve antes de los efectos residuales normales (veneno, quemadura)
    # para respetar el orden canónico de Showdown.
    if wild and player:
        # Wild está sembrado → le drena HP y cura al jugador
        if getattr(battle, "wild_leechseeded", False) and wild.hp_actual > 0:
            leech_dmg = max(1, wild.hp_max // 8)
            wild.hp_actual = max(0, wild.hp_actual - leech_dmg)
            if player.hp_actual > 0:
                healed = min(leech_dmg, p_max_hp - player.hp_actual)
                if healed > 0:
                    new_p_hp = player.hp_actual + healed
                    player.hp_actual = new_p_hp
                    try:
                        db_manager.execute_update(
                            "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                            (new_p_hp, battle.player_pokemon_id),
                        )
                    except Exception as _le:
                        logger.error(f"Error leechseed curar jugador: {_le}")
            log.append(
                f"  🌿 Drenadoras le quitaron <b>{leech_dmg}</b> HP a "
                f"<b>{wild.nombre}</b>!\n"
            )

        # Jugador está sembrado → le drena HP y cura al wild
        if getattr(battle, "player_leechseeded", False) and player.hp_actual > 0:
            leech_dmg = max(1, p_max_hp // 8)
            new_p_hp  = max(0, player.hp_actual - leech_dmg)
            player.hp_actual = new_p_hp
            try:
                db_manager.execute_update(
                    "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                    (new_p_hp, battle.player_pokemon_id),
                )
            except Exception as _le:
                logger.error(f"Error leechseed dañar jugador: {_le}")
            if wild.hp_actual > 0:
                wild.hp_actual = min(wild.hp_max, wild.hp_actual + leech_dmg)
            log.append(
                f"  🌿 Drenadoras le quitaron <b>{leech_dmg}</b> HP a "
                f"<b>{p_name}</b>!\n"
            )

    part_a = ResidualParticipant(
        name          = wild.nombre if wild else "?",
        hp_actual     = wild.hp_actual if wild else 0,
        hp_max        = wild.hp_max if wild else 1,
        tipos         = getattr(wild, "tipos", ["Normal"]) if wild else ["Normal"],
        status        = battle.wild_status,
        toxic_counter = battle.wild_toxic_counter,
        yawn_counter  = battle.wild_yawn_counter,
    )

    part_b = ResidualParticipant(
        name          = p_name,
        hp_actual     = player.hp_actual if player else 0,
        hp_max        = p_max_hp,
        tipos         = p_tipos,
        status        = battle.player_status,
        toxic_counter = battle.player_toxic_counter,
        yawn_counter  = battle.player_yawn_counter,
    )

    # ── Calcular (función pura) ───────────────────────────────────────────────
    result = calculate_residual_effects(
        side_a                = part_a,
        side_b                = part_b,
        weather               = battle.weather,
        terrain               = battle.terrain,
        weather_immune_types  = WEATHER_IMMUNE_TYPES,
        weather_info          = WEATHER_INFO,
    )

    # ── Aplicar resultado a side_a (salvaje — sólo memoria) ──────────────────
    fx_a = result.side_a
    if wild and fx_a.hp_delta != 0:
        # No curar un wild ya debilitado
        if wild.hp_actual > 0 or fx_a.hp_delta < 0:
            wild.hp_actual = max(0, min(wild.hp_max, wild.hp_actual + fx_a.hp_delta))
    if wild:
        battle.wild_toxic_counter = fx_a.new_toxic_counter
        # Bostezo
        if battle.wild_yawn_counter > 0:
            battle.wild_yawn_counter -= 1
        if fx_a.trigger_sleep:
            apply_ailment(battle, "slp", target_is_wild=True,
                          target_name=wild.nombre, log=log)
    log.extend(fx_a.log)

    # ── Aplicar resultado a side_b (jugador — persiste en BD) ────────────────
    fx_b = result.side_b
    if player and fx_b.hp_delta != 0:
        # CRÍTICO: no curar ni dañar a un Pokémon ya debilitado (hp == 0).
        if player.hp_actual > 0 or fx_b.hp_delta < 0:
            # Magic Guard: el jugador es inmune a daño indirecto (veneno, clima…)
            _player_hab = getattr(player, "habilidad", "") or ""
            if fx_b.hp_delta < 0 and tiene_magic_guard(_player_hab):
                pass  # daño indirecto bloqueado por Magic Guard
            else:
                new_hp = max(0, min(p_max_hp, player.hp_actual + fx_b.hp_delta))
                player.hp_actual = new_hp
                try:
                    db_manager.execute_update(
                        "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                        (new_hp, battle.player_pokemon_id),
                    )
                except Exception as _e:
                    logger.error(f"Error residual HP jugador: {_e}")
    if player:
        battle.player_toxic_counter = fx_b.new_toxic_counter
        # Bostezo
        if battle.player_yawn_counter > 0:
            battle.player_yawn_counter -= 1
        if fx_b.trigger_sleep:
            apply_ailment(battle, "slp", target_is_wild=False,
                          target_name=p_name, log=log)
    log.extend(fx_b.log)

    # ── Tick del campo (clima y terreno) — ya lo hace tick_field_turns ────────
    tick_field_turns(battle, log)

# ============================================================================
# GESTOR DE BATALLAS
# ============================================================================

class WildBattleManager:
    """Gestor principal de batallas contra Pokémon salvajes"""
    
    def __init__(self):
        self.active_battles: Dict[int, BattleData] = {}
        self._cleanup_interval = 60  # Limpiar batallas expiradas cada 60s
        self._last_cleanup = time.time()
    
    def _cleanup_expired_battles(self):
        """Limpia batallas expiradas"""
        if time.time() - self._last_cleanup < self._cleanup_interval:
            return
        
        expired = [
            uid for uid, battle in self.active_battles.items()
            if battle.is_expired()
        ]
        
        for uid in expired:
            del self.active_battles[uid]
            logger.info(f"[BATTLE] Batalla expirada limpiada: user {uid}")
        
        self._last_cleanup = time.time()
    
    def has_active_battle(self, user_id: int) -> bool:
        """Verifica si el usuario tiene una batalla activa"""
        self._cleanup_expired_battles()
        return user_id in self.active_battles
    
    def get_battle(self, user_id: int) -> Optional[BattleData]:
        """Obtiene la batalla activa del usuario"""
        return self.active_battles.get(user_id)
    
    def validate_can_battle(self, user_id: int) -> Tuple[bool, str]:
        """
        Valida si el usuario puede iniciar una batalla
        
        Returns:
            (puede_combatir, mensaje_error)
        """
        try:
            # 1. Verificar que tenga Pokémon
            team = pokemon_service.obtener_equipo(user_id)
            if not team:
                return False, (
                    "❌ No tienes Pokémon en tu equipo.\n"
                    "Usa /profesor para obtener tu Pokémon inicial."
                )
            
            # 2. Verificar que al menos uno tenga vida
            has_healthy_pokemon = any(p.hp_actual > 0 for p in team)
            if not has_healthy_pokemon:
                return False, (
                    "❌ Todos tus Pokémon están debilitados.\n"
                    "Ve al Centro Pokémon para curarlos.\n"
                    "Usa: /pokemon → Centro Pokémon"
                )
            
            # 3. Verificar que no tenga batalla activa
            if self.has_active_battle(user_id):
                return False, "❌ Ya tienes una batalla en curso."
            
            return True, ""
            
        except Exception as e:
            logger.error(f"Error validando batalla: {e}")
            return False, f"❌ Error: {str(e)}"
    
    def start_battle(
        self,
        user_id: int,
        thread_id: int,
        spawn_data: Dict[str, Any],
        bot
    ) -> Tuple[bool, str]:
        """
        Inicia una batalla contra un Pokémon salvaje
        
        Args:
            user_id: ID del usuario
            thread_id: ID del hilo/canal
            spawn_data: Datos del spawn activo
            bot: Instancia del bot
        
        Returns:
            (exito, mensaje)
        """
        try:
            # Validar que puede combatir
            can_battle, error_msg = self.validate_can_battle(user_id)
            if not can_battle:
                return False, error_msg
            
            # Obtener nivel del Pokémon.
            # spawn_data llega con pokemon_id, shiny y nivel (puede ser None).
            # Para /salvaje no hay nada en spawn_service; para spawns públicos
            # el nivel ya viene calculado desde el callback del grupo.
            nivel = spawn_data.get("nivel")
            if nivel is None:
                nivel = spawn_service.calcular_nivel_spawn_por_id(
                    pokemon_id=spawn_data["pokemon_id"],
                    user_id=user_id,
                )

            # Obtener medallas del usuario
            medals = self._count_user_medals(user_id)
            
            # ── Evaluar shiny con multiplicador del usuario ───────────────────────────
            # Si el spawn ya llegó shiny (decidido en canal sin user_id), se respeta.
            # Si no, se le da al usuario una segunda oportunidad con su multiplicador.
            _spawn_shiny = spawn_data.get('shiny', False)
            if not _spawn_shiny:
                try:
                    from funciones.pokedex_usuario import get_shiny_multiplier
                    from config import POKEMON_SPAWN_CONFIG
                    _prob = POKEMON_SPAWN_CONFIG.get("probabilidad_shiny", 1 / 4096)
                    _mult = get_shiny_multiplier(user_id)
                    if _mult > 1.0:
                        _spawn_shiny = random.random() < _prob * _mult
                except Exception:
                    pass

            # Generar Pokémon salvaje
            wild_pokemon = WildPokemonGenerator.generate(
                pokemon_id=spawn_data['pokemon_id'],
                user_medals=medals,
                shiny=_spawn_shiny,
                level=nivel
            )
            
            if not wild_pokemon:
                return False, "❌ Error generando Pokémon salvaje."
            
            # Obtener primer Pokémon con vida del equipo
            team = pokemon_service.obtener_equipo(user_id)
            active_pokemon = next(p for p in team if p.hp_actual > 0)
            
            if not active_pokemon.id_unico:
                return False, "❌ Error: Pokémon sin ID válido"
            
            # Crear datos de batalla
            battle = BattleData(
                user_id=user_id,
                thread_id=thread_id,
                state=BattleState.ACTIVE,
                wild_pokemon=wild_pokemon,
                player_pokemon_id=active_pokemon.id_unico
            )
            # Snapshot de posiciones originales — leer directo de BD porque el
            # dataclass Pokemon no expone posicion_equipo como atributo.
            _equipo_rows = db_manager.execute_query(
                "SELECT id_unico, posicion_equipo "
                "FROM POKEMON_USUARIO WHERE userID = ? AND en_equipo = 1",
                (user_id,),
            )
            battle.posiciones_originales = {
                row["id_unico"]: row["posicion_equipo"]
                for row in (_equipo_rows or [])
            }
            # Asegurar que todos tengan posición asignada
            pokemon_service.inicializar_posiciones_equipo(user_id)
                    
            self.active_battles[user_id] = battle
            # Registrar el pokémon inicial como participante
            battle.participant_ids.add(active_pokemon.id_unico)
            
            # Enviar menú de batalla por privado
            self._send_battle_menu(battle, bot)
            
            logger.info(
                f"[BATTLE] Iniciada: Usuario {user_id} vs "
                f"{wild_pokemon.nombre} Nv.{wild_pokemon.nivel}"
            )
            
            return True, (
                f"⚔️ ¡Batalla iniciada!\n\n"
                f"🔴 {wild_pokemon.nombre} Nv.{wild_pokemon.nivel}\n\n"
                f"Revisa tu chat privado para controlar la batalla."
            )
            
        except Exception as e:
            logger.error(f"Error iniciando batalla: {e}", exc_info=True)
            return False, f"❌ Error: {str(e)}"
    
    def _count_user_medals(self, user_id: int) -> int:
        """
        Cuenta las medallas del usuario.
        Siempre retorna 0 ante cualquier error (tabla inexistente, columna
        incorrecta, usuario sin fila, etc.) para que el nivel mínimo de los
        Pokémon salvajes sea 5 en lugar de propagar la excepción.
        """
        try:
            result = db_manager.execute_query(
                "SELECT COUNT(*) as count FROM MEDALLAS_USUARIOS WHERE userID = ?",
                (user_id,)
            )
            if result and len(result) > 0:
                return int(result[0].get('count', 0))
            return 0
        except Exception:
            # Tabla no existente, columna incorrecta, o cualquier error de BD:
            # silenciar y retornar 0 medallas.
            return 0
        
    def _edit_battle_message(self, bot, user_id: int, message_id: Optional[int],
                              text: str, keyboard=None, parse_mode: str = "HTML"):
        """
        Edita el mensaje de texto de batalla (message_id).
        Ya no intenta editar captions de fotos — el sprite es un mensaje separado.
        """
        if not message_id:
            return False
        kwargs = {'parse_mode': parse_mode}
        if keyboard:
            kwargs['reply_markup'] = keyboard
        try:
            bot.edit_message_text(
                text=text,
                chat_id=user_id,
                message_id=message_id,
                **kwargs
            )
            return True
        except Exception as e:
            if "message is not modified" in str(e):
                return True
            logger.error(f"[BATTLE] No se pudo editar mensaje: {e}")
            return False
        
    def _send_battle_menu(self, battle: BattleData, bot):
        """
        Menú principal de batalla.
        - Primera vez: envía sprite (sin botones) + mensaje de texto con menú.
        - Siguientes veces: edita solo el mensaje de texto.
        Esto evita el límite de 1024 chars de Telegram en captions de fotos.
        """
        try:
            player_pokemon = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
            if not player_pokemon:
                return

            wild       = battle.wild_pokemon
            shiny_text = " ✨" if wild.shiny else ""

            hp_w_max = wild.hp_max
            hp_w_act = wild.hp_actual
            hp_p_max = player_pokemon.stats.get('hp', 1)
            hp_p_act = player_pokemon.hp_actual

            bar_w = self._hp_bar(int(hp_w_act / hp_w_max * 100) if hp_w_max else 0)
            bar_p = self._hp_bar(int(hp_p_act / hp_p_max * 100) if hp_p_max else 0)

            # ── Línea de campo (clima + terreno + salas + hazards) ────────────
            from pokemon.battle_ui import build_field_status_line
            _fl_txt    = build_field_status_line(battle)
            field_line = (_fl_txt + "\n") if _fl_txt else ""

            # ── Status del wild y del jugador ─────────────────────────────────
            wild_status_str   = (f" [{STATUS_ICONS[battle.wild_status]}]"
                                 if battle.wild_status else "")
            player_status_str = (f" [{STATUS_ICONS[battle.player_status]}]"
                                 if battle.player_status else "")

            # ── Log de turnos ─────────────────────────────────────────────────
            log_reciente = ""
            if battle.battle_log:
                entradas   = battle.battle_log[-5:]
                encabezado = ("📋 <b>Último turno:</b>" if len(entradas) == 1
                              else f"📋 <b>Últimos {len(entradas)} turnos:</b>")
                log_texto  = "\n─\n".join(entradas)
                log_reciente = f"\n\n{encabezado}\n{log_texto}"

            if battle.player_transformed and battle.player_transform_nombre:
                _nb   = player_pokemon.mote or player_pokemon.nombre
                sexo  = self._sexo_emoji(getattr(player_pokemon, "sexo", None))
                boosts = self._boosts_str(getattr(battle, "player_stat_stages", {}))
                partes = [f"{battle.player_transform_nombre} ({_nb})"]
                if sexo:   partes.append(sexo)
                if boosts: partes.append(boosts)
                p_label = " ".join(partes)
            else:
                p_label = self._formato_nombre_jugador(
                    player_pokemon,
                    getattr(battle, "player_stat_stages", {}),
                )

            wild_tipos   = getattr(wild, "tipos", ["Normal"])
            player_tipos = _pdx_svc.obtener_tipos(player_pokemon.pokemonID)

            wild_line   = build_pokemon_line(
                lado      = "🔴",
                nombre    = wild.nombre_display() + shiny_text,
                sexo      = None,
                tipos     = wild_tipos,
                nivel     = wild.nivel,
                hp_actual = hp_w_act,
                hp_max    = hp_w_max,
                status    = battle.wild_status,
                stages    = getattr(battle, "wild_stat_stages", {}),
            )
            player_line = build_pokemon_line(
                lado      = "🔵",
                nombre    = p_label,
                sexo      = None,
                tipos     = player_tipos,
                nivel     = player_pokemon.nivel,
                hp_actual = hp_p_act,
                hp_max    = hp_p_max,
                status    = battle.player_status,
                stages    = getattr(battle, "player_stat_stages", {}),
            )
            text = (
                f"⚔️ <b>BATALLA POKÉMON</b>\n"
                f"{field_line}"
                f"\n"
                f"{wild_line}\n\n"
                f"{player_line}"
                f"{log_reciente}\n\n"
                f"💡 <b>Tu turno</b> — ¿Qué harás?"
            )

            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton("⚔️ Combate", callback_data=f"battle_fight_{battle.user_id}"),
                types.InlineKeyboardButton("🎒 Mochila",  callback_data=f"battle_bag_{battle.user_id}")
            )
            keyboard.add(
                types.InlineKeyboardButton("👥 Equipo",   callback_data=f"battle_team_{battle.user_id}"),
                types.InlineKeyboardButton("🏃 Huir",     callback_data=f"battle_run_{battle.user_id}")
            )

            # ── Primera vez: enviar sprite mudo + mensaje de texto con menú ──
            if not battle.message_id:
                from pokemon.sprite_system import SpriteSystem
                sprite_url, es_animado = SpriteSystem.get_sprite_url(
                    wild.pokemon_id, wild.shiny
                )
                caption_aparicion = (
                    f"🌿 <b>¡Un {wild.nombre_display()}{shiny_text} salvaje apareció!</b>\n"
                    f"Nivel <b>{wild.nivel}</b>"
                )
                # Mensaje 1: sprite sin botones
                try:
                    if es_animado:
                        import requests as _req, io as _io
                        try:
                            _resp = _req.get(sprite_url, timeout=5)
                            _resp.raise_for_status()
                            _gif_bytes = _io.BytesIO(_resp.content)
                            _gif_bytes.name = f"{wild.pokemon_id}.gif"
                            smsg = bot.send_animation(
                                battle.user_id, _gif_bytes,
                                caption=caption_aparicion, parse_mode="HTML",
                                width=96, height=96,
                            )
                        except Exception:
                            # Fallback: intentar con URL directa
                            smsg = bot.send_animation(
                                battle.user_id, sprite_url,
                                caption=caption_aparicion, parse_mode="HTML"
                            )
                    else:
                        smsg = bot.send_photo(
                            battle.user_id, sprite_url,
                            caption=caption_aparicion, parse_mode="HTML"
                        )
                    battle.sprite_message_id = smsg.message_id
                except Exception as sprite_err:
                    logger.warning(f"[BATTLE] No se pudo enviar sprite: {sprite_err}")

                # Mensaje 2: texto puro con menú completo y botones
                tmsg = bot.send_message(
                    battle.user_id, text,
                    parse_mode="HTML", reply_markup=keyboard
                )
                battle.message_id = tmsg.message_id
                return

            # ── Si Ditto acaba de transformarse, actualizar el sprite ─────────
            _transform_id = getattr(battle, "player_transform_species_id", None)

            if _transform_id is not None and battle.sprite_message_id:
                try:
                    from pokemon.sprite_system import SpriteSystem
                    from telebot.types import InputMediaPhoto
                    
                    # Al usar _transform_id tras el check de "is not None", el tipo es garantizado como int
                    _t_url, _ = SpriteSystem.get_sprite_url(_transform_id, False)
                    
                    if _t_url:
                        bot.edit_message_media(
                            media=InputMediaPhoto(_t_url),
                            chat_id=battle.user_id,
                            message_id=battle.sprite_message_id,
                        )
                except Exception as _sp_err:
                    logger.debug(f"[BATTLE] No se pudo editar sprite Ditto: {_sp_err}")
                
                # Limpiar para no editar cada turno
                battle.player_transform_species_id = None


            # ── Siguientes veces: editar solo el mensaje de texto ────────────
            try:
                bot.edit_message_text(
                    text=text,
                    chat_id=battle.user_id,
                    message_id=battle.message_id,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            except Exception as e:
                if "message is not modified" not in str(e):
                    logger.debug(f"[BATTLE] No se pudo editar mensaje de texto: {e}")

            self._start_turn_timer(battle, battle.user_id, bot)

        except Exception as e:
            logger.error(f"Error enviando menú de batalla: {e}", exc_info=True)
    
    def handle_fight_action(self, user_id: int, bot) -> bool:
        """
        Muestra el menú de movimientos con layout 2 columnas por fila:
          Fila 1: [Nombre Mov1 (poder)]  [emoji Tipo  Cat  PP]
          Fila 2: [Nombre Mov2 (poder)]  [emoji Tipo  Cat  PP]
          Fila 3: [❓ No aprendido    ]  [—————————————————]   ← slots vacíos
          Fila 4: [❓ No aprendido    ]  [—————————————————]
          Fila 5: [         ◀️ Volver              ]
        Siempre muestra exactamente 4 filas de movimientos.
        """
        from pokemon.services.pp_service import pp_service

        try:
            battle = self.get_battle(user_id)
            if not battle:
                return False

            # Durante faint-switch el jugador debe elegir reemplazo primero
            if getattr(battle, "awaiting_faint_switch", False):
                return False

            player_pokemon = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
            if not player_pokemon:
                return False

            # ── Obtener / inicializar movimientos reales ──────────────────────
            movimientos = list(player_pokemon.movimientos) if player_pokemon.movimientos else []

            if not movimientos:
                movimientos = movimientos_service.obtener_todos_movimientos_hasta_nivel(
                    player_pokemon.pokemonID,
                    player_pokemon.nivel,
                )
                if not movimientos:
                    movimientos = ["tackle"]
                try:
                    player_pokemon.movimientos = movimientos[:4]
                    player_pokemon.guardar()
                except Exception as save_err:
                    logger.warning(f"[BATTLE] No se pudieron persistir movimientos: {save_err}")

            movimientos = movimientos[:4]

            # ── Texto superior ────────────────────────────────────────────────
            wild_mv  = battle.wild_pokemon
            hp_p_max = player_pokemon.stats.get("hp", 1)
            bar_p    = self._hp_bar(
                int(player_pokemon.hp_actual / hp_p_max * 100) if hp_p_max else 0
            )
            bar_w    = self._hp_bar(
                int(wild_mv.hp_actual / wild_mv.hp_max * 100) if wild_mv.hp_max else 0
            )

            if battle.player_transformed and battle.player_transform_nombre:
                _nb   = player_pokemon.mote or player_pokemon.nombre
                sexo  = self._sexo_emoji(getattr(player_pokemon, "sexo", None))
                boosts = self._boosts_str(getattr(battle, "player_stat_stages", {}))
                partes = [f"{battle.player_transform_nombre} ({_nb})"]
                if sexo:   partes.append(sexo)
                if boosts: partes.append(boosts)
                p_label = " ".join(partes)
            else:
                p_label = self._formato_nombre_jugador(
                    player_pokemon,
                    getattr(battle, "player_stat_stages", {}),
                )

            # ── Log de los últimos turnos (igual que el menú principal) ───────
            log_reciente = ""
            if battle.battle_log:
                entradas   = battle.battle_log[-3:]
                encabezado = "📋 <b>Último turno:</b>" if len(entradas) == 1 else f"📋 <b>Últimos {len(entradas)} turnos:</b>"
                log_texto  = "\n─\n".join(entradas)
                if len(log_texto) > 400:
                    log_texto = log_texto[-400:]
                log_reciente = f"\n\n{encabezado}\n{log_texto}"

            shiny_text = " ✨" if wild_mv.shiny else ""
            _wt  = getattr(wild_mv, "tipos", ["Normal"])
            _pt  = _pdx_svc.obtener_tipos(player_pokemon.pokemonID)
            text = (
                build_pokemon_line(
                    lado="🔴", nombre=wild_mv.nombre, sexo=wild_mv.sexo,
                    tipos=_wt, nivel=wild_mv.nivel,
                    hp_actual=wild_mv.hp_actual, hp_max=wild_mv.hp_max,
                    status=battle.wild_status,
                    stages=getattr(battle, "wild_stat_stages", {}),
                ) + "\n\n" +
                build_pokemon_line(
                    lado="🔵", nombre=p_label,
                    sexo=getattr(player_pokemon, "sexo", None),
                    tipos=_pt, nivel=player_pokemon.nivel,
                    hp_actual=player_pokemon.hp_actual, hp_max=hp_p_max,
                    status=battle.player_status,
                    stages=getattr(battle, "player_stat_stages", {}),
                ) +
                f"{log_reciente}\n\n⚔️ <b>Elige un movimiento:</b>"
            )


            # ── Construir teclado — 2 botones por fila siempre ───────────────
            keyboard = types.InlineKeyboardMarkup(row_width=2)

            NOOP = f"battle_noop_{user_id}"

            for i in range(4):
                if i < len(movimientos):
                    move = movimientos[i]
                    tiene_pp = pp_service.verificar_tiene_pp(battle.player_pokemon_id, move)
                    label_nombre, label_info = self._format_move_button(
                        move, battle.player_pokemon_id
                    )
                    if not tiene_pp:
                        label_nombre = f"❌ {label_nombre}"
                    cb_move = (
                        f"battle_move_{user_id}_{move}"
                        if tiene_pp
                        else NOOP
                    )
                else:
                    # Slot vacío
                    label_nombre = "❓ No aprendido"
                    label_info   = "—"
                    cb_move      = NOOP

                btn_nombre = types.InlineKeyboardButton(label_nombre, callback_data=cb_move)
                btn_info   = types.InlineKeyboardButton(label_info,   callback_data=NOOP)
                keyboard.row(btn_nombre, btn_info)

            keyboard.add(
                types.InlineKeyboardButton("◀️ Volver", callback_data=f"battle_back_{user_id}")
            )

            self._edit_battle_message(bot, user_id, battle.message_id, text, keyboard)
            self._start_turn_timer(battle, user_id, bot)
            return True

        except Exception as e:
            logger.error(f"Error en handle_fight_action: {e}", exc_info=True)
            return False
        
    def handle_team_action(self, user_id: int, bot) -> bool:
        """Muestra el equipo del jugador con opción de cambio"""
        try:
            battle = self.get_battle(user_id)
            if not battle:
                return False

            team = pokemon_service.obtener_equipo(user_id)
            current_id = battle.player_pokemon_id

            text = "👥 <b>Tu Equipo</b>\n\n"
            keyboard = types.InlineKeyboardMarkup(row_width=1)

            for pokemon in team:
                indicator  = "▶️" if pokemon.id_unico == current_id else "  "
                hp_max     = pokemon.stats.get('hp', 1)
                hp_percent = (pokemon.hp_actual / hp_max) * 100 if hp_max else 0

                if pokemon.hp_actual == 0:
                    status = "💀"
                elif hp_percent < 30:
                    status = "🔴"
                elif hp_percent < 60:
                    status = "🟡"
                else:
                    status = "🟢"

                button_text = (
                    f"{indicator} {pokemon.nombre} Nv.{pokemon.nivel} "
                    f"{status} {pokemon.hp_actual}/{hp_max}"
                )

                if pokemon.hp_actual > 0 and pokemon.id_unico != current_id:
                    keyboard.add(types.InlineKeyboardButton(
                        button_text,
                        callback_data=f"battle_switch_{user_id}_{pokemon.id_unico}"
                    ))
                else:
                    keyboard.add(types.InlineKeyboardButton(
                        button_text,
                        callback_data=f"battle_noop_{user_id}"
                    ))

            keyboard.add(types.InlineKeyboardButton(
                "◀️ Volver", callback_data=f"battle_back_{user_id}"
            ))

            self._edit_battle_message(bot, user_id, battle.message_id, text, keyboard)
            return True

        except Exception as e:
            logger.error(f"Error en handle_team_action: {e}")
            return False
        
    def handle_bag_action(self, user_id: int, bot) -> bool:
        """Muestra la mochila con categorías de items que el usuario tiene."""
        try:
            battle = self.get_battle(user_id)
            if not battle:
                return False
 
            inventario = items_service.obtener_inventario(user_id)
 
            TIPOS_MEDICINA = {'medicina', 'curacion'}
            TIPOS_POKEBALL = {'pokeball'}
            TIPOS_BAYA     = {
                'baya', 'baya_ofensiva', 'baya_mitigacion', 'baya_pp',
                'baya_estado', 'baya_hp',
            }
 
            num_medicinas = 0
            num_pokeballs = 0
            num_bayas     = 0
 
            for item_nombre, cantidad in inventario.items():
                if not cantidad or cantidad <= 0:
                    continue
                # FIX: usar helper con fallback en lugar de items_service directo
                tipo, _ = _get_battle_item_tipo(item_nombre)
                if tipo in TIPOS_MEDICINA:
                    num_medicinas += cantidad
                elif tipo in TIPOS_POKEBALL:
                    num_pokeballs += cantidad
                elif tipo in TIPOS_BAYA:
                    num_bayas += cantidad
 
            text = "🎒 <b>Mochila</b>\n\nSelecciona una categoría:"
 
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton(
                    f"⚕️ Medicinas ({num_medicinas})",
                    callback_data=f"battle_bag_cat_medicine_{user_id}"
                ),
                types.InlineKeyboardButton(
                    f"⚾ Poké Balls ({num_pokeballs})",
                    callback_data=f"battle_bag_cat_pokeballs_{user_id}"
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    f"🍓 Bayas ({num_bayas})",
                    callback_data=f"battle_bag_cat_berries_{user_id}"
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    "◀️ Volver",
                    callback_data=f"battle_back_{user_id}"
                )
            )
 
            self._edit_battle_message(bot, user_id, battle.message_id, text, keyboard)
            return True
 
        except Exception as e:
            logger.error(f"Error en handle_bag_action: {e}")
            return False

    def handle_bag_category(self, user_id: int, categoria: str, bot) -> bool:
        """
        Muestra los items de una categoría específica con su cantidad.
        categoria: 'medicine' | 'pokeballs' | 'berries'
        """
        try:
            battle = self.get_battle(user_id)
            if not battle:
                return False
 
            inventario = items_service.obtener_inventario(user_id)
 
            TIPOS_POR_CAT = {
                'medicine' : {'medicina', 'curacion'},
                'pokeballs': {'pokeball'},
                'berries'  : {
                    'baya', 'baya_ofensiva', 'baya_mitigacion',
                    'baya_pp', 'baya_estado', 'baya_hp',
                },
            }
            EMOJIS_CAT = {
                'medicine' : '⚕️ Medicinas',
                'pokeballs': '⚾ Poké Balls',
                'berries'  : '🍓 Bayas',
            }
 
            tipos_validos     = TIPOS_POR_CAT.get(categoria, set())
            items_disponibles = []
 
            for item_nombre, cantidad in inventario.items():
                if not cantidad or cantidad <= 0:
                    continue
                # FIX: usar helper con fallback en lugar de items_service directo
                tipo, item_data = _get_battle_item_tipo(item_nombre)
                if tipo in tipos_validos:
                    items_disponibles.append((item_nombre, cantidad, item_data))
 
            titulo = EMOJIS_CAT.get(categoria, '🎒 Items')
 
            if not items_disponibles:
                text = f"🎒 <b>{titulo}</b>\n\n❌ No tienes ninguno."
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton(
                    "◀️ Volver", callback_data=f"battle_bag_{user_id}"
                ))
                try:
                    self._edit_battle_message(bot, user_id, battle.message_id, text, keyboard)
                except Exception as e:
                    if "message is not modified" not in str(e):
                        raise
                return True
 
            text = f"🎒 <b>{titulo}</b>\n\nElige un item:"
            keyboard = types.InlineKeyboardMarkup(row_width=1)
 
            for item_nombre, cantidad, item_data in items_disponibles:
                desc     = item_data.get('desc', item_nombre) if item_data else item_nombre
                label    = f"{item_nombre.title()} x{cantidad} — {desc}"
                item_key = item_nombre.replace(' ', '~')
                keyboard.add(types.InlineKeyboardButton(
                    label,
                    callback_data=f"battle_item_{user_id}_{item_key}"
                ))
 
            keyboard.add(types.InlineKeyboardButton(
                "◀️ Volver", callback_data=f"battle_bag_{user_id}"
            ))
 
            try:
                self._edit_battle_message(bot, user_id, battle.message_id, text, keyboard)
            except Exception as e:
                if "message is not modified" not in str(e):
                    raise
            return True
 
        except Exception as e:
            logger.error(f"Error en handle_bag_category: {e}")
            return False

    def handle_item_selected(self, user_id: int, item_nombre: str, bot) -> bool:
        """
        Recibe el item elegido. Si es Pokéball lo lanza directo.
        Si es medicina/baya, muestra el equipo para elegir en qué Pokémon usarlo.
        """
        try:
            battle = self.get_battle(user_id)
            if not battle:
                return False

            item_data = items_service.obtener_item(item_nombre)
            if not item_data:
                return False

            tipo = item_data.get('tipo', '')

            # Pokéballs van directo a lanzar
            if tipo == 'pokeball':
                return self.handle_use_pokeball(user_id, item_nombre, bot)

            # Medicinas/bayas: elegir Pokémon del equipo
            return self._mostrar_equipo_para_item(user_id, item_nombre, bot)

        except Exception as e:
            logger.error(f"Error en handle_item_selected: {e}")
            return False

    def _mostrar_equipo_para_item(self, user_id: int, item_nombre: str, bot) -> bool:
        """Muestra el equipo del jugador para elegir en qué Pokémon usar el item."""
        try:
            battle = self.get_battle(user_id)
            if not battle:
                return False

            from pokemon.services import pokemon_service
            equipo = pokemon_service.obtener_equipo(user_id)

            if not equipo:
                return False

            item_data = items_service.obtener_item(item_nombre)
            desc = item_data.get('desc', item_nombre) if item_data else item_nombre
            text = (
                f"💊 <b>{item_nombre.title()}</b>\n"
                f"<i>{desc}</i>\n\n"
                f"¿En qué Pokémon lo usas?"
            )

            keyboard = types.InlineKeyboardMarkup(row_width=1)
            item_key = item_nombre.replace(' ', '~')

            for poke in equipo:
                hp_max = poke.stats.get('hp', 1)
                hp_act = poke.hp_actual
                pct    = int((hp_act / hp_max) * 100)
                estado = "💀" if hp_act <= 0 else ("💚" if pct >= 50 else "💛")
                label  = f"{estado} {poke.mote or poke.nombre} Nv.{poke.nivel}  HP: {hp_act}/{hp_max}"
                keyboard.add(types.InlineKeyboardButton(
                    label,
                    callback_data=f"battle_use_item_{user_id}_{item_key}_{poke.id_unico}"
                ))

            keyboard.add(types.InlineKeyboardButton(
                "◀️ Volver", callback_data=f"battle_bag_{user_id}"
            ))

            try:
                self._edit_battle_message(bot, user_id, battle.message_id, text, keyboard)
            except Exception as e:
                if "message is not modified" not in str(e):
                    raise
            return True

        except Exception as e:
            logger.error(f"Error en _mostrar_equipo_para_item: {e}")
            return False

    def handle_use_item_on_pokemon(self, user_id: int, item_nombre: str,
                                    pokemon_id: int, bot) -> bool:
        """
        Aplica el item, consume del inventario, ejecuta turno rival y refresca UI.
        Correcciones:
          - _execute_wild_turn llamado con (battle) solamente (firma nueva)
          - Item consumido ANTES del turno rival (orden lógico correcto)
          - Error en aplicar item se muestra sin terminar el turno
        """
        try:
            battle = self.get_battle(user_id)
            if not battle or battle.state != BattleState.ACTIVE:
                return False

            # Verificar stock
            inventario = items_service.obtener_inventario(user_id)
            if inventario.get(item_nombre, 0) <= 0:
                return False

            # Aplicar efecto
            resultado = items_service.aplicar_item_batalla(item_nombre, pokemon_id)

            if not resultado.get("exito", False):
                msg = resultado.get("mensaje", "No se pudo usar el item.")
                # Mostrar error pero NO consumir ni avanzar turno
                self._edit_battle_message(
                    bot, user_id, battle.message_id,
                    f"❌ {msg}\n\nElige otra acción.",
                )
                import threading
                threading.Timer(1.5, lambda: self._send_battle_menu(battle, bot)).start()
                return True   # handled

            # Consumir item del inventario
            items_service.usar_item(user_id, item_nombre, 1)

            # Cancelar timer — el jugador actuó
            self._cancel_turn_timer(battle)

            # Log del turno del jugador
            nombre_poke = self._get_pokemon_display_name(pokemon_id)
            efecto_msg  = resultado.get("mensaje", "Efecto aplicado.")
            log_lines   = [
                f"✅ Usaste <b>{item_nombre.title()}</b> en {nombre_poke}.\n",
                f"  {efecto_msg}\n",
            ]

             # Leer el flag aquí mismo para ser autosuficientes,
            # independientemente de si el header del patch fue aplicado.
            # True  → faint switch: el Pokémon anterior se debilitó,
            #          el jugador elige reemplazo fuera del turno → salvaje NO ataca.
            # False → hard switch: cambio voluntario en combate → salvaje SÍ ataca.
            is_faint_switch: bool = getattr(battle, "awaiting_faint_switch", False)

            log_lines = [f"🔄 ¡{nombre_poke} entró al combate!\n"]

            if is_faint_switch:
                # ── FAINT SWITCH: reemplazo limpio ────────────────────────────
                battle.awaiting_faint_switch = False
                battle.player_stat_stages = {k: 0 for k in battle.player_stat_stages}
                log_lines.append("  ✊ Reemplazo limpio — el rival no ataca este turno.\n")
                self._refresh_battle_ui(battle, user_id, bot, extra_log=log_lines)
                self._start_turn_timer(battle, user_id, bot)

            else:
                # ── HARD SWITCH: cambio voluntario en combate ─────────────────
                rival_log = self._execute_wild_turn(battle)
                if rival_log:
                    log_lines.extend(rival_log)

                updated = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
                if updated and updated.hp_actual <= 0:
                    self._handle_defeat(battle, bot)
                    return True

                self._refresh_battle_ui(battle, user_id, bot, extra_log=log_lines)
                self._start_turn_timer(battle, user_id, bot)

            return True

        except Exception as e:
            logger.error(f"Error en handle_use_item_on_pokemon: {e}", exc_info=True)
            return False

    def handle_use_pokeball(self, user_id: int, pokeball_nombre: str, bot) -> bool:
        """
        Lanza una Poké Ball al Pokémon salvaje.

        Fórmula oficial Gen 6+ / Gen 9:
        a = floor( (3·MaxHP − 2·CurHP) / (3·MaxHP) · CatchRate · BallMult · StatusMult )
        b = floor( 65536 / (255/a)^0.1875 )
        Captura si 4 shakes con rand(0,65535) < b
        Critical Catch: 1 shake si rand(0,255) < a // 6

        Fuentes: Bulbapedia — "Catch rate" (Gen VI–IX mechanics)
        """
        try:
            battle = self.get_battle(user_id)
            if not battle or battle.state.value != "active":
                return False

            inventario = items_service.obtener_inventario(user_id)
            if inventario.get(pokeball_nombre, 0) <= 0:
                return False

            items_service.usar_item(user_id, pokeball_nombre, 1)
            self._cancel_turn_timer(battle)

            wild      = battle.wild_pokemon
            # Obtener datos del ítem con fallback a items_database_complete.
            # Necesario para balls como beastball que solo están en esa BD.
            item_data = items_service.obtener_item(pokeball_nombre) or {}
            if not item_data:
                try:
                    from pokemon.items_database_complete import obtener_item_info as _get_ball_info
                    item_data = _get_ball_info(pokeball_nombre) or {}
                except Exception:
                    pass
            condicion = item_data.get("condicion", "")

            # ── 1. Ball multiplier ────────────────────────────────────────────────
            ratio = _calcular_ball_ratio(
                pokeball_nombre = pokeball_nombre,
                condicion       = condicion,
                item_data       = item_data,
                wild            = wild,
                turn_number     = battle.turn_number,
                user_id         = user_id,
            )

            # ── 2. Catch rate de la especie ───────────────────────────────────────
            _cr_raw = getattr(wild, "capture_rate", None)
            if _cr_raw is not None:
                catch_rate: int = max(1, int(_cr_raw))
            else:
                try:
                    data = pokedex_service.obtener_pokemon(wild.pokemon_id)
                    catch_rate = max(1, int(
                        (data or {}).get("ratio_captura")
                        or (data or {}).get("catch_rate")
                        or 45
                    ))
                except Exception:
                    catch_rate = 45

            # Override para legendarios: evita que un JSON mal configurado
            # les asigne el default 45 y sean triviales de capturar.
            _LEGENDARIOS_CATCH: dict[int, int] = {
                144: 3, 145: 3, 146: 3, 150: 3, 151: 45,
                243: 3, 244: 3, 245: 3, 249: 3, 250: 3, 251: 45,
                377: 3, 378: 3, 379: 3, 380: 3, 381: 3,
                382: 5, 383: 5, 384: 3, 385: 3, 386: 3,
                480: 3, 481: 3, 482: 3, 483: 5, 484: 5,
                485: 3, 486: 3, 487: 3, 488: 100, 491: 3, 493: 3,
                638: 3, 639: 3, 640: 3, 641: 3, 642: 3,
                643: 3, 644: 3, 645: 3, 646: 3,
                716: 3, 717: 3, 718: 3,
                888: 3, 889: 3, 890: 3,
                1007: 3, 1008: 3,
            }
            catch_rate = _LEGENDARIOS_CATCH.get(wild.pokemon_id, catch_rate)

            # ── 3. Status multiplier ──────────────────────────────────────────────
            # CORRECCIÓN: leer battle.wild_status, no wild_status_condition
            wild_status   = getattr(battle, "wild_status", None)
            status_bonus  = _STATUS_CATCH_BONUS.get(wild_status or "", 1.0)

            # ── 4. HP ratio ───────────────────────────────────────────────────────
            hp_max = max(1, wild.hp_max)
            hp_act = max(1, wild.hp_actual)

            # ── 5. Valor a (fórmula oficial) ──────────────────────────────────────
            # a = floor( (3·MaxHP − 2·CurHP) / (3·MaxHP) · CatchRate · BallMult · StatusMult )
            a_raw = (3 * hp_max - 2 * hp_act) / (3 * hp_max) * catch_rate * ratio * status_bonus
            a = max(1, min(255, int(a_raw)))

            # ── 6. Master Ball o captura garantizada (a >= 255) ───────────────────
            if ratio >= 255.0 or a >= 255:
                return self._handle_capture_success(battle, user_id, bot)

            # ── 7. Critical Catch (Gen 6+) ────────────────────────────────────────
            # Probabilidad de 1 shake: a // 6 en 256
            critical_catch = random.randint(0, 255) < (a // 6)
            required_shakes = 1 if critical_catch else 4

            # ── 8. Shake checks ───────────────────────────────────────────────────
            # b = floor( 65536 / (255/a)^0.1875 )
            # 0.1875 = 3/16 — exponente exacto de la fórmula Gen 6+
            b = min(65535, int(65536 / ((255 / a) ** 0.1875)))
            captured = all(random.randint(0, 65535) < b for _ in range(required_shakes))

            # ── 9. Construir texto de log ─────────────────────────────────────────
            ball_label = pokeball_nombre.replace("ball", " Ball").title()
            if captured:
                return self._handle_capture_success(battle, user_id, bot)

            # Falló: feedback proporcional al número de shakes
            shakes_done = sum(
                1 for _ in range(required_shakes)
                if random.randint(0, 65535) < b
            )
            if critical_catch:
                escape_txt = "⭐ ¡Critical Catch fallido!"
            elif shakes_done >= 3:
                escape_txt = "💢 ¡Casi lo atrapa!"
            elif shakes_done == 2:
                escape_txt = "😤 ¡Se resistió con fuerza!"
            elif shakes_done == 1:
                escape_txt = "😤 ¡Escapó rápido!"
            else:
                escape_txt = "😤 ¡Ni se movió la Ball!"

            rival_log = self._execute_wild_turn(battle)
            log_lines = [
                f"⚾ Lanzaste una <b>{ball_label}</b>!\n",
                f"{escape_txt} <b>{wild.nombre}</b> escapó.\n",
            ]
            if rival_log:
                log_lines.extend(rival_log)

            updated = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
            if updated and updated.hp_actual <= 0:
                self._handle_defeat(battle, bot)
                return True

            self._refresh_battle_ui(battle, user_id, bot, extra_log=log_lines)
            self._start_turn_timer(battle, user_id, bot)
            return True

        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error en handle_use_pokeball: {e}", exc_info=True)
            return False

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _get_pokemon_display_name(self, pokemon_id: int) -> str:
        """Nombre para mostrar de un Pokémon de usuario."""
        try:
            from pokemon.services import pokemon_service
            poke = pokemon_service.obtener_pokemon(pokemon_id)
            if poke:
                return poke.mote or poke.nombre
        except Exception:
            pass
        return f"Pokémon #{pokemon_id}"

    @staticmethod
    def _sexo_emoji(sexo: Optional[str]) -> str:
        """'M' → '♂', 'F' → '♀', None → ''"""
        return {"M": "♂", "F": "♀"}.get(sexo or "", "")
    @staticmethod
    def _boosts_str(stages: Optional[Dict[str, int]]) -> str:
        """Genera '+2Atk -1Def' a partir de las etapas de stat activas."""
        if not stages:
            return ""
        _LABELS = {"atq": "Atk", "def": "Def", "atq_sp": "SpA", "def_sp": "SpD", "vel": "Vel"}
        parts = []
        for stat, label in _LABELS.items():
            val = stages.get(stat, 0)
            if val != 0:
                parts.append(f"{'+'if val>0 else ''}{val}{label}")
        return " ".join(parts)
    def _formato_nombre_jugador(
        self,
        pokemon,
        stages: Optional[Dict[str, int]] = None,
    ) -> str:
        """
        Retorna el nombre completo del Pokémon del jugador para la UI de batalla.
        Formato: 'Mote ♂ +2Atk -1Def'  /  'Charmander ♀'  /  'Magneton'
        """
        nombre = pokemon.mote or pokemon.nombre
        sexo   = self._sexo_emoji(getattr(pokemon, "sexo", None))
        boosts = self._boosts_str(stages)
        partes = [nombre]
        if sexo:   partes.append(sexo)
        if boosts: partes.append(boosts)
        return " ".join(partes)
    
    def _execute_wild_turn(self, battle) -> list:
        """
        Ejecuta el turno del Pokémon salvaje.
        Usa check_can_move + check_confusion + _apply_status_move (estado)
        o la lógica de daño directa. Persiste HP del jugador en BD.
        """
        try:
            wild   = battle.wild_pokemon
            player = pokemon_service.obtener_pokemon(battle.player_pokemon_id)

            if not wild or not player or wild.hp_actual <= 0 or player.hp_actual <= 0:
                return []

            move      = random.choice(wild.moves) if wild.moves else "tackle"
            move_data = movimientos_service.obtener_movimiento(move)

            poder     = int((move_data.get("poder", 0) if move_data else 0) or 0)
            categoria = move_data.get("categoria", "Normal") if move_data else "Normal"
            move_tipo = move_data.get("tipo", "Normal")      if move_data else "Normal"
            move_es   = MOVE_NAMES_ES.get(move.lower().replace(" ", ""), move.title())

            log = [f"\n⚔️ ¡<b>{wild.nombre}</b> usó <b>{move_es}</b>!\n"]
            daño = 0

            # ── ¿Puede actuar el salvaje? ─────────────────────────────────
            if not check_can_move(battle, is_player=False,
                                   actor_name=wild.nombre, log=log):
                return log

            # ── Confusión del salvaje ─────────────────────────────────────
            if check_confusion(
                battle, False, wild.nombre,
                wild.nivel,
                wild.stats.get("atq", 50),
                log,
            ):
                return log  # se golpeó a sí mismo

            move_key_wild = move.lower().replace(" ", "").replace("-", "")
            _wild_effect  = MOVE_EFFECTS.get(move_key_wild, {})

            # ── Switch forzado (Remolino, Rugido, Cola Dragón) ────────────
            if _wild_effect.get("forced_switch"):
                p_name_local = player.mote or player.nombre
                equipo = pokemon_service.obtener_equipo(battle.user_id)
                candidatos = [
                    p for p in equipo
                    if p.id_unico != battle.player_pokemon_id and p.hp_actual > 0
                ]
                if not candidatos:
                    log.append(f"  💨 ¡{wild.nombre} usó {move_es}!\n")
                    log.append(f"  😤 ¡Pero no tuvo efecto!\n")
                else:
                    log.append(f"  💨 ¡{wild.nombre} usó {move_es}!\n")
                    log.append(f"  🔀 ¡{p_name_local} fue expulsado del combate!\n")
                    battle.awaiting_forced_switch = True
                return log

            # ── Poder variable por peso (Low Kick / Heavy Slam del salvaje) ─────
            if move_key_wild in _LOWKICK_MOVES:
                _def_peso_p = get_peso_pokemon(player.pokemonID)
                poder = calcular_poder_lowkick(_def_peso_p)
            elif move_key_wild in _HEAVYSLAM_MOVES:
                _atk_peso_w = get_peso_pokemon(wild.pokemon_id)
                _def_peso_p = get_peso_pokemon(player.pokemonID)
                poder = calcular_poder_heavyslam(_atk_peso_w, _def_peso_p)
                
            # ── Movimiento de estado ──────────────────────────────────────
            if categoria == "Estado" or poder == 0:
                p_name_local = player.mote or player.nombre
                self._apply_status_move(
                    move,
                    wild.nombre,
                    p_name_local,
                    battle.wild_stat_stages,
                    battle.player_stat_stages,
                    log,
                    battle=battle,
                    is_player_attacker=False,
                )
                battle.turn_number += 1
                battle._last_enemy_entry = f"{wild.nombre} usó {move_es}"
                return log

            # ── Movimiento de daño ────────────────────────────────────────
            player_tipos = []
            try:
                player_tipos = pokedex_service.obtener_tipos(player.pokemonID)
            except Exception:
                player_tipos = ["Normal"]
            wild_tipos = getattr(wild, "tipos", ["Normal"])

            type_eff = movimientos_service._calcular_efectividad(move_tipo, player_tipos)
            if type_eff == 0.0:
                log.append(f"  🚫 ¡No afecta a {player.mote or player.nombre}!\n")
                battle.turn_number += 1
                battle._last_enemy_entry = f"{wild.nombre} usó {move_es}"
                return log

            _w_weather_mult = apply_weather_boost(battle.weather, move_tipo)
            _wild_ground    = is_grounded(getattr(wild, "tipos", ["Normal"]), battle)
            _w_terrain_mult = apply_terrain_boost(battle.terrain, move_tipo, _wild_ground)

            # Multiplicador de habilidad del salvaje (obtenido de Pokédex si existe)
            from pokemon.battle_engine import calcular_mult_habilidad as _cmh
            _wild_hab = getattr(wild, "habilidad", "") or ""
            _w_hab_mult, _ = _cmh(
                _wild_hab, move_key_wild, move_tipo, categoria,
                poder, hp_ratio=wild.hp_actual / max(wild.hp_max, 1),
            )
            # Objeto del wild (normalmente no tienen, pero soporte por consistencia)
            from pokemon.battle_engine import calcular_mult_objeto as _cmo
            _wild_obj     = getattr(wild, "objeto", "") or ""
            _type_eff_pre = movimientos_service._calcular_efectividad(move_tipo, player_tipos)
            _w_obj_mult, _w_obj_recoil = _cmo(_wild_obj, move_tipo, categoria, _type_eff_pre)
            poder_efectivo_wild = max(1, int(poder * _w_hab_mult * _w_obj_mult))

            # Life Orb del wild (rarísimo pero posible en diseño custom)
            if _w_obj_recoil > 0 and daño > 0:
                _lo_dmg = max(1, int(wild.hp_max * _w_obj_recoil))
                wild.hp_actual = max(0, wild.hp_actual - _lo_dmg)
                log.append(f"  🔴 ¡{wild.nombre} perdió {_lo_dmg} HP por la Vida Esfera!\n")

            _w_crit_stg = battle.wild_crit_stage
            if move_key_wild in _HIGH_CRIT_MOVES:
                _w_crit_stg = min(3, _w_crit_stg + 1)
            is_wild_crit = BattleUtils.check_critical_hit(crit_stage=_w_crit_stg)

            _CAT = {"Physical": "Físico", "Special": "Especial", "Status": "Estado"}
            cat_norm = _CAT.get(categoria, categoria)

            if cat_norm == "Físico":
                _w_atk_stage = max(0, battle.wild_stat_stages.get("atq", 0)) \
                               if is_wild_crit else battle.wild_stat_stages.get("atq", 0)
                _p_def_stage = min(0, battle.player_stat_stages.get("def", 0)) \
                               if is_wild_crit else battle.player_stat_stages.get("def", 0)
                atk     = max(1, int(wild.stats.get("atq", 50) *
                                     stage_multiplier(_w_atk_stage)))
                _p_def_stat = "def_sp" if getattr(battle, "wonder_room", False) else "def"
                def_eff = max(1, int(player.stats.get(_p_def_stat, 50) *
                                     stage_multiplier(_p_def_stage)))
            else:
                _w_atk_stage = max(0, battle.wild_stat_stages.get("atq_sp", 0)) \
                               if is_wild_crit else battle.wild_stat_stages.get("atq_sp", 0)
                _p_def_stage = min(0, battle.player_stat_stages.get("def_sp", 0)) \
                               if is_wild_crit else battle.player_stat_stages.get("def_sp", 0)
                atk     = max(1, int(wild.stats.get("atq_sp", 50) *
                                     stage_multiplier(_w_atk_stage)))
                _p_def_stat2 = "def" if getattr(battle, "wonder_room", False) else "def_sp"
                def_eff = max(1, int(player.stats.get(_p_def_stat2, 50) *
                                     stage_multiplier(_p_def_stage)))

            stab     = 1.5 if move_tipo in wild_tipos else 1.0
            daño     = BattleUtils.calculate_damage(
                wild.nivel, atk, def_eff,
                max(1, int(poder_efectivo_wild * _w_weather_mult * _w_terrain_mult)),
                stab * type_eff,
                is_wild_crit,
            )

            if is_wild_crit: log.append("  ✨ ¡Golpe crítico!\n")
            if type_eff > 1.0:   log.append("  🔥 ¡Es muy efectivo!\n")
            elif type_eff < 1.0: log.append("  😐 No es muy efectivo...\n")
            log.append(f"  💥 {player.mote or player.nombre} recibió <b>{daño}</b> de daño.\n")

            nuevo_hp = max(0, player.hp_actual - daño)
            try:
                db_manager.execute_update(
                    "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                    (nuevo_hp, battle.player_pokemon_id),
                )
            except Exception as db_err:
                logger.error(f"Error persistiendo HP: {db_err}")

            if nuevo_hp <= 0:
                log.append(f"  💀 ¡{player.mote or player.nombre} se debilitó!\n")

            # Absorción del wild
            _w_drain = DRAIN_MOVES.get(move_key_wild)
            if _w_drain and daño > 0:
                w_healed = max(1, int(daño * _w_drain))
                wild.hp_actual = min(wild.hp_max, wild.hp_actual + w_healed)
                log.append(f"  🌿 ¡{wild.nombre} absorbió {w_healed} HP!\n")

            # Efecto secundario de ailment
            if nuevo_hp > 0 and battle.player_status is None:
                _sec = SECONDARY_AILMENTS.get(move_key_wild)
                if _sec:
                    _ail, _chance = _sec
                    if random.randint(1, 100) <= _chance:
                        apply_ailment(battle, _ail, target_is_wild=False,
                                      target_name=(player.mote or player.nombre), log=log)

            battle.turn_number += 1
            _enemy_txt = f"{wild.nombre} salvaje usó {move_es}"
            if daño:
                _enemy_txt += f", hizo {daño} de daño"
            battle._last_enemy_entry = _enemy_txt
            return log

        except Exception as e:
            logger.error(f"Error en _execute_wild_turn: {e}", exc_info=True)
            return []

    def _mostrar_selector_pivot(self, battle: "BattleData", user_id: int, bot) -> None:
        """
        Muestra el panel de selección de Pokémon después de un move pivot
        (U-turn, Volt Switch, Parting Shot).
        El wild NO ataca mientras se elige — el switch es gratuito.
        """
        try:
            if not battle or not battle.awaiting_pivot_switch:
                return

            wild    = battle.wild_pokemon
            equipo  = pokemon_service.obtener_equipo(user_id)
            current = battle.player_pokemon_id

            texto = (
                f"💨 <b>¡Elige el siguiente Pokémon!</b>\n\n"
                f"🔴 {wild.nombre} Nv.{wild.nivel} "
                f"({wild.hp_actual}/{wild.hp_max} HP)\n\n"
                f"Selecciona quién saldrá a combatir:"
            )
            keyboard = types.InlineKeyboardMarkup(row_width=1)

            for poke in equipo:
                if poke.id_unico == current:
                    continue  # el activo no puede elegirse
                hp_max = poke.stats.get("hp", 1) or 1
                hp_pct = (poke.hp_actual / hp_max) * 100 if hp_max else 0

                if poke.hp_actual <= 0:
                    status = "💀"
                elif hp_pct < 30:
                    status = "🔴"
                elif hp_pct < 60:
                    status = "🟡"
                else:
                    status = "🟢"

                label = (
                    f"{status} {poke.mote or poke.nombre} "
                    f"Nv.{poke.nivel}  {poke.hp_actual}/{hp_max}"
                )

                if poke.hp_actual > 0:
                    keyboard.add(types.InlineKeyboardButton(
                        label,
                        callback_data=f"battle_pivotswitch_{user_id}_{poke.id_unico}",
                    ))
                else:
                    keyboard.add(types.InlineKeyboardButton(
                        label,
                        callback_data=f"battle_noop_{user_id}",
                    ))

            self._edit_battle_message(bot, user_id, battle.message_id, texto, keyboard)

        except Exception as e:
            logger.error(f"Error en _mostrar_selector_pivot: {e}", exc_info=True)

    def _update_battle_message(self, battle, user_id: int, bot, extra_text: str = ""):
        """Edita el mensaje de batalla con un texto simple (para errores)."""
        try:
            self._edit_battle_message(bot, user_id, battle.message_id, extra_text)
        except Exception:
            pass

    def _refresh_battle_ui(self, battle, user_id: int, bot, extra_log: Optional[list] = None):
        """
        Muestra el resultado del turno con delay y vuelve al menú.
        Agrega extra_log al battle_log antes de refrescar.
        """
        import threading

        try:
            # Agregar líneas del turno al historial
            if extra_log:
                # Filtrar líneas vacías y de formato (solo guardamos texto limpio)
                for linea in extra_log:
                    linea_limpia = linea.strip()
                    if linea_limpia and not linea_limpia.startswith("\n"):
                        # Quitar tags HTML para el historial
                        import re
                        limpia = re.sub(r'<[^>]+>', '', linea_limpia)
                        if limpia:
                            battle.battle_log.append(limpia)

            # Mostrar resultado intermedio (sin teclado)
            if extra_log:
                wild   = battle.wild_pokemon
                player = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
                if player:
                    hp_p_max = player.stats.get('hp', 1)
                    hp_w_max = wild.hp_max
                    bar_w = self._hp_bar(int(wild.hp_actual / hp_w_max * 100) if hp_w_max else 0)
                    bar_p = self._hp_bar(int(player.hp_actual / hp_p_max * 100) if hp_p_max else 0)
                    
                    p_label = self._formato_nombre_jugador(player,getattr(battle, "player_stat_stages", {}))
                    # ── Campo ─────────────────────────────────────────────────
                    from pokemon.battle_ui import build_field_status_line
                    _rf_field_txt = build_field_status_line(battle)
                    _rf_field = (_rf_field_txt + "\n") if _rf_field_txt else ""

                    _ws = (f" [{STATUS_ICONS[battle.wild_status]}]"
                           if battle.wild_status else "")
                    _ps = (f" [{STATUS_ICONS[battle.player_status]}]"
                           if battle.player_status else "")

                    _wild_tipos   = getattr(wild, "tipos", ["Normal"])
                    _player_tipos = _pdx_svc.obtener_tipos(player.pokemonID)

                    _wild_line   = build_pokemon_line(
                        lado="🔴", nombre=wild.nombre_display(), sexo=None,
                        tipos=_wild_tipos, nivel=wild.nivel,
                        hp_actual=wild.hp_actual, hp_max=hp_w_max,
                        status=battle.wild_status,
                        stages=getattr(battle, "wild_stat_stages", {}),
                    )
                    _player_line = build_pokemon_line(
                        lado="🔵", nombre=p_label,
                        sexo=getattr(player, "sexo", None),
                        tipos=_player_tipos, nivel=player.nivel,
                        hp_actual=player.hp_actual, hp_max=hp_p_max,
                        status=battle.player_status,
                        stages=getattr(battle, "player_stat_stages", {}),
                    )
                    resultado_text = (
                        f"⚔️ <b>BATALLA POKÉMON</b>\n"
                        f"{_rf_field}\n"
                        f"{_wild_line}\n\n"
                        f"{_player_line}\n"
                        f"━━━━━━━━━━━━━━━\n"
                        + "\n".join(extra_log)
    )
                    try:
                        bot.edit_message_caption(
                            caption=resultado_text,
                            chat_id=user_id,
                            message_id=battle.message_id,
                            parse_mode="HTML"
                        )
                    except Exception:
                        try:
                            self._edit_battle_message(bot, user_id, battle.message_id, resultado_text)
                        except Exception:
                            pass

            # Si el jugador fue debilitado → manejar derrota
            player_check = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
            if player_check and player_check.hp_actual <= 0:
                threading.Timer(1.5, lambda: self._handle_defeat(battle, bot)).start()
                return

            # Si el salvaje fue debilitado → victoria
            if battle.wild_pokemon.hp_actual <= 0:
                player_check2 = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
                threading.Timer(1.5, lambda: self._handle_victory(battle, player_check2, bot)).start()
                return

            # Volver al menú principal (con sprite + HP actualizados + log)
            threading.Timer(2.0, lambda: self._send_battle_menu(battle, bot)).start()

        except Exception as e:
            logger.error(f"Error en _refresh_battle_ui: {e}", exc_info=True)

    @staticmethod
    def _hp_bar(pct: int, length: int = 10) -> str:
        """Genera una barra de HP visual con emojis."""
        filled = max(0, min(length, int(pct / 100 * length)))
        color  = "🟩" if pct > 50 else ("🟨" if pct > 20 else "🟥")
        return color * filled + "⬛" * (length - filled)

    def _handle_capture_success(self, battle, user_id: int, bot) -> bool:
        """
        Maneja la captura exitosa del Pokémon salvaje.
        - Crea el Pokémon en la BD del usuario.
        - Otorga EXP con fórmula Gen 9 igual que una victoria.
        - Otorga cosmos proporcionales al nivel.
        - Limpia el spawn y la batalla.
        - Edita el mensaje del DM con el resultado.
        """
        try:
            wild = battle.wild_pokemon
            from pokemon.services import pokemon_service, spawn_service

            # 1. Crear el Pokémon capturado en la BD
            nuevo_id = pokemon_service.crear_pokemon(
                user_id   = user_id,
                pokemon_id = wild.pokemon_id,
                nivel      = wild.nivel,
                shiny      = wild.shiny,
                sexo       = wild.sexo,
            )
            destino = "tu equipo" if nuevo_id else "el PC"

            # 2. EXP y cosmos para el Pokémon activo (igual que victoria)
            player_pokemon = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
            linea_exp = ""
            if player_pokemon:
                exp_ganada = ExperienceSystem.exp_por_victoria(
                    nivel_enemigo      = wild.nivel,
                    pokemon_id_enemigo = wild.pokemon_id,
                    nivel_ganador      = player_pokemon.nivel,
                    es_salvaje         = True,
                    es_entrenador      = False,
                )
                money_reward = max(10, min(50, 10 + wild.nivel * 40 // 100))

                exp_result = ExperienceSystem.aplicar_experiencia(
                    battle.player_pokemon_id, exp_ganada
                )
                economy_service.add_credits(user_id, money_reward, "Captura de Pokémon")

                # ── EVs al Pokémon activo ─────────────────────────────────────
                try:
                    from pokemon.services.ev_service import ev_service
                    _, _ev_log = ev_service.otorgar_evs(
                        ganador_id           = battle.player_pokemon_id,
                        derrotado_pokemon_id = wild.pokemon_id,
                    )
                    if _ev_log:
                        linea_exp += _ev_log
                except Exception as _ev_e:
                    logger.error(f"[EV] Error en captura: {_ev_e}")
                
                if exp_result.get("subio_nivel"):
                    from pokemon.level_up_handler import LevelUpHandler
                    LevelUpHandler.procesar_subida(
                        bot=bot,
                        user_id=user_id,
                        pokemon_id=battle.player_pokemon_id,
                        exp_result=exp_result,
                        delay=3.0,
                    )
                    
                p_name = player_pokemon.mote or player_pokemon.nombre
                linea_exp = (
                    f"\n💫 {p_name} ganó <b>{exp_ganada} EXP</b>\n"
                    f"💰 Ganaste <b>{money_reward} cosmos</b>"
                )
                if exp_result.get("subio_nivel"):
                    linea_exp += (
                        f"\n✨ ¡<b>{p_name}</b> subió al nivel "
                        f"<b>{exp_result['nivel_nuevo']}</b>!"
                    )
            # ── Restaurar posiciones del equipo ───────────────────────────
                try:
                    if battle.posiciones_originales:
                        pokemon_service.restaurar_posiciones(battle.posiciones_originales)
                except Exception as _rp_e:
                    logger.error(f"[POS] Error restaurando posiciones: {_rp_e}")

            # 3. Limpiar estado
            spawn_service.limpiar_spawn(battle.thread_id)
            if user_id in self.active_battles:
                del self.active_battles[user_id]

            # 4. Mensaje final
            shiny_text = "✨ ¡Es shiny! " if wild.shiny else ""
            text = (
                f"🎉 <b>¡{wild.nombre} fue capturado!</b>\n"
                f"{shiny_text}"
                f"Nv.{wild.nivel} → añadido a {destino}."
                f"{linea_exp}"
            )

            self._edit_battle_message(bot, user_id, battle.message_id, text)
            logger.info(
                f"[BATTLE] Captura exitosa: Usuario {user_id} capturó "
                f"{wild.nombre} Nv.{wild.nivel}"
            )
            # Registrar en Pokédex personal del usuario
            try:
                from funciones.pokedex_usuario import registrar_capturado
                registrar_capturado(
                    user_id    = user_id,
                    pokemon_id = wild.pokemon_id,
                    bot        = bot,
                    chat_id    = battle.thread_id,
                    thread_id  = battle.thread_id,
                )
            except Exception as _pdx_e:
                logger.warning(f"[POKEDEX] No se pudo registrar captura: {_pdx_e}")
            # Pedir mote al jugador si se creó el Pokémon correctamente
            if nuevo_id:
                nuevo_poke = pokemon_service.obtener_pokemon(nuevo_id)
                if nuevo_poke:
                    from pokemon.pokemon_class import pedir_mote_pokemon
                    def _guardar_mote_captura(mote):
                        if mote:
                            db_manager.execute_update(
                                "UPDATE POKEMON_USUARIO SET apodo = ? WHERE id_unico = ?",
                                (mote, nuevo_id)
                            )
                    pedir_mote_pokemon(
                        bot=bot,
                        user_id=user_id,
                        pokemon=nuevo_poke,
                        mensaje_callback=_guardar_mote_captura,
                    )
            return True

        except Exception as e:
            logger.error(f"Error en _handle_capture_success: {e}", exc_info=True)
            return False
    
    def execute_move(self, user_id: int, move_name: str, bot) -> bool:
        """
        Ejecuta el turno del jugador con orden de ataque basado en velocidad.
 
        CAMBIOS:
        - _cancel_turn_timer() es LO PRIMERO que se hace al entrar.
        - Si el wild cae, se muestra el log del turno y se despacha
          _handle_victory() con un delay de 2.5s para que sea legible.
        - Si el jugador cae, igual: muestra log y despacha _handle_defeat()
          con delay de 2.0s.
        """
        try:
            battle = self.get_battle(user_id)
            if not battle or battle.state != BattleState.ACTIVE:
                return False
 
            # ── PRIMERO: cancelar el timer ANTES de cualquier lógica ──────────
            # Evita que un timeout "tardío" se dispare después de que el
            # jugador ya eligió su movimiento.
            self._cancel_turn_timer(battle)
 
            # No permitir acción mientras se elige reemplazo
            if getattr(battle, "awaiting_faint_switch", False):
                return False
            if getattr(battle, "awaiting_pivot_switch", False):
                return False
 
            wild           = battle.wild_pokemon
            player_pokemon = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
 
            if not player_pokemon or wild.hp_actual <= 0 or player_pokemon.hp_actual <= 0:
                return False
 
            move_data      = movimientos_service.obtener_movimiento(move_name)
            move_poder     = int((move_data.get("basePower", move_data.get("poder", 0)) if move_data else 0) or 0)
            move_tipo      = (move_data.get("type",      move_data.get("tipo",      "Normal")) if move_data else "Normal")
            move_categoria = (move_data.get("category",  move_data.get("categoria", "Físico")) if move_data else "Físico")
            _cat_map = {"Physical": "Físico", "Special": "Especial", "Status": "Estado"}
            move_categoria = _cat_map.get(move_categoria, move_categoria)
            nombre_es      = MOVE_NAMES_ES.get(move_name.lower().replace(" ", ""), move_name.title())
            p_name         = player_pokemon.mote or player_pokemon.nombre
 
            log: list = []
 
            # ── Verificar PP ──────────────────────────────────────────────────
            pp_data: dict = {}
            try:
                import json as _json
                r = db_manager.execute_query(
                    "SELECT pp_data FROM POKEMON_USUARIO WHERE id_unico = ?",
                    (battle.player_pokemon_id,),
                )
                if r and r[0]["pp_data"]:
                    pp_data = _json.loads(r[0]["pp_data"])
            except Exception:
                pass
 
            move_key = move_name.lower().replace(" ", "")
            _pp_val = pp_data.get(move_key, pp_data.get(move_name, 1))
            if isinstance(_pp_val, dict):
                _pp_val = _pp_val.get("actual", 1)
            if int(_pp_val) <= 0:
                log.append(f"❌ ¡<b>{nombre_es}</b> no tiene PP!\n")
                self._refresh_battle_ui(battle, user_id, bot, extra_log=log)
                self._start_turn_timer(battle, user_id, bot)
                return True
 
            # ── Verificar precisión ───────────────────────────────────────────
            _prec_raw = movimientos_service.obtener_precision(move_name)
            precision = 999 if (_prec_raw is True or not _prec_raw) else int(_prec_raw)
            if precision < 999 and random.randint(1, 100) > precision:
                log.append(f"⚡ <b>{p_name}</b> usó <b>{nombre_es}</b>... ¡pero falló!\n")
                enemy_log = self._execute_wild_turn(battle)
                log.extend(enemy_log)
                battle.turn_number += 1
                self._refresh_battle_ui(battle, user_id, bot, extra_log=log)
                self._start_turn_timer(battle, user_id, bot)
                return True
 
            # ── Descontar PP ──────────────────────────────────────────────────
            from pokemon.services.pp_service import pp_service as _pp_service
            _pp_service.usar_pp(battle.player_pokemon_id, move_name)
 
            # ── Determinar orden por velocidad ────────────────────────────────
            player_vel = BattleUtils.effective_speed(
                player_pokemon.stats.get("vel", 50),
                battle.player_stat_stages.get("vel", 0),
                battle.player_status,
            )
            wild_vel = BattleUtils.effective_speed(
                wild.stats.get("vel", 50),
                battle.wild_stat_stages.get("vel", 0),
                battle.wild_status,
            )
 
            if player_vel == wild_vel:
                wild_first = random.random() < 0.5
            else:
                if getattr(battle, "trick_room", False):
                    wild_first = player_vel > wild_vel
                else:
                    wild_first = wild_vel > player_vel
 
            if wild_first:
                log.append(
                    f"⚡ <i>{wild.nombre} es más rápido "
                    f"({int(wild_vel)} vs {int(player_vel)} Vel) y ataca primero!</i>\n"
                )
 
            # ── Closure: ataque del jugador ───────────────────────────────────
            player_damage = 0
 
            def _player_attacks() -> bool:
                nonlocal player_damage
 
                p_side = side_from_player(player_pokemon, battle)
                w_side = side_from_wild(wild, battle)
 
                ko = apply_move(
                    p_side, w_side, battle,
                    move_name, move_data if move_data is not None else {}, log,
                    type_effectiveness_fn=movimientos_service._calcular_efectividad,
                )
 
                sync_player_side(p_side, battle, persist=True)
                sync_wild_side(w_side, wild, battle)
 
                player_damage = p_side.hp_max - p_side.hp_actual
                return ko
 
            # ── Ejecutar en orden de velocidad ────────────────────────────────
            wild_died = False
            if wild_first:
                enemy_log = self._execute_wild_turn(battle)
                log.extend(enemy_log)
 
                updated_p = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
                if updated_p and updated_p.hp_actual <= 0:
                    # Jugador cayó antes de atacar — mostrar log y manejar derrota
                    battle.turn_number += 1
                    self._append_turn_log(battle, p_name, nombre_es, player_damage, battle._last_enemy_entry or "")
                    self._refresh_battle_ui(battle, user_id, bot, extra_log=log)
                    import threading as _th
                    _th.Timer(2.0, lambda: self._handle_defeat(battle, bot)).start()
                    return True
 
                wild_died = _player_attacks()
            else:
                wild_died = _player_attacks()
 
                if not wild_died:
                    enemy_log = self._execute_wild_turn(battle)
                    log.extend(enemy_log)
 
            # ── Consolidar log del turno ──────────────────────────────────────
            battle.turn_number += 1
            self._append_turn_log(battle, p_name, nombre_es, player_damage, getattr(battle, "_last_enemy_entry", ""))
 
            # ── Si el wild cayó por daño directo ──────────────────────────────
            if wild_died or wild.hp_actual <= 0:
                self._refresh_battle_ui(battle, user_id, bot, extra_log=log)
                player_poke_final = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
                import threading as _th
                _th.Timer(2.5, lambda: self._handle_victory(battle, player_poke_final, bot)).start()
                return True
 
            # ── Verificar si jugador cayó (por contraataque) ──────────────────
            updated_p = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
            if updated_p and updated_p.hp_actual <= 0:
                self._refresh_battle_ui(battle, user_id, bot, extra_log=log)
                import threading as _th
                _th.Timer(2.0, lambda: self._handle_defeat(battle, bot)).start()
                return True
 
            # ── Efectos residuales de fin de turno ────────────────────────────
            _apply_residual_effects(battle, log)
 
            # ── Chequeo post-residuales ───────────────────────────────────────
            if wild.hp_actual <= 0:
                self._refresh_battle_ui(battle, user_id, bot, extra_log=log)
                player_poke_final2 = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
                import threading as _th
                _th.Timer(2.5, lambda: self._handle_victory(battle, player_poke_final2, bot)).start()
                return True
 
            updated_p2 = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
            if updated_p2 and updated_p2.hp_actual <= 0:
                self._refresh_battle_ui(battle, user_id, bot, extra_log=log)
                import threading as _th
                _th.Timer(2.0, lambda: self._handle_defeat(battle, bot)).start()
                return True
 
            self._refresh_battle_ui(battle, user_id, bot, extra_log=log)
            self._start_turn_timer(battle, user_id, bot)
            return True
 
        except Exception as e:
            logger.error(f"Error en execute_move: {e}", exc_info=True)
            return False

    def _append_turn_log(self, battle, p_name: str, nombre_es: str, player_damage: int, enemy_entry: str):
        """Helper: consolida una entrada en battle.battle_log sin duplicar lógica."""
        _p_entry = f"T{battle.turn_number}:\n  {p_name} usó {nombre_es}"
        if player_damage:
            _p_entry += f", causó {player_damage} de daño"
        battle._last_player_entry = _p_entry
 
        combined = _p_entry
        if enemy_entry:
            combined += f"\n  {enemy_entry}"
        battle.battle_log.append(combined)
        if len(battle.battle_log) > 3:
            battle.battle_log = battle.battle_log[-3:]

        
    def _apply_status_move(
        self,
        move_name: str,
        attacker_name: str,
        defender_name: str,
        attacker_stages: dict,
        defender_stages: dict,
        log: list,
        battle=None,
        is_player_attacker: bool = True,
    ) -> "bool | str":
        """
        Aplica el efecto completo de un movimiento de estado o sin daño.
        Cubre: cambios de etapa, ailments reales, curación y Bostezo.
        Retorna True si se aplicó algún efecto.
        """
        key    = move_name.lower().replace(" ", "").replace("-", "")
        effect = MOVE_EFFECTS.get(key)

        if not effect:
            return False

        applied = False

        # ── Cambios de etapa ──────────────────────────────────────────────────
        for (target, stat, delta) in effect.get("stages", []):
            stages = attacker_stages if target == "self" else defender_stages
            quien  = attacker_name   if target == "self" else defender_name
            # apply_stage_change maneja tanto el caso "ya en límite" como el
            # cambio normal, y añade la línea de log internamente.
            apply_stage_change(stat, delta, stages, quien, log)
            applied = True

        # ── Bostezo ───────────────────────────────────────────────────────────
        if effect.get("yawn") and battle is not None:
            target_counter = "wild_yawn_counter" if is_player_attacker else "player_yawn_counter"
            if getattr(battle, target_counter) == 0:
                setattr(battle, target_counter, 1)
                log.append(f"  😪 ¡{defender_name} comenzó a adormilarse!\n")
            else:
                log.append("  💫 ¡Pero no tuvo efecto!\n")
            applied = True

        # ── Ailment ───────────────────────────────────────────────────────────
        if "ailment" in effect and battle is not None:
            ailment = effect["ailment"]

            if key == "rest":
                # Descanso: siempre duerme al ATACANTE (no al defensor).
                # Cura HP completo y cualquier status previo.
                attacker_pid = (
                    battle.player_pokemon_id
                    if is_player_attacker
                    else (battle.wild_pokemon.id_unico if hasattr(battle.wild_pokemon, "id_unico") else None)
                )
                attacker_status_key    = "player_status"    if is_player_attacker else "wild_status"
                attacker_sleep_key     = "player_sleep_turns" if is_player_attacker else "wild_sleep_turns"
                attacker_toxic_key     = "player_toxic_counter" if is_player_attacker else "wild_toxic_counter"

                if attacker_pid:
                    attacker_p = pokemon_service.obtener_pokemon(attacker_pid)
                    if attacker_p and attacker_p.hp_actual > 0:
                        hp_max = attacker_p.stats.get("hp", attacker_p.hp_actual)
                        db_manager.execute_update(
                            "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                            (hp_max, attacker_pid),
                        )
                        # Curar status previo
                        setattr(battle, attacker_status_key, None)
                        setattr(battle, attacker_toxic_key, 0)
                        # Aplicar sueño al atacante
                        setattr(battle, attacker_status_key, "slp")
                        setattr(battle, attacker_sleep_key, random.randint(2, 3))
                        log.append(
                            f"  💚 ¡<b>{attacker_name}</b> se curó completamente "
                            f"y se quedó dormido!\n"
                        )
                    else:
                        log.append(f"  💫 ¡{attacker_name} no puede usar Descanso!\n")
                applied = True

            else:
                # Ailment normal: apunta al DEFENSOR
                current_key = "wild_status" if is_player_attacker else "player_status"
                if getattr(battle, current_key) is not None:
                    log.append(f"  💫 ¡{defender_name} ya tiene una alteración!\n")
                else:
                    apply_ailment(
                        battle, ailment,
                        target_is_wild=is_player_attacker,
                        target_name=defender_name,
                        log=log,
                    )
            applied = True
        
        # ── Drenadoras (Leechseed) ────────────────────────────────────────────
        if effect.get("leechseed") and battle is not None:
            # El atacante siembra al defensor
            target_flag = "wild_leechseeded" if is_player_attacker else "player_leechseeded"
            if getattr(battle, target_flag, False):
                log.append(f"  🌿 ¡{defender_name} ya está sembrado con Drenadoras!\n")
            else:
                setattr(battle, target_flag, True)
                log.append(f"  🌿 ¡{defender_name} fue sembrado con Drenadoras!\n")
            applied = True

        # ── Clima ─────────────────────────────────────────────────────────────
        if "weather" in effect and battle is not None:
            w_key, w_turns = effect["weather"]
            activate_weather(battle, w_key, w_turns, attacker_name, log)
            applied = True

        # ── Terreno ───────────────────────────────────────────────────────────
        if "terrain" in effect and battle is not None:
            t_key, t_turns = effect["terrain"]
            activate_terrain(battle, t_key, t_turns, attacker_name, log)
            applied = True

        # ── Salas ─────────────────────────────────────────────────────────────
        if "room" in effect and battle is not None:
            room_attr = effect["room"]
            turns_attr = room_attr + "_turns"
            current = getattr(battle, room_attr, False)
            emoji, nombre, default_turns = ROOM_INFO.get(room_attr, ("", room_attr, 5))
            if current:
                # Segunda activación cancela el efecto
                setattr(battle, room_attr, False)
                setattr(battle, turns_attr, 0)
                log.append(f"  {emoji} <i>{nombre} terminó.</i>\n")
            else:
                setattr(battle, room_attr, True)
                setattr(battle, turns_attr, default_turns)
                log.append(f"  {emoji} ¡<b>{nombre}</b> está activo!\n")
            applied = True

        # ── Neblina ───────────────────────────────────────────────────────────
        if effect.get("haze") and battle is not None:
            for s in ("atq", "def", "atq_sp", "def_sp", "vel"):
                battle.wild_stat_stages[s]   = 0
                battle.player_stat_stages[s] = 0
            log.append("  🌫️ ¡Las etapas de todos los Pokémon volvieron a 0!\n")
            applied = True

        # ── Curación propia ───────────────────────────────────────────────────
        if "heal" in effect and battle is not None and key != "rest":
            heal_ratio = effect["heal"]
            if is_player_attacker:
                updated = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
                if updated:
                    max_hp = updated.stats.get("hp", updated.hp_actual) or updated.hp_actual
                    gained = max(1, int(max_hp * heal_ratio))
                    new_hp = min(max_hp, updated.hp_actual + gained)
                    updated.hp_actual = new_hp
                    try:
                        db_manager.execute_update(
                            "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                            (new_hp, battle.player_pokemon_id),
                        )
                    except Exception as _e:
                        logger.error(f"Error heal jugador: {_e}")
                    log.append(f"  💚 ¡{attacker_name} recuperó {gained} HP!\n")
                    applied = True
            else:
                wild   = battle.wild_pokemon
                max_hp = wild.hp_max
                gained = max(1, int(max_hp * heal_ratio))
                wild.hp_actual = min(max_hp, wild.hp_actual + gained)
                log.append(f"  💚 ¡{attacker_name} recuperó {gained} HP!\n")
                applied = True

        # ── Golpe crítico (Focus Energy / Laser Focus) ────────────────────
        if "crit_stage" in effect and battle is not None:
            crit_target, crit_delta = effect["crit_stage"]
            if crit_target == "self":
                stage_attr = "player_crit_stage" if is_player_attacker else "wild_crit_stage"
            else:
                stage_attr = "wild_crit_stage" if is_player_attacker else "player_crit_stage"

            current = getattr(battle, stage_attr, 0)
            new_val = min(3, current + crit_delta)   # cap en 3 (garantizado)
            setattr(battle, stage_attr, new_val)

            if new_val >= 3:
                log.append(f"  🎯 ¡{attacker_name if crit_target == 'self' else defender_name} "
                           f"garantiza golpes críticos!\n")
            else:
                log.append(f"  🎯 ¡{attacker_name if crit_target == 'self' else defender_name} "
                           f"está concentrado para asestar golpes críticos!\n")
            applied = True
        # ── Transformar ───────────────────────────────────────────────────────────────
        if effect.get("transform") and battle is not None:
            if is_player_attacker:
                # Jugador transforma → copia stats del wild
                wild = battle.wild_pokemon
                nombre_objetivo = wild.nombre_display()
                species_id      = getattr(wild, "pokemon_id", getattr(wild, "pokemonID", None))
                battle.player_transformed          = True
                battle.player_transform_stats      = dict(wild.stats)
                battle.player_transform_moves      = list(wild.moves)
                battle.player_transform_types      = list(getattr(wild, "tipos", ["Normal"]))
                battle.player_transform_species_id = species_id
                battle.player_transform_nombre     = nombre_objetivo
                log.append(
                    f"  🔄 ¡<b>{attacker_name}</b> se transformó en "
                    f"<b>{nombre_objetivo}</b>!\n"
                )
            else:
                # Wild transforma → copia stats del jugador (poco común, pero manejarlo)
                player = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
                if player:
                    wild = battle.wild_pokemon
                    wild.stats = dict(player.stats)
                    wild.moves = list(player.movimientos or [])
                    p_tipos    = pokedex_service.obtener_tipos(player.pokemonID)
                    wild.tipos = list(p_tipos)
                    log.append(
                        f"  🔄 ¡<b>{wild.nombre}</b> se transformó en "
                        f"<b>{attacker_name}</b>!\n"
                    )
            applied = True

        # ── Huida garantizada (Teleport) ─────────────────────────────────────
        if effect.get("flee") and is_player_attacker and battle is not None:
            log.append(f"  📡 ¡{attacker_name} usó Teleport!\n")
            battle._teleport_flee = True
            return "flee"

        # ── Pivot de estado (Parting Shot, etc.): efecto + jugador elige ──────
        # Nota: U-turn/Volt Switch tienen power > 0 y se manejan en execute_move.
        # Aquí solo entran movimientos de Estado con {"pivot": True}.
        if effect.get("pivot") and is_player_attacker and battle is not None:
            move_es = MOVE_NAMES_ES.get(
                move_name.lower().replace(" ", ""), move_name.title()
            )
            log.append(f"  💨 ¡{attacker_name} usó {move_es} y volvió!\n")
            battle.awaiting_pivot_switch = True
            return "pivot"

        # ── Switch forzado (Remolino, Rugido) — el salvaje lo usa ─────────────
        if effect.get("forced_switch") and not is_player_attacker and battle is not None:
            # Manejado directamente en _execute_wild_turn
            return "forced_switch"

        if not applied:
            log.append(f"  💫 ¡{attacker_name} usó {move_name.title()}!\n")
        return applied
            
    def attempt_flee(self, user_id: int, bot) -> bool:
        """Intenta huir del combate"""
        try:
            battle = self.get_battle(user_id)
            if not battle or battle.state != BattleState.ACTIVE:
                return False

            if getattr(battle, "awaiting_faint_switch", False):
                return False   # No se puede huir mientras se elige reemplazo
            
            player_pokemon = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
            if not player_pokemon:
                return False
            
            wild = battle.wild_pokemon
            battle.flee_attempts += 1
            
            # Calcular probabilidad de huir
            flee_chance = BattleUtils.calculate_flee_chance(
                player_pokemon.stats['vel'],
                wild.stats['vel'],
                battle.flee_attempts
            )
            
            success = random.random() < flee_chance
            
            if success:
                # Huida exitosa
                battle.state = BattleState.FLED                
                # Limpiar spawn
                spawn_service.limpiar_spawn(battle.thread_id)
                if battle.group_chat_id and battle.group_message_id:
                    try:
                        nombre_usuario = bot.get_chat(user_id).first_name
                        bot.edit_message_caption(
                            caption=(
                                f"🏃 <b>{nombre_usuario} huyó del combate</b>\n\n"
                                f"El {wild.nombre} sigue libre..."
                            ),
                            chat_id=battle.group_chat_id,
                            message_id=battle.group_message_id,
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.warning(f"No se pudo editar mensaje del grupo: {e}")

                del self.active_battles[user_id]
                
                text = (
                    f"🏃 <b>¡Huiste con éxito!</b>\n\n"
                    f"Te escapaste de {wild.nombre}."
                )
                self._edit_battle_message(bot, user_id, battle.message_id, text)
                logger.info(f"[BATTLE] Usuario {user_id} huyó exitosamente")
                return True
                
            else:
                # Huida fallida - turno del enemigo
                enemy_move_name = random.choice(wild.moves)
                enemy_move_data = movimientos_service.obtener_movimiento(enemy_move_name)
                
                enemy_damage = BattleUtils.calculate_damage(
                    attacker_level=wild.nivel,
                    attacker_stat=wild.stats['atq'],
                    defender_stat=player_pokemon.stats['def'],
                    move_power=enemy_move_data.get('basePower', 40) if enemy_move_data else 40
                )
                
                player_pokemon.hp_actual = max(0, player_pokemon.hp_actual - enemy_damage)
                player_pokemon.guardar()
                
                text = (
                    f"❌ <b>¡No pudiste huir!</b>\n\n"
                    f"🔴 {wild.nombre} usó <b>{enemy_move_name}</b>\n"
                    f"💥 Causó {enemy_damage} de daño\n\n"
                )
                
                # Verificar si fue derrotado
                if player_pokemon.hp_actual == 0:
                    self._handle_defeat(battle, bot)
                    return True
                
                text += self._get_battle_status(battle, player_pokemon)
                
                self._edit_battle_message(bot, user_id, battle.message_id, text)
                import threading
                threading.Timer(2.0, lambda: self._send_battle_menu(battle, bot)).start()
                
                return True
            
        except Exception as e:
            logger.error(f"Error intentando huir: {e}")
            return False
    
    def _get_battle_status(self, battle: BattleData, player_pokemon) -> str:
        """Genera el texto del estado actual de la batalla"""
        wild = battle.wild_pokemon
        
        return (
            f"━━━━━━━━━━━━━━━\n"
            f"🔴 {wild.nombre_display()}: {wild.hp_actual}/{wild.hp_max} HP\n"
            f"🔵 {player_pokemon.nombre}: {player_pokemon.hp_actual}/{player_pokemon.stats['hp']} HP"
        )
    
    def _handle_victory(self, battle, player_pokemon, bot):
        """
        Procesa la victoria del jugador.
 
        CAMBIOS:
        - Se cancela el timer SIEMPRE al entrar.
        - La victoria ya llega con delay desde execute_move (2.5s),
          por lo que no se añade un delay adicional aquí.
        """
        try:
            # ── Cancelar timer SIEMPRE ────────────────────────────────────────
            self._cancel_turn_timer(battle)
 
            wild    = battle.wild_pokemon
            user_id = battle.user_id
 
            # Si player_pokemon no se pasó o es None, intentar releer
            if player_pokemon is None:
                player_pokemon = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
 
            exp_ganada = ExperienceSystem.exp_por_victoria(
                nivel_enemigo      = wild.nivel,
                pokemon_id_enemigo = wild.pokemon_id,
                nivel_ganador      = player_pokemon.nivel if player_pokemon else 1,
                es_salvaje         = True,
                es_entrenador      = False,
            )
            money_reward = max(10, min(50, 10 + wild.nivel * 40 // 100))
            economy_service.add_credits(user_id, money_reward, "Victoria en batalla Pokémon")
 
            linea_exp = _repartir_experiencia(battle, exp_ganada, user_id, bot, delay=1.0)
 
            text = (
                f"🏆 <b>¡Victoria!</b>\n\n"
                f"🔴 {wild.nombre} fue derrotado.\n\n"
                f"{linea_exp}\n"
                f"💰 Ganaste <b>{money_reward} cosmos</b>\n"
            )
 
            # EVs al Pokémon activo
            try:
                from pokemon.services.ev_service import ev_service
                _, _ev_log = ev_service.otorgar_evs(
                    ganador_id           = battle.player_pokemon_id,
                    derrotado_pokemon_id = wild.pokemon_id,
                )
                if _ev_log:
                    text += _ev_log
            except Exception as _ev_e:
                logger.error(f"[EV] Error en victoria: {_ev_e}")
 
            # Restaurar posiciones del equipo
            try:
                if battle.posiciones_originales:
                    pokemon_service.restaurar_posiciones(battle.posiciones_originales)
            except Exception as _rp_e:
                logger.error(f"[POS] Error restaurando posiciones: {_rp_e}")
 
            # Limpiar estado
            spawn_service.limpiar_spawn(battle.thread_id)
            if user_id in self.active_battles:
                del self.active_battles[user_id]
 
            self._edit_battle_message(bot, user_id, battle.message_id, text)
 
            logger.info(
                f"[BATTLE] Victoria: Usuario {user_id} derrotó {wild.nombre} "
                f"Nv.{wild.nivel} → +{exp_ganada} EXP, +{money_reward} cosmos"
            )
 
        except Exception as e:
            logger.error(f"Error procesando victoria: {e}", exc_info=True)
    
    def _handle_defeat(self, battle, bot):
        """
        Procesa la derrota del jugador.
 
        CAMBIOS:
        - Se cancela el timer SIEMPRE al entrar.
        - Si quedan reemplazos: se muestra el selector de Pokémon CON el
          keyboard correcto Y sin arrancar ningún timer (el jugador no
          tiene límite de tiempo para elegir reemplazo).
        - Si es derrota total: se edita el mensaje final directamente
          (sin delay adicional porque el llamador ya puso un delay).
        """
        try:
            # ── Cancelar timer SIEMPRE ────────────────────────────────────────
            self._cancel_turn_timer(battle)
 
            wild    = battle.wild_pokemon
            user_id = battle.user_id
 
            player_pokemon = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
            if not player_pokemon:
                return
 
            team = pokemon_service.obtener_equipo(user_id)
            has_more = any(
                p.hp_actual > 0 and p.id_unico != battle.player_pokemon_id
                for p in team
            )
 
            if has_more:
                # ── Mostrar selector de reemplazo ─────────────────────────────
                # NO se arranca el timer aquí — el jugador elige sin presión.
                p_name = player_pokemon.mote or player_pokemon.nombre
                text = (
                    f"💀 <b>{p_name} fue derrotado!</b>\n\n"
                    "¿Enviás otro Pokémon?"
                )
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(
                    types.InlineKeyboardButton(
                        "👥 Elegir Pokémon",
                        callback_data=f"battle_team_{user_id}"
                    )
                )
                keyboard.add(
                    types.InlineKeyboardButton(
                        "🏳️ Rendirse",
                        callback_data=f"battle_forfeit_{user_id}"
                    )
                )
                battle.state                = BattleState.ACTIVE
                battle.awaiting_faint_switch = True
                self._edit_battle_message(bot, user_id, battle.message_id, text, keyboard)
                # No llamar _start_turn_timer aquí
                return
 
            # ── Derrota total ─────────────────────────────────────────────────
            text = (
                f"💀 <b>Derrota</b>\n\n"
                f"{wild.nombre} derrotó a todos tus Pokémon.\n\n"
                "Ve al Centro Pokémon para curarlos."
            )
            battle.state = BattleState.PLAYER_LOSE
 
            # Restaurar posiciones del equipo
            try:
                if battle.posiciones_originales:
                    pokemon_service.restaurar_posiciones(battle.posiciones_originales)
            except Exception as _rp_e:
                logger.error(f"[POS] Error restaurando posiciones en derrota: {_rp_e}")
 
            spawn_service.limpiar_spawn(battle.thread_id)
            if user_id in self.active_battles:
                del self.active_battles[user_id]
 
            self._edit_battle_message(bot, user_id, battle.message_id, text)
 
        except Exception as e:
            logger.error(f"Error procesando derrota: {e}", exc_info=True)
    
    def _on_pokemon_enter(self, battle, nuevo_pokemon_id: int, log: list) -> None:
        """
        Aplica efectos de entrada cuando un Pokémon nuevo sale a combatir.
 
        CAMBIOS:
        - Limpia charging_move y recharge_pending del Pokémon entrante
          (no hereda estados de 2-turno del anterior).
        - Limpia cualquier pending_action residual del turno anterior.
        """
        # Resetear etapas del jugador (volátiles: no se transfieren)
        battle.player_stat_stages = {
            "atq": 0, "def": 0, "atq_sp": 0, "def_sp": 0, "vel": 0
        }
        # Resetear estados volátiles
        battle.player_yawn_counter    = 0
        battle.player_crit_stage      = 0
        battle.player_confusion_turns = 0
 
        # ── NUEVO: limpiar mecánicas de 2-turno ───────────────────────────────
        # El Pokémon entrante no hereda una carga o recarga del anterior.
        battle.player_charging_move    = None
        battle.player_recharge_pending = False
 
        # ── NUEVO: limpiar pending action residual ────────────────────────────
        # Si el turno anterior quedó con algún movimiento "elegido" pero
        # no ejecutado (edge case de race condition), lo limpiamos aquí.
        # (En wild battles no hay pending_action explícito; el equivalente
        #  es el flag awaiting_faint_switch que ya se limpia en switch_pokemon)
 
        # Log de ingreso
        nuevo_p = pokemon_service.obtener_pokemon(nuevo_pokemon_id)
        if nuevo_p:
            nombre = nuevo_p.mote or nuevo_p.nombre
            hp_max = nuevo_p.stats.get("hp", 1) or 1
            log.append(
                f"  🔄 ¡<b>{nombre}</b> salió a combatir! "
                f"({nuevo_p.hp_actual}/{hp_max} HP)\n"
            )
            # ── Habilidades de entrada ─────────────────────────────────────────
            hab_str = (getattr(nuevo_p, "habilidad", "") or "").lower().replace(" ", "").replace("-", "")
            from pokemon.battle_engine import apply_entry_abilities_ordered
            from pokemon.battle_adapter import side_from_player, side_from_wild, sync_player_side, sync_wild_side
 
            p_side = side_from_player(nuevo_p, battle)
            w_side = side_from_wild(battle.wild_pokemon, battle)
            apply_entry_abilities_ordered(p_side, w_side, battle, log)
            sync_player_side(p_side, battle, persist=False)
            sync_wild_side(w_side, battle.wild_pokemon, battle)
 
            # Intimidación explícita (compatibilidad)
            if hab_str in ("intimidacion", "intimidation"):
                wild_p = getattr(battle, "wild_pokemon", None)
                if wild_p:
                    _old_stg = battle.wild_stat_stages.get("atq", 0)
                    battle.wild_stat_stages["atq"] = max(-6, _old_stg - 1)
                    if battle.wild_stat_stages["atq"] < _old_stg:
                        log.append(
                            f"  😤 ¡<b>Intimidación</b> de {nombre} bajó el "
                            f"Ataque de {wild_p.nombre}!\n"
                        )
 
            # Impostor
            if hab_str == "impostor":
                wild_imp    = battle.wild_pokemon
                hp_orig     = nuevo_p.hp_actual
                hp_max_orig = nuevo_p.stats.get("hp", hp_orig)
                new_stats   = {k: v for k, v in wild_imp.stats.items() if k != "hp"}
                new_stats["hp"]     = hp_max_orig
                nuevo_p.stats       = new_stats
                nuevo_p.movimientos = list(wild_imp.moves)
                nuevo_p.hp_actual   = hp_orig
                battle.player_stat_stages = dict(battle.wild_stat_stages)
                battle.player_transformed     = False
                battle.player_transform_stats = None
                battle.player_transform_moves = None
                battle.player_transform_types = None
                log.append(
                    f"  🔄 ¡<b>{nombre}</b> se transformó en "
                    f"<b>{wild_imp.nombre}</b> (Impostor)!\n"
                )
        

    # ─────────────────────────────────────────────────────────────────────────────
    # Helpers: persistencia de status por Pokémon individual
    # ─────────────────────────────────────────────────────────────────────────────

    def _save_player_status(self, battle: "BattleData", pokemon_id: int) -> None:
        """
        Guarda el estado volátil-persistente del Pokémon activo antes de salir.
        No guarda confusión (es volátil y se borra siempre al salir).
        """
        battle.player_leechseeded = False
        battle._pokemon_statuses[pokemon_id] = {
            "status":        battle.player_status,
            "sleep_turns":   battle.player_sleep_turns,
            "toxic_counter": battle.player_toxic_counter,
        }
        logger.debug(
            f"[SWITCH] Guardado status pokémon {pokemon_id}: "
            f"{battle._pokemon_statuses[pokemon_id]}"
        )

    def _restore_player_status(self, battle: "BattleData", pokemon_id: int) -> None:
        """
        Restaura el estado del Pokémon que entra a combatir.
        Confusión siempre empieza en 0 (es volátil).
        """
        saved = battle._pokemon_statuses.get(pokemon_id, {})
        battle.player_status         = saved.get("status",        None)
        battle.player_sleep_turns    = saved.get("sleep_turns",   0)
        battle.player_toxic_counter  = saved.get("toxic_counter", 0)
        # leechseeded no se restaura: las Drenadoras se curan al hacer switch
        battle.player_confusion_turns = 0
        logger.debug(
            f"[SWITCH] Restaurado status pokémon {pokemon_id}: "
            f"status={battle.player_status}"
        )
    def switch_pokemon(self, user_id: int, new_pokemon_id: int, bot, is_post_pivot: bool = False) -> bool:
        """
        Cambia el Pokémon activo en batalla.
 
        CAMBIOS:
        - Al inicio, SIEMPRE se cancela el timer activo (previene timeout
          mientras el jugador estaba eligiendo reemplazo).
        - Faint switch ya NO activa el timer hasta que se muestre el panel
          actualizado (se llama al final).
        - Se limpian charging_move y recharge_pending al entrar (via
          _on_pokemon_enter).
        """
        try:
            battle = self.get_battle(user_id)
            if not battle or battle.state != BattleState.ACTIVE:
                return False
 
            # ── Cancelar timer SIEMPRE al cambiar Pokémon ────────────────────
            self._cancel_turn_timer(battle)
 
            new_pokemon = pokemon_service.obtener_pokemon(new_pokemon_id)
            if not new_pokemon or new_pokemon.hp_actual == 0:
                return False
 
            # Leer flag antes de modificar
            is_faint_switch: bool = getattr(battle, "awaiting_faint_switch", False)
            battle.awaiting_faint_switch = False
 
            old_pokemon = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
            if not old_pokemon:
                logger.error("Pokemon no encontrado")
                return False
 
            # Guardar status del Pokémon que sale
            self._save_player_status(battle, old_pokemon.id_unico)
 
            battle.player_pokemon_id = new_pokemon_id
            battle.participant_ids.add(new_pokemon_id)
 
            old_id = old_pokemon.id_unico
            new_id = new_pokemon_id
            pokemon_service.intercambiar_posiciones(old_id, new_id)
 
            battle.awaiting_pivot_switch = False
 
            # Checks de entrada: resetea stages, confusión, bostezo,
            # charging_move, recharge_pending, habilidades
            entry_log: list = []
            self._on_pokemon_enter(battle, new_pokemon_id, entry_log)
 
            # Restaurar status persistente del Pokémon que entra
            self._restore_player_status(battle, new_pokemon_id)
 
            # ── Post-pivot: el wild NO contraataca ────────────────────────────
            if is_post_pivot:
                self._refresh_battle_ui(battle, user_id, bot, extra_log=entry_log)
                self._start_turn_timer(battle, user_id, bot)
                return True
 
            # ── Faint switch: reemplazo limpio — wild NO contraataca ──────────
            if is_faint_switch:
                self._refresh_battle_ui(battle, user_id, bot, extra_log=entry_log)
                # Timer empieza DESPUÉS de que el panel se actualiza
                self._start_turn_timer(battle, user_id, bot)
                return True
 
            # ── Hard switch: cambio voluntario — wild SÍ contraataca ──────────
            enemy_log = self._execute_wild_turn(battle)
            all_log   = entry_log + enemy_log
 
            updated_new = pokemon_service.obtener_pokemon(new_pokemon_id)
            if updated_new and updated_new.hp_actual <= 0:
                self._refresh_battle_ui(battle, user_id, bot, extra_log=all_log)
                import threading as _th
                _th.Timer(1.5, lambda: self._handle_defeat(battle, bot)).start()
                return True
 
            self._refresh_battle_ui(battle, user_id, bot, extra_log=all_log)
            self._start_turn_timer(battle, user_id, bot)
            return True
 
        except Exception as e:
            logger.error(f"Error cambiando Pokémon: {e}")
            return False

    def _format_move_button(self, move_id: str, pokemon_id: int) -> tuple[str, str]:
        """
        Retorna (label_nombre, label_info) para el layout de 2 columnas.

        label_nombre : "Placaje (40)"
        label_info   : "⚪Normal  ⚔️Físico  PP:35/35"
        """
        move_data = movimientos_service.obtener_movimiento(move_id)

        # ── Nombre en español ────────────────────────────────────────────────
        nombre_es = MOVE_NAMES_ES.get(move_id.lower().replace(' ', ''), None)
        if not nombre_es:
            nombre_es = (
                move_data.get('nombre', move_id.title())
                if move_data else move_id.title()
            )

        # ── Poder ────────────────────────────────────────────────────────────
        poder = int((move_data.get('poder', 0) or 0)) if move_data else 0

        # ── Tipo y emoji ─────────────────────────────────────────────────────
        tipo       = move_data.get('tipo', 'Normal') if move_data else 'Normal'
        tipo_emoji = MOVE_TYPE_EMOJI.get(tipo, '⚪')

        # ── Categoría y emoji ────────────────────────────────────────────────
        categoria  = move_data.get('categoria', 'Estado') if move_data else 'Estado'
        cat_emoji  = MOVE_CAT_EMOJI.get(categoria, '💫')

        # ── PP ───────────────────────────────────────────────────────────────
        try:
            from pokemon.services.pp_service import pp_service
            pp = pp_service.obtener_pp(pokemon_id, move_id)
            pp_text = f"{pp['actual']}/{pp['maximo']}"
        except Exception:
            pp_max  = move_data.get('pp', '?') if move_data else '?'
            pp_text = f"{pp_max}/{pp_max}"

        # Tipo + nombre en el botón izquierdo; categoría + PP en el derecho
        if poder:
            label_nombre = f"{tipo_emoji} {nombre_es} ({poder})"
        else:
            label_nombre = f"{tipo_emoji} {nombre_es}"
        label_info = f"{cat_emoji}{categoria} {pp_text}"

        return label_nombre, label_info
    
# ══════════════════════════════════════════════════════════════════════════════
# MÉTODO: _cancel_turn_timer  (NUEVO)
# ══════════════════════════════════════════════════════════════════════════════

    def _cancel_turn_timer(self, battle):
        """Cancela el timer de turno activo (si existe)."""
        try:
            t = getattr(battle, "turn_timer", None)
            if t is not None:
                t.cancel()
                battle.turn_timer = None
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# MÉTODO: _turn_timeout  (NUEVO)
# ══════════════════════════════════════════════════════════════════════════════

    def _turn_timeout(self, user_id: int, turn_number_expected: int, bot):
        """
        Llamado cuando el timer de 30 s expira sin que el jugador actúe.
        Si el turno sigue siendo el mismo (el jugador no hizo nada),
        ejecuta el turno del salvaje como penalidad.
        """
        try:
            battle = self.get_battle(user_id)
            if not battle or battle.state != BattleState.ACTIVE:
                return
            # El jugador está eligiendo reemplazo → no penalizar nunca
            if getattr(battle, "awaiting_faint_switch", False):
                return
            if getattr(battle, "awaiting_pivot_switch", False):
                return
            # Si el turn_number ya avanzó, el jugador actuó → no hacer nada
            if battle.turn_number != turn_number_expected:
                return
 
            logger.info(f"[BATTLE] Timeout de turno para usuario {user_id}")
 
            penalty_log = ["⏰ <b>¡Tiempo agotado!</b> Perdiste tu turno.\n"]
            enemy_log   = self._execute_wild_turn(battle)
            penalty_log.extend(enemy_log)
 
            # ¿Jugador derrotado?
            updated = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
            if updated and updated.hp_actual <= 0:
                # Mostrar lo que pasó antes de procesar la derrota
                self._refresh_battle_ui(battle, user_id, bot, extra_log=penalty_log)
                import threading as _th
                _th.Timer(2.0, lambda: self._handle_defeat(battle, bot)).start()
                return
 
            self._refresh_battle_ui(battle, user_id, bot, extra_log=penalty_log)
 
            # Arrancar nuevo timer para el siguiente turno
            self._start_turn_timer(battle, user_id, bot)
 
        except Exception as e:
            logger.error(f"Error en _turn_timeout: {e}", exc_info=True)


# ══════════════════════════════════════════════════════════════════════════════
# MÉTODO: _start_turn_timer  (NUEVO)
# ══════════════════════════════════════════════════════════════════════════════

    def _start_turn_timer(self, battle, user_id: int, bot, seconds: int = 30):
        """
        Arranca (o reinicia) el timer para el turno actual.
 
        GUARD: nunca arrancar el timer mientras el jugador está eligiendo
        reemplazo por faint switch; en ese estado no hay límite de tiempo.
        """
        # ── Guard: faint switch no tiene timer ────────────────────────────────
        if getattr(battle, "awaiting_faint_switch", False):
            return
        # ── Guard: pivot pendiente tampoco tiene timer ────────────────────────
        if getattr(battle, "awaiting_pivot_switch", False):
            return
 
        self._cancel_turn_timer(battle)
        turn_snapshot = battle.turn_number
        t = threading.Timer(
            seconds,
            self._turn_timeout,
            args=(user_id, turn_snapshot, bot)
        )
        t.daemon = True
        t.start()
        battle.turn_timer = t

def _repartir_experiencia(
    battle,
    exp_total: int,
    user_id: int,
    bot,
    delay: float = 2.5,
) -> str:
        """
        Reparte exp_total entre los participantes del combate.

        Lógica con Repartidor de EXP (slot 0 del equipo tiene 'repartidor_exp'):
        - La EXP se divide equitativamente entre TODOS los pokémon del equipo
            que tengan un id_unico válido, incluyendo los debilitados.
            (Comportamiento oficial Gen 6+: el Exp. Share beneficia a todo el equipo.)

        Lógica sin Repartidor de EXP:
        - Solo reciben EXP los pokémon que participaron en el combate
            Y que no estén debilitados (hp_actual > 0).
            Si ninguno cumple ambas condiciones, se usa el primer pokémon vivo
            como fallback.

        Returns:
            Texto HTML con el resumen de EXP repartida (listo para incrustar
            en el mensaje de victoria).
        """
        from pokemon.level_up_handler import LevelUpHandler

        equipo = pokemon_service.obtener_equipo(user_id)
        if not equipo:
            return ""

        # ── Verificar si el primer slot lleva el Repartidor de EXP ──────────────
        lider = equipo[0]
        tiene_repartidor = getattr(lider, "objeto", None) == "repartidor_exp"

        if tiene_repartidor:
            # ── CON repartidor: TODOS los pokémon del equipo reciben EXP ─────────
            # Incluye debilitados (comportamiento oficial Gen 6+).
            # Solo excluimos entradas sin id_unico (datos corruptos).
            receptores = [p for p in equipo if p.id_unico]
        else:
            # ── SIN repartidor: solo participantes vivos ──────────────────────────
            # Un pokémon debilitado NO recibe EXP aunque haya participado.
            participantes = battle.participant_ids or {battle.player_pokemon_id}
            receptores = [
                p for p in equipo
                if p.id_unico in participantes and p.hp_actual > 0
            ]

            # Fallback: si ningún participante sobrevivió, primer pokémon vivo
            if not receptores:
                receptores = [p for p in equipo if p.hp_actual > 0][:1]

        if not receptores:
            return ""   # equipo completamente debilitado y sin repartidor

        # ── Reparto equitativo ────────────────────────────────────────────────────
        exp_cada_uno = max(1, exp_total // len(receptores))
        lineas: list[str] = []
        pendientes_levelup: list = []   # (pokemon_id, exp_result)

        for p in receptores:
            resultado = ExperienceSystem.aplicar_experiencia(p.id_unico, exp_cada_uno)
            nombre = p.mote or p.nombre

            # Indicar si el pokémon estaba debilitado al recibir EXP
            estado = " <i>(debilitado)</i>" if p.hp_actual <= 0 else ""
            lineas.append(f"  💫 <b>{nombre}</b>{estado} ganó <b>{exp_cada_uno} EXP</b>")

            if resultado.get("subio_nivel"):
                lineas.append(
                    f"  ✨ ¡<b>{nombre}</b> subió al nivel "
                    f"<b>{resultado['nivel_nuevo']}</b>!"
                )
                pendientes_levelup.append((p.id_unico, resultado))

        # Encadenar los levelups en COLA: el siguiente arranca solo cuando
        # el anterior terminó (on_complete → siguiente).
        def _encolar_levelups(pending: list, idx: int):
            if idx >= len(pending):
                return
            pid, exp_res = pending[idx]
            LevelUpHandler.procesar_subida(
                bot=bot,
                user_id=user_id,
                pokemon_id=pid,
                exp_result=exp_res,
                delay=delay if idx == 0 else 0.5,
                on_complete=lambda: _encolar_levelups(pending, idx + 1),
            )

        if pendientes_levelup:
            _encolar_levelups(pendientes_levelup, 0)

        prefijo = "🎁 <b>Repartidor de EXP activo</b>\n" if tiene_repartidor else ""
        return prefijo + "\n".join(lineas)
# ============================================================================
# INSTANCIA GLOBAL
# ============================================================================

wild_battle_manager = WildBattleManager()