# -*- coding: utf-8 -*-
"""
handlers/pitu_handler.py
Usando Groq (gratuito) en lugar de Gemini
"""

import random
import logging
import time
from groq import Groq
from config import (
    GROQ_API_KEY,
    BOT_USERNAME,
    PITU_PROBABILIDAD_RANDOM,
    PITU_PALABRAS_CLAVE,
    PITU_SYSTEM_INSTRUCTION,
)
from utils.thread_utils import get_thread_id

logger = logging.getLogger(__name__)

# ── Inicialización de Groq ─────────────────────────────────────────────────────
client = Groq(api_key=GROQ_API_KEY)
MODEL_ID = "llama-3.3-70b-versatile"  # El más capaz en tier gratuito

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

    # Agregar mensaje del usuario al historial
    history.append({"role": "user", "content": prompt})

    # Mantener historial acotado
    # FIX: antes se reasignaba a una variable local y nunca se guardaba en el dict
    if len(history) > MAX_HISTORY:
        _chat_histories[chat_id] = history[-MAX_HISTORY:]
        history = _chat_histories[chat_id]

    max_intentos = 3
    espera = 15  # segundos entre reintentos por rate-limit

    for intento in range(max_intentos):
        try:
            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": PITU_SYSTEM_INSTRUCTION},
                    *history,
                ],
                max_tokens=300,
                temperature=0.85,
            )
            respuesta = response.choices[0].message.content.strip()

            # Guardar respuesta en historial
            history.append({"role": "assistant", "content": respuesta})

            return respuesta

        except Exception as e:
            error_str = str(e)
            logger.error(f"[PITU] Error Groq (intento {intento + 1}/{max_intentos}): {e}")

            if "429" in error_str and intento < max_intentos - 1:
                logger.warning(f"[PITU] Rate limit Groq, esperando {espera}s...")
                time.sleep(espera)
                espera *= 2  # back-off exponencial
                continue

            break  # Cualquier otro error → salir del loop

    # FIX: si no se pudo responder, sacar el mensaje del usuario del historial
    # para no dejar un turno sin respuesta que rompa el formato user/assistant
    if history and history[-1]["role"] == "user":
        history.pop()

    return "Che, me trabé un momento. Probá de nuevo 😅"


# ── Helpers de detección ───────────────────────────────────────────────────────

def _menciona_a_pitu(message) -> bool:
    texto = (message.text or message.caption or "").lower()
    if any(kw in texto for kw in ["pitu", "pitufo", "enrique"]):
        return True
    # Detección por entities (forma correcta para @menciones)
    entities = message.entities or message.caption_entities or []
    for entity in entities:
        if entity.type == "mention":
            mention_text = (message.text or message.caption or "")[
                entity.offset: entity.offset + entity.length
            ].lower()
            if mention_text == f"@{BOT_USERNAME.lower()}":
                return True
    return False


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
        logger.debug(f"[PITU] Error en predicado: {e}")
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
            logger.warning(f"[PITU] reply_to falló: {e}")
            try:
                bot.send_message(chat_id, respuesta, message_thread_id=thread_id)
            except Exception as e2:
                logger.error(f"[PITU] send_message también falló: {e2}")

    @bot.message_handler(commands=["resetpitu"])
    def pitu_reset(message):
        chat_id = message.chat.id
        if chat_id in _chat_histories:
            del _chat_histories[chat_id]
            logger.info(f"[PITU] Historial reseteado para chat_id={chat_id}")
        bot.reply_to(message, "Borrón y cuenta nueva, che. ¿De qué estábamos hablando? 🤷")

    logger.info("[OK] Pitu handler registrado con Groq")
