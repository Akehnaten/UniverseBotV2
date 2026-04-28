# -*- coding: utf-8 -*-
"""
handlers/forwarder_handler.py
══════════════════════════════════════════════════════════════════════════════
Reenvío automático entre threads, con soporte completo de media groups
(álbumes de fotos/videos enviados en paquete).

Reglas:
  · Thread 521 → DEST_CANAL_ID  (video → thread 4 | resto → thread 2)
  · Thread 515 → DEST_CANAL_ID  thread 64

Restricción: SOLO actúa si message.chat.id == CANAL_ID.
══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import telebot
from telebot import types

from config import CANAL_ID

logger = logging.getLogger(__name__)

# ─── Destino ──────────────────────────────────────────────────────────────────
DEST_CANAL_ID: int = -1003952202112

_REGLAS: dict[int, Optional[int]] = {
    521: None,   # None = depende del tipo: video→4, resto→2
    515: 64,
}
_THREAD_521_VIDEO = 4
_THREAD_521_RESTO = 2

# Tiempo de espera para acumular todos los mensajes de un álbum (segundos)
_BUFFER_DELAY = 1.5


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_thread(message: types.Message) -> Optional[int]:
    raw = getattr(message, "message_thread_id", None)
    if raw is not None:
        try:
            tid = int(raw)
            if tid > 0:
                return tid
        except (TypeError, ValueError):
            pass
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
    fijo = _REGLAS[thread_origen]
    if fijo is not None:
        return fijo
    return _THREAD_521_VIDEO if _es_video(message) else _THREAD_521_RESTO


# ─── Handler ─────────────────────────────────────────────────────────────────

class ForwarderHandler:
    """
    Escucha mensajes en CANAL_ID y los reenvía según las reglas configuradas.
    Acumula mensajes de un mismo álbum (media_group_id) antes de enviarlos
    juntos con send_media_group.
    """

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        # Buffer de álbumes: {media_group_id: {"msgs": [], "timer": Timer, "thread_destino": int}}
        self._mg_buffer: dict = {}
        self._mg_lock = threading.Lock()
        self._register()

    def _register(self) -> None:
        self.bot.register_message_handler(
            self._on_message,
            content_types=[
                "text", "photo", "video", "video_note", "animation",
                "audio", "voice", "document", "sticker",
            ],
        )
        logger.info(
            "[FORWARDER] Registrado | CANAL_ID=%s threads=%s → dest=%s",
            CANAL_ID, list(_REGLAS.keys()), DEST_CANAL_ID,
        )

    # ── Entrada principal ─────────────────────────────────────────────────────

    def _on_message(self, message: types.Message) -> None:
        # Guard 1: solo el canal configurado
        if message.chat.id != CANAL_ID:
            return

        # Guard 2: solo threads monitoreados
        tid = _get_thread(message)
        if tid is None or tid not in _REGLAS:
            return

        thread_destino = _resolver_destino(tid, message)
        if thread_destino is None:
            return

        logger.info(
            "[FORWARDER] msg_id=%s | thread=%s | tipo=%s | media_group=%s → thread_dest=%s",
            message.message_id, tid, message.content_type,
            getattr(message, "media_group_id", None), thread_destino,
        )

        # ── Álbum (múltiples fotos/videos en paquete) ─────────────────────────
        mg_id = getattr(message, "media_group_id", None)
        if mg_id:
            self._buffer_album(mg_id, message, thread_destino)
            return

        # ── Mensaje individual ────────────────────────────────────────────────
        self._copy_single(message, thread_destino)

    # ── Álbumes ───────────────────────────────────────────────────────────────

    def _buffer_album(self, mg_id: str, message: types.Message, thread_destino: int) -> None:
        """Acumula mensajes del álbum y programa el envío diferido."""
        with self._mg_lock:
            if mg_id not in self._mg_buffer:
                self._mg_buffer[mg_id] = {
                    "msgs": [],
                    "timer": None,
                    "thread_destino": thread_destino,
                }
            entry = self._mg_buffer[mg_id]
            entry["msgs"].append(message)

            # Reiniciar el timer con cada mensaje nuevo del álbum
            if entry["timer"]:
                entry["timer"].cancel()

            timer = threading.Timer(_BUFFER_DELAY, self._flush_album, args=(mg_id,))
            entry["timer"] = timer
            timer.start()

    def _flush_album(self, mg_id: str) -> None:
        """Envía todos los mensajes del álbum como send_media_group."""
        with self._mg_lock:
            entry = self._mg_buffer.pop(mg_id, None)

        if not entry or not entry["msgs"]:
            return

        thread_destino = entry["thread_destino"]
        # Ordenar por message_id para respetar el orden original
        msgs = sorted(entry["msgs"], key=lambda m: m.message_id)

        media_list = []
        for i, msg in enumerate(msgs):
            # La caption solo va en el primer elemento del álbum
            caption          = msg.caption if i == 0 else None
            caption_entities = msg.caption_entities if i == 0 else None

            if msg.photo:
                media_list.append(types.InputMediaPhoto(
                    msg.photo[-1].file_id,
                    caption=caption,
                    caption_entities=caption_entities,
                    parse_mode="HTML" if caption else None,
                ))
            elif msg.video:
                media_list.append(types.InputMediaVideo(
                    msg.video.file_id,
                    caption=caption,
                    caption_entities=caption_entities,
                    parse_mode="HTML" if caption else None,
                ))
            elif msg.document:
                media_list.append(types.InputMediaDocument(
                    msg.document.file_id,
                    caption=caption,
                    caption_entities=caption_entities,
                    parse_mode="HTML" if caption else None,
                ))
            elif msg.audio:
                media_list.append(types.InputMediaAudio(
                    msg.audio.file_id,
                    caption=caption,
                    caption_entities=caption_entities,
                    parse_mode="HTML" if caption else None,
                ))

        if not media_list:
            logger.warning("[FORWARDER] Álbum %s vacío después de procesar.", mg_id)
            return

        logger.info(
            "[FORWARDER] Enviando álbum %s (%d items) → dest=%s thread=%s",
            mg_id, len(media_list), DEST_CANAL_ID, thread_destino,
        )

        try:
            self.bot.send_media_group(
                chat_id           = DEST_CANAL_ID,
                media             = media_list,
                message_thread_id = thread_destino,
            )
            logger.info("[FORWARDER] ✅ Álbum %s enviado.", mg_id)
        except Exception as exc:
            logger.error("[FORWARDER] ❌ Error enviando álbum %s: %s", mg_id, exc)

    # ── Mensaje individual ────────────────────────────────────────────────────

    def _copy_single(self, message: types.Message, thread_destino: int) -> None:
        try:
            self.bot.copy_message(
                chat_id           = DEST_CANAL_ID,
                from_chat_id      = message.chat.id,
                message_id        = message.message_id,
                message_thread_id = thread_destino,
            )
            logger.info(
                "[FORWARDER] ✅ msg_id=%s → dest=%s thread=%s",
                message.message_id, DEST_CANAL_ID, thread_destino,
            )
        except Exception as exc:
            logger.error(
                "[FORWARDER] ❌ Error copiando msg_id=%s → thread %s: %s",
                message.message_id, thread_destino, exc,
            )


# ─── Setup ───────────────────────────────────────────────────────────────────

def setup(bot: telebot.TeleBot) -> None:
    ForwarderHandler(bot)
    logger.info("✅ ForwarderHandler registrado.")
