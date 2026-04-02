# -*- coding: utf-8 -*-
"""
Comandos: /pokemon, /profesor, /spawn, /salvaje
"""

import telebot
from telebot import types
import time
import threading
import logging

from funciones import user_service
from config import MSG_USUARIO_NO_REGISTRADO
from pokemon.services import pokemon_service, spawn_service
from utils.thread_utils import get_thread_id

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS DE MÓDULO
# ─────────────────────────────────────────────────────────────────────────────

def _delete_after(bot, chat_id: int, message_id: int, delay: float = 10.0) -> None:
    """Borra un mensaje después de `delay` segundos sin bloquear el hilo."""
    def _del() -> None:
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass
    threading.Timer(delay, _del).start()


def calcular_costo_salvaje(user_id: int) -> int:
    """
    Calcula el costo de /salvaje según las medallas del usuario.

    Criterio: 50% del reward promedio esperado a ese rango de niveles.
    Fórmula reward: randint(1,10) * nivel → promedio = 5.5 * nivel_promedio
    Costo = round(5.5 * nivel_promedio * 0.50)
    """
    try:
        nivel_min, nivel_max = spawn_service.obtener_nivel_spawn_por_medallas(user_id)
        nivel_promedio = (nivel_min + nivel_max) / 2
        costo = round(5.5 * nivel_promedio * 0.50)
        return max(5, costo)   # mínimo 5 cosmos
    except Exception:
        return 10              # fallback seguro


class PokemonHandlers:
    """
    Handlers para comandos de Pokémon
    Integrado con servicios profesionales de Pokemon
    """

    def __init__(self, bot: telebot.TeleBot):
        self.bot = bot

        # Dict privado de invocaciones /salvaje.
        # Clave:  user_id (int)
        # Valor:  dict con los datos del spawn generado
        #         {"pokemon_id": int, "nivel": int|None, "shiny": bool, "nombre": str}
        #
        # IMPORTANTE: este dict es completamente independiente de
        # spawn_service.spawns_activos.  Los spawns automáticos (thread_id)
        # y las invocaciones privadas (user_id) son dos sistemas que nunca
        # comparten estado.
        self._invocaciones_privadas: dict[int, dict] = {}

        self._register_handlers()
        self._register_callbacks()

    # ──────────────────────────────────────────────────────────────────────────
    # REGISTRO DE HANDLERS Y CALLBACKS
    # ──────────────────────────────────────────────────────────────────────────

    def _register_handlers(self):
        """Registra todos los handlers de mensajes de este módulo."""
        self.bot.register_message_handler(self.cmd_pokemon,  commands=['pokemon'])
        self.bot.register_message_handler(self.cmd_profesor, commands=['profesor'])
        self.bot.register_message_handler(self.cmd_salvaje,  commands=['salvaje'])
        self.bot.register_message_handler(self.cmd_pokedex,  commands=['pokedex'])

        # ── Pasos de guardería: mensajes de TEXTO en GRUPO (excluye comandos) ─
        self.bot.register_message_handler(
            self._handle_texto_grupo,
            func=lambda m: (
                m.chat.type in ('group', 'supergroup')
                and m.content_type == 'text'
                and not (m.text or '').startswith('/')
            ),
        )

        # ── Captura de mote tras eclosión: solo en DM (excluye comandos) ──────
        self.bot.register_message_handler(
            self._handle_texto_privado,
            func=lambda m: (
                m.chat.id == m.from_user.id
                and m.content_type == 'text'
                and not (m.text or '').startswith('/')
            ),
        )

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('mt_'))
        def callback_mt(call):
            from pokemon.mt_system import handle_mt_callback
            handle_mt_callback(call, self.bot)

    def _register_callbacks(self):
        """Registra callbacks para botones inline del módulo Pokémon."""

        # ── Starters (pantalla del profesor) ──────────────────────────────────
        @self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('starter_')
        )
        def callback_starter(call):
            self.callback_elegir_starter(call)

        # ── Menú principal Pokémon (pokemenu_*) ───────────────────────────────
        @self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('pokemenu_')
        )
        def callback_pokemenu(call):
            from pokemon.menu_pokemon import MenuPokemon
            MenuPokemon.procesar_callback(call, self.bot)

        # ── Mochila (pokebag_*) ───────────────────────────────────────────────
        @self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('pokebag_')
        )
        def callback_pokebag(call):
            from pokemon.menu_pokemon import MenuPokemon
            MenuPokemon.procesar_callback(call, self.bot)

        # ── Tienda Pokémon (pokeshop_*) ───────────────────────────────────────
        @self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('pokeshop_')
        )
        def callback_pokeshop(call):
            from pokemon.menu_pokemon import MenuPokemon
            try:
                self.bot.answer_callback_query(call.id)
            except Exception:
                pass
            MenuPokemon.procesar_callback(call, self.bot)

        # ── /salvaje — botón exclusivo del dueño ──────────────────────────────
        @self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('salvaje_combatir_')
        )
        def callback_salvaje_combatir(call):
            self._callback_salvaje_combatir(call)

        # ── MTs ───────────────────────────────────────────────────────────────
        @self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('mt_')
        )
        def callback_mt(call):
            from pokemon.mt_system import handle_mt_callback
            handle_mt_callback(call, self.bot)

    # ──────────────────────────────────────────────────────────────────────────
    # TEXTO EN GRUPO (pasos de guardería)
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_texto_grupo(self, message):
        """
        Intercepta mensajes de texto en el grupo para sumar pasos a los huevos
        del usuario.
        """
        from pokemon.guarderia_steps import sumar_pasos_mensaje
        sumar_pasos_mensaje(self.bot, message)

    # ──────────────────────────────────────────────────────────────────────────
    # TEXTO PRIVADO (captura de mote tras eclosión)
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_texto_privado(self, message):
        """
        Intercepta mensajes de texto en chat privado para capturar el apodo
        de un Pokémon recién nacido.
        """
        from pokemon.guarderia_steps import interceptar_mote
        interceptar_mote(self.bot, message)

    # ──────────────────────────────────────────────────────────────────────────
    # /pokemon
    # ──────────────────────────────────────────────────────────────────────────

    def cmd_pokemon(self, message):
        """
        Comando /pokemon — Menú principal de Pokémon.
        Bloqueado si el usuario tiene una batalla activa.
        """
        from funciones import user_service
        from pokemon.menu_pokemon import MenuPokemon
        from config import MSG_USUARIO_NO_REGISTRADO

        uid = message.from_user.id
        cid = message.chat.id

        from config import CANAL_ID, POKECLUB

        tid = get_thread_id(message)
        es_privado   = message.chat.type == 'private'
        es_pokeclub  = (message.chat.id == CANAL_ID and tid == POKECLUB)

        if not es_privado and not es_pokeclub:
            try:
                self.bot.delete_message(message.chat.id, message.message_id)
                m = self.bot.send_message(
                    cid, "❌ Solo puedes usar este comando en pokeclub!.",
                    message_thread_id=tid,
                )
                time.sleep(5)
                self.bot.delete_message(cid, m.message_id)
            except Exception:
                pass
            return

        user_info = user_service.get_user_info(uid)
        if not user_info:
            m = self.bot.send_message(
                cid, MSG_USUARIO_NO_REGISTRADO,
                message_thread_id=getattr(message, "message_thread_id", None),
            )
            time.sleep(5)
            try:
                self.bot.delete_message(cid, m.message_id)
            except Exception:
                pass
            return

        try:
            from pokemon.wild_battle_system import wild_battle_manager
            if wild_battle_manager.has_active_battle(uid):
                m = self.bot.send_message(
                    cid,
                    "⚔️ <b>¡Estás en combate!</b>\n\n"
                    "No puedes abrir el menú Pokémon durante una batalla activa.\n"
                    "Termina o huye del combate primero.",
                    parse_mode="HTML",
                    message_thread_id=getattr(message, "message_thread_id", None),
                )
                time.sleep(5)
                try:
                    self.bot.delete_message(cid, m.message_id)
                    self.bot.delete_message(cid, message.message_id)
                except Exception:
                    pass
                return
        except Exception:
            pass

        try:
            from pokemon.pvp_battle_system import pvp_manager
            if pvp_manager.has_active_battle(uid):
                m = self.bot.send_message(
                    cid,
                    "⚔️ <b>¡Estás en un combate PvP!</b>\n\nTermínalo primero.",
                    parse_mode="HTML",
                    message_thread_id=getattr(message, "message_thread_id", None),
                )
                time.sleep(5)
                try:
                    self.bot.delete_message(cid, m.message_id)
                    self.bot.delete_message(cid, message.message_id)
                except Exception:
                    pass
                return
        except Exception:
            pass

        MenuPokemon.mostrar_menu_principal(uid, self.bot, message)

    # ──────────────────────────────────────────────────────────────────────────
    # /profesor — Elige starter según la región activa del servidor
    # ──────────────────────────────────────────────────────────────────────────

    def cmd_profesor(self, message):
        """
        /profesor — Elige starter UNA VEZ por región.

        - Lee la región activa desde config.POKEMON_REGION_SERVIDOR.
        - Carga los starters dinámicamente desde pokemon.region_config.get_starters().
        - Verifica que el usuario NO tenga ya Pokémon en esa región.
        - Advierte qué Pokémon del equipo actual irán al PC antes de confirmar.
        """
        from config import CANAL_ID, POKECLUB, POKEMON_REGION_SERVIDOR
        from database import db_manager
        from pokemon.region_config import get_starters

        uid = message.from_user.id
        cid = message.chat.id
        tid = get_thread_id(message)

        es_privado  = message.chat.type == 'private'
        es_pokeclub = (cid == CANAL_ID and tid == POKECLUB)

        if not es_privado and not es_pokeclub:
            try:
                self.bot.delete_message(cid, message.message_id)
                m = self.bot.send_message(
                    cid, "❌ Solo puedes usar este comando en pokeclub!.",
                    message_thread_id=tid,
                )
                time.sleep(5)
                self.bot.delete_message(cid, m.message_id)
            except Exception:
                pass
            return

        # ── Región activa ─────────────────────────────────────────────────────
        # POKEMON_REGION_SERVIDOR puede cambiar mientras el bot corre; se lee
        # en tiempo de ejecución para siempre reflejar el valor actual.
        region_actual = POKEMON_REGION_SERVIDOR.upper().strip()

        # ── Verificar si ya tiene Pokémon en ESTA región ──────────────────────
        try:
            ya_tiene = db_manager.execute_query(
                "SELECT COUNT(*) as total FROM POKEMON_USUARIO "
                "WHERE userID = ? AND region = ?",
                (uid, region_actual),
            )
            if ya_tiene and ya_tiene[0]["total"] > 0:
                m = self.bot.send_message(
                    cid,
                    f"❌ Ya elegiste tu Pokémon inicial en <b>{region_actual.capitalize()}</b>.\n"
                    "Solo puedes elegir un starter una vez por región.",
                    parse_mode="HTML",
                    message_thread_id=tid,
                )
                _delete_after(self.bot, cid, m.message_id, 8)
                return
        except Exception as e:
            logger.error(f"[PROFESOR] Error verificando región: {e}")

        try:
            # ── Cargar starters de la región activa ───────────────────────────
            starters = get_starters(region_actual)

            if not starters:
                m = self.bot.send_message(
                    cid,
                    f"⚠️ No se encontraron starters para la región <b>{region_actual}</b>.\n"
                    "Contacta a un administrador.",
                    parse_mode="HTML",
                    message_thread_id=tid,
                )
                _delete_after(self.bot, cid, m.message_id, 10)
                return

            # ── Botones inline ────────────────────────────────────────────────
            markup = types.InlineKeyboardMarkup(row_width=3)
            markup.add(*[
                types.InlineKeyboardButton(
                    f"{s['emoji']} {s['nombre']}",
                    callback_data=s["callback"],   # ej: "starter_152"
                )
                for s in starters
            ])

            # ── Descripción de cada starter ───────────────────────────────────
            descripciones = "\n".join(
                f"{s['emoji']} <b>{s['nombre']}</b> (#{s['id']})"
                for s in starters
            )

            # ── Aviso: equipo actual irá al PC ────────────────────────────────
            equipo_actual = pokemon_service.obtener_equipo(uid)
            aviso_pc = ""
            if equipo_actual:
                nombres = ", ".join(p.mote or p.nombre for p in equipo_actual)
                aviso_pc = (
                    f"\n\n⚠️ Tu equipo actual (<b>{nombres}</b>) "
                    f"será guardado en el PC al elegir."
                )

            # ── Texto del mensaje ─────────────────────────────────────────────
            region_display = region_actual.capitalize()
            texto = (
                f"🎓 <b>¡Bienvenido a la región {region_display}!</b>\n\n"
                f"Elige tu Pokémon inicial:\n\n"
                f"{descripciones}"
                f"{aviso_pc}\n\n"
                f"<i>Elige sabiamente — solo puedes elegir una vez por región.</i>"
            )

            self.bot.send_message(
                cid, texto,
                parse_mode="HTML",
                reply_markup=markup,
                message_thread_id=tid,
            )

            logger.info(
                f"[PROFESOR] Usuario {uid} solicitó starter en región {region_actual} "
                f"({len(starters)} starters disponibles)"
            )

        except Exception as e:
            logger.error(f"[PROFESOR] Error en cmd_profesor: {e}", exc_info=True)
            try:
                m = self.bot.send_message(
                    cid, f"❌ Error cargando la pantalla del profesor: {str(e)}",
                    message_thread_id=tid,
                )
                _delete_after(self.bot, cid, m.message_id, 10)
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────────────────────
    # callback_elegir_starter — procesa la elección del starter
    # ──────────────────────────────────────────────────────────────────────────

    def callback_elegir_starter(self, call):
        """
        Procesa la elección del starter.

        Flujo:
          1. Verifica que el callback venga del usuario correcto.
          2. Comprueba que no exista ya un starter para la región activa.
          3. Mueve TODO el equipo actual al PC (en_equipo=0, posicion_equipo=NULL).
          4. Crea el nuevo starter con la región activa.
          5. Lo agrega al equipo (slot 0).
          6. Entrega items de bienvenida.
          7. Pide apodo al usuario.
        """
        from config import POKEMON_REGION_SERVIDOR
        from database import db_manager
        from pokemon.services.pokedex_service import pokedex_service as _pdex

        uid = call.from_user.id
        cid = call.message.chat.id

        try:
            # ── Parsear el ID del starter desde callback_data ─────────────────
            # callback_data tiene el formato "starter_<pokemon_id>"
            pokemon_id = int(call.data.split('_')[1])
        except (IndexError, ValueError) as e:
            logger.error(f"[STARTER] callback_data inválido: {call.data} — {e}")
            self.bot.answer_callback_query(
                call.id, "❌ Datos inválidos.", show_alert=True
            )
            return

        # ── Región activa (leída en tiempo real) ──────────────────────────────
        region_actual = POKEMON_REGION_SERVIDOR.upper().strip()

        try:
            # ── 1. Re-verificar que no tenga ya un starter de esta región ─────
            #    (edge case: dos clicks rápidos desde distintos devices)
            ya_tiene = db_manager.execute_query(
                "SELECT COUNT(*) as total FROM POKEMON_USUARIO "
                "WHERE userID = ? AND region = ?",
                (uid, region_actual),
            )
            if ya_tiene and ya_tiene[0]["total"] > 0:
                self.bot.answer_callback_query(
                    call.id,
                    f"❌ Ya tienes un Pokémon en {region_actual.capitalize()}.",
                    show_alert=True,
                )
                return

            # ── 2. Mover equipo actual al PC ──────────────────────────────────
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO "
                "SET en_equipo = 0, posicion_equipo = NULL "
                "WHERE userID = ? AND en_equipo = 1",
                (uid,),
            )
            logger.info(
                f"[STARTER] Equipo de {uid} movido al PC "
                f"para nueva región {region_actual}"
            )

            # ── 3. Crear el nuevo starter con la región activa ────────────────
            pokemon_creado_id = pokemon_service.crear_pokemon(
                user_id    = uid,
                pokemon_id = pokemon_id,
                nivel      = 5,
                region     = region_actual,
                shiny      = False,
            )

            if not pokemon_creado_id:
                self.bot.answer_callback_query(
                    call.id, "❌ Error al crear el Pokémon.", show_alert=True
                )
                return

            # ── 4. Agregar al equipo (slot 0) ─────────────────────────────────
            pokemon_service.mover_a_equipo(pokemon_creado_id, uid)

            # ── 5. Items de bienvenida ─────────────────────────────────────────
            from pokemon.services import items_service
            try:
                items_service.agregar_item(uid, 'pokeball', 10)
                items_service.agregar_item(uid, 'pocion', 3)
            except Exception as item_err:
                logger.warning(f"[STARTER] No se pudieron entregar items: {item_err}")

            # ── 6. Nombre del Pokémon desde la Pokédex ────────────────────────
            pokemon_data = _pdex.obtener_pokemon(pokemon_id)
            nombre = (
                pokemon_data.get('nombre', f'Pokémon #{pokemon_id}')
                if pokemon_data else f'Pokémon #{pokemon_id}'
            )

            # ── 7. Editar el mensaje del grupo con el resultado ───────────────
            region_display = region_actual.capitalize()
            texto = (
                f"✅ <b>¡{nombre} elegido!</b>\n\n"
                f"🗺️ Región: <b>{region_display}</b>\n\n"
                f"🎁 <b>Items recibidos:</b>\n"
                f"• 10× Poké Ball\n"
                f"• 3× Poción\n\n"
                f"¡Tu aventura en {region_display} comienza ahora!\n"
                f"Usa /pokemon para ver tu menú."
            )
            self.bot.edit_message_text(
                texto, cid, call.message.message_id, parse_mode='HTML'
            )
            self.bot.answer_callback_query(call.id, f"✅ {nombre} elegido!")

            logger.info(
                f"[STARTER] {uid} eligió {nombre} (#{pokemon_id}) "
                f"en región {region_actual}"
            )

            # ── 8. Pedir apodo ─────────────────────────────────────────────────
            nuevo_poke = pokemon_service.obtener_pokemon(pokemon_creado_id)
            if nuevo_poke:
                from pokemon.pokemon_class import pedir_mote_pokemon

                def _guardar_mote(mote: str | None) -> None:
                    if mote:
                        db_manager.execute_update(
                            "UPDATE POKEMON_USUARIO SET apodo = ? WHERE id_unico = ?",
                            (mote, pokemon_creado_id),
                        )

                pedir_mote_pokemon(
                    bot=self.bot,
                    user_id=uid,
                    pokemon=nuevo_poke,
                    mensaje_callback=_guardar_mote,
                    chat_id=cid,
                    message_thread_id=getattr(call.message, "message_thread_id", None),
                )

        except Exception as e:
            logger.error(
                f"[STARTER] Error en callback_elegir_starter: {e}", exc_info=True
            )
            self.bot.answer_callback_query(
                call.id, f"❌ Error: {str(e)}", show_alert=True
            )

    # ──────────────────────────────────────────────────────────────────────────
    # /pokedex
    # ──────────────────────────────────────────────────────────────────────────

    def cmd_pokedex(self, message):
        """
        /pokedex — muestra el progreso de la Pokédex regional del usuario.
        """
        cid = message.chat.id
        uid = message.from_user.id
        tid = getattr(message, "message_thread_id", None)

        try:
            self.bot.delete_message(cid, message.message_id)
        except Exception:
            pass

        from funciones.pokedex_usuario import obtener_progreso, tiene_amuleto_iris
        from config import POKEMON_REGION_SERVIDOR

        user_info = user_service.get_user_info(uid)
        if not user_info:
            m = self.bot.send_message(cid, "❌ No estás registrado.", message_thread_id=tid)
            _delete_after(self.bot, cid, m.message_id)
            return

        progreso = obtener_progreso(uid, POKEMON_REGION_SERVIDOR)
        region   = progreso["region"]
        total    = progreso["total"]
        av       = progreso["avistados"]
        cap      = progreso["capturados"]
        pct_av   = round(av  / total * 100, 1) if total else 0
        pct_cap  = round(cap / total * 100, 1) if total else 0

        def barra(n, t, largo=20):
            filled = int(n / t * largo) if t else 0
            return "█" * filled + "░" * (largo - filled)

        amuleto_txt = (
            "\n\n🌈 <b>¡Tienes el Amuleto Iris!</b> ×3 Shiny"
            if tiene_amuleto_iris(uid) else ""
        )

        texto = (
            f"📖 <b>Pokédex de {region}</b>\n\n"
            f"👁 Avistados:  <b>{av}/{total}</b> ({pct_av}%)\n"
            f"<code>{barra(av, total)}</code>\n\n"
            f"🔴 Capturados: <b>{cap}/{total}</b> ({pct_cap}%)\n"
            f"<code>{barra(cap, total)}</code>"
            f"{amuleto_txt}"
        )

        self.bot.send_message(cid, texto, parse_mode="HTML", message_thread_id=tid)

    # ──────────────────────────────────────────────────────────────────────────
    # /salvaje — Pokémon salvaje de pago, exclusivo del invocador
    # ──────────────────────────────────────────────────────────────────────────

    def cmd_salvaje(self, message):
        """
        /salvaje — El usuario paga cosmos para invocar un Pokémon salvaje
        que SOLO él puede combatir.
        """
        user_id = message.from_user.id
        chat_id = message.chat.id
        from config import CANAL_ID, POKECLUB

        tid = get_thread_id(message)
        es_privado   = message.chat.type == 'private'
        es_pokeclub  = (message.chat.id == CANAL_ID and tid == POKECLUB)

        if not es_privado and not es_pokeclub:
            try:
                self.bot.delete_message(message.chat.id, message.message_id)
                m = self.bot.send_message(
                    chat_id, "❌ Solo puedes usar este comando en pokeclub!.",
                    message_thread_id=tid,
                )
                time.sleep(5)
                self.bot.delete_message(chat_id, m.message_id)
            except Exception:
                pass
            return

        try:
            self.bot.delete_message(chat_id, message.message_id)
        except Exception:
            pass

        def _responder_error(texto: str):
            try:
                m = self.bot.send_message(
                    chat_id, texto,
                    parse_mode="HTML",
                    message_thread_id=tid,
                )
                time.sleep(8)
                self.bot.delete_message(chat_id, m.message_id)
            except Exception:
                pass

        try:
            from funciones import user_service, economy_service

            equipo = pokemon_service.obtener_equipo(user_id)
            if not equipo:
                _responder_error(
                    "❌ No tienes Pokémon en tu equipo.\n"
                    "Usa /profesor para obtener tu Pokémon inicial."
                )
                return

            if not any(p.hp_actual > 0 for p in equipo):
                _responder_error(
                    "❌ Todos tus Pokémon están debilitados.\n"
                    "Ve al Centro Pokémon: /pokemon → Centro Pokémon"
                )
                return

            costo_salvaje = calcular_costo_salvaje(user_id)
            saldo = economy_service.get_balance(user_id)
            if saldo is None or saldo < costo_salvaje:
                _responder_error(
                    f"❌ Saldo insuficiente para invocar un Pokémon salvaje.\n"
                    f"💰 Costo: <b>{costo_salvaje} cosmos</b>\n"
                    f"💳 Tienes: <b>{saldo or 0} cosmos</b>"
                )
                return

            if user_id in self._invocaciones_privadas:
                _responder_error(
                    "⚠️ Ya tienes un Pokémon salvaje esperándote.\n"
                    "¡Combátelo antes de invocar otro!"
                )
                return

            ok_pago = economy_service.subtract_credits(
                user_id, costo_salvaje,
                "Invocación Pokémon salvaje (/salvaje)",
            )
            if not ok_pago:
                _responder_error("❌ Error al procesar el pago. Intenta de nuevo.")
                return

            spawn = spawn_service.generar_datos_spawn(user_id)

            if spawn is None:
                economy_service.add_credits(
                    user_id, costo_salvaje,
                    "Reembolso /salvaje (spawn fallido)",
                )
                _responder_error(
                    "⚠️ No se pudo generar el Pokémon. "
                    "Los cosmos fueron reembolsados."
                )
                return

            self._invocaciones_privadas[user_id] = {
                "pokemon_id": spawn.pokemon_id,
                "nivel":      spawn.nivel,
                "shiny":      spawn.shiny,
                "nombre":     spawn.nombre,
            }

            shiny_text = " ✨ <b>¡¡¡SHINY!!!</b>" if spawn.shiny else ""
            nombre_usuario = (
                f"@{message.from_user.username}"
                if message.from_user.username
                else message.from_user.first_name
            )
            caption = (
                f"⚡ <b>¡Pokémon salvaje invocado por {nombre_usuario}!{shiny_text}</b>\n\n"
                f"❓ Un Pokémon misterioso responde al llamado...\n"
                f"💰 Costo: <b>{costo_salvaje} cosmos</b>\n\n"
                f"🔒 <i>Solo {nombre_usuario} puede combatirlo.</i>"
            )

            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton(
                    "⚔️ ¡Combatir!",
                    callback_data=f"salvaje_combatir_{user_id}",
                )
            )

            from pathlib import Path
            from config import UNKNOWN_SPRITE

            sprite_path = Path(UNKNOWN_SPRITE) if UNKNOWN_SPRITE else None
            msg_grupo   = None

            if sprite_path and sprite_path.exists():
                try:
                    with open(sprite_path, "rb") as f:
                        if sprite_path.suffix.lower() == ".gif":
                            msg_grupo = self.bot.send_animation(
                                chat_id, f,
                                caption=caption, parse_mode="HTML",
                                reply_markup=keyboard,
                                message_thread_id=tid,
                            )
                        else:
                            msg_grupo = self.bot.send_photo(
                                chat_id, f,
                                caption=caption, parse_mode="HTML",
                                reply_markup=keyboard,
                                message_thread_id=tid,
                            )
                except Exception:
                    msg_grupo = None

            if not msg_grupo:
                msg_grupo = self.bot.send_message(
                    chat_id, caption,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    message_thread_id=tid,
                )

            logger.info(
                f"[SALVAJE] Usuario {user_id} invocó spawn privado "
                f"(Pokémon #{spawn.pokemon_id})"
            )

        except Exception as e:
            logger.error(f"[SALVAJE] Error en cmd_salvaje: {e}", exc_info=True)
            _responder_error("❌ Error inesperado. Intenta de nuevo.")

    def _callback_salvaje_combatir(self, call):
        """
        Callback del botón "⚔️ ¡Combatir!" del Pokémon salvaje privado.
        """
        user_id = call.from_user.id

        try:
            partes = call.data.split("_")
            if len(partes) < 3:
                self.bot.answer_callback_query(
                    call.id, "❌ Datos inválidos.", show_alert=True
                )
                return

            uid_dueño = int(partes[2])

            if user_id != uid_dueño:
                self.bot.answer_callback_query(
                    call.id,
                    "🔒 ¡Este Pokémon salvaje no es tuyo!",
                    show_alert=True,
                )
                return

            spawn_data = self._invocaciones_privadas.get(user_id)
            if not spawn_data:
                self.bot.answer_callback_query(
                    call.id,
                    "❌ El Pokémon salvaje ya huyó...",
                    show_alert=True,
                )
                try:
                    self.bot.edit_message_reply_markup(
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=None,
                    )
                except Exception:
                    pass
                return

            try:
                self.bot.answer_callback_query(
                    call.id, "⚔️ ¡Iniciando batalla!", show_alert=False
                )
            except Exception:
                pass

            self._invocaciones_privadas.pop(user_id, None)

            from pokemon.wild_battle_system import wild_battle_manager

            success, msg = wild_battle_manager.start_battle(
                user_id=user_id,
                thread_id=user_id,
                spawn_data=spawn_data,
                bot=self.bot,
            )

            if not success:
                logger.warning(f"[SALVAJE] Batalla no iniciada para {user_id}: {msg}")
                try:
                    self.bot.send_message(user_id, msg, parse_mode="HTML")
                except Exception:
                    pass
                return

            battle = wild_battle_manager.get_battle(user_id)
            if battle:
                battle.group_chat_id    = call.message.chat.id
                battle.group_message_id = call.message.message_id

            try:
                self.bot.delete_message(
                    call.message.chat.id,
                    call.message.message_id,
                )
            except Exception:
                pass

        except Exception as e:
            logger.error(
                f"[SALVAJE] Error en _callback_salvaje_combatir: {e}", exc_info=True
            )
            try:
                self.bot.send_message(user_id, "❌ Error iniciando combate.")
            except Exception:
                pass


def setup(bot: telebot.TeleBot):
    """Función para registrar los handlers."""
    PokemonHandlers(bot)