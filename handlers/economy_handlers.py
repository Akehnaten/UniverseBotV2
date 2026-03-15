# -*- coding: utf-8 -*-
"""
handlers/economy_handlers.py
FIX en cmd_puntos:
  - Usa user_id como llave (no username)
  - Soporta text_mention (usuarios sin @username)
  - Soporta @username como argumento

AGREGADO:
  - cmd_compravip  → /compravip
  - cmd_regalarvip → /regalarvip @usuario
"""

import telebot
import time
import logging

from funciones import economy_service, user_service
from config import MSG_USUARIO_NO_REGISTRADO, LOG_GROUP_ID
from utils.thread_utils import get_thread_id

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

# Costo en cosmos para obtener el VIP mensual (propio o regalo).
COSTO_VIP = 5000

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _delete_after(bot, chat_id: int, message_id: int, delay: float = 10.0) -> None:
    import threading
    def _del():
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass
    threading.Timer(delay, _del).start()


def _es_vip(user_info: dict) -> bool:
    """True si el nickname del usuario es exactamente 'VIP' (case-insensitive)."""
    return str(user_info.get("nickname", "")).upper() == "VIP"


class EconomyHandlers:
    """Handlers para comandos económicos"""

    def __init__(self, bot: telebot.TeleBot):
        self.bot = bot
        self._register_handlers()

    def _register_handlers(self):
        self.bot.register_message_handler(self.cmd_tablero,    commands=['tablero'])
        self.bot.register_message_handler(self.cmd_ranking,    commands=['ranking'])
        self.bot.register_message_handler(self.cmd_puntos,     commands=['puntos'])
        self.bot.register_message_handler(self.cmd_creditos,   commands=['cosmos'])
        self.bot.register_message_handler(self.cmd_transferir, commands=['transferir'])
        self.bot.register_message_handler(self.cmd_compravip,  commands=['compravip'])
        self.bot.register_message_handler(self.cmd_regalarvip, commands=['regalarvip'])

    # =========================================================================
    # /tablero
    # =========================================================================
    def cmd_tablero(self, message):
        cid = message.chat.id
        tid = get_thread_id(message)
        self.bot.delete_message(cid, message.message_id)

        try:
            parts  = message.text.split()
            limite = int(parts[1]) if len(parts) > 1 else 0
        except Exception:
            limite = 0

        texto = economy_service.get_leaderboard(limit=limite)
        m = self.bot.send_message(cid, texto, parse_mode='html', message_thread_id=tid)
        time.sleep(30)
        self.bot.delete_message(cid, m.message_id)

    # =========================================================================
    # /ranking
    # =========================================================================
    def cmd_ranking(self, message):
        cid = message.chat.id
        tid = get_thread_id(message)
        self.bot.delete_message(cid, message.message_id)

        try:
            parts  = message.text.split()
            limite = int(parts[1]) if len(parts) > 1 else 0
        except Exception:
            limite = 0

        from database import db_manager
        texto = db_manager.get_ranking_by_points(limit=limite)

        default = "<b><u>Lista de usuarios y sus Puntos:</u></b>\n\n"
        if texto == default:
            self.bot.send_message(
                cid, 'Aún no hay usuarios registrados.',
                message_thread_id=tid,
            )
        else:
            m = self.bot.send_message(cid, texto, parse_mode='html', message_thread_id=tid)
            time.sleep(30)
            self.bot.delete_message(cid, m.message_id)

    # =========================================================================
    # /puntos  [@usuario]
    # =========================================================================
    def cmd_puntos(self, message):
        """
        Muestra puntos del mes, roles del mes y cosmos del usuario.
        Si se menciona a alguien con @, muestra sus stats.

        La búsqueda en BD se hace SIEMPRE por userID (nunca por username).
        """
        cid = message.chat.id
        uid = message.from_user.id
        tid = get_thread_id(message)

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        from database import db_manager
        from funciones.user_utils import extraer_user_id, _es_reply_de_contexto_topic

        # ── Determinar usuario objetivo ────────────────────────────────────
        # BUG ANTERIOR:
        #   tiene_mencion = message.reply_to_message or (...)
        #   En grupos con Topics, reply_to_message SIEMPRE está seteado
        #   apuntando al mensaje de apertura del topic (creado por el owner).
        #   Esto hacía que todos los usuarios recibieran los stats del owner.
        #
        # CORRECCIÓN:
        #   1. Ignorar reply_to_message si es solo el contexto del topic.
        #   2. Pasar prefer_mention=True a extraer_user_id para que un
        #      @mention en el texto tenga prioridad sobre cualquier reply.
        tiene_mencion = (
            # Reply real (no el contexto automático del topic)
            (
                message.reply_to_message
                and not _es_reply_de_contexto_topic(message)
            )
            or
            # @mention o text_mention explícito en el texto
            (
                message.entities
                and any(
                    e.type in ("mention", "text_mention")
                    for e in message.entities
                )
            )
        )

        if tiene_mencion:
            target_id, display_o_error = extraer_user_id(
                message, self.bot, prefer_mention=True
            )
            if not target_id:
                m = self.bot.send_message(
                    cid, display_o_error or "❌ No pude identificar al usuario.",
                    message_thread_id=tid,
                )
                _delete_after(self.bot, cid, m.message_id)
                return

            row = db_manager.execute_query(
                "SELECT nombre, puntos, jugando, wallet FROM USUARIOS WHERE userID = ?",
                (target_id,),
            )
            if not row:
                m = self.bot.send_message(
                    cid, "❌ Ese usuario no está registrado.",
                    message_thread_id=tid,
                )
                _delete_after(self.bot, cid, m.message_id)
                return

            r           = row[0]
            target_name = r["nombre"]
            puntos      = r["puntos"]
            jugando     = r["jugando"]
            wallet      = r["wallet"]

        else:
            row = db_manager.execute_query(
                "SELECT nombre, puntos, jugando, wallet FROM USUARIOS WHERE userID = ?",
                (uid,),
            )
            if not row:
                m = self.bot.send_message(
                    cid, "❌ No estás registrado. Usa /registrar.",
                    message_thread_id=tid,
                )
                _delete_after(self.bot, cid, m.message_id)
                return

            r           = row[0]
            target_name = r["nombre"]
            puntos      = r["puntos"]
            jugando     = r["jugando"]
            wallet      = r["wallet"]

        texto = (
            f"📊 <b>Estadísticas de {target_name}</b>\n\n"
            f"🏆 Puntos del mes: <b>{puntos}</b>\n"
            f"🎭 Roles del mes:  <b>{jugando}</b>\n"
            f"✨ Cosmos:         <b>{wallet}</b>"
        )
        m = self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
        _delete_after(self.bot, cid, m.message_id, 30)

    # =========================================================================
    # /cosmos
    # =========================================================================
    def cmd_creditos(self, message):
        cid = message.chat.id
        uid = message.from_user.id
        tid = get_thread_id(message)

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        user_info = user_service.get_user_info(uid)
        if not user_info:
            texto = MSG_USUARIO_NO_REGISTRADO
        else:
            balance = economy_service.get_balance(uid)
            nombre  = user_info.get('nombre', 'Usuario')
            texto   = f"💰 <b>{nombre}</b>\nSaldo: <b>{balance}</b> Cosmos"

        m = self.bot.send_message(cid, texto, parse_mode='html', message_thread_id=tid)
        time.sleep(10)
        try:
            self.bot.delete_message(cid, m.message_id)
        except Exception:
            pass

    # =========================================================================
    # /transferir @usuario cantidad
    # =========================================================================
    def cmd_transferir(self, message):
        """
        /transferir @usuario cantidad
        Transfiere cosmos del emisor al destinatario.
        """
        cid = message.chat.id
        uid = message.from_user.id
        tid = get_thread_id(message)

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        def _err(texto: str, delay: int = 8):
            m = self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
            _delete_after(self.bot, cid, m.message_id, delay)

        # ── Validar registro ──────────────────────────────────────────────────
        user_info = user_service.get_user_info(uid)
        if not user_info:
            _err(MSG_USUARIO_NO_REGISTRADO)
            return

        # ── Parsear cantidad ──────────────────────────────────────────────────
        parts    = (message.text or "").split()
        cantidad = None
        for p in reversed(parts[1:]):
            try:
                cantidad = int(p)
                break
            except ValueError:
                continue

        if not cantidad or cantidad <= 0:
            _err(
                "❌ Uso: <code>/transferir @usuario cantidad</code>\n"
                "Ejemplo: <code>/transferir @ana 500</code>"
            )
            return

        # ── Resolver destinatario ─────────────────────────────────────────────
        # Estrategia idéntica a /cargar y /regalarvip:
        # parsear el @username del texto crudo primero para no depender del
        # autocomplete de Telegram. Solo si no hay @username se usa reply
        # como fallback legítimo (ej: /transferir 500 respondiendo a un mensaje).
        from funciones.user_utils import extraer_user_id, resolver_username_crudo
        from database import db_manager

        # `parts` ya fue declarado arriba para parsear `cantidad`
        mention_raw = next(
            (p.lstrip("@") for p in parts[1:] if p.startswith("@") and len(p) > 1),
            None,
        )

        if mention_raw:
            # Hay @username en el texto → resolverlo siempre desde texto crudo.
            # NUNCA hacer fallback a reply si falla: evita enviar a alguien
            # distinto al destinatario declarado.
            target_id = resolver_username_crudo(mention_raw, cid, self.bot)
            if not target_id:
                _err(
                    f"❌ No pude encontrar a <b>@{mention_raw}</b>.\n"
                    "Debe haber escrito en el grupo al menos una vez, "
                    "o respondé directamente a su mensaje."
                )
                return
            target_info = f"@{mention_raw}"
        else:
            # Sin @username → fallback a reply (uso legítimo: responder al
            # mensaje del destinatario y escribir /transferir 500)
            target_id, target_info = extraer_user_id(message, self.bot)
            if not target_id:
                _err(target_info or "❌ No pude identificar al usuario destinatario.")
                return

        if target_id == uid:
            _err("❌ No puedes transferirte cosmos a ti mismo.")
            return

        if not db_manager.user_exists(target_id):
            _err("❌ El destinatario no está registrado en el sistema.")
            return

        # ── Verificar saldo ───────────────────────────────────────────────────
        saldo = economy_service.get_balance(uid)
        if saldo < cantidad:
            _err(
                f"❌ Saldo insuficiente.\n"
                f"💳 Tienes: <b>{saldo} cosmos</b>\n"
                f"💸 Intentás transferir: <b>{cantidad} cosmos</b>"
            )
            return

        # ── Ejecutar transferencia ────────────────────────────────────────────
        ok = economy_service.transfer_credits(uid, target_id, cantidad)
        if not ok:
            _err("❌ Error al realizar la transferencia. Intenta de nuevo.")
            return

        dest_row    = db_manager.execute_query(
            "SELECT nombre FROM USUARIOS WHERE userID = ?", (target_id,)
        )
        dest_nombre = dest_row[0]["nombre"] if dest_row else str(target_id)
        nuevo_saldo = economy_service.get_balance(uid)

        texto = (
            f"✅ <b>Transferencia exitosa</b>\n\n"
            f"💸 Enviaste <b>{cantidad} cosmos</b> a <b>{dest_nombre}</b>\n"
            f"💳 Tu nuevo saldo: <b>{nuevo_saldo} cosmos</b>"
        )
        m = self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
        _delete_after(self.bot, cid, m.message_id, 15)

    # =========================================================================
    # /compravip
    # =========================================================================
    def cmd_compravip(self, message) -> None:
        """
        /compravip — El usuario compra el estado VIP para sí mismo por COSTO_VIP cosmos.

        Condiciones:
          · Debe estar registrado.
          · No debe tener ya VIP activo (nickname == 'VIP').
          · Debe tener saldo suficiente.

        Efecto:
          · Descuenta COSTO_VIP cosmos.
          · Setea nickname = 'VIP' en USUARIOS.
          · Envía log al grupo de administración.
        """
        cid = message.chat.id
        uid = message.from_user.id
        tid = get_thread_id(message)

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        def _err(texto: str, delay: int = 10):
            m = self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
            _delete_after(self.bot, cid, m.message_id, delay)

        # ── Validar registro ──────────────────────────────────────────────────
        user_info = user_service.get_user_info(uid)
        if not user_info:
            _err(MSG_USUARIO_NO_REGISTRADO)
            return

        nombre = user_info.get("nombre", str(uid))

        # ── Verificar que no sea ya VIP ───────────────────────────────────────
        if _es_vip(user_info):
            _err(
                "✨ <b>Ya tienes cuenta VIP activa.</b>\n"
                f"Se renueva automáticamente con /nuevomes."
            )
            return

        # ── Verificar saldo ───────────────────────────────────────────────────
        saldo = economy_service.get_balance(uid)
        if saldo < COSTO_VIP:
            _err(
                f"❌ <b>Cosmos insuficientes para VIP</b>\n\n"
                f"💰 Costo:  <b>{COSTO_VIP:,} cosmos</b>\n"
                f"💳 Tienes: <b>{saldo:,} cosmos</b>\n"
                f"🔻 Faltan: <b>{COSTO_VIP - saldo:,} cosmos</b>"
            )
            return

        # ── Descontar cosmos ──────────────────────────────────────────────────
        ok = economy_service.subtract_credits(uid, COSTO_VIP, "Compra VIP")
        if not ok:
            _err("❌ Error al procesar el pago. Inténtalo de nuevo.")
            return

        # ── Activar VIP en BD ─────────────────────────────────────────────────
        from database import db_manager
        try:
            db_manager.execute_update(
                "UPDATE USUARIOS SET nickname = 'VIP' WHERE userID = ?",
                (uid,),
            )
        except Exception as exc:
            # Revertir cobro si falla la BD
            economy_service.add_credits(uid, COSTO_VIP, "Reembolso VIP (error BD)")
            logger.error("[COMPRAVIP] Error al activar VIP para %s: %s", uid, exc)
            _err("❌ Error al activar el VIP. El pago fue revertido.")
            return

        nuevo_saldo = economy_service.get_balance(uid)
        logger.info("[COMPRAVIP] %s (%s) activó VIP — costo %s cosmos", nombre, uid, COSTO_VIP)

        # ── Respuesta al usuario ──────────────────────────────────────────────
        m = self.bot.send_message(
            cid,
            f"✨ <b>¡Cuenta VIP activada!</b>\n\n"
            f"👤 {nombre}\n"
            f"💸 Costo: <b>-{COSTO_VIP:,} cosmos</b>\n"
            f"💳 Saldo restante: <b>{nuevo_saldo:,} cosmos</b>\n\n"
            f"🎁 <b>Beneficios VIP:</b>\n"
            f"  • +25% puntos por rol\n"
            f"  • +25% ganancias en casino\n\n"
            f"<i>El VIP se resetea al inicio de cada mes con /nuevomes.</i>",
            parse_mode="HTML",
            message_thread_id=tid,
        )
        _delete_after(self.bot, cid, m.message_id, 30)

        # ── Log al grupo de administración ────────────────────────────────────
        try:
            self.bot.send_message(
                LOG_GROUP_ID,
                f"✨ #COMPRA_VIP\n"
                f"• Usuario: {nombre} [{uid}]\n"
                f"• Costo: {COSTO_VIP} cosmos\n"
                f"• Saldo tras compra: {nuevo_saldo} cosmos",
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.warning("[COMPRAVIP] No se pudo enviar log al grupo: %s", exc)

    # =========================================================================
    # /regalarvip @usuario
    # =========================================================================
    def cmd_regalarvip(self, message) -> None:
        """
        /regalarvip @usuario — El remitente paga el VIP para otro usuario.

        Condiciones:
          · El remitente debe estar registrado y tener saldo suficiente.
          · El destinatario debe estar registrado y NO tener VIP activo.
          · El destinatario se identifica igual que en /cargar:
              primero por @username en el texto crudo (no depende del autocomplete),
              luego por reply como fallback legítimo.

        Efecto:
          · Descuenta COSTO_VIP cosmos al remitente.
          · Setea nickname = 'VIP' en USUARIOS para el destinatario.
          · Envía log al grupo de administración.
        """
        cid = message.chat.id
        uid = message.from_user.id
        tid = get_thread_id(message)

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        def _err(texto: str, delay: int = 10):
            m = self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
            _delete_after(self.bot, cid, m.message_id, delay)

        # ── Validar remitente ─────────────────────────────────────────────────
        user_info = user_service.get_user_info(uid)
        if not user_info:
            _err(MSG_USUARIO_NO_REGISTRADO)
            return

        remitente_nombre = user_info.get("nombre", str(uid))

        # ── Resolver destinatario ─────────────────────────────────────────────
        # Misma estrategia que /cargar: texto crudo primero para no depender
        # del autocomplete de Telegram; reply como fallback legítimo.
        from funciones.user_utils import extraer_user_id, resolver_username_crudo
        from database import db_manager

        parts       = (message.text or "").split()
        mention_raw = next(
            (p.lstrip("@") for p in parts[1:] if p.startswith("@") and len(p) > 1),
            None,
        )

        target_id: int | None    = None
        target_nombre: str | None = None

        if mention_raw:
            target_id = resolver_username_crudo(mention_raw, cid, self.bot)
            if target_id:
                target_nombre = f"@{mention_raw}"
            else:
                _err(
                    f"❌ No pude encontrar a <b>@{mention_raw}</b>.\n"
                    "Debe haber escrito en el grupo al menos una vez, "
                    "o respondé directamente a su mensaje."
                )
                return
        else:
            # Sin @username → intentar por reply
            target_id, target_nombre_o_error = extraer_user_id(message, self.bot)
            if not target_id:
                _err(
                    target_nombre_o_error or
                    "❌ Mencioná al usuario con <b>@</b> o respondé a su mensaje.\n"
                    "Uso: <code>/regalarvip @usuario</code>"
                )
                return
            target_nombre = target_nombre_o_error

        # ── El remitente no puede regalarse VIP a sí mismo ───────────────────
        if target_id == uid:
            _err("❌ No puedes regalarte VIP a ti mismo. Usa <code>/compravip</code>.")
            return

        # ── Verificar que el destinatario esté registrado ─────────────────────
        target_info = user_service.get_user_info(target_id)
        if not target_info:
            _err("❌ Ese usuario no está registrado en el sistema.")
            return

        # Preferir el nombre guardado en BD sobre el display del resolver
        target_nombre = target_info.get("nombre", target_nombre)

        # ── Verificar que el destinatario no sea ya VIP ───────────────────────
        if _es_vip(target_info):
            _err(f"✨ <b>{target_nombre}</b> ya tiene cuenta VIP activa.")
            return

        # ── Verificar saldo del remitente ─────────────────────────────────────
        saldo = economy_service.get_balance(uid)
        if saldo < COSTO_VIP:
            _err(
                f"❌ <b>Cosmos insuficientes para regalar VIP</b>\n\n"
                f"💰 Costo:  <b>{COSTO_VIP:,} cosmos</b>\n"
                f"💳 Tienes: <b>{saldo:,} cosmos</b>\n"
                f"🔻 Faltan: <b>{COSTO_VIP - saldo:,} cosmos</b>"
            )
            return

        # ── Descontar cosmos al remitente ─────────────────────────────────────
        ok = economy_service.subtract_credits(uid, COSTO_VIP, f"Regalo VIP a {target_id}")
        if not ok:
            _err("❌ Error al procesar el pago. Inténtalo de nuevo.")
            return

        # ── Activar VIP en BD para el destinatario ────────────────────────────
        try:
            db_manager.execute_update(
                "UPDATE USUARIOS SET nickname = 'VIP' WHERE userID = ?",
                (target_id,),
            )
        except Exception as exc:
            economy_service.add_credits(uid, COSTO_VIP, "Reembolso regalo VIP (error BD)")
            logger.error("[REGALARVIP] Error al activar VIP para %s: %s", target_id, exc)
            _err("❌ Error al activar el VIP. El pago fue revertido.")
            return

        nuevo_saldo = economy_service.get_balance(uid)
        logger.info(
            "[REGALARVIP] %s (%s) regaló VIP a %s (%s) — costo %s cosmos",
            remitente_nombre, uid, target_nombre, target_id, COSTO_VIP,
        )

        # ── Respuesta en el grupo ─────────────────────────────────────────────
        m = self.bot.send_message(
            cid,
            f"🎁 <b>¡VIP regalado!</b>\n\n"
            f"✨ <b>{target_nombre}</b> ahora tiene cuenta VIP\n"
            f"💝 Cortesía de: <b>{remitente_nombre}</b>\n"
            f"💸 Costo: <b>-{COSTO_VIP:,} cosmos</b>\n"
            f"💳 Saldo restante de {remitente_nombre}: <b>{nuevo_saldo:,} cosmos</b>\n\n"
            f"<i>El VIP se resetea al inicio de cada mes con /nuevomes.</i>",
            parse_mode="HTML",
            message_thread_id=tid,
        )
        _delete_after(self.bot, cid, m.message_id, 30)

        # ── Log al grupo de administración ────────────────────────────────────
        try:
            self.bot.send_message(
                LOG_GROUP_ID,
                f"🎁 #REGALO_VIP\n"
                f"• De: {remitente_nombre} [{uid}]\n"
                f"• A: {target_nombre} [{target_id}]\n"
                f"• Costo: {COSTO_VIP} cosmos\n"
                f"• Saldo remitente tras regalo: {nuevo_saldo} cosmos",
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.warning("[REGALARVIP] No se pudo enviar log al grupo: %s", exc)