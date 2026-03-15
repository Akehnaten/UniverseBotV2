# -*- coding: utf-8 -*-
"""
Servicio de Spawns Pokémon COMPLETO
Con configuración de región, intervalos ajustables y spawns automáticos

CORRECCIONES:
- Solo spawnean Pokémon cuyo nivel mínimo es compatible con el nivel del encuentro.
  (Ej: Charizard no puede aparecer antes del nivel 36, ya que evoluciona a ese nivel.)
- Pokémon legendarios y singulares tienen probabilidad muy baja (~0.5 %).
"""

import random
import time
import logging
from typing import Optional, Dict, List, Tuple, Any
from database import db_manager
from config import NIVELES_SPAWN_POR_MEDALLAS, NIVEL_SPAWN_DEFAULT
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Importar configuración de forma segura
try:
    from pokemon.battle_config import SPAWN_CONFIG, obtener_config_region
except ImportError:
    SPAWN_CONFIG = {
        "habilitado": True,
        "intervalo_minimo": 60,
        "intervalo_maximo": 300,
        "probabilidad_shiny": 1/4096,
        "nivel_minimo": 5,
        "nivel_maximo": 50,
        "cooldown_usuario": 30,
    }
    def obtener_config_region():
        return {"pokemon_salvajes": list(range(1, 152))}


# ============================================================================
# NIVEL MÍNIMO DE APARICIÓN POR ESPECIE
# ============================================================================
# Solo se listan las formas evolucionadas. Las formas base tienen nivel mínimo 1.
# El nivel mínimo es el nivel al que la especie EVOLUCIONA desde su preforma.
# Si una cadena tiene dos evoluciones, la tercera forma acumula ambos niveles mínimos.
#
# Ejemplo: Charmeleon evoluciona de Charmander a nivel 16 → min_nivel = 16
#          Charizard evoluciona de Charmeleon a nivel 36  → min_nivel = 36
#
# Pokémon que evolucionan por piedra o intercambio: en el mundo salvaje NO
# aparecen las formas finales (ej: no existe Gengar salvaje), pero si el
# servidor lo permite, su nivel mínimo queda en 1 (no tienen restricción de nivel).
# Aquí los excluimos directamente del pool de spawn por defecto.

POKEMON_NIVEL_MINIMO: Dict[int, int] = {
    # ────── KANTO (1-151) ──────────────────────────────────────────
    # Bulbasaur line
    2: 16, 3: 32,
    # Charmander line
    5: 16, 6: 36,
    # Squirtle line
    8: 16, 9: 36,
    # Caterpie line
    11: 7, 12: 10,
    # Weedle line
    14: 7, 15: 10,
    # Pidgey line
    17: 18, 18: 36,
    # Rattata line
    20: 20,
    # Spearow line
    22: 20,
    # Ekans line
    24: 22,
    # Pikachu evoluciona con piedra → Raichu NO spawnea salvaje (excluir)
    # Sandshrew line
    28: 22,
    # Nidoran F line  (Nidorina→Nidoqueen por piedra: no spawnean formas finales)
    30: 16,
    # Nidoran M line
    33: 16,
    # Clefairy → Clefable por piedra: excluir Clefable
    # Vulpix → Ninetales por piedra: excluir Ninetales
    # Jigglypuff → Wigglytuff por piedra: excluir Wigglytuff
    # Zubat line
    42: 22,
    # Oddish line (Gloom→Vileplume por piedra: excluir Vileplume)
    44: 21,
    # Paras line
    47: 24,
    # Venonat line
    49: 31,
    # Diglett line
    51: 26,
    # Meowth line
    53: 28,
    # Psyduck line
    55: 33,
    # Mankey line
    57: 28,
    # Growlithe → Arcanine por piedra: excluir Arcanine
    # Poliwag line (Poliwhirl→Poliwrath por piedra: excluir Poliwrath)
    61: 25,
    # Abra line
    64: 16,  # Kadabra (en este bot evoluciona por nivel)
    65: 36,  # Alakazam
    # Machop line
    67: 28, 68: 36,
    # Bellsprout line (Weepinbell→Victreebel por piedra: excluir)
    70: 21,
    # Tentacool line
    73: 30,
    # Geodude line (Graveler→Golem en original por intercambio; aquí por nivel)
    75: 25, 76: 36,
    # Ponyta line
    78: 40,
    # Slowpoke line
    80: 37,
    # Magnemite line
    82: 30,
    # Doduo line
    85: 31,
    # Seel line
    87: 34,
    # Grimer line
    89: 38,
    # Shellder → Cloyster por piedra: excluir Cloyster
    # Gastly line
    93: 25, 94: 36,
    # Drowzee line
    97: 26,
    # Krabby line
    99: 28,
    # Voltorb line
    101: 30,
    # Exeggcute → Exeggutor por piedra: excluir
    # Cubone line
    105: 28,
    # Koffing line
    110: 35,
    # Rhyhorn line
    112: 42,
    # Horsea line
    117: 32,
    # Goldeen line
    119: 33,
    # Staryu → Starmie por piedra: excluir
    # Magikarp line
    130: 20,
    # Dratini line
    148: 30, 149: 55,

    # ────── JOHTO (152-251) ──────────────────────────────────────────
    153: 18, 154: 32,   # Bayleef, Meganium
    156: 14, 157: 36,   # Quilava, Typhlosion
    159: 18, 160: 30,   # Croconaw, Feraligatr
    162: 15,            # Furret
    164: 20,            # Noctowl
    166: 14,            # Ledian
    168: 22,            # Ariados
    170: 27,            # Chinchou line
    173: 1,             # Cleffa → base, ok
    175: 1,             # Togepi → base, ok
    177: 25,            # Natu line
    180: 25, 181: 30,   # Flaaffy, Ampharos
    183: 18,            # Marill line
    185: 1,             # Sudowoodo → no evoluciona (es base)
    188: 18, 189: 27,   # Skiploom, Jumpluff
    193: 24,            # Yanma (no tiene evo en esta gen)
    195: 20,            # Quagsire
    197: 25,            # Umbreon/Espeon por amistad — nivel mínimo libre
    199: 37,            # Slowking (intercambio)
    202: 1,             # Wobbuffet → base
    205: 31,            # Forretress
    207: 22,            # Gligar
    210: 23,            # Granbull
    212: 1,             # Scizor (intercambio)
    213: 1,             # Shuckle → base
    214: 1,             # Heracross → base
    216: 25,            # Ursaring
    219: 28,            # Magcargo
    221: 33,            # Piloswine
    224: 25,            # Octillery
    226: 1,             # Mantine → base
    227: 1,             # Skarmory → base
    229: 24,            # Houndoom
    231: 25,            # Donphan line
    234: 1,             # Stantler → base
    235: 1,             # Smeargle → base
    237: 1,             # Hitmontop → base (Tyrogue)
    241: 1,             # Miltank → base
    # Legendarios Johto: excluir (manejados aparte)

    # ────── HOENN (252-386) ──────────────────────────────────────────
    253: 16, 254: 36,   # Grovyle, Sceptile
    256: 16, 257: 36,   # Combusken, Blaziken
    259: 16, 260: 36,   # Marshtomp, Swampert
    262: 18,            # Mightyena
    264: 20,            # Linoone
    266: 7, 267: 10,    # Silcoon, Beautifly
    268: 7, 269: 10,    # Cascoon, Dustox
    271: 20, 272: 30,   # Lombre, Ludicolo (piedra)
    274: 14, 275: 30,   # Nuzleaf, Shiftry (piedra)
    277: 22,            # Swellow
    279: 25,            # Pelipper
    281: 20, 282: 30,   # Kirlia, Gardevoir
    284: 22,            # Masquerain
    286: 23,            # Breloom
    288: 24,            # Vigoroth
    289: 36,            # Slaking
    291: 20, 292: 20,   # Ninjask, Shedinja
    295: 25,            # Exploud
    297: 24,            # Hariyama
    302: 1,             # Sableye → base
    303: 1,             # Mawile → base
    305: 32, 306: 42,   # Lairon, Aggron
    308: 24,            # Medicham
    310: 26,            # Manectric
    312: 25,            # Minun/Plusle no tienen evo
    314: 25,            # Illumise
    317: 36,            # Swalot
    319: 30,            # Sharpedo
    321: 40,            # Wailord
    323: 33,            # Camerupt
    325: 32, 326: 1,    # Spoink, Grumpig (no tiene restricción de nivel real)
    328: 35, 329: 45,   # Vibrava, Flygon
    332: 40,            # Cacturne
    334: 35,            # Altaria
    335: 1,             # Zangoose → base
    336: 1,             # Seviper → base
    337: 1,             # Lunatone → base
    338: 1,             # Solrock → base
    340: 30,            # Whiscash
    342: 30,            # Crawdaunt
    344: 36,            # Claydol
    346: 40,            # Cradily
    348: 40,            # Armaldo
    350: 1,             # Milotic (intercambio)
    352: 1,             # Kecleon → base
    354: 30,            # Banette
    356: 37,            # Dusclops
    357: 1,             # Tropius → base
    358: 1,             # Chimecho
    360: 1,             # Wynaut → base
    362: 42,            # Glalie
    364: 32, 365: 44,   # Sealeo, Walrein
    368: 30,            # Gorebyss
    369: 1,             # Relicanth → base
    370: 1,             # Luvdisc → base
    372: 30, 373: 50,   # Shelgon, Salamence
    375: 45, 376: 1,    # Metang, Metagross (piedroa no, nivel 45)

    # ────── SINNOH (387-493) ──────────────────────────────────────────
    388: 18, 389: 32,   # Grotle, Torterra
    391: 14, 392: 36,   # Monferno, Infernape
    394: 16, 395: 36,   # Prinplup, Empoleon
    397: 14, 398: 34,   # Staravia, Staraptor
    400: 15,            # Bibarel
    402: 10,            # Kricketune
    404: 20, 405: 30,   # Luxio, Luxray
    407: 1,             # Roserade (piedra)
    409: 30,            # Rampardos
    411: 30,            # Bastiodon
    413: 20,            # Wormadam
    414: 20,            # Mothim
    416: 1,             # Vespiquen → base
    418: 26,            # Floatzel
    420: 1,             # Cherubi
    422: 1,             # Shellos → base
    424: 1,             # Ambipom
    426: 1,             # Drifblim
    428: 1,             # Lopunny
    430: 37,            # Honchkrow
    432: 1,             # Purugly
    434: 34,            # Skuntank
    436: 33, 437: 1,    # Bronzong (intercambio)
    440: 1,             # Happiny → base
    442: 1,             # Spiritomb → base
    444: 24, 445: 48,   # Gabite, Garchomp
    447: 1,             # Riolu → base
    449: 34,            # Hippowdon
    451: 40,            # Drapion
    453: 37,            # Toxicroak
    455: 1,             # Carnivine → base
    457: 1,             # Lumineon
    460: 40,            # Abomasnow
    461: 1,             # Weavile (intercambio)
    462: 30,            # Magnezone
    464: 42,            # Rhyperior (intercambio)
    466: 1,             # Electivire (intercambio)
    467: 1,             # Magmortar (intercambio)
    468: 1,             # Togekiss (piedra)
    469: 1,             # Yanmega
    470: 1,             # Leafeon (piedra)
    471: 1,             # Glaceon (piedra)
    472: 1,             # Gliscor
    473: 1,             # Mamoswine
    474: 1,             # Porygon-Z (intercambio)
    475: 1,             # Gallade (piedra)
    477: 1,             # Dusknoir (intercambio)
    478: 1,             # Froslass (piedra)
}

# ============================================================================
# POKÉMON LEGENDARIOS Y SINGULARES (probabilidad muy baja en spawn)
# ============================================================================
# Estos Pokémon pueden aparecer pero con probabilidad muy reducida (~0.5 %).
# Solo incluir IDs que estén en el pool de la región activa.

POKEMON_LEGENDARIOS: set = {
    # Kanto
    144, 145, 146, 150, 151,
    # Johto
    243, 244, 245, 249, 250, 251,
    # Hoenn
    377, 378, 379, 380, 381, 382, 383, 384, 385, 386,
    # Sinnoh
    480, 481, 482, 483, 484, 485, 486, 487, 488, 489, 490, 491, 492, 493,
    # Teselia
    638, 639, 640, 641, 642, 643, 644, 645, 646, 647, 648, 649,
    # Kalos
    716, 717, 718,
    # Alola
    785, 786, 787, 788, 789, 790, 791, 792, 800, 801,
    # Galar
    888, 889, 890, 891, 892, 894, 895, 896, 897, 898,
}

# Pokémon que evolucionan solo por piedra o intercambio y cuya forma final
# NO debe aparecer como wild (ya que en los juegos nunca spawnan salvajes).
# Si el servidor quiere habilitarlos, se puede vaciar este set.
POKEMON_NO_SPAWN_SALVAJE: set = {
    # Evoluciones por piedra (Kanto) → formas finales no spawnean
    36,   # Clefable   (Clefairy + piedra lunar)
    38,   # Ninetales  (Vulpix + piedra fuego)
    40,   # Wigglytuff (Jigglypuff + piedra lunar)
    45,   # Vileplume  (Gloom + piedra hoja)
    59,   # Arcanine   (Growlithe + piedra fuego)
    62,   # Poliwrath  (Poliwhirl + piedra agua)
    78,   # Rapidash   (Ponyta - en este caso SÍ spawnea, comentado)
    91,   # Cloyster   (Shellder + piedra agua)
    103,  # Exeggutor  (Exeggcute + piedra hoja)
    121,  # Starmie    (Staryu + piedra agua)
    135,  # Jolteon    (Eevee + piedra trueno)
    134,  # Vaporeon   (Eevee + piedra agua)
    136,  # Flareon    (Eevee + piedra fuego)
    # Evoluciones por intercambio (Kanto) → forma final no spawnea salvaje
    28,   # NO — Sandslash sí spawnea normalmente (evol por nivel en este bot)
    # Comentado: 65/68/94/76 porque en este bot evolucionan por nivel
}


@dataclass
class Spawn:
    """
    Datos de un spawn de Pokémon
    ✅ CORREGIDO: nivel puede ser None hasta que se inicie combate
    """
    pokemon_id: int
    nombre: str
    nivel: Optional[int]  # ✅ Acepta None o int
    shiny: bool
    canal_id: int
    timestamp: float
    capturado_por: Optional[int] = None


class SpawnService:
    """Servicio completo de spawns con configuración dinámica"""

    def __init__(self):
        self.db = db_manager
        self.spawns_activos = {}
        self.ultimo_spawn = {}
        self.cooldowns_usuario = {}
        self.config = SPAWN_CONFIG

    def puede_generar_spawn(self, canal_id: int) -> Tuple[bool, str]:
        """Verifica si puede generar un spawn"""
        if not self.config['habilitado']:
            return False, "Los spawns están deshabilitados"

        if canal_id in self.spawns_activos:
            return False, "Ya hay un Pokémon salvaje aquí"

        ultimo = self.ultimo_spawn.get(canal_id, 0)
        tiempo_transcurrido = time.time() - ultimo

        if tiempo_transcurrido < self.config['intervalo_minimo']:
            esperar = int(self.config['intervalo_minimo'] - tiempo_transcurrido)
            return False, f"Debes esperar {esperar} segundos"

        return True, ""

    def obtener_nivel_spawn_por_medallas(self, user_id: Optional[int] = None) -> Tuple[int, int]:
        """Obtiene el rango de niveles para spawns según medallas del usuario"""
        try:
            if user_id is None:
                return NIVEL_SPAWN_DEFAULT

            from pokemon.services import gimnasio_service
            medallas = gimnasio_service.obtener_medallas(user_id)
            num_medallas = len(medallas) if medallas else 0
            return NIVELES_SPAWN_POR_MEDALLAS.get(num_medallas, NIVEL_SPAWN_DEFAULT)

        except Exception as e:
            logger.error(f"Error obteniendo nivel spawn: {e}")
            return NIVEL_SPAWN_DEFAULT

    # ──────────────────────────────────────────────────────────────────────────
    # FILTRADO DEL POOL DE SPAWN
    # ──────────────────────────────────────────────────────────────────────────

    def _filtrar_pool_por_nivel(
        self,
        pool: List[int],
        nivel_min: int,
        nivel_max: int,
    ) -> Tuple[List[int], List[int]]:
        """
        Divide el pool en dos listas:
          - comunes:     Pokémon aptos para el nivel, que no son legendarios.
          - legendarios: Pokémon legendarios aptos para el nivel.

        Un Pokémon es apto si:
          1. Su nivel mínimo de aparición ≤ nivel_max del encuentro.
          2. No está en POKEMON_NO_SPAWN_SALVAJE.

        Args:
            pool:      Lista completa de IDs de la región.
            nivel_min: Nivel mínimo del encuentro (según medallas).
            nivel_max: Nivel máximo del encuentro.

        Returns:
            (comunes, legendarios)
        """
        comunes     = []
        legendarios = []

        for pid in pool:
            # Excluir formas que nunca spawnean salvajes
            if pid in POKEMON_NO_SPAWN_SALVAJE:
                continue

            # Nivel mínimo requerido para que este Pokémon aparezca
            nivel_minimo_especie = POKEMON_NIVEL_MINIMO.get(pid, 1)

            # El nivel máximo del spawn debe alcanzar el mínimo de la especie
            if nivel_max < nivel_minimo_especie:
                continue

            if pid in POKEMON_LEGENDARIOS:
                legendarios.append(pid)
            else:
                comunes.append(pid)

        return comunes, legendarios

    def _elegir_pokemon_del_pool(
        self,
        comunes: List[int],
        legendarios: List[int],
    ) -> int:
        """
        Selecciona un Pokémon del pool con las siguientes probabilidades:
          - 99.5 % → un Pokémon común (distribución uniforme).
          - 0.5 %  → un Pokémon legendario (si existe alguno en el pool).

        Si no hay legendarios en el pool, el 100 % va a comunes.
        """
        prob_legendario = self.config.get("probabilidad_legendario", 0.005)

        if legendarios and random.random() < prob_legendario:
            return random.choice(legendarios)
        return random.choice(comunes)

    # ──────────────────────────────────────────────────────────────────────────
    # GENERACIÓN DE SPAWN
    # ──────────────────────────────────────────────────────────────────────────

    def generar_spawn(
        self,
        canal_id: int,
        pokemon_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> Tuple[bool, Optional[Spawn]]:
        """
        Genera un spawn de Pokémon.

        ✅ CORRECCIÓN: si pokemon_id es None, filtra el pool de la región
        para que solo aparezcan Pokémon con nivel mínimo compatible con el
        rango de niveles del encuentro. Los legendarios aparecen con
        probabilidad muy baja (≈ 0.5 %).

        Args:
            canal_id:   ID del canal / thread.
            pokemon_id: ID del Pokémon (None para aleatorio).
            user_id:    ID del usuario (None = no calcular nivel aún).

        Returns:
            (éxito, Spawn o None)
        """
        try:
            puede, mensaje = self.puede_generar_spawn(canal_id)
            if not puede:
                return False, None

            config_region     = obtener_config_region()
            pokemon_salvajes  = config_region['pokemon_salvajes']

            # ── Selección del Pokémon ──────────────────────────────────────
            if pokemon_id is None:
                # Determinar rango de nivel para filtrar el pool
                if user_id is not None:
                    nivel_min, nivel_max = self.obtener_nivel_spawn_por_medallas(user_id)
                else:
                    nivel_min, nivel_max = NIVEL_SPAWN_DEFAULT

                comunes, legendarios = self._filtrar_pool_por_nivel(
                    pokemon_salvajes, nivel_min, nivel_max
                )

                if not comunes:
                    # Fallback: usar todo el pool sin filtrar (debería ser raro)
                    logger.warning(
                        f"[SPAWN] Pool vacío tras filtrado (nivel {nivel_min}-{nivel_max}), "
                        "usando pool completo como fallback."
                    )
                    comunes = [p for p in pokemon_salvajes if p not in POKEMON_LEGENDARIOS]
                    legendarios = [p for p in pokemon_salvajes if p in POKEMON_LEGENDARIOS]

                pokemon_id = self._elegir_pokemon_del_pool(comunes, legendarios)

            _prob_base = self.config.get("probabilidad_shiny", 1 / 4096)
            if user_id is not None:
                try:
                    from funciones.pokedex_usuario import get_shiny_multiplier
                    _prob_base *= get_shiny_multiplier(user_id)
                except Exception:
                    pass
            es_shiny = random.random() < _prob_base

            # ── Obtener datos del Pokémon ─────────────────────────────────
            from pokemon.services import pokedex_service

            pokemon_data = pokedex_service.obtener_pokemon(pokemon_id)
            nombre = (
                pokemon_data.get('nombre', f'Pokemon #{pokemon_id}')
                if pokemon_data
                else f'Pokemon #{pokemon_id}'
            )

            # ── Calcular nivel ────────────────────────────────────────────
            if user_id is not None:
                nivel_min, nivel_max = self.obtener_nivel_spawn_por_medallas(user_id)

                # El nivel mínimo real del Pokémon puede ser mayor que nivel_min
                nivel_minimo_especie = POKEMON_NIVEL_MINIMO.get(pokemon_id, 1)
                nivel_real_min = max(nivel_min, nivel_minimo_especie)
                nivel_real_min = min(nivel_real_min, nivel_max)  # No puede superar el máx

                nivel = random.randint(nivel_real_min, nivel_max)
            else:
                # Nivel se calculará al iniciar combate
                nivel = None

            # ── Crear spawn ───────────────────────────────────────────────
            spawn = Spawn(
                pokemon_id=pokemon_id,
                nombre=nombre,
                nivel=nivel,
                shiny=es_shiny,
                canal_id=canal_id,
                timestamp=time.time(),
                capturado_por=None,
            )

            self.spawns_activos[canal_id] = spawn
            self.ultimo_spawn[canal_id] = time.time()

            es_legendario = pokemon_id in POKEMON_LEGENDARIOS
            log_extra = " ⭐LEGENDARIO" if es_legendario else ""
            if nivel is not None:
                logger.info(
                    f"[SPAWN] ✅ {nombre} (#{pokemon_id}) Nv.{nivel} generado{log_extra}"
                )
            else:
                logger.info(
                    f"[SPAWN] ✅ {nombre} (#{pokemon_id}) generado (nivel pendiente){log_extra}"
                )

            return True, spawn

        except Exception as e:
            logger.error(f"[SPAWN] [ERROR] Error generando spawn: {e}", exc_info=True)
            return False, None

    # Agregar este método nuevo a la clase SpawnService:

    def generar_datos_spawn(self, user_id: int) -> Optional[Spawn]:
        """
        Genera y devuelve los datos de un Pokémon aleatorio calibrado para
        el usuario, SIN escribir nada en spawns_activos ni en ultimo_spawn.

        Uso exclusivo de /salvaje: el handler guarda el resultado en su
        propio dict interno.  spawn_service queda completamente ciego a
        esa invocación; los spawns automáticos siguen su ciclo sin
        ninguna interferencia.

        Returns:
            Objeto Spawn con los datos generados, o None si falla.
        """
        try:
            config_region    = obtener_config_region()
            pokemon_salvajes = config_region["pokemon_salvajes"]

            nivel_min, nivel_max = self.obtener_nivel_spawn_por_medallas(user_id)
            comunes, legendarios = self._filtrar_pool_por_nivel(
                pokemon_salvajes, nivel_min, nivel_max
            )
            if not comunes:
                comunes = pokemon_salvajes
                legendarios = []

            pokemon_id = self._elegir_pokemon_del_pool(comunes, legendarios)

            _prob_base = self.config.get("probabilidad_shiny", 1 / 4096)
            try:
                from funciones.pokedex_usuario import get_shiny_multiplier
                _prob_base *= get_shiny_multiplier(user_id)
            except Exception:
                pass
            shiny = random.random() < _prob_base

            try:
                from pokemon.services.pokedex_service import pokedex_service
                poke_data = pokedex_service.obtener_pokemon(pokemon_id)
                nombre = (
                    poke_data.get("nombre", f"Pokémon #{pokemon_id}")
                    if poke_data
                    else f"Pokémon #{pokemon_id}"
                )
            except Exception:
                nombre = f"Pokémon #{pokemon_id}"

            spawn = Spawn(
                pokemon_id=pokemon_id,
                nombre=nombre,
                nivel=None,         # Se calcula al iniciar el combate.
                shiny=shiny,
                canal_id=user_id,   # Solo para trazabilidad; NO se almacena.
                timestamp=time.time(),
            )

            # ── Nunca se escribe en spawns_activos ni en ultimo_spawn ────────
            logger.info(
                f"[SALVAJE] Datos generados para usuario {user_id}: "
                f"#{pokemon_id} ({nombre}), shiny={shiny}"
            )
            return spawn

        except Exception as exc:
            logger.error(
                f"[SALVAJE] Error en generar_datos_spawn: {exc}", exc_info=True
            )
            return None

    def generar_spawn_privado(self, user_id: int) -> Tuple[bool, Optional[Spawn]]:
        """Alias deprecado de generar_datos_spawn. No almacena estado."""
        spawn = self.generar_datos_spawn(user_id)
        return (True, spawn) if spawn is not None else (False, None)

    def calcular_nivel_spawn(self, spawn: Spawn, user_id: int) -> int:
        """
        Calcula el nivel del spawn según medallas del usuario.
        ✅ Respeta el nivel mínimo de la especie.

        Args:
            spawn:   Spawn sin nivel asignado.
            user_id: Usuario que va a combatir.

        Returns:
            Nivel calculado.
        """
        try:
            nivel_min, nivel_max = self.obtener_nivel_spawn_por_medallas(user_id)

            nivel_minimo_especie = POKEMON_NIVEL_MINIMO.get(spawn.pokemon_id, 1)
            nivel_real_min = max(nivel_min, nivel_minimo_especie)
            nivel_real_min = min(nivel_real_min, nivel_max)

            nivel = random.randint(nivel_real_min, nivel_max)
            spawn.nivel = nivel

            logger.info(
                f"[SPAWN] Nivel calculado para {spawn.nombre}: {nivel} "
                f"(usuario {user_id})"
            )
            return nivel

        except Exception as e:
            logger.error(f"Error calculando nivel spawn: {e}")
            return 5  # Nivel por defecto

    def calcular_nivel_spawn_por_id(self, pokemon_id: int, user_id: int) -> int:
        """
        Calcula el nivel de spawn para un pokemon_id sin necesitar un objeto Spawn.
        Usado por start_battle cuando el nivel es None (invocaciones /salvaje).
        """
        try:
            nivel_min, nivel_max = self.obtener_nivel_spawn_por_medallas(user_id)
            nivel_minimo_especie = POKEMON_NIVEL_MINIMO.get(pokemon_id, 1)
            nivel_real_min = max(nivel_min, nivel_minimo_especie)
            nivel_real_min = min(nivel_real_min, nivel_max)
            return random.randint(nivel_real_min, nivel_max)
        except Exception as e:
            logger.error(f"Error calculando nivel por id: {e}")
            return 5

    def obtener_spawn_activo(self, canal_id: int) -> Optional[Spawn]:
        """Obtiene el spawn activo en un canal"""
        return self.spawns_activos.get(canal_id)

    def limpiar_spawn(self, canal_id: int) -> bool:
        """Limpia un spawn activo"""
        if canal_id in self.spawns_activos:
            del self.spawns_activos[canal_id]
            logger.info(f"[SPAWN] Spawn limpiado en canal {canal_id}")
            return True
        return False


# Instancia global - se crea en __init__.py
spawn_service = SpawnService()