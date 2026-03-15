# -*- coding: utf-8 -*-
"""
pokemon/pvp_battle_callbacks.py
════════════════════════════════════════════════════════════════════════════════
Callbacks de Telegram para el sistema PvP/VGC.
Equivalente a wild_battle_callbacks.py pero para batallas entre jugadores.

Se registra en UniverseBot.py exactamente igual que los otros sistemas:

    from pokemon.pvp_battle_callbacks import setup_pvp_callbacks
    setup_pvp_callbacks(bot)
════════════════════════════════════════════════════════════════════════════════
"""
import logging
from telebot import types
from pokemon.pvp_battle_system import pvp_manager, pvp_cmd

logger = logging.getLogger(__name__)


class PvPCallbacks:
    """Manejador de callbacks para batallas PvP / VGC."""

    def __init__(self, bot):
        self.bot = bot
        self._register()

    # ── Registro ──────────────────────────────────────────────────────────────

    def _register(self):
        handlers = [
            # Selección de formato
            (lambda c: c.data.startswith("pvp_fmt_"),         self._cb_fmt),
            # Aceptar / Rechazar desafío
            (lambda c: c.data in ("pvp_accept", "pvp_reject"), self._cb_accept_reject),
            # Menú principal → sub-menú ataques
            (lambda c: c.data.startswith("pvp_fight_"),        self._cb_fight),
            # Sub-menú ataques → menú principal
            (lambda c: c.data.startswith("pvp_back_"),         self._cb_back),
            # Sub-menú equipo
            (lambda c: c.data.startswith("pvp_team_"),         self._cb_team),
            # Rendirse
            (lambda c: c.data.startswith("pvp_forfeit_"),      self._cb_forfeit),
            # Movimiento elegido
            (lambda c: c.data.startswith("pvp_move_"),         self._cb_move),
            # Cambio de Pokémon
            (lambda c: c.data.startswith("pvp_switch_"),       self._cb_switch),
            # VGC — selección de equipo
            (lambda c: c.data.startswith("pvp_vgcsel_"),       self._cb_vgc_toggle),
            (lambda c: c.data.startswith("pvp_vgcconfirm_"),   self._cb_vgc_confirm),
            # Botones deshabilitados / informativos
            (lambda c: c.data.startswith("pvp_noop_")
                    or c.data.startswith("pvp_vgcnoop_"),       self._cb_noop),
        ]
        for func, handler in handlers:
            self.bot.callback_query_handler(func=func)(handler)

        logger.info("[PVP_CALLBACKS] Callbacks PvP registrados")

    # ── Selección de formato ──────────────────────────────────────────────────

    def _cb_fmt(self, call: types.CallbackQuery):
        pvp_cmd.handle_format_selection(call, self.bot)

    # ── Aceptar / Rechazar ────────────────────────────────────────────────────

    def _cb_accept_reject(self, call: types.CallbackQuery):
        pvp_manager.handle_callback(call, self.bot)

    # ── Menú principal → ataques ──────────────────────────────────────────────

    def _cb_fight(self, call: types.CallbackQuery):
        """pvp_fight_{user_id}"""
        try:
            uid = int(call.data.split("_")[-1])
            if call.from_user.id != uid:
                self.bot.answer_callback_query(call.id, "❌ No es tu turno.")
                return
            pvp_manager.handle_fight_action(uid, self.bot)
            self.bot.answer_callback_query(call.id)
        except Exception as exc:
            logger.error(f"[PVP_CB] fight: {exc}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Error.")

    # ── Volver al menú principal ──────────────────────────────────────────────

    def _cb_back(self, call: types.CallbackQuery):
        """pvp_back_{user_id}"""
        try:
            uid = int(call.data.split("_")[-1])
            if call.from_user.id != uid:
                self.bot.answer_callback_query(call.id, "❌ No es tu panel.")
                return
            pvp_manager.handle_back_action(uid, self.bot)
            self.bot.answer_callback_query(call.id)
        except Exception as exc:
            logger.error(f"[PVP_CB] back: {exc}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Error.")

    # ── Sub-menú equipo ───────────────────────────────────────────────────────

    def _cb_team(self, call: types.CallbackQuery):
        """pvp_team_{user_id}"""
        try:
            uid = int(call.data.split("_")[-1])
            if call.from_user.id != uid:
                self.bot.answer_callback_query(call.id, "❌ No es tu equipo.")
                return
            pvp_manager.handle_team_pvp(uid, self.bot)
            self.bot.answer_callback_query(call.id)
        except Exception as exc:
            logger.error(f"[PVP_CB] team: {exc}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Error.")

    # ── Rendirse ──────────────────────────────────────────────────────────────

    def _cb_forfeit(self, call: types.CallbackQuery):
        """pvp_forfeit_{user_id}"""
        try:
            uid = int(call.data.split("_")[-1])
            if call.from_user.id != uid:
                self.bot.answer_callback_query(call.id, "❌ No es tu batalla.")
                return
            pvp_manager.handle_forfeit_pvp(uid, self.bot)
            self.bot.answer_callback_query(call.id)
        except Exception as exc:
            logger.error(f"[PVP_CB] forfeit: {exc}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Error.")

    # ── Movimiento ────────────────────────────────────────────────────────────

    def _cb_move(self, call: types.CallbackQuery):
        pvp_manager.handle_callback(call, self.bot)

    # ── Cambio de Pokémon ─────────────────────────────────────────────────────

    def _cb_switch(self, call: types.CallbackQuery):
        pvp_manager.handle_callback(call, self.bot)

    # ── VGC — selección de equipo ─────────────────────────────────────────────

    def _cb_vgc_toggle(self, call: types.CallbackQuery):
        """pvp_vgcsel_{battle_id}_{user_id}_{pokemon_id}"""
        try:
            parts      = call.data.split("_")
            pokemon_id = int(parts[-1])
            user_id    = int(parts[-2])
            battle_id  = "_".join(parts[1:-2])

            if call.from_user.id != user_id:
                self.bot.answer_callback_query(call.id, "❌ No es tu selección.")
                return

            pvp_manager.handle_vgc_selection_toggle(
                battle_id, user_id, pokemon_id, self.bot, call.message
            )
            self.bot.answer_callback_query(call.id)
        except Exception as exc:
            logger.error(f"[PVP_CB] vgc_toggle: {exc}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Error.")

    def _cb_vgc_confirm(self, call: types.CallbackQuery):
        """pvp_vgcconfirm_{battle_id}_{user_id}"""
        try:
            parts     = call.data.split("_")
            user_id   = int(parts[-1])
            battle_id = "_".join(parts[1:-1])

            if call.from_user.id != user_id:
                self.bot.answer_callback_query(call.id, "❌ No es tu selección.")
                return

            ok, msg = pvp_manager.handle_vgc_confirm_selection(
                battle_id, user_id, self.bot, call.message
            )
            self.bot.answer_callback_query(call.id, msg if not ok else "✅")
        except Exception as exc:
            logger.error(f"[PVP_CB] vgc_confirm: {exc}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Error.")

    # ── Botones deshabilitados ────────────────────────────────────────────────

    def _cb_noop(self, call: types.CallbackQuery):
        self.bot.answer_callback_query(call.id, show_alert=False)


def setup_pvp_callbacks(bot):
    """
    Inicializa el sistema PvP completo (callbacks + comando /retar).
    Llamar desde UniverseBot.py.
    """
    PvPCallbacks(bot)
    pvp_cmd.register(bot)
    logger.info("✅ Sistema PvP/VGC inicializado")