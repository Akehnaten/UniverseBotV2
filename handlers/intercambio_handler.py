# -*- coding: utf-8 -*-
"""
handlers/intercambio_handler.py

Handler unificado de intercambios P2P:
  - Photocards : mercado público (listar / aceptar / cancelar)
  - Pokémon    : P2P directo (/ofrecerpoke) + gestión inline de ofertas

Prefijos de callback (todos < 64 bytes):
  itrd_*   → intercambio trade (este handler)

Acciones photocards:
  itrd_pcm   → mercado (pagina)
  itrd_pcmy  → mis listados
  itrd_pcl   → listar carta (confirmación)
  itrd_pccl  → confirmar listar
  itrd_pccan → cancelar listado
  itrd_pca   → elegir carta a dar (pagina)
  itrd_pcx   → ejecutar swap

Acciones pokémon:
  itrd_pkrv  → recibidos
  itrd_pkev  → enviados
  itrd_pka   → elegir pokémon a dar (pagina)
  itrd_pkx   → ejecutar swap
  itrd_pkrj  → rechazar oferta
  itrd_pkcc  → cancelar oferta propia

Acción común:
  itrd_close → cerrar menú
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import telebot
from telebot import types
import threading as _threading
import uuid     as _uuid
import time     as _time_mod

from database import db_manager
from funciones.photocards_service import photocards_service
from pokemon.services.intercambio_service import intercambio_service
from pokemon.services.pokemon_service import pokemon_service
from pokemon.services.pokedex_service import pokedex_service

logger = logging.getLogger(__name__)

# Configuración de paginación
_PC_LISTADOS_POR_PAG  = 5
_PC_CARTAS_POR_PAG    = 8
_PK_POKEMON_POR_PAG   = 5

RAREZA_EMOJI: Dict[str, str] = {"comun": "⚪", "rara": "🔵", "legendaria": "🟡"}


class IntercambioHandler:
    """Handler de intercambios P2P para photocards y pokémon."""

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        self._register()
        IntercambioHandler._instance = self

    def _register(self) -> None:
        self.bot.register_message_handler(self.cmd_intercambio,  commands=["intercambio"])
        self.bot.register_message_handler(self.cmd_ofrecerpoke,  commands=["ofrecerpoke"])
        self.bot.register_callback_query_handler(
            self.handle_callback,
            func=lambda c: c.data and c.data.startswith("itrd_"),
        )

    # ── helpers generales ─────────────────────────────────────────────────────

    def _answer(self, call: types.CallbackQuery, text: str = "", alert: bool = False) -> None:
        try:
            self.bot.answer_callback_query(call.id, text, show_alert=alert)
        except Exception:
            pass

    def _edit(
        self,
        call: types.CallbackQuery,
        texto: str,
        markup: Optional[types.InlineKeyboardMarkup] = None,
    ) -> None:
        try:
            self.bot.edit_message_text(
                texto,
                call.message.chat.id,
                call.message.message_id,
                parse_mode="HTML",
                reply_markup=markup,
            )
        except Exception as exc:
            logger.debug(f"_edit: {exc}")

    def _check_owner(self, call: types.CallbackQuery, owner_id: int) -> bool:
        if not call.from_user or call.from_user.id != owner_id:
            self._answer(call, "🚫 Este menú no es tuyo.", alert=True)
            return False
        return True

    def _notify(self, user_id: int, texto: str) -> None:
        """Envía una notificación privada silenciosa al usuario (no falla si bloqueado)."""
        try:
            self.bot.send_message(user_id, texto, parse_mode="HTML")
        except Exception as exc:
            logger.debug(f"_notify uid={user_id}: {exc}")

    # ── /intercambio ──────────────────────────────────────────────────────────

    def cmd_intercambio(self, message: types.Message) -> None:
        """Menú principal de intercambios."""
        if not message.from_user:
            return
        uid = message.from_user.id
        if not db_manager.user_exists(uid):
            self.bot.reply_to(message, "⚠️ Registrate primero con /registrar")
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🃏 Mercado Photocards",        callback_data=f"itrd_pcm:{uid}:0"),
            types.InlineKeyboardButton("📋 Mis listados",              callback_data=f"itrd_pcmy:{uid}"),
            types.InlineKeyboardButton("🐾 Intercambios Pokémon recibidos", callback_data=f"itrd_pkrv:{uid}"),
            types.InlineKeyboardButton("📤 Intercambios Pokémon enviados",  callback_data=f"itrd_pkev:{uid}"),
            types.InlineKeyboardButton("❌ Cerrar",                     callback_data=f"itrd_close:{uid}"),
        )
        self.bot.send_message(
            message.chat.id,
            "🔄 <b>Intercambios</b>\n\nElegí qué querés ver:",
            parse_mode="HTML",
            reply_markup=markup,
            message_thread_id=getattr(message, "message_thread_id", None),
        )

    # ── /ofrecerpoke <destinatario_id> <pokemon_id> ───────────────────────────

    def cmd_ofrecerpoke(self, message: types.Message) -> None:
        """
        Crea una oferta de intercambio Pokémon P2P.
        Uso: /ofrecerpoke <ID_Telegram_destinatario> <id_unico_pokemon>
        """
        if not message.from_user:
            return
        uid = message.from_user.id
        if not db_manager.user_exists(uid):
            self.bot.reply_to(message, "⚠️ Registrate primero con /registrar")
            return

        if message.text is None:
            return # Ignoramos el mensaje si no tiene texto
        partes = message.text.split()
        if len(partes) < 3:
            self.bot.reply_to(
                message,
                "❌ Uso: <code>/ofrecerpoke ID_destinatario ID_pokemon</code>\n"
                "Ejemplo: <code>/ofrecerpoke 123456789 42</code>",
                parse_mode="HTML",
            )
            return

        try:
            destinatario_id = int(partes[1])
            pokemon_id      = int(partes[2])
        except ValueError:
            self.bot.reply_to(message, "❌ Los IDs deben ser números enteros.")
            return

        if destinatario_id == uid:
            self.bot.reply_to(message, "❌ No podés ofrecerte un intercambio a vos mismo.")
            return

        exito, msg, intercambio_id = intercambio_service.crear_oferta(uid, pokemon_id, destinatario_id)
        self.bot.reply_to(message, msg, parse_mode="HTML")

        if exito and intercambio_id:
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton(
                    "👀 Ver oferta",
                    callback_data=f"itrd_pkrv:{destinatario_id}",
                )
            )
            self._notify(
                destinatario_id,
                f"📬 <b>¡Tenés una oferta de intercambio Pokémon!</b>\n\n"
                f"El usuario <code>{uid}</code> te quiere intercambiar un Pokémon.\n"
                f"Usá /intercambio para verla.",
            )

    # ── dispatch principal ────────────────────────────────────────────────────

    def handle_callback(self, call: types.CallbackQuery) -> None:
        """Enruta todos los callbacks con prefijo itrd_."""
        # Guard: call.data puede ser None en Telegram
        if not call.data:
            return
        # Guard: from_user puede ser None en mensajes de sistema
        if not call.from_user:
            return

        partes = call.data.split(":")
        accion = partes[0]
        try:
            uid = int(partes[1])
        except (IndexError, ValueError):
            return

        # Los callbacks de trade directo donde B es el owner usan uid de B,
        # pero el check_owner aplica igualmente.
        if not self._check_owner(call, uid):
            return

        try:
            # ── Trade directo PC ──────────────────────────────────────────────
            if accion == "itrd_pcd_inv":
                sid    = partes[2] if len(partes) > 2 else ""
                pagina = int(partes[3]) if len(partes) > 3 else 0
                self._pcd_show_inventario_b(call, uid, sid, pagina)

            elif accion == "itrd_pcd_sel":
                sid        = partes[2] if len(partes) > 2 else ""
                carta_b_id = int(partes[3]) if len(partes) > 3 else 0
                self._pcd_b_eligio_carta(call, uid, sid, carta_b_id)

            elif accion == "itrd_pcd_conf":
                sid    = partes[2] if len(partes) > 2 else ""
                answer = partes[3] if len(partes) > 3 else "no"
                self._pcd_confirmar(call, uid, sid, answer)

            elif accion == "itrd_pcd_rej":
                sid = partes[2] if len(partes) > 2 else ""
                self._pcd_rechazar(call, uid, sid)

            elif accion == "itrd_close":
                self._answer(call)
                try:
                    self.bot.delete_message(call.message.chat.id, call.message.message_id)
                except Exception:
                    pass

            # ── Photocards — mercado ──────────────────────────────────────────
            elif accion == "itrd_pcm":
                pagina = int(partes[2]) if len(partes) > 2 else 0
                self._show_pc_mercado(call, uid, pagina)

            elif accion == "itrd_pcmy":
                self._show_pc_mis_listados(call, uid)

            elif accion == "itrd_pcl":
                carta_id = int(partes[2]) if len(partes) > 2 else 0
                self._confirmar_listar_pc(call, uid, carta_id)

            elif accion == "itrd_pccl":
                carta_id = int(partes[2]) if len(partes) > 2 else 0
                self._ejecutar_listar_pc(call, uid, carta_id)

            elif accion == "itrd_pccan":
                listado_id = int(partes[2]) if len(partes) > 2 else 0
                self._cancelar_listado_pc(call, uid, listado_id)

            elif accion == "itrd_pca":
                listado_id = int(partes[2]) if len(partes) > 2 else 0
                pagina     = int(partes[3]) if len(partes) > 3 else 0
                self._show_pc_elegir_carta(call, uid, listado_id, pagina)

            elif accion == "itrd_pcx":
                listado_id  = int(partes[2]) if len(partes) > 2 else 0
                mi_carta_id = int(partes[3]) if len(partes) > 3 else 0
                self._ejecutar_trade_pc(call, uid, listado_id, mi_carta_id)

            # ── Pokémon ───────────────────────────────────────────────────────
            elif accion == "itrd_pkrv":
                self._show_pk_recibidos(call, uid)

            elif accion == "itrd_pkev":
                self._show_pk_enviados(call, uid)

            elif accion == "itrd_pka":
                interc_id = partes[2] if len(partes) > 2 else ""
                pagina    = int(partes[3]) if len(partes) > 3 else 0
                self._show_pk_elegir_pokemon(call, uid, interc_id, pagina)

            elif accion == "itrd_pkx":
                interc_id  = partes[2] if len(partes) > 2 else ""
                mi_poke_id = int(partes[3]) if len(partes) > 3 else 0
                self._ejecutar_trade_pk(call, uid, interc_id, mi_poke_id)

            elif accion == "itrd_pkrj":
                interc_id = partes[2] if len(partes) > 2 else ""
                self._rechazar_trade_pk(call, uid, interc_id)

            elif accion == "itrd_pkcc":
                interc_id = partes[2] if len(partes) > 2 else ""
                self._cancelar_trade_pk(call, uid, interc_id)

        except Exception as exc:
            logger.error(
                f"[INTERCAMBIO] handle_callback ({call.data}): {exc}", exc_info=True
            )
            self._answer(call, "❌ Error inesperado.", alert=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TRADE DIRECTO P2P DE PHOTOCARDS
    # ══════════════════════════════════════════════════════════════════════════
    #
    # Sesiones en memoria: _PC_DIRECT_SESSIONS[sid] = {
    #   oferente_id, receptor_id, carta_a_id, carta_b_id,
    #   conf_a, conf_b, msg_a_id, msg_b_id, chat_a_id, chat_b_id, ts
    # }
    # ══════════════════════════════════════════════════════════════════════════

    _PC_DIRECT_SESSIONS: dict = {}
    _PC_SESSION_TTL:     int  = 300   # 5 minutos
    _instance = None                  # referencia a la instancia activa

    # ── gestión de sesiones ───────────────────────────────────────────────────

    def _pcd_nueva_sesion(self, oferente_id: int, receptor_id: int, carta_a_id: int) -> str:
        """Crea sesión y programa su limpieza automática."""
        import uuid as _uuid, time as _time_mod, threading as _threading

        sid = _uuid.uuid4().hex[:12]
        IntercambioHandler._PC_DIRECT_SESSIONS[sid] = {
            "sid":          sid,
            "oferente_id":  oferente_id,
            "receptor_id":  receptor_id,
            "carta_a_id":   carta_a_id,
            "carta_b_id":   None,
            "conf_a":       False,
            "conf_b":       False,
            "msg_a_id":     None,
            "msg_b_id":     None,
            "chat_a_id":    None,
            "chat_b_id":    None,
            "ts":           _time_mod.time(),
        }

        def _limpiar():
            s = IntercambioHandler._PC_DIRECT_SESSIONS.pop(sid, None)
            if not s:
                return
            if s["conf_a"] and s["conf_b"]:
                return   # ya completado
            for cid_, mid_ in [(s["chat_a_id"], s["msg_a_id"]), (s["chat_b_id"], s["msg_b_id"])]:
                if cid_ and mid_:
                    try:
                        self.bot.edit_message_text(
                            "⌛ El intercambio expiró sin completarse.",
                            cid_, mid_, parse_mode="HTML",
                        )
                    except Exception:
                        pass

        t = _threading.Timer(self._PC_SESSION_TTL, _limpiar)
        t.daemon = True
        t.start()
        return sid

    def _pcd_get_sesion(self, sid: str):
        return IntercambioHandler._PC_DIRECT_SESSIONS.get(sid)

    def _pcd_cancelar_sesion(self, sid: str, motivo: str = "❌ Intercambio cancelado.") -> None:
        s = IntercambioHandler._PC_DIRECT_SESSIONS.pop(sid, None)
        if not s:
            return
        for cid_, mid_ in [(s["chat_a_id"], s["msg_a_id"]), (s["chat_b_id"], s["msg_b_id"])]:
            if cid_ and mid_:
                try:
                    self.bot.edit_message_text(motivo, cid_, mid_, parse_mode="HTML")
                except Exception:
                    pass

    # ── notificación a B ──────────────────────────────────────────────────────

    def _pcd_notificar_receptor(
        self,
        receptor_id: int,
        oferente_id: int,
        carta_a_id: int,
        sid: str,
        chat_id_a: int,
    ) -> None:
        """Envía propuesta a B (privado primero, fallback en el chat de A)."""
        pc_a  = photocards_service.get_carta_by_id(carta_a_id)
        nom_a = pc_a.nombre if pc_a else f"#{carta_a_id}"
        em_a  = RAREZA_EMOJI.get(pc_a.rareza if pc_a else "", "⚪")

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(
                "✅ Aceptar — elegir mi carta",
                callback_data=f"itrd_pcd_inv:{receptor_id}:{sid}:0",
            ),
            types.InlineKeyboardButton(
                "❌ Rechazar",
                callback_data=f"itrd_pcd_rej:{receptor_id}:{sid}",
            ),
        )
        texto = (
            f"📬 <b>¡Te proponen un intercambio de Photocard!</b>\n\n"
            f"El usuario <code>{oferente_id}</code> quiere intercambiarte:\n"
            f"{em_a} <b>{nom_a}</b>\n\n"
            f"Si aceptás, elegís qué carta ofrecés a cambio y ambos confirman.\n"
            f"<i>⌛ Expira en 5 minutos.</i>"
        )
        sent = None
        try:
            sent = self.bot.send_message(receptor_id, texto, parse_mode="HTML", reply_markup=markup)
        except Exception:
            try:
                sent = self.bot.send_message(chat_id_a, texto, parse_mode="HTML", reply_markup=markup)
            except Exception as exc:
                logger.error(f"[PCD] No se pudo notificar a {receptor_id}: {exc}")
                return

        if sent:
            s = self._pcd_get_sesion(sid)
            if s:
                s["msg_b_id"]  = sent.message_id
                s["chat_b_id"] = sent.chat.id

    # ── B abre su inventario ──────────────────────────────────────────────────

    def _pcd_show_inventario_b(
        self,
        call: types.CallbackQuery,
        uid: int,
        sid: str,
        pagina: int,
    ) -> None:
        self._answer(call)
        s = self._pcd_get_sesion(sid)
        if not s:
            self._edit(call, "⌛ Esta oferta ya expiró o fue cancelada.")
            return
        if uid != s["receptor_id"]:
            self._answer(call, "🚫 Este botón no es tuyo.", alert=True)
            return

        # Obtener inventario de B
        cartas: dict = {}
        try:
            rows = photocards_service.db.execute_query(
                "SELECT cartaID, SUM(cantidad) AS cant FROM INVENTARIOS WHERE userID = ? GROUP BY cartaID",
                (uid,),
            )
            for row in rows:
                r = {k.lower(): v for k, v in row.items()}
                if r.get("cant") and int(r["cant"]) > 0:
                    cartas[int(r["cartaid"])] = int(r["cant"])
        except Exception as exc:
            logger.error(f"[PCD] inventario B: {exc}", exc_info=True)

        markup = types.InlineKeyboardMarkup(row_width=1)
        if not cartas:
            markup.add(types.InlineKeyboardButton("❌ Rechazar oferta", callback_data=f"itrd_pcd_rej:{uid}:{sid}"))
            self._edit(call, "😔 No tenés photocards para ofrecer.", markup)
            return

        ids_ord    = sorted(cartas.keys())
        por_pag    = _PC_CARTAS_POR_PAG
        total_pags = max(1, (len(ids_ord) + por_pag - 1) // por_pag)
        pagina     = max(0, min(pagina, total_pags - 1))
        ids_pag    = ids_ord[pagina * por_pag:(pagina + 1) * por_pag]

        pc_a  = photocards_service.get_carta_by_id(s["carta_a_id"])
        nom_a = pc_a.nombre if pc_a else f"#{s['carta_a_id']}"
        em_a  = RAREZA_EMOJI.get(pc_a.rareza if pc_a else "", "⚪")

        for cid in ids_pag:
            pc    = photocards_service.get_carta_by_id(cid)
            emoji = RAREZA_EMOJI.get(pc.rareza, "⚪") if pc else "❓"
            nom   = pc.nombre if pc else f"#{cid}"
            markup.add(types.InlineKeyboardButton(
                f"{emoji} {nom} ×{cartas[cid]}",
                callback_data=f"itrd_pcd_sel:{uid}:{sid}:{cid}",
            ))

        nav = []
        if pagina > 0:
            nav.append(types.InlineKeyboardButton("⬅️", callback_data=f"itrd_pcd_inv:{uid}:{sid}:{pagina-1}"))
        if pagina < total_pags - 1:
            nav.append(types.InlineKeyboardButton("➡️", callback_data=f"itrd_pcd_inv:{uid}:{sid}:{pagina+1}"))
        if nav:
            markup.row(*nav)
        markup.add(types.InlineKeyboardButton("❌ Rechazar oferta", callback_data=f"itrd_pcd_rej:{uid}:{sid}"))

        s["msg_b_id"]  = s["msg_b_id"]  or call.message.message_id
        s["chat_b_id"] = s["chat_b_id"] or call.message.chat.id

        self._edit(
            call,
            f"🔄 <b>Oferta de intercambio</b>\n\n"
            f"Te ofrecen: {em_a} <b>{nom_a}</b>\n\n"
            f"Pág. {pagina+1}/{total_pags} — elegí qué carta das a cambio:",
            markup,
        )

    # ── B eligió su carta → mostrar confirmación a ambos ─────────────────────

    def _pcd_b_eligio_carta(
        self,
        call: types.CallbackQuery,
        uid: int,
        sid: str,
        carta_b_id: int,
    ) -> None:
        self._answer(call)
        s = self._pcd_get_sesion(sid)
        if not s:
            self._edit(call, "⌛ Esta oferta ya expiró.")
            return
        if uid != s["receptor_id"]:
            self._answer(call, "🚫 Este botón no es tuyo.", alert=True)
            return
        if photocards_service.get_cantidad_carta(uid, carta_b_id) < 1:
            self._edit(call, "❌ Ya no tenés esa carta.")
            return

        s["carta_b_id"] = carta_b_id
        s["msg_b_id"]   = call.message.message_id
        s["chat_b_id"]  = call.message.chat.id

        pc_a  = photocards_service.get_carta_by_id(s["carta_a_id"])
        pc_b  = photocards_service.get_carta_by_id(carta_b_id)
        nom_a = pc_a.nombre if pc_a else f"#{s['carta_a_id']}"
        nom_b = pc_b.nombre if pc_b else f"#{carta_b_id}"
        em_a  = RAREZA_EMOJI.get(pc_a.rareza if pc_a else "", "⚪")
        em_b  = RAREZA_EMOJI.get(pc_b.rareza if pc_b else "", "⚪")

        # Panel de B
        mk_b = types.InlineKeyboardMarkup(row_width=2)
        mk_b.add(
            types.InlineKeyboardButton("✅ Confirmar", callback_data=f"itrd_pcd_conf:{uid}:{sid}:yes"),
            types.InlineKeyboardButton("❌ Cancelar",  callback_data=f"itrd_pcd_conf:{uid}:{sid}:no"),
        )
        self._edit(
            call,
            f"🔄 <b>Confirmación de intercambio</b>\n\n"
            f"📤 Vos das:     {em_b} <b>{nom_b}</b>\n"
            f"📥 Vos recibís: {em_a} <b>{nom_a}</b>\n\n"
            f"¿Confirmás?",
            mk_b,
        )

        # Panel de A
        mk_a = types.InlineKeyboardMarkup(row_width=2)
        mk_a.add(
            types.InlineKeyboardButton("✅ Confirmar", callback_data=f"itrd_pcd_conf:{s['oferente_id']}:{sid}:yes"),
            types.InlineKeyboardButton("❌ Cancelar",  callback_data=f"itrd_pcd_conf:{s['oferente_id']}:{sid}:no"),
        )
        resumen_a = (
            f"🔄 <b>Confirmación de intercambio</b>\n\n"
            f"📤 Vos das:     {em_a} <b>{nom_a}</b>\n"
            f"📥 Vos recibís: {em_b} <b>{nom_b}</b>\n\n"
            f"¿Confirmás?"
        )
        try:
            chat_a = s.get("chat_a_id")
            msg_a  = s.get("msg_a_id")
            if chat_a and msg_a:
                self.bot.edit_message_text(
                    resumen_a, int(chat_a), int(msg_a),
                    parse_mode="HTML", reply_markup=mk_a,
                )
            else:
                m = self.bot.send_message(
                    s["oferente_id"], resumen_a,
                    parse_mode="HTML", reply_markup=mk_a,
                )
                s["chat_a_id"] = m.chat.id
                s["msg_a_id"]  = m.message_id
        except Exception as exc:
            logger.error(f"[PCD] notificar A en confirmación: {exc}")

    # ── confirmación individual ───────────────────────────────────────────────

    def _pcd_confirmar(
        self,
        call: types.CallbackQuery,
        uid: int,
        sid: str,
        answer: str,
    ) -> None:
        self._answer(call)
        s = self._pcd_get_sesion(sid)
        if not s:
            self._edit(call, "⌛ Este intercambio ya expiró o fue procesado.")
            return
        if uid not in (s["oferente_id"], s["receptor_id"]):
            self._answer(call, "🚫 No sos parte de este intercambio.", alert=True)
            return

        if answer == "no":
            self._pcd_cancelar_sesion(sid, "❌ Intercambio cancelado por uno de los participantes.")
            return

        # Marcar confirmación
        if uid == s["oferente_id"]:
            s["conf_a"] = True
        else:
            s["conf_b"] = True

        self._edit(call, "⏳ Confirmado. Esperando al otro usuario...")

        # ── Ambos confirmaron → ejecutar swap ─────────────────────────────────
        if s["conf_a"] and s["conf_b"]:
            IntercambioHandler._PC_DIRECT_SESSIONS.pop(s["sid"], None)
            exito, msg = photocards_service.ejecutar_swap_directo(
                oferente_id = s["oferente_id"],
                carta_a_id  = s["carta_a_id"],
                receptor_id = s["receptor_id"],
                carta_b_id  = s["carta_b_id"],
            )
            resultado = msg if exito else f"❌ Error: {msg}"
            for cid_, mid_ in [(s["chat_a_id"], s["msg_a_id"]), (s["chat_b_id"], s["msg_b_id"])]:
                if cid_ and mid_:
                    try:
                        self.bot.edit_message_text(resultado, cid_, mid_, parse_mode="HTML")
                    except Exception:
                        pass
            if not exito:
                logger.error(f"[PCD] swap directo falló: {msg}")

    # ── B rechaza ─────────────────────────────────────────────────────────────

    def _pcd_rechazar(self, call: types.CallbackQuery, uid: int, sid: str) -> None:
        self._answer(call)
        if sid == "__none__":
            # El que inició canceló antes de que nadie respondiera
            try:
                self.bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass
            return
        s = self._pcd_get_sesion(sid)
        if not s:
            self._edit(call, "⌛ Esta oferta ya no está activa.")
            return
        if uid not in (s["receptor_id"], s["oferente_id"]):
            self._answer(call, "🚫 Este botón no es tuyo.", alert=True)
            return
        self._pcd_cancelar_sesion(sid, "❌ El intercambio fue rechazado.")

    # ══════════════════════════════════════════════════════════════════════════
    # PHOTOCARDS — flujo de mercado
    # ══════════════════════════════════════════════════════════════════════════

    def _confirmar_listar_pc(self, call: types.CallbackQuery, uid: int, carta_id: int) -> None:
        """Muestra confirmación antes de listar la carta."""
        self._answer(call)
        pc    = photocards_service.get_carta_by_id(carta_id)
        if pc is None:
            self._edit(call, "❌ Carta no encontrada.")
            return
        emoji = RAREZA_EMOJI.get(pc.rareza, "⚪")
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ Listar",   callback_data=f"itrd_pccl:{uid}:{carta_id}"),
            types.InlineKeyboardButton("❌ Cancelar", callback_data=f"itrd_pcm:{uid}:0"),
        )
        self._edit(
            call,
            f"🔄 <b>Listar para intercambio</b>\n\n"
            f"{emoji} <b>{pc.nombre}</b> — {pc.rareza.capitalize()}\n\n"
            f"Tu carta aparecerá en el mercado público y otros usuarios "
            f"podrán ofrecerte algo a cambio.",
            markup,
        )

    def _ejecutar_listar_pc(self, call: types.CallbackQuery, uid: int, carta_id: int) -> None:
        """Persiste el listado y muestra resultado."""
        self._answer(call)
        exito, msg = photocards_service.listar_photocard_para_intercambio(uid, carta_id)
        markup = types.InlineKeyboardMarkup(row_width=1)
        if exito:
            markup.add(types.InlineKeyboardButton("🏪 Ver mercado", callback_data=f"itrd_pcm:{uid}:0"))
        markup.add(types.InlineKeyboardButton("📋 Mis listados", callback_data=f"itrd_pcmy:{uid}"))
        self._edit(call, msg, markup)

    def _show_pc_mercado(self, call: types.CallbackQuery, uid: int, pagina: int) -> None:
        """Muestra los listados disponibles de otros usuarios (paginado)."""
        self._answer(call)
        listados = photocards_service.obtener_mercado_photocards(uid)
        markup   = types.InlineKeyboardMarkup(row_width=1)

        if not listados:
            markup.add(types.InlineKeyboardButton("❌ Cerrar", callback_data=f"itrd_close:{uid}"))
            self._edit(
                call,
                "🏪 <b>Mercado de Photocards</b>\n\nNo hay cartas listadas para intercambio.",
                markup,
            )
            return

        total_pags = max(1, (len(listados) + _PC_LISTADOS_POR_PAG - 1) // _PC_LISTADOS_POR_PAG)
        pagina     = max(0, min(pagina, total_pags - 1))
        en_pagina  = listados[pagina * _PC_LISTADOS_POR_PAG:(pagina + 1) * _PC_LISTADOS_POR_PAG]

        lineas: List[str] = []
        for entry in en_pagina:
            pc     = photocards_service.get_carta_by_id(entry["carta_ofrecida"])
            emoji  = RAREZA_EMOJI.get(pc.rareza, "⚪") if pc else "❓"
            nombre = pc.nombre if pc else f"#{entry['carta_ofrecida']}"
            sol    = ""
            if entry.get("carta_solicitada"):
                pc_sol = photocards_service.get_carta_by_id(entry["carta_solicitada"])
                sol    = f" (pide: {pc_sol.nombre if pc_sol else '?'})"
            lineas.append(f"{emoji} <b>{nombre}</b>{sol}")
            markup.add(
                types.InlineKeyboardButton(
                    f"🔄 {emoji} {nombre}",
                    callback_data=f"itrd_pca:{uid}:{entry['id']}:0",
                )
            )

        nav: List[types.InlineKeyboardButton] = []
        if pagina > 0:
            nav.append(types.InlineKeyboardButton("⬅️", callback_data=f"itrd_pcm:{uid}:{pagina - 1}"))
        if pagina < total_pags - 1:
            nav.append(types.InlineKeyboardButton("➡️", callback_data=f"itrd_pcm:{uid}:{pagina + 1}"))
        if nav:
            markup.row(*nav)
        markup.add(types.InlineKeyboardButton("❌ Cerrar", callback_data=f"itrd_close:{uid}"))

        self._edit(
            call,
            f"🏪 <b>Mercado de Photocards</b> — Pág. {pagina + 1}/{total_pags}\n\n"
            + "\n".join(lineas)
            + "\n\nTocá una carta para ofrecer algo a cambio:",
            markup,
        )

    def _show_pc_mis_listados(self, call: types.CallbackQuery, uid: int) -> None:
        """Lista las cartas que el usuario tiene actualmente en el mercado."""
        self._answer(call)
        listados = photocards_service.obtener_mis_listados_photocards(uid)
        markup   = types.InlineKeyboardMarkup(row_width=1)

        if not listados:
            markup.add(types.InlineKeyboardButton("❌ Cerrar", callback_data=f"itrd_close:{uid}"))
            self._edit(
                call,
                "📋 <b>Mis listados</b>\n\nNo tenés cartas listadas en el mercado.",
                markup,
            )
            return

        for entry in listados:
            pc     = photocards_service.get_carta_by_id(entry["carta_ofrecida"])
            emoji  = RAREZA_EMOJI.get(pc.rareza, "⚪") if pc else "❓"
            nombre = pc.nombre if pc else f"#{entry['carta_ofrecida']}"
            markup.add(
                types.InlineKeyboardButton(
                    f"❌ Quitar: {emoji} {nombre}",
                    callback_data=f"itrd_pccan:{uid}:{entry['id']}",
                )
            )
        markup.add(types.InlineKeyboardButton("❌ Cerrar", callback_data=f"itrd_close:{uid}"))
        self._edit(
            call,
            "📋 <b>Mis listados activos</b>\n\nTocá para retirar un listado:",
            markup,
        )

    def _cancelar_listado_pc(self, call: types.CallbackQuery, uid: int, listado_id: int) -> None:
        """Retira un listado del mercado."""
        self._answer(call)
        exito, msg = photocards_service.cancelar_listado_photocard(uid, listado_id)
        markup     = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("📋 Mis listados", callback_data=f"itrd_pcmy:{uid}"))
        self._edit(call, msg, markup)

    def _show_pc_elegir_carta(
        self,
        call: types.CallbackQuery,
        uid: int,
        listado_id: int,
        pagina: int,
    ) -> None:
        """
        Muestra la colección del usuario para que elija qué carta entregar
        a cambio del listado. Si el listado especificó una carta concreta,
        va directo a la confirmación sin mostrar la colección.
        """
        self._answer(call)
        markup = types.InlineKeyboardMarkup(row_width=1)

        # Verificar que el listado sigue activo
        listados = photocards_service.obtener_mercado_photocards(uid)
        entry    = next((l for l in listados if l["id"] == listado_id), None)
        if entry is None:
            markup.add(types.InlineKeyboardButton("⬅️ Volver", callback_data=f"itrd_pcm:{uid}:0"))
            self._edit(call, "❌ Ese listado ya no está disponible.", markup)
            return

        pc_ofrecida     = photocards_service.get_carta_by_id(entry["carta_ofrecida"])
        nombre_ofrecida = pc_ofrecida.nombre if pc_ofrecida else f"#{entry['carta_ofrecida']}"
        emoji_ofrecida  = RAREZA_EMOJI.get(pc_ofrecida.rareza, "⚪") if pc_ofrecida else "❓"

        # ── Oferta con carta específica: confirmación directa ─────────────────
        if entry.get("carta_solicitada"):
            cid_sol = int(entry["carta_solicitada"])
            if photocards_service.get_cantidad_carta(uid, cid_sol) < 1:
                pc_sol     = photocards_service.get_carta_by_id(cid_sol)
                nombre_sol = pc_sol.nombre if pc_sol else f"#{cid_sol}"
                markup.add(types.InlineKeyboardButton("⬅️ Volver", callback_data=f"itrd_pcm:{uid}:0"))
                self._edit(
                    call,
                    f"❌ Esta oferta requiere <b>{nombre_sol}</b> y no la tenés.",
                    markup,
                )
                return
            pc_sol     = photocards_service.get_carta_by_id(cid_sol)
            nombre_sol = pc_sol.nombre if pc_sol else f"#{cid_sol}"
            emoji_sol  = RAREZA_EMOJI.get(pc_sol.rareza, "⚪") if pc_sol else "⚪"
            markup.add(
                types.InlineKeyboardButton(
                    "✅ Confirmar intercambio",
                    callback_data=f"itrd_pcx:{uid}:{listado_id}:{cid_sol}",
                ),
                types.InlineKeyboardButton("❌ Cancelar", callback_data=f"itrd_pcm:{uid}:0"),
            )
            self._edit(
                call,
                f"🔄 <b>Confirmar intercambio</b>\n\n"
                f"Das: {emoji_sol} <b>{nombre_sol}</b>\n"
                f"Recibís: {emoji_ofrecida} <b>{nombre_ofrecida}</b>",
                markup,
            )
            return

        # ── Oferta abierta: mostrar colección del usuario ─────────────────────
        cartas_usuario: Dict[int, int] = {}
        for album in photocards_service.get_albums_usuario(uid):
            cartas_usuario.update(photocards_service.get_cartas_usuario_en_album(uid, album))

        if not cartas_usuario:
            markup.add(types.InlineKeyboardButton("⬅️ Volver", callback_data=f"itrd_pcm:{uid}:0"))
            self._edit(call, "❌ No tenés photocards para ofrecer.", markup)
            return

        ids_disponibles = sorted(cartas_usuario.keys())
        total_pags      = max(1, (len(ids_disponibles) + _PC_CARTAS_POR_PAG - 1) // _PC_CARTAS_POR_PAG)
        pagina          = max(0, min(pagina, total_pags - 1))
        ids_pag         = ids_disponibles[pagina * _PC_CARTAS_POR_PAG:(pagina + 1) * _PC_CARTAS_POR_PAG]

        for cid in ids_pag:
            pc     = photocards_service.get_carta_by_id(cid)
            emoji  = RAREZA_EMOJI.get(pc.rareza, "⚪") if pc else "❓"
            nombre = pc.nombre if pc else f"#{cid}"
            markup.add(
                types.InlineKeyboardButton(
                    f"{emoji} {nombre} ×{cartas_usuario[cid]}",
                    callback_data=f"itrd_pcx:{uid}:{listado_id}:{cid}",
                )
            )

        nav: List[types.InlineKeyboardButton] = []
        if pagina > 0:
            nav.append(types.InlineKeyboardButton("⬅️", callback_data=f"itrd_pca:{uid}:{listado_id}:{pagina - 1}"))
        if pagina < total_pags - 1:
            nav.append(types.InlineKeyboardButton("➡️", callback_data=f"itrd_pca:{uid}:{listado_id}:{pagina + 1}"))
        if nav:
            markup.row(*nav)
        markup.add(types.InlineKeyboardButton("❌ Cancelar", callback_data=f"itrd_pcm:{uid}:0"))

        self._edit(
            call,
            f"🔄 <b>Elegí qué carta ofrecés a cambio</b>\n\n"
            f"Recibís: {emoji_ofrecida} <b>{nombre_ofrecida}</b>\n\n"
            f"Pág. {pagina + 1}/{total_pags} — tocá la carta que das:",
            markup,
        )

    def _ejecutar_trade_pc(
        self,
        call: types.CallbackQuery,
        uid: int,
        listado_id: int,
        mi_carta_id: int,
    ) -> None:
        """Finaliza el intercambio de photocards y notifica al ofertante."""
        self._answer(call)
        exito, msg = photocards_service.aceptar_listado_photocard(listado_id, uid, mi_carta_id)
        markup     = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("🏪 Ver mercado", callback_data=f"itrd_pcm:{uid}:0"))
        self._edit(call, msg, markup)

        if exito:
            # Recuperar datos del ofertante para notificarlo
            try:
                filas = photocards_service.db.execute_query(
                    "SELECT ofertante_id, carta_ofrecida FROM INTERCAMBIOS_PHOTOCARDS WHERE id = ?",
                    (listado_id,),
                )
                if filas:
                    r            = {k.lower(): v for k, v in filas[0].items()}
                    ofertante_id = int(r["ofertante_id"])
                    pc_ofrecida  = photocards_service.get_carta_by_id(int(r["carta_ofrecida"]))
                    nombre_pc    = pc_ofrecida.nombre if pc_ofrecida else f"#{r['carta_ofrecida']}"
                    self._notify(
                        ofertante_id,
                        f"🎉 <b>¡Tu listado de intercambio fue aceptado!</b>\n\n"
                        f"Tu carta <b>{nombre_pc}</b> fue intercambiada.\n"
                        f"Revisá tu colección con /menu.",
                    )
            except Exception as exc:
                logger.warning(f"[INTERCAMBIO PC] No se pudo notificar al ofertante: {exc}")

    # ══════════════════════════════════════════════════════════════════════════
    # POKÉMON — flujo P2P
    # ══════════════════════════════════════════════════════════════════════════

    def _show_pk_recibidos(self, call: types.CallbackQuery, uid: int) -> None:
        """Muestra las ofertas de intercambio pokémon recibidas y pendientes."""
        self._answer(call)
        ofertas = intercambio_service.obtener_ofertas_recibidas(uid)
        markup  = types.InlineKeyboardMarkup(row_width=1)

        if not ofertas:
            markup.add(types.InlineKeyboardButton("❌ Cerrar", callback_data=f"itrd_close:{uid}"))
            self._edit(call, "📭 <b>Intercambios recibidos</b>\n\nNo tenés ofertas pendientes.", markup)
            return

        lineas = [f"📬 <b>{len(ofertas)} oferta(s) pendiente(s):</b>\n"]
        for oferta in ofertas[:5]:
            o         = oferta if isinstance(oferta, dict) else dict(oferta)
            poke_id   = o.get("pokemon_ofrecido_id")
            ofert_uid = o.get("ofertante_id")
            iid       = o.get("intercambio_id", "")
            nombre_p, nivel_p = self._nombre_nivel_pokemon(poke_id)
            lineas.append(f"• <code>{ofert_uid}</code> → <b>{nombre_p}</b> Nv.{nivel_p}")
            markup.add(
                types.InlineKeyboardButton(
                    f"✅ Aceptar — {nombre_p}",
                    callback_data=f"itrd_pka:{uid}:{iid}:0",
                ),
                types.InlineKeyboardButton(
                    f"❌ Rechazar — {nombre_p}",
                    callback_data=f"itrd_pkrj:{uid}:{iid}",
                ),
            )

        markup.add(types.InlineKeyboardButton("❌ Cerrar", callback_data=f"itrd_close:{uid}"))
        self._edit(call, "\n".join(lineas), markup)

    def _show_pk_enviados(self, call: types.CallbackQuery, uid: int) -> None:
        """Muestra las ofertas de intercambio pokémon enviadas y pendientes."""
        self._answer(call)
        ofertas = intercambio_service.obtener_ofertas_enviadas(uid)
        markup  = types.InlineKeyboardMarkup(row_width=1)

        if not ofertas:
            markup.add(types.InlineKeyboardButton("❌ Cerrar", callback_data=f"itrd_close:{uid}"))
            self._edit(call, "📭 <b>Intercambios enviados</b>\n\nNo tenés ofertas pendientes.", markup)
            return

        lineas = [f"📤 <b>{len(ofertas)} oferta(s) enviada(s):</b>\n"]
        for oferta in ofertas[:5]:
            o       = oferta if isinstance(oferta, dict) else dict(oferta)
            poke_id = o.get("pokemon_ofrecido_id")
            dest    = o.get("destinatario_id")
            iid     = o.get("intercambio_id", "")
            nombre_p, nivel_p = self._nombre_nivel_pokemon(poke_id)
            lineas.append(f"• Para <code>{dest}</code>: <b>{nombre_p}</b> Nv.{nivel_p}")
            markup.add(
                types.InlineKeyboardButton(
                    f"🚫 Cancelar — {nombre_p}",
                    callback_data=f"itrd_pkcc:{uid}:{iid}",
                )
            )

        markup.add(types.InlineKeyboardButton("❌ Cerrar", callback_data=f"itrd_close:{uid}"))
        self._edit(call, "\n".join(lineas), markup)

    def _show_pk_elegir_pokemon(
        self,
        call: types.CallbackQuery,
        uid: int,
        intercambio_id: str,
        pagina: int,
    ) -> None:
        """
        Muestra los pokémon disponibles del usuario (equipo + PC) para elegir
        cuál da a cambio. Excluye los que están en el equipo activo, ya que
        intercambio_service los bloquea por diseño.
        """
        self._answer(call)
        markup = types.InlineKeyboardMarkup(row_width=1)

        # Verificar que la oferta sigue activa y es para este usuario
        oferta = self._buscar_oferta_recibida(uid, intercambio_id)
        if oferta is None:
            markup.add(types.InlineKeyboardButton("⬅️ Volver", callback_data=f"itrd_pkrv:{uid}"))
            self._edit(call, "❌ Oferta no encontrada o ya no disponible.", markup)
            return

        poke_id       = oferta.get("pokemon_ofrecido_id")
        solicitado_id = oferta.get("pokemon_solicitado_id")
        nombre_p, nivel_p = self._nombre_nivel_pokemon(poke_id)

        # ── Oferta con pokémon específico: ir directo a confirmación ──────────
        if solicitado_id:
            markup.add(
                types.InlineKeyboardButton(
                    "✅ Confirmar intercambio",
                    callback_data=f"itrd_pkx:{uid}:{intercambio_id}:{solicitado_id}",
                ),
                types.InlineKeyboardButton(
                    "❌ Rechazar",
                    callback_data=f"itrd_pkrj:{uid}:{intercambio_id}",
                ),
            )
            nombre_sol, nivel_sol = self._nombre_nivel_pokemon(solicitado_id)
            self._edit(
                call,
                f"🔄 <b>Confirmar intercambio Pokémon</b>\n\n"
                f"Das: <b>{nombre_sol}</b> Nv.{nivel_sol}\n"
                f"Recibís: <b>{nombre_p}</b> Nv.{nivel_p}",
                markup,
            )
            return

        # ── Oferta abierta: mostrar pokémon fuera del equipo ─────────────────
        try:
            disponibles = pokemon_service.obtener_pc(uid, offset=0, limit=100)
        except Exception as exc:
            logger.warning(f"[INTERCAMBIO PK] obtener_pc: {exc}")
            disponibles = []

        if not disponibles:
            markup.add(types.InlineKeyboardButton("⬅️ Volver", callback_data=f"itrd_pkrv:{uid}"))
            self._edit(
                call,
                "❌ No tenés Pokémon disponibles para intercambiar (los del equipo no se pueden ofrecer).",
                markup,
            )
            return

        total_pags  = max(1, (len(disponibles) + _PK_POKEMON_POR_PAG - 1) // _PK_POKEMON_POR_PAG)
        pagina      = max(0, min(pagina, total_pags - 1))
        pag_pokemon = disponibles[pagina * _PK_POKEMON_POR_PAG:(pagina + 1) * _PK_POKEMON_POR_PAG]

        for p in pag_pokemon:
            nombre_pk, _ = self._nombre_nivel_pokemon(p.id_unico, from_id_unico=True)
            markup.add(
                types.InlineKeyboardButton(
                    f"{nombre_pk} Nv.{p.nivel}",
                    callback_data=f"itrd_pkx:{uid}:{intercambio_id}:{p.id_unico}",
                )
            )

        nav: List[types.InlineKeyboardButton] = []
        if pagina > 0:
            nav.append(types.InlineKeyboardButton("⬅️", callback_data=f"itrd_pka:{uid}:{intercambio_id}:{pagina - 1}"))
        if pagina < total_pags - 1:
            nav.append(types.InlineKeyboardButton("➡️", callback_data=f"itrd_pka:{uid}:{intercambio_id}:{pagina + 1}"))
        if nav:
            markup.row(*nav)
        markup.add(types.InlineKeyboardButton("❌ Cancelar", callback_data=f"itrd_pkrv:{uid}"))

        self._edit(
            call,
            f"🔄 <b>Elegí qué Pokémon ofrecés</b>\n\n"
            f"Recibís: <b>{nombre_p}</b> Nv.{nivel_p}\n\n"
            f"Pág. {pagina + 1}/{total_pags} — Pokémon en el PC:",
            markup,
        )

    def _ejecutar_trade_pk(
        self,
        call: types.CallbackQuery,
        uid: int,
        intercambio_id: str,
        mi_pokemon_id: int,
    ) -> None:
        """Finaliza el intercambio de pokémon y notifica al ofertante."""
        self._answer(call)
        exito, msg = intercambio_service.aceptar_intercambio(intercambio_id, uid, mi_pokemon_id)
        markup     = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("⬅️ Ver recibidos", callback_data=f"itrd_pkrv:{uid}"))
        self._edit(call, msg, markup)

        if exito:
            try:
                rows = intercambio_service.db.execute_query(
                    "SELECT ofertante_id FROM INTERCAMBIOS WHERE intercambio_id = ?",
                    (intercambio_id,),
                )
                if rows:
                    r = {k.lower(): v for k, v in rows[0].items()}
                    self._notify(
                        int(r["ofertante_id"]),
                        "🎉 <b>¡Tu oferta de intercambio Pokémon fue aceptada!</b>\n\n"
                        "El intercambio se completó. Revisá tu equipo con /pokemon.",
                    )
            except Exception as exc:
                logger.warning(f"[INTERCAMBIO PK] No se pudo notificar al ofertante: {exc}")

    def _rechazar_trade_pk(self, call: types.CallbackQuery, uid: int, intercambio_id: str) -> None:
        """Rechaza una oferta recibida y notifica al ofertante."""
        self._answer(call)
        exito, msg = intercambio_service.rechazar_intercambio(intercambio_id, uid)
        markup     = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("⬅️ Ver recibidos", callback_data=f"itrd_pkrv:{uid}"))
        self._edit(call, msg, markup)

        if exito:
            try:
                rows = intercambio_service.db.execute_query(
                    "SELECT ofertante_id FROM INTERCAMBIOS WHERE intercambio_id = ?",
                    (intercambio_id,),
                )
                if rows:
                    r = {k.lower(): v for k, v in rows[0].items()}
                    self._notify(
                        int(r["ofertante_id"]),
                        "❌ <b>Tu oferta de intercambio Pokémon fue rechazada.</b>",
                    )
            except Exception as exc:
                logger.warning(f"[INTERCAMBIO PK] No se pudo notificar: {exc}")

    def _cancelar_trade_pk(self, call: types.CallbackQuery, uid: int, intercambio_id: str) -> None:
        """Cancela una oferta enviada por el propio usuario."""
        self._answer(call)
        exito, msg = intercambio_service.cancelar_intercambio(intercambio_id, uid)
        markup     = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("⬅️ Ver enviados", callback_data=f"itrd_pkev:{uid}"))
        self._edit(call, msg, markup)

    # ── utilidades internas ───────────────────────────────────────────────────

    def _nombre_nivel_pokemon(
        self,
        pokemon_id: Optional[int],
        from_id_unico: bool = False,
    ) -> tuple[str, str]:
        """
        Devuelve (nombre_especie, nivel) de un pokémon dado su id_unico o pokemonID.
        Maneja excepciones internamente y devuelve valores de fallback.

        Args:
            pokemon_id:    id_unico del pokémon en POKEMON_USUARIO.
            from_id_unico: Si True, se asume que pokemon_id es id_unico y se
                           consulta la especie a través de pokemon_service.
        """
        if pokemon_id is None:
            return "Desconocido", "?"
        try:
            poke   = pokemon_service.obtener_pokemon(pokemon_id)
            if poke is None:
                return f"#{pokemon_id}", "?"
            nombre = pokedex_service.obtener_nombre(poke.pokemonID)
            nivel  = str(poke.nivel)
            return nombre, nivel
        except Exception:
            return f"#{pokemon_id}", "?"

    def _buscar_oferta_recibida(
        self,
        uid: int,
        intercambio_id: str,
    ) -> Optional[Dict]:
        """
        Busca una oferta pendiente por intercambio_id entre las del usuario.
        Retorna el dict de la oferta o None si no existe / ya no está disponible.
        """
        try:
            ofertas = intercambio_service.obtener_ofertas_recibidas(uid)
            return next(
                (
                    (o if isinstance(o, dict) else dict(o))
                    for o in ofertas
                    if (o if isinstance(o, dict) else dict(o)).get("intercambio_id") == intercambio_id
                ),
                None,
            )
        except Exception:
            return None

# ─────────────────────────────────────────────────────────────────────────────
# Función de módulo — punto de entrada desde photocards_handlers
# ─────────────────────────────────────────────────────────────────────────────

def _pc_direct_iniciar_oferta(bot, call, oferente_id: int, carta_id: int, pc, emoji: str) -> None:
    """
    Lanzada por PhotocardsHandlers._intercambiar.

    Muestra a A el mensaje "¿con quién querés intercambiar?" y registra
    un listener de un único mensaje para capturar la mención.
    """
    import threading as _threading

    nom   = pc.nombre if pc else f"#{carta_id}"
    texto = (
        f"🔄 <b>Intercambio directo — {emoji} {nom}</b>\n\n"
        f"Respondé este mensaje <b>mencionando</b> al usuario con quien\n"
        f"querés intercambiar (etiquetalo con @ o hacé reply a su mensaje).\n\n"
        f"<i>Tenés 60 segundos para responder.</i>"
    )
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton(
        "❌ Cancelar",
        callback_data=f"itrd_pcd_rej:{oferente_id}:__none__",
    ))

    chat_id   = call.message.chat.id
    thread_id = getattr(call.message, "message_thread_id", None)

    try:
        bot.edit_message_text(
            texto, chat_id, call.message.message_id,
            parse_mode="HTML", reply_markup=mk,
        )
        msg_a_id = call.message.message_id
    except Exception:
        m = bot.send_message(chat_id, texto, parse_mode="HTML",
                             reply_markup=mk, message_thread_id=thread_id)
        msg_a_id = m.message_id

    _stop = _threading.Event()

    def _listener(message):
        if _stop.is_set():
            return
        if message.from_user.id != oferente_id:
            return
        if message.chat.id != chat_id:
            return
        _stop.set()

        try:
            bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass

        receptor_id     = None
        receptor_nombre = "el otro usuario"

        # ── Resolver receptor ──────────────────────────────────────────────
        # 1. entity mention (@username)
        if message.entities:
            for e in message.entities:
                if e.type == "mention" and message.text:
                    username = message.text[e.offset + 1: e.offset + e.length]
                    try:
                        from database import db_manager as _db
                        rows = _db.execute_query(
                            "SELECT userID, nombre FROM USUARIOS WHERE nombre_usuario = ?",
                            (username,),
                        )
                        if rows:
                            receptor_id     = int(rows[0]["userID"])
                            receptor_nombre = rows[0].get("nombre") or username
                    except Exception:
                        pass
                elif e.type == "text_mention" and e.user:
                    receptor_id     = e.user.id
                    receptor_nombre = e.user.first_name or str(e.user.id)

        # 2. reply al mensaje del receptor
        if not receptor_id and message.reply_to_message:
            u = message.reply_to_message.from_user
            if u and u.id != bot.get_me().id:
                receptor_id     = u.id
                receptor_nombre = u.first_name or str(u.id)

        # 3. número puro (ID directo)
        if not receptor_id:
            try:
                receptor_id     = int((message.text or "").strip())
                receptor_nombre = str(receptor_id)
            except (ValueError, TypeError):
                pass

        if not receptor_id:
            try:
                bot.edit_message_text(
                    "❌ No pude identificar al usuario.\n"
                    "Mencionalo con @ o hacé reply a su mensaje.",
                    chat_id, msg_a_id, parse_mode="HTML",
                )
            except Exception:
                pass
            return

        if receptor_id == oferente_id:
            try:
                bot.edit_message_text(
                    "❌ No podés intercambiar con vos mismo.",
                    chat_id, msg_a_id, parse_mode="HTML",
                )
            except Exception:
                pass
            return

        # ── Obtener instancia del handler y crear sesión ───────────────────
        handler = IntercambioHandler._instance
        if not handler:
            logger.error("[PCD] IntercambioHandler._instance es None")
            return

        sid = handler._pcd_nueva_sesion(oferente_id, receptor_id, carta_id)
        s   = handler._pcd_get_sesion(sid)
        if s is None:
            logger.error(f"[PCD] Sesión {sid} no encontrada tras crearla")
            return
        s["chat_a_id"] = chat_id
        s["msg_a_id"]  = msg_a_id

        try:
            bot.edit_message_text(
                f"⏳ Oferta enviada a <b>{receptor_nombre}</b>.\n"
                f"Esperando que acepte y elija su carta...\n"
                f"<i>⌛ Expira en 5 minutos.</i>",
                chat_id, msg_a_id, parse_mode="HTML",
            )
        except Exception:
            pass

        handler._pcd_notificar_receptor(receptor_id, oferente_id, carta_id, sid, chat_id)

    # ── Timeout del listener ───────────────────────────────────────────────
    def _timeout():
        if not _stop.is_set():
            _stop.set()
            try:
                bot.edit_message_text(
                    "⌛ Tiempo agotado. Volvé a pulsar 🔄 Intercambiar.",
                    chat_id, msg_a_id, parse_mode="HTML",
                )
            except Exception:
                pass

    t = _threading.Timer(60, _timeout)
    t.daemon = True
    t.start()

    bot.register_next_step_handler_by_chat_id(chat_id, _listener)

def setup(bot: telebot.TeleBot) -> None:
    IntercambioHandler(bot)
    logger.info("✅ IntercambioHandler registrado.")