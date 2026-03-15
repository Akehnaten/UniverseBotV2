"""
Servicio Core de Pokémon
Encapsula la lógica de la clase Pokemon y proporciona una API limpia
AHORA CON CÁLCULO REAL DE STATS DESDE POKÉDEX
"""

import random
import logging
from typing import Optional, Dict, List, Tuple, Any, TYPE_CHECKING
from datetime import datetime

from database import db_manager

if TYPE_CHECKING:
    from pokemon.pokemon_class import Pokemon
from pokemon.battle_config import REGION_SERVIDOR
from pokemon.services.habilidades_service import habilidades_service

try:
    from pokemon.services.crianza_service import determinar_sexo
except ImportError:
    import random as _random
    from typing import Optional as _Optional

    def determinar_sexo(pokemon_id: int) -> _Optional[str]:  # ← str | None, igual que la real
        return "M" if _random.random() < 0.5 else "F"

logger = logging.getLogger(__name__)


class PokemonService:
    """Servicio para gestionar Pokémon individuales"""
    
    def __init__(self):
        # Pokemon se importa cuando se necesita
        from pokemon.pokemon_class import Pokemon
        from pokemon.services.pokedex_service import pokedex_service
        self.Pokemon = Pokemon
        self.db = db_manager
        self.pokedex = pokedex_service
    
    def crear_pokemon(self, 
                      user_id: int, 
                      pokemon_id: int, 
                      nivel: int = 5,
                      region: str = REGION_SERVIDOR, 
                      shiny: Optional[bool] = None,
                      ivs: Optional[Dict] = None,
                      naturaleza: Optional[str] = None,
                      sexo: Optional[str] = None, ) -> Optional[int]:
        """
        Crea un nuevo Pokémon para un usuario con stats reales y sexo asignado.
        """
        try:

            if ivs is None:
                ivs = {stat: random.randint(0, 31)
                       for stat in ["hp", "atq", "def", "atq_sp", "def_sp", "vel"]}

            if shiny is None:
                shiny = random.randint(1, 4096) == 1

            if naturaleza is None:
                naturalezas = [
                    "Hardy", "Lonely", "Brave", "Adamant", "Naughty",
                    "Bold", "Docile", "Relaxed", "Impish", "Lax",
                    "Timid", "Hasty", "Serious", "Jolly", "Naive",
                    "Modest", "Mild", "Quiet", "Bashful", "Rash",
                    "Calm", "Gentle", "Sassy", "Careful", "Quirky",
                ]
                naturaleza = random.choice(naturalezas)

            evs = {stat: 0 for stat in ["hp", "atq", "def", "atq_sp", "def_sp", "vel"]}
            stats = self.pokedex.calcular_stats(pokemon_id, nivel, ivs, evs, naturaleza)
            hp_actual = stats["hp"]

            habilidades_posibles = self.pokedex.obtener_habilidades(pokemon_id)
            habilidad = habilidades_service.seleccionar_habilidad(habilidades_posibles)

            sexo = sexo if sexo is not None else determinar_sexo(pokemon_id)

            result = self.db.execute_query(
                "SELECT COUNT(*) as total FROM POKEMON_USUARIO WHERE userID = ? AND en_equipo = 1",
                (user_id,)
            )
            en_equipo = 1 if result[0]['total'] < 6 else 0

            # Después de calcular stats y habilidad, agregar:
            from pokemon.services import movimientos_service
            movimientos_iniciales = movimientos_service.obtener_todos_movimientos_hasta_nivel(pokemon_id, nivel)
            movimientos_iniciales = movimientos_iniciales[:4] if movimientos_iniciales else ["Placaje"]
            moves = movimientos_iniciales + [None] * (4 - len(movimientos_iniciales))

            # ── Calcular stats iniciales con la fórmula oficial Gen 3+ ───────
            # Los Pokémon nacen con EV=0. Los IVs ya fueron generados arriba.
            evs_iniciales = {
                "hp": 0, "atq": 0, "def": 0,
                "atq_sp": 0, "def_sp": 0, "vel": 0,
            }
            stats_iniciales = self.pokedex.calcular_stats(
                pokemon_id, nivel, ivs, evs_iniciales, naturaleza
            )
            hp_actual = stats_iniciales["hp"]   # nace con HP lleno

            pokemon_id_unico = self.db.execute_insert(
                """
                INSERT INTO POKEMON_USUARIO (
                    userID, pokemonID, nivel,
                    iv_hp, iv_atq, iv_def, iv_atq_sp, iv_def_sp, iv_vel,
                    ev_hp, ev_atq, ev_def, ev_atq_sp, ev_def_sp, ev_vel,
                    naturaleza, en_equipo, shiny,
                    ps, atq, def, atq_sp, def_sp, vel,
                    hp_actual, exp, region, habilidad, sexo,
                    move1, move2, move3, move4
                ) VALUES (
                    ?, ?, ?,
                    ?, ?, ?, ?, ?, ?,
                    0, 0, 0, 0, 0, 0,
                    ?, ?, ?,
                    ?, ?, ?, ?, ?, ?,
                    ?, 0, ?, ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    user_id, pokemon_id, nivel,
                    # IVs
                    ivs["hp"], ivs["atq"], ivs["def"],
                    ivs["atq_sp"], ivs["def_sp"], ivs["vel"],
                    # naturaleza, en_equipo, shiny
                    naturaleza, en_equipo, int(shiny),
                    # stats calculados
                    stats_iniciales["hp"],    stats_iniciales["atq"],
                    stats_iniciales["def"],   stats_iniciales["atq_sp"],
                    stats_iniciales["def_sp"], stats_iniciales["vel"],
                    # hp_actual, exp=0, region, habilidad, sexo
                    hp_actual, region, habilidad, sexo,
                    # movimientos
                    moves[0], moves[1], moves[2], moves[3],
                ),
            )
            nombre = self.pokedex.obtener_nombre(pokemon_id)
            sexo_txt = {"M": "♂", "F": "♀"}.get(sexo or "", "◯")
            logger.info(f"✅ {nombre} (#{pokemon_id}) {sexo_txt} creado para usuario {user_id} (ID: {pokemon_id_unico})")

            # Asignar posicion_equipo si entró al equipo
            if en_equipo == 1 and pokemon_id_unico:
                try:
                    equipo_actual = self.obtener_equipo(user_id)
                    nueva_pos = len(equipo_actual) - 1  # ya está en la lista
                    self.db.execute_update(
                        "UPDATE POKEMON_USUARIO SET posicion_equipo = ? WHERE id_unico = ?",
                        (max(0, nueva_pos), pokemon_id_unico),
                    )
                except Exception as _pos_e:
                    logger.warning(f"[POS] No se pudo asignar posicion_equipo al crear: {_pos_e}")
                    # No es crítico — COALESCE(posicion_equipo, id_unico) lo maneja

            return pokemon_id_unico

        except Exception as e:
            logger.error(f"❌ Error creando Pokémon: {e}")
            return None
    
    def obtener_pokemon(self, pokemon_id: int) -> Optional["Pokemon"]:
        """
        Obtiene un Pokémon como objeto.
        """
        results = self.db.execute_query(
            "SELECT * FROM POKEMON_USUARIO WHERE id_unico = ?",
            (pokemon_id,)
        )
        if not results:
            return None
        return self._row_a_pokemon(dict(results[0]))
    
    def obtener_equipo(self, user_id: int) -> List["Pokemon"]:
        """
        Obtiene el equipo Pokémon del usuario (máximo 6).
        """
        results = self.db.execute_query(
            """
            SELECT * FROM POKEMON_USUARIO
            WHERE userID = ? AND en_equipo = 1
            ORDER BY COALESCE(posicion_equipo, id_unico)
            LIMIT 6
            """,
            (user_id,)
        )
        return [self._row_a_pokemon(dict(row)) for row in results]
    
    def mover_posicion_equipo_arriba(self, user_id: int, pokemon_id: int) -> bool:
        """
        Sube una posición al Pokémon en el equipo.
        Intercambia con el que estaba en la posición anterior.
        Retorna True si el cambio fue exitoso.
        """
        try:
            equipo = self.obtener_equipo(user_id)
            ids = [p.id_unico for p in equipo]

            if pokemon_id not in ids:
                return False
            idx = ids.index(pokemon_id)
            if idx == 0:
                return False  # Ya es el primero

            # Intercambiar posicion_equipo entre idx-1 e idx
            id_arriba  = ids[idx - 1]
            id_abajo   = ids[idx]
            pos_arriba = idx - 1
            pos_abajo  = idx

            self.db.execute_update(
                "UPDATE POKEMON_USUARIO SET posicion_equipo = ? WHERE id_unico = ?",
                (pos_abajo, id_arriba),
            )
            self.db.execute_update(
                "UPDATE POKEMON_USUARIO SET posicion_equipo = ? WHERE id_unico = ?",
                (pos_arriba, id_abajo),
            )
            return True

        except Exception as e:
            logger.error(f"[POS] Error moviendo posición: {e}")
            return False
    
    def mover_posicion_equipo_abajo(self, user_id: int, pokemon_id: int) -> bool:
        """Baja una posición al Pokémon en el equipo. Intercambia con el siguiente."""
        try:
            equipo = self.obtener_equipo(user_id)
            ids = [p.id_unico for p in equipo]

            if pokemon_id not in ids:
                return False
            idx = ids.index(pokemon_id)
            if idx == len(ids) - 1:
                return False  # Ya es el último

            id_arriba = ids[idx]
            id_abajo  = ids[idx + 1]

            self.db.execute_update(
                "UPDATE POKEMON_USUARIO SET posicion_equipo = ? WHERE id_unico = ?",
                (idx + 1, id_arriba),
            )
            self.db.execute_update(
                "UPDATE POKEMON_USUARIO SET posicion_equipo = ? WHERE id_unico = ?",
                (idx, id_abajo),
            )
            return True

        except Exception as e:
            logger.error(f"[POS] Error moviendo posición abajo: {e}")
            return False

    def inicializar_posiciones_equipo(self, user_id: int) -> None:
        """
        Asigna posiciones 0,1,2... a los Pokémon del equipo que no las tengan.
        Llamar al mover un Pokémon al equipo o al inicializar el sistema.
        """
        try:
            equipo = self.obtener_equipo(user_id)
            for idx, p in enumerate(equipo):
                if getattr(p, "posicion_equipo", None) is None:
                    self.db.execute_update(
                        "UPDATE POKEMON_USUARIO SET posicion_equipo = ? WHERE id_unico = ?",
                        (idx, p.id_unico),
                    )
        except Exception as e:
            logger.error(f"[POS] Error inicializando posiciones: {e}")

    def intercambiar_posiciones(self, id_a: int, id_b: int) -> None:
        """
        Intercambia las posiciones_equipo de dos Pokémon.
        Usado durante battle switch.
        """
        try:
            ra = self.db.execute_query(
                "SELECT posicion_equipo FROM POKEMON_USUARIO WHERE id_unico = ?", (id_a,)
            )
            rb = self.db.execute_query(
                "SELECT posicion_equipo FROM POKEMON_USUARIO WHERE id_unico = ?", (id_b,)
            )
            pos_a = ra[0]["posicion_equipo"] if ra else None
            pos_b = rb[0]["posicion_equipo"] if rb else None

            self.db.execute_update(
                "UPDATE POKEMON_USUARIO SET posicion_equipo = ? WHERE id_unico = ?",
                (pos_b, id_a),
            )
            self.db.execute_update(
                "UPDATE POKEMON_USUARIO SET posicion_equipo = ? WHERE id_unico = ?",
                (pos_a, id_b),
            )
        except Exception as e:
            logger.error(f"[POS] Error intercambiando posiciones: {e}")

    def restaurar_posiciones(self, posiciones: dict) -> None:
        """
        Restaura las posiciones desde un snapshot {pokemon_id: posicion}.
        Llamar al terminar una batalla.
        """
        try:
            for pokemon_id, pos in posiciones.items():
                self.db.execute_update(
                    "UPDATE POKEMON_USUARIO SET posicion_equipo = ? WHERE id_unico = ?",
                    (pos, pokemon_id),
                )
        except Exception as e:
            logger.error(f"[POS] Error restaurando posiciones: {e}")

    def obtener_pc(self, user_id: int, offset: int = 0, limit: int = 30) -> List["Pokemon"]:
        """
        Obtiene los Pokémon en el PC del usuario (paginado)

        Args:
            user_id: ID del usuario
            offset: Desplazamiento para paginación
            limit: Cantidad máxima a retornar

        Returns:
            Lista de objetos Pokemon en el PC
        """
        query = """
            SELECT pu.* FROM POKEMON_USUARIO pu
            WHERE pu.userID = ? AND pu.en_equipo = 0
              AND pu.id_unico NOT IN (
                  SELECT pokemon_id FROM GUARDERIA WHERE userID = ?
              )
            ORDER BY pu.id_unico
            LIMIT ? OFFSET ?
        """
        results = self.db.execute_query(query, (user_id, user_id, limit, offset))
        return [self._row_a_pokemon(dict(row)) for row in results]  # ✅ Fix
    
    def curar_pokemon(self, pokemon_id: int) -> bool:
        """
        Cura un Pokémon restaurando su HP al máximo
        USA STATS REALES calculadas desde la Pokédex
        
        Args:
            pokemon_id: ID único del Pokémon
        
        Returns:
            True si se curó correctamente
        """
        try:
            # Obtener datos del Pokémon
            pokemon = self.obtener_pokemon(pokemon_id)
            
            if not pokemon:
                return False
            
            # Type guard #2
            if not pokemon.pokemonID:
                logger.error(f"Pokemon sin ID")
                return False
                    
            # Obtener IVs y EVs
            ivs = {
                "hp": pokemon.ivs['hp'],
                "atq": pokemon.ivs['atq'],
                "def": pokemon.ivs['def'],
                "atq_sp": pokemon.ivs['atq_sp'],
                "def_sp": pokemon.ivs['def_sp'],
                "vel": pokemon.ivs['vel']
            }
            
            evs = {
                "hp": pokemon.evs['hp'],
                "atq": pokemon.evs['atq'],
                "def": pokemon.evs['def'],
                "atq_sp": pokemon.evs['atq_sp'],
                "def_sp": pokemon.evs['def_sp'],
                "vel": pokemon.evs['vel']
            }
            
            # CALCULAR HP MÁXIMO REAL
            stats = self.pokedex.calcular_stats(
                pokemon.pokemonID,
                pokemon.nivel,
                ivs,
                evs,
                pokemon.naturaleza
            )
            
            hp_max = stats["hp"]
            
            # Actualizar HP
            query = "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?"
            self.db.execute_update(query, (hp_max, pokemon_id))
            
            logger.info(f"💚 Pokémon {pokemon_id} curado (HP: {hp_max})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error curando Pokémon: {e}")
            return False
    
    def curar_equipo(self, user_id: int) -> int:
        """
        Cura todos los Pokémon del equipo del usuario
        
        Args:
            user_id: ID del usuario
        
        Returns:
            Cantidad de Pokémon curados
        """
        equipo = self.obtener_equipo(user_id)
        curados = 0
        
        for pokemon in equipo:
            if pokemon.id_unico and self.curar_pokemon(pokemon.id_unico):
                curados += 1
        
        logger.info(f"💚 {curados} Pokémon curados para usuario {user_id}")
        return curados
    
    def mover_a_equipo(self, pokemon_id: int, user_id: int) -> Tuple[bool, str]:
        """
        Mueve un Pokémon del PC al equipo
        
        Args:
            pokemon_id: ID único del Pokémon
            user_id: ID del usuario (para verificar límite)
        
        Returns:
            (exitoso, mensaje)
        """
        try:
            # Verificar cuántos hay en el equipo
            query_count = """
                SELECT COUNT(*) as total 
                FROM POKEMON_USUARIO 
                WHERE userID = ? AND en_equipo = 1
            """
            result = self.db.execute_query(query_count, (user_id,))
            
            if result[0]['total'] >= 6:
                return False, "El equipo está lleno (máximo 6 Pokémon)"
            
            # Mover al equipo
            query = "UPDATE POKEMON_USUARIO SET en_equipo = 1 WHERE id_unico = ?"
            self.db.execute_update(query, (pokemon_id,))

            # Asignar posicion_equipo = siguiente disponible
            equipo_actual = self.obtener_equipo(user_id)
            nueva_pos = len(equipo_actual) - 1  # acaba de entrar al equipo
            self.db.execute_update(
                "UPDATE POKEMON_USUARIO SET posicion_equipo = ? WHERE id_unico = ?",
                (nueva_pos, pokemon_id),
            )
            
            logger.info(f"📦 Pokémon {pokemon_id} movido al equipo")
            return True, "Pokémon movido al equipo"
            
        except Exception as e:
            logger.error(f"❌ Error moviendo Pokémon: {e}")
            return False, f"Error: {str(e)}"
    
    def mover_a_pc(self, pokemon_id: int) -> Tuple[bool, str]:
        """
        Mueve un Pokémon del equipo al PC
        
        Args:
            pokemon_id: ID único del Pokémon (columna id_unico)
        
        Returns:
            (exitoso, mensaje)
        """
        try:
            # 1. Obtener userID ANTES de mover (necesario para recompactar)
            result = self.db.execute_query(
                "SELECT userID FROM POKEMON_USUARIO WHERE id_unico = ?",
                (pokemon_id,)
            )
            user_id = result[0]["userID"] if result else None

            # 2. Sacar del equipo y limpiar posición
            self.db.execute_update(
                "UPDATE POKEMON_USUARIO SET en_equipo = 0, posicion_equipo = NULL WHERE id_unico = ?",
                (pokemon_id,)
            )

            # 3. Recompactar posiciones del equipo restante (0,1,3 → 0,1,2)
            if user_id:
                self.inicializar_posiciones_equipo(user_id)

            logger.info(f"📦 Pokémon {pokemon_id} movido al PC")
            return True, "Pokémon movido al PC"

        except Exception as e:
            logger.error(f"❌ Error moviendo Pokémon: {e}")
            return False, f"Error: {str(e)}"
    
    def ganar_experiencia(self, pokemon_id: int, exp_ganada: int) -> Dict:
        """
        Añade experiencia a un Pokémon y gestiona subidas de nivel
        
        Args:
            pokemon_id: ID único del Pokémon
            exp_ganada: Cantidad de experiencia ganada
        
        Returns:
            Diccionario con información de la ganancia
            {
                'subio_nivel': bool,
                'nivel_anterior': int,
                'nivel_nuevo': int,
                'exp_total': int
            }
        """
        try:
            pokemon = self.obtener_pokemon(pokemon_id)
            
            if not pokemon:
                return {'subio_nivel': False}
            
            nivel_actual = pokemon.nivel
            exp_actual = pokemon.exp
            exp_nueva = exp_actual + exp_ganada
            
            # Calcular nuevo nivel (fórmula simplificada: nivel^3)
            nivel_nuevo = nivel_actual
            while nivel_nuevo < 100:  # Nivel máximo
                exp_requerida = (nivel_nuevo + 1) ** 3
                if exp_nueva >= exp_requerida:
                    nivel_nuevo += 1
                else:
                    break
            
            # Actualizar en BD
            query = "UPDATE POKEMON_USUARIO SET exp = ?, nivel = ? WHERE id_unico = ?"
            self.db.execute_update(query, (exp_nueva, nivel_nuevo, pokemon_id))
            
            resultado = {
                'subio_nivel': nivel_nuevo > nivel_actual,
                'nivel_anterior': nivel_actual,
                'nivel_nuevo': nivel_nuevo,
                'exp_total': exp_nueva,
                'exp_ganada': exp_ganada
            }
            
            if resultado['subio_nivel']:
                logger.info(f"⭐ Pokémon {pokemon_id} subió al nivel {nivel_nuevo}")
            
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error añadiendo experiencia: {e}")
            return {'subio_nivel': False}
    
    def liberar_pokemon(self, pokemon_id: int, user_id: int) -> Tuple[bool, str]:
        """
        Libera un Pokémon (lo elimina de la BD)
        
        Args:
            pokemon_id: ID único del Pokémon
            user_id: ID del usuario (para verificar pertenencia)
        
        Returns:
            (exitoso, mensaje)
        """
        try:
            # Verificar que pertenece al usuario
            pokemon = self.obtener_pokemon(pokemon_id)
            
            if not pokemon:
                return False, "Pokémon no encontrado"
            
            if pokemon.usuario_id != user_id:
                return False, "Este Pokémon no te pertenece"
            
            # Eliminar
            query = "DELETE FROM POKEMON_USUARIO WHERE id_unico = ?"
            self.db.execute_update(query, (pokemon_id,))
            
            logger.info(f"🕊️ Usuario {user_id} liberó Pokémon {pokemon_id}")
            return True, "Pokémon liberado"
            
        except Exception as e:
            logger.error(f"❌ Error liberando Pokémon: {e}")
            return False, f"Error: {str(e)}"
    
    def _row_a_pokemon(self, row: dict) -> "Pokemon":
        """
        Convierte una fila de POKEMON_USUARIO al dataclass Pokemon.

        Prioriza los stats persistidos en BD (columnas ps/atq/def/…).
        Si las columnas son 0 (BD antigua o fila sin stats), recalcula
        en tiempo real como fallback — no falla la sesión.
        """
        nombre = self.pokedex.obtener_nombre(row.get("pokemonID", 0))

        movimientos = [
            row.get("move1"), row.get("move2"),
            row.get("move3"), row.get("move4"),
        ]
        movimientos = [m for m in movimientos if m]

        ivs = {
            "hp":     int(row.get("iv_hp",     0) or 0),
            "atq":    int(row.get("iv_atq",    0) or 0),
            "def":    int(row.get("iv_def",    0) or 0),
            "atq_sp": int(row.get("iv_atq_sp", 0) or 0),
            "def_sp": int(row.get("iv_def_sp", 0) or 0),
            "vel":    int(row.get("iv_vel",    0) or 0),
        }
        evs = {
            "hp":     int(row.get("ev_hp",     0) or 0),
            "atq":    int(row.get("ev_atq",    0) or 0),
            "def":    int(row.get("ev_def",    0) or 0),
            "atq_sp": int(row.get("ev_atq_sp", 0) or 0),
            "def_sp": int(row.get("ev_def_sp", 0) or 0),
            "vel":    int(row.get("ev_vel",    0) or 0),
        }

        # Leer stats de BD (resultado pre-calculado de la fórmula Gen 3+)
        stats_bd = {
            "hp":     int(row.get("ps",     0) or 0),
            "atq":    int(row.get("atq",    0) or 0),
            "def":    int(row.get("def",    0) or 0),
            "atq_sp": int(row.get("atq_sp", 0) or 0),
            "def_sp": int(row.get("def_sp", 0) or 0),
            "vel":    int(row.get("vel",    0) or 0),
        }

        # Fallback: si ps==0, la fila viene de una BD sin las columnas nuevas.
        # Calculamos en RAM para no romper la sesión actual.
        if stats_bd["hp"] == 0:
            naturaleza_fb = row.get("naturaleza", "Hardy") or "Hardy"
            stats_bd = self.pokedex.calcular_stats(
                row.get("pokemonID", 1),
                row.get("nivel", 5),
                ivs,
                evs,
                naturaleza_fb,
            )

        _hp_stored    = row.get("hp_actual")
        hp_actual_val = _hp_stored if _hp_stored is not None else stats_bd["hp"]
        
        return self.Pokemon(
            id_unico      = row["id_unico"],
            pokemonID     = row["pokemonID"],
            usuario_id    = row["userID"],
            nombre        = nombre,
            mote          = row.get("apodo"),
            nivel         = row.get("nivel", 5),
            exp           = row.get("exp", 0),
            hp_actual     = hp_actual_val,
            stats         = stats_bd,
            ivs           = ivs,
            evs           = evs,
            naturaleza    = row.get("naturaleza", "Hardy") or "Hardy",
            habilidad     = row.get("habilidad"),
            shiny         = bool(row.get("shiny", 0)),
            sexo          = row.get("sexo"),
            movimientos   = movimientos,
            en_equipo     = bool(row.get("en_equipo", 0)),
            objeto        = row.get("objeto"),
            fecha_captura = row.get("fecha_captura"),
        )
    
_PESO_NORMAL = 85
_PESO_OCULTA = 15

def _seleccionar_habilidad(habilidades: list) -> str:
    """
    Selecciona habilidad con probabilidades canónicas Gen 5+.
    Convención: la ÚLTIMA de la lista es siempre la habilidad oculta.

    1 entrada  → 100% esa habilidad
    2 entradas → 85% primera (normal), 15% segunda (oculta)
    3 entradas → 42.5% / 42.5% / 15% (oculta)
    """
    if not habilidades:
        return "overgrow"
    if len(habilidades) == 1:
        return habilidades[0]
    pesos = [_PESO_NORMAL] * (len(habilidades) - 1) + [_PESO_OCULTA]
    return random.choices(habilidades, weights=pesos, k=1)[0]


# Instancia global del servicio
pokemon_service = PokemonService()
