# -*- coding: utf-8 -*-
"""
handlers/mercado_ofertas_handlers.py
════════════════════════════════════════════════════════════════════════════════
Handler del sistema P2P de Ofertas de Acciones — UniverseBot V2.0

Todos los comandos funcionan en MERCADO_THREAD (342521).

Comandos:
  /vender_acciones [SIM] [cant] [precio]    — Oferta pública
  /vender_a @user [SIM] [cant] [precio]     — Oferta directa a un usuario
  /ofertas [SIM]                            — Ver ofertas activas (todas o de un grupo)
  /mis_ofertas                              — Tus ofertas activas
  /ofertas_recibidas                        — Ofertas directas que te llegaron
  /comprar_oferta [ID]                      — Aceptar una oferta
  /cancelar_oferta [ID]                     — Cancelar tu oferta
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

import telebot
from telebot import types

from config import CANAL_ID, MSG_USUARIO_NO_REGISTRADO
from database import db_manager
from funciones import user_service
from funciones.mercado_service import mercado_service
from funciones.mercado_ofertas_service import (
    OFERTA_EXPIRA_HORAS,
    mercado_ofertas_service,
)

logger = logging.getLogger(__name__)

MERCADO_THREAD = 342521


class MercadoOfertasHandlers:

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.bot.register_message_handler(self.cmd_vender_acciones,   commands=["vender_acciones"])
        self.bot.register_message_handler(self.cmd_vender_a,          commands=["vender_a"])
        self.bot.register_message_handler(self.cmd_ofertas,           commands=["ofertas"])
        self.bot.register_message_handler(self.cmd_mis_ofertas,       commands=["mis_ofertas"])
        self.bot.register_message_handler(self.cmd_ofertas_recibidas, commands=["ofertas_recibidas"])
        self.bot.register_message_handler(self.cmd_comprar_oferta,    commands=["comprar_oferta"])
        self.bot.register_message_handler(self.cmd_cancelar_oferta,   commands=["cancelar_oferta"])
        self.bot.register_message_handler(self.cmd_rechazar_oferta,   commands=["rechazar_oferta"])
        # Botones inline ✅/❌ de las ofertas directas
        self.bot.register_callback_query_handler(
            self.cb_oferta,
            func=lambda c: bool(c.data) and c.data.startswith("mof:"),
        )

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _del(self, cid: int, mid: int) -> None:
        try:
            self.bot.delete_message(cid, mid)
        except Exception:
            pass

    def _del_after(self, cid: int, mid: int, delay: float = 60.0) -> None:
        threading.Timer(delay, lambda: self._del(cid, mid)).start()

    def _err(self, cid: int, txt: str, tid: Optional[int] = None, delay: float = 10.0) -> None:
        try:
            m = self.bot.send_message(cid, txt, parse_mode="HTML", message_thread_id=tid)
            self._del_after(cid, m.message_id, delay)
        except Exception:
            pass

    def _solo_mercado(self, message: telebot.types.Message) -> bool:
        if message.message_thread_id == MERCADO_THREAD:
            return True
        self._del(message.chat.id, message.message_id)
        self._err(
            message.chat.id,
            "📊 Este comando solo funciona en el canal de Mercado.",
            message.message_thread_id, 6.0,
        )
        return False

    def _get_nombre(self, uid: int) -> str:
        info = user_service.get_user_info(uid)
        return info.get("nombre", str(uid)) if info else str(uid)

    def _resolver_usuario(self, message: telebot.types.Message) -> Optional[tuple]:
        """Extrae (user_id, nombre) del primer @mention del mensaje."""
        for entity in (message.entities or []):
            if entity.type == "mention":
                username = message.text[entity.offset + 1: entity.offset + entity.length]
                rows = db_manager.execute_query(
                    "SELECT userID, nombre FROM USUARIOS WHERE nombre_usuario=?", (username,)
                )
                if rows:
                    return int(rows[0]["userID"]), rows[0]["nombre"]
            elif entity.type == "text_mention" and entity.user:
                uid   = entity.user.id
                nombre = self._get_nombre(uid)
                return uid, nombre
        return None

    def _render_oferta(self, o: dict, idx: Optional[int] = None) -> str:
        activo   = mercado_service.get_activo(o["simbolo"])
        nombre_g = activo.nombre if activo else o["simbolo"]
        precio_m = mercado_service.get_activo(o["simbolo"])
        precio_mercado = f"  <i>(mercado: {precio_m.precio_actual:,.0f} ✨)</i>" if precio_m else ""
        total    = int(o["cantidad"] * float(o["precio_unit"]))
        num      = f"<b>#{o['id']}</b>" if idx is None else f"<b>#{o['id']}</b>"
        directa  = f"  →  {o['comprador_nombre']}" if o.get("comprador_nombre") else ""
        return (
            f"{num}  {o['simbolo']} — {nombre_g}{directa}\n"
            f"   {o['cantidad']} acc. × <b>{float(o['precio_unit']):,.0f} ✨</b>/acc"
            f"{precio_mercado}\n"
            f"   Total: <b>{total:,} ✨</b>  |  Vendedor: {o['vendedor_nombre']}\n"
            f"   → <code>/comprar_oferta {o['id']}</code>"
        )

    def _anunciar_ceo(self, ceo_event: dict) -> None:
        try:
            tipo       = ceo_event.get("tipo")
            simbolo    = ceo_event.get("simbolo", "")
            nombre_g   = ceo_event.get("nombre_grupo", simbolo)
            nuevo      = ceo_event.get("nuevo_nombre", "")
            old_nombre = ceo_event.get("old_nombre", "")
            pct        = ceo_event.get("porcentaje", 0)
            if tipo == "nuevo":
                texto = f"👑 <b>¡NUEVO CEO!</b>\n\n<b>{nuevo}</b> se convirtió en CEO de <b>{nombre_g} ({simbolo})</b> con el <b>{pct:.1f}%</b> del supply."
            elif tipo == "takeover":
                texto = f"⚔️ <b>¡HOSTILE TAKEOVER!</b>\n\n<b>{nuevo}</b> desbancó a <b>{old_nombre}</b> y es el nuevo CEO de <b>{nombre_g} ({simbolo})</b>."
            elif tipo == "perdida":
                texto = f"📉 <b>{old_nombre}</b> perdió el título de CEO de <b>{nombre_g} ({simbolo})</b>."
            else:
                return
            self.bot.send_message(CANAL_ID, texto, parse_mode="HTML", message_thread_id=MERCADO_THREAD)
        except Exception:
            pass

    # ── Teclado inline de oferta directa ────────────────────────────────────────

    def _kb_oferta_directa(self, oferta_id: int, target_id: int) -> types.InlineKeyboardMarkup:
        """
        Botones ✅ Aceptar / ❌ Rechazar para el destinatario de una oferta directa.

        callback_data: mof:<accion>:<oferta_id>:<target_id>
          · accion ∈ {acc, rej}
          · target_id permite verificar que solo el destinatario use los botones.
        """
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton(
                "✅ Aceptar", callback_data=f"mof:acc:{oferta_id}:{target_id}"
            ),
            types.InlineKeyboardButton(
                "❌ Rechazar", callback_data=f"mof:rej:{oferta_id}:{target_id}"
            ),
        )
        return kb

    def cb_oferta(self, call: telebot.types.CallbackQuery) -> None:
        """Procesa los botones ✅/❌ de las ofertas directas."""
        try:
            partes = (call.data or "").split(":")
            # mof:<accion>:<oferta_id>:<target_id>
            if len(partes) != 4:
                self.bot.answer_callback_query(call.id, "Botón inválido.")
                return
            _, accion, oferta_id_s, target_id_s = partes
            oferta_id = int(oferta_id_s)
            target_id = int(target_id_s)
            uid = call.from_user.id

            # Solo el destinatario de la oferta puede usar estos botones.
            if uid != target_id:
                self.bot.answer_callback_query(
                    call.id, "🚫 Esta oferta no es para vos.", show_alert=True
                )
                return

            if not db_manager.user_exists(uid):
                self.bot.answer_callback_query(call.id, "Registrate primero.", show_alert=True)
                return

            nombre = self._get_nombre(uid)

            if accion == "rej":
                ok, err = mercado_ofertas_service.rechazar_oferta(uid, oferta_id)
                if not ok:
                    self.bot.answer_callback_query(call.id, f"❌ {err}", show_alert=True)
                    return
                self.bot.answer_callback_query(call.id, "Oferta rechazada.")
                self._editar_cerrada(call, f"❌ Oferta #{oferta_id} rechazada por <b>{nombre}</b>.")
                return

            if accion == "acc":
                ok, err, resumen = mercado_ofertas_service.aceptar_oferta(uid, nombre, oferta_id)
                if not ok:
                    self.bot.answer_callback_query(call.id, f"❌ {err}", show_alert=True)
                    return
                self.bot.answer_callback_query(call.id, "¡Trato cerrado!")
                self._editar_cerrada(
                    call,
                    f"✅ <b>¡Trato cerrado! — Oferta #{oferta_id}</b>\n\n"
                    f"📦 <b>{resumen['nombre_activo']} ({resumen['simbolo']})</b>\n"
                    f"   {resumen['cantidad']} acciones × <b>{resumen['precio_unit']:,.0f} ✨</b>/acc\n"
                    f"   Total: <b>{resumen['total']:,} ✨</b>\n\n"
                    f"💸 <b>{resumen['vendedor_nombre']}</b> recibió {resumen['total']:,} ✨\n"
                    f"📈 <b>{resumen['comprador_nombre']}</b> recibió {resumen['cantidad']} acciones",
                )
                if resumen.get("ceo_event"):
                    self._anunciar_ceo(resumen["ceo_event"])
                return

            self.bot.answer_callback_query(call.id, "Acción desconocida.")
        except Exception as exc:
            logger.error("[OFERTAS] cb_oferta: %s", exc, exc_info=True)
            try:
                self.bot.answer_callback_query(call.id, "❌ Error inesperado.", show_alert=True)
            except Exception:
                pass

    def _editar_cerrada(self, call: telebot.types.CallbackQuery, texto: str) -> None:
        """Reemplaza el mensaje de la oferta por el resultado y quita los botones."""
        try:
            self.bot.edit_message_text(
                texto,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="HTML",
            )
        except Exception:
            # Si no se puede editar (p. ej. mensaje viejo), al menos respondemos.
            try:
                self.bot.send_message(
                    call.message.chat.id, texto,
                    parse_mode="HTML", message_thread_id=MERCADO_THREAD,
                )
            except Exception:
                pass

    # ── /vender_acciones ──────────────────────────────────────────────────────

    def cmd_vender_acciones(self, message: telebot.types.Message) -> None:
        """
        /vender_acciones [SIMBOLO] [cantidad] [precio_por_accion]
        Crea una oferta PÚBLICA visible para todos.
        """
        if not self._solo_mercado(message):
            return
        cid = message.chat.id
        uid = message.from_user.id
        self._del(cid, message.message_id)
        try:
            if not db_manager.user_exists(uid):
                self._err(cid, MSG_USUARIO_NO_REGISTRADO, MERCADO_THREAD)
                return
            parts = (message.text or "").split()
            if len(parts) < 4:
                self._err(
                    cid,
                    "❌ Uso: <code>/vender_acciones [SIMBOLO] [cantidad] [precio/acc]</code>\n"
                    "Ej: <code>/vender_acciones BTS 5 9500</code>",
                    MERCADO_THREAD,
                )
                return
            try:
                cantidad   = int(parts[2])
                precio_u   = float(parts[3])
            except ValueError:
                self._err(cid, "❌ Cantidad y precio deben ser números.", MERCADO_THREAD)
                return

            nombre = self._get_nombre(uid)
            ok, err, oferta_id = mercado_ofertas_service.crear_oferta(
                uid, nombre, parts[1], cantidad, precio_u,
            )
            if not ok:
                self._err(cid, f"❌ {err}", MERCADO_THREAD)
                return
            if not oferta_id:
                self._err(cid, "❌ No se pudo crear la oferta (ID inválido). Intentá de nuevo.", MERCADO_THREAD)
                return

            activo = mercado_service.get_activo(parts[1].upper())
            total  = int(cantidad * precio_u)
            m = self.bot.send_message(
                cid,
                f"📢 <b>Oferta pública creada — #{oferta_id}</b>\n\n"
                f"📦 <b>{activo.nombre if activo else parts[1]} ({parts[1].upper()})</b>\n"
                f"   {cantidad} acciones × <b>{precio_u:,.0f} ✨</b>/acc\n"
                f"   Total: <b>{total:,} ✨</b>\n\n"
                f"Vendedor: <b>{nombre}</b>\n"
                f"Cualquier usuario puede aceptar con <code>/comprar_oferta {oferta_id}</code>",
                parse_mode="HTML", message_thread_id=MERCADO_THREAD,
            )
        except Exception as exc:
            logger.error("[OFERTAS] cmd_vender_acciones: %s", exc, exc_info=True)
            self._err(cid, f"❌ Error: <code>{exc}</code>", MERCADO_THREAD)

    # ── /vender_a ─────────────────────────────────────────────────────────────

    def cmd_vender_a(self, message: telebot.types.Message) -> None:
        """
        /vender_a @usuario [SIMBOLO] [cantidad] [precio_por_accion]
        Crea una oferta DIRECTA solo para ese usuario.
        """
        if not self._solo_mercado(message):
            return
        cid = message.chat.id
        uid = message.from_user.id
        self._del(cid, message.message_id)
        try:
            if not db_manager.user_exists(uid):
                self._err(cid, MSG_USUARIO_NO_REGISTRADO, MERCADO_THREAD)
                return

            target = self._resolver_usuario(message)
            if not target:
                self._err(
                    cid,
                    "❌ Uso: <code>/vender_a @usuario [SIMBOLO] [cantidad] [precio/acc]</code>\n"
                    "Ej: <code>/vender_a @maria BTS 5 9000</code>",
                    MERCADO_THREAD,
                )
                return
            target_id, target_nombre = target

            # Parsear argumentos después del @mention
            parts = (message.text or "").split()
            # Buscar los 3 parámetros: SIM, cant, precio (después del @)
            args = [p for p in parts[1:] if not p.startswith("@")]
            if len(args) < 3:
                self._err(
                    cid,
                    "❌ Uso: <code>/vender_a @usuario [SIMBOLO] [cantidad] [precio/acc]</code>",
                    MERCADO_THREAD,
                )
                return
            try:
                simbolo  = args[0]
                cantidad = int(args[1])
                precio_u = float(args[2])
            except ValueError:
                self._err(cid, "❌ Cantidad y precio deben ser números.", MERCADO_THREAD)
                return

            nombre = self._get_nombre(uid)
            ok, err, oferta_id = mercado_ofertas_service.crear_oferta(
                uid, nombre, simbolo, cantidad, precio_u,
                comprador_id=target_id, comprador_nombre=target_nombre,
            )
            if not ok:
                self._err(cid, f"❌ {err}", MERCADO_THREAD)
                return
            if not oferta_id:
                # Nunca mostrar "#0": la oferta no quedó identificable.
                self._err(cid, "❌ No se pudo crear la oferta (ID inválido). Intentá de nuevo.", MERCADO_THREAD)
                return

            activo = mercado_service.get_activo(simbolo.upper())
            total  = int(cantidad * precio_u)
            precio_mercado = activo.precio_actual if activo else None
            diferencia = ""
            if precio_mercado:
                diff_pct = ((precio_u - precio_mercado) / precio_mercado) * 100
                diferencia = f"\n   <i>Vs. precio de mercado: {diff_pct:+.1f}%</i>"

            self.bot.send_message(
                cid,
                f"🤝 <b>Oferta directa — #{oferta_id}</b>\n\n"
                f"De: <b>{nombre}</b>  →  Para: <b>{target_nombre}</b>\n\n"
                f"📦 <b>{activo.nombre if activo else simbolo} ({simbolo.upper()})</b>\n"
                f"   {cantidad} acciones × <b>{precio_u:,.0f} ✨</b>/acc\n"
                f"   Total: <b>{total:,} ✨</b>{diferencia}\n\n"
                f"<b>{target_nombre}</b>, respondé con los botones de abajo "
                f"(o <code>/comprar_oferta {oferta_id}</code> / "
                f"<code>/rechazar_oferta {oferta_id}</code>).\n"
                f"<i>Expira en {OFERTA_EXPIRA_HORAS} horas.</i>",
                parse_mode="HTML", message_thread_id=MERCADO_THREAD,
                reply_markup=self._kb_oferta_directa(oferta_id, target_id),
            )
        except Exception as exc:
            logger.error("[OFERTAS] cmd_vender_a: %s", exc, exc_info=True)
            self._err(cid, f"❌ Error: <code>{exc}</code>", MERCADO_THREAD)

    # ── /ofertas ──────────────────────────────────────────────────────────────

    def cmd_ofertas(self, message: telebot.types.Message) -> None:
        """
        /ofertas [SIMBOLO]  — Muestra ofertas públicas activas.
        Sin argumento muestra todas.
        """
        if not self._solo_mercado(message):
            return
        cid = message.chat.id
        self._del(cid, message.message_id)
        try:
            parts   = (message.text or "").split()
            simbolo = parts[1].upper() if len(parts) > 1 else None

            ofertas = mercado_ofertas_service.get_ofertas_publicas(simbolo)
            if not ofertas:
                titulo = f"de {simbolo}" if simbolo else "disponibles"
                self._err(cid, f"📋 No hay ofertas públicas {titulo} en este momento.", MERCADO_THREAD)
                return

            titulo = f"OFERTAS PÚBLICAS — {simbolo}" if simbolo else "OFERTAS PÚBLICAS"
            lineas = [f"📋 <b>{titulo}</b>\n"]
            for o in ofertas[:15]:  # máx 15 en pantalla
                lineas.append(self._render_oferta(o))

            if len(ofertas) > 15:
                lineas.append(f"\n<i>... y {len(ofertas) - 15} más. Filtrá por grupo: /ofertas BTS</i>")

            m = self.bot.send_message(
                cid, "\n\n".join(lineas),
                parse_mode="HTML", message_thread_id=MERCADO_THREAD,
            )
            self._del_after(cid, m.message_id, 90.0)
        except Exception as exc:
            logger.error("[OFERTAS] cmd_ofertas: %s", exc, exc_info=True)
            self._err(cid, f"❌ Error: <code>{exc}</code>", MERCADO_THREAD)

    # ── /mis_ofertas ──────────────────────────────────────────────────────────

    def cmd_mis_ofertas(self, message: telebot.types.Message) -> None:
        if not self._solo_mercado(message):
            return
        cid = message.chat.id
        uid = message.from_user.id
        self._del(cid, message.message_id)
        try:
            if not db_manager.user_exists(uid):
                self._err(cid, MSG_USUARIO_NO_REGISTRADO, MERCADO_THREAD)
                return
            ofertas = mercado_ofertas_service.get_mis_ofertas(uid)
            if not ofertas:
                self._err(cid, "📋 No tenés ofertas activas.", MERCADO_THREAD)
                return
            nombre = self._get_nombre(uid)
            lineas = [f"📋 <b>Tus ofertas activas — {nombre}</b>\n"]
            for o in ofertas:
                tipo   = "→ " + o["comprador_nombre"] if o.get("comprador_nombre") else "🌐 Pública"
                total  = int(o["cantidad"] * float(o["precio_unit"]))
                lineas.append(
                    f"<b>#{o['id']}</b>  {o['simbolo']}  {tipo}\n"
                    f"   {o['cantidad']} acc. × {float(o['precio_unit']):,.0f} ✨  |  "
                    f"Total: <b>{total:,} ✨</b>\n"
                    f"   → <code>/cancelar_oferta {o['id']}</code>"
                )
            m = self.bot.send_message(
                cid, "\n\n".join(lineas),
                parse_mode="HTML", message_thread_id=MERCADO_THREAD,
            )
            self._del_after(cid, m.message_id, 60.0)
        except Exception as exc:
            logger.error("[OFERTAS] cmd_mis_ofertas: %s", exc, exc_info=True)
            self._err(cid, f"❌ Error: <code>{exc}</code>", MERCADO_THREAD)

    # ── /ofertas_recibidas ────────────────────────────────────────────────────

    def cmd_ofertas_recibidas(self, message: telebot.types.Message) -> None:
        if not self._solo_mercado(message):
            return
        cid = message.chat.id
        uid = message.from_user.id
        self._del(cid, message.message_id)
        try:
            if not db_manager.user_exists(uid):
                self._err(cid, MSG_USUARIO_NO_REGISTRADO, MERCADO_THREAD)
                return
            ofertas = mercado_ofertas_service.get_ofertas_recibidas(uid)
            if not ofertas:
                self._err(cid, "📋 No tenés ofertas directas pendientes.", MERCADO_THREAD)
                return
            nombre = self._get_nombre(uid)
            lineas = [f"📬 <b>Ofertas directas para {nombre}</b>\n"]
            for o in ofertas:
                total = int(o["cantidad"] * float(o["precio_unit"]))
                lineas.append(
                    f"<b>#{o['id']}</b>  {o['simbolo']}  de <b>{o['vendedor_nombre']}</b>\n"
                    f"   {o['cantidad']} acc. × {float(o['precio_unit']):,.0f} ✨  |  "
                    f"Total: <b>{total:,} ✨</b>\n"
                    f"   ✅ <code>/comprar_oferta {o['id']}</code>   "
                    f"❌ <code>/rechazar_oferta {o['id']}</code>"
                )
            m = self.bot.send_message(
                cid, "\n\n".join(lineas),
                parse_mode="HTML", message_thread_id=MERCADO_THREAD,
            )
            self._del_after(cid, m.message_id, 60.0)
        except Exception as exc:
            logger.error("[OFERTAS] cmd_ofertas_recibidas: %s", exc, exc_info=True)
            self._err(cid, f"❌ Error: <code>{exc}</code>", MERCADO_THREAD)

    # ── /comprar_oferta ───────────────────────────────────────────────────────

    def cmd_comprar_oferta(self, message: telebot.types.Message) -> None:
        """
        /comprar_oferta [ID]
        Acepta la oferta con ese ID.
        """
        if not self._solo_mercado(message):
            return
        cid = message.chat.id
        uid = message.from_user.id
        self._del(cid, message.message_id)
        try:
            if not db_manager.user_exists(uid):
                self._err(cid, MSG_USUARIO_NO_REGISTRADO, MERCADO_THREAD)
                return
            parts = (message.text or "").split()
            if len(parts) < 2:
                self._err(cid, "❌ Uso: <code>/comprar_oferta [ID]</code>  ej: <code>/comprar_oferta 5</code>", MERCADO_THREAD)
                return
            try:
                oferta_id = int(parts[1])
            except ValueError:
                self._err(cid, "❌ El ID debe ser un número.", MERCADO_THREAD)
                return

            nombre = self._get_nombre(uid)
            ok, err, resumen = mercado_ofertas_service.aceptar_oferta(uid, nombre, oferta_id)
            if not ok:
                self._err(cid, f"❌ {err}", MERCADO_THREAD)
                return

            saldo_c = mercado_service.get_activo(resumen["simbolo"])
            self.bot.send_message(
                cid,
                f"✅ <b>¡Trato cerrado! — Oferta #{oferta_id}</b>\n\n"
                f"📦 <b>{resumen['nombre_activo']} ({resumen['simbolo']})</b>\n"
                f"   {resumen['cantidad']} acciones × <b>{resumen['precio_unit']:,.0f} ✨</b>/acc\n"
                f"   Total: <b>{resumen['total']:,} ✨</b>\n\n"
                f"💸 <b>{resumen['vendedor_nombre']}</b> recibió {resumen['total']:,} ✨\n"
                f"📈 <b>{resumen['comprador_nombre']}</b> recibió {resumen['cantidad']} acciones",
                parse_mode="HTML", message_thread_id=MERCADO_THREAD,
            )

            if resumen.get("ceo_event"):
                self._anunciar_ceo(resumen["ceo_event"])
        except Exception as exc:
            logger.error("[OFERTAS] cmd_comprar_oferta: %s", exc, exc_info=True)
            self._err(cid, f"❌ Error: <code>{exc}</code>", MERCADO_THREAD)

    # ── /cancelar_oferta ──────────────────────────────────────────────────────

    def cmd_cancelar_oferta(self, message: telebot.types.Message) -> None:
        if not self._solo_mercado(message):
            return
        cid = message.chat.id
        uid = message.from_user.id
        self._del(cid, message.message_id)
        try:
            parts = (message.text or "").split()
            if len(parts) < 2:
                self._err(cid, "❌ Uso: <code>/cancelar_oferta [ID]</code>", MERCADO_THREAD)
                return
            try:
                oferta_id = int(parts[1])
            except ValueError:
                self._err(cid, "❌ El ID debe ser un número.", MERCADO_THREAD)
                return

            ok, err = mercado_ofertas_service.cancelar_oferta(uid, oferta_id)
            if not ok:
                self._err(cid, f"❌ {err}", MERCADO_THREAD)
                return
            m = self.bot.send_message(
                cid,
                f"🚫 Oferta <b>#{oferta_id}</b> cancelada.",
                parse_mode="HTML", message_thread_id=MERCADO_THREAD,
            )
            self._del_after(cid, m.message_id, 10.0)
        except Exception as exc:
            logger.error("[OFERTAS] cmd_cancelar_oferta: %s", exc, exc_info=True)
            self._err(cid, f"❌ Error: <code>{exc}</code>", MERCADO_THREAD)

    # ── /rechazar_oferta ──────────────────────────────────────────────────────

    def cmd_rechazar_oferta(self, message: telebot.types.Message) -> None:
        """
        /rechazar_oferta [ID]
        El destinatario de una oferta directa la rechaza, liberando las
        acciones reservadas del vendedor.
        """
        if not self._solo_mercado(message):
            return
        cid = message.chat.id
        uid = message.from_user.id
        self._del(cid, message.message_id)
        try:
            if not db_manager.user_exists(uid):
                self._err(cid, MSG_USUARIO_NO_REGISTRADO, MERCADO_THREAD)
                return
            parts = (message.text or "").split()
            if len(parts) < 2:
                self._err(cid, "❌ Uso: <code>/rechazar_oferta [ID]</code>", MERCADO_THREAD)
                return
            try:
                oferta_id = int(parts[1])
            except ValueError:
                self._err(cid, "❌ El ID debe ser un número.", MERCADO_THREAD)
                return

            ok, err = mercado_ofertas_service.rechazar_oferta(uid, oferta_id)
            if not ok:
                self._err(cid, f"❌ {err}", MERCADO_THREAD)
                return
            nombre = self._get_nombre(uid)
            m = self.bot.send_message(
                cid,
                f"❌ Oferta <b>#{oferta_id}</b> rechazada por <b>{nombre}</b>.",
                parse_mode="HTML", message_thread_id=MERCADO_THREAD,
            )
            self._del_after(cid, m.message_id, 10.0)
        except Exception as exc:
            logger.error("[OFERTAS] cmd_rechazar_oferta: %s", exc, exc_info=True)
            self._err(cid, f"❌ Error: <code>{exc}</code>", MERCADO_THREAD)
