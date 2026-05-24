# -*- coding: utf-8 -*-
"""
handlers/mercado_handlers.py
Mercado de Cosmos — UniverseBot V2.0

Comandos de consulta (cualquier hilo):
  /activo [SIM]         — Ficha del activo con info CEO
  /ceo    [SIM]         — CEO de un grupo / tabla completa
  /ceos                 — Tabla completa de CEOs

Comandos de operación (solo hilo MERCADO_THREAD = 2553):
  /mercado              — Precios actuales
  /comprar [SIM] [N]    — Compra acciones
  /vender  [SIM] [N]    — Vende acciones
  /portfolio            — Tu portfolio (alias: /portafolio)
  /ranking_mercado      — Top 10 inversores
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

MERCADO_THREAD = 2553


class MercadoHandlers:

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        self._register_handlers()
        mercado_service.iniciar_loop(notif_callback=self._notificar)

    # ── Registro de handlers ──────────────────────────────────────────────────

    def _register_handlers(self) -> None:
        # Consulta — cualquier hilo
        self.bot.register_message_handler(self.cmd_activo,          commands=["activo"])
        self.bot.register_message_handler(self.cmd_ceo,             commands=["ceo"])
        self.bot.register_message_handler(self.cmd_ceos,            commands=["ceos"])
        # Operación — solo MERCADO_THREAD
        self.bot.register_message_handler(self.cmd_mercado,         commands=["mercado"])
        self.bot.register_message_handler(self.cmd_comprar,         commands=["comprar"])
        self.bot.register_message_handler(self.cmd_vender,          commands=["vender"])
        self.bot.register_message_handler(self.cmd_portfolio,       commands=["portfolio"])
        self.bot.register_message_handler(self.cmd_portfolio,       commands=["portafolio"])
        self.bot.register_message_handler(self.cmd_ranking_mercado, commands=["ranking_mercado"])

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
        """True si el mensaje viene del thread de Mercado. Avisa si no."""
        if message.message_thread_id == MERCADO_THREAD:
            return True
        self._del(message.chat.id, message.message_id)
        self._err(
            message.chat.id,
            "📊 Este comando solo funciona en el canal de Mercado.",
            message.message_thread_id,
            6.0,
        )
        return False

    def _get_nombre(self, uid: int) -> str:
        info = user_service.get_user_info(uid)
        return info.get("nombre", "Usuario") if info else "Usuario"

    @staticmethod
    def _barra(pct: float, largo: int = 20) -> str:
        pos   = max(0, min(int(pct / 100 * largo), largo - 1))
        barra = "─" * pos + "●" + "─" * (largo - pos - 1)
        return f"Min {barra} Max"

    # ── Callback de notificación (eventos, dividendos, reporte) ───────────────

    def _notificar(
        self,
        simbolo:      str,
        nombre:       str,
        texto:        str,
        impacto_pct:  float,
        es_positivo:  bool,
    ) -> None:
        try:
            if simbolo == "__REPORTE__":
                contenido = texto + "\n\n<i>Usá /mercado para ver precios actuales.</i>"
            elif simbolo == "__DIVIDENDO__":
                contenido = f"💰 <b>DIVIDENDOS PAGADOS</b>\n\n{texto}\n\n<i>Usá /portfolio para ver tus ganancias.</i>"
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
            logger.warning("[MERCADO] _notificar: %s", exc)

    # ── /mercado ──────────────────────────────────────────────────────────────

    def cmd_mercado(self, message: telebot.types.Message) -> None:
        if not self._solo_mercado(message):
            return
        cid = message.chat.id
        self._del(cid, message.message_id)
        try:
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
                    f"<i>hoy: {a.variacion_diaria_pct:+.1f}%  última hora: {a.variacion_pct:+.1f}%</i>"
                )
            lineas.append(
                "\n<i>Precios actualizados cada hora.</i>\n"
                "💡 <code>/activo [SIM]</code> · <code>/ceos</code>"
            )
            m = self.bot.send_message(
                cid, "\n".join(lineas),
                parse_mode="HTML", message_thread_id=MERCADO_THREAD,
            )
            self._del_after(cid, m.message_id, 120.0)
        except Exception as exc:
            logger.error("[MERCADO] cmd_mercado: %s", exc, exc_info=True)
            self._err(cid, f"❌ Error: <code>{exc}</code>", MERCADO_THREAD)

    # ── /activo ───────────────────────────────────────────────────────────────

    def cmd_activo(self, message: telebot.types.Message) -> None:
        cid = message.chat.id
        tid = message.message_thread_id
        self._del(cid, message.message_id)
        try:
            parts = (message.text or "").split()
            if len(parts) < 2:
                self._err(cid, "❌ Uso: <code>/activo [SIMBOLO]</code>  ej: <code>/activo BTS</code>", tid)
                return
            activo = mercado_service.get_activo(parts[1].upper())
            if not activo:
                self._err(cid, "❌ Activo no encontrado. Usá /mercado.", tid)
                return
            rango        = activo.precio_maximo - activo.precio_minimo
            pos          = ((activo.precio_actual - activo.precio_minimo) / rango * 100) if rango > 0 else 50.0
            barra        = self._barra(pos)
            acciones_ceo = math.ceil(activo.supply_total * 0.51)
            costo_ceo    = int(acciones_ceo * activo.precio_actual)
            disponibles  = mercado_service.get_acciones_disponibles(activo.simbolo)
            ceo_info     = mercado_service.get_ceo(activo.simbolo)
            ceo_linea    = (
                f"\n👑 CEO: <b>{ceo_info['nombre']}</b> ({ceo_info['porcentaje']:.1f}%)"
                if ceo_info else "\n👑 CEO: <i>Sin CEO — ¡posición libre!</i>"
            )
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
                f"💸 Dividendo yield: <b>{activo.yield_diario*100:.1f}%</b>/día\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📦 Supply total:    <b>{activo.supply_total:,} acciones</b>\n"
                f"🛒 Disponibles:     <b>{disponibles:,} acciones</b>\n"
                f"👑 Para ser CEO:    <b>{acciones_ceo:,} acciones</b> (~{costo_ceo:,} ✨)"
                f"{ceo_linea}",
                parse_mode="HTML", message_thread_id=tid,
            )
            self._del_after(cid, m.message_id, 60.0)
        except Exception as exc:
            logger.error("[MERCADO] cmd_activo: %s", exc, exc_info=True)
            self._err(cid, f"❌ Error: <code>{exc}</code>", tid)

    # ── /ceo ─────────────────────────────────────────────────────────────────

    def cmd_ceo(self, message: telebot.types.Message) -> None:
        cid = message.chat.id
        tid = message.message_thread_id
        self._del(cid, message.message_id)
        try:
            parts = (message.text or "").split()
            if len(parts) < 2:
                self._mostrar_tabla_ceos(cid, tid)
                return
            activo = mercado_service.get_activo(parts[1].upper())
            if not activo:
                self._err(cid, f"❌ Activo <b>{parts[1].upper()}</b> no encontrado. Usá /mercado.", tid)
                return
            acciones_ceo = math.ceil(activo.supply_total * 0.51)
            costo_est    = int(acciones_ceo * activo.precio_actual)
            disponibles  = mercado_service.get_acciones_disponibles(activo.simbolo)
            ceo_info     = mercado_service.get_ceo(activo.simbolo)
            if ceo_info:
                ceo_bloque = (
                    f"👑 <b>CEO: {ceo_info['nombre']}</b>\n"
                    f"   Acciones: <b>{ceo_info['cantidad']:,}</b> ({ceo_info['porcentaje']:.1f}%)\n"
                    f"   CEO desde: <i>{str(ceo_info['fecha_desde'])[:10]}</i>"
                )
                if ceo_info.get("mensaje"):
                    ceo_bloque += f"\n   💬 <i>\"{ceo_info['mensaje']}\"</i>"
                ceo_bloque += f"\n\n⚔️ Para destronar: <b>{acciones_ceo:,} acciones</b> (~{costo_est:,} ✨)"
            else:
                ceo_bloque = (
                    f"👑 <b>Sin CEO</b> — ¡posición libre!\n\n"
                    f"🎯 Necesitás <b>{acciones_ceo:,} acciones</b>\n"
                    f"   Costo: ~<b>{costo_est:,} ✨</b>\n"
                    f"   Disponibles: <b>{disponibles:,}</b>"
                )
            m = self.bot.send_message(
                cid,
                f"{activo.tier_emoji} <b>{activo.nombre} ({activo.simbolo})</b>\n"
                f"Supply: <b>{activo.supply_total:,} acciones</b>\n\n"
                f"{ceo_bloque}",
                parse_mode="HTML", message_thread_id=tid,
            )
            self._del_after(cid, m.message_id, 60.0)
        except Exception as exc:
            logger.error("[MERCADO] cmd_ceo: %s", exc, exc_info=True)
            self._err(cid, f"❌ Error: <code>{exc}</code>", tid)

    # ── /ceos ─────────────────────────────────────────────────────────────────

    def cmd_ceos(self, message: telebot.types.Message) -> None:
        cid = message.chat.id
        tid = message.message_thread_id
        self._del(cid, message.message_id)
        self._mostrar_tabla_ceos(cid, tid)

    def _mostrar_tabla_ceos(self, cid: int, tid: Optional[int] = None) -> None:
        try:
            activos = mercado_service.get_activos()
            lineas  = ["👑 <b>CEOs DEL MERCADO DE COSMOS</b>\n"]
            tier_actual = None
            for a in activos:
                if a.tier != tier_actual:
                    tier_actual = a.tier
                    lineas.append(f"\n{TIER_EMOJI.get(a.tier,'')} <b>{a.tier} CAP</b>")
                acciones_ceo = math.ceil(a.supply_total * 0.51)
                costo_est    = int(acciones_ceo * a.precio_actual)
                ceo_info     = mercado_service.get_ceo(a.simbolo)
                estado       = (
                    f"👑 {ceo_info['nombre']} ({ceo_info['porcentaje']:.0f}%)"
                    if ceo_info else "<i>Libre</i>"
                )
                lineas.append(
                    f"<b>{a.simbolo}</b>  {a.nombre}\n"
                    f"   CEO: {estado}\n"
                    f"   Para CEO: <b>{acciones_ceo:,} acc.</b>  ~{costo_est:,} ✨"
                )
            lineas.append("\n<i>💡 <code>/ceo [SIM]</code> para detalle de un grupo</i>")
            m = self.bot.send_message(
                cid, "\n".join(lineas),
                parse_mode="HTML", message_thread_id=tid,
            )
            self._del_after(cid, m.message_id, 120.0)
        except Exception as exc:
            logger.error("[MERCADO] _mostrar_tabla_ceos: %s", exc, exc_info=True)
            self._err(cid, f"❌ Error: <code>{exc}</code>", tid)

    # ── /comprar ──────────────────────────────────────────────────────────────

    def cmd_comprar(self, message: telebot.types.Message) -> None:
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
            if len(parts) < 3:
                self._err(cid, "❌ Uso: <code>/comprar [SIMBOLO] [cantidad]</code>  ej: <code>/comprar BTS 5</code>", MERCADO_THREAD)
                return
            try:
                cantidad = int(parts[2])
            except ValueError:
                self._err(cid, "❌ La cantidad debe ser un número entero.", MERCADO_THREAD)
                return
            nombre = self._get_nombre(uid)
            ok, err, costo, ceo_event = mercado_service.comprar(uid, parts[1], cantidad, nombre)
            if not ok:
                self._err(cid, f"❌ {err}", MERCADO_THREAD)
                return
            activo  = mercado_service.get_activo(parts[1].upper())
            div_est = int(activo.precio_actual * cantidad * activo.yield_diario) if activo else 0
            m = self.bot.send_message(
                cid,
                f"✅ <b>{nombre}</b> compró <b>{cantidad} acciones</b> de "
                f"<b>{activo.nombre if activo else parts[1]}</b>\n"
                f"💸 Costo:           <b>{int(costo):,} ✨</b>\n"
                f"📊 Precio unitario: <b>{activo.precio_actual:,.0f} ✨</b>\n"
                f"💰 Dividendo/día:   <b>~{div_est:,} ✨</b>",
                parse_mode="HTML", message_thread_id=MERCADO_THREAD,
            )
            self._del_after(cid, m.message_id, 30.0)
            if ceo_event:
                self._anunciar_ceo(ceo_event)
        except Exception as exc:
            logger.error("[MERCADO] cmd_comprar: %s", exc, exc_info=True)
            self._err(cid, f"❌ Error: <code>{exc}</code>", MERCADO_THREAD)

    # ── /vender ───────────────────────────────────────────────────────────────

    def cmd_vender(self, message: telebot.types.Message) -> None:
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
            if len(parts) < 3:
                self._err(cid, "❌ Uso: <code>/vender [SIMBOLO] [cantidad]</code>  ej: <code>/vender BTS 5</code>", MERCADO_THREAD)
                return
            try:
                cantidad = int(parts[2])
            except ValueError:
                self._err(cid, "❌ La cantidad debe ser un número entero.", MERCADO_THREAD)
                return
            nombre = self._get_nombre(uid)
            ok, err, ingreso, ceo_event = mercado_service.vender(uid, parts[1], cantidad, nombre)
            if not ok:
                self._err(cid, f"❌ {err}", MERCADO_THREAD)
                return
            activo = mercado_service.get_activo(parts[1].upper())
            m = self.bot.send_message(
                cid,
                f"💹 <b>{nombre}</b> vendió <b>{cantidad} acciones</b> de "
                f"<b>{activo.nombre if activo else parts[1]}</b>\n"
                f"💰 Ingreso total:   <b>{int(ingreso):,} ✨</b>\n"
                f"📊 Precio unitario: <b>{activo.precio_actual:,.0f} ✨</b>",
                parse_mode="HTML", message_thread_id=MERCADO_THREAD,
            )
            self._del_after(cid, m.message_id, 30.0)
            if ceo_event:
                self._anunciar_ceo(ceo_event)
        except Exception as exc:
            logger.error("[MERCADO] cmd_vender: %s", exc, exc_info=True)
            self._err(cid, f"❌ Error: <code>{exc}</code>", MERCADO_THREAD)

    # ── /portfolio ────────────────────────────────────────────────────────────

    def cmd_portfolio(self, message: telebot.types.Message) -> None:
        if not self._solo_mercado(message):
            return
        cid = message.chat.id
        uid = message.from_user.id
        self._del(cid, message.message_id)
        try:
            if not db_manager.user_exists(uid):
                self._err(cid, MSG_USUARIO_NO_REGISTRADO, MERCADO_THREAD)
                return
            nombre     = self._get_nombre(uid)
            posiciones = mercado_service.get_portfolio(uid)
            if not posiciones:
                self._err(cid, f"📭 <b>{nombre}</b>, no tenés acciones todavía.\nUsá <code>/mercado</code> para ver los activos.", MERCADO_THREAD)
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
                ceo_tag = " 👑" if p.es_ceo else ""
                lineas.append(
                    f"{emoji_p} <b>{p.simbolo}</b>{ceo_tag} — {p.cantidad} acc.\n"
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
                cid, "\n".join(lineas),
                parse_mode="HTML", message_thread_id=MERCADO_THREAD,
            )
            self._del_after(cid, m.message_id, 90.0)
        except Exception as exc:
            logger.error("[MERCADO] cmd_portfolio: %s", exc, exc_info=True)
            self._err(cid, f"❌ Error: <code>{exc}</code>", MERCADO_THREAD)

    # ── /ranking_mercado ──────────────────────────────────────────────────────

    def cmd_ranking_mercado(self, message: telebot.types.Message) -> None:
        if not self._solo_mercado(message):
            return
        cid = message.chat.id
        self._del(cid, message.message_id)
        try:
            ranking = mercado_service.get_ranking(top_n=10)
            if not ranking:
                self._err(cid, "📊 Nadie tiene acciones todavía.", MERCADO_THREAD)
                return
            medallas = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
            lineas   = ["🏆 <b>RANKING — Mercado de Cosmos</b>\n"]
            for i, e in enumerate(ranking):
                emoji_gl = "📈" if e["ganancia"] >= 0 else "📉"
                ceos     = e.get("ceos", [])
                ceo_tag  = "  👑 " + "·".join(c["simbolo"] for c in ceos) if ceos else ""
                lineas.append(
                    f"{medallas[i]} <b>{e['nombre']}</b>{ceo_tag}\n"
                    f"   Portfolio: <b>{e['valor_total']:,.0f} ✨</b>  "
                    f"{emoji_gl} P&L: <b>{e['ganancia']:+,.0f} ✨</b>"
                )
            m = self.bot.send_message(
                cid, "\n".join(lineas),
                parse_mode="HTML", message_thread_id=MERCADO_THREAD,
            )
            self._del_after(cid, m.message_id, 90.0)
        except Exception as exc:
            logger.error("[MERCADO] cmd_ranking_mercado: %s", exc, exc_info=True)
            self._err(cid, f"❌ Error: <code>{exc}</code>", MERCADO_THREAD)

    # ── Anuncio CEO ───────────────────────────────────────────────────────────

    def _anunciar_ceo(self, ceo_event: dict) -> None:
        try:
            tipo        = ceo_event.get("tipo")
            simbolo     = ceo_event.get("simbolo", "")
            nombre_g    = ceo_event.get("nombre_grupo", simbolo)
            nuevo       = ceo_event.get("nuevo_nombre", "")
            old_nombre  = ceo_event.get("old_nombre", "")
            pct         = ceo_event.get("porcentaje", 0)

            if tipo == "nuevo":
                texto = (
                    f"👑 <b>¡NUEVO CEO!</b>\n\n"
                    f"<b>{nuevo}</b> se convirtió en CEO de <b>{nombre_g} ({simbolo})</b>\n"
                    f"Con el <b>{pct:.1f}%</b> de las acciones en su poder."
                )
            elif tipo == "takeover":
                texto = (
                    f"⚔️ <b>¡HOSTILE TAKEOVER!</b>\n\n"
                    f"<b>{nuevo}</b> desbancó a <b>{old_nombre}</b>\n"
                    f"y es el nuevo CEO de <b>{nombre_g} ({simbolo})</b>\n"
                    f"Control: <b>{pct:.1f}%</b> del supply."
                )
            elif tipo == "perdida":
                texto = (
                    f"📉 <b>{old_nombre}</b> perdió el título de CEO de "
                    f"<b>{nombre_g} ({simbolo})</b> al bajar del 51%."
                )
            else:
                return

            self.bot.send_message(
                CANAL_ID, texto,
                parse_mode="HTML",
                message_thread_id=MERCADO_THREAD,
            )
        except Exception as exc:
            logger.warning("[MERCADO] _anunciar_ceo: %s", exc)
