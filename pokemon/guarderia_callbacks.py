# -*- coding: utf-8 -*-
"""
Guardería Callbacks
===================
Maneja todos los callbacks de botones de la guardería Pokémon.

Patrón idéntico a wild_battle_callbacks.py:
- Clase GuarderiaCallbacks con __init__(bot) que registra sus propios callbacks
- Función setup_guarderia_callbacks(bot) que se llama desde UniverseBot.py

Los prefijos de callback que maneja este módulo:
    daycare_*   → menú y acciones de guardería
    mote_*      → respuesta de apodo tras eclosión
"""

import logging
from telebot import types

logger = logging.getLogger(__name__)


class GuarderiaCallbacks:
    """Manejador de callbacks para la guardería Pokémon"""

    def __init__(self, bot):
        self.bot = bot
        self._register_callbacks()

    def _register_callbacks(self):
        """Registra todos los callbacks de guardería en el bot."""

        self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('daycare_')
        )(self._handle_daycare)

        self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('mote_no_')
        )(self._handle_mote_no)

        logger.info("[GUARDERIA_CALLBACKS] Callbacks de guardería registrados")

    # ──────────────────────────────────────────────────────────
    # DISPATCHER PRINCIPAL daycare_*
    # ──────────────────────────────────────────────────────────

    def _handle_daycare(self, call: types.CallbackQuery):
        """
        Procesa todos los callbacks daycare_<accion>_<uid>[_<extra>].

        Prefijos usados:
            daycare_menu_<uid>              → mostrar menú principal
            daycare_depositar_<uid>         → elegir Pokémon a depositar
            daycare_retirar_<uid>           → elegir Pokémon a retirar
            daycare_rethuevo_<uid>          → elegir huevo a retirar
            daycare_dep_<uid>_<poke_id>     → confirmar depósito
            daycare_ret_<uid>_<poke_id>     → confirmar retiro de Pokémon
            daycare_delhuevo_<uid>_<huevo_id> → confirmar eliminación de huevo
        """
        from pokemon.menu_pokemon import MenuPokemon
        from pokemon.services.crianza_service import crianza_service
        from database import db_manager

        data = call.data
        parts = data.split('_')
        # partes mínimas: daycare / accion / uid
        if len(parts) < 3:
            self.bot.answer_callback_query(call.id, "❌ Datos inválidos")
            return

        accion = parts[1]

        # Validar que el uid del callback coincide con quien pulsa
        try:
            uid_callback = int(parts[2])
        except ValueError:
            self.bot.answer_callback_query(call.id, "❌ UID inválido")
            return

        if call.from_user.id != uid_callback:
            self.bot.answer_callback_query(call.id, "❌ Este menú no es tuyo", show_alert=True)
            return

        user_id = uid_callback

        if accion == 'menu':
            MenuPokemon._mostrar_guarderia(user_id, call.message, self.bot)
            self.bot.answer_callback_query(call.id)

        elif accion == 'depositar':
            MenuPokemon._guarderia_depositar(user_id, call.message, self.bot)
            self.bot.answer_callback_query(call.id)

        elif accion == 'retirar':
            MenuPokemon._guarderia_retirar(user_id, call.message, self.bot)
            self.bot.answer_callback_query(call.id)

        elif accion == 'rethuevo':
            MenuPokemon._guarderia_retirar_huevo(user_id, call.message, self.bot)
            self.bot.answer_callback_query(call.id)

        elif accion == 'dep':
            # daycare_dep_<uid>_<poke_id>
            if len(parts) < 4:
                self.bot.answer_callback_query(call.id, "❌ Datos incompletos")
                return
            try:
                poke_id = int(parts[3])
            except ValueError:
                self.bot.answer_callback_query(call.id, "❌ ID inválido")
                return

            ok, msg = crianza_service.depositar_en_guarderia(user_id, poke_id)
            self.bot.answer_callback_query(call.id, msg, show_alert=not ok)
            if ok:
                # Si ya hay 2 en guardería, intentar producir huevo
                tiene_huevo, msg_h, _ = crianza_service.intentar_producir_huevo(user_id)
                MenuPokemon._mostrar_guarderia(user_id, call.message, self.bot)
                if tiene_huevo:
                    self.bot.send_message(user_id, msg_h)

        elif accion == 'ret':
            # daycare_ret_<uid>_<poke_id>
            if len(parts) < 4:
                self.bot.answer_callback_query(call.id, "❌ Datos incompletos")
                return
            try:
                poke_id = int(parts[3])
            except ValueError:
                self.bot.answer_callback_query(call.id, "❌ ID inválido")
                return

            ok, msg = crianza_service.retirar_de_guarderia(user_id, poke_id)
            self.bot.answer_callback_query(call.id, msg, show_alert=not ok)
            if ok:
                MenuPokemon._mostrar_guarderia(user_id, call.message, self.bot)

        elif accion == 'delhuevo':
            # daycare_delhuevo_<uid>_<huevo_id>
            if len(parts) < 4:
                self.bot.answer_callback_query(call.id, "❌ Datos incompletos")
                return
            try:
                huevo_id = int(parts[3])
            except ValueError:
                self.bot.answer_callback_query(call.id, "❌ ID inválido")
                return

            ok, msg = crianza_service.retirar_huevo(user_id, huevo_id)
            self.bot.answer_callback_query(call.id, msg, show_alert=not ok)
            MenuPokemon._mostrar_guarderia(user_id, call.message, self.bot)

        else:
            self.bot.answer_callback_query(call.id, "Acción no reconocida.")

    # ──────────────────────────────────────────────────────────
    # CALLBACK mote_no_* (botón "Sin apodo")
    # ──────────────────────────────────────────────────────────

    def _handle_mote_no(self, call: types.CallbackQuery):
        """
        Procesa el botón 'Sin apodo' tras la eclosión de un huevo.
        Formato: mote_no_<uid>_<pokemon_id>
        """
        from pokemon.services.crianza_service import crianza_service
        from pokemon.guarderia_steps import _esperando_mote

        parts = call.data.split('_')
        if len(parts) < 4:
            self.bot.answer_callback_query(call.id, "❌ Datos inválidos")
            return

        try:
            uid_callback = int(parts[2])
            pokemon_id   = int(parts[3])
        except ValueError:
            self.bot.answer_callback_query(call.id, "❌ IDs inválidos")
            return

        if call.from_user.id != uid_callback:
            self.bot.answer_callback_query(call.id, "❌ No es tu Pokémon", show_alert=True)
            return

        # Limpiar estado pendiente si existe
        _esperando_mote.pop(uid_callback, None)

        ok, msg = crianza_service.finalizar_eclosion(uid_callback, pokemon_id, None)
        self.bot.answer_callback_query(call.id)

        # Editar el mensaje original quitando los botones
        try:
            if call.message.content_type in ("photo", "animation", "document", "video"):
                self.bot.edit_message_caption(
                    caption=msg,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode="HTML",
                    reply_markup=None,
                )
            else:
                self.bot.edit_message_text(
                    text=msg,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode="HTML",
                    reply_markup=None,
                )
        except Exception as e:
            logger.warning(f"[GUARDERIA] No se pudo editar mensaje mote_no: {e}")
            self.bot.send_message(uid_callback, msg)


def setup_guarderia_callbacks(bot):
    """
    Inicializa los callbacks de guardería.
    Se llama desde UniverseBot.py igual que setup_wild_battle_callbacks.
    """
    GuarderiaCallbacks(bot)
    logger.info("[GUARDERIA] Sistema de callbacks de guardería inicializado")