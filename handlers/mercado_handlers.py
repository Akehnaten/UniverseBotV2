# -*- coding: utf-8 -*-
"""
handlers/mercado_handlers.py
════════════════════════════════════════════════════════════════════════════════
Handler del Mercado de Cosmos para UniverseBot V2.0

Comandos (cualquier hilo del grupo):
  /mercado              — Tabla de precios actuales con tendencia
  /comprar [SIM] [N]    — Compra N acciones del activo SIM
  /vender [SIM] [N]     — Vende N acciones del activo SIM
  /portfolio            — Tus posiciones actuales + P&L
  /ranking_mercado      — Top 10 inversores por valor de portfolio
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import math
import threading
from typing import Optional

import telebot

from config import MSG_USUARIO_NO_REGISTRADO
from database import db_manager
from funciones import user_service
from funciones.mercado_service import mercado_service

logger = logging.getLogger(__name__)


class MercadoHandlers:
    """Handler del Mercado. Una instancia por proceso."""

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        self._register_handlers()
        mercado_service.iniciar_loop()   # arranca el loop de precios

    def _register_handlers(self) -> None:
        self.bot.register_message_handler(self.cmd_mercado,         commands=["mercado"])
        self.bot.register_message_handler(self.cmd_comprar,         commands=["comprar"])
        self.bot.register_message_handler(self.cmd_vender,          commands=["vender"])
        self.bot.register_message_handler(self.cmd_portfolio,       commands=["portfolio"])
        self.bot.register_message_handler(self.cmd_ranking_mercado, commands=["ranking_mercado"])

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _del(self, cid: int, mid: int) -> None:
        try:
            self.bot.delete_message(cid, mid)
        except Exception:
            pass

    def _del_after(self, cid: int, mid: int, delay: float = 30.0) -> None:
        threading.Timer(delay, lambda: self._del(cid, mid)).start()

    def _err(self, cid: int, txt: str, tid: Optional[int] = None, delay: float = 10.0) -> None:
        m = self.bot.send_message(cid, txt, parse_mode="HTML", message_thread_id=tid)
        self._del_after(cid, m.message_id, delay)

    def _get_nombre(self, uid: int) -> str:
        info = user_service.get_user_info(uid)
        return info.get("nombre", "Usuario") if info else "Usuario"

    # ── /mercado ──────────────────────────────────────────────────────────────

    def cmd_mercado(self, message: telebot.types.Message) -> None:
        """Muestra la tabla de precios actuales con tendencia."""
        cid = message.chat.id
        tid = message.message_thread_id

        self._del(cid, message.message_id)

        activos = mercado_service.get_activos()

        lineas = ["📊 <b>MERCADO DE COSMOS</b>\n"]
        for a in activos:
            variacion = f"{a.variacion_pct:+.1f}%"
            lineas.append(
                f"{a.emoji_tendencia} <b>{a.simbolo}</b>  {a.nombre}\n"
                f"   💰 <b>{a.precio_actual:,.0f} ✨</b>  <i>({variacion})</i>"
            )

        lineas.append(
            "\n<i>Precios se actualizan cada hora.</i>\n"
            "📥 <code>/comprar [SIM] [cant]</code>  |  📤 <code>/vender [SIM] [cant]</code>"
        )

        m = self.bot.send_message(
            cid, "\n".join(lineas), parse_mode="HTML", message_thread_id=tid
        )
        self._del_after(cid, m.message_id, 60.0)

    # ── /comprar ──────────────────────────────────────────────────────────────

    def cmd_comprar(self, message: telebot.types.Message) -> None:
        """
        /comprar [SIMBOLO] [cantidad]

        Ej: /comprar BTS 10
        """
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        self._del(cid, message.message_id)

        if not db_manager.user_exists(uid):
            self._err(cid, MSG_USUARIO_NO_REGISTRADO, tid)
            return

        parts = (message.text or "").split()
        if len(parts) < 3:
            self._err(
                cid,
                "❌ Uso: <code>/comprar [SIMBOLO] [cantidad]</code>\n"
                "Ej: <code>/comprar BTS 5</code>\n\n"
                "Usá <code>/mercado</code> para ver los símbolos disponibles.",
                tid,
            )
            return

        simbolo = parts[1].upper()
        try:
            cantidad = int(parts[2])
        except ValueError:
            self._err(cid, "❌ La cantidad debe ser un número entero.", tid)
            return

        nombre = self._get_nombre(uid)
        ok, err, costo = mercado_service.comprar(uid, simbolo, cantidad)

        if not ok:
            self._err(cid, f"❌ {err}", tid)
            return

        activo = mercado_service.get_activo(simbolo)
        m = self.bot.send_message(
            cid,
            f"✅ <b>{nombre}</b> compró <b>{cantidad} acciones</b> de "
            f"<b>{activo.nombre if activo else simbolo}</b>\n"
            f"💸 Costo total: <b>{int(costo):,} ✨</b>\n"
            f"📊 Precio unitario: <b>{activo.precio_actual:,.0f} ✨</b>",
            parse_mode="HTML",
            message_thread_id=tid,
        )
        self._del_after(cid, m.message_id, 20.0)

    # ── /vender ───────────────────────────────────────────────────────────────

    def cmd_vender(self, message: telebot.types.Message) -> None:
        """
        /vender [SIMBOLO] [cantidad]

        Ej: /vender BTS 5
        """
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        self._del(cid, message.message_id)

        if not db_manager.user_exists(uid):
            self._err(cid, MSG_USUARIO_NO_REGISTRADO, tid)
            return

        parts = (message.text or "").split()
        if len(parts) < 3:
            self._err(
                cid,
                "❌ Uso: <code>/vender [SIMBOLO] [cantidad]</code>\n"
                "Ej: <code>/vender BTS 5</code>",
                tid,
            )
            return

        simbolo = parts[1].upper()
        try:
            cantidad = int(parts[2])
        except ValueError:
            self._err(cid, "❌ La cantidad debe ser un número entero.", tid)
            return

        nombre = self._get_nombre(uid)
        ok, err, ingreso = mercado_service.vender(uid, simbolo, cantidad)

        if not ok:
            self._err(cid, f"❌ {err}", tid)
            return

        activo = mercado_service.get_activo(simbolo)
        m = self.bot.send_message(
            cid,
            f"💹 <b>{nombre}</b> vendió <b>{cantidad} acciones</b> de "
            f"<b>{activo.nombre if activo else simbolo}</b>\n"
            f"💰 Ingreso total: <b>{int(ingreso):,} ✨</b>\n"
            f"📊 Precio unitario: <b>{activo.precio_actual:,.0f} ✨</b>",
            parse_mode="HTML",
            message_thread_id=tid,
        )
        self._del_after(cid, m.message_id, 20.0)

    # ── /portfolio ────────────────────────────────────────────────────────────

    def cmd_portfolio(self, message: telebot.types.Message) -> None:
        """Muestra el portfolio del usuario: holdings, valor y P&L."""
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        self._del(cid, message.message_id)

        if not db_manager.user_exists(uid):
            self._err(cid, MSG_USUARIO_NO_REGISTRADO, tid)
            return

        nombre     = self._get_nombre(uid)
        posiciones = mercado_service.get_portfolio(uid)

        if not posiciones:
            self._err(
                cid,
                f"📭 <b>{nombre}</b>, no tenés acciones todavía.\n"
                "Usá <code>/mercado</code> para ver los activos disponibles.",
                tid,
            )
            return

        valor_total = sum(p.valor_actual for p in posiciones)
        costo_total = sum(p.costo_total  for p in posiciones)
        ganancia    = valor_total - costo_total
        ganancia_pct = (ganancia / costo_total * 100) if costo_total > 0 else 0.0
        emoji_gl    = "📈" if ganancia >= 0 else "📉"

        lineas = [f"💼 <b>Portfolio de {nombre}</b>\n"]
        for p in posiciones:
            emoji_p = "📈" if p.ganancia_neta >= 0 else "📉"
            lineas.append(
                f"{emoji_p} <b>{p.simbolo}</b> — {p.cantidad} acc.\n"
                f"   Precio actual: {p.precio_actual:,.0f} ✨  |  "
                f"Promedio compra: {p.precio_promedio:,.0f} ✨\n"
                f"   Valor: <b>{p.valor_actual:,.0f} ✨</b>  "
                f"P&L: <b>{p.ganancia_neta:+,.0f} ✨</b> ({p.ganancia_pct:+.1f}%)"
            )

        lineas.append(
            f"\n{emoji_gl} <b>Total</b>\n"
            f"   Valor: <b>{valor_total:,.0f} ✨</b>\n"
            f"   P&L total: <b>{ganancia:+,.0f} ✨</b> ({ganancia_pct:+.1f}%)"
        )

        m = self.bot.send_message(
            cid, "\n".join(lineas), parse_mode="HTML", message_thread_id=tid
        )
        self._del_after(cid, m.message_id, 60.0)

    # ── /ranking_mercado ──────────────────────────────────────────────────────

    def cmd_ranking_mercado(self, message: telebot.types.Message) -> None:
        """Top 10 inversores por valor de portfolio."""
        cid = message.chat.id
        tid = message.message_thread_id

        self._del(cid, message.message_id)

        ranking = mercado_service.get_ranking(top_n=10)

        if not ranking:
            self._err(cid, "📊 Nadie tiene acciones todavía.", tid)
            return

        medallas = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
        lineas   = ["🏆 <b>RANKING — Mercado de Cosmos</b>\n"]

        for i, entry in enumerate(ranking):
            emoji_gl = "📈" if entry["ganancia"] >= 0 else "📉"
            lineas.append(
                f"{medallas[i]} <b>{entry['nombre']}</b>\n"
                f"   Portfolio: <b>{entry['valor_total']:,.0f} ✨</b>  "
                f"{emoji_gl} P&L: <b>{entry['ganancia']:+,.0f} ✨</b>"
            )

        m = self.bot.send_message(
            cid, "\n".join(lineas), parse_mode="HTML", message_thread_id=tid
        )
        self._del_after(cid, m.message_id, 60.0)
