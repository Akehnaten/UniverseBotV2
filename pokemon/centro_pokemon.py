# -*- coding: utf-8 -*-
"""
Centro Pokémon
==============
El costo de curación se importa desde config.py (COSTO_CENTRO_POKEMON),
permitiendo ajustarlo sin tocar la lógica de negocio.
"""

import logging
from typing import Tuple

from pokemon.services import pokemon_service
from funciones import economy_service
from config import COSTO_CENTRO_POKEMON

logger = logging.getLogger(__name__)


class CentroPokemon:
    """Centro Pokémon para curar el equipo completo."""

    # Costo leído de config.py para facilitar ajustes sin editar este archivo.
    COSTO_CURACION: int = COSTO_CENTRO_POKEMON

    @staticmethod
    def curar_equipo(user_id: int) -> Tuple[bool, str]:
        try:
            from database import db_manager

            # 1. Verificar saldo
            saldo = economy_service.get_balance(user_id)
            if saldo is None or saldo < CentroPokemon.COSTO_CURACION:
                return False, "¡No tienes dinero suficiente para que te atendamos!"

            # 2. Obtener equipo
            equipo = pokemon_service.obtener_equipo(user_id)
            if not equipo:
                return False, "❌ No tienes Pokémon en tu equipo."

            # 3. ¿Necesitan curación? Usar stats reales con naturaleza
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

            # 4. Descontar cosmos
            ok = economy_service.subtract_credits(
                user_id, CentroPokemon.COSTO_CURACION, "Centro Pokémon"
            )
            if not ok:
                return False, "❌ Error al descontar cosmos. Intenta de nuevo."

            # 5. Curar HP
            curados = 0
            for poke, hp_max in necesitan:
                db_manager.execute_update(
                    "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                    (hp_max, poke.id_unico)
                )
                curados += 1

            # 6. Restaurar PP
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
                f"(−{CentroPokemon.COSTO_CURACION} cosmos)"
            )

            return True, (
                f"✨ <b>¡Equipo curado!</b>\n\n"
                f"💚 {curados} Pokémon restaurados\n"
                f"💧 PP restaurados al máximo\n"
                f"💰 Pagaste <b>{CentroPokemon.COSTO_CURACION}</b> cosmos\n\n"
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
