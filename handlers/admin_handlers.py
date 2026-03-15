# -*- coding: utf-8 -*-
"""
handlers/admin_handlers.py
Comandos de administración y utilidades de usuario.

Comandos:
  /editar  TABLA @etiqueta campo valor  — owner only
  /nuevomes                             — owner only
  /cargar  @usuario cantidad            — admins
  /quitar  @usuario cantidad            — admins
  /remover @usuario [motivo]            — admins
  /alerta  mensaje                      — admins
"""

import threading
import time
import logging
from datetime import datetime
from typing import List, Optional
from utils.thread_utils import get_thread_id
import telebot

from config import LOG_GROUP_ID  # FIX: importar desde config en lugar de hardcodear
from funciones import user_service, economy_service
from funciones.user_utils import extraer_user_id, resolver_username_crudo
from database import db_manager

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

_TABLAS_PERMITIDAS: frozenset = frozenset({
    "USUARIOS", "ROLES", "RECORDS", "SOLICITUDES", "APUESTAS",
    "MEDALLAS_USUARIOS", "LADDER_STATS", "MISIONES", "INVENTARIO_USUARIO",
    "POKEMON_USUARIO", "EXMIEMBROS",
})

# PK canónica por tabla; se usa como columna del WHERE en /editar
_PK_POR_TABLA: dict = {
    "USUARIOS":           "userID",
    "ROLES":              "rolID",
    "RECORDS":            "userID",
    "SOLICITUDES":        "solID",
    "APUESTAS":           "betID",
    "MEDALLAS_USUARIOS":  "id",
    "LADDER_STATS":       "userID",
    "MISIONES":           "userID",
    "INVENTARIO_USUARIO": "id",
    "POKEMON_USUARIO":    "id_unico",
    "EXMIEMBROS":         "userID",
}

# Tablas cuya PK es userID de Telegram (se resuelven desde @mention)
_TABLAS_PK_USERID: frozenset = frozenset(
    t for t, pk in _PK_POR_TABLA.items() if pk == "userID"
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de módulo
# ─────────────────────────────────────────────────────────────────────────────

def _is_owner(bot, chat_id: int, user_id: int) -> bool:
    """True si el usuario es el creador del grupo."""
    try:
        return bot.get_chat_member(chat_id, user_id).status == "creator"
    except Exception:
        return False


def _delete_after(bot, chat_id: int, message_id: int, delay: float = 10.0) -> None:
    """Borra un mensaje después de `delay` segundos sin bloquear."""
    def _del():
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass
    threading.Timer(delay, _del).start()


def _thread_id(message) -> Optional[int]:
    """
    Extrae message_thread_id de forma segura con fallback para grupos foro.

    Versión mejorada de la función homónima en admin_handlers.py.
    Delega a _get_thread_id() para cubrir el caso donde pyTelegramBotAPI
    no deserializa el campo correctamente en grupos con Topics.
    """
    return get_thread_id(message)

def _cast_value(raw: str):
    """Intenta convertir a int → float → str."""
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _resolve_userid_for_edit(message, bot) -> Optional[int]:
    """
    Resuelve la etiqueta de /editar a un userID.

    Orden:
      1. Entities del mensaje (text_mention / mention con prefer_mention=True)
      2. parts[2] como @username buscado en BD (por si la entity no fue reconocida)
      3. parts[2] como número ≥ 100 000 (userID explícito)
    """
    uid, _ = extraer_user_id(message, bot, prefer_mention=True)
    if uid:
        return uid

    parts = (message.text or "").split(maxsplit=4)
    if len(parts) >= 3:
        raw = parts[2].lstrip("@").strip()
        if raw:
            # Intentar BD por nombre_usuario
            try:
                result = db_manager.execute_query(
                    "SELECT userID FROM USUARIOS WHERE LOWER(nombre_usuario) = LOWER(?)",
                    (raw,),
                )
                if result:
                    row = result[0]
                    return int(row["userID"] if isinstance(row, dict) else row[0])
            except Exception as exc:
                logger.warning("[EDITAR] Fallback BD falló para '%s': %s", raw, exc)
            # Intentar userID numérico directo
            try:
                candidate = int(raw)
                if candidate >= 100_000:
                    return candidate
            except ValueError:
                pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Handler principal
# ─────────────────────────────────────────────────────────────────────────────

class AdminHandlers:
    """Handlers para comandos administrativos."""

    def __init__(self, bot: telebot.TeleBot, admin_ids: Optional[List[int]] = None):
        self.bot = bot
        self.admin_ids: List[int] = admin_ids or [6037695672]
        self._register_handlers()

    def _register_handlers(self) -> None:
        r = self.bot.register_message_handler
        r(self.cmd_cargar,   commands=["cargar"])
        r(self.cmd_quitar,   commands=["quitar"])
        r(self.cmd_remover,  commands=["remover"])
        r(self.cmd_alerta,   commands=["alerta"])
        r(self.cmd_editar,   commands=["editar"])
        r(self.cmd_nuevomes, commands=["nuevomes"])
        r(self.cmd_limpiar,  commands=["limpiar"])

    def _is_admin(self, message) -> bool:
        uid = message.from_user.id
        cid = message.chat.id
        try:
            if self.bot.get_chat_member(cid, uid).status in ("creator", "administrator"):
                return True
        except Exception:
            pass
        return uid in self.admin_ids

    def _send_temp(self, cid, tid, texto, delay=10, parse_mode='html'):
        """Envía un mensaje y lo borra tras `delay` segundos (no bloquea el hilo)."""
        try:
            m = self.bot.send_message(
                cid, texto,
                parse_mode=parse_mode,
                message_thread_id=tid,
            )
            _delete_after(self.bot, cid, m.message_id, float(delay))
        except Exception as e:
            logger.error(f"[SEND_TEMP] Error enviando mensaje temporal: {e}")

    def _resolver_target(self, message, prefer_mention: bool = False):
        """(target_id, nombre, None) o (None, None, error_msg)."""
        target_id, nombre_o_error = extraer_user_id(
            message, self.bot, prefer_mention=prefer_mention
        )
        if target_id:
            return target_id, nombre_o_error, None
        return None, None, nombre_o_error or "❌ No se pudo identificar al usuario."

    def _try_delete(self, chat_id: int, message_id: int) -> None:
        try:
            self.bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    # ════════════════════════════════════════════════════════════════════
    # /limpiar
    # ════════════════════════════════════════════════════════════════════

    def cmd_limpiar(self, message) -> None:
        """
        /limpiar — Solo el owner del grupo puede usar este comando.

        Itera cada miembro registrado en la tabla USUARIOS y consulta su
        estado actual con get_chat_member. Si el usuario:
          · Ha salido del grupo   (status == 'left')
          · Fue expulsado         (status == 'kicked')
          · No se encuentra en la caché del chat (excepción de la API)

        → Sus datos se migran de USUARIOS a EXMIEMBROS.

        Al finalizar, reporta los nombres de todos los usuarios migrados.
        """
        cid = message.chat.id
        uid = message.from_user.id
        tid = _thread_id(message)

        self._try_delete(cid, message.message_id)

        # Solo el owner puede ejecutar este comando
        if not _is_owner(self.bot, cid, uid):
            self._send_temp(cid, tid, "❌ Solo el owner del grupo puede usar /limpiar.", delay=8)
            return

        # Aviso de inicio (puede tardar según el tamaño del grupo)
        try:
            aviso = self.bot.send_message(
                cid,
                "🧹 <b>Limpiando base de datos...</b>\n"
                "Verificando el estado de cada usuario registrado. Por favor espera.",
                parse_mode="html",
                message_thread_id=tid,
            )
        except Exception:
            aviso = None

        # Obtener todos los usuarios registrados
        try:
            usuarios = db_manager.execute_query(
                "SELECT userID, nombre, nombre_usuario FROM USUARIOS ORDER BY nombre"
            )
        except Exception as e:
            logger.error(f"[LIMPIAR] Error consultando USUARIOS: {e}")
            self._send_temp(cid, tid, f"❌ Error consultando la base de datos: {e}", delay=15)
            if aviso:
                try:
                    self.bot.delete_message(cid, aviso.message_id)
                except Exception:
                    pass
            return

        if not usuarios:
            if aviso:
                try:
                    self.bot.delete_message(cid, aviso.message_id)
                except Exception:
                    pass
            self._send_temp(cid, tid, "ℹ️ No hay usuarios registrados en la base de datos.", delay=10)
            return

        migrados: list         = []
        errores_migracion: list = []

        for fila in usuarios:
            user_id_fila   = fila["userID"]   if isinstance(fila, dict) else fila[0]
            nombre_fila    = fila["nombre"]    if isinstance(fila, dict) else fila[1]
            username_fila  = fila["nombre_usuario"] if isinstance(fila, dict) else fila[2]

            debe_migrar      = False
            motivo_migracion = ""

            try:
                miembro = self.bot.get_chat_member(cid, user_id_fila)
                if miembro.status in ("left", "kicked"):
                    debe_migrar      = True
                    motivo_migracion = f"Salió/expulsado del grupo (status={miembro.status})"
            except Exception as api_exc:
                debe_migrar      = True
                motivo_migracion = f"No encontrado en el chat ({type(api_exc).__name__})"
                logger.info(
                    f"[LIMPIAR] Error API para {user_id_fila} ({nombre_fila}): {api_exc}"
                )

            if debe_migrar:
                try:
                    from handlers.member_handlers import _mover_a_exmiembros
                    ok = _mover_a_exmiembros(user_id_fila, motivo_migracion)
                    if ok:
                        display = f"{nombre_fila}"
                        if username_fila:
                            display += f" (@{username_fila})"
                        migrados.append(display)
                        logger.info(
                            f"[LIMPIAR] Migrado a EXMIEMBROS: {user_id_fila} "
                            f"({nombre_fila}) — Motivo: {motivo_migracion}"
                        )
                    else:
                        errores_migracion.append(f"{nombre_fila} (error al migrar)")
                        logger.warning(
                            f"[LIMPIAR] Falló la migración de {user_id_fila} ({nombre_fila})"
                        )
                except Exception as mig_exc:
                    errores_migracion.append(f"{nombre_fila} (excepción: {mig_exc})")
                    logger.error(
                        f"[LIMPIAR] Excepción migrando {user_id_fila}: {mig_exc}",
                        exc_info=True,
                    )

        # ── Borrar el aviso de "limpiando..." ────────────────────────────────
        if aviso:
            try:
                self.bot.delete_message(cid, aviso.message_id)
            except Exception:
                pass

        # ── Construir mensaje de resultado ────────────────────────────────────
        if not migrados and not errores_migracion:
            texto_resultado = (
                "✅ <b>Base de datos limpia</b>\n\n"
                f"Se verificaron <b>{len(usuarios)}</b> usuarios.\n"
                "Todos siguen activos en el grupo. No se migró a nadie."
            )
        else:
            texto_resultado = (
                f"🧹 <b>Limpieza completada</b>\n\n"
                f"Usuarios verificados: <b>{len(usuarios)}</b>\n"
                f"Usuarios migrados a EXMIEMBROS: <b>{len(migrados)}</b>\n"
            )
            if migrados:
                texto_resultado += "\n<b>Usuarios migrados:</b>\n"
                for nombre_migrado in migrados:
                    texto_resultado += f"  • {nombre_migrado}\n"

            if errores_migracion:
                texto_resultado += "\n⚠️ <b>Errores durante la migración:</b>\n"
                for err in errores_migracion:
                    texto_resultado += f"  • {err}\n"

        logger.info(
            f"[LIMPIAR] Completado por owner {uid}: "
            f"{len(migrados)} migrados, {len(errores_migracion)} errores."
        )

        try:
            self.bot.send_message(
                cid,
                texto_resultado,
                parse_mode="html",
                message_thread_id=tid,
            )
        except Exception as e:
            logger.error(f"[LIMPIAR] Error enviando resultado: {e}")

    # =========================================================================
    # /editar  TABLA  @etiqueta  columna  valor
    # =========================================================================
    def cmd_editar(self, message) -> None:
        """
        Solo el owner del grupo puede usar este comando.

        Uso:
          /editar TABLA @usuario   columna valor
          /editar TABLA userID     columna valor   (numérico directo)
          /editar ROLES 44         validez No      (tabla con PK no-userID)

        Ejemplos:
          /editar USUARIOS @jennie_ruby_love idol Nayeon
          /editar LADDER_STATS @ash puntos 1500
          /editar ROLES 44 validez No
        """
        cid = message.chat.id
        uid = message.from_user.id
        tid = _thread_id(message)

        self._try_delete(cid, message.message_id)

        if not _is_owner(self.bot, cid, uid):
            self._send_temp(cid, tid, "❌ Solo el owner del grupo puede usar /editar.", delay=8)
            return

        parts = message.text.split(maxsplit=4)
        if len(parts) < 5:
            self._send_temp(
                cid, tid,
                "⚠️ Uso: <code>/editar TABLA @usuario columna valor</code>\n"
                "Ejemplos:\n"
                "  <code>/editar USUARIOS @jennie idol Nayeon</code>\n"
                "  <code>/editar ROLES 44 validez No</code>",
                delay=20,
            )
            return

        tabla   = parts[1].upper()
        etiq    = parts[2]
        columna = parts[3]
        valor   = parts[4]

        if tabla not in _TABLAS_PERMITIDAS:
            self._send_temp(
                cid, tid,
                f"❌ Tabla <b>{tabla}</b> no permitida.\n"
                f"Disponibles: {', '.join(sorted(_TABLAS_PERMITIDAS))}",
                delay=15,
            )
            return

        pk: str = _PK_POR_TABLA.get(tabla, "id")

        # ── Resolución de clave WHERE ────────────────────────────────────────
        if tabla in _TABLAS_PK_USERID:
            clave = _resolve_userid_for_edit(message, self.bot)
            if not clave:
                self._send_temp(
                    cid, tid,
                    f"❌ No se encontró el usuario <b>{etiq}</b>.\n"
                    "Mencionalo con @ o asegurate de que haya escrito en el grupo.",
                    delay=15,
                )
                return
        else:
            # Tabla con PK no-userID: usar la etiqueta como valor literal
            clave = _cast_value(etiq)

        # ── Ejecutar UPDATE ──────────────────────────────────────────────────
        valor_cast = _cast_value(valor)
        try:
            rows = db_manager.execute_update(
                f"UPDATE {tabla} SET {columna} = ? WHERE {pk} = ?",
                (valor_cast, clave),
            )
            texto = (
                f"✅ <b>{tabla}</b> actualizado.\n"
                f"  {pk} = <code>{clave}</code>\n"
                f"  {columna} → <code>{valor}</code>"
                if rows and rows > 0
                else (
                    f"⚠️ No se encontró ningún registro en <b>{tabla}</b> "
                    f"con {pk} = <code>{clave}</code>."
                )
            )
        except Exception as exc:
            logger.error("[EDITAR] Error: %s", exc)
            texto = f"❌ Error al editar: <code>{exc}</code>"

        self._send_temp(cid, tid, texto, delay=20)

    # =========================================================================
    # /nuevomes  — owner only
    # =========================================================================
    def cmd_nuevomes(self, message) -> None:
        cid = message.chat.id
        uid = message.from_user.id
        tid = _thread_id(message)

        self._try_delete(cid, message.message_id)

        if not _is_owner(self.bot, cid, uid):
            self._send_temp(cid, tid, "❌ Solo el owner del grupo puede usar /nuevomes.")
            return

        top_idols = db_manager.execute_query(
            "SELECT nombre, puntos, jugando, wallet "
            "FROM USUARIOS WHERE clase='idol' ORDER BY puntos DESC LIMIT 6"
        ) or []
        top_clientes = db_manager.execute_query(
            "SELECT nombre, puntos, jugando, wallet "
            "FROM USUARIOS WHERE clase='cliente' ORDER BY puntos DESC LIMIT 6"
        ) or []

        try:
            # Resetear puntos, roles y — crítico — el estado VIP mensual.
            # El VIP se compra cada mes; al inicio de uno nuevo todos vuelven
            # a 'Normal' para que quienes quieran renovarlo usen /compravip.
            db_manager.execute_update(
                "UPDATE USUARIOS SET jugando=0, puntos=0, nickname='Normal'"
            )
            reset_ok = True
        except Exception as exc:
            logger.error("[NUEVOMES] Error reseteando: %s", exc)
            reset_ok = False

        mes = datetime.now().strftime("%B %Y")
        medallas = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣"]

        def _bloque(titulo: str, filas: list) -> str:
            if not filas:
                return f"\n<b>{titulo}</b>\n— Sin datos —"
            lineas = [f"\n<b>{titulo}</b>"]
            for i, row in enumerate(filas):
                med = medallas[i] if i < len(medallas) else f"{i + 1}."
                lineas.append(
                    f"{med} <b>{row['nombre']}</b>  "
                    f"— {row['puntos']} pts  |  {row['jugando']} roles  |  {row['wallet']} ✨"
                )
            return "\n".join(lineas)

        self.bot.send_message(
            cid,
            f"🗓️ <b>Cierre de mes — {mes}</b>\n"
            f"{_bloque('👑 TOP 6 Idols', top_idols)}\n"
            f"{_bloque('🎭 TOP 6 Clientes', top_clientes)}\n\n"
            f"{'✅ Puntos, roles y VIP del mes reseteados.' if reset_ok else '❌ Error al resetear datos.'}",
            parse_mode="HTML",
            message_thread_id=tid,
        )

    # =========================================================================
    # /cargar  →  /cargar @usuario puntos cosmos motivo
    # =========================================================================
    def cmd_cargar(self, message) -> None:
        """
        Uso: /cargar @usuario <puntos> <cosmos> <motivo...>
        Ejemplo: /cargar @juan 100 200 Victoria en evento

        Acredita puntos (+ experiencia equivalente) y cosmos al usuario.
        Envía log al grupo de administración.
        """
        cid = message.chat.id
        tid = _thread_id(message)
        uid = message.from_user.id

        # FIX: registrar la invocación desde el inicio, igual que /registrar.
        # Antes solo había un logger.info al final (si todo salía bien),
        # por lo que cualquier fallo previo quedaba sin traza en los logs.
        logger.info("[CARGAR] Invocado por admin %s en chat %s", uid, cid)

        self._try_delete(cid, message.message_id)

        if not self._is_admin(message):
            logger.warning("[CARGAR] Acceso denegado a usuario %s (no es admin)", uid)
            self._send_temp(cid, tid, "❌ Este comando es solo para administradores.", delay=5)
            return

        # ── Parsear argumentos ────────────────────────────────────────────────
        # Formato: /cargar [@usuario] <puntos> <cosmos> <motivo...>
        # Los dos primeros enteros encontrados son puntos y cosmos.
        # El resto del texto (sin @mention y sin los números) es el motivo.
        parts       = (message.text or "").split()
        cmd_args    = parts[1:]           # sin /cargar
        int_indices = []
        for i, p in enumerate(cmd_args):
            try:
                int(p)
                int_indices.append(i)
            except ValueError:
                pass

        if len(int_indices) < 2:
            logger.warning(
                "[CARGAR] Argumentos insuficientes de admin %s: %r",
                uid, message.text,
            )
            self._send_temp(
                cid, tid,
                "❌ Uso: <code>/cargar @usuario &lt;puntos&gt; &lt;cosmos&gt; &lt;motivo&gt;</code>\n"
                "Ejemplo: <code>/cargar @juan 100 200 Victoria en evento</code>",
                delay=12,
            )
            return

        puntos_idx = int_indices[0]
        cosmos_idx = int_indices[1]
        puntos_val = int(cmd_args[puntos_idx])
        cosmos_val = int(cmd_args[cosmos_idx])

        # Motivo: todo lo que no sea @mention ni los dos números
        skip_indices = {puntos_idx, cosmos_idx}
        motivo_parts = [
            p for i, p in enumerate(cmd_args)
            if i not in skip_indices and not p.startswith("@")
        ]
        motivo = " ".join(motivo_parts).strip() or "Sin motivo"

        if puntos_val < 0 or cosmos_val < 0:
            logger.warning("[CARGAR] Valores negativos rechazados por admin %s", uid)
            self._send_temp(cid, tid, "❌ Los valores deben ser positivos.", delay=8)
            return

        # ── Resolver usuario objetivo ─────────────────────────────────────────
        #
        # BUG RAÍZ CORREGIDO:
        # Telegram solo genera una entity "mention" cuando el admin selecciona
        # el @usuario desde el autocomplete. Si lo tipea manualmente, no hay
        # entity. En ese caso, extraer_user_id con prefer_mention=True iteraba
        # las entities (solo encontraba bot_command → skip), no retornaba nada,
        # y caía silenciosamente al fallback reply_to_message. Si el admin tenía
        # activo un reply a un mensaje de otro usuario, ese usuario recibía la
        # carga en lugar del @usuario escrito.
        #
        # SOLUCIÓN: parsear el @username directamente del texto crudo (ya tenemos
        # cmd_args), resolverlo con resolver_username_crudo y usarlo como target
        # primario. Esto es independiente de si Telegram creó la entity o no.
        # Solo si no hay @username en el texto, delegamos a _resolver_target
        # (que sí puede usar reply legítimamente: /cargar 100 200 motivo
        # respondiendo al mensaje del usuario destino).
        target_id: Optional[int] = None
        target_nombre: Optional[str] = None

        mention_raw = next(
            (p.lstrip("@") for p in cmd_args if p.startswith("@") and len(p) > 1),
            None,
        )

        if mention_raw:
            # Hay @username en el texto → resolverlo siempre desde texto crudo.
            # Nunca hacer fallback a reply si este paso falla: sería aplicar la
            # carga a alguien completamente distinto al objetivo declarado.
            target_id = resolver_username_crudo(mention_raw, cid, self.bot)
            if target_id:
                target_nombre = f"@{mention_raw}"
                logger.info(
                    "[CARGAR] Target resuelto por texto crudo → %s (%s)",
                    target_id, target_nombre,
                )
            else:
                logger.warning(
                    "[CARGAR] @%s no pudo resolverse (no en BD ni API) — "
                    "operación abortada sin fallback a reply.",
                    mention_raw,
                )
                self._send_temp(
                    cid, tid,
                    f"❌ No pude encontrar a <b>@{mention_raw}</b>.\n"
                    "Debe haber escrito en el grupo al menos una vez, "
                    "o respondé directamente a su mensaje.",
                    delay=10,
                )
                return
        else:
            # Sin @username en el texto → delegar a _resolver_target.
            # Aquí sí es válido usar reply: el admin respondió al mensaje
            # del usuario destino y escribió /cargar 100 200 motivo.
            target_id, target_nombre, error = self._resolver_target(
                message, prefer_mention=True
            )
            if not target_id:
                logger.warning(
                    "[CARGAR] No se pudo resolver el usuario objetivo: %s", error
                )
                self._send_temp(cid, tid, error, delay=8)
                return

        if not db_manager.user_exists(target_id):
            logger.warning("[CARGAR] Usuario objetivo %s no está registrado", target_id)
            self._send_temp(cid, tid, "❌ El usuario no está registrado en el sistema.", delay=8)
            return

        # ── Nombre del admin ──────────────────────────────────────────────────
        try:
            admin_row    = db_manager.execute_query(
                "SELECT nombre FROM USUARIOS WHERE userID = ?", (uid,)
            )
            admin_nombre = admin_row[0]["nombre"] if admin_row else str(uid)
        except Exception:
            admin_nombre = str(uid)

        logger.info(
            "[CARGAR] Admin %s (%s) → usuario %s (%s) | puntos=%s cosmos=%s motivo=%r",
            uid, admin_nombre, target_id, target_nombre, puntos_val, cosmos_val, motivo,
        )

        # ── Aplicar cosmos ────────────────────────────────────────────────────
        cosmos_ok = True
        if cosmos_val > 0:
            cosmos_ok = economy_service.add_credits(
                target_id, cosmos_val, f"Carga admin: {motivo}"
            )
            if not cosmos_ok:
                logger.error(
                    "[CARGAR] add_credits falló para %s (+%s cosmos)", target_id, cosmos_val
                )

        # ── Aplicar puntos ────────────────────────────────────────────────────
        puntos_ok = True
        if puntos_val > 0:
            try:
                db_manager.execute_update(
                    "UPDATE USUARIOS SET puntos = puntos + ? WHERE userID = ?",
                    (puntos_val, target_id),
                )
                # XP equivalente a los puntos cargados
                from funciones.user_experience import aplicar_experiencia_usuario
                aplicar_experiencia_usuario(
                    target_id, puntos_val,
                    self.bot, cid, tid,
                )
            except Exception as exc:
                logger.error("[CARGAR] Error aplicando puntos a %s: %s", target_id, exc)
                puntos_ok = False

        if not cosmos_ok or not puntos_ok:
            self._send_temp(cid, tid, "❌ Error al aplicar alguna de las recompensas.", delay=8)
            return

        # ── Respuesta en el grupo ─────────────────────────────────────────────
        nuevo_cosmos = economy_service.get_balance(target_id)
        self._send_temp(
            cid, tid,
            f"✅ <b>Carga aplicada</b>\n"
            f"👤 {target_nombre} — +{puntos_val} pts | +{cosmos_val} cosmos\n"
            f"💰 Nuevo saldo: {nuevo_cosmos} cosmos",
            delay=10,
        )

        # ── Log en grupo de administración ────────────────────────────────────
        # FIX: se eliminó la variable local "LOG_GROUP_ID = 2002779047" que
        # sobreescribía el import de config con un valor incorrecto (positivo,
        # sin el prefijo -100 de los supergrupos). Ahora se usa el valor
        # importado al inicio del módulo: LOG_GROUP_ID = -1002002779047.
        log_texto = (
            f"✏️ #CARGA_PUNTOS\n"
            f"• De: {admin_nombre} [{uid}]\n"
            f"• A: {target_nombre} [{target_id}]\n"
            f"• Puntos: {puntos_val} | Cosmos: {cosmos_val}\n"
            f"• Motivo: {motivo}"
        )
        try:
            self.bot.send_message(LOG_GROUP_ID, log_texto, parse_mode="HTML")
        except Exception as exc:
            logger.warning("[CARGAR] No se pudo enviar log al grupo %s: %s", LOG_GROUP_ID, exc)

        logger.info(
            "[CARGAR] ✅ Completado — Admin %s → %s | +%s pts +%s cosmos | %s",
            uid, target_id, puntos_val, cosmos_val, motivo,
        )

    # =========================================================================
    # /quitar  →  descuenta Cosmos
    # =========================================================================
    def cmd_quitar(self, message) -> None:
        cid = message.chat.id
        tid = _thread_id(message)
        uid = message.from_user.id

        self._try_delete(cid, message.message_id)

        if not self._is_admin(message):
            self._send_temp(cid, tid, "❌ Este comando es solo para administradores.", delay=5)
            return

        cantidad: Optional[int] = None
        for part in reversed((message.text or "").split()[1:]):
            try:
                cantidad = int(part)
                break
            except ValueError:
                continue

        if not cantidad or cantidad <= 0:
            self._send_temp(
                cid, tid,
                "❌ Uso correcto: <code>/quitar @usuario cantidad</code>\n"
                "También podés responder al mensaje del usuario.\n"
                "Ejemplo: <code>/quitar @juan 500</code>",
                delay=10,
            )
            return

        target_id, target_nombre, error = self._resolver_target(message, prefer_mention=True)
        if not target_id:
            self._send_temp(cid, tid, error, delay=8)
            return

        if not db_manager.user_exists(target_id):
            self._send_temp(cid, tid, "❌ El usuario no está registrado en el sistema.", delay=8)
            return

        try:
            ok = economy_service.subtract_credits(
                target_id, cantidad, f"Quita manual por admin {uid}"
            )
            if ok:
                nuevo_saldo = economy_service.get_balance(target_id)
                texto = (
                    f"✅ <b>Cosmos descontados</b>\n\n"
                    f"👤 Usuario: {target_nombre}\n"
                    f"➖ Cantidad: -{cantidad} Cosmos\n"
                    f"💰 Nuevo saldo: {nuevo_saldo} Cosmos"
                )
                logger.info("💰 Admin %s quitó %s Cosmos a %s", uid, cantidad, target_id)
            else:
                texto = "❌ Error al quitar Cosmos (saldo insuficiente o error interno)."
        except Exception as exc:
            texto = f"❌ Error: {exc}"
            logger.error("[QUITAR] %s", exc)

        self._send_temp(cid, tid, texto, delay=10)

    # =========================================================================
    # /remover  →  banea / mueve a EXMIEMBROS
    # =========================================================================
    def cmd_remover(self, message) -> None:
        cid = message.chat.id
        tid = _thread_id(message)
        uid = message.from_user.id

        self._try_delete(cid, message.message_id)

        if not self._is_admin(message):
            self._send_temp(cid, tid, "❌ Este comando es solo para administradores.", delay=5)
            return

        parts  = (message.text or "").split()
        motivo = (
            " ".join(parts[1:]) if message.reply_to_message else " ".join(parts[2:])
        ) or "No especificado"

        target_id, target_nombre, error = self._resolver_target(message, prefer_mention=True)
        if not target_id:
            self._send_temp(
                cid, tid,
                error or (
                    "❌ Uso correcto: <code>/remover @usuario [motivo]</code>\n"
                    "Ejemplo: <code>/remover @juan Inactividad</code>"
                ),
                delay=10,
            )
            return

        if not db_manager.user_exists(target_id):
            self._send_temp(cid, tid, "❌ El usuario no está registrado en el sistema.", delay=8)
            return

        try:
            ok = user_service.ban_user(target_id, motivo)
            texto = (
                f"✅ <b>Usuario removido</b>\n\n"
                f"👤 Usuario: {target_nombre}\n"
                f"📋 Motivo: {motivo}\n\n"
                "El usuario ha sido movido a EXMIEMBROS."
                if ok else "❌ Error al remover usuario."
            )
            if ok:
                logger.info("🚫 Admin %s removió a %s — Motivo: %s", uid, target_id, motivo)
        except Exception as exc:
            texto = f"❌ Error: {exc}"
            logger.error("[REMOVER] %s", exc)

        self._send_temp(cid, tid, texto, delay=10)

    # =========================================================================
    # /alerta  →  listas de inactividad del mes
    # =========================================================================
    def cmd_alerta(self, message) -> None:
        """
        Genera dos listas de inactividad para el mes en curso:

          1. Idols con menos de 4 roles jugados (columna jugando < 4).
          2. Clientes con menos de 600 puntos acumulados (columna puntos < 600).

        Solo admins pueden ejecutarlo. El mensaje se borra tras 60 segundos.
        """
        cid = message.chat.id
        tid = _thread_id(message)
        uid = message.from_user.id

        self._try_delete(cid, message.message_id)

        if not self._is_admin(message):
            self._send_temp(cid, tid, "❌ Este comando es solo para administradores.", delay=5)
            return

        try:
            idols_inactivas = db_manager.execute_query(
                "SELECT nombre, jugando FROM USUARIOS "
                "WHERE clase = 'idol' AND jugando < 4 "
                "ORDER BY jugando ASC, nombre ASC"
            ) or []

            clientes_inactivos = db_manager.execute_query(
                "SELECT nombre, puntos FROM USUARIOS "
                "WHERE clase = 'cliente' AND puntos < 600 "
                "ORDER BY puntos ASC, nombre ASC"
            ) or []

        except Exception as exc:
            logger.error("[ALERTA] Error consultando BD: %s", exc)
            self._send_temp(cid, tid, f"❌ Error al consultar la base de datos: {exc}", delay=10)
            return

        # ── Bloque idols ──────────────────────────────────────────────────────
        if idols_inactivas:
            lineas_idols = [
                f"  • {row['nombre']} — {row['jugando']} rol{'es' if row['jugando'] != 1 else ''}"
                for row in idols_inactivas
            ]
            bloque_idols = (
                f"👑 <b>Idols con menos de 4 roles ({len(idols_inactivas)})</b>\n"
                + "\n".join(lineas_idols)
            )
        else:
            bloque_idols = "👑 <b>Idols con menos de 4 roles</b>\n  — Todas al día ✅"

        # ── Bloque clientes ───────────────────────────────────────────────────
        if clientes_inactivos:
            lineas_clientes = [
                f"  • {row['nombre']} — {row['puntos']} pts"
                for row in clientes_inactivos
            ]
            bloque_clientes = (
                f"🎭 <b>Clientes con menos de 600 puntos ({len(clientes_inactivos)})</b>\n"
                + "\n".join(lineas_clientes)
            )
        else:
            bloque_clientes = "🎭 <b>Clientes con menos de 600 puntos</b>\n  — Todos al día ✅"

        texto = (
            f"⚠️ <b>Alerta de inactividad del mes</b>\n\n"
            f"{bloque_idols}\n\n"
            f"{bloque_clientes}"
        )

        logger.info(
            "[ALERTA] Admin %s consultó inactividad — %s idols, %s clientes",
            uid, len(idols_inactivas), len(clientes_inactivos),
        )

        self._send_temp(cid, tid, texto, delay=60)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def setup(bot: telebot.TeleBot, admin_ids: Optional[List[int]] = None) -> None:
    """Registra todos los handlers administrativos en el bot."""
    AdminHandlers(bot, admin_ids)