# -*- coding: utf-8 -*-
"""
handlers/ahorcado_handlers.py
════════════════════════════════════════════════════════════════════════════════
Handler del Ahorcado para UniverseBot V2.0

Comandos (cualquier hilo del grupo):
  /ahorcado [palabra]     — Inicia una partida (sin palabra = aleatoria K-pop)
  /letra X               — Propone la letra X para la partida activa del hilo
  /cancelar_ahorcado     — Cancela la partida activa (solo iniciador o admin)

Diseño:
  - Una sola partida activa por thread_id
  - El bot mantiene un único mensaje de panel que se EDITA en cada jugada
    (así el historial del chat no se llena de mensajes)
  - /letra X es el único punto de entrada de letras, evitando que cualquier
    mensaje del chat sea interpretado como jugada
  - Al ganar: todos los que aportaron letras correctas reciben cosmos
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

import telebot
from telebot import types

from config import MSG_USUARIO_NO_REGISTRADO
from database import db_manager
from funciones import economy_service, user_service
from funciones.ahorcado_service import (
    MAX_ERRORES,
    RECOMPENSA_BASE,
    PartidaAhorcado,
    ahorcado_service,
)

logger = logging.getLogger(__name__)


class AhorcadoHandlers:
    """Handler del Ahorcado. Una instancia por proceso."""

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.bot.register_message_handler(self.cmd_ahorcado,         commands=["ahorcado"])
        self.bot.register_message_handler(self.cmd_letra,            commands=["letra"])
        self.bot.register_message_handler(self.cmd_cancelar_ahorcado, commands=["cancelar_ahorcado"])

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _del(self, cid: int, mid: int) -> None:
        try:
            self.bot.delete_message(cid, mid)
        except Exception:
            pass

    def _del_after(self, cid: int, mid: int, delay: float = 8.0) -> None:
        threading.Timer(delay, lambda: self._del(cid, mid)).start()

    def _err(self, cid: int, txt: str, tid: Optional[int] = None, delay: float = 8.0) -> None:
        m = self.bot.send_message(cid, txt, parse_mode="HTML", message_thread_id=tid)
        self._del_after(cid, m.message_id, delay)

    def _actualizar_panel(self, cid: int, partida: PartidaAhorcado) -> None:
        """Edita el mensaje del panel con el estado actual."""
        if not partida.message_id:
            return
        try:
            self.bot.edit_message_text(
                partida.render_panel(),
                chat_id=cid,
                message_id=partida.message_id,
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.warning("[AHORCADO] No se pudo editar el panel: %s", exc)

    def _is_admin(self, cid: int, uid: int) -> bool:
        try:
            return self.bot.get_chat_member(cid, uid).status in ("creator", "administrator")
        except Exception:
            return False

    # ── /ahorcado ─────────────────────────────────────────────────────────────

    def cmd_ahorcado(self, message: telebot.types.Message) -> None:
        """
        /ahorcado [palabra]

        Inicia una partida. Si se pasa una palabra, esa se usa; si no, se elige
        una aleatoria del banco K-pop. La palabra NO se muestra en el chat
        (la borra el bot de inmediato si se pasó en el comando).
        """
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        if message.chat.type not in ("group", "supergroup"):
            return

        self._del(cid, message.message_id)   # borrar siempre para ocultar la palabra si fue escrita

        if not db_manager.user_exists(uid):
            self._err(cid, MSG_USUARIO_NO_REGISTRADO, tid)
            return

        user_info = user_service.get_user_info(uid)
        nombre    = user_info.get("nombre", "Usuario") if user_info else "Usuario"

        # Extraer palabra si fue pasada como argumento
        parts  = (message.text or "").split(maxsplit=1)
        palabra = parts[1].strip() if len(parts) > 1 else None

        # Validar que la palabra tenga solo letras y espacios
        if palabra and not all(c.isalpha() or c.isspace() for c in palabra):
            self._err(cid, "❌ La palabra solo puede contener letras y espacios.", tid)
            return

        partida, error = ahorcado_service.nueva_partida(
            thread_id=tid or cid,
            iniciador_id=uid,
            iniciador_nombre=nombre,
            palabra=palabra,
        )

        if error or not partida:
            self._err(cid, f"⚠️ {error}", tid)
            return

        msg = self.bot.send_message(
            cid,
            partida.render_panel(),
            parse_mode="HTML",
            message_thread_id=tid,
        )
        partida.message_id = msg.message_id
        logger.info(
            "[AHORCADO] Nueva partida | thread=%s | palabra=%s | iniciador=%s",
            tid or cid, partida.palabra, nombre,
        )

    # ── /letra ────────────────────────────────────────────────────────────────

    def cmd_letra(self, message: telebot.types.Message) -> None:
        """
        /letra X

        Propone la letra X para la partida activa del hilo.
        Es el único canal oficial de entrada de letras.
        """
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        if message.chat.type not in ("group", "supergroup"):
            return

        self._del(cid, message.message_id)

        if not db_manager.user_exists(uid):
            self._err(cid, MSG_USUARIO_NO_REGISTRADO, tid)
            return

        user_info = user_service.get_user_info(uid)
        nombre    = user_info.get("nombre", "Usuario") if user_info else "Usuario"

        parts = (message.text or "").split()
        if len(parts) < 2:
            self._err(cid, "❌ Uso: <code>/letra [letra]</code>  ej: <code>/letra A</code>", tid)
            return

        letra_propuesta = parts[1]

        partida, feedback, es_correcta = ahorcado_service.proponer_letra(
            thread_id=tid or cid,
            user_id=uid,
            nombre=nombre,
            letra=letra_propuesta,
        )

        if not partida:
            self._err(cid, feedback, tid)
            return

        # Enviar feedback breve que se autodestruye
        m_feedback = self.bot.send_message(
            cid, feedback, parse_mode="HTML", message_thread_id=tid
        )
        self._del_after(cid, m_feedback.message_id, delay=5.0)

        # Actualizar panel principal
        self._actualizar_panel(cid, partida)

        # ── Verificar fin de partida ──────────────────────────────────────────
        if partida.ganada:
            self._resolver_victoria(partida, cid, tid)
        elif partida.perdida:
            self._resolver_derrota(partida, cid, tid)

    # ── /cancelar_ahorcado ────────────────────────────────────────────────────

    def cmd_cancelar_ahorcado(self, message: telebot.types.Message) -> None:
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        self._del(cid, message.message_id)

        partida = ahorcado_service.get_partida(tid or cid)
        if not partida:
            self._err(cid, "❌ No hay partida activa en este canal.", tid)
            return

        # Solo el iniciador o un admin puede cancelar
        if uid != partida.iniciador_id and not self._is_admin(cid, uid):
            self._err(cid, "⛔ Solo el iniciador o un admin puede cancelar la partida.", tid)
            return

        ahorcado_service.cancelar_partida(tid or cid)

        texto = (
            f"🚫 Partida cancelada.\n"
            f"🔤 La palabra era: <b>{partida.palabra}</b>"
        )
        m = self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
        self._del_after(cid, m.message_id, 15.0)

    # ── Resolución ────────────────────────────────────────────────────────────

    def _resolver_victoria(self, partida: PartidaAhorcado, cid: int, tid: Optional[int]) -> None:
        """Distribuye recompensas y anuncia la victoria."""
        ahorcado_service.cerrar_partida(tid or cid)

        lineas_premios = []
        for user_id, letras_ok in partida.participantes.items():
            premio = RECOMPENSA_BASE * letras_ok
            economy_service.add_credits(user_id, premio, "ahorcado_victoria")
            nombre_g = user_service.get_user_info(user_id)
            nombre_g = nombre_g.get("nombre", str(user_id)) if nombre_g else str(user_id)
            lineas_premios.append(f"  🏅 {nombre_g}: <b>+{premio:,} ✨</b> ({letras_ok} letra/s acertadas)")

        texto = (
            f"🎉 <b>¡GANARON! La palabra era:</b>\n\n"
            f"🔤 <code>{partida.palabra}</code>\n\n"
        )
        if lineas_premios:
            texto += "<b>Recompensas:</b>\n" + "\n".join(lineas_premios)
        else:
            texto += "<i>Nadie acertó letras esta vez.</i>"

        self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
        logger.info("[AHORCADO] Victoria | thread=%s | palabra=%s", tid or cid, partida.palabra)

    def _resolver_derrota(self, partida: PartidaAhorcado, cid: int, tid: Optional[int]) -> None:
        """Anuncia la derrota y revela la palabra."""
        ahorcado_service.cerrar_partida(tid or cid)

        texto = (
            f"💀 <b>¡PERDIERON! El muñeco fue ahorcado.</b>\n\n"
            f"<code>{partida.render_frame()}</code>\n\n"
            f"🔤 La palabra era: <b>{partida.palabra}</b>\n\n"
            f"<i>Mejor suerte la próxima vez. Usen /ahorcado para volver a intentarlo.</i>"
        )
        self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
        logger.info("[AHORCADO] Derrota | thread=%s | palabra=%s", tid or cid, partida.palabra)
