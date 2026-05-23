# -*- coding: utf-8 -*-
"""
handlers/duelo_handlers.py
════════════════════════════════════════════════════════════════════════════════
Handler de Duelos de Dados para UniverseBot V2.0

Comandos (cualquier hilo del grupo):
  /duelo @usuario [apuesta]  — Reta a un usuario
  /aceptar_duelo             — Acepta el duelo pendiente (retado)
  /rechazar_duelo            — Rechaza el duelo pendiente (retado)
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

import telebot
from telebot import types

from config import MSG_USUARIO_NO_REGISTRADO
from database import db_manager
from funciones import economy_service, user_service
from funciones.duelo_service import ResultadoDuelo, duelo_service

logger = logging.getLogger(__name__)

_APUESTA_MIN_DUELO = 50
_APUESTA_MAX_DUELO = 100_000


class DueloHandlers:
    """Handler de duelos de dados. Una instancia por proceso."""

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

    def _send_temp(
        self, cid: int, texto: str, tid: Optional[int] = None, delay: float = 10.0
    ) -> None:
        m = self.bot.send_message(cid, texto, message_thread_id=tid, parse_mode="HTML")
        self._del_after(cid, m.message_id, delay)

    def _get_nombre(self, uid: int) -> str:
        info = user_service.get_user_info(uid)
        return info.get("nombre", str(uid)) if info else str(uid)

    def _mencion(self, uid: int, nombre: str) -> str:
        return f'<a href="tg://user?id={uid}">{nombre}</a>'

    # ── /duelo ────────────────────────────────────────────────────────────────

    def cmd_duelo(self, message: telebot.types.Message) -> None:
        """
        /duelo @usuario [apuesta]

        Crea un reto de dados contra otro usuario registrado.
        """
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        if message.chat.type not in ("group", "supergroup"):
            return

        self._del(cid, message.message_id)

        # ── Verificar registro del retador ────────────────────────────────────
        if not db_manager.user_exists(uid):
            self._send_temp(cid, MSG_USUARIO_NO_REGISTRADO, tid)
            return

        nombre_retador = self._get_nombre(uid)

        # ── Parsear argumentos: /duelo @usuario 500 ───────────────────────────
        parts = (message.text or "").split()
        if len(parts) < 3:
            self._send_temp(
                cid,
                "⚄ <b>Duelo de Dados</b>\n\n"
                "Uso: <code>/duelo @usuario [apuesta]</code>\n"
                f"Mínimo: <b>{_APUESTA_MIN_DUELO:,} ✨</b>",
                tid,
            )
            return

        # Buscar al retado por mención o username
        retado_id   = None
        retado_nombre = None

        # Prioridad: mención de usuario en el mensaje
        if message.entities:
            for entity in message.entities:
                if entity.type == "mention":
                    username = message.text[entity.offset + 1: entity.offset + entity.length]
                    rows = db_manager.execute_query(
                        "SELECT userID, nombre FROM USUARIOS WHERE nombre_usuario = ?",
                        (username,),
                    )
                    if rows:
                        retado_id    = rows[0]["userID"]
                        retado_nombre = rows[0]["nombre"]
                    break
                elif entity.type == "text_mention" and entity.user:
                    retado_id    = entity.user.id
                    retado_nombre = self._get_nombre(retado_id)
                    break

        if not retado_id:
            self._send_temp(cid, "❌ No encontré al usuario retado. Mencionalo con @.", tid)
            return

        if retado_id == uid:
            self._send_temp(cid, "❌ No podés retarte a vos mismo.", tid)
            return

        if not db_manager.user_exists(retado_id):
            self._send_temp(cid, "❌ El usuario retado no está registrado.", tid)
            return

        # ── Parsear apuesta ───────────────────────────────────────────────────
        try:
            apuesta = int(parts[-1])
        except ValueError:
            self._send_temp(cid, "❌ La apuesta debe ser un número válido.", tid)
            return

        if apuesta < _APUESTA_MIN_DUELO:
            self._send_temp(cid, f"❌ Apuesta mínima: <b>{_APUESTA_MIN_DUELO:,} ✨</b>", tid)
            return
        if apuesta > _APUESTA_MAX_DUELO:
            self._send_temp(cid, f"❌ Apuesta máxima: <b>{_APUESTA_MAX_DUELO:,} ✨</b>", tid)
            return

        saldo_retador = economy_service.get_balance(uid)
        if saldo_retador < apuesta:
            self._send_temp(
                cid,
                f"❌ No tenés suficientes cosmos. Saldo: <b>{saldo_retador:,} ✨</b>",
                tid,
            )
            return

        saldo_retado = economy_service.get_balance(retado_id)
        if saldo_retado < apuesta:
            self._send_temp(
                cid,
                f"❌ {retado_nombre} no tiene suficientes cosmos para aceptar.",
                tid,
            )
            return

        # ── Reservar cosmos del retador ───────────────────────────────────────
        if not economy_service.subtract_credits(uid, apuesta, "duelo_reserva"):
            self._send_temp(cid, "❌ Error al reservar la apuesta.", tid)
            return

        # ── Crear duelo ───────────────────────────────────────────────────────

        def _timeout():
            """Devuelve la apuesta al retador si nadie acepta en 60 s."""
            duelo = duelo_service.get_duelo_para(retado_id)
            if not duelo:
                return
            duelo_service.cancelar_duelo(retado_id)
            economy_service.add_credits(uid, apuesta, "duelo_timeout_reembolso")
            try:
                self.bot.send_message(
                    cid,
                    f"⏰ El duelo de {self._mencion(uid, nombre_retador)} expiró sin respuesta.\n"
                    f"Apuesta devuelta.",
                    parse_mode="HTML",
                    message_thread_id=tid,
                )
            except Exception:
                pass

        ok, err = duelo_service.crear_duelo(
            retador_id=uid,
            retado_id=retado_id,
            apuesta=apuesta,
            chat_id=cid,
            thread_id=tid,
            on_timeout_callback=_timeout,
        )

        if not ok:
            economy_service.add_credits(uid, apuesta, "duelo_reembolso_conflicto")
            self._send_temp(cid, f"❌ {err}", tid)
            return

        # ── Anuncio del reto ──────────────────────────────────────────────────
        m_retador = self._mencion(uid, nombre_retador)
        m_retado  = self._mencion(retado_id, retado_nombre)

        texto = (
            f"⚄ <b>¡DUELO DE DADOS!</b>\n\n"
            f"🤺 {m_retador} reta a {m_retado}\n"
            f"💰 Apuesta: <b>{apuesta:,} ✨</b>\n\n"
            f"{m_retado}, tenés <b>60 segundos</b> para:\n"
            f"  ✅ <code>/aceptar_duelo</code>\n"
            f"  ❌ <code>/rechazar_duelo</code>"
        )
        self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)

    # ── /aceptar_duelo ────────────────────────────────────────────────────────

    def cmd_aceptar_duelo(self, message: telebot.types.Message) -> None:
        """Acepta el duelo pendiente. Solo puede usarlo el retado."""
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        self._del(cid, message.message_id)

        duelo = duelo_service.get_duelo_para(uid)
        if not duelo:
            self._send_temp(cid, "❌ No tenés ningún duelo pendiente.", tid)
            return

        # ── Reservar cosmos del retado ────────────────────────────────────────
        saldo_retado = economy_service.get_balance(uid)
        if saldo_retado < duelo.apuesta:
            duelo_service.cancelar_duelo(uid)
            economy_service.add_credits(duelo.retador_id, duelo.apuesta, "duelo_reembolso")
            self._send_temp(
                cid,
                f"❌ No tenés suficientes cosmos. Duelo cancelado, apuesta devuelta al retador.",
                tid,
            )
            return

        economy_service.subtract_credits(uid, duelo.apuesta, "duelo_reserva")

        # ── Resolver duelo ────────────────────────────────────────────────────
        resultado, err = duelo_service.resolver_duelo(uid)
        if not resultado:
            self._send_temp(cid, f"❌ {err}", tid)
            return

        self._publicar_resultado(resultado, cid, tid)

    # ── /rechazar_duelo ───────────────────────────────────────────────────────

    def cmd_rechazar_duelo(self, message: telebot.types.Message) -> None:
        """Rechaza el duelo y devuelve la apuesta al retador."""
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        self._del(cid, message.message_id)

        duelo = duelo_service.cancelar_duelo(uid)
        if not duelo:
            self._send_temp(cid, "❌ No tenés ningún duelo pendiente.", tid)
            return

        economy_service.add_credits(duelo.retador_id, duelo.apuesta, "duelo_rechazado_reembolso")

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

    # ── Publicar resultado ────────────────────────────────────────────────────

    def _publicar_resultado(
        self,
        res: ResultadoDuelo,
        cid: int,
        tid: Optional[int],
    ) -> None:
        nombre_retador = self._get_nombre(res.retador_id)
        nombre_retado  = self._get_nombre(res.retado_id)
        m_retador      = self._mencion(res.retador_id, nombre_retador)
        m_retado       = self._mencion(res.retado_id, nombre_retado)

        lineas = [f"⚄ <b>DUELO DE DADOS</b> — {m_retador} vs {m_retado}\n"]

        for i, (r_retador, r_retado) in enumerate(res.rondas, 1):
            prefijo = f"<i>Ronda {i}</i>" if len(res.rondas) > 1 else ""
            lineas.append(
                f"{prefijo}\n"
                f"🤺 {nombre_retador}: {r_retador.render()}\n"
                f"⚔️ {nombre_retado}:  {r_retado.render()}"
            )

        if res.triple_empate:
            lineas.append(
                f"\n🤝 <b>¡TRIPLE EMPATE!</b> Se devuelven las apuestas."
            )
            economy_service.add_credits(res.retador_id, res.apuesta, "duelo_triple_empate")
            economy_service.add_credits(res.retado_id,  res.apuesta, "duelo_triple_empate")
        else:
            perdedor_id = res.retado_id if res.ganador_id == res.retador_id else res.retador_id
            nombre_ganador = nombre_retador if res.ganador_id == res.retador_id else nombre_retado
            m_ganador = self._mencion(res.ganador_id, nombre_ganador)

            # Ganador recibe su apuesta + la del perdedor
            economy_service.add_credits(res.ganador_id, res.apuesta * 2, "duelo_ganancia")

            balance_ganador = economy_service.get_balance(res.ganador_id)
            lineas.append(
                f"\n🏆 <b>¡GANÓ {m_ganador}!</b>\n"
                f"💰 +<b>{res.apuesta:,} ✨</b>\n"
                f"💳 Nuevo saldo: <b>{balance_ganador:,} ✨</b>"
            )

        self.bot.send_message(
            cid,
            "\n".join(lineas),
            parse_mode="HTML",
            message_thread_id=tid,
        )
