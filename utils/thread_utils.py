# -*- coding: utf-8 -*-
"""
utils/thread_utils.py
═══════════════════════════════════════════════════════════════════════════════
Utilidad compartida para extraer el topic ID real en supergrupos con Topics.

Importar en cualquier handler con:
    from utils.thread_utils import get_thread_id
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_thread_id(message) -> Optional[int]:
    """
    Extrae el topic ID real de un mensaje en un supergrupo con Topics (foro).

    En grupos donde los Topics siempre estuvieron activos, pyTelegramBotAPI
    puede devolver message_thread_id como None en ciertos updates, porque
    Telegram codifica internamente los topics como replies al mensaje de
    apertura del topic. El ID real queda en reply_to_message.message_id.

    Estrategia (en orden):
        1. message.message_thread_id  → si existe y es > 0, retornarlo.
        2. Fallback: reply_to_message.message_id cuando is_topic_message=True.

    Returns:
        int  → ID del topic al que pertenece el mensaje.
        None → el mensaje no pertenece a ningún topic (chat privado, etc).
    """
    # ── 1. Campo directo ──────────────────────────────────────────────────────
    raw = getattr(message, "message_thread_id", None)
    if raw is not None:
        try:
            tid = int(raw)
            if tid > 0:
                return tid
        except (TypeError, ValueError):
            logger.warning(
                "[THREAD_ID] Valor inesperado '%r' en message_thread_id "
                "(msg_id=%s) — intentando fallback.",
                raw, getattr(message, "message_id", "?"),
            )

    # ── 2. Fallback: reply_to_message cuando is_topic_message=True ───────────
    if getattr(message, "is_topic_message", False):
        reply = getattr(message, "reply_to_message", None)
        if reply is not None:
            try:
                tid = int(reply.message_id)
                if tid > 0:
                    logger.debug(
                        "[THREAD_ID] Fallback: topic_id=%s desde "
                        "reply_to_message.message_id (msg_id=%s)",
                        tid, getattr(message, "message_id", "?"),
                    )
                    return tid
            except (TypeError, ValueError):
                pass

    return None