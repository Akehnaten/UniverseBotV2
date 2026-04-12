# -*- coding: utf-8 -*-
"""
handlers/pitu_handler.py
Actualizado para google-genai v1.x
"""

import random
import logging
from google import genai  # Importación para el nuevo SDK
from google.genai import types # Necesario para las configuraciones
from config import (
    GEMINI_API_KEY,
    BOT_USERNAME,
    PITU_PROBABILIDAD_RANDOM,
    PITU_PALABRAS_CLAVE,
    PITU_SYSTEM_INSTRUCTION,
)
from utils.thread_utils import get_thread_id

logger = logging.getLogger(__name__)

# ── Inicialización de Gemini (NUEVO SDK) ───────────────────────────────────────
# En el nuevo SDK no hay "configure", se usa una instancia de Client
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_ID = "gemini-2.0-flash-lite"

# Historial de chat por chat_id → sesión de Gemini con memoria
_chat_sessions: dict = {}

def _get_session(chat_id: int):
    """Devuelve (o crea) la sesión de chat de Gemini usando client.chats.create."""
    if chat_id not in _chat_sessions:
        # En el nuevo SDK, system_instruction se pasa aquí dentro del config
        _chat_sessions[chat_id] = client.chats.create(
            model=MODEL_ID,
            config=types.GenerateContentConfig(
                system_instruction=PITU_SYSTEM_INSTRUCTION
            )
        )
        logger.info(f"[PITU] Nueva sesión (SDK v1.x) para chat_id={chat_id}")
    return _chat_sessions[chat_id]


def _pedir_respuesta(chat_id: int, prompt: str) -> str:
    """Manda el prompt a Gemini y devuelve el texto de respuesta."""
    try:
        session = _get_session(chat_id)
        # El método sigue siendo send_message pero el retorno es un objeto simplificado
        response = session.send_message(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"[PITU] Error Gemini: {e}")
        return "Che, me trabé un momento. Probá de nuevo, boludo 😅"


# ── Helpers de detección (Sin cambios) ────────────────────────────────────────

def _menciona_a_pitu(message) -> bool:
    texto = (message.text or message.caption or "").lower()
    return (
        "pitu" in texto
        or "pitufo" in texto
        or "enrique" in texto
        or f"@{BOT_USERNAME.lower()}" in texto
    )

def _es_reply_a_pitu(message) -> bool:
    return (
        message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
        and (message.reply_to_message.from_user.username or "").lower()
        == BOT_USERNAME.lower()
    )

def _tiene_palabra_clave_random(message) -> bool:
    texto = (message.text or message.caption or "").lower()
    tiene_kw = any(kw in texto for kw in PITU_PALABRAS_CLAVE)
    return tiene_kw and random.random() < PITU_PROBABILIDAD_RANDOM

def _deberia_responder_pitu(message) -> bool:
    try:
        if _es_reply_a_pitu(message):
            return True
        if message.text is None and message.caption is None:
            return False
        return _menciona_a_pitu(message) or _tiene_palabra_clave_random(message)
    except Exception as e:
        logger.debug(f"[PITU] Error en predicado _deberia_responder_pitu: {e}")
        return False


# ── Setup principal ────────────────────────────────────────────────────────────

def setup_pitu_handler(bot) -> None:
    @bot.message_handler(
        content_types=["text", "photo", "video", "document", "sticker", "audio", "voice"],
        func=_deberia_responder_pitu,
    )
    def pitu_responder(message):
        chat_id   = message.chat.id
        thread_id = get_thread_id(message)
        user_name = message.from_user.first_name or "alguien"

        texto = message.text or message.caption or "[sin texto]"
        prompt = f"{user_name} dice: {texto}"
        logger.info(f"[PITU] chat={chat_id} | {prompt[:80]}")

        respuesta = _pedir_respuesta(chat_id, prompt)

        try:
            bot.reply_to(message, respuesta)
        except Exception as e:
            logger.warning(f"[PITU] reply_to falló: {e}. Usando fallback.")
            try:
                bot.send_message(chat_id, respuesta, message_thread_id=thread_id)
            except Exception as e2:
                logger.error(f"[PITU] send_message también falló: {e2}")

    @bot.message_handler(commands=["resetpitu"])
    def pitu_reset(message):
        chat_id = message.chat.id
        if chat_id in _chat_sessions:
            del _chat_sessions[chat_id]
            logger.info(f"[PITU] Historial reseteado para chat_id={chat_id}")
        bot.reply_to(message, "Borrón y cuenta nueva, che. ¿De qué estábamos hablando? 🤷")

    logger.info("[OK] Pitu handler registrado con SDK v1.x")
