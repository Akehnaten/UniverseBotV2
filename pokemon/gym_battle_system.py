# -*- coding: utf-8 -*-
"""
pokemon/gym_battle_system.py
═════════════════════════════════════════════════════════════════════════════
Sistema de Batalla de Gimnasio y Alto Mando

Flujo:
  1. Usuario usa /gimnasio → GymCommandHandler detecta el siguiente líder
  2. Se llama GymBattleManager.start_battle() →
       a. gimnasio_service.puede_desafiar_lider() valida el acceso
       b. gimnasio_service.crear_equipo_lider() crea los Pokémon NPC en BD
       c. Se inicializa GymBattleData y se muestra la UI de batalla
  3. Cada turno del jugador → GymBattleManager.handle_move()
  4. Cada turno del NPC   → _exec_npc_move() usa GymBattleAI.seleccionar_movimiento()
  5. Cuando un Pokémon del NPC cae → _on_npc_faint() avanza al siguiente
  6. Victoria → gimnasio_service.otorgar_medalla() + limpiar_equipo_npc()
  7. Derrota / rendición → limpiar_equipo_npc() sin medalla

Nomenclatura interna:
  "wild_*"   → lado NPC  (mismos nombres que battle_engine espera)
  "player_*" → lado jugador

Registrar en UniverseBot.py:
    from pokemon.gym_battle_system import gym_cmd, gym_manager
    gym_cmd.register(bot)
═════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from telebot import types

from database import db_manager
from pokemon.battle_engine import (
    BattleUtils,
    DamageResult,
    UniversalSide, 
    apply_move, 
    apply_end_of_turn, 
    apply_entry_ability,
    check_confusion,
    resolve_damage_move,
    apply_stage_change,
    determine_turn_order,
    apply_ailment,
    check_can_move,
    can_apply_ailment_in_field,
    tick_field_turns,
    activate_weather,
    activate_terrain,
    apply_weather_boost,
    apply_terrain_boost,
    is_grounded,
    MOVE_EFFECTS,
    SECONDARY_AILMENTS,
    DRAIN_MOVES,
    RECOIL_MOVES,
    MOVE_NAMES_ES,
    STATUS_ICONS,
    _HIGH_CRIT_MOVES,
)
from pokemon.services import (
    pokemon_service,
    movimientos_service,
    pokedex_service,
)
from pokemon.services.pp_service import pp_service
from pokemon.services.gimnasio_service import GymBattleAI, gimnasio_service
from pokemon.experience_system import ExperienceSystem
from pokemon.battle_adapter import (
          side_from_gym_player, side_from_gym_npc,
          sync_gym_player, sync_gym_npc,)
from pokemon.battle_ui import build_pokemon_line
from pokemon.services.pokedex_service import pokedex_service as _pdx_svc
from config import POKECLUB
from utils.thread_utils import get_thread_id

logger = logging.getLogger(__name__)

_BATTLE_TIMEOUT = 120   # segundos por turno antes de cancelar
_BATTLE_EXPIRY  = 1800  # segundos totales antes de expirar la batalla


# ═════════════════════════════════════════════════════════════════════════════
# ENUMS
# ═════════════════════════════════════════════════════════════════════════════
MOVE_TYPE_EMOJI: dict = {
    "Normal": "⚪", "Fuego": "🔥", "Agua": "💧", "Planta": "🌿",
    "Eléctrico": "⚡", "Hielo": "🧊", "Lucha": "🥊", "Veneno": "☠️",
    "Tierra": "🌍", "Volador": "🌪️", "Psíquico": "🔮", "Bicho": "🐛",
    "Roca": "🪨", "Fantasma": "👻", "Dragón": "🐉", "Siniestro": "🌑",
    "Acero": "⚙️", "Hada": "🌸",
}
MOVE_CAT_EMOJI: dict = {
    "Físico": "⚔️", "Especial": "✨", "Estado": "💫",
}

class GymBattleState(str, Enum):
    ACTIVE         = "active"
    PLAYER_WIN     = "player_win"
    PLAYER_LOSE    = "player_lose"
    PLAYER_FORFEIT = "forfeit"
    SWITCHING      = "switching"   # jugador eligiendo nuevo Pokémon


# ═════════════════════════════════════════════════════════════════════════════
# DATACLASS DE ESTADO
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class GymBattleData:
    """Estado completo de una batalla de gimnasio o Alto Mando en curso."""

    user_id:           int
    chat_id:           int
    thread_id:         Optional[int]   # hilo del mensaje (None en privado)
    lider_id:          str
    is_e4:             bool

    # NPC — equipo creado por gimnasio_service.crear_equipo_lider()
    npc_equipo_ids:    List[int]      # id_unico de cada Pokémon NPC
    npc_current_index: int = 0        # índice activo en npc_equipo_ids

    # ── Lado NPC ("wild_*" para compatibilidad con battle_engine) ─────────
    wild_stat_stages:   Dict[str, int] = field(
        default_factory=lambda: {"atq": 0, "def": 0, "atq_sp": 0, "def_sp": 0, "vel": 0}
    )
    wild_status:          Optional[str] = None
    wild_sleep_turns:     int = 0
    wild_toxic_counter:   int = 0
    wild_yawn_counter:    int = 0
    wild_leechseeded:     bool = False
    wild_confusion_turns:   int = 0
    npc_setup_counter:    int = 0     # setup moves usados con el Pokémon actual del NPC
    npc_delayed_attacks:    list = field(default_factory=list)
    npc_charging_move:        Optional[str] = None
    npc_focus_interrupted:    bool          = False

    # ── Lado jugador ──────────────────────────────────────────────────────
    player_pokemon_id:  int = 0
    player_stat_stages: Dict[str, int] = field(
        default_factory=lambda: {"atq": 0, "def": 0, "atq_sp": 0, "def_sp": 0, "vel": 0}
    )
    player_status:        Optional[str] = None
    player_sleep_turns:   int = 0
    player_toxic_counter: int = 0
    player_yawn_counter:  int = 0
    player_leechseeded:     bool = False
    player_confusion_turns: int = 0
    player_delayed_attacks: list = field(default_factory=list)
    player_charging_move:        Optional[str] = None
    player_focus_interrupted: bool          = False
    # Status persistente por Pokémon individual (clave = id_unico).
    # Permite que veneno, sueño, drenadoras, etc. sobrevivan al switch.
    # Formato: { pokemon_id: {"status": ..., "sleep_turns": ...,
    #                          "toxic_counter": ..., "leechseeded": ...} }
    _pokemon_statuses:      dict = field(default_factory=dict)
    is_faint_switch: bool = False # True → el switch no consume turno del NPC

    # ── Campo de batalla ──────────────────────────────────────────────────
    weather:          Optional[str] = None
    weather_turns:    int = 0
    terrain:          Optional[str] = None
    terrain_turns:    int = 0
    trick_room:       bool = False
    trick_room_turns: int = 0
    gravity:          bool = False
    gravity_turns:    int = 0
    magic_room:       bool = False
    magic_room_turns: int = 0
    wonder_room:      bool = False
    wonder_room_turns: int = 0

    # ── Control ───────────────────────────────────────────────────────────
    state:       GymBattleState = GymBattleState.ACTIVE
    message_id:  Optional[int] = None
    turn_number: int = 0
    battle_log:  List[str] = field(default_factory=list)
    turn_timer:  Optional[threading.Timer] = field(default=None, repr=False)
    created_at:  float = field(default_factory=time.time)

    @property
    def npc_pokemon_id(self) -> Optional[int]:
        if self.npc_current_index < len(self.npc_equipo_ids):
            return self.npc_equipo_ids[self.npc_current_index]
        return None

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > _BATTLE_EXPIRY


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS UI
# ═════════════════════════════════════════════════════════════════════════════

def _hp_bar(hp: int, hp_max: int, length: int = 10) -> str:
    pct    = (hp / max(hp_max, 1)) * 100
    filled = max(0, min(length, round(pct / 100 * length)))
    color  = "🟢" if pct > 50 else ("🟡" if pct > 20 else "🔴")
    return color * filled + "⬛" * (length - filled)


# ═════════════════════════════════════════════════════════════════════════════
# GESTOR DE BATALLAS
# ═════════════════════════════════════════════════════════════════════════════

class GymBattleManager:
    """Orquesta el ciclo completo de una batalla de gimnasio o Alto Mando."""

    def __init__(self):
        self._battles:      Dict[int, GymBattleData] = {}
        self._lock          = threading.Lock()
        self._cleanup_last  = time.time()

    # ── Mapa de batallas ──────────────────────────────────────────────────

    def _cleanup(self) -> None:
        if time.time() - self._cleanup_last < 60:
            return
        with self._lock:
            expired = [(uid, b) for uid, b in self._battles.items() if b.is_expired()]
            for uid, b in expired:
                self._battles.pop(uid, None)
                self._cancel_timer(b)
                # Borrar solo los NPCs de ESA batalla expirada
                if b.npc_equipo_ids:
                    gimnasio_service.limpiar_equipo_npc_ids(b.npc_equipo_ids)
                else:
                    gimnasio_service.limpiar_equipo_npc()
                logger.info(f"[GYM] Batalla expirada limpiada: user {uid}")
        self._cleanup_last = time.time()

    def has_active_battle(self, user_id: int) -> bool:
        self._cleanup()
        return user_id in self._battles

    def get_battle(self, user_id: int) -> Optional[GymBattleData]:
        return self._battles.get(user_id)

    def _remove_battle(self, user_id: int) -> None:
        with self._lock:
            battle = self._battles.pop(user_id, None)
        if battle:
            self._cancel_timer(battle)
            # Borrar SOLO los NPC de esta batalla (no afectar otras en curso)
            if battle.npc_equipo_ids:
                gimnasio_service.limpiar_equipo_npc_ids(battle.npc_equipo_ids)
            else:
                gimnasio_service.limpiar_equipo_npc()

    # ── Timer de turno ────────────────────────────────────────────────────

    def _cancel_timer(self, battle: GymBattleData) -> None:
        if battle.turn_timer:
            battle.turn_timer.cancel()
            battle.turn_timer = None

    def _start_timer(self, battle: GymBattleData, bot) -> None:
        self._cancel_timer(battle)

        def _timeout() -> None:
            if self.get_battle(battle.user_id) is battle:
                self._handle_defeat(battle, bot, motivo="⏱️ Tiempo agotado.")

        t = threading.Timer(_BATTLE_TIMEOUT, _timeout)
        t.daemon = True
        t.start()
        battle.turn_timer = t

    # ── UI ────────────────────────────────────────────────────────────────

    def _edit_message(
        self,
        bot,
        battle: GymBattleData,
        text: str,
        keyboard: Optional[types.InlineKeyboardMarkup] = None,
    ) -> None:
        if not battle.message_id:
            return
        try:
            bot.edit_message_text(
                chat_id=battle.chat_id,
                message_id=battle.message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.debug(f"[GYM] edit_message silenciado: {e}")

    def _build_panel(
        self, battle: GymBattleData
    ) -> Tuple[str, types.InlineKeyboardMarkup]:
        from pokemon.battle_ui import build_pokemon_line
        from pokemon.services.pokedex_service import pokedex_service as _pdx_svc

        lider   = gimnasio_service.obtener_lider(battle.lider_id) or {}
        npc_pid = battle.npc_pokemon_id
        player  = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
        npc     = pokemon_service.obtener_pokemon(npc_pid) if npc_pid is not None else None

        # ── Líneas de HP ─────────────────────────────────────────────────────
        if npc:
            npc_tipos = _pdx_svc.obtener_tipos(npc.pokemonID)
            npc_line  = build_pokemon_line(
                lado      = "🔴",
                nombre    = npc.nombre,
                sexo      = getattr(npc, "sexo", None),
                tipos     = npc_tipos,
                nivel     = npc.nivel,
                hp_actual = max(0, npc.hp_actual),
                hp_max    = npc.stats.get("hp", 1),
                status    = battle.wild_status,
                stages    = battle.wild_stat_stages,
            )
        else:
            npc_line = "🔴 (sin Pokémon)"

        if player:
            p_tipos  = _pdx_svc.obtener_tipos(player.pokemonID)
            p_label  = player.mote or player.nombre
            p_line   = build_pokemon_line(
                lado      = "🔵",
                nombre    = p_label,
                sexo      = getattr(player, "sexo", None),
                tipos     = p_tipos,
                nivel     = player.nivel,
                hp_actual = max(0, player.hp_actual),
                hp_max    = player.stats.get("hp", 1),
                status    = battle.player_status,
                stages    = battle.player_stat_stages,
            )
        else:
            p_line = "🔵 (sin Pokémon)"

        # ── Log ───────────────────────────────────────────────────────────────
        log_txt = ""
        if battle.battle_log:
            log_txt = "\n\n📋 " + "\n".join(battle.battle_log[-2:])

        titulo        = f"{lider.get('emoji','⚔️')} <b>{lider.get('nombre','Líder')}</b> — {lider.get('titulo','')}"
        # clampado a 0: cuando el último NPC acaba de caer el índice ya apuntó\n"
        # más allá del final, dando -1 antes de que se declare la victoria\n"
        npc_restantes = max(0, len(battle.npc_equipo_ids) - battle.npc_current_index - 1)
        medalla_lider = lider.get("medalla", "")
        subtitulo     = "🏆 Alto Mando" if battle.is_e4 else f"🏅 {medalla_lider} en juego"

        text = (
            f"{titulo}\n"
            f"{subtitulo}\n\n"
            f"{npc_line}\n"
            f"💊 Pokémon restantes rival: {npc_restantes}\n\n"
            f"{p_line}"
            f"{log_txt}\n\n"
            f"💡 <b>Tu turno</b> — ¿Qué harás?"
        )

        uid      = battle.user_id
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("⚔️ Combate",  callback_data=f"gym_fight_{uid}"),
            types.InlineKeyboardButton("🎒 Mochila",  callback_data=f"gym_bag_{uid}"),
        )
        keyboard.add(
            types.InlineKeyboardButton("👥 Equipo",   callback_data=f"gym_team_{uid}"),
            types.InlineKeyboardButton("🏳️ Rendirse", callback_data=f"gym_forfeit_{uid}"),
        )
        return text, keyboard

    def _build_fight_panel(
        self, battle: GymBattleData
    ) -> Tuple[str, types.InlineKeyboardMarkup]:
        from pokemon.battle_ui import build_pokemon_line
        from pokemon.services.pokedex_service import pokedex_service as _pdx_svc

        npc_pid = battle.npc_pokemon_id
        player  = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
        npc     = pokemon_service.obtener_pokemon(npc_pid) if npc_pid is not None else None

        if npc:
            npc_tipos = _pdx_svc.obtener_tipos(npc.pokemonID)
            npc_line  = build_pokemon_line(
                lado="🔴", nombre=npc.nombre, sexo=getattr(npc, "sexo", None),
                tipos=npc_tipos, nivel=npc.nivel,
                hp_actual=npc.hp_actual, hp_max=npc.stats.get("hp", 1),
                status=battle.wild_status, stages=battle.wild_stat_stages,
            )
        else:
            npc_line = "🔴 (sin Pokémon)"

        if player:
            p_tipos = _pdx_svc.obtener_tipos(player.pokemonID)
            p_line  = build_pokemon_line(
                lado="🔵", nombre=player.mote or player.nombre,
                sexo=getattr(player, "sexo", None),
                tipos=p_tipos, nivel=player.nivel,
                hp_actual=player.hp_actual, hp_max=player.stats.get("hp", 1),
                status=battle.player_status, stages=battle.player_stat_stages,
            )
        else:
            p_line = "🔵 (sin Pokémon)"

        log_txt = ""
        if battle.battle_log:
            log_txt = "\n\n📋 " + "\n".join(battle.battle_log[-1:])

        text = f"{npc_line}\n\n{p_line}{log_txt}\n\n⚔️ <b>Elige un movimiento:</b>"

        uid      = battle.user_id
        NOOP     = f"gym_noop_{uid}"
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        movimientos = player.movimientos or [] if player else []

        for i in range(4):
            if i < len(movimientos):
                mv        = movimientos[i]
                move_data = movimientos_service.obtener_movimiento(mv) or {}
                mv_key    = mv.lower().replace(" ", "").replace("-", "")
                nombre_es = MOVE_NAMES_ES.get(mv_key) or move_data.get("nombre", mv.title())
                poder     = int(move_data.get("poder") or move_data.get("basePower") or 0)
                tipo      = move_data.get("tipo") or move_data.get("type", "Normal")
                _cat_map  = {"Physical": "Físico", "Special": "Especial", "Status": "Estado"}
                categoria = move_data.get("categoria") or _cat_map.get(move_data.get("category", ""), "Estado")
                tipo_emoji = MOVE_TYPE_EMOJI.get(tipo, "⚪")
                cat_emoji  = MOVE_CAT_EMOJI.get(categoria, "💫")
                try:
                    pp_info  = pp_service.obtener_pp(battle.player_pokemon_id, mv)
                    pp_txt   = f"{pp_info['actual']}/{pp_info['maximo']}"
                    tiene_pp = pp_info["actual"] > 0
                except Exception:
                    pp_max   = move_data.get("pp", "?")
                    pp_txt   = f"{pp_max}/{pp_max}"
                    tiene_pp = True
                label_nombre = f"{tipo_emoji} {nombre_es} ({poder})" if poder else f"{tipo_emoji} {nombre_es}"
                label_info   = f"{cat_emoji}{categoria} {pp_txt}"
                if not tiene_pp:
                    label_nombre = f"❌ {nombre_es}"
                    label_info   = "Sin PP"
                cb_mv = f"gym_move_{uid}_{mv}" if tiene_pp else NOOP
            else:
                label_nombre, label_info, cb_mv = "❓ No aprendido", "—", NOOP

            keyboard.row(
                types.InlineKeyboardButton(label_nombre, callback_data=cb_mv),
                types.InlineKeyboardButton(label_info,   callback_data=NOOP),
            )

        keyboard.add(types.InlineKeyboardButton("◀️ Volver", callback_data=f"gym_back_{uid}"))
        return text, keyboard

    def handle_fight(self, user_id: int, bot) -> None:
        """Muestra el sub-menú de movimientos al presionar ⚔️ Combate."""
        battle = self.get_battle(user_id)
        if not battle or battle.state != GymBattleState.ACTIVE:
            return
        text, kb = self._build_fight_panel(battle)
        self._edit_message(bot, battle, text, kb)
        
    def _refresh_ui(
        self,
        battle: GymBattleData,
        bot,
        extra_log: Optional[List[str]] = None,
    ) -> None:
        if extra_log:
            combined = "".join(extra_log).strip()
            if combined:
                battle.battle_log.append(combined)
                if len(battle.battle_log) > 3:
                    battle.battle_log = battle.battle_log[-3:]
        text, kb = self._build_panel(battle)
        self._edit_message(bot, battle, text, kb)

    # ── Iniciar batalla ───────────────────────────────────────────────────

    def start_battle(
        self,
        user_id:   int,
        chat_id:   int,
        bot,
        thread_id: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """Inicia una batalla contra el siguiente líder (o E4) disponible."""
        if self.has_active_battle(user_id):
            return False, "❌ Ya tienes una batalla de gimnasio en curso."

        equipo = pokemon_service.obtener_equipo(user_id)
        if not equipo:
            return False, "❌ No tienes Pokémon. Usa /profesor para empezar."
        if all(p.hp_actual <= 0 for p in equipo):
            return False, "❌ Todos tus Pokémon están debilitados. Ve al Centro Pokémon."

        # Determinar oponente
        siguiente = gimnasio_service.obtener_siguiente_lider(user_id)
        is_e4     = False
        if siguiente is None:
            siguiente = gimnasio_service.obtener_siguiente_e4(user_id)
            is_e4     = True
            if siguiente is None:
                return False, "🏆 ¡Ya eres el Campeón de esta región!"

        lider_id = siguiente["id"]

        # Validar acceso
        if is_e4:
            puede, msg = gimnasio_service.puede_desafiar_e4(user_id, lider_id)
        else:
            puede, msg = gimnasio_service.puede_desafiar_lider(user_id, lider_id)
        if not puede:
            return False, msg

        # 1. Crear equipo NPC
        npc_ids = gimnasio_service.crear_equipo_lider(lider_id)
        if not npc_ids:
            return False, "❌ Error preparando el equipo del líder. Inténtalo de nuevo."

        # Primer Pokémon del jugador con vida
        primer = next((p for p in equipo if p.hp_actual > 0), None)
        if not primer:
            gimnasio_service.limpiar_equipo_npc()
            return False, "❌ No tienes Pokémon disponibles."

        battle = GymBattleData(
            user_id=user_id,
            chat_id=chat_id,
            thread_id=thread_id,
            lider_id=lider_id,
            is_e4=is_e4,
            npc_equipo_ids=npc_ids,
            player_pokemon_id=primer.id_unico,
        )
        with self._lock:
            self._battles[user_id] = battle

        # Inicializar PP de ambos equipos
        for p in equipo:
            if p.movimientos:
                pp_service.inicializar_pp_movimientos(p.id_unico, p.movimientos)
        for npc_pid in npc_ids:
            npc_p = pokemon_service.obtener_pokemon(npc_pid)
            if npc_p and npc_p.movimientos:
                pp_service.inicializar_pp_movimientos(npc_pid, npc_p.movimientos)

        # Mensaje de presentación
        lider = siguiente
        intro = (
            f"{'🏆 ALTO MANDO' if is_e4 else '🏟️ BATALLA DE GIMNASIO'}\n\n"
            f"{lider.get('emoji','⚔️')} <b>{lider['nombre']}</b> — {lider['titulo']}\n"
            f"🏅 En juego: <b>{lider['medalla']}</b>\n"
            f"📍 {lider['ciudad']}\n\n"
            f"<b>{lider['nombre']}:</b> \"¡Prepárate para la batalla!\"\n\n"
            f"💰 Recompensa: {lider['recompensa']:,} cosmos\n"
        )
        mt = lider.get("mt_recompensa", {})
        if mt and mt.get("move_key"):
            from pokemon.mt_system import MT_MAP
            _mk   = mt["move_key"].lower().replace(" ", "").replace("-", "")
            _item = next((k for k, v in MT_MAP.items() if v == _mk), None)
            if _item:
                intro += f"📀 <b>{_item.upper()}</b> — {mt.get('nombre_es', _mk)}\n"
            else:
                intro += f"📀 MT ?? — {mt.get('nombre_es', _mk)}\n"

        try:
            sent = bot.send_message(
                chat_id, intro,
                parse_mode="HTML",
                message_thread_id=thread_id,   # None en privado, tid en grupo
            )
            battle.message_id = sent.message_id
        except Exception as e:
            logger.error(f"[GYM] Error enviando mensaje inicial: {e}")
            self._remove_battle(user_id)
            return False, "❌ Error al iniciar la batalla."

        self._refresh_ui(battle, bot)
        self._start_timer(battle, bot)
        logger.info(f"[GYM] Batalla iniciada: user={user_id} vs {lider_id}")
        return True, ""

    # ── Turno del jugador ─────────────────────────────────────────────────

    def handle_move(self, user_id: int, move_key: str, bot) -> bool:
        """Procesa el movimiento elegido por el jugador en su turno."""
        battle = self.get_battle(user_id)
        if not battle or battle.state != GymBattleState.ACTIVE:
            return False

        self._cancel_timer(battle)

        # Guardia: debe haber Pokémon NPC activo
        npc_pid = battle.npc_pokemon_id
        if npc_pid is None:
            # No hay más NPC → victoria (puede ocurrir si el índice ya avanzó)
            self._handle_victory(battle, bot)
            return True

        player = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
        npc    = pokemon_service.obtener_pokemon(npc_pid)

        if not player:
            # Jugador sin datos: derrota por seguridad
            self._handle_defeat(battle, bot, motivo="⚠️ Error recuperando tu Pokémon.")
            return False

        if not npc:
            # NPC desapareció (borrado por otra batalla concurrente — Bug A)
            # Verificar si aún quedan NPCs en el índice actual
            logger.warning(
                f"[GYM] NPC pid={npc_pid} no encontrado para battle user={battle.user_id}. "
                "Posible colisión multi-batalla. Avanzando índice."
            )
            battle.npc_current_index += 1
            if battle.npc_pokemon_id is None:
                # No quedan más NPCs → victoria
                self._handle_victory(battle, bot)
            else:
                # Todavía hay NPCs registrados, reiniciar timer para no congelar
                self._start_timer(battle, bot)
            return True

        p_name   = player.mote or player.nombre
        npc_name = npc.nombre
        log: List[str] = []

        # ── Elegir movimiento del NPC ahora (antes de ejecutar turnos) ────
        npc_moves_con_pp: List[str] = [
            mv for mv in (npc.movimientos or [])
            if pp_service.verificar_tiene_pp(npc_pid, mv)
        ] or ["tackle"]

        lider    = gimnasio_service.obtener_lider(battle.lider_id) or {}
        ia_cfg   = lider.get("ia_config", {})
        npc_move = GymBattleAI.seleccionar_movimiento(
            movimientos       = npc_moves_con_pp,
            estrategia        = ia_cfg.get("estrategia", "aggressive"),
            hp_ratio          = npc.hp_actual / max(npc.stats.get("hp", 1), 1),
            rival_tiene_status= bool(battle.player_status),
            setup_aplicado    = battle.npc_setup_counter,
        )

        # ── Datos de movimientos ──────────────────────────────────────────
        move_data     = movimientos_service.obtener_movimiento(move_key) or {}
        npc_move_data = movimientos_service.obtener_movimiento(npc_move) or {}

        move_prio     = int(move_data.get("prioridad", 0) or 0)
        npc_move_prio = int(npc_move_data.get("prioridad", 0) or 0)

        # ── Orden de turno ─────────────────────────────────────────────────
        # determine_turn_order(speed_a, stages_a, speed_b, stages_b, priority_a, priority_b)
        player_va_primero = determine_turn_order(
            speed_a   = player.stats.get("vel", 1),
            stages_a  = battle.player_stat_stages.get("vel", 0),
            speed_b   = npc.stats.get("vel", 1),
            stages_b  = battle.wild_stat_stages.get("vel", 0),
            priority_a= move_prio,
            priority_b= npc_move_prio,
        )
        # Trick Room invierte la prioridad de velocidad
        if battle.trick_room:
            player_va_primero = not player_va_primero

        npc_fainted    = False
        player_fainted = False

        from pokemon.battle_engine import (
            TWO_TURN_MOVES, FIXED_DAMAGE_MOVES, _roll_num_hits, 
            DRAIN_MOVES, RECOIL_MOVES, _HIGH_CRIT_MOVES
        )

        def _exec_player() -> None:
            nonlocal npc_fainted
            
            # 1. VALIDACIONES INICIALES Y CARGA DE DATOS
            _p = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
            _npc = pokemon_service.obtener_pokemon(npc_pid)  # type: ignore[arg-type]
            
            if not _p or not _npc or _p.hp_actual <= 0:
                return

            # Limpieza de strings para lógica y nombres
            mk_clean = move_key.lower().replace(" ", "").replace("-", "")
            nombre_es = MOVE_NAMES_ES.get(mk_clean, move_key.title())

            log.append(f"\n⚔️ <b>{p_name}</b> usó <b>{nombre_es}</b>!\n")

            # 2. CHECKS DE ESTADO (Parálisis, Sueño, Confusión, etc.)
            if not check_can_move(battle, is_player=True, actor_name=p_name, log=log):
                return
            
            if check_confusion(
                battle, is_player=True,
                actor_name=p_name, actor_level=_p.nivel,
                actor_atq=_p.stats.get("atq", 50), log=log
            ):
                return

            # 3. LÓGICA DE MOVIMIENTOS ESPECIALES (Focus Punch y Carga)
            # Caso especial: Focus Punch (Interrupción si recibió daño antes)
            if getattr(battle, "player_focus_interrupted", False) and mk_clean == "focuspunch":
                battle.player_focus_interrupted = False
                battle.player_charging_move = None
                log.append(f"  💔 ¡<b>{p_name}</b> perdió la concentración!\n")
                return

            # Movimientos de 2 turnos (Solar Beam, Fly, etc.)
            if mk_clean in TWO_TURN_MOVES:
                cfg_tt = TWO_TURN_MOVES[mk_clean]
                weather = getattr(battle, "weather", None)
                skip = cfg_tt["skip_weather"] and weather == cfg_tt["skip_weather"]
                
                if not skip and getattr(battle, "player_charging_move", None) != mk_clean:
                    battle.player_charging_move = mk_clean
                    msg = cfg_tt.get("msg_carga", "¡{nombre} está cargando!")
                    log.append(f"  ⚡ {msg.format(nombre=f'<b>{p_name}</b>')}\n")
                    return
                else:
                    battle.player_charging_move = None # Ejecución en segundo turno

            # 4. PREPARACIÓN DE PARÁMETROS DE COMBATE
            pp_service.usar_pp(battle.player_pokemon_id, move_key)
            cat = move_data.get("categoria", "Normal")
            poder = int(move_data.get("poder", 0) or 0)
            tipo_mv = move_data.get("tipo", "Normal")
            npc_tipos = pokedex_service.obtener_tipos(_npc.pokemonID)
            p_tipos = pokedex_service.obtener_tipos(_p.pokemonID)

            # Acumuladores para minimizar llamadas a la DB
            total_dmg_to_npc = 0
            total_recoil_to_player = 0
            total_drain_to_player = 0
            last_result = None

            # 5. RESOLUCIÓN DE DAÑO SEGÚN TIPO DE MOVIMIENTO
            
            # --- CASO A: DAÑO FIJO ---
            if mk_clean in FIXED_DAMAGE_MOVES:
                cfg_fd = FIXED_DAMAGE_MOVES[mk_clean]
                if any(t in cfg_fd.get("immune_types", []) for t in npc_tipos):
                    log.append(f"  💫 ¡No le afecta a <b>{npc_name}</b>!\n")
                else:
                    total_dmg_to_npc = _p.nivel if cfg_fd["damage_fn"] == "level" else cfg_fd.get("damage", 40)
                    log.append(f"  ⚡ Causó <b>{total_dmg_to_npc}</b> de daño fijo.\n")

            # --- CASO B: MOVIMIENTO DE ESTADO ---
            elif cat == "Estado" or poder == 0:
                ok = _apply_status_move(
                    battle, move_key, p_name, npc_name,
                    battle.player_stat_stages, battle.wild_stat_stages,
                    log, is_player=True,
                )
                if not ok: log.append("  💫 ¡Pero no tuvo efecto!\n")

            # --- CASO C: DAÑO NORMAL (Físico/Especial) ---
            else:
                w_mult = apply_weather_boost(battle.weather, tipo_mv)
                t_mult = apply_terrain_boost(battle.terrain, tipo_mv, is_grounded(p_tipos, battle))
                num_hits = _roll_num_hits(mk_clean, getattr(_p, "habilidad", "") or "")

                for h in range(num_hits):
                    # Verificar si el enemigo sigue vivo antes de cada golpe
                    if (_npc.hp_actual - total_dmg_to_npc) <= 0: break
                    
                    _h_pow = poder * (h + 1) if mk_clean in {"triplekick", "tripleaxel"} else poder
                    _h_name = nombre_es if h == 0 else f"{nombre_es} (golpe {h + 1})"

                    res = resolve_damage_move(
                        attacker_name=p_name, defender_name=npc_name,
                        attacker_level=_p.nivel, attacker_stats=_p.stats,
                        attacker_types=p_tipos, attacker_stages=battle.player_stat_stages,
                        defender_hp=max(0, _npc.hp_actual - total_dmg_to_npc),
                        defender_stats=_npc.stats, defender_types=npc_tipos,
                        defender_stages=battle.wild_stat_stages,
                        move_name=_h_name, move_power=int(_h_pow * w_mult * t_mult),
                        move_category=cat, move_type=tipo_mv,
                        type_effectiveness_fn=movimientos_service._calcular_efectividad,
                        drain_ratio=DRAIN_MOVES.get(mk_clean, 0.0),
                        crit_stage=1 if mk_clean in _HIGH_CRIT_MOVES else 0,
                    )
                    
                    log.extend(res.log)
                    total_dmg_to_npc += res.damage
                    
                    # Log de drenaje inmediato (ej: Gigadrenado)
                    if res.drained_hp > 0:
                        total_drain_to_player += res.drained_hp
                        log.append(f"  🍃 ¡<b>{p_name}</b> recuperó salud!\n")
                    
                    # Acumular retroceso para aplicar al final
                    recoil_ratio = RECOIL_MOVES.get(mk_clean, 0.0)
                    if recoil_ratio > 0 and res.damage > 0:
                        total_recoil_to_player += max(1, int(res.damage * recoil_ratio))
                    
                    last_result = res

                # Interrumpir Focus Punch del rival si recibió daño
                if total_dmg_to_npc > 0 and getattr(battle, "npc_charging_move", None) == "focuspunch":
                    battle.npc_focus_interrupted = True

            # 6. PERSISTENCIA EN BASE DE DATOS (Updates Únicos)
            # Actualizar NPC
            if total_dmg_to_npc > 0:
                _npc.hp_actual = max(0, _npc.hp_actual - total_dmg_to_npc)
                db_manager.execute_update(
                    "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                    (_npc.hp_actual, npc_pid)
                )

            # Actualizar Atacante (Drenaje y Retroceso)
            if total_drain_to_player > 0 or total_recoil_to_player > 0:
                p_max = _p.stats.get("hp", 1)
                nuevo_hp_p = min(p_max, max(0, _p.hp_actual + total_drain_to_player - total_recoil_to_player))
                
                if total_recoil_to_player > 0:
                    log.append(f"  🔙 ¡<b>{p_name}</b> se hirió con el retroceso! (<b>{total_recoil_to_player}</b> HP)\n")
                    
                _p.hp_actual = nuevo_hp_p
                db_manager.execute_update(
                    "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                    (_p.hp_actual, battle.player_pokemon_id)
                )

            # 7. EFECTOS SECUNDARIOS Y ESTADOS FINALES
            if last_result:
                _apply_secondary_effect(
                    move_key, last_result, battle, 
                    is_player_attacker=True, 
                    attacker_name=p_name, defender_name=npc_name, log=log
                )

            if _npc.hp_actual <= 0:
                log.append(f"  💀 ¡<b>{npc_name}</b> se ha debilitado!\n")
                npc_fainted = True

        # ─────────────────────────────────────────────────────────────────
        def _exec_npc() -> None:
            """Delegación liviana al método de instancia reutilizable."""
            nonlocal player_fainted
            player_fainted = self._apply_npc_attack(
                battle, npc_move, npc_pid, npc_name, log
            )

        # ── Ejecutar en orden ─────────────────────────────────────────────
        if player_va_primero:
            _exec_player()
            if not npc_fainted:
                _exec_npc()
        else:
            _exec_npc()
            if not player_fainted:
                _exec_player()

        # ── Fin de turno ──────────────────────────────────────────────────
        battle.turn_number += 1
        tick_field_turns(battle, log)
        _apply_eot_status(battle, log)   # ← mantener llamada existente

        # ── Verificar resultado ───────────────────────────────────────────
        _npc_pid_final = battle.npc_pokemon_id
        npc_r    = pokemon_service.obtener_pokemon(_npc_pid_final) if _npc_pid_final is not None else None
        player_r = pokemon_service.obtener_pokemon(battle.player_pokemon_id)

        npc_dead    = bool(npc_r    and npc_r.hp_actual    <= 0)
        player_dead = bool(player_r and player_r.hp_actual <= 0)

        if npc_dead and player_dead:
            # Ambos caen → derrota del jugador (regla estándar Pokémon)
            self._refresh_ui(battle, bot, extra_log=log)
            self._handle_defeat(
                battle, bot,
                motivo="💀 Ambos Pokémon fueron debilitados al mismo tiempo."
            )
            return True

        if npc_dead:
            self._refresh_ui(battle, bot, extra_log=log)
            self._on_npc_faint(battle, bot)
            return True

        if player_dead:
            self._refresh_ui(battle, bot, extra_log=log)
            self._on_player_faint(battle, bot)
            return True

        self._refresh_ui(battle, bot, extra_log=log)
        self._start_timer(battle, bot)
        return True

    # ── Cambio de Pokémon del jugador ─────────────────────────────────────

    def handle_switch(self, user_id: int, new_pokemon_id: int, bot) -> bool:
        battle = self.get_battle(user_id)
        if not battle:
            return False

        new_p = pokemon_service.obtener_pokemon(new_pokemon_id)
        if not new_p or new_p.hp_actual <= 0:
            return False

        old_name = ""
        if battle.player_pokemon_id:
            old = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
            old_name = (old.mote or old.nombre) if old else ""

        # Leer el flag ANTES de modificarlo
        es_faint_switch = battle.is_faint_switch

        # ── Guardar status del Pokémon que sale ──────────────────────────────────
        old_pid = battle.player_pokemon_id
        if old_pid:
            battle.player_leechseeded = False
            battle._pokemon_statuses[old_pid] = {
                "status":        battle.player_status,
                "sleep_turns":   battle.player_sleep_turns,
                "toxic_counter": battle.player_toxic_counter,
            }

        battle.player_pokemon_id    = new_pokemon_id
        # Volátiles: siempre se resetean al cambiar
        battle.player_stat_stages   = {"atq": 0, "def": 0, "atq_sp": 0, "def_sp": 0, "vel": 0}
        battle.player_yawn_counter  = 0
        battle.player_confusion_turns = 0
        battle.is_faint_switch      = False
        battle.state                = GymBattleState.ACTIVE

        # ── Restaurar status persistente del nuevo Pokémon ───────────────────────
        saved = battle._pokemon_statuses.get(new_pokemon_id, {})
        battle.player_status        = saved.get("status",        None)
        battle.player_sleep_turns   = saved.get("sleep_turns",   0)
        battle.player_toxic_counter = saved.get("toxic_counter", 0)
        # leechseeded no se restaura: las Drenadoras se curan al hacer switch

        log = []
        if old_name and not es_faint_switch:
            log.append(f"↩️ ¡{old_name} volvió!\n")
        log.append(f"✅ ¡Adelante, <b>{new_p.mote or new_p.nombre}</b>!\n")

        if es_faint_switch:
            # Reemplazo gratuito — el NPC NO ataca este turno
            self._refresh_ui(battle, bot, extra_log=log)
            self._start_timer(battle, bot)
        else:
            # Switch voluntario — el NPC ataca
            self._exec_npc_free_move(battle, bot, log)

        return True

    # ── Lógica de ataque NPC reutilizable ─────────────────────────────────

    def _apply_npc_attack(
        self,
        battle:   GymBattleData,
        npc_move: str,
        npc_pid:  int,
        npc_name: str,
        log:      List[str],
    ) -> bool:
        # 1. Obtención de datos y validación inicial
        _p   = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
        _npc = pokemon_service.obtener_pokemon(npc_pid)
        
        if not _p or not _npc or _npc.hp_actual <= 0 or _p.hp_actual <= 0:
            return False

        p_name = _p.mote or _p.nombre
        npc_mk_clean = npc_move.lower().replace(" ", "").replace("-", "")
        npc_nombre_es = MOVE_NAMES_ES.get(npc_mk_clean, npc_move.title())

        log.append(f"\n⚔️ <b>{npc_name}</b> usó <b>{npc_nombre_es}</b>!\n")

        # 2. Estados: Confusión y Restricciones de movimiento
        if check_confusion(battle, is_player=False, actor_name=npc_name, actor_level=_npc.nivel, 
                           actor_atq=_npc.stats.get("atq", 50), log=log):
            return False

        if not check_can_move(battle, is_player=False, actor_name=npc_name, log=log):
            return False

        # 3. Lógica de Focus Punch e interrupciones
        if getattr(battle, "npc_focus_interrupted", False) and npc_mk_clean == "focuspunch":
            battle.npc_focus_interrupted = False
            battle.npc_charging_move = None
            log.append(f"  💔 ¡{npc_name} perdió la concentración!\n")
            return False

        # 4. Movimientos de Carga (2 turnos)
        from pokemon.battle_engine import TWO_TURN_MOVES
        if npc_mk_clean in TWO_TURN_MOVES:
            cfg_tt = TWO_TURN_MOVES[npc_mk_clean]
            weather = getattr(battle, "weather", None)
            if cfg_tt["skip_weather"] and weather == cfg_tt["skip_weather"]:
                pass
            elif getattr(battle, "npc_charging_move", None) == npc_mk_clean:
                battle.npc_charging_move = None
            else:
                battle.npc_charging_move = npc_mk_clean
                msg = cfg_tt.get("msg_carga", "¡{nombre} está cargando!")
                log.append(f"  ⚡ {msg.format(nombre=npc_name)}\n")
                return False

        # 5. Consumo de PP y Datos del movimiento
        pp_service.usar_pp(npc_pid, npc_move)
        if npc_mk_clean in GymBattleAI._SETUP_MOVES:
            battle.npc_setup_counter += 1

        npc_move_data = movimientos_service.obtener_movimiento(npc_move) or {}
        npc_cat       = npc_move_data.get("categoria", "Normal")
        npc_poder     = int(npc_move_data.get("poder", 0) or 0)
        tipo_mv       = npc_move_data.get("tipo", "Normal")

        # 6. RESOLUCIÓN DE DAÑO
        from pokemon.battle_engine import FIXED_DAMAGE_MOVES
        damage_dealt = 0

        # --- CASO A: DAÑO FIJO ---
        if npc_mk_clean in FIXED_DAMAGE_MOVES:
            cfg_fd = FIXED_DAMAGE_MOVES[npc_mk_clean]
            p_tipos = pokedex_service.obtener_tipos(_p.pokemonID)
            if any(t in cfg_fd.get("immune_types", []) for t in p_tipos):
                log.append(f"  💫 ¡No le afecta a <b>{p_name}</b>!\n")
            else:
                damage_dealt = _npc.nivel if cfg_fd["damage_fn"] == "level" else cfg_fd.get("damage", 40)
                _p.hp_actual = max(0, _p.hp_actual - damage_dealt)
                db_manager.execute_update("UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?", 
                                          (_p.hp_actual, battle.player_pokemon_id))
                log.append(f"  ⚡ Causó <b>{damage_dealt}</b> de daño fijo.\n")

        # --- CASO B: MOVIMIENTO DE ESTADO ---
        elif npc_cat == "Estado" or npc_poder == 0:
            ok = _apply_status_move(battle, npc_move, npc_name, p_name, battle.wild_stat_stages, 
                                   battle.player_stat_stages, log, is_player=False)
            if not ok: log.append("  💫 ¡Pero no tuvo efecto!\n")

        # --- CASO C: DAÑO NORMAL ---
        else:
            npc_tipos = pokedex_service.obtener_tipos(_npc.pokemonID)
            p_tipos   = pokedex_service.obtener_tipos(_p.pokemonID)
            w_mult    = apply_weather_boost(battle.weather, tipo_mv)
            t_mult    = apply_terrain_boost(battle.terrain, tipo_mv, is_grounded(npc_tipos, battle))
            
            result = resolve_damage_move(
                attacker_name=npc_name, defender_name=p_name, attacker_level=_npc.nivel,
                attacker_stats=_npc.stats, attacker_types=npc_tipos, attacker_stages=battle.wild_stat_stages,
                defender_hp=_p.hp_actual, defender_stats=_p.stats, defender_types=p_tipos,
                defender_stages=battle.player_stat_stages, move_name=npc_nombre_es,
                move_power=int(npc_poder * w_mult * t_mult), move_category=npc_cat, move_type=tipo_mv,
                type_effectiveness_fn=movimientos_service._calcular_efectividad,
                drain_ratio=DRAIN_MOVES.get(npc_mk_clean, 0.0), crit_stage=1 if npc_mk_clean in _HIGH_CRIT_MOVES else 0
            )
            log.extend(result.log)
            damage_dealt = result.damage

            if damage_dealt > 0:
                _p.hp_actual = max(0, _p.hp_actual - damage_dealt)
                db_manager.execute_update("UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?", 
                                          (_p.hp_actual, battle.player_pokemon_id))
                
                if result.drained_hp > 0:
                    _npc.hp_actual = min(_npc.stats.get("hp", 1), _npc.hp_actual + result.drained_hp)
                    db_manager.execute_update("UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?", 
                                              (_npc.hp_actual, npc_pid))

            _apply_secondary_effect(npc_move, result, battle, is_player_attacker=False, 
                                   attacker_name=npc_name, defender_name=p_name, log=log)

        # 7. Interrupción de Focus Punch del Jugador y Retorno
        if damage_dealt > 0 and getattr(battle, "player_charging_move", None) == "focuspunch":
            battle.player_focus_interrupted = True

        return _p.hp_actual <= 0
    
    def _exec_npc_free_move(
        self, battle: GymBattleData, bot, log: List[str]
    ) -> None:
        """Ejecuta un turno del NPC sin que el jugador actúe (hard switch)."""
        npc_pid = battle.npc_pokemon_id
        if npc_pid is None:
            self._refresh_ui(battle, bot, extra_log=log)
            self._start_timer(battle, bot)
            return

        npc    = pokemon_service.obtener_pokemon(npc_pid)
        player = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
        if not npc or not player:
            self._refresh_ui(battle, bot, extra_log=log)
            self._start_timer(battle, bot)
            return

        # ── Nombre visible del NPC (faltaba en la versión anterior) ──────
        npc_name = npc.nombre

        lider   = gimnasio_service.obtener_lider(battle.lider_id) or {}
        ia_cfg  = lider.get("ia_config", {})
        npc_moves_con_pp = [
            mv for mv in (npc.movimientos or [])
            if pp_service.verificar_tiene_pp(npc_pid, mv)
        ] or ["tackle"]
        npc_move = GymBattleAI.seleccionar_movimiento(
            movimientos        = npc_moves_con_pp,
            estrategia         = ia_cfg.get("estrategia", "aggressive"),
            hp_ratio           = npc.hp_actual / max(npc.stats.get("hp", 1), 1),
            rival_tiene_status = bool(battle.player_status),
            setup_aplicado     = battle.npc_setup_counter,
        )

        # ── Ejecutar el ataque mediante el método de instancia ────────────
        player_fainted = self._apply_npc_attack(battle, npc_move, npc_pid, npc_name, log)

        if player_fainted:
            self._refresh_ui(battle, bot, extra_log=log)
            self._on_player_faint(battle, bot)
            return

        self._refresh_ui(battle, bot, extra_log=log)
        self._start_timer(battle, bot)

    def handle_forfeit(self, user_id: int, bot) -> bool:
        """
        Acepta la rendición del jugador en cualquier estado de la batalla.
        Robusto frente a batallas congeladas (NPC desaparecidos, timer muerto).
        """
        battle = self.get_battle(user_id)
        if not battle:
            return False
        # Cancelar timer antes de llamar defeat para evitar doble ejecución
        self._cancel_timer(battle)
        # Aceptar rendición independientemente del estado actual
        if battle.state not in (GymBattleState.PLAYER_WIN,
                                 GymBattleState.PLAYER_LOSE,
                                 GymBattleState.PLAYER_FORFEIT):
            battle.state = GymBattleState.PLAYER_FORFEIT
            self._handle_defeat(battle, bot, motivo="🏳️ Te rendiste.")
        return True


    # ── Caída de Pokémon ──────────────────────────────────────────────────

    def _on_npc_faint(self, battle: GymBattleData, bot) -> None:
        _fainted_pid = battle.npc_pokemon_id
        npc = pokemon_service.obtener_pokemon(_fainted_pid) if _fainted_pid is not None else None
        npc_name = npc.nombre if npc else "Pokémon rival"
        log      = [f"\n💀 <b>{npc_name}</b> fue derrotado!\n"]

        self._grant_exp(battle, fainted_npc_pid=battle.npc_pokemon_id, log=log, bot=bot)

        # Guardia: si el jugador también cayó (ej. por retroceso en el mismo turno)
        # la derrota tiene prioridad sobre el avance al siguiente NPC.
        player_r = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
        if player_r and player_r.hp_actual <= 0:
            self._handle_defeat(
                battle, bot,
                motivo="💀 Ambos Pokémon fueron debilitados al mismo tiempo."
            )
            return

        battle.npc_current_index  += 1
        battle.wild_stat_stages    = {"atq": 0, "def": 0, "atq_sp": 0, "def_sp": 0, "vel": 0}
        battle.wild_status         = None
        battle.wild_sleep_turns    = 0
        battle.wild_toxic_counter  = 0
        battle.wild_yawn_counter   = 0
        battle.wild_leechseeded    = False
        battle.npc_setup_counter   = 0

        next_pid = battle.npc_pokemon_id
        if next_pid is None:
            # No quedan más Pokémon del líder → victoria
            self._refresh_ui(battle, bot, extra_log=log)
            self._handle_victory(battle, bot)
            return  # ← evitar que el código continúe tras declarar victoria
        else:
            next_p  = pokemon_service.obtener_pokemon(next_pid)
            np_name = next_p.nombre if next_p else "Pokémon"
            lider   = gimnasio_service.obtener_lider(battle.lider_id) or {}
            log.append(
                f"⚔️ <b>{lider.get('nombre','El rival')}</b> "
                f"envía a <b>{np_name}</b>!\n"
            )
            self._refresh_ui(battle, bot, extra_log=log)
            self._start_timer(battle, bot)

    def _on_player_faint(self, battle: GymBattleData, bot) -> None:
        player  = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
        p_name  = (player.mote or player.nombre) if player else "Tu Pokémon"
        log     = [f"\n💀 <b>{p_name}</b> fue derrotado!\n"]

        equipo     = pokemon_service.obtener_equipo(battle.user_id)
        reemplazos = [
            p for p in equipo
            if p.hp_actual > 0 and p.id_unico != battle.player_pokemon_id
        ]

        if not reemplazos:
            self._refresh_ui(battle, bot, extra_log=log)
            self._handle_defeat(battle, bot, motivo="💀 Todos tus Pokémon fueron derrotados.")
            return

        battle.is_faint_switch  = True   # ← AGREGAR esta línea
        battle.state            = GymBattleState.SWITCHING
        battle.player_stat_stages = {"atq": 0, "def": 0, "atq_sp": 0, "def_sp": 0, "vel": 0}

        text = f"💀 <b>{p_name}</b> fue derrotado!\n\n¿A quién envías ahora?"
        kb   = types.InlineKeyboardMarkup(row_width=1)
        for p in reemplazos:
            hp_max = p.stats.get("hp", 1)
            pct    = round((p.hp_actual / hp_max) * 100)
            icon   = "🟢" if pct > 50 else ("🟡" if pct > 20 else "🔴")
            kb.add(types.InlineKeyboardButton(
                f"{icon} {p.mote or p.nombre} Nv.{p.nivel} — {p.hp_actual}/{hp_max}",
                callback_data=f"gym_switch_{battle.user_id}_{p.id_unico}",
            ))
        self._edit_message(bot, battle, text, kb)

    # ── Victoria y derrota ────────────────────────────────────────────────

    def _handle_victory(self, battle: GymBattleData, bot) -> None:
        battle.state = GymBattleState.PLAYER_WIN
        self._cancel_timer(battle)

        if battle.is_e4:
            ok, msg = gimnasio_service.otorgar_victoria_e4(battle.user_id, battle.lider_id)
        else:
            ok, msg = gimnasio_service.otorgar_medalla(battle.user_id, battle.lider_id)

        victoria_text = f"🏆 <b>¡VICTORIA!</b>\n\n{msg}"
        # 1. Editar el panel de batalla en curso (puede fallar silenciosamente)\n'
        self._edit_message(bot, battle, victoria_text)
        # 2. Enviar SIEMPRE un mensaje nuevo en el hilo.\n'
        #    No se condiciona con «if ok» — el usuario ganó la batalla\n'
        #    independientemente de errores secundarios en otorgar_medalla.\n'
        try:
            bot.send_message(
                battle.chat_id,
                victoria_text,
                parse_mode="HTML",
                message_thread_id=battle.thread_id,
            )
        except Exception as e:
            logger.warning("[GYM] No se pudo enviar mensaje de victoria: %s", e)

        logger.info(f"[GYM] Victoria: user={battle.user_id} vs {battle.lider_id}")
        self._remove_battle(battle.user_id)

    def _handle_defeat(
        self, battle: GymBattleData, bot, motivo: str = ""
    ) -> None:
        battle.state = GymBattleState.PLAYER_LOSE
        self._cancel_timer(battle)

        lider = gimnasio_service.obtener_lider(battle.lider_id) or {}
        text  = (
            f"💀 <b>Derrota</b>\n\n"
            f"{motivo}\n\n"
            f"<b>{lider.get('nombre','El líder')}</b> derrotó a todos tus Pokémon.\n"
            f"Ve al Centro Pokémon y vuelve cuando estés listo."
        )
        self._edit_message(bot, battle, text)
        logger.info(f"[GYM] Derrota: user={battle.user_id} — {motivo}")
        self._remove_battle(battle.user_id)

    # ── EXP ───────────────────────────────────────────────────────────────

    def _grant_exp(
        self,
        battle:          GymBattleData,
        fainted_npc_pid: Optional[int],
        log:             List[str],
        bot,
    ) -> None:
        if fainted_npc_pid is None:
            return
        try:
            player = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
            npc_p  = pokemon_service.obtener_pokemon(fainted_npc_pid)
            if not player or not npc_p:
                return

            exp = ExperienceSystem.exp_por_victoria(
                nivel_enemigo      = npc_p.nivel,
                pokemon_id_enemigo = npc_p.pokemonID,
                nivel_ganador      = player.nivel,
                es_salvaje         = False,
                es_entrenador      = True,
            )
            resultado = ExperienceSystem.aplicar_experiencia(
                battle.player_pokemon_id, exp
            )
            p_name = player.mote or player.nombre
            log.append(f"  ⭐ <b>{p_name}</b> ganó <b>{exp}</b> EXP.\n")

            if resultado.get("subio_nivel"):
                log.append(
                    f"  🎉 ¡<b>{p_name}</b> subió al nivel "
                    f"<b>{resultado['nivel_nuevo']}</b>!\n"
                )
                try:
                    from pokemon.level_up_handler import LevelUpHandler
                    # Cancelar timer: el jugador no puede actuar hasta que
                    # termine el flujo de aprender movimientos.
                    self._cancel_timer(battle)

                    def _on_levelup_complete():
                        b = self.get_battle(battle.user_id)
                        if b and b.state == GymBattleState.ACTIVE:
                            self._refresh_ui(b, bot)
                            self._start_timer(b, bot)

                    LevelUpHandler.procesar_subida(
                        bot        = bot,
                        user_id    = battle.user_id,
                        pokemon_id = battle.player_pokemon_id,
                        exp_result = resultado,
                        delay      = 3.0,
                        on_complete= _on_levelup_complete,
                    )
                except Exception as _lv_e:
                    logger.error(f"[GYM] Error en LevelUpHandler: {_lv_e}")
                    self._start_timer(battle, bot)   # fallback: reanudar timer

        except Exception as e:
            logger.error(f"[GYM] Error otorgando EXP: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# FUNCIONES AUXILIARES
# ═════════════════════════════════════════════════════════════════════════════

def _apply_eot_status(battle: GymBattleData, log: List[str]) -> None:
    """Efectos de fin de turno: drenadoras, status (veneno/quemadura/tóxico)."""

    # ── Drenadoras ────────────────────────────────────────────────────────────
    npc_pid = battle.npc_pokemon_id
    npc     = pokemon_service.obtener_pokemon(npc_pid) if npc_pid is not None else None
    player  = pokemon_service.obtener_pokemon(battle.player_pokemon_id)

    if npc and player:
        # NPC está sembrado → pierde HP, jugador recupera
        if getattr(battle, "wild_leechseeded", False) and npc.hp_actual > 0:
            dmg    = max(1, npc.stats.get("hp", 1) // 8)
            new_hp = max(0, npc.hp_actual - dmg)
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                (new_hp, npc_pid),
            )
            p_max  = player.stats.get("hp", 1)
            new_php = min(p_max, player.hp_actual + dmg)
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                (new_php, battle.player_pokemon_id),
            )
            log.append(f"  🌱 Drenadoras: {npc.nombre} pierde {dmg} HP.\n")

        # Jugador está sembrado → pierde HP, NPC recupera
        if getattr(battle, "player_leechseeded", False) and player.hp_actual > 0:
            p_max  = player.stats.get("hp", 1)
            dmg    = max(1, p_max // 8)
            new_php = max(0, player.hp_actual - dmg)
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                (new_php, battle.player_pokemon_id),
            )
            if npc and npc.hp_actual > 0:
                npc_max  = npc.stats.get("hp", 1)
                new_nhp  = min(npc_max, npc.hp_actual + dmg)
                db_manager.execute_update(
                    "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                    (new_nhp, npc_pid),
                )
            log.append(f"  🌱 Drenadoras: {player.mote or player.nombre} pierde {dmg} HP.\n")

    # ── Status del NPC ────────────────────────────────────────────────────────
    if battle.wild_status in ("psn", "tox", "brn"):
        npc_r = pokemon_service.obtener_pokemon(npc_pid) if npc_pid is not None else None
        if npc_r and npc_r.hp_actual > 0:
            npc_max = npc_r.stats.get("hp", 1)
            if battle.wild_status == "tox":
                battle.wild_toxic_counter += 1
                dmg = max(1, (npc_max * battle.wild_toxic_counter) // 16)
            else:
                dmg = max(1, npc_max // 8)
            new_hp = max(0, npc_r.hp_actual - dmg)
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                (new_hp, npc_pid),
            )
            icon = STATUS_ICONS.get(battle.wild_status, "")
            log.append(f"  {icon} {npc_r.nombre} sufrió {dmg} de daño.\n")

    # ── Status del jugador ────────────────────────────────────────────────────
    if battle.player_status in ("psn", "tox", "brn"):
        player_r = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
        if player_r and player_r.hp_actual > 0:
            p_max = player_r.stats.get("hp", 1)
            if battle.player_status == "tox":
                battle.player_toxic_counter += 1
                dmg = max(1, (p_max * battle.player_toxic_counter) // 16)
            else:
                dmg = max(1, p_max // 8)
            new_hp = max(0, player_r.hp_actual - dmg)
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                (new_hp, battle.player_pokemon_id),
            )
            p_name = player_r.mote or player_r.nombre
            icon   = STATUS_ICONS.get(battle.player_status, "")
            log.append(f"  {icon} {p_name} sufrió {dmg} de daño.\n")

    # ── Bostezo → sueño ───────────────────────────────────────────────────────
    if battle.wild_yawn_counter > 0:
        battle.wild_yawn_counter -= 1
        if battle.wild_yawn_counter == 0 and battle.wild_status is None:
            npc_r2 = pokemon_service.obtener_pokemon(npc_pid) if npc_pid else None
            if npc_r2:
                apply_ailment(battle, "slp", target_is_wild=True,
                              target_name=npc_r2.nombre, log=log)

    if battle.player_yawn_counter > 0:
        battle.player_yawn_counter -= 1
        if battle.player_yawn_counter == 0 and battle.player_status is None:
            player_r2 = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
            if player_r2:
                apply_ailment(battle, "slp", target_is_wild=False,
                              target_name=(player_r2.mote or player_r2.nombre), log=log)


def _apply_status_move(
    battle:          GymBattleData,
    move_key:        str,
    attacker_name:   str,
    defender_name:   str,
    attacker_stages: dict,
    defender_stages: dict,
    log:             List[str],
    *,
    is_player:       bool,
) -> bool:
    """
    Aplica el efecto de un movimiento de estado usando MOVE_EFFECTS.
    Retorna True si tuvo algún efecto.
    """
    mk     = move_key.lower().replace(" ", "").replace("-", "")
    effect = MOVE_EFFECTS.get(mk)
    if not effect:
        return False

    applied = False

    # Cambios de etapas
    for (target, stat, delta) in effect.get("stages", []):
        stages = attacker_stages if target == "self" else defender_stages
        quien  = attacker_name   if target == "self" else defender_name
        apply_stage_change(stat, delta, stages, quien, log)
        applied = True

    # Bostezo
    if effect.get("yawn"):
        target_attr = "wild_yawn_counter" if is_player else "player_yawn_counter"
        if getattr(battle, target_attr, 0) == 0:
            setattr(battle, target_attr, 1)
            log.append(f"  😪 ¡{defender_name} comenzó a adormilarse!\n")
        else:
            log.append("  💫 ¡Pero no tuvo efecto!\n")
        applied = True

    # Ailment
    # Ailment
    ailment = effect.get("ailment")
    if ailment:
        if mk == "rest":
            # Rest: siempre duerme al ATACANTE (no al defensor).
            # La curación de HP ya se maneja en el bloque "heal" de abajo.
            attacker_is_player = is_player
            attacker_status_key     = "player_status"       if attacker_is_player else "wild_status"
            attacker_sleep_key      = "player_sleep_turns"  if attacker_is_player else "wild_sleep_turns"
            attacker_toxic_key      = "player_toxic_counter" if attacker_is_player else "wild_toxic_counter"
            pid = battle.player_pokemon_id if attacker_is_player else battle.npc_pokemon_id
            poke = pokemon_service.obtener_pokemon(pid) if pid is not None else None
            if poke and poke.hp_actual > 0:
                # Curar HP al máximo
                p_max = poke.stats.get("hp", 1)
                db_manager.execute_update(
                    "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                    (p_max, pid),
                )
                # Limpiar status previo y aplicar sueño
                setattr(battle, attacker_status_key, None)
                setattr(battle, attacker_toxic_key, 0)
                setattr(battle, attacker_status_key, "slp")
                setattr(battle, attacker_sleep_key, random.randint(2, 3))
                log.append(
                    f"  💚 ¡<b>{attacker_name}</b> se curó completamente "
                    f"y se quedó dormido!\n"
                )
            else:
                log.append(f"  💫 ¡{attacker_name} no puede usar Descanso!\n")
            applied = True
        elif can_apply_ailment_in_field(battle, ailment):
            target_is_wild = is_player   # jugador aplica → afecta al NPC (wild)
            apply_ailment(battle, ailment, target_is_wild=target_is_wild,
                          target_name=defender_name, log=log)
            applied = True

    # Clima
    weather_entry = effect.get("weather")
    if weather_entry:
        w_key, w_turns = weather_entry
        activate_weather(battle, w_key, w_turns, attacker_name, log)
        applied = True

    # Terreno
    terrain_entry = effect.get("terrain")
    if terrain_entry:
        t_key, t_turns = terrain_entry
        activate_terrain(battle, t_key, t_turns, attacker_name, log)
        applied = True

    # Curación propia
    heal_ratio = effect.get("heal")
    if heal_ratio:
        pid  = battle.player_pokemon_id if is_player else battle.npc_pokemon_id
        poke = pokemon_service.obtener_pokemon(pid) if pid is not None else None
        if poke:
            p_max    = poke.stats.get("hp", 1)
            heal_amt = max(1, int(p_max * heal_ratio))
            new_hp   = min(p_max, poke.hp_actual + heal_amt)
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                (new_hp, pid),
            )
            log.append(f"  💚 {attacker_name} recuperó {heal_amt} HP.\n")
            applied = True

    # Drenadoras (Leech Seed)
    if effect.get("leechseed"):
        target_flag = "wild_leechseeded" if is_player else "player_leechseeded"
        if getattr(battle, target_flag, False):
            log.append(f"  🌿 ¡{defender_name} ya está sembrado!\n")
        else:
            setattr(battle, target_flag, True)
            log.append(f"  🌱 ¡{defender_name} fue sembrado con Drenadoras!\n")
        applied = True

    # Focus Energy / Laser Focus
    if "crit_stage" in effect:
        # GymBattleData no tiene crit_stage separado, ignorar silenciosamente
        pass

    # ── Curación (Síntesis, Sol Matinal, Luz Lunar, Recuperación…) ───────────
    heal_ratio = effect.get("heal")
    if heal_ratio is not None and mk != "rest":
        pid  = battle.player_pokemon_id if is_player else battle.npc_pokemon_id
        poke = pokemon_service.obtener_pokemon(pid) if pid is not None else None
        if poke and poke.hp_actual > 0:
            hp_max = poke.stats.get("hp", 1)
            if mk in {"synthesis", "morningsun", "moonlight"}:
                weather = getattr(battle, "weather", None)
                if weather == "sun":
                    ratio = 2 / 3
                elif weather in {"rain", "sand", "snow", "fog"}:
                    ratio = 1 / 4
                else:
                    ratio = 0.50
            else:
                ratio = float(heal_ratio)
            healed = max(1, int(hp_max * ratio))
            new_hp = min(hp_max, poke.hp_actual + healed)
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                (new_hp, pid),
            )
            log.append(f"  💚 {attacker_name} recuperó {healed} HP.\n")
            applied = True
        else:
            log.append(f"  💫 ¡Pero no tuvo efecto!\n")

    return applied


def _apply_secondary_effect(
    move_key:           str,
    result:             DamageResult,
    battle:             GymBattleData,
    *,
    is_player_attacker: bool,
    attacker_name:      str,
    defender_name:      str,
    log:                List[str],
) -> None:
    """Aplica ailment secundario de movimientos de daño (quemadura de Lanzallamas, etc.)."""
    if result.damage <= 0:
        return

    mk  = move_key.lower().replace(" ", "").replace("-", "")
    sec = SECONDARY_AILMENTS.get(mk)
    if not sec:
        return

    ailment, chance = sec
    if random.random() < (chance / 100) and can_apply_ailment_in_field(battle, ailment):
        target_is_wild = is_player_attacker
        apply_ailment(
            battle, ailment,
            target_is_wild=target_is_wild,
            target_name=defender_name,
            log=log,
        )


# ═════════════════════════════════════════════════════════════════════════════
# HANDLER DE COMANDOS
# ═════════════════════════════════════════════════════════════════════════════

class GymCommandHandler:
    """
    Registra /gimnasio, /altomando y todos los callbacks gym_*.

    Uso en UniverseBot.py:
        from pokemon.gym_battle_system import gym_cmd, gym_manager
        gym_cmd.register(bot)
    """

    def register(self, bot) -> None:
        bot.register_message_handler(
            lambda message: self._cmd_gimnasio(message, bot),
            commands=["gimnasio", "gym", "lider"],
        )
        bot.register_message_handler(
            lambda message: self._cmd_altomando(message, bot),
            commands=["altomando", "e4", "elitecuatro"],
        )
        bot.register_callback_query_handler(
            lambda call: self._handle_callback(call, bot),
            func=lambda c: c.data and c.data.startswith("gym_"),
        )
        logger.info("[GYM] Registrado: /gimnasio /altomando + callbacks gym_*")

    # ── Comandos ──────────────────────────────────────────────────────────

    def _cmd_gimnasio(self, message: types.Message, bot) -> None:
        user_id = message.from_user.id
        chat_id = message.chat.id
        tid     = get_thread_id(message)   # FIX: usa fallback via is_topic_message

        # ── Guard: solo PokéClub o privado ───────────────────────────────────
        from config import CANAL_ID, POKECLUB
        es_privado  = message.chat.type == 'private'
        es_pokeclub = (chat_id == CANAL_ID and tid == POKECLUB)
        if not es_privado and not es_pokeclub:
            try:
                bot.delete_message(message.chat.id, message.message_id)
                m = bot.send_message(
                    chat_id, "❌ Solo puedes usar este comando en pokeclub!.",
                    message_thread_id=tid,
                )
                time.sleep(5)
                bot.delete_message(chat_id, m.message_id)
            except Exception:
                pass
            return

        # ── Guard: registro obligatorio en privado ────────────────────────────
        if es_privado and not db_manager.user_exists(user_id):
            bot.reply_to(
                message,
                "⚠️ No estás registrado en el sistema.\n"
                "Regístrate en el grupo con <code>/registrar</code> primero.",
                parse_mode="HTML",
            )
            return

        if gym_manager.has_active_battle(user_id):
            bot.reply_to(message, "❌ Ya tienes una batalla de gimnasio en curso.")
            return

        siguiente = gimnasio_service.obtener_siguiente_lider(user_id)
        if siguiente is None:
            siguiente = gimnasio_service.obtener_siguiente_e4(user_id)
            if siguiente is None:
                bot.reply_to(message, "🏆 ¡Ya eres el Campeón de esta región!")
                return

        lider = siguiente
        texto = (
            f"{lider.get('emoji','⚔️')} <b>{lider['nombre']}</b>"
            f" — {lider['titulo']}\n"
            f"🏅 <b>{lider['medalla']}</b>\n"
            f"📍 {lider['ciudad']}\n"
            f"⚡ Tipo: {lider['tipo']}\n\n"
            f"💰 Recompensa: {lider['recompensa']:,} cosmos\n"
        )
        mt = lider.get("mt_recompensa", {})
        if mt and mt.get("move_key"):
            from pokemon.mt_system import MT_MAP
            _mk   = mt["move_key"].lower().replace(" ", "").replace("-", "")
            _item = next((k for k, v in MT_MAP.items() if v == _mk), None)
            if _item:
                texto += f"📀 <b>{_item.upper()}</b> — {mt.get('nombre_es', _mk)}\n"
            else:
                texto += f"📀 MT ?? — {mt.get('nombre_es', _mk)}\n"

        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton(
                "⚔️ ¡Combatir!", callback_data=f"gym_start_{user_id}"
            ),
            types.InlineKeyboardButton(
                "❌ Cancelar", callback_data=f"gym_cancel_{user_id}"
            ),
        )
        bot.send_message(
            chat_id, texto,
            parse_mode="HTML",
            reply_markup=kb,
            message_thread_id=tid,
        )

    def _cmd_altomando(self, message: types.Message, bot) -> None:
        user_id = message.from_user.id

        if not gimnasio_service.todas_las_medallas(user_id):
            n      = gimnasio_service.total_gimnasios
            actual = gimnasio_service.medallas_count(user_id)
            bot.reply_to(
                message,
                f"❌ Necesitas las {n} medallas para acceder al Alto Mando.\n"
                f"Tienes: {actual}/{n}",
            )
            return

        self._cmd_gimnasio(message, bot)

    # ── Callbacks ─────────────────────────────────────────────────────────

    def _handle_callback(self, call: types.CallbackQuery, bot) -> None:
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass

        data   = call.data or ""
        caller = call.from_user.id
        parts  = data.split("_")

        if len(parts) < 3:
            return
        try:
            target_uid = int(parts[2])
        except ValueError:
            return

        if caller != target_uid:
            try:
                bot.answer_callback_query(call.id, "Este no es tu turno.", show_alert=True)
            except Exception:
                pass
            return

        action  = parts[1]
        chat_id = call.message.chat.id

        # gym_start ────────────────────────────────────────────────────────
        if action == "start":
            tid_call = get_thread_id(call.message)   # FIX: era getattr directo → None
            ok, err  = gym_manager.start_battle(target_uid, chat_id, bot, thread_id=tid_call)
            if not ok and err:
                bot.send_message(
                    chat_id, err,
                    parse_mode="HTML",
                    message_thread_id=tid_call,
                )
            try:
                bot.edit_message_reply_markup(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=None,
                )
            except Exception:
                pass

        # gym_cancel ───────────────────────────────────────────────────────
        elif action == "cancel":
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Batalla cancelada.",
                )
            except Exception:
                pass

        # gym_fight ────────────────────────────────────────────────────────
        elif action == "fight":
            gym_manager.handle_fight(target_uid, bot)

        # gym_bag ──────────────────────────────────────────────────────────
        elif action == "bag":
            battle = gym_manager.get_battle(target_uid)
            if battle:
                kb = types.InlineKeyboardMarkup()
                kb.add(types.InlineKeyboardButton(
                    "◀️ Volver", callback_data=f"gym_back_{target_uid}"
                ))
                try:
                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text="🎒 No puedes usar items durante una batalla de Gimnasio.",
                        parse_mode="HTML",
                        reply_markup=kb,
                    )
                except Exception:
                    pass

        # gym_move ─────────────────────────────────────────────────────────
        elif action == "move":
            move_key = "_".join(parts[3:])
            if move_key:
                gym_manager.handle_move(target_uid, move_key, bot)

        # gym_team ─────────────────────────────────────────────────────────
        elif action == "team":
            battle = gym_manager.get_battle(target_uid)
            if not battle:
                return
            equipo     = pokemon_service.obtener_equipo(target_uid)
            current_id = battle.player_pokemon_id
            text       = "👥 <b>Tu Equipo</b>\n\n"
            kb         = types.InlineKeyboardMarkup(row_width=1)
            for p in equipo:
                hp_max = p.stats.get("hp", 1)
                pct    = (p.hp_actual / hp_max) * 100
                icon   = (
                    "▶️" if p.id_unico == current_id else
                    "💀" if p.hp_actual == 0 else
                    "🟢" if pct > 50 else
                    "🟡" if pct > 20 else "🔴"
                )
                can_switch = p.hp_actual > 0 and p.id_unico != current_id
                cb = (
                    f"gym_switch_{target_uid}_{p.id_unico}"
                    if can_switch else f"gym_noop_{target_uid}"
                )
                kb.add(types.InlineKeyboardButton(
                    f"{icon} {p.mote or p.nombre} Nv.{p.nivel}"
                    f" — {p.hp_actual}/{hp_max}",
                    callback_data=cb,
                ))
            kb.add(types.InlineKeyboardButton(
                "◀️ Volver", callback_data=f"gym_back_{target_uid}"
            ))
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=kb,
                )
            except Exception:
                pass

        # gym_switch ───────────────────────────────────────────────────────
        elif action == "switch":
            try:
                new_pid = int(parts[3])
            except (IndexError, ValueError):
                return
            gym_manager.handle_switch(target_uid, new_pid, bot)

        # gym_back ─────────────────────────────────────────────────────────
        elif action == "back":
            battle = gym_manager.get_battle(target_uid)
            if battle:
                gym_manager._refresh_ui(battle, bot)

        # gym_forfeit ──────────────────────────────────────────────────────
        elif action == "forfeit":
            if len(parts) == 3:
                kb = types.InlineKeyboardMarkup()
                kb.add(
                    types.InlineKeyboardButton(
                        "✅ Confirmar rendición",
                        callback_data=f"gym_forfeit_confirm_{target_uid}",
                    ),
                    types.InlineKeyboardButton(
                        "◀️ Volver", callback_data=f"gym_back_{target_uid}"
                    ),
                )
                try:
                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text="¿Seguro que quieres rendirte?",
                        reply_markup=kb,
                    )
                except Exception:
                    pass
            elif len(parts) == 4 and parts[3] == "confirm":
                gym_manager.handle_forfeit(target_uid, bot)

        # gym_noop → no hace nada (botones deshabilitados)


# ═════════════════════════════════════════════════════════════════════════════
# Instancias globales
# ═════════════════════════════════════════════════════════════════════════════
gym_manager = GymBattleManager()
gym_cmd     = GymCommandHandler()