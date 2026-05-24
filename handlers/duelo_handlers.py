# -*- coding: utf-8 -*-
"""
handlers/duelo_handlers.py
════════════════════════════════════════════════════════════════════════════════
Handler de Duelos de Dados — UniverseBot V2.0

Comandos (cualquier hilo del grupo):
  /duelo @usuario [apuesta]  — Reta a un usuario
  /aceptar_duelo             — Acepta el duelo (retado)
  /rechazar_duelo            — Rechaza el duelo (retado)

Mecánica:
  · Al aceptar, el bot usa send_dice() de Telegram: dados ANIMADOS reales.
  · Se envía primero el dado del retador, luego el del retado.
  · Se espera 4 s para que ambas animaciones terminen.
  · Si empatan se vuelve a tirar (máx 3 rondas). Triple empate → devuelve cosmos.
  · El resultado usa el valor real del dado de Telegram (no RNG interno).
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import time
import threading
from typing import Optional

import telebot

from config import MSG_USUARIO_NO_REGISTRADO
from database import db_manager
from funciones import economy_service, user_service
from funciones.duelo_service import DueloPendiente, duelo_service

logger = logging.getLogger(__name__)

# Representación visual de cada cara del dado
DADO_CARA = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}

# Segundos a esperar tras enviar los dados (animación de Telegram ~3 s)
_ESPERA_ANIMACION = 4.0
_MAX_RONDAS       = 3


class DueloHandlers:

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.bot.register_message_handler(self.cmd_duelo,          commands=["duelo"])
        self.bot.register_message_handler(self.cmd_aceptar_duelo,  commands=["aceptar_duelo"])
        self.bot.register_message_handler(self.cmd_rechazar_duelo, commands=["rechazar_duelo"])

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _del(self, cid: int, mid: int) -> None:
        try:
            self.bot.delete_message(cid, mid)
        except Exception:
            pass

    def _del_after(self, cid: int, mid: int, delay: float = 10.0) -> None:
        threading.Timer(delay, lambda: self._del(cid, mid)).start()

    def _send_temp(self, cid: int, txt: str, tid: Optional[int] = None, delay: float = 10.0) -> None:
        m = self.bot.send_message(cid, txt, parse_mode="HTML", message_thread_id=tid)
        self._del_after(cid, m.message_id, delay)

    def _get_nombre(self, uid: int) -> str:
        info = user_service.get_user_info(uid)
        return info.get("nombre", str(uid)) if info else str(uid)

    def _mencion(self, uid: int, nombre: str) -> str:
        return f'<a href="tg://user?id={uid}">{nombre}</a>'

    def _send_dado(self, cid: int, tid: Optional[int]):
        """Envía un dado animado de Telegram y devuelve el mensaje."""
        kwargs = {"emoji": "🎲"}
        if tid:
            kwargs["message_thread_id"] = tid
        return self.bot.send_dice(cid, **kwargs)

    # ── /duelo ────────────────────────────────────────────────────────────────

    def cmd_duelo(self, message: telebot.types.Message) -> None:
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        if message.chat.type not in ("group", "supergroup"):
            return
        self._del(cid, message.message_id)

        if not db_manager.user_exists(uid):
            self._send_temp(cid, MSG_USUARIO_NO_REGISTRADO, tid)
            return

        nombre_retador = self._get_nombre(uid)
        parts = (message.text or "").split()

        if len(parts) < 3:
            self._send_temp(
                cid,
                "⚄ <b>Duelo de Dados</b>\n\n"
                "Uso: <code>/duelo @usuario [apuesta]</code>\n"
                f"Mínimo: <b>{duelo_service.apuesta_min:,} ✨</b>",
                tid,
            )
            return

        # ── Resolver usuario retado ────────────────────────────────────────────
        retado_id    = None
        retado_nombre = None
        if message.entities:
            for entity in message.entities:
                if entity.type == "mention":
                    username = message.text[entity.offset + 1: entity.offset + entity.length]
                    rows = db_manager.execute_query(
                        "SELECT userID, nombre FROM USUARIOS WHERE nombre_usuario = ?", (username,)
                    )
                    if rows:
                        retado_id     = rows[0]["userID"]
                        retado_nombre = rows[0]["nombre"]
                    break
                elif entity.type == "text_mention" and entity.user:
                    retado_id     = entity.user.id
                    retado_nombre = self._get_nombre(retado_id)
                    break

        if not retado_id:
            self._send_temp(cid, "❌ No encontré al usuario. Mencionalo con @.", tid)
            return
        if retado_id == uid:
            self._send_temp(cid, "❌ No podés retarte a vos mismo.", tid)
            return
        if not db_manager.user_exists(retado_id):
            self._send_temp(cid, "❌ El usuario retado no está registrado.", tid)
            return

        # ── Validar apuesta ────────────────────────────────────────────────────
        try:
            apuesta = int(parts[-1])
        except ValueError:
            self._send_temp(cid, "❌ La apuesta debe ser un número.", tid)
            return

        if apuesta < duelo_service.apuesta_min:
            self._send_temp(cid, f"❌ Apuesta mínima: <b>{duelo_service.apuesta_min:,} ✨</b>", tid)
            return
        if apuesta > duelo_service.apuesta_max:
            self._send_temp(cid, f"❌ Apuesta máxima: <b>{duelo_service.apuesta_max:,} ✨</b>", tid)
            return

        saldo_retador = economy_service.get_balance(uid)
        if saldo_retador < apuesta:
            self._send_temp(cid, f"❌ Saldo insuficiente. Tenés <b>{saldo_retador:,} ✨</b>.", tid)
            return

        saldo_retado = economy_service.get_balance(retado_id)
        if saldo_retado < apuesta:
            self._send_temp(cid, f"❌ {retado_nombre} no tiene cosmos suficientes.", tid)
            return

        # ── Reservar cosmos del retador ────────────────────────────────────────
        if not economy_service.subtract_credits(uid, apuesta, "duelo_reserva"):
            self._send_temp(cid, "❌ Error al reservar la apuesta.", tid)
            return

        # ── Crear duelo ────────────────────────────────────────────────────────
        def _timeout():
            if not duelo_service.get_duelo_para(retado_id):
                return
            duelo_service.cancelar_duelo(retado_id)
            economy_service.add_credits(uid, apuesta, "duelo_timeout_reembolso")
            try:
                self.bot.send_message(
                    cid,
                    f"⏰ El duelo de {self._mencion(uid, nombre_retador)} expiró. "
                    f"Apuesta devuelta.",
                    parse_mode="HTML",
                    message_thread_id=tid,
                )
            except Exception:
                pass

        ok, err = duelo_service.crear_duelo(uid, retado_id, apuesta, cid, tid, _timeout)
        if not ok:
            economy_service.add_credits(uid, apuesta, "duelo_reembolso_conflicto")
            self._send_temp(cid, f"❌ {err}", tid)
            return

        m_retador = self._mencion(uid, nombre_retador)
        m_retado  = self._mencion(retado_id, retado_nombre)
        self.bot.send_message(
            cid,
            f"⚄ <b>¡RETO DE DADOS!</b>\n\n"
            f"🤺 {m_retador} reta a {m_retado}\n"
            f"💰 Apuesta: <b>{apuesta:,} ✨</b>\n\n"
            f"{m_retado}, tenés <b>60 segundos</b> para:\n"
            f"✅ <code>/aceptar_duelo</code>  ·  ❌ <code>/rechazar_duelo</code>",
            parse_mode="HTML",
            message_thread_id=tid,
        )

    # ── /aceptar_duelo ────────────────────────────────────────────────────────

    def cmd_aceptar_duelo(self, message: telebot.types.Message) -> None:
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id
        self._del(cid, message.message_id)

        duelo_pend = duelo_service.get_duelo_para(uid)
        if not duelo_pend:
            self._send_temp(cid, "❌ No tenés ningún duelo pendiente.", tid)
            return

        # Reservar cosmos del retado
        if economy_service.get_balance(uid) < duelo_pend.apuesta:
            duelo_service.cancelar_duelo(uid)
            economy_service.add_credits(duelo_pend.retador_id, duelo_pend.apuesta, "duelo_reembolso")
            self._send_temp(cid, "❌ No tenés cosmos suficientes. Duelo cancelado, apuesta devuelta.", tid)
            return
        economy_service.subtract_credits(uid, duelo_pend.apuesta, "duelo_reserva")

        # Sacar de pendientes
        duelo, err = duelo_service.aceptar_duelo(uid)
        if not duelo:
            self._send_temp(cid, f"❌ {err}", tid)
            return

        # Ejecutar en thread para no bloquear el bot durante la animación
        threading.Thread(
            target=self._ejecutar_dados,
            args=(duelo, cid, tid),
            daemon=True,
        ).start()

    # ── /rechazar_duelo ───────────────────────────────────────────────────────

    def cmd_rechazar_duelo(self, message: telebot.types.Message) -> None:
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id
        self._del(cid, message.message_id)

        duelo = duelo_service.cancelar_duelo(uid)
        if not duelo:
            self._send_temp(cid, "❌ No tenés ningún duelo pendiente.", tid)
            return

        economy_service.add_credits(duelo.retador_id, duelo.apuesta, "duelo_rechazado")
        nombre_retado  = self._get_nombre(uid)
        nombre_retador = self._get_nombre(duelo.retador_id)
        self.bot.send_message(
            cid,
            f"❌ {self._mencion(uid, nombre_retado)} rechazó el duelo de "
            f"{self._mencion(duelo.retador_id, nombre_retador)}.\n"
            f"Apuesta de <b>{duelo.apuesta:,} ✨</b> devuelta.",
            parse_mode="HTML",
            message_thread_id=tid,
        )

    # ── Animación de dados ────────────────────────────────────────────────────

    def _ejecutar_dados(self, duelo: DueloPendiente, cid: int, tid: Optional[int]) -> None:
        """
        Ejecuta el duelo con dados animados de Telegram.
        Corre en un hilo separado para no bloquear el bot.

        Flujo por ronda:
          1. Mensaje "X vs Y — Ronda N"
          2. Dado animado del retador  🎲
          3. Dado animado del retado   🎲
          4. Espera 4 s (animación)
          5. Veredicto de la ronda
          Si empatan → ronda extra (máx 3). Triple empate → cosmos devueltos.
        """
        nombre_retador = self._get_nombre(duelo.retador_id)
        nombre_retado  = self._get_nombre(duelo.retado_id)
        m_retador      = self._mencion(duelo.retador_id, nombre_retador)
        m_retado       = self._mencion(duelo.retado_id, nombre_retado)

        ganador_id    = None
        triple_empate = False
        historial     = []   # [(v_retador, v_retado), ...]

        for ronda in range(1, _MAX_RONDAS + 1):
            try:
                # ── Anuncio de ronda ──────────────────────────────────────────
                if ronda == 1:
                    encabezado = (
                        f"⚄ <b>DUELO DE DADOS</b>\n"
                        f"{m_retador} vs {m_retado}\n"
                        f"💰 <b>{duelo.apuesta:,} ✨</b> en juego\n\n"
                        f"🎲 ¡A tirar!"
                    )
                else:
                    encabezado = f"🤝 <b>¡Empate!</b> Ronda extra {ronda} de {_MAX_RONDAS}…"

                self.bot.send_message(cid, encabezado, parse_mode="HTML", message_thread_id=tid)
                time.sleep(0.5)

                # ── Lanzar dado del retador ───────────────────────────────────
                self.bot.send_message(
                    cid, f"🎲 <b>{nombre_retador}</b> tira…",
                    parse_mode="HTML", message_thread_id=tid,
                )
                time.sleep(0.3)
                msg_dado_retador = self._send_dado(cid, tid)
                time.sleep(0.8)

                # ── Lanzar dado del retado ────────────────────────────────────
                self.bot.send_message(
                    cid, f"🎲 <b>{nombre_retado}</b> tira…",
                    parse_mode="HTML", message_thread_id=tid,
                )
                time.sleep(0.3)
                msg_dado_retado = self._send_dado(cid, tid)

                # ── Esperar que terminen las animaciones ──────────────────────
                time.sleep(_ESPERA_ANIMACION)

                # ── Leer valores reales de Telegram ──────────────────────────
                v_retador = msg_dado_retador.dice.value
                v_retado  = msg_dado_retado.dice.value
                # Re-fetch para asegurar valor final (Telegram lo incluye en el send)
                v_retador = msg_dado_retador.dice.value
                v_retado  = msg_dado_retado.dice.value

                historial.append((v_retador, v_retado))

                # ── Veredicto de la ronda ─────────────────────────────────────
                cara_r  = DADO_CARA.get(v_retador, str(v_retador))
                cara_t  = DADO_CARA.get(v_retado,  str(v_retado))

                if v_retador > v_retado:
                    ganador_id = duelo.retador_id
                    self.bot.send_message(
                        cid,
                        f"{cara_r} <b>{nombre_retador}: {v_retador}</b>\n"
                        f"{cara_t} {nombre_retado}: {v_retado}",
                        parse_mode="HTML", message_thread_id=tid,
                    )
                    break
                elif v_retado > v_retador:
                    ganador_id = duelo.retado_id
                    self.bot.send_message(
                        cid,
                        f"{cara_r} {nombre_retador}: {v_retador}\n"
                        f"{cara_t} <b>{nombre_retado}: {v_retado}</b>",
                        parse_mode="HTML", message_thread_id=tid,
                    )
                    break
                else:
                    # Empate en esta ronda
                    self.bot.send_message(
                        cid,
                        f"{cara_r} {nombre_retador}: {v_retador}\n"
                        f"{cara_t} {nombre_retado}: {v_retado}\n"
                        f"<i>Empate en la ronda {ronda}.</i>",
                        parse_mode="HTML", message_thread_id=tid,
                    )
                    time.sleep(1.5)

            except Exception as exc:
                logger.error("[DUELO] Error en ronda %d: %s", ronda, exc, exc_info=True)
                # Devolver cosmos ante error inesperado
                economy_service.add_credits(duelo.retador_id, duelo.apuesta, "duelo_error_reembolso")
                economy_service.add_credits(duelo.retado_id,  duelo.apuesta, "duelo_error_reembolso")
                try:
                    self.bot.send_message(
                        cid,
                        "❌ Error inesperado durante el duelo. Cosmos devueltos a ambos jugadores.",
                        message_thread_id=tid,
                    )
                except Exception:
                    pass
                return
        else:
            triple_empate = True

        # ── Resultado final ───────────────────────────────────────────────────
        time.sleep(0.5)

        if triple_empate:
            economy_service.add_credits(duelo.retador_id, duelo.apuesta, "duelo_triple_empate")
            economy_service.add_credits(duelo.retado_id,  duelo.apuesta, "duelo_triple_empate")
            self.bot.send_message(
                cid,
                f"🤝 <b>¡TRIPLE EMPATE!</b>\n"
                f"Las apuestas de <b>{duelo.apuesta:,} ✨</b> fueron devueltas.",
                parse_mode="HTML", message_thread_id=tid,
            )
            return

        # Pagar al ganador
        perdedor_id   = duelo.retado_id if ganador_id == duelo.retador_id else duelo.retador_id
        nombre_ganador = nombre_retador if ganador_id == duelo.retador_id else nombre_retado
        m_ganador      = self._mencion(ganador_id, nombre_ganador)

        economy_service.add_credits(ganador_id, duelo.apuesta * 2, "duelo_ganancia")
        balance = economy_service.get_balance(ganador_id)

        self.bot.send_message(
            cid,
            f"🏆 <b>¡{m_ganador} GANA EL DUELO!</b>\n\n"
            f"💰 +<b>{duelo.apuesta:,} ✨</b>\n"
            f"💳 Nuevo saldo: <b>{balance:,} ✨</b>",
            parse_mode="HTML", message_thread_id=tid,
        )
        logger.info(
            "[DUELO] Finalizado | ganador=%s | apuesta=%d | rondas=%d",
            ganador_id, duelo.apuesta, len(historial),
        )
