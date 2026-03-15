# -*- coding: utf-8 -*-
"""
Servicio de PP (Power Points)
Gestiona los PP de los movimientos de cada Pokémon
"""

import json
import logging
from typing import Optional, Dict, List

from database import db_manager

logger = logging.getLogger(__name__)


class PPService:
    """Servicio para gestionar PP (Power Points) de movimientos."""

    def __init__(self):
        self.db = db_manager

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _pp_max(movimiento: str) -> int:
        """
        PP máximos de un movimiento según moves.json.
        Prueba múltiples formas del nombre: tal cual, sin espacios, en minúscula.
        Fallback: 10.
        """
        try:
            from pokemon.services.movimientos_service import movimientos_service
            # Intentar con el nombre tal cual, luego sin espacios (move_id del JSON)
            move_data = movimientos_service.obtener_movimiento(movimiento)
            if move_data and move_data.get('pp'):
                return int(move_data['pp'])
        except Exception:
            pass
        return 10

    @staticmethod
    def _normalizar_entrada(valor, movimiento: str, pp_max: int) -> Dict[str, int]:
        """
        Garantiza que una entrada de pp_data sea siempre
        {'actual': int, 'maximo': int} con el maximo correcto desde moves.json.

        Cubre el caso de BD corrupta donde se guardó un int en lugar de un dict,
        o donde el maximo fue guardado con un valor incorrecto (ej: 4 en vez de 25).
        """
        if isinstance(valor, dict):
            maximo = pp_max  # siempre usar el valor de moves.json
            actual = int(valor.get('actual', maximo))
            # Si actual > maximo correcto, ajustar
            actual = min(actual, maximo)
            return {'actual': actual, 'maximo': maximo}
        if isinstance(valor, (int, float)):
            n = min(int(valor), pp_max)
            return {'actual': n, 'maximo': pp_max}
        return {'actual': pp_max, 'maximo': pp_max}

    # ── API pública ───────────────────────────────────────────────────────────

    def obtener_pp(self, pokemon_id: int, movimiento: str) -> Dict[str, int]:
        """
        Obtiene los PP actuales y máximos de un movimiento.

        Returns:
            {'actual': int, 'maximo': int}  — nunca lanza excepción.
        """
        try:
            pp_max = self._pp_max(movimiento)

            result = self.db.execute_query(
                "SELECT pp_data FROM POKEMON_USUARIO WHERE id_unico = ?",
                (pokemon_id,),
            )

            if not result or not result[0]['pp_data']:
                return {'actual': pp_max, 'maximo': pp_max}

            pp_data = json.loads(result[0]['pp_data'])

            # Buscar por el nombre tal cual Y por nombre sin espacios (move_id)
            move_key = movimiento.lower().replace(" ", "")
            valor = pp_data.get(movimiento) or pp_data.get(move_key)

            if valor is not None:
                return self._normalizar_entrada(valor, movimiento, pp_max)

            # Movimiento no registrado aún
            return {'actual': pp_max, 'maximo': pp_max}

        except Exception as e:
            logger.error(f"❌ Error obteniendo PP ({movimiento}): {e}")
            return {'actual': 10, 'maximo': 10}

    def usar_pp(self, pokemon_id: int, movimiento: str) -> bool:
        """
        Consume 1 PP de un movimiento.

        Returns:
            True si se pudo usar, False si no hay PP.
        """
        try:
            pp_max = self._pp_max(movimiento)
            pp_actual = self.obtener_pp(pokemon_id, movimiento)

            if pp_actual['actual'] <= 0:
                return False

            result = self.db.execute_query(
                "SELECT pp_data FROM POKEMON_USUARIO WHERE id_unico = ?",
                (pokemon_id,),
            )

            pp_data = {}
            if result and result[0]['pp_data']:
                pp_data = json.loads(result[0]['pp_data'])

            entrada = self._normalizar_entrada(
                pp_data.get(movimiento) or pp_data.get(movimiento.lower().replace(" ", "")),
                movimiento,
                pp_max
            )
            entrada['actual'] = max(0, entrada['actual'] - 1)
            # Guardar siempre con el nombre original del movimiento
            pp_data[movimiento] = entrada
            # Limpiar clave duplicada si existía
            move_key = movimiento.lower().replace(" ", "")
            if move_key in pp_data and move_key != movimiento:
                del pp_data[move_key]

            self.db.execute_update(
                "UPDATE POKEMON_USUARIO SET pp_data = ? WHERE id_unico = ?",
                (json.dumps(pp_data), pokemon_id),
            )

            logger.debug(
                f"💧 PP usado: {movimiento} "
                f"({entrada['actual']}/{entrada['maximo']})"
            )
            return True

        except Exception as e:
            logger.error(f"❌ Error usando PP ({movimiento}): {e}")
            return False

    def restaurar_pp(self, pokemon_id: int, movimiento: Optional[str] = None) -> bool:
        """
        Restaura los PP de un movimiento (o todos).

        Args:
            pokemon_id: ID único del Pokémon.
            movimiento: Nombre del movimiento (None = todos).
        """
        try:
            result = self.db.execute_query(
                "SELECT pp_data FROM POKEMON_USUARIO WHERE id_unico = ?",
                (pokemon_id,),
            )

            pp_data = {}
            if result and result[0]['pp_data']:
                pp_data = json.loads(result[0]['pp_data'])

            if movimiento:
                pp_max = self._pp_max(movimiento)
                move_key = movimiento.lower().replace(" ", "")
                val = pp_data.get(movimiento) or pp_data.get(move_key)
                entrada = self._normalizar_entrada(val, movimiento, pp_max)
                entrada['actual'] = entrada['maximo']
                pp_data[movimiento] = entrada
            else:
                for mv in list(pp_data.keys()):
                    pp_max = self._pp_max(mv)
                    entrada = self._normalizar_entrada(pp_data[mv], mv, pp_max)
                    entrada['actual'] = entrada['maximo']
                    pp_data[mv] = entrada

            self.db.execute_update(
                "UPDATE POKEMON_USUARIO SET pp_data = ? WHERE id_unico = ?",
                (json.dumps(pp_data), pokemon_id),
            )

            logger.debug(f"💚 PP restaurados para Pokémon {pokemon_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error restaurando PP: {e}")
            return False

    def inicializar_pp_movimientos(self, pokemon_id: int, movimientos: List[str]) -> bool:
        """
        Inicializa o corrige los PP de los movimientos de un Pokémon.
        Siempre sincroniza el 'maximo' con moves.json (corrige BD corrupta).
        Conserva el 'actual' si ya existía y era válido.
        """
        try:
            result = self.db.execute_query(
                "SELECT pp_data FROM POKEMON_USUARIO WHERE id_unico = ?",
                (pokemon_id,),
            )

            pp_data = {}
            if result and result[0]['pp_data']:
                pp_data = json.loads(result[0]['pp_data'])

            for movimiento in movimientos:
                pp_max = self._pp_max(movimiento)
                move_key = movimiento.lower().replace(" ", "")
                val = pp_data.get(movimiento) or pp_data.get(move_key)
                entrada = self._normalizar_entrada(val, movimiento, pp_max)
                pp_data[movimiento] = entrada
                # Limpiar clave duplicada
                if move_key in pp_data and move_key != movimiento:
                    del pp_data[move_key]

            self.db.execute_update(
                "UPDATE POKEMON_USUARIO SET pp_data = ? WHERE id_unico = ?",
                (json.dumps(pp_data), pokemon_id),
            )

            logger.debug(f"✅ PP inicializados para {len(movimientos)} movimientos")
            return True

        except Exception as e:
            logger.error(f"❌ Error inicializando PP: {e}")
            return False

    def verificar_tiene_pp(self, pokemon_id: int, movimiento: str) -> bool:
        """Devuelve True si el Pokémon tiene PP disponibles para el movimiento."""
        pp = self.obtener_pp(pokemon_id, movimiento)
        return pp['actual'] > 0


# Instancia global del servicio
pp_service = PPService()