# -*- coding: utf-8 -*-
"""
handlers/roulette_handlers.py
════════════════════════════════════════════════════════════════════════════════
Sistema de Ruleta para UniverseBot V2.0

Comandos (solo admins del grupo):
  /ruleta on   — Abre la ruleta en el canal CASINO y arranca el ciclo de 5 min
  /ruleta off  — Cierra la ruleta (devuelve cosmos a apuestas pendientes)

Flujo de usuario:
  1. El admin activa la ruleta → aparece mensaje en CASINO con botón "Apostar"
  2. El usuario pulsa el botón → el bot le abre un DM con el tablero completo
  3. El usuario elige tipo → detalle → monto → confirma
     (Los cosmos se descuentan en el momento de confirmar)
  4. Cada 5 min el bot gira, publica resultados en CASINO y abona a ganadores
  5. Se abre automáticamente una nueva ronda con un nuevo botón de apuesta

Tipos de apuesta disponibles:
  Pleno (35×) · Caballo/Split (17×) · Calle (11×) · Cuadro/Corner (8×)
  Línea (5×) · Columna (2×) · Docena (2×) · Color (1×) · Par/Impar (1×)
  Baja/Alta (1×)
════════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

import telebot
from telebot import types

from config import MSG_USUARIO_NO_REGISTRADO
from funciones import economy_service, user_service
from funciones.roulette_service import (
    PAGOS,
    TIPOS_APUESTA,
    color_numero,
    cuadros_validos,
    numeros_adyacentes,
    roulette_service,
)

logger = logging.getLogger(__name__)

# ─── Constantes UI ───────────────────────────────────────────────────────────

_EMOJI_COLOR: Dict[str, str] = {"rojo": "🔴", "negro": "⚫", "verde": "💚"}

# Montos rápidos disponibles en el teclado de apuesta
_MONTOS_RAPIDOS = (50, 100, 250, 500, 1_000, 2_500, 5_000)

# ─── Estado de sesión por usuario (en memoria) ───────────────────────────────
# Estructura de cada entrada:
# {
#   "step":          "tipo" | "detalle" | "monto" | ...,
#   "tipo":          str | None,
#   "detalle":       str | None,
#   "cosmos":        int | None,
#   "msg_id":        int,
#   "apuestas_ronda": list[dict]   ← NUEVO: apuestas confirmadas en esta sesión
# }
_sessions: Dict[int, Dict[str, Any]] = {}
_sessions_lock = threading.Lock()


# ─── Helpers internos ────────────────────────────────────────────────────────

def _thread_id(message) -> Optional[int]:
    return getattr(message, "message_thread_id", None)


def _try_delete(bot: telebot.TeleBot, chat_id: int, msg_id: int) -> None:
    try:
        bot.delete_message(chat_id, msg_id)
    except Exception:
        pass


def _delete_after(bot: telebot.TeleBot, chat_id: int, msg_id: int, delay: float = 8.0) -> None:
    threading.Timer(delay, lambda: _try_delete(bot, chat_id, msg_id)).start()


def _is_admin(bot: telebot.TeleBot, chat_id: int, user_id: int) -> bool:
    try:
        return bot.get_chat_member(chat_id, user_id).status in ("creator", "administrator")
    except Exception:
        return False


def _detalle_legible(tipo: str, detalle: str) -> str:
    """Convierte el detalle interno en texto amigable para mostrar al usuario."""
    if tipo == "pleno":
        n = int(detalle)
        emoji = _EMOJI_COLOR.get(color_numero(n), "")
        return f"{emoji} {detalle}"
    if tipo == "caballo":
        return f"Split {detalle}"
    if tipo == "calle":
        n = int(detalle)
        return f"Calle {n}-{n+2}"
    if tipo == "cuadro":
        from funciones.roulette_service import _cuadro_desde_n
        nums = _cuadro_desde_n(int(detalle)) or []
        return "Corner " + "-".join(str(x) for x in nums)
    if tipo == "linea":
        n = int(detalle)
        return f"Línea {n}-{n+5}"
    if tipo == "columna":
        return f"Columna {detalle}"
    if tipo == "docena":
        etiq = {"1": "1ª (1-12)", "2": "2ª (13-24)", "3": "3ª (25-36)"}
        return etiq.get(detalle, detalle)
    if tipo == "color":
        return f"{_EMOJI_COLOR.get(detalle, '')} {detalle.capitalize()}"
    if tipo == "paridad":
        return detalle.capitalize()
    if tipo == "mitad":
        return "1-18 (Baja)" if detalle == "baja" else "19-36 (Alta)"
    return detalle


# ─── Teclados inline ─────────────────────────────────────────────────────────

def _kb_menu_principal() -> types.InlineKeyboardMarkup:
    """Menú raíz: selección del tipo de apuesta."""
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🎯 Pleno (35×)",      callback_data="rl:tipo:pleno"),
        types.InlineKeyboardButton("🐴 Caballo (17×)",    callback_data="rl:tipo:caballo"),
        types.InlineKeyboardButton("🛣️ Calle (11×)",      callback_data="rl:tipo:calle"),
        types.InlineKeyboardButton("⬛ Cuadro (8×)",      callback_data="rl:tipo:cuadro"),
        types.InlineKeyboardButton("📏 Línea (5×)",       callback_data="rl:tipo:linea"),
        types.InlineKeyboardButton("🏛️ Columna (2×)",     callback_data="rl:tipo:columna"),
        types.InlineKeyboardButton("📦 Docena (2×)",      callback_data="rl:tipo:docena"),
        types.InlineKeyboardButton("🔴⚫ Color (1×)",     callback_data="rl:tipo:color"),
        types.InlineKeyboardButton("2️⃣ Par / Impar (1×)", callback_data="rl:tipo:paridad"),
        types.InlineKeyboardButton("⬆️ Baja / Alta (1×)", callback_data="rl:tipo:mitad"),
    )
    kb.add(types.InlineKeyboardButton("❌ Cancelar", callback_data="rl:cancelar"))
    return kb


def _fila_pano(fila: int, cb_prefix: str) -> list:
    """
    Genera los 12 botones de una fila del paño de ruleta.

    Layout del paño (igual que roulette_service.numeros_adyacentes):
      fila 3 (tope):  3,  6,  9, 12, 15, 18, 21, 24, 27, 30, 33, 36
      fila 2 (medio): 2,  5,  8, 11, 14, 17, 20, 23, 26, 29, 32, 35
      fila 1 (base):  1,  4,  7, 10, 13, 16, 19, 22, 25, 28, 31, 34

    Args:
        fila:      3, 2 o 1
        cb_prefix: prefijo del callback_data ("rl:num" o "rl:cab1")
    """
    # Cada columna del paño agrupa 3 números: col k → k*3-2, k*3-1, k*3
    # La fila indica el offset dentro de cada grupo: fila 1=base, 2=medio, 3=tope
    nums = [col * 3 - (3 - fila) for col in range(1, 13)]
    btns = []
    for n in nums:
        emoji = "🔴" if n in _ROJOS else "⚫"
        btns.append(
            types.InlineKeyboardButton(f"{emoji}{n}", callback_data=f"{cb_prefix}:{n}")
        )
    return btns


def _kb_numeros_pleno() -> types.InlineKeyboardMarkup:
    """
    Grilla numérica para elegir pleno.
    Respeta el layout real del paño: 3 filas × 12 columnas + 0 aparte.

      Fila 3:  3  6  9 12 15 18 21 24 27 30 33 36
      Fila 2:  2  5  8 11 14 17 20 23 26 29 32 35
      Fila 1:  1  4  7 10 13 16 19 22 25 28 31 34
    """
    kb = types.InlineKeyboardMarkup(row_width=12)
    kb.add(types.InlineKeyboardButton("0 💚", callback_data="rl:num:0"))
    kb.row(*_fila_pano(3, "rl:num"))
    kb.row(*_fila_pano(2, "rl:num"))
    kb.row(*_fila_pano(1, "rl:num"))
    kb.add(types.InlineKeyboardButton("↩️ Volver", callback_data="rl:volver"))
    return kb


def _kb_numeros_caballo_1() -> types.InlineKeyboardMarkup:
    """
    Paso 1 del caballo: elige el primer número.
    Misma grilla real del paño que _kb_numeros_pleno.
    """
    kb = types.InlineKeyboardMarkup(row_width=12)
    kb.row(*_fila_pano(3, "rl:cab1"))
    kb.row(*_fila_pano(2, "rl:cab1"))
    kb.row(*_fila_pano(1, "rl:cab1"))
    kb.add(types.InlineKeyboardButton("↩️ Volver", callback_data="rl:volver"))
    return kb


def _kb_numeros_caballo_2(primer_numero: int) -> types.InlineKeyboardMarkup:
    """Paso 2 del caballo: muestra solo los adyacentes al primer número."""
    kb = types.InlineKeyboardMarkup(row_width=4)
    adyacentes = numeros_adyacentes(primer_numero)
    btns = []
    for adj in adyacentes:
        emoji = "🔴" if adj in _ROJOS else "⚫"
        detalle = f"{min(primer_numero, adj)}-{max(primer_numero, adj)}"
        btns.append(
            types.InlineKeyboardButton(f"{emoji}{adj}", callback_data=f"rl:det:{detalle}")
        )
    kb.row(*btns)
    kb.add(types.InlineKeyboardButton("↩️ Volver", callback_data="rl:volver"))
    return kb


def _kb_calle() -> types.InlineKeyboardMarkup:
    """Calles: inicio de cada fila (1, 4, 7, …, 34)."""
    kb = types.InlineKeyboardMarkup(row_width=4)
    btns = [
        types.InlineKeyboardButton(f"{n}-{n+2}", callback_data=f"rl:det:{n}")
        for n in range(1, 35, 3)
    ]
    for i in range(0, len(btns), 4):
        kb.row(*btns[i : i + 4])
    kb.add(types.InlineKeyboardButton("↩️ Volver", callback_data="rl:volver"))
    return kb


def _kb_cuadro() -> types.InlineKeyboardMarkup:
    """Cuadros (corners): todos los bloques 2×2 válidos del paño."""
    kb = types.InlineKeyboardMarkup(row_width=3)
    btns = [
        types.InlineKeyboardButton(
            f"{ns[0]},{ns[1]},{ns[2]},{ns[3]}", callback_data=f"rl:det:{n}"
        )
        for n, ns in cuadros_validos()
    ]
    for i in range(0, len(btns), 3):
        kb.row(*btns[i : i + 3])
    kb.add(types.InlineKeyboardButton("↩️ Volver", callback_data="rl:volver"))
    return kb


def _kb_linea() -> types.InlineKeyboardMarkup:
    """Líneas (dobles calles): 1-6, 4-9, …, 31-36."""
    kb = types.InlineKeyboardMarkup(row_width=3)
    btns = [
        types.InlineKeyboardButton(f"{n}-{n+5}", callback_data=f"rl:det:{n}")
        for n in range(1, 32, 3)
    ]
    for i in range(0, len(btns), 3):
        kb.row(*btns[i : i + 3])
    kb.add(types.InlineKeyboardButton("↩️ Volver", callback_data="rl:volver"))
    return kb


def _kb_columna() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("Col. 1\n1·4·7···34", callback_data="rl:det:1"),
        types.InlineKeyboardButton("Col. 2\n2·5·8···35", callback_data="rl:det:2"),
        types.InlineKeyboardButton("Col. 3\n3·6·9···36", callback_data="rl:det:3"),
    )
    kb.add(types.InlineKeyboardButton("↩️ Volver", callback_data="rl:volver"))
    return kb


def _kb_docena() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("1ª Docena\n1 – 12",  callback_data="rl:det:1"),
        types.InlineKeyboardButton("2ª Docena\n13 – 24", callback_data="rl:det:2"),
        types.InlineKeyboardButton("3ª Docena\n25 – 36", callback_data="rl:det:3"),
    )
    kb.add(types.InlineKeyboardButton("↩️ Volver", callback_data="rl:volver"))
    return kb


def _kb_color() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🔴 Rojo",  callback_data="rl:det:rojo"),
        types.InlineKeyboardButton("⚫ Negro", callback_data="rl:det:negro"),
    )
    kb.add(types.InlineKeyboardButton("↩️ Volver", callback_data="rl:volver"))
    return kb


def _kb_paridad() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("2️⃣ Par",   callback_data="rl:det:par"),
        types.InlineKeyboardButton("1️⃣ Impar", callback_data="rl:det:impar"),
    )
    kb.add(types.InlineKeyboardButton("↩️ Volver", callback_data="rl:volver"))
    return kb


def _kb_mitad() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("⬇️ Baja  1-18",  callback_data="rl:det:baja"),
        types.InlineKeyboardButton("⬆️ Alta  19-36", callback_data="rl:det:alta"),
    )
    kb.add(types.InlineKeyboardButton("↩️ Volver", callback_data="rl:volver"))
    return kb


def _kb_montos(balance: int) -> types.InlineKeyboardMarkup:
    """Teclado de montos rápidos; muestra solo los que el usuario puede pagar."""
    kb = types.InlineKeyboardMarkup(row_width=4)
    btns = [
        types.InlineKeyboardButton(f"{m} ✨", callback_data=f"rl:monto:{m}")
        for m in _MONTOS_RAPIDOS
        if m <= balance
    ]
    if balance > 0:
        btns.append(
            types.InlineKeyboardButton(
                f"💥 All-In ({balance:,})", callback_data="rl:monto:allin"
            )
        )
    for i in range(0, len(btns), 4):
        kb.row(*btns[i : i + 4])
    kb.add(types.InlineKeyboardButton("↩️ Volver", callback_data="rl:volver"))
    return kb


def _kb_confirmar() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ Confirmar apuesta", callback_data="rl:confirmar"),
        types.InlineKeyboardButton("❌ Cancelar",         callback_data="rl:cancelar"),
    )
    return kb


# Set auxiliar para el teclado numérico (evita importar el módulo dos veces)
from funciones.roulette_service import NUMEROS_ROJOS as _ROJOS  # noqa: E402


# ─── Clase principal ──────────────────────────────────────────────────────────

class RouletteHandlers:
    """
    Handlers del sistema de ruleta.

    Registra:
      - /ruleta  (admins del grupo)
      - callback 'ruleta:abrir'  (botón del anuncio en el canal)
      - callbacks 'rl:*'         (flujo de apuesta en DM)
    """

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        self._register_handlers()

    # ── Registro de handlers ──────────────────────────────────────────────────

    def _register_handlers(self) -> None:
        self.bot.register_message_handler(self.cmd_ruleta, commands=["ruleta"])
        self.bot.register_callback_query_handler(
            self.callback_abrir_ruleta,
            func=lambda c: c.data == "ruleta:abrir",
        )
        self.bot.register_callback_query_handler(
            self.callback_ruleta,
            func=lambda c: c.data.startswith("rl:"),
        )

    # ── /ruleta on | off ──────────────────────────────────────────────────────

    def cmd_ruleta(self, message) -> None:
        cid = message.chat.id
        tid = _thread_id(message)
        uid = message.from_user.id

        _try_delete(self.bot, cid, message.message_id)

        if not _is_admin(self.bot, cid, uid):
            m = self.bot.send_message(
                cid,
                "❌ Solo los administradores pueden gestionar la ruleta.",
                message_thread_id=tid,
            )
            _delete_after(self.bot, cid, m.message_id)
            return

        partes = (message.text or "").split()
        accion = partes[1].lower() if len(partes) > 1 else ""

        if accion == "on":
            self._activar_ruleta(cid, tid)
        elif accion == "off":
            self._desactivar_ruleta(cid, tid)
        else:
            m = self.bot.send_message(
                cid,
                "ℹ️ Uso: <code>/ruleta on</code> o <code>/ruleta off</code>",
                parse_mode="HTML",
                message_thread_id=tid,
            )
            _delete_after(self.bot, cid, m.message_id)

    # ── Activar ───────────────────────────────────────────────────────────────

    def _activar_ruleta(self, chat_id: int, thread_id: Optional[int]) -> None:
        ok = roulette_service.activar(chat_id, thread_id)
        if not ok:
            m = self.bot.send_message(
                chat_id, "⚠️ La ruleta ya está activa.", message_thread_id=thread_id
            )
            _delete_after(self.bot, chat_id, m.message_id)
            return

        self._publicar_anuncio_ronda(chat_id, thread_id, primera_vez=True)
        roulette_service.iniciar_timer(self._giro_automatico)

    # ── Desactivar ────────────────────────────────────────────────────────────

    def _desactivar_ruleta(self, chat_id: int, thread_id: Optional[int]) -> None:
        ok, pendientes = roulette_service.desactivar()
        if not ok:
            m = self.bot.send_message(
                chat_id, "⚠️ La ruleta no estaba activa.", message_thread_id=thread_id
            )
            _delete_after(self.bot, chat_id, m.message_id)
            return

        # Devolver cosmos a jugadores con apuestas pendientes
        for uid, cosmos in pendientes.items():
            economy_service.add_credits(uid, cosmos, "Devolución ruleta cerrada por admin")
            try:
                self.bot.send_message(
                    uid,
                    f"ℹ️ La ruleta fue cerrada por un administrador.\n"
                    f"Se te devolvieron <b>{cosmos} ✨ Cosmos</b>.",
                    parse_mode="HTML",
                )
            except Exception:
                pass  # El usuario puede no tener DM abierto

        texto_dev = (
            f"\n\n↩️ <i>{len(pendientes)} jugadores recibieron sus cosmos de vuelta.</i>"
            if pendientes else ""
        )
        self.bot.send_message(
            chat_id,
            f"🛑 <b>La ruleta ha sido cerrada</b> por un administrador.{texto_dev}",
            parse_mode="HTML",
            message_thread_id=thread_id,
        )
    
    # ── Publicar anuncio de ronda ─────────────────────────────────────────────

    def _publicar_anuncio_ronda(
        self,
        chat_id: int,
        thread_id: Optional[int],
        primera_vez: bool = False,
    ) -> None:
        """Publica (o re-publica) el mensaje de ronda abierta en el canal."""
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🎰 ¡Apostar ahora!", callback_data="ruleta:abrir"))

        encabezado = (
            "🎡 <b>¡LA RULETA ESTÁ ABIERTA!</b> 🎡\n\n"
            if primera_vez
            else f"🎡 <b>Nueva ronda — #{roulette_service.ronda}</b>\n\n"
        )

        msg = self.bot.send_message(
            chat_id,
            f"{encabezado}"
            f"Tienes <b>5 minutos</b> para colocar tus apuestas.\n"
            f"Pulsa el botón y te abriré el tablero en privado.\n\n"
            f"<b>Tipos de apuesta:</b>\n"
            f"🎯 Pleno 35× · 🐴 Caballo 17× · 🛣️ Calle 11×\n"
            f"⬛ Cuadro 8× · 📏 Línea 5× · 🏛️ Columna 2× · 📦 Docena 2×\n"
            f"🔴 Color 1× · 2️⃣ Par/Impar 1× · ⬆️ Baja/Alta 1×",
            parse_mode="HTML",
            message_thread_id=thread_id,
            reply_markup=kb,
        )
        roulette_service.set_mensaje_anuncio(msg.message_id)

    # ── Giro automático ───────────────────────────────────────────────────────

    def _giro_automatico(self) -> None:
        """Llamado por el timer cada 5 minutos."""
        if not roulette_service.activa:
            return

        # Capturar IDs ANTES del giro: mientras la ruleta está activa se garantiza
        # que chat_id no es None (fue asignado en activar()).
        chat_id   = roulette_service.chat_id
        thread_id = roulette_service.thread_id

        if chat_id is None:
            # Nunca debería ocurrir, pero lo capturamos para evitar un crash silencioso.
            logger.error(
                "[RULETA] _giro_automatico: chat_id es None con ruleta activa — "
                "abortando ciclo."
            )
            return

        try:
            self._ejecutar_giro()
        except Exception as exc:
            logger.error("[RULETA] Error en giro automático: %s", exc, exc_info=True)
        finally:
            # Reiniciar ciclo si la ruleta sigue activa.
            # CRÍTICO: usar nueva_ronda() en vez de activar() porque activar()
            # devuelve False cuando _activa ya es True, impidiendo que la ronda avance.
            if roulette_service.activa:
                roulette_service.nueva_ronda()
                roulette_service.iniciar_timer(self._giro_automatico)
                self._publicar_anuncio_ronda(chat_id, thread_id)

    def _ejecutar_giro(self) -> None:
        """Gira la ruleta, distribuye pagos y publica el resultado."""
        chat_id   = roulette_service.chat_id
        thread_id = roulette_service.thread_id

        if chat_id is None:
            # Defensa adicional: _giro_automatico ya lo verifica, pero si
            # _ejecutar_giro se llama de forma independiente en el futuro,
            # este guard evita un crash.
            logger.error(
                "[RULETA] _ejecutar_giro: chat_id es None — no se puede publicar el resultado."
            )
            return

        numero, color, resultados = roulette_service.girar()
        usernames = roulette_service.get_last_usernames()

        emoji_col = _EMOJI_COLOR.get(color, "🎡")
        lineas = [
            "🎡 <b>¡LA RULETA HA GIRADO!</b>\n",
            f"🔢 Número: <b>{numero}</b>",
            f"🎨 Color: {emoji_col} <b>{color.capitalize()}</b>\n",
        ]

        if not resultados:
            lineas.append("📭 <i>No hubo apuestas esta ronda.</i>")
        else:
            ganadores  = {uid: r for uid, r in resultados.items() if r["gano"]}
            perdedores = {uid: r for uid, r in resultados.items() if not r["gano"]}

            if ganadores:
                lineas.append("🏆 <b>Ganadores:</b>")
                for uid, res in sorted(ganadores.items(), key=lambda x: -x[1]["pago"]):
                    nombre   = usernames.get(uid, f"Usuario {uid}")
                    ganancia = res["pago"] - res["apostado"]   # beneficio neto
                    economy_service.add_credits(
                        uid, res["pago"], f"Ruleta giro #{roulette_service.ronda-1}"
                    )
                    lineas.append(
                        f"  ✅ {nombre}: apostó {res['apostado']:,} ✨ → "
                        f"<b>+{ganancia:,} ✨</b>"
                    )

            if perdedores:
                lineas.append("\n😔 <b>Sin suerte esta vez:</b>")
                for uid, res in perdedores.items():
                    nombre = usernames.get(uid, f"Usuario {uid}")
                    lineas.append(f"  ❌ {nombre}: -{res['apostado']:,} ✨")

        self.bot.send_message(
            chat_id,
            "\n".join(lineas),
            parse_mode="HTML",
            message_thread_id=thread_id,
        )

    # ── Callback: abrir tablero en DM ─────────────────────────────────────────

    def callback_abrir_ruleta(self, call: types.CallbackQuery) -> None:
        """Responde al botón 'Apostar' del anuncio en el canal."""
        uid      = call.from_user.id
        username = call.from_user.username or call.from_user.first_name

        if not roulette_service.activa:
            self.bot.answer_callback_query(
                call.id, "⚠️ La ruleta ya cerró esta ronda.", show_alert=True
            )
            return

        user_info = user_service.get_user_info(uid)
        if not user_info:
            self.bot.answer_callback_query(
                call.id, MSG_USUARIO_NO_REGISTRADO, show_alert=True
            )
            return

        self.bot.answer_callback_query(call.id)
        balance = economy_service.get_balance(uid)

        try:
            msg = self.bot.send_message(
                uid,
                f"🎡 <b>Ruleta — Ronda #{roulette_service.ronda}</b>\n\n"
                f"💰 Saldo: <b>{balance:,} ✨</b>\n\n"
                "Elige el tipo de apuesta:",
                parse_mode="HTML",
                reply_markup=_kb_menu_principal(),
            )
            with _sessions_lock:
                _sessions[uid] = {
                    "step":    "tipo",
                    "tipo":    None,
                    "detalle": None,
                    "cosmos":  None,
                    "msg_id":  msg.message_id,
                    "apuestas_ronda": [],
                }
        except telebot.apihelper.ApiTelegramException as exc:
            if "bot can't initiate conversation" in str(exc).lower():
                self.bot.answer_callback_query(
                    call.id,
                    "⚠️ Primero inicia una conversación privada conmigo para poder enviarte el tablero.",
                    show_alert=True,
                )
            else:
                logger.error("[RULETA] Error abriendo DM: %s", exc)

    # ── Dispatcher principal de callbacks del tablero ─────────────────────────

    def callback_ruleta(self, call: types.CallbackQuery) -> None:
        """Gestiona todos los callbacks 'rl:*' del flujo de apuesta en DM."""
        uid   = call.from_user.id
        partes = call.data.split(":", 2)
        accion = partes[1] if len(partes) > 1 else ""
        valor  = partes[2] if len(partes) > 2 else ""

        self.bot.answer_callback_query(call.id)

        if accion == "noop":
            return

        if accion == "cancelar":
            self._limpiar_sesion(uid, call.message.chat.id, call.message.message_id)
            return

        if accion == "volver":
            self._ir_al_menu(uid, call.message)
            return
        
        if accion == "nueva_apuesta":
            # Volver al menú sin resetear apuestas_ronda
            self._ir_al_menu(uid, call.message, reset_apuestas=False)
            return

        if accion == "listo":
            with _sessions_lock:
                apuestas = _sessions.pop(uid, {}).get("apuestas_ronda", [])
            total = sum(a["cosmos"] for a in apuestas)
            resumen = "\n".join(
                f"  • {a['tipo'].capitalize()} → {_detalle_legible(a['tipo'], a['detalle'])}"
                f"  <b>{a['cosmos']:,} ✨</b>"
                for a in apuestas
            ) or "  (ninguna)"
            self._editar(
                call.message.chat.id, call.message.message_id,
                f"🎡 <b>Ronda #{roulette_service.ronda}</b>\n\n"
                f"<b>Apuestas confirmadas:</b>\n{resumen}\n\n"
                f"💸 Total: <b>{total:,} ✨</b>\n\n"
                "¡El resultado se publicará cuando gire la ruleta! 🍀",
                None,
            )
            return

        if accion == "repetir":
            self._repetir_apuestas(uid, call)
            return
        
        if accion == "nueva_apuesta":
            # Volver al menú principal sin borrar apuestas_ronda
            self._ir_al_menu(uid, call.message, reset_apuestas=False)
            return

        if accion == "listo":
            # El usuario terminó de apostar — mostrar resumen final
            with _sessions_lock:
                apuestas = _sessions.get(uid, {}).get("apuestas_ronda", [])
            total = sum(a["cosmos"] for a in apuestas)
            resumen = "\n".join(
                f"  • {a['tipo'].capitalize()} → {_detalle_legible(a['tipo'], a['detalle'])}"
                f"  ({a['cosmos']:,} ✨)"
                for a in apuestas
            ) or "  (ninguna)"
            self._editar(
                call.message.chat.id, call.message.message_id,
                f"🎡 <b>Ronda #{roulette_service.ronda}</b>\n\n"
                f"<b>Apuestas confirmadas:</b>\n{resumen}\n\n"
                f"💸 Total: <b>{total:,} ✨</b>\n\n"
                "¡El resultado se publicará cuando gire la ruleta! 🍀",
                None,
            )
            with _sessions_lock:
                _sessions.pop(uid, None)
            return

        if accion == "repetir":
            # Repetir todas las apuestas de la ronda anterior
            self._repetir_apuestas(uid, call)
            return
        
        # Verificar que la ruleta siga activa antes de continuar
        if not roulette_service.activa:
            self._editar(
                call.message.chat.id, call.message.message_id,
                "⚠️ La ruleta ya no está activa.", None,
            )
            with _sessions_lock:
                _sessions.pop(uid, None)
            return

        with _sessions_lock:
            sesion = _sessions.get(uid)

        if sesion is None:
            # Sesión expirada (bot reiniciado, etc.) → reiniciar menú
            self._ir_al_menu(uid, call.message)
            return

        if accion == "tipo":
            self._paso_tipo(uid, valor, call.message)
        elif accion == "num":
            # Pleno: número seleccionado
            self._paso_detalle(uid, valor, call.message)
        elif accion == "cab1":
            # Caballo paso 1: primer número elegido
            self._paso_caballo_2(uid, int(valor), call.message)
        elif accion == "det":
            # Detalle final para cualquier tipo (incluye split en caballo paso 2)
            self._paso_detalle(uid, valor, call.message)
        elif accion == "monto":
            self._paso_monto(uid, valor, call.message)
        elif accion == "confirmar":
            self._paso_confirmar(uid, call)

    # ── Pasos del flujo ───────────────────────────────────────────────────────

    def _paso_tipo(self, uid: int, tipo: str, message: types.Message) -> None:
        """El usuario eligió el tipo de apuesta."""
        with _sessions_lock:
            if uid not in _sessions:
                return
            _sessions[uid]["tipo"]   = tipo
            _sessions[uid]["step"]   = "detalle"
            _sessions[uid]["detalle"] = None

        kb, instruccion = self._teclado_para_tipo(tipo)
        self._editar(
            message.chat.id, message.message_id,
            f"🎡 <b>{TIPOS_APUESTA[tipo]}</b>\n\n{instruccion}",
            kb,
        )

    def _teclado_para_tipo(self, tipo: str):
        """Retorna (InlineKeyboardMarkup, texto_instruccion) según el tipo."""
        if tipo == "pleno":
            return _kb_numeros_pleno(), "Elige el número exacto:"
        if tipo == "caballo":
            return _kb_numeros_caballo_1(), "Paso 1 — Elige el primer número:"
        if tipo == "calle":
            return _kb_calle(), "Elige la fila (3 números consecutivos):"
        if tipo == "cuadro":
            return _kb_cuadro(), "Elige el bloque 2×2 (Corner):"
        if tipo == "linea":
            return _kb_linea(), "Elige la línea (6 números, 2 filas):"
        if tipo == "columna":
            return _kb_columna(), "Elige la columna:"
        if tipo == "docena":
            return _kb_docena(), "Elige la docena:"
        if tipo == "color":
            return _kb_color(), "Elige el color:"
        if tipo == "paridad":
            return _kb_paridad(), "¿Par o Impar?"
        if tipo == "mitad":
            return _kb_mitad(), "¿Baja (1-18) o Alta (19-36)?"
        return _kb_menu_principal(), "Elige el tipo de apuesta:"

    def _paso_caballo_2(self, uid: int, primer_num: int, message: types.Message) -> None:
        """Caballo paso 2: mostrar los adyacentes al primer número elegido."""
        with _sessions_lock:
            if uid not in _sessions:
                return

        kb = _kb_numeros_caballo_2(primer_num)
        self._editar(
            message.chat.id, message.message_id,
            f"🎡 <b>Caballo / Split</b>\n\n"
            f"Primer número: <b>{primer_num}</b>\n"
            f"Paso 2 — Elige el número adyacente para el split:",
            kb,
        )

    def _paso_detalle(self, uid: int, detalle: str, message: types.Message) -> None:
        """El usuario eligió el detalle (número, color, columna, etc.)."""
        with _sessions_lock:
            if uid not in _sessions:
                return
            sesion         = _sessions[uid]
            sesion["detalle"] = detalle
            sesion["step"]    = "monto"
            tipo = sesion["tipo"]

        balance = economy_service.get_balance(uid)
        det_leg = _detalle_legible(tipo, detalle)

        self._editar(
            message.chat.id, message.message_id,
            f"🎡 <b>{TIPOS_APUESTA[tipo]}</b>\n"
            f"📌 Elección: <b>{det_leg}</b>\n"
            f"💰 Saldo disponible: <b>{balance:,} ✨</b>\n\n"
            "¿Cuántos Cosmos apostás?",
            _kb_montos(balance),
        )

    def _paso_monto(self, uid: int, valor: str, message: types.Message) -> None:
        """El usuario eligió el monto de la apuesta."""
        with _sessions_lock:
            if uid not in _sessions:
                return
            sesion = _sessions[uid]
            tipo   = sesion["tipo"]
            detalle = sesion["detalle"]

        balance = economy_service.get_balance(uid)

        cosmos = balance if valor == "allin" else _parse_int(valor, 0)

        if cosmos <= 0:
            self.bot.send_message(uid, "❌ Monto inválido.")
            return
        if cosmos > balance:
            self.bot.send_message(
                uid,
                f"❌ Saldo insuficiente. Tienes <b>{balance:,} ✨</b>.",
                parse_mode="HTML",
            )
            return

        with _sessions_lock:
            if uid not in _sessions:
                return
            _sessions[uid]["cosmos"] = cosmos
            _sessions[uid]["step"]   = "confirmar"

        det_leg      = _detalle_legible(tipo, detalle)
        multiplicador = PAGOS[tipo]
        ganancia_neta = cosmos * multiplicador
        pago_total    = cosmos + ganancia_neta

        self._editar(
            message.chat.id, message.message_id,
            f"🎡 <b>Confirmar apuesta</b>\n\n"
            f"📋 Tipo: <b>{tipo.capitalize()}</b>\n"
            f"📌 Elección: <b>{det_leg}</b>\n"
            f"💸 Apuesta: <b>{cosmos:,} ✨</b>\n"
            f"💰 Si ganás recibirás: <b>{pago_total:,} ✨</b> "
            f"({multiplicador}× + apuesta devuelta)\n\n"
            "¿Confirmás?",
            _kb_confirmar(),
        )

    def _paso_confirmar(self, uid: int, call: types.CallbackQuery) -> None:
        """El usuario confirma la apuesta: descontar cosmos y registrar."""
        with _sessions_lock:
            sesion = _sessions.pop(uid, None)

        if sesion is None:
            return

        tipo    = sesion["tipo"]
        detalle = sesion["detalle"]
        cosmos  = sesion["cosmos"]
        username = call.from_user.username or call.from_user.first_name

        # Descontar cosmos antes de registrar
        if not economy_service.subtract_credits(
            uid, cosmos, f"Apuesta ruleta ronda #{roulette_service.ronda}: {tipo}/{detalle}"
        ):
            self._editar(
                call.message.chat.id, call.message.message_id,
                "❌ No se pudo descontar los Cosmos. ¿Tienes saldo suficiente?",
                None,
            )
            return

        ok, err = roulette_service.registrar_apuesta(uid, username, tipo, detalle, cosmos)
        if not ok:
            economy_service.add_credits(
                uid, cosmos, "Reversión: ruleta cerrada al confirmar apuesta"
            )
            self._editar(
                call.message.chat.id, call.message.message_id,
                f"❌ No se pudo registrar la apuesta: {err}\n"
                f"Se te devolvieron <b>{cosmos:,} ✨</b>.",
                None,
            )
            return

        # ── Guardar apuesta en sesión (NO borrar la sesión) ───────────────
        with _sessions_lock:
            if uid not in _sessions:
                _sessions[uid] = {
                    "step": "listo", "tipo": None, "detalle": None,
                    "cosmos": None, "msg_id": call.message.message_id,
                    "apuestas_ronda": [],
                }
            sesion_actual = _sessions[uid]
            sesion_actual.setdefault("apuestas_ronda", []).append(
                {"tipo": tipo, "detalle": detalle, "cosmos": cosmos}
            )
            sesion_actual["step"] = "listo"
            sesion_actual["tipo"] = None
            sesion_actual["detalle"] = None
            sesion_actual["cosmos"] = None
            apuestas_ronda = list(sesion_actual["apuestas_ronda"])

        det_leg       = _detalle_legible(tipo, detalle)
        multiplicador = PAGOS[tipo]
        pago_total    = cosmos + cosmos * multiplicador
        nuevo_balance = economy_service.get_balance(uid)
        total_apostado = sum(a["cosmos"] for a in apuestas_ronda)

        resumen = "\n".join(
            f"  • {a['tipo'].capitalize()} → {_detalle_legible(a['tipo'], a['detalle'])}"
            f"  <b>{a['cosmos']:,} ✨</b>"
            for a in apuestas_ronda
        )

        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton(
                "➕ Agregar otra apuesta", callback_data="rl:nueva_apuesta"
            ),
            types.InlineKeyboardButton(
                "✅ Listo (esperar el giro)", callback_data="rl:listo"
            ),
        )

        self._editar(
            call.message.chat.id, call.message.message_id,
            f"✅ <b>¡Apuesta registrada!</b>\n\n"
            f"🎡 Ronda #{roulette_service.ronda}\n\n"
            f"<b>Tus apuestas esta ronda:</b>\n{resumen}\n\n"
            f"💸 Total apostado: <b>{total_apostado:,} ✨</b>\n"
            f"🏦 Saldo restante: <b>{nuevo_balance:,} ✨</b>\n\n"
            "Podés agregar más apuestas o esperar el giro 🍀",
            kb,
        )

    # ── Helpers de sesión y UI ────────────────────────────────────────────────

    def _ir_al_menu(self, uid: int, message: types.Message,
                    reset_apuestas: bool = True) -> None:
        """Vuelve al menú principal de tipos de apuesta."""
        balance = economy_service.get_balance(uid)
        with _sessions_lock:
            if uid in _sessions:
                update = {"step": "tipo", "tipo": None, "detalle": None, "cosmos": None}
                if reset_apuestas:
                    update["apuestas_ronda"] = []
                _sessions[uid].update(update)
            else:
                _sessions[uid] = {
                    "step": "tipo", "tipo": None, "detalle": None,
                    "cosmos": None, "msg_id": message.message_id,
                    "apuestas_ronda": [],
                }

        # Añadir botón "Repetir" si hay apuestas de ronda anterior
        ultimas = roulette_service.get_last_apuestas_by_user(uid)
        kb = _kb_menu_principal()
        if ultimas:
            total_prev = sum(a["cosmos"] for a in ultimas)
            kb.add(types.InlineKeyboardButton(
                f"🔁 Repetir última apuesta ({total_prev:,} ✨)",
                callback_data="rl:repetir",
            ))

        self._editar(
            message.chat.id, message.message_id,
            f"🎡 <b>Ruleta — Ronda #{roulette_service.ronda}</b>\n\n"
            f"💰 Saldo: <b>{balance:,} ✨</b>\n\n"
            "Elige el tipo de apuesta:",
            kb,
        )

    def _repetir_apuestas(self, uid: int, call: types.CallbackQuery) -> None:
        """Re-registra las apuestas de la ronda anterior."""
        ultimas = roulette_service.get_last_apuestas_by_user(uid)
        if not ultimas:
            self.bot.answer_callback_query(
                call.id, "⚠️ No hay apuestas anteriores para repetir.", show_alert=True
            )
            return
        if not roulette_service.activa:
            self.bot.answer_callback_query(
                call.id, "⚠️ La ruleta no está activa.", show_alert=True
            )
            return

        username  = call.from_user.username or call.from_user.first_name
        balance   = economy_service.get_balance(uid)
        total_req = sum(a["cosmos"] for a in ultimas)

        if balance < total_req:
            self.bot.answer_callback_query(
                call.id,
                f"❌ Saldo insuficiente. Necesitás {total_req:,} ✨, tenés {balance:,} ✨.",
                show_alert=True,
            )
            return

        economy_service.subtract_credits(uid, total_req, "Ruleta — repetir apuestas")

        registradas, cosmos_fallidos = [], 0
        for ap in ultimas:
            ok, _ = roulette_service.registrar_apuesta(
                uid, username, ap["tipo"], ap["detalle"], ap["cosmos"]
            )
            if ok:
                registradas.append(ap)
            else:
                cosmos_fallidos += ap["cosmos"]

        if cosmos_fallidos:
            economy_service.add_credits(uid, cosmos_fallidos, "Ruleta — reversión apuestas fallidas")

        with _sessions_lock:
            _sessions[uid] = {
                "step": "listo", "tipo": None, "detalle": None, "cosmos": None,
                "msg_id": call.message.message_id,
                "apuestas_ronda": registradas,
            }

        resumen = "\n".join(
            f"  • {a['tipo'].capitalize()} → {_detalle_legible(a['tipo'], a['detalle'])}"
            f"  <b>{a['cosmos']:,} ✨</b>"
            for a in registradas
        )
        nuevo_balance = economy_service.get_balance(uid)
        self._editar(
            call.message.chat.id, call.message.message_id,
            f"🔁 <b>¡Apuestas repetidas!</b>\n\n"
            f"🎡 Ronda #{roulette_service.ronda}\n\n"
            f"{resumen}\n\n"
            f"💸 Total: <b>{sum(a['cosmos'] for a in registradas):,} ✨</b>\n"
            f"🏦 Saldo: <b>{nuevo_balance:,} ✨</b>\n\n"
            "¡El resultado se publicará cuando gire la ruleta! 🍀",
            None,
        )

    def _limpiar_sesion(self, uid: int, chat_id: int, msg_id: int) -> None:
        with _sessions_lock:
            _sessions.pop(uid, None)
        self._editar(chat_id, msg_id, "❌ Apuesta cancelada.", None)

    def _editar(
        self,
        chat_id: int,
        msg_id: int,
        texto: str,
        kb: Optional[types.InlineKeyboardMarkup],
    ) -> None:
        """Edita el mensaje de la botonera con nuevo texto y teclado."""
        try:
            self.bot.edit_message_text(
                texto,
                chat_id=chat_id,
                message_id=msg_id,
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception as exc:
            logger.debug("[RULETA] No se pudo editar mensaje %s: %s", msg_id, exc)


# ─── Helper de conversión segura ─────────────────────────────────────────────

def _parse_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
