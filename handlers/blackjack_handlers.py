# -*- coding: utf-8 -*-
"""
handlers/blackjack_handlers.py
════════════════════════════════════════════════════════════════════════════════
Handler de Blackjack para UniverseBot V2.0

Comandos (solo en hilo CASINO):
  /blackjack [apuesta | allin]  — Inicia una partida nueva

Callbacks (inline keyboards):
  bj_hit:{user_id}    — Pedir carta
  bj_stand:{user_id}  — Plantarse
  bj_double:{user_id} — Doblar apuesta

Flujo:
  1. Usuario escribe /blackjack 500
  2. Bot descuenta 500 cosmos y envía panel con cartas + botones
  3. Usuario interactúa con botones hasta que la partida termina
  4. Bot acredita/descuenta cosmos y cierra la partida
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

import telebot
from telebot import types

from config import CASINO, MSG_USUARIO_NO_REGISTRADO
from database import db_manager
from funciones import economy_service, user_service
from funciones.blackjack_service import (
    APUESTA_MAXIMA_BJ,
    APUESTA_MINIMA_BJ,
    EstadoBJ,
    PartidaBJ,
    blackjack_service,
)

logger = logging.getLogger(__name__)

# ─── Emojis de estado ─────────────────────────────────────────────────────────

_EMOJI_ESTADO = {
    EstadoBJ.GANADO:    "🏆 ¡GANASTE!",
    EstadoBJ.PERDIDO:   "💀 ¡PERDISTE!",
    EstadoBJ.EMPATE:    "🤝 EMPATE",
    EstadoBJ.BLACKJACK: "🃏✨ ¡BLACKJACK!",
}


class BlackjackHandlers:
    """Handler completo de Blackjack. Una instancia por proceso."""

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        self._register_handlers()

    # ── Registro ──────────────────────────────────────────────────────────────

    def _register_handlers(self) -> None:
        self.bot.register_message_handler(
            self.cmd_blackjack, commands=["blackjack"]
        )
        self.bot.register_callback_query_handler(
            self.cb_blackjack,
            func=lambda c: c.data.startswith("bj_"),
        )

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _del(self, chat_id: int, msg_id: int) -> None:
        try:
            self.bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

    def _del_after(self, chat_id: int, msg_id: int, delay: float = 6.0) -> None:
        threading.Timer(delay, lambda: self._del(chat_id, msg_id)).start()

    def _err(self, chat_id: int, texto: str, tid: Optional[int] = None, delay: float = 6.0) -> None:
        m = self.bot.send_message(chat_id, texto, message_thread_id=tid, parse_mode="HTML")
        self._del_after(chat_id, m.message_id, delay)

    def _solo_casino(self, message: telebot.types.Message) -> bool:
        if message.message_thread_id == CASINO:
            return True
        self._del(message.chat.id, message.message_id)
        self._err(
            message.chat.id,
            "🃏 El Blackjack solo se puede jugar en el canal de Casino.",
            message.message_thread_id,
        )
        return False

    # ── Construcción del panel ────────────────────────────────────────────────

    def _build_panel(self, partida: PartidaBJ, nombre: str) -> str:
        """Genera el texto HTML del panel de la partida."""
        cartas_j = partida.render_mano(partida.mano_jugador)
        cartas_c = partida.render_mano(partida.mano_crupier)
        pts_j    = partida.puntos_jugador
        pts_c    = partida.puntos_crupier_visible

        encabezado = "🃏 <b>BLACKJACK — Universe Casino</b>\n\n"

        texto = (
            f"{encabezado}"
            f"👤 <b>{nombre}</b>\n"
            f"🂠 Tu mano:       <code>{cartas_j}</code>  [{pts_j}]\n"
            f"🏦 Crupier:       <code>{cartas_c}</code>  [{pts_c}]\n\n"
            f"💰 Apuesta: <b>{partida.apuesta_efectiva:,} ✨</b>"
        )

        if partida.doble:
            texto += "  <i>(Doble)</i>"

        if partida.estado != EstadoBJ.EN_CURSO:
            pts_c_real = partida.puntos_crupier_total
            titulo = _EMOJI_ESTADO.get(partida.estado, "")
            texto += (
                f"\n\n{titulo}\n"
                f"🏦 Crupier final: [{pts_c_real}]"
            )

        return texto

    def _build_markup(self, partida: PartidaBJ) -> Optional[types.InlineKeyboardMarkup]:
        """Botones de acción. None si la partida ya terminó."""
        if partida.estado != EstadoBJ.EN_CURSO:
            return None

        uid = partida.user_id
        kb  = types.InlineKeyboardMarkup(row_width=3)
        puede_doblar = len(partida.mano_jugador) == 2

        botones = [
            types.InlineKeyboardButton("🃏 Pedir",    callback_data=f"bj_hit:{uid}"),
            types.InlineKeyboardButton("✋ Plantarse", callback_data=f"bj_stand:{uid}"),
        ]
        if puede_doblar:
            botones.append(
                types.InlineKeyboardButton("⬆️ Doblar", callback_data=f"bj_double:{uid}")
            )
        kb.add(*botones)
        return kb

    # ── /blackjack ────────────────────────────────────────────────────────────

    def cmd_blackjack(self, message: telebot.types.Message) -> None:
        """
        /blackjack [apuesta | allin]

        Inicia una nueva partida de Blackjack en el hilo CASINO.
        """
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        if not self._solo_casino(message):
            return
        self._del(cid, message.message_id)

        # ── Validar registro ──────────────────────────────────────────────────
        user_info = user_service.get_user_info(uid)
        if not user_info:
            self._err(cid, MSG_USUARIO_NO_REGISTRADO, tid)
            return

        nombre = user_info.get("nombre", "Usuario")

        # ── Partida en curso ──────────────────────────────────────────────────
        if blackjack_service.get_partida(uid):
            self._err(cid, f"⚠️ {nombre}, ya tenés una partida activa.", tid)
            return

        # ── Parsear apuesta ───────────────────────────────────────────────────
        parts = (message.text or "").split()
        saldo = economy_service.get_balance(uid)

        try:
            if len(parts) < 2:
                self._err(
                    cid,
                    (
                        "🃏 <b>Blackjack</b>\n\n"
                        "Uso: <code>/blackjack [cantidad]</code> o <code>/blackjack allin</code>\n"
                        f"Mínimo: <b>{APUESTA_MINIMA_BJ:,} ✨</b>  |  "
                        f"Máximo: <b>{APUESTA_MAXIMA_BJ:,} ✨</b>"
                    ),
                    tid,
                    delay=10,
                )
                return

            apuesta = saldo if parts[1].lower() == "allin" else int(parts[1])

        except ValueError:
            self._err(cid, "❌ La apuesta debe ser un número válido.", tid)
            return

        # ── Validar rango de apuesta ──────────────────────────────────────────
        if apuesta < APUESTA_MINIMA_BJ:
            self._err(cid, f"❌ Apuesta mínima: <b>{APUESTA_MINIMA_BJ:,} ✨</b>", tid)
            return
        if apuesta > APUESTA_MAXIMA_BJ:
            self._err(cid, f"❌ Apuesta máxima: <b>{APUESTA_MAXIMA_BJ:,} ✨</b>", tid)
            return
        if saldo < apuesta:
            self._err(cid, f"❌ {nombre}, no tenés suficientes cosmos. Saldo: <b>{saldo:,} ✨</b>", tid)
            return

        # ── Descontar apuesta ─────────────────────────────────────────────────
        if not economy_service.subtract_credits(uid, apuesta, "blackjack_apuesta"):
            self._err(cid, "❌ Error al descontar la apuesta.", tid)
            return

        # ── Iniciar partida ───────────────────────────────────────────────────
        partida, error = blackjack_service.nueva_partida(uid, apuesta, cid)
        if error or not partida:
            economy_service.add_credits(uid, apuesta, "blackjack_reembolso")
            self._err(cid, f"❌ Error al iniciar la partida: {error}", tid)
            return

        # ── Enviar panel ──────────────────────────────────────────────────────
        texto  = self._build_panel(partida, nombre)
        markup = self._build_markup(partida)

        msg = self.bot.send_message(
            cid, texto,
            parse_mode="HTML",
            message_thread_id=tid,
            reply_markup=markup,
        )
        partida.message_id = msg.message_id

        # Si fue BJ natural, liquidar de inmediato
        if partida.estado == EstadoBJ.BLACKJACK:
            self._liquidar(partida, nombre, cid, tid)

    # ── Callbacks inline ──────────────────────────────────────────────────────

    def cb_blackjack(self, call: types.CallbackQuery) -> None:
        """Maneja bj_hit, bj_stand, bj_double."""
        try:
            accion, target_str = call.data.split(":", 1)
            target_id = int(target_str)
        except (ValueError, IndexError):
            self.bot.answer_callback_query(call.id, "❌ Datos inválidos.")
            return

        uid = call.from_user.id

        # Solo el dueño de la partida puede interactuar
        if uid != target_id:
            self.bot.answer_callback_query(call.id, "⛔ Esta no es tu partida.", show_alert=True)
            return

        partida = blackjack_service.get_partida(uid)
        if not partida:
            self.bot.answer_callback_query(call.id, "❌ No tenés partida activa.")
            try:
                self.bot.edit_message_reply_markup(
                    call.message.chat.id, call.message.message_id, reply_markup=None
                )
            except Exception:
                pass
            return

        # Partida existe pero ya terminó (ej: doble callback por tap rápido).
        # Liquidar si aún no se hizo (cerrar_partida es idempotente: retorna
        # False si ya no estaba en el dict, así sabemos si debemos pagar).
        if partida.estado != EstadoBJ.EN_CURSO:
            self.bot.answer_callback_query(call.id, "La partida ya terminó.")
            user_info = user_service.get_user_info(uid)
            nombre    = user_info.get("nombre", "Usuario") if user_info else "Usuario"
            cid       = call.message.chat.id
            tid       = getattr(call.message, "message_thread_id", None)
            # Solo liquidar si la partida todavía está registrada (evita doble pago)
            if blackjack_service.get_partida(uid):
                self._liquidar(partida, nombre, cid, tid)
            return

        # ── Obtener nombre ────────────────────────────────────────────────────
        user_info = user_service.get_user_info(uid)
        nombre    = user_info.get("nombre", "Usuario") if user_info else "Usuario"
        cid       = call.message.chat.id
        tid       = getattr(call.message, "message_thread_id", None)

        # ── Ejecutar acción ───────────────────────────────────────────────────
        error = ""
        match accion:
            case "bj_hit":
                partida, error = blackjack_service.pedir(uid)
                self.bot.answer_callback_query(call.id, "🃏 Carta pedida")
            case "bj_stand":
                partida, error = blackjack_service.plantarse(uid)
                self.bot.answer_callback_query(call.id, "✋ Te plantaste")
            case "bj_double":
                saldo_actual = economy_service.get_balance(uid)
                if saldo_actual < partida.apuesta:
                    self.bot.answer_callback_query(
                        call.id, "❌ No tenés cosmos suficientes para doblar.", show_alert=True
                    )
                    return
                # Descontar la apuesta extra antes de doblar
                economy_service.subtract_credits(uid, partida.apuesta, "blackjack_doble")
                partida, error = blackjack_service.doblar(uid)
                self.bot.answer_callback_query(call.id, "⬆️ ¡Doblaste!")
            case _:
                self.bot.answer_callback_query(call.id, "Acción desconocida.")
                return

        if error or not partida:
            self.bot.answer_callback_query(call.id, error or "Error interno.", show_alert=True)
            # Si el service devolvió None, la partida quedó en un estado
            # desconocido. Cerrarla y reembolsar para no dejar al usuario bloqueado.
            if not partida:
                partida_huerfana = blackjack_service.get_partida(uid)
                if partida_huerfana:
                    economy_service.add_credits(
                        uid, partida_huerfana.apuesta_efectiva, "blackjack_reembolso_error"
                    )
                    blackjack_service.cerrar_partida(uid)
                    logger.warning("[BJ] Partida huérfana cerrada y reembolsada | uid=%s", uid)
            return

        # ── Actualizar panel ──────────────────────────────────────────────────
        texto  = self._build_panel(partida, nombre)
        markup = self._build_markup(partida)

        try:
            self.bot.edit_message_text(
                texto,
                chat_id=cid,
                message_id=call.message.message_id,
                parse_mode="HTML",
                reply_markup=markup,
            )
        except Exception as exc:
            logger.warning("[BJ] No se pudo editar el panel: %s", exc)

        # ── Liquidar si la partida terminó ────────────────────────────────────
        if partida.estado != EstadoBJ.EN_CURSO:
            self._liquidar(partida, nombre, cid, tid)

    # ── Liquidación ───────────────────────────────────────────────────────────

    def _liquidar(
        self,
        partida: PartidaBJ,
        nombre: str,
        cid: int,
        tid: Optional[int],
    ) -> None:
        """Aplica el pago, envía resumen y cierra la partida."""
        uid   = partida.user_id
        pago  = blackjack_service.calcular_pago(partida)

        if pago > 0:
            economy_service.add_credits(uid, pago + partida.apuesta_efectiva, "blackjack_ganancia")
        elif pago == 0:
            # Empate: devolver apuesta
            economy_service.add_credits(uid, partida.apuesta_efectiva, "blackjack_empate")
        # pago < 0: ya se descontó al inicio (y al doblar si aplica)

        balance = economy_service.get_balance(uid)

        iconos = {
            EstadoBJ.BLACKJACK: "🃏✨",
            EstadoBJ.GANADO:    "🏆",
            EstadoBJ.EMPATE:    "🤝",
            EstadoBJ.PERDIDO:   "💀",
        }
        icono = iconos.get(partida.estado, "🃏")

        if pago > 0:
            resultado_str = f"<b>+{pago:,} ✨</b>"
        elif pago == 0:
            resultado_str = f"<b>Apuesta devuelta: {partida.apuesta_efectiva:,} ✨</b>"
        else:
            resultado_str = f"<b>-{abs(pago):,} ✨</b>"

        resumen = (
            f"{icono} <b>{nombre}</b>\n"
            f"Resultado: {resultado_str}\n"
            f"💳 Nuevo saldo: <b>{balance:,} ✨</b>"
        )

        m = self.bot.send_message(cid, resumen, parse_mode="HTML", message_thread_id=tid)
        threading.Timer(15.0, lambda: self._del(cid, m.message_id)).start()

        blackjack_service.cerrar_partida(uid)
        logger.info(
            "[BJ] Partida cerrada | uid=%s | estado=%s | pago=%s",
            uid, partida.estado.name, pago,
        )
