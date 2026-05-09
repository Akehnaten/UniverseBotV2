# -*- coding: utf-8 -*-
"""
handlers/event_handlers.py
════════════════════════════════════════════════════════════════════════════════
Sistema de Verdad o Reto para UniverseBot V2.0

Comandos (thread EVENTOS):
  /participar      — Te une a la lista del juego.
  /verdadoreto     — (solo admins) Sortea 2 jugadores. Si hay turno activo,
                     lo cancela y lanza uno nuevo (útil para saltear AFK).
  /participando    — Muestra quién está en la lista.
  /salir           — Te quita de la lista.
  /expulsar        — (solo admins) Expulsa a un usuario de la lista por
                     username o respondiendo a su mensaje. Cancela el turno
                     si el expulsado era parte de él.
  /terminarjuego   — (solo admins) Termina el juego activo y resetea todo.

Flujo de una ronda:
  1. Admin usa /verdadoreto → bot sortea jugador A (pregunta) y B (responde).
     Si había un turno activo, lo cancela y arranca el nuevo sin bloquear.
  2. Bot publica: "A le toca preguntarle a B — ¿qué le ponés?"
     con botones [🗣️ Verdad automática] [🎯 Reto automático] [✏️ Escribir la mía]
  3a. Si A elige automático → se publica aleatoriamente del banco.
  3b. Si A elige escribir   → bot edita el mensaje y espera que A escriba
      su texto en el canal. El siguiente mensaje de A en ese thread se
      publica formateado para todos.
  4. Los botones se reemplazan con el contenido final.
  5. El turno se libera — listo para el próximo /verdadoreto.

Nota: /salir también es capturado por role_handlers en el thread ROLES.
      Este handler ignora silenciosamente los mensajes de otros threads.
════════════════════════════════════════════════════════════════════════════════
"""

import random
import threading
import logging
from typing import Optional

import telebot
from telebot import types
from utils.thread_utils import get_thread_id

from config import EVENTOS, CANAL_ID, MSG_USUARIO_NO_REGISTRADO
from funciones import user_service

logger = logging.getLogger(__name__)


# ─── Banco de preguntas y retos ───────────────────────────────────────────────

_VERDADES: list[str] = [
    "¿Cuál es la cosa más vergonzosa que te ha pasado?",
    "¿A quién del grupo le mandarías un mensaje a las 3am?",
    "¿Cuál es tu crush secreto dentro del servidor?",
    "¿Qué es lo peor que has hecho y nunca confesaste?",
    "¿Con quién del grupo no te llevarías bien en la vida real?",
    "¿Cuál fue la mentira más grande que dijiste este mes?",
    "¿Qué canción escuchás en secreto pero jamás admitirías?",
    "¿A quién del servidor bloquerías si pudieras sin consecuencias?",
    "¿Cuál es el pensamiento más raro que tuviste hoy?",
    "¿Qué es lo primero que notás cuando conocés a alguien?",
    "¿Alguna vez le hablaste mal de alguien del servidor a otra persona?",
    "¿Cuál es tu mayor inseguridad?",
    "¿Qué harías si tuvieras un día invisible?",
    "¿Cuál fue tu peor cita o situación romántica?",
    "¿A quién del servidor le pedirías consejos de amor?",
    "¿Qué aplicación usás más y no admitirías públicamente?",
    "¿Cuántas veces al día revisás el celular sin motivo?",
    "¿Qué es lo más atrevido que hiciste por llamar la atención?",
    "¿Alguna vez mandaste un mensaje al destinatario equivocado?",
    "¿Cuál es el peor regalo que recibiste y fingiste que te gustó?",
]

_RETOS: list[str] = [
    "Mandá un audio cantando los primeros 10 segundos de una canción.",
    "Escribí 'Te amo' al último contacto de tu lista de chats.",
    "Enviá el último meme que guardaste en tu galería.",
    "Hacé una imitación de texto del admin más estricto del servidor.",
    "Describí a la persona de tu derecha usando solo emojis (3 máx.).",
    "Escribí un mensaje de amor a un personaje ficticio de tu elección.",
    "Contá un chiste en menos de 2 líneas. Si nadie se ríe, contá otro.",
    "Enviá una selfie con la cara más ridícula que puedas hacer.",
    "Cambiá tu nombre en el servidor por 'Patito de Goma' durante 5 minutos.",
    "Escribí un poema de 4 versos sobre el servidor.",
    "Mandá el último sticker que usaste con una frase explicando cuándo lo usarías.",
    "Copiá exactamente el último mensaje que mandaste en otro chat y enviálo aquí.",
    "Hacé una predicción del próximo evento del servidor.",
    "Describí tu día de hoy usando solo palabras de 4 letras.",
    "Enviá una recomendación de algo (canción, serie, lugar) en menos de 20 palabras.",
    "Escribí el nombre de 5 miembros del servidor al revés.",
    "Mandá un mensaje de voz diciendo el abecedario en 10 segundos.",
    "Escribí un trabalenguas inventado sobre algún miembro del servidor.",
    "Adiviná de quién es este mensaje (el admin elige uno antiguo del canal).",
    "Enviá una foto de lo que tenés en la mesa ahora mismo.",
]


# ─── Clase principal ──────────────────────────────────────────────────────────

class EventHandlers:
    """
    Handlers para el sistema de Verdad o Reto y el canal de Eventos.

    Estado en memoria por turno activo (_turno: dict | None):
        preguntador    : dict   — jugador que elige y pone la verdad/reto.
        respondedor    : dict   — jugador que responde o cumple.
        chat_id        : int
        tid            : int | None
        msg_id         : int    — message_id del mensaje con botones.
        esperando_texto: bool   — True cuando se espera texto del preguntador.
    """

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot    = bot
        self._lista: list[dict]     = []    # {"uid", "nombre", "mencion"}
        self._turno: Optional[dict] = None  # turno activo o None
        self._register_handlers()

    # ── Registro de handlers ──────────────────────────────────────────────────

    def _register_handlers(self) -> None:
        # IMPORTANTE: el handler de texto personalizado se registra PRIMERO
        # para que tenga prioridad sobre cualquier catch-all de texto de otros módulos.
        self.bot.register_message_handler(
            self.capturar_texto_personalizado,
            func=self._es_texto_del_preguntador,
            content_types=["text"],
        )
        self.bot.register_message_handler(self.cmd_participar,     commands=["participar"])
        self.bot.register_message_handler(self.cmd_verdadoreto,    commands=["verdadoreto"])
        self.bot.register_message_handler(self.cmd_participando,   commands=["participando"])
        self.bot.register_message_handler(self.cmd_salir_evento,   commands=["salir"])
        self.bot.register_message_handler(self.cmd_expulsar,       commands=["expulsar"])
        self.bot.register_message_handler(self.cmd_terminar_juego, commands=["terminarjuego"])
        self.bot.register_callback_query_handler(
            self.callback_vor,
            func=lambda c: c.data.startswith("vor:"),
        )

    # ── Helpers privados ─────────────────────────────────────────────────────

    def _borrar_seguro(self, chat_id: int, message_id: int) -> None:
        try:
            self.bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    def _temp(
        self,
        chat_id: int,
        texto: str,
        tid: Optional[int],
        delay: float = 7.0,
        parse_mode: str = "HTML",
    ) -> None:
        """Envía un mensaje temporal que se borra automáticamente."""
        try:
            m = self.bot.send_message(
                chat_id, texto,
                parse_mode=parse_mode,
                message_thread_id=tid,
            )
            threading.Timer(
                delay,
                lambda: self._borrar_seguro(chat_id, m.message_id),
            ).start()
        except Exception as e:
            logger.error("[EVENTOS] Error enviando mensaje temporal: %s", e)

    def _verificar_canal_eventos(self, message: telebot.types.Message) -> bool:
        """Devuelve True solo si el mensaje proviene del thread EVENTOS."""
        if message.chat.id != CANAL_ID or get_thread_id(message) != EVENTOS:
            try:
                self.bot.delete_message(message.chat.id, message.message_id)
            except Exception:
                pass
            return False
        return True

    def _es_admin(self, message: telebot.types.Message) -> bool:
        """Devuelve True si el remitente es admin del chat."""
        try:
            member = self.bot.get_chat_member(message.chat.id, message.from_user.id)
            return member.status in ("administrator", "creator")
        except Exception:
            return False

    def _nombre_display(
        self, message: telebot.types.Message, user_info: dict
    ) -> str:
        """Devuelve una mención HTML para el usuario."""
        uid    = message.from_user.id
        nombre = user_info.get("nombre") or message.from_user.first_name or "Jugador"
        return f'<a href="tg://user?id={uid}">{nombre}</a>'

    def _kb_eleccion(self, uid_preguntador: int) -> types.InlineKeyboardMarkup:
        """Teclado inline con las tres opciones para el preguntador."""
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton(
                "🗣️ Verdad automática",
                callback_data=f"vor:auto_verdad:{uid_preguntador}",
            ),
            types.InlineKeyboardButton(
                "🎯 Reto automático",
                callback_data=f"vor:auto_reto:{uid_preguntador}",
            ),
        )
        kb.add(
            types.InlineKeyboardButton(
                "✏️ Escribir la mía",
                callback_data=f"vor:escribir:{uid_preguntador}",
            )
        )
        return kb

    def _cancelar_turno_activo(self) -> None:
        """
        Cancela el turno activo en memoria y elimina el mensaje con botones
        si todavía existe. No lanza excepciones hacia afuera.
        """
        if self._turno is None:
            return
        t = self._turno
        self._turno = None
        try:
            self.bot.edit_message_text(
                "⏭️ <i>Turno cancelado por el administrador.</i>",
                chat_id=t["chat_id"],
                message_id=t["msg_id"],
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            # Si ya fue editado o borrado, no importa
            pass

    def _publicar_resultado(
        self,
        chat_id: int,
        tid: Optional[int],
        msg_id: int,
        tipo: str,
        contenido: str,
        mencion_preguntador: str,
        mencion_respondedor: str,
    ) -> None:
        """Edita el mensaje de la ronda con el resultado final."""
        encabezado = "🗣️ <b>VERDAD</b>" if tipo == "verdad" else "🎯 <b>RETO</b>"
        emoji      = "❓" if tipo == "verdad" else "⚡"
        texto = (
            f"{encabezado}\n\n"
            f"👤 Le toca a: {mencion_respondedor}\n"
            f"📝 Puesto por: {mencion_preguntador}\n\n"
            f"{emoji} {contenido}"
        )
        try:
            self.bot.edit_message_text(
                texto,
                chat_id=chat_id,
                message_id=msg_id,
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            try:
                self.bot.send_message(
                    chat_id, texto,
                    parse_mode="HTML",
                    message_thread_id=tid,
                )
            except Exception as e:
                logger.error("[VoR] Error publicando resultado: %s", e)

    def _es_texto_del_preguntador(self, message: telebot.types.Message) -> bool:
        """
        Filtro para el handler de texto personalizado.
        Activa SOLO si:
          - Hay un turno activo esperando texto.
          - El mensaje viene del preguntador correcto.
          - El mensaje está en el thread EVENTOS del canal correcto.
          - El mensaje no es un comando.
        Registrado primero en _register_handlers para tener prioridad
        sobre cualquier catch-all de texto de otros módulos.
        """
        if self._turno is None:
            return False
        if not self._turno.get("esperando_texto"):
            return False
        if message.chat.id != self._turno.get("chat_id"):
            return False
        if get_thread_id(message) != EVENTOS:
            return False
        if message.from_user.id != self._turno["preguntador"]["uid"]:
            return False
        if (message.text or "").startswith("/"):
            return False
        return True

    # ── /participar ───────────────────────────────────────────────────────────

    def cmd_participar(self, message: telebot.types.Message) -> None:
        """Te une a la lista del juego activo."""
        if not self._verificar_canal_eventos(message):
            return

        cid = message.chat.id
        tid = get_thread_id(message)
        uid = message.from_user.id

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        user_info = user_service.get_user_info(uid)
        if not user_info:
            self._temp(cid, MSG_USUARIO_NO_REGISTRADO, tid)
            return

        if any(p["uid"] == uid for p in self._lista):
            self._temp(
                cid,
                "⚠️ Ya estás en la lista del juego.\nUsá /salir para abandonar.",
                tid,
            )
            return

        nombre     = user_info.get("nombre") or message.from_user.first_name
        mencion    = self._nombre_display(message, user_info)
        es_primero = len(self._lista) == 0

        self._lista.append({"uid": uid, "nombre": nombre, "mencion": mencion})
        logger.info("[VoR] %s (%s) se unió. Total: %s", nombre, uid, len(self._lista))

        if es_primero:
            self.bot.send_message(
                cid,
                "🎲 <b>¡Nuevo juego de Verdad o Reto!</b>\n\n"
                f"👤 {mencion} ha iniciado la partida.\n\n"
                "¿Querés participar? Usá <code>/participar</code>\n"
                "Cuando haya al menos 2 jugadores, un admin lanza "
                "<code>/verdadoreto</code>.",
                parse_mode="HTML",
                message_thread_id=tid,
            )
        else:
            self._temp(
                cid,
                f"✅ {mencion} se unió al juego.\n"
                f"👥 Participantes: <b>{len(self._lista)}</b>",
                tid,
                delay=10.0,
            )

    # ── /verdadoreto ──────────────────────────────────────────────────────────

    def cmd_verdadoreto(self, message: telebot.types.Message) -> None:
        """
        Sortea 2 jugadores e inicia una ronda. Solo admins pueden ejecutarlo.

        Si hay un turno activo (ej: el preguntador está AFK), lo CANCELA
        automáticamente y lanza una ronda nueva sin bloquear.
        """
        if not self._verificar_canal_eventos(message):
            return

        cid = message.chat.id
        tid = get_thread_id(message)

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        if not self._es_admin(message):
            self._temp(cid, "❌ Solo los administradores pueden iniciar el sorteo.", tid)
            return

        if len(self._lista) < 2:
            self._temp(
                cid,
                "⚠️ Se necesitan al menos <b>2 participantes</b> para jugar.\n"
                "Pedile a la gente que use <code>/participar</code>.",
                tid,
            )
            return

        # Si hay un turno activo lo cancelamos antes de arrancar uno nuevo.
        # Esto permite saltear a alguien que esté AFK sin quedarse trabado.
        if self._turno is not None:
            pname = self._turno["preguntador"]["mencion"]
            logger.info("[VoR] Admin canceló turno de %s para lanzar uno nuevo.", pname)
            self._cancelar_turno_activo()  # limpia self._turno y edita el mensaje

        # Sortear 2 jugadores distintos al azar
        elegidos    = random.sample(self._lista, 2)
        preguntador = elegidos[0]
        respondedor = elegidos[1]

        try:
            msg = self.bot.send_message(
                cid,
                f"🎲 <b>¡Nueva ronda!</b>\n\n"
                f"🎤 {preguntador['mencion']} le pone una verdad o reto "
                f"a {respondedor['mencion']}\n\n"
                f"{preguntador['mencion']}, ¿qué le ponés?",
                parse_mode="HTML",
                reply_markup=self._kb_eleccion(preguntador["uid"]),
                message_thread_id=tid,
            )
        except Exception as e:
            logger.error("[VoR] Error enviando mensaje de sorteo: %s", e)
            return

        self._turno = {
            "preguntador":     preguntador,
            "respondedor":     respondedor,
            "chat_id":         cid,
            "tid":             tid,
            "msg_id":          msg.message_id,
            "esperando_texto": False,
        }
        logger.info(
            "[VoR] Ronda iniciada — pregunta: %s (%s) → responde: %s (%s)",
            preguntador["nombre"], preguntador["uid"],
            respondedor["nombre"], respondedor["uid"],
        )

    # ── /expulsar ─────────────────────────────────────────────────────────────

    def cmd_expulsar(self, message: telebot.types.Message) -> None:
        """
        /expulsar — (solo admins) Quita a un jugador de la lista.

        Formas de uso:
          • Responder al mensaje del usuario: /expulsar
          • Por @username:                    /expulsar @username
          • Por nombre de display:            /expulsar Nombre

        Si el expulsado forma parte del turno activo, el turno se cancela.
        """
        if not self._verificar_canal_eventos(message):
            return

        cid = message.chat.id
        tid = get_thread_id(message)

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        if not self._es_admin(message):
            self._temp(cid, "❌ Solo los administradores pueden expulsar jugadores.", tid)
            return

        # ── Determinar el UID objetivo ────────────────────────────────────────
        uid_objetivo: Optional[int] = None
        nombre_objetivo: str        = ""

        # Caso 1: respuesta a un mensaje
        if message.reply_to_message and message.reply_to_message.from_user:
            uid_objetivo     = message.reply_to_message.from_user.id
            nombre_objetivo  = (
                message.reply_to_message.from_user.first_name or str(uid_objetivo)
            )

        # Caso 2: argumento de texto (@username o nombre)
        else:
            partes = (message.text or "").split(maxsplit=1)
            if len(partes) < 2 or not partes[1].strip():
                self._temp(
                    cid,
                    "⚠️ Uso: <code>/expulsar @username</code> o respondé al mensaje "
                    "del jugador con <code>/expulsar</code>.",
                    tid,
                )
                return

            termino = partes[1].strip().lstrip("@").lower()

            # Buscar en la lista por username o nombre
            for p in self._lista:
                nombre_lower = p["nombre"].lower()
                # Intentar también contra el username si lo tenemos guardado
                username_lower = p.get("username", "").lower()
                if termino in (nombre_lower, username_lower):
                    uid_objetivo    = p["uid"]
                    nombre_objetivo = p["nombre"]
                    break

            if uid_objetivo is None:
                self._temp(
                    cid,
                    f"❌ No encontré a <b>{partes[1].strip()}</b> en la lista de jugadores.\n"
                    "Verificá el nombre o respondé a su mensaje con <code>/expulsar</code>.",
                    tid,
                )
                return

        # ── Verificar que está en la lista ────────────────────────────────────
        if not any(p["uid"] == uid_objetivo for p in self._lista):
            self._temp(
                cid,
                f"⚠️ Ese usuario no está en la lista del juego.",
                tid,
            )
            return

        # ── Si el expulsado es parte del turno activo, cancelar el turno ─────
        turno_cancelado = False
        if self._turno is not None:
            uids_en_turno = {
                self._turno["preguntador"]["uid"],
                self._turno["respondedor"]["uid"],
            }
            if uid_objetivo in uids_en_turno:
                self._cancelar_turno_activo()
                turno_cancelado = True

        # ── Quitar de la lista ────────────────────────────────────────────────
        self._lista = [p for p in self._lista if p["uid"] != uid_objetivo]
        logger.info("[VoR] Expulsado uid %s (%s). Quedan %s.", uid_objetivo, nombre_objetivo, len(self._lista))

        extra = "\n⏭️ El turno activo fue cancelado." if turno_cancelado else ""
        self._temp(
            cid,
            f"🚪 <b>{nombre_objetivo}</b> fue expulsado/a del juego.{extra}\n"
            f"👥 Participantes restantes: <b>{len(self._lista)}</b>",
            tid,
            delay=10.0,
        )

    # ── /terminarjuego ────────────────────────────────────────────────────────

    def cmd_terminar_juego(self, message: telebot.types.Message) -> None:
        """
        /terminarjuego — (solo admins) Finaliza el juego, cancela el turno
        activo y vacía la lista de participantes.
        """
        if not self._verificar_canal_eventos(message):
            return

        cid = message.chat.id
        tid = get_thread_id(message)

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        if not self._es_admin(message):
            self._temp(cid, "❌ Solo los administradores pueden terminar el juego.", tid)
            return

        if not self._lista and self._turno is None:
            self._temp(cid, "ℹ️ No hay ningún juego activo en este momento.", tid)
            return

        jugadores = len(self._lista)

        # Cancelar turno activo si existe
        self._cancelar_turno_activo()

        # Vaciar todo
        self._lista  = []
        self._turno  = None

        logger.info("[VoR] Juego terminado por admin. Había %s jugadores.", jugadores)

        try:
            self.bot.send_message(
                cid,
                "🏁 <b>¡Juego terminado!</b>\n\n"
                f"Se cerró la partida con <b>{jugadores}</b> participante(s).\n"
                "Usá <code>/participar</code> para arrancar uno nuevo cuando quieran.",
                parse_mode="HTML",
                message_thread_id=tid,
            )
        except Exception as e:
            logger.error("[VoR] Error anunciando fin de juego: %s", e)

    # ── /participando ─────────────────────────────────────────────────────────

    def cmd_participando(self, message: telebot.types.Message) -> None:
        """Muestra quiénes están en la lista y el estado del turno activo."""
        if not self._verificar_canal_eventos(message):
            return

        cid = message.chat.id
        tid = get_thread_id(message)

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        if not self._lista:
            self._temp(
                cid,
                "📋 No hay ningún juego activo.\n"
                "Usá <code>/participar</code> para iniciar uno.",
                tid,
            )
            return

        uid_preg = self._turno["preguntador"]["uid"] if self._turno else None
        uid_resp = self._turno["respondedor"]["uid"] if self._turno else None

        lineas = []
        for i, p in enumerate(self._lista, 1):
            if p["uid"] == uid_preg:
                marca = " 🎤"
            elif p["uid"] == uid_resp:
                marca = " ⏳"
            else:
                marca = ""
            lineas.append(f"  {i}. {p['mencion']}{marca}")

        estado = ""
        if self._turno:
            if self._turno.get("esperando_texto"):
                estado = "\n\n✏️ Esperando que el preguntador escriba su consigna..."
            else:
                estado = "\n\n🎤 Turno activo — esperando elección del preguntador."

        texto = (
            f"🎲 <b>Verdad o Reto — Participantes</b>\n\n"
            f"👥 Total: <b>{len(self._lista)}</b>\n\n"
            + "\n".join(lineas)
            + estado
        )
        try:
            m = self.bot.send_message(
                cid, texto,
                parse_mode="HTML",
                message_thread_id=tid,
            )
            threading.Timer(
                20.0,
                lambda: self._borrar_seguro(cid, m.message_id),
            ).start()
        except Exception as e:
            logger.error("[EVENTOS] Error en /participando: %s", e)

    # ── /salir ────────────────────────────────────────────────────────────────

    def cmd_salir_evento(self, message: telebot.types.Message) -> None:
        """
        /salir en EVENTOS — Te quita de la lista de Verdad o Reto.
        Si el thread no es EVENTOS, ignora silenciosamente.
        """
        if message.chat.id != CANAL_ID or get_thread_id(message) != EVENTOS:
            return  # Silencioso: puede ser /salir de ROLES

        cid = message.chat.id
        tid = get_thread_id(message)
        uid = message.from_user.id

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        if not any(p["uid"] == uid for p in self._lista):
            self._temp(cid, "⚠️ No estás en la lista del juego.", tid)
            return

        nombre = next(p["nombre"] for p in self._lista if p["uid"] == uid)

        # Si el que sale forma parte del turno activo, cancelar el turno
        if self._turno is not None:
            uids_en_turno = {
                self._turno["preguntador"]["uid"],
                self._turno["respondedor"]["uid"],
            }
            if uid in uids_en_turno:
                self._cancelar_turno_activo()
                self._temp(
                    cid,
                    f"👋 {nombre} salió del juego.\n"
                    "⏭️ El turno activo fue cancelado porque era parte de él.",
                    tid,
                    delay=10.0,
                )
                self._lista = [p for p in self._lista if p["uid"] != uid]
                return

        self._lista = [p for p in self._lista if p["uid"] != uid]
        logger.info("[VoR] %s (%s) salió. Quedan %s.", nombre, uid, len(self._lista))

        self._temp(
            cid,
            f"👋 {nombre} salió del juego.\n"
            f"👥 Participantes: <b>{len(self._lista)}</b>",
            tid,
            delay=8.0,
        )

    # ── Callback: elección del preguntador ───────────────────────────────────

    def callback_vor(self, call: types.CallbackQuery) -> None:
        """
        Gestiona vor:auto_verdad, vor:auto_reto y vor:escribir.
        Solo el preguntador sorteado puede presionar los botones.
        """
        partes = call.data.split(":")
        if len(partes) != 3:
            self.bot.answer_callback_query(call.id)
            return

        _, accion, uid_str = partes
        uid_preguntador    = int(uid_str)
        uid_caller         = call.from_user.id
        cid                = call.message.chat.id
        tid                = getattr(call.message, "message_thread_id", None)

        if uid_caller != uid_preguntador:
            self.bot.answer_callback_query(
                call.id,
                "⛔ No sos el preguntador de esta ronda.",
                show_alert=True,
            )
            return

        if self._turno is None or self._turno["preguntador"]["uid"] != uid_preguntador:
            self.bot.answer_callback_query(
                call.id, "⚠️ Este turno ya no está activo.", show_alert=True,
            )
            return

        self.bot.answer_callback_query(call.id)

        t = self._turno

        if accion == "auto_verdad":
            contenido = random.choice(_VERDADES)
            self._publicar_resultado(
                cid, tid, call.message.message_id,
                "verdad", contenido,
                t["preguntador"]["mencion"], t["respondedor"]["mencion"],
            )
            logger.info("[VoR] Verdad automática publicada.")
            self._turno = None

        elif accion == "auto_reto":
            contenido = random.choice(_RETOS)
            self._publicar_resultado(
                cid, tid, call.message.message_id,
                "reto", contenido,
                t["preguntador"]["mencion"], t["respondedor"]["mencion"],
            )
            logger.info("[VoR] Reto automático publicado.")
            self._turno = None

        elif accion == "escribir":
            # Marcar que esperamos texto y editar el mensaje quitando botones.
            # A partir de acá, _es_texto_del_preguntador devolverá True para
            # el próximo mensaje de texto del preguntador en este chat/thread.
            self._turno["esperando_texto"] = True
            try:
                self.bot.edit_message_text(
                    f"🎲 <b>Nueva ronda</b>\n\n"
                    f"🎤 {t['preguntador']['mencion']} le pone una verdad o reto "
                    f"a {t['respondedor']['mencion']}\n\n"
                    f"✏️ {t['preguntador']['mencion']}, escribí tu verdad o reto "
                    f"en el canal ahora:",
                    chat_id=cid,
                    message_id=call.message.message_id,
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except Exception as e:
                logger.warning("[VoR] No se pudo editar el mensaje al esperando_texto: %s", e)

    # ── Captura del texto personalizado ──────────────────────────────────────

    def capturar_texto_personalizado(self, message: telebot.types.Message) -> None:
        """
        Captura el siguiente mensaje del preguntador cuando eligió
        "Escribir la mía" y lo publica formateado para todos.

        Este handler es registrado PRIMERO en _register_handlers para tener
        prioridad sobre cualquier catch-all de texto de otros módulos.
        El filtro _es_texto_del_preguntador garantiza que solo activa cuando
        corresponde exactamente.
        """
        # Doble-check defensivo por si el estado cambió entre el filtro y acá
        if self._turno is None or not self._turno.get("esperando_texto"):
            return

        t         = self._turno
        cid       = message.chat.id
        tid       = get_thread_id(message)
        contenido = (message.text or "").strip()

        if not contenido:
            return

        # Borrar el mensaje del preguntador para no duplicar en el canal
        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        # Si termina en "?" se clasifica como verdad, si no como reto
        tipo = "verdad" if contenido.endswith("?") else "reto"

        self._publicar_resultado(
            cid, tid, t["msg_id"],
            tipo, contenido,
            t["preguntador"]["mencion"], t["respondedor"]["mencion"],
        )
        logger.info(
            "[VoR] Texto personalizado publicado por uid %s: %r",
            t["preguntador"]["uid"], contenido[:60],
        )
        # Liberar el turno
        self._turno = None
