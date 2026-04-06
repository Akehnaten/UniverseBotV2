# -*- coding: utf-8 -*-
"""
pokemon/pvp_battle_system.py
════════════════════════════════════════════════════════════════════════════════
Sistema de Combate PvP y VGC (2v2) entre jugadores.

Arquitectura:
  • Un único motor de combate: battle_engine.py  (sin estado, sin Telegram)
  • PvPBattle / VGCBattle: contenedores de estado para la partida
  • PvPManager: orquesta desafíos, batallas y broadcasts
  • Comando /retar: flujo de selección de formato con botones inline

Flujo de usuario:
  /retar
    → inline: [1v1] [2v2]
    → bot pregunta: "¿A quién quieres retar? Escribe su @username o reenvía un mensaje."
    → se crea un PvPChallenge (pendiente de aceptación)
    → el retado recibe mensaje con [✅ Aceptar] [❌ Rechazar]
    → al aceptar:
        - cada jugador ve su propio panel de batalla (DM, igual al salvaje)
        - en el hilo POKECLUB del grupo se publica un mensaje "espejo" que
          se actualiza en cada turno con las acciones y estado de los Pokémon

Formatos soportados:
  • 1v1  — un Pokémon activo por bando
  • 2v2  — dos Pokémon activos por bando (VGC simplificado)
════════════════════════════════════════════════════════════════════════════════
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

from config import CANAL_ID, POKECLUB
from database import db_manager
from pokemon.battle_engine import (
    BattleUtils,
    DamageResult,
    ResidualParticipant,
    ResidualResult,
    UniversalSide, 
    apply_move, 
    apply_end_of_turn, 
    apply_entry_ability,
    check_confusion,
    calculate_residual_effects,
    resolve_damage_move,
    apply_stage_change,
    determine_turn_order,
    apply_ailment,
    check_can_move,
    can_apply_ailment_in_field,
    WEATHER_IMMUNE_TYPES,
    WEATHER_INFO,
    WEATHER_TYPE_MULT,
    TERRAIN_INFO,
    TERRAIN_TYPE_MULT,
    STATUS_ICONS,
    apply_weather_boost,
    apply_terrain_boost,
    is_grounded,
    activate_weather,
    activate_terrain,
    tick_field_turns,
    # ── Datos de movimientos ─────────────────────────────────────────────────
    MOVE_EFFECTS,
    SECONDARY_AILMENTS,
    DRAIN_MOVES,
    RECOIL_MOVES,
    MOVE_NAMES_ES,
    _HIGH_CRIT_MOVES,
    SELF_KO_MOVES,
)
from pokemon.services import pokemon_service, movimientos_service, pokedex_service
from pokemon.battle_adapter import (side_from_pvp, sync_pvp_side)
from pokemon.battle_ui import build_pokemon_line
from funciones.user_utils import _obtener_id_desde_username

MOVE_TYPE_EMOJI: dict = {
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

MOVE_CAT_EMOJI: dict = {
    "Físico":   "⚔️",
    "Especial": "✨",
    "Estado":   "💫",
}

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class PvPFormat(str, Enum):
    ONE_V_ONE = "1v1"
    TWO_V_TWO = "2v2"  # VGC


class PvPState(str, Enum):
    PENDING    = "pending"     # esperando aceptación
    SELECTING  = "selecting"   # jugadores eligiendo equipo (2v2: elegir 2 de 4)
    ACTIVE     = "active"
    FINISHED   = "finished"


# ══════════════════════════════════════════════════════════════════════════════
# DATACLASSES DE ESTADO
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class PvPChallenge:
    """Desafío pendiente de aceptación."""
    challenger_id:  int
    challenged_id:  int
    fmt:            PvPFormat
    created_at:     float = field(default_factory=time.time)
    # IDs de mensajes enviados al retado (para editar con resultado)
    msg_challenged: Optional[int] = None


@dataclass
class PvPSide:
    """Estado de un bando dentro de la batalla."""
    user_id:          int
    pokemon_ids:      List[int]         # id_unico de Pokémon activos (en orden)
    active_index:     int = 0           # índice actual en pokemon_ids
    # stat stages del Pokémon activo (se resetean al cambiar)
    stat_stages:      Dict[str, int] = field(
        default_factory=lambda: {"atq": 0, "def": 0, "atq_sp": 0, "def_sp": 0, "vel": 0}
    )
    status:           Optional[str] = None   # ailment del activo
    toxic_counter:    int = 0
    sleep_turns:      int = 0
    yawn_counter:     int = 0
    crit_stage:       int = 0   # etapa de golpe crítico (Gen 6+: 0/1/2/3)
    confusion_turns:  int = 0       # ← NUEVO
    leechseeded:      bool = False   # ← NUEVO
    # Mensajes de Telegram
    dm_message_id:        Optional[int] = None  # panel texto + botones (SIEMPRE texto)
    rival_sprite_msg_id:  Optional[int] = None  # foto del rival  (arriba en DM)
    own_sprite_msg_id:    Optional[int] = None  # foto propia     (abajo en DM)
    # Acción elegida este turno (None = aún no eligió)
    pending_action:   Optional[dict] = None  # {"type":"move"|"switch","value":str|int}
    action_timer:     Optional[threading.Timer] = field(default=None, repr=False)
    # True cuando el Pokémon activo se debilitó en combate y el jugador debe
    # elegir un reemplazo de forma GRATUITA (el rival no ataca en ese instante).
    needs_faint_switch: bool = False
    # Status persistente indexado por slot (posición en pokemon_ids)
    slot_statuses: dict = field(default_factory=dict)

    def get_active_pokemon(self):
        """Obtiene el Pokémon activo desde la BD."""
        if self.active_index >= len(self.pokemon_ids):
            return None
        return pokemon_service.obtener_pokemon(self.pokemon_ids[self.active_index])

    def next_alive(self) -> Optional[int]:
        """Retorna el índice del siguiente Pokémon con vida, o None."""
        for i, pid in enumerate(self.pokemon_ids):
            if i == self.active_index:
                continue
            p = pokemon_service.obtener_pokemon(pid)
            if p and p.hp_actual > 0:
                return i
        return None

    def save_slot_status(self) -> None:
        """Guarda el status del Pokémon activo antes de salir."""
        self.leechseeded = False
        self.slot_statuses[self.active_index] = {
            "status":        self.status,
            "sleep_turns":   self.sleep_turns,
            "toxic_counter": self.toxic_counter,
        }

    def restore_slot_status(self, slot_index: int) -> None:
        """Restaura el status del Pokémon que entra. Confusión siempre empieza en 0."""
        saved = self.slot_statuses.get(slot_index, {})
        self.status        = saved.get("status",        None)
        self.sleep_turns   = saved.get("sleep_turns",   0)
        self.toxic_counter = saved.get("toxic_counter", 0)
        # leechseeded no se restaura: las Drenadoras se curan al hacer switch
        self.confusion_turns = 0  # volátil

    def all_fainted(self) -> bool:
        """True si todos los Pokémon del bando están ko."""
        for pid in self.pokemon_ids:
            p = pokemon_service.obtener_pokemon(pid)
            if p and p.hp_actual > 0:
                return False
        return True

    def reset_stages_on_switch(self):
        """
        Resetea únicamente los estados VOLÁTILES al cambiar de Pokémon.
        Los estados PERSISTENTES (status, leechseed, toxic, sleep) NO se borran:
        se guardan/restauran a través de slot_statuses.
        """
        # ── Volátiles (siempre se limpian al cambiar) ────────────────────────
        self.stat_stages     = {"atq": 0, "def": 0, "atq_sp": 0, "def_sp": 0, "vel": 0}
        self.yawn_counter    = 0
        self.crit_stage      = 0
        self.confusion_turns = 0   # Confusión es volátil
        self.needs_faint_switch = False
        # ── Persistentes (NO tocar aquí — manejados por slot_statuses) ───────
        # self.status, self.toxic_counter, self.sleep_turns, self.leechseeded
        # → se guardan en save_slot_status() y se restauran en restore_slot_status()



@dataclass
class PvPBattle:
    """Contenedor completo del estado de una batalla PvP."""
    battle_id:   str
    fmt:         PvPFormat
    side1:       PvPSide           # el retador
    side2:       PvPSide           # el retado
    state:       PvPState = PvPState.ACTIVE
    turn_number: int = 0
    # Campo de batalla (compartido entre bandos)
    weather:         Optional[str] = None
    weather_turns:   int = 0
    terrain:         Optional[str] = None
    terrain_turns:   int = 0
    trick_room:      bool = False
    trick_room_turns: int = 0
    gravity:         bool = False
    gravity_turns:   int = 0
    magic_room:      bool = False
    magic_room_turns: int = 0
    wonder_room:     bool = False
    wonder_room_turns: int = 0
    # Broadcast en el grupo
    group_msg_id:    Optional[int] = None
    # Historial de líneas para el broadcast
    broadcast_log:   List[str] = field(default_factory=list)
    battle_log:      List[str] = field(default_factory=list)   # log mostrado en DM
    winner_id:       Optional[int] = None
    created_at:      float = field(default_factory=time.time)
    # ── Snapshot para restaurar HP/stats reales al finalizar ─────────────────
    _hp_snapshot:    Dict[int, int]  = field(default_factory=dict, repr=False)
    _stats_snapshot: Dict[int, dict] = field(default_factory=dict, repr=False)

    def get_side(self, user_id: int) -> Optional[PvPSide]:
        if self.side1.user_id == user_id:
            return self.side1
        if self.side2.user_id == user_id:
            return self.side2
        return None

    def get_opponent_side(self, user_id: int) -> Optional[PvPSide]:
        if self.side1.user_id == user_id:
            return self.side2
        if self.side2.user_id == user_id:
            return self.side1
        return None

    def both_chose(self) -> bool:
        return (
            self.side1.pending_action is not None
            and self.side2.pending_action is not None
        )

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > 1800  # 30 min


# ══════════════════════════════════════════════════════════════════════════════
# GESTOR PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

class PvPManager:
    """
    Gestiona desafíos y batallas PvP / VGC.

    Instancia global: pvp_manager (al final del módulo).
    """

    TURN_TIMEOUT = 60  # segundos para elegir acción

    def __init__(self):
        self._challenges:   Dict[int, PvPChallenge] = {}
        self._battles:      Dict[str, PvPBattle]    = {}
        self._user_battle:  Dict[int, str]          = {}
        self._pending_vgc:  Dict[str, dict]         = {}  # battle_id → VGC selection state
        self._lock = threading.Lock()

    # ──────────────────────────────────────────────────────────────────────────
    # DESAFÍOS
    # ──────────────────────────────────────────────────────────────────────────
    def _send_vgc_selection_ui(self,battle_id: str,user_id: int,equipo: list,bot,) -> None:
        """Envía al jugador el selector de 4 Pokémon para VGC."""
        estado = self._pending_vgc.get(battle_id)
        if not estado:
            return

        seleccionados = estado["selections"].get(user_id, [])

        texto = (
            "🏆 <b>VGC — Selección de equipo</b>\n\n"
            "Elige exactamente <b>4 Pokémon</b> para llevar a la batalla.\n"
            "Los otros 2 no podrán participar.\n"
            f"Seleccionados: <b>{len(seleccionados)}/4</b>\n\n"
            "Toca un Pokémon para seleccionar/deseleccionar."
        )
        markup = types.InlineKeyboardMarkup(row_width=1)

        for p in equipo:
            pid    = p.id_unico
            nombre = p.mote or p.nombre
            nivel  = p.nivel
            hp_max = p.stats.get("hp", 1) or 1

            # Mostrar stats escalados a nivel 50 como referencia
            stats50 = pokedex_service.calcular_stats(
                p.pokemonID, 50, p.ivs, p.evs, p.naturaleza
            )

            elegido = pid in seleccionados
            prefijo = "✅" if elegido else "⬜"
            label   = (
                f"{prefijo} {nombre} Nv.{nivel}  "
                f"| HP50:{stats50['hp']} Atk50:{stats50['atq']}"
            )
            markup.add(types.InlineKeyboardButton(
                label,
                callback_data=f"pvp_vgcsel_{battle_id}_{user_id}_{pid}",
            ))

        # Botón confirmar (solo habilitado con exactamente 4)
        if len(seleccionados) == 4:
            markup.add(types.InlineKeyboardButton(
                "✅ Confirmar equipo",
                callback_data=f"pvp_vgcconfirm_{battle_id}_{user_id}",
            ))
        else:
            markup.add(types.InlineKeyboardButton(
                f"⬛ Confirmar ({len(seleccionados)}/4 elegidos)",
                callback_data=f"pvp_vgcnoop_{user_id}",
            ))

        try:
            bot.send_message(user_id, texto, parse_mode="HTML", reply_markup=markup)
        except Exception as e:
            logger.error(f"[VGC] Error enviando selector a {user_id}: {e}")

    def handle_vgc_selection_toggle(
        self,
        battle_id: str,
        user_id: int,
        pokemon_id: int,
        bot,
        message,
    ) -> None:
        """Toggle de selección de un Pokémon en VGC."""
        estado = self._pending_vgc.get(battle_id)
        if not estado or estado["confirmed"].get(user_id):
            return

        seleccionados: List[int] = estado["selections"][user_id]

        if pokemon_id in seleccionados:
            seleccionados.remove(pokemon_id)
        elif len(seleccionados) < 4:
            seleccionados.append(pokemon_id)
        # Si ya hay 4 y no está seleccionado → ignorar

        estado["selections"][user_id] = seleccionados

        # Reconstruir UI con el estado actualizado
        ch     = estado["challenge"]
        eq_ids = (estado["equipo1"]
                if user_id == ch.challenger_id else estado["equipo2"])
        equipo = [pokemon_service.obtener_pokemon(pid) for pid in eq_ids]
        equipo = [p for p in equipo if p]

        texto = (
            "🏆 <b>VGC — Selección de equipo</b>\n\n"
            "Elige exactamente <b>4 Pokémon</b> para llevar a la batalla.\n"
            "Los otros 2 no podrán participar.\n"
            f"Seleccionados: <b>{len(seleccionados)}/4</b>\n\n"
            "Toca un Pokémon para seleccionar/deseleccionar."
        )
        markup = types.InlineKeyboardMarkup(row_width=1)
        for p in equipo:
            elegido = p.id_unico in seleccionados
            prefijo = "✅" if elegido else "⬜"
            stats50 = pokedex_service.calcular_stats(
                p.pokemonID, 50, p.ivs, p.evs, p.naturaleza
            )
            label = (
                f"{prefijo} {p.mote or p.nombre} Nv.{p.nivel}  "
                f"| HP50:{stats50['hp']} Atk50:{stats50['atq']}"
            )
            markup.add(types.InlineKeyboardButton(
                label,
                callback_data=f"pvp_vgcsel_{battle_id}_{user_id}_{p.id_unico}",
            ))

        if len(seleccionados) == 4:
            markup.add(types.InlineKeyboardButton(
                "✅ Confirmar equipo",
                callback_data=f"pvp_vgcconfirm_{battle_id}_{user_id}",
            ))
        else:
            markup.add(types.InlineKeyboardButton(
                f"⬛ Confirmar ({len(seleccionados)}/4 elegidos)",
                callback_data=f"pvp_vgcnoop_{user_id}",
            ))

        try:
            bot.edit_message_text(
                texto, message.chat.id, message.message_id,
                parse_mode="HTML", reply_markup=markup,
            )
        except Exception as e:
            logger.warning(f"[VGC] Error editando selector: {e}")

    def handle_vgc_confirm_selection(
        self,
        battle_id: str,
        user_id: int,
        bot,
        message,
    ) -> Tuple[bool, str]:
        """Confirma la selección del jugador. Si ambos confirmaron, inicia la batalla."""
        estado = self._pending_vgc.get(battle_id)
        if not estado:
            return False, "❌ Selección no encontrada."

        seleccionados = estado["selections"].get(user_id, [])
        if len(seleccionados) != 4:
            return False, f"❌ Debes seleccionar exactamente 4 Pokémon ({len(seleccionados)} seleccionados)."

        estado["confirmed"][user_id] = True

        try:
            bot.edit_message_text(
                f"✅ <b>Equipo confirmado</b> ({len(seleccionados)} Pokémon).\n"
                "Esperando al rival...",
                message.chat.id, message.message_id,
                parse_mode="HTML",
            )
        except Exception:
            pass

        # Verificar si ambos confirmaron
        ch = estado["challenge"]
        if all(estado["confirmed"].values()):
            self._iniciar_batalla_vgc(battle_id, estado, bot)

        return True, "✅ Selección confirmada."

    def _iniciar_batalla_vgc(self, battle_id: str, estado: dict, bot) -> None:
        """Inicia la batalla VGC una vez ambos jugadores confirmaron su equipo."""
        ch      = estado["challenge"]
        pids1   = estado["selections"][ch.challenger_id]
        pids2   = estado["selections"][ch.challenged_id]

        side1 = PvPSide(user_id=ch.challenger_id, pokemon_ids=pids1)
        side2 = PvPSide(user_id=ch.challenged_id, pokemon_ids=pids2)

        battle = PvPBattle(
            battle_id=battle_id, fmt=ch.fmt,
            side1=side1, side2=side2,
        )

        with self._lock:
            self._battles[battle_id]                = battle
            self._user_battle[ch.challenger_id]     = battle_id
            self._user_battle[ch.challenged_id]     = battle_id
            self._pending_vgc.pop(battle_id, None)

        # Escalar a nivel 50
        self._escalar_equipo_pvp(battle, pids1 + pids2)

        logger.info(f"[PVP] VGC batalla iniciada: {battle_id}")
        self._send_battle_panels(battle, bot)
        self._send_group_broadcast(battle, bot, ["⚔️ ¡Batalla VGC iniciada! (Nivel 50)\n"])
        
    def create_challenge(
        self,
        challenger_id: int,
        challenged_id: int,
        fmt: PvPFormat,
    ) -> Tuple[bool, str]:
        """Crea un desafío pendiente. Retorna (ok, mensaje)."""
        if challenger_id == challenged_id:
            return False, "❌ No puedes retarte a ti mismo."
        if self.get_battle_for(challenger_id):
            return False, "❌ Ya tienes una batalla activa."
        if self.get_battle_for(challenged_id):
            return False, "❌ Ese jugador ya está en batalla."
        if challenged_id in self._challenges:
            return False, "❌ Ese jugador ya tiene un desafío pendiente."

        eq_challenger = pokemon_service.obtener_equipo(challenger_id)
        if not eq_challenger:
            return False, "❌ No tienes Pokémon para combatir."

        eq_challenged = pokemon_service.obtener_equipo(challenged_id)
        if not eq_challenged:
            return False, "❌ El rival no tiene Pokémon."

        min_pokes = 2 if fmt == PvPFormat.TWO_V_TWO else 1
        if len(eq_challenger) < min_pokes:
            return False, f"❌ Necesitas al menos {min_pokes} Pokémon para {fmt.value}."
        if len(eq_challenged) < min_pokes:
            return False, f"❌ Tu rival no tiene suficientes Pokémon para {fmt.value}."

        ch = PvPChallenge(
            challenger_id = challenger_id,
            challenged_id = challenged_id,
            fmt           = fmt,
        )
        with self._lock:
            self._challenges[challenged_id] = ch

        # Auto-expirar en 120 s
        threading.Timer(120, self._expire_challenge, args=(challenged_id,)).start()
        return True, "✅ Desafío enviado."

    def _expire_challenge(self, challenged_id: int):
        with self._lock:
            self._challenges.pop(challenged_id, None)

    def get_pending_challenge(self, user_id: int) -> Optional[PvPChallenge]:
        return self._challenges.get(user_id)

    def accept_challenge(self, challenged_id: int, bot) -> Tuple[bool, str]:
        """Acepta el desafío e inicia la batalla."""
        ch = self._challenges.pop(challenged_id, None)
        if not ch:
            return False, "❌ No tienes desafíos pendientes."

        eq1 = pokemon_service.obtener_equipo(ch.challenger_id)
        eq2 = pokemon_service.obtener_equipo(challenged_id)

        if ch.fmt == PvPFormat.ONE_V_ONE:
            # Incluir TODO el equipo (HP > 0) normalizado a nivel 50
            pids1 = [p.id_unico for p in eq1 if p.hp_actual > 0]
            pids2 = [p.id_unico for p in eq2 if p.hp_actual > 0]

            # Fallback: si por alguna razón no hay Pokémon con HP, usar todos
            if not pids1:
                pids1 = [p.id_unico for p in eq1]
            if not pids2:
                pids2 = [p.id_unico for p in eq2]

            battle_id = f"pvp_{ch.challenger_id}_{challenged_id}_{int(time.time())}"
            side1 = PvPSide(user_id=ch.challenger_id, pokemon_ids=pids1)
            side2 = PvPSide(user_id=challenged_id,    pokemon_ids=pids2)
            battle = PvPBattle(
                battle_id=battle_id, fmt=ch.fmt,
                side1=side1, side2=side2,
            )

            with self._lock:
                self._battles[battle_id]              = battle
                self._user_battle[ch.challenger_id]   = battle_id
                self._user_battle[challenged_id]      = battle_id

            # Escalar a nivel 50 ANTES de enviar paneles
            self._escalar_equipo_pvp(battle, pids1 + pids2)

            logger.info(f"[PVP] Batalla 1v1 iniciada: {battle_id}")

            # ── Disparar habilidades de entrada al inicio ──────────────────
            # Se recolecta el log para mostrarlo junto al primer panel.
            _entry_log: List[str] = []
            _p1_init = side1.get_active_pokemon()
            _p2_init = side2.get_active_pokemon()
            if _p1_init and _p2_init:
                # Orden de velocidad: el más rápido activa primero
                _sp1 = _p1_init.stats.get("vel", 50)
                _sp2 = _p2_init.stats.get("vel", 50)
                _h1  = getattr(_p1_init, "habilidad", "") or ""
                _h2  = getattr(_p2_init, "habilidad", "") or ""
                if _sp1 >= _sp2:
                    if _h1: self._apply_pvp_entry_ability(battle, side1, side2, _p1_init, _p2_init, _h1, _entry_log)
                    if _h2: self._apply_pvp_entry_ability(battle, side2, side1, _p2_init, _p1_init, _h2, _entry_log)
                else:
                    if _h2: self._apply_pvp_entry_ability(battle, side2, side1, _p2_init, _p1_init, _h2, _entry_log)
                    if _h1: self._apply_pvp_entry_ability(battle, side1, side2, _p1_init, _p2_init, _h1, _entry_log)
            if _entry_log:
                battle.battle_log.append("".join(_entry_log).strip())

            # _send_battle_panels retorna False y cancela la batalla si alguien
            # no tiene DM abierto; en ese caso no hay que hacer nada más.
            panels_ok = self._send_battle_panels(battle, bot)
            if not panels_ok:
                return False, "❌ Batalla cancelada: un jugador no tiene chat privado con el bot."

            n_p1 = len(pids1)
            n_p2 = len(pids2)
            self._send_group_broadcast(
                battle, 
                bot,
                [f"⚔️ ¡Batalla 1v1 iniciada! ({n_p1} vs {n_p2} Pokémon — Nivel 50)\n"])

            # Notificar al challenger que la batalla comenzó
            try:
                p1 = side1.get_active_pokemon()
                p2 = side2.get_active_pokemon()
                n1 = (p1.mote or p1.nombre) if p1 else "?"
                n2 = (p2.mote or p2.nombre) if p2 else "?"
                bot.send_message(
                    ch.challenger_id,
                    f"⚔️ <b>¡{challenged_id} aceptó el desafío!</b>\n\n"
                    f"Tu <b>{n1}</b> (Nv.50) vs su <b>{n2}</b> (Nv.50)\n"
                    f"Todos los Pokémon normalizados a nivel 50.\n"
                    f"¡Revisa el panel de arriba para elegir tu movimiento!",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning(f"[PVP] No se pudo notificar al challenger: {e}")

            return True, "✅ ¡Batalla iniciada! Revisa tu DM."
        else:
            # 2v2 VGC — cada jugador elige 4 de su equipo antes de empezar
            battle_id = f"pvp_{ch.challenger_id}_{challenged_id}_{int(time.time())}"

            # Guardar el challenge con battle_id para la selección
            self._pending_vgc[battle_id] = {
                "challenge":   ch,
                "selections":  {ch.challenger_id: [], challenged_id: []},
                "confirmed":   {ch.challenger_id: False, challenged_id: False},
                "equipo1":     [p.id_unico for p in eq1],
                "equipo2":     [p.id_unico for p in eq2],
            }

            logger.info(f"[PVP] VGC selección iniciada: {battle_id}")
            self._send_vgc_selection_ui(battle_id, ch.challenger_id, eq1, bot)
            self._send_vgc_selection_ui(battle_id, challenged_id,    eq2, bot)
            return True, battle_id

    def reject_challenge(self, challenged_id: int) -> Tuple[bool, str]:
        ch = self._challenges.pop(challenged_id, None)
        if not ch:
            return False, "❌ No tienes desafíos pendientes."
        return True, "❌ Desafío rechazado."

    def _escalar_equipo_pvp(self, battle: PvPBattle, all_pokemon_ids: List[int]) -> None:
        """
        Escala todos los Pokémon participantes a nivel 50 en la BD.
        Guarda un snapshot de HP y stats originales para restaurarlos
        al finalizar la batalla.

        La fórmula usada es la oficial Gen 3+:
        HP:   floor((2*B + IV + EV//4) * 50 / 100) + 50 + 10
        Otro: floor((floor((2*B + IV + EV//4) * 50 / 100) + 5) * nat)
        Con 252 EVs, 31 IVs y naturaleza neutra el rendimiento es
        aproximadamente la mitad que a nivel 100.
        """
        for pid in all_pokemon_ids:
            p = pokemon_service.obtener_pokemon(pid)
            if not p:
                continue

            # Guardar estado original (HP, stats, nivel Y objeto equipado)
            battle._hp_snapshot[pid]    = p.hp_actual
            battle._stats_snapshot[pid] = {
                **p.stats,
                "_nivel":  p.nivel,
                "_objeto": getattr(p, "objeto", None),   # ← NUEVO: preservar objeto
            }

            # Calcular stats a nivel 50 con IVs/EVs/naturaleza reales del Pokémon
            stats50 = pokedex_service.calcular_stats(
                p.pokemonID, 50, p.ivs, p.evs, p.naturaleza
            )
            hp50 = stats50["hp"]

            try:
                db_manager.execute_update(
                    """UPDATE POKEMON_USUARIO SET
                        nivel = 50,
                        ps = ?, atq = ?, def = ?, atq_sp = ?, def_sp = ?, vel = ?,
                        hp_actual = ?
                    WHERE id_unico = ?""",
                    (
                        stats50["hp"],  stats50["atq"],  stats50["def"],
                        stats50["atq_sp"], stats50["def_sp"], stats50["vel"],
                        hp50,
                        pid,
                    ),
                )
            except Exception as e:
                logger.error(f"[PVP] Error escalando Pokémon {pid} a nivel 50: {e}")

    def _restaurar_equipo_pvp(self, battle: PvPBattle) -> None:
        """
        Restaura HP y stats originales de todos los Pokémon al finalizar.
        Importante: el HP real no se toca — los Pokémon salen de PvP
        con el HP que tenían ANTES de entrar (PvP no desgasta).
        """
        for pid, original_hp in battle._hp_snapshot.items():
            original_stats = battle._stats_snapshot.get(pid, {})
            if not original_stats:
                continue
            try:
                nivel_original  = original_stats.pop("_nivel",  None)
                objeto_original = original_stats.pop("_objeto", None)   # ← NUEVO

                nivel_sql      = "nivel = ?,"  if nivel_original is not None else ""
                nivel_params   = (nivel_original,) if nivel_original is not None else ()

                # objeto: restaurar siempre (None limpia, valor devuelve la baya)
                db_manager.execute_update(
                    f"""UPDATE POKEMON_USUARIO SET
                        {nivel_sql}
                        ps = ?, atq = ?, def = ?, atq_sp = ?, def_sp = ?, vel = ?,
                        hp_actual = ?,
                        objeto = ?
                    WHERE id_unico = ?""",
                    (
                        *nivel_params,
                        original_stats.get("ps",     original_stats.get("hp",     50)),
                        original_stats.get("atq",    50),
                        original_stats.get("def",    50),
                        original_stats.get("atq_sp", 50),
                        original_stats.get("def_sp", 50),
                        original_stats.get("vel",    50),
                        original_hp,
                        objeto_original,   # ← restaura la baya (o None si no tenía)
                        pid,
                    ),
                )
            except Exception as e:
                logger.error(f"[PVP] Error restaurando Pokémon {pid}: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # LOOKUP
    # ──────────────────────────────────────────────────────────────────────────

    def get_battle_for(self, user_id: int) -> Optional[PvPBattle]:
        bid = self._user_battle.get(user_id)
        if not bid:
            return None
        return self._battles.get(bid)

    def has_active_battle(self, user_id: int) -> bool:
        b = self.get_battle_for(user_id)
        return b is not None and b.state == PvPState.ACTIVE

    # ──────────────────────────────────────────────────────────────────────────
    # ACCIONES DE TURNO
    # ──────────────────────────────────────────────────────────────────────────

    def submit_action(
        self,
        user_id: int,
        action: dict,
        bot,
    ) -> Tuple[bool, str]:
        """
        Registra la acción del jugador para este turno.
 
        CAMBIOS:
        - Al recibir cualquier acción (move o switch normal), se cancela
          el timer del bando que acaba de actuar de forma inmediata.
        - En faint switch: se limpian charging_move / stat_stages correctamente
          y NO se arranca ningún timer hasta que ambos bandos tengan su
          Pokémon en campo.
        """
        battle = self.get_battle_for(user_id)
        if not battle or battle.state != PvPState.ACTIVE:
            return False, "❌ No tienes batalla activa."
 
        side = battle.get_side(user_id)
        if side is None:
            return False, "❌ Error interno."
 
        # ── Cancelar timer del bando que acaba de actuar ──────────────────────
        if side.action_timer:
            try:
                side.action_timer.cancel()
            except Exception:
                pass
            side.action_timer = None
 
        # ── CASO ESPECIAL: faint switch (reemplazo limpio) ────────────────────
        if side.needs_faint_switch:
            if action.get("type") != "switch":
                return False, "⚠️ Debes elegir un Pokémon de reemplazo."
 
            new_idx = int(action["value"])
            if new_idx >= len(side.pokemon_ids):
                return False, "❌ Índice fuera de rango."
 
            new_p = pokemon_service.obtener_pokemon(side.pokemon_ids[new_idx])
            if not new_p or new_p.hp_actual <= 0:
                return False, "❌ Ese Pokémon está debilitado."
 
            # Guardar status del caído y limpiar estados de 2-turno
            side.save_slot_status()
 
            old_index = side.active_index
            side.active_index = new_idx
            side.reset_stages_on_switch()
 
            # ── NUEVO: limpiar mecánicas de 2-turno del entrante ──────────────
            # El nuevo Pokémon no hereda charging_move ni pending_action del
            # anterior que acaba de caer.
            # PvPSide no tiene charging_move como atributo directo; se maneja
            # a través del pending_action que fue del Pokémon caído.
            # Asegurar que no quede ninguna acción residual del turno anterior.
            side.pending_action = None   # limpiar acción del Pokémon caído
 
            side.restore_slot_status(new_idx)
            side.needs_faint_switch = False
 
            new_name   = new_p.mote or new_p.nombre
            faint_log  = [
                f"  ✊ <b>{self._get_username(user_id)}</b> "
                f"envió a <b>{new_name}</b> (reemplazo limpio — sin coste de turno).\n"
            ]
 
            # Aplicar habilidades de entrada del nuevo Pokémon
            opponent = battle.get_opponent_side(user_id)
            
            # Validación de seguridad: solo procedemos si hay un oponente válido
            if opponent is not None:
                opponent_p = opponent.get_active_pokemon()
                hab = getattr(new_p, "habilidad", "") or ""
                
                if hab and opponent_p:
                    self._apply_pvp_entry_ability(
                        battle, 
                        side, 
                        opponent,  # Ahora el linter sabe que no es None
                        new_p, 
                        opponent_p, 
                        hab, 
                        faint_log,
                    )

 
            # Si el rival también está en faint switch, esperar
            if opponent and opponent.needs_faint_switch:
                self._update_panels(battle, bot, extra_log=faint_log)
                self._update_group_broadcast(battle, bot, faint_log)
                return True, "✅ Pokémon enviado al campo."
 
            # El rival ya tiene su Pokémon activo → iniciar siguiente turno
            self._update_panels(battle, bot, extra_log=faint_log)
            self._update_group_broadcast(battle, bot, faint_log)
            # Timer solo si ninguno está en faint switch
            if not battle.side1.needs_faint_switch and not battle.side2.needs_faint_switch:
                self._start_turn_timer(battle, side.user_id, bot)
                if opponent:
                    self._start_turn_timer(battle, opponent.user_id, bot)
            return True, "✅ Pokémon enviado al campo."
 
        # ── TURNO NORMAL ──────────────────────────────────────────────────────
        if side.pending_action is not None:
            return False, "⏳ Ya elegiste una acción este turno."
 
        opponent = battle.get_opponent_side(user_id)
 
        # Bloquear si el rival todavía está eligiendo reemplazo
        if opponent and opponent.needs_faint_switch:
            return (
                False,
                "⏳ Espera a que tu rival elija su Pokémon de reemplazo."
            )
 
        side.pending_action = action
 
        if battle.both_chose():
            self._cancel_turn_timers(battle)
            self._resolve_turn(battle, bot)
        else:
            # El rival aún no eligió — arrancar su timer si no está activo
            if opponent and opponent.pending_action is None:
                self._start_turn_timer(battle, opponent.user_id, bot)
 
        return True, "✅ Acción registrada."

    def _start_turn_timer(self, battle: PvPBattle, user_id: int, bot):
        """
        Arranca el timer de turno para un jugador.
 
        GUARD: si cualquiera de los dos bandos está en faint switch,
        no se arranca el timer — nadie tiene límite mientras se elige reemplazo.
        """
        # ── Guard: no timer durante faint switch ──────────────────────────────
        if battle.side1.needs_faint_switch or battle.side2.needs_faint_switch:
            return
 
        side = battle.get_side(user_id)
        if not side:
            return
 
        def _timeout():
            if battle.state != PvPState.ACTIVE:
                return
            # Si el bando está en faint switch al momento del timeout, ignorar
            if side.needs_faint_switch:
                return
            if side.pending_action is not None:
                return
            logger.info(f"[PVP] Timeout de turno para {user_id}")
            p = side.get_active_pokemon()
            default_move = (p.movimientos[0] if p and p.movimientos else "tackle")
            side.pending_action = {"type": "move", "value": default_move}
            try:
                bot.send_message(
                    user_id,
                    "⏰ ¡Tiempo agotado! Se usó tu primer movimiento.",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            if battle.both_chose():
                self._cancel_turn_timers(battle)
                self._resolve_turn(battle, bot)
 
        t = threading.Timer(self.TURN_TIMEOUT, _timeout)
        t.daemon = True
        t.start()
        side.action_timer = t

    def _cancel_turn_timers(self, battle: PvPBattle):
        for side in (battle.side1, battle.side2):
            if side.action_timer:
                try:
                    side.action_timer.cancel()
                except Exception:
                    pass
                side.action_timer = None

    # ──────────────────────────────────────────────────────────────────────────
    # RESOLUCIÓN DE TURNO
    # ──────────────────────────────────────────────────────────────────────────

    def _resolve_turn(self, battle: PvPBattle, bot):
        """
        Resuelve el turno cuando ambos bandos eligieron acción.
 
        CAMBIOS:
        - Cuando hay ganador, se muestra el panel actualizado CON el log
          del turno ANTES de llamar _end_battle(), con un delay de 2.5s
          para que ambos jugadores puedan leer qué pasó.
        - Cuando hay faint switch pendiente, NO se arrancan timers.
        - El log del turno se agrega a battle.battle_log antes del panel.
        """
        try:
            battle.turn_number += 1
            turn_log: List[str] = [f"<b>— Turno {battle.turn_number} —</b>\n"]
 
            s1, s2 = battle.side1, battle.side2
            p1 = s1.get_active_pokemon()
            p2 = s2.get_active_pokemon()
 
            # Determinar orden por velocidad (Trick Room lo invierte)
            spd1 = BattleUtils.effective_speed(
                p1.stats.get("vel", 50) if p1 else 50,
                s1.stat_stages.get("vel", 0),
                s1.status,
            ) if p1 else 0
            spd2 = BattleUtils.effective_speed(
                p2.stats.get("vel", 50) if p2 else 50,
                s2.stat_stages.get("vel", 0),
                s2.status,
            ) if p2 else 0
 
            trick_room = getattr(battle, "trick_room", False)
            if trick_room:
                first, second = (s1, s2) if spd1 <= spd2 else (s2, s1)
            else:
                first, second = (s1, s2) if spd1 >= spd2 else (s2, s1)
 
            # Ejecutar primer atacante
            fainted = self._execute_action(battle, first, second, turn_log, bot)
            if not fainted:
                self._execute_action(battle, second, first, turn_log, bot)
 
            # ── Efectos residuales ────────────────────────────────────────────
            a_ctx = side_from_pvp(battle.side1)
            b_ctx = side_from_pvp(battle.side2)
            apply_end_of_turn(a_ctx, b_ctx, battle, turn_log)
            sync_pvp_side(a_ctx, battle.side1)
            sync_pvp_side(b_ctx, battle.side2)
 
            # ── Verificar fin de batalla ──────────────────────────────────────
            winner = None
            if s1.all_fainted():
                winner = s2.user_id
            elif s2.all_fainted():
                winner = s1.user_id
 
            if winner:
                # Mostrar panel actualizado con el log del turno ANTES de
                # terminar — dar tiempo a leer qué pasó.
                self._update_panels(battle, bot, extra_log=turn_log)
                self._update_group_broadcast(battle, bot, turn_log)
                import threading as _th
                _th.Timer(2.5, lambda: self._end_battle(battle, winner, bot, [])).start()
                return
 
            # ── Detectar faint switch necesario ──────────────────────────────
            faint_switches: list = []
            for _side in (s1, s2):
                _active = _side.get_active_pokemon()
                if _active and _active.hp_actual <= 0 and not _side.all_fainted():
                    _side.needs_faint_switch = True
                    # Limpiar pending_action del Pokémon caído
                    _side.pending_action = None
                    faint_switches.append(_side)
 
            # Limpiar acciones del turno en los bandos que NO tienen faint switch
            for _side in (s1, s2):
                if not _side.needs_faint_switch:
                    _side.pending_action = None
 
            self._update_panels(battle, bot, extra_log=turn_log)
            self._update_group_broadcast(battle, bot, turn_log)
 
            if faint_switches:
                # Avisar a cada jugador que debe elegir reemplazo
                for _fside in faint_switches:
                    try:
                        bot.send_message(
                            _fside.user_id,
                            "💀 <b>¡Tu Pokémon se debilitó!</b>\n"
                            "Elige tu siguiente Pokémon usando los botones "
                            "del panel de arriba.\n"
                            "<i>El rival NO atacará mientras eliges.</i>",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass
                # NO iniciar timers mientras haya faint switches pendientes
                return
 
            # ── Turno normal: arrancar timers ─────────────────────────────────
            self._start_turn_timer(battle, s1.user_id, bot)
            self._start_turn_timer(battle, s2.user_id, bot)
 
        except Exception as e:
            logger.error(f"[PVP] Error en _resolve_turn: {e}", exc_info=True)

    def _execute_action(
        self,
        battle:         PvPBattle,
        attacker_side:  PvPSide,
        defender_side:  PvPSide,
        turn_log:       list,
        bot,
    ) -> bool:
        """
        Ejecuta la acción de attacker_side contra defender_side.
        Retorna True si el defensor (y todo su equipo) quedó debilitado.
        """
        action = attacker_side.pending_action
        if action is None:
            return False

        atk_p = attacker_side.get_active_pokemon()
        def_p = defender_side.get_active_pokemon()

        # No actuar si el atacante ya está K.O. (ej: usó Explosión antes)
        if not atk_p or not def_p or atk_p.hp_actual <= 0 or def_p.hp_actual <= 0:
            return False

        atk_name = atk_p.mote or atk_p.nombre
        def_name = def_p.mote or def_p.nombre

        # ── Cambio de Pokémon ─────────────────────────────────────────────
        if action["type"] == "switch":
            new_idx = action["value"]
            new_p   = (
                pokemon_service.obtener_pokemon(attacker_side.pokemon_ids[new_idx])
                if new_idx < len(attacker_side.pokemon_ids)
                else None
            )
            if new_p and new_p.hp_actual > 0:
                attacker_side.active_index = new_idx
                attacker_side.reset_stages_on_switch()
                new_name = new_p.mote or new_p.nombre
                turn_log.append(
                    f"  🔄 {self._get_username(attacker_side.user_id)} "
                    f"envió a <b>{new_name}</b>!\n"
                )
                # Habilidades de entrada
                opponent_p = defender_side.get_active_pokemon()
                hab        = getattr(new_p, "habilidad", "") or ""
                if hab and opponent_p:
                    self._apply_pvp_entry_ability(
                        battle, attacker_side, defender_side,
                        new_p, opponent_p, hab, turn_log,
                    )
            return False

        # ── Movimiento ────────────────────────────────────────────────────
        move_name = action["value"]
        move_key  = move_name.lower().replace(" ", "").replace("-", "")
        move_data = movimientos_service.obtener_movimiento(move_name) or {}
        move_es   = MOVE_NAMES_ES.get(move_key, move_name.title())

        # Proxy para battle_engine (acepta "battle" con wild_* / player_*)
        proxy = _PvPFieldProxy(battle, attacker_side, defender_side)

        turn_log.append(f"\n⚔️ ¡<b>{atk_name}</b> usó <b>{move_es}</b>!\n")

        # ── ¿Puede moverse? ───────────────────────────────────────────────
        if not check_can_move(proxy, is_player=True, actor_name=atk_name, log=turn_log):
            return False

        # ── Confusión ─────────────────────────────────────────────────────
        if check_confusion(
            proxy, is_player=True,
            actor_name  = atk_name,
            actor_level = atk_p.nivel,
            actor_atq   = atk_p.stats.get("atq", 50),
            log         = turn_log,
        ):
            # Sync confusion_turns de vuelta al side
            attacker_side.confusion_turns = proxy.player_confusion_turns
            return False

        # ── Precisión ─────────────────────────────────────────────────────
        # None, 0 o True = movimiento que nunca falla (Aura Esfera, Rotura Rompe,
        # Danza Espada, Rotura Smash, etc.)
        _prec_raw = move_data.get("precision") or move_data.get("accuracy")
        if _prec_raw is None or _prec_raw is True or _prec_raw == 0:
            precision = 999   # nunca falla
        else:
            precision = int(_prec_raw)
        if precision < 100 and random.randint(1, 100) > precision:
            turn_log.append(f"  💨 ¡Pero falló!\n")
            return False

        # ── Datos del movimiento ──────────────────────────────────────────
        _CAT   = {"Physical": "Físico", "Special": "Especial", "Status": "Estado"}
        cat    = move_data.get("categoria") or _CAT.get(move_data.get("category", ""), "Estado")
        poder  = int(move_data.get("poder") or move_data.get("basePower") or 0)

        # ── Movimiento de estado ──────────────────────────────────────────
        if cat == "Estado" or poder == 0:
            self._apply_status_move_pvp(
                battle, attacker_side, defender_side,
                move_key, atk_name, def_name, turn_log,
            )
            return False

        # ── Movimiento de daño ────────────────────────────────────────────
        tipo_mv = move_data.get("tipo") or move_data.get("type", "Normal")

        atk_tipos = []
        def_tipos = []
        try:
            atk_tipos = pokedex_service.obtener_tipos(atk_p.pokemonID)
            def_tipos = pokedex_service.obtener_tipos(def_p.pokemonID)
        except Exception:
            pass

        type_eff = movimientos_service._calcular_efectividad(tipo_mv, def_tipos)
        if type_eff == 0.0:
            turn_log.append(f"  🚫 ¡No afecta a {def_name}!\n")
            return False

        w_mult = apply_weather_boost(battle.weather, tipo_mv)
        t_mult = apply_terrain_boost(
            battle.terrain, tipo_mv,
            is_grounded(atk_tipos, proxy),
        )
        drain  = DRAIN_MOVES.get(move_key, 0.0)
        recoil = RECOIL_MOVES.get(move_key, 0.0)
        _crit  = attacker_side.crit_stage + (1 if move_key in _HIGH_CRIT_MOVES else 0)

        # ── Poder variable por peso ───────────────────────────────────────
        from pokemon.battle_engine import (
            _LOWKICK_MOVES, _HEAVYSLAM_MOVES,
            get_peso_pokemon, calcular_poder_lowkick, calcular_poder_heavyslam,
            tiene_magic_guard,
        )
        if move_key in _LOWKICK_MOVES:
            poder = calcular_poder_lowkick(get_peso_pokemon(def_p.pokemonID))
        elif move_key in _HEAVYSLAM_MOVES:
            poder = calcular_poder_heavyslam(
                get_peso_pokemon(atk_p.pokemonID),
                get_peso_pokemon(def_p.pokemonID),
            )

        _atk_magic_guard = tiene_magic_guard(getattr(atk_p, "habilidad", "") or "")

        # Multiplicador de habilidad del atacante
        from pokemon.battle_engine import calcular_mult_habilidad as _cmh
        _atk_hab = getattr(atk_p, "habilidad", "") or ""
        _atk_hab_mult, _ = _cmh(
            _atk_hab, move_key, tipo_mv, cat,
            poder, hp_ratio=atk_p.hp_actual / max(atk_p.stats.get("hp", 1), 1),
        )
        from pokemon.battle_engine import calcular_mult_objeto as _cmo
        _atk_obj = getattr(atk_p, "objeto", "") or ""
        _atk_type_eff_pre = movimientos_service._calcular_efectividad(tipo_mv, def_tipos)
        _atk_obj_mult, _atk_obj_recoil = _cmo(_atk_obj, tipo_mv, cat, _atk_type_eff_pre)
        poder = max(1, int(poder * _atk_hab_mult * _atk_obj_mult)) if poder > 0 else poder
        _atk_lo_recoil = _atk_obj_recoil

        # Loop multi-hit (para movimientos normales num_hits == 1)
        from pokemon.battle_engine import _roll_num_hits
        num_hits  = _roll_num_hits(move_key, getattr(atk_p, "habilidad", "") or "")
        total_dmg = 0
        result    = None

        for _hit_idx in range(num_hits):
            if def_p.hp_actual <= 0:
                break
            _hit_power = poder * (_hit_idx + 1) if move_key in {"triplekick", "tripleaxel"} else poder
            _hit_name  = move_es if _hit_idx == 0 else f"{move_es} (golpe {_hit_idx + 1})"

            result = resolve_damage_move(
                attacker_name         = atk_name,
                defender_name         = def_name,
                attacker_level        = atk_p.nivel,
                attacker_stats        = atk_p.stats,
                attacker_types        = atk_tipos,
                attacker_stages       = attacker_side.stat_stages,
                defender_hp           = def_p.hp_actual,
                defender_stats        = def_p.stats,
                defender_types        = def_tipos,
                defender_stages       = defender_side.stat_stages,
                move_name             = _hit_name,
                move_power            = max(1, int(_hit_power * w_mult * t_mult)),
                move_category         = cat,
                move_type             = tipo_mv,
                type_effectiveness_fn = movimientos_service._calcular_efectividad,
                drain_ratio           = drain,
                crit_stage            = _crit,
            )
            turn_log.extend(result.log)
            total_dmg += result.damage

            if result.damage > 0:
                def_p.hp_actual = max(0, def_p.hp_actual - result.damage)
                if result.drained_hp > 0:
                    atk_max         = atk_p.stats.get("hp", atk_p.hp_actual) or atk_p.hp_actual
                    atk_p.hp_actual = min(atk_max, atk_p.hp_actual + result.drained_hp)
                    turn_log.append(f"  💚 ¡{atk_name} absorbió {result.drained_hp} HP!\n")
                # Retroceso — bloqueado por Magic Guard
                if recoil and not _atk_magic_guard:
                    recoil_dmg      = max(1, int(result.damage * recoil))
                    atk_p.hp_actual = max(0, atk_p.hp_actual - recoil_dmg)
                    turn_log.append(f"  💢 ¡{atk_name} sufrió {recoil_dmg} de retroceso!\n")

        if num_hits > 1 and total_dmg > 0:
            turn_log.append(f"  🔢 ¡{num_hits} golpes! Daño total: <b>{total_dmg}</b>\n")

        # Life Orb / objeto recoil — bloqueado por Magic Guard
        if _atk_lo_recoil > 0 and total_dmg > 0 and not _atk_magic_guard:
            _lo_pvp = max(1, int(atk_p.stats.get("hp", atk_p.hp_actual) * _atk_lo_recoil))
            atk_p.hp_actual = max(0, atk_p.hp_actual - _lo_pvp)
            turn_log.append(f"  🔴 ¡<b>{atk_name}</b> perdió {_lo_pvp} HP por la Vida Esfera!\n")
            # Persistir HP del atacante (el defensor se persiste más abajo)
            try:
                db_manager.execute_update(
                    "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                    (atk_p.hp_actual, atk_p.id_unico),
                )
            except Exception:
                pass

        if type_eff > 1.0:       turn_log.append("  💥 ¡Es muy eficaz!\n")
        elif 0 < type_eff < 1.0: turn_log.append("  😐 No es muy eficaz…\n")

        # ── Self-KO: Explosión / Autodestrucción debilitan al atacante ──────────
        if move_key in SELF_KO_MOVES and total_dmg > 0:
            atk_p.hp_actual = 0
            turn_log.append(f"  💥 ¡<b>{atk_name}</b> se debilitó por el esfuerzo!\n")

        # Persistir HPs al final del loop (una sola escritura cada uno)
        try:
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                (def_p.hp_actual, def_p.id_unico),
            )
        except Exception as _e:
            logger.error(f"[PVP] Error persistiendo HP def: {_e}")
        try:
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                (atk_p.hp_actual, atk_p.id_unico),
            )
        except Exception:
            pass

        # Efecto secundario de ailment (usa el resultado del último golpe)
        if result is not None and def_p.hp_actual > 0 and defender_side.status is None:
            _sec = SECONDARY_AILMENTS.get(move_key)
            if _sec:
                _ail, _chance = _sec
                if random.randint(1, 100) <= _chance:
                    apply_ailment(proxy, _ail, target_is_wild=True,
                                  target_name=def_name, log=turn_log)
                    defender_side.status = proxy.wild_status

        fainted = def_p.hp_actual <= 0
        if fainted:
            turn_log.append(f"  💀 ¡<b>{def_name}</b> se debilitó!\n")
            next_idx = defender_side.next_alive()
            if next_idx is not None:
                defender_side.active_index = next_idx
                defender_side.reset_stages_on_switch()
                next_p = defender_side.get_active_pokemon()
                if next_p:
                    nname = next_p.mote or next_p.nombre
                    turn_log.append(
                        f"  🔄 {self._get_username(defender_side.user_id)} "
                        f"envió a <b>{nname}</b>!\n"
                    )
                    # Habilidades de entrada del Pokémon nuevo
                    hab2 = getattr(next_p, "habilidad", "") or ""
                    if hab2 and atk_p:
                        self._apply_pvp_entry_ability(
                            battle, defender_side, attacker_side,
                            next_p, atk_p, hab2, turn_log,
                        )

        return fainted and defender_side.all_fainted()

    def _apply_pvp_entry_ability(
        self,
        battle:          PvPBattle,
        entering_side:   PvPSide,
        opponent_side:   PvPSide,
        entering_poke,
        opponent_poke,
        ability:         str,
        log:             list,
    ) -> None:
        """
        Dispara la habilidad de entrada del Pokémon que acaba de salir a campo.
        Cubre: Intimidación, Climas, Terrenos, Rastreo (Trace) y Mimetismo.
        """
        if not ability:
            return
        hab = ability.lower().replace(" ", "").replace("-", "")

        proxy_atk = _PvPFieldProxy(battle, entering_side, opponent_side)

        # ── Intimidación ──────────────────────────────────────────────────────
        if hab in ("intimidacion", "intimidation"):
            opp_name = opponent_poke.mote or opponent_poke.nombre
            ent_name = entering_poke.mote or entering_poke.nombre
            # Verificar que el oponente no tenga Magic Guard ni Claridad Mental
            opp_hab = (getattr(opponent_poke, "habilidad", "") or "").lower().replace(" ", "").replace("-", "")
            if opp_hab not in ("claridadmental", "clearbody", "hiperesc", "hypercutter",
                               "propiopaso", "fullmetalbody"):
                apply_stage_change("atq", -1, opponent_side.stat_stages, opp_name, log)
                log.append(
                    f"  😤 ¡<b>Intimidación</b> de {ent_name} bajó el Ataque de {opp_name}!\n"
                )
            else:
                log.append(
                    f"  😤 La Intimidación de {ent_name} no afectó a {opp_name}.\n"
                )

        # ── Climas ────────────────────────────────────────────────────────────
        _CLIMAS = {
            "sequia": ("sun", 5), "drought": ("sun", 5),
            "sequiaextrema": ("sun", 8), "desolateland": ("sun", 8),
            "llovizna": ("rain", 5), "drizzle": ("rain", 5),
            "lluviaprimordial": ("rain", 8), "primordialsea": ("rain", 8),
            "chorroarena": ("sand", 5), "sandstream": ("sand", 5),
            "nevada": ("snow", 5), "snowwarning": ("snow", 5),
        }
        if hab in _CLIMAS:
            w_key, w_turns = _CLIMAS[hab]
            activate_weather(proxy_atk, w_key, w_turns,
                             entering_poke.mote or entering_poke.nombre, log)

        # ── Terrenos ──────────────────────────────────────────────────────────
        _TERRENOS = {
            "electrogénesis": ("electric", 5), "electricsurge": ("electric", 5),
            "herbogénesis":   ("grassy",   5), "grassysurge":   ("grassy",   5),
            "psicogénesis":   ("psychic",  5), "psychicsurge":  ("psychic",  5),
            "nebulogénesis":  ("misty",    5), "mistysurge":    ("misty",    5),
        }
        if hab in _TERRENOS:
            t_key, t_turns = _TERRENOS[hab]
            activate_terrain(proxy_atk, t_key, t_turns,
                             entering_poke.mote or entering_poke.nombre, log)

        # ── Rastreo (Trace) — copia la habilidad del rival REAL y la persiste ─
        if hab in ("rastreo", "trace"):
            opp_hab_real = getattr(opponent_poke, "habilidad", "") or ""
            ent_name     = entering_poke.mote or entering_poke.nombre
            if opp_hab_real:
                # Persistir la habilidad copiada en BD
                try:
                    db_manager.execute_update(
                        "UPDATE POKEMON_USUARIO SET habilidad = ? WHERE id_unico = ?",
                        (opp_hab_real, entering_poke.id_unico),
                    )
                    entering_poke.habilidad = opp_hab_real
                except Exception as _te:
                    logger.warning(f"[PVP] Trace: error persistiendo habilidad: {_te}")
                log.append(
                    f"  🔍 ¡<b>Rastreo</b>! {ent_name} copió la habilidad "
                    f"<b>{opp_hab_real}</b> del rival.\n"
                )
                # Aplicar la habilidad copiada si tiene efecto de entrada
                self._apply_pvp_entry_ability(
                    battle, entering_side, opponent_side,
                    entering_poke, opponent_poke, opp_hab_real, log,
                )
            else:
                log.append(
                    f"  🔍 ¡Rastreo de {ent_name} no detectó ninguna habilidad!\n"
                )

        # ── Mimetismo — tipo según terreno activo ─────────────────────────────
        if hab in ("mimetismo", "mimicry"):
            _T = {"electric": "Eléctrico", "grassy": "Planta",
                  "misty": "Hada", "psychic": "Psíquico"}
            new_type = _T.get(getattr(battle, "terrain", None) or "", "Normal")
            log.append(
                f"  🎭 {entering_poke.mote or entering_poke.nombre} "
                f"cambió su tipo a <b>{new_type}</b> (Mimetismo).\n"
            )

    def _apply_status_move_pvp(
        self,
        battle: PvPBattle,
        attacker_side: PvPSide,
        defender_side: PvPSide,
        move_key: str,
        atk_name: str,
        def_name: str,
        log: list,
    ):
        """Aplica un movimiento de estado usando MOVE_EFFECTS."""
        effect = MOVE_EFFECTS.get(move_key)
        if not effect:
            log.append(f"  💫 ¡{atk_name} usó {move_key.title()}! (Sin efecto conocido)\n")
            return

        proxy = _PvPFieldProxy(battle, attacker_side, defender_side)

        for (target, stat, delta) in effect.get("stages", []):
            stages = attacker_side.stat_stages if target == "self" else defender_side.stat_stages
            quien  = atk_name if target == "self" else def_name
            apply_stage_change(stat, delta, stages, quien, log)

        if effect.get("yawn") and defender_side.yawn_counter == 0:
            defender_side.yawn_counter = 1
            log.append(f"  😪 ¡{def_name} comenzó a adormilarse!\n")

        if "ailment" in effect:
            ailment = effect["ailment"]
            mk = move_key.lower().replace(" ", "").replace("-", "")

            if mk == "rest":
                # Rest: cura HP completo y duerme al ATACANTE, no al defensor.
                atk_p = attacker_side.get_active_pokemon()
                if atk_p and atk_p.hp_actual > 0:
                    max_hp = atk_p.stats.get("hp", atk_p.hp_actual) or atk_p.hp_actual
                    atk_p.hp_actual = max_hp
                    try:
                        db_manager.execute_update(
                            "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                            (max_hp, atk_p.id_unico),
                        )
                    except Exception:
                        pass
                    attacker_side.status = None
                    attacker_side.toxic_counter = 0
                    attacker_side.status = "slp"
                    attacker_side.sleep_turns = random.randint(2, 3)
                    log.append(
                        f"  💚 ¡<b>{atk_name}</b> se curó completamente "
                        f"y se quedó dormido!\n"
                    )
                else:
                    log.append(f"  💫 ¡{atk_name} no puede usar Descanso!\n")
            elif defender_side.status is None:
                apply_ailment(proxy, ailment, target_is_wild=True,
                              target_name=def_name, log=log)
                defender_side.status = proxy.wild_status

        if "weather" in effect:
            w_key, w_turns = effect["weather"]
            activate_weather(proxy, w_key, w_turns, atk_name, log)

        if "terrain" in effect:
            t_key, t_turns = effect["terrain"]
            activate_terrain(proxy, t_key, t_turns, atk_name, log)

        # ── Golpe crítico (Focus Energy / Laser Focus) ─────────────────────
        if "crit_stage" in effect:
            crit_target, crit_delta = effect["crit_stage"]
            side = attacker_side if crit_target == "self" else defender_side
            side.crit_stage = min(3, side.crit_stage + crit_delta)
            nombre = atk_name if crit_target == "self" else def_name
            if side.crit_stage >= 3:
                log.append(f"  🎯 ¡{nombre} garantiza golpes críticos!\n")
            else:
                log.append(f"  🎯 ¡{nombre} está concentrado para asestar golpes críticos!\n")

        if "heal" in effect:
            atk_p = attacker_side.get_active_pokemon()
            if atk_p:
                max_hp = atk_p.stats.get("hp", atk_p.hp_actual) or atk_p.hp_actual
                gained = max(1, int(max_hp * effect["heal"]))
                new_hp = min(max_hp, atk_p.hp_actual + gained)
                atk_p.hp_actual = new_hp
                try:
                    db_manager.execute_update(
                        "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                        (new_hp, atk_p.id_unico),
                    )
                except Exception:
                    pass
                log.append(f"  💚 {atk_name} recuperó {gained} HP.\n")

        # ── Transformar (Ditto / Move Transformación) ──────────────────────
        if effect.get("transform"):
            def_p = defender_side.get_active_pokemon()
            if def_p:
                atk_p = attacker_side.get_active_pokemon()
                if atk_p:
                    # Copiar stats ofensivas/defensivas (NO hp)
                    new_stats = {k: v for k, v in def_p.stats.items() if k != "hp"}
                    new_stats["hp"] = atk_p.stats.get("hp", atk_p.hp_actual)
                    atk_p.stats = new_stats
                    # Copiar tipos, movimientos y habilidad
                    from pokemon.services.pokedex_service import pokedex_service as _pdx_t
                    atk_p_types = _pdx_t.obtener_tipos(def_p.pokemonID)
                    atk_p.movimientos = list(def_p.movimientos or [])
                    # Copiar etapas de stat del rival
                    attacker_side.stat_stages = dict(defender_side.stat_stages)
                    # Persistir los stats copiados en BD para que el motor los use
                    try:
                        db_manager.execute_update(
                            """UPDATE POKEMON_USUARIO SET
                               ps=?, atq=?, def=?, atq_sp=?, def_sp=?, vel=?,
                               movimientos=?
                               WHERE id_unico=?""",
                            (
                                new_stats.get("hp", 1),
                                new_stats.get("atq", 50),
                                new_stats.get("def", 50),
                                new_stats.get("atq_sp", 50),
                                new_stats.get("def_sp", 50),
                                new_stats.get("vel", 50),
                                ",".join(atk_p.movimientos),
                                atk_p.id_unico,
                            ),
                        )
                    except Exception as _te:
                        logger.warning(f"[PVP] Error persistiendo Transform: {_te}")
                    def_name_t = def_p.mote or def_p.nombre
                    log.append(
                        f"  🔄 ¡<b>{atk_name}</b> se transformó en "
                        f"<b>{def_name_t}</b>!\n"
                        f"  📋 Copió stats, movimientos y etapas de stat.\n"
                    )

    def _apply_pvp_residual(self, battle: PvPBattle, log: list) -> None:
        """Residuales de fin de turno para PvP: drenadoras, status, bostezo."""
        for side_a, side_b in ((battle.side1, battle.side2), (battle.side2, battle.side1)):
            if side_a.leechseeded:
                poke_a = side_a.get_active_pokemon()
                poke_b = side_b.get_active_pokemon()
                if poke_a and poke_a.hp_actual > 0 and poke_b:
                    max_a  = poke_a.stats.get("hp", 1) or 1
                    drain  = max(1, max_a // 8)
                    new_a  = max(0, poke_a.hp_actual - drain)
                    poke_a.hp_actual = new_a
                    try:
                        db_manager.execute_update(
                            "UPDATE POKEMON_USUARIO SET hp_actual=? WHERE id_unico=?",
                            (new_a, poke_a.id_unico),
                        )
                    except Exception:
                        pass
                    max_b  = poke_b.stats.get("hp", 1) or 1
                    new_b  = min(max_b, poke_b.hp_actual + drain)
                    poke_b.hp_actual = new_b
                    try:
                        db_manager.execute_update(
                            "UPDATE POKEMON_USUARIO SET hp_actual=? WHERE id_unico=?",
                            (new_b, poke_b.id_unico),
                        )
                    except Exception:
                        pass
                    log.append(f"  🌱 Drenadoras: {poke_a.mote or poke_a.nombre} pierde {drain} HP.\n")

        for side in (battle.side1, battle.side2):
            poke = side.get_active_pokemon()
            if not poke or poke.hp_actual <= 0:
                continue

            if side.status in ("psn", "brn"):
                hp_max = poke.stats.get("hp", 1) or 1
                dmg    = max(1, hp_max // 8)
                new_hp = max(0, poke.hp_actual - dmg)
                poke.hp_actual = new_hp
                try:
                    db_manager.execute_update(
                        "UPDATE POKEMON_USUARIO SET hp_actual=? WHERE id_unico=?",
                        (new_hp, poke.id_unico),
                    )
                except Exception:
                    pass
                icon  = STATUS_ICONS.get(side.status, "")
                label = "quemadura" if side.status == "brn" else "veneno"
                log.append(f"  {icon} {poke.mote or poke.nombre} sufre {dmg} HP por {label}.\n")

            elif side.status == "tox":
                hp_max = poke.stats.get("hp", 1) or 1
                side.toxic_counter += 1
                dmg    = max(1, (hp_max * side.toxic_counter) // 16)
                new_hp = max(0, poke.hp_actual - dmg)
                poke.hp_actual = new_hp
                try:
                    db_manager.execute_update(
                        "UPDATE POKEMON_USUARIO SET hp_actual=? WHERE id_unico=?",
                        (new_hp, poke.id_unico),
                    )
                except Exception:
                    pass
                log.append(f"  ☠️ {poke.mote or poke.nombre} sufre {dmg} HP por tóxico (×{side.toxic_counter}).\n")

            if side.yawn_counter > 0:
                side.yawn_counter -= 1
                if side.yawn_counter == 0 and side.status is None:
                    proxy = _PvPFieldProxy(battle, side, side)   # solo para apply_ailment
                    apply_ailment(proxy, "slp", target_is_wild=False,
                                  target_name=poke.mote or poke.nombre, log=log)
                    side.status      = proxy.player_status
                    side.sleep_turns = proxy.player_sleep_turns

        # Tick de campo
        tick_field_turns(battle, log)


    # ──────────────────────────────────────────────────────────────────────────
    # MENSAJES TELEGRAM
    # ──────────────────────────────────────────────────────────────────────────

    def _get_username(self, user_id: int) -> str:
        try:
            from funciones import user_service
            info = user_service.get_user_info(user_id)
            return info["nombre"] if info else f"User {user_id}"
        except Exception:
            return f"User {user_id}"

    # ── Sub-menú de ataques ───────────────────────────────────────────────────

    def handle_fight_action(self, user_id: int, bot) -> bool:
        """
        Muestra el selector de movimientos.

        dm_message_id es siempre texto → edit_message_text nunca falla.
        """
        battle = self.get_battle_for(user_id)
        if not battle or battle.state != PvPState.ACTIVE:
            return False

        side  = battle.get_side(user_id)
        own_p = side.get_active_pokemon() if side else None
        if not side or not own_p:
            return False

        if side.pending_action is not None:
            try:
                bot.send_message(
                    user_id,
                    "⏳ Ya elegiste una acción este turno.",
                    parse_mode = "HTML",
                )
            except Exception:
                pass
            return False

        txt = self._build_battle_panel(battle, side)
        txt += "\n\n⚔️ <b>Elige un movimiento:</b>"
        mk  = self._build_moves_markup(battle, side)

        try:
            bot.edit_message_text(
                txt,
                chat_id      = user_id,
                message_id   = side.dm_message_id,
                parse_mode   = "HTML",
                reply_markup = mk,
            )
        except Exception as exc:
            if "message is not modified" not in str(exc):
                logger.warning(f"[PVP] handle_fight_action edit error: {exc}")
        return True

    def handle_back_action(self, user_id: int, bot) -> bool:
        """
        Vuelve al menú principal desde el sub-menú de ataques o equipo.

        dm_message_id es siempre texto → edit_message_text nunca falla.
        """
        battle = self.get_battle_for(user_id)
        if not battle or battle.state != PvPState.ACTIVE:
            return False

        side = battle.get_side(user_id)
        if not side:
            return False

        txt = self._build_battle_panel(battle, side)
        mk  = self._build_battle_markup(battle, side)
        try:
            bot.edit_message_text(
                txt,
                chat_id      = user_id,
                message_id   = side.dm_message_id,
                parse_mode   = "HTML",
                reply_markup = mk,
            )
        except Exception as exc:
            if "message is not modified" not in str(exc):
                logger.warning(f"[PVP] handle_back_action edit error: {exc}")
        return True

    def handle_team_pvp(self, user_id: int, bot) -> bool:
        """
        Muestra el equipo del jugador durante la batalla PvP.
        • Pokémon activo marcado con ▶️
        • Solo permite cambiar a Pokémon con vida distintos del activo
          (hard switch → el rival PUEDE atacar ese turno)
        """
        battle = self.get_battle_for(user_id)
        if not battle or battle.state != PvPState.ACTIVE:
            return False

        side  = battle.get_side(user_id)
        if not side:
            return False

        if side.pending_action is not None:
            try:
                bot.send_message(
                    user_id,
                    "⏳ Ya elegiste una acción este turno.",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return False

        txt = "👥 <b>Tu Equipo</b>\n\n"
        mk  = types.InlineKeyboardMarkup(row_width=1)

        for i, pid in enumerate(side.pokemon_ids):
            p      = pokemon_service.obtener_pokemon(pid)
            if not p:
                continue
            hp_max = p.stats.get("hp", 1) or 1
            hp_pct = (p.hp_actual / hp_max) * 100

            if p.hp_actual <= 0:
                icon = "💀"
            elif hp_pct < 30:
                icon = "🔴"
            elif hp_pct < 60:
                icon = "🟡"
            else:
                icon = "🟢"

            activo = i == side.active_index
            prefijo = "▶️ " if activo else "     "
            p_name  = p.mote or p.nombre
            linea   = f"{prefijo}{icon} {p_name} Nv.{p.nivel}  {p.hp_actual}/{hp_max} HP"
            txt    += linea + "\n"

            if activo or p.hp_actual <= 0:
                # Deshabilitado (activo o KO)
                mk.add(types.InlineKeyboardButton(
                    linea, callback_data=f"pvp_noop_{user_id}",
                ))
            else:
                mk.add(types.InlineKeyboardButton(
                    linea, callback_data=f"pvp_switch_{user_id}_{i}",
                ))

        txt += "\n<i>⚠️ Cambiar aquí es un <b>hard switch</b>: el rival puede atacarte.</i>"
        mk.add(types.InlineKeyboardButton(
            "◀️ Volver", callback_data=f"pvp_back_{user_id}",
        ))

        try:
            bot.edit_message_text(
                txt,
                chat_id      = user_id,
                message_id   = side.dm_message_id,
                parse_mode   = "HTML",
                reply_markup = mk,
            )
        except Exception as exc:
            if "message is not modified" not in str(exc):
                logger.warning(f"[PVP] handle_team_pvp edit error: {exc}")
        return True

    def handle_forfeit_pvp(self, user_id: int, bot) -> bool:
        """
        Procesa la rendición de un jugador. El rival gana automáticamente.
        """
        battle = self.get_battle_for(user_id)
        if not battle or battle.state != PvPState.ACTIVE:
            return False

        opponent_side = battle.get_opponent_side(user_id)
        if not opponent_side:
            return False

        winner_id = opponent_side.user_id
        forfeit_log = [
            f"🏳️ <b>{self._get_username(user_id)}</b> se rindió.\n"
        ]
        self._end_battle(battle, winner_id, bot, forfeit_log)
        return True

    def _build_moves_markup(
        self, battle: "PvPBattle", viewer_side: "PvPSide"
    ) -> "types.InlineKeyboardMarkup":
        """
        Sub-menú de movimientos (idéntico al del combate salvaje):
          Fila i: [Nombre (Poder)]  [🔥Tipo  ⚔️Cat  PP:x/y]
          Última fila: [◀️ Volver]
        """
        from pokemon.services.pp_service import pp_service as _pp_svc

        uid  = viewer_side.user_id
        mk   = types.InlineKeyboardMarkup(row_width=2)
        NOOP = f"pvp_noop_{uid}"

        own_p = viewer_side.get_active_pokemon()
        if not own_p:
            # Sin Pokémon activo: devolver teclado vacío con solo "Volver"
            mk.add(types.InlineKeyboardButton(
                "◀️ Volver", callback_data=f"pvp_back_{uid}",
            ))
            return mk

        movs       = own_p.movimientos
        pokemon_id = own_p.id_unico   # ahora es garantizado int

        for i in range(4):
            if i < len(movs):
                mv         = movs[i]
                mv_key     = mv.lower().replace(" ", "").replace("-", "")
                move_data  = movimientos_service.obtener_movimiento(mv) or {}

                # Nombre en español
                nombre_es  = (
                    MOVE_NAMES_ES.get(mv_key)
                    or move_data.get("nombre", mv.title())
                )

                # Atributos con fallback bilingüe
                _cat_map   = {"Physical": "Físico", "Special": "Especial", "Status": "Estado"}
                poder      = int(move_data.get("poder") or move_data.get("basePower") or 0)
                tipo       = move_data.get("tipo") or move_data.get("type", "Normal")
                categoria  = (
                    move_data.get("categoria")
                    or _cat_map.get(move_data.get("category", ""), "Estado")
                )
                tipo_emoji = MOVE_TYPE_EMOJI.get(tipo, "⚪")
                cat_emoji  = MOVE_CAT_EMOJI.get(categoria, "💫")
                poder_txt  = str(poder) if poder else "—"

                # PP
                try:
                    _pp    = _pp_svc.obtener_pp(pokemon_id, mv)
                    pp_txt = f"{_pp['actual']}/{_pp['maximo']}"
                    tiene_pp = _pp["actual"] > 0
                except Exception:
                    pp_max  = move_data.get("pp", "?")
                    pp_txt  = f"?/{pp_max}"
                    tiene_pp = True

                label_nombre = f"{nombre_es} ({poder_txt})"
                label_info   = f"{tipo_emoji}{tipo}  {cat_emoji}{categoria}  PP:{pp_txt}"

                if not tiene_pp:
                    label_nombre = f"❌ {label_nombre}"

                # ⚠️ FIX BUTTON_DATA_INVALID: Telegram limita callback_data a 64 bytes.
                # Usamos el índice del movimiento (0-3) en lugar del nombre completo.
                # El nombre se resuelve en handle_callback al momento de procesar.
                cb_move = f"pvp_move_{uid}_{i}" if tiene_pp else NOOP
                mk.row(
                    types.InlineKeyboardButton(label_nombre, callback_data=cb_move),
                    types.InlineKeyboardButton(label_info,   callback_data=NOOP),
                )
            else:
                mk.row(
                    types.InlineKeyboardButton("❓ No aprendido", callback_data=NOOP),
                    types.InlineKeyboardButton("—",               callback_data=NOOP),
                )

        mk.add(types.InlineKeyboardButton(
            "◀️ Volver", callback_data=f"pvp_back_{uid}",
        ))
        return mk

    # ── Helpers de visualización del panel PvP ────────────────────────────────
    _TIPO_EMO_PVP = {
        "Normal":"⭐","Fuego":"🔥","Agua":"💧","Planta":"🌿",
        "Eléctrico":"⚡","Hielo":"❄️","Lucha":"🥊","Veneno":"☠️",
        "Tierra":"🌍","Volador":"🌪️","Psíquico":"🔮","Bicho":"🐛",
        "Roca":"🪨","Fantasma":"👻","Dragón":"🐉","Siniestro":"🌑",
        "Acero":"⚙️","Hada":"🌸",
    }
    _STATUS_ICO_PVP = {
        "par":"⚡PAR","brn":"🔥QMD","frz":"❄️CON",
        "slp":"💤DOR","psn":"☠️ENV","tox":"☠️TOX",
    }

    @staticmethod
    def _pvp_tipos_str(tipos: list) -> str:
        emo = PvPManager._TIPO_EMO_PVP
        return "  ".join(f"{emo.get(t,'')} {t}" for t in (tipos or ["Normal"]))

    @staticmethod
    def _pvp_hp_bar(hp: int, hp_max: int, largo: int = 10) -> str:
        pct = hp / max(hp_max, 1)
        f   = max(0, min(largo, round(pct * largo)))
        col = "🟩" if pct > 0.5 else ("🟨" if pct > 0.2 else "🟥")
        return col * f + "⬜" * (largo - f)

    @staticmethod
    def _pvp_stages_str(stages: dict) -> str:
        _L = {"atq":"Atk","def":"Def","atq_sp":"SpA","def_sp":"SpD","vel":"Vel"}
        parts = [
            (f"+{v}" if v > 0 else str(v)) + lbl
            for k, lbl in _L.items()
            if (v := stages.get(k, 0)) != 0
        ]
        return "  ".join(parts)

    @staticmethod
    def _pvp_sprite_url(pokemon_id: int, shiny: bool = False) -> str:
        base = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon"
        return f"{base}/shiny/{pokemon_id}.png" if shiny else f"{base}/{pokemon_id}.png"

    def _build_battle_panel(self, battle: "PvPBattle", viewer_side: "PvPSide") -> str:
        """
        Construye el texto del panel de batalla.

        Formato (los sprites ya están en las fotos de arriba y abajo):

          ⚔️ BATALLA PvP 1v1  —  Turno N
          👤 Rival: NombreRival
          [clima / terreno / salas si hay]

          🔴 NombreRival ─ PokémonRival  ⚙️ Acero  🌸 Hada  Nv.25
             HP: 🟩🟩🟩🟩🟩🟨🟨⬛⬛⬛  45/60
             💊 En pie: 3
             ⚡PAR  +2Atk

          🔵 TuNombre ─ TuPokémon  🔥 Fuego  Nv.30
             HP: 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩  80/80
             💊 En pie: 2

          📋 Últimos N turnos:
          ...log...

          💡 Tu turno — ¿Qué harás?
        """
        from pokemon.battle_ui import build_field_status_line
        from pokemon.services.pokedex_service import pokedex_service as _pdx_svc
        from pokemon.services import pokemon_service as _pksvc

        own   = viewer_side
        rival = battle.get_opponent_side(viewer_side.user_id)

        own_p   = own.get_active_pokemon()
        rival_p = rival.get_active_pokemon() if rival else None

        own_tipos   = _pdx_svc.obtener_tipos(own_p.pokemonID)   if own_p   else ["Normal"]
        rival_tipos = _pdx_svc.obtener_tipos(rival_p.pokemonID) if rival_p else ["Normal"]

        own_max   = own_p.stats.get("hp", own_p.hp_actual)     if own_p   else 1
        rival_max = rival_p.stats.get("hp", rival_p.hp_actual) if rival_p else 1

        rival_username = self._get_username(rival.user_id) if rival else "?"
        own_username   = self._get_username(own.user_id)

        # ── Estado del campo ──────────────────────────────────────────────
        _fl_txt    = build_field_status_line(battle)
        field_line = (f"{_fl_txt}\n") if _fl_txt else ""

        # ── Contar Pokémon en pie ─────────────────────────────────────────
        rival_vivos = 0
        if rival:
            for pid in rival.pokemon_ids:
                p = _pksvc.obtener_pokemon(pid)
                if p and p.hp_actual > 0:
                    rival_vivos += 1

        own_vivos = sum(
            1 for pid in own.pokemon_ids
            if (p := _pksvc.obtener_pokemon(pid)) and p.hp_actual > 0
        )

        # ── Helpers locales ───────────────────────────────────────────────
        def _bar(hp: int, mx: int, length: int = 10) -> str:
            pct    = int(hp / max(1, mx) * 100)
            filled = max(0, min(length, int(pct / 100 * length)))
            color  = "🟩" if pct > 50 else ("🟨" if pct > 20 else "🟥")
            return color * filled + "⬛" * (length - filled)

        def _tipos_str(tipos: list) -> str:
            _EMO = {
                "Normal": "⚪", "Fuego": "🔥", "Agua": "💧", "Planta": "🌿",
                "Eléctrico": "⚡", "Hielo": "🧊", "Lucha": "🥊", "Veneno": "☠️",
                "Tierra": "🌍", "Volador": "🌪️", "Psíquico": "🔮", "Bicho": "🐛",
                "Roca": "🪨", "Fantasma": "👻", "Dragón": "🐉", "Siniestro": "🌑",
                "Acero": "⚙️", "Hada": "🌸",
            }
            return "  ".join(f"{_EMO.get(t, '')} {t}" for t in tipos)

        def _info_str(status: Optional[str], stages: dict) -> str:
            _STA = {
                "brn": "🔥QMD", "par": "⚡PAR", "psn": "☠️ENV",
                "tox": "☠️TOX", "slp": "💤DOR", "frz": "🧊CON", "cnf": "😵CNF",
            }
            _STG = {
                "atq": "Atk", "def": "Def", "atq_sp": "SpA",
                "def_sp": "SpD", "vel": "Vel",
            }
            parts = []
            if status:
                parts.append(_STA.get(status, status.upper()))
            for stat, lbl in _STG.items():
                v = (stages or {}).get(stat, 0)
                if v:
                    parts.append(f"{'+'if v > 0 else ''}{v}{lbl}")
            return "  ".join(parts)

        # ── Bloque RIVAL ──────────────────────────────────────────────────
        if rival_p:
            r_hp   = max(0, rival_p.hp_actual)
            r_info = _info_str(
                rival.status if rival else None,
                rival.stat_stages if rival else {},
            )
            rival_block = (
                f"🔴 <b>{rival_username}</b>  ─  "
                f"<b>{rival_p.mote or rival_p.nombre}</b>  "
                f"{_tipos_str(rival_tipos)}  Nv.{rival_p.nivel}\n"
                f"   HP: {_bar(r_hp, rival_max)}  {r_hp}/{rival_max}\n"
                f"   💊 En pie: {rival_vivos}"
                + (f"\n   {r_info}" if r_info else "")
            )
        else:
            rival_block = f"🔴 <b>{rival_username}</b>  (sin Pokémon)"

        # ── Bloque PROPIO ─────────────────────────────────────────────────
        if own_p:
            o_hp   = max(0, own_p.hp_actual)
            o_info = _info_str(own.status, own.stat_stages)
            own_block = (
                f"🔵 <b>{own_username}</b>  ─  "
                f"<b>{own_p.mote or own_p.nombre}</b>  "
                f"{_tipos_str(own_tipos)}  Nv.{own_p.nivel}\n"
                f"   HP: {_bar(o_hp, own_max)}  {o_hp}/{own_max}\n"
                f"   💊 En pie: {own_vivos}"
                + (f"\n   {o_info}" if o_info else "")
            )
        else:
            own_block = f"🔵 <b>{own_username}</b>  (sin Pokémon)"

        # ── Log de turnos recientes ───────────────────────────────────────
        log_txt = ""
        if battle.battle_log:
            entradas   = battle.battle_log[-3:]
            encabezado = (
                "📋 <b>Último turno:</b>"
                if len(entradas) == 1
                else f"📋 <b>Últimos {len(entradas)} turnos:</b>"
            )
            log_txt = f"\n\n{encabezado}\n" + "\n─\n".join(entradas)

        # ── Composición final ─────────────────────────────────────────────
        return (
            f"⚔️ <b>BATALLA PvP {battle.fmt.value}</b>  —  Turno {battle.turn_number}\n"
            f"👤 Rival: <b>{rival_username}</b>\n"
            + (field_line)
            + f"\n"
            f"{rival_block}\n\n"
            f"{own_block}"
            f"{log_txt}\n\n"
            f"💡 <b>Tu turno</b> — ¿Qué harás?"
        )

    def _build_battle_markup(
        self, battle: "PvPBattle", viewer_side: "PvPSide"
    ) -> "types.InlineKeyboardMarkup":
        """
        Teclado del panel principal de batalla PvP.

        • needs_faint_switch → selector de reemplazo (switch gratuito).
        • Normal → menú principal: ⚔️ Atacar | 👥 Equipo | 🏳️ Rendirse
          (idéntico al menú del combate salvaje)
        """
        uid = viewer_side.user_id
        mk  = types.InlineKeyboardMarkup(row_width=2)

        # ── Faint switch: solo reemplazos ─────────────────────────────────────
        if viewer_side.needs_faint_switch:
            mk.add(types.InlineKeyboardButton(
                "💀 Elige tu Pokémon de reemplazo:",
                callback_data=f"pvp_noop_{uid}",
            ))
            for i, pid in enumerate(viewer_side.pokemon_ids):
                if i == viewer_side.active_index:
                    continue
                p = pokemon_service.obtener_pokemon(pid)
                if not p:
                    continue
                hp_max = p.stats.get("hp", 1) or 1
                hp_pct = (p.hp_actual / hp_max) * 100
                icon   = (
                    "💀" if p.hp_actual <= 0 else
                    "🔴" if hp_pct < 30 else
                    "🟡" if hp_pct < 60 else "🟢"
                )
                if p.hp_actual > 0:
                    mk.add(types.InlineKeyboardButton(
                        f"{icon} {p.mote or p.nombre}  Nv.{p.nivel}  "
                        f"{p.hp_actual}/{hp_max} HP",
                        callback_data=f"pvp_switch_{uid}_{i}",
                    ))
            return mk

        mk.add(
            types.InlineKeyboardButton("⚔️ Combate",  callback_data=f"pvp_fight_{uid}"),
            types.InlineKeyboardButton("👥 Equipo",   callback_data=f"pvp_team_{uid}"),
        )
        mk.add(
            types.InlineKeyboardButton("🏳️ Rendirse", callback_data=f"pvp_forfeit_{uid}"),
        )
        return mk

    def _send_battle_panels(self, battle: "PvPBattle", bot) -> bool:
        """
        Envía el panel inicial de batalla a ambos jugadores por DM.

        Arquitectura de 3 mensajes por jugador:
          Mensaje 1 ── foto sprite RIVAL          → rival_sprite_msg_id
          Mensaje 2 ── foto sprite PROPIO          → own_sprite_msg_id
          Mensaje 3 ── texto panel + botones       → dm_message_id

        dm_message_id apunta SIEMPRE a un mensaje de texto, por lo que
        edit_message_text en handle_fight_action/handle_back_action nunca
        producirá "there is no text in the message to edit".
        """
        _FORBIDDEN_KEYWORDS = (
            "forbidden", "chat not found", "bot was blocked",
            "user is deactivated", "have no rights",
        )
        failed_users: list = []

        for side in (battle.side1, battle.side2):
            try:
                rival_side = battle.get_opponent_side(side.user_id)
                rival_p    = rival_side.get_active_pokemon() if rival_side else None
                own_p      = side.get_active_pokemon()
                rival_name = self._get_username(rival_side.user_id) if rival_side else "Rival"
                own_name   = self._get_username(side.user_id)

                # ── Mensaje 1: foto del RIVAL (arriba) ───────────────────────
                if rival_p:
                    try:
                        rmsg = bot.send_photo(
                            side.user_id,
                            self._pvp_sprite_url(
                                rival_p.pokemonID, getattr(rival_p, "shiny", False)
                            ),
                            caption    = (
                                f"🔴 <b>{rival_name}</b>  —  "
                                f"{rival_p.mote or rival_p.nombre}"
                            ),
                            parse_mode = "HTML",
                        )
                        side.rival_sprite_msg_id = rmsg.message_id
                    except Exception as _re:
                        logger.warning(
                            f"[PVP] No se pudo enviar sprite rival a {side.user_id}: {_re}"
                        )

                # ── Mensaje 2: foto PROPIA (abajo) ───────────────────────────
                if own_p:
                    try:
                        omsg = bot.send_photo(
                            side.user_id,
                            self._pvp_sprite_url(
                                own_p.pokemonID, getattr(own_p, "shiny", False)
                            ),
                            caption    = (
                                f"🔵 <b>{own_name}</b>  —  "
                                f"{own_p.mote or own_p.nombre}"
                            ),
                            parse_mode = "HTML",
                        )
                        side.own_sprite_msg_id = omsg.message_id
                    except Exception as _oe:
                        logger.warning(
                            f"[PVP] No se pudo enviar sprite propio a {side.user_id}: {_oe}"
                        )

                # ── Mensaje 3: panel de TEXTO + botones ──────────────────────
                txt = self._build_battle_panel(battle, side)
                mk  = self._build_battle_markup(battle, side)
                msg = bot.send_message(
                    side.user_id,
                    txt,
                    parse_mode   = "HTML",
                    reply_markup = mk,
                )
                side.dm_message_id = msg.message_id
                logger.info(f"[PVP] Panel enviado a {side.user_id}")

            except Exception as exc:
                err_str   = str(exc)
                is_dm_err = any(kw in err_str.lower() for kw in _FORBIDDEN_KEYWORDS)
                if is_dm_err:
                    logger.warning(
                        f"[PVP] Usuario {side.user_id} no tiene DM abierto: {exc}"
                    )
                else:
                    logger.error(
                        f"[PVP] Error de código enviando panel a {side.user_id}: {exc}",
                        exc_info=True,
                    )
                failed_users.append((side.user_id, err_str, is_dm_err))

        if not failed_users:
            return True

        # ── Notificar fallos en el grupo (igual que antes) ──────────────────
        aviso_lines = ["⚠️ <b>No se pudo iniciar la batalla:</b>"]
        for uid, err, is_dm in failed_users:
            name = self._get_username(uid)
            if is_dm:
                aviso_lines.append(
                    f"• {name} no tiene el chat privado con el bot abierto. "
                    f"Inicia una conversación con el bot e intenta de nuevo."
                )
            else:
                aviso_lines.append(
                    f"• Error inesperado con {name}. Revisa los logs del servidor."
                )
        try:
            from config import CANAL_ID, POKECLUB
            bot.send_message(
                CANAL_ID,
                "\n".join(aviso_lines),
                parse_mode        = "HTML",
                message_thread_id = POKECLUB,
            )
        except Exception as ge:
            logger.error(f"[PVP] No se pudo avisar en el grupo: {ge}")

        return False

    def _update_sprites(self, battle: "PvPBattle", side: "PvPSide", bot) -> None:
        """
        Actualiza las fotos de sprites cuando el Pokémon activo cambia.

        Usa edit_message_media para sobreescribir las fotos existentes
        sin enviar mensajes nuevos. Si la imagen no cambió, Telegram
        lo ignora silenciosamente.
        """
        from telebot.types import InputMediaPhoto

        rival_side = battle.get_opponent_side(side.user_id)
        rival_p    = rival_side.get_active_pokemon() if rival_side else None
        own_p      = side.get_active_pokemon()

        # Sprite del RIVAL
        if side.rival_sprite_msg_id and rival_p:
            try:
                rival_name = self._get_username(rival_side.user_id) if rival_side else "Rival"
                bot.edit_message_media(
                    InputMediaPhoto(
                        self._pvp_sprite_url(
                            rival_p.pokemonID, getattr(rival_p, "shiny", False)
                        ),
                        caption    = (
                            f"🔴 <b>{rival_name}</b>  —  "
                            f"{rival_p.mote or rival_p.nombre}"
                        ),
                        parse_mode = "HTML",
                    ),
                    chat_id    = side.user_id,
                    message_id = side.rival_sprite_msg_id,
                )
            except Exception as exc:
                if "message is not modified" not in str(exc).lower():
                    logger.warning(
                        f"[PVP] No se pudo actualizar sprite rival de {side.user_id}: {exc}"
                    )

        # Sprite PROPIO
        if side.own_sprite_msg_id and own_p:
            try:
                own_name = self._get_username(side.user_id)
                bot.edit_message_media(
                    InputMediaPhoto(
                        self._pvp_sprite_url(
                            own_p.pokemonID, getattr(own_p, "shiny", False)
                        ),
                        caption    = (
                            f"🔵 <b>{own_name}</b>  —  "
                            f"{own_p.mote or own_p.nombre}"
                        ),
                        parse_mode = "HTML",
                    ),
                    chat_id    = side.user_id,
                    message_id = side.own_sprite_msg_id,
                )
            except Exception as exc:
                if "message is not modified" not in str(exc).lower():
                    logger.warning(
                        f"[PVP] No se pudo actualizar sprite propio de {side.user_id}: {exc}"
                    )

    def _update_panels(self, battle: "PvPBattle", bot, extra_log: Optional[List[str]] = None):
        """
        Edita el panel de texto de ambos jugadores y actualiza sus sprites.

        - extra_log se acumula en battle.battle_log (máximo 5 entradas).
        - Los sprites se actualizan con _update_sprites para reflejar
          cambios de Pokémon activo sin enviar mensajes nuevos.
        - dm_message_id es siempre texto → edit_message_text nunca falla.
        """
        if extra_log:
            combined = "".join(extra_log).strip()
            if combined:
                battle.battle_log.append(combined)
                if len(battle.battle_log) > 5:
                    battle.battle_log = battle.battle_log[-5:]

        for side in (battle.side1, battle.side2):
            # ── Actualizar sprites ────────────────────────────────────────────
            try:
                self._update_sprites(battle, side, bot)
            except Exception as _se:
                logger.warning(f"[PVP] Error actualizando sprites de {side.user_id}: {_se}")

            # ── Editar panel de texto ─────────────────────────────────────────
            txt = self._build_battle_panel(battle, side)
            mk  = self._build_battle_markup(battle, side)

            if side.dm_message_id:
                try:
                    bot.edit_message_text(
                        txt,
                        chat_id      = side.user_id,
                        message_id   = side.dm_message_id,
                        parse_mode   = "HTML",
                        reply_markup = mk,
                    )
                except Exception as exc:
                    exc_str = str(exc)
                    if "message is not modified" in exc_str:
                        pass  # inofensivo: el contenido no cambió
                    else:
                        logger.warning(
                            f"[PVP] No se pudo editar panel {side.user_id}: {exc}"
                        )
                        # Fallback: enviar nuevo mensaje de texto
                        try:
                            msg = bot.send_message(
                                side.user_id, txt,
                                parse_mode   = "HTML",
                                reply_markup = mk,
                            )
                            side.dm_message_id = msg.message_id
                        except Exception as e3:
                            logger.warning(
                                f"[PVP] No se pudo re-enviar panel {side.user_id}: {e3}"
                            )
            else:
                # Sin mensaje previo (no debería ocurrir en flujo normal)
                try:
                    msg = bot.send_message(
                        side.user_id, txt,
                        parse_mode   = "HTML",
                        reply_markup = mk,
                    )
                    side.dm_message_id = msg.message_id
                except Exception as e3:
                    logger.warning(f"[PVP] No se pudo enviar panel {side.user_id}: {e3}")

    # ──────────────────────────────────────────────────────────────────────────
    # BROADCAST EN GRUPO (PokeClub)
    # ──────────────────────────────────────────────────────────────────────────

    def _build_broadcast_text(self, battle: PvPBattle, extra_log: Optional[List[str]] = None) -> str:
        """Texto espejo para el grupo — estado actual + últimas acciones."""
        s1 = battle.side1
        s2 = battle.side2
        p1 = s1.get_active_pokemon()
        p2 = s2.get_active_pokemon()

        n1 = self._get_username(s1.user_id)
        n2 = self._get_username(s2.user_id)

        pn1 = (p1.mote or p1.nombre) if p1 else "?"
        pn2 = (p2.mote or p2.nombre) if p2 else "?"
        hp1 = f"{p1.hp_actual}/{p1.stats.get('hp', p1.hp_actual)}" if p1 else "?/??"
        hp2 = f"{p2.hp_actual}/{p2.stats.get('hp', p2.hp_actual)}" if p2 else "?/??"

        txt = (
            f"⚔️ <b>PvP en vivo</b>  [{battle.fmt.value}]  T{battle.turn_number}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🔵 <b>{n1}</b> — {pn1} ({hp1} HP)\n"
            f"🔴 <b>{n2}</b> — {pn2} ({hp2} HP)\n"
            f"━━━━━━━━━━━━━━━\n"
        )

        if extra_log:
            txt += "".join(extra_log)[-1500:]  # limitar longitud

        return txt

    def _send_group_broadcast(self, battle: PvPBattle, bot, initial_log: Optional[List[str]] = None):
        """Envía el mensaje espejo al hilo POKECLUB."""
        try:
            txt = self._build_broadcast_text(battle, initial_log)
            msg = bot.send_message(
                CANAL_ID, txt,
                parse_mode       = "HTML",
                message_thread_id = POKECLUB,
            )
            battle.group_msg_id = msg.message_id
        except Exception as e:
            logger.error(f"[PVP] Error enviando broadcast grupal: {e}")

    def _update_group_broadcast(self, battle: PvPBattle, bot, turn_log: List[str]):
        """Actualiza el mensaje espejo del grupo con el log del turno."""
        if not battle.group_msg_id:
            self._send_group_broadcast(battle, bot, turn_log)
            return
        try:
            txt = self._build_broadcast_text(battle, turn_log)
            # edit_message_text NO acepta message_thread_id
            bot.edit_message_text(
                txt,
                chat_id    = CANAL_ID,
                message_id = battle.group_msg_id,
                parse_mode = "HTML",
            )
        except Exception as e:
            logger.warning(f"[PVP] No se pudo actualizar broadcast: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # FIN DE BATALLA
    # ──────────────────────────────────────────────────────────────────────────

    def _end_battle(self, battle: PvPBattle, winner_id: int, bot, turn_log: list):
        """
        Cierra la batalla, actualiza MMR y notifica.
 
        CAMBIOS:
        - El panel ya fue actualizado con el log del turno antes de llamar
          aquí (desde _resolve_turn con delay). turn_log puede estar vacío.
        - Se cancela los timers al inicio para evitar race conditions.
        """
        # ── Cancelar timers SIEMPRE al entrar ─────────────────────────────────
        self._cancel_turn_timers(battle)
 
        # Restaurar HP y stats originales
        self._restaurar_equipo_pvp(battle)
        battle.state     = PvPState.FINISHED
        battle.winner_id = winner_id
 
        loser_id = (
            battle.side2.user_id if winner_id == battle.side1.user_id
            else battle.side1.user_id
        )
 
        w_name = self._get_username(winner_id)
        l_name = self._get_username(loser_id)
 
        result_log = [f"\n🏆 ¡<b>{w_name}</b> ganó la batalla!\n"]
        if turn_log:
            result_log = turn_log + result_log
 
        # Actualizar MMR
        try:
            self._actualizar_mmr(winner_id, loser_id, battle.fmt.value)
        except Exception as _e:
            logger.warning(f"[PVP] No se pudo actualizar MMR: {_e}")
 
        # Notificar a ambos jugadores
        result_txt = f"{'🏆' if winner_id == battle.side1.user_id else '💀'} ¡{w_name} ganó!\n"
        for side in (battle.side1, battle.side2):
            try:
                role = "🏆 ¡Ganaste!" if side.user_id == winner_id else "💀 Perdiste..."
                txt  = f"{role}\n\n<b>Batalla terminada</b>\n{result_txt}"
                if side.dm_message_id:
                    bot.edit_message_text(
                        txt,
                        chat_id      = side.user_id,
                        message_id   = side.dm_message_id,
                        parse_mode   = "HTML",
                        reply_markup = types.InlineKeyboardMarkup(),
                    )
                else:
                    bot.send_message(side.user_id, txt, parse_mode="HTML")
            except Exception:
                pass
 
        # Actualizar broadcast
        self._update_group_broadcast(battle, bot, result_log)
 
        # Limpiar estado
        with self._lock:
            self._user_battle.pop(battle.side1.user_id, None)
            self._user_battle.pop(battle.side2.user_id, None)
            self._battles.pop(battle.battle_id, None)

    # ──────────────────────────────────────────────────────────────────────────
    # MMR  (ELO simplificado — no depende de pvp_system.py)
    # ──────────────────────────────────────────────────────────────────────────

    def _obtener_mmr(self, user_id: int, fmt: str) -> int:
        campo = f"mmr_{fmt}"
        try:
            r = db_manager.execute_query(
                f"SELECT {campo} FROM LADDER_STATS WHERE userID = ?", (user_id,)
            )
            if r:
                val = r[0][campo] if isinstance(r[0], dict) else r[0][0]
                return int(val) if val is not None else 1000
        except Exception:
            pass
        # Crear fila si no existe
        try:
            db_manager.execute_update(
                "INSERT OR IGNORE INTO LADDER_STATS (userID) VALUES (?)", (user_id,)
            )
        except Exception:
            pass
        return 1000

    def _actualizar_mmr(self, winner_id: int, loser_id: int, fmt: str):
        """Sistema ELO simplificado. Actualiza LADDER_STATS y registra en HISTORIAL_BATALLAS."""
        campo   = f"mmr_{fmt}"
        mmr_w   = self._obtener_mmr(winner_id, fmt)
        mmr_l   = self._obtener_mmr(loser_id,  fmt)
        dif     = mmr_l - mmr_w
        cambio  = 40 if dif > 200 else (25 if dif > 0 else (15 if dif > -200 else 10))

        nuevo_w = mmr_w + cambio
        nuevo_l = max(0, mmr_l - cambio)

        try:
            db_manager.execute_update(
                f"UPDATE LADDER_STATS SET {campo} = ? WHERE userID = ?", (nuevo_w, winner_id)
            )
            db_manager.execute_update(
                f"UPDATE LADDER_STATS SET {campo} = ? WHERE userID = ?", (nuevo_l, loser_id)
            )
        except Exception as e:
            logger.error(f"[PVP] Error actualizando MMR en BD: {e}")
            return

        # Registrar historial (tabla puede no existir en BD antigua — ignorar)
        try:
            db_manager.execute_update(
                """INSERT INTO HISTORIAL_BATALLAS
                   (ganador_id, perdedor_id, tipo_batalla,
                    mmr_ganador_antes, mmr_ganador_despues,
                    mmr_perdedor_antes, mmr_perdedor_despues, cambio_mmr)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (winner_id, loser_id, fmt, mmr_w, nuevo_w, mmr_l, nuevo_l, cambio),
            )
        except Exception:
            pass  # tabla HISTORIAL_BATALLAS opcional

        logger.info(
            f"[PVP] MMR {fmt}: ganador {winner_id} {mmr_w}→{nuevo_w} | "
            f"perdedor {loser_id} {mmr_l}→{nuevo_l}"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # CALLBACK HANDLERS (llamados desde el handler de callbacks de Telegram)
    # ──────────────────────────────────────────────────────────────────────────

    def handle_callback(self, call, bot) -> bool:
        """
        Maneja callbacks con prefix pvp_.
        Retorna True si fue procesado.
        """
        data = call.data
        uid  = call.from_user.id

        # pvp_accept / pvp_reject
        if data == "pvp_accept":
            ok, result = self.accept_challenge(uid, bot)
            bot.answer_callback_query(call.id, result)
            return True

        if data == "pvp_reject":
            ok, result = self.reject_challenge(uid)
            bot.answer_callback_query(call.id, result)
            try:
                bot.edit_message_reply_markup(
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=types.InlineKeyboardMarkup(),
                )
            except Exception:
                pass
            return True

        # pvp_move_{uid}_{idx}
        # idx es el índice (0-3) del movimiento en la lista del Pokémon activo.
        # Resolvemos la clave real aquí para evitar superar el límite de 64 bytes.
        if data.startswith("pvp_move_"):
            suffix = data[len("pvp_move_"):]
            # Último segmento = índice; todo lo anterior = uid (puede tener guiones bajos)
            sep  = suffix.rindex("_")
            cuid = int(suffix[:sep])
            idx  = int(suffix[sep + 1:])

            if cuid != uid:
                bot.answer_callback_query(call.id, "❌ Acción no válida.")
                return True

            # Resolver clave del movimiento desde el Pokémon activo del jugador
            battle = self.get_battle_for(uid)
            if not battle:
                bot.answer_callback_query(call.id, "❌ Sin batalla activa.")
                return True
            side = battle.get_side(uid)
            poke = side.get_active_pokemon() if side else None
            if not poke or not poke.movimientos or idx >= len(poke.movimientos):
                bot.answer_callback_query(call.id, "❌ Movimiento no disponible.")
                return True

            move = poke.movimientos[idx]
            ok, msg = self.submit_action(uid, {"type": "move", "value": move}, bot)
            bot.answer_callback_query(call.id, "✅ Movimiento registrado." if ok else msg)
            return True

        # pvp_switch_{uid}_{idx}
        if data.startswith("pvp_switch_"):
            suffix = data[len("pvp_switch_"):]
            cuid_str, idx_str = suffix.rsplit("_", 1)
            cuid = int(cuid_str)
            idx  = int(idx_str)
            if cuid != uid:
                bot.answer_callback_query(call.id, "❌ Acción no válida.")
                return True
            ok, msg = self.submit_action(uid, {"type": "switch", "value": idx}, bot)
            bot.answer_callback_query(call.id, "🔄 Cambio registrado." if ok else msg)
            return True
        
        return False

# ══════════════════════════════════════════════════════════════════════════════
# PROXY DE CAMPO  (adapta PvPBattle a la interfaz que espera battle_engine)
# ══════════════════════════════════════════════════════════════════════════════

class _PvPFieldProxy:
    """
    Proxy liviano que expone la interfaz de 'battle' que usan las funciones
    de battle_engine (activate_weather, check_can_move, apply_ailment, etc.).

    Las funciones de battle_engine leen/escriben atributos como:
      battle.weather, battle.weather_turns, battle.terrain, battle.terrain_turns
      battle.wild_status, battle.player_status
      battle.wild_sleep_turns, battle.player_sleep_turns
      battle.wild_yawn_counter, battle.player_yawn_counter
      battle.wild_toxic_counter, battle.player_toxic_counter
      battle.gravity, battle.trick_room, ...
    """

    def __init__(self, battle: PvPBattle, attacker: PvPSide, defender: PvPSide):
        self._battle   = battle
        self._attacker = attacker
        self._defender = defender

    # Campo compartido — redirigir a battle
    @property
    def weather(self): return self._battle.weather
    @weather.setter
    def weather(self, v): self._battle.weather = v

    @property
    def weather_turns(self): return self._battle.weather_turns
    @weather_turns.setter
    def weather_turns(self, v): self._battle.weather_turns = v

    @property
    def terrain(self): return self._battle.terrain
    @terrain.setter
    def terrain(self, v): self._battle.terrain = v

    @property
    def terrain_turns(self): return self._battle.terrain_turns
    @terrain_turns.setter
    def terrain_turns(self, v): self._battle.terrain_turns = v

    @property
    def trick_room(self): return getattr(self._battle, "trick_room", False)
    @trick_room.setter
    def trick_room(self, v): self._battle.trick_room = v

    @property
    def trick_room_turns(self): return getattr(self._battle, "trick_room_turns", 0)
    @trick_room_turns.setter
    def trick_room_turns(self, v): self._battle.trick_room_turns = v

    @property
    def gravity(self): return getattr(self._battle, "gravity", False)
    @gravity.setter
    def gravity(self, v): self._battle.gravity = v

    @property
    def gravity_turns(self): return getattr(self._battle, "gravity_turns", 0)
    @gravity_turns.setter
    def gravity_turns(self, v): self._battle.gravity_turns = v

    @property
    def magic_room(self): return getattr(self._battle, "magic_room", False)
    @magic_room.setter
    def magic_room(self, v): self._battle.magic_room = v

    @property
    def magic_room_turns(self): return getattr(self._battle, "magic_room_turns", 0)
    @magic_room_turns.setter
    def magic_room_turns(self, v): self._battle.magic_room_turns = v

    @property
    def wonder_room(self): return getattr(self._battle, "wonder_room", False)
    @wonder_room.setter
    def wonder_room(self, v): self._battle.wonder_room = v

    @property
    def wonder_room_turns(self): return getattr(self._battle, "wonder_room_turns", 0)
    @wonder_room_turns.setter
    def wonder_room_turns(self, v): self._battle.wonder_room_turns = v

    # Status del "wild" → defensor (opponent)
    @property
    def wild_status(self): return self._defender.status
    @wild_status.setter
    def wild_status(self, v): self._defender.status = v

    @property
    def wild_sleep_turns(self): return self._defender.sleep_turns
    @wild_sleep_turns.setter
    def wild_sleep_turns(self, v): self._defender.sleep_turns = v

    @property
    def wild_toxic_counter(self): return self._defender.toxic_counter
    @wild_toxic_counter.setter
    def wild_toxic_counter(self, v): self._defender.toxic_counter = v

    @property
    def wild_yawn_counter(self): return self._defender.yawn_counter
    @wild_yawn_counter.setter
    def wild_yawn_counter(self, v): self._defender.yawn_counter = v

    # Status del "player" → atacante
    @property
    def player_status(self): return self._attacker.status
    @player_status.setter
    def player_status(self, v): self._attacker.status = v

    @property
    def player_sleep_turns(self): return self._attacker.sleep_turns
    @player_sleep_turns.setter
    def player_sleep_turns(self, v): self._attacker.sleep_turns = v

    @property
    def player_toxic_counter(self): return self._attacker.toxic_counter
    @player_toxic_counter.setter
    def player_toxic_counter(self, v): self._attacker.toxic_counter = v

    @property
    def player_yawn_counter(self): return self._attacker.yawn_counter
    @player_yawn_counter.setter
    def player_yawn_counter(self, v): self._attacker.yawn_counter = v

    # ── Confusión ─────────────────────────────────────────────────────────────
    @property
    def player_confusion_turns(self):
        return self._attacker.confusion_turns
    @player_confusion_turns.setter
    def player_confusion_turns(self, v):
        self._attacker.confusion_turns = v

    @property
    def wild_confusion_turns(self):
        return self._defender.confusion_turns
    @wild_confusion_turns.setter
    def wild_confusion_turns(self, v):
        self._defender.confusion_turns = v

    # ── Drenadoras (Leech Seed) ────────────────────────────────────────────────
    @property
    def player_leechseeded(self):
        return self._attacker.leechseeded
    @player_leechseeded.setter
    def player_leechseeded(self, v):
        self._attacker.leechseeded = v

    @property
    def wild_leechseeded(self):
        return self._defender.leechseeded
    @wild_leechseeded.setter
    def wild_leechseeded(self, v):
        self._defender.leechseeded = v

    # ── Etapas de stats ────────────────────────────────────────────────────────
    @property
    def wild_stat_stages(self): return self._defender.stat_stages
    @property
    def player_stat_stages(self): return self._attacker.stat_stages


# ══════════════════════════════════════════════════════════════════════════════
# UTILS UI
# ══════════════════════════════════════════════════════════════════════════════

def _hp_bar(pct: int, length: int = 10) -> str:
    filled = max(0, min(length, int(pct / 100 * length)))
    color  = "🟢" if pct > 50 else ("🟡" if pct > 20 else "🔴")
    return color * filled + "⬛" * (length - filled)

def _format_stages(stages: dict) -> str:
    """Muestra los stat stages activos. Ej: '📊 Def▼▼ Vel▲'  Vacío si todos son 0."""
    _LABELS = {"atq": "Atq", "def": "Def", "atq_sp": "AtqE", "def_sp": "DefE", "vel": "Vel"}
    parts = []
    for key, label in _LABELS.items():
        v = stages.get(key, 0)
        if v > 0:
            parts.append(f"{label}{'▲' * min(v, 6)}")
        elif v < 0:
            parts.append(f"{label}{'▼' * min(abs(v), 6)}")
    return ("📊 " + " ".join(parts)) if parts else ""

# ══════════════════════════════════════════════════════════════════════════════
# COMANDO /retar  — handler para registrar en el bot
# ══════════════════════════════════════════════════════════════════════════════

class PvPCommandHandler:
    """
    Handler del comando /retar.
    Registrar en UniverseBot.py:
 
        from pokemon.pvp_battle_system import pvp_cmd, pvp_manager
        pvp_cmd.register(bot)
    """
 
    def register(self, bot):
        """Registra los handlers del comando /retar y los callbacks."""
 
        @bot.message_handler(commands=["retar"])
        def cmd_retar(message):
            self.handle_retar(message, bot)
 
        # ── Selección de formato ──────────────────────────────────────────────
        @bot.callback_query_handler(func=lambda c: c.data.startswith("pvp_fmt_"))
        def cb_pvp_fmt(call):
            self.handle_format_selection(call, bot)
 
        # ── Aceptar / Rechazar desafío ────────────────────────────────────────
        @bot.callback_query_handler(func=lambda c: c.data in ("pvp_accept", "pvp_reject"))
        def cb_pvp_accept(call):
            pvp_manager.handle_callback(call, bot)
 
        # ── Acciones de batalla: movimiento y switch ──────────────────────────
        @bot.callback_query_handler(
            func=lambda c: (
                c.data.startswith("pvp_move_")
                or c.data.startswith("pvp_switch_")
            )
        )
        def cb_pvp_action(call):
            pvp_manager.handle_callback(call, bot)
 
        # ── Panel principal: Atacar ───────────────────────────────────────────
        @bot.callback_query_handler(func=lambda c: c.data.startswith("pvp_fight_"))
        def cb_pvp_fight(call):
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            uid = call.from_user.id
            pvp_manager.handle_fight_action(uid, bot)
 
        # ── Panel principal: Volver ───────────────────────────────────────────
        @bot.callback_query_handler(func=lambda c: c.data.startswith("pvp_back_"))
        def cb_pvp_back(call):
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            uid = call.from_user.id
            pvp_manager.handle_back_action(uid, bot)
 
        # ── Panel principal: Equipo ───────────────────────────────────────────
        @bot.callback_query_handler(func=lambda c: c.data.startswith("pvp_team_"))
        def cb_pvp_team(call):
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            uid = call.from_user.id
            pvp_manager.handle_team_pvp(uid, bot)
 
        # ── Panel principal: Rendirse ─────────────────────────────────────────
        @bot.callback_query_handler(func=lambda c: c.data.startswith("pvp_forfeit_"))
        def cb_pvp_forfeit(call):
            uid = call.from_user.id
            # Pedir confirmación si aún no se confirmó
            parts = call.data.split("_")   # pvp_forfeit_{uid}  o  pvp_forfeit_confirm_{uid}
            if len(parts) == 3:
                # Primera pulsación: mostrar confirmación
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass
                kb = types.InlineKeyboardMarkup(row_width=2)
                kb.add(
                    types.InlineKeyboardButton(
                        "✅ Confirmar rendición",
                        callback_data=f"pvp_forfeit_confirm_{uid}",
                    ),
                    types.InlineKeyboardButton(
                        "◀️ Volver",
                        callback_data=f"pvp_back_{uid}",
                    ),
                )
                battle = pvp_manager.get_battle_for(uid)
                if battle:
                    side = battle.get_side(uid)
                    if side and side.dm_message_id:
                        try:
                            bot.edit_message_text(
                                "¿Seguro que quieres rendirte?",
                                chat_id      = uid,
                                message_id   = side.dm_message_id,
                                reply_markup = kb,
                            )
                        except Exception:
                            pass
            elif len(parts) == 4 and parts[2] == "confirm":
                # Segunda pulsación: ejecutar rendición
                try:
                    bot.answer_callback_query(call.id, "🏳️ Te rendiste.")
                except Exception:
                    pass
                pvp_manager.handle_forfeit_pvp(uid, bot)
 
        # ── Botones deshabilitados (noop) ─────────────────────────────────────
        @bot.callback_query_handler(func=lambda c: c.data.startswith("pvp_noop_"))
        def cb_pvp_noop(call):
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
 
        # ── Selección VGC ─────────────────────────────────────────────────────
        @bot.callback_query_handler(func=lambda c: c.data.startswith("pvp_vgcsel_"))
        def cb_pvp_vgcsel(call):
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            # pvp_vgcsel_{battle_id}_{user_id}_{pokemon_id}
            parts = call.data.split("_", 4)
            if len(parts) < 5:
                return
            battle_id  = parts[2]
            user_id    = int(parts[3])
            pokemon_id = int(parts[4])
            if call.from_user.id != user_id:
                return
            pvp_manager.handle_vgc_selection_toggle(
                battle_id, user_id, pokemon_id, bot, call.message
            )
 
        @bot.callback_query_handler(func=lambda c: c.data.startswith("pvp_vgcconfirm_"))
        def cb_pvp_vgcconfirm(call):
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
            # pvp_vgcconfirm_{battle_id}_{user_id}
            parts = call.data.split("_", 3)
            if len(parts) < 4:
                return
            battle_id = parts[2]
            user_id   = int(parts[3])
            if call.from_user.id != user_id:
                return
            pvp_manager.handle_vgc_confirm_selection(battle_id, user_id, bot, call.message)
 
        @bot.callback_query_handler(func=lambda c: c.data.startswith("pvp_vgcnoop_"))
        def cb_pvp_vgcnoop(call):
            try:
                bot.answer_callback_query(call.id, "Selecciona exactamente 4 Pokémon.")
            except Exception:
                pass
 
        import logging as _logging
        _logging.getLogger(__name__).info(
            "[PVP] Registrado: /retar + todos los callbacks pvp_*"
        )
 
    # ── Comandos ──────────────────────────────────────────────────────────────
 
    def handle_retar(self, message, bot):
        uid = message.from_user.id
        cid = message.chat.id
        tid = getattr(message, "message_thread_id", None)
 
        eq = pokemon_service.obtener_equipo(uid)
        if not eq:
            bot.send_message(
                cid,
                "❌ No tienes Pokémon para retar. Usa /profesor.",
                parse_mode="HTML",
                message_thread_id=tid,
            )
            return
 
        if pvp_manager.has_active_battle(uid):
            bot.send_message(
                cid,
                "⚔️ Ya tienes una batalla activa.",
                parse_mode="HTML",
                message_thread_id=tid,
            )
            return
 
        mk = types.InlineKeyboardMarkup(row_width=2)
        mk.add(
            types.InlineKeyboardButton("⚔️ 1v1", callback_data="pvp_fmt_1v1"),
            types.InlineKeyboardButton("🌀 2v2 (VGC)", callback_data="pvp_fmt_2v2"),
        )
 
        bot.send_message(
            cid,
            "🏟️ <b>¡Modo Desafío!</b>\n\n¿Qué formato quieres jugar?",
            parse_mode        = "HTML",
            reply_markup      = mk,
            message_thread_id = tid,
        )
 
    def handle_format_selection(self, call, bot):
        """
        Callback para elegir el formato. Tras elegir, usa
        register_next_step_handler para capturar el mensaje con el rival
        con máxima prioridad (no compite con otros handlers).
        """
        uid     = call.from_user.id
        fmt_str = call.data.replace("pvp_fmt_", "")
 
        try:
            fmt = PvPFormat(fmt_str)
        except ValueError:
            bot.answer_callback_query(call.id, "❌ Formato inválido.")
            return
 
        bot.answer_callback_query(call.id, f"Formato {fmt.value} seleccionado ✅")
 
        # Editar el mensaje para pedir el rival
        instrucciones = (
            f"🏟️ <b>Formato elegido: {fmt.value}</b>\n\n"
            f"Ahora dime quién es tu rival.\n"
            f"Podés:\n"
            f"• Escribir su <b>@username</b> (con la @)\n"
            f"• <b>Mencionar</b> su nombre tocando el @\n"
            f"• <b>Reenviar</b> un mensaje suyo\n\n"
            f"<i>(Tienes 60 segundos para responder)</i>"
        )
        try:
            bot.edit_message_text(
                instrucciones,
                chat_id      = call.message.chat.id,
                message_id   = call.message.message_id,
                parse_mode   = "HTML",
                reply_markup = types.InlineKeyboardMarkup(),
            )
        except Exception:
            pass
 
        # ── FIX Bug 1: usar next_step_handler en lugar de message_handler ──────
        # register_next_step_handler tiene MAYOR prioridad que los handlers
        # normales y sólo se dispara UNA vez para el chat_id correcto.
        # Esto garantiza que el mensaje de respuesta llegue aquí y no sea
        # interceptado por _handle_texto_grupo u otros handlers registrados
        # anteriormente.
        def _esperar_objetivo(response_message):
            # Auto-expirar: si tardó demasiado el next_step ya no está activo
            self._procesar_objetivo(response_message, fmt, bot)
 
        bot.register_next_step_handler(call.message, _esperar_objetivo)
 
    def _procesar_objetivo(self, message, fmt: "PvPFormat", bot):
        """
        Resuelve el usuario objetivo desde el mensaje de respuesta y crea
        el desafío. Llamado por register_next_step_handler — prioridad máxima.
        """
        uid = message.from_user.id
        cid = message.chat.id
        tid = getattr(message, "message_thread_id", None)
 
        target_id:    int | None = None
        target_debug: str        = ""
 
        # ── 1. Forward ────────────────────────────────────────────────────────
        if message.forward_from:
            target_id    = message.forward_from.id
            target_debug = f"forward:{target_id}"
 
        # ── 2. text_mention (usuario sin @username — entidad Telegram) ────────
        if target_id is None and message.entities:
            for entity in message.entities:
                if entity.type == "text_mention" and entity.user:
                    target_id    = entity.user.id
                    target_debug = f"text_mention:{target_id}"
                    break
 
        # ── 3. @mention clásico → resolver por BD ─────────────────────────────
        if target_id is None and message.entities:
            for entity in message.entities:
                if entity.type == "mention":
                    # Extraer username SIN la '@'
                    username_raw = message.text[
                        entity.offset + 1: entity.offset + entity.length
                    ]
                    if username_raw:
                        from funciones.user_utils import _obtener_id_desde_username
                        resolved = _obtener_id_desde_username(username_raw, cid, bot)
                        if resolved:
                            target_id    = resolved
                            target_debug = f"mention_entity:{username_raw}"
                        break
 
        # ── 4. Texto libre con @ al inicio (fallback) ─────────────────────────
        if target_id is None:
            text = (message.text or "").strip().lstrip("@")
            if text:
                from funciones.user_utils import _obtener_id_desde_username
                resolved = _obtener_id_desde_username(text, cid, bot)
                if resolved:
                    target_id    = resolved
                    target_debug = f"text_fallback:{text}"
 
        if not target_id:
            bot.send_message(
                cid,
                "❌ No pude identificar al jugador.\n\n"
                "Intentá de nuevo con <b>/retar</b> usando una de estas formas:\n"
                "• Escribí su <b>@username</b> (con el símbolo @)\n"
                "• Tocá su nombre para que aparezca la mención azul\n"
                "• Reenviá un mensaje suyo",
                parse_mode        = "HTML",
                message_thread_id = tid,
            )
            return
 
        import logging as _log
        _log.getLogger(__name__).debug(f"[PVP] Rival resuelto: {target_debug}")
 
        if target_id == uid:
            bot.send_message(cid, "❌ No puedes retarte a ti mismo.",
                             message_thread_id=tid)
            return
 
        ok, msg = pvp_manager.create_challenge(uid, target_id, fmt)
        if not ok:
            bot.send_message(cid, msg, parse_mode="HTML", message_thread_id=tid)
            return
 
        # Notificar al retado
        challenger_name = self._get_username(uid)
        mk = types.InlineKeyboardMarkup(row_width=2)
        mk.add(
            types.InlineKeyboardButton("✅ Aceptar", callback_data="pvp_accept"),
            types.InlineKeyboardButton("❌ Rechazar", callback_data="pvp_reject"),
        )
 
        try:
            sent = bot.send_message(
                target_id,
                f"⚔️ <b>¡Desafío recibido!</b>\n\n"
                f"<b>{challenger_name}</b> te reta a una batalla <b>{fmt.value}</b>.\n\n"
                f"⏰ Tienes 120 segundos para responder.",
                parse_mode   = "HTML",
                reply_markup = mk,
            )
            ch = pvp_manager._challenges.get(target_id)
            if ch:
                ch.msg_challenged = sent.message_id
        except Exception as e:
            import logging as _log
            _log.getLogger(__name__).error(
                f"[PVP] No se pudo notificar al retado {target_id}: {e}"
            )
            bot.send_message(
                cid,
                "⚠️ Desafío creado pero no pude enviar DM al rival.\n"
                "Asegurate de que haya iniciado chat con el bot.",
                message_thread_id=tid,
            )
            return
 
        target_name = self._get_username(target_id)
        bot.send_message(
            cid,
            f"✅ ¡Desafío enviado a <b>{target_name}</b>!\n"
            f"Esperando respuesta…",
            parse_mode        = "HTML",
            message_thread_id = tid,
        )
 
    def _get_username(self, user_id: int) -> str:
        try:
            from funciones import user_service
            info = user_service.get_user_info(user_id)
            return info["nombre"] if info else f"User {user_id}"
        except Exception:
            return f"User {user_id}"
 


# ══════════════════════════════════════════════════════════════════════════════
# INSTANCIAS GLOBALES
# ══════════════════════════════════════════════════════════════════════════════

pvp_manager = PvPManager()
pvp_cmd     = PvPCommandHandler()