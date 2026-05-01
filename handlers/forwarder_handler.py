# handlers/forwarder_handler.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
import threading
from typing import Optional

import telebot
from telebot import types
from config import CANAL_ID

logger = logging.getLogger(__name__)

DEST_CANAL_ID: int = -1003952202112

_REGLAS: dict[int, Optional[int]] = {
    521: None,
    515: 64,
}
_THREAD_521_VIDEO = 4
_THREAD_521_RESTO = 2
_BUFFER_DELAY     = 1.5

# Buffer de álbumes compartido a nivel de módulo (no de instancia)
_mg_buffer: dict = {}
_mg_lock = threading.Lock()


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
    return (
        message.video is not None
        or message.video_note is not None
        or message.animation is not None
    )


def _resolver_destino(thread_origen: int, message: types.Message) -> Optional[int]:
    if thread_origen not in _REGLAS:
        return None
    fijo = _REGLAS[thread_origen]
    if fijo is not None:
        return fijo
    return _THREAD_521_VIDEO if _es_video(message) else _THREAD_521_RESTO


def _copy_single(bot: telebot.TeleBot, message: types.Message, thread_destino: int) -> None:
    try:
        bot.copy_message(
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
            "[FORWARDER] ❌ Error copiando msg_id=%s: %s",
            message.message_id, exc,
        )


def _flush_album(bot: telebot.TeleBot, mg_id: str) -> None:
    with _mg_lock:
        entry = _mg_buffer.pop(mg_id, None)
    if not entry or not entry["msgs"]:
        return

    thread_destino = entry["thread_destino"]
    msgs = sorted(entry["msgs"], key=lambda m: m.message_id)

    media_list = []
    for i, msg in enumerate(msgs):
        caption          = msg.caption if i == 0 else None
        caption_entities = msg.caption_entities if i == 0 else None
        pm               = "HTML" if caption else None

        if msg.photo:
            media_list.append(types.InputMediaPhoto(
                msg.photo[-1].file_id, caption=caption,
                caption_entities=caption_entities, parse_mode=pm,
            ))
        elif msg.video:
            media_list.append(types.InputMediaVideo(
                msg.video.file_id, caption=caption,
                caption_entities=caption_entities, parse_mode=pm,
            ))
        elif msg.document:
            media_list.append(types.InputMediaDocument(
                msg.document.file_id, caption=caption,
                caption_entities=caption_entities, parse_mode=pm,
            ))
        elif msg.audio:
            media_list.append(types.InputMediaAudio(
                msg.audio.file_id, caption=caption,
                caption_entities=caption_entities, parse_mode=pm,
            ))

    if not media_list:
        return

    try:
        bot.send_media_group(
            chat_id           = DEST_CANAL_ID,
            media             = media_list,
            message_thread_id = thread_destino,
        )
        logger.info("[FORWARDER] ✅ Álbum %s enviado (%d items).", mg_id, len(media_list))
    except Exception as exc:
        logger.error("[FORWARDER] ❌ Error enviando álbum %s: %s", mg_id, exc)


def _buffer_album(bot: telebot.TeleBot, mg_id: str, message: types.Message, thread_destino: int) -> None:
    with _mg_lock:
        if mg_id not in _mg_buffer:
            _mg_buffer[mg_id] = {"msgs": [], "timer": None, "thread_destino": thread_destino}
        entry = _mg_buffer[mg_id]
        entry["msgs"].append(message)
        if entry["timer"]:
            entry["timer"].cancel()
        timer = threading.Timer(_BUFFER_DELAY, _flush_album, args=(bot, mg_id))
        entry["timer"] = timer
        timer.start()


def forward_if_needed(message: types.Message, bot: telebot.TeleBot) -> None:
    """
    Punto de entrada llamado desde el middleware.
    Evalúa si el mensaje debe reenviarse y actúa en consecuencia.
    No registra ningún handler — es una función pura.
    """
    # Ignorar comandos
    if message.text and message.text.startswith("/"):
        return

    if message.chat.id != CANAL_ID:
        return

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

    mg_id = getattr(message, "media_group_id", None)
    if mg_id:
        _buffer_album(bot, mg_id, message, thread_destino)
    else:
        _copy_single(bot, message, thread_destino)


def setup(bot: telebot.TeleBot) -> None:
    """
    Mantenido por compatibilidad con __init__.py.
    Ya no registra ningún handler — la lógica vive en el middleware.
    """
    logger.info("✅ ForwarderHandler listo (modo middleware, sin handler registrado).")
