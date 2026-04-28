# -*- coding: utf-8 -*-
"""
handlers/forwarder_handler.py
══════════════════════════════════════════════════════════════════════════════
Reenvío automático de contenido entre threads del grupo.

Reglas configuradas:
  · Thread 521 → canal DEST_CANAL_ID
        video  → thread 4
        resto  → thread 2
  · Thread 515 → canal DEST_CANAL_ID, thread 64

Restricción de seguridad:
  SOLO actúa si message.chat.id == CANAL_ID (config.py).
  Si el bot se agrega a otro grupo, las reglas NO se aplican allí.
  Esta verificación ocurre DENTRO del callback (no en func=) para
  garantizar que funcione en todas las versiones de pyTelegramBotAPI.
══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
from typing import Optional

import telebot
from telebot import types

from config import CANAL_ID

logger = logging.getLogger(__name__)

# ─── Destino ──────────────────────────────────────────────────────────────────
DEST_CANAL_ID: int = -1003952202112

# ─── Threads origen monitoreados ─────────────────────────────────────────────
#   Valor: int  → thread destino fijo
#   Valor: None → depende del tipo de contenido (ver _resolver_destino)
_REGLAS: dict[int, Optional[int]] = {
    521: None,  # video→4, resto→2
    515: 64,
}

_THREAD_521_VIDEO = 4
_THREAD_521_RESTO = 2


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_thread(message: types.Message) -> Optional[int]:
    """
    Extrae el topic ID del mensaje.
    Intenta message_thread_id primero; si falla usa el fallback de
    reply_to_message (grupos con topics siempre activos).
    """
    # Intento 1: campo directo
    raw = getattr(message, "message_thread_id", None)
    if raw is not None:
        try:
            tid = int(raw)
            if tid > 0:
                return tid
        except (TypeError, ValueError):
            pass

    # Intento 2: fallback via reply_to_message cuando is_topic_message=True
    if getattr(message, "is_topic_message", False):
        reply = getattr(message, "reply_to_message", None)
        if reply is not None:
            try:
                tid = int(reply.message_id)
                if tid > 0:
                    return tid
            except (TypeError, ValueError):
                pass

    return None


def _es_video(message: types.Message) -> bool:
    return message.video is not None or message.video_note is not None


def _resolver_destino(thread_origen: int, message: types.Message) -> Optional[int]:
    if thread_origen not in _REGLAS:
        return None
    destino_fijo = _REGLAS[thread_origen]
    if destino_fijo is not None:
        return destino_fijo
    # Thread 521: depende del contenido
    return _THREAD_521_VIDEO if _es_video(message) else _THREAD_521_RESTO


# ─── Handler ─────────────────────────────────────────────────────────────────

class ForwarderHandler:

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        self._register()

    def _register(self) -> None:
        # NO se usa func= para evitar el bug de pyTelegramBotAPI donde
        # func= combinado con content_types= es ignorado en algunas versiones.
        # Toda la lógica de filtrado va DENTRO del callback.
        self.bot.register_message_handler(
            self._on_message,
            content_types=[
                "text", "photo", "video", "video_note", "animation",
                "audio", "voice", "document", "sticker",
            ],
        )
        logger.info(
            "[FORWARDER] Registrado | origen: CANAL_ID=%s threads=%s → dest=%s",
            CANAL_ID, list(_REGLAS.keys()), DEST_CANAL_ID,
        )

    def _on_message(self, message: types.Message) -> None:
        # ── Guard 1: solo el canal configurado ───────────────────────────────
        if message.chat.id != CANAL_ID:
            return

        # ── Guard 2: solo threads monitoreados ───────────────────────────────
        tid = _get_thread(message)

        logger.debug(
            "[FORWARDER] mensaje recibido | chat=%s thread=%s content=%s msg_id=%s",
            message.chat.id, tid, message.content_type, message.message_id,
        )

        if tid is None or tid not in _REGLAS:
            return

        # ── Resolver thread destino ───────────────────────────────────────────
        thread_destino = _resolver_destino(tid, message)
        if thread_destino is None:
            return

        tipo_log = "video" if _es_video(message) else message.content_type
        logger.info(
            "[FORWARDER] copiando | thread_origen=%s tipo=%s → dest=%s thread=%s msg_id=%s",
            tid, tipo_log, DEST_CANAL_ID, thread_destino, message.message_id,
        )

        try:
            self.bot.copy_message(
                chat_id           = DEST_CANAL_ID,
                from_chat_id      = message.chat.id,
                message_id        = message.message_id,
                message_thread_id = thread_destino,
            )
            logger.info(
                "[FORWARDER] ✅ copiado msg_id=%s → %s thread %s",
                message.message_id, DEST_CANAL_ID, thread_destino,
            )
        except Exception as exc:
            logger.error(
                "[FORWARDER] ❌ error al copiar msg_id=%s → %s thread %s: %s",
                message.message_id, DEST_CANAL_ID, thread_destino, exc,
            )


# ─── Setup ───────────────────────────────────────────────────────────────────

def setup(bot: telebot.TeleBot) -> None:
    ForwarderHandler(bot)
    logger.info("✅ ForwarderHandler registrado.")
