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
        self.bot.register_message_handler(self.cmd_pokedex, commands=['pokedex'])

        # Contar pasos de guardería en mensajes de texto del DM
        self.bot.register_message_handler(
            self._handle_texto_privado,
            func=lambda m: m.chat.id == m.from_user.id and m.content_type == 'text',
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

        # ── Mts  ──────────────────────────────────────────────────────────────
        @self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('mt_')
        )
        def callback_mt(call):
            from pokemon.mt_system import handle_mt_callback
            handle_mt_callback(call, self.bot)

    # ──────────────────────────────────────────────────────────────────────────
    # TEXTO PRIVADO (mote de guardería + pasos)
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_texto_privado(self, message):
        """
        Intercepta mensajes de texto en chat privado:
        1. Si el usuario espera poner mote a un Pokémon recién nacido, lo consume.
        2. En cualquier caso, suma pasos de guardería.
        """
        from pokemon.guarderia_steps import interceptar_mote, sumar_pasos_mensaje
        if interceptar_mote(self.bot, message):
            return
        sumar_pasos_mensaje(self.bot, message)

    # ──────────────────────────────────────────────────────────────────────────
    # /pokemon
    # ──────────────────────────────────────────────────────────────────────────

    def cmd_pokemon(self, message):
        """
        Comando /pokemon — Menú principal de Pokémon.
        Bloqueado si el usuario tiene una batalla activa (salvaje, PvP o gimnasio).
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
                m = self.bot.send_message(cid, "❌ Solo puedes usar este comando en pokeclub!.",message_thread_id=tid,)
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
    # /profesor
    # ──────────────────────────────────────────────────────────────────────────

    def cmd_profesor(self, message):
        """Comando /profesor - Elige el Pokémon inicial."""
        uid = message.from_user.id
        cid = message.chat.id
        from config import CANAL_ID, POKECLUB

        tid = get_thread_id(message)
        es_privado   = message.chat.type == 'private'
        es_pokeclub  = (message.chat.id == CANAL_ID and tid == POKECLUB)

        if not es_privado and not es_pokeclub:
            try:
                self.bot.delete_message(message.chat.id, message.message_id)
                m = self.bot.send_message(cid, "❌ Solo puedes usar este comando en pokeclub!.",message_thread_id=tid,)
                time.sleep(5)
                self.bot.delete_message(cid, m.message_id)
            except Exception:
                pass
            return

        try:
            equipo = pokemon_service.obtener_equipo(uid)
            pc     = pokemon_service.obtener_pc(uid, limit=1)

            if equipo or pc:
                m = self.bot.send_message(
                    cid, "❌ Ya tienes Pokémon. No puedes elegir otro inicial.",
                    message_thread_id=tid,
                )
                time.sleep(5)
                try:
                    self.bot.delete_message(cid, m.message_id)
                except Exception:
                    pass
                return

            markup = types.InlineKeyboardMarkup(row_width=3)
            markup.add(
                types.InlineKeyboardButton("🌿 Bulbasaur", callback_data="starter_1"),
                types.InlineKeyboardButton("🔥 Charmander", callback_data="starter_4"),
                types.InlineKeyboardButton("💧 Squirtle",   callback_data="starter_7"),
            )

            texto = (
                "🎓 <b>¡Bienvenido al mundo Pokémon!</b>\n\n"
                "Antes de comenzar tu aventura, necesitas elegir tu primer Pokémon:\n\n"
                "🌿 <b>Bulbasaur</b> (#1) - Tipo Planta/Veneno\n"
                "🔥 <b>Charmander</b> (#4) - Tipo Fuego\n"
                "💧 <b>Squirtle</b> (#7) - Tipo Agua\n\n"
                "Elige sabiamente, solo podrás hacerlo una vez."
            )
            self.bot.send_message(
                cid, texto,
                parse_mode="HTML",
                reply_markup=markup,
                message_thread_id=tid,
            )

        except Exception as e:
            logger.error(f"Error en cmd_profesor: {e}")
            self.bot.send_message(cid, f"❌ Error: {str(e)}", message_thread_id=tid)

    def callback_elegir_starter(self, call):
        """Callback para elegir Pokémon inicial."""
        uid = call.from_user.id
        cid = call.message.chat.id

        try:
            pokemon_id = int(call.data.split('_')[1])

            equipo = pokemon_service.obtener_equipo(uid)
            pc     = pokemon_service.obtener_pc(uid, limit=1)
            if equipo or pc:
                self.bot.answer_callback_query(call.id, "❌ Ya tienes Pokémon", show_alert=True)
                return

            pokemon_creado_id = pokemon_service.crear_pokemon(
                user_id=uid, pokemon_id=pokemon_id, nivel=5,
                region='KANTO', shiny=False,
            )

            if pokemon_creado_id:
                pokemon_service.mover_a_equipo(pokemon_creado_id, uid)

                from pokemon.services import items_service
                try:
                    items_service.agregar_item(uid, 'pokeball', 10)
                    items_service.agregar_item(uid, 'pocion', 3)
                except Exception:
                    pass

                nombres_starters = {1: "Bulbasaur", 4: "Charmander", 7: "Squirtle"}
                nombre = nombres_starters.get(pokemon_id, f"Pokémon #{pokemon_id}")

                texto = (
                    f"✅ <b>¡Felicidades!</b>\n\n"
                    f"Has elegido a <b>{nombre}</b> como tu compañero inicial.\n\n"
                    f"🎁 <b>Items recibidos:</b>\n"
                    f"• 10× Pokéball\n"
                    f"• 3× Poción\n\n"
                    f"Tu aventura Pokémon comienza ahora. ¡Buena suerte!\n\n"
                    f"Usa /pokemon para ver tu menú completo."
                )
                self.bot.edit_message_text(
                    texto, cid, call.message.message_id, parse_mode='HTML'
                )
                self.bot.answer_callback_query(call.id, f"✅ {nombre} elegido!")
                logger.info(f"🎉 Usuario {uid} eligió {nombre} como starter")

                nuevo_poke = pokemon_service.obtener_pokemon(pokemon_creado_id)
                if nuevo_poke:
                    from pokemon.pokemon_class import pedir_mote_pokemon

                    def _guardar_mote_starter(mote):
                        if mote:
                            from database import db_manager as _db
                            _db.execute_update(
                                "UPDATE POKEMON_USUARIO SET apodo = ? WHERE id_unico = ?",
                                (mote, pokemon_creado_id),
                            )

                    pedir_mote_pokemon(
                        bot=self.bot,
                        user_id=uid,
                        pokemon=nuevo_poke,
                        mensaje_callback=_guardar_mote_starter,
                        chat_id=cid,
                        message_thread_id=getattr(call.message, "message_thread_id", None),
                    )
            else:
                self.bot.answer_callback_query(
                    call.id, "❌ Error al crear Pokémon. Intenta de nuevo.", show_alert=True
                )
                logger.error(f"Error: crear_pokemon retornó None para usuario {uid}")

        except Exception as e:
            logger.error(f"Error en callback_elegir_starter: {e}", exc_info=True)
            self.bot.answer_callback_query(call.id, f"❌ Error: {str(e)}", show_alert=True)

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

        barra = lambda n, t, largo=20: (
            "█" * int(n / t * largo) + "░" * (largo - int(n / t * largo))
        ) if t else "░" * largo

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
        /salvaje — El usuario paga COSTO_INVOCACION_SALVAJE cosmos para
        invocar un Pokémon salvaje que SOLO él puede combatir.

        Diseño:
        - El anuncio se publica en el mismo hilo del grupo (igual que los
          spawns automáticos), para que el usuario no necesite DM previo.
        - El callback_data lleva el user_id del invocador, de modo que el
          handler verifica que solo ese usuario pueda presionar "Combatir".
        - El spawn se almacena con canal_id = user_id (clave privada que
          nadie más puede reclamar en los spawns del canal).
        - El mensaje del grupo se borra al iniciar el combate, igual que
          en los spawns automáticos.
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
                m = self.bot.send_message(chat_id, "❌ Solo puedes usar este comando en pokeclub!.",message_thread_id=tid,)
                time.sleep(5)
                self.bot.delete_message(chat_id, m.message_id)
            except Exception:
                pass
            return

        # Intentar borrar el comando para mantener el hilo limpio
        try:
            self.bot.delete_message(chat_id, message.message_id)
        except Exception:
            pass

        def _responder_error(texto: str):
            """Envía error en el hilo y lo borra tras 8 s."""
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

            # 1. Validar equipo
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

            # 2. Validar saldo
            costo_salvaje = calcular_costo_salvaje(user_id)
            saldo = economy_service.get_balance(user_id)
            if saldo is None or saldo < costo_salvaje:
                _responder_error(
                    f"❌ Saldo insuficiente para invocar un Pokémon salvaje.\n"
                    f"💰 Costo: <b>{costo_salvaje} cosmos</b>\n"
                    f"💳 Tienes: <b>{saldo or 0} cosmos</b>"
                )
                return

            # 3. Verificar que el usuario no tenga ya una invocación pendiente.
            #    Nota: se consulta el dict INTERNO del handler, completamente
            #    independiente de spawn_service.  Los spawns automáticos del
            #    canal NO interfieren con esta comprobación y viceversa.
            if user_id in self._invocaciones_privadas:
                _responder_error(
                    "⚠️ Ya tienes un Pokémon salvaje esperándote.\n"
                    "¡Combátelo antes de invocar otro!"
                )
                return

            # 4. Cobrar cosmos ANTES de generar (no reembolsable en caso de fallo).
            ok_pago = economy_service.subtract_credits(
                user_id,
                costo_salvaje,
                "Invocación Pokémon salvaje (/salvaje)",
            )
            if not ok_pago:
                _responder_error("❌ Error al procesar el pago. Intenta de nuevo.")
                return

            # 5. Generar datos del Pokémon SIN escribir nada en spawn_service.
            #    spawn_service.generar_datos_spawn solo calcula y devuelve
            #    el objeto Spawn; no lo almacena en spawns_activos.
            spawn = spawn_service.generar_datos_spawn(user_id)

            if spawn is None:
                # Reembolsar si la generación falla.
                economy_service.add_credits(
                    user_id,
                    costo_salvaje,
                    "Reembolso /salvaje (spawn fallido)",
                )
                _responder_error(
                    "⚠️ No se pudo generar el Pokémon. "
                    "Los cosmos fueron reembolsados."
                )
                return

            # Guardar en el dict interno del handler.  spawn_service no sabe
            # nada de esta invocación; los spawns automáticos siguen su propio
            # ciclo sin interferencia.
            self._invocaciones_privadas[user_id] = {
                "pokemon_id": spawn.pokemon_id,
                "nivel":      spawn.nivel,
                "shiny":      spawn.shiny,
                "nombre":     spawn.nombre,
            }

            # 6. Publicar anuncio en el hilo del grupo con botón exclusivo
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

            # callback_data lleva user_id → el handler lo valida
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

        Lee los datos de la invocación desde self._invocaciones_privadas,
        completamente independiente de spawn_service.  Esto permite que un
        spawn automático público y una invocación privada de /salvaje
        coexistan simultáneamente sin interferencia.
        """
        user_id = call.from_user.id

        try:
            # Extraer uid_dueño del callback: salvaje_combatir_{uid}
            partes = call.data.split("_")
            if len(partes) < 3:
                self.bot.answer_callback_query(
                    call.id, "❌ Datos inválidos.", show_alert=True
                )
                return

            uid_dueño = int(partes[2])

            # Solo el dueño puede combatir este Pokémon.
            if user_id != uid_dueño:
                self.bot.answer_callback_query(
                    call.id,
                    "🔒 ¡Este Pokémon salvaje no es tuyo!",
                    show_alert=True,
                )
                return

            # Recuperar datos del dict INTERNO del handler.
            # spawn_service no tiene registro de esta invocación.
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

            # Responder el callback DE INMEDIATO para no dejar expirar el query_id.
            try:
                self.bot.answer_callback_query(
                    call.id, "⚔️ ¡Iniciando batalla!", show_alert=False
                )
            except Exception:
                pass

            # Consumir la invocación antes de iniciar la batalla.
            # Si start_battle falla, el usuario tendrá que invocar de nuevo.
            self._invocaciones_privadas.pop(user_id, None)

            from pokemon.wild_battle_system import wild_battle_manager

            success, msg = wild_battle_manager.start_battle(
                user_id=user_id,
                thread_id=user_id,   # thread_id = user_id identifica batallas privadas
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
