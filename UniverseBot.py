# -*- coding: utf-8 -*-
"""
UniverseBot V2.0 - Bot de Telegram Completo
Sistema Pokémon, Economía, Photocards y más
"""

import sys
import os
from pathlib import Path

# Ruta base del proyecto
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Configurar logging
from utils.logging_config import setup_logging, get_logger
import logging

setup_logging(level=logging.INFO, log_file=str(BASE_DIR / 'universebot.log'))
logger = get_logger(__name__)

# Importar telebot
import telebot
from telebot import apihelper

# IMPORTANTE: Habilitar middleware ANTES de crear el bot
apihelper.ENABLE_MIDDLEWARE = True

from config import (
    DATABASE_PATH,
    TELEGRAM_TOKEN,
    ENTREVISTADORES,
    INVITADOS_TEMPORALES,
)

logger.info("="*60)
logger.info("[START] INICIANDO UNIVERSEBOT V2.0")
logger.info(f"[PATH] Directorio: {BASE_DIR}")
logger.info("="*60)

from database import db_manager
from funciones import user_service
from funciones.caja_misteriosa import caja_misteriosa

# Inicializar bot
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")
logger.info("[OK] Bot inicializado")

# Verificar/crear base de datos
if not os.path.exists(DATABASE_PATH) or os.path.getsize(DATABASE_PATH) == 0:
    logger.info("[DB] Base de datos no existe, creando...")
    db_manager.create_tables()
    logger.info("[OK] Tablas creadas")
else:
    logger.info("[OK] Base de datos existe")
    try:
        result = db_manager.execute_query("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
        if not result:
            logger.warning("[DB] Base de datos vacía, creando tablas...")
            db_manager.create_tables()
            logger.info("[OK] Tablas creadas")
        else:
            logger.info("[OK] Base de datos con tablas")
    except Exception as e:
        logger.error(f"[ERROR] Verificando BD: {e}")
        logger.info("[DB] Recreando tablas...")
        db_manager.create_tables()


def _es_admin_grupo(bot_ref, chat_id: int, user_id: int) -> bool:
    """Devuelve True si user_id es admin o propietario del chat."""
    try:
        member = bot_ref.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


def _get_thread_id(message) -> int | None:
    """
    Extrae el topic ID real de un mensaje en un supergrupo con Topics (foro).

    En grupos donde los Topics SIEMPRE estuvieron activos, Telegram codifica
    los mensajes de cada hilo como replies internos al mensaje de apertura
    del topic. pyTelegramBotAPI puede deserializar message_thread_id como
    None en algunos updates, dejando el ID real en reply_to_message.message_id.

    Estrategia (en orden):
        1. message.message_thread_id  → si existe y es > 0, retornarlo.
        2. Fallback via reply_to_message.message_id → solo si
           message.is_topic_message es True.

    Returns:
        int  → ID del topic al que pertenece el mensaje.
        None → el mensaje no pertenece a ningún topic (ej: chat privado).
    """
    # ── 1. Campo directo ──────────────────────────────────────────────────────
    raw = getattr(message, "message_thread_id", None)
    if raw is not None:
        try:
            tid = int(raw)
            if tid > 0:
                return tid
        except (TypeError, ValueError):
            logger.warning(
                "[THREAD_ID] Valor inesperado '%r' en message_thread_id "
                "(msg_id=%s) — intentando fallback.",
                raw, getattr(message, "message_id", "?"),
            )

    # ── 2. Fallback: reply_to_message cuando is_topic_message=True ───────────
    # Telegram marca is_topic_message=True en todos los mensajes de un topic.
    # El ID del topic está en el message_id del mensaje raíz (apertura del topic).
    if getattr(message, "is_topic_message", False):
        reply = getattr(message, "reply_to_message", None)
        if reply is not None:
            try:
                tid = int(reply.message_id)
                if tid > 0:
                    logger.debug(
                        "[THREAD_ID] Fallback activo: topic_id=%s obtenido de "
                        "reply_to_message.message_id (msg_id=%s)",
                        tid, getattr(message, "message_id", "?"),
                    )
                    return tid
            except (TypeError, ValueError):
                pass

    return None


def _eliminar_mensaje_seguro(bot, chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# MIDDLEWARE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

@bot.middleware_handler(update_types=['message'])
def check_user_and_channel(bot_instance, message):
    """
    Middleware principal.

    Responsabilidades (en orden de ejecución):
    1. Sincronizar nombre y nombre_usuario en USUARIOS para cada mensaje
       de un usuario ya registrado.
    2. Filtrar el canal ROLES: solo idols (clase='idol') y admins del grupo
       pueden escribir; el resto tiene su mensaje eliminado silenciosamente.
    3. Filtrar el canal ENTREVISTAS: igual que ROLES.
    4. Exigir registro para cualquier otro mensaje en grupo/supergrupo.
    5. Generar caja misteriosa con probabilidad configurada.
    6. Entregar recompensa diaria.
    """
    import threading
    from datetime import date
    from config import (
        RECOMPENSA_DIARIA, RECOMPENSA_DIARIA_P,
        PROBABILIDAD_CAJA_MISTERIOSA,
        CANAL_ENTREVISTAS, ENTREVISTADORES, INVITADOS_TEMPORALES,
        ROLES, ADMIN_IDS,
    )
    from funciones import economy_service

    user_id   = message.from_user.id
    chat_id   = message.chat.id
    chat_type = message.chat.type

    # ── 1. Sincronización silenciosa de datos de perfil ───────────────────────
    try:
        from funciones.user_service import user_service as _us
        _username = message.from_user.username or ""
        _nombre   = message.from_user.first_name or ""
        if message.from_user.last_name:
            _nombre += f" {message.from_user.last_name}"
        if db_manager.user_exists(user_id):
            _us.sync_user_data(user_id, _username, _nombre)
    except Exception as _sync_err:
        logger.warning(f"[MIDDLEWARE] Error en sync_user_data: {_sync_err}")

    # ── Solo aplicar filtros de canal en grupos ───────────────────────────────
    if chat_type not in ("group", "supergroup"):
        return  # Mensajes privados: no aplicar ningún filtro

    # FIX: usar _get_thread_id() en lugar de getattr directo para cubrir
    # el caso donde pyTelegramBotAPI no deserializa message_thread_id
    # correctamente en grupos con Topics siempre activos.
    thread_id = _get_thread_id(message)

    # ── 2. Filtro ROLES: solo idols y admins ──────────────────────────────────
    if thread_id == ROLES:
        if _es_admin_grupo(bot_instance, chat_id, user_id):
            return
        if user_id in ADMIN_IDS:
            return
        try:
            user_data = db_manager.get_user(user_id)
            if user_data and user_data.get("clase") == "idol":
                return
        except Exception as _roles_err:
            logger.warning(f"[MIDDLEWARE] Error verificando clase en ROLES: {_roles_err}")
        try:
            bot_instance.delete_message(chat_id, message.message_id)
        except Exception:
            pass
        return

    # ── 3. Filtro ENTREVISTAS ─────────────────────────────────────────────────
    if CANAL_ENTREVISTAS and thread_id == CANAL_ENTREVISTAS:
        if (user_id not in ENTREVISTADORES
                and user_id not in INVITADOS_TEMPORALES):
            try:
                bot_instance.delete_message(chat_id, message.message_id)
            except Exception:
                pass
            return

    # ── 4. Registro obligatorio ───────────────────────────────────────────────
    message_text      = message.text or message.caption or ""
    sin_registro_cmds = ("/registrar", "/start", "/help")
    if any(message_text.startswith(cmd) for cmd in sin_registro_cmds):
        return

    if not db_manager.user_exists(user_id):
        try:
            bot_instance.delete_message(chat_id, message.message_id)
            warning = bot_instance.send_message(
                chat_id,
                f"⚠️ {message.from_user.first_name}, debes registrarte primero.\n"
                f"Usa: /registrar cliente\n"
                f"o: /registrar idol [nombre]",
                message_thread_id=thread_id,
            )
            threading.Timer(
                10,
                lambda: _eliminar_mensaje_seguro(bot_instance, chat_id, warning.message_id),
            ).start()
        except Exception:
            pass
        return

    # ── 5. Caja misteriosa ────────────────────────────────────────────────────
    import random
    if random.random() <= PROBABILIDAD_CAJA_MISTERIOSA:
        try:
            caja_misteriosa.generar_caja(user_id, chat_id, bot_instance, thread_id)
        except Exception:
            pass

    # ── 6. Recompensa diaria ──────────────────────────────────────────────────
    if message.content_type in ("text", "photo", "video"):
        try:
            hoy       = str(date.today())
            resultado = db_manager.execute_query(
                "SELECT ultima_recompensa_diaria FROM USUARIOS WHERE userID = ?",
                (user_id,),
            )
            if resultado:
                ultima = resultado[0].get("ultima_recompensa_diaria")
                if ultima != hoy:
                    economy_service.add_credits(
                        user_id, RECOMPENSA_DIARIA, "Recompensa diaria"
                    )
                    db_manager.execute_update(
                        "UPDATE USUARIOS SET puntos = puntos + ? WHERE userID = ?",
                        (RECOMPENSA_DIARIA_P, user_id),
                    )
                    db_manager.execute_update(
                        "UPDATE USUARIOS SET ultima_recompensa_diaria = ? WHERE userID = ?",
                        (hoy, user_id),
                    )
                    if RECOMPENSA_DIARIA_P > 0:
                        from funciones.user_experience import aplicar_experiencia_usuario
                        aplicar_experiencia_usuario(
                            user_id, RECOMPENSA_DIARIA_P,
                            bot_instance, chat_id, thread_id,
                        )
        except Exception as _daily_err:
            logger.warning(f"[MIDDLEWARE] Error en recompensa diaria: {_daily_err}")


# ─────────────────────────────────────────────────────────────────────────────
# CALLBACKS Y COMANDOS DE ENTREVISTAS
# ─────────────────────────────────────────────────────────────────────────────

@bot.callback_query_handler(func=lambda call: call.data.startswith('opencaja_'))
def callback_abrir_caja(call):
    try:
        caja_misteriosa.abrir_caja(call, bot)
    except Exception as e:
        logger.error(f"[ERROR] Caja: {e}")


@bot.message_handler(commands=['aceptar_invitado'])
def cmd_aceptar_invitado(message):
    user_id = message.from_user.id
    if user_id not in ENTREVISTADORES:
        bot.reply_to(message, "❌ Sin permisos")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "⚠️ Responde al mensaje del usuario")
        return
    invitado_id = message.reply_to_message.from_user.id
    if invitado_id not in INVITADOS_TEMPORALES:
        INVITADOS_TEMPORALES.append(invitado_id)
        bot.reply_to(message, f"✅ {message.reply_to_message.from_user.first_name} aceptado")


@bot.message_handler(commands=['remover_invitado'])
def cmd_remover_invitado(message):
    user_id = message.from_user.id
    if user_id not in ENTREVISTADORES:
        bot.reply_to(message, "❌ Sin permisos")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "⚠️ Responde al mensaje del usuario")
        return
    invitado_id = message.reply_to_message.from_user.id
    if invitado_id in INVITADOS_TEMPORALES:
        INVITADOS_TEMPORALES.remove(invitado_id)
        bot.reply_to(message, f"✅ Removido")


logger.info("[OK] Middleware configurado")

# ─────────────────────────────────────────────────────────────────────────────
# SETUP DE HANDLERS Y SISTEMAS
# ─────────────────────────────────────────────────────────────────────────────

from handlers import setup_all_handlers
setup_all_handlers(bot)
logger.info("[OK] Handlers configurados")

# Spawns automáticos
try:
    from pokemon.spawn_manager_mejorado import inicializar_spawn_manager
    spawn_manager = inicializar_spawn_manager(bot)
    if spawn_manager:
        logger.info("[OK] Spawns automáticos iniciados")
    from pokemon.wild_battle_callbacks import setup_wild_battle_callbacks
    setup_wild_battle_callbacks(bot)
    logger.info("✅ Sistema de combate salvaje inicializado")

    from pokemon.mote_callbacks import setup_mote_callbacks
    setup_mote_callbacks(bot)
    logger.info("✅ Sistema de motes/apodos inicializado")

    from pokemon.guarderia_callbacks import setup_guarderia_callbacks
    setup_guarderia_callbacks(bot)
    logger.info("✅ Sistema de guardería inicializado")

except Exception as e:
    logger.warning(f"[WARN] Spawns: {e}")

# Sistema PvP / VGC
try:
    from pokemon.pvp_battle_callbacks import setup_pvp_callbacks
    setup_pvp_callbacks(bot)
    logger.info("✅ Callbacks PvP/VGC inicializados")

    # Registra /retar, pvp_fmt_*, pvp_accept/reject y el listener de @username
    from pokemon.pvp_battle_system import pvp_cmd
    pvp_cmd.register(bot)
    logger.info("✅ Comandos PvP (/retar, desafíos) registrados")
except Exception as e:
    logger.warning(f"[WARN] PvP: {e}")

# Sistema de uso de ítems con selector de Pokémon (piedras, mentas, chapas…)
try:
    from pokemon.item_use_system import register_item_use_callbacks
    register_item_use_callbacks(bot)
    logger.info("✅ Callbacks de uso de ítems registrados")
except Exception as e:
    logger.warning(f"[WARN] item_use_callbacks: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# ARRANQUE
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from config import (
        WEBHOOK_URL,
        WEBHOOK_HOST,
        WEBHOOK_PORT,
        WEBHOOK_SECRET_TOKEN,
    )
 
    if WEBHOOK_URL:
        logger.info("[START] Modo: WEBHOOK")
        logger.info("[START] URL pública: %s", WEBHOOK_URL)
        from webhook_server import start_webhook
        start_webhook(
            bot=bot,
            webhook_url=WEBHOOK_URL,
            host=WEBHOOK_HOST,
            port=WEBHOOK_PORT,
            secret_token=WEBHOOK_SECRET_TOKEN,
        )
    else:
        # Fallback: polling para desarrollo local sin ngrok
        logger.warning("[START] WEBHOOK_URL no configurado — usando polling (fallback).")
        bot.infinity_polling(timeout=60, long_polling_timeout=60)