# -*- coding: utf-8 -*-
"""
pokemon/trade_handler.py
════════════════════════════════════════════════════════════════════════════════
Sistema de intercambio P2P de Pokémon entre jugadores.

Flujo completo
──────────────
  PASO 1 — En PokeClub (grupo)
    Usuario usa /trade.
    Bot borra el comando y responde en el mismo hilo:
      "¿Con quién querés intercambiar?  (reenvía su mensaje, mencionalo o
       escribí su @username)"
    El usuario responde en el hilo → el bot resuelve al destinatario.
    Toda esta parte es pública para que etiquetar sea natural.

  PASO 2 en adelante — En DM (privado de cada usuario)
    Una vez identificado el rival, toda la interacción migra a DM,
    simulando la consola personal del entrenador.

    2a. Bot avisa brevemente en PokeClub que se resolvió (mensaje efímero).
    2b. Iniciador recibe su equipo en DM → elige Pokémon a ofrecer.
    2c. Destinatario recibe en DM: "X te quiere hacer un trade. [✅][❌]"
    3.  Si acepta → elige su Pokémon del equipo en DM.
    4.  Cada jugador recibe la tarjeta de confirmación con el sprite del
        Pokémon que va a RECIBIR.  [✅ Confirmar][❌ Cancelar]
    5.  Si ambos confirman → swap en BD + chequeo evolución por intercambio.
        Cualquier rechazo/cancelación notifica a ambos en DM.

Objetos equipados
─────────────────
    `objeto` es columna de POKEMON_USUARIO.  Al intercambiar solo se
    cambia `userID`, así que el objeto viaja con el Pokémon sin lógica extra.

Prefijo de callbacks: ``pktrade_``
Expiración de sesión: 5 minutos sin actividad.
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import telebot
from telebot import types

from config import CANAL_ID, POKECLUB
from database import db_manager
from funciones.user_utils import extraer_user_id
from pokemon.services.evolucion_service import evolucion_service
from pokemon.services.pokedex_service import pokedex_service
from pokemon.services.pokemon_service import pokemon_service
from utils.thread_utils import get_thread_id

logger = logging.getLogger(__name__)

_SESSION_TTL   = 300   # segundos hasta que expira una sesión sin actividad
_CLEANUP_EVERY = 120   # intervalo del hilo de limpieza


# ─────────────────────────────────────────────────────────────────────────────
# Modelo de sesión
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _TradeSession:
    """Estado completo de un intercambio pendiente entre dos jugadores."""

    session_id:   str
    initiator_id: int
    target_id:    Optional[int] = None

    # id_unico en POKEMON_USUARIO
    pokemon_a: Optional[int] = None   # Pokémon del iniciador
    pokemon_b: Optional[int] = None   # Pokémon del destinatario

    # Confirmaciones de la tarjeta final
    confirmed_a: bool = False
    confirmed_b: bool = False

    created_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.created_at = time.time()

    def expired(self) -> bool:
        return (time.time() - self.created_at) > _SESSION_TTL


# ─────────────────────────────────────────────────────────────────────────────
# Handler principal
# ─────────────────────────────────────────────────────────────────────────────

class TradeHandler:
    """
    Handler de intercambios P2P de Pokémon.
    Paso 1: identificar rival en PokeClub.
    Paso 2+: toda la interacción en DM.
    """

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        self._sessions: Dict[str, _TradeSession] = {}
        self._by_user:  Dict[int, str]            = {}

        self._register()
        self._start_cleanup()

    # ── registro ──────────────────────────────────────────────────────────────

    def _register(self) -> None:
        self.bot.register_message_handler(self.cmd_trade, commands=["trade"])
        self.bot.register_callback_query_handler(
            self.handle_callback,
            func=lambda c: bool(c.data and c.data.startswith("pktrade_")),
        )

    # ── limpieza periódica ────────────────────────────────────────────────────

    def _start_cleanup(self) -> None:
        def _loop() -> None:
            while True:
                time.sleep(_CLEANUP_EVERY)
                self._purge_expired()
        threading.Thread(target=_loop, daemon=True, name="trade-cleanup").start()

    def _purge_expired(self) -> None:
        expired = [sid for sid, s in list(self._sessions.items()) if s.expired()]
        for sid in expired:
            s = self._sessions.pop(sid, None)
            if not s:
                continue
            self._by_user.pop(s.initiator_id, None)
            if s.target_id:
                self._by_user.pop(s.target_id, None)
            self._dm(s.initiator_id, "⌛ Tu trade expiró sin completarse (5 min).")
            if s.target_id:
                self._dm(s.target_id, "⌛ El trade que tenías pendiente expiró.")
        if expired:
            logger.info(f"[TRADE] {len(expired)} sesión(es) expirada(s) purgadas.")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _dm(
        self,
        user_id: int,
        text: str,
        markup: Optional[types.InlineKeyboardMarkup] = None,
    ) -> Optional[types.Message]:
        try:
            return self.bot.send_message(
                user_id, text, parse_mode="HTML", reply_markup=markup
            )
        except Exception as exc:
            logger.debug(f"[TRADE] _dm uid={user_id}: {exc}")
            return None

    def _edit_dm(
        self,
        user_id: int,
        message_id: int,
        text: str,
        markup: Optional[types.InlineKeyboardMarkup] = None,
    ) -> None:
        try:
            self.bot.edit_message_text(
                text, user_id, message_id, parse_mode="HTML", reply_markup=markup
            )
        except Exception as exc:
            logger.debug(f"[TRADE] _edit_dm uid={user_id}: {exc}")

    def _delete(self, chat_id: int, message_id: int) -> None:
        try:
            self.bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    def _answer(
        self, call: types.CallbackQuery, text: str = "", alert: bool = False
    ) -> None:
        try:
            self.bot.answer_callback_query(call.id, text, show_alert=alert)
        except Exception:
            pass

    def _ephemeral(self, chat_id: int, text: str, tid: Optional[int], delay: float = 10.0) -> None:
        """Mensaje en el grupo que se borra solo."""
        try:
            m = self.bot.send_message(
                chat_id, text, parse_mode="HTML", message_thread_id=tid
            )
            threading.Timer(delay, lambda: self._delete(chat_id, m.message_id)).start()
        except Exception:
            pass

    # ── datos de Pokémon ──────────────────────────────────────────────────────

    @staticmethod
    def _display_name(p) -> str:
        return p.mote or p.nombre

    @staticmethod
    def _sprite_url(p) -> str:
        base = (
            "https://raw.githubusercontent.com/PokeAPI/sprites/master"
            "/sprites/pokemon/versions/generation-v/black-white/animated"
        )
        suffix = f"/shiny/{p.pokemonID}.gif" if getattr(p, "shiny", False) else f"/{p.pokemonID}.gif"
        return base + suffix

    def _ficha(self, p) -> str:
        """Ficha completa del Pokémon para la tarjeta de confirmación del trade."""
        nombre = self._display_name(p)
        shiny  = " ✨" if getattr(p, "shiny", False) else ""
        sexo   = {"M": " ♂", "F": " ♀"}.get(getattr(p, "sexo", None) or "", "")
        tipos  = " / ".join(pokedex_service.obtener_tipos(p.pokemonID) or ["—"])

        objeto_txt = f"\n🎒 <b>Objeto:</b> {p.objeto}" if p.objeto else ""
        nat = getattr(p, "naturaleza", None) or "—"
        hab = getattr(p, "habilidad",  None) or "—"

        ivs = getattr(p, "ivs", {}) or {}
        def iv(k): return ivs.get(k, "?")

        evs = getattr(p, "evs", {}) or {}
        ev_labels = {"hp": "HP", "atq": "Atq", "def": "Def",
                     "atq_sp": "SpAtq", "def_sp": "SpDef", "vel": "Vel"}
        evs_txt = "  ".join(
            f"{ev_labels[k]}:{v}" for k, v in evs.items() if v and int(v) > 0
        ) or "Sin EVs"

        movs = [m for m in (getattr(p, "movimientos", []) or []) if m]
        movs_txt = "\n".join(f"  • {m}" for m in movs) if movs else "  • —"

        return (
            f"<b>{nombre}</b>{shiny}{sexo}  <code>#{p.pokemonID}</code>\n"
            f"<i>{tipos}</i> · Nv.<b>{p.nivel}</b>{objeto_txt}\n"
            f"\n🌿 <b>Naturaleza:</b> {nat}"
            f"\n⚡ <b>Habilidad:</b> {hab}"
            f"\n\n📊 <b>IVs:</b>"
            f"\n  HP:<b>{iv('hp')}</b>  Atq:<b>{iv('atq')}</b>  Def:<b>{iv('def')}</b>"
            f"\n  SpAtq:<b>{iv('atq_sp')}</b>  SpDef:<b>{iv('def_sp')}</b>  Vel:<b>{iv('vel')}</b>"
            f"\n\n📈 <b>EVs:</b> {evs_txt}"
            f"\n\n⚔️ <b>Movimientos:</b>\n{movs_txt}"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 1 — /trade en PokeClub
    # ─────────────────────────────────────────────────────────────────────────

    def cmd_trade(self, message: types.Message) -> None:
        """
        Punto de entrada.  Permitido en PokeClub o en privado.

        Borra el comando y pregunta en el mismo hilo con quién se quiere
        intercambiar, para que etiquetar al rival sea natural.
        """
        if not message.from_user:
            return
        uid     = message.from_user.id
        chat_id = message.chat.id
        tid     = get_thread_id(message)

        es_privado  = message.chat.type == "private"
        es_pokeclub = (chat_id == CANAL_ID and tid == POKECLUB)

        if not es_privado and not es_pokeclub:
            self._delete(chat_id, message.message_id)
            self._ephemeral(chat_id, "❌ Solo podés usar /trade en PokeClub.", tid, delay=6)
            return

        self._delete(chat_id, message.message_id)

        if not db_manager.user_exists(uid):
            self._ephemeral(chat_id, "⚠️ Registrate primero con /registrar.", tid, delay=6)
            return

        if uid in self._by_user:
            self._dm(uid, "⚠️ Ya tenés un trade activo. Esperá a que expire o cancelalo.")
            return

        equipo = pokemon_service.obtener_equipo(uid)
        if not equipo:
            self._ephemeral(
                chat_id,
                "❌ No tenés Pokémon en el equipo para intercambiar.",
                tid, delay=8,
            )
            return

        # ── Publicar pregunta en PokeClub ─────────────────────────────────────
        fu = message.from_user  # ya validado no-None arriba
        nombre_user = f"@{fu.username}" if fu.username else (fu.first_name or "Entrenador")
        try:
            msg_pregunta = self.bot.send_message(
                chat_id,
                f"🔄 <b>{nombre_user}</b> quiere hacer un trade.\n\n"
                f"<b>{nombre_user}</b>, ¿con quién querés intercambiar?\n"
                f"Respondé <b>este mensaje</b>:\n"
                f"• Reenviá un mensaje del otro jugador\n"
                f"• Mencionalo con @username\n"
                f"• Escribí su ID numérico",
                parse_mode="HTML",
                message_thread_id=tid,
            )
        except Exception as exc:
            logger.error(f"[TRADE] No se pudo publicar en PokeClub: {exc}")
            return

        self.bot.register_next_step_handler(
            msg_pregunta,
            lambda reply: self._resolve_target(
                reply, uid, msg_pregunta, chat_id, tid
            ),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 2 — Resolución del rival en PokeClub
    # ─────────────────────────────────────────────────────────────────────────

    def _resolve_target(
        self,
        message: types.Message,
        initiator_id: int,
        msg_pregunta: types.Message,
        chat_id: int,
        tid: Optional[int],
    ) -> None:
        """
        Recibe la respuesta del iniciador en PokeClub.
        Solo procesa el mensaje si el autor es el iniciador; cualquier otro
        mensaje de un tercero re-registra el handler y lo descarta.
        """
        # Guard: mensajes de sistema no tienen from_user
        if not message.from_user:
            self.bot.register_next_step_handler(
                msg_pregunta,
                lambda reply: self._resolve_target(
                    reply, initiator_id, msg_pregunta, chat_id, tid
                ),
            )
            return

        if message.from_user.id != initiator_id:
            # Mensaje de otra persona en el hilo — ignorar y seguir esperando
            self.bot.register_next_step_handler(
                msg_pregunta,
                lambda reply: self._resolve_target(
                    reply, initiator_id, msg_pregunta, chat_id, tid
                ),
            )
            return

        # Limpiar el hilo: borrar pregunta y respuesta
        self._delete(chat_id, msg_pregunta.message_id)
        self._delete(chat_id, message.message_id)

        # Cancelación explícita por texto
        texto = (message.text or "").strip().lower()
        if texto in ("/cancelartrade", "cancelar", "/cancelar"):
            self._ephemeral(chat_id, "❌ Trade cancelado.", tid, delay=5)
            return

        # prefer_mention=True: si el usuario A responde etiquetando a B,
        # la mención tiene prioridad sobre el reply_to (que apuntaría al
        # bot, no a B). Sin esto se resuelve el ID del bot y falla con
        # "no podés intercambiar con vos mismo".
        target_id, display = extraer_user_id(message, self.bot, prefer_mention=True)

        if target_id is None:
            self._ephemeral(
                chat_id,
                f"❌ {display}\n\nUsá /trade de nuevo para intentarlo.",
                tid, delay=12,
            )
            return

        if target_id == initiator_id:
            self._ephemeral(chat_id, "❌ No podés intercambiar con vos mismo.", tid, delay=6)
            return

        if not db_manager.user_exists(target_id):
            self._ephemeral(
                chat_id, f"❌ {display} no está registrado.", tid, delay=8
            )
            return

        if target_id in self._by_user:
            self._ephemeral(
                chat_id,
                f"❌ {display} ya tiene un trade activo. Intentalo más tarde.",
                tid, delay=8,
            )
            return

        # ── Crear sesión ──────────────────────────────────────────────────────
        session_id = f"trade_{initiator_id}_{int(time.time())}"
        session    = _TradeSession(
            session_id=session_id,
            initiator_id=initiator_id,
            target_id=target_id,
        )
        self._sessions[session_id] = session
        self._by_user[initiator_id] = session_id
        self._by_user[target_id]    = session_id

        fu_init = message.from_user  # ya validado no-None en _resolve_target
        nombre_init = f"@{fu_init.username}" if (fu_init and fu_init.username) else (fu_init.first_name if fu_init else "Entrenador")
        self._ephemeral(
            chat_id,
            f"📲 <b>{nombre_init}</b> ↔ <b>{display}</b>\n"
            f"Revisá tu DM para continuar el trade 🎮",
            tid, delay=12,
        )

        equipo = pokemon_service.obtener_equipo(initiator_id)
        if not equipo:
            self._cancel_session(session_id, "❌ No tenés Pokémon en el equipo.")
            return

        self._ask_pokemon(initiator_id, equipo, session_id, step="a")

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 3 — Selección de Pokémon en DM
    # ─────────────────────────────────────────────────────────────────────────

    def _ask_pokemon(
        self,
        user_id: int,
        equipo: list,
        session_id: str,
        step: str,
    ) -> None:
        """
        Envía al usuario su equipo en DM para que elija qué Pokémon intercambiar.
        step="a" → iniciador  |  step="b" → destinatario
        """
        markup = types.InlineKeyboardMarkup(row_width=1)
        for p in equipo:
            nombre = self._display_name(p)
            shiny  = " ✨" if getattr(p, "shiny", False) else ""
            sexo   = {"M": " ♂", "F": " ♀"}.get(getattr(p, "sexo", None) or "", "")
            objeto = f"  🎒 {p.objeto}" if p.objeto else ""
            label  = f"{nombre}{shiny}{sexo} · Nv.{p.nivel}{objeto}"
            cb     = f"pktrade_sel{step}:{user_id}:{session_id}:{p.id_unico}"
            markup.add(types.InlineKeyboardButton(label, callback_data=cb))

        markup.add(
            types.InlineKeyboardButton(
                "❌ Cancelar trade",
                callback_data=f"pktrade_cancel:{user_id}:{session_id}",
            )
        )
        self._dm(
            user_id,
            "🎮 <b>Trade Pokémon</b>\n\n"
            "¿Qué Pokémon querés intercambiar?\n"
            "<i>(Solo podés ofrecer Pokémon de tu equipo activo)</i>",
            markup,
        )

    def _handle_sela(
        self,
        call: types.CallbackQuery,
        uid: int,
        session_id: str,
        pokemon_id: int,
    ) -> None:
        """Iniciador eligió su Pokémon → notificar al destinatario en DM."""
        self._answer(call)

        session = self._sessions.get(session_id)
        if not session or session.expired():
            self._edit_dm(uid, call.message.message_id, "⌛ La sesión expiró.")
            return

        p = pokemon_service.obtener_pokemon(pokemon_id)
        if not p or p.usuario_id != uid:
            self._edit_dm(uid, call.message.message_id, "❌ Pokémon no válido.")
            return

        session.pokemon_a = pokemon_id
        session.touch()

        self._edit_dm(
            uid, call.message.message_id,
            f"✅ Elegiste <b>{self._display_name(p)}</b> Nv.{p.nivel}.\n\n"
            f"⏳ Esperando que el otro jugador acepte el trade…",
        )

        fu = call.from_user
        nombre_init = f"@{fu.username}" if (fu and fu.username) else (fu.first_name if fu else "Entrenador")
        if session.target_id is None:
            self._edit_dm(uid, call.message.message_id, "❌ Sesión inválida.")
            return
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(
                "✅ Aceptar",
                callback_data=f"pktrade_acc:{session.target_id}:{session_id}",
            ),
            types.InlineKeyboardButton(
                "❌ Rechazar",
                callback_data=f"pktrade_rej:{session.target_id}:{session_id}",
            ),
        )
        self._dm(
            session.target_id,
            f"🔄 <b>Solicitud de trade</b>\n\n"
            f"<b>{nombre_init}</b> quiere intercambiar un Pokémon con vos.\n\n"
            f"Te ofrece:\n{self._ficha(p)}\n\n"
            f"¿Aceptás?",
            markup,
        )

    def _handle_selb(
        self,
        call: types.CallbackQuery,
        uid: int,
        session_id: str,
        pokemon_id: int,
    ) -> None:
        """Destinatario eligió su Pokémon → enviar tarjetas de confirmación."""
        self._answer(call)

        session = self._sessions.get(session_id)
        if not session or session.expired():
            self._edit_dm(uid, call.message.message_id, "⌛ La sesión expiró.")
            return

        p = pokemon_service.obtener_pokemon(pokemon_id)
        if not p or p.usuario_id != uid:
            self._edit_dm(uid, call.message.message_id, "❌ Pokémon no válido.")
            return

        session.pokemon_b = pokemon_id
        session.touch()

        self._delete(uid, call.message.message_id)
        self._send_confirmations(session)

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 4 — El destinatario acepta o rechaza
    # ─────────────────────────────────────────────────────────────────────────

    def _handle_acc(
        self, call: types.CallbackQuery, uid: int, session_id: str
    ) -> None:
        """Destinatario aceptó → mostrarle su equipo en DM."""
        self._answer(call)

        session = self._sessions.get(session_id)
        if not session or session.expired():
            self._edit_dm(uid, call.message.message_id, "⌛ Esta solicitud expiró.")
            return

        equipo = pokemon_service.obtener_equipo(uid)
        if not equipo:
            self._edit_dm(
                uid, call.message.message_id,
                "❌ No tenés Pokémon en el equipo.",
            )
            self._cancel_session(
                session_id,
                "❌ El otro jugador no tiene Pokémon en su equipo. Trade cancelado.",
                notify_target=False,
            )
            return

        self._edit_dm(uid, call.message.message_id, "✅ Aceptaste el trade.")
        session.touch()
        self._ask_pokemon(uid, equipo, session_id, step="b")

    def _handle_rej(
        self, call: types.CallbackQuery, uid: int, session_id: str
    ) -> None:
        """Destinatario rechazó."""
        self._answer(call)
        session = self._sessions.get(session_id)
        if session and not session.expired():
            self._edit_dm(uid, call.message.message_id, "❌ Rechazaste el trade.")
            self._cancel_session(
                session_id,
                "❌ El otro jugador rechazó tu trade.",
                notify_target=False,
            )
        else:
            self._edit_dm(uid, call.message.message_id, "⌛ Esta solicitud ya expiró.")

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 5 — Tarjetas de confirmación con sprites
    # ─────────────────────────────────────────────────────────────────────────

    def _send_confirmations(self, session: _TradeSession) -> None:
        """
        Envía a cada jugador la tarjeta mostrando el sprite del Pokémon
        que va a RECIBIR.  Ambos deben presionar ✅ para ejecutar el swap.
        """
        if session.pokemon_a is None or session.pokemon_b is None:
            self._cancel_session(session.session_id, "❌ Faltan datos de Pokémon en la sesión.")
            return
        p_a = pokemon_service.obtener_pokemon(session.pokemon_a)
        p_b = pokemon_service.obtener_pokemon(session.pokemon_b)

        if not p_a or not p_b:
            self._cancel_session(session.session_id, "❌ Error al obtener los Pokémon.")
            return

        def _markup(owner_id: int) -> types.InlineKeyboardMarkup:
            mk = types.InlineKeyboardMarkup(row_width=2)
            mk.add(
                types.InlineKeyboardButton(
                    "✅ ¡Confirmar trade!",
                    callback_data=f"pktrade_conf:{owner_id}:{session.session_id}:yes",
                ),
                types.InlineKeyboardButton(
                    "❌ Cancelar",
                    callback_data=f"pktrade_conf:{owner_id}:{session.session_id}:no",
                ),
            )
            return mk

        def _send_card(user_id: int, recibe, da) -> None:
            caption = (
                f"🎮 <b>Confirmación de trade</b>\n\n"
                f"📤 Entregás:\n{self._ficha(da)}\n\n"
                f"📥 Recibís:\n{self._ficha(recibe)}\n\n"
                f"<i>¿Confirmás el intercambio?</i>"
            )
            try:
                self.bot.send_photo(
                    user_id,
                    self._sprite_url(recibe),
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=_markup(user_id),
                )
            except Exception:
                # Fallback sin foto si el sprite no carga
                self._dm(user_id, caption, _markup(user_id))

        # Cada jugador ve el sprite del Pokémon que va a recibir
        _send_card(session.initiator_id, recibe=p_b, da=p_a)
        if session.target_id is not None:
            _send_card(session.target_id, recibe=p_a, da=p_b)

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 6 — Confirmación final
    # ─────────────────────────────────────────────────────────────────────────

    def _handle_conf(
        self,
        call: types.CallbackQuery,
        uid: int,
        session_id: str,
        respuesta: str,
    ) -> None:
        self._answer(call)

        session = self._sessions.get(session_id)
        if not session or session.expired():
            self._edit_dm(uid, call.message.message_id, "⌛ La sesión expiró.")
            return

        if respuesta == "no":
            fu = call.from_user
            nombre = f"@{fu.username}" if (fu and fu.username) else (fu.first_name if fu else "Entrenador")
            self._edit_dm(uid, call.message.message_id, "❌ Cancelaste el trade.")
            self._cancel_session(
                session_id,
                f"❌ <b>{nombre}</b> canceló el trade.",
                notify_initiator=(uid == session.target_id),
                notify_target=(uid == session.initiator_id),
            )
            return

        if uid == session.initiator_id:
            session.confirmed_a = True
        elif uid == session.target_id:
            session.confirmed_b = True
        else:
            return

        self._edit_dm(uid, call.message.message_id, "✅ Confirmaste. Esperando al otro jugador…")
        session.touch()

        if session.confirmed_a and session.confirmed_b:
            self._execute_trade(session)

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 7 — Ejecución del swap
    # ─────────────────────────────────────────────────────────────────────────

    def _execute_trade(self, session: _TradeSession) -> None:
        """
        Intercambia los userID en POKEMON_USUARIO.
        El objeto viaja automáticamente con el Pokémon (misma fila).
        Tras el swap se chequea evolución por intercambio en ambos Pokémon.
        """
        if session.pokemon_a is None or session.pokemon_b is None:
            self._cancel_session(session.session_id, "❌ Faltan datos de Pokémon en la sesión.")
            return
        p_a = pokemon_service.obtener_pokemon(session.pokemon_a)
        p_b = pokemon_service.obtener_pokemon(session.pokemon_b)

        if not p_a or not p_b:
            self._cancel_session(session.session_id, "❌ Error al obtener los Pokémon.")
            return

        try:
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET userID = ? WHERE id_unico = ?",
                (session.target_id, session.pokemon_a),
            )
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET userID = ? WHERE id_unico = ?",
                (session.initiator_id, session.pokemon_b),
            )
        except Exception as exc:
            logger.error(f"[TRADE] Error en swap BD: {exc}", exc_info=True)
            self._cancel_session(
                session.session_id, "❌ Error de base de datos. Trade cancelado."
            )
            return

        logger.info(
            f"[TRADE] ✅ uid={session.initiator_id} ↔ uid={session.target_id}  |  "
            f"poke#{session.pokemon_a} ↔ poke#{session.pokemon_b}"
        )

        # ── Evoluciones por intercambio ───────────────────────────────────────
        evo_lineas: list[str] = []
        for poke_id in (session.pokemon_a, session.pokemon_b):
            if poke_id is None:
                continue
            try:
                puede, evo_data = evolucion_service.verificar_evolucion_por_intercambio(poke_id)
                if puede and evo_data:
                    ok, msg_evo, _ = evolucion_service.evolucionar_pokemon(
                        poke_id, forzar=True, evo_data_override=evo_data
                    )
                    if ok and msg_evo:
                        evo_lineas.append(msg_evo)
            except Exception as exc:
                logger.warning(f"[TRADE] Evolución poke#{poke_id}: {exc}")

        evo_extra = ("\n\n" + "\n".join(evo_lineas)) if evo_lineas else ""

        # ── Notificar resultado ───────────────────────────────────────────────
        nombre_a = self._display_name(p_a)
        nombre_b = self._display_name(p_b)
        obj_a    = f"  🎒 {p_a.objeto}" if p_a.objeto else ""
        obj_b    = f"  🎒 {p_b.objeto}" if p_b.objeto else ""

        self._dm(
            session.initiator_id,
            f"🎉 <b>¡Trade completado!</b>\n\n"
            f"📤 Entregaste: <b>{nombre_a}</b>\n"
            f"📥 Recibiste: <b>{nombre_b}</b>{obj_b}"
            f"{evo_extra}",
        )
        if session.target_id is not None:
            self._dm(
                session.target_id,
                f"🎉 <b>¡Trade completado!</b>\n\n"
                f"📤 Entregaste: <b>{nombre_b}</b>\n"
                f"📥 Recibiste: <b>{nombre_a}</b>{obj_a}"
                f"{evo_extra}",
            )

        # ── Limpiar sesión ────────────────────────────────────────────────────
        self._sessions.pop(session.session_id, None)
        self._by_user.pop(session.initiator_id, None)
        if session.target_id is not None:
            self._by_user.pop(session.target_id, None)

    # ─────────────────────────────────────────────────────────────────────────
    # Cancelación genérica
    # ─────────────────────────────────────────────────────────────────────────

    def _cancel_session(
        self,
        session_id: str,
        message: str,
        notify_initiator: bool = True,
        notify_target: bool    = True,
    ) -> None:
        session = self._sessions.pop(session_id, None)
        if not session:
            return
        self._by_user.pop(session.initiator_id, None)
        if session.target_id:
            self._by_user.pop(session.target_id, None)
        if notify_initiator:
            self._dm(session.initiator_id, message)
        if notify_target and session.target_id:
            self._dm(session.target_id, message)

    # ─────────────────────────────────────────────────────────────────────────
    # Dispatch de callbacks
    # ─────────────────────────────────────────────────────────────────────────

    def handle_callback(self, call: types.CallbackQuery) -> None:
        if not call.data or not call.from_user:
            return
        partes = call.data.split(":")
        accion = partes[0]
        uid    = call.from_user.id

        try:
            owner_id = int(partes[1])
        except (IndexError, ValueError):
            return

        if uid != owner_id:
            self._answer(call, "🚫 Este botón no es tuyo.", alert=True)
            return

        try:
            if accion == "pktrade_sela":
                # pktrade_sela:{uid}:{session_id}:{pokemon_id}
                self._handle_sela(call, uid, partes[2], int(partes[3]))

            elif accion == "pktrade_acc":
                # pktrade_acc:{uid}:{session_id}
                self._handle_acc(call, uid, partes[2])

            elif accion == "pktrade_rej":
                # pktrade_rej:{uid}:{session_id}
                self._handle_rej(call, uid, partes[2])

            elif accion == "pktrade_selb":
                # pktrade_selb:{uid}:{session_id}:{pokemon_id}
                self._handle_selb(call, uid, partes[2], int(partes[3]))

            elif accion == "pktrade_conf":
                # pktrade_conf:{uid}:{session_id}:{yes|no}
                self._handle_conf(call, uid, partes[2], partes[3])

            elif accion == "pktrade_cancel":
                # pktrade_cancel:{uid}:{session_id}
                self._answer(call)
                session_id = partes[2] if len(partes) > 2 else ""
                if session_id:
                    self._cancel_session(session_id, "❌ Trade cancelado.")
                else:
                    self._by_user.pop(uid, None)
                    self._edit_dm(uid, call.message.message_id, "❌ Trade cancelado.")

        except Exception as exc:
            logger.error(
                f"[TRADE] handle_callback ({call.data}): {exc}", exc_info=True
            )
            self._answer(call, "❌ Error inesperado.", alert=True)


# ─────────────────────────────────────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────────────────────────────────────

def setup(bot: telebot.TeleBot) -> None:
    TradeHandler(bot)
    logger.info("✅ TradeHandler registrado (/trade).")
