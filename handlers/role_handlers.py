# -*- coding: utf-8 -*-
"""
handlers/role_handlers.py
═══════════════════════════════════════════════════════════════════════════════
v3 — Nuevas funcionalidades:
  FEAT 1 — /anular <rol_id>: cierra rol sin recompensas. Lo pueden usar
           los participantes o cualquier admin. Notifica en Roles.
  FEAT 2 — /finrol: si duración < 10 min → anulación automática por
           incumplimiento de tiempo mínimo. Sin recompensas.
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import threading
import logging
from datetime import datetime
from typing import Optional

import telebot

from funciones import role_service, user_service, economy_service
from database import db_manager
from config import MSG_USUARIO_NO_REGISTRADO, ROLES, ADMIN_IDS
from funciones.user_utils import _obtener_id_desde_username

logger = logging.getLogger(__name__)

_dispo_timers: dict[int, threading.Timer] = {}
_DISPO_DURACION_SEG: int = 3 * 60 * 60
_TIEMPO_MINIMO_ROL_SEG: int = 10 * 60   # ← nuevo: tiempo mínimo de rol válido


def _cancelar_timer_dispo(user_id: int) -> None:
    timer = _dispo_timers.pop(user_id, None)
    if timer:
        timer.cancel()
        logger.debug(f"[DISPO] Timer cancelado para {user_id}")
    try:
        db_manager.execute_update(
            "UPDATE USUARIOS SET encola = 0, dispo_expira = NULL WHERE userID = ?",
            (user_id,),
        )
    except Exception as _e:
        logger.error(f"[DISPO] Error limpiando dispo_expira en BD para {user_id}: {_e}")


def _migrar_columna_dispo_expira() -> None:
    try:
        db_manager.execute_update(
            "ALTER TABLE USUARIOS ADD COLUMN dispo_expira TEXT DEFAULT NULL"
        )
        logger.info("[DISPO] Columna dispo_expira agregada a USUARIOS.")
    except Exception:
        pass


def _restaurar_timers_dispo(bot) -> None:
    from datetime import datetime, timezone
    try:
        rows = db_manager.execute_query(
            "SELECT userID, dispo_expira FROM USUARIOS "
            "WHERE encola = 1 AND dispo_expira IS NOT NULL"
        )
        if not rows:
            return
        ahora = datetime.now(timezone.utc)
        for row in rows:
            uid        = row["userID"]
            expira_str = row["dispo_expira"]
            try:
                expira = datetime.fromisoformat(expira_str)
                if expira.tzinfo is None:
                    expira = expira.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                expira = ahora
            restante = (expira - ahora).total_seconds()
            if restante <= 0:
                db_manager.execute_update(
                    "UPDATE USUARIOS SET encola = 0, dispo_expira = NULL WHERE userID = ?",
                    (uid,),
                )
                logger.info(f"[DISPO] Disponibilidad expirada durante downtime → limpiada para {uid}")
            else:
                def _hacer_expirar(u=uid):
                    _cancelar_timer_dispo(u)
                    logger.info(f"[DISPO] Timeout restaurado → {u} ya no está disponible")
                t = threading.Timer(restante, _hacer_expirar)
                t.daemon = True
                t.start()
                _dispo_timers[uid] = t
                logger.info(f"[DISPO] Timer restaurado para {uid}: {restante:.0f}s restantes")
    except Exception as e:
        logger.error(f"[DISPO] Error restaurando timers de disponibilidad: {e}")


class RoleHandlers:
    """Handlers para el sistema de roles."""

    def __init__(self, bot: telebot.TeleBot):
        self.bot = bot
        self.roles_activos: dict[int, dict] = {}
        self._register_handlers()
        self._cargar_roles_activos()
        _migrar_columna_dispo_expira()
        _restaurar_timers_dispo(bot)

    def _register_handlers(self) -> None:
        r = self.bot.register_message_handler
        r(self.cmd_rol,      commands=["rol"])
        r(self.cmd_finrol,   commands=["finrol"])
        r(self.cmd_anular,   commands=["anular"])       # ← NUEVO
        r(self.cmd_dispo,    commands=["dispo"])
        r(self.cmd_findispo, commands=["findispo"])
        r(self.cmd_verdispo, commands=["verdispo"])

    def _cargar_roles_activos(self) -> None:
        """Reconstruye roles_activos desde la BD al arrancar el bot."""
        try:
            rows = db_manager.execute_query(
                "SELECT rolID, idolID, clienteID, comienzo "
                "FROM ROLES WHERE estado = 'en curso'"
            )
            for row in rows:
                rol_id       = row["rolID"]
                idol_id      = row["idolID"]
                cliente_raw  = str(row["clienteID"] or "")
                clientes_ids = [
                    int(c.strip()) for c in cliente_raw.split(",") if c.strip()
                ]
                try:
                    inicio = datetime.strptime(row["comienzo"], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    inicio = datetime.now()
                self.roles_activos[rol_id] = {
                    "inicio":       inicio,
                    "idol_id":      idol_id,
                    "clientes_ids": clientes_ids,
                }
            if rows:
                logger.info(f"[ROL] {len(rows)} rol(es) activo(s) recuperado(s) desde BD.")
        except Exception as e:
            logger.error(f"[ROL] Error al cargar roles activos desde BD: {e}", exc_info=True)

    def _verificar_canal_roles(self, message: telebot.types.Message) -> bool:
        tid = message.message_thread_id
        cid = message.chat.id
        if tid == ROLES:
            return True
        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass
        m = self.bot.send_message(
            cid, "❌ Este comando solo puede usarse en el canal de roles.",
            message_thread_id=tid,
        )
        threading.Timer(5.0, lambda: self._borrar_seguro(cid, m.message_id)).start()
        return False

    def _borrar_seguro(self, chat_id: int, message_id: int) -> None:
        try:
            self.bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    def _temp_msg(self, cid: int, texto: str, tid, delay: float = 5.0) -> None:
        m = self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
        threading.Timer(delay, lambda: self._borrar_seguro(cid, m.message_id)).start()

    # ── Helpers de lógica de roles ────────────────────────────────────────────

    def _es_admin_o_participante(self, cid: int, uid: int, rol_info: dict) -> bool:
        """
        True si uid está autorizado a operar sobre un rol.
        Incluye: idol del rol, cualquier cliente, admin en ADMIN_IDS,
        o admin/creador del grupo via Telegram.
        """
        if uid == rol_info["idol_id"] or uid in rol_info.get("clientes_ids", []):
            return True
        if uid in ADMIN_IDS:
            return True
        try:
            return self.bot.get_chat_member(cid, uid).status in (
                "administrator", "creator"
            )
        except Exception:
            return False

    def _anular_rol_interno(
        self, rol_id: int, rol_info: dict, motivo: str = "anulado"
    ) -> None:
        """
        Ejecuta la anulación de un rol SIN distribuir recompensas.

        Acciones:
          1. Persiste estado='anulado', validez='anulado' en ROLES.
          2. Libera a todos los participantes (enrol → 0).
          3. Elimina el rol de roles_activos en memoria.

        Llamado por: cmd_anular (manual) y cmd_finrol (tiempo mínimo).
        """
        final_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            db_manager.execute_update(
                "UPDATE ROLES "
                "SET estado = 'anulado', final = ?, validez = 'anulado' "
                "WHERE rolID = ?",
                (final_str, rol_id),
            )
        except Exception as e:
            logger.error(f"[ROL] Error actualizando BD en anulación #{rol_id}: {e}")

        participantes = [rol_info["idol_id"]] + rol_info.get("clientes_ids", [])
        for pid in participantes:
            try:
                db_manager.execute_update(
                    "UPDATE USUARIOS SET enrol = 0 WHERE userID = ?", (pid,)
                )
            except Exception as e:
                logger.warning(f"[ROL] Error liberando participante {pid}: {e}")

        self.roles_activos.pop(rol_id, None)
        logger.info(
            f"[ROL] #{rol_id} anulado ({motivo}). "
            f"Participantes liberados: {participantes}"
        )

    def _incrementar_roles(
        self, rol_id: int, rol_info: Optional[dict] = None
    ) -> None:
        """
        Incrementa contadores al finalizar un rol VÁLIDO.
          · rol_hist +1 → siempre para todos.
          · jugando  +1 → solo en idol ↔ cliente (no idol vs idol).
        """
        try:
            if rol_info:
                idol_id      = rol_info["idol_id"]
                clientes_ids = [int(c) for c in rol_info.get("clientes_ids", [])]
            else:
                row = db_manager.execute_query(
                    "SELECT idolID, clienteID FROM ROLES WHERE rolID = ?", (rol_id,)
                )
                if not row:
                    logger.warning(f"[ROL] _incrementar_roles: rol #{rol_id} no en BD")
                    return
                idol_id      = row[0]["idolID"]
                cliente_raw  = str(row[0]["clienteID"] or "")
                clientes_ids = [
                    int(c.strip()) for c in cliente_raw.split(",") if c.strip()
                ]

            todos = [idol_id] + clientes_ids

            es_idol_vs_idol = False
            if clientes_ids:
                primera_clase = db_manager.execute_query(
                    "SELECT clase FROM USUARIOS WHERE userID = ?", (clientes_ids[0],)
                )
                if primera_clase and primera_clase[0].get("clase") == "idol":
                    es_idol_vs_idol = True

            if es_idol_vs_idol:
                for uid_p in todos:
                    db_manager.execute_update(
                        "UPDATE USUARIOS SET rol_hist = rol_hist + 1 WHERE userID = ?",
                        (uid_p,),
                    )
                logger.info(f"[ROL] #{rol_id} idol vs idol → rol_hist+1 para {todos}")
            else:
                for uid_p in todos:
                    db_manager.execute_update(
                        "UPDATE USUARIOS "
                        "SET rol_hist = rol_hist + 1, jugando = jugando + 1 "
                        "WHERE userID = ?",
                        (uid_p,),
                    )
                logger.info(
                    f"[ROL] #{rol_id} idol vs cliente → rol_hist+1, jugando+1 para {todos}"
                )
        except Exception as e:
            logger.error(f"[ROL] Error en _incrementar_roles #{rol_id}: {e}")

    # ── /rol ─────────────────────────────────────────────────────────────────

    def cmd_rol(self, message: telebot.types.Message) -> None:
        """
        Inicia un rol entre una idol y uno o más usuarios.
        Restricciones: solo idols, clientes sin rol activo, idol fuera de rol.
        """
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        if not self._verificar_canal_roles(message):
            return
        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        idol_info = user_service.get_user_info(uid)
        if not idol_info:
            self._temp_msg(cid, MSG_USUARIO_NO_REGISTRADO, tid)
            return
        if idol_info["clase"] != "idol":
            self._temp_msg(cid, "❌ Solo las idols pueden iniciar roles.", tid)
            return

        text     = message.text or ""
        entities = message.entities or []
        clientes_ids: list[int] = []
        errores: list[str]      = []

        for ent in entities:
            if ent.type == "text_mention" and ent.user:
                resolved_id = ent.user.id
                if resolved_id == uid:
                    errores.append("❌ No puedes iniciar un rol contigo mismo.")
                    continue
                if not db_manager.user_exists(resolved_id):
                    errores.append("❌ El usuario mencionado no está registrado.")
                    continue
                clientes_ids.append(resolved_id)
            elif ent.type == "mention":
                username_raw = text[ent.offset + 1 : ent.offset + ent.length]
                resolved_id  = _obtener_id_desde_username(username_raw, cid, self.bot)
                if not resolved_id:
                    errores.append(f"❌ No se pudo resolver @{username_raw}.")
                    continue
                if resolved_id == uid:
                    errores.append("❌ No puedes iniciar un rol contigo mismo.")
                    continue
                if not db_manager.user_exists(resolved_id):
                    errores.append(f"❌ @{username_raw} no está registrado.")
                    continue
                clientes_ids.append(resolved_id)

        clientes_ids = list(dict.fromkeys(clientes_ids))

        if errores:
            m = self.bot.send_message(cid, "\n".join(errores), message_thread_id=tid)
            threading.Timer(7.0, lambda: self._borrar_seguro(cid, m.message_id)).start()
            return
        if not clientes_ids:
            m = self.bot.send_message(
                cid,
                "❌ Debes mencionar al menos un usuario registrado.\n"
                "Uso: <code>/rol @usuario</code>",
                parse_mode="HTML",
                message_thread_id=tid,
            )
            threading.Timer(5.0, lambda: self._borrar_seguro(cid, m.message_id)).start()
            return

        clientes_bloqueados: list[str] = []
        for cliente_id in clientes_ids:
            info_cliente = user_service.get_user_info(cliente_id)
            if not info_cliente:
                continue
            if info_cliente.get("clase") == "cliente":
                fila = db_manager.execute_query(
                    "SELECT enrol FROM USUARIOS WHERE userID = ?", (cliente_id,)
                )
                if fila and int(fila[0].get("enrol", 0)) == 1:
                    clientes_bloqueados.append(
                        info_cliente.get("nombre") or str(cliente_id)
                    )
        if clientes_bloqueados:
            nombres = ", ".join(clientes_bloqueados)
            m = self.bot.send_message(
                cid,
                f"⚠️ Los siguientes clientes ya están en un rol activo:\n"
                f"<b>{nombres}</b>",
                parse_mode="HTML",
                message_thread_id=tid,
            )
            threading.Timer(10.0, lambda: self._borrar_seguro(cid, m.message_id)).start()
            return

        try:
            clientes_str = ",".join(str(c) for c in clientes_ids)
            rol_id = db_manager.create_role(uid, clientes_str)

            # ── Sistema cazadora ──────────────────────────────────────────────
            # Aplica si: exactamente 1 cliente, nunca rolearon juntos este mes,
            # y la idol no estaba en otro rol activo en este momento.
            cazadora = False
            if len(clientes_ids) == 1:
                from funciones.role_service import get_frecuencia
                freq_previa = get_frecuencia(uid, clientes_ids[0])
                if freq_previa == 0:
                    cazadora = True

            self.roles_activos[rol_id] = {
                "inicio":       datetime.now(),
                "idol_id":      uid,
                "clientes_ids": clientes_ids,
                "cazadora":     cazadora,
            }
            db_manager.execute_update(
                "UPDATE USUARIOS SET enrol = 1, encola = 0 WHERE userID = ?", (uid,)
            )
            _cancelar_timer_dispo(uid)
            for cliente_id in clientes_ids:
                db_manager.execute_update(
                    "UPDATE USUARIOS SET enrol = 1 WHERE userID = ?", (cliente_id,)
                )
            nombres_clientes = []
            for cliente_id in clientes_ids:
                info = user_service.get_user_info(cliente_id)
                nombres_clientes.append(info["nombre"] if info else str(cliente_id))
            texto = (
                f"✅ <b>Rol iniciado</b>\n\n"
                f"🎭 Rol <b>#{rol_id}</b>\n"
                f"👑 Idol: {idol_info['nombre']}\n"
                f"🎭 Cliente(s): {', '.join(nombres_clientes)}\n\n"
                f"Usa <code>/finrol {rol_id}</code> para finalizar."
            )
            logger.info(f"[ROL] #{rol_id} iniciado — Idol: {uid}, Clientes: {clientes_ids}")
        except Exception as e:
            texto = f"❌ Error al iniciar rol: {e}"
            logger.error(f"[ROL] cmd_rol: {e}", exc_info=True)

        self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)

    # ── /finrol ──────────────────────────────────────────────────────────────

    def cmd_finrol(self, message: telebot.types.Message) -> None:
        """
        Finaliza un rol activo y distribuye recompensas.

        Si la duración es < 10 minutos, el rol se anula automáticamente
        sin distribuir recompensas (incumplimiento de tiempo mínimo).
        """
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        if not self._verificar_canal_roles(message):
            return
        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        user_info = user_service.get_user_info(uid)
        if not user_info:
            self._temp_msg(cid, MSG_USUARIO_NO_REGISTRADO, tid)
            return

        try:
            parts = (message.text or "").split()
            if len(parts) < 2:
                self._temp_msg(
                    cid, "❌ Debes especificar el ID del rol\nUso: /finrol [ID]", tid
                )
                return

            rol_id = int(parts[1])

            if rol_id not in self.roles_activos:
                self._temp_msg(
                    cid, f"❌ Rol #{rol_id} no encontrado o ya finalizado.", tid
                )
                return

            rol_info = self.roles_activos[rol_id]

            if not self._es_admin_o_participante(cid, uid, rol_info):
                self._temp_msg(
                    cid,
                    "❌ Solo los participantes del rol o un administrador "
                    "pueden finalizarlo.",
                    tid,
                )
                return

            duracion        = datetime.now() - rol_info["inicio"]
            tiempo_segundos = int(duracion.total_seconds())

            # ── Validar tiempo mínimo (10 minutos) ────────────────────────────
            if tiempo_segundos < _TIEMPO_MINIMO_ROL_SEG:
                mins_reales = tiempo_segundos // 60
                segs_reales = tiempo_segundos % 60
                self._anular_rol_interno(
                    rol_id, rol_info, motivo="tiempo mínimo no alcanzado"
                )
                texto = (
                    f"🚫 <b>Rol #{rol_id} ANULADO</b>\n\n"
                    f"⚠️ Duración: <b>{mins_reales}m {segs_reales}s</b> — "
                    f"el mínimo requerido es <b>10 minutos</b>.\n\n"
                    f"<i>No se han distribuido recompensas por incumplimiento "
                    f"del tiempo mínimo.</i>"
                )
                self.bot.send_message(
                    cid, texto, parse_mode="HTML", message_thread_id=tid
                )
                return
            # ─────────────────────────────────────────────────────────────────

            _snap_antes   = user_service.get_user_info(uid)
            _wallet_antes = int(_snap_antes["wallet"]) if _snap_antes else 0

            cazadora_flag = rol_info.get("cazadora", False)

            is_valid, puntos_ganados, info_sistemas = role_service.end_role(
                rol_id          = rol_id,
                tiempo_segundos = tiempo_segundos,
                validez         = "valido",
                clientes_ids    = rol_info.get("clientes_ids", []),
                cazadora        = cazadora_flag,
            )

            if is_valid:
                self._incrementar_roles(rol_id, rol_info)

                if puntos_ganados > 0:
                    from funciones.user_experience import aplicar_experiencia_usuario
                    aplicar_experiencia_usuario(uid, puntos_ganados, self.bot, cid, tid)

                _snap_despues   = user_service.get_user_info(uid)
                _wallet_despues = (
                    int(_snap_despues["wallet"]) if _snap_despues else _wallet_antes
                )
                cosmos_ganados = max(0, _wallet_despues - _wallet_antes)

                _clientes        = rol_info.get("clientes_ids", [])
                _es_idol_vs_idol = False
                if _clientes:
                    _fila_clase = db_manager.execute_query(
                        "SELECT clase FROM USUARIOS WHERE userID = ?", (_clientes[0],)
                    )
                    if _fila_clase and _fila_clase[0].get("clase") == "idol":
                        _es_idol_vs_idol = True
                icono_tipo = "❌" if _es_idol_vs_idol else "✅"

                h    = tiempo_segundos // 3600
                mins = (tiempo_segundos % 3600) // 60
                s    = tiempo_segundos % 60

                # ── Líneas de sistemas especiales ─────────────────────────────
                lineas_extra = ""

                info_caz  = info_sistemas.get("cazadora", {})
                info_freq = info_sistemas.get("frecuentes", {})

                if info_caz.get("activo"):
                    lineas_extra += (
                        f"🦅 <b>Bonus cazadora:</b> +{info_caz['puntos_bonus']} pts (×2)\n"
                    )

                if info_freq:
                    pct  = info_freq["penalizacion_pct"]
                    cant = info_freq["cantidad_previa"]
                    lineas_extra += (
                        f"⚠️ <b>Penalización frecuentes:</b> -{pct}% puntos "
                        f"({cant} rol{'es' if cant != 1 else ''} previo{'s' if cant != 1 else ''} este mes)\n"
                    )

                texto = (
                    f"✅ <b>Rol #{rol_id} finalizado</b>\n\n"
                    f"⏱️ Duración: {h}h {mins}m {s}s\n"
                    f"🏆 Puntos ganados: <b>{puntos_ganados}</b>\n"
                    f"{lineas_extra}"
                    f"Cuenta para rol del mes: {icono_tipo}\n"
                    f"✨ Cosmos obtenidos: <b>{cosmos_ganados}</b>\n\n"
                    f"¡Gracias por disfrutar de nuestros servicios! 💋"
                )
                logger.info(f"[ROL] #{rol_id} finalizado — {h}h {mins}m {s}s")
            else:
                texto = (
                    f"⚠️ Rol #{rol_id} finalizado como NO VÁLIDO "
                    f"(duración insuficiente)."
                )

            participantes = [rol_info["idol_id"]] + rol_info.get("clientes_ids", [])
            for participante_id in participantes:
                db_manager.execute_update(
                    "UPDATE USUARIOS SET enrol = 0 WHERE userID = ?",
                    (participante_id,),
                )
            del self.roles_activos[rol_id]

        except ValueError:
            texto = "❌ El ID del rol debe ser un número válido."
        except Exception as e:
            texto = f"❌ Error al finalizar rol: {e}"
            logger.error(f"[ROL] cmd_finrol: {e}", exc_info=True)

        self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)

    # ── /anular ──────────────────────────────────────────────────────────────

    def cmd_anular(self, message: telebot.types.Message) -> None:
        """
        Anula un rol activo sin distribuir recompensas ni actualizar contadores.

        Uso:   /anular <rol_id>

        Autorización:
          · Idol del rol.
          · Cualquier cliente del rol.
          · Admin del grupo (Telegram) o admin en ADMIN_IDS.

        El rol queda en BD con estado='anulado'. Se notifica en Roles.
        """
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        if not self._verificar_canal_roles(message):
            return
        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        user_info = user_service.get_user_info(uid)
        if not user_info:
            self._temp_msg(cid, MSG_USUARIO_NO_REGISTRADO, tid)
            return

        parts = (message.text or "").split()
        if len(parts) < 2:
            self._temp_msg(
                cid,
                "❌ Debes especificar el ID del rol.\n"
                "Uso: <code>/anular &lt;número_de_rol&gt;</code>\n"
                "Ejemplo: <code>/anular 42</code>",
                tid,
            )
            return

        try:
            rol_id = int(parts[1])
        except ValueError:
            self._temp_msg(cid, "❌ El ID del rol debe ser un número válido.", tid)
            return

        if rol_id not in self.roles_activos:
            self._temp_msg(
                cid, f"❌ Rol #{rol_id} no encontrado o ya finalizado.", tid
            )
            return

        rol_info = self.roles_activos[rol_id]

        if not self._es_admin_o_participante(cid, uid, rol_info):
            self._temp_msg(
                cid,
                "❌ Solo los participantes del rol o un administrador "
                "pueden anularlo.",
                tid,
            )
            return

        duracion        = datetime.now() - rol_info["inicio"]
        tiempo_segundos = int(duracion.total_seconds())
        h    = tiempo_segundos // 3600
        mins = (tiempo_segundos % 3600) // 60
        s    = tiempo_segundos % 60

        quien = (
            user_info.get("idol")
            or user_info.get("nombre")
            or user_info.get("nombre_usuario")
            or str(uid)
        )

        self._anular_rol_interno(
            rol_id, rol_info, motivo=f"anulado manualmente por {uid}"
        )

        texto = (
            f"🚫 <b>Rol #{rol_id} ANULADO</b>\n\n"
            f"⏱️ Duración al cierre: {h}h {mins}m {s}s\n"
            f"👤 Cancelado por: <b>{quien}</b>\n\n"
            f"<i>No se han distribuido recompensas.</i>"
        )
        self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
        logger.info(
            f"[ROL] /anular: #{rol_id} anulado por {uid} ({quien}) "
            f"tras {h}h {mins}m {s}s"
        )

    # ── /dispo ───────────────────────────────────────────────────────────────

    def cmd_dispo(self, message: telebot.types.Message) -> None:
        """
        Pone a la idol en disponibilidad (encola=1, timer 3h, foto a Roles).
        Uso: /dispo [texto personalizado]
        """
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        if not self._verificar_canal_roles(message):
            return
        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        user_info = user_service.get_user_info(uid)
        if not user_info:
            self._temp_msg(cid, MSG_USUARIO_NO_REGISTRADO, tid)
            return
        if user_info["clase"] != "idol":
            self._temp_msg(
                cid, "❌ Solo las idols pueden anunciarse como disponibles. 💋", tid
            )
            return

        text  = message.text or ""
        parts = text.split(maxsplit=1)
        texto_dispo = (
            parts[1].strip()
            if len(parts) > 1 and parts[1].strip()
            else "Estaré disponible durante 3 horas bombones 💋"
        )
        nombre_idol = user_info.get("idol") or user_info.get("nombre") or "Idol"

        _cancelar_timer_dispo(uid)

        from datetime import timezone, timedelta
        expira_en  = datetime.now(timezone.utc) + timedelta(seconds=_DISPO_DURACION_SEG)
        expira_str = expira_en.isoformat()
        db_manager.execute_update(
            "UPDATE USUARIOS SET encola = 1, dispo_expira = ? WHERE userID = ?",
            (expira_str, uid),
        )

        def _expirar_dispo():
            _cancelar_timer_dispo(uid)
            logger.info(f"[DISPO] Timeout de 3h → {nombre_idol} ({uid}) ya no disponible")

        t = threading.Timer(_DISPO_DURACION_SEG, _expirar_dispo)
        t.daemon = True
        t.start()
        _dispo_timers[uid] = t

        caption = (
            f"💋 <b>{nombre_idol}</b> está disponible...\n\n"
            f"<i>{texto_dispo}</i> 🌹"
        )

        enviado = False
        try:
            from typing import cast as _cast
            fotos = self.bot.get_user_profile_photos(uid, limit=1)
            if fotos and fotos.total_count > 0 and fotos.photos:
                photo_sizes = _cast(list[telebot.types.PhotoSize], fotos.photos[0])
                mejor_foto  = max(photo_sizes, key=lambda p: p.width * p.height)
                self.bot.send_photo(
                    cid,
                    photo=mejor_foto.file_id,
                    caption=caption,
                    parse_mode="HTML",
                    message_thread_id=tid,
                )
                enviado = True
        except Exception as e:
            logger.warning(f"[DISPO] Error obteniendo foto de perfil de {uid}: {e}")

        if not enviado:
            try:
                self.bot.send_message(
                    cid, caption, parse_mode="HTML", message_thread_id=tid
                )
            except Exception as e:
                logger.error(f"[DISPO] Error enviando mensaje de dispo: {e}")

        logger.info(f"[DISPO] {nombre_idol} ({uid}) marcada como disponible")

    # ── /findispo ────────────────────────────────────────────────────────────

    def cmd_findispo(self, message: telebot.types.Message) -> None:
        """Saca a la idol de disponibilidad manualmente."""
        cid = message.chat.id
        tid = message.message_thread_id
        uid = message.from_user.id

        if not self._verificar_canal_roles(message):
            return
        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        user_info = user_service.get_user_info(uid)
        if not user_info:
            self._temp_msg(cid, MSG_USUARIO_NO_REGISTRADO, tid)
            return
        if user_info["clase"] != "idol":
            self._temp_msg(cid, "❌ Solo las idols pueden usar este comando.", tid)
            return

        nombre_idol = user_info.get("idol") or user_info.get("nombre") or "Idol"
        _cancelar_timer_dispo(uid)

        m = self.bot.send_message(
            cid,
            f"🌙 <b>{nombre_idol}</b> ya no está disponible. "
            f"Hasta pronto, bombones... 💋",
            parse_mode="HTML",
            message_thread_id=tid,
        )
        threading.Timer(8.0, lambda: self._borrar_seguro(cid, m.message_id)).start()
        logger.info(f"[FINDISPO] {nombre_idol} ({uid}) salió de disponibilidad")

    # ── /verdispo ────────────────────────────────────────────────────────────

    def cmd_verdispo(self, message: telebot.types.Message) -> None:
        """Lista idols disponibles (encola=1). Se borra en 10s."""
        cid = message.chat.id
        tid = message.message_thread_id

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        disponibles = db_manager.execute_query(
            "SELECT nombre, idol, nombre_usuario FROM USUARIOS "
            "WHERE encola = 1 AND clase = 'idol' ORDER BY nombre"
        )

        if not disponibles:
            texto = (
                "😔 <b>Ninguna idol está disponible en este momento...</b>\n\n"
                "Vuelve más tarde, bombón 💋"
            )
        else:
            lineas = []
            for row in disponibles:
                nombre_mostrar = (
                    row.get("idol")
                    or row.get("nombre")
                    or row.get("nombre_usuario")
                    or "Idol"
                )
                lineas.append(f"  💋 <b>{nombre_mostrar}</b>")
            texto = (
                "🌹 <b>Idols disponibles ahora mismo</b> 🌹\n\n"
                + "\n".join(lineas)
                + "\n\n<i>¡Date prisa, este mensaje desaparece en 10 segundos! 💫</i>"
            )

        m = self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
        threading.Timer(10.0, lambda: self._borrar_seguro(cid, m.message_id)).start()


def setup(bot: telebot.TeleBot) -> None:
    """Función de registro compatible con setup_all_handlers."""
    RoleHandlers(bot)
    logger.info("✅ RoleHandlers registrados")