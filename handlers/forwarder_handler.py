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
  El handler SOLO actúa si el mensaje proviene del canal configurado
  en CANAL_ID (config.py). Si el bot se agrega a otro grupo, las
  reglas NO se aplican allí.

Implementación:
  Se usa copy_message() en lugar de forward_message() para que el
  mensaje llegue limpio, sin el encabezado "Reenviado de …".
══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
from typing import Optional

import telebot
from telebot import types
from utils.thread_utils import get_thread_id

from config import CANAL_ID

logger = logging.getLogger(__name__)

# ─── Destino ──────────────────────────────────────────────────────────────────
DEST_CANAL_ID: int = -1003952202112

# ─── Reglas: {thread_origen: destino_fijo | None}
#     None significa que el destino depende del tipo de contenido.
# ─────────────────────────────────────────────────────────────────────────────
_REGLAS: dict[int, int | None] = {
    521: None,   # depende del tipo → video=4, resto=2
    515: 64,     # siempre thread 64
}

# Threads de destino para el thread 521 según tipo de contenido
_THREAD_521_VIDEO = 4
_THREAD_521_RESTO = 2


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _es_video(message: types.Message) -> bool:
    """True si el mensaje es un video (incluyendo video_note)."""
    return message.video is not None or message.video_note is not None


def _resolver_thread_destino(thread_origen: int, message: types.Message) -> Optional[int]:
    """
    Devuelve el thread de destino para el mensaje dado.
    Retorna None si el thread origen no tiene regla configurada.
    """
    if thread_origen not in _REGLAS:
        return None

    destino_fijo = _REGLAS[thread_origen]

    if destino_fijo is not None:
        return destino_fijo

    # Thread 521: depende del contenido
    return _THREAD_521_VIDEO if _es_video(message) else _THREAD_521_RESTO


# ─── Handler principal ────────────────────────────────────────────────────────

class ForwarderHandler:
    """
    Escucha todos los mensajes del CANAL_ID y reenvía los de los
    threads configurados al canal destino.
    """

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        self._register()

    def _register(self) -> None:
        # content_types=['any'] captura texto, fotos, videos, documentos,
        # audio, stickers, etc., sin necesidad de listar cada uno.
        self.bot.register_message_handler(
            self._on_message,
            content_types=["text", "photo", "video", "video_note", "animation",
                            "audio", "voice", "document", "sticker", "poll",
                            "location", "venue", "contact"],
            func=self._debe_procesar,
        )
        logger.info(
            "[FORWARDER] Registrado — canal origen: %s | threads: %s → dest: %s",
            CANAL_ID, list(_REGLAS.keys()), DEST_CANAL_ID,
        )

    # ── Filtro ────────────────────────────────────────────────────────────────

    def _debe_procesar(self, message: types.Message) -> bool:
        """
        Devuelve True solo si:
          1. El mensaje viene del CANAL_ID configurado.
          2. El thread_id está entre los monitoreados.
        """
        if message.chat.id != CANAL_ID:
            return False  # bot en otro grupo → ignorar

        tid = get_thread_id(message)
        return tid in _REGLAS

    # ── Acción ────────────────────────────────────────────────────────────────

    def _on_message(self, message: types.Message) -> None:
        tid = get_thread_id(message)
        thread_destino = _resolver_thread_destino(tid, message)

        if thread_destino is None:
            return  # por seguridad, nunca debería ocurrir dado el filtro

        tipo = "video" if _es_video(message) else message.content_type
        logger.info(
            "[FORWARDER] thread %s (%s) → %s thread %s | msg_id=%s",
            tid, tipo, DEST_CANAL_ID, thread_destino, message.message_id,
        )

        try:
            self.bot.copy_message(
                chat_id             = DEST_CANAL_ID,
                from_chat_id        = message.chat.id,
                message_id          = message.message_id,
                message_thread_id   = thread_destino,
            )
        except Exception as exc:
            logger.error(
                "[FORWARDER] Error al copiar msg_id=%s → %s thread %s: %s",
                message.message_id, DEST_CANAL_ID, thread_destino, exc,
            )


# ─── Setup ────────────────────────────────────────────────────────────────────

def setup(bot: telebot.TeleBot) -> None:
    ForwarderHandler(bot)
    logger.info("✅ ForwarderHandler registrado.")
