# -*- coding: utf-8 -*-
"""
handlers/pitu_handler.py

Pitufo Enrique ("Pitu") — integrante IA del grupo, powered by Gemini 1.5 Flash.

Integración con UniverseBot V2.0:
  - Se registra via setup_pitu_handler(bot) desde handlers/__init__.py
  - Configuración centralizada en config.py (GEMINI_API_KEY, BOT_USERNAME, etc.)
  - No toca la DB: Pitu es un tipo del grupo, no un sistema de puntos.
"""

import random
import logging
import google.generativeai as genai
from config import (
    GEMINI_API_KEY,
    BOT_USERNAME,
    PITU_PROBABILIDAD_RANDOM,
    PITU_PALABRAS_CLAVE,
    PITU_SYSTEM_INSTRUCTION,
)

logger = logging.getLogger(__name__)

# ── Inicialización de Gemini ───────────────────────────────────────────────────
genai.configure(api_key=GEMINI_API_KEY)

_pitu_model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=PITU_SYSTEM_INSTRUCTION,
)

# Historial de chat por chat_id → sesión de Gemini con memoria
_chat_sessions: dict = {}


def _get_session(chat_id: int):
    """Devuelve (o crea) la sesión de chat de Gemini para ese chat."""
    if chat_id not in _chat_sessions:
        _chat_sessions[chat_id] = _pitu_model.start_chat(history=[])
        logger.info(f"[PITU] Nueva sesión para chat_id={chat_id}")
    return _chat_sessions[chat_id]


def _pedir_respuesta(chat_id: int, prompt: str) -> str:
    """Manda el prompt a Gemini y devuelve el texto de respuesta."""
    try:
        session = _get_session(chat_id)
        response = session.send_message(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"[PITU] Error Gemini: {e}")
        return "Che, me trabé un momento. Probá de nuevo, boludo 😅"


# ── Helpers de detección ───────────────────────────────────────────────────────

def _menciona_a_pitu(message) -> bool:
    """True si el texto nombra a Pitu o menciona el @username del bot."""
    texto = (message.text or "").lower()
    return (
        "pitu" in texto
        or "pitufo" in texto
        or "enrique" in texto
        or f"@{BOT_USERNAME.lower()}" in texto
    )


def _es_reply_a_pitu(message) -> bool:
    """True si el mensaje es un reply a un mensaje del propio bot."""
    return (
        message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
        and (message.reply_to_message.from_user.username or "").lower()
        == BOT_USERNAME.lower()
    )


def _tiene_palabra_clave_random(message) -> bool:
    """True si el mensaje tiene una palabra clave Y el 5 % aleatorio se activa."""
    texto = (message.text or "").lower()
    tiene_kw = any(kw in texto for kw in PITU_PALABRAS_CLAVE)
    return tiene_kw and random.random() < PITU_PROBABILIDAD_RANDOM


# ── Setup principal ────────────────────────────────────────────────────────────

def setup_pitu_handler(bot) -> None:
    """
    Registra todos los handlers de Pitu en el bot.
    Llamar desde handlers/__init__.py dentro de setup_all_handlers(bot).
    """

    @bot.message_handler(
        func=lambda m: m.text is not None and (
            _menciona_a_pitu(m)
            or _es_reply_a_pitu(m)
            or _tiene_palabra_clave_random(m)
        )
    )
    def pitu_responder(message):
        chat_id   = message.chat.id
        user_name = message.from_user.first_name or "alguien"
        texto     = message.text

        # Damos contexto a Gemini: quién habla y qué dice
        prompt = f"{user_name} dice: {texto}"
        logger.info(f"[PITU] chat={chat_id} | {prompt[:80]}")

        respuesta = _pedir_respuesta(chat_id, prompt)
        bot.reply_to(message, respuesta)

    @bot.message_handler(commands=["resetpitu"])
    def pitu_reset(message):
        """Borra el historial de conversación de Pitu para ese chat."""
        chat_id = message.chat.id
        if chat_id in _chat_sessions:
            del _chat_sessions[chat_id]
            logger.info(f"[PITU] Historial reseteado para chat_id={chat_id}")
        bot.reply_to(
            message,
            "Borrón y cuenta nueva, che. ¿De qué estábamos hablando? 🤷"
        )

    logger.info("[OK] Pitu handler registrado")
