"""
Handlers para Comandos Básicos de Usuarios
Comandos: /start, /help, /registrar, /perfil
"""

import telebot
from telebot import types
import time
import logging
from datetime import date, datetime
from database import db_manager
from funciones import user_service, economy_service
from config import MSG_USUARIO_NO_REGISTRADO, LOG_GROUP_ID
from utils.thread_utils import get_thread_id

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Región emoji
# ─────────────────────────────────────────────────────────────────────────────
_REGION_EMOJI = {
    "KANTO":   "🔴",
    "JOHTO":   "🟡",
    "HOENN":   "🟢",
    "SINNOH":  "🔵",
    "TESELIA": "⚫",
    "KALOS":   "🩵",
    "ALOLA":   "🌺",
    "GALAR":   "🟣",
    "PALDEA":  "🟠",
}

_TODAS_REGIONES = list(_REGION_EMOJI.keys())

# MMR formats disponibles
_MMR_FORMATS = ["1v1", "2v2", "3v3"]

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _delete_after(bot, chat_id: int, message_id: int, delay: float = 10.0) -> None:
    import threading
    def _del():
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass
    threading.Timer(delay, _del).start()

def _borrar_perfil(bot, chat_id: int, message_id: int) -> None:
    """Elimina un mensaje ignorando errores (mensaje ya borrado, sin permisos, etc.)."""
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass

def _tiempo_en_grupo(registro_str: str) -> str:
    """
    Recibe la fecha de registro (string 'YYYY-MM-DD' o datetime).
    Devuelve algo como '2 años, 3 meses' o '5 meses, 12 días'.
    """
    try:
        if isinstance(registro_str, str):
            registro = datetime.strptime(registro_str[:10], "%Y-%m-%d").date()
        elif isinstance(registro_str, datetime):
            registro = registro_str.date()
        else:
            registro = registro_str

        hoy   = date.today()
        delta = hoy - registro
        dias  = delta.days

        anios   = dias // 365
        meses   = (dias % 365) // 30
        dias_r  = (dias % 365) % 30

        partes = []
        if anios:
            partes.append(f"{anios} año{'s' if anios > 1 else ''}")
        if meses:
            partes.append(f"{meses} mes{'es' if meses > 1 else ''}")
        if not partes:
            partes.append(f"{max(0, dias_r)} día{'s' if dias_r != 1 else ''}")

        return ", ".join(partes)
    except Exception:
        return "—"

def _enviar_log_registro(
    bot,
    uid: int,
    nombre: str,
    clase: str,
    idol_name,
    es_nuevo: bool,
    clase_anterior,
    idol_anterior,
) -> None:
    """Envía un log de registro/cambio al canal LOG_GROUP_ID."""
    try:
        mencion = f'<a href="tg://user?id={uid}">{nombre}</a>'

        if es_nuevo:
            if clase == "idol":
                motivo = f"Nuevo registro como idol: <b>{idol_name}</b>"
            else:
                motivo = "Nuevo registro como <b>cliente</b>"
        else:
            if clase_anterior == "cliente" and clase == "idol":
                motivo = f"Cambió de <b>cliente</b> a idol: <b>{idol_name}</b>"
            elif clase_anterior == "idol" and clase == "cliente":
                motivo = f"Cambió de idol (<b>{idol_anterior}</b>) a <b>cliente</b>"
            elif clase == "idol" and idol_anterior and idol_name and idol_anterior != idol_name:
                motivo = f"Cambió de idol: <b>{idol_anterior}</b> → <b>{idol_name}</b>"
            elif clase == "idol":
                motivo = f"Actualizó registro como idol: <b>{idol_name}</b>"
            else:
                motivo = f"Actualizó registro como <b>{clase}</b>"

        log_texto = (
            f"✏️ #REGISTRO\n"
            f"• De: {mencion} [{uid}]\n"
            f"• {motivo}"
        )
        bot.send_message(LOG_GROUP_ID, log_texto, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"[REGISTRAR] No se pudo enviar log: {e}")


class BasicUserHandlers:
    """Handlers para comandos básicos de usuarios"""
    
    def __init__(self, bot: telebot.TeleBot):
        self.bot = bot
        self._register_handlers()
    
    def _register_handlers(self):
        """Registra todos los handlers de este módulo"""
        self.bot.register_message_handler(self.cmd_start, commands=['start'])
        self.bot.register_message_handler(self.cmd_help, commands=['ayuda', 'help'])
        self.bot.register_message_handler(self.cmd_registrar, commands=['registrar'])
        self.bot.register_message_handler(self.cmd_perfil, commands=['perfil'])
        self.bot.register_message_handler(self.cmd_entrenador,  commands=["entrenador"])
        self.bot.register_callback_query_handler(
            self.cb_entrenador,
            func=lambda c: c.data and c.data.startswith("entrenador_"),
        )
    
    def cmd_start(self, message):
        """
        Comando /start - Bienvenida al bot
        """
        cid = message.chat.id
        uid = message.from_user.id
        tid = get_thread_id(message)
        
        # Verificar si viene del deep link de pokemon
        args = message.text.split()
        if len(args) > 1 and args[1] == "pokemon":
            # TODO: Integrar con sistema Pokemon
            texto = "🎮 Menú Pokémon próximamente..."
            self.bot.send_message(cid, texto, message_thread_id=tid)
            return
        
        # Start normal
        texto = """
¡Bienvenido a UniverseBot! 👋

Soy tu asistente para gestionar roles, Cosmos y mucho más.

📋 **Comandos principales:**
• /help - Ver todos los comandos
• /registrar - Registrarte en el sistema
• /perfil - Ver tu perfil
• /tablero - Ver ranking de Cosmos
• /puntos - Ver tus estadísticas

💰 **Sistema de Cosmos:**
• /creditos - Comprar boletos/items
• /slots [cantidad] - Jugar tragaperras

🎭 **Sistema de roles:**
• /rol @usuario - Iniciar rol
• /finrol [ID] - Finalizar rol
• /dispo - Entrar en cola

¡Comienza registrándote con /registrar!
"""
        self.bot.send_message(cid, texto, message_thread_id=tid)
    
    def cmd_help(self, message):
        """
        Comando /help - Muestra ayuda según el rango del usuario
        """
        cid = message.chat.id
        uid = message.from_user.id
        tid = get_thread_id(message)
        
        self.bot.delete_message(cid, message.message_id)
        
        try:
            rango = self.bot.get_chat_member(cid, uid).status
            is_admin = rango in ['creator', 'administrator']
        except:
            is_admin = False
        
        if is_admin:
            texto = """<b><u>Comandos para admins</u></b>

► /remover @usuario - Quita un usuario de la base de datos
► /cargar @usuario [cantidad] - Acredita Cosmos
► /quitar @usuario [cantidad] - Desacredita Cosmos
► /alerta - Usuarios en peligro de expulsión
► /finrol [ID] - Finaliza un rol (desde admin)

<b><u>Comandos para usuarios</u></b>

► /registrar [clase] - Registrarse (cliente o idol)
► /tablero - Ver tabla de Cosmos
► /ranking - Top usuarios por puntos
► /puntos [@usuario] - Ver estadísticas
► /perfil - Ver tu perfil completo
► /todos - Etiquetar todos los usuarios

<b><u>Sistema de roles</u></b>

► /rol @usuario - Iniciar rol
► /finrol [ID] - Finalizar rol activo
► /dispo - Entrar en cola de búsqueda
► /salir - Salir de la cola
► /ver - Ver cola actual

<b><u>Sistema económico</u></b>

► /slots [apuesta] - Jugar tragaperras
► /creditos - Ver tu saldo
► /transferir @usuario [cantidad] - Transferir Cosmos

<b><u>Sistema de apuestas</u></b>

► /apuestas - Ver apuestas disponibles
► /apostar [ID] [cantidad] [opcion] - Realizar apuesta
► /misapuestas - Ver tus apuestas activas
"""
        else:
            texto = """<b><u>Comandos disponibles</u></b>

<b>📋 Básicos:</b>
► /registrar [clase] - Registrarse como cliente o idol
► /perfil - Ver tu perfil
► /tablero - Ver ranking de Cosmos
► /ranking - Top usuarios por puntos
► /puntos [@usuario] - Ver estadísticas

<b>🎭 Roles:</b>
► /rol @usuario - Iniciar rol
► /finrol [ID] - Finalizar rol activo
► /dispo - Entrar en cola de búsqueda
► /salir - Salir de la cola

<b>💰 Economía:</b>
► /creditos - Ver tu saldo
► /slots [cantidad] - Jugar tragaperras
► /transferir @usuario [cantidad] - Transferir Cosmos

<b>🎲 Apuestas:</b>
► /apuestas - Ver apuestas disponibles
► /apostar [ID] [cantidad] [opcion] - Realizar apuesta

<b>ℹ️ Ayuda:</b>
► /help - Ver esta ayuda
► /todos - Etiquetar todos los usuarios
"""
        
        m = self.bot.send_message(cid, texto, parse_mode='html', message_thread_id=tid)
        time.sleep(30)
        self.bot.delete_message(cid, m.message_id)
    
    # =========================================================================
    # /entrenador
    # =========================================================================
    def cmd_entrenador(self, message):
        cid = message.chat.id
        uid = message.from_user.id
        tid = get_thread_id(message)

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        user_info = user_service.get_user_info(uid)
        if not user_info:
            m = self.bot.send_message(
                cid, "❌ No estás registrado. Usa /registrar.",
                message_thread_id=tid,
            )
            _delete_after(self.bot, cid, m.message_id)
            return

        texto, markup = self._build_entrenador_page(uid, 0)
        self.bot.send_message(
            cid, texto, parse_mode="HTML",
            reply_markup=markup, message_thread_id=tid,
        )

    def cb_entrenador(self, call):
        try:
            _, target_uid, pagina = call.data.split("_", 2)
            target_uid = int(target_uid)
            pagina     = int(pagina)

            if call.from_user.id != target_uid:
                self.bot.answer_callback_query(call.id, "❌ No es tu perfil.")
                return

            texto, markup = self._build_entrenador_page(target_uid, pagina)
            self.bot.edit_message_text(
                texto,
                chat_id      = call.message.chat.id,
                message_id   = call.message.message_id,
                parse_mode   = "HTML",
                reply_markup = markup,
            )
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"[ENTRENADOR CB] {e}")
            self.bot.answer_callback_query(call.id, "❌ Error.")

    def _build_entrenador_page(self, user_id: int, pagina: int):
        """
        Construye el texto e InlineKeyboard del perfil entrenador.
        Usa la instancia global `gimnasio_service` (no la clase) para acceder
        a self.lideres, self.elite_four, self.obtener_medallas, etc.
        """
        # ── Importar instancia global (no la clase) ───────────────────────────
        from pokemon.services.gimnasio_service import gimnasio_service as _gym_svc

        # ── Medallas del usuario ──────────────────────────────────────────────
        try:
            rows = db_manager.execute_query(
                "SELECT lider_id FROM MEDALLAS_USUARIOS WHERE userID = ?", (user_id,)
            ) or []
            medallas_set = {(r["lider_id"] or "").lower() for r in rows}
        except Exception:
            medallas_set = set()

        # ── MMR ───────────────────────────────────────────────────────────────
        mmr_data = {}
        try:
            r = db_manager.execute_query(
                "SELECT mmr_1v1, mmr_2v2, mmr_3v3 FROM LADDER_STATS WHERE userID = ?",
                (user_id,),
            )
            if r:
                mmr_data = {k: (v if v is not None else 1000) for k, v in dict(r[0]).items()}
        except Exception:
            pass

        # ── Determinar páginas disponibles ────────────────────────────────────
        # IDs de Kanto no tienen prefijo de región
        _KANTO_IDS = {
            "brock","misty","surge","erika","koga","sabrina","blaine","giovanni",
            "kanto_e4_lorelei","kanto_e4_bruno","kanto_e4_agatha",
            "kanto_e4_lance","kanto_champion",
        }

        def _medallas_de_region(region: str) -> list:
            if region == "KANTO":
                return [m for m in medallas_set if m in _KANTO_IDS]
            prefijo = region.lower() + "_"
            return [m for m in medallas_set if m.startswith(prefijo)]

        paginas_regiones = [r for r in _TODAS_REGIONES if _medallas_de_region(r)]
        if not paginas_regiones:
            paginas_regiones = ["KANTO"]

        pagina = max(0, min(pagina, len(paginas_regiones) - 1))
        region_actual = paginas_regiones[pagina]
        emoji_region  = _REGION_EMOJI.get(region_actual, "🗺️")
        med_region    = _medallas_de_region(region_actual)

        # ── ¿Es campeón? ──────────────────────────────────────────────────────
        champion_id = "kanto_champion" if region_actual == "KANTO" \
                      else f"{region_actual.lower()}_champion"
        es_campeon  = champion_id in medallas_set

        # ── Mapa de datos de líder por ID ──────────────────────────────────────
        # Usamos la instancia global; sus atributos son listas de dicts
        gym_data_map: dict = {}
        try:
            for lider in _gym_svc.lideres:
                gym_data_map[lider["id"]] = lider
            for miembro in _gym_svc.elite_four:
                gym_data_map[miembro["id"]] = miembro
        except Exception as e:
            logger.warning(f"[ENTRENADOR] No se pudo cargar gym_data_map: {e}")

        # ── Líneas de medallas ────────────────────────────────────────────────
        lineas_medallas = []
        for lid in sorted(med_region):
            info    = gym_data_map.get(lid, {})
            nombre  = info.get("nombre",  lid.replace("_", " ").title())
            medalla = info.get("medalla", "Insignia")
            em      = info.get("emoji",  "🏅")
            lineas_medallas.append(f"  {em} <b>{medalla}</b>  <i>({nombre})</i>")

        if not lineas_medallas:
            lineas_medallas = ["  — Aún sin medallas en esta región —"]

        campeon_txt = "  👑 <b>¡CAMPEÓN DE LA LIGA!</b>" if es_campeon \
                      else "  ⏳ Liga no completada"

        # ── MMR ───────────────────────────────────────────────────────────────
        mmr_lines = [
            f"  <code>{fmt.upper()}</code>: <b>{mmr_data.get(f'mmr_{fmt}', 1000)}</b>"
            for fmt in _MMR_FORMATS
        ]

        user_info = user_service.get_user_info(user_id)
        nombre_entrenador = (user_info or {}).get("nombre", f"Entrenador #{user_id}")

        texto = (
            f"🎮 <b>Perfil Entrenador — {nombre_entrenador}</b>\n\n"
            f"{emoji_region} <b>Región: {region_actual.capitalize()}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏅 <b>Medallas ({len(med_region)}):</b>\n"
            f"{chr(10).join(lineas_medallas)}\n\n"
            f"🏆 <b>Liga:</b>\n"
            f"{campeon_txt}\n\n"
            f"📊 <b>MMR Ladder:</b>\n"
            f"{chr(10).join(mmr_lines)}\n\n"
            f"<i>Página {pagina + 1} / {len(paginas_regiones)}</i>"
        )

        # ── Botones ───────────────────────────────────────────────────────────
        markup = types.InlineKeyboardMarkup(row_width=2)
        btns = []
        if pagina > 0:
            btns.append(types.InlineKeyboardButton(
                "⬅️ Anterior",
                callback_data=f"entrenador_{user_id}_{pagina - 1}",
            ))
        if pagina < len(paginas_regiones) - 1:
            btns.append(types.InlineKeyboardButton(
                "Siguiente ➡️",
                callback_data=f"entrenador_{user_id}_{pagina + 1}",
            ))
        if btns:
            markup.add(*btns)

        return texto, markup


    def cmd_registrar(self, message):
        """
        Comando /registrar — Registra un nuevo usuario o cambia su clase/idol.

        Uso:
            /registrar cliente
            /registrar idol Jisoo
            /registrar idol Jennie/Lisa     ← nombres separados por /

        Flujo:
            · Usuario NO registrado → registro gratuito + recompensa de bienvenida.
            · Usuario YA registrado → edición de clase/idol con cobro de cosmos:
                  cambio a idol   → 5000 cosmos
                  cambio a cliente→ 1000 cosmos
        """
        import time
        from config import RECOMPENSA_REGISTRO
        from funciones import economy_service

        cid = message.chat.id
        uid = message.from_user.id
        tid = get_thread_id(message)
        nombre_usuario = message.from_user.username or message.from_user.first_name
        nombre = message.from_user.first_name
        if message.from_user.last_name:
            nombre += f" {message.from_user.last_name}"

        # Intentar borrar el comando (no crítico)
        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception as e:
            logger.debug(f"[REGISTRAR] No se pudo borrar el mensaje de comando: {e}")

        # ── Parsear argumentos ────────────────────────────────────────────────
        parts = message.text.split()

        if len(parts) < 2:
            texto = (
                "❌ Uso incorrecto.\n\n"
                "<b>Uso correcto:</b>\n"
                "• /registrar cliente\n"
                "• /registrar idol [nombre_idol]\n\n"
                "<b>Ejemplos:</b>\n"
                "/registrar idol Jisoo\n"
                "/registrar idol Jennie/Lisa"
            )
            m = self.bot.send_message(cid, texto, parse_mode="html", message_thread_id=tid)
            time.sleep(10)
            try:
                self.bot.delete_message(cid, m.message_id)
            except Exception:
                pass
            return

        clase = parts[1].lower()

        if clase not in ("cliente", "idol"):
            texto = (
                f"❌ Clase inválida: '<b>{clase}</b>'\n\n"
                "Clases disponibles:\n"
                "• cliente\n"
                "• idol"
            )
            m = self.bot.send_message(cid, texto, parse_mode="html", message_thread_id=tid)
            time.sleep(10)
            try:
                self.bot.delete_message(cid, m.message_id)
            except Exception:
                pass
            return

        # Para idol, el nombre es obligatorio
        idol_name = None
        if clase == "idol":
            if len(parts) < 3:
                texto = (
                    "❌ Debes especificar el nombre del idol.\n\n"
                    "<b>Ejemplos:</b>\n"
                    "/registrar idol Jisoo\n"
                    "/registrar idol Jennie/Lisa"
                )
                m = self.bot.send_message(cid, texto, parse_mode="html", message_thread_id=tid)
                time.sleep(10)
                try:
                    self.bot.delete_message(cid, m.message_id)
                except Exception:
                    pass
                return
            idol_name = " ".join(parts[2:])

        # ── Verificar si ya está registrado ───────────────────────────────────
        user_info = user_service.get_user_info(uid)

        if user_info:
            # ── USUARIO YA REGISTRADO: cobrar cosmos y actualizar ─────────────
            COSTO_CAMBIO = {
                "idol":    5000,
                "cliente": 1000,
            }
            costo = COSTO_CAMBIO[clase]
            saldo_actual = economy_service.get_balance(uid)

            if saldo_actual < costo:
                texto = (
                    f"💸 <b>Cosmos insuficientes</b>\n\n"
                    f"Para cambiar tu registro a <b>{clase}</b> necesitas "
                    f"<b>{costo:,} cosmos</b>.\n"
                    f"Tu saldo actual: <b>{saldo_actual:,} cosmos</b>.\n\n"
                    f"Te faltan <b>{costo - saldo_actual:,} cosmos</b> para realizar el cambio."
                )
                m = self.bot.send_message(cid, texto, parse_mode="html", message_thread_id=tid)
                time.sleep(12)
                try:
                    self.bot.delete_message(cid, m.message_id)
                except Exception:
                    pass
                return

            # Cobrar cosmos
            ok_cobro = economy_service.subtract_credits(
                uid, costo, f"Cambio de registro a {clase}"
            )
            if not ok_cobro:
                texto = "❌ Error al procesar el pago. Inténtalo de nuevo."
                m = self.bot.send_message(cid, texto, parse_mode="html", message_thread_id=tid)
                time.sleep(8)
                try:
                    self.bot.delete_message(cid, m.message_id)
                except Exception:
                    pass
                return

            # Actualizar clase e idol en BD
            try:
                from database import db_manager
                db_manager.execute_update(
                    "UPDATE USUARIOS SET clase = ?, idol = ? WHERE userID = ?",
                    (clase, idol_name, uid),
                )
                nuevo_saldo = economy_service.get_balance(uid)

                if clase == "idol":
                    texto = (
                        f"✅ <b>Registro actualizado</b>\n\n"
                        f"Ahora eres <b>Idol</b>: {idol_name}\n"
                        f"💸 Costo: -{costo:,} cosmos\n"
                        f"💰 Saldo restante: {nuevo_saldo:,} cosmos"
                    )
                else:
                    texto = (
                        f"✅ <b>Registro actualizado</b>\n\n"
                        f"Ahora eres <b>Cliente</b>.\n"
                        f"💸 Costo: -{costo:,} cosmos\n"
                        f"💰 Saldo restante: {nuevo_saldo:,} cosmos"
                    )

                logger.info(
                    f"[REGISTRAR] Cambio de clase: {nombre_usuario} ({uid}) → "
                    f"{clase} | -{costo} cosmos"
                )
                _enviar_log_registro(
                    bot=self.bot,
                    uid=uid,
                    nombre=nombre,
                    clase=clase,
                    idol_name=idol_name,
                    es_nuevo=False,
                    clase_anterior=user_info.get("clase"),
                    idol_anterior=user_info.get("idol"),
                )
            except Exception as e:
                # Si falló la actualización, reembolsar el cobro
                economy_service.add_credits(uid, costo, "Reembolso por error en actualización")
                texto = f"❌ Error al actualizar el registro: {e}"
                logger.error(f"[REGISTRAR] Error actualizando clase para {uid}: {e}")

            m = self.bot.send_message(cid, texto, parse_mode="html", message_thread_id=tid)
            time.sleep(12)
            try:
                self.bot.delete_message(cid, m.message_id)
            except Exception:
                pass
            return

        # ── USUARIO NO REGISTRADO: registro normal gratuito ───────────────────
        exito = False
        try:
            exito = user_service.register_user(uid, nombre_usuario, nombre, clase, idol_name)

            if exito:
                # Aplicar recompensa de bienvenida
                try:
                    economy_service.add_credits(
                        uid,
                        RECOMPENSA_REGISTRO,
                        "Recompensa de registro",
                    )
                    logger.info(f"[REGISTRAR] +{RECOMPENSA_REGISTRO} cosmos aplicados a {uid}")
                except Exception as e:
                    logger.error(f"[REGISTRAR] Error aplicando recompensa: {e}")

                if clase == "idol":
                    texto = (
                        f"✅ ¡Bienvenida <b>{idol_name or nombre_usuario}</b>!\n\n"
                        f"Te has registrado como <b>Idol</b> 👑\n\n"
                        f"💰 Cosmos iniciales: {RECOMPENSA_REGISTRO:,}\n"
                        f"📊 Nivel: 1\n\n"
                        f"Usa /help para ver los comandos disponibles."
                    )
                else:
                    texto = (
                        f"✅ ¡Bienvenido <b>{nombre_usuario}</b>!\n\n"
                        f"Te has registrado como <b>Cliente</b> 🎭\n\n"
                        f"💰 Cosmos iniciales: {RECOMPENSA_REGISTRO:,}\n"
                        f"📊 Nivel: 1\n\n"
                        f"Usa /help para ver los comandos disponibles."
                    )

                logger.info(
                    f"[REGISTRAR] Nuevo usuario: {nombre_usuario} ({uid}) — Clase: {clase}"
                )
                _enviar_log_registro(
                    bot=self.bot,
                    uid=uid,
                    nombre=nombre,
                    clase=clase,
                    idol_name=idol_name,
                    es_nuevo=True,
                    clase_anterior=None,
                    idol_anterior=None,
                )
            else:
                texto = "❌ Error al registrar. Inténtalo de nuevo."
                logger.error(f"[REGISTRAR] Falló el registro para: {uid}")

        except Exception as e:
            texto = (
                f"❌ Error al registrar: {e}\n\n"
                "Uso correcto:\n"
                "• /registrar cliente\n"
                "• /registrar idol [nombre_idol]"
            )
            logger.error(f"[REGISTRAR] Excepción en cmd_registrar: {e}")

        m = self.bot.send_message(cid, texto, parse_mode="html", message_thread_id=tid)

        # Solo borrar automáticamente los mensajes de error/aviso, no los de éxito
        if not exito or any(kw in texto for kw in ("Error", "error", "❌")):
            time.sleep(10)
            try:
                self.bot.delete_message(cid, m.message_id)
            except Exception:
                pass
    
    # ─────────────────────────────────────────────────────────────────────────────
    # DENTRO de BasicUserHandlers, con 4 espacios de indentación
    # ─────────────────────────────────────────────────────────────────────────────
    def cmd_perfil(self, message: telebot.types.Message) -> None:
        """
        Comando /perfil — envía la foto de perfil del usuario con formato estético.
        Soporta usuarios con y sin @username.
        """
        cid = message.chat.id
        uid = message.from_user.id
        tid = get_thread_id(message)
        import threading

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        user_info = user_service.get_user_info(uid)
        if not user_info:
            m = self.bot.send_message(
                cid,
                "⚠️ No estás registrado. Usa /registrar",
                message_thread_id=tid,
            )
            time.sleep(5)
            try:
                self.bot.delete_message(cid, m.message_id)
            except Exception:
                pass
            return

        # ── Datos del usuario ─────────────────────────────────────────────────
        nombre            = user_info.get("nombre", "—")
        clase             = user_info.get("clase", "cliente")
        idol_nombre       = user_info.get("idol", None)
        nivel             = user_info.get("nivel", 1)
        experiencia       = user_info.get("experiencia", 0)
        wallet            = user_info.get("wallet", 0)
        puntos            = user_info.get("puntos", 0)
        jugando           = user_info.get("jugando", 0)
        rol_hist          = user_info.get("rol_hist", 0)
        nickname          = user_info.get("nickname", "Normal")
        registro          = user_info.get("registro", None)
        ultima_recompensa = user_info.get("ultima_recompensa_diaria", "—") or "—"

        from funciones.user_experience import exp_requerida_usuario
        xp_req = exp_requerida_usuario(nivel)
        estadia     = _tiempo_en_grupo(registro) if registro else "—"
        cuenta_tipo = "VIP" if str(nickname).upper() == "VIP" else "Normal"
        clase_display = "idol" if clase == "idol" else "Usuario"

        username_raw = message.from_user.username
        mencion = (
            f"@{username_raw}"
            if username_raw
            else f'<a href="tg://user?id={uid}">{nombre}</a>'
        )

        idol_linea = (
            f"\n                ⋆ {idol_nombre}⋆"
            if (clase == "idol" and idol_nombre)
            else ""
        )

        # ── Texto con formato estético ────────────────────────────────────────
        texto = (
            "｡･:*:･ﾟ★,｡･:*:･ﾟ☆   ｡･:*:･ﾟ★,｡･:*:･ﾟ☆\n"
            "｡ﾟﾟ･｡･ﾟﾟ｡\n"
            f"ﾟ。[ <b>{nombre}</b> ]\n"
            f"<i>𝑪𝒖𝒆𝒏𝒕𝒂 {cuenta_tipo}!</i>\n"
            f"*.·:·.☽✧    Nivel: {nivel}  Exp: {experiencia} / {xp_req}    ✧☾.·:·.*\n"
            "     ₊‧.°.⋆ •˚₊‧⋆.\n"
            f"⊹₊ㆍ✿ㆍ{mencion}ㆍ✿ㆍ₊⊹\n"
            f"      ⊹ ˚ . <i>𝑪𝒍𝒂𝒔𝒆: {clase_display}</i> ｡ﾟ⋆ ⊹"
            f"{idol_linea}\n"
            "                    *.·:·.☽✧    ✦    ✧☾.·:·.*\n"
            f" <i>𝑬𝒔𝒕𝒂𝒅𝒊́𝒂:</i> {estadia} (desde {registro or '—'})\n"
            f"  <i>𝑼𝒍𝒕𝒊𝒎𝒐 𝑷𝒐𝒔𝒕</i> ➵ {ultima_recompensa}\n"
            f"   <i>𝑪𝒐𝒔𝒎𝒐𝒔</i> ➵ {wallet}\n"
            f"     <i>𝑹𝒐𝒍𝒆𝒔 𝒕𝒐𝒕𝒂𝒍𝒆𝒔</i> ➵ {rol_hist}\n"
            f"      <i>𝑹𝒐𝒍𝒆𝒔 𝒅𝒆𝒍 𝒎𝒆𝒔</i> ➵ {jugando}\n"
            f"       <i>𝑷𝒖𝒏𝒕𝒐𝒔</i> ➵ {puntos}\n"
            "        <i>Pase de batalla</i> ➵ Próximamente\n\n"
            "☞* . °•★|•°∵ Universe ∵°•|☆•° . *\n"
            "༄ ⋆ 🌙 ｡˚ Disfruta tu estancia! 🧷 ✧ ˚."
        )

        # ── Intentar obtener foto de perfil ───────────────────────────────────
        foto_enviada = False
        try:
            from typing import cast
            pict = self.bot.get_user_profile_photos(uid, offset=0, limit=1)
            if pict.total_count > 0 and pict.photos:
                photo_sizes = cast(list[telebot.types.PhotoSize], pict.photos[0])
                mejor = max(photo_sizes, key=lambda p: p.width * p.height)
                m = self.bot.send_photo(
                    cid,
                    mejor.file_id,
                    caption=texto,
                    parse_mode="HTML",
                    message_thread_id=tid,
                )
                threading.Timer(30.0, _borrar_perfil, args=(self.bot, cid, m.message_id)).start()
                foto_enviada = True
        except Exception as e:
            logger.warning(f"[PERFIL] No se pudo obtener foto de perfil: {e}")

        if not foto_enviada:
            m = self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)
            threading.Timer(30.0, _borrar_perfil, args=(self.bot, cid, m.message_id)).start()

def setup(bot: telebot.TeleBot):
    """Función para registrar los handlers"""
    BasicUserHandlers(bot)
    logger.info("✅ BasicUserHandlers registrados")

