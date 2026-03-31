# -*- coding: utf-8 -*-
"""
handlers/apodo_handler.py
════════════════════════════════════════════════════════════════════════════════
Sistema de tags/apodos visibles en el grupo.

Usa setChatMemberTag a través de telebot.apihelper, la infraestructura HTTP
interna de pyTelegramBotAPI — no requiere `requests` directamente.
Funciona para miembros REGULARES del grupo (no solo admins).

Comandos:
  /apodo [texto]   Establece el apodo. Cuesta 3000 cosmos si tiene éxito.
  /apodo borrar    Elimina el apodo actual. Sin costo.
  /apodo           Muestra el apodo actual y la ayuda.

Requisito en Telegram:
  El bot debe ser administrador con el permiso "Manage Member Tags"
  (can_manage_tags) activado.

Caracteres permitidos en el tag (máx. 16):
  PERMITIDOS : letras de cualquier idioma, números, espacios, emoji
  BLOQUEADOS : signos de puntuación y caracteres especiales
               (. , ; : ! ? @ # $ % ^ & * ( ) [ ] { } | / \ ' " ` ~ + = _ -)
════════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
import threading
import unicodedata
from typing import Optional

import telebot
from telebot import apihelper

from config import MSG_USUARIO_NO_REGISTRADO, TELEGRAM_TOKEN
from database import db_manager
from funciones import economy_service, user_service
from utils.thread_utils import get_thread_id

logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────

COSTO_APODO: int  = 3000
_TAG_MAX_LEN: int = 16
_PALABRA_BORRAR   = "borrar"


# ══════════════════════════════════════════════════════════════════════════════
# VALIDACIÓN DE CARACTERES
# ══════════════════════════════════════════════════════════════════════════════

def _es_caracter_valido(ch: str) -> bool:
    """
    Retorna True si el carácter está permitido en un tag de Telegram.

    Categorías Unicode permitidas:
      L*  — Letras (cualquier idioma: latín, cirílico, kanji, árabe, etc.)
      N*  — Números (0-9 y equivalentes en otros sistemas)
      S*  — Símbolos (incluye la gran mayoría de emoji Unicode)
      Zs  — Separadores de espacio (espacio normal y variantes unicode)

    Bloqueadas:
      P*  — Puntuación (. , ; : ! ? " ' ` ( ) [ ] { } / \ @ # etc.)
      C*  — Caracteres de control e invisibles
      Zl, Zp — Separadores de línea y párrafo
    """
    if ch == " ":
        return True
    cat = unicodedata.category(ch)
    return cat.startswith(("L", "N", "S", "Zs"))


def validar_tag(tag: str) -> tuple[bool, str]:
    """
    Valida longitud y caracteres de un tag propuesto.

    Returns:
        (valido: bool, mensaje_error: str)  — mensaje vacío si es válido.
    """
    if not tag:
        return False, "El apodo no puede estar vacío."

    if len(tag) > _TAG_MAX_LEN:
        return False, (
            f"Apodo demasiado largo.\n\n"
            f"Máximo permitido: <b>{_TAG_MAX_LEN} caracteres</b>.\n"
            f"El tuyo tiene <b>{len(tag)}</b> caracteres."
        )

    chars_invalidos: list[str] = []
    for ch in tag:
        if not _es_caracter_valido(ch) and ch not in chars_invalidos:
            chars_invalidos.append(ch)

    if chars_invalidos:
        muestra = "  ".join(f"<code>{c}</code>" for c in chars_invalidos[:8])
        return False, (
            f"El apodo contiene caracteres no permitidos: {muestra}\n\n"
            f"<b>Permitidos:</b> letras, números, espacios y emoji.\n"
            f"<b>Bloqueados:</b> <code>. , ; : ! ? @ # $ % &amp; * ( ) [ ] "
            f"/ \\ ' \" ` ~ + = _ -</code>"
        )

    return True, ""


# ══════════════════════════════════════════════════════════════════════════════
# LLAMADA A LA API VÍA APIHELPER
# ══════════════════════════════════════════════════════════════════════════════

def _set_chat_member_tag(
    chat_id: int,
    user_id: int,
    tag: Optional[str],
) -> tuple[bool, str]:
    """
    Llama a setChatMemberTag usando telebot.apihelper._make_request.

    Usar apihelper en lugar de bot.set_chat_member_tag() nativo nos da
    certeza de que funciona en 4.32 aunque el wrapper de alto nivel tenga
    un nombre ligeramente distinto en alguna sub-versión.

    Args:
        chat_id : ID del grupo.
        user_id : ID del usuario.
        tag     : Texto del tag, o None / "" para borrar.

    Returns:
        (exito: bool, codigo_error: str)
    """
    params: dict = {"chat_id": chat_id, "user_id": user_id}
    if tag:
        params["tag"] = tag

    try:
        apihelper._make_request(TELEGRAM_TOKEN, "setChatMemberTag", params=params)
        return True, ""

    except telebot.apihelper.ApiTelegramException as exc:
        description = str(exc)
        logger.warning("[APODO] setChatMemberTag falló: %s", description)
        return False, _traducir_error(description)

    except Exception as exc:
        logger.error("[APODO] Error inesperado en setChatMemberTag: %s", exc)
        return False, f"error_inesperado:{exc}"


def _traducir_error(description: str) -> str:
    desc = description.lower()
    if "not enough rights" in desc or "can_manage_tags" in desc:
        return "sin_permiso"
    if "user is not a member" in desc:
        return "no_miembro"
    if "chat not found" in desc:
        return "chat_no_encontrado"
    if "user not found" in desc:
        return "usuario_no_encontrado"
    if "tag" in desc and ("invalid" in desc or "empty" in desc):
        return "tag_invalido_api"
    return f"api:{description}"


def _mensaje_error(codigo: str) -> str:
    if codigo == "sin_permiso":
        return (
            "El bot no tiene el permiso <b>Manage Member Tags</b> en este grupo.\n\n"
            "Un admin debe activarlo en:\n"
            "<i>Configuración → Administradores → [bot] → Manage Member Tags</i>"
        )
    if codigo == "no_miembro":
        return "El usuario ya no es miembro activo del grupo."
    if codigo == "chat_no_encontrado":
        return "No se encontró el grupo. Verificá que el bot siga siendo admin."
    if codigo == "usuario_no_encontrado":
        return "Telegram no pudo encontrar al usuario."
    if codigo == "tag_invalido_api":
        return "Telegram rechazó el tag. Probá con otro texto."
    return f"Error de Telegram: <code>{codigo}</code>"


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _delete_after(bot: telebot.TeleBot, chat_id: int, msg_id: int, delay: float) -> None:
    def _del() -> None:
        try:
            bot.delete_message(chat_id, msg_id)
        except Exception:
            pass
    threading.Timer(delay, _del).start()


def _try_delete(bot: telebot.TeleBot, chat_id: int, msg_id: int) -> None:
    try:
        bot.delete_message(chat_id, msg_id)
    except Exception:
        pass


def _guardar_titulo_bd(user_id: int, titulo: Optional[str]) -> bool:
    try:
        rows = db_manager.execute_update(
            "UPDATE USUARIOS SET titulo = ? WHERE userID = ?",
            (titulo, user_id),
        )
        return bool(rows and rows > 0)
    except Exception as exc:
        logger.error("[APODO] Error BD para %s: %s", user_id, exc)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# HANDLER PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

class ApodoHandler:

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        self.bot.register_message_handler(self.cmd_apodo, commands=["apodo"])

    def cmd_apodo(self, message: telebot.types.Message) -> None:
        """
        /apodo [texto | borrar]

        Flujo de cobro (solo aplica al establecer un apodo):
          1. ¿Usuario registrado?
          2. ¿Caracteres válidos?          → si no: error, SIN cobro
          3. ¿Saldo >= 3000 cosmos?        → si no: error, SIN cobro
          4. ¿API de Telegram responde OK? → si no: error, SIN cobro
          5. Todo OK → cobrar 3000 + guardar en BD + mensaje de éxito
        """
        cid = message.chat.id
        uid = message.from_user.id
        tid = get_thread_id(message)

        _try_delete(self.bot, cid, message.message_id)

        def _r(texto: str, delay: float = 10.0) -> None:
            m = self.bot.send_message(
                cid, texto, parse_mode="HTML", message_thread_id=tid,
            )
            _delete_after(self.bot, cid, m.message_id, delay)

        # ── 1. Usuario registrado ─────────────────────────────────────────────
        user_info = user_service.get_user_info(uid)
        if not user_info:
            _r(MSG_USUARIO_NO_REGISTRADO)
            return

        nombre = user_info.get("nombre") or message.from_user.first_name

        # ── 2. Parsear argumento ──────────────────────────────────────────────
        parts     = (message.text or "").split(maxsplit=1)
        argumento = parts[1].strip() if len(parts) > 1 else ""

        # ── Sin argumento: mostrar ayuda ──────────────────────────────────────
        if not argumento:
            apodo_actual = user_info.get("titulo") or None
            encabezado = (
                f"Tu apodo actual: <code>{apodo_actual}</code>\n\n"
                if apodo_actual
                else "No tenés ningún apodo configurado.\n\n"
            )
            _r(
                f"<b>🏷️ Apodos de grupo</b>\n\n"
                f"{encabezado}"
                f"<b>Uso:</b>\n"
                f"  <code>/apodo [texto]</code>  —  Establece tu apodo\n"
                f"  <code>/apodo borrar</code>    —  Elimina tu apodo\n\n"
                f"<b>💸 Costo:</b> {COSTO_APODO:,} cosmos "
                f"(solo si se aplica correctamente)\n"
                f"<b>📏 Máximo:</b> {_TAG_MAX_LEN} caracteres\n"
                f"<b>✅ Permitidos:</b> letras, números, espacios y emoji\n"
                f"<b>❌ Bloqueados:</b> signos de puntuación y caracteres especiales",
                delay=25.0,
            )
            return

        # ── BORRAR apodo ──────────────────────────────────────────────────────
        if argumento.lower() == _PALABRA_BORRAR:
            tg_ok, tg_error = _set_chat_member_tag(cid, uid, None)
            _guardar_titulo_bd(uid, None)   # limpiar BD siempre

            if tg_ok:
                _r("🗑️ <b>Apodo eliminado correctamente.</b>", delay=10.0)
            else:
                _r(
                    f"⚠️ <b>Apodo eliminado del sistema.</b>\n\n"
                    f"El tag de Telegram no pudo ser removido:\n"
                    f"{_mensaje_error(tg_error)}",
                    delay=20.0,
                )
            logger.info("[APODO] %s (%s) borró su apodo (TG=%s)", nombre, uid, tg_ok)
            return

        # ── ESTABLECER apodo ──────────────────────────────────────────────────

        # Paso 1: validar caracteres
        valido, msg_val = validar_tag(argumento)
        if not valido:
            _r(
                f"<b>❌ No se pudo aplicar el apodo.</b>\n\n{msg_val}",
                delay=15.0,
            )
            return

        # Paso 2: verificar saldo
        saldo = economy_service.get_balance(uid)
        if saldo < COSTO_APODO:
            _r(
                f"<b>❌ Cosmos insuficientes.</b>\n\n"
                f"💸 Costo del apodo: <b>{COSTO_APODO:,} cosmos</b>\n"
                f"💳 Tu saldo actual: <b>{saldo:,} cosmos</b>\n"
                f"🔻 Te faltan: <b>{COSTO_APODO - saldo:,} cosmos</b>",
                delay=12.0,
            )
            return

        # Paso 3: intentar aplicar en Telegram ANTES de cobrar
        tg_ok, tg_error = _set_chat_member_tag(cid, uid, argumento)

        if not tg_ok:
            _r(
                f"<b>❌ No se pudo aplicar el apodo.</b>\n\n"
                f"{_mensaje_error(tg_error)}\n\n"
                f"<i>No se te cobraron cosmos.</i>",
                delay=20.0,
            )
            logger.warning(
                "[APODO] %s (%s) '%s' falló (motivo=%s) sin cobro",
                nombre, uid, argumento, tg_error,
            )
            return

        # Paso 4: éxito en Telegram → cobrar y guardar en BD
        cobro_ok = economy_service.subtract_credits(
            uid, COSTO_APODO, f"Apodo: {argumento}"
        )
        _guardar_titulo_bd(uid, argumento)

        if cobro_ok:
            nuevo_saldo = economy_service.get_balance(uid)
            _r(
                f"<b>✅ ¡Apodo aplicado!</b>\n\n"
                f"👤 {nombre}\n"
                f"🏷️ <b>{argumento}</b>\n\n"
                f"💸 Costo: <b>-{COSTO_APODO:,} cosmos</b>\n"
                f"💳 Saldo restante: <b>{nuevo_saldo:,} cosmos</b>",
                delay=20.0,
            )
            logger.info(
                "[APODO] %s (%s) -> '%s' OK (-%d cosmos, saldo=%d)",
                nombre, uid, argumento, COSTO_APODO, nuevo_saldo,
            )
        else:
            # Rarísimo: TG OK pero subtract_credits falló
            logger.error(
                "[APODO] Tag aplicado en TG pero subtract_credits falló para %s", uid
            )
            _r(
                "⚠️ <b>Apodo aplicado, pero hubo un error al cobrar los cosmos.</b>\n"
                "Contactá a un administrador.",
                delay=20.0,
            )


def setup(bot: telebot.TeleBot) -> None:
    ApodoHandler(bot)
    logger.info("✅ ApodoHandler registrado.")
