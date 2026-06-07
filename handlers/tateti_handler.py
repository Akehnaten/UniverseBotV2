# -*- coding: utf-8 -*-
"""
handlers/tateti_handler.py
════════════════════════════════════════════════════════════════════════════════
Ta-Te-Ti (tres en raya) para 2 jugadores con tablero de botones inline.

Estado en memoria (una partida por chat/thread). Flujo:
  /tateti           → un jugador abre un desafío abierto, o /tateti @rival
  Otro toca "Unirse" (o el retado acepta) → empieza la partida
  Los jugadores tocan las casillas por turnos.
  El bot detecta victoria/empate y cierra.

Comandos:
  /tateti [@rival]  — crear desafío
  /tateti_cancelar  — cancelar la partida/desafío en curso

Callbacks (prefijo ttt_):
  ttt_join          unirse a un desafío abierto
  ttt_<pos>         jugar en la casilla pos (0-8)
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Optional

import telebot
from telebot import types

from config import MSG_USUARIO_NO_REGISTRADO
from funciones import user_service
from utils.thread_utils import get_thread_id

logger = logging.getLogger(__name__)

_TIMEOUT_DESAFIO = 120   # segundos para que alguien acepte el desafío
_VACIO = " "
_X = "❌"
_O = "⭕"

# Combinaciones ganadoras (índices del tablero 3x3).
_LINEAS = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),   # filas
    (0, 3, 6), (1, 4, 7), (2, 5, 8),   # columnas
    (0, 4, 8), (2, 4, 6),              # diagonales
]


@dataclass
class _Partida:
    chat_id: int
    thread_id: Optional[int]
    jugador_x: int                       # uid de quien juega con ❌ (empieza)
    nombre_x: str
    jugador_o: Optional[int] = None      # uid de ⭕ (None mientras es desafío abierto)
    nombre_o: str = ""
    tablero: list = field(default_factory=lambda: [_VACIO] * 9)
    turno: int = 0                       # uid de quien tiene el turno
    message_id: Optional[int] = None     # mensaje del tablero (para editarlo)
    iniciada: bool = False
    rival_objetivo: Optional[int] = None # si fue desafío dirigido a alguien


class TaTeTiHandler:

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        # clave = (chat_id, thread_id) -> _Partida
        self._partidas: dict[tuple, _Partida] = {}
        self._timers: dict[tuple, threading.Timer] = {}
        self._lock = threading.RLock()
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.bot.register_message_handler(self.cmd_tateti, commands=["tateti"])
        self.bot.register_message_handler(self.cmd_cancelar, commands=["tateti_cancelar"])
        self.bot.register_callback_query_handler(
            self.on_callback, func=lambda c: c.data and c.data.startswith("ttt_")
        )

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _clave(self, message_or_call) -> tuple:
        if isinstance(message_or_call, types.CallbackQuery):
            msg = message_or_call.message
        else:
            msg = message_or_call
        return (msg.chat.id, get_thread_id(msg))

    def _mencion(self, uid: int, nombre: str) -> str:
        return f'<a href="tg://user?id={uid}">{nombre}</a>'

    def _cancelar_timer(self, clave: tuple) -> None:
        t = self._timers.pop(clave, None)
        if t:
            t.cancel()

    def _teclado(self, p: _Partida) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=3)
        fila = []
        for i in range(9):
            simbolo = p.tablero[i] if p.tablero[i] != _VACIO else "·"
            fila.append(types.InlineKeyboardButton(simbolo, callback_data=f"ttt_{i}"))
            if len(fila) == 3:
                kb.row(*fila)
                fila = []
        return kb

    def _texto_estado(self, p: _Partida) -> str:
        turno_nombre = p.nombre_x if p.turno == p.jugador_x else p.nombre_o
        turno_simbolo = _X if p.turno == p.jugador_x else _O
        return (
            "🎮 <b>TA-TE-TI</b>\n\n"
            f"{_X} {self._mencion(p.jugador_x, p.nombre_x)}\n"
            f"{_O} {self._mencion(p.jugador_o, p.nombre_o)}\n\n"
            f"Turno de {turno_simbolo} {self._mencion(p.turno, turno_nombre)}"
        )

    # ── /tateti ─────────────────────────────────────────────────────────────────

    def cmd_tateti(self, message) -> None:
        with self._lock:
            clave = self._clave(message)
            cid, tid = clave
            uid = message.from_user.id

            if not user_service.get_user_info(uid):
                self.bot.send_message(cid, MSG_USUARIO_NO_REGISTRADO, message_thread_id=tid)
                return
            if clave in self._partidas:
                self.bot.send_message(
                    cid, "⚠️ Ya hay un Ta-Te-Ti en curso acá. Usá /tateti_cancelar.",
                    message_thread_id=tid)
                return

            nombre = user_service.get_user_info(uid).get("nombre") or message.from_user.first_name

            # ¿Desafío dirigido? (responder a alguien o mencionar)
            rival_uid = None
            if message.reply_to_message and message.reply_to_message.from_user:
                rival_uid = message.reply_to_message.from_user.id

            p = _Partida(
                chat_id=cid, thread_id=tid,
                jugador_x=uid, nombre_x=nombre, turno=uid,
                rival_objetivo=rival_uid,
            )
            self._partidas[clave] = p

            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("✋ Unirse", callback_data="ttt_join"))
            if rival_uid:
                txt = (f"🎮 <b>Ta-Te-Ti</b>\n\n{self._mencion(uid, nombre)} desafía a "
                       f'<a href="tg://user?id={rival_uid}">alguien</a>. ¡Tocá Unirse!')
            else:
                txt = (f"🎮 <b>Ta-Te-Ti</b>\n\n{self._mencion(uid, nombre)} busca rival. "
                       "¡El primero en tocar Unirse juega!")
            m = self.bot.send_message(cid, txt, parse_mode="HTML",
                                      message_thread_id=tid, reply_markup=kb)
            p.message_id = m.message_id

            t = threading.Timer(_TIMEOUT_DESAFIO, lambda: self._timeout_desafio(clave))
            t.daemon = True
            self._timers[clave] = t
            t.start()

    def _timeout_desafio(self, clave: tuple) -> None:
        with self._lock:
            p = self._partidas.get(clave)
            if not p or p.iniciada:
                return
            self._partidas.pop(clave, None)
            try:
                self.bot.edit_message_text(
                    "⌛ Nadie aceptó el desafío de Ta-Te-Ti. Cancelado.",
                    p.chat_id, p.message_id)
            except Exception:
                pass

    def cmd_cancelar(self, message) -> None:
        with self._lock:
            clave = self._clave(message)
            p = self._partidas.get(clave)
            if not p:
                self.bot.send_message(message.chat.id, "No hay partida activa.",
                                      message_thread_id=clave[1])
                return
            self._cancelar_timer(clave)
            self._partidas.pop(clave, None)
            self.bot.send_message(message.chat.id, "🛑 Ta-Te-Ti cancelado.",
                                  message_thread_id=clave[1])

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def on_callback(self, call: types.CallbackQuery) -> None:
        with self._lock:
            clave = self._clave(call)
            p = self._partidas.get(clave)
            if not p:
                self.bot.answer_callback_query(call.id, "Esta partida ya terminó.")
                return

            if call.data == "ttt_join":
                self._unirse(call, p, clave)
            else:
                self._jugar(call, p, clave)

    def _unirse(self, call, p: _Partida, clave) -> None:
        uid = call.from_user.id
        if p.iniciada:
            self.bot.answer_callback_query(call.id, "La partida ya empezó.")
            return
        if uid == p.jugador_x:
            self.bot.answer_callback_query(call.id, "No podés jugar contra vos mismo.", show_alert=True)
            return
        if p.rival_objetivo and uid != p.rival_objetivo:
            self.bot.answer_callback_query(call.id, "Este desafío es para otra persona.", show_alert=True)
            return
        if not user_service.get_user_info(uid):
            self.bot.answer_callback_query(call.id, "No estás registrado.", show_alert=True)
            return

        p.jugador_o = uid
        p.nombre_o = user_service.get_user_info(uid).get("nombre") or call.from_user.first_name
        p.iniciada = True
        self._cancelar_timer(clave)
        self.bot.answer_callback_query(call.id, "¡Te uniste!")
        try:
            self.bot.edit_message_text(
                self._texto_estado(p), p.chat_id, p.message_id,
                parse_mode="HTML", reply_markup=self._teclado(p))
        except Exception as e:
            logger.error(f"[TTT] Error iniciando: {e}")

    def _jugar(self, call, p: _Partida, clave) -> None:
        uid = call.from_user.id
        if not p.iniciada:
            self.bot.answer_callback_query(call.id, "La partida todavía no empezó.")
            return
        if uid not in (p.jugador_x, p.jugador_o):
            self.bot.answer_callback_query(call.id, "No estás en esta partida.", show_alert=True)
            return
        if uid != p.turno:
            self.bot.answer_callback_query(call.id, "No es tu turno.")
            return

        pos = int(call.data.split("_")[1])
        if p.tablero[pos] != _VACIO:
            self.bot.answer_callback_query(call.id, "Esa casilla está ocupada.")
            return

        simbolo = _X if uid == p.jugador_x else _O
        p.tablero[pos] = simbolo
        self.bot.answer_callback_query(call.id)

        # ¿Ganó?
        ganador = self._hay_ganador(p)
        if ganador:
            self._cerrar_partida(p, clave, ganador_simbolo=ganador)
            return
        # ¿Empate?
        if _VACIO not in p.tablero:
            self._cerrar_partida(p, clave, empate=True)
            return

        # Cambiar turno
        p.turno = p.jugador_o if uid == p.jugador_x else p.jugador_x
        try:
            self.bot.edit_message_text(
                self._texto_estado(p), p.chat_id, p.message_id,
                parse_mode="HTML", reply_markup=self._teclado(p))
        except Exception:
            pass

    def _hay_ganador(self, p: _Partida) -> Optional[str]:
        for a, b, c in _LINEAS:
            if p.tablero[a] != _VACIO and p.tablero[a] == p.tablero[b] == p.tablero[c]:
                return p.tablero[a]
        return None

    def _cerrar_partida(self, p: _Partida, clave, ganador_simbolo=None, empate=False) -> None:
        self._cancelar_timer(clave)
        self._partidas.pop(clave, None)

        if empate:
            texto = (
                "🎮 <b>TA-TE-TI — ¡EMPATE!</b>\n\n"
                f"{self._tablero_final(p)}\n\n"
                "Nadie ganó. ¡Revancha con /tateti!"
            )
        else:
            if ganador_simbolo == _X:
                gan_uid, gan_nombre = p.jugador_x, p.nombre_x
            else:
                gan_uid, gan_nombre = p.jugador_o, p.nombre_o
            texto = (
                f"🎮 <b>TA-TE-TI — ¡GANÓ {ganador_simbolo}!</b>\n\n"
                f"{self._tablero_final(p)}\n\n"
                f"🏆 {self._mencion(gan_uid, gan_nombre)} ganó la partida."
            )
        try:
            self.bot.edit_message_text(texto, p.chat_id, p.message_id, parse_mode="HTML")
        except Exception:
            pass

    def _tablero_final(self, p: _Partida) -> str:
        filas = []
        for r in range(0, 9, 3):
            filas.append("".join(
                p.tablero[r + c] if p.tablero[r + c] != _VACIO else "▫️"
                for c in range(3)))
        return "\n".join(filas)


def setup_tateti_handler(bot):
    TaTeTiHandler(bot)
