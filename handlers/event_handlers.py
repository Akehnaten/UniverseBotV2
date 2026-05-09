# -*- coding: utf-8 -*-
"""
handlers/event_handlers.py
Sistema de Verdad o Reto para UniverseBot V2.0

Comandos (thread EVENTOS):
  /participar      - Te une a la lista del juego.
  /verdadoreto     - (solo admins) Sortea 2 jugadores usando el sistema de
                     dos colas para evitar repetidos.
  /participando    - Muestra quien esta en cada cola.
  /salir           - Te quita del juego.
  /expulsar        - (solo admins) Expulsa a un jugador de la lista.
  /terminarjuego   - (solo admins) Termina el juego y resetea todo.

Sistema de dos colas (sin repetidos):
  _sin_participar  - Jugadores que aun no fueron sorteados en este ciclo.
  _participaron    - Jugadores que ya fueron sorteados en este ciclo.

  Sorteo normal   -> se eligen 2 de _sin_participar y pasan a _participaron.
  Ultimo restante -> si queda 1 en _sin_participar, se toma 1 al azar de
                     _participaron como pareja. Esos 2 quedan solos en
                     _participaron y todos los demas vuelven a _sin_participar.
  Ciclo completo  -> si _sin_participar queda vacia entre rondas (por
                     expulsiones), se reinicia el ciclo con _participaron.
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


# ---------------------------------------------------------------------------
# Banco de preguntas y retos
# ---------------------------------------------------------------------------

_VERDADES: list[str] = [
    "Cual es la cosa mas vergonzosa que te ha pasado?",
    "A quien del grupo le mandarias un mensaje a las 3am?",
    "Cual es tu crush secreto dentro del servidor?",
    "Que es lo peor que has hecho y nunca confesaste?",
    "Con quien del grupo no te llevarias bien en la vida real?",
    "Cual fue la mentira mas grande que dijiste este mes?",
    "Que cancion escuchas en secreto pero jamas admitiras?",
    "A quien del servidor bloquearias si pudieras sin consecuencias?",
    "Cual es el pensamiento mas raro que tuviste hoy?",
    "Que es lo primero que notas cuando conoces a alguien?",
    "Alguna vez le hablaste mal de alguien del servidor a otra persona?",
    "Cual es tu mayor inseguridad?",
    "Que harias si tuvieras un dia invisible?",
    "Cual fue tu peor cita o situacion romantica?",
    "A quien del servidor le pediras consejos de amor?",
    "Que aplicacion usas mas y no admitiras publicamente?",
    "Cuantas veces al dia revisas el celular sin motivo?",
    "Que es lo mas atrevido que hiciste por llamar la atencion?",
    "Alguna vez mandaste un mensaje al destinatario equivocado?",
    "Cual es el peor regalo que recibiste y fingiste que te gusto?",
]

_RETOS: list[str] = [
    "Manda un audio cantando los primeros 10 segundos de una cancion.",
    "Escribi 'Te amo' al ultimo contacto de tu lista de chats.",
    "Envia el ultimo meme que guardaste en tu galeria.",
    "Haz una imitacion de texto del admin mas estricto del servidor.",
    "Describe a la persona de tu derecha usando solo emojis (3 max.).",
    "Escribi un mensaje de amor a un personaje ficticio de tu eleccion.",
    "Conta un chiste en menos de 2 lineas. Si nadie se rie, conta otro.",
    "Envia una selfie con la cara mas ridicula que puedas hacer.",
    "Cambia tu nombre en el servidor por 'Patito de Goma' durante 5 minutos.",
    "Escribi un poema de 4 versos sobre el servidor.",
    "Manda el ultimo sticker que usaste con una frase explicando cuando lo usarias.",
    "Copia exactamente el ultimo mensaje que mandaste en otro chat y envialo aqui.",
    "Haz una prediccion del proximo evento del servidor.",
    "Describe tu dia de hoy usando solo palabras de 4 letras.",
    "Envia una recomendacion de algo (cancion, serie, lugar) en menos de 20 palabras.",
    "Escribi el nombre de 5 miembros del servidor al reves.",
    "Manda un mensaje de voz diciendo el abecedario en 10 segundos.",
    "Escribi un trabalenguas inventado sobre algun miembro del servidor.",
    "Adivina de quien es este mensaje (el admin elige uno antiguo del canal).",
    "Envia una foto de lo que tenes en la mesa ahora mismo.",
]


# ---------------------------------------------------------------------------
# Clase principal
# ---------------------------------------------------------------------------

class EventHandlers:
    """
    Handlers para el sistema de Verdad o Reto.

    Estado de listas:
        _lista          - Todos los jugadores registrados. Fuente de verdad.
        _sin_participar - Jugadores que aun no salieron sorteados en el ciclo.
        _participaron   - Jugadores ya sorteados en el ciclo actual.

        Invariante: _sin_participar U _participaron == _lista (por uid)

    Estado del turno activo (_turno):
        preguntador    : dict
        respondedor    : dict
        chat_id        : int
        tid            : int | None
        msg_id         : int
        esperando_texto: bool
    """

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        self._lista:          list[dict]     = []
        self._sin_participar: list[dict]     = []
        self._participaron:   list[dict]     = []
        self._turno:          Optional[dict] = None
        self._register_handlers()

    # -----------------------------------------------------------------------
    # Registro de handlers
    # -----------------------------------------------------------------------

    def _register_handlers(self) -> None:
        # El handler de texto personalizado va PRIMERO para ganar la carrera
        # contra cualquier catch-all de texto de otros modulos.
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

    # -----------------------------------------------------------------------
    # Helpers de cola
    # -----------------------------------------------------------------------

    def _agregar_jugador(self, jugador: dict) -> None:
        """Agrega un jugador a _lista y a _sin_participar (aun no jugo)."""
        self._lista.append(jugador)
        self._sin_participar.append(jugador)

    def _quitar_jugador(self, uid: int) -> None:
        """Quita un jugador de todas las listas y re-sincroniza las colas."""
        self._lista          = [p for p in self._lista          if p["uid"] != uid]
        self._sin_participar = [p for p in self._sin_participar if p["uid"] != uid]
        self._participaron   = [p for p in self._participaron   if p["uid"] != uid]
        self._sincronizar_colas()

    def _sincronizar_colas(self) -> None:
        """
        Si _sin_participar quedo vacia pero aun hay jugadores en _participaron,
        reinicia el ciclo: todos vuelven a _sin_participar.
        Llamar siempre despues de modificar las listas.
        """
        if not self._sin_participar and self._participaron:
            logger.info(
                "[VoR] _sin_participar vacia - reiniciando ciclo con %s jugadores.",
                len(self._participaron),
            )
            self._sin_participar = list(self._participaron)
            self._participaron   = []

    def _sortear_dos(self) -> tuple:
        """
        Aplica la logica de las dos colas y devuelve (preguntador, respondedor).

        Caso A - Quedan >= 2 en _sin_participar:
            Elige 2 al azar y los pasa a _participaron.

        Caso B - Queda exactamente 1 en _sin_participar:
            Toma al unico restante y elige 1 al azar de _participaron como pareja.
            Esos 2 quedan solos en _participaron.
            Todos los demas de _participaron vuelven a _sin_participar.
            => Comienza un nuevo ciclo.
        """
        if len(self._sin_participar) >= 2:
            # Caso A: sorteo normal
            elegidos = random.sample(self._sin_participar, 2)
            for p in elegidos:
                self._sin_participar.remove(p)
                self._participaron.append(p)
            logger.info(
                "[VoR] Sorteo normal - sin_participar: %s | participaron: %s",
                len(self._sin_participar), len(self._participaron),
            )
        else:
            # Caso B: ultimo restante, reinicio de ciclo
            ultimo    = self._sin_participar[0]
            companero = random.choice(self._participaron)

            # Todos excepto el companero elegido vuelven a la cola de espera
            self._sin_participar = [
                p for p in self._participaron if p["uid"] != companero["uid"]
            ]
            # Los 2 elegidos quedan solos en _participaron
            self._participaron = [ultimo, companero]
            elegidos = [ultimo, companero]

            logger.info(
                "[VoR] Ciclo reiniciado - ultimo: %s + companero: %s | "
                "sin_participar: %s | participaron: 2",
                ultimo["nombre"], companero["nombre"], len(self._sin_participar),
            )

        random.shuffle(elegidos)  # quien pregunta y quien responde es aleatorio
        return elegidos[0], elegidos[1]

    # -----------------------------------------------------------------------
    # Helpers generales
    # -----------------------------------------------------------------------

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
        if message.chat.id != CANAL_ID or get_thread_id(message) != EVENTOS:
            try:
                self.bot.delete_message(message.chat.id, message.message_id)
            except Exception:
                pass
            return False
        return True

    def _es_admin(self, message: telebot.types.Message) -> bool:
        try:
            member = self.bot.get_chat_member(message.chat.id, message.from_user.id)
            return member.status in ("administrator", "creator")
        except Exception:
            return False

    def _nombre_display(self, message: telebot.types.Message, user_info: dict) -> str:
        uid    = message.from_user.id
        nombre = user_info.get("nombre") or message.from_user.first_name or "Jugador"
        return f'<a href="tg://user?id={uid}">{nombre}</a>'

    def _kb_eleccion(self, uid_preguntador: int) -> types.InlineKeyboardMarkup:
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton(
                "Verdad automatica",
                callback_data=f"vor:auto_verdad:{uid_preguntador}",
            ),
            types.InlineKeyboardButton(
                "Reto automatico",
                callback_data=f"vor:auto_reto:{uid_preguntador}",
            ),
        )
        kb.add(
            types.InlineKeyboardButton(
                "Escribir la mia",
                callback_data=f"vor:escribir:{uid_preguntador}",
            )
        )
        return kb

    def _cancelar_turno_activo(self) -> None:
        """Cancela el turno en memoria y edita el mensaje para avisar."""
        if self._turno is None:
            return
        t = self._turno
        self._turno = None
        try:
            self.bot.edit_message_text(
                "<i>Turno cancelado por el administrador.</i>",
                chat_id=t["chat_id"],
                message_id=t["msg_id"],
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
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
        encabezado = "<b>VERDAD</b>" if tipo == "verdad" else "<b>RETO</b>"
        emoji      = "" if tipo == "verdad" else ""
        texto = (
            f"{encabezado}\n\n"
            f"Le toca a: {mencion_respondedor}\n"
            f"Puesto por: {mencion_preguntador}\n\n"
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
        Filtro de maxima especificidad para capturar el texto personalizado.
        Registrado primero en _register_handlers para ganar la carrera
        contra catch-alls de texto de otros modulos.
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

    # -----------------------------------------------------------------------
    # /participar
    # -----------------------------------------------------------------------

    def cmd_participar(self, message: telebot.types.Message) -> None:
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
                "Ya estas en la lista del juego.\nUsa /salir para abandonar.",
                tid,
            )
            return

        nombre    = user_info.get("nombre") or message.from_user.first_name
        mencion   = self._nombre_display(message, user_info)
        jugador   = {"uid": uid, "nombre": nombre, "mencion": mencion}
        es_primero = len(self._lista) == 0

        self._agregar_jugador(jugador)
        logger.info(
            "[VoR] %s (%s) se unio. Total: %s | sin_p: %s | part: %s",
            nombre, uid,
            len(self._lista), len(self._sin_participar), len(self._participaron),
        )

        if es_primero:
            self.bot.send_message(
                cid,
                "<b>Nuevo juego de Verdad o Reto!</b>\n\n"
                f"{mencion} ha iniciado la partida.\n\n"
                "Queres participar? Usa <code>/participar</code>\n"
                "Cuando haya al menos 2 jugadores, un admin lanza "
                "<code>/verdadoreto</code>.",
                parse_mode="HTML",
                message_thread_id=tid,
            )
        else:
            self._temp(
                cid,
                f"{mencion} se unio al juego.\n"
                f"Participantes: <b>{len(self._lista)}</b>",
                tid,
                delay=10.0,
            )

    # -----------------------------------------------------------------------
    # /verdadoreto
    # -----------------------------------------------------------------------

    def cmd_verdadoreto(self, message: telebot.types.Message) -> None:
        """
        Sortea 2 jugadores usando el sistema de dos colas.
        Si hay turno activo, lo cancela y arranca uno nuevo (salteo de AFK).
        Solo admins.
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
            self._temp(cid, "Solo los administradores pueden iniciar el sorteo.", tid)
            return

        if len(self._lista) < 2:
            self._temp(
                cid,
                "Se necesitan al menos <b>2 participantes</b> para jugar.\n"
                "Pedile a la gente que use <code>/participar</code>.",
                tid,
            )
            return

        # Cancelar turno activo si existe (permite saltear AFK)
        if self._turno is not None:
            logger.info(
                "[VoR] Admin salto el turno de %s.",
                self._turno["preguntador"]["nombre"],
            )
            self._cancelar_turno_activo()

        # Garantizar que las colas esten en estado consistente
        self._sincronizar_colas()

        # Sortear usando la logica de dos colas
        preguntador, respondedor = self._sortear_dos()

        # Texto informativo del estado de las colas
        sin_p = len(self._sin_participar)
        if sin_p == 0:
            estado_cola = "<i>Todos participaron! Nuevo ciclo iniciado.</i>"
        else:
            estado_cola = f"<i>Quedan {sin_p} jugador(es) sin participar en este ciclo.</i>"

        try:
            msg = self.bot.send_message(
                cid,
                f"<b>Nueva ronda!</b>\n\n"
                f"{preguntador['mencion']} le pone una verdad o reto "
                f"a {respondedor['mencion']}\n\n"
                f"{preguntador['mencion']}, que le pones?\n\n"
                f"{estado_cola}",
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
            "[VoR] Ronda - pregunta: %s (%s) -> responde: %s (%s)",
            preguntador["nombre"], preguntador["uid"],
            respondedor["nombre"], respondedor["uid"],
        )

    # -----------------------------------------------------------------------
    # /expulsar
    # -----------------------------------------------------------------------

    def cmd_expulsar(self, message: telebot.types.Message) -> None:
        """
        /expulsar - (solo admins) Quita a un jugador de todas las listas.
        Uso: responder al mensaje del jugador, o /expulsar @username / Nombre.
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
            self._temp(cid, "Solo los administradores pueden expulsar jugadores.", tid)
            return

        uid_objetivo:    Optional[int] = None
        nombre_objetivo: str           = ""

        if message.reply_to_message and message.reply_to_message.from_user:
            uid_objetivo    = message.reply_to_message.from_user.id
            nombre_objetivo = (
                message.reply_to_message.from_user.first_name or str(uid_objetivo)
            )
        else:
            partes = (message.text or "").split(maxsplit=1)
            if len(partes) < 2 or not partes[1].strip():
                self._temp(
                    cid,
                    "Uso: <code>/expulsar @username</code> o responde al mensaje "
                    "del jugador con <code>/expulsar</code>.",
                    tid,
                )
                return

            termino = partes[1].strip().lstrip("@").lower()
            for p in self._lista:
                if termino in (p["nombre"].lower(), p.get("username", "").lower()):
                    uid_objetivo    = p["uid"]
                    nombre_objetivo = p["nombre"]
                    break

            if uid_objetivo is None:
                self._temp(
                    cid,
                    f"No encontre a <b>{partes[1].strip()}</b> en la lista.\n"
                    "Verifica el nombre o responde a su mensaje con <code>/expulsar</code>.",
                    tid,
                )
                return

        if not any(p["uid"] == uid_objetivo for p in self._lista):
            self._temp(cid, "Ese usuario no esta en la lista del juego.", tid)
            return

        turno_cancelado = False
        if self._turno is not None:
            uids_en_turno = {
                self._turno["preguntador"]["uid"],
                self._turno["respondedor"]["uid"],
            }
            if uid_objetivo in uids_en_turno:
                self._cancelar_turno_activo()
                turno_cancelado = True

        self._quitar_jugador(uid_objetivo)
        logger.info(
            "[VoR] Expulsado uid %s (%s). Total: %s | sin_p: %s | part: %s",
            uid_objetivo, nombre_objetivo,
            len(self._lista), len(self._sin_participar), len(self._participaron),
        )

        extra = "\nEl turno activo fue cancelado." if turno_cancelado else ""
        self._temp(
            cid,
            f"<b>{nombre_objetivo}</b> fue expulsado/a del juego.{extra}\n"
            f"Participantes restantes: <b>{len(self._lista)}</b>",
            tid,
            delay=10.0,
        )

    # -----------------------------------------------------------------------
    # /terminarjuego
    # -----------------------------------------------------------------------

    def cmd_terminar_juego(self, message: telebot.types.Message) -> None:
        """
        /terminarjuego - (solo admins) Finaliza el juego y resetea todo.
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
            self._temp(cid, "Solo los administradores pueden terminar el juego.", tid)
            return

        if not self._lista and self._turno is None:
            self._temp(cid, "No hay ningun juego activo en este momento.", tid)
            return

        jugadores = len(self._lista)
        self._cancelar_turno_activo()
        self._lista          = []
        self._sin_participar = []
        self._participaron   = []
        self._turno          = None

        logger.info("[VoR] Juego terminado por admin. Habia %s jugadores.", jugadores)

        try:
            self.bot.send_message(
                cid,
                "<b>Juego terminado!</b>\n\n"
                f"Se cerro la partida con <b>{jugadores}</b> participante(s).\n"
                "Usa <code>/participar</code> para arrancar uno nuevo cuando quieran.",
                parse_mode="HTML",
                message_thread_id=tid,
            )
        except Exception as e:
            logger.error("[VoR] Error anunciando fin de juego: %s", e)

    # -----------------------------------------------------------------------
    # /participando
    # -----------------------------------------------------------------------

    def cmd_participando(self, message: telebot.types.Message) -> None:
        """Muestra las dos colas y el estado del turno activo."""
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
                "No hay ningun juego activo.\n"
                "Usa <code>/participar</code> para iniciar uno.",
                tid,
            )
            return

        uid_preg = self._turno["preguntador"]["uid"] if self._turno else None
        uid_resp = self._turno["respondedor"]["uid"] if self._turno else None

        def _formatear_fila(jugadores: list) -> str:
            if not jugadores:
                return "  <i>(vacia)</i>"
            lineas = []
            for p in jugadores:
                if p["uid"] == uid_preg:
                    marca = " (preguntando)"
                elif p["uid"] == uid_resp:
                    marca = " (respondiendo)"
                else:
                    marca = ""
                lineas.append(f"  - {p['mencion']}{marca}")
            return "\n".join(lineas)

        estado_turno = ""
        if self._turno:
            if self._turno.get("esperando_texto"):
                estado_turno = "\n<i>Esperando que el preguntador escriba su consigna...</i>"
            else:
                estado_turno = "\n<i>Turno activo - esperando eleccion del preguntador.</i>"

        texto = (
            f"<b>Verdad o Reto - Estado del juego</b>\n"
            f"Total: <b>{len(self._lista)}</b>"
            f"{estado_turno}\n\n"
            f"<b>Sin participar aun ({len(self._sin_participar)}):</b>\n"
            f"{_formatear_fila(self._sin_participar)}\n\n"
            f"<b>Ya participaron ({len(self._participaron)}):</b>\n"
            f"{_formatear_fila(self._participaron)}"
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

    # -----------------------------------------------------------------------
    # /salir
    # -----------------------------------------------------------------------

    def cmd_salir_evento(self, message: telebot.types.Message) -> None:
        """
        /salir en EVENTOS - Te quita de todas las listas del juego.
        Si el thread no es EVENTOS, ignora silenciosamente (puede ser /salir de ROLES).
        """
        if message.chat.id != CANAL_ID or get_thread_id(message) != EVENTOS:
            return

        cid = message.chat.id
        tid = get_thread_id(message)
        uid = message.from_user.id

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        if not any(p["uid"] == uid for p in self._lista):
            self._temp(cid, "No estas en la lista del juego.", tid)
            return

        nombre = next(p["nombre"] for p in self._lista if p["uid"] == uid)

        turno_cancelado = False
        if self._turno is not None:
            uids_en_turno = {
                self._turno["preguntador"]["uid"],
                self._turno["respondedor"]["uid"],
            }
            if uid in uids_en_turno:
                self._cancelar_turno_activo()
                turno_cancelado = True

        self._quitar_jugador(uid)
        logger.info(
            "[VoR] %s (%s) salio. Total: %s | sin_p: %s | part: %s",
            nombre, uid,
            len(self._lista), len(self._sin_participar), len(self._participaron),
        )

        extra = (
            "\nEl turno activo fue cancelado porque eras parte de el."
            if turno_cancelado else ""
        )
        self._temp(
            cid,
            f"{nombre} salio del juego.{extra}\n"
            f"Participantes: <b>{len(self._lista)}</b>",
            tid,
            delay=8.0,
        )

    # -----------------------------------------------------------------------
    # Callback: eleccion del preguntador
    # -----------------------------------------------------------------------

    def callback_vor(self, call: types.CallbackQuery) -> None:
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
                "No sos el preguntador de esta ronda.",
                show_alert=True,
            )
            return

        if self._turno is None or self._turno["preguntador"]["uid"] != uid_preguntador:
            self.bot.answer_callback_query(
                call.id, "Este turno ya no esta activo.", show_alert=True,
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
            logger.info("[VoR] Verdad automatica publicada.")
            self._turno = None

        elif accion == "auto_reto":
            contenido = random.choice(_RETOS)
            self._publicar_resultado(
                cid, tid, call.message.message_id,
                "reto", contenido,
                t["preguntador"]["mencion"], t["respondedor"]["mencion"],
            )
            logger.info("[VoR] Reto automatico publicado.")
            self._turno = None

        elif accion == "escribir":
            self._turno["esperando_texto"] = True
            try:
                self.bot.edit_message_text(
                    f"<b>Nueva ronda</b>\n\n"
                    f"{t['preguntador']['mencion']} le pone una verdad o reto "
                    f"a {t['respondedor']['mencion']}\n\n"
                    f"{t['preguntador']['mencion']}, escribi tu verdad o reto "
                    f"en el canal ahora:",
                    chat_id=cid,
                    message_id=call.message.message_id,
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except Exception as e:
                logger.warning("[VoR] No se pudo editar el mensaje: %s", e)

    # -----------------------------------------------------------------------
    # Captura del texto personalizado
    # -----------------------------------------------------------------------

    def capturar_texto_personalizado(self, message: telebot.types.Message) -> None:
        """
        Captura el texto del preguntador cuando eligio "Escribir la mia".
        Registrado primero en _register_handlers para tener prioridad
        sobre cualquier catch-all de texto de otros modulos.
        """
        if self._turno is None or not self._turno.get("esperando_texto"):
            return

        t         = self._turno
        cid       = message.chat.id
        tid       = get_thread_id(message)
        contenido = (message.text or "").strip()

        if not contenido:
            return

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        tipo = "verdad" if contenido.endswith("?") else "reto"

        self._publicar_resultado(
            cid, tid, t["msg_id"],
            tipo, contenido,
            t["preguntador"]["mencion"], t["respondedor"]["mencion"],
        )
        logger.info(
            "[VoR] Texto personalizado de uid %s: %r",
            t["preguntador"]["uid"], contenido[:60],
        )
        self._turno = None
