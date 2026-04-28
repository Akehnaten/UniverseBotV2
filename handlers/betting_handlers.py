# -*- coding: utf-8 -*-
"""
handlers/betting_handlers.py
═══════════════════════════════════════════════════════════════════════════════
Handlers del sistema de apuestas deportivas.

Comandos (admins):
  /openbet  deporte/equipoA/equipoB/winA/draw/winB/YYYY-MM-DD HH:MM
  /closebet mesa resultado

Comandos (usuarios):
  /newbet    mesa cosmos resultado
  /apuestas
  /misapuestas
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import telebot

from funciones import user_service
from funciones.betting_service import betting_service
from config import MSG_USUARIO_NO_REGISTRADO, APOSTADOR as _APOSTADOR_ID

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _thread_id(message) -> Optional[int]:
    return getattr(message, "message_thread_id", None)

def _puede_gestionar_apuestas(bot, message) -> bool:
    """Admins del grupo + usuario APOSTADOR de config.py."""
    if message.from_user.id == _APOSTADOR_ID:
        return True
    try:
        status = bot.get_chat_member(
            message.chat.id, message.from_user.id
        ).status
        return status in ("creator", "administrator")
    except Exception:
        return False


def _delete_after(bot, chat_id: int, msg_id: int, delay: float = 10.0) -> None:
    threading.Timer(
        delay,
        lambda: _try_delete(bot, chat_id, msg_id),
    ).start()


def _try_delete(bot, chat_id: int, msg_id: int) -> None:
    try:
        bot.delete_message(chat_id, msg_id)
    except Exception:
        pass


def _send_temp(bot, cid: int, tid, texto: str, delay: float = 12.0) -> None:
    try:
        m = bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
        _delete_after(bot, cid, m.message_id, delay)
    except Exception as e:
        logger.error(f"[BET] Error enviando mensaje temporal: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CLASE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

class BettingHandlers:
    """Handlers del sistema de apuestas."""

    def __init__(self, bot: telebot.TeleBot):
        self.bot = bot
        self._register_handlers()

    def _register_handlers(self) -> None:
        r = self.bot.register_message_handler
        # Admin
        r(self.cmd_openbet,    commands=["openbet"])
        r(self.cmd_closebet,   commands=["closebet"])
        # Usuarios
        r(self.cmd_newbet,     commands=["newbet"])
        r(self.cmd_apuestas,   commands=["apuestas"])
        r(self.cmd_misapuestas, commands=["misapuestas"])

    # =========================================================================
    # /openbet  deporte/equipoA/equipoB/winA/draw/winB/YYYY-MM-DD HH:MM
    # Solo admins
    # =========================================================================

    def cmd_openbet(self, message: telebot.types.Message) -> None:
        """
        Crea una nueva mesa de apuestas.

        Uso:
            /openbet deporte/equipoA/equipoB/winA/draw/winB/YYYY-MM-DD HH:MM

        Ejemplo:
            /openbet Futbol/Barcelona/Juventus/1.1/4/5/2025-11-25 21:45
        """
        cid = message.chat.id
        tid = _thread_id(message)
        uid = message.from_user.id

        _try_delete(self.bot, cid, message.message_id)

        if not _puede_gestionar_apuestas(self.bot, message):
            _send_temp(self.bot, cid, tid, "❌ Solo los admins pueden abrir mesas.")
            return

        # Parsear argumentos: todo lo que va después de /openbet
        text = (message.text or "").strip()
        # Separar el comando del contenido
        partes_cmd = text.split(maxsplit=1)
        if len(partes_cmd) < 2 or not partes_cmd[1].strip():
            _send_temp(
                self.bot, cid, tid,
                "❌ <b>Uso correcto:</b>\n"
                "<code>/openbet deporte/equipoA/equipoB/winA/draw/winB/YYYY-MM-DD HH:MM</code>\n\n"
                "<b>Ejemplo:</b>\n"
                "<code>/openbet Futbol/Barcelona/Juventus/1.1/4/5/2025-11-25 21:45</code>",
                delay=20,
            )
            return

        contenido = partes_cmd[1].strip()

        # El horario tiene un espacio interno (YYYY-MM-DD HH:MM), por eso
        # no podemos simplemente split("/"). Separamos por "/" pero el último
        # fragmento puede contener el espacio del horario.
        # Formato garantizado: 7 segmentos separados por "/"
        segmentos = contenido.split("/")

        if len(segmentos) < 7:
            _send_temp(
                self.bot, cid, tid,
                "❌ Faltan datos. El formato es:\n"
                "<code>deporte/equipoA/equipoB/winA/draw/winB/YYYY-MM-DD HH:MM</code>\n\n"
                f"Recibido: <code>{contenido}</code>",
                delay=20,
            )
            return

        deporte  = segmentos[0].strip()
        equipo_a = segmentos[1].strip()
        equipo_b = segmentos[2].strip()
        horario  = "/".join(segmentos[6:]).strip()  # por si el horario tiene "/"

        try:
            win_a = float(segmentos[3].strip())
            draw  = float(segmentos[4].strip())
            win_b = float(segmentos[5].strip())
        except ValueError:
            _send_temp(
                self.bot, cid, tid,
                "❌ Las cuotas deben ser números.\n"
                f"Recibido: winA=<code>{segmentos[3]}</code>, "
                f"draw=<code>{segmentos[4]}</code>, "
                f"winB=<code>{segmentos[5]}</code>",
                delay=15,
            )
            return

        ok, resultado = betting_service.create_bet(
            deporte, equipo_a, equipo_b, win_a, draw, win_b, horario
        )

        if ok:
            bet_id = resultado
            texto = (
                f"✅ <b>Mesa #{bet_id} creada</b>\n\n"
                f"🏟️ <b>{deporte}</b>\n"
                f"⚔️ {equipo_a} vs {equipo_b}\n"
                f"📅 {horario}\n\n"
                f"📊 Cuotas:\n"
                f"   • {equipo_a} (A): <b>{win_a}×</b>\n"
            )
            if draw > 0:
                texto += f"   • Empate (D): <b>{draw}×</b>\n"
            texto += (
                f"   • {equipo_b} (B): <b>{win_b}×</b>\n\n"
                f"Los usuarios pueden apostar con:\n"
                f"<code>/newbet {bet_id} [cosmos] [A/D/B]</code>"
            )
            # Intentar con thread, luego sin thread, luego DM al admin.
            enviado = False
            for kwargs in (
                {"message_thread_id": tid},
                {},
            ):
                try:
                    self.bot.send_message(cid, texto, parse_mode="HTML", **kwargs)
                    enviado = True
                    break
                except Exception as e:
                    logger.warning(f"[BET] send_message openbet (kwargs={kwargs}): {e}")

            if not enviado:
                # Último recurso: DM al admin que ejecutó el comando
                try:
                    self.bot.send_message(uid, texto, parse_mode="HTML")
                    logger.warning(f"[BET] Confirmación enviada por DM a uid={uid} (grupo bloqueado)")
                except Exception as e:
                    logger.error(f"[BET] No se pudo entregar confirmación de mesa #{bet_id}: {e}")
        else:
            _send_temp(self.bot, cid, tid, resultado, delay=15)

    # =========================================================================
    # /closebet  mesa  resultado
    # Solo admins
    # =========================================================================

    def cmd_closebet(self, message: telebot.types.Message) -> None:
        """
        Cierra una mesa, reparte ganancias y anuncia ganadores.

        Uso:
            /closebet [mesa] [A|D|B]

        Ejemplo:
            /closebet 1 B     ← Mesa 1, ganó el equipo B
        """
        cid = message.chat.id
        tid = _thread_id(message)

        _try_delete(self.bot, cid, message.message_id)

        if not _puede_gestionar_apuestas(self.bot, message):
            _send_temp(self.bot, cid, tid, "❌ Solo los admins pueden cerrar mesas.")
            return

        parts = (message.text or "").split()
        if len(parts) < 3:
            _send_temp(
                self.bot, cid, tid,
                "❌ <b>Uso correcto:</b>\n"
                "<code>/closebet [mesa] [A|D|B]</code>\n\n"
                "<b>Ejemplo:</b> <code>/closebet 1 B</code>",
                delay=15,
            )
            return

        try:
            bet_id  = int(parts[1])
        except ValueError:
            _send_temp(self.bot, cid, tid, "❌ El número de mesa debe ser un entero.", delay=10)
            return

        ganador = parts[2].upper()

        ok, ganadores, mensaje_base = betting_service.close_bet(bet_id, ganador)

        if not ok:
            _send_temp(self.bot, cid, tid, mensaje_base, delay=12)
            return

        # ── Construir mensaje de resultado ────────────────────────────────────
        if not ganadores:
            # Sin ganadores: todos apostaron al equipo equivocado, o error de pago.
            texto = (
                f"🏁 <b>Mesa #{bet_id} cerrada</b>\n\n"
                f"Resultado: <b>{ganador}</b>\n\n"
                f"😔 Nadie acertó el resultado. No hay premios que repartir."
            )
        else:
            lineas_ganadores: list[str] = []
            for g in ganadores:
                username       = g["username"]
                cosmos_apostados = g["cosmos_apostados"]
                ganancia       = g["ganancia"]
                cuota          = g["cuota"]
                lineas_ganadores.append(
                    f"  🏆 <b>{username}</b> — apostó {cosmos_apostados} → "
                    f"ganó <b>{ganancia} cosmos</b> (×{cuota})"
                )

            texto = (
                f"🏁 <b>Mesa #{bet_id} cerrada</b>\n\n"
                f"Resultado: <b>{ganador}</b>\n\n"
                f"🎉 <b>Ganadores ({len(ganadores)}):</b>\n"
                + "\n".join(lineas_ganadores)
            )

        try:
            self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
        except Exception as e:
            logger.error(f"[BET] Error enviando resultado closebet: {e}")

    # =========================================================================
    # /newbet  mesa  cosmos  resultado
    # =========================================================================

    def cmd_newbet(self, message: telebot.types.Message) -> None:
        """
        Realiza una apuesta en una mesa activa.

        Uso:
            /newbet [mesa] [cosmos] [A|D|B]

        Ejemplo:
            /newbet 1 500 A
        """
        cid = message.chat.id
        tid = _thread_id(message)
        uid = message.from_user.id

        _try_delete(self.bot, cid, message.message_id)

        user_info = user_service.get_user_info(uid)
        if not user_info:
            _send_temp(self.bot, cid, tid, MSG_USUARIO_NO_REGISTRADO)
            return

        parts = (message.text or "").split()
        if len(parts) < 4:
            _send_temp(
                self.bot, cid, tid,
                "❌ <b>Uso correcto:</b>\n"
                "<code>/newbet [mesa] [cosmos] [A|D|B]</code>\n\n"
                "<b>Ejemplo:</b> <code>/newbet 1 500 A</code>",
                delay=15,
            )
            return

        try:
            bet_id = int(parts[1])
            cosmos = int(parts[2])
        except ValueError:
            _send_temp(
                self.bot, cid, tid,
                "❌ La mesa y los cosmos deben ser números enteros.\n"
                "Ejemplo: <code>/newbet 1 500 A</code>",
                delay=12,
            )
            return

        opcion   = parts[3].upper()
        username = user_info.get("nombre") or user_info.get("nombre_usuario") or str(uid)

        ok, respuesta = betting_service.place_bet(bet_id, uid, username, cosmos, opcion)

        m = self.bot.send_message(cid, respuesta, parse_mode="HTML", message_thread_id=tid)
        if not ok:
            _delete_after(self.bot, cid, m.message_id, 12.0)

    # =========================================================================
    # /apuestas  — mesas disponibles (horario no alcanzado)
    # =========================================================================

    def cmd_apuestas(self, message: telebot.types.Message) -> None:
        """Muestra las mesas en las que todavía se puede apostar."""
        logger.info("[BET-DIAG] /apuestas ENTRÓ AL HANDLER — uid=%s chat=%s thread=%s",
        message.from_user.id, message.chat.id, _thread_id(message))
        cid = message.chat.id
        tid = _thread_id(message)

        _try_delete(self.bot, cid, message.message_id)

        user_info = user_service.get_user_info(message.from_user.id)
        if not user_info:
            _send_temp(self.bot, cid, tid, MSG_USUARIO_NO_REGISTRADO)
            return

        mesas = betting_service.get_available_bets()

        if not mesas:
            _send_temp(
                self.bot, cid, tid,
                "📭 No hay mesas de apuestas disponibles en este momento.",
                delay=10,
            )
            return

        bloques: list[str] = []
        for mesa in mesas:
            bloques.append(betting_service.format_mesa(mesa))

        texto = (
            "🎰 <b>Mesas de apuestas disponibles</b>\n\n"
            + "\n\n─────────────────\n\n".join(bloques)
            + "\n\nPara apostar usa: <code>/newbet [mesa] [cosmos] [A|D|B]</code>"
        )

        try:
            self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
        except Exception as e:
            logger.error(f"[BET] Error enviando /apuestas: {e}")

    # =========================================================================
    # /misapuestas  — apuestas activas del usuario
    # =========================================================================

    def cmd_misapuestas(self, message: telebot.types.Message) -> None:
        """Muestra las mesas en las que el usuario tiene una apuesta activa."""
        cid = message.chat.id
        tid = _thread_id(message)
        uid = message.from_user.id

        _try_delete(self.bot, cid, message.message_id)

        user_info = user_service.get_user_info(uid)
        if not user_info:
            _send_temp(self.bot, cid, tid, MSG_USUARIO_NO_REGISTRADO)
            return

        mis_mesas = betting_service.get_user_bets(uid)

        if not mis_mesas:
            _send_temp(
                self.bot, cid, tid,
                "📭 No tienes apuestas activas en ninguna mesa.",
                delay=10,
            )
            return

        bloques: list[str] = []
        for mesa in mis_mesas:
            opcion_label = {
                "A": mesa["equipoA"],
                "D": "Empate",
                "B": mesa["equipoB"],
            }.get(mesa["_mi_opcion"], mesa["_mi_opcion"])

            cuotas = {"A": float(mesa["winA"]), "D": float(mesa["draw"]), "B": float(mesa["winB"])}
            cuota  = cuotas.get(mesa["_mi_opcion"], 0)
            potencial = int(mesa["_mi_cosmos"] * cuota)

            bloque = (
                f"🎲 <b>Mesa #{mesa['betID']}</b> — {mesa['deporte']}\n"
                f"⚔️ {mesa['equipoA']} vs {mesa['equipoB']}\n"
                f"📅 {mesa['horario']}\n"
                f"📌 Tu apuesta: <b>{opcion_label} ({mesa['_mi_opcion']})</b>\n"
                f"💸 Apostado: <b>{mesa['_mi_cosmos']} cosmos</b>\n"
                f"💰 Potencial: <b>{potencial} cosmos</b> (×{cuota})"
            )
            bloques.append(bloque)

        nombre = user_info.get("nombre") or "Usuario"
        texto  = (
            f"📋 <b>Apuestas activas de {nombre}</b>\n\n"
            + "\n\n─────────────────\n\n".join(bloques)
        )

        try:
            self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
        except Exception as e:
            logger.error(f"[BET] Error enviando /misapuestas: {e}")


# ── Setup ─────────────────────────────────────────────────────────────────────

def setup(bot: telebot.TeleBot) -> None:
    """Registra los handlers de apuestas en el bot."""
    BettingHandlers(bot)
    logger.info("✅ BettingHandlers registrados")