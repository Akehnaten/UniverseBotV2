"""
Servicio de Crianza Pokémon
Sistema completo: guardería, huevos, herencia de IVs/naturaleza/movimientos,
pasos por caracteres escritos, eclosión con notificación y mote.
"""

import json
import logging
import random
from typing import Optional, Dict, List, Tuple
from database import db_manager

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ──────────────────────────────────────────────────────────────────────────────

DITTO_ID = 132

# Pokémon que no pueden criar (legendarios y asexuados especiales)
POKEMON_UNDISCOVERED: set = {
    144, 145, 146, 150, 151,
    243, 244, 245, 249, 250, 251,
    377, 378, 379, 380, 381, 382, 383, 384, 385, 386,
    480, 481, 482, 483, 484, 485, 486, 487, 488, 489, 490, 491, 492, 493,
    638, 639, 640, 641, 642, 643, 644, 645, 646, 647, 648, 649,
    716, 717, 718, 719, 720, 721,
    785, 786, 787, 788, 789, 790, 791, 792, 800, 801, 802,
    888, 889, 890, 891, 892, 893, 894, 895, 896, 897, 898,
}

# 100% macho
SOLO_MACHO: set = {32, 33, 34, 106, 107, 128, 236, 237}

# 100% hembra
SOLO_HEMBRA: set = {29, 30, 31, 115, 238, 241}

# Sin género
SIN_GENERO: set = {81, 82, 100, 101, 120, 121, 137, 233, 343, 344, 374, 375, 376}

# Grupos de huevos por pokemonID
GRUPOS_HUEVOS: Dict[int, List[str]] = {
    1: ["Monster", "Grass"], 2: ["Monster", "Grass"], 3: ["Monster", "Grass"],
    4: ["Monster", "Dragon"], 5: ["Monster", "Dragon"], 6: ["Monster", "Dragon"],
    7: ["Monster", "Water1"], 8: ["Monster", "Water1"], 9: ["Monster", "Water1"],
    10: ["Bug"], 11: ["Bug"], 12: ["Bug"],
    13: ["Bug"], 14: ["Bug"], 15: ["Bug"],
    16: ["Flying"], 17: ["Flying"], 18: ["Flying"],
    19: ["Field"], 20: ["Field"],
    21: ["Flying"], 22: ["Flying"],
    23: ["Field"], 24: ["Field"],
    25: ["Field", "Fairy"], 26: ["Field", "Fairy"],
    27: ["Field"], 28: ["Field"],
    29: ["Field"], 30: ["Field"], 31: ["Field"],
    32: ["Field"], 33: ["Field"], 34: ["Field"],
    35: ["Fairy"], 36: ["Fairy"],
    37: ["Field"], 38: ["Field"],
    39: ["Fairy"], 40: ["Fairy"],
    41: ["Flying"], 42: ["Flying"],
    43: ["Grass"], 44: ["Grass"], 45: ["Grass"],
    46: ["Bug", "Grass"], 47: ["Bug", "Grass"],
    48: ["Bug"], 49: ["Bug"],
    50: ["Field"], 51: ["Field"],
    52: ["Field"], 53: ["Field"],
    54: ["Field", "Water1"], 55: ["Field", "Water1"],
    56: ["Field"], 57: ["Field"],
    58: ["Field"], 59: ["Field"],
    60: ["Water1"], 61: ["Water1"], 62: ["Water1"], 186: ["Water1"],
    63: ["Human-Like"], 64: ["Human-Like"], 65: ["Human-Like"],
    66: ["Human-Like"], 67: ["Human-Like"], 68: ["Human-Like"],
    69: ["Grass"], 70: ["Grass"], 71: ["Grass"],
    72: ["Water3"], 73: ["Water3"],
    74: ["Mineral"], 75: ["Mineral"], 76: ["Mineral"],
    77: ["Field"], 78: ["Field"],
    79: ["Monster", "Water1"], 80: ["Monster", "Water1"],
    81: ["Mineral"], 82: ["Mineral"],
    83: ["Flying", "Field"],
    84: ["Flying"], 85: ["Flying"],
    86: ["Water1"], 87: ["Water1"],
    88: ["Amorphous"], 89: ["Amorphous"],
    90: ["Water3"], 91: ["Water3"],
    92: ["Amorphous"], 93: ["Amorphous"], 94: ["Amorphous"],
    95: ["Mineral"],
    96: ["Human-Like"], 97: ["Human-Like"],
    98: ["Water3"], 99: ["Water3"],
    100: ["Mineral"], 101: ["Mineral"],
    102: ["Grass"], 103: ["Grass"],
    104: ["Monster"], 105: ["Monster"],
    106: ["Human-Like"], 107: ["Human-Like"], 236: ["Human-Like"], 237: ["Human-Like"],
    108: ["Monster"],
    109: ["Amorphous"], 110: ["Amorphous"],
    111: ["Monster", "Field"], 112: ["Monster", "Field"],
    113: ["Fairy"],
    114: ["Grass"],
    115: ["Monster"],
    116: ["Water1", "Dragon"], 117: ["Water1", "Dragon"],
    118: ["Water2"], 119: ["Water2"],
    120: ["Water3"], 121: ["Water3"],
    122: ["Human-Like"],
    123: ["Bug"],
    124: ["Human-Like"],
    125: ["Human-Like"],
    126: ["Human-Like"],
    127: ["Bug"],
    128: ["Field"],
    129: ["Water2", "Dragon"], 130: ["Water2", "Dragon"],
    131: ["Monster", "Water1"],
    132: ["Ditto"],
    133: ["Field"], 134: ["Field"], 135: ["Field"], 136: ["Field"],
    196: ["Field"], 197: ["Field"], 470: ["Field"], 471: ["Field"], 700: ["Fairy"],
    137: ["Mineral"],
    138: ["Water3"], 139: ["Water3"],
    140: ["Water3"], 141: ["Water3"],
    142: ["Flying"],
    143: ["Monster"],
    147: ["Water1", "Dragon"], 148: ["Water1", "Dragon"], 149: ["Water1", "Dragon"],
}

PASOS_POR_GRUPO: Dict[str, int] = {
    "Monster": 5120, "Water1": 5120, "Bug": 3840, "Flying": 5120,
    "Field": 5120, "Fairy": 3840, "Grass": 5120, "Human-Like": 5120,
    "Water3": 5120, "Mineral": 5120, "Amorphous": 5120, "Water2": 5120,
    "Ditto": 5120, "Dragon": 10240, "Undiscovered": 999999,
}

PASOS_ESPECIALES: Dict[int, int] = {
    131: 10240,  # Lapras
    133: 8960,   # Eevee
    143: 10240,  # Snorlax
}

NATURALEZAS: List[str] = [
    "Hardy", "Lonely", "Brave", "Adamant", "Naughty",
    "Bold", "Docile", "Relaxed", "Impish", "Lax",
    "Timid", "Hasty", "Serious", "Jolly", "Naive",
    "Modest", "Mild", "Quiet", "Bashful", "Rash",
    "Calm", "Gentle", "Sassy", "Careful", "Quirky",
]

HABILIDAD_CUERPO_LLAMA = "cuerpo llama"


# ──────────────────────────────────────────────────────────────────────────────
# HELPER PÚBLICO: sexo
# ──────────────────────────────────────────────────────────────────────────────

def determinar_sexo(pokemon_id: int) -> Optional[str]:
    """
    Determina el sexo aleatorio de un Pokémon según las mecánicas oficiales.

    Returns:
        'M', 'F' o None (asexuado)
    """
    if pokemon_id in SIN_GENERO or pokemon_id in POKEMON_UNDISCOVERED:
        return None
    if pokemon_id in SOLO_MACHO:
        return "M"
    if pokemon_id in SOLO_HEMBRA:
        return "F"
    # Starters y pseudo-legendarios: 87.5% macho
    starters_y_pseudo = {
        1, 2, 3, 4, 5, 6, 7, 8, 9,
        147, 148, 149,
        246, 247, 248,
        443, 444, 445,
    }
    if pokemon_id in starters_y_pseudo:
        return "M" if random.random() < 0.875 else "F"
    return "M" if random.random() < 0.5 else "F"


# ──────────────────────────────────────────────────────────────────────────────
# SERVICIO
# ──────────────────────────────────────────────────────────────────────────────

class CrianzaService:
    """Servicio completo de crianza de Pokémon"""

    def __init__(self):
        self.db = db_manager

    # ══════════════════════════════════════════════
    # GUARDERÍA
    # ══════════════════════════════════════════════

    def obtener_pokemon_guarderia(self, user_id: int) -> Dict:
        """
        Retorna el estado de la guardería como diccionario de slots.

        Returns:
            Dict con estructura:
                {
                    "poke1": Pokemon | None,  # objeto Pokemon o None si el slot está vacío
                    "poke2": Pokemon | None,
                }
        Siempre devuelve ambas claves aunque estén vacías.
        """
        from pokemon.services.pokemon_service import pokemon_service as _ps

        resultados = self.db.execute_query(
            "SELECT slot, pokemon_id FROM GUARDERIA WHERE userID = ? ORDER BY slot",
            (user_id,)
        ) or []

        guarderia: Dict[str, object] = {"poke1": None, "poke2": None}
        for row in resultados:
            slot = row.get("slot") or "poke1"
            pid  = row.get("pokemon_id")
            if slot in guarderia and pid:
                poke = _ps.obtener_pokemon(int(pid))
                guarderia[slot] = poke  # puede ser None si el Pokémon fue borrado

        return guarderia

    def obtener_pokemon_guarderia_lista(self, user_id: int) -> List:
        """
        Versión de compatibilidad que devuelve lista de Pokémon presentes
        (omite slots vacíos).  Útil para lógica de crianza que espera list.
        """
        d = self.obtener_pokemon_guarderia(user_id)
        return [p for p in d.values() if p is not None]

    def depositar_en_guarderia(self, user_id: int, pokemon_id: int) -> Tuple[bool, str]:
        """
        Deposita un Pokémon en la guardería usando el primer slot libre.

        Reglas:
          - Máximo 2 Pokémon (slots poke1 y poke2).
          - No se aceptan legendarios / grupo Undiscovered.
          - El Pokémon se saca del equipo (en_equipo = 0).
          - Al llenar el segundo slot se intenta producir un huevo si
            los dos Pokémon son compatibles.

        Returns:
            (exito, mensaje)
        """
        try:
            from pokemon.services.pokemon_service import pokemon_service

            # ── Validaciones básicas ──────────────────────────────────────────
            poke = pokemon_service.obtener_pokemon(pokemon_id)
            if not poke:
                return False, "❌ Pokémon no encontrado."
            if poke.usuario_id != user_id:
                return False, "❌ Ese Pokémon no te pertenece."

            grupos = GRUPOS_HUEVOS.get(poke.pokemonID, ["Undiscovered"])
            if "Undiscovered" in grupos or poke.pokemonID in POKEMON_UNDISCOVERED:
                return False, f"❌ {poke.nombre} no puede quedarse en la guardería."

            # ── Determinar slot libre ─────────────────────────────────────────
            guarderia = self.obtener_pokemon_guarderia(user_id)

            # Verificar que no esté ya depositado
            for slot_poke in guarderia.values():
                if slot_poke and getattr(slot_poke, "id_unico", None) == pokemon_id:
                    return False, f"❌ {poke.nombre} ya está en la guardería."

            if guarderia["poke1"] is None:
                slot_libre = "poke1"
            elif guarderia["poke2"] is None:
                slot_libre = "poke2"
            else:
                return False, "❌ La guardería ya tiene 2 Pokémon. Retira uno primero."

            # ── Sacar del equipo y registrar ──────────────────────────────────
            self.db.execute_update(
                "UPDATE POKEMON_USUARIO SET en_equipo = 0 WHERE id_unico = ?",
                (pokemon_id,)
            )
            self.db.execute_update(
                "INSERT INTO GUARDERIA (userID, pokemon_id, slot) VALUES (?, ?, ?)",
                (user_id, pokemon_id, slot_libre)
            )

            logger.info(
                f"🏡 {poke.nombre} (slot {slot_libre}) depositado "
                f"en guardería por usuario {user_id}"
            )

            # ── Si el segundo slot acaba de llenarse, intentar huevo ──────────
            guarderia_nueva = self.obtener_pokemon_guarderia(user_id)
            p1 = guarderia_nueva["poke1"]
            p2 = guarderia_nueva["poke2"]
            msg_huevo = ""
            if p1 and p2:
                tiene_huevo, msg_h, _ = self.intentar_producir_huevo(user_id)
                if tiene_huevo:
                    msg_huevo = f"\n🥚 {msg_h}"

            return True, f"✅ {poke.nombre} fue dejado en la guardería (slot {slot_libre}).{msg_huevo}"

        except Exception as e:
            logger.error(f"❌ Error depositando en guardería: {e}")
            return False, f"Error: {str(e)}"

    def retirar_de_guarderia(self, user_id: int, pokemon_id: int) -> Tuple[bool, str]:
        """
        Retira un Pokémon de la guardería liberando su slot.
        Lo devuelve al equipo si hay lugar, o al PC si está lleno.

        Returns:
            (exito, mensaje)
        """
        try:
            from pokemon.services.pokemon_service import pokemon_service

            # Verificar que esté realmente en la guardería
            fila = self.db.execute_query(
                "SELECT id, slot FROM GUARDERIA WHERE userID = ? AND pokemon_id = ?",
                (user_id, pokemon_id)
            )
            if not fila:
                return False, "❌ Ese Pokémon no está en la guardería."

            # Liberar el slot
            self.db.execute_update(
                "DELETE FROM GUARDERIA WHERE userID = ? AND pokemon_id = ?",
                (user_id, pokemon_id)
            )

            # Devolver al equipo o al PC
            equipo = pokemon_service.obtener_equipo(user_id)
            if len(equipo) < 6:
                self.db.execute_update(
                    "UPDATE POKEMON_USUARIO SET en_equipo = 1 WHERE id_unico = ?",
                    (pokemon_id,)
                )
                destino = "devuelto a tu equipo"
            else:
                destino = "guardado en el PC (equipo lleno)"

            poke   = pokemon_service.obtener_pokemon(pokemon_id)
            nombre = poke.nombre if poke else f"Pokémon #{pokemon_id}"
            slot   = fila[0].get("slot", "?")
            logger.info(
                f"🏡 {nombre} (slot {slot}) retirado de guardería "
                f"por usuario {user_id}"
            )
            return True, f"✅ {nombre} fue retirado ({slot}). Fue {destino}."

        except Exception as e:
            logger.error(f"❌ Error retirando de guardería: {e}")
            return False, f"Error: {str(e)}"

    # ══════════════════════════════════════════════
    # COMPATIBILIDAD
    # ══════════════════════════════════════════════

    def pueden_criar(self, pokemon1_id: int, pokemon2_id: int) -> Tuple[bool, str]:
        """
        Verifica compatibilidad de cría.

        Reglas oficiales:
        - No puede criar consigo mismo.
        - Ditto cría con cualquiera que no sea Undiscovered.
        - Sin Ditto: sexos opuestos + grupo de huevo compartido.
        - Asexuados solo pueden criar con Ditto.
        """
        try:
            from pokemon.services.pokemon_service import pokemon_service

            if pokemon1_id == pokemon2_id:
                return False, "Un Pokémon no puede criar consigo mismo."

            poke1 = pokemon_service.obtener_pokemon(pokemon1_id)
            poke2 = pokemon_service.obtener_pokemon(pokemon2_id)
            if not poke1 or not poke2:
                return False, "Uno o ambos Pokémon no existen."

            id1, id2 = poke1.pokemonID, poke2.pokemonID
            grupos1 = GRUPOS_HUEVOS.get(id1, ["Undiscovered"])
            grupos2 = GRUPOS_HUEVOS.get(id2, ["Undiscovered"])

            if "Undiscovered" in grupos1 or id1 in POKEMON_UNDISCOVERED:
                return False, f"{poke1.nombre} no puede tener crías."
            if "Undiscovered" in grupos2 or id2 in POKEMON_UNDISCOVERED:
                return False, f"{poke2.nombre} no puede tener crías."

            if id1 == DITTO_ID or id2 == DITTO_ID:
                return True, "✅ Compatibles (con Ditto)"

            # Sin Ditto: verificar sexo
            sexo1 = poke1.sexo
            sexo2 = poke2.sexo
            if sexo1 is None or sexo2 is None:
                return False, "Los Pokémon asexuados solo pueden criar con Ditto."
            if sexo1 == sexo2:
                return False, "Los Pokémon deben ser de sexos opuestos."

            comunes = set(grupos1) & set(grupos2)
            if not comunes:
                return False, f"{poke1.nombre} y {poke2.nombre} no comparten grupo de huevo."

            return True, f"✅ Compatibles (Grupo: {', '.join(comunes)})"

        except Exception as e:
            logger.error(f"❌ Error verificando compatibilidad: {e}")
            return False, f"Error: {str(e)}"

    # ══════════════════════════════════════════════
    # PRODUCCIÓN DE HUEVOS
    # ══════════════════════════════════════════════

    def intentar_producir_huevo(self, user_id: int) -> Tuple[bool, str, Optional[int]]:
        """
        Intenta producir un huevo con los 2 Pokémon en guardería.
        Llamar al revisar la guardería o al alcanzar cierto número de pasos.

        Returns:
            (producido, mensaje, huevo_id)
        """
        # obtener_pokemon_guarderia devuelve dict {slot: Pokemon|None}
        guardados_dict = self.obtener_pokemon_guarderia(user_id)
        guardados = [p for p in guardados_dict.values() if p is not None]
        if len(guardados) < 2:
            return False, "Se necesitan 2 Pokémon en la guardería.", None

        pueden, msg = self.pueden_criar(guardados[0]['pokemon_id'], guardados[1]['pokemon_id'])
        if not pueden:
            return False, msg, None

        return self._crear_huevo(user_id, guardados[0]['pokemon_id'], guardados[1]['pokemon_id'])

    def _crear_huevo(self, user_id: int, p1_id: int, p2_id: int) -> Tuple[bool, str, Optional[int]]:
        """Crea un huevo en BD con todos los datos heredados."""
        try:
            from pokemon.services.pokemon_service import pokemon_service

            poke1 = pokemon_service.obtener_pokemon(p1_id)
            poke2 = pokemon_service.obtener_pokemon(p2_id)
            if not poke1 or not poke2:
                return False, "Pokémon no encontrado.", None

            p1, p2 = vars(poke1), vars(poke2)
            especie = self._determinar_especie_huevo(p1, p2)
            pasos = self._calcular_pasos_necesarios(especie)
            ivs = self._calcular_ivs_heredados(p1, p2)
            naturaleza = self._determinar_naturaleza(p1, p2)
            habilidad = self._determinar_habilidad(especie)
            movimientos = self._calcular_movimientos_huevo(p1, p2, especie)
            pasos_offset = self._obtener_pasos_globales(user_id)

            self.db.execute_update(
                """
                INSERT INTO HUEVOS (
                    userID, pokemon_id, ivs_heredados, naturaleza,
                    habilidad, movimientos_huevo, pasos_necesarios, pasos_offset, eclosionado
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    user_id, especie, json.dumps(ivs), naturaleza,
                    habilidad, json.dumps(movimientos), pasos, pasos_offset
                )
            )

            id_r = self.db.execute_query("SELECT last_insert_rowid() AS id")
            huevo_id: Optional[int] = id_r[0]['id'] if id_r else None

            nombre = self._obtener_nombre_especie(especie)
            logger.info(f"🥚 Huevo {huevo_id} creado para {user_id} (especie {especie})")
            return True, (
                f"🥚 ¡La guardería tiene un huevo!\n"
                f"Especie: {nombre}\n"
                f"Pasos necesarios: {pasos}"
            ), huevo_id

        except Exception as e:
            logger.error(f"❌ Error creando huevo: {e}")
            return False, f"Error: {str(e)}", None

    # ══════════════════════════════════════════════
    # SISTEMA DE PASOS
    # ══════════════════════════════════════════════

    def _obtener_pasos_globales(self, user_id: int) -> int:
        """Pasos globales acumulados del usuario en guardería."""
        r = self.db.execute_query(
            "SELECT pasos_guarderia FROM USUARIOS WHERE userID = ?",
            (user_id,)
        )
        if r and r[0].get('pasos_guarderia') is not None:
            return r[0]['pasos_guarderia']
        return 0

    def _tiene_cuerpo_llama(self, user_id: int) -> bool:
        """Verifica si hay un Pokémon con habilidad Cuerpo Llama en el equipo."""
        try:
            from pokemon.services.pokemon_service import pokemon_service
            equipo = pokemon_service.obtener_equipo(user_id)
            return any(
                p.habilidad and p.habilidad.lower() == HABILIDAD_CUERPO_LLAMA
                for p in equipo
            )
        except Exception:
            return False

    def sumar_pasos(self, user_id: int, caracteres: int) -> List[Dict]:
        """
        Suma pasos al contador global del usuario.
        - 1 carácter = 1 paso (x2 con Cuerpo Llama en equipo).
        - Verifica y eclosiona todos los huevos que alcancen su umbral.
        - Cada huevo tiene su propio offset; los pasos se comparan
          contra (pasos_globales - pasos_offset) del huevo.

        Returns:
            Lista de dicts de eclosiones ocurridas.
        """
        try:
            multiplicador = 2 if self._tiene_cuerpo_llama(user_id) else 1
            nuevos_pasos = caracteres * multiplicador

            self.db.execute_update(
                """
                UPDATE USUARIOS
                SET pasos_guarderia = COALESCE(pasos_guarderia, 0) + ?
                WHERE userID = ?
                """,
                (nuevos_pasos, user_id)
            )

            pasos_globales = self._obtener_pasos_globales(user_id)
            huevos = self.db.execute_query(
                "SELECT * FROM HUEVOS WHERE userID = ? AND eclosionado = 0",
                (user_id,)
            )

            eclosionados = []
            for row in (huevos or []):
                huevo = dict(row)
                efectivos = pasos_globales - huevo.get('pasos_offset', 0)
                if efectivos >= huevo['pasos_necesarios']:
                    resultado = self._eclosionar_huevo(huevo['id'], huevo)
                    if resultado:
                        eclosionados.append(resultado)

            return eclosionados

        except Exception as e:
            logger.error(f"❌ Error sumando pasos: {e}")
            return []

    def _eclosionar_huevo(self, huevo_id: int, huevo: Dict) -> Optional[Dict]:
        """
        Eclosiona el huevo: crea el Pokémon (sin equipo), lo marca eclosionado.
        El handler debe llamar a `finalizar_eclosion` tras pedir mote al usuario.

        Returns:
            Dict con datos del nuevo Pokémon, o None si falla.
        """
        try:
            from pokemon.services.pokemon_service import pokemon_service
            from database import db_manager as _db

            ivs: Dict = json.loads(huevo['ivs_heredados'])
            naturaleza: str = huevo['naturaleza']
            especie_id: int = huevo['pokemon_id']
            sexo = determinar_sexo(especie_id)
            sexo_texto = {"M": "♂", "F": "♀"}.get(sexo or "", "◯")

            # ── Calcular shiny con multiplicador del Amuleto Iris ────────────────────
            try:
                from funciones.pokedex_usuario import get_shiny_multiplier
                from config import POKEMON_SPAWN_CONFIG
                _prob_shiny = POKEMON_SPAWN_CONFIG.get("probabilidad_shiny", 1 / 4096)
                _prob_shiny *= get_shiny_multiplier(huevo['userID'])
            except Exception:
                _prob_shiny = 1 / 4096
            es_shiny = random.random() < _prob_shiny

            nuevo_id = pokemon_service.crear_pokemon(
                user_id=huevo['userID'],
                pokemon_id=especie_id,
                nivel=1,
                ivs=ivs,
                shiny=es_shiny,
            )
            if not nuevo_id:
                return None

            _db.execute_update(
                "UPDATE POKEMON_USUARIO SET naturaleza = ?, sexo = ?, en_equipo = 0 WHERE id_unico = ?",
                (naturaleza, sexo, nuevo_id)
            )
            self.db.execute_update(
                "UPDATE HUEVOS SET eclosionado = 1, pokemon_nacido_id = ? WHERE id = ?",
                (nuevo_id, huevo_id)
            )

            nombre = self._obtener_nombre_especie(especie_id)
            iv_total = sum(ivs.values())
            logger.info(f"🐣 Huevo {huevo_id} → {nombre} #{nuevo_id}")

            return {
                'huevo_id': huevo_id,
                'pokemon_id': nuevo_id,
                'especie_id': especie_id,
                'nombre': nombre,
                'nivel': 1,
                'naturaleza': naturaleza,
                'sexo': sexo,
                'sexo_texto': sexo_texto,
                'ivs': ivs,
                'iv_total': iv_total,
                'mensaje': (
                    f"🎉 ¡El huevo ha eclosionado!\n"
                    f"✨ {nombre} {sexo_texto} Nv.1\n"
                    f"🧬 Naturaleza: {naturaleza}\n"
                    f"💎 IVs totales: {iv_total}/186"
                ),
            }

        except Exception as e:
            logger.error(f"❌ Error eclosionando huevo {huevo_id}: {e}")
            return None

    def finalizar_eclosion(self, user_id: int, pokemon_id: int,
                           mote: Optional[str]) -> Tuple[bool, str]:
        """
        Aplica el mote (opcional) y deposita el Pokémon en equipo o PC.
        Llamar desde el handler tras recibir la respuesta del usuario.
        """
        try:
            from pokemon.services.pokemon_service import pokemon_service
            from database import db_manager as _db

            if mote:
                _db.execute_update(
                    "UPDATE POKEMON_USUARIO SET apodo = ? WHERE id_unico = ?",
                    (mote, pokemon_id)
                )

            equipo = pokemon_service.obtener_equipo(user_id)
            if len(equipo) < 6:
                _db.execute_update(
                    "UPDATE POKEMON_USUARIO SET en_equipo = 1 WHERE id_unico = ?",
                    (pokemon_id,)
                )
                destino = "tu equipo"
            else:
                destino = "el PC"

            poke = pokemon_service.obtener_pokemon(pokemon_id)
            nombre_display = mote or (poke.nombre if poke else f"#{pokemon_id}")
            return True, f"✅ {nombre_display} fue guardado en {destino}."

        except Exception as e:
            logger.error(f"❌ Error finalizando eclosión: {e}")
            return False, f"Error: {str(e)}"

    # ══════════════════════════════════════════════
    # HELPERS DE HERENCIA
    # ══════════════════════════════════════════════

    def _determinar_especie_huevo(self, p1: Dict, p2: Dict) -> int:
        """
        La especie del huevo es siempre la de la madre.
        Si uno es Ditto, la especie es la del otro.
        """
        id1 = int(p1.get('pokemonID') or p1.get('pokemon_id', 0))
        id2 = int(p2.get('pokemonID') or p2.get('pokemon_id', 0))

        if id1 == DITTO_ID:
            return id2
        if id2 == DITTO_ID:
            return id1

        # Sin Ditto: la hembra determina la especie
        if p1.get('sexo') == 'F':
            return id1
        if p2.get('sexo') == 'F':
            return id2

        return id1  # fallback

    def _calcular_ivs_heredados(self, p1: Dict, p2: Dict) -> Dict:
        """
        Hereda 3 IVs de los padres (5 con Nudo Destino).
        El resto son aleatorios.
        """
        stats = ['hp', 'atq', 'def', 'atq_sp', 'def_sp', 'vel']
        iv_col = {
            'hp': 'iv_hp', 'atq': 'iv_atq', 'def': 'iv_def',
            'atq_sp': 'iv_atq_sp', 'def_sp': 'iv_def_sp', 'vel': 'iv_vel'
        }

        ivs1 = {s: int(p1.get(iv_col[s]) or 0) for s in stats}
        ivs2 = {s: int(p2.get(iv_col[s]) or 0) for s in stats}

        item1 = str(p1.get('objeto') or '').lower()
        item2 = str(p2.get('objeto') or '').lower()
        n = 5 if ('nudo destino' in item1 or 'nudo destino' in item2) else 3

        resultado: Dict = {}
        for stat in random.sample(stats, n):
            resultado[stat] = ivs1[stat] if random.random() < 0.5 else ivs2[stat]
        for stat in stats:
            if stat not in resultado:
                resultado[stat] = random.randint(0, 31)

        return resultado

    def _determinar_naturaleza(self, p1: Dict, p2: Dict) -> str:
        """Hereda naturaleza si alguno lleva Piedra Eterna, sino aleatoria."""
        item1 = str(p1.get('objeto') or '').lower()
        item2 = str(p2.get('objeto') or '').lower()
        if 'piedra eterna' in item1:
            return str(p1.get('naturaleza') or random.choice(NATURALEZAS))
        if 'piedra eterna' in item2:
            return str(p2.get('naturaleza') or random.choice(NATURALEZAS))
        return random.choice(NATURALEZAS)

    def _determinar_habilidad(self, especie_id: int) -> str:
      """
      Selecciona habilidad de la especie con pesos canónicos Gen 5+.
      La lista viene del pokedex.json; la lógica de pesos vive en habilidades_service.
      """
      try:
          from pokemon.services.pokedex_service import pokedex_service
          from pokemon.services.habilidades_service import habilidades_service
          habs = pokedex_service.obtener_habilidades(especie_id)
          return habilidades_service.seleccionar_habilidad(habs)
      except Exception:
          return "overgrow"  # fallback inocuo

    def _calcular_movimientos_huevo(self, p1: Dict, p2: Dict, especie_id: int) -> List[str]:
        """Movimientos huevo (pendiente de implementar learnset completo)."""
        return []

    def _calcular_pasos_necesarios(self, especie_id: int) -> int:
        """Pasos según grupo de huevo de la especie."""
        if especie_id in PASOS_ESPECIALES:
            return PASOS_ESPECIALES[especie_id]
        grupos = GRUPOS_HUEVOS.get(especie_id, ["Field"])
        return PASOS_POR_GRUPO.get(grupos[0], 5120)

    def _obtener_nombre_especie(self, especie_id: int) -> str:
        try:
            from pokemon.services.pokedex_service import pokedex_service
            return pokedex_service.obtener_nombre(especie_id)
        except Exception:
            return f"Pokémon #{especie_id}"

    # ══════════════════════════════════════════════
    # CONSULTAS
    # ══════════════════════════════════════════════

    def obtener_huevos_usuario(self, user_id: int) -> List[Dict]:
        """Huevos pendientes del usuario con progreso calculado."""
        try:
            pasos_globales = self._obtener_pasos_globales(user_id)
            results = self.db.execute_query(
                "SELECT * FROM HUEVOS WHERE userID = ? AND eclosionado = 0 ORDER BY id",
                (user_id,)
            )
            huevos = []
            for row in (results or []):
                h = dict(row)
                efectivos = max(0, pasos_globales - h.get('pasos_offset', 0))
                h['pasos_efectivos'] = efectivos
                h['progreso_pct'] = min(100.0, round(efectivos / h['pasos_necesarios'] * 100, 1))
                h['nombre'] = self._obtener_nombre_especie(h['pokemon_id'])
                huevos.append(h)
            return huevos
        except Exception as e:
            logger.error(f"❌ Error obteniendo huevos: {e}")
            return []

    
# Instancia global
crianza_service = CrianzaService()