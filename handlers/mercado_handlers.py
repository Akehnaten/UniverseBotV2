# -*- coding: utf-8 -*-
"""
handlers/mercado_handlers.py
════════════════════════════════════════════════════════════════════════════════
Handler del Mercado de Cosmos — UniverseBot V2.0

Todos los comandos funcionan SOLO en el thread 2553.
Las notificaciones de eventos, dividendos y reporte diario
también se publican en ese mismo thread.

Comandos:
  /mercado              — Tabla de precios con tier, tendencia y variación diaria
  /activo [SIM]         — Ficha completa de un activo
  /comprar [SIM] [N]    — Compra N acciones
  /vender  [SIM] [N]    — Vende N acciones
  /portfolio            — Holdings + P&L + dividendo estimado
  /ranking_mercado      — Top 10 inversores
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import math
import threading
from typing import Optional

import telebot

from config import CANAL_ID, MSG_USUARIO_NO_REGISTRADO
from database import db_manager
from funciones import user_service
from funciones.mercado_service import TIER_EMOJI, mercado_service

logger = logging.getLogger(__name__)

MERCADO_THREAD = 2553   # Único thread donde funciona el mercado


class MercadoHandlers:

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        self._register_handlers()
        mercado_service.iniciar_loop(notif_callback=self._notificar)

    def _register_handlers(self) -> None:
        self.bot.register_message_handler(self.cmd_mercado,         commands=["mercado"])
        self.bot.register_message_handler(self.cmd_activo,          commands=["activo"])
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

    def _del_after(self, cid: int, mid: int, delay: float = 60.0) -> None:
        threading.Timer(delay, lambda: self._del(cid, mid)).start()

    def _err(self, cid: int, txt: str, delay: float = 10.0) -> None:
        m = self.bot.send_message(
            cid, txt, parse_mode="HTML", message_thread_id=MERCADO_THREAD
        )
        self._del_after(cid, m.message_id, delay)

    def _solo_mercado(self, message: telebot.types.Message) -> bool:
        """Devuelve True solo si el mensaje viene del thread de Mercado."""
        if message.message_thread_id == MERCADO_THREAD:
            return True
        self._del(message.chat.id, message.message_id)
        return False

    def _get_nombre(self, uid: int) -> str:
        info = user_service.get_user_info(uid)
        return info.get("nombre", "Usuario") if info else "Usuario"

    # ── Callback de notificación ──────────────────────────────────────────────

    def _notificar(
        self,
        simbolo: str,
        nombre: str,
        texto: str,
        impacto_pct: float,
        es_positivo: bool,
    ) -> None:
        """Publica en el thread de Mercado: eventos, dividendos y reporte diario."""
        try:
            if simbolo == "__REPORTE__":
                # El texto ya viene formateado desde el service
                contenido = texto + "\n\n<i>Usá /mercado para ver precios actuales.</i>"

            elif simbolo == "__DIVIDENDO__":
                contenido = (
                    f"💰 <b>DIVIDENDOS PAGADOS</b>\n\n"
                    f"{texto}\n\n"
                    f"<i>Usá /portfolio para ver tus ganancias.</i>"
                )

            else:
                emoji  = "🚀" if es_positivo else "💥"
                signo  = "+" if es_positivo else ""
                contenido = (
                    f"{emoji} <b>NOTICIA — {nombre} ({simbolo})</b>\n\n"
                    f"📰 {texto}\n\n"
                    f"📊 Impacto estimado: <b>{signo}{impacto_pct:.1f}%</b>"
                )

            self.bot.send_message(
                CANAL_ID, contenido,
                parse_mode="HTML",
                message_thread_id=MERCADO_THREAD,
            )
        except Exception as exc:
            logger.warning("[MERCADO] _notificar falló: %s", exc)

    # ── /mercado ──────────────────────────────────────────────────────────────

    def cmd_mercado(self, message: telebot.types.Message) -> None:
        if not self._solo_mercado(message):
            return
        cid = message.chat.id
        self._del(cid, message.message_id)

        activos = mercado_service.get_activos()
        lineas  = ["📊 <b>MERCADO DE COSMOS</b>\n"]

        tier_actual = None
        for a in activos:
            if a.tier != tier_actual:
                tier_actual = a.tier
                lineas.append(f"\n{TIER_EMOJI.get(a.tier,'')} <b>{a.tier} CAP</b>")
            lineas.append(
                f"{a.emoji_tendencia} <b>{a.simbolo}</b>  {a.nombre}\n"
                f"   💰 <b>{a.precio_actual:,.0f} ✨</b>  "
                f"<i>hoy: {a.variacion_diaria_pct:+.1f}%  |  última hora: {a.variacion_pct:+.1f}%</i>"
            )

        lineas.append(
            "\n<i>Precios actualizados cada hora. Eventos K-pop disparan movimientos adicionales.</i>\n"
            "💡 <code>/activo [SIM]</code> · <code>/comprar [SIM] [N]</code> · <code>/vender [SIM] [N]</code>"
        )

        m = self.bot.send_message(
            cid, "\n".join(lineas), parse_mode="HTML", message_thread_id=MERCADO_THREAD
        )
        self._del_after(cid, m.message_id, 120.0)

    # ── /activo ───────────────────────────────────────────────────────────────

    def cmd_activo(self, message: telebot.types.Message) -> None:
        if not self._solo_mercado(message):
            return
        cid = message.chat.id
        self._del(cid, message.message_id)

        parts = (message.text or "").split()
        if len(parts) < 2:
            self._err(cid, "❌ Uso: <code>/activo [SIMBOLO]</code>  ej: <code>/activo BTS</code>")
            return

        activo = mercado_service.get_activo(parts[1].upper())
        if not activo:
            self._err(cid, "❌ Activo no encontrado. Usá /mercado para ver los disponibles.")
            return

        rango = activo.precio_maximo - activo.precio_minimo
        pos   = ((activo.precio_actual - activo.precio_minimo) / rango * 100) if rango > 0 else 50.0
        barra = self._barra(pos)

        m = self.bot.send_message(
            cid,
            f"{activo.tier_emoji} <b>{activo.nombre} ({activo.simbolo})</b>\n"
            f"Tier: <b>{activo.tier} CAP</b>\n\n"
            f"💰 Precio:          <b>{activo.precio_actual:,.0f} ✨</b>\n"
            f"📊 Var. hoy:        <b>{activo.variacion_diaria_pct:+.1f}%</b>  "
            f"Última hora: <b>{activo.variacion_pct:+.1f}%</b>\n"
            f"📈 Máximo hist.:    <b>{activo.precio_maximo:,.0f} ✨</b>\n"
            f"📉 Mínimo hist.:    <b>{activo.precio_minimo:,.0f} ✨</b>\n"
            f"<code>{barra}</code>\n\n"
            f"📉 Volatilidad:     <b>{activo.volatilidad*100:.0f}%</b>/ciclo\n"
            f"💸 Dividendo yield: <b>{activo.yield_diario*100:.1f}%</b>/día",
            parse_mode="HTML",
            message_thread_id=MERCADO_THREAD,
        )
        self._del_after(cid, m.message_id, 60.0)

    @staticmethod
    def _barra(pct: float, largo: int = 20) -> str:
        pos   = max(0, min(int(pct / 100 * largo), largo - 1))
        barra = "─" * pos + "●" + "─" * (largo - pos - 1)
        return f"Min {barra} Max"

    # ── /comprar ──────────────────────────────────────────────────────────────

    def cmd_comprar(self, message: telebot.types.Message) -> None:
        if not self._solo_mercado(message):
            return
        cid = message.chat.id
        uid = message.from_user.id
        self._del(cid, message.message_id)

        if not db_manager.user_exists(uid):
            self._err(cid, MSG_USUARIO_NO_REGISTRADO)
            return

        parts = (message.text or "").split()
        if len(parts) < 3:
            self._err(cid, "❌ Uso: <code>/comprar [SIMBOLO] [cantidad]</code>  ej: <code>/comprar BTS 5</code>")
            return

        try:
            cantidad = int(parts[2])
        except ValueError:
            self._err(cid, "❌ La cantidad debe ser un número entero.")
            return

        ok, err, costo = mercado_service.comprar(uid, parts[1], cantidad)
        if not ok:
            self._err(cid, f"❌ {err}")
            return

        activo  = mercado_service.get_activo(parts[1].upper())
        div_est = int(activo.precio_actual * cantidad * activo.yield_diario) if activo else 0

        m = self.bot.send_message(
            cid,
            f"✅ <b>{self._get_nombre(uid)}</b> compró <b>{cantidad} acciones</b> de "
            f"<b>{activo.nombre if activo else parts[1]}</b>\n"
            f"💸 Costo:           <b>{int(costo):,} ✨</b>\n"
            f"📊 Precio unitario: <b>{activo.precio_actual:,.0f} ✨</b>\n"
            f"💰 Dividendo/día:   <b>~{div_est:,} ✨</b>",
            parse_mode="HTML",
            message_thread_id=MERCADO_THREAD,
        )
        self._del_after(cid, m.message_id, 30.0)

    # ── /vender ───────────────────────────────────────────────────────────────

    def cmd_vender(self, message: telebot.types.Message) -> None:
        if not self._solo_mercado(message):
            return
        cid = message.chat.id
        uid = message.from_user.id
        self._del(cid, message.message_id)

        if not db_manager.user_exists(uid):
            self._err(cid, MSG_USUARIO_NO_REGISTRADO)
            return

        parts = (message.text or "").split()
        if len(parts) < 3:
            self._err(cid, "❌ Uso: <code>/vender [SIMBOLO] [cantidad]</code>  ej: <code>/vender BTS 5</code>")
            return

        try:
            cantidad = int(parts[2])
        except ValueError:
            self._err(cid, "❌ La cantidad debe ser un número entero.")
            return

        ok, err, ingreso = mercado_service.vender(uid, parts[1], cantidad)
        if not ok:
            self._err(cid, f"❌ {err}")
            return

        activo = mercado_service.get_activo(parts[1].upper())
        m = self.bot.send_message(
            cid,
            f"💹 <b>{self._get_nombre(uid)}</b> vendió <b>{cantidad} acciones</b> de "
            f"<b>{activo.nombre if activo else parts[1]}</b>\n"
            f"💰 Ingreso total:   <b>{int(ingreso):,} ✨</b>\n"
            f"📊 Precio unitario: <b>{activo.precio_actual:,.0f} ✨</b>",
            parse_mode="HTML",
            message_thread_id=MERCADO_THREAD,
        )
        self._del_after(cid, m.message_id, 30.0)

    # ── /portfolio ────────────────────────────────────────────────────────────

    def cmd_portfolio(self, message: telebot.types.Message) -> None:
        if not self._solo_mercado(message):
            return
        cid = message.chat.id
        uid = message.from_user.id
        self._del(cid, message.message_id)

        if not db_manager.user_exists(uid):
            self._err(cid, MSG_USUARIO_NO_REGISTRADO)
            return

        nombre     = self._get_nombre(uid)
        posiciones = mercado_service.get_portfolio(uid)

        if not posiciones:
            self._err(
                cid,
                f"📭 <b>{nombre}</b>, no tenés acciones todavía.\n"
                "Usá <code>/mercado</code> para ver los activos disponibles.",
            )
            return

        valor_total = sum(p.valor_actual  for p in posiciones)
        costo_total = sum(p.costo_total   for p in posiciones)
        ganancia    = valor_total - costo_total
        gan_pct     = (ganancia / costo_total * 100) if costo_total > 0 else 0.0
        div_total   = sum(p.dividendo_diario_estimado for p in posiciones)
        emoji_gl    = "🚀" if ganancia > 0 else ("💥" if ganancia < 0 else "➡️")

        lineas = [f"💼 <b>Portfolio de {nombre}</b>\n"]
        for p in posiciones:
            emoji_p = "📈" if p.ganancia_neta >= 0 else "📉"
            lineas.append(
                f"{emoji_p} <b>{p.simbolo}</b> — {p.cantidad} acc.\n"
                f"   Precio: {p.precio_actual:,.0f} ✨  |  Costo prom.: {p.precio_promedio:,.0f} ✨\n"
                f"   Valor: <b>{p.valor_actual:,.0f} ✨</b>  "
                f"P&L: <b>{p.ganancia_neta:+,.0f} ✨</b> ({p.ganancia_pct:+.1f}%)\n"
                f"   💰 Dividendo/día: ~{p.dividendo_diario_estimado:,} ✨"
            )

        lineas.append(
            f"\n{emoji_gl} <b>Resumen</b>\n"
            f"   Valor total:          <b>{valor_total:,.0f} ✨</b>\n"
            f"   P&L total:            <b>{ganancia:+,.0f} ✨</b> ({gan_pct:+.1f}%)\n"
            f"   💰 Dividendo/día est.: <b>~{div_total:,} ✨</b>"
        )

        m = self.bot.send_message(
            cid, "\n".join(lineas), parse_mode="HTML", message_thread_id=MERCADO_THREAD
        )
        self._del_after(cid, m.message_id, 120.0)

    # ── /ranking_mercado ──────────────────────────────────────────────────────

    def cmd_ranking_mercado(self, message: telebot.types.Message) -> None:
        if not self._solo_mercado(message):
            return
        cid = message.chat.id
        self._del(cid, message.message_id)

        ranking = mercado_service.get_ranking(top_n=10)
        if not ranking:
            self._err(cid, "📊 Nadie tiene acciones todavía.")
            return

        medallas = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
        lineas   = ["🏆 <b>RANKING — Mercado de Cosmos</b>\n"]

        for i, e in enumerate(ranking):
            emoji_gl = "📈" if e["ganancia"] >= 0 else "📉"
            lineas.append(
                f"{medallas[i]} <b>{e['nombre']}</b>\n"
                f"   Portfolio: <b>{e['valor_total']:,.0f} ✨</b>  "
                f"{emoji_gl} P&L: <b>{e['ganancia']:+,.0f} ✨</b>"
            )

        m = self.bot.send_message(
            cid, "\n".join(lineas), parse_mode="HTML", message_thread_id=MERCADO_THREAD
        )
        self._del_after(cid, m.message_id, 120.0)
