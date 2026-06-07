# -*- coding: utf-8 -*-
"""
secrethitler/sh_handler.py
════════════════════════════════════════════════════════════════════════════════
Capa de Telegram para Secret Hitler. Conecta el motor (game_engine) con el
grupo y los DMs, gestiona temporizadores por fase y traduce callbacks.

Diseño (según decisiones del proyecto):
  • Híbrido: tablero y votación en el grupo (thread SECRETHITLER); cartas y
    poderes con información oculta van por DM.
  • Estado en memoria: una sola partida activa por grupo (self._game).
  • Acción por defecto al expirar el timer de cada fase.

Comandos:
  /sh_nuevo    — abre lobby (en el thread de Secret Hitler)
  /sh_unir     — unirse al lobby (requiere DM abierto con el bot)
  /sh_salir    — salir del lobby
  /sh_iniciar  — repartir roles y empezar (creador o admin)
  /sh_cancelar — cancelar partida
  /sh_estado   — mostrar el tablero

Callbacks (prefijo sh_):
  sh_nom_<uid>        nominar canciller
  sh_vote_<ja|nein>   votar
  sh_pdesc_<idx>      presidente descarta carta idx (en DM)
  sh_cprom_<idx>      canciller promulga (descarta idx) (en DM)
  sh_pwr_<uid>        objetivo de un poder (investigar/ejecutar/eleccion)
  sh_peekok           cerrar el peek

Requiere en config.py:
  SECRETHITLER = <thread_id del topic dedicado>
"""
from __future__ import annotations

import logging
import random
import threading
from typing import Optional

import telebot
from telebot import types

from config import CANAL_ID, MSG_USUARIO_NO_REGISTRADO
try:
    from config import SECRETHITLER
except ImportError:
    SECRETHITLER = None  # el handler avisará si no está configurado

from funciones import user_service
from secrethitler.game_engine import (
    SecretHitlerGame, Jugador, Rol, Politica, Poder, Fase,
)
from secrethitler import sh_render as R

logger = logging.getLogger(__name__)

# Tiempos por fase (segundos). Ajustables.
_T_NOMINACION = 60
_T_VOTACION = 60
_T_LEGISLATIVA = 60
_T_PODER = 60

_MIN_JUGADORES = 5
_MAX_JUGADORES = 10


class SecretHitlerHandler:

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        # Una partida activa por grupo. Para multi-grupo, usar dict[chat_id].
        self._game: Optional[SecretHitlerGame] = None
        self._lobby: list[dict] = []          # [{uid, nombre}]
        self._creador: Optional[int] = None
        self._chat_id: Optional[int] = None
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.RLock()
        self._register_handlers()

    # ── Registro ──────────────────────────────────────────────────────────────

    def _register_handlers(self) -> None:
        self.bot.register_message_handler(self.cmd_nuevo,    commands=["sh_nuevo"])
        self.bot.register_message_handler(self.cmd_unir,     commands=["sh_unir"])
        self.bot.register_message_handler(self.cmd_salir,    commands=["sh_salir"])
        self.bot.register_message_handler(self.cmd_iniciar,  commands=["sh_iniciar"])
        self.bot.register_message_handler(self.cmd_cancelar, commands=["sh_cancelar"])
        self.bot.register_message_handler(self.cmd_estado,   commands=["sh_estado"])
        self.bot.register_callback_query_handler(
            self.on_callback, func=lambda c: c.data and c.data.startswith("sh_")
        )

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _en_thread(self, message) -> bool:
        if SECRETHITLER is None:
            self.bot.reply_to(
                message,
                "⚠️ Secret Hitler no está configurado: falta SECRETHITLER en config.py",
            )
            return False
        return getattr(message, "message_thread_id", None) == SECRETHITLER

    def _grupo(self, texto: str, **kw):
        return self.bot.send_message(
            self._chat_id, texto, parse_mode="HTML",
            message_thread_id=SECRETHITLER, **kw,
        )

    def _dm(self, uid: int, texto: str, **kw) -> bool:
        """Envía DM. Devuelve False si el usuario nunca habló con el bot (403)."""
        try:
            self.bot.send_message(uid, texto, parse_mode="HTML", **kw)
            return True
        except Exception as e:
            if "403" in str(e):
                return False
            logger.error(f"[SH] Error DM a {uid}: {e}")
            return False

    def _cancelar_timer(self) -> None:
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _set_timer(self, segundos: int, fn) -> None:
        self._cancelar_timer()
        self._timer = threading.Timer(segundos, fn)
        self._timer.daemon = True
        self._timer.start()

    def _reset(self) -> None:
        self._cancelar_timer()
        self._game = None
        self._lobby = []
        self._creador = None

    # ─────────────────────────────────────────────────────────────────────────
    # LOBBY
    # ─────────────────────────────────────────────────────────────────────────

    def cmd_nuevo(self, message) -> None:
        if not self._en_thread(message):
            return
        with self._lock:
            if self._game or self._lobby:
                self._grupo("⚠️ Ya hay una partida o lobby activo. Usá /sh_cancelar.")
                return
            uid = message.from_user.id
            if not user_service.get_user_info(uid):
                self._grupo(MSG_USUARIO_NO_REGISTRADO)
                return
            self._chat_id = message.chat.id
            self._creador = uid
            nombre = user_service.get_user_info(uid).get("nombre") or message.from_user.first_name
            self._lobby = [{"uid": uid, "nombre": nombre}]
            self._grupo(
                "🏛 <b>Nueva partida de Secret Hitler</b>\n\n"
                f"Creada por {nombre}.\n"
                f"Jugadores ({_MIN_JUGADORES}-{_MAX_JUGADORES}): únanse con /sh_unir\n\n"
                "⚠️ <b>Importante:</b> antes de unirte, abrí un chat privado con el "
                "bot y mandale /start, o no podrás recibir tu carta de rol.\n\n"
                f"👥 En el lobby: 1 ({nombre})"
            )

    def cmd_unir(self, message) -> None:
        if not self._en_thread(message):
            return
        with self._lock:
            if not self._lobby and not self._game:
                self._grupo("No hay lobby abierto. Creá uno con /sh_nuevo.")
                return
            if self._game:
                self._grupo("La partida ya empezó. Esperá a la próxima.")
                return
            uid = message.from_user.id
            if any(p["uid"] == uid for p in self._lobby):
                return
            if len(self._lobby) >= _MAX_JUGADORES:
                self._grupo("El lobby está lleno (10 jugadores).")
                return
            info = user_service.get_user_info(uid)
            if not info:
                self._grupo(MSG_USUARIO_NO_REGISTRADO)
                return
            nombre = info.get("nombre") or message.from_user.first_name
            # CHECK CRÍTICO: ¿podemos abrir DM con este usuario?
            if not self._dm(uid, "✅ Te uniste a Secret Hitler. Recibirás aquí tu carta de rol."):
                self._grupo(
                    f"❌ {nombre}, no puedo enviarte mensajes privados.\n"
                    "Abrí un chat conmigo y mandame /start, luego volvé a usar /sh_unir."
                )
                return
            self._lobby.append({"uid": uid, "nombre": nombre})
            nombres = ", ".join(p["nombre"] for p in self._lobby)
            self._grupo(f"✅ {nombre} se unió.\n👥 Lobby ({len(self._lobby)}): {nombres}")

    def cmd_salir(self, message) -> None:
        if not self._en_thread(message):
            return
        with self._lock:
            if self._game:
                self._grupo("No podés salir de una partida en curso.")
                return
            uid = message.from_user.id
            antes = len(self._lobby)
            self._lobby = [p for p in self._lobby if p["uid"] != uid]
            if len(self._lobby) < antes:
                if not self._lobby:
                    self._reset()
                    self._grupo("El lobby quedó vacío. Partida cancelada.")
                else:
                    self._grupo(f"Saliste del lobby. Quedan {len(self._lobby)}.")

    def cmd_cancelar(self, message) -> None:
        if not self._en_thread(message):
            return
        with self._lock:
            uid = message.from_user.id
            if uid != self._creador and not self._es_admin(message):
                self._grupo("Solo el creador o un admin puede cancelar.")
                return
            self._reset()
            self._grupo("🛑 Partida de Secret Hitler cancelada.")

    def _es_admin(self, message) -> bool:
        try:
            return self.bot.get_chat_member(
                message.chat.id, message.from_user.id
            ).status in ("administrator", "creator")
        except Exception:
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # INICIO DE PARTIDA
    # ─────────────────────────────────────────────────────────────────────────

    def cmd_iniciar(self, message) -> None:
        if not self._en_thread(message):
            return
        with self._lock:
            if self._game:
                self._grupo("Ya hay una partida en curso.")
                return
            uid = message.from_user.id
            if uid != self._creador and not self._es_admin(message):
                self._grupo("Solo el creador o un admin puede iniciar.")
                return
            if len(self._lobby) < _MIN_JUGADORES:
                self._grupo(f"Faltan jugadores. Mínimo {_MIN_JUGADORES}, hay {len(self._lobby)}.")
                return

            # Construir motor con orden de turno aleatorio.
            jugadores = [Jugador(uid=p["uid"], nombre=p["nombre"]) for p in self._lobby]
            random.shuffle(jugadores)
            self._game = SecretHitlerGame(jugadores)
            self._game.repartir_roles()

            # Repartir cartas de rol por DM.
            fallos = []
            for j in self._game.jugadores:
                info = self._game.info_revelacion(j.uid)
                if not self._dm(j.uid, R.carta_rol(info)):
                    fallos.append(j.nombre)

            if fallos:
                self._grupo(
                    "❌ No pude enviar la carta de rol a: " + ", ".join(fallos) +
                    "\nDeben mandarme /start en privado. Partida cancelada."
                )
                self._reset()
                return

            self._grupo("🎴 Roles repartidos por DM. ¡Comienza la partida!")
            self._iniciar_nominacion()

    # ─────────────────────────────────────────────────────────────────────────
    # FASE: NOMINACIÓN
    # ─────────────────────────────────────────────────────────────────────────

    def _iniciar_nominacion(self) -> None:
        g = self._game
        self._grupo(R.tablero(g))
        elegibles = g.elegibles_canciller()
        kb = types.InlineKeyboardMarkup(row_width=2)
        for j in elegibles:
            kb.add(types.InlineKeyboardButton(j.nombre, callback_data=f"sh_nom_{j.uid}"))
        self._grupo(R.anuncio_nominacion(g), reply_markup=kb)
        self._set_timer(_T_NOMINACION, self._timeout_nominacion)

    def _timeout_nominacion(self) -> None:
        with self._lock:
            g = self._game
            if not g or g.fase != Fase.NOMINACION:
                return
            # Acción por defecto: nominar a un elegible al azar.
            elegibles = g.elegibles_canciller()
            if not elegibles:
                self._grupo("⏱ Sin candidatos válidos. Avanza la presidencia.")
                g._avanzar_presidencia()
                self._iniciar_nominacion()
                return
            elegido = random.choice(elegibles)
            self._grupo(f"⏱ Tiempo agotado. Se nomina automáticamente a {elegido.nombre}.")
            g.nominar(elegido.uid)
            self._iniciar_votacion()

    # ─────────────────────────────────────────────────────────────────────────
    # FASE: VOTACIÓN
    # ─────────────────────────────────────────────────────────────────────────

    def _iniciar_votacion(self) -> None:
        g = self._game
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("✅ Ja", callback_data="sh_vote_ja"),
            types.InlineKeyboardButton("❌ Nein", callback_data="sh_vote_nein"),
        )
        self._grupo(R.anuncio_votacion(g), reply_markup=kb)
        self._set_timer(_T_VOTACION, self._timeout_votacion)

    def _timeout_votacion(self) -> None:
        with self._lock:
            g = self._game
            if not g or g.fase != Fase.VOTACION:
                return
            # Acción por defecto: ausentes votan Nein.
            for j in g.vivos:
                if j.uid not in g.votos:
                    g.registrar_voto(j.uid, False)
            self._grupo("⏱ Tiempo agotado. Los votos ausentes cuentan como Nein.")
            self._finalizar_votacion()

    def _finalizar_votacion(self) -> None:
        g = self._game
        self._cancelar_timer()
        r = g.resolver_votacion()
        self._grupo(R.resultado_votacion(g, r))

        if r.get("caos"):
            self._grupo(
                f"😱 <b>Caos:</b> 3 elecciones fallidas. Se promulga "
                f"automáticamente: {R.anuncio_promulgacion(r['carta_caos'])}"
            )
        if r["fin_juego"]:
            self._terminar(r["ganador"], r["motivo"])
            return
        if not r["aprobado"]:
            self._grupo(R.tablero(g))
            self._iniciar_nominacion()
            return
        # Aprobado => fase legislativa por DM.
        self._iniciar_legislativa_presidente()

    # ─────────────────────────────────────────────────────────────────────────
    # FASE: LEGISLATIVA (en DM)
    # ─────────────────────────────────────────────────────────────────────────

    def _iniciar_legislativa_presidente(self) -> None:
        g = self._game
        presi = g.jugador(g.uid_presidente)
        cartas = g.mano_presidente
        kb = types.InlineKeyboardMarkup()
        for i, c in enumerate(cartas):
            icono = R.LIB if c == Politica.LIBERAL else R.FAS
            kb.add(types.InlineKeyboardButton(
                f"Descartar {icono}", callback_data=f"sh_pdesc_{i}"))
        self._dm(presi.uid, R.mano_para_descartar(cartas, es_presidente=True),
                 reply_markup=kb)
        self._grupo(
            f"📜 {R._mencion(presi)} (Presidente) está eligiendo qué descartar… (en DM)"
        )
        self._set_timer(_T_LEGISLATIVA, self._timeout_leg_presidente)

    def _timeout_leg_presidente(self) -> None:
        with self._lock:
            g = self._game
            if not g or g.fase != Fase.LEGISLATIVA_PRES:
                return
            g.presidente_descarta(0)  # descarta la primera por defecto
            self._grupo("⏱ El Presidente tardó demasiado. Se descartó una carta automáticamente.")
            self._iniciar_legislativa_canciller()

    def _iniciar_legislativa_canciller(self) -> None:
        g = self._game
        canc = g.jugador(g.uid_canciller)
        cartas = g.mano_canciller
        kb = types.InlineKeyboardMarkup()
        for i, c in enumerate(cartas):
            icono = R.LIB if c == Politica.LIBERAL else R.FAS
            otra = cartas[1 - i]
            otra_ic = R.LIB if otra == Politica.LIBERAL else R.FAS
            kb.add(types.InlineKeyboardButton(
                f"Promulgar {otra_ic} (descartar {icono})",
                callback_data=f"sh_cprom_{i}"))
        # Botón de veto solo si está desbloqueado (5+ políticas fascistas).
        if g.veto_disponible():
            kb.add(types.InlineKeyboardButton(
                "🚫 Proponer veto", callback_data="sh_vetoprop"))
        self._dm(canc.uid, R.mano_para_descartar(cartas, es_presidente=False),
                 reply_markup=kb)
        aviso = f"📜 {R._mencion(canc)} (Canciller) está decidiendo la política… (en DM)"
        if g.veto_disponible():
            aviso += "\n🚫 El veto está disponible."
        self._grupo(aviso)
        self._set_timer(_T_LEGISLATIVA, self._timeout_leg_canciller)

    def _timeout_leg_canciller(self) -> None:
        with self._lock:
            g = self._game
            if not g or g.fase != Fase.LEGISLATIVA_CANC:
                return
            res = g.canciller_promulga(0)
            self._grupo("⏱ El Canciller tardó demasiado. Se promulgó una carta automáticamente.")
            self._tras_promulgar(res)

    # ── Sub-flujo de veto ──────────────────────────────────────────────────────

    def _iniciar_decision_veto(self) -> None:
        g = self._game
        presi = g.jugador(g.uid_presidente)
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("✅ Aceptar veto", callback_data="sh_veto_si"),
            types.InlineKeyboardButton("❌ Rechazar veto", callback_data="sh_veto_no"),
        )
        # La decisión del presidente es información pública (botones en grupo).
        self._grupo(R.propuesta_veto(g), reply_markup=kb)
        self._set_timer(_T_LEGISLATIVA, self._timeout_veto)

    def _timeout_veto(self) -> None:
        with self._lock:
            g = self._game
            if not g or g.fase != Fase.VETO:
                return
            # Acción por defecto: el presidente rechaza el veto.
            self._grupo("⏱ El Presidente no respondió. El veto se rechaza por defecto.")
            r = g.presidente_responde_veto(acepta=False)
            self._grupo(R.veto_rechazado(g))
            self._iniciar_legislativa_canciller()

    def _resolver_veto(self, acepta: bool) -> None:
        g = self._game
        self._cancelar_timer()
        r = g.presidente_responde_veto(acepta=acepta)
        if not acepta:
            self._grupo(R.veto_rechazado(g))
            self._iniciar_legislativa_canciller()
            return
        # Veto aceptado.
        self._grupo(R.veto_aceptado())
        if r.get("caos"):
            self._grupo(
                f"😱 <b>Caos:</b> 3 elecciones fallidas. Se promulga "
                f"automáticamente: {R.anuncio_promulgacion(r['carta_caos'])}"
            )
        if r["fin_juego"]:
            self._terminar(r["ganador"], r["motivo"])
            return
        self._grupo(R.tablero(g))
        self._iniciar_nominacion()

    def _tras_promulgar(self, res) -> None:
        g = self._game
        self._grupo(R.anuncio_promulgacion(res.politica))
        self._grupo(R.tablero(g))
        if res.fin_juego:
            self._terminar(res.ganador, res.motivo)
            return
        if res.poder_activado:
            self._iniciar_poder(res.poder_activado)
            return
        self._iniciar_nominacion()

    # ─────────────────────────────────────────────────────────────────────────
    # FASE: PODERES
    # ─────────────────────────────────────────────────────────────────────────

    def _iniciar_poder(self, poder: Poder) -> None:
        g = self._game
        presi = g.jugador(g.uid_presidente)
        self._grupo(R.anuncio_poder(poder, g))

        if poder == Poder.PEEK:
            cartas = g.peek_mazo()
            iconos = "  ".join(
                R.LIB if c == Politica.LIBERAL else R.FAS for c in cartas)
            self._dm(presi.uid, f"👁 Próximas 3 cartas del mazo:\n{iconos}")
            self._grupo(f"👁 {presi.nombre} miró las próximas cartas. Continúa el juego.")
            self._iniciar_nominacion()
            return

        # Poderes con objetivo: botones en el grupo (solo el presidente puede usar).
        objetivos = [j for j in g.vivos if j.uid != presi.uid]
        kb = types.InlineKeyboardMarkup(row_width=2)
        for j in objetivos:
            kb.add(types.InlineKeyboardButton(j.nombre, callback_data=f"sh_pwr_{j.uid}"))
        self._grupo(
            f"{R._mencion(presi)}, elegí el objetivo:", reply_markup=kb)
        self._set_timer(_T_PODER, lambda: self._timeout_poder(poder))

    def _timeout_poder(self, poder: Poder) -> None:
        with self._lock:
            g = self._game
            if not g or g.fase != Fase.PODER:
                return
            presi = g.jugador(g.uid_presidente)
            objetivos = [j for j in g.vivos if j.uid != presi.uid]
            objetivo = random.choice(objetivos)
            self._grupo(f"⏱ Tiempo agotado. Objetivo automático: {objetivo.nombre}.")
            self._aplicar_poder(poder, objetivo.uid)

    def _aplicar_poder(self, poder: Poder, uid_objetivo: int) -> None:
        g = self._game
        self._cancelar_timer()
        objetivo = g.jugador(uid_objetivo)

        if poder == Poder.EJECUTAR:
            res = g.ejecutar_jugador(uid_objetivo)
            self._grupo(f"💀 {objetivo.nombre} fue ejecutado.")
            if res.fin_juego:
                self._terminar(res.ganador, res.motivo)
                return
            self._iniciar_nominacion()

        elif poder == Poder.INVESTIGAR:
            lealtad = g.investigar_jugador(uid_objetivo)
            presi = g.jugador(g.uid_presidente)
            etiqueta = "Liberal 🔵" if lealtad == Rol.LIBERAL else "Fascista 🔴"
            self._dm(presi.uid, f"🔍 Lealtad de {objetivo.nombre}: <b>{etiqueta}</b>")
            self._grupo(f"🔍 {presi.nombre} investigó a {objetivo.nombre}.")
            self._iniciar_nominacion()

        elif poder == Poder.ELECCION_ESPECIAL:
            g.fijar_eleccion_especial(uid_objetivo)
            self._grupo(f"🎯 {objetivo.nombre} será el próximo Presidente.")
            self._iniciar_nominacion()

    # ─────────────────────────────────────────────────────────────────────────
    # FIN
    # ─────────────────────────────────────────────────────────────────────────

    def _terminar(self, ganador: str, motivo: str) -> None:
        g = self._game
        self._cancelar_timer()
        self._grupo(R.fin_juego(ganador, motivo, g))
        self._reset()

    def cmd_estado(self, message) -> None:
        if not self._en_thread(message):
            return
        if not self._game:
            self._grupo("No hay partida en curso.")
            return
        self._grupo(R.tablero(self._game))

    # ─────────────────────────────────────────────────────────────────────────
    # CALLBACKS
    # ─────────────────────────────────────────────────────────────────────────

    def on_callback(self, call: types.CallbackQuery) -> None:
        with self._lock:
            g = self._game
            data = call.data
            uid = call.from_user.id

            if data.startswith("sh_nom_"):
                self._cb_nominar(call, g, uid)
            elif data.startswith("sh_vote_"):
                self._cb_votar(call, g, uid)
            elif data.startswith("sh_pdesc_"):
                self._cb_pres_descarta(call, g, uid)
            elif data.startswith("sh_cprom_"):
                self._cb_canc_promulga(call, g, uid)
            elif data == "sh_vetoprop":
                self._cb_proponer_veto(call, g, uid)
            elif data.startswith("sh_veto_"):
                self._cb_responder_veto(call, g, uid)
            elif data.startswith("sh_pwr_"):
                self._cb_poder(call, g, uid)

    def _cb_nominar(self, call, g, uid) -> None:
        if not g or g.fase != Fase.NOMINACION:
            self.bot.answer_callback_query(call.id, "Fase incorrecta.")
            return
        if uid != g.uid_presidente:
            self.bot.answer_callback_query(call.id, "Solo el Presidente nomina.", show_alert=True)
            return
        target = int(call.data.split("_")[-1])
        if target not in [j.uid for j in g.elegibles_canciller()]:
            self.bot.answer_callback_query(call.id, "Ese jugador no es elegible.", show_alert=True)
            return
        self.bot.answer_callback_query(call.id, "Canciller nominado.")
        try:
            self.bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        g.nominar(target)
        self._iniciar_votacion()

    def _cb_votar(self, call, g, uid) -> None:
        if not g or g.fase != Fase.VOTACION:
            self.bot.answer_callback_query(call.id, "No hay votación activa.")
            return
        votante = g.jugador(uid)
        if not votante or not votante.vivo:
            self.bot.answer_callback_query(call.id, "No estás en la partida.", show_alert=True)
            return
        if uid in g.votos:
            self.bot.answer_callback_query(call.id, "Ya votaste.")
            return
        ja = call.data.endswith("_ja")
        g.registrar_voto(uid, ja)
        self.bot.answer_callback_query(call.id, "Voto registrado en secreto.")
        if g.votacion_completa():
            self._finalizar_votacion()

    def _cb_pres_descarta(self, call, g, uid) -> None:
        if not g or g.fase != Fase.LEGISLATIVA_PRES:
            self.bot.answer_callback_query(call.id, "Fase incorrecta.")
            return
        if uid != g.uid_presidente:
            self.bot.answer_callback_query(call.id, "No sos el Presidente.", show_alert=True)
            return
        idx = int(call.data.split("_")[-1])
        self.bot.answer_callback_query(call.id, "Carta descartada.")
        try:
            self.bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        g.presidente_descarta(idx)
        self._iniciar_legislativa_canciller()

    def _cb_canc_promulga(self, call, g, uid) -> None:
        if not g or g.fase != Fase.LEGISLATIVA_CANC:
            self.bot.answer_callback_query(call.id, "Fase incorrecta.")
            return
        if uid != g.uid_canciller:
            self.bot.answer_callback_query(call.id, "No sos el Canciller.", show_alert=True)
            return
        idx = int(call.data.split("_")[-1])
        self.bot.answer_callback_query(call.id, "Política promulgada.")
        try:
            self.bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        res = g.canciller_promulga(idx)
        self._tras_promulgar(res)

    def _cb_proponer_veto(self, call, g, uid) -> None:
        if not g or g.fase != Fase.LEGISLATIVA_CANC:
            self.bot.answer_callback_query(call.id, "Fase incorrecta.")
            return
        if uid != g.uid_canciller:
            self.bot.answer_callback_query(call.id, "Solo el Canciller propone veto.", show_alert=True)
            return
        if not g.veto_disponible():
            self.bot.answer_callback_query(call.id, "El veto aún no está disponible.", show_alert=True)
            return
        self.bot.answer_callback_query(call.id, "Veto propuesto. Espera al Presidente.")
        try:
            self.bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        g.canciller_propone_veto()
        self._iniciar_decision_veto()

    def _cb_responder_veto(self, call, g, uid) -> None:
        if not g or g.fase != Fase.VETO:
            self.bot.answer_callback_query(call.id, "No hay veto pendiente.")
            return
        if uid != g.uid_presidente:
            self.bot.answer_callback_query(call.id, "Solo el Presidente responde el veto.", show_alert=True)
            return
        acepta = call.data.endswith("_si")
        self.bot.answer_callback_query(call.id, "Veto aceptado." if acepta else "Veto rechazado.")
        try:
            self.bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        self._resolver_veto(acepta)

    def _cb_poder(self, call, g, uid) -> None:
        if not g or g.fase != Fase.PODER:
            self.bot.answer_callback_query(call.id, "Fase incorrecta.")
            return
        if uid != g.uid_presidente:
            self.bot.answer_callback_query(call.id, "Solo el Presidente usa el poder.", show_alert=True)
            return
        target = int(call.data.split("_")[-1])
        self.bot.answer_callback_query(call.id, "Objetivo elegido.")
        try:
            self.bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        self._aplicar_poder(g.poder_pendiente, target)


def setup_secrethitler_handler(bot):
    SecretHitlerHandler(bot)
