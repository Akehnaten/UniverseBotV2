# -*- coding: utf-8 -*-
"""
pokemon/move_reminder.py
══════════════════════════════════════════════════════════════════════════════
NPC Recordador de Movimientos.

Permite al jugador recuperar cualquier movimiento del learnset de su Pokémon
que haya olvidado, reemplazando uno de los que ya sabe.

Flujo:
  pokemenu_reminder_{uid}              → selector de Pokémon del equipo
  pokemenu_reminder_pk_{uid}_{poke_id} → lista de movimientos olvidables
  pokemenu_reminder_mv_{uid}_{poke_id}_{move_key} → selector de slot a reemplazar
  pokemenu_reminder_sl_{uid}_{poke_id}_{move_key}_{slot} → confirmar

Costo: 0 (el recordador clásico es gratuito en los juegos).
══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
from typing import Optional

from telebot import types

logger = logging.getLogger(__name__)

TITULO_NPC = "📚 Recordador de Movimientos"


def _edit_or_send(message, bot, user_id: int, texto: str, markup) -> None:
    try:
        bot.edit_message_text(
            texto, message.chat.id, message.message_id,
            parse_mode="HTML", reply_markup=markup,
        )
    except Exception:
        bot.send_message(user_id, texto, parse_mode="HTML", reply_markup=markup)


def _kb_volver(user_id: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        "⬅️ Menú Pokémon", callback_data=f"pokemenu_back_{user_id}"
    ))
    return kb


# ─── PASO 1: Elegir Pokémon ──────────────────────────────────────────────────

def mostrar_selector_pokemon(user_id: int, message, bot) -> None:
    from pokemon.services import pokemon_service

    equipo = pokemon_service.obtener_equipo(user_id)
    if not equipo:
        _edit_or_send(message, bot, user_id,
                      "❌ No tienes Pokémon en tu equipo.", _kb_volver(user_id))
        return

    texto = (
        f"{TITULO_NPC}\n\n"
        "Aquí puedo enseñarle a tu Pokémon un movimiento que haya olvidado.\n\n"
        "¿Con qué Pokémon quieres trabajar?"
    )
    kb = types.InlineKeyboardMarkup(row_width=1)
    for poke in equipo:
        nombre = poke.mote or poke.nombre
        sexo   = {"M": " ♂", "F": " ♀"}.get(getattr(poke, "sexo", None) or "", "")
        kb.add(types.InlineKeyboardButton(
            f"{nombre}{sexo} — Nv.{poke.nivel}",
            callback_data=f"pokemenu_reminder_pk_{user_id}_{poke.id_unico}",
        ))
    kb.add(types.InlineKeyboardButton(
        "⬅️ Volver", callback_data=f"pokemenu_back_{user_id}"
    ))
    _edit_or_send(message, bot, user_id, texto, kb)


# ─── PASO 2: Elegir movimiento a recordar ────────────────────────────────────

def mostrar_movimientos_olvidados(user_id: int, poke_id: int, message, bot) -> None:
    from pokemon.services import pokemon_service
    from pokemon.services.movimientos_service import movimientos_service
    from pokemon.battle_engine import MOVE_NAMES_ES

    poke = pokemon_service.obtener_pokemon(poke_id)
    if not poke or poke.usuario_id != user_id:
        _edit_or_send(message, bot, user_id, "❌ Pokémon no encontrado.", _kb_volver(user_id))
        return

    nombre_poke = poke.mote or poke.nombre

    # Todos los movimientos que puede aprender hasta su nivel actual
    learnset = movimientos_service.obtener_learnset(poke.pokemonID)
    todos_aprendibles: set[str] = set()
    for lvl, moves in learnset.items():
        if lvl <= poke.nivel:
            for m in moves:
                todos_aprendibles.add(m.lower().replace(" ", "").replace("-", ""))

    # Movimientos actuales (normalizados)
    actuales_norm = {
        m.lower().replace(" ", "").replace("-", "")
        for m in (poke.movimientos or [])
        if m
    }

    # Movimientos olvidados = aprendibles - actuales
    olvidados_norm = todos_aprendibles - actuales_norm
    if not olvidados_norm:
        _edit_or_send(
            message, bot, user_id,
            f"{TITULO_NPC}\n\n"
            f"<b>{nombre_poke}</b> ya conoce todos los movimientos disponibles "
            f"para su nivel. ¡No hay nada que recordar!",
            _kb_volver(user_id),
        )
        return

    # Construir lista legible ordenada
    movimientos_display: list[tuple[str, str]] = []
    for mk in sorted(olvidados_norm):
        nombre_es = MOVE_NAMES_ES.get(mk, mk.replace("_", " ").title())
        movimientos_display.append((mk, nombre_es))

    texto = (
        f"{TITULO_NPC}\n\n"
        f"<b>{nombre_poke}</b> puede recordar estos movimientos olvidados:\n\n"
        "Elige el movimiento que quieres recuperar:"
    )
    kb = types.InlineKeyboardMarkup(row_width=2)
    for mk, nombre_es in movimientos_display[:20]:   # máximo 20 para no saturar
        kb.add(types.InlineKeyboardButton(
            nombre_es,
            callback_data=f"pokemenu_reminder_mv_{user_id}_{poke_id}_{mk}",
        ))
    kb.add(types.InlineKeyboardButton(
        "⬅️ Volver", callback_data=f"pokemenu_reminder_{user_id}"
    ))
    _edit_or_send(message, bot, user_id, texto, kb)


# ─── PASO 3: Elegir slot a reemplazar ────────────────────────────────────────

def mostrar_selector_slot(user_id: int, poke_id: int,
                           move_key: str, message, bot) -> None:
    from pokemon.services import pokemon_service
    from pokemon.battle_engine import MOVE_NAMES_ES
    from pokemon.services.movimientos_service import movimientos_service

    poke = pokemon_service.obtener_pokemon(poke_id)
    if not poke or poke.usuario_id != user_id:
        _edit_or_send(message, bot, user_id, "❌ Pokémon no encontrado.", _kb_volver(user_id))
        return

    nombre_poke  = poke.mote or poke.nombre
    nombre_nuevo = MOVE_NAMES_ES.get(move_key, move_key.title())
    movs_actuales = poke.movimientos or []

    if len(movs_actuales) < 4:
        # Slot libre — aprender directamente
        _aplicar_recordar(user_id, poke_id, move_key, None, message, bot)
        return

    texto = (
        f"{TITULO_NPC}\n\n"
        f"<b>{nombre_poke}</b> quiere recordar <b>{nombre_nuevo}</b>.\n\n"
        "¿Qué movimiento quieres reemplazar?"
    )
    kb = types.InlineKeyboardMarkup(row_width=1)
    for i, mv in enumerate(movs_actuales):
        if not mv:
            continue
        mv_norm   = mv.lower().replace(" ", "").replace("-", "")
        mv_nombre = MOVE_NAMES_ES.get(mv_norm, mv.title())
        kb.add(types.InlineKeyboardButton(
            f"❌ Olvidar {mv_nombre}",
            callback_data=f"pokemenu_reminder_sl_{user_id}_{poke_id}_{move_key}_{i}",
        ))
    kb.add(types.InlineKeyboardButton(
        "🚫 Cancelar", callback_data=f"pokemenu_reminder_pk_{user_id}_{poke_id}"
    ))
    _edit_or_send(message, bot, user_id, texto, kb)


# ─── PASO 4: Aplicar ─────────────────────────────────────────────────────────

def _aplicar_recordar(user_id: int, poke_id: int, move_key: str,
                       slot: Optional[int], message, bot) -> None:
    from pokemon.services import pokemon_service
    from database import db_manager
    from pokemon.battle_engine import MOVE_NAMES_ES
    from pokemon.services.movimientos_service import movimientos_service
    from pokemon.services.pp_service import pp_service

    poke = pokemon_service.obtener_pokemon(poke_id)
    if not poke or poke.usuario_id != user_id:
        _edit_or_send(message, bot, user_id, "❌ Pokémon no encontrado.", _kb_volver(user_id))
        return

    nombre_poke  = poke.mote or poke.nombre
    nombre_nuevo = MOVE_NAMES_ES.get(move_key, move_key.title())
    movs         = list(poke.movimientos or [])

    olvidado_nombre = None
    if slot is not None and slot < len(movs):
        old_mk         = movs[slot]
        olvidado_nombre = MOVE_NAMES_ES.get(
            (old_mk or "").lower().replace(" ", "").replace("-", ""),
            (old_mk or "").title(),
        )
        movs[slot] = move_key
        col = f"move{slot + 1}"
        db_manager.execute_update(
            f"UPDATE POKEMON_USUARIO SET {col} = ? WHERE id_unico = ?",
            (move_key, poke_id),
        )
    else:
        # Slot libre
        movs = [m for m in movs if m]
        if len(movs) < 4:
            movs.append(move_key)
            cols = ["move1", "move2", "move3", "move4"]
            col  = cols[len(movs) - 1]
            db_manager.execute_update(
                f"UPDATE POKEMON_USUARIO SET {col} = ? WHERE id_unico = ?",
                (move_key, poke_id),
            )
        else:
            _edit_or_send(message, bot, user_id,
                          "❌ No hay slots disponibles.", _kb_volver(user_id))
            return

    # Inicializar PP del nuevo movimiento
    try:
        pp_service.inicializar_pp_movimientos(poke_id, movs)
    except Exception as exc:
        logger.warning(f"[REMINDER] Error inicializando PP: {exc}")

    if olvidado_nombre:
        texto = (
            f"{TITULO_NPC}\n\n"
            f"✅ <b>{nombre_poke}</b> olvidó <b>{olvidado_nombre}</b>\n"
            f"y recordó <b>{nombre_nuevo}</b>!"
        )
    else:
        texto = (
            f"{TITULO_NPC}\n\n"
            f"✅ <b>{nombre_poke}</b> recordó <b>{nombre_nuevo}</b>!"
        )

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            "🔄 Recordar otro movimiento",
            callback_data=f"pokemenu_reminder_pk_{user_id}_{poke_id}",
        ),
        types.InlineKeyboardButton(
            "⬅️ Menú Pokémon", callback_data=f"pokemenu_back_{user_id}"
        ),
    )
    _edit_or_send(message, bot, user_id, texto, kb)


# ─── Handler de aplicar desde callback ───────────────────────────────────────

def aplicar_desde_callback(user_id: int, poke_id: int,
                             move_key: str, slot: int, message, bot) -> None:
    _aplicar_recordar(user_id, poke_id, move_key, slot, message, bot)