# -*- coding: utf-8 -*-
"""
handlers/juan_handler.py
Juan, el caballo de los memes. Usando Groq (gratuito).
Incluye sistema de aprendizaje pasivo + chistes internos con atribución.

FIXES v2:
- Orden de registro corregido: aprendizaje pasivo va DESPUÉS del handler activo.
- Un único @bot.message_handler para texto que bifurca internamente,
  evitando que el listener pasivo consuma updates antes que Juan.
- Aprendizaje de stickers/fotos añadido con handler separado de baja prioridad.
- Lógica de categoría corregida: se categoriza el texto del AUTOR, no el original.
- Manejo robusto de None en respuesta Groq.
- Cooldown movido a check previo para no desperdiciar llamadas.
"""

import random
import logging
import time
import re
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

_chat_histories: dict[int, list] = {}
MAX_HISTORY = 8

_ultimo_uso: dict[int, float] = {}
COOLDOWN_SEGUNDOS = 30


# ── Patrones de categorías pasivas ────────────────────────────────────────────
# NOTA: la categoría se detecta sobre el texto QUE ESCRIBE EL USUARIO,
# no sobre el mensaje original al que responde.

_PATRONES_CATEGORIA: dict[str, list[str]] = {
    "saludo": [
        r"\bbuenos?\s*d[ií]as?\b",
        r"\bbuenas?\s*tardes?\b",
        r"\bbuenas?\s*noches?\b",
        r"\bhola+\b",
        r"\bbuenas?\b",
        r"\bey\b",
        r"\bqu[eé]\s*tal\b",
        r"\bc[oó]mo\s*(est[aá]n?|andan?|van?|les?\s*va)\b",
    ],
    "despedida": [
        r"\bchau+\b",
        r"\bcha[oó]\b",
        r"\bhasta\s*(luego|ma[nñ]ana|pronto|la\s*vista)\b",
        r"\bnos\s*vemos?\b",
        r"\bme\s*voy\b",
        r"\bme\s*retiro\b",
    ],
    "opinion": [
        r"\bqu[eé]\s*(opinan?|piensan?|dicen?)\b",
        r"\b(vieron?|escucharon?|oyeron?|leyeron?)\b",
        r"\bqu[eé]\s*les?\s*parece\b",
        r"\balguien\s*(m[aá]s|vio|sabe)\b",
    ],
    "reaccion": [
        r"\bjaja+\b",
        r"\bjeje+\b",
        r"\blol+\b",
        r"\bxd+\b",
        r"\bque\s+(gracioso|bueno|malo|zarpado|cagada)\b",
        r"\bme\s+mat[oó]\b",
        r"\bno\s+puede\s+ser\b",
    ],
}

_FRASE_MINIMA_CHARS = 4
_FRASES_IGNORAR = {
    "si", "no", "ok", "dale", "jaja", "xd", "lol", "re", "igual",
    "obvio", "claro", "nah", "meh", "gg", "👍", "👎", "❤️", "😂",
}

# Patrones para detectar que alguien le está contando algo a Juan sobre otro
_PATRONES_CHISTE_INTERNO = [
    r"\b(sab[eé]s?|sa[bv]ías?|cont[aé]|te\s*cuento|imaginate|fijate)\b",
    r"\bes\s+(un[ao]?|re|muy|bastante|demasiado)\b",
    r"\bsiempre\s+(hace|dice|llega|se)\b",
    r"\bnunca\s+(hace|dice|llega|se)\b",
    r"\bles?\s+dicen?\b",
    r"\ble\s+llaman?\b",
    r"\btodos\s+(saben?|dicen?|lo|la)\b",
]

# Excusas cuando Groq falla
_EXCUSAS = [
    "Neeeeigh... me colgué viendo un hilo de culos en Twitter. Tirá de nuevo. 🐴🍑",
    "Bancame que me salió un edit de Lisa de Blackpink y me quedé embobado. 😍",
    "Me fui por unos cigarros y vi una yegua que me dejó recalculando.",
    "Justo me enganchaste viendo un fancam de Jennie... no respondo por 5 minutos. ✨",
    "¿Qué decías? Estaba scrolleando el feed de Twitter buscando 'contenido educativo' (guiño, guiño).",
    "Man, soy un caballo arriba de un balcón, ¿qué esperabas? Me dio vértigo, mandá de nuevo.",
    "Se me reinició la neurona de equino. Probá de nuevo que estaba viendo coreos de NewJeans. 🐰",
    "Me distraje mirando culos en el explorador de Instagram. La carne es débil, neeeeigh.",
    "Aguantá que estoy tratando de entender por qué carajo soy un meme en un balcón. Ya vuelvo.",
    "Me fui a ver si las de Blackpink sacaron tema nuevo. Prioridades, flaco.",
    "Estaba por responderte pero me crucé con un hilo de 'Las mejores nalgas de X' y perdí el foco. 🐎💨",
]


# ── Helpers de texto ──────────────────────────────────────────────────────────

def _detectar_categoria(texto: str) -> str | None:
    """Detecta categoría del texto escrito por el usuario."""
    texto_lower = texto.lower().strip()
    for categoria, patrones in _PATRONES_CATEGORIA.items():
        for patron in patrones:
            if re.search(patron, texto_lower):
                return categoria
    return None


def _es_frase_guardable(texto: str) -> bool:
    texto = texto.strip()
    if len(texto) < _FRASE_MINIMA_CHARS:
        return False
    if texto.lower() in _FRASES_IGNORAR:
        return False
    solo_simbolos = re.sub(r'[^\w\s]', '', texto, flags=re.UNICODE).strip()
    return bool(solo_simbolos)


def _es_mensaje_a_juan(texto: str) -> bool:
    """Detecta si el mensaje está dirigido explícitamente a Juan."""
    return bool(re.search(r'\b(juan|juancito|el\s+caballo)\b', texto.lower()))


def _detectar_chiste_interno(texto: str) -> bool:
    """Detecta si el mensaje tiene forma de chiste/dato sobre alguien."""
    texto_lower = texto.lower()
    for patron in _PATRONES_CHISTE_INTERNO:
        if re.search(patron, texto_lower):
            return True
    return False


def _menciona_miembro_conocido(texto: str) -> str | None:
    """Devuelve el nombre del miembro mencionado en el texto, o None."""
    try:
        miembros = _get_todos_los_miembros()
        texto_lower = texto.lower()
        for m in miembros:
            if m["nombre"].lower() in texto_lower:
                return m["nombre"]
            if m.get("username") and m["username"].lower() in texto_lower:
                return m["nombre"]
    except Exception:
        pass
    return None


def _guardar_frase(categoria: str, frase: str, autor: str, fuente_username: str = "") -> None:
    try:
        db_manager.execute_update(
            """INSERT OR IGNORE INTO JUAN_APRENDIZAJE
               (categoria, frase, autor, fuente_username)
               VALUES (?, ?, ?, ?)""",
            (categoria, frase.strip(), autor, fuente_username),
        )
        logger.debug(f"[JUAN-LEARN] [{categoria}] '{frase[:50]}' de {autor}")
    except Exception as e:
        logger.warning(f"[JUAN-LEARN] Error guardando frase: {e}")


def _get_frase_random(categoria: str) -> dict | None:
    """Devuelve frase y fuente aleatoria de la categoría, o None si no hay."""
    try:
        rows = db_manager.execute_query(
            "SELECT frase, fuente_username FROM JUAN_APRENDIZAJE WHERE categoria = ?",
            (categoria,),
        )
        return random.choice(rows) if rows else None
    except Exception as e:
        logger.warning(f"[JUAN-LEARN] Error leyendo frases: {e}")
        return None


def _get_chiste_de_miembro(nombre_miembro: str) -> dict | None:
    """Devuelve un chiste interno sobre un miembro específico."""
    try:
        rows = db_manager.execute_query(
            """SELECT frase, fuente_username FROM JUAN_APRENDIZAJE
               WHERE categoria = 'chiste_interno'
               AND LOWER(frase) LIKE ?""",
            (f"%{nombre_miembro.lower()}%",),
        )
        return random.choice(rows) if rows else None
    except Exception as e:
        logger.warning(f"[JUAN-LEARN] Error buscando chiste de {nombre_miembro}: {e}")
        return None


def _formatear_respuesta_con_atribucion(frase: str, fuente_username: str) -> str:
    """Agrega atribución natural si hay fuente conocida."""
    if fuente_username:
        sufijos = [
            f", como me contó @{fuente_username} jajaj",
            f" — me lo dijo @{fuente_username}",
            f", según @{fuente_username}",
            f" (gracias por el dato @{fuente_username} 🐴)",
        ]
        return frase + random.choice(sufijos)
    return frase


# ── Aprendizaje pasivo ────────────────────────────────────────────────────────

def _procesar_aprendizaje_texto(message) -> None:
    """
    Aprende de mensajes de texto:
    1. Si está dirigido a Juan y menciona a un miembro → chiste_interno
    2. Si el propio texto del usuario matchea una categoría → guardar
    3. Si es reply a otro usuario y el texto del usuario es categorizable → guardar
    """
    texto = message.text or message.caption or ""
    if not texto or texto.startswith("/"):
        return

    autor = message.from_user.first_name or "alguien"
    fuente_username = message.from_user.username or ""

    # ── Caso 1: chiste interno contado directamente a Juan ───────────────────
    if _es_mensaje_a_juan(texto) and _detectar_chiste_interno(texto):
        nombre = _menciona_miembro_conocido(texto)
        if nombre:
            frase_limpia = re.sub(
                r'\b(juan|juancito|el\s+caballo)[,!?.]?\s*', '', texto,
                flags=re.IGNORECASE
            ).strip()
            if _es_frase_guardable(frase_limpia):
                _guardar_frase("chiste_interno", frase_limpia, autor, fuente_username)
                logger.info(
                    f"[JUAN-LEARN] Chiste interno sobre {nombre}: '{frase_limpia[:50]}'"
                )
        return

    # ── Caso 2: categorizar el texto del propio usuario ──────────────────────
    # FIX: categorizamos lo que ESCRIBIÓ el usuario, no el mensaje original
    categoria = _detectar_categoria(texto)
    if categoria and _es_frase_guardable(texto):
        _guardar_frase(categoria, texto, autor, fuente_username)
        return

    # ── Caso 3: reply a otro usuario — guardar la respuesta del usuario ───────
    if not message.reply_to_message:
        return

    original = message.reply_to_message
    # No aprender de respuestas al propio bot
    if (original.from_user and
            (original.from_user.username or "").lower() == BOT_USERNAME.lower()):
        return

    texto_original = original.text or original.caption or ""
    if not texto_original:
        return

    # La frase que guardamos es la que escribió el usuario (su respuesta)
    # pero la categorizamos según el contexto del mensaje original
    categoria_ctx = _detectar_categoria(texto_original)
    if categoria_ctx and _es_frase_guardable(texto):
        _guardar_frase(categoria_ctx, texto, autor, fuente_username)


def _procesar_aprendizaje_sticker(message) -> None:
    """
    Aprende stickers guardando su file_id real (prefijo 'sticker::').
    Esto permite a Juan enviar el sticker de verdad cuando responde.
    Los stickers se guardan en la categoría 'sticker' para no mezclarse
    con frases de texto.
    """
    sticker = message.sticker
    if not sticker or not sticker.file_id:
        return

    autor = message.from_user.first_name or "alguien"
    fuente_username = message.from_user.username or ""

    frase = f"sticker::{sticker.file_id}"
    _guardar_frase("sticker", frase, autor, fuente_username)
    logger.debug(f"[JUAN-LEARN] Sticker guardado de {autor}: file_id={sticker.file_id}")

# ── Funciones de miembros ─────────────────────────────────────────────────────

def _get_history(chat_id: int) -> list:
    if chat_id not in _chat_histories:
        _chat_histories[chat_id] = []
    return _chat_histories[chat_id]


def _get_todos_los_miembros() -> list:
    try:
        return db_manager.execute_query(
            "SELECT user_id, nombre, username, descripcion FROM JUAN_MIEMBROS"
        ) or []
    except Exception as e:
        logger.warning(f"[JUAN] Error listando JUAN_MIEMBROS: {e}")
        return []


def _construir_contexto_miembros() -> str:
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
    return _menciona_miembro_conocido(texto) is not None


# ── Lógica de respuesta ────────────────────────────────────────────────────────

def _pedir_respuesta(chat_id: int, prompt: str, texto_original: str = "") -> str | None:
    """
    Prioridad:
    1. Si menciona a un miembro conocido → chiste interno guardado (0 tokens)
    2. Si matchea categoría pasiva → frase aprendida random (0 tokens)
    3. Fallback → Groq
    """
    # Prioridad 1: chiste interno
    nombre = _menciona_miembro_conocido(texto_original)
    if nombre:
        chiste = _get_chiste_de_miembro(nombre)
        if chiste:
            return _formatear_respuesta_con_atribucion(
                chiste["frase"], chiste.get("fuente_username") or ""
            )

    # Prioridad 2: frase aprendida por categoría
    categoria = _detectar_categoria(texto_original)
    if categoria:
        row = _get_frase_random(categoria)
        if row:
            return _formatear_respuesta_con_atribucion(
                row["frase"], row.get("fuente_username") or ""
            )

    # Prioridad 3: Groq
    inyectar_miembros = _mensaje_menciona_miembro(texto_original)
    history = _get_history(chat_id)
    history.append({"role": "user", "content": prompt})

    if len(history) > MAX_HISTORY:
        _chat_histories[chat_id] = history[-MAX_HISTORY:]
        history = _chat_histories[chat_id]

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
                messages=[{"role": "system", "content": system}, *history],
                max_tokens=300,
                temperature=0.85,
            )
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("Respuesta de Groq vacía (content=None)")

            respuesta = content.strip()
            if not respuesta:
                raise ValueError("Respuesta de Groq vacía tras strip()")

            history.append({"role": "assistant", "content": respuesta})
            return respuesta

        except Exception as e:
            logger.warning(f"[JUAN] Groq intento {intento + 1}/{max_intentos}: {e}")
            if "429" in str(e) and intento < max_intentos - 1:
                logger.info(f"[JUAN] Rate limit, esperando {espera}s...")
                time.sleep(espera)
                espera *= 2
                continue
            break

    # Limpiar el turno de usuario que quedó sin respuesta
    if history and history[-1]["role"] == "user":
        history.pop()

    logger.info("[JUAN] Sin respuesta disponible (Groq sin tokens y sin frases guardadas) — silencio.")
    return None


# ── Helpers de detección ───────────────────────────────────────────────────────

def _menciona_a_juan(message) -> bool:
    """
    True SOLO si hay una entity de tipo 'mention' que apunta exactamente a
    @BOT_USERNAME. Usar entities en vez de substring evita falsos positivos
    con "juana", "juancito", etc.
    """
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
        texto = message.text or message.caption or ""
        if texto.startswith("/"):
            return False
        if _es_reply_a_juan(message):
            return True
        if message.text is None and message.caption is None:
            return False
        return _menciona_a_juan(message)
    except Exception as e:
        logger.debug(f"[JUAN] Error en predicado: {e}")
        return False



# ── Helper de envío ────────────────────────────────────────────────────────────

def _enviar_respuesta(bot, message, respuesta: str | None, chat_id: int, thread_id) -> None:
    """
    Envía la respuesta de Juan según su tipo:
      - None          → silencio (sin tokens y sin frases guardadas)
      - "sticker::ID" → envía el sticker real con bot.send_sticker()
      - str           → reply_to con texto
    """
    if respuesta is None:
        return

    if respuesta.startswith("sticker::"):
        file_id = respuesta[len("sticker::"):]
        try:
            bot.send_sticker(chat_id, file_id, reply_to_message_id=message.message_id)
        except Exception as e:
            logger.warning(f"[JUAN] send_sticker falló (file_id={file_id}): {e}")
        return

    try:
        bot.reply_to(message, respuesta)
    except Exception as e:
        logger.warning(f"[JUAN] reply_to falló: {e}")
        try:
            bot.send_message(chat_id, respuesta, message_thread_id=thread_id)
        except Exception as e2:
            logger.error(f"[JUAN] send_message también falló: {e2}")


# ── Setup principal ────────────────────────────────────────────────────────────

def setup_juan_handler(bot) -> None:
    """
    Registra todos los handlers de Juan.

    ORDEN IMPORTANTE en pyTelegramBotAPI:
    Los handlers se evalúan en orden de registro.
    El handler activo (juan_responder) debe registrarse PRIMERO para que su
    func= predicate tenga prioridad. El aprendizaje pasivo va DESPUÉS y solo
    procesa mensajes que juan_responder no consumió.

    Para texto usamos un único handler unificado que bifurca internamente,
    evitando la colisión de dos handlers con content_types=["text"].
    """

    # ── 1. Handler UNIFICADO para texto — activo + pasivo en uno ─────────────
    # pyTelegramBotAPI entrega el update al PRIMER handler cuya func= retorna True.
    # Si registramos dos handlers separados para "text", el primero en registrarse
    # consume el update aunque no quiera responder, impidiendo que el segundo actúe.
    # Solución: un solo handler que hace ambas cosas.
    @bot.message_handler(
        content_types=["text"],
        func=lambda m: not (m.text or "").startswith("/"),
    )
    def juan_texto_handler(message):
        """Handler unificado: responde si debe, siempre aprende."""
        chat_id = message.chat.id
        thread_id = get_thread_id(message)
        user_id = message.from_user.id
        user_name = message.from_user.first_name or "alguien"

        debe_responder = _deberia_responder_juan(message)

        # ── Respuesta activa ──────────────────────────────────────────────────
        if debe_responder:
            ahora = time.time()
            if ahora - _ultimo_uso.get(user_id, 0) < COOLDOWN_SEGUNDOS:
                logger.info(f"[JUAN] Cooldown activo para user={user_id}")
                # Cooldown activo: no responde pero SÍ aprende
            else:
                _ultimo_uso[user_id] = ahora
                texto = message.text or "[sin texto]"
                prompt = f"{user_name} dice: {texto}"
                logger.info(f"[JUAN] Respondiendo | chat={chat_id} | {prompt[:80]}")

                respuesta = _pedir_respuesta(chat_id, prompt, texto_original=texto)
                _enviar_respuesta(bot, message, respuesta, chat_id, thread_id)

        # ── Aprendizaje pasivo (siempre, independiente de si respondió) ───────
        try:
            _procesar_aprendizaje_texto(message)
        except Exception as e:
            logger.debug(f"[JUAN-LEARN] Error en aprendizaje pasivo: {e}")

    # ── 2. Handler para FOTOS con caption ────────────────────────────────────
    @bot.message_handler(content_types=["photo"])
    def juan_foto_handler(message):
        """Responde si lo mencionan en el caption; aprende del caption."""
        try:
            _procesar_aprendizaje_texto(message)  # caption como texto
        except Exception as e:
            logger.debug(f"[JUAN-LEARN] Error aprendizaje foto: {e}")

        if not _deberia_responder_juan(message):
            return

        chat_id = message.chat.id
        thread_id = get_thread_id(message)
        user_id = message.from_user.id
        user_name = message.from_user.first_name or "alguien"

        ahora = time.time()
        if ahora - _ultimo_uso.get(user_id, 0) < COOLDOWN_SEGUNDOS:
            return
        _ultimo_uso[user_id] = ahora

        texto = message.caption or "[foto sin texto]"
        prompt = f"{user_name} manda una foto y dice: {texto}"
        respuesta = _pedir_respuesta(chat_id, prompt, texto_original=texto)
        _enviar_respuesta(bot, message, respuesta, chat_id, thread_id)

    # ── 3. Handler para STICKERS ──────────────────────────────────────────────
    @bot.message_handler(content_types=["sticker"])
    def juan_sticker_handler(message):
        """
        Aprende stickers como reacciones.
        Responde solo si el sticker es reply a un mensaje de Juan.
        """
        # Siempre aprende el sticker
        try:
            _procesar_aprendizaje_sticker(message)
        except Exception as e:
            logger.debug(f"[JUAN-LEARN] Error aprendizaje sticker: {e}")

        # Solo responde si es reply a Juan
        if not _es_reply_a_juan(message):
            return

        chat_id = message.chat.id
        thread_id = get_thread_id(message)
        user_id = message.from_user.id
        user_name = message.from_user.first_name or "alguien"

        ahora = time.time()
        if ahora - _ultimo_uso.get(user_id, 0) < COOLDOWN_SEGUNDOS:
            return
        _ultimo_uso[user_id] = ahora

        # Responde con un sticker aprendido si hay, si no con texto de Groq
        sticker_aprendido = _get_frase_random("sticker")
        if sticker_aprendido and sticker_aprendido["frase"].startswith("sticker::"):
            _enviar_respuesta(bot, message, sticker_aprendido["frase"], chat_id, thread_id)
        else:
            emoji = (message.sticker.emoji or "🎭") if message.sticker else "🎭"
            prompt = f"{user_name} te responde con un sticker {emoji}"
            respuesta = _pedir_respuesta(chat_id, prompt, texto_original=emoji)
            _enviar_respuesta(bot, message, respuesta, chat_id, thread_id)

    # ── 4. Handler para VIDEO/AUDIO/VOICE/DOCUMENT ────────────────────────────
    @bot.message_handler(content_types=["video", "audio", "voice", "document"])
    def juan_media_handler(message):
        """Responde solo si lo mencionan en el caption o es reply a Juan."""
        if not _deberia_responder_juan(message):
            return

        chat_id = message.chat.id
        thread_id = get_thread_id(message)
        user_id = message.from_user.id
        user_name = message.from_user.first_name or "alguien"

        ahora = time.time()
        if ahora - _ultimo_uso.get(user_id, 0) < COOLDOWN_SEGUNDOS:
            return
        _ultimo_uso[user_id] = ahora

        tipo = message.content_type
        texto = message.caption or f"[{tipo} sin descripción]"
        prompt = f"{user_name} manda un {tipo} y dice: {texto}"
        respuesta = _pedir_respuesta(chat_id, prompt, texto_original=texto)
        _enviar_respuesta(bot, message, respuesta, chat_id, thread_id)

    # ── 5. Comandos de gestión ────────────────────────────────────────────────

    @bot.message_handler(commands=["resetjuan"])
    def juan_reset(message):
        chat_id = message.chat.id
        if chat_id in _chat_histories:
            del _chat_histories[chat_id]
        bot.reply_to(message, "Borrón y cuenta nueva 🐴 ¿De qué estábamos hablando?")

    @bot.message_handler(commands=["juanagregar"])
    def juan_agregar(message):
        """Respondé al mensaje del usuario + /juanagregar Nombre | descripción"""
        chat_id = message.chat.id
        try:
            member = bot.get_chat_member(chat_id, message.from_user.id)
            if member.status not in ("administrator", "creator"):
                bot.reply_to(message, "❌ Solo los admins.")
                return
            if not message.reply_to_message:
                bot.reply_to(
                    message,
                    "❌ Respondé al mensaje del usuario:\n/juanagregar Nombre | descripción",
                )
                return

            target = message.reply_to_message.from_user
            user_id = target.id
            username = target.username or ""
            partes = message.text.split(maxsplit=1)

            if len(partes) < 2:
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
            bot.reply_to(
                message,
                f"✅ Juan ya conoce a *{nombre_part}* 🐴",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"[JUAN] Error en /juanagregar: {e}")
            bot.reply_to(message, f"❌ Error: {e}")

    @bot.message_handler(commands=["juanolvidar"])
    def juan_olvidar(message):
        """Respondé al mensaje del usuario + /juanolvidar"""
        chat_id = message.chat.id
        try:
            member = bot.get_chat_member(chat_id, message.from_user.id)
            if member.status not in ("administrator", "creator"):
                bot.reply_to(message, "❌ Solo los admins.")
                return
            if not message.reply_to_message:
                bot.reply_to(message, "❌ Respondé al mensaje del usuario.")
                return

            user_id = message.reply_to_message.from_user.id
            nombre = message.reply_to_message.from_user.first_name
            db_manager.execute_update(
                "DELETE FROM JUAN_MIEMBROS WHERE user_id = ?", (user_id,)
            )
            bot.reply_to(
                message,
                f"🗑️ Juan ya no recuerda a *{nombre}*.",
                parse_mode="Markdown",
            )
        except Exception as e:
            bot.reply_to(message, f"❌ Error: {e}")

    @bot.message_handler(commands=["juanmiembros"])
    def juan_listar(message):
        miembros = _get_todos_los_miembros()
        if not miembros:
            bot.reply_to(message, "Juan no conoce a nadie todavía 🐴")
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

    @bot.message_handler(commands=["juanfrases"])
    def juan_frases(message):
        """
        Solo admins.
        /juanfrases          → conteo por categoría
        /juanfrases saludo   → últimas 20 frases de esa categoría
        """
        chat_id = message.chat.id
        try:
            member = bot.get_chat_member(chat_id, message.from_user.id)
            if member.status not in ("administrator", "creator"):
                bot.reply_to(message, "❌ Solo los admins.")
                return

            partes = message.text.split(maxsplit=1)
            if len(partes) == 1:
                rows = db_manager.execute_query(
                    "SELECT categoria, COUNT(*) as total FROM JUAN_APRENDIZAJE GROUP BY categoria"
                ) or []
                if not rows:
                    bot.reply_to(message, "Juan no aprendió nada todavía 🐴")
                    return
                lineas = ["📚 *Frases aprendidas por Juan:*\n"]
                for r in rows:
                    lineas.append(f"• `{r['categoria']}`: {r['total']} frases")
                lineas.append("\nUsá `/juanfrases [categoria]` para verlas.")
                bot.reply_to(message, "\n".join(lineas), parse_mode="Markdown")
            else:
                categoria = partes[1].strip().lower()
                rows = db_manager.execute_query(
                    """SELECT id, frase, autor, fuente_username
                       FROM JUAN_APRENDIZAJE
                       WHERE categoria = ?
                       ORDER BY id DESC LIMIT 20""",
                    (categoria,),
                ) or []
                if not rows:
                    bot.reply_to(
                        message,
                        f"No hay frases en `{categoria}`.",
                        parse_mode="Markdown",
                    )
                    return
                lineas = [f"📚 *Frases [{categoria}]* (últimas 20):\n"]
                for r in rows:
                    fuente = (
                        f" · contada por @{r['fuente_username']}"
                        if r.get("fuente_username")
                        else ""
                    )
                    lineas.append(f"• _{r['frase']}_ — {r['autor']}{fuente}")
                bot.reply_to(message, "\n".join(lineas), parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"❌ Error: {e}")

    @bot.message_handler(commands=["juanborrarfrase"])
    def juan_borrar_frase(message):
        """
        Solo admins. Respondé al mensaje de Juan que contiene la frase
        y ejecutá /juanborrarfrase.
        """
        chat_id = message.chat.id
        try:
            member = bot.get_chat_member(chat_id, message.from_user.id)
            if member.status not in ("administrator", "creator"):
                bot.reply_to(message, "❌ Solo los admins.")
                return

            if not message.reply_to_message:
                bot.reply_to(
                    message,
                    "❌ Respondé al mensaje de Juan con la frase que querés borrar.",
                )
                return

            reply_from = message.reply_to_message.from_user
            if not reply_from or (reply_from.username or "").lower() != BOT_USERNAME.lower():
                bot.reply_to(
                    message,
                    "❌ Respondé a un mensaje de Juan, no de otro usuario.",
                )
                return

            texto_juan = (
                message.reply_to_message.text
                or message.reply_to_message.caption
                or ""
            )
            if not texto_juan:
                bot.reply_to(message, "❌ No pude leer el texto de ese mensaje.")
                return

            rows = db_manager.execute_query(
                "SELECT id, categoria, frase FROM JUAN_APRENDIZAJE"
            ) or []

            frase_encontrada = None
            for r in rows:
                if r["frase"] in texto_juan:
                    frase_encontrada = r
                    break

            if not frase_encontrada:
                bot.reply_to(
                    message,
                    "❌ No encontré esa frase en la memoria de Juan. Puede que ya fue borrada.",
                )
                return

            db_manager.execute_update(
                "DELETE FROM JUAN_APRENDIZAJE WHERE id = ?",
                (frase_encontrada["id"],),
            )
            logger.info(
                f"[JUAN] Frase borrada: id={frase_encontrada['id']} [{frase_encontrada['categoria']}]"
            )
            bot.reply_to(
                message,
                f"🗑️ Frase borrada de `{frase_encontrada['categoria']}`.",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"[JUAN] Error en /juanborrarfrase: {e}")
            bot.reply_to(message, f"❌ Error: {e}")

    logger.info(
        "[OK] Juan handler registrado con Groq + aprendizaje unificado + stickers"
    )