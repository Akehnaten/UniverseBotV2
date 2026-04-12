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
from database import db_manager

logger = logging.getLogger(__name__)

# ── Inicialización de Groq ─────────────────────────────────────────────────────
client = Groq(api_key=GROQ_API_KEY)
MODEL_ID = "llama-3.3-70b-versatile"

# Historial de conversación por chat_id
_chat_histories: dict[int, list] = {}
MAX_HISTORY = 8

# Cooldown por usuario
_ultimo_uso: dict[int, float] = {}
COOLDOWN_SEGUNDOS = 30


# ── Funciones de miembros (BD) ─────────────────────────────────────────────────

def _get_history(chat_id: int) -> list:
    if chat_id not in _chat_histories:
        _chat_histories[chat_id] = []
    return _chat_histories[chat_id]


def _get_todos_los_miembros() -> list:
    """Devuelve todos los miembros registrados en JUAN_MIEMBROS."""
    try:
        return db_manager.execute_query(
            "SELECT user_id, nombre, username, descripcion FROM JUAN_MIEMBROS"
        ) or []
    except Exception as e:
        logger.warning(f"[JUAN] Error listando JUAN_MIEMBROS: {e}")
        return []


def _construir_contexto_miembros() -> str:
    """
    Arma el bloque de texto con los miembros conocidos.
    Se inyecta en el prompt SOLO cuando el mensaje menciona a alguien,
    así no se gastan tokens en cada llamada.
    """
    miembros = _get_todos_los_miembros()
    if not miembros:
        return ""
    lineas = ["Miembros del grupo que conocés:"]
    for m in miembros:
        linea = f"- {m['nombre']}"
        if m.get("username"):
            linea += f" (@{m['username']})"
        if m.get("descripcion"):
            linea += f": {m['descripcion']}"
        lineas.append(linea)
    return "\n".join(lineas)


def _mensaje_menciona_miembro(texto: str) -> bool:
    """Detecta si el mensaje nombra a algún miembro registrado."""
    try:
        miembros = _get_todos_los_miembros()
        texto_lower = texto.lower()
        for m in miembros:
            if m["nombre"].lower() in texto_lower:
                return True
            if m.get("username") and m["username"].lower() in texto_lower:
                return True
    except Exception:
        pass
    return False


# ── Lógica de respuesta ────────────────────────────────────────────────────────

def _pedir_respuesta(chat_id: int, prompt: str, inyectar_miembros: bool = False) -> str:
    """Manda el prompt a Groq y devuelve el texto de respuesta."""
    history = _get_history(chat_id)

    history.append({"role": "user", "content": prompt})

    if len(history) > MAX_HISTORY:
        _chat_histories[chat_id] = history[-MAX_HISTORY:]
        history = _chat_histories[chat_id]

    # System prompt base + contexto de miembros solo si hace falta
    system = JUAN_SYSTEM_INSTRUCTION
    if inyectar_miembros:
        ctx = _construir_contexto_miembros()
        if ctx:
            system = f"{system}\n\n{ctx}"

    max_intentos = 3
    espera = 15

    for intento in range(max_intentos):
        try:
            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": system},
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
        user_id   = message.from_user.id
        user_name = message.from_user.first_name or "alguien"

        # Cooldown por usuario
        ahora = time.time()
        ultimo = _ultimo_uso.get(user_id, 0)
        if ahora - ultimo < COOLDOWN_SEGUNDOS:
            restante = int(COOLDOWN_SEGUNDOS - (ahora - ultimo))
            logger.info(f"[JUAN] Cooldown activo para user={user_id}, faltan {restante}s")
            return
        _ultimo_uso[user_id] = ahora

        texto = message.text or message.caption or "[sin texto]"
        prompt = f"{user_name} dice: {texto}"
        logger.info(f"[JUAN] chat={chat_id} | {prompt[:80]}")

        # Inyectar contexto de miembros solo si el mensaje nombra a alguien → ahorra tokens
        inyectar = _mensaje_menciona_miembro(texto)
        respuesta = _pedir_respuesta(chat_id, prompt, inyectar_miembros=inyectar)

        try:
            bot.reply_to(message, respuesta)
        except Exception as e:
            logger.warning(f"[JUAN] reply_to falló: {e}")
            try:
                bot.send_message(chat_id, respuesta, message_thread_id=thread_id)
            except Exception as e2:
                logger.error(f"[JUAN] send_message también falló: {e2}")

    # ── /resetjuan — borrar historial ─────────────────────────────────────────
    @bot.message_handler(commands=["resetjuan"])
    def juan_reset(message):
        chat_id = message.chat.id
        if chat_id in _chat_histories:
            del _chat_histories[chat_id]
            logger.info(f"[JUAN] Historial reseteado para chat_id={chat_id}")
        bot.reply_to(message, "Borrón y cuenta nueva 🐴 ¿De qué estábamos hablando?")

    # ── /juanagregar — registrar miembro (solo admins) ────────────────────────
    @bot.message_handler(commands=["juanagregar"])
    def juan_agregar(message):
        """
        Respondé al mensaje del usuario y ejecutá:
        /juanagregar Nombre | descripción opcional
        Ejemplo: /juanagregar Santi | hincha de River, le gusta el anime
        """
        chat_id = message.chat.id
        try:
            member = bot.get_chat_member(chat_id, message.from_user.id)
            if member.status not in ("administrator", "creator"):
                bot.reply_to(message, "❌ Solo los admins pueden registrar miembros.")
                return

            if not message.reply_to_message:
                bot.reply_to(message, "❌ Respondé al mensaje del usuario y luego:\n/juanagregar Nombre | descripción")
                return

            target   = message.reply_to_message.from_user
            user_id  = target.id
            username = target.username or ""

            partes = message.text.split(maxsplit=1)
            if len(partes) < 2:
                # Sin args: usar el nombre de Telegram como nombre
                nombre_part = target.first_name
                descripcion = ""
            elif "|" in partes[1]:
                nombre_part, descripcion = [x.strip() for x in partes[1].split("|", 1)]
            else:
                nombre_part = partes[1].strip()
                descripcion = ""

            db_manager.execute_update(
                """INSERT INTO JUAN_MIEMBROS (user_id, nombre, username, descripcion)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       nombre=excluded.nombre,
                       username=excluded.username,
                       descripcion=excluded.descripcion""",
                (user_id, nombre_part, username, descripcion),
            )
            logger.info(f"[JUAN] Miembro registrado: {nombre_part} ({user_id})")
            bot.reply_to(message, f"✅ Juan ya conoce a *{nombre_part}* 🐴", parse_mode="Markdown")

        except Exception as e:
            logger.error(f"[JUAN] Error en /juanagregar: {e}")
            bot.reply_to(message, f"❌ Error al registrar: {e}")

    # ── /juanolvidar — eliminar miembro (solo admins) ─────────────────────────
    @bot.message_handler(commands=["juanolvidar"])
    def juan_olvidar(message):
        """Respondé al mensaje del usuario y ejecutá /juanolvidar"""
        chat_id = message.chat.id
        try:
            member = bot.get_chat_member(chat_id, message.from_user.id)
            if member.status not in ("administrator", "creator"):
                bot.reply_to(message, "❌ Solo los admins pueden hacer esto.")
                return

            if not message.reply_to_message:
                bot.reply_to(message, "❌ Respondé al mensaje del usuario que querés que Juan olvide.")
                return

            user_id = message.reply_to_message.from_user.id
            nombre  = message.reply_to_message.from_user.first_name
            db_manager.execute_update(
                "DELETE FROM JUAN_MIEMBROS WHERE user_id = ?", (user_id,)
            )
            logger.info(f"[JUAN] Miembro eliminado: {user_id}")
            bot.reply_to(message, f"🗑️ Juan ya no recuerda a *{nombre}*.", parse_mode="Markdown")

        except Exception as e:
            logger.error(f"[JUAN] Error en /juanolvidar: {e}")
            bot.reply_to(message, f"❌ Error: {e}")

    # ── /juanmiembros — listar quién conoce Juan ──────────────────────────────
    @bot.message_handler(commands=["juanmiembros"])
    def juan_listar(message):
        miembros = _get_todos_los_miembros()
        if not miembros:
            bot.reply_to(message, "Juan no conoce a nadie todavía 🐴\nUsá /juanagregar para enseñarle.")
            return
        lineas = ["🐴 *Miembros que Juan conoce:*\n"]
        for m in miembros:
            linea = f"• *{m['nombre']}*"
            if m.get("username"):
                linea += f" (@{m['username']})"
            if m.get("descripcion"):
                linea += f" — {m['descripcion']}"
            lineas.append(linea)
        bot.reply_to(message, "\n".join(lineas), parse_mode="Markdown")

    logger.info("[OK] Juan handler registrado con Groq")