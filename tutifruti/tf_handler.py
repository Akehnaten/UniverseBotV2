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
    def __init__(self, chat_id: int, creador: int):
        self.chat_id = chat_id
        self.creador = creador
        self.letra: Optional[str] = None
        self.jugadores: dict[int, str] = {}        # uid -> nombre
        self.iniciada = False
        self.listos: set[int] = set()              # quienes tocaron "listo para mí"
        # Edición en curso por usuario en su DM: uid -> categoria que está escribiendo
        self.editando: dict[int, str] = {}
        # message_id del formulario en el DM de cada usuario (para refrescarlo)
        self.form_msg: dict[int, int] = {}
        # Validación: lista de items pendientes [(uid, nombre, categoria, palabra)]
        self.cola_validacion: list[tuple] = []
        self.idx_validacion = 0
        self.votos: dict[tuple, dict[int, bool]] = {}   # (uid,cat) -> {votante: V/X}
        self.validez: dict[int, dict[str, bool]] = {}   # resultado final


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
        self.bot.register_message_handler(self.cmd_cancelar, commands=["tf_cancelar"])
        # Texto en privado: lo usa el jugador para rellenar la categoría que está editando.
        self.bot.register_message_handler(
            self.on_dm_texto,
            func=lambda m: (m.chat.type == "private"
                            and self._ronda is not None
                            and m.from_user.id in (self._ronda.editando if self._ronda else {})),
            content_types=["text"],
        )
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
                self._grupo_msg(message, "No hay ronda. Creá una con /tf_nuevo.")
                return
            if r.iniciada:
                self._grupo("La ronda ya está en curso.")
                return
            if message.from_user.id != r.creador and not self._es_admin(message):
                self._grupo("Solo el creador o un admin puede iniciar.")
                return
            if len(r.jugadores) < 2:
                self._grupo("Hacen falta al menos 2 jugadores.")
                return

            r.iniciada = True
            r.letra = random.choice(_LETRAS)
            # Limpiar cualquier resto de tabla.
            try:
                db_manager.execute_update("DELETE FROM TUTIFRUTI_RESPUESTAS")
            except Exception:
                pass

            self._grupo(
                f"🍓 <b>¡EMPIEZA EL TUTI FRUTI!</b>\n\n"
                f"🔤 Letra: <b>{r.letra}</b>\n\n"
                "Revisen su DM y completen las categorías. Cuando terminen, toquen "
                "«✅ Listo para mí». Para cortar la ronda ya, «🏁 ¡Listo para todos!»."
            )
            # Enviar el formulario a cada jugador por DM.
            for uid, nombre in r.jugadores.items():
                self._enviar_formulario(uid)

            self._timer = threading.Timer(_TIEMPO_RONDA, self._timeout_ronda)
            self._timer.daemon = True
            self._timer.start()

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

    def on_dm_texto(self, message) -> None:
        with self._lock:
            r = self._ronda
            if not r:
                return
            uid = message.from_user.id
            cat = r.editando.get(uid)
            if not cat:
                return
            palabra = (message.text or "").strip()
            # Validación de la letra inicial (suave: avisa pero deja escribir).
            if palabra and r.letra and not scoring.normalizar(palabra).startswith(r.letra.lower()):
                self._dm(uid, f"⚠️ Tu respuesta no empieza con «{r.letra}». Igual la guardé, "
                              "pero puede ser invalidada por los demás.")
            self._guardar_respuesta(uid, cat, palabra)
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
        # Construir cola de validación: solo palabras no vacías.
        r.cola_validacion = []
        for uid, fila in todas.items():
            for cat in CATEGORIAS:
                palabra = (fila.get(cat) or "").strip()
                if palabra:
                    r.cola_validacion.append((uid, r.jugadores.get(uid, "?"), cat, palabra))

        if not r.cola_validacion:
            self._grupo("Nadie escribió ninguna respuesta. Ronda terminada sin puntajes.")
            self._reset()
            return

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
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("✅ V", callback_data="tf_v_1"),
            types.InlineKeyboardButton("❌ X", callback_data="tf_v_0"),
        )
        self._grupo(
            f"<b>{cat}</b> ({self._mencion(uid, nombre)})\n"
            f"➡️ <b>{palabra}</b>\n\n"
            f"({r.idx_validacion + 1}/{len(r.cola_validacion)})  ✅ 0 · ❌ 0",
            reply_markup=kb)

    def _avanzar_validacion(self) -> None:
        r = self._ronda
        r.idx_validacion += 1
        self._publicar_siguiente_validacion()

    def _finalizar(self) -> None:
        r = self._ronda
        respuestas = self._leer_todas()
        puntajes = scoring.calcular_puntajes(respuestas, r.validez)
        totales = scoring.totales(puntajes)

        ranking = sorted(totales.items(), key=lambda kv: kv[1], reverse=True)
        lineas = []
        for pos, (uid, total) in enumerate(ranking, 1):
            medalla = {1: "🥇", 2: "🥈", 3: "🥉"}.get(pos, f"{pos}.")
            lineas.append(f"{medalla} {self._mencion(uid, r.jugadores.get(uid,'?'))} — <b>{total}</b> pts")

        self._grupo(
            f"🏆 <b>RESULTADO — Letra {r.letra}</b>\n\n" + "\n".join(lineas) +
            "\n\n¡Gracias por jugar! La tabla se reinició."
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
        self._dm(uid, f"✏️ Escribí tu respuesta para <b>{cat}</b> (letra {r.letra}):")

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
                f"<b>{cat}</b> ({self._mencion(uid_dueno, nombre)})\n"
                f"➡️ <b>{palabra}</b>\n\n"
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
