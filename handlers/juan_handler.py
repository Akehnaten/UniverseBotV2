# -*- coding: utf-8 -*-
"""
handlers/juan_handler.py
Juan, el caballo de los memes. Usando Groq (gratuito).
"""

import random
import logging
import time
from groq import Groq
from config import (
    GROQ_API_KEY,
    BOT_USERNAME,
    JUAN_PROBABILIDAD_RANDOM,
    JUAN_PALABRAS_CLAVE,
    JUAN_SYSTEM_INSTRUCTION,
)
from utils.thread_utils import get_thread_id

logger = logging.getLogger(__name__)

# ── Inicialización de Groq ─────────────────────────────────────────────────────
client = Groq(api_key=GROQ_API_KEY)
MODEL_ID = "llama-3.3-70b-versatile"

# Historial de conversación por chat_id (Groq es stateless, lo manejamos nosotros)
_chat_histories: dict[int, list] = {}
MAX_HISTORY = 20  # Mensajes a recordar por chat


def _get_history(chat_id: int) -> list:
    if chat_id not in _chat_histories:
        _chat_histories[chat_id] = []
    return _chat_histories[chat_id]


def _pedir_respuesta(chat_id: int, prompt: str) -> str:
    """Manda el prompt a Groq y devuelve el texto de respuesta."""
    history = _get_history(chat_id)

    history.append({"role": "user", "content": prompt})

    if len(history) > MAX_HISTORY:
        _chat_histories[chat_id] = history[-MAX_HISTORY:]
        history = _chat_histories[chat_id]

    max_intentos = 3
    espera = 15

    for intento in range(max_intentos):
        try:
            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": JUAN_SYSTEM_INSTRUCTION},
                    *history,
                ],
                max_tokens=300,
                temperature=0.85,
            )
            respuesta = response.choices[0].message.content.strip()
            history.append({"role": "assistant", "content": respuesta})
            return respuesta

        except Exception as e:
            error_str = str(e)
            logger.error(f"[JUAN] Error Groq (intento {intento + 1}/{max_intentos}): {e}")

            if "429" in error_str and intento < max_intentos - 1:
                logger.warning(f"[JUAN] Rate limit Groq, esperando {espera}s...")
                time.sleep(espera)
                espera *= 2
                continue

            break

    if history and history[-1]["role"] == "user":
        history.pop()

    return "Neeeeigh... me trabé. Probá de nuevo 🐴"


# ── Helpers de detección ───────────────────────────────────────────────────────

def _menciona_a_juan(message) -> bool:
    texto = (message.text or message.caption or "").lower()
    if any(kw in texto for kw in ["juan", "juancito", "el caballo"]):
        return True
    entities = message.entities or message.caption_entities or []
    for entity in entities:
        if entity.type == "mention":
            mention_text = (message.text or message.caption or "")[
                entity.offset: entity.offset + entity.length
            ].lower()
            if mention_text == f"@{BOT_USERNAME.lower()}":
                return True
    return False


def _es_reply_a_juan(message) -> bool:
    return (
        message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
        and (message.reply_to_message.from_user.username or "").lower()
        == BOT_USERNAME.lower()
    )


def _tiene_palabra_clave_random(message) -> bool:
    texto = (message.text or message.caption or "").lower()
    tiene_kw = any(kw in texto for kw in JUAN_PALABRAS_CLAVE)
    return tiene_kw and random.random() < JUAN_PROBABILIDAD_RANDOM


def _deberia_responder_juan(message) -> bool:
    try:
        if _es_reply_a_juan(message):
            return True
        if message.text is None and message.caption is None:
            return False
        return _menciona_a_juan(message) or _tiene_palabra_clave_random(message)
    except Exception as e:
        logger.debug(f"[JUAN] Error en predicado: {e}")
        return False


# ── Setup principal ────────────────────────────────────────────────────────────

def setup_juan_handler(bot) -> None:
    @bot.message_handler(
        content_types=["text", "photo", "video", "document", "sticker", "audio", "voice"],
        func=_deberia_responder_juan,
    )
    def juan_responder(message):
        chat_id   = message.chat.id
        thread_id = get_thread_id(message)
        user_name = message.from_user.first_name or "alguien"

        texto = message.text or message.caption or "[sin texto]"
        prompt = f"{user_name} dice: {texto}"
        logger.info(f"[JUAN] chat={chat_id} | {prompt[:80]}")

        respuesta = _pedir_respuesta(chat_id, prompt)

        try:
            bot.reply_to(message, respuesta)
        except Exception as e:
            logger.warning(f"[JUAN] reply_to falló: {e}")
            try:
                bot.send_message(chat_id, respuesta, message_thread_id=thread_id)
            except Exception as e2:
                logger.error(f"[JUAN] send_message también falló: {e2}")

    @bot.message_handler(commands=["resetjuan"])
    def juan_reset(message):
        chat_id = message.chat.id
        if chat_id in _chat_histories:
            del _chat_histories[chat_id]
            logger.info(f"[JUAN] Historial reseteado para chat_id={chat_id}")
        bot.reply_to(message, "Borrón y cuenta nueva 🐴 ¿De qué estábamos hablando?")

    logger.info("[OK] Juan handler registrado con Groq")
