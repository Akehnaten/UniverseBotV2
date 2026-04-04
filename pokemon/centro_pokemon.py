# -*- coding: utf-8 -*-
"""
Centro Pokémon
==============
El costo de curación se importa desde config.py (COSTO_CENTRO_POKEMON),
ahora representa el costo POR POKÉMON curado (no tarifa plana).
Ejemplo: curar 3 Pokémon heridos = 3 × 10 = 30 cosmos.
"""

import logging
from typing import Tuple

from pokemon.services import pokemon_service
from funciones import economy_service
from config import COSTO_CENTRO_POKEMON

logger = logging.getLogger(__name__)


class CentroPokemon:
    """Centro Pokémon para curar el equipo completo."""

    # Costo POR Pokémon curado (leído de config.py).
    # Curar 1 Pokémon = COSTO_POR_POKEMON cosmos.
    # Curar 6 Pokémon = 6 × COSTO_POR_POKEMON cosmos.
    COSTO_POR_POKEMON: int = COSTO_CENTRO_POKEMON

    @staticmethod
    def curar_equipo(user_id: int) -> Tuple[bool, str]:
        try:
            from database import db_manager

            # 1. Obtener equipo
            equipo = pokemon_service.obtener_equipo(user_id)
            if not equipo:
                return False, "❌ No tienes Pokémon en tu equipo."

            # 2. ¿Necesitan curación? Usar stats reales con naturaleza
            from pokemon.services.pokedex_service import pokedex_service

            necesitan = []
            for p in equipo:
                hp_max_real = pokedex_service.calcular_stats(
                    p.pokemonID, p.nivel, p.ivs, p.evs, p.naturaleza
                ).get("hp", 1)
                if p.hp_actual < hp_max_real:
                    necesitan.append((p, hp_max_real))

            if not necesitan:
                return False, "ℹ️ Tus Pokémon ya están completamente curados."

            # 3. Calcular costo total: COSTO_POR_POKEMON cosmos × Pokémon a curar
            costo_total = len(necesitan) * CentroPokemon.COSTO_POR_POKEMON

            # 4. Verificar saldo
            saldo = economy_service.get_balance(user_id)
            if saldo is None or saldo < costo_total:
                return False, (
                    f"¡No tienes cosmos suficientes para la curación!\n\n"
                    f"💊 Pokémon a curar: <b>{len(necesitan)}</b>\n"
                    f"💰 Costo total: <b>{costo_total} cosmos</b> "
                    f"({CentroPokemon.COSTO_POR_POKEMON} × {len(necesitan)})\n"
                    f"💳 Tienes: <b>{saldo or 0} cosmos</b>"
                )

            # 5. Descontar cosmos
            ok = economy_service.subtract_credits(
                user_id, costo_total, "Centro Pokémon"
            )
            if not ok:
                return False, "❌ Error al descontar cosmos. Intenta de nuevo."

            # 6. Curar HP
            curados = 0
            for poke, hp_max in necesitan:
                db_manager.execute_update(
                    "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                    (hp_max, poke.id_unico)
                )
                curados += 1

            # 7. Restaurar PP
            try:
                from pokemon.services.pp_service import pp_service
                for poke in equipo:
                    try:
                        pp_service.restaurar_pp(poke.id_unico)
                    except Exception as pp_err:
                        logger.warning(
                            f"[CENTRO] PP no restaurados ({poke.id_unico}): {pp_err}"
                        )
            except ImportError:
                logger.warning(
                    "[CENTRO] pp_service no disponible, se omite restauración de PP"
                )

            logger.info(
                f"[CENTRO] Usuario {user_id} curó {curados} Pokémon "
                f"(−{costo_total} cosmos)"
            )

            return True, (
                f"✨ <b>¡Equipo curado!</b>\n\n"
                f"💚 {curados} Pokémon restaurados\n"
                f"💧 PP restaurados al máximo\n"
                f"💰 Pagaste <b>{costo_total} cosmos</b> "
                f"({CentroPokemon.COSTO_POR_POKEMON} × {curados})\n\n"
                "¡Tus Pokémon están listos para combatir!"
            )

        except Exception as e:
            logger.error(f"[CENTRO] Error en curar_equipo: {e}", exc_info=True)
            return False, f"❌ Error inesperado: {str(e)}"

    @staticmethod
    def verificar_estado_equipo(user_id: int) -> dict:
        """
        Verifica el estado de salud del equipo.

        Returns:
            dict con claves: total, sanos, heridos, debilitados, necesita_curacion
        """
        try:
            from pokemon.services.pokedex_service import pokedex_service

            equipo = pokemon_service.obtener_equipo(user_id)
            if not equipo:
                return {
                    "total": 0,
                    "sanos": 0,
                    "heridos": 0,
                    "debilitados": 0,
                    "necesita_curacion": False,
                }

            sanos = heridos = debilitados = 0

            for p in equipo:
                hp_max_real = pokedex_service.calcular_stats(
                    p.pokemonID, p.nivel, p.ivs, p.evs, p.naturaleza
                ).get("hp", 1)

                if p.hp_actual <= 0:
                    debilitados += 1
                elif p.hp_actual < hp_max_real:
                    heridos += 1
                else:
                    sanos += 1

            return {
                "total": len(equipo),
                "sanos": sanos,
                "heridos": heridos,
                "debilitados": debilitados,
                "necesita_curacion": (heridos + debilitados) > 0,
            }

        except Exception as e:
            logger.error(f"[CENTRO] Error verificando estado: {e}", exc_info=True)
            return {
                "total": 0,
                "sanos": 0,
                "heridos": 0,
                "debilitados": 0,
                "necesita_curacion": False,
            }


# Instancia global
centro_pokemon = CentroPokemon()