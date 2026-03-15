# -*- coding: utf-8 -*-
"""
Sistema de Experiencia — Fórmula Gen 9 oficial
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Carga lazy de exp_base.json  (data/exp_base.json)
# ---------------------------------------------------------------------------
_EXP_BASE: dict = {}


def _cargar_exp_base() -> dict:
    """
    Carga exp_base.json la primera vez que se necesita.
    El JSON usa claves string ("1", "25", …) para cumplir el estándar JSON.
    """
    global _EXP_BASE
    if _EXP_BASE:
        return _EXP_BASE
    try:
        from config import BASE_DIR
        path = Path(BASE_DIR) / "data" / "exp_base.json"
        with open(path, encoding="utf-8") as f:
            _EXP_BASE = json.load(f)
        logger.info(f"[EXP] exp_base.json cargado: {len(_EXP_BASE)} especies")
    except Exception as e:
        logger.error(f"[EXP] No se pudo cargar exp_base.json: {e}")
        _EXP_BASE = {}
    return _EXP_BASE


def _exp_base(pokemon_id: int) -> int:
    """
    Devuelve la exp base oficial de una especie.
    Fallback: 100 si el Pokémon no está en el JSON.
    """
    return _cargar_exp_base().get(str(pokemon_id), 100)


def _exp_multiplier() -> float:
    """Lee el multiplicador de EXP desde config."""
    try:
        from config import POKEMON_EXP_MULTIPLIER
        return float(POKEMON_EXP_MULTIPLIER)
    except (ImportError, AttributeError):
        return 1.0


# ---------------------------------------------------------------------------


class ExperienceSystem:
    """
    Sistema de experiencia con fórmula oficial Gen 9.

    Fórmula de EXP ganada (Gen 5+, usada en Gen 9):
        exp = (base_exp * L / 5)
              * ((2L + 10) / (L + Lp + 10)) ^ 2.5
              * factor_entrenador

    Curva de nivel: "Medium Fast"  ->  exp_total(n) = n^3
    La exp en BD es el delta dentro del nivel actual (se resetea a 0 al
    subir de nivel), igual que en los juegos oficiales.
    """

    # -- Curva Medium Fast ----------------------------------------------------

    @staticmethod
    def exp_total_para_nivel(nivel: int) -> int:
        """Exp acumulada para alcanzar `nivel` desde cero (n^3)."""
        return max(1, min(100, nivel)) ** 3

    @staticmethod
    def exp_necesaria_para_nivel(nivel: int) -> int:
        """Exp necesaria para pasar de `nivel` a `nivel+1`."""
        return (
            ExperienceSystem.exp_total_para_nivel(nivel + 1)
            - ExperienceSystem.exp_total_para_nivel(nivel)
        )

    # -- Calculo de EXP ganada ------------------------------------------------

    @staticmethod
    def exp_por_victoria(
        nivel_enemigo: int,
        pokemon_id_enemigo: int,
        nivel_ganador: int,
        es_salvaje: bool = True,
        es_entrenador: bool = False,
    ) -> int:
        """
        EXP ganada usando la formula oficial Gen 5+ (Gen 9).

        Args:
            nivel_enemigo:      Nivel del Pokemon derrotado/capturado.
            pokemon_id_enemigo: ID de especie del enemigo.
            nivel_ganador:      Nivel del Pokemon que gano.
            es_salvaje:         True si el enemigo es salvaje.
            es_entrenador:      True si pertenece a un entrenador
                                (lider de gimnasio, Alto Mando, usuario).
                                Da bono x1.5 sobre el salvaje base.

        Returns:
            EXP ganada (entero, minimo 1).
        """
        base_exp = _exp_base(pokemon_id_enemigo)

        # Pokemon de entrenador dan 1.5x mas exp que los salvajes
        factor_entrenador = 1.5 if es_entrenador else 1.0

        L  = nivel_enemigo
        Lp = nivel_ganador
        ratio    = ((2 * L + 10) / (L + Lp + 10)) ** 2.5
        exp_raw  = (base_exp * L / 5) * ratio * factor_entrenador
        exp_final = int(exp_raw * _exp_multiplier())
        return max(1, exp_final)

    # -- Aplicacion de EXP a la BD --------------------------------------------

    @staticmethod
    def aplicar_experiencia(pokemon_id: int, exp_ganada: int) -> dict:
        """
        Aplica experiencia a un Pokemon y gestiona subidas de nivel.

        Devuelve un dict con:
            subio_nivel     bool   — True si subió al menos un nivel
            nivel_anterior  int
            nivel_nuevo     int
            niveles_subidos list[int]  — cada nivel alcanzado en orden
                                         (vacío si no subió)
            exp_actual      int
            exp_siguiente   int
            exp_ganada      int
        """
        from database import db_manager

        try:
            result = db_manager.execute_query(
                "SELECT nivel, exp FROM POKEMON_USUARIO WHERE id_unico = ?",
                (pokemon_id,),
            )
            if not result:
                return {'subio_nivel': False, 'niveles_subidos': []}

            nivel_actual = int(result[0]['nivel'])
            exp_actual   = int(result[0]['exp'])
            exp_nueva    = exp_actual + exp_ganada

            nivel_nuevo     = nivel_actual
            niveles_subidos: List[int] = []

            # Iterar nivel a nivel para detectar CADA subida (saltos de 2+)
            while nivel_nuevo < 100:
                necesaria = ExperienceSystem.exp_necesaria_para_nivel(nivel_nuevo)
                if exp_nueva >= necesaria:
                    exp_nueva  -= necesaria
                    nivel_nuevo += 1
                    niveles_subidos.append(nivel_nuevo)
                else:
                    break

            if nivel_nuevo >= 100:
                nivel_nuevo = 100
                exp_nueva   = 0

            # Persistir nivel y exp
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET nivel = ?, exp = ? WHERE id_unico = ?",
                (nivel_nuevo, exp_nueva, pokemon_id),
            )

            # Recalcular stats con el nivel final (fórmula directa → correcto)
            if niveles_subidos:
                ExperienceSystem._recalcular_stats(pokemon_id, nivel_nuevo)

            logger.info(
                f"[EXP] Pokemon {pokemon_id}: +{exp_ganada} exp -> "
                f"Nv.{nivel_actual}->{nivel_nuevo}"
                + (f" (niveles: {niveles_subidos})" if niveles_subidos else "")
            )

            return {
                'subio_nivel':    bool(niveles_subidos),
                'nivel_anterior': nivel_actual,
                'nivel_nuevo':    nivel_nuevo,
                'niveles_subidos': niveles_subidos,   # ← NUEVO
                'exp_actual':     exp_nueva,
                'exp_siguiente':  ExperienceSystem.exp_necesaria_para_nivel(nivel_nuevo),
                'exp_ganada':     exp_ganada,
            }

        except Exception as e:
            logger.error(f"[EXP] Error aplicando experiencia: {e}")
            return {'subio_nivel': False, 'niveles_subidos': []}

    # -- Recalculo de stats al subir de nivel ---------------------------------

    @staticmethod
    def _recalcular_stats(pokemon_id: int, nivel_nuevo: int) -> None:
        """
        Recalcula y persiste las 6 stats al subir de nivel.

        El HP se ajusta PROPORCIONALMENTE para no curar ni matar al Pokémon
        al subir de nivel (comportamiento idéntico a los juegos oficiales):
            hp_nuevo = round(hp_actual × (ps_nuevo / ps_viejo))

        Si ps_viejo es 0 (primera vez), el Pokémon nace con HP lleno.
        """
        from database import db_manager

        try:
            result = db_manager.execute_query(
                """
                SELECT pokemonID,
                       iv_hp, iv_atq, iv_def, iv_atq_sp, iv_def_sp, iv_vel,
                       ev_hp, ev_atq, ev_def, ev_atq_sp, ev_def_sp, ev_vel,
                       naturaleza, hp_actual, ps
                FROM POKEMON_USUARIO
                WHERE id_unico = ?
                """,
                (pokemon_id,),
            )
            if not result:
                return

            row        = result[0]
            poke_id    = int(row["pokemonID"])
            naturaleza = row["naturaleza"] or "Hardy"

            ivs = {
                "hp":     int(row["iv_hp"]     or 0),
                "atq":    int(row["iv_atq"]    or 0),
                "def":    int(row["iv_def"]    or 0),
                "atq_sp": int(row["iv_atq_sp"] or 0),
                "def_sp": int(row["iv_def_sp"] or 0),
                "vel":    int(row["iv_vel"]    or 0),
            }
            evs = {
                "hp":     int(row["ev_hp"]     or 0),
                "atq":    int(row["ev_atq"]    or 0),
                "def":    int(row["ev_def"]    or 0),
                "atq_sp": int(row["ev_atq_sp"] or 0),
                "def_sp": int(row["ev_def_sp"] or 0),
                "vel":    int(row["ev_vel"]    or 0),
            }

            from pokemon.services import pokedex_service
            s = pokedex_service.calcular_stats(poke_id, nivel_nuevo, ivs, evs, naturaleza)

            # Ajuste proporcional de HP al subir de nivel
            ps_viejo  = int(row["ps"]       or 0)
            hp_actual = int(row["hp_actual"] or s["hp"])

            if hp_actual <= 0:
                # Pokémon debilitado: subir de nivel NO lo revive.
                # Solo el Centro Pokémon, Revivir u objetos equivalentes
                # pueden restaurar HP desde 0.
                hp_nuevo = 0
            elif ps_viejo > 0:
                # Ajuste proporcional: conservar la fracción de HP actual.
                # max(1, ...) garantiza que un pokémon vivo nunca quede en 0.
                hp_nuevo = max(1, round(hp_actual * s["hp"] / ps_viejo))
            else:
                # Primera asignación de stats (ps_viejo == 0): HP lleno.
                hp_nuevo = s["hp"]

            # Nunca superar el nuevo HP máximo, pero
            # si hp_nuevo == 0 (debilitado) no tocarlo con min().
            if hp_nuevo > 0:
                hp_nuevo = min(hp_nuevo, s["hp"])

            db_manager.execute_update(
                """
                UPDATE POKEMON_USUARIO
                SET ps     = ?,
                    atq    = ?,
                    def    = ?,
                    atq_sp = ?,
                    def_sp = ?,
                    vel    = ?,
                    hp_actual = ?
                WHERE id_unico = ?
                """,
                (
                    s["hp"], s["atq"], s["def"],
                    s["atq_sp"], s["def_sp"], s["vel"],
                    hp_nuevo,
                    pokemon_id,
                ),
            )
            logger.info(
                f"[EXP] Stats actualizados — Pokémon {pokemon_id} Nv.{nivel_nuevo}: "
                f"ps={s['hp']} atq={s['atq']} def={s['def']} "
                f"atq_sp={s['atq_sp']} def_sp={s['def_sp']} vel={s['vel']}"
            )

        except Exception as e:
            logger.error(
                f"[EXP] Error recalculando stats del Pokémon {pokemon_id}: {e}"
            )

    # -- Consulta de progreso -------------------------------------------------

    @staticmethod
    def obtener_progreso(pokemon_id: int) -> Optional[dict]:
        """
        Progreso de experiencia de un Pokemon.

        Returns:
            {
                'nivel':         int,
                'exp_actual':    int,
                'exp_siguiente': int,
                'porcentaje':    float,
            }
        """
        from database import db_manager

        try:
            result = db_manager.execute_query(
                "SELECT nivel, exp FROM POKEMON_USUARIO WHERE id_unico = ?",
                (pokemon_id,),
            )
            if not result:
                return None

            nivel      = int(result[0]['nivel'])
            exp_actual = int(result[0]['exp'])
            necesaria  = ExperienceSystem.exp_necesaria_para_nivel(nivel)
            porcentaje = (exp_actual / necesaria * 100) if necesaria > 0 else 100.0

            return {
                'nivel':         nivel,
                'exp_actual':    exp_actual,
                'exp_siguiente': necesaria,
                'porcentaje':    round(porcentaje, 1),
            }

        except Exception as e:
            logger.error(f"[EXP] Error obteniendo progreso: {e}")
            return None
    
    # -- Movimientos nuevos por nivel -----------------------------------------

    @staticmethod
    def obtener_movimientos_nuevos_en_nivel(
        pokemon_id_especie: int,
        nivel: int,) -> List[str]:
        """
        Devuelve la lista de movimientos que el Pokémon aprende
        exactamente al alcanzar `nivel`.

        Args:
            pokemon_id_especie: pokemonID de la especie (no id_unico).
            nivel:              Nivel recién alcanzado.

        Returns:
            Lista de nombres de movimiento (puede ser vacía).
        """
        try:
            from pokemon.services import movimientos_service
            moves = movimientos_service.obtener_movimientos_nivel(
                pokemon_id_especie, nivel
            )
            return moves if moves else []
        except Exception as e:
            logger.error(
                f"[EXP] Error buscando movimientos en nivel "
                f"{nivel} para especie {pokemon_id_especie}: {e}"
            )
            return []

# Instancia global
exp_system = ExperienceSystem()
