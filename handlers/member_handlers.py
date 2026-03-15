# -*- coding: utf-8 -*-
"""
handlers/member_handlers.py
══════════════════════════════════════════════════════════════════════════════
Maneja los eventos de entrada y salida de miembros del grupo.

Responsabilidades:
  · new_chat_members  → Si el usuario está en EXMIEMBROS, restaurar todos sus
                        datos a USUARIOS (reintegro completo).
  · left_chat_member  → Mover todos los datos del usuario de USUARIOS a
                        EXMIEMBROS, registrando si fue expulsado o salió solo.

Criterio de distinción ban vs. salida voluntaria:
  - Si message.from_user.id != left_user.id → fue expulsado/baneado por
    otro usuario (admin o bot).
  - Si message.from_user.id == left_user.id → salió por su propia voluntad.

Integración en UniverseBot.py:
    from handlers.member_handlers import setup_member_handlers
    setup_member_handlers(bot)
══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

import telebot
from telebot import types

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS PRIVADOS
# ─────────────────────────────────────────────────────────────────────────────

def _borrar_seguro(bot: telebot.TeleBot, chat_id: int, message_id: int) -> None:
    """Elimina un mensaje de forma silenciosa."""
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass


def _temp_msg(
    bot: telebot.TeleBot,
    chat_id: int,
    texto: str,
    thread_id: Optional[int] = None,
    delay: float = 8.0,
) -> None:
    """Envía un mensaje y lo elimina tras `delay` segundos (non-blocking)."""
    try:
        kwargs: dict = {"parse_mode": "HTML"}
        if thread_id:
            kwargs["message_thread_id"] = thread_id
        m = bot.send_message(chat_id, texto, **kwargs)
        threading.Timer(delay, lambda: _borrar_seguro(bot, chat_id, m.message_id)).start()
    except Exception as exc:
        logger.warning(f"[MEMBER_HANDLERS] Error enviando mensaje temporal: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# HANDLER: ENTRADA DE MIEMBRO
# ─────────────────────────────────────────────────────────────────────────────

def _handle_new_member(message: types.Message, bot: telebot.TeleBot) -> None:
    """
    Procesa cada nuevo miembro que entra al grupo.

    Flujo:
      1. Para cada usuario en new_chat_members:
         a. Si está en EXMIEMBROS → restaurar a USUARIOS (reintegro completo).
         b. Si NO está en ninguna tabla → primer ingreso, nada que hacer
            (el usuario deberá registrarse con /registrar).
    """
    from database import db_manager

    chat_id   = message.chat.id
    thread_id = getattr(message, "message_thread_id", None)

    members = message.new_chat_members or []
    for new_user in members:
        user_id    = new_user.id
        first_name = new_user.first_name or "Usuario"

        try:
            # ── Ignorar al propio bot ─────────────────────────────────────────
            if new_user.is_bot:
                continue

            # ── Verificar si es un exmiembro que regresa ──────────────────────
            if db_manager.user_in_exmembers(user_id):
                exito = _restaurar_exmiembro(bot, user_id, new_user)
                if exito:
                    logger.info(
                        f"[MEMBER_HANDLERS] Usuario {user_id} ({first_name}) "
                        f"restaurado de EXMIEMBROS a USUARIOS."
                    )
                    _temp_msg(
                        bot, chat_id,
                        f"🎉 ¡Bienvenido de nuevo, <b>{first_name}</b>!\n"
                        f"<i>Tu cuenta ha sido reactivada.</i>",
                        thread_id=thread_id,
                        delay=15.0,
                    )
                else:
                    logger.error(
                        f"[MEMBER_HANDLERS] Falló la restauración de {user_id}."
                    )
            else:
                logger.debug(
                    f"[MEMBER_HANDLERS] Nuevo miembro {user_id} ({first_name}) "
                    f"no está en EXMIEMBROS — primer ingreso o ya registrado."
                )

        except Exception as exc:
            logger.error(
                f"[MEMBER_HANDLERS] Error procesando nuevo miembro {user_id}: {exc}",
                exc_info=True,
            )


def _restaurar_exmiembro(
    bot: telebot.TeleBot,
    user_id: int,
    tg_user: types.User,
) -> bool:
    """
    Mueve todos los datos de EXMIEMBROS a USUARIOS, actualizando nombre y
    username con los valores actuales de Telegram si difieren.

    La tabla EXMIEMBROS tiene las mismas columnas que USUARIOS excepto que
    tiene 'motivo' en vez de 'pasos_guarderia' y 'ultima_recompensa_diaria'.
    El INSERT reconstruye un registro completo en USUARIOS.

    Returns:
        True si la operación fue exitosa.
    """
    from database import db_manager

    try:
        # Obtener datos guardados en EXMIEMBROS
        resultado = db_manager.execute_query(
            "SELECT * FROM EXMIEMBROS WHERE userID = ?",
            (user_id,),
        )
        if not resultado:
            logger.warning(f"[MEMBER_HANDLERS] {user_id} no encontrado en EXMIEMBROS.")
            return False

        ex = dict(resultado[0])

        # Actualizar nombre y username con la info más reciente de Telegram
        nombre_actual   = tg_user.first_name or ""
        if tg_user.last_name:
            nombre_actual += f" {tg_user.last_name}"
        username_actual = tg_user.username or ""

        # Usar INSERT OR REPLACE para evitar conflictos si el usuario ya existe
        # por alguna otra vía (registro manual, etc.)
        db_manager.execute_update(
            """
            INSERT OR REPLACE INTO USUARIOS (
                userID, nombre_usuario, nombre, clase, idol,
                puntos, material, registro, wallet,
                jugando, encola, enrol, nickname, passwd,
                rol_hist, nivel, experiencia,
                pasos_guarderia, ultima_recompensa_diaria
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?,
                0, NULL
            )
            """,
            (
                ex["userID"],
                username_actual,
                nombre_actual,
                ex.get("clase", "cliente"),
                ex.get("idol"),
                ex.get("puntos", 0),
                ex.get("material"),
                ex.get("registro"),
                ex.get("wallet", 0),
                0,  # jugando → resetear a 0 al reingresar
                0,  # encola  → resetear
                0,  # enrol   → resetear
                ex.get("nickname"),
                ex.get("passwd"),
                ex.get("rol_hist", 0),
                ex.get("nivel", 1),
                ex.get("experiencia", 0),
            ),
        )

        # Eliminar de EXMIEMBROS solo si el INSERT fue exitoso
        db_manager.execute_update(
            "DELETE FROM EXMIEMBROS WHERE userID = ?",
            (user_id,),
        )

        logger.info(
            f"[MEMBER_HANDLERS] {user_id} reintegrado: "
            f"nombre='{nombre_actual}', username='{username_actual}'"
        )
        return True

    except Exception as exc:
        logger.error(
            f"[MEMBER_HANDLERS] Error restaurando exmiembro {user_id}: {exc}",
            exc_info=True,
        )
        return False


# ─────────────────────────────────────────────────────────────────────────────
# HANDLER: SALIDA DE MIEMBRO
# ─────────────────────────────────────────────────────────────────────────────

def _handle_left_member(message: types.Message, bot: telebot.TeleBot) -> None:
    """
    Procesa la salida de un miembro del grupo.

    Casos:
      · message.from_user.id == left_user.id  → salida voluntaria
      · message.from_user.id != left_user.id  → expulsado/baneado por un admin

    Solo actúa si el usuario está registrado en USUARIOS.
    Si ya estaba en EXMIEMBROS (no debería ocurrir), se omite para evitar
    duplicados.
    """
    from database import db_manager

    left_user = message.left_chat_member
    if left_user is None:
        return

    user_id    = left_user.id
    first_name = left_user.first_name or "Usuario"

    try:
        # ── Ignorar al propio bot ─────────────────────────────────────────────
        if left_user.is_bot:
            return

        # ── Verificar que el usuario esté registrado ──────────────────────────
        if not db_manager.user_exists(user_id):
            logger.debug(
                f"[MEMBER_HANDLERS] {user_id} ({first_name}) salió pero no "
                f"estaba registrado — no se hace nada."
            )
            return

        # ── Evitar duplicados ─────────────────────────────────────────────────
        if db_manager.user_in_exmembers(user_id):
            logger.warning(
                f"[MEMBER_HANDLERS] {user_id} ya estaba en EXMIEMBROS — "
                f"eliminando de USUARIOS para mantener consistencia."
            )
            db_manager.execute_update(
                "DELETE FROM USUARIOS WHERE userID = ?", (user_id,)
            )
            return

        # ── Determinar motivo ─────────────────────────────────────────────────
        actor_id = message.from_user.id if message.from_user else user_id
        if actor_id != user_id:
            actor_name = (
                message.from_user.first_name
                if message.from_user
                else "Admin"
            )
            motivo = f"Expulsado por {actor_name}"
        else:
            motivo = "Salida voluntaria"

        # ── Mover a EXMIEMBROS ────────────────────────────────────────────────
        exito = _mover_a_exmiembros(user_id, motivo)

        if exito:
            logger.info(
                f"[MEMBER_HANDLERS] {user_id} ({first_name}) → EXMIEMBROS. "
                f"Motivo: '{motivo}'"
            )
        else:
            logger.error(
                f"[MEMBER_HANDLERS] Falló el movimiento de {user_id} a EXMIEMBROS."
            )

    except Exception as exc:
        logger.error(
            f"[MEMBER_HANDLERS] Error procesando salida de {user_id}: {exc}",
            exc_info=True,
        )


def _mover_a_exmiembros(user_id: int, motivo: str) -> bool:
    """
    Copia todos los datos del usuario de USUARIOS a EXMIEMBROS y luego
    elimina la fila de USUARIOS.

    Preserva: userID, nombre_usuario, nombre, clase, idol, puntos, material,
              registro, wallet, jugando, encola, enrol, nickname, passwd,
              rol_hist, nivel, experiencia.
    Agrega:   motivo (razón de salida).

    Usa una transacción implícita vía execute_update para garantizar
    atomicidad.
    """
    from database import db_manager

    try:
        # Obtener datos actuales del usuario
        resultado = db_manager.execute_query(
            "SELECT * FROM USUARIOS WHERE userID = ?",
            (user_id,),
        )
        if not resultado:
            logger.warning(f"[MEMBER_HANDLERS] {user_id} no encontrado en USUARIOS.")
            return False

        u = dict(resultado[0])

        # Insertar en EXMIEMBROS (INSERT OR REPLACE por si existe de antes)
        db_manager.execute_update(
            """
            INSERT OR REPLACE INTO EXMIEMBROS (
                userID, nombre_usuario, nombre, clase, idol,
                puntos, material, registro, wallet,
                jugando, encola, enrol, nickname, passwd,
                rol_hist, nivel, experiencia, motivo
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?
            )
            """,
            (
                u["userID"],
                u.get("nombre_usuario", ""),
                u.get("nombre", ""),
                u.get("clase", "cliente"),
                u.get("idol"),
                u.get("puntos", 0),
                u.get("material"),
                u.get("registro"),
                u.get("wallet", 0),
                u.get("jugando", 0),
                u.get("encola", 0),
                u.get("enrol", 0),
                u.get("nickname"),
                u.get("passwd"),
                u.get("rol_hist", 0),
                u.get("nivel", 1),
                u.get("experiencia", 0),
                motivo,
            ),
        )

        # Eliminar de USUARIOS
        db_manager.execute_update(
            "DELETE FROM USUARIOS WHERE userID = ?",
            (user_id,),
        )

        return True

    except Exception as exc:
        logger.error(
            f"[MEMBER_HANDLERS] Error en _mover_a_exmiembros({user_id}): {exc}",
            exc_info=True,
        )
        return False


# ─────────────────────────────────────────────────────────────────────────────
# PUNTO DE ENTRADA
# ─────────────────────────────────────────────────────────────────────────────

def setup_member_handlers(bot: telebot.TeleBot) -> None:
    """
    Registra los handlers de eventos de miembros en el bot.

    Llamar desde UniverseBot.py una sola vez, tras crear la instancia del bot:

        from handlers.member_handlers import setup_member_handlers
        setup_member_handlers(bot)
    """

    @bot.message_handler(content_types=["new_chat_members"])
    def on_new_member(message: types.Message) -> None:
        _handle_new_member(message, bot)

    @bot.message_handler(content_types=["left_chat_member"])
    def on_left_member(message: types.Message) -> None:
        _handle_left_member(message, bot)

    @bot.chat_member_handler()
    def on_chat_member_update(update: types.ChatMemberUpdated) -> None:
        """
        Captura cambios de estado de miembros (incluyendo baneos).
        Telegram envía esto cuando un usuario es baneado, desbaneado,
        promovido, degradado, etc.
        """
        try:
            new_status = update.new_chat_member.status   # "kicked", "left", "member", etc.
            old_status = update.old_chat_member.status

            user    = update.new_chat_member.user
            user_id = user.id

            if user.is_bot:
                return

            # Solo actuar cuando el usuario SALE o es BANEADO
            # (old_status era member/admin/creator y new es kicked/left)
            ESTADOS_DENTRO = {"member", "administrator", "creator", "restricted"}
            ESTADOS_FUERA  = {"kicked", "left"}

            if old_status in ESTADOS_DENTRO and new_status in ESTADOS_FUERA:
                from database import db_manager

                if not db_manager.user_exists(user_id):
                    return

                if db_manager.user_in_exmembers(user_id):
                    db_manager.execute_update(
                        "DELETE FROM USUARIOS WHERE userID = ?", (user_id,)
                    )
                    return

                # Determinar quién realizó la acción
                actor    = update.from_user
                actor_id = actor.id if actor else user_id

                if new_status == "kicked":
                    if actor_id != user_id:
                        motivo = f"Baneado por {actor.first_name if actor else 'Admin'}"
                    else:
                        motivo = "Salida voluntaria"
                else:
                    motivo = "Salida voluntaria"

                exito = _mover_a_exmiembros(user_id, motivo)
                if exito:
                    logger.info(
                        f"[MEMBER_HANDLERS] (chat_member) {user_id} "
                        f"({user.first_name}) → EXMIEMBROS. Motivo: {motivo}"
                    )

        except Exception as exc:
            logger.error(
                f"[MEMBER_HANDLERS] Error en on_chat_member_update: {exc}",
                exc_info=True,
            )

    logger.info(
        "[MEMBER_HANDLERS] Handlers de new_chat_members, left_chat_member "
        "y chat_member (baneos) registrados."
    )