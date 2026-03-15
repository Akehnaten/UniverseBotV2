# -*- coding: utf-8 -*-
"""
pokemon/battle_adapter.py
═══════════════════════════════════════════════════════════════════════════════
Funciones de adaptación entre los modelos nativos de cada sistema de batalla
y el UniversalSide del motor. Importado por wild, pvp y gym.

No contiene lógica de combate — solo mapeo de datos y persistencia en BD.
═══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
from typing import Optional

from database import db_manager
from pokemon.services import pokemon_service
from pokemon.services.pokedex_service import pokedex_service
from pokemon.battle_engine import UniversalSide

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Construcción de UniversalSide desde distintos modelos
# ─────────────────────────────────────────────────────────────────────────────

def side_from_wild(wild, battle) -> UniversalSide:
    """Construye un UniversalSide a partir de un WildPokemon + BattleData."""
    return UniversalSide(
        name            = wild.nombre,
        pokemon_db_id   = 0,           # salvajes no tienen id_unico en BD
        species_id      = wild.pokemon_id,
        level           = wild.nivel,
        ability         = "",
        hp_actual       = wild.hp_actual,
        hp_max          = wild.hp_max,
        stats           = wild.stats,
        types           = wild.tipos,
        moves           = wild.moves,
        stat_stages     = battle.wild_stat_stages,
        crit_stage      = getattr(battle, "wild_crit_stage", 0),
        status          = battle.wild_status,
        sleep_turns     = battle.wild_sleep_turns,
        toxic_counter   = battle.wild_toxic_counter,
        yawn_counter    = battle.wild_yawn_counter,
        confusion_turns = getattr(battle, "wild_confusion_turns", 0),
        leechseeded      = getattr(battle, "wild_leechseeded", False),
        charging_move    = getattr(wild, "charging_move", None),
        recharge_pending = getattr(wild, "recharge_pending", False),
    )


def side_from_player(player, battle) -> UniversalSide:
    """Construye un UniversalSide a partir de un Pokémon de usuario + BattleData."""
    tipos = []
    try:
        tipos = pokedex_service.obtener_tipos(player.pokemonID)
    except Exception:
        tipos = ["Normal"]

    return UniversalSide(
        name            = player.mote or player.nombre,
        pokemon_db_id   = player.id_unico,
        species_id      = player.pokemonID,
        level           = player.nivel,
        ability         = getattr(player, "habilidad", "") or "",
        hp_actual       = player.hp_actual,
        hp_max          = player.stats.get("hp", player.hp_actual) or player.hp_actual,
        stats           = player.stats,
        types           = tipos,
        moves           = player.movimientos or [],
        stat_stages     = battle.player_stat_stages,
        crit_stage      = getattr(battle, "player_crit_stage", 0),
        status          = battle.player_status,
        sleep_turns     = battle.player_sleep_turns,
        toxic_counter   = battle.player_toxic_counter,
        yawn_counter    = battle.player_yawn_counter,
        confusion_turns = getattr(battle, "player_confusion_turns", 0),
        leechseeded     = getattr(battle, "player_leechseeded", False),
        charging_move    = getattr(battle, "player_charging_move", None),
        recharge_pending = getattr(battle, "player_recharge_pending", False),
        berry_eaten      = getattr(battle, "player_berry_eaten", False),
        objeto           = getattr(player, "objeto", None) or None,
    )


def side_from_pvp(pvp_side, pokedex_svc=None) -> UniversalSide:
    """Construye un UniversalSide desde un PvPSide."""
    poke = pvp_side.get_active_pokemon()
    tipos = []
    if poke:
        try:
            tipos = (pokedex_svc or pokedex_service).obtener_tipos(poke.pokemonID)
        except Exception:
            tipos = ["Normal"]
    return UniversalSide(
        name            = (poke.mote or poke.nombre) if poke else "?",
        pokemon_db_id   = poke.id_unico if poke else 0,
        species_id      = poke.pokemonID if poke else 0,
        level           = poke.nivel if poke else 1,
        ability         = getattr(poke, "habilidad", "") or "" if poke else "",
        hp_actual       = poke.hp_actual if poke else 0,
        hp_max          = poke.stats.get("hp", 1) if poke else 1,
        stats           = poke.stats if poke else {},
        types           = tipos,
        moves           = poke.movimientos or [] if poke else [],
        stat_stages     = pvp_side.stat_stages,
        crit_stage      = pvp_side.crit_stage,
        status          = pvp_side.status,
        sleep_turns     = pvp_side.sleep_turns,
        toxic_counter   = pvp_side.toxic_counter,
        yawn_counter    = pvp_side.yawn_counter,
        confusion_turns = pvp_side.confusion_turns,
        leechseeded      = pvp_side.leechseeded,
        berry_eaten      = getattr(pvp_side, "berry_eaten", False),
        objeto           = getattr(poke, "objeto", None) or None if poke else None,
    )


def side_from_gym_player(battle) -> UniversalSide:
    """Construye un UniversalSide para el jugador en una batalla de gimnasio."""
    player = pokemon_service.obtener_pokemon(battle.player_pokemon_id)
    tipos  = []
    if player:
        try:
            tipos = pokedex_service.obtener_tipos(player.pokemonID)
        except Exception:
            tipos = ["Normal"]
    return UniversalSide(
        name            = (player.mote or player.nombre) if player else "?",
        pokemon_db_id   = player.id_unico if player else 0,
        species_id      = player.pokemonID if player else 0,
        level           = player.nivel if player else 1,
        ability         = getattr(player, "habilidad", "") or "" if player else "",
        hp_actual       = player.hp_actual if player else 0,
        hp_max          = player.stats.get("hp", 1) if player else 1,
        stats           = player.stats if player else {},
        types           = tipos,
        moves           = player.movimientos or [] if player else [],
        stat_stages     = battle.player_stat_stages,
        crit_stage      = 0,
        status          = battle.player_status,
        sleep_turns     = battle.player_sleep_turns,
        toxic_counter   = battle.player_toxic_counter,
        yawn_counter    = battle.player_yawn_counter,
        confusion_turns = getattr(battle, "player_confusion_turns", 0),
        leechseeded     = getattr(battle, "player_leechseeded", False),
        delayed_attacks  = list(getattr(battle, "player_delayed_attacks", [])),
        objeto           = getattr(player, "objeto", None) or None,
    )


def side_from_gym_npc(battle) -> UniversalSide:
    """Construye un UniversalSide para el NPC en una batalla de gimnasio."""
    npc   = pokemon_service.obtener_pokemon(battle.npc_pokemon_id) if battle.npc_pokemon_id else None
    tipos = []
    if npc:
        try:
            tipos = pokedex_service.obtener_tipos(npc.pokemonID)
        except Exception:
            tipos = ["Normal"]
    return UniversalSide(
        name            = npc.nombre if npc else "?",
        pokemon_db_id   = npc.id_unico if npc else 0,
        species_id      = npc.pokemonID if npc else 0,
        level           = npc.nivel if npc else 1,
        ability         = getattr(npc, "habilidad", "") or "" if npc else "",
        hp_actual       = npc.hp_actual if npc else 0,
        hp_max          = npc.stats.get("hp", 1) if npc else 1,
        stats           = npc.stats if npc else {},
        types           = tipos,
        moves           = npc.movimientos or [] if npc else [],
        stat_stages     = battle.wild_stat_stages,
        crit_stage      = 0,
        status          = battle.wild_status,
        sleep_turns     = battle.wild_sleep_turns,
        toxic_counter   = battle.wild_toxic_counter,
        yawn_counter    = battle.wild_yawn_counter,
        confusion_turns = getattr(battle, "wild_confusion_turns", 0),
        leechseeded     = getattr(battle, "wild_leechseeded", False),
        delayed_attacks  = list(getattr(battle, "npc_delayed_attacks", [])),
        objeto           = getattr(npc, "objeto", None) or None if npc else None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sincronización de vuelta a los modelos nativos
# ─────────────────────────────────────────────────────────────────────────────

def sync_wild_side(ctx: UniversalSide, wild, battle) -> None:
    """Copia el estado del UniversalSide de vuelta al wild + BattleData."""
    wild.hp_actual                          = ctx.hp_actual
    battle.wild_stat_stages                 = ctx.stat_stages
    battle.wild_status                      = ctx.status
    battle.wild_sleep_turns                 = ctx.sleep_turns
    battle.wild_toxic_counter               = ctx.toxic_counter
    battle.wild_yawn_counter                = ctx.yawn_counter
    battle.wild_confusion_turns             = ctx.confusion_turns
    battle.wild_leechseeded                 = ctx.leechseeded
    if hasattr(battle, "wild_crit_stage"):
        battle.wild_crit_stage              = ctx.crit_stage
    # Persistir estado de 2 turnos en el wild
    wild.charging_move    = ctx.charging_move
    wild.recharge_pending = ctx.recharge_pending


def sync_player_side(ctx: UniversalSide, battle, *, persist: bool = True) -> None:
    """Copia el estado del UniversalSide de vuelta al BattleData del jugador y persiste HP."""
    battle.player_stat_stages               = ctx.stat_stages
    battle.player_status                    = ctx.status
    battle.player_sleep_turns               = ctx.sleep_turns
    battle.player_toxic_counter             = ctx.toxic_counter
    battle.player_yawn_counter              = ctx.yawn_counter
    battle.player_confusion_turns           = ctx.confusion_turns
    battle.player_leechseeded               = ctx.leechseeded
    if hasattr(battle, "player_crit_stage"):
        battle.player_crit_stage            = ctx.crit_stage
    # Persistir estado de 2 turnos (siempre escribir, no depender de hasattr)
    battle.player_charging_move    = ctx.charging_move
    battle.player_recharge_pending = ctx.recharge_pending
    # Persistir berry_eaten: una vez True, permanece True (necesario para Eructo)
    if ctx.berry_eaten:
        battle.player_berry_eaten = True

    # Si se consumió una baya (objeto fue puesto a None), limpiar en BD
    if persist and ctx.baya_consumida:
        db_manager.execute_update(
            "UPDATE POKEMON_USUARIO SET objeto = NULL WHERE id_unico = ?",
            (battle.player_pokemon_id,),
        )
    
    if persist and ctx.pokemon_db_id:
        try:
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                (ctx.hp_actual, ctx.pokemon_db_id),
            )
        except Exception as e:
            logger.error(f"[ADAPTER] Error persistiendo HP jugador: {e}")


def sync_pvp_side(ctx: UniversalSide, pvp_side, *, persist: bool = True) -> None:
    """
    Copia el estado del UniversalSide de vuelta a un PvPSide y persiste HP.

    IMPORTANTE: el campo `objeto` NO se persiste aquí aunque ctx.objeto sea None
    (baya consumida durante el combate). En PvP/VGC los objetos consumidos solo
    desaparecen durante la batalla; _restaurar_equipo_pvp los devuelve al
    finalizar. La escritura permanente del objeto queda EXCLUSIVAMENTE en manos
    de _restaurar_equipo_pvp al cerrar la batalla.
    """
    pvp_side.stat_stages     = ctx.stat_stages
    pvp_side.status          = ctx.status
    pvp_side.sleep_turns     = ctx.sleep_turns
    pvp_side.toxic_counter   = ctx.toxic_counter
    pvp_side.yawn_counter    = ctx.yawn_counter
    pvp_side.confusion_turns = ctx.confusion_turns
    pvp_side.leechseeded     = ctx.leechseeded
    pvp_side.crit_stage      = ctx.crit_stage
    if ctx.berry_eaten:
        pvp_side.berry_eaten = True   # una vez comida, permanece
    # ── objeto: NO persistir — se restaura al finalizar la batalla ───────────
    # (ctx.objeto puede ser None si una baya se consumió en combate; ese cambio
    #  es temporal y _restaurar_equipo_pvp lo revierte al terminar la partida)

    if persist and ctx.pokemon_db_id:
        try:
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                (ctx.hp_actual, ctx.pokemon_db_id),
            )
        except Exception as e:
            logger.error(f"[ADAPTER] Error persistiendo HP PvP: {e}")


def sync_gym_player(ctx: UniversalSide, battle, *, persist: bool = True) -> None:
    """Copia el estado del jugador de vuelta a un GymBattleData."""
    battle.player_stat_stages               = ctx.stat_stages
    battle.player_status                    = ctx.status
    battle.player_sleep_turns               = ctx.sleep_turns
    battle.player_toxic_counter             = ctx.toxic_counter
    battle.player_yawn_counter              = ctx.yawn_counter
    if hasattr(battle, "player_confusion_turns"):
        battle.player_confusion_turns       = ctx.confusion_turns
    battle.player_leechseeded               = ctx.leechseeded

    if persist and ctx.pokemon_db_id:
        try:
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                (ctx.hp_actual, ctx.pokemon_db_id),
            )
        except Exception as e:
            logger.error(f"[ADAPTER] Error persistiendo HP gym player: {e}")
    if hasattr(battle, "player_delayed_attacks"):
        battle.player_delayed_attacks = list(ctx.delayed_attacks)
    

def sync_gym_npc(ctx: UniversalSide, battle, *, persist: bool = True) -> None:
    """Copia el estado del NPC de vuelta a un GymBattleData."""
    battle.wild_stat_stages                 = ctx.stat_stages
    battle.wild_status                      = ctx.status
    battle.wild_sleep_turns                 = ctx.sleep_turns
    battle.wild_toxic_counter               = ctx.toxic_counter
    battle.wild_yawn_counter                = ctx.yawn_counter
    if hasattr(battle, "wild_confusion_turns"):
        battle.wild_confusion_turns         = ctx.confusion_turns
    battle.wild_leechseeded                 = ctx.leechseeded

    # Sincronizar baya consumida del NPC
    if ctx.baya_consumida and ctx.pokemon_db_id:
        db_manager.execute_update(
            "UPDATE POKEMON_USUARIO SET objeto = NULL WHERE id_unico = ?",
            (ctx.pokemon_db_id,),
        )
            
    if persist and ctx.pokemon_db_id:
        try:
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                (ctx.hp_actual, ctx.pokemon_db_id),
            )
        except Exception as e:
            logger.error(f"[ADAPTER] Error persistiendo HP gym NPC: {e}")

    if hasattr(battle, "npc_delayed_attacks"):
        battle.npc_delayed_attacks = list(ctx.delayed_attacks)
