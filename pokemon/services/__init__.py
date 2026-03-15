from typing import List, Dict, Optional, Tuple, Any
# -*- coding: utf-8 -*-
"""
Servicios de Pokémon
"""

from pokemon.services.pokemon_service import PokemonService
from pokemon.services.pokedex_service import PokedexService
from pokemon.services.movimientos_service import MovimientosService
from pokemon.services.battle_service import BattleService
from pokemon.services.gimnasio_service import GimnasioService
from pokemon.services.intercambio_service import IntercambioService
from pokemon.services.items_service import ItemsService
from pokemon.services.evolucion_service import EvolucionService
from pokemon.services.spawn_service import SpawnService

# Instancias globales
pokemon_service = PokemonService()
pokedex_service = PokedexService()
movimientos_service = MovimientosService()
battle_service = BattleService()
gimnasio_service = GimnasioService()
intercambio_service = IntercambioService()
items_service = ItemsService()
evolucion_service: EvolucionService = EvolucionService()
spawn_service = SpawnService()

