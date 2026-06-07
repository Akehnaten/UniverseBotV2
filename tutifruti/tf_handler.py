# -*- coding: utf-8 -*-
"""
tutifruti/tf_handler.py
════════════════════════════════════════════════════════════════════════════════
Tuti Fruti para el canal de juegos.

Flujo:
  1. /tf_nuevo (en el thread de juegos) abre un lobby.
  2. /tf_unir para entrar (requiere DM abierto con el bot).
  3. /tf_iniciar saca una letra al azar y abre la ronda. El bot manda a cada
     jugador, por DM, un formulario con las 11 categorías para rellenar.
  4. Cada jugador completa escribiendo en su DM y toca "✅ Listo para mí".
     Cualquiera puede tocar "🏁 ¡Listo para todos!" para cortar la ronda ya.
  5. Al cerrarse, comienza la VALIDACIÓN COMUNITARIA en el canal: el bot publica
     cada palabra con botones ✅ V / ❌ X. Vota todo el mundo menos el dueño.
     Mayoría de V (o empate) = válida; mayoría de X = invalidada.
  6. Se calculan los puntajes (10/5/0/15) y se publica el ranking.
  7. La tabla de respuestas de la ronda se borra.

Persistencia: tabla TUTIFRUTI_RESPUESTAS, que se llena durante la ronda y se
vacía (DELETE) al terminar. El estado de control de la ronda vive en memoria.

Requiere en config.py:
  JUEGOS = <thread_id del canal de juegos>   (o reutilizá EVENTOS)
"""
from __future__ import annotations

import logging
import random
import threading
from typing import Optional

import telebot
from telebot import types

from config import MSG_USUARIO_NO_REGISTRADO
try:
    from config import JUEGOS
except ImportError:
    try:
        from config import EVENTOS as JUEGOS
    except ImportError:
        JUEGOS = None

from database import db_manager
from funciones import user_service
from utils.thread_utils import get_thread_id
from tutifruti import scoring
from tutifruti.scoring import CATEGORIAS

logger = logging.getLogger(__name__)

_LETRAS = "ABCDEFGHIJLMNOPRSTU"   # se excluyen letras difíciles (K,Ñ,Q,W,X,Y,Z)
_TIEMPO_RONDA = 300                # segundos máximos para rellenar (luego corta)


# ─────────────────────────────────────────────────────────────────────────────
# Migración de la tabla
# ─────────────────────────────────────────────────────────────────────────────

def _asegurar_tabla() -> None:
    """Crea la tabla de respuestas si no existe (idempotente)."""
    try:
        db_manager.execute_update("""
            CREATE TABLE IF NOT EXISTS TUTIFRUTI_RESPUESTAS (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                userID    INTEGER NOT NULL,
                nombre    TEXT,
                categoria TEXT NOT NULL,
                palabra   TEXT,
                UNIQUE(userID, categoria)
            )
        """)
    except Exception as e:
        logger.error(f"[TF] Error creando tabla: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Estado en memoria de la ronda
# ─────────────────────────────────────────────────────────────────────────────

class _Ronda:
    """
    Mantiene el estado de toda la PARTIDA (varias rondas) y de la ronda en curso.
      • Estado de partida (persiste entre rondas): jugadores, puntaje_acumulado,
        letras_usadas, numero_ronda.
      • Estado de ronda (se reinicia con nueva_ronda): letra, listos, editando,
        form_msg, cola_validacion, votos, validez.
    """
    def __init__(self, chat_id: int, creador: int):
        self.chat_id = chat_id
        self.creador = creador
        self.jugadores: dict[int, str] = {}        # uid -> nombre
        self.iniciada = False
        # ── Estado acumulado de la partida ──
        self.puntaje_acumulado: dict[int, int] = {}   # uid -> puntos totales
        self.letras_usadas: set[str] = set()
        self.numero_ronda = 0
        # ── Estado de la ronda en curso ──
        self.letra: Optional[str] = None
        self.listos: set[int] = set()
        self.editando: dict[int, str] = {}
        self.form_msg: dict[int, int] = {}
        self.cola_validacion: list[tuple] = []
        self.idx_validacion = 0
        self.votos: dict[tuple, dict[int, bool]] = {}
        self.validez: dict[int, dict[str, bool]] = {}
        self.en_validacion = False

    def nueva_ronda(self) -> None:
        """Reinicia solo el estado de la ronda, conservando el acumulado."""
        self.letra = None
        self.listos = set()
        self.editando = {}
        self.form_msg = {}
        self.cola_validacion = []
        self.idx_validacion = 0
        self.votos = {}
        self.validez = {}
        self.en_validacion = False


class TutiFrutiHandler:

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        _asegurar_tabla()
        self._ronda: Optional[_Ronda] = None
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.RLock()
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.bot.register_message_handler(self.cmd_nuevo,    commands=["tf_nuevo"])
        self.bot.register_message_handler(self.cmd_unir,     commands=["tf_unir"])
        self.bot.register_message_handler(self.cmd_iniciar,  commands=["tf_iniciar"])
        self.bot.register_message_handler(self.cmd_terminar, commands=["tf_terminar"])
        self.bot.register_message_handler(self.cmd_cancelar, commands=["tf_cancelar"])
        # La recepción de texto en el DM se hace con register_next_step_handler
        # (ver _cb_elegir_categoria), que tiene prioridad sobre los handlers
        # globales de texto y no compite con otros sistemas (motes, guardería…).
        self.bot.register_callback_query_handler(
            self.on_callback, func=lambda c: c.data and c.data.startswith("tf_")
        )

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _en_juegos(self, message) -> bool:
        if JUEGOS is None:
            self.bot.reply_to(message, "⚠️ Falta configurar JUEGOS en config.py")
            return False
        return get_thread_id(message) == JUEGOS

    def _grupo(self, texto: str, **kw):
        return self.bot.send_message(self._ronda.chat_id, texto, parse_mode="HTML",
                                     message_thread_id=JUEGOS, **kw)

    def _dm(self, uid: int, texto: str, **kw) -> Optional[types.Message]:
        try:
            return self.bot.send_message(uid, texto, parse_mode="HTML", **kw)
        except Exception as e:
            if "403" in str(e):
                return None
            logger.error(f"[TF] Error DM {uid}: {e}")
            return None

    def _mencion(self, uid: int, nombre: str) -> str:
        return f'<a href="tg://user?id={uid}">{nombre}</a>'

    def _reset(self) -> None:
        if self._timer:
            self._timer.cancel()
            self._timer = None
        try:
            db_manager.execute_update("DELETE FROM TUTIFRUTI_RESPUESTAS")
        except Exception as e:
            logger.error(f"[TF] Error limpiando tabla: {e}")
        self._ronda = None

    # ── /tf_nuevo, /tf_unir, /tf_cancelar ──────────────────────────────────────

    def cmd_nuevo(self, message) -> None:
        if not self._en_juegos(message):
            return
        with self._lock:
            if self._ronda:
                self._grupo("⚠️ Ya hay una ronda de Tuti Fruti activa.")
                return
            uid = message.from_user.id
            if not user_service.get_user_info(uid):
                self.bot.send_message(message.chat.id, MSG_USUARIO_NO_REGISTRADO,
                                      message_thread_id=JUEGOS)
                return
            self._ronda = _Ronda(chat_id=message.chat.id, creador=uid)
            nombre = user_service.get_user_info(uid).get("nombre") or message.from_user.first_name
            self._ronda.jugadores[uid] = nombre
            self._grupo(
                "🍓 <b>¡Nuevo Tuti Fruti!</b>\n\n"
                f"Creado por {nombre}.\n"
                "Únanse con /tf_unir y arranquen con /tf_iniciar.\n\n"
                "⚠️ Mandale /start al bot por privado antes de unirte, o no podrás jugar.\n\n"
                f"👥 Jugadores: 1"
            )

    def cmd_unir(self, message) -> None:
        if not self._en_juegos(message):
            return
        with self._lock:
            if not self._ronda:
                self._grupo_msg(message, "No hay ronda abierta. Creá una con /tf_nuevo.")
                return
            if self._ronda.iniciada:
                self._grupo("La ronda ya empezó. Esperá a la próxima.")
                return
            uid = message.from_user.id
            if uid in self._ronda.jugadores:
                return
            info = user_service.get_user_info(uid)
            if not info:
                self.bot.send_message(message.chat.id, MSG_USUARIO_NO_REGISTRADO,
                                      message_thread_id=JUEGOS)
                return
            nombre = info.get("nombre") or message.from_user.first_name
            if self._dm(uid, "✅ Te uniste al Tuti Fruti. Cuando empiece, te mando acá el formulario.") is None:
                self._grupo(f"❌ {nombre}, no puedo escribirte por privado. Mandame /start y reintentá /tf_unir.")
                return
            self._ronda.jugadores[uid] = nombre
            self._grupo(f"✅ {nombre} se unió.\n👥 Jugadores: {len(self._ronda.jugadores)}")

    def _grupo_msg(self, message, texto):
        self.bot.send_message(message.chat.id, texto, parse_mode="HTML", message_thread_id=JUEGOS)

    def cmd_cancelar(self, message) -> None:
        if not self._en_juegos(message):
            return
        with self._lock:
            if not self._ronda:
                return
            if message.from_user.id != self._ronda.creador and not self._es_admin(message):
                self._grupo("Solo el creador o un admin puede cancelar.")
                return
            self._reset()
            self._grupo("🛑 Tuti Fruti cancelado.")

    def _es_admin(self, message) -> bool:
        try:
            return self.bot.get_chat_member(
                message.chat.id, message.from_user.id).status in ("administrator", "creator")
        except Exception:
            return False

    # ── /tf_iniciar ─────────────────────────────────────────────────────────────

    def cmd_iniciar(self, message) -> None:
        if not self._en_juegos(message):
            return
        with self._lock:
            r = self._ronda
            if not r:
                self._grupo_msg(message, "No hay partida. Creá una con /tf_nuevo.")
                return
            if r.iniciada:
                self._grupo("La partida ya está en curso.")
                return
            if message.from_user.id != r.creador and not self._es_admin(message):
                self._grupo("Solo el creador o un admin puede iniciar.")
                return
            if len(r.jugadores) < 2:
                self._grupo("Hacen falta al menos 2 jugadores.")
                return

            r.iniciada = True
            self._grupo(
                "🍓 <b>¡EMPIEZA EL TUTI FRUTI!</b>\n\n"
                "Se jugarán varias rondas. Los puntos se acumulan.\n"
                "El creador puede cerrar el juego cuando quiera con /tf_terminar."
            )
            self._arrancar_ronda()

    def cmd_terminar(self, message) -> None:
        if not self._en_juegos(message):
            return
        with self._lock:
            r = self._ronda
            if not r or not r.iniciada:
                self._grupo_msg(message, "No hay una partida en curso.")
                return
            if message.from_user.id != r.creador and not self._es_admin(message):
                self._grupo("Solo el creador o un admin puede terminar el juego.")
                return
            if r.en_validacion:
                self._grupo("Esperá a que termine la validación de la ronda actual "
                            "y volvé a usar /tf_terminar.")
                return
            if self._timer:
                self._timer.cancel()
                self._timer = None
            self._terminar_partida()

    def _enviar_formulario(self, uid: int) -> None:
        r = self._ronda
        # Pre-crear filas vacías en la BD para este jugador.
        for cat in CATEGORIAS:
            try:
                db_manager.execute_update(
                    "INSERT OR IGNORE INTO TUTIFRUTI_RESPUESTAS (userID, nombre, categoria, palabra) "
                    "VALUES (?, ?, ?, '')",
                    (uid, r.jugadores[uid], cat))
            except Exception as e:
                logger.error(f"[TF] Error pre-insert {uid}/{cat}: {e}")
        m = self._dm(uid, self._texto_formulario(uid),
                     reply_markup=self._teclado_formulario(uid))
        if m:
            r.form_msg[uid] = m.message_id

    def _texto_formulario(self, uid: int) -> str:
        r = self._ronda
        respuestas = self._leer_respuestas(uid)
        lineas = []
        for cat in CATEGORIAS:
            val = respuestas.get(cat, "")
            check = "✏️" if not val else "✅"
            lineas.append(f"{check} <b>{cat}:</b> {val or '—'}")
        return (
            f"🍓 <b>TUTI FRUTI — Letra {r.letra}</b>\n\n"
            "Tocá una categoría para escribir tu respuesta (debe empezar con la "
            f"letra <b>{r.letra}</b>):\n\n" + "\n".join(lineas)
        )

    def _teclado_formulario(self, uid: int) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        botones = [types.InlineKeyboardButton(cat, callback_data=f"tf_cat_{i}")
                   for i, cat in enumerate(CATEGORIAS)]
        for j in range(0, len(botones), 2):
            kb.row(*botones[j:j + 2])
        kb.add(types.InlineKeyboardButton("✅ Listo para mí", callback_data="tf_listo"))
        kb.add(types.InlineKeyboardButton("🏁 ¡Listo para todos!", callback_data="tf_listotodos"))
        return kb

    # ── Lectura/escritura de respuestas en BD ───────────────────────────────────

    def _leer_respuestas(self, uid: int) -> dict[str, str]:
        try:
            filas = db_manager.execute_query(
                "SELECT categoria, palabra FROM TUTIFRUTI_RESPUESTAS WHERE userID = ?", (uid,))
            return {f["categoria"]: (f["palabra"] or "") for f in filas}
        except Exception as e:
            logger.error(f"[TF] Error leyendo respuestas {uid}: {e}")
            return {}

    def _guardar_respuesta(self, uid: int, categoria: str, palabra: str) -> None:
        try:
            db_manager.execute_update(
                "UPDATE TUTIFRUTI_RESPUESTAS SET palabra = ? WHERE userID = ? AND categoria = ?",
                (palabra.strip(), uid, categoria))
        except Exception as e:
            logger.error(f"[TF] Error guardando {uid}/{categoria}: {e}")

    def _leer_todas(self) -> dict[int, dict[str, str]]:
        try:
            filas = db_manager.execute_query(
                "SELECT userID, categoria, palabra FROM TUTIFRUTI_RESPUESTAS")
            out: dict[int, dict[str, str]] = {}
            for f in filas:
                out.setdefault(f["userID"], {})[f["categoria"]] = f["palabra"] or ""
            return out
        except Exception as e:
            logger.error(f"[TF] Error leyendo todas: {e}")
            return {}

    # ── DM: el jugador escribe la respuesta de la categoría que está editando ──

    def _recibir_palabra(self, message, uid_esperado: int, categoria: str) -> None:
        """
        Receptor de register_next_step_handler. Solo procesa si el autor es el
        jugador esperado; si no, vuelve a registrar el paso y descarta.
        """
        # Guard: mensajes de sistema sin autor, o de otra persona.
        if not message.from_user or message.from_user.id != uid_esperado:
            try:
                self.bot.register_next_step_handler_by_chat_id(
                    uid_esperado,
                    lambda m: self._recibir_palabra(m, uid_esperado, categoria))
            except Exception:
                pass
            return

        with self._lock:
            r = self._ronda
            if not r or not r.iniciada:
                return
            uid = message.from_user.id
            palabra = (message.text or "").strip()
            # Si tocó otro botón en vez de escribir, el texto vendría vacío: ignorar.
            if palabra:
                if r.letra and not scoring.normalizar(palabra).startswith(r.letra.lower()):
                    self._dm(uid, f"⚠️ «{palabra}» no empieza con {r.letra}. La guardé igual, "
                                  "pero pueden invalidarla en la votación.")
                self._guardar_respuesta(uid, categoria, palabra)
            r.editando.pop(uid, None)
            # Refrescar el formulario.
            try:
                self.bot.edit_message_text(
                    self._texto_formulario(uid), uid, r.form_msg[uid],
                    parse_mode="HTML", reply_markup=self._teclado_formulario(uid))
            except Exception:
                self._enviar_formulario(uid)

    # ── Cierre de la ronda y validación ──────────────────────────────────────

    def _timeout_ronda(self) -> None:
        with self._lock:
            if self._ronda and self._ronda.iniciada and not self._ronda.cola_validacion:
                self._grupo("⏱ Se acabó el tiempo de la ronda.")
                self._cerrar_recepcion()

    def _cerrar_recepcion(self) -> None:
        """Pasa de la fase de relleno a la validación comunitaria."""
        r = self._ronda
        if self._timer:
            self._timer.cancel()
            self._timer = None

        todas = self._leer_todas()
        # Construir cola de validación AGRUPADA POR CATEGORÍA: primero todos los
        # "Nombre", luego todos los "Animal", etc. (como en el juego de mesa).
        r.cola_validacion = []
        for cat in CATEGORIAS:
            for uid, fila in todas.items():
                palabra = (fila.get(cat) or "").strip()
                if palabra:
                    r.cola_validacion.append((uid, r.jugadores.get(uid, "?"), cat, palabra))

        if not r.cola_validacion:
            # Nadie escribió en esta ronda: no se corta la partida, se pasa a la
            # siguiente letra (o se cierra si ya no quedan letras).
            self._grupo("Nadie escribió nada en esta ronda. Pasamos a la siguiente.")
            if len(r.letras_usadas) >= len(_LETRAS):
                self._terminar_partida()
            else:
                self._timer = threading.Timer(4.0, self._siguiente_ronda_auto)
                self._timer.daemon = True
                self._timer.start()
            return

        r.en_validacion = True
        self._grupo(
            "🗳 <b>VALIDACIÓN COMUNITARIA</b>\n\n"
            "Voten cada palabra: ✅ V si es válida, ❌ X si no. "
            "No podés votar tus propias palabras. Mayoría manda."
        )
        r.idx_validacion = 0
        self._publicar_siguiente_validacion()

    def _publicar_siguiente_validacion(self) -> None:
        r = self._ronda
        if r.idx_validacion >= len(r.cola_validacion):
            self._finalizar()
            return
        uid, nombre, cat, palabra = r.cola_validacion[r.idx_validacion]

        # Si arrancamos una categoría nueva, anunciarla como encabezado.
        es_primera = r.idx_validacion == 0
        cat_anterior = (r.cola_validacion[r.idx_validacion - 1][2]
                        if not es_primera else None)
        if es_primera or cat != cat_anterior:
            self._grupo(f"📋 <b>Revisando categoría: {cat}</b>")

        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("✅ V", callback_data="tf_v_1"),
            types.InlineKeyboardButton("❌ X", callback_data="tf_v_0"),
        )
        self._grupo(
            f"{self._mencion(uid, nombre)}\n"
            f"➡️ <b>{palabra}</b>\n\n"
            f"({r.idx_validacion + 1}/{len(r.cola_validacion)})  ✅ 0 · ❌ 0",
            reply_markup=kb)

    def _avanzar_validacion(self) -> None:
        r = self._ronda
        r.idx_validacion += 1
        self._publicar_siguiente_validacion()

    def _finalizar(self) -> None:
        """Cierra la RONDA: acumula puntos, muestra parciales y encadena la siguiente."""
        r = self._ronda
        r.en_validacion = False
        respuestas = self._leer_todas()
        puntajes = scoring.calcular_puntajes(respuestas, r.validez)
        totales_ronda = scoring.totales(puntajes)

        # Acumular al marcador de la partida.
        for uid in r.jugadores:
            r.puntaje_acumulado[uid] = r.puntaje_acumulado.get(uid, 0) + totales_ronda.get(uid, 0)

        # Ranking de ESTA ronda.
        ranking_r = sorted(totales_ronda.items(), key=lambda kv: kv[1], reverse=True)
        lineas_r = []
        for uid, pts in ranking_r:
            lineas_r.append(f"  {self._mencion(uid, r.jugadores.get(uid,'?'))}: {pts} pts")

        # Marcador acumulado.
        ranking_acum = sorted(r.puntaje_acumulado.items(), key=lambda kv: kv[1], reverse=True)
        lineas_acum = []
        for pos, (uid, total) in enumerate(ranking_acum, 1):
            medalla = {1: "🥇", 2: "🥈", 3: "🥉"}.get(pos, f"{pos}.")
            lineas_acum.append(f"{medalla} {self._mencion(uid, r.jugadores.get(uid,'?'))} — <b>{total}</b> pts")

        self._grupo(
            f"📊 <b>Resultado de la ronda {r.numero_ronda} (letra {r.letra})</b>\n"
            + "\n".join(lineas_r)
            + "\n\n🏆 <b>Marcador acumulado:</b>\n" + "\n".join(lineas_acum)
        )

        # ¿Quedan letras para seguir?
        if len(r.letras_usadas) >= len(_LETRAS):
            self._grupo("¡Se usaron todas las letras disponibles! Cierro la partida.")
            self._terminar_partida()
            return

        # Encadenar la siguiente ronda automáticamente tras una breve pausa.
        self._grupo(
            "▶️ La siguiente ronda arranca en unos segundos…\n"
            "Para cerrar el juego y ver el ganador final: /tf_terminar"
        )
        self._timer = threading.Timer(6.0, self._siguiente_ronda_auto)
        self._timer.daemon = True
        self._timer.start()

    def _siguiente_ronda_auto(self) -> None:
        with self._lock:
            r = self._ronda
            if not r or not r.iniciada:
                return
            self._arrancar_ronda()

    def _arrancar_ronda(self) -> None:
        """Sortea una letra nueva (sin repetir) y abre la fase de relleno."""
        r = self._ronda
        # Limpiar la tabla de respuestas de la ronda anterior.
        try:
            db_manager.execute_update("DELETE FROM TUTIFRUTI_RESPUESTAS")
        except Exception:
            pass
        r.nueva_ronda()
        disponibles = [l for l in _LETRAS if l not in r.letras_usadas]
        r.letra = random.choice(disponibles)
        r.letras_usadas.add(r.letra)
        r.numero_ronda += 1

        self._grupo(
            f"🍓 <b>RONDA {r.numero_ronda} — Letra {r.letra}</b>\n\n"
            "Revisen su DM y completen las categorías. Cuando terminen, «✅ Listo "
            "para mí». Para cortar la ronda ya, «🏁 ¡Listo para todos!»."
        )
        for uid in r.jugadores:
            self._enviar_formulario(uid)

        self._timer = threading.Timer(_TIEMPO_RONDA, self._timeout_ronda)
        self._timer.daemon = True
        self._timer.start()

    def _terminar_partida(self) -> None:
        """Cierra TODA la partida: ranking final acumulado y limpieza."""
        r = self._ronda
        if not r.puntaje_acumulado:
            self._grupo("La partida terminó sin puntajes registrados.")
            self._reset()
            return
        ranking = sorted(r.puntaje_acumulado.items(), key=lambda kv: kv[1], reverse=True)
        lineas = []
        for pos, (uid, total) in enumerate(ranking, 1):
            medalla = {1: "🥇", 2: "🥈", 3: "🥉"}.get(pos, f"{pos}.")
            lineas.append(f"{medalla} {self._mencion(uid, r.jugadores.get(uid,'?'))} — <b>{total}</b> pts")
        ganador_uid = ranking[0][0]
        self._grupo(
            f"🎉 <b>¡FIN DEL TUTI FRUTI!</b>\n"
            f"Se jugaron {r.numero_ronda} ronda(s).\n\n"
            "🏆 <b>RANKING FINAL:</b>\n" + "\n".join(lineas) +
            f"\n\n👑 ¡Gana {self._mencion(ganador_uid, r.jugadores.get(ganador_uid,'?'))}!"
        )
        self._reset()

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def on_callback(self, call: types.CallbackQuery) -> None:
        with self._lock:
            r = self._ronda
            data = call.data
            if not r:
                self.bot.answer_callback_query(call.id, "No hay ronda activa.")
                return
            if data.startswith("tf_cat_"):
                self._cb_elegir_categoria(call, r)
            elif data == "tf_listo":
                self._cb_listo(call, r)
            elif data == "tf_listotodos":
                self._cb_listo_todos(call, r)
            elif data.startswith("tf_v_"):
                self._cb_validar(call, r)

    def _cb_elegir_categoria(self, call, r) -> None:
        uid = call.from_user.id
        if uid not in r.jugadores or not r.iniciada:
            self.bot.answer_callback_query(call.id, "No estás en esta ronda.")
            return
        idx = int(call.data.split("_")[-1])
        cat = CATEGORIAS[idx]
        r.editando[uid] = cat
        self.bot.answer_callback_query(call.id, f"Escribí tu respuesta para {cat}.")
        m = self._dm(uid, f"✏️ Escribí tu respuesta para <b>{cat}</b> (letra {r.letra}):")
        # Esperar el próximo mensaje de ESTE usuario en su DM. Tiene prioridad
        # sobre los handlers de texto globales (motes, guardería, etc.).
        try:
            self.bot.register_next_step_handler_by_chat_id(
                uid, lambda msg: self._recibir_palabra(msg, uid, cat))
        except Exception as e:
            logger.error(f"[TF] Error registrando next_step {uid}: {e}")

    def _cb_listo(self, call, r) -> None:
        uid = call.from_user.id
        if uid not in r.jugadores:
            self.bot.answer_callback_query(call.id, "No estás en esta ronda.")
            return
        r.listos.add(uid)
        self.bot.answer_callback_query(call.id, "Marcado como listo ✅")
        self._grupo(f"✅ {self._mencion(uid, r.jugadores[uid])} terminó. "
                    f"({len(r.listos)}/{len(r.jugadores)})")
        if len(r.listos) >= len(r.jugadores):
            self._cerrar_recepcion()

    def _cb_listo_todos(self, call, r) -> None:
        uid = call.from_user.id
        if uid not in r.jugadores:
            self.bot.answer_callback_query(call.id, "No estás en esta ronda.")
            return
        self.bot.answer_callback_query(call.id, "Cortaste la ronda 🏁")
        self._grupo(f"🏁 {self._mencion(uid, r.jugadores[uid])} cortó la ronda. ¡Tiempo!")
        self._cerrar_recepcion()

    def _cb_validar(self, call, r) -> None:
        if not r.cola_validacion or r.idx_validacion >= len(r.cola_validacion):
            self.bot.answer_callback_query(call.id, "No hay nada que validar ahora.")
            return
        votante = call.from_user.id
        uid_dueno, nombre, cat, palabra = r.cola_validacion[r.idx_validacion]

        if votante == uid_dueno:
            self.bot.answer_callback_query(call.id, "No podés votar tu propia palabra.", show_alert=True)
            return
        if votante not in r.jugadores:
            self.bot.answer_callback_query(call.id, "Solo los jugadores votan.", show_alert=True)
            return

        clave = (uid_dueno, cat)
        r.votos.setdefault(clave, {})
        es_v = call.data.endswith("_1")
        r.votos[clave][votante] = es_v
        self.bot.answer_callback_query(call.id, "Voto registrado.")

        v = sum(1 for x in r.votos[clave].values() if x)
        x = sum(1 for x in r.votos[clave].values() if not x)
        # Actualizar contador en el mensaje.
        try:
            kb = types.InlineKeyboardMarkup(row_width=2)
            kb.add(
                types.InlineKeyboardButton("✅ V", callback_data="tf_v_1"),
                types.InlineKeyboardButton("❌ X", callback_data="tf_v_0"),
            )
            self.bot.edit_message_text(
                f"{self._mencion(uid_dueno, nombre)}\n"
                f"➡️ <b>{palabra}</b>  <i>({cat})</i>\n\n"
                f"({r.idx_validacion + 1}/{len(r.cola_validacion)})  ✅ {v} · ❌ {x}",
                call.message.chat.id, call.message.message_id,
                parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass

        # ¿Votaron todos los habilitados? (todos menos el dueño)
        habilitados = len(r.jugadores) - 1
        if len(r.votos[clave]) >= habilitados:
            valida = scoring.palabra_valida_por_votos(v, x)
            r.validez.setdefault(uid_dueno, {})[cat] = valida
            self._avanzar_validacion()


def setup_tutifruti_handler(bot):
    TutiFrutiHandler(bot)
