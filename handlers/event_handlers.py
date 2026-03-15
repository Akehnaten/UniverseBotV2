# -*- coding: utf-8 -*-
"""
handlers/event_handlers.py
Comandos del canal de Eventos: /verdadoreto, /participando, /salir
Todos restringidos al thread EVENTOS.
"""

import threading
import logging
from typing import Optional
from utils.thread_utils import get_thread_id
import telebot

from config import EVENTOS, CANAL_ID, MSG_USUARIO_NO_REGISTRADO
from funciones import user_service

logger = logging.getLogger(__name__)


class EventHandlers:
    """
    Handlers para el sistema de Verdad o Reto y el canal de Eventos.

    Estado en memoria:
        _lista: list[dict]  — participantes actuales del juego activo.
            Cada entrada: {"uid": int, "nombre": str}
    """

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        self._lista: list[dict] = []          # participantes verdadoreto
        self._register_handlers()

    # ─────────────────────────────────────────────────────────────────────────
    # Registro de handlers
    # ─────────────────────────────────────────────────────────────────────────

    def _register_handlers(self) -> None:
        self.bot.register_message_handler(self.cmd_verdadoreto,  commands=["verdadoreto"])
        self.bot.register_message_handler(self.cmd_participando, commands=["participando"])
        self.bot.register_message_handler(self.cmd_salir_evento, commands=["salir"])

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers privados
    # ─────────────────────────────────────────────────────────────────────────

    def _borrar_seguro(self, chat_id: int, message_id: int) -> None:
        """Elimina un mensaje ignorando errores."""
        try:
            self.bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    def _temp(
        self,
        chat_id: int,
        texto: str,
        tid: Optional[int],
        delay: float = 7.0,
        parse_mode: str = "HTML",
    ) -> None:
        """Envía un mensaje y lo borra automáticamente tras `delay` segundos."""
        try:
            m = self.bot.send_message(
                chat_id, texto,
                parse_mode=parse_mode,
                message_thread_id=tid,
            )
            threading.Timer(
                delay,
                lambda: self._borrar_seguro(chat_id, m.message_id),
            ).start()
        except Exception as e:
            logger.error(f"[EVENTOS] Error enviando mensaje temporal: {e}")

    def _verificar_canal_eventos(self, message: telebot.types.Message) -> bool:
        """
        Devuelve True solo si el mensaje proviene del thread EVENTOS.
        Si no, borra el comando y envía aviso temporal.
        """
        if message.message_thread_id == EVENTOS:
            return True

        cid = message.chat.id
        tid = message.message_thread_id

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        self._temp(
            cid,
            "❌ Este comando solo puede usarse en el canal de eventos.",
            tid,
        )
        return False

    def _nombre_display(self, message: telebot.types.Message, user_info: dict) -> str:
        """Devuelve mención HTML del usuario."""
        username = message.from_user.username
        if username:
            return f"@{username}"
        nombre = user_info.get("nombre") or message.from_user.first_name
        uid    = message.from_user.id
        return f'<a href="tg://user?id={uid}">{nombre}</a>'

    # ─────────────────────────────────────────────────────────────────────────
    # /verdadoreto
    # ─────────────────────────────────────────────────────────────────────────

    def cmd_verdadoreto(self, message: telebot.types.Message) -> None:
        """
        /verdadoreto — Te une a la lista del juego activo.
        Si la lista estaba vacía, anuncia el inicio de un juego nuevo en el canal.
        """
        if not self._verificar_canal_eventos(message):
            return

        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        user_info = user_service.get_user_info(uid)
        if not user_info:
            self._temp(cid, MSG_USUARIO_NO_REGISTRADO, tid)
            return

        # Verificar si ya está en la lista
        if any(p["uid"] == uid for p in self._lista):
            self._temp(
                cid,
                "⚠️ Ya estás participando en el juego actual.\n"
                "Usa /salir para abandonar.",
                tid,
            )
            return

        nombre     = user_info.get("nombre") or message.from_user.first_name
        mencion    = self._nombre_display(message, user_info)
        lista_vacia = len(self._lista) == 0

        self._lista.append({"uid": uid, "nombre": nombre, "mencion": mencion})
        logger.info(f"[VoR] {nombre} ({uid}) se unió. Total: {len(self._lista)}")

        if lista_vacia:
            # Anunciar nuevo juego
            texto = (
                "🎲 <b>¡Nuevo juego de Verdad o Reto!</b>\n\n"
                f"👤 {mencion} ha iniciado la partida.\n\n"
                "¿Quieres participar? Usa <code>/verdadoreto</code>"
            )
            self.bot.send_message(
                cid, texto,
                parse_mode="HTML",
                message_thread_id=tid,
            )
        else:
            texto = (
                f"✅ {mencion} se unió al juego.\n"
                f"👥 Participantes: <b>{len(self._lista)}</b>"
            )
            self._temp(cid, texto, tid, delay=10.0)

    # ─────────────────────────────────────────────────────────────────────────
    # /participando
    # ─────────────────────────────────────────────────────────────────────────

    def cmd_participando(self, message: telebot.types.Message) -> None:
        """
        /participando — Muestra cuántas personas y quiénes están en la lista.
        """
        if not self._verificar_canal_eventos(message):
            return

        cid = message.chat.id
        tid = message.message_thread_id

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        if not self._lista:
            self._temp(
                cid,
                "📋 No hay ningún juego activo.\n"
                "Usa <code>/verdadoreto</code> para iniciar uno.",
                tid,
            )
            return

        lineas = "\n".join(
            f"  {i + 1}. {p['mencion']}"
            for i, p in enumerate(self._lista)
        )
        texto = (
            f"🎲 <b>Verdad o Reto — Participantes</b>\n\n"
            f"👥 Total: <b>{len(self._lista)}</b>\n\n"
            f"{lineas}"
        )
        try:
            m = self.bot.send_message(
                cid, texto,
                parse_mode="HTML",
                message_thread_id=tid,
            )
            threading.Timer(
                20.0,
                lambda: self._borrar_seguro(cid, m.message_id),
            ).start()
        except Exception as e:
            logger.error(f"[EVENTOS] Error en /participando: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # /salir  (solo en EVENTOS → quita de la lista de verdadoreto)
    # ─────────────────────────────────────────────────────────────────────────

    def cmd_salir_evento(self, message: telebot.types.Message) -> None:
        """
        /salir en EVENTOS — Te quita de la lista de Verdad o Reto.
        Si el thread no es EVENTOS, ignora silenciosamente para no
        interferir con el handler de roles (/salir en ROLES).
        """
        if get_thread_id(message) != EVENTOS:
            return  # dejar que lo maneje role_handlers

        cid = message.chat.id
        tid = get_thread_id(message)
        uid = message.from_user.id

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        user_info = user_service.get_user_info(uid)
        if not user_info:
            self._temp(cid, MSG_USUARIO_NO_REGISTRADO, tid)
            return

        antes = len(self._lista)
        self._lista = [p for p in self._lista if p["uid"] != uid]

        if len(self._lista) < antes:
            nombre  = user_info.get("nombre") or message.from_user.first_name
            mencion = self._nombre_display(message, user_info)
            logger.info(f"[VoR] {nombre} ({uid}) salió. Quedan: {len(self._lista)}")
            self._temp(
                cid,
                f"👋 {mencion} salió del juego.\n"
                f"👥 Participantes restantes: <b>{len(self._lista)}</b>",
                tid,
                delay=8.0,
            )
        else:
            self._temp(
                cid,
                "⚠️ No estás en la lista del juego actual.",
                tid,
            )