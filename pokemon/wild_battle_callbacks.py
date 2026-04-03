# -*- coding: utf-8 -*-
"""
Callbacks Handler para Sistema de Combate Salvaje
==================================================

Maneja todos los callbacks de botones en batallas contra Pokémon salvajes
"""

import logging
from telebot import types
from pokemon.wild_battle_system import wild_battle_manager

logger = logging.getLogger(__name__)


class WildBattleCallbacks:
    """Manejador de callbacks para batallas salvajes"""
    
    def __init__(self, bot):
        self.bot = bot
        self._register_callbacks()
    
    def _register_callbacks(self):
        """Registra todos los callbacks relacionados con batallas"""
        
        # Menú principal
        self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('battle_fight_')
        )(self.handle_fight_button)
        
        # Mochila principal — SOLO "battle_bag_<user_id>" (no subcategorías)
        self.bot.callback_query_handler(
            func=lambda call: (
                call.data.startswith('battle_bag_') and
                not call.data.startswith('battle_bag_cat_')
            )
        )(self.handle_bag_button)

        # Categorías de mochila — "battle_bag_cat_medicine_123" etc.
        self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('battle_bag_cat_')
        )(self.handle_bag_category_button)

        # Item seleccionado — "battle_item_123_pocion"
        self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('battle_item_')
        )(self.handle_item_selected_button)

        # Usar item en Pokémon — "battle_use_item_123_pocion_456"
        self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('battle_use_item_')
        )(self.handle_use_item_button)
        
        self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('battle_team_')
        )(self.handle_team_button)
        
        self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('battle_run_')
        )(self.handle_run_button)

        self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('battle_bag_berries_')
        )(self.handle_berries_button)
        
        # Acciones de combate
        self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('battle_move_')
        )(self.handle_move_button)
        
        self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('battle_switch_')
        )(self.handle_switch_button)
        
        @self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('battle_pivotswitch_')
        )
        def callback_pivot_switch(call):
            self.handle_pivot_switch_button(call)
            
        # Navegación
        self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('battle_back_')
        )(self.handle_back_button)
        
        self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('battle_noop_')
        )(self.handle_noop_button)
        
        self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('battle_forfeit_')
        )(self.handle_forfeit_button)
        
        logger.info("[BATTLE_CALLBACKS] Callbacks de batalla registrados")
    
    def handle_fight_button(self, call: types.CallbackQuery):
        """Maneja el botón 'Combate'"""
        try:
            user_id = call.from_user.id
            
            if not wild_battle_manager.has_active_battle(user_id):
                self.bot.answer_callback_query(
                call.id, "❌ No tienes una batalla activa", show_alert=True
                )
                return

            battle = wild_battle_manager.get_battle(user_id)
            if battle and getattr(battle, "awaiting_faint_switch", False):
                self.bot.answer_callback_query(
                call.id,
                "⚠️ ¡Tu Pokémon fue derrotado! Elige un reemplazo primero.",
                show_alert=True
                )
                return

            success = wild_battle_manager.handle_fight_action(user_id, self.bot)
            
            if success:
                self.bot.answer_callback_query(call.id)
            else:
                self.bot.answer_callback_query(
                    call.id,
                    "❌ Error mostrando movimientos",
                    show_alert=True
                )
            
        except Exception as e:
            logger.error(f"Error en handle_fight_button: {e}")
            self.bot.answer_callback_query(
                call.id,
                "❌ Error procesando acción",
                show_alert=True
            )
    
    def handle_bag_button(self, call: types.CallbackQuery):
        """Maneja el botón 'Mochila'"""
        try:
            user_id = call.from_user.id
            
            if not wild_battle_manager.has_active_battle(user_id):
                self.bot.answer_callback_query(
                    call.id,
                    "❌ No tienes una batalla activa",
                    show_alert=True
                )
                return
            
            success = wild_battle_manager.handle_bag_action(user_id, self.bot)
            
            if success:
                self.bot.answer_callback_query(call.id)
            else:
                self.bot.answer_callback_query(
                    call.id,
                    "❌ Error mostrando mochila",
                    show_alert=True
                )
            
        except Exception as e:
            logger.error(f"Error en handle_bag_button: {e}")
            self.bot.answer_callback_query(
                call.id,
                "❌ Error procesando acción",
                show_alert=True
            )
    
    def handle_team_button(self, call: types.CallbackQuery):
        """Maneja el botón 'Equipo'"""
        try:
            user_id = call.from_user.id
            
            if not wild_battle_manager.has_active_battle(user_id):
                self.bot.answer_callback_query(
                    call.id,
                    "❌ No tienes una batalla activa",
                    show_alert=True
                )
                return
            
            success = wild_battle_manager.handle_team_action(user_id, self.bot)
            
            if success:
                self.bot.answer_callback_query(call.id)
            else:
                self.bot.answer_callback_query(
                    call.id,
                    "❌ Error mostrando equipo",
                    show_alert=True
                )
            
        except Exception as e:
            logger.error(f"Error en handle_team_button: {e}")
            self.bot.answer_callback_query(
                call.id,
                "❌ Error procesando acción",
                show_alert=True
            )
    
    def handle_run_button(self, call: types.CallbackQuery):
        """Maneja el botón 'Huir'"""

         # --- VALIDACIÓN ROBUSTA ---
        if not call.data or not call.message:
            return
        
        try:
            user_id = call.from_user.id
            
            if not wild_battle_manager.has_active_battle(user_id):
                self.bot.answer_callback_query(
                call.id, "❌ No tienes una batalla activa", show_alert=True
                )
                return

            battle = wild_battle_manager.get_battle(user_id)
            if battle and getattr(battle, "awaiting_faint_switch", False):
                self.bot.answer_callback_query(
                call.id,
                "⚠️ ¡Tu Pokémon fue derrotado! Elige un reemplazo primero.",
                show_alert=True
                )
                return

            success = wild_battle_manager.attempt_flee(user_id, self.bot)
            
            if success:
                self.bot.answer_callback_query(call.id)
            else:
                self.bot.answer_callback_query(
                    call.id,
                    "❌ Error intentando huir",
                    show_alert=True
                )
            
        except Exception as e:
            logger.error(f"Error en handle_run_button: {e}")
            self.bot.answer_callback_query(
                call.id,
                "❌ Error procesando acción",
                show_alert=True
            )
    
    def handle_move_button(self, call: types.CallbackQuery):
        """Maneja la selección de un movimiento"""

         # --- VALIDACIÓN ROBUSTA ---
        if not call.data or not call.message:
            return
        
        try:
            # Parsear: battle_move_{user_id}_{move_name}
            parts = call.data.split('_', 3)
            if len(parts) < 4:
                self.bot.answer_callback_query(call.id, "❌ Datos inválidos")
                return
            
            user_id = call.from_user.id
            move_name = parts[3]
            
            if not wild_battle_manager.has_active_battle(user_id):
                self.bot.answer_callback_query(
                    call.id,
                    "❌ No tienes una batalla activa",
                    show_alert=True
                )
                return
            
            success = wild_battle_manager.execute_move(user_id, move_name, self.bot)
            
            if success:
                self.bot.answer_callback_query(call.id)
            else:
                self.bot.answer_callback_query(
                    call.id,
                    "❌ Error ejecutando movimiento",
                    show_alert=True
                )
            
        except Exception as e:
            logger.error(f"Error en handle_move_button: {e}")
            self.bot.answer_callback_query(
                call.id,
                "❌ Error procesando movimiento",
                show_alert=True
            )
    
    def handle_switch_button(self, call: types.CallbackQuery):
        """Maneja el cambio de Pokémon"""

         # --- VALIDACIÓN ROBUSTA ---
        if not call.data or not call.message:
            return
        
        try:
            # Parsear: battle_switch_{user_id}_{pokemon_id}
            parts = call.data.split('_')
            if len(parts) < 4:
                self.bot.answer_callback_query(call.id, "❌ Datos inválidos")
                return
            
            user_id = call.from_user.id
            pokemon_id = int(parts[3])
            
            if not wild_battle_manager.has_active_battle(user_id):
                self.bot.answer_callback_query(
                    call.id,
                    "❌ No tienes una batalla activa",
                    show_alert=True
                )
                return
            
            success = wild_battle_manager.switch_pokemon(user_id, pokemon_id, self.bot)
            
            if success:
                self.bot.answer_callback_query(call.id)
            else:
                self.bot.answer_callback_query(
                    call.id,
                    "❌ No puedes cambiar a ese Pokémon",
                    show_alert=True
                )
            
        except Exception as e:
            logger.error(f"Error en handle_switch_button: {e}")
            self.bot.answer_callback_query(
                call.id,
                "❌ Error cambiando Pokémon",
                show_alert=True
            )

    def handle_pivot_switch_button(self, call: types.CallbackQuery):
        """
        Maneja la selección de Pokémon después de un move pivot del jugador
        (U-turn, Volt Switch, Parting Shot).
        El wild NO contraataca — es un switch gratuito.
        """

         # --- VALIDACIÓN ROBUSTA ---
        if not call.data or not call.message:
            return
        
        try:
            parts = call.data.split('_')
            # battle_pivotswitch_{user_id}_{pokemon_id}
            if len(parts) < 4:
                self.bot.answer_callback_query(call.id, "❌ Datos inválidos")
                return

            user_id    = call.from_user.id
            pokemon_id = int(parts[3])

            if not wild_battle_manager.has_active_battle(user_id):
                self.bot.answer_callback_query(
                    call.id, "❌ No tienes una batalla activa", show_alert=True
                )
                return

            battle = wild_battle_manager.get_battle(user_id)
            if not battle or not battle.awaiting_pivot_switch:
                self.bot.answer_callback_query(
                    call.id, "❌ No estás esperando un cambio pivot", show_alert=True
                )
                return

            success = wild_battle_manager.switch_pokemon(
                user_id, pokemon_id, self.bot, is_post_pivot=True
            )

            if success:
                self.bot.answer_callback_query(call.id)
            else:
                self.bot.answer_callback_query(
                    call.id, "❌ No puedes cambiar a ese Pokémon", show_alert=True
                )

        except Exception as e:
            logger.error(f"Error en handle_pivot_switch_button: {e}")
            self.bot.answer_callback_query(call.id, "❌ Error procesando cambio")

    def handle_back_button(self, call: types.CallbackQuery):
        """Maneja el botón 'Volver' - regresa al menú principal"""
        try:
            user_id = call.from_user.id
            
            battle = wild_battle_manager.get_battle(user_id)
            if not battle:
                self.bot.answer_callback_query(
                    call.id,
                    "❌ No tienes una batalla activa",
                    show_alert=True
                )
                return
            
            # Reenviar menú principal
            wild_battle_manager._send_battle_menu(battle, self.bot)
            self.bot.answer_callback_query(call.id)
            
        except Exception as e:
            logger.error(f"Error en handle_back_button: {e}")
            self.bot.answer_callback_query(
                call.id,
                "❌ Error volviendo al menú",
                show_alert=True
            )
    
    def handle_noop_button(self, call: types.CallbackQuery):
        """Maneja botones deshabilitados (no-operation)"""
        self.bot.answer_callback_query(
            call.id,
            "Este Pokémon no está disponible",
            show_alert=False
        )
    
    def handle_berries_button(self, call: types.CallbackQuery):
        """Maneja el menú de bayas"""
        try:
            user_id = call.from_user.id
            
            if not wild_battle_manager.has_active_battle(user_id):
                self.bot.answer_callback_query(
                    call.id,
                    "❌ No tienes una batalla activa",
                    show_alert=True
                )
                return
            
            # Mostrar bayas disponibles
            from pokemon.services import items_service
            inventario = items_service.obtener_inventario(user_id)
            
            battle = wild_battle_manager.get_battle(user_id)
            
            text = "🍓 <b>Bayas</b>\n\nSelecciona una baya:"
            
            keyboard = types.InlineKeyboardMarkup(row_width=1)
            
            # Filtrar solo bayas
            bayas = {}
            for item, cantidad in inventario.items():
                item_data = items_service.obtener_item(item)
                if item_data and item_data.get('tipo') == 'baya':
                    bayas[item] = {
                        'cantidad': cantidad,
                        'data': item_data  # ✅ Guardamos item_data para usarlo después
                    }

            if not bayas:
                text = "🍓 <b>Bayas</b>\n\n❌ No tienes bayas"
            else:
                for item, info in bayas.items():
                    cantidad = info['cantidad']
                    item_data = info['data']  # ✅ Ahora sí se usa item_data
                    
                    # Puedes usar item_data para mostrar descripción u otros datos
                    desc = item_data.get('desc', '')
                    
                    keyboard.add(
                        types.InlineKeyboardButton(
                            f"{item.title()} x{cantidad}",
                            callback_data=f"battle_use_berry_{user_id}_{item}"
                        )
                    )
            
            keyboard.add(
                types.InlineKeyboardButton(
                    "◀️ Volver",
                    callback_data=f"battle_bag_{user_id}"
                )
            )

            if not battle:
                logger.error(f"No hay batalla activa para usuario {user_id}")
                return False

            if not battle.message_id:
                logger.error(f"Batalla sin message_id para usuario {user_id}")
                return False            
            self.bot.edit_message_text(
                text,
                user_id,
                battle.message_id,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            
            self.bot.answer_callback_query(call.id)
            
        except Exception as e:
            logger.error(f"Error en handle_berries_button: {e}")
            self.bot.answer_callback_query(
                call.id,
                "❌ Error mostrando bayas",
                show_alert=True
            )

    def handle_forfeit_button(self, call: types.CallbackQuery):
        """Maneja el botón de rendirse"""
        try:
            user_id = call.from_user.id
            
            battle = wild_battle_manager.get_battle(user_id)
            if not battle:
                self.bot.answer_callback_query(
                    call.id,
                    "❌ No tienes una batalla activa",
                    show_alert=True
                )
                return
            
            # Rendirse
            from pokemon.services import spawn_service
            
            text = (
                f"🏳️ <b>Te rendiste</b>\n\n"
                f"{battle.wild_pokemon.nombre} escapó."
            )
            
            # Limpiar spawn y batalla
            spawn_service.limpiar_spawn(battle.thread_id)
            del wild_battle_manager.active_battles[user_id]
            
            self.bot.edit_message_text(
                text,
                user_id,
                battle.message_id,
                parse_mode="HTML"
            )
            
            self.bot.answer_callback_query(call.id)
            
            logger.info(f"[BATTLE] Usuario {user_id} se rindió")
            
        except Exception as e:
            logger.error(f"Error en handle_forfeit_button: {e}")
            self.bot.answer_callback_query(
                call.id,
                "❌ Error procesando rendición",
                show_alert=True
            )
    def handle_bag_category_button(self, call: types.CallbackQuery):
        """
        Maneja click en categoría de mochila.
        Callback: battle_bag_cat_<categoria>_<user_id>
        Ejemplo:  battle_bag_cat_medicine_123456
        """

         # --- VALIDACIÓN ROBUSTA ---
        if not call.data or not call.message:
            return
        
        try:
            user_id = call.from_user.id

            if not wild_battle_manager.has_active_battle(user_id):
                self.bot.answer_callback_query(
                    call.id, "❌ No tienes una batalla activa", show_alert=True
                )
                return

            # Parsear la categoría del callback_data
            # Formato: battle_bag_cat_medicine_123456
            # Índices: [0]=battle [1]=bag [2]=cat [3]=medicine [4]=123456
            parts     = call.data.split('_')
            categoria = parts[3]  # "medicine", "pokeballs" o "berries"

            success = wild_battle_manager.handle_bag_category(user_id, categoria, self.bot)

            if success:
                self.bot.answer_callback_query(call.id)
            else:
                self.bot.answer_callback_query(
                    call.id, "❌ Error mostrando categoría", show_alert=True
                )

        except Exception as e:
            logger.error(f"Error en handle_bag_category_button: {e}")
            self.bot.answer_callback_query(call.id, "❌ Error", show_alert=True)

    def handle_item_selected_button(self, call: types.CallbackQuery):
        """
        Maneja click en un item de la lista.
        Callback: battle_item_<user_id>_<item_key>
        Ejemplo:  battle_item_123456_pocion
        Ejemplo:  battle_item_123456_pocion~maxima  (~ reemplaza espacios)
        """

         # --- VALIDACIÓN ROBUSTA ---
        if not call.data or not call.message:
            return
        
        try:
            user_id = call.from_user.id

            if not wild_battle_manager.has_active_battle(user_id):
                self.bot.answer_callback_query(
                    call.id, "❌ No tienes una batalla activa", show_alert=True
                )
                return

            # Parsear el nombre del item del callback_data
            # Formato: battle_item_123456_pocion~maxima
            # Usamos split con límite 3 para no partir el nombre del item
            parts       = call.data.split('_', 3)
            item_key    = parts[3] if len(parts) > 3 else ""
            item_nombre = item_key.replace('~', ' ')

            success = wild_battle_manager.handle_item_selected(user_id, item_nombre, self.bot)

            if success:
                self.bot.answer_callback_query(call.id)
            else:
                self.bot.answer_callback_query(
                    call.id, "❌ Error con el item", show_alert=True
                )

        except Exception as e:
            logger.error(f"Error en handle_item_selected_button: {e}")
            self.bot.answer_callback_query(call.id, "❌ Error", show_alert=True)

    def handle_use_item_button(self, call: types.CallbackQuery):
        """
        Maneja click en un Pokémon para usar el item.
        Callback: battle_use_item_<user_id>_<item_key>_<pokemon_id>
        Ejemplo:  battle_use_item_123456_pocion_789
        Ejemplo:  battle_use_item_123456_pocion~maxima_789
        """

         # --- VALIDACIÓN ROBUSTA ---
        if not call.data or not call.message:
            return
        
        try:
            user_id = call.from_user.id

            if not wild_battle_manager.has_active_battle(user_id):
                self.bot.answer_callback_query(
                    call.id, "❌ No tienes una batalla activa", show_alert=True
                )
                return

            # Parsear callback_data manualmente para manejar items con espacios (~)
            # Formato: battle_use_item_123456_pocion~maxima_789
            data        = call.data
            sin_prefijo = data[len('battle_use_item_'):]  # "123456_pocion~maxima_789"

            # Separar user_id (primer bloque antes de _)
            idx1     = sin_prefijo.index('_')
            resto    = sin_prefijo[idx1 + 1:]             # "pocion~maxima_789"

            # Separar pokemon_id (último bloque después del último _)
            idx2      = resto.rindex('_')
            item_key  = resto[:idx2]                      # "pocion~maxima"
            poke_id   = int(resto[idx2 + 1:])             # 789

            item_nombre = item_key.replace('~', ' ')

            success = wild_battle_manager.handle_use_item_on_pokemon(
                user_id, item_nombre, poke_id, self.bot
            )

            if success:
                self.bot.answer_callback_query(call.id)
            else:
                self.bot.answer_callback_query(
                    call.id, "❌ No se pudo usar el item", show_alert=True
                )

        except Exception as e:
            logger.error(f"Error en handle_use_item_button: {e}")
            self.bot.answer_callback_query(call.id, "❌ Error", show_alert=True)

def setup_wild_battle_callbacks(bot):
    """
    Función para configurar los callbacks de batalla salvaje
    
    Args:
        bot: Instancia del bot de Telegram
    """
    WildBattleCallbacks(bot)
    logger.info("[BATTLE] Sistema de callbacks de batalla inicializado")
