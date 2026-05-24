# -*- coding: utf-8 -*-
"""
handlers/ahorcado_handlers.py
════════════════════════════════════════════════════════════════════════════════
Handler del Ahorcado — UniverseBot V2.0

Comandos (cualquier hilo del grupo):
  /ahorcado           — Palabra aleatoria del banco (863 palabras, 15 categorías)
  /ahorcado ia        — Palabra generada por Groq en tiempo real
  /ahorcado [PALABRA] — Palabra específica del iniciador (bot borra el mensaje)
  /letra X            — Propone la letra X (único punto de entrada oficial)
  /cancelar_ahorcado  — Cancela la partida (iniciador o admin)
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

import telebot

from config import MSG_USUARIO_NO_REGISTRADO
from database import db_manager
from funciones import economy_service, user_service
from funciones.ahorcado_service import (
    MAX_ERRORES,
    RECOMPENSA_BASE,
    PartidaAhorcado,
    ahorcado_service,
)

logger = logging.getLogger(__name__)


class AhorcadoHandlers:

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.bot.register_message_handler(self.cmd_ahorcado,          commands=["ahorcado"])
        self.bot.register_message_handler(self.cmd_letra,             commands=["letra"])
        self.bot.register_message_handler(self.cmd_cancelar_ahorcado, commands=["cancelar_ahorcado"])

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _del(self, cid: int, mid: int) -> None:
        try:
            self.bot.delete_message(cid, mid)
        except Exception:
            pass

    def _del_after(self, cid: int, mid: int, delay: float = 8.0) -> None:
        threading.Timer(delay, lambda: self._del(cid, mid)).start()

    def _err(self, cid: int, txt: str, tid: Optional[int] = None, delay: float = 8.0) -> None:
        m = self.bot.send_message(cid, txt, parse_mode="HTML", message_thread_id=tid)
        self._del_after(cid, m.message_id, delay)

    def _actualizar_panel(self, cid: int, partida: PartidaAhorcado) -> None:
        if not partida.message_id:
            return
        try:
            self.bot.edit_message_text(
                partida.render_panel(),
                chat_id=cid,
                message_id=partida.message_id,
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.warning("[AHORCADO] No se pudo editar el panel: %s", exc)

    def _is_admin(self, cid: int, uid: int) -> bool:
        try:
            return self.bot.get_chat_member(cid, uid).status in ("creator", "administrator")
        except Exception:
            return False

    # ── /ahorcado ─────────────────────────────────────────────────────────────

    def cmd_ahorcado(self, message: telebot.types.Message) -> None:
        """
        /ahorcado           → banco estático (rotación anti-repetición)
        /ahorcado ia        → Groq genera la palabra al momento
        /ahorcado [PALABRA] → palabra específica del iniciador
        """
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        if message.chat.type not in ("group", "supergroup"):
            return

        # Borrar siempre para ocultar la palabra si viene en el comando
        self._del(cid, message.message_id)

        if not db_manager.user_exists(uid):
            self._err(cid, MSG_USUARIO_NO_REGISTRADO, tid)
            return

        user_info = user_service.get_user_info(uid)
        nombre    = user_info.get("nombre", "Usuario") if user_info else "Usuario"
        parts     = (message.text or "").split(maxsplit=1)
        arg       = parts[1].strip() if len(parts) > 1 else ""

        usar_ia   = arg.lower() in ("ia", "groq", "ai")
        palabra   = None if (not arg or usar_ia) else arg

        if palabra and not all(c.isalpha() or c.isspace() for c in palabra):
            self._err(cid, "❌ La palabra solo puede contener letras y espacios.", tid)
            return

        # Si usa IA, avisar que puede tardar un momento
        msg_espera = None
        if usar_ia:
            msg_espera = self.bot.send_message(
                cid, "✨ <i>Generando palabra con IA…</i>",
                parse_mode="HTML", message_thread_id=tid,
            )

        partida, error = ahorcado_service.nueva_partida(
            thread_id=tid or cid,
            iniciador_id=uid,
            iniciador_nombre=nombre,
            palabra=palabra,
            usar_ia=usar_ia,
        )

        if msg_espera:
            self._del(cid, msg_espera.message_id)

        if error or not partida:
            self._err(cid, f"⚠️ {error}", tid)
            return

        # Mostrar categoría solo si es del banco (no si es personalizada o IA)
        disponibles = ahorcado_service.palabras_disponibles(tid or cid)
        pie = ""
        if not usar_ia and not palabra:
            pie = f"\n<i>🗂 {disponibles} palabras restantes en el banco</i>"

        msg = self.bot.send_message(
            cid,
            partida.render_panel() + pie,
            parse_mode="HTML",
            message_thread_id=tid,
        )
        partida.message_id = msg.message_id

        logger.info(
            "[AHORCADO] Nueva partida | thread=%s | palabra=%s | cat=%s | ia=%s",
            tid or cid, partida.palabra, partida.categoria, usar_ia,
        )

    # ── /letra ────────────────────────────────────────────────────────────────

    def cmd_letra(self, message: telebot.types.Message) -> None:
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        if message.chat.type not in ("group", "supergroup"):
            return
        self._del(cid, message.message_id)

        if not db_manager.user_exists(uid):
            self._err(cid, MSG_USUARIO_NO_REGISTRADO, tid)
            return

        user_info = user_service.get_user_info(uid)
        nombre    = user_info.get("nombre", "Usuario") if user_info else "Usuario"
        parts     = (message.text or "").split()

        if len(parts) < 2:
            self._err(cid, "❌ Uso: <code>/letra A</code>", tid)
            return

        partida, feedback, es_correcta = ahorcado_service.proponer_letra(
            thread_id=tid or cid,
            user_id=uid,
            nombre=nombre,
            letra=parts[1],
        )

        if not partida:
            self._err(cid, feedback, tid)
            return

        m = self.bot.send_message(cid, feedback, parse_mode="HTML", message_thread_id=tid)
        self._del_after(cid, m.message_id, 5.0)
        self._actualizar_panel(cid, partida)

        if partida.ganada:
            self._resolver_victoria(partida, cid, tid)
        elif partida.perdida:
            self._resolver_derrota(partida, cid, tid)

    # ── /cancelar_ahorcado ────────────────────────────────────────────────────

    def cmd_cancelar_ahorcado(self, message: telebot.types.Message) -> None:
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id
        self._del(cid, message.message_id)

        partida = ahorcado_service.get_partida(tid or cid)
        if not partida:
            self._err(cid, "❌ No hay partida activa.", tid)
            return
        if uid != partida.iniciador_id and not self._is_admin(cid, uid):
            self._err(cid, "⛔ Solo el iniciador o un admin puede cancelar.", tid)
            return

        ahorcado_service.cancelar_partida(tid or cid)
        m = self.bot.send_message(
            cid,
            f"🚫 Partida cancelada.\n🔤 La palabra era: <b>{partida.palabra}</b>",
            parse_mode="HTML", message_thread_id=tid,
        )
        self._del_after(cid, m.message_id, 15.0)

    # ── Resolución ────────────────────────────────────────────────────────────

    def _resolver_victoria(self, partida: PartidaAhorcado, cid: int, tid: Optional[int]) -> None:
        ahorcado_service.cerrar_partida(tid or cid)

        lineas_premios = []
        for user_id, letras_ok in partida.participantes.items():
            premio = RECOMPENSA_BASE * letras_ok
            economy_service.add_credits(user_id, premio, "ahorcado_victoria")
            info   = user_service.get_user_info(user_id)
            nombre = info.get("nombre", str(user_id)) if info else str(user_id)
            lineas_premios.append(
                f"  🏅 {nombre}: <b>+{premio} ✨</b> ({letras_ok} letra/s)"
            )

        texto = (
            f"🎉 <b>¡GANARON! La palabra era:</b>\n\n"
            f"🔤 <code>{partida.palabra}</code>\n"
            f"<i>Categoría: {partida.categoria}</i>\n\n"
        )
        if lineas_premios:
            texto += "<b>Recompensas:</b>\n" + "\n".join(lineas_premios)
        else:
            texto += "<i>Nadie propuso letras correctas.</i>"

        self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
        logger.info("[AHORCADO] Victoria | thread=%s | palabra=%s", tid or cid, partida.palabra)

    def _resolver_derrota(self, partida: PartidaAhorcado, cid: int, tid: Optional[int]) -> None:
        ahorcado_service.cerrar_partida(tid or cid)

        texto = (
            f"💀 <b>¡PERDIERON!</b>\n\n"
            f"<code>{partida.render_frame()}</code>\n\n"
            f"🔤 La palabra era: <b>{partida.palabra}</b>\n"
            f"<i>Categoría: {partida.categoria}</i>\n\n"
            f"<i>Usá /ahorcado para volver a intentarlo.</i>"
        )
        self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
        logger.info("[AHORCADO] Derrota | thread=%s | palabra=%s", tid or cid, partida.palabra)
