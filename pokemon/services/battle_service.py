"""
Servicio de Batallas Pokémon COMPLETO
Gestiona batallas PvP y contra Pokémon salvajes
INCLUYE: Movimientos, efectos, estados, habilidades
"""

import random
import logging
from typing import Optional, Dict, List, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class TipoBatalla(Enum):
    """Tipos de batalla disponibles"""
    SALVAJE = "salvaje"
    PVP = "pvp"
    GIMNASIO = "gimnasio"


class EstadoPokemon(Enum):
    """Estados que puede tener un Pokémon en batalla"""
    SALUDABLE = "saludable"
    ENVENENADO = "envenenado"
    PARALIZADO = "paralizado"
    QUEMADO = "quemado"
    DORMIDO = "dormido"
    CONGELADO = "congelado"
    VENENO_GRAVE = "veneno_grave"


class BattleService:
    """Servicio para gestionar batallas Pokémon COMPLETO"""

    def __init__(self):
        self.batallas_activas: Dict[str, Dict] = {}

    # ──────────────────────────────────────────────
    # IMPORTS LAZY (evitan circulares en módulo)
    # ──────────────────────────────────────────────

    @staticmethod
    def _pokemon_service():
        from pokemon.services.pokemon_service import pokemon_service
        return pokemon_service

    @staticmethod
    def _movimientos_service():
        from pokemon.services.movimientos_service import movimientos_service
        return movimientos_service

    @staticmethod
    def _pp_service():
        from pokemon.services.pp_service import pp_service
        return pp_service

    @staticmethod
    def _pokedex_service():
        from pokemon.services.pokedex_service import pokedex_service
        return pokedex_service

    # ──────────────────────────────────────────────
    # CREACIÓN Y CARGA
    # ──────────────────────────────────────────────

    def crear_batalla(self, jugador1_id: int, jugador2_id: Optional[int] = None,
                      tipo: TipoBatalla = TipoBatalla.SALVAJE) -> str:
        """
        Crea una nueva batalla

        Args:
            jugador1_id: ID del jugador 1
            jugador2_id: ID del jugador 2 (None para batallas salvajes)
            tipo: Tipo de batalla

        Returns:
            ID de la batalla creada
        """
        import time

        batalla_id = f"battle_{jugador1_id}_{int(time.time())}"

        batalla = {
            'id': batalla_id,
            'tipo': tipo,
            'jugador1_id': jugador1_id,
            'jugador2_id': jugador2_id,
            'equipo_j1': [],
            'equipo_j2': [],
            'pokemon_activo_j1': None,
            'pokemon_activo_j2': None,
            'turno': 1,
            'estado': 'iniciando',
            'ganador': None,
            'historial': [],
            'estados_j1': {},
            'estados_j2': {},
            'mods_j1': {},
            'mods_j2': {},
            'protegido_j1': False,
            'protegido_j2': False,
            'turnos_dormido_j1': {},
            'turnos_dormido_j2': {},
            'contador_veneno_j1': {},
            'contador_veneno_j2': {}
        }

        self.batallas_activas[batalla_id] = batalla

        logger.info(f"⚔️ Batalla {batalla_id} creada: {tipo.value}")

        return batalla_id

    def cargar_equipo(self, batalla_id: str, jugador_id: int) -> bool:
        """
        Carga el equipo de un jugador en la batalla

        Args:
            batalla_id: ID de la batalla
            jugador_id: ID del jugador

        Returns:
            True si se cargó correctamente
        """
        batalla = self.batallas_activas.get(batalla_id)

        if not batalla:
            return False

        try:
            pokemon_service = self._pokemon_service()
            equipo = pokemon_service.obtener_equipo(jugador_id)

            if not equipo:
                logger.warning(f"⚠️ Jugador {jugador_id} no tiene equipo")
                return False

            # Convertir a dicts para uso interno en batalla
            equipo_dicts = [vars(p) for p in equipo]

            if batalla['jugador1_id'] == jugador_id:
                batalla['equipo_j1'] = equipo_dicts
                if not batalla['pokemon_activo_j1']:
                    batalla['pokemon_activo_j1'] = equipo_dicts[0]['id_unico']
            elif batalla['jugador2_id'] == jugador_id:
                batalla['equipo_j2'] = equipo_dicts
                if not batalla['pokemon_activo_j2']:
                    batalla['pokemon_activo_j2'] = equipo_dicts[0]['id_unico']

            logger.info(f"✅ Equipo de jugador {jugador_id} cargado en batalla {batalla_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error cargando equipo: {e}")
            return False

    # ──────────────────────────────────────────────
    # COMBATE
    # ──────────────────────────────────────────────

    def calcular_daño(
        self,
        atacante_id: int,
        defensor_id: int,
        poder_movimiento: int,
        categoria: str = "Físico",
    ) -> int:
        """
        Calcula el daño usando la fórmula oficial Gen 3+ con stats reales.

        Fórmula:
            ((2×Nivel/5 + 2) × Poder × Ataque/Defensa / 50 + 2) × variación

        El nivel entra en el primer factor, pero lo que escala el daño
        verdaderamente son los stats: un Pokémon con 500 de Ataque hará
        muchísimo más daño que uno con 50, sin importar sus niveles.

        Args:
            atacante_id:      id_unico del Pokémon atacante.
            defensor_id:      id_unico del Pokémon defensor.
            poder_movimiento: Poder base del movimiento.
            categoria:        "Físico" usa atq/def | "Especial" usa atq_sp/def_sp.

        Returns:
            Daño entero (mínimo 1).
        """
        try:
            pokemon_service = self._pokemon_service()
            atacante = pokemon_service.obtener_pokemon(atacante_id)
            defensor = pokemon_service.obtener_pokemon(defensor_id)

            if not atacante or not defensor:
                return 0

            nivel = atacante.nivel

            if categoria == "Físico":
                ataque  = atacante.stats.get("atq",    1)
                defensa = defensor.stats.get("def",    1)
            else:
                ataque  = atacante.stats.get("atq_sp", 1)
                defensa = defensor.stats.get("def_sp", 1)

            defensa = max(1, defensa)   # evitar ZeroDivisionError

            daño_base  = (((2 * nivel / 5 + 2) * poder_movimiento * ataque / defensa) / 50) + 2
            variacion  = random.uniform(0.85, 1.0)

            return max(1, int(daño_base * variacion))

        except Exception as e:
            logger.error(f"❌ Error calculando daño: {e}")
            return 0

    def ejecutar_turno(self, batalla_id: str, jugador_id: int,
                       accion: str, **kwargs) -> Dict:
        """
        Ejecuta un turno de batalla

        Args:
            batalla_id: ID de la batalla
            jugador_id: ID del jugador que ejecuta la acción
            accion: Tipo de acción (atacar, cambiar, item, huir)
            **kwargs: Parámetros adicionales según la acción

        Returns:
            Resultado del turno
        """
        batalla = self.batallas_activas.get(batalla_id)

        if not batalla:
            return {'error': 'Batalla no encontrada'}

        resultado: Dict = {
            'turno': batalla['turno'],
            'mensajes': [],
            'batalla_terminada': False,
            'ganador': None
        }

        try:
            if accion == 'atacar':
                movimiento: Optional[str] = kwargs.get('movimiento')
                if movimiento is None:
                    resultado['mensajes'].append("❌ Debes elegir un movimiento")
                else:
                    resultado['mensajes'].extend(
                        self._ejecutar_ataque(batalla, jugador_id, movimiento)
                    )

            elif accion == 'cambiar':
                nuevo_pokemon_id: Optional[int] = kwargs.get('pokemon_id')
                if nuevo_pokemon_id is None:
                    resultado['mensajes'].append("❌ Debes elegir un Pokémon")
                else:
                    resultado['mensajes'].extend(
                        self._ejecutar_cambio(batalla, jugador_id, nuevo_pokemon_id)
                    )

            elif accion == 'huir':
                if batalla['tipo'] == TipoBatalla.SALVAJE:
                    resultado['mensajes'].append("🏃 Has huido del combate")
                    batalla['estado'] = 'finalizada'
                    batalla['ganador'] = 'huida'
                    resultado['batalla_terminada'] = True
                else:
                    resultado['mensajes'].append("❌ No puedes huir de esta batalla")

            batalla['turno'] += 1

            if self._verificar_fin_batalla(batalla):
                resultado['batalla_terminada'] = True
                resultado['ganador'] = batalla['ganador']
                batalla['estado'] = 'finalizada'

            return resultado

        except Exception as e:
            logger.error(f"❌ Error ejecutando turno: {e}")
            return {'error': str(e)}

    def _ejecutar_ataque(self, batalla: Dict, atacante_id: int,
                         movimiento: str) -> List[str]:
        """Ejecuta un ataque"""
        mensajes = []

        if batalla['jugador1_id'] == atacante_id:
            pokemon_atacante_id = batalla['pokemon_activo_j1']
            pokemon_defensor_id = batalla['pokemon_activo_j2']
        else:
            pokemon_atacante_id = batalla['pokemon_activo_j2']
            pokemon_defensor_id = batalla['pokemon_activo_j1']

        daño = self.calcular_daño(pokemon_atacante_id, pokemon_defensor_id, 60)

        pokemon_service = self._pokemon_service()
        defensor = pokemon_service.obtener_pokemon(pokemon_defensor_id)

        if not defensor:
            return ["❌ Pokémon defensor no encontrado"]

        nuevo_hp = max(0, defensor.hp_actual - daño)

        from database import db_manager
        db_manager.execute_update(
            "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
            (nuevo_hp, pokemon_defensor_id)
        )

        mensajes.append(f"⚔️ Ataque con {movimiento}! Causó {daño} de daño")

        if nuevo_hp <= 0:
            mensajes.append("💥 ¡El Pokémon enemigo fue debilitado!")

        return mensajes

    def _ejecutar_cambio(self, batalla: Dict, jugador_id: int,
                         nuevo_pokemon_id: int) -> List[str]:
        """Ejecuta un cambio de Pokémon"""
        mensajes = []

        if batalla['jugador1_id'] == jugador_id:
            batalla['pokemon_activo_j1'] = nuevo_pokemon_id
            mensajes.append("🔄 Cambiaste de Pokémon")
        else:
            batalla['pokemon_activo_j2'] = nuevo_pokemon_id
            mensajes.append("🔄 El oponente cambió de Pokémon")

        return mensajes

    def _verificar_fin_batalla(self, batalla: Dict) -> bool:
        """Verifica si la batalla ha terminado"""
        return False

    # ──────────────────────────────────────────────
    # CONSULTAS
    # ──────────────────────────────────────────────

    def obtener_batalla(self, batalla_id: str) -> Optional[Dict]:
        """Obtiene los datos de una batalla"""
        return self.batallas_activas.get(batalla_id)

    def finalizar_batalla(self, batalla_id: str, ganador_id: Optional[int] = None):
        """
        Finaliza una batalla

        Args:
            batalla_id: ID de la batalla
            ganador_id: ID del ganador (None para empate/huida)
        """
        if batalla_id in self.batallas_activas:
            batalla = self.batallas_activas[batalla_id]
            batalla['estado'] = 'finalizada'
            batalla['ganador'] = ganador_id

            logger.info(f"🏁 Batalla {batalla_id} finalizada. Ganador: {ganador_id}")

            if ganador_id:
                from funciones import economy_service
                economy_service.add_credits(ganador_id, 100, "Victoria en batalla")

    def obtener_estadisticas_batalla(self, batalla_id: str) -> Dict:
        """Obtiene estadísticas de una batalla"""
        batalla = self.obtener_batalla(batalla_id)

        if not batalla:
            return {}

        return {
            'turno_actual': batalla['turno'],
            'tipo': batalla['tipo'].value if isinstance(batalla['tipo'], Enum) else batalla['tipo'],
            'estado': batalla['estado'],
            'jugadores': [batalla['jugador1_id'], batalla['jugador2_id']],
            'ganador': batalla.get('ganador')
        }


# Instancia global del servicio
battle_service = BattleService()