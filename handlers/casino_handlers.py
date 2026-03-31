# -*- coding: utf-8 -*-
"""
handlers/casino_handlers.py
════════════════════════════════════════════════════════════════════════════════
Handlers de Casino para UniverseBot V2.0

Comandos registrados:
  /slots   [apuesta | allin]  — Tragaperras K-pop con 5 líneas de pago
  /slotsinfo                  — Tabla de premios y explicación del sistema
  /sorteo  [max]              — Número aleatorio para sorteos
  /newbingo [max]             — Inicia un bingo (solo admins)
  /bingo                      — Saca el siguiente número del bingo
  /finbingo                   — Finaliza el bingo actual

Integración con slots_service:
  - girar()                   → motor de slots puro (sin Telegram)
  - render_mensaje_resultado() → texto HTML del resultado
  - render_mensaje_animacion() → texto HTML de animación
  - render_tabla_premios()    → tabla de /slotsinfo
════════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
import random
import threading
import time

import telebot

from config import CASINO, MSG_USUARIO_NO_REGISTRADO
from database import db_manager
from funciones import economy_service, user_service
from funciones.slots_service import (
    girar,
    render_mensaje_animacion,
    render_mensaje_resultado,
    render_tabla_premios,
)

logger = logging.getLogger(__name__)

# ─── Constantes internas ──────────────────────────────────────────────────────

_APUESTA_MINIMA     = 50       # Cosmos mínimos por giro
_APUESTA_MAXIMA     = 50_000   # Cosmos máximos por giro
_DELAY_ANIMACION    = 1.2      # Segundos entre fases de animación
_FASES_ANIMACION    = 3        # Cuántas fases mostrar antes del resultado
_TTL_MSG_ERROR      = 5        # Segundos antes de borrar mensajes de error
_TTL_MSG_INFO       = 20       # Segundos antes de borrar /slotsinfo


# ─── Clase principal ──────────────────────────────────────────────────────────

class CasinoHandlers:
    """
    Handlers de Casino y Juegos.

    Gestiona:
      - /slots  : Tragaperras K-pop con motor en slots_service.py
      - /slotsinfo : Tabla de premios
      - /sorteo : Generador de números para sorteos
      - /newbingo / /bingo / /finbingo : Sistema de bingo
    """

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot            = bot
        self.bingo_numeros: list[int] = []
        self.bingo_total:   int       = 0

        # Cooldown anti-spam: {user_id: timestamp_ultimo_giro}
        self._cooldown: dict[int, float] = {}
        self._cooldown_segundos = 3

        # Seguimiento de giros gratis pendientes: {user_id: cantidad}
        self._giros_gratis: dict[int, int] = {}
        self._lock = threading.Lock()

        self._register_handlers()

    # ─── Registro de handlers ─────────────────────────────────────────────────

    def _register_handlers(self) -> None:
        self.bot.register_message_handler(self.cmd_slots,     commands=["slots"])
        self.bot.register_message_handler(self.cmd_slotsinfo, commands=["slotsinfo"])
        self.bot.register_message_handler(self.cmd_sorteo,    commands=["sorteo"])
        self.bot.register_message_handler(self.cmd_newbingo,  commands=["newbingo"])
        self.bot.register_message_handler(self.cmd_bingo,     commands=["bingo"])
        self.bot.register_message_handler(self.cmd_finbingo,  commands=["finbingo"])

    # ─── Utilidades internas ──────────────────────────────────────────────────

    def _borrar_seguro(self, chat_id: int, message_id: int) -> None:
        """Elimina un mensaje ignorando cualquier error de Telegram."""
        try:
            self.bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    def _borrar_tras_delay(self, chat_id: int, message_id: int, delay: float) -> None:
        """Elimina un mensaje después de `delay` segundos (hilo separado)."""
        threading.Timer(
            delay,
            lambda: self._borrar_seguro(chat_id, message_id),
        ).start()

    def _error_y_borrar(
        self,
        chat_id:   int,
        texto:     str,
        thread_id: int | None = None,
        delay:     float = _TTL_MSG_ERROR,
    ) -> None:
        """Envía un mensaje de error y lo borra automáticamente."""
        m = self.bot.send_message(chat_id, texto, message_thread_id=thread_id)
        self._borrar_tras_delay(chat_id, m.message_id, delay)

    def _verificar_canal_casino(self, message: telebot.types.Message) -> bool:
        """
        Verifica que el mensaje provenga del hilo CASINO.

        Si no, borra el comando del usuario, informa y retorna False.
        """
        if message.message_thread_id == CASINO:
            return True

        self._borrar_seguro(message.chat.id, message.message_id)
        self._error_y_borrar(
            message.chat.id,
            "🎰 Este comando solo puede usarse en el canal de casino.",
            thread_id=message.message_thread_id,
        )
        return False

    def _en_cooldown(self, user_id: int) -> bool:
        """
        Verifica si el usuario está en período de cooldown anti-spam.

        Returns:
            True si debe esperar, False si puede jugar.
        """
        ahora = time.monotonic()
        ultimo = self._cooldown.get(user_id, 0.0)
        return (ahora - ultimo) < self._cooldown_segundos

    def _registrar_giro(self, user_id: int) -> None:
        """Actualiza el timestamp de último giro para el cooldown."""
        self._cooldown[user_id] = time.monotonic()

    def _tiene_giro_gratis(self, user_id: int) -> bool:
        """Retorna True si el usuario tiene al menos un giro gratis pendiente."""
        with self._lock:
            return self._giros_gratis.get(user_id, 0) > 0

    def _consumir_giro_gratis(self, user_id: int) -> None:
        """Decrementa en 1 los giros gratis del usuario."""
        with self._lock:
            if self._giros_gratis.get(user_id, 0) > 0:
                self._giros_gratis[user_id] -= 1

    def _otorgar_giro_gratis(self, user_id: int) -> None:
        """Incrementa en 1 los giros gratis del usuario."""
        with self._lock:
            self._giros_gratis[user_id] = self._giros_gratis.get(user_id, 0) + 1

    # ─── /slots ───────────────────────────────────────────────────────────────

    def cmd_slots(self, message: telebot.types.Message) -> None:
        """
        /slots [apuesta | allin]

        Flujo completo:
          1. Validaciones (canal, registro, cooldown, apuesta, saldo)
          2. Descuento de cosmos (o consumo de giro gratis)
          3. Animación de giro (3 fases editando el mismo mensaje)
          4. Cálculo del resultado via slots_service.girar()
          5. Edición final del mensaje con el resultado completo
          6. Crédito de ganancias + giro gratis si aplica
        """
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        # ── 1a. Solo en el canal casino ───────────────────────────────────
        if not self._verificar_canal_casino(message):
            return

        self._borrar_seguro(cid, message.message_id)

        # ── 1b. Usuario registrado ────────────────────────────────────────
        user_info = user_service.get_user_info(uid)
        if not user_info:
            self._error_y_borrar(cid, MSG_USUARIO_NO_REGISTRADO, thread_id=tid)
            return

        nombre = user_info.get("nombre", "Usuario")

        # ── 1c. Cooldown anti-spam ────────────────────────────────────────
        if self._en_cooldown(uid):
            self._error_y_borrar(
                cid,
                f"⏳ {nombre}, espera un momento antes de volver a girar.",
                thread_id=tid,
            )
            return

        # ── 1d. Parsear apuesta ───────────────────────────────────────────
        parts = (message.text or "").split()
        es_giro_gratis = self._tiene_giro_gratis(uid)

        try:
            if es_giro_gratis:
                # Usamos el saldo actual como "apuesta" para calcular premios,
                # pero sin descontar cosmos. Si el saldo es 0, apuesta mínima.
                apuesta = max(_APUESTA_MINIMA, economy_service.get_balance(uid))
                apuesta = min(apuesta, _APUESTA_MAXIMA)
            elif len(parts) > 1 and parts[1].lower() == "allin":
                apuesta = economy_service.get_balance(uid)
                if apuesta == 0:
                    self._error_y_borrar(
                        cid,
                        f"❌ {nombre}, no tienes Cosmos para apostar.",
                        thread_id=tid,
                    )
                    return
            elif len(parts) > 1:
                apuesta = int(parts[1])
            else:
                # Sin argumento: mostrar ayuda rápida
                self._error_y_borrar(
                    cid,
                    (
                        "🎰 <b>Universe Slots</b>\n\n"
                        "Uso: <code>/slots [cantidad]</code> o <code>/slots allin</code>\n"
                        f"Mínimo: {_APUESTA_MINIMA:,} ✨  |  Máximo: {_APUESTA_MAXIMA:,} ✨\n\n"
                        "📋 Ver premios: /slotsinfo"
                    ),
                    thread_id=tid,
                    delay=8,
                )
                return

        except ValueError:
            self._error_y_borrar(
                cid, "❌ La apuesta debe ser un número válido.", thread_id=tid
            )
            return

        # ── 1e. Rango de apuesta ──────────────────────────────────────────
        if not es_giro_gratis:
            if apuesta < _APUESTA_MINIMA:
                self._error_y_borrar(
                    cid,
                    f"❌ Apuesta mínima: <b>{_APUESTA_MINIMA:,} ✨</b>",
                    thread_id=tid,
                )
                return
            if apuesta > _APUESTA_MAXIMA:
                self._error_y_borrar(
                    cid,
                    f"❌ Apuesta máxima: <b>{_APUESTA_MAXIMA:,} ✨</b>",
                    thread_id=tid,
                )
                return

        # ── 1f. Verificar saldo ───────────────────────────────────────────
        if not es_giro_gratis:
            balance_previo = economy_service.get_balance(uid)
            if balance_previo < apuesta:
                self._error_y_borrar(
                    cid,
                    (
                        f"❌ {nombre}, saldo insuficiente.\n"
                        f"💳 Tienes: <b>{balance_previo:,} ✨</b>\n"
                        f"🎯 Apuesta: <b>{apuesta:,} ✨</b>"
                    ),
                    thread_id=tid,
                )
                return

        # ── 2. Descontar apuesta / consumir giro gratis ───────────────────
        if es_giro_gratis:
            self._consumir_giro_gratis(uid)
            logger.info("🎁 %s (%d) usa giro gratis | apuesta efectiva: %d", nombre, uid, apuesta)
        else:
            ok = economy_service.subtract_credits(uid, apuesta, "slots")
            if not ok:
                self._error_y_borrar(
                    cid, "❌ Error al procesar la apuesta. Intenta de nuevo.", thread_id=tid
                )
                return

        self._registrar_giro(uid)

        # ── 3. Mensaje inicial + animación ────────────────────────────────
        try:
            msg_anim = self.bot.send_message(
                cid,
                render_mensaje_animacion(0, nombre, apuesta),
                parse_mode="HTML",
                message_thread_id=tid,
            )
        except Exception as exc:
            logger.error("Error enviando mensaje de animación: %s", exc)
            # Si falla el mensaje de animación, revertir cosmos y salir
            if not es_giro_gratis:
                economy_service.add_credits(uid, apuesta, "reverso_slots_error")
            return

        # Fases 1 y 2 de animación
        for fase in range(1, _FASES_ANIMACION):
            time.sleep(_DELAY_ANIMACION)
            try:
                self.bot.edit_message_text(
                    render_mensaje_animacion(fase, nombre, apuesta),
                    chat_id    = cid,
                    message_id = msg_anim.message_id,
                    parse_mode = "HTML",
                )
            except Exception:
                pass  # Si falla la edición, continuamos igual

        time.sleep(_DELAY_ANIMACION)

        # ── 4. Calcular resultado ─────────────────────────────────────────
        result = girar(apuesta)

       # ── 6. Acreditar ganancias / devolver apuesta en empate ────────────
        if result.ganancia_neta > 0:
            # Ganancia real: devolver apuesta + ganancia neta (giro normal),
            # o solo la ganancia neta (giro gratis, donde la apuesta no se descontó).
            pago = result.ganancia_neta if es_giro_gratis else result.ganancia_neta + result.apuesta
            economy_service.add_credits(uid, pago, "slots_ganancia")
            logger.info(
                "🎰 GANANCIA | %s (%d) | apuesta: %d | neta: +%d | pago: %d | jackpot: %s",
                nombre, uid, apuesta, result.ganancia_neta, pago, result.jackpot,
            )
 
        elif result.ganancia_neta == 0 and not es_giro_gratis:
            # Empate (ganancia_bruta == apuesta): la apuesta fue descontada en el
            # paso 2 pero el multiplicador total cubrió exactamente el costo.
            # Se devuelve la apuesta íntegra; el usuario no gana ni pierde.
            economy_service.add_credits(uid, result.apuesta, "slots_empate")
            logger.info(
                "🎰 EMPATE   | %s (%d) | apuesta: %d | devuelta íntegra",
                nombre, uid, apuesta,
            )
 
        else:
            logger.info(
                "🎰 PÉRDIDA  | %s (%d) | apuesta: %d | neta: %d",
                nombre, uid, apuesta, result.ganancia_neta,
            )
 
        # ── 5 (MOVIDO). Editar mensaje con resultado final ────────────────
        # IMPORTANTE: get_balance se llama DESPUÉS de acreditar ganancias
        # para que el balance mostrado refleje el estado real del usuario.
        # Antes estaba antes del paso 6, por lo que nunca incluía las ganancias.
        balance_nuevo = economy_service.get_balance(uid)
        texto_resultado = (
            render_mensaje_resultado(result, nombre)
            + f"\n💳 Balance: <b>{balance_nuevo:,} ✨</b>"
        )
 
        if es_giro_gratis:
            texto_resultado = "🎁 <i>Giro Gratis</i>\n" + texto_resultado
 
        try:
            self.bot.edit_message_text(
                texto_resultado,
                chat_id    = cid,
                message_id = msg_anim.message_id,
                parse_mode = "HTML",
            )
        except Exception as exc:
            logger.warning("No se pudo editar el mensaje final: %s", exc)
            self.bot.send_message(cid, texto_resultado, parse_mode="HTML", message_thread_id=tid)
 
        # ── 7. Giro gratis si aplica ──────────────────────────────────────
        if result.giro_gratis and not es_giro_gratis:
            self._otorgar_giro_gratis(uid)
            logger.info("🎁 Giro gratis otorgado a %s (%d)", nombre, uid)

    # ─── /slotsinfo ───────────────────────────────────────────────────────────

    def cmd_slotsinfo(self, message: telebot.types.Message) -> None:
        """
        /slotsinfo — Muestra la tabla de premios y cómo funciona el sistema.
        """
        cid = message.chat.id
        tid = message.message_thread_id

        self._borrar_seguro(cid, message.message_id)

        if not self._verificar_canal_casino(message):
            return

        m = self.bot.send_message(
            cid,
            render_tabla_premios(),
            parse_mode="HTML",
            message_thread_id=tid,
        )
        self._borrar_tras_delay(cid, m.message_id, _TTL_MSG_INFO)

    # ─── /sorteo ──────────────────────────────────────────────────────────────

    def cmd_sorteo(self, message: telebot.types.Message) -> None:
        """
        /sorteo [numero_maximo]

        Genera un número aleatorio entre 1 y numero_maximo para sorteos.
        Solo en el hilo CASINO.
        """
        cid = message.chat.id
        tid = message.message_thread_id

        self._borrar_seguro(cid, message.message_id)

        try:
            parts = (message.text or "").split()

            if len(parts) < 2:
                self._error_y_borrar(
                    cid,
                    "❌ Debes especificar el número máximo.\nEjemplo: /sorteo 100",
                    thread_id=tid,
                )
                return

            numero_max = int(parts[1])

            if numero_max < 2:
                self._error_y_borrar(
                    cid,
                    "❌ El número máximo debe ser al menos 2.",
                    thread_id=tid,
                )
                return

            ganador = random.randint(1, numero_max)
            texto   = (
                f"🎲 <b>¡SORTEO!</b>\n\n"
                f"Número ganador: <b>{ganador}</b>\n"
                f"<i>(de 1 a {numero_max})</i>"
            )

            logger.info("🎲 Sorteo: %d / %d", ganador, numero_max)
            m = self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
            self._borrar_tras_delay(cid, m.message_id, 15.0)

        except ValueError:
            self._error_y_borrar(
                cid, "❌ El número máximo debe ser un número válido.", thread_id=tid
            )
        except Exception as exc:
            logger.error("Error en cmd_sorteo: %s", exc)
            self._error_y_borrar(cid, f"❌ Error: {exc}", thread_id=tid)

    # ─── /newbingo ────────────────────────────────────────────────────────────

    def cmd_newbingo(self, message: telebot.types.Message) -> None:
        """
        /newbingo [numero_maximo]

        Inicia un nuevo juego de bingo. Solo admins.
        """
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        self._borrar_seguro(cid, message.message_id)

        # Verificar permisos
        try:
            miembro  = self.bot.get_chat_member(cid, uid)
            is_admin = miembro.status in ("creator", "administrator")
        except Exception:
            is_admin = False

        if not is_admin:
            self._error_y_borrar(
                cid, "❌ Solo los administradores pueden iniciar un bingo.", thread_id=tid
            )
            return

        try:
            parts      = (message.text or "").split()
            numero_max = int(parts[1]) if len(parts) > 1 else 75

            if numero_max < 10:
                self._error_y_borrar(
                    cid, "❌ El número máximo debe ser al menos 10.", thread_id=tid
                )
                return

            self.bingo_numeros = list(range(1, numero_max + 1))
            random.shuffle(self.bingo_numeros)
            self.bingo_total = numero_max

            texto = (
                f"🎱 <b>¡BINGO INICIADO!</b>\n\n"
                f"Números del 1 al {numero_max}.\n"
                f"Usa /bingo para sacar el siguiente número.\n"
                f"Usa /finbingo para terminar."
            )

            logger.info("🎱 Bingo iniciado con max=%d", numero_max)
            self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)

        except (ValueError, IndexError):
            self._error_y_borrar(
                cid,
                "❌ Uso: /newbingo [numero_maximo]\nEjemplo: /newbingo 75",
                thread_id=tid,
            )
        except Exception as exc:
            logger.error("Error en cmd_newbingo: %s", exc)
            self._error_y_borrar(cid, f"❌ Error: {exc}", thread_id=tid)

    # ─── /bingo ───────────────────────────────────────────────────────────────

    def cmd_bingo(self, message: telebot.types.Message) -> None:
        """
        /bingo — Saca el siguiente número del bingo activo.
        """
        cid = message.chat.id
        tid = message.message_thread_id

        self._borrar_seguro(cid, message.message_id)

        if not self.bingo_numeros:
            self._error_y_borrar(
                cid,
                "❌ No hay bingo activo. Usa /newbingo para iniciar uno.",
                thread_id=tid,
            )
            return

        numero    = self.bingo_numeros.pop(0)
        restantes = len(self.bingo_numeros)

        texto = (
            f"🎱 <b>BINGO</b>\n\n"
            f"Número: <b>{numero}</b>\n"
            f"Quedan: {restantes} de {self.bingo_total}"
        )

        if restantes == 0:
            texto += "\n\n🏁 <i>¡Todos los números han salido!</i>"

        logger.info("🎱 Bingo número: %d | Quedan: %d", numero, restantes)
        self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)

    # ─── /finbingo ────────────────────────────────────────────────────────────

    def cmd_finbingo(self, message: telebot.types.Message) -> None:
        """
        /finbingo — Finaliza el bingo activo. Solo admins.
        """
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        self._borrar_seguro(cid, message.message_id)

        try:
            miembro  = self.bot.get_chat_member(cid, uid)
            is_admin = miembro.status in ("creator", "administrator")
        except Exception:
            is_admin = False

        if not is_admin:
            self._error_y_borrar(
                cid, "❌ Solo los administradores pueden finalizar el bingo.", thread_id=tid
            )
            return

        if not self.bingo_numeros and self.bingo_total == 0:
            self._error_y_borrar(
                cid, "❌ No hay bingo activo.", thread_id=tid
            )
            return

        numeros_sacados = self.bingo_total - len(self.bingo_numeros)
        self.bingo_numeros = []
        self.bingo_total   = 0

        texto = (
            f"🏁 <b>Bingo finalizado.</b>\n"
            f"Se sacaron {numeros_sacados} número(s)."
        )

        logger.info("🎱 Bingo finalizado. Números sacados: %d", numeros_sacados)
        m = self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
        self._borrar_tras_delay(cid, m.message_id, 10.0)