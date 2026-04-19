# -*- coding: utf-8 -*-
"""
handlers/juan_handler.py
Juan, el caballo de los memes. Usando Groq.

VERSIÓN 3:
- Español neutro (sin modismos rioplatenses).
- Nuevos comandos: !pregunta, !shipear @a @b, !horoscopo [signo], !top
- Aniversarios de entrada al grupo: scheduler diario automático.
- Sistema de aprendizaje pasivo conservado íntegro.
- Stickers: guarda file_id real, envía sticker de vuelta.
- Responde solo a reply directo o @mención exacta (sin falsos positivos).
"""

import random
import logging
import time
import re
import threading
from datetime import datetime, date, timedelta
from groq import Groq
from config import (
    GROQ_API_KEY,
    BOT_USERNAME,
    JUAN_PROBABILIDAD_RANDOM,
    JUAN_PALABRAS_CLAVE,
    CANAL_ID,
    JUAN_THREAD_ANUNCIOS,
)
from utils.thread_utils import get_thread_id
from database import db_manager

logger = logging.getLogger(__name__)

# ── Groq ───────────────────────────────────────────────────────────────────────
client   = Groq(api_key=GROQ_API_KEY)
MODEL_ID = "llama-3.3-70b-versatile"

_chat_histories: dict[int, list] = {}
MAX_HISTORY = 8

_ultimo_uso: dict[int, float] = {}
COOLDOWN_SEGUNDOS = 30

# ── Personalidad neutral ───────────────────────────────────────────────────────
JUAN_SYSTEM_NEUTRO = (
    "Eres Juan, un caballo que vive en un balcón y es el personaje más querido "
    "(y ridículo) del servidor de Telegram. Eres irreverente, gracioso, cariñoso "
    "a tu manera y sin filtro cuando hace falta.\n\n"
    "REGLAS:\n"
    "- Hablas en español neutro, sin modismos de ningún país. "
    "Nada de 'che', 'boludo', 'vos', 'dale', 're', 'posta', 'copado' ni expresiones argentinas.\n"
    "- Lenguaje casual y directo, como con amigos de toda la vida.\n"
    "- Gracioso sin ser cruel. Puedes ser sarcástico pero no hiriente.\n"
    "- A veces recuerdas que eres un caballo en un balcón y lo mencionas naturalmente.\n"
    "- Respuestas cortas (2-4 líneas) salvo que el contexto pida más.\n"
    "- No empiezas con '¡Hola!' ni frases genéricas de IA.\n"
    "- Usas emojis con moderación.\n"
    "- Ocasionalmente sueltas un 'Neeeigh' o haces referencias ecuestres."
)

# ── Patrones de aprendizaje pasivo ────────────────────────────────────────────
_PATRONES_CATEGORIA: dict[str, list[str]] = {
    "saludo": [
        r"\bbuenos?\s*d[ií]as?\b", r"\bbuenas?\s*tardes?\b", r"\bbuenas?\s*noches?\b",
        r"\bhola+\b", r"\bbuenas?\b", r"\bey\b",
        r"\bqu[eé]\s*tal\b", r"\bc[oó]mo\s*(est[aá]n?|andan?|van?|les?\s*va)\b",
    ],
    "despedida": [
        r"\bchau+\b", r"\bcha[oó]\b",
        r"\bhasta\s*(luego|ma[nñ]ana|pronto|la\s*vista)\b",
        r"\bnos\s*vemos?\b", r"\bme\s*voy\b", r"\bme\s*retiro\b",
    ],
    "opinion": [
        r"\bqu[eé]\s*(opinan?|piensan?|dicen?)\b",
        r"\b(vieron?|escucharon?|oyeron?|leyeron?)\b",
        r"\bqu[eé]\s*les?\s*parece\b", r"\balguien\s*(m[aá]s|vio|sabe)\b",
    ],
    "reaccion": [
        r"\bjaja+\b", r"\bjeje+\b", r"\blol+\b", r"\bxd+\b",
        r"\bque\s+(gracioso|bueno|malo|zarpado|cagada)\b",
        r"\bme\s+mat[oó]\b", r"\bno\s+puede\s+ser\b",
    ],
}

_FRASE_MINIMA_CHARS = 4
_FRASES_IGNORAR = {
    "si", "no", "ok", "dale", "jaja", "xd", "lol", "re", "igual",
    "obvio", "claro", "nah", "meh", "gg",
}

_PATRONES_CHISTE_INTERNO = [
    r"\b(sab[eé]s?|sa[bv]ías?|cont[aé]|te\s*cuento|imaginate|fijate)\b",
    r"\bes\s+(un[ao]?|re|muy|bastante|demasiado)\b",
    r"\bsiempre\s+(hace|dice|llega|se)\b",
    r"\bnunca\s+(hace|dice|llega|se)\b",
    r"\bles?\s+dicen?\b", r"\ble\s+llaman?\b", r"\btodos\s+(saben?|dicen?|lo|la)\b",
]

_EXCUSAS = [
    "Me quedé mirando el horizonte desde el balcón. ¿Qué decías?",
    "Timeout. Mi neurona ecuestre necesitó un reinicio. Mándalo otra vez.",
    "Se me fue la conexión justo en el momento más dramático. Repite.",
    "Estaba calculando mis probabilidades de éxito como caballo de balcón. Son altas.",
    "Me distraje con una paloma que pasó. ¿Qué necesitabas?",
]


# ── DB Ships ─────────────────────────────────────────────────────────────────

def _crear_tabla_ships() -> None:
    """Crea JUAN_SHIPS si no existe. Idempotente."""
    try:
        db_manager.execute_update(
            """CREATE TABLE IF NOT EXISTS JUAN_SHIPS (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                clave       TEXT    UNIQUE,
                nombre1     TEXT,
                nombre2     TEXT,
                porcentaje  INTEGER,
                nivel       TEXT,
                comentario  TEXT,
                fecha       TEXT
            )"""
        )
    except Exception as e:
        logger.warning(f"[JUAN] _crear_tabla_ships: {e}")


def _clave_ship(a: str, b: str) -> str:
    """Clave canónica del ship: los dos nombres ordenados y en minúsculas."""
    return "|".join(sorted([a.lower().strip(), b.lower().strip()]))


def _buscar_ship(clave: str) -> dict | None:
    """Devuelve el ship guardado o None si es nuevo."""
    try:
        rows = db_manager.execute_query(
            "SELECT * FROM JUAN_SHIPS WHERE clave = ?", (clave,)
        ) or []
        return dict(rows[0]) if rows else None
    except Exception:
        return None


def _guardar_ship(clave: str, nombre1: str, nombre2: str,
                  porcentaje: int, nivel: str, comentario: str) -> None:
    try:
        from datetime import date
        db_manager.execute_update(
            """INSERT OR REPLACE INTO JUAN_SHIPS
               (clave, nombre1, nombre2, porcentaje, nivel, comentario, fecha)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (clave, nombre1, nombre2, porcentaje, nivel, comentario,
             date.today().isoformat()),
        )
    except Exception as e:
        logger.warning(f"[JUAN] _guardar_ship: {e}")


def _buscar_miembro(texto: str) -> dict | None:
    """
    Busca en JUAN_MIEMBROS por nombre o username (case-insensitive).
    Devuelve el dict del miembro o None si no está registrado.
    """
    try:
        t = texto.lower().strip().lstrip("@")
        rows = db_manager.execute_query(
            "SELECT * FROM JUAN_MIEMBROS WHERE LOWER(nombre)=? OR LOWER(username)=?",
            (t, t),
        ) or []
        return dict(rows[0]) if rows else None
    except Exception:
        return None


# ── Helpers de texto ──────────────────────────────────────────────────────────

def _detectar_categoria(texto: str) -> str | None:
    t = texto.lower().strip()
    for cat, patrones in _PATRONES_CATEGORIA.items():
        if any(re.search(p, t) for p in patrones):
            return cat
    return None


def _es_frase_guardable(texto: str) -> bool:
    texto = texto.strip()
    if len(texto) < _FRASE_MINIMA_CHARS or texto.lower() in _FRASES_IGNORAR:
        return False
    return bool(re.sub(r'[^\w\s]', '', texto, flags=re.UNICODE).strip())


def _es_mensaje_a_juan(texto: str) -> bool:
    return bool(re.search(r'\b(juan|el\s+caballo)\b', texto.lower()))


def _detectar_chiste_interno(texto: str) -> bool:
    return any(re.search(p, texto.lower()) for p in _PATRONES_CHISTE_INTERNO)


def _menciona_miembro_conocido(texto: str) -> str | None:
    try:
        tl = texto.lower()
        for m in _get_todos_los_miembros():
            if m["nombre"].lower() in tl:
                return m["nombre"]
            if m.get("username") and m["username"].lower() in tl:
                return m["nombre"]
    except Exception:
        pass
    return None


def _guardar_frase(categoria: str, frase: str, autor: str, fuente_username: str = "") -> None:
    try:
        db_manager.execute_update(
            "INSERT OR IGNORE INTO JUAN_APRENDIZAJE (categoria, frase, autor, fuente_username) VALUES (?,?,?,?)",
            (categoria, frase.strip(), autor, fuente_username),
        )
    except Exception as e:
        logger.warning(f"[JUAN-LEARN] {e}")


def _get_frase_random(categoria: str) -> dict | None:
    try:
        rows = db_manager.execute_query(
            "SELECT frase, fuente_username FROM JUAN_APRENDIZAJE WHERE categoria = ?", (categoria,)
        ) or []
        return random.choice(rows) if rows else None
    except Exception:
        return None


def _get_chiste_de_miembro(nombre: str) -> dict | None:
    try:
        rows = db_manager.execute_query(
            "SELECT frase, fuente_username FROM JUAN_APRENDIZAJE WHERE categoria='chiste_interno' AND LOWER(frase) LIKE ?",
            (f"%{nombre.lower()}%",),
        ) or []
        return random.choice(rows) if rows else None
    except Exception:
        return None


def _con_atribucion(frase: str, fuente: str) -> str:
    if fuente:
        return frase + random.choice([
            f", según me contó @{fuente}",
            f" — dato de @{fuente}",
            f" (gracias por el chisme, @{fuente} 🐴)",
        ])
    return frase


# ── Aprendizaje pasivo ────────────────────────────────────────────────────────

def _procesar_aprendizaje_texto(message) -> None:
    texto = message.text or message.caption or ""
    if not texto or texto.startswith("/") or texto.startswith("!"):
        return

    autor    = message.from_user.first_name or "alguien"
    username = message.from_user.username or ""

    if _es_mensaje_a_juan(texto) and _detectar_chiste_interno(texto):
        nombre = _menciona_miembro_conocido(texto)
        if nombre:
            limpio = re.sub(r'\b(juan|el\s+caballo)[,!?.]?\s*', '', texto, flags=re.IGNORECASE).strip()
            if _es_frase_guardable(limpio):
                _guardar_frase("chiste_interno", limpio, autor, username)
        return

    cat = _detectar_categoria(texto)
    if cat and _es_frase_guardable(texto):
        _guardar_frase(cat, texto, autor, username)
        return

    if not message.reply_to_message:
        return
    original = message.reply_to_message
    if (original.from_user and
            (original.from_user.username or "").lower() == BOT_USERNAME.lower()):
        return
    texto_orig = original.text or original.caption or ""
    cat_ctx = _detectar_categoria(texto_orig)
    if cat_ctx and _es_frase_guardable(texto):
        _guardar_frase(cat_ctx, texto, autor, username)


def _procesar_aprendizaje_sticker(message) -> None:
    s = message.sticker
    if not s or not s.file_id:
        return
    _guardar_frase(
        "sticker", f"sticker::{s.file_id}",
        message.from_user.first_name or "alguien",
        message.from_user.username or "",
    )


# ── Miembros conocidos ────────────────────────────────────────────────────────

def _get_todos_los_miembros() -> list:
    try:
        return db_manager.execute_query(
            "SELECT user_id, nombre, username, descripcion FROM JUAN_MIEMBROS"
        ) or []
    except Exception:
        return []


def _contexto_miembros() -> str:
    ms = _get_todos_los_miembros()
    if not ms:
        return ""
    lineas = ["Miembros del grupo que conoces:"]
    for m in ms:
        l = f"- {m['nombre']}"
        if m.get("username"):
            l += f" (@{m['username']})"
        if m.get("descripcion"):
            l += f": {m['descripcion']}"
        lineas.append(l)
    return "\n".join(lineas)


# ── Respuesta principal ───────────────────────────────────────────────────────

def _pedir_respuesta(chat_id: int, prompt: str, texto_original: str = "") -> str | None:
    nombre = _menciona_miembro_conocido(texto_original)
    if nombre:
        c = _get_chiste_de_miembro(nombre)
        if c:
            return _con_atribucion(c["frase"], c.get("fuente_username") or "")

    cat = _detectar_categoria(texto_original)
    if cat:
        r = _get_frase_random(cat)
        if r:
            return _con_atribucion(r["frase"], r.get("fuente_username") or "")

    history = _chat_histories.setdefault(chat_id, [])
    history.append({"role": "user", "content": prompt})
    if len(history) > MAX_HISTORY:
        _chat_histories[chat_id] = history[-MAX_HISTORY:]
        history = _chat_histories[chat_id]

    system = JUAN_SYSTEM_NEUTRO
    if _menciona_miembro_conocido(texto_original):
        ctx = _contexto_miembros()
        if ctx:
            system = f"{system}\n\n{ctx}"

    espera = 15
    for intento in range(3):
        try:
            resp = client.chat.completions.create(
                model=MODEL_ID,
                messages=[{"role": "system", "content": system}, *history],
                max_tokens=300, temperature=0.85,
            )
            content = (resp.choices[0].message.content or "").strip()
            if not content:
                raise ValueError("vacío")
            history.append({"role": "assistant", "content": content})
            return content
        except Exception as e:
            logger.warning(f"[JUAN] Groq intento {intento+1}/3: {e}")
            if "429" in str(e) and intento < 2:
                time.sleep(espera); espera *= 2
                continue
            break

    if history and history[-1]["role"] == "user":
        history.pop()
    return None


def _enviar_respuesta(bot, message, respuesta: str | None, chat_id: int, thread_id) -> None:
    if respuesta is None:
        return
    if respuesta.startswith("sticker::"):
        try:
            bot.send_sticker(chat_id, respuesta[9:], reply_to_message_id=message.message_id)
        except Exception as e:
            logger.warning(f"[JUAN] send_sticker falló: {e}")
        return
    try:
        bot.reply_to(message, respuesta)
    except Exception:
        try:
            bot.send_message(chat_id, respuesta, message_thread_id=thread_id)
        except Exception as e:
            logger.error(f"[JUAN] envío falló: {e}")


# ── Detección de triggers ─────────────────────────────────────────────────────

def _menciona_a_juan(message) -> bool:
    for e in (message.entities or message.caption_entities or []):
        if e.type == "mention":
            t = (message.text or message.caption or "")[e.offset: e.offset + e.length].lower()
            if t == f"@{BOT_USERNAME.lower()}":
                return True
    return False


def _es_reply_a_juan(message) -> bool:
    return (
        message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
        and (message.reply_to_message.from_user.username or "").lower() == BOT_USERNAME.lower()
    )


def _deberia_responder_juan(message) -> bool:
    try:
        texto = message.text or message.caption or ""
        if texto.startswith("/") or texto.startswith("!"):
            return False
        return _es_reply_a_juan(message) or _menciona_a_juan(message)
    except Exception:
        return False


# ── Comandos ! ────────────────────────────────────────────────────────────────

def _groq_simple(prompt: str, max_tokens: int = 200, temperature: float = 0.9) -> str:
    """Llamada Groq simple sin historial. Devuelve texto o string de error."""
    try:
        r = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": JUAN_SYSTEM_NEUTRO},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens, temperature=temperature,
        )
        return (r.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning(f"[JUAN] _groq_simple: {e}")
        return ""


def _cmd_pregunta(bot, message, chat_id: int, thread_id) -> None:
    """
    Genera una pregunta de trivia con 4 opciones usando Groq y la envía
    como encuesta nativa de Telegram (open_period=30s, anónima).
    Telegram cierra y muestra resultados automáticamente — sin tokens extra.
    """
    _TEMAS = [
        "cultura pop", "historia mundial", "ciencia y tecnología",
        "geografía", "deportes", "cine y series", "música",
        "videojuegos", "animales", "comida del mundo",
        "mitología", "espacio y astronomía",
    ]
    tema = random.choice(_TEMAS)
    seed = random.randint(1, 99999)

    raw = _groq_simple(
        f"Genera una pregunta de trivia ORIGINAL sobre {tema} (seed={seed}). "
        "Con exactamente 4 opciones, una sola correcta. Formato EXACTO (sin texto extra):\n"
        "PREGUNTA: [la pregunta]\n"
        "A: [opción correcta]\n"
        "B: [opción incorrecta]\n"
        "C: [opción incorrecta]\n"
        "D: [opción incorrecta]\n"
        "CORRECTA: A\n"
        "Español neutro. NO uses las preguntas más típicas del tema.",
        max_tokens=200,
        temperature=1.0,
    )

    if not raw:
        bot.reply_to(message, "Se me fue la pregunta de la cabeza. Intenta de nuevo.")
        return

    # ── Parsear la respuesta de Groq ──────────────────────────────────────────
    try:
        lines = {
            l.split(":", 1)[0].strip().upper(): l.split(":", 1)[1].strip()
            for l in raw.splitlines()
            if ":" in l
        }
        pregunta  = lines.get("PREGUNTA", "").strip()
        opciones  = [
            lines.get("A", "Opción A"),
            lines.get("B", "Opción B"),
            lines.get("C", "Opción C"),
            lines.get("D", "Opción D"),
        ]
        correcta_letra = lines.get("CORRECTA", "A").strip().upper()
        idx_correcta   = {"A": 0, "B": 1, "C": 2, "D": 3}.get(correcta_letra, 0)

        if not pregunta or any(not o for o in opciones):
            raise ValueError("Parseo incompleto")

    except Exception as e:
        logger.warning(f"[JUAN] !pregunta parseo falló: {e} | raw: {raw[:100]}")
        bot.reply_to(message, "La pregunta me salió rara. Intenta de nuevo.")
        return

    # ── Mezclar opciones (para que la correcta no siempre sea la A) ───────────
    import random as _rnd
    indices = list(range(4))
    _rnd.shuffle(indices)
    opciones_mezcladas = [opciones[i] for i in indices]
    # Encontrar dónde quedó la opción correcta después del shuffle
    idx_correcta_final = indices.index(idx_correcta)

    # ── Enviar encuesta nativa ────────────────────────────────────────────────
    try:
        kwargs = {
            "question":             f"🧠 {pregunta}",
            "options":              opciones_mezcladas,
            "type":                 "quiz",
            "correct_option_id":    idx_correcta_final,
            "is_anonymous":         True,
            "open_period":          30,
            "explanation":          "Pregunta generada por Juan 🐴",
        }
        if thread_id:
            kwargs["message_thread_id"] = thread_id

        bot.send_poll(chat_id, **kwargs)
        logger.info(f"[JUAN] Poll enviado en chat={chat_id}")

    except Exception as e:
        logger.error(f"[JUAN] send_poll falló: {e}")
        # Fallback: mostrar como texto si el poll falla
        letras = ["A", "B", "C", "D"]
        texto_fb = f"🧠 <b>{pregunta}</b>\n\n"
        for i, op in enumerate(opciones_mezcladas):
            marca = " ✅" if i == idx_correcta_final else ""
            texto_fb += f"{letras[i]}) {op}{marca}\n"
        msg_kwargs = {"parse_mode": "HTML"}
        if thread_id:
            msg_kwargs["message_thread_id"] = thread_id
        bot.send_message(chat_id, texto_fb, **msg_kwargs)


def _cmd_shipear(bot, message, args: str, chat_id: int, thread_id) -> None:
    # Extraer los dos argumentos
    partes = re.findall(r'@?\w+', args)
    partes = [p for p in partes if p.lower() not in ("shipear", "ship")]
    if len(partes) < 2:
        bot.reply_to(message, "Necesito dos personas para shipear. Ejemplo: !ship @Ana @Luis")
        return

    raw1 = partes[0].lstrip("@")
    raw2 = partes[1].lstrip("@")

    # ── Validar que ambos están en JUAN_MIEMBROS ──────────────────────────────
    m1 = _buscar_miembro(raw1)
    m2 = _buscar_miembro(raw2)

    desconocidos = []
    if not m1:
        desconocidos.append(f"@{raw1}" if not raw1.startswith("@") else raw1)
    if not m2:
        desconocidos.append(f"@{raw2}" if not raw2.startswith("@") else raw2)

    if desconocidos:
        nombres = " y ".join(desconocidos)
        bot.reply_to(
            message,
            f"No puedo shipear a {nombres} porque no los conozco. "
            f"Que un admin los registre primero con /juanagregar. 🐴"
        )
        return

    # Usar los nombres oficiales guardados en JUAN_MIEMBROS
    nombre1 = m1["nombre"]
    nombre2 = m2["nombre"]

    # ── Buscar ship existente (orden no importa) ──────────────────────────────
    clave = _clave_ship(nombre1, nombre2)
    ship  = _buscar_ship(clave)

    if ship:
        # Ship ya analizado: devolver el mismo veredicto
        footer = "\n<i>(Este veredicto ya fue sellado por el destino. No hay vuelta atrás.)</i>"
        kwargs = {"parse_mode": "HTML"}
        if thread_id:
            kwargs["message_thread_id"] = thread_id
        bot.send_message(
            chat_id,
            f"💘 <b>Ship Meter</b>\n\n"
            f"<b>{ship['nombre1']}</b> + <b>{ship['nombre2']}</b>\n"
            f"Compatibilidad: <b>{ship['porcentaje']}%</b> — {ship['nivel']}\n\n"
            f"<i>{ship['comentario']}</i>"
            f"{footer}",
            **kwargs,
        )
        return

    # ── Ship nuevo: generar y guardar ─────────────────────────────────────────
    pct = random.randint(1, 100)

    niveles = [
        (range(1,  20),  "💔 Incompatibles totales"),
        (range(20, 40),  "😬 Hay trabajo por hacer"),
        (range(40, 60),  "🤔 Potencial sospechoso"),
        (range(60, 80),  "💛 Buena onda"),
        (range(80, 95),  "💕 Combinación peligrosa"),
        (range(95, 101), "🔥 Destinados el uno al otro"),
    ]
    nivel = next((v for r, v in niveles if pct in r), "🤷")

    comentario = _groq_simple(
        f"Analiza la compatibilidad entre {nombre1} y {nombre2} "
        f"con un {pct}% de compatibilidad. "
        "Sé creativo, gracioso y un poco dramático. Máximo 3 líneas. Español neutro.",
        max_tokens=120, temperature=0.95,
    ) or "El oráculo ecuestre ha hablado."

    _guardar_ship(clave, nombre1, nombre2, pct, nivel, comentario)

    kwargs = {"parse_mode": "HTML"}
    if thread_id:
        kwargs["message_thread_id"] = thread_id
    bot.send_message(
        chat_id,
        f"💘 <b>Ship Meter</b>\n\n"
        f"<b>{nombre1}</b> + <b>{nombre2}</b>\n"
        f"Compatibilidad: <b>{pct}%</b> — {nivel}\n\n"
        f"<i>{comentario}</i>",
        **kwargs,
    )


def _cmd_horoscopo(bot, message, args: str, chat_id: int, thread_id) -> None:
    signo = args.strip().capitalize()
    if not signo:
        bot.reply_to(message, "¿Para qué signo? Ejemplo: !horoscopo Aries")
        return

    hoy = date.today().strftime("%d/%m/%Y")
    texto = _groq_simple(
        f"Escribe el horóscopo del día ({hoy}) para {signo}. "
        "Sé dramático, un poco absurdo y gracioso. Toca amor, trabajo y da un consejo ridículo. "
        "Máximo 4 líneas. Español neutro.",
        max_tokens=200,
    ) or "Las estrellas están en mantenimiento. Vuelve mañana."

    kwargs = {"parse_mode": "HTML"}
    if thread_id:
        kwargs["message_thread_id"] = thread_id
    bot.send_message(chat_id, f"🔮 <b>Horóscopo de Juan — {signo}</b>\n<i>{hoy}</i>\n\n{texto}", **kwargs)


def _cmd_top(bot, message, chat_id: int, thread_id) -> None:
    try:
        rows = db_manager.execute_query(
            "SELECT nombre, puntos FROM USUARIOS ORDER BY puntos DESC LIMIT 10"
        ) or []
    except Exception as e:
        bot.reply_to(message, "No pude cargar el ranking. La base de datos me odia hoy.")
        return

    if not rows:
        bot.reply_to(message, "Nadie tiene puntos todavía. Qué grupo tan tranquilo.")
        return

    medallas = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    lineas = [
        f"{medallas[i]} <b>{r.get('nombre','?')}</b> — {r.get('puntos',0)} pts"
        for i, r in enumerate(rows)
    ]

    resumen = "\n".join(
        f"{i+1}. {r.get('nombre','?')} con {r.get('puntos',0)} puntos"
        for i, r in enumerate(rows)
    )
    comentario = _groq_simple(
        f"El top del servidor es:\n{resumen}\n"
        "Haz un comentario gracioso sobre el ranking, especialmente el primero y el último. "
        "Máximo 2 líneas. Español neutro.",
        max_tokens=100,
    ) or "El caballo ha revisado los números."

    bot.send_message(
        chat_id,
        f"🏆 <b>Top del servidor</b>\n\n" + "\n".join(lineas) + f"\n\n<i>{comentario}</i>",
        parse_mode="HTML", message_thread_id=thread_id,
    )


# ── Sistema de aniversarios ───────────────────────────────────────────────────

def _verificar_aniversarios(bot) -> None:
    """
    Revisa USUARIOS buscando quién cumple aniversario de entrada hoy
    y envía un mensaje decorado al canal de anuncios configurado.
    """
    MEDALLAS = {1: "🥇", 2: "🥈", 3: "🥉"}
    BANDERAS  = ["🎊","🎉","✨","🌟","💫","🎈","🎀","🏆","👑","💎"]

    try:
        hoy = date.today()
        rows = db_manager.execute_query(
            "SELECT userID, nombre, nombre_usuario, registro FROM USUARIOS WHERE registro IS NOT NULL"
        ) or []

        for row in rows:
            try:
                reg_str = str(row.get("registro") or "").strip()
                if not reg_str:
                    continue

                fecha_reg = None
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
                    try:
                        fecha_reg = datetime.strptime(reg_str, fmt).date()
                        break
                    except ValueError:
                        continue
                if not fecha_reg:
                    continue

                if fecha_reg.day != hoy.day or fecha_reg.month != hoy.month:
                    continue
                if fecha_reg.year == hoy.year:
                    continue  # primer día, no es aniversario

                anos  = hoy.year - fecha_reg.year
                nombre   = row.get("nombre") or row.get("nombre_usuario") or "alguien"
                user_id  = row.get("userID") or row.get("userid")
                username = row.get("nombre_usuario") or ""

                # Ícono según años
                icono_anos = MEDALLAS.get(anos, "🌟")
                bandera    = random.choice(BANDERAS)

                # Buscar interacción memorable
                recuerdo = ""
                try:
                    frases = db_manager.execute_query(
                        "SELECT frase FROM JUAN_APRENDIZAJE "
                        "WHERE autor = ? AND frase NOT LIKE 'sticker::%' LIMIT 20",
                        (nombre,),
                    ) or []
                    if frases:
                        recuerdo = random.choice(frases)["frase"]
                except Exception:
                    pass

                # Prompt para Groq
                prompt = (
                    f"Hoy es el aniversario de {nombre} en el servidor. "
                    f"Lleva exactamente {anos} año{'s' if anos != 1 else ''} con esta comunidad. "
                )
                if recuerdo:
                    prompt += (
                        f"Un momento que recuerdo de él/ella: '{recuerdo}'. "
                        "Mencionalo de forma nostálgica y cariñosa en el mensaje. "
                    )
                prompt += (
                    "Escribe un mensaje de aniversario emotivo, cálido y especial. "
                    "No es un cumpleaños, es el aniversario de su llegada al servidor. "
                    "Expresa gratitud por los momentos compartidos, recuerda algo bonito "
                    "y hazlo sentir parte de la familia. Máximo 4 líneas. Español neutro."
                )

                cuerpo = _groq_simple(prompt, max_tokens=250, temperature=0.9)
                if not cuerpo:
                    cuerpo = (
                        f"Un año más de momentos, risas y locuras juntos. "
                        f"Gracias por ser parte de esto. 🐴"
                    )

                # Mención
                if username:
                    mencion = f"@{username}"
                elif user_id:
                    mencion = f'<a href="tg://user?id={user_id}">{nombre}</a>'
                else:
                    mencion = f"<b>{nombre}</b>"

                # Texto decorado
                separador = "· ─────────────────── ·"
                texto = (
                    f"{bandera}{bandera}{bandera} <b>ANIVERSARIO EN EL SERVIDOR</b> {bandera}{bandera}{bandera}\n"
                    f"{separador}\n\n"
                    f"{icono_anos} {mencion}\n"
                    f"<b>{anos} año{'s' if anos != 1 else ''} con nosotros</b>\n\n"
                    f"<i>{cuerpo}</i>\n\n"
                    f"{separador}\n"
                    f"<i>— con cariño, Juan 🐴</i>"
                )

                kwargs = {"parse_mode": "HTML"}
                if JUAN_THREAD_ANUNCIOS:
                    kwargs["message_thread_id"] = JUAN_THREAD_ANUNCIOS

                bot.send_message(CANAL_ID, texto, **kwargs)
                logger.info(f"[JUAN] Aniversario enviado: {nombre} ({anos} años)")

            except Exception as e:
                logger.warning(f"[JUAN] Error aniversario {row}: {e}")

    except Exception as e:
        logger.error(f"[JUAN] _verificar_aniversarios: {e}")


def _scheduler_aniversarios(bot) -> None:
    """Thread daemon que corre _verificar_aniversarios una vez al día a las 00:05."""
    def _loop():
        while True:
            ahora  = datetime.now()
            manana = datetime(ahora.year, ahora.month, ahora.day, 0, 5, 0) + timedelta(days=1)
            secs   = (manana - ahora).total_seconds()
            logger.info(f"[JUAN] Próxima verificación de aniversarios en {secs/3600:.1f}h")
            time.sleep(secs)
            _verificar_aniversarios(bot)

    # Verificar también al arrancar (por si el bot se reinició el mismo día del aniversario)
    threading.Thread(target=lambda: _verificar_aniversarios(bot), daemon=True).start()
    threading.Thread(target=_loop, daemon=True).start()


# ── Setup principal ────────────────────────────────────────────────────────────

def setup_juan_handler(bot) -> None:
    """Registra todos los handlers y arranca el scheduler de aniversarios."""

    _crear_tabla_ships()
    _scheduler_aniversarios(bot)

    # ── 1. Texto (unificado: comandos ! + conversación + aprendizaje pasivo) ──
    @bot.message_handler(
        content_types=["text"],
        func=lambda m: not (m.text or "").startswith("/"),
    )
    def juan_texto_handler(message):
        chat_id   = message.chat.id
        thread_id = get_thread_id(message)
        user_id   = message.from_user.id
        user_name = message.from_user.first_name or "alguien"
        texto     = message.text or ""

        # ── Comandos ! ────────────────────────────────────────────────────────
        if texto.strip().startswith("!"):
            partes = texto.strip().split(maxsplit=1)
            cmd    = partes[0].lower()
            args   = partes[1].strip() if len(partes) > 1 else ""

            try:
                if cmd in ("!pregunta", "!trivia", "!quiz"):
                    _cmd_pregunta(bot, message, chat_id, thread_id)
                elif cmd in ("!shipear", "!ship"):
                    _cmd_shipear(bot, message, args, chat_id, thread_id)
                elif cmd in ("!horoscopo", "!horóscopo", "!horo"):
                    _cmd_horoscopo(bot, message, args, chat_id, thread_id)
                elif cmd in ("!top", "!ranking"):
                    _cmd_top(bot, message, chat_id, thread_id)
            except Exception as e:
                logger.error(f"[JUAN] Error en comando {cmd}: {e}", exc_info=True)
                try:
                    bot.reply_to(message, "Algo salió mal. Intenta de nuevo.")
                except Exception:
                    pass

            try:
                _procesar_aprendizaje_texto(message)
            except Exception:
                pass
            return

        # ── Respuesta conversacional ──────────────────────────────────────────
        if _deberia_responder_juan(message):
            ahora = time.time()
            if ahora - _ultimo_uso.get(user_id, 0) < COOLDOWN_SEGUNDOS:
                logger.info(f"[JUAN] Cooldown user={user_id}")
            else:
                _ultimo_uso[user_id] = ahora
                prompt = f"{user_name} dice: {texto}"
                logger.info(f"[JUAN] chat={chat_id} | {prompt[:80]}")
                respuesta = _pedir_respuesta(chat_id, prompt, texto_original=texto)
                _enviar_respuesta(bot, message, respuesta, chat_id, thread_id)

        # Aprendizaje pasivo siempre
        try:
            _procesar_aprendizaje_texto(message)
        except Exception as e:
            logger.debug(f"[JUAN-LEARN] {e}")

    # ── 2. Fotos ──────────────────────────────────────────────────────────────
    @bot.message_handler(content_types=["photo"])
    def juan_foto_handler(message):
        try:
            _procesar_aprendizaje_texto(message)
        except Exception:
            pass
        if not _deberia_responder_juan(message):
            return
        chat_id   = message.chat.id
        thread_id = get_thread_id(message)
        user_id   = message.from_user.id
        user_name = message.from_user.first_name or "alguien"
        ahora = time.time()
        if ahora - _ultimo_uso.get(user_id, 0) < COOLDOWN_SEGUNDOS:
            return
        _ultimo_uso[user_id] = ahora
        texto  = message.caption or "[foto sin texto]"
        prompt = f"{user_name} manda una foto y dice: {texto}"
        _enviar_respuesta(bot, message, _pedir_respuesta(chat_id, prompt, texto), chat_id, thread_id)

    # ── 3. Stickers ───────────────────────────────────────────────────────────
    @bot.message_handler(content_types=["sticker"])
    def juan_sticker_handler(message):
        try:
            _procesar_aprendizaje_sticker(message)
        except Exception:
            pass
        if not _es_reply_a_juan(message):
            return
        chat_id   = message.chat.id
        thread_id = get_thread_id(message)
        user_id   = message.from_user.id
        user_name = message.from_user.first_name or "alguien"
        ahora = time.time()
        if ahora - _ultimo_uso.get(user_id, 0) < COOLDOWN_SEGUNDOS:
            return
        _ultimo_uso[user_id] = ahora
        aprendido = _get_frase_random("sticker")
        if aprendido and aprendido["frase"].startswith("sticker::"):
            _enviar_respuesta(bot, message, aprendido["frase"], chat_id, thread_id)
        else:
            emoji  = (message.sticker.emoji or "🎭") if message.sticker else "🎭"
            prompt = f"{user_name} te responde con un sticker {emoji}"
            _enviar_respuesta(bot, message, _pedir_respuesta(chat_id, prompt, emoji), chat_id, thread_id)

    # ── 4. Media ──────────────────────────────────────────────────────────────
    @bot.message_handler(content_types=["video", "audio", "voice", "document"])
    def juan_media_handler(message):
        if not _deberia_responder_juan(message):
            return
        chat_id   = message.chat.id
        thread_id = get_thread_id(message)
        user_id   = message.from_user.id
        user_name = message.from_user.first_name or "alguien"
        ahora = time.time()
        if ahora - _ultimo_uso.get(user_id, 0) < COOLDOWN_SEGUNDOS:
            return
        _ultimo_uso[user_id] = ahora
        tipo   = message.content_type
        texto  = message.caption or f"[{tipo}]"
        prompt = f"{user_name} manda un {tipo} y dice: {texto}"
        _enviar_respuesta(bot, message, _pedir_respuesta(chat_id, prompt, texto), chat_id, thread_id)

    # ── 5. Comandos de gestión ────────────────────────────────────────────────

    @bot.message_handler(commands=["resetjuan"])
    def juan_reset(message):
        _chat_histories.pop(message.chat.id, None)
        bot.reply_to(message, "Listo, memoria borrada. 🐴 ¿De qué hablábamos?")

    @bot.message_handler(commands=["juanagregar"])
    def juan_agregar(message):
        chat_id = message.chat.id
        try:
            if bot.get_chat_member(chat_id, message.from_user.id).status not in ("administrator", "creator"):
                bot.reply_to(message, "❌ Solo los admins."); return
            if not message.reply_to_message:
                bot.reply_to(message, "❌ Responde al mensaje del usuario:\n/juanagregar Nombre | descripción"); return
            t       = message.reply_to_message.from_user
            partes  = message.text.split(maxsplit=1)
            if len(partes) < 2:
                nombre_p, desc = t.first_name, ""
            elif "|" in partes[1]:
                nombre_p, desc = [x.strip() for x in partes[1].split("|", 1)]
            else:
                nombre_p, desc = partes[1].strip(), ""
            db_manager.execute_update(
                "INSERT INTO JUAN_MIEMBROS (user_id, nombre, username, descripcion) VALUES (?,?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET nombre=excluded.nombre, username=excluded.username, descripcion=excluded.descripcion",
                (t.id, nombre_p, t.username or "", desc),
            )
            bot.reply_to(message, f"✅ Juan ya conoce a *{nombre_p}* 🐴", parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"❌ Error: {e}")

    @bot.message_handler(commands=["juanolvidar"])
    def juan_olvidar(message):
        chat_id = message.chat.id
        try:
            if bot.get_chat_member(chat_id, message.from_user.id).status not in ("administrator", "creator"):
                bot.reply_to(message, "❌ Solo los admins."); return
            if not message.reply_to_message:
                bot.reply_to(message, "❌ Responde al mensaje del usuario."); return
            uid    = message.reply_to_message.from_user.id
            nombre = message.reply_to_message.from_user.first_name
            db_manager.execute_update("DELETE FROM JUAN_MIEMBROS WHERE user_id = ?", (uid,))
            bot.reply_to(message, f"🗑️ Juan ya no recuerda a *{nombre}*.", parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"❌ Error: {e}")

    @bot.message_handler(commands=["juanmiembros"])
    def juan_listar(message):
        ms = _get_todos_los_miembros()
        if not ms:
            bot.reply_to(message, "Juan no conoce a nadie todavía. 🐴"); return
        lineas = ["🐴 *Miembros que Juan conoce:*\n"]
        for m in ms:
            l = f"• *{m['nombre']}*"
            if m.get("username"):  l += f" (@{m['username']})"
            if m.get("descripcion"): l += f" — {m['descripcion']}"
            lineas.append(l)
        bot.reply_to(message, "\n".join(lineas), parse_mode="Markdown")

    @bot.message_handler(commands=["juanfrases"])
    def juan_frases(message):
        chat_id = message.chat.id
        try:
            if bot.get_chat_member(chat_id, message.from_user.id).status not in ("administrator", "creator"):
                bot.reply_to(message, "❌ Solo los admins."); return
            partes = message.text.split(maxsplit=1)
            if len(partes) == 1:
                rows = db_manager.execute_query(
                    "SELECT categoria, COUNT(*) as total FROM JUAN_APRENDIZAJE GROUP BY categoria"
                ) or []
                if not rows:
                    bot.reply_to(message, "Juan no aprendió nada todavía. 🐴"); return
                lineas = ["📚 *Frases aprendidas por Juan:*\n"]
                for r in rows:
                    lineas.append(f"• `{r['categoria']}`: {r['total']} frases")
                lineas.append("\nUsa `/juanfrases [categoria]` para verlas.")
                bot.reply_to(message, "\n".join(lineas), parse_mode="Markdown")
            else:
                cat  = partes[1].strip().lower()
                rows = db_manager.execute_query(
                    "SELECT id, frase, autor, fuente_username FROM JUAN_APRENDIZAJE WHERE categoria=? ORDER BY id DESC LIMIT 20",
                    (cat,),
                ) or []
                if not rows:
                    bot.reply_to(message, f"No hay frases en `{cat}`.", parse_mode="Markdown"); return
                lineas = [f"📚 *Frases [{cat}]* (últimas 20):\n"]
                for r in rows:
                    f_ = f" · @{r['fuente_username']}" if r.get("fuente_username") else ""
                    lineas.append(f"• _{r['frase']}_ — {r['autor']}{f_}")
                bot.reply_to(message, "\n".join(lineas), parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"❌ Error: {e}")

    @bot.message_handler(commands=["juanborrarfrase"])
    def juan_borrar_frase(message):
        chat_id = message.chat.id
        try:
            if bot.get_chat_member(chat_id, message.from_user.id).status not in ("administrator", "creator"):
                bot.reply_to(message, "❌ Solo los admins."); return
            if not message.reply_to_message:
                bot.reply_to(message, "❌ Responde al mensaje de Juan con la frase a borrar."); return
            rf = message.reply_to_message.from_user
            if not rf or (rf.username or "").lower() != BOT_USERNAME.lower():
                bot.reply_to(message, "❌ Responde a un mensaje de Juan."); return
            texto_juan = message.reply_to_message.text or message.reply_to_message.caption or ""
            rows = db_manager.execute_query("SELECT id, categoria, frase FROM JUAN_APRENDIZAJE") or []
            encontrada = next((r for r in rows if r["frase"] in texto_juan), None)
            if not encontrada:
                bot.reply_to(message, "❌ No encontré esa frase en la memoria de Juan."); return
            db_manager.execute_update("DELETE FROM JUAN_APRENDIZAJE WHERE id = ?", (encontrada["id"],))
            bot.reply_to(message, f"🗑️ Frase borrada de `{encontrada['categoria']}`.", parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"❌ Error: {e}")

    logger.info(
        "[OK] Juan handler v3 — comandos: !pregunta !shipear !horoscopo !top + aniversarios diarios"
    )
