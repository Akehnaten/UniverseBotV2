# -*- coding: utf-8 -*-
"""
handlers/juan_handler.py
Juan, el caballo de los memes. Usando Groq (gratuito).
Incluye sistema de aprendizaje pasivo + chistes internos con atribución.
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
# Ejemplo: "juan, cris es intenso" / "juancito sabés que cris es intenso?"
_PATRONES_CHISTE_INTERNO = [
    r"\b(sab[eé]s?|sa[bv]ías?|cont[aé]|te\s*cuento|imaginate|fijate)\b",
    r"\bes\s+(un[ao]?|re|muy|bastante|demasiado)\b",
    r"\bsiempre\s+(hace|dice|llega|se)\b",
    r"\bnunca\s+(hace|dice|llega|se)\b",
    r"\bles?\s+dicen?\b",
    r"\ble\s+llaman?\b",
    r"\btodos\s+(saben?|dicen?|lo|la)\b",
]


def _detectar_categoria(texto: str) -> str | None:
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
    """
    Si la frase tiene fuente conocida, agrega la atribución de forma natural.
    Ejemplo: "Sí, Cris es intenso, como me contó @rei jajaj"
    """
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

def _procesar_aprendizaje(message) -> None:
    """
    Escucha todos los mensajes:
    1. Si es reply a otro usuario → categoría pasiva (saludo, opinión, etc.)
    2. Si está dirigido a Juan y menciona a un miembro → chiste_interno
    """
    texto = message.text or message.caption or ""
    if not texto:
        return

    autor = message.from_user.first_name or "alguien"
    fuente_username = message.from_user.username or ""

    # ── Caso 1: chiste interno contado directamente a Juan ───────────────────
    if _es_mensaje_a_juan(texto) and _detectar_chiste_interno(texto):
        nombre = _menciona_miembro_conocido(texto)
        if nombre:
            # Guardar la parte del texto que viene después de mencionar a Juan
            # para extraer el dato sobre el miembro
            frase_limpia = re.sub(
                r'\b(juan|juancito|el\s+caballo)[,!?.]?\s*', '', texto,
                flags=re.IGNORECASE
            ).strip()
            if _es_frase_guardable(frase_limpia):
                _guardar_frase("chiste_interno", frase_limpia, autor, fuente_username)
                logger.info(f"[JUAN-LEARN] Chiste interno aprendido sobre {nombre}: '{frase_limpia[:50]}'")
        return

    # ── Caso 2: reply a otro usuario → categoría pasiva ──────────────────────
    if not message.reply_to_message:
        return

    original = message.reply_to_message
    # No aprender de mensajes del propio bot
    if (original.from_user and
            (original.from_user.username or "").lower() == BOT_USERNAME.lower()):
        return

    texto_original = original.text or original.caption or ""
    if not texto_original:
        return

    categoria = _detectar_categoria(texto_original)
    if not categoria:
        return

    if not _es_frase_guardable(texto):
        return

    _guardar_frase(categoria, texto, autor, fuente_username)


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

def _pedir_respuesta(chat_id: int, prompt: str, texto_original: str = "") -> str:
    """
    Prioridad:
    1. Si menciona a un miembro conocido → buscar chiste interno guardado (0 tokens)
    2. Si matchea categoría pasiva → frase aprendida random (0 tokens)
    3. Fallback → Groq
    """
    # Prioridad 1: chiste interno sobre miembro mencionado
    nombre = _menciona_miembro_conocido(texto_original)
    if nombre:
        chiste = _get_chiste_de_miembro(nombre)
        if chiste:
            return _formatear_respuesta_con_atribucion(
                chiste["frase"], chiste["fuente_username"] or ""
            )

    # Prioridad 2: frase aprendida por categoría
    categoria = _detectar_categoria(texto_original)
    if categoria:
        row = _get_frase_random(categoria)
        if row:
            return _formatear_respuesta_con_atribucion(
                row["frase"], row["fuente_username"] or ""
            )

    # Lista de excusas para cuando el modelo falla
    excusas = [
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
        "Estaba por responderte pero me crucé con un hilo de 'Las mejores nalgas de X' y perdí el foco. 🐎💨"
    ]

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
            
            # SOLUCIÓN AL ERROR: Validamos que content no sea None antes de usar .strip()
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("La respuesta de Groq vino vacía")
                
            respuesta = content.strip()
            history.append({"role": "assistant", "content": respuesta})
            return respuesta
            
        except Exception as e:
            # ... (Lógica de logs y rate limit se mantiene igual) ...
            if "429" in str(e) and intento < max_intentos - 1:
                time.sleep(espera)
                espera *= 2
                continue
            break

    # Limpieza de historial si falló
    if history and history[-1]["role"] == "user":
        history.pop()

    # Retorna una frase aleatoria de la lista de excusas
    return random.choice(excusas)


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

    # ── Listener pasivo — escucha todos los mensajes de texto ─────────────────
    @bot.message_handler(content_types=["text"])
    def juan_aprender(message):
        try:
            _procesar_aprendizaje(message)
        except Exception as e:
            logger.debug(f"[JUAN-LEARN] Error en aprendizaje pasivo: {e}")

    # ── Respuesta activa de Juan ───────────────────────────────────────────────
    @bot.message_handler(
        content_types=["text", "photo", "video", "document", "sticker", "audio", "voice"],
        func=_deberia_responder_juan,
    )
    def juan_responder(message):
        chat_id   = message.chat.id
        thread_id = get_thread_id(message)
        user_id   = message.from_user.id
        user_name = message.from_user.first_name or "alguien"

        ahora = time.time()
        if ahora - _ultimo_uso.get(user_id, 0) < COOLDOWN_SEGUNDOS:
            logger.info(f"[JUAN] Cooldown activo para user={user_id}")
            return
        _ultimo_uso[user_id] = ahora

        texto = message.text or message.caption or "[sin texto]"
        prompt = f"{user_name} dice: {texto}"
        logger.info(f"[JUAN] chat={chat_id} | {prompt[:80]}")

        respuesta = _pedir_respuesta(chat_id, prompt, texto_original=texto)

        try:
            bot.reply_to(message, respuesta)
        except Exception as e:
            logger.warning(f"[JUAN] reply_to falló: {e}")
            try:
                bot.send_message(chat_id, respuesta, message_thread_id=thread_id)
            except Exception as e2:
                logger.error(f"[JUAN] send_message también falló: {e2}")

    # ── /resetjuan ────────────────────────────────────────────────────────────
    @bot.message_handler(commands=["resetjuan"])
    def juan_reset(message):
        chat_id = message.chat.id
        if chat_id in _chat_histories:
            del _chat_histories[chat_id]
        bot.reply_to(message, "Borrón y cuenta nueva 🐴 ¿De qué estábamos hablando?")

    # ── /juanagregar ──────────────────────────────────────────────────────────
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
                bot.reply_to(message, "❌ Respondé al mensaje del usuario:\n/juanagregar Nombre | descripción")
                return

            target   = message.reply_to_message.from_user
            user_id  = target.id
            username = target.username or ""
            partes   = message.text.split(maxsplit=1)

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
            bot.reply_to(message, f"✅ Juan ya conoce a *{nombre_part}* 🐴", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"[JUAN] Error en /juanagregar: {e}")
            bot.reply_to(message, f"❌ Error: {e}")

    # ── /juanolvidar ──────────────────────────────────────────────────────────
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
            nombre  = message.reply_to_message.from_user.first_name
            db_manager.execute_update("DELETE FROM JUAN_MIEMBROS WHERE user_id = ?", (user_id,))
            bot.reply_to(message, f"🗑️ Juan ya no recuerda a *{nombre}*.", parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"❌ Error: {e}")

    # ── /juanmiembros ─────────────────────────────────────────────────────────
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

    # ── /juanfrases ───────────────────────────────────────────────────────────
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
                    bot.reply_to(message, f"No hay frases en `{categoria}`.", parse_mode="Markdown")
                    return
                lineas = [f"📚 *Frases [{categoria}]* (últimas 20):\n"]
                for r in rows:
                    fuente = f" · contada por @{r['fuente_username']}" if r.get("fuente_username") else ""
                    lineas.append(f"• _{r['frase']}_ — {r['autor']}{fuente}")
                bot.reply_to(message, "\n".join(lineas), parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"❌ Error: {e}")

    # ── /juanborrarfrase ──────────────────────────────────────────────────────
    @bot.message_handler(commands=["juanborrarfrase"])
    def juan_borrar_frase(message):
        """
        Solo admins. Respondé al mensaje de Juan que contiene la frase
        y ejecutá /juanborrarfrase — la busca y borra automáticamente.
        """
        chat_id = message.chat.id
        try:
            member = bot.get_chat_member(chat_id, message.from_user.id)
            if member.status not in ("administrator", "creator"):
                bot.reply_to(message, "❌ Solo los admins.")
                return

            if not message.reply_to_message:
                bot.reply_to(message, "❌ Respondé al mensaje de Juan con la frase que querés borrar.")
                return

            # Verificar que el reply sea a Juan
            reply_from = message.reply_to_message.from_user
            if not reply_from or (reply_from.username or "").lower() != BOT_USERNAME.lower():
                bot.reply_to(message, "❌ Respondé a un mensaje de Juan, no de otro usuario.")
                return

            texto_juan = message.reply_to_message.text or message.reply_to_message.caption or ""
            if not texto_juan:
                bot.reply_to(message, "❌ No pude leer el texto de ese mensaje.")
                return

            # Buscar la frase en la BD — buscamos si el texto del mensaje de Juan
            # contiene alguna frase guardada (puede tener sufijo de atribución)
            rows = db_manager.execute_query(
                "SELECT id, categoria, frase FROM JUAN_APRENDIZAJE"
            ) or []

            frase_encontrada = None
            for r in rows:
                if r["frase"] in texto_juan:
                    frase_encontrada = r
                    break

            if not frase_encontrada:
                bot.reply_to(message, "❌ No encontré esa frase en la memoria de Juan. Puede que ya fue borrada.")
                return

            db_manager.execute_update(
                "DELETE FROM JUAN_APRENDIZAJE WHERE id = ?",
                (frase_encontrada["id"],),
            )
            logger.info(f"[JUAN] Frase borrada: id={frase_encontrada['id']} [{frase_encontrada['categoria']}]")
            bot.reply_to(
                message,
                f"🗑️ Frase borrada de `{frase_encontrada['categoria']}`.",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"[JUAN] Error en /juanborrarfrase: {e}")
            bot.reply_to(message, f"❌ Error: {e}")

    logger.info("[OK] Juan handler registrado con Groq + aprendizaje + chistes internos")