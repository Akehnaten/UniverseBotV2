# -*- coding: utf-8 -*-
"""
handlers/carreras_handlers.py
════════════════════════════════════════════════════════════════════════════════
Handler de Carreras de Caballos para UniverseBot V2.0

Comandos (solo admins, solo en hilo CASINO):
  /carreras on   — Abre ronda de apuestas (3 min)
  /carreras off  — Cancela la carrera y devuelve apuestas

Callbacks (inline, cualquier usuario del grupo):
  carrera_apostar          — Abre panel de selección de caballo
  carrera_caballo:{idx}    — Selecciona caballo, pide monto
  carrera_monto:{idx}:{c}  — Confirma apuesta

Flujo:
  1. Admin: /carreras on → Bot publica panel en CASINO con botón "Apostar"
  2. Usuario pulsa "Apostar" → Bot muestra 5 caballos + montos (inline)
  3. Usuario elige caballo + monto → cosmos descontados, apuesta registrada
  4. Al vencer el timer: Bot ejecuta la carrera con animación
  5. Resultados + pagos publicados en CASINO
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import telebot
from telebot import types

from config import CASINO, MSG_USUARIO_NO_REGISTRADO
from database import db_manager
from funciones import economy_service, user_service
from funciones.carreras_service import (
    PISTA_LONGITUD,
    CABALLOS,
    DURACION_APUESTAS,
    PAGO_MINIMO_MULT,
    ApuestaCarrera,
    carreras_service,
)

logger = logging.getLogger(__name__)

_MONTOS_RAPIDOS = (50, 100, 250, 500, 1_000, 5_000)
_APUESTA_MIN    = 50
_APUESTA_MAX    = 50_000


def _is_admin(bot: telebot.TeleBot, chat_id: int, user_id: int) -> bool:
    try:
        return bot.get_chat_member(chat_id, user_id).status in ("creator", "administrator")
    except Exception:
        return False


class CarrerasHandlers:
    """Handler completo de Carreras. Una instancia por proceso."""

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.bot.register_message_handler(self.cmd_carreras, commands=["carreras"])
        self.bot.register_callback_query_handler(
            self.cb_carreras,
            func=lambda c: c.data.startswith("carrera_"),
        )

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _del(self, cid: int, mid: int) -> None:
        try:
            self.bot.delete_message(cid, mid)
        except Exception:
            pass

    def _err(self, cid: int, txt: str, tid: Optional[int] = None, delay: float = 8.0) -> None:
        m = self.bot.send_message(cid, txt, message_thread_id=tid, parse_mode="HTML")
        threading.Timer(delay, lambda: self._del(cid, m.message_id)).start()

    # ── /carreras ─────────────────────────────────────────────────────────────

    def cmd_carreras(self, message: telebot.types.Message) -> None:
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        if message.message_thread_id != CASINO:
            self._del(cid, message.message_id)
            return

        self._del(cid, message.message_id)

        if not _is_admin(self.bot, cid, uid):
            self._err(cid, "❌ Solo los admins pueden controlar las carreras.", tid)
            return

        parts = (message.text or "").split()
        subcomando = parts[1].lower() if len(parts) > 1 else ""

        if subcomando == "on":
            self._activar(cid, tid)
        elif subcomando == "off":
            self._desactivar_manual(cid, tid)
        else:
            self._err(
                cid,
                "🏇 Uso: <code>/carreras on</code> o <code>/carreras off</code>",
                tid,
            )

    def _activar(self, cid: int, tid: Optional[int]) -> None:
        ok = carreras_service.activar(
            chat_id=cid,
            thread_id=tid,
            on_carrera_callback=self._ejecutar_carrera_automatica,
        )
        if not ok:
            self._err(cid, "⚠️ Ya hay una carrera activa.", tid)
            return

        self._publicar_panel_apuestas(cid, tid, primera_vez=True)

    def _desactivar_manual(self, cid: int, tid: Optional[int]) -> None:
        estado = carreras_service.desactivar()
        if not estado.activa:
            self._err(cid, "⚠️ No hay ninguna carrera activa.", tid)
            return

        # Reembolsar a todos
        for apuesta in estado.apuestas:
            economy_service.add_credits(
                apuesta.user_id, apuesta.cosmos, "carreras_cancelacion_reembolso"
            )

        self.bot.send_message(
            cid,
            "🚫 <b>Carrera cancelada.</b> Se reembolsaron todas las apuestas.",
            parse_mode="HTML",
            message_thread_id=tid,
        )

    # ── Panel de apuestas ─────────────────────────────────────────────────────

    def _publicar_panel_apuestas(
        self, cid: int, tid: Optional[int], primera_vez: bool = False
    ) -> None:
        """Publica el mensaje de ronda abierta con botón de apostar."""
        totales = carreras_service.apuestas_por_caballo()
        pool    = carreras_service.total_apostado()

        lineas_caballos = []
        for c in CABALLOS:
            t = totales.get(c["idx"], 0)
            lineas_caballos.append(
                f"{c['emoji']} <b>{c['nombre']}</b> — {c['color']}  "
                f"(<i>{t:,} ✨ apostados</i>)"
            )

        titulo = "🏁 <b>¡CARRERAS UNIVERSE!</b> 🏁\n\n" if primera_vez else "🔄 <b>Ronda abierta</b>\n\n"

        texto = (
            f"{titulo}"
            f"{'  '.join('')}\n"
            f"🐎 <b>Participantes:</b>\n"
            + "\n".join(lineas_caballos)
            + f"\n\n💰 Pool total: <b>{pool:,} ✨</b>"
            f"\n⏰ Quedan <b>{DURACION_APUESTAS // 60} minutos</b> para apostar."
            f"\n\n🎯 Pulsa el botón para elegir tu caballo."
        )

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🏇 ¡Apostar!", callback_data="carrera_apostar"))

        msg = self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid, reply_markup=kb)
        carreras_service.set_msg_id(msg.message_id)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def cb_carreras(self, call: types.CallbackQuery) -> None:
        uid = call.from_user.id
        cid = call.message.chat.id

        if not db_manager.user_exists(uid):
            self.bot.answer_callback_query(call.id, "⚠️ Debes registrarte primero.", show_alert=True)
            return

        if not carreras_service.activa:
            self.bot.answer_callback_query(call.id, "⚠️ No hay carrera activa.", show_alert=True)
            return

        data = call.data

        if data == "carrera_apostar":
            self._cb_elegir_caballo(call)
        elif data.startswith("carrera_caballo:"):
            idx = int(data.split(":")[1])
            self._cb_elegir_monto(call, idx)
        elif data.startswith("carrera_monto:"):
            _, idx_str, cosmos_str = data.split(":")
            self._cb_confirmar(call, int(idx_str), int(cosmos_str))
        else:
            self.bot.answer_callback_query(call.id, "Acción desconocida.")

    def _cb_elegir_caballo(self, call: types.CallbackQuery) -> None:
        """Muestra los 5 caballos para elegir."""
        self.bot.answer_callback_query(call.id)
        uid    = call.from_user.id
        actual = carreras_service.get_apuesta_usuario(uid)

        texto = "🏇 <b>Elegí tu caballo:</b>"
        if actual:
            cab = CABALLOS[actual.caballo_idx]
            texto += f"\n<i>(Apuesta actual: {cab['emoji']} {cab['nombre']} — {actual.cosmos:,} ✨)</i>"

        kb = types.InlineKeyboardMarkup(row_width=1)
        for c in CABALLOS:
            totales = carreras_service.apuestas_por_caballo()
            t = totales.get(c["idx"], 0)
            kb.add(types.InlineKeyboardButton(
                f"{c['emoji']} {c['nombre']}  ({t:,} ✨ apostados)",
                callback_data=f"carrera_caballo:{c['idx']}",
            ))

        try:
            self.bot.edit_message_text(
                texto,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception:
            pass

    def _cb_elegir_monto(self, call: types.CallbackQuery, caballo_idx: int) -> None:
        """Muestra los montos rápidos para apostar."""
        self.bot.answer_callback_query(call.id)
        uid    = call.from_user.id
        saldo  = economy_service.get_balance(uid)
        caballo = CABALLOS[caballo_idx]

        texto = (
            f"{caballo['emoji']} <b>{caballo['nombre']}</b>\n\n"
            f"💳 Tu saldo: <b>{saldo:,} ✨</b>\n"
            f"Elegí cuánto apostás:"
        )

        kb = types.InlineKeyboardMarkup(row_width=3)
        botones = []
        for m in _MONTOS_RAPIDOS:
            if saldo >= m:
                botones.append(types.InlineKeyboardButton(
                    f"{m:,} ✨",
                    callback_data=f"carrera_monto:{caballo_idx}:{m}",
                ))
        if saldo >= _APUESTA_MIN:
            botones.append(types.InlineKeyboardButton(
                "💎 All In",
                callback_data=f"carrera_monto:{caballo_idx}:{min(saldo, _APUESTA_MAX)}",
            ))
        if not botones:
            self.bot.answer_callback_query(
                call.id, f"❌ Necesitás al menos {_APUESTA_MIN} ✨", show_alert=True
            )
            return

        kb.add(*botones)
        try:
            self.bot.edit_message_text(
                texto,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception:
            pass

    def _cb_confirmar(self, call: types.CallbackQuery, caballo_idx: int, cosmos: int) -> None:
        """Registra la apuesta definitiva."""
        uid     = call.from_user.id
        caballo = CABALLOS[caballo_idx]

        user_info = user_service.get_user_info(uid)
        nombre    = user_info.get("nombre", "Usuario") if user_info else "Usuario"

        # Si ya tenía apuesta, reembolsar la anterior primero
        apuesta_anterior = carreras_service.get_apuesta_usuario(uid)
        if apuesta_anterior:
            economy_service.add_credits(uid, apuesta_anterior.cosmos, "carreras_cambio_apuesta")

        saldo = economy_service.get_balance(uid)
        if saldo < cosmos:
            self.bot.answer_callback_query(
                call.id, f"❌ Saldo insuficiente: {saldo:,} ✨", show_alert=True
            )
            return

        if not economy_service.subtract_credits(uid, cosmos, "carreras_apuesta"):
            self.bot.answer_callback_query(call.id, "❌ Error al descontar cosmos.", show_alert=True)
            return

        ok, err = carreras_service.registrar_apuesta(uid, nombre, caballo_idx, cosmos)
        if not ok:
            economy_service.add_credits(uid, cosmos, "carreras_reembolso")
            self.bot.answer_callback_query(call.id, f"❌ {err}", show_alert=True)
            return

        self.bot.answer_callback_query(
            call.id,
            f"✅ ¡Apostaste {cosmos:,} ✨ a {caballo['emoji']} {caballo['nombre']}!",
            show_alert=True,
        )

        # Restaurar el panel de anuncio
        try:
            self.bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("🏇 ¡Apostar!", callback_data="carrera_apostar")
                ),
            )
        except Exception:
            pass

        logger.info("[CARRERA] %s apostó %d ✨ al caballo %s", nombre, cosmos, caballo["nombre"])

    # ── Carrera automática ────────────────────────────────────────────────────

    def _ejecutar_carrera_automatica(self) -> None:
        """Disparado por el timer cuando se acaba el tiempo de apuestas."""
        estado = carreras_service.estado
        if not estado.activa:
            return

        cid = estado.chat_id
        tid = estado.thread_id
        apuestas_snap = list(estado.apuestas)   # snapshot antes de desactivar

        # Desactivar para prevenir nuevas apuestas
        carreras_service.desactivar()

        if not apuestas_snap:
            self.bot.send_message(
                cid,
                "🏁 La carrera fue cancelada: nadie apostó.",
                parse_mode="HTML",
                message_thread_id=tid,
            )
            return

        # ── Anuncio de inicio ──────────────────────────────────────────────
        msg_anim = self.bot.send_message(
            cid,
            "🏁 <b>¡¡¡ARRANCAN LOS CABALLOS!!!</b> 🏁\n\n"
            + carreras_service.render_frame([0] * len(CABALLOS)),
            parse_mode="HTML",
            message_thread_id=tid,
        )

        # ── Simular carrera ────────────────────────────────────────────────
        ganador_idx, frames = carreras_service.ejecutar_carrera()

        # Animar cada N frames para no saturar la API
        paso_animacion = max(1, len(frames) // 6)
        for i, (_, posiciones) in enumerate(frames):
            if i % paso_animacion == 0 or i == len(frames) - 1:
                try:
                    self.bot.edit_message_text(
                        "🏁 <b>¡¡¡CARRERA EN CURSO!!!</b> 🏁\n\n"
                        + carreras_service.render_frame(posiciones),
                        chat_id=cid,
                        message_id=msg_anim.message_id,
                        parse_mode="HTML",
                    )
                    time.sleep(0.8)
                except Exception:
                    pass

        # ── Frame final con ganador ────────────────────────────────────────
        pos_final = [PISTA_LONGITUD] * len(CABALLOS)  # tipo todos en meta visual
        # Usar el último frame real
        if frames:
            pos_final = frames[-1][1]

        try:
            self.bot.edit_message_text(
                "🏆 <b>¡LLEGARON A LA META!</b>\n\n"
                + carreras_service.render_frame(pos_final, ganador_idx=ganador_idx),
                chat_id=cid,
                message_id=msg_anim.message_id,
                parse_mode="HTML",
            )
        except Exception:
            pass

        # ── Calcular y distribuir pagos ────────────────────────────────────
        pagos = carreras_service.calcular_pagos(ganador_idx, apuestas_snap)
        caballo_ganador = CABALLOS[ganador_idx]

        ganadores_lineas = []
        for user_id, pago in pagos.items():
            economy_service.add_credits(user_id, pago, "carreras_ganancia")
            nombre_g = next(
                (a.nombre for a in apuestas_snap if a.user_id == user_id), str(user_id)
            )
            ganadores_lineas.append(f"  🏅 {nombre_g}: <b>+{pago:,} ✨</b>")

        pool = sum(a.cosmos for a in apuestas_snap)
        perdedores = [a for a in apuestas_snap if a.caballo_idx != ganador_idx]

        texto_resultado = (
            f"🏆 <b>¡GANÓ {caballo_ganador['emoji']} {caballo_ganador['nombre']}!</b>\n\n"
            f"💰 Pool total: <b>{pool:,} ✨</b>\n\n"
        )
        if ganadores_lineas:
            texto_resultado += "<b>Ganadores:</b>\n" + "\n".join(ganadores_lineas)
        else:
            texto_resultado += "😔 Nadie apostó al ganador. La casa lo agradece."

        if perdedores:
            texto_resultado += (
                f"\n\n😔 <i>Perdedores: "
                + ", ".join(a.nombre for a in perdedores)
                + "</i>"
            )

        self.bot.send_message(
            cid, texto_resultado, parse_mode="HTML", message_thread_id=tid
        )
        logger.info(
            "[CARRERA] Ronda finalizada. Ganador: %s | Pool: %d ✨ | Apostadores: %d",
            caballo_ganador["nombre"], pool, len(apuestas_snap),
        )
