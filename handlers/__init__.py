# -*- coding: utf-8 -*-
"""
handlers/__init__.py
Configura todos los manejadores de comandos en orden determinístico.

ORDEN DE REGISTRO (importa en pyTelegramBotAPI):
  1. Handlers de comandos específicos (commands=[...]) — primero siempre.
  2. Juan — tiene func=lambda que excluye "/" así que no chupa comandos,
     pero debe ir ANTES de cualquier handler con content_types=["text"] sin
     filtro (Forwarder, EventHandlers) para recibir texto normal primero.
  3. Forwarder — captura media antes de roulette/photocards.
  4. Resto de handlers de contenido.
  5. Juan ya no va al final.
"""

import logging

logger = logging.getLogger(__name__)


def setup_all_handlers(bot):
    handlers_initialized = []

    # ── 0. Juan PRIMERO — su func excluye "/" así que nunca chupa comandos ───
    try:
        from handlers.juan_handler import setup_juan_handler
        setup_juan_handler(bot)
        handlers_initialized.append("Juan")
        logger.info("✅ Juan (el caballo) cargado")
    except Exception as e:
        logger.error(f"❌ Juan handler: {e}", exc_info=True)

    # ── 1. Handlers de comandos específicos ──────────────────────────────────

    try:
        from handlers.basic_handlers import BasicUserHandlers
        BasicUserHandlers(bot)
        handlers_initialized.append("Basic")
        logger.info("✅ Basic handlers configurados")
    except Exception as e:
        logger.error(f"❌ Basic handlers: {e}", exc_info=True)

    try:
        from handlers.pokemon_handlers import PokemonHandlers
        PokemonHandlers(bot)
        handlers_initialized.append("Pokemon")
        logger.info("✅ Pokemon handlers configurados")
    except Exception as e:
        logger.error(f"❌ Pokemon handlers: {e}", exc_info=True)

    try:
        from handlers.economy_handlers import EconomyHandlers
        EconomyHandlers(bot)
        handlers_initialized.append("Economy")
        logger.info("✅ Economy handlers configurados")
    except Exception as e:
        logger.error(f"❌ Economy handlers: {e}", exc_info=True)

    try:
        from handlers.casino_handlers import CasinoHandlers
        CasinoHandlers(bot)
        handlers_initialized.append("Casino")
        logger.info("✅ Casino handlers configurados")
    except Exception as e:
        logger.error(f"❌ Casino handlers: {e}", exc_info=True)

    try:
        from handlers.admin_handlers import AdminHandlers
        AdminHandlers(bot)
        handlers_initialized.append("Admin")
        logger.info("✅ Admin handlers configurados")
    except Exception as e:
        logger.error(f"❌ Admin handlers: {e}", exc_info=True)

    try:
        from handlers.role_handlers import RoleHandlers
        RoleHandlers(bot)
        handlers_initialized.append("Role")
        logger.info("✅ Role handlers configurados")
    except Exception as e:
        logger.error(f"❌ Role handlers: {e}", exc_info=True)

    try:
        from handlers.betting_handlers import BettingHandlers
        BettingHandlers(bot)
        handlers_initialized.append("Betting")
        logger.info("✅ Betting handlers configurados")
    except Exception as e:
        logger.error(f"❌ Betting handlers: {e}", exc_info=True)

    try:
        from handlers.roulette_handlers import RouletteHandlers
        RouletteHandlers(bot)
        handlers_initialized.append("Roulette")
        logger.info("✅ Roulette handlers configurados")
    except Exception as e:
        logger.error(f"❌ Roulette handlers: {e}", exc_info=True)

    try:
        from handlers.photocards_handlers import PhotocardsHandlers
        PhotocardsHandlers(bot)
        handlers_initialized.append("Photocards")
        logger.info("✅ Photocards handlers configurados")
    except Exception as e:
        logger.error(f"❌ Photocard handlers: {e}", exc_info=True)

    try:
        from handlers.intercambio_handler import IntercambioHandler
        IntercambioHandler(bot)
        handlers_initialized.append("Intercambio")
        logger.info("✅ Intercambio handlers configurados")
    except Exception as e:
        logger.error(f"❌ Intercambio handlers: {e}", exc_info=True)

    try:
        from pokemon.trade_handler import TradeHandler
        TradeHandler(bot)
        handlers_initialized.append("Trade")
        logger.info("✅ Trade handler configurado")
    except Exception as e:
        logger.error(f"❌ Trade handler: {e}", exc_info=True)

    try:
        from pokemon.gym_battle_system import gym_cmd
        gym_cmd.register(bot)
        handlers_initialized.append("Gym")
        logger.info("✅ Gym handlers configurados")
    except Exception as e:
        logger.error(f"❌ Gym handlers: {e}", exc_info=True)

    try:
        from pokemon.item_use_system import register_item_use_callbacks
        register_item_use_callbacks(bot)
        handlers_initialized.append("ItemUse")
        logger.info("✅ ItemUse callbacks configurados")
    except Exception as e:
        logger.error(f"❌ ItemUse callbacks: {e}", exc_info=True)

    try:
        from handlers.apodo_handler import ApodoHandler
        ApodoHandler(bot)
        handlers_initialized.append("Apodo")
        logger.info("✅ Apodo handler configurado")
    except Exception as e:
        logger.error(f"❌ Apodo handler: {e}", exc_info=True)

    try:
        from pokemon.level_up_handler import registrar_callbacks
        registrar_callbacks(bot)
        handlers_initialized.append("LevelUp")
        logger.info("✅ LevelUp callbacks configurados")
    except Exception as e:
        logger.error(f"❌ LevelUp callbacks: {e}", exc_info=True)

    try:
        from handlers.event_handlers import EventHandlers
        EventHandlers(bot)
        handlers_initialized.append("Event")
        logger.info("✅ Event handlers configurados")
    except Exception as e:
        logger.error(f"❌ Event handlers: {e}", exc_info=True)

    logger.info(
        "[HANDLERS] %d módulos configurados: %s",
        len(handlers_initialized),
        ", ".join(handlers_initialized),
    )


__all__ = ["setup_all_handlers"]
