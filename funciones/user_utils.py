# -*- coding: utf-8 -*-
"""
funciones/user_utils.py
════════════════════════════════════════════════════════════════════════════════
Utilidades para extracción y resolución de usuarios desde mensajes de Telegram.

Regla de oro
────────────
  La BD se consulta SIEMPRE con userID (inmutable).
  El @username se usa solo para display, nunca como clave final.

Orden de resolución
────────────────────
  1. reply_to_message  → from_user.id   (solo si es reply REAL, no contexto de topic)
  2. forward_from      → from_user.id   (userID directo)
  3. text_mention      → entity.user.id (userID directo, sin @)
  4. mention (@username)
       a. BD por nombre_usuario  (rápido, sin rate-limit)
       b. API get_chat_member    (fallback si no está en BD)
  5. Número de userID escrito en el texto (≥ 6 dígitos)

CAMBIOS en esta versión
───────────────────────
  - extraer_user_id: nuevo parámetro prefer_mention (default=False).
    Cuando True, las entities @mention/@text_mention tienen prioridad
    sobre reply_to_message y forward.  Necesario para /puntos @usuario y
    comandos admin que mencionan a alguien mientras responden a otro.

  - BUG RAÍZ CORREGIDO — reply_to_message en grupos con Topics (foro):
    En supergrupos con Topics, Telegram setea automáticamente
    reply_to_message en TODOS los mensajes apuntando al mensaje de
    apertura del topic (creado por el owner/admin). Esto hacía que
    cualquier comando resolviera siempre al creador del topic.
    Fix: se ignora reply_to_message cuando su message_id coincide con
    message_thread_id (señal de que es el reply automático del topic).
════════════════════════════════════════════════════════════════════════════════
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Resolución de @username → userID
# ─────────────────────────────────────────────────────────────────────────────

def _obtener_id_desde_username(username: str, chat_id: int, bot) -> Optional[int]:
    """
    Resuelve @username → userID.
    Estrategia: BD primero (sin rate-limit), API de Telegram como fallback.
    """
    username_limpio = username.lstrip("@").strip()
    if not username_limpio:
        return None

    # 1. BD por nombre_usuario ─────────────────────────────────────────────
    try:
        from database import db_manager
        result = db_manager.execute_query(
            "SELECT userID FROM USUARIOS WHERE LOWER(nombre_usuario) = LOWER(?)",
            (username_limpio,),
        )
        if result:
            row = result[0]
            uid = row["userID"] if isinstance(row, dict) else row[0]
            logger.debug("[USER_UTILS] '%s' resuelto por BD → %s", username_limpio, uid)
            return int(uid)
    except Exception as exc:
        logger.error(
            "[USER_UTILS] Error BD para '%s': %s: %s",
            username_limpio, type(exc).__name__, exc,
        )

    # 2. API de Telegram (fallback) ─────────────────────────────────────────
    try:
        member = bot.get_chat_member(chat_id, f"@{username_limpio}")
        if member and member.user:
            uid = member.user.id
            logger.debug("[USER_UTILS] '%s' resuelto por API → %s", username_limpio, uid)
            return uid
    except Exception as exc:
        logger.warning(
            "[USER_UTILS] get_chat_member falló para '@%s': %s: %s",
            username_limpio, type(exc).__name__, exc,
        )

    logger.warning("[USER_UTILS] No se pudo resolver '@%s' por ninguna vía", username_limpio)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Resolución de un username crudo (sin contexto de entity)
# ─────────────────────────────────────────────────────────────────────────────

def resolver_username_crudo(username: str, chat_id: int, bot) -> Optional[int]:
    """
    Igual que _obtener_id_desde_username pero público.
    Útil cuando se recibe un @username parseado manualmente del texto.
    """
    return _obtener_id_desde_username(username, chat_id, bot)


def _es_reply_de_contexto_topic(message) -> bool:
    """
    Detecta si reply_to_message es el reply automático de contexto de un
    Topic/Foro de Telegram, y NO un reply real hecho intencionalmente por
    el usuario.

    En supergrupos con Topics, Telegram setea reply_to_message en TODOS
    los mensajes del topic apuntando al mensaje de apertura del mismo.
    Si reply_to_message.message_id == message_thread_id, es ese reply
    automático de contexto — no indica intención del usuario — y debe
    ignorarse para no resolver siempre al creador del topic.

    Returns:
        True  → reply automático del topic (ignorar)
        False → reply real del usuario, o no hay reply, o sin info suficiente
    """
    reply = getattr(message, "reply_to_message", None)
    if reply is None:
        return False

    thread_id = getattr(message, "message_thread_id", None)
    if thread_id is None:
        return False

    try:
        es_contexto = int(reply.message_id) == int(thread_id)
        if es_contexto:
            logger.debug(
                "[USER_UTILS] reply_to_message.message_id=%s == message_thread_id=%s "
                "→ reply de contexto de topic, ignorado.",
                reply.message_id, thread_id,
            )
        return es_contexto
    except (TypeError, ValueError):
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Extracción principal del usuario objetivo
# ─────────────────────────────────────────────────────────────────────────────

def extraer_user_id(
    message,
    bot,
    prefer_mention: bool = False,
) -> Tuple[Optional[int], Optional[str]]:
    """
    Extrae el userID del usuario objetivo desde un mensaje de Telegram.

    Parámetros
    ----------
    message         : Mensaje de Telegram.
    bot             : Instancia del bot (para get_chat_member).
    prefer_mention  : Si True, las entities @mention y text_mention tienen
                      prioridad sobre reply y forward.
                      Útil en comandos como /puntos @pepito donde se quiere
                      explícitamente al usuario mencionado, no al autor del
                      mensaje al que se está respondiendo.

    Retorna
    -------
    (userID, display_name)  → éxito
    (None,   error_msg)     → fallo
    """
    try:
        cid = message.chat.id

        # ── prefer_mention: entities antes que reply/forward ──────────────
        if prefer_mention and message.entities:
            for entity in message.entities:
                if entity.type == "text_mention" and entity.user:
                    uid     = entity.user.id
                    display = (
                        f"@{entity.user.username}"
                        if entity.user.username
                        else entity.user.first_name
                    )
                    logger.debug(
                        "[USER_UTILS] prefer_mention text_mention → %s (%s)",
                        uid, display,
                    )
                    return uid, display

                if entity.type == "mention":
                    raw_text = message.text or ""
                    username = raw_text[entity.offset + 1 : entity.offset + entity.length]
                    if username:
                        uid = _obtener_id_desde_username(username, cid, bot)
                        if uid:
                            logger.debug(
                                "[USER_UTILS] prefer_mention mention → %s (@%s)",
                                uid, username,
                            )
                            return uid, f"@{username}"
                        # No se pudo resolver el username → informar y salir
                        return None, (
                            f"❌ No pude encontrar al usuario <b>@{username}</b>.\n"
                            "Debe haber escrito en el grupo para poder localizarlo.\n\n"
                            "Alternativa: responde directamente a su mensaje."
                        )

        # ── 1. Reply real (ignorar el reply automático de contexto de topic) ──
        if message.reply_to_message and not _es_reply_de_contexto_topic(message):
            target  = message.reply_to_message.from_user
            display = f"@{target.username}" if target.username else target.first_name
            logger.debug(
                "[USER_UTILS] Resuelto por reply → %s (%s)", target.id, display
            )
            return target.id, display

        # ── 2. Forward ────────────────────────────────────────────────────
        if getattr(message, "forward_from", None):
            target  = message.forward_from
            display = f"@{target.username}" if target.username else target.first_name
            logger.debug(
                "[USER_UTILS] Resuelto por forward → %s (%s)", target.id, display
            )
            return target.id, display

        # ── 3. text_mention entity ────────────────────────────────────────
        for entity in (message.entities or []):
            if entity.type == "text_mention" and entity.user:
                target = entity.user
                logger.debug(
                    "[USER_UTILS] Resuelto por text_mention → %s (%s)",
                    target.id, target.first_name,
                )
                return target.id, target.first_name

            # ── 4. mention entity (@username) ─────────────────────────────
            if entity.type == "mention":
                raw = (message.text or "")[entity.offset + 1 : entity.offset + entity.length]
                resolved_id = _obtener_id_desde_username(raw, cid, bot)
                if resolved_id:
                    logger.debug(
                        "[USER_UTILS] Resuelto por mention → %s (@%s)",
                        resolved_id, raw,
                    )
                    return resolved_id, f"@{raw}"

                return None, (
                    f"❌ No se pudo identificar a @{raw}.\n"
                    "Asegurate de que haya hablado en el grupo al menos una vez, "
                    "o respondé directamente su mensaje."
                )

        # ── 5. userID numérico en texto ───────────────────────────────────
        # IDs reales de Telegram comienzan desde ~100 000.
        for part in (message.text or "").split()[1:]:
            try:
                potential_id = int(part)
                if potential_id >= 100_000:
                    logger.debug(
                        "[USER_UTILS] Resuelto por ID numérico → %s", potential_id
                    )
                    return potential_id, str(potential_id)
            except ValueError:
                continue

        return None, (
            "❌ No encontré ningún usuario mencionado.\n\n"
            "Respondé su mensaje o mencionalo con @."
        )

    except Exception as exc:
        logger.error(
            "[USER_UTILS] Excepción inesperada en extraer_user_id: %s: %s",
            type(exc).__name__, exc,
            exc_info=True,
        )
        return None, "❌ Error interno al resolver el usuario."


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de formato
# ─────────────────────────────────────────────────────────────────────────────

def obtener_nombre_completo(user) -> str:
    nombre = user.first_name or ""
    if getattr(user, "last_name", None):
        nombre += f" {user.last_name}"
    return nombre.strip()


def formatear_user_link(user) -> str:
    nombre = obtener_nombre_completo(user)
    if getattr(user, "username", None):
        return f"[@{user.username}](tg://user?id={user.id})"
    return f"[{nombre}](tg://user?id={user.id})"


# ─────────────────────────────────────────────────────────────────────────────
# Wrapper con validación de registro
# ─────────────────────────────────────────────────────────────────────────────

def extraer_user_objetivo(
    message,
    bot,
    requiere_registrado: bool = True,
) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    """
    Extrae el usuario objetivo y, opcionalmente, verifica que esté registrado.

    Retorna:
        (user_id, display, None)       → éxito
        (None,    None,    error_msg)  → fallo
    """
    user_id, display_o_error = extraer_user_id(message, bot)

    if not user_id:
        return None, None, display_o_error

    if requiere_registrado:
        from funciones import user_service
        if not user_service.get_user_by_id(user_id):
            return None, None, "❌ Ese usuario no está registrado. Debe usar /registrar primero."

    return user_id, display_o_error, None


# ─────────────────────────────────────────────────────────────────────────────
# Decorador de conveniencia
# ─────────────────────────────────────────────────────────────────────────────

def with_target_user(requiere_registrado: bool = True):
    """
    Decorador que extrae y valida el usuario objetivo antes de llamar al handler.
    Uso:
        @with_target_user()
        def mi_handler(message, bot, user_id, display): ...
    """
    def decorator(func):
        def wrapper(message, bot):
            user_id, display, error = extraer_user_objetivo(
                message, bot, requiere_registrado
            )
            if error:
                bot.reply_to(message, error)
                return
            return func(message, bot, user_id, display)
        return wrapper
    return decorator
