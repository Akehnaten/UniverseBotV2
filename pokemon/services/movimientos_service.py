# -*- coding: utf-8 -*-
"""
Servicio de Movimientos Pokémon - Sistema Completo
Carga TODOS los movimientos desde moves.json (800+)
Sistema de learnsets en cascada: Gen9 → Región específica
"""
from __future__ import annotations
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class MovimientosService:
    """
    Servicio completo de movimientos
    - Carga moves.json al inicio (una sola vez)
    - Cache en memoria para velocidad
    - Sistema de learnsets en cascada
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        from config import MOVES_JSON, DATA_DIR
        from pathlib import Path as PathLib
        self.movimientos = {}
        self.learnsets_cache = {}
        self.moves_path = PathLib(MOVES_JSON)
        self.learnsets_gen9_path = PathLib(DATA_DIR) / "learnsets_gen9_total.json"

        data_path = PathLib(DATA_DIR)
        self.learnsets_archivos = {
            "GEN3":    data_path / "learnsets_gen3.json",
            "SINNOH":  data_path / "learnsets_gen4_sinnoh.json",
            "TESELIA": data_path / "learnsets_gen5_teselia.json",
            "KALOS":   data_path / "learnsets_gen6_kalos.json",
            "ALOLA":   data_path / "learnsets_gen7_alola.json",
        }

        # Cache del JSON gen9 en memoria (se carga una sola vez)
        self._gen9_data: Dict[str, Any] = {}  # empty until lazy-loaded

        self._crear_mapeos()
        self._cargar_movimientos()

    # =========================================================================
    # MAPEOS Y CARGA DE MOVIMIENTOS
    # =========================================================================

    def _crear_mapeos(self):
        self.tipo_map = {
            "Normal": "Normal", "Fire": "Fuego", "Water": "Agua",
            "Electric": "Eléctrico", "Grass": "Planta", "Ice": "Hielo",
            "Fighting": "Lucha", "Poison": "Veneno", "Ground": "Tierra",
            "Flying": "Volador", "Psychic": "Psíquico", "Bug": "Bicho",
            "Rock": "Roca", "Ghost": "Fantasma", "Dragon": "Dragón",
            "Dark": "Siniestro", "Steel": "Acero", "Fairy": "Hada"
        }
        self.categoria_map = {
            "Physical": "Físico",
            "Special": "Especial",
            "Status": "Estado"
        }

    def _cargar_movimientos(self):
        """Carga TODOS los movimientos desde moves.json"""
        try:
            if not self.moves_path.exists():
                logger.error(f"❌ No se encontró {self.moves_path}")
                self._crear_movimientos_fallback()
                return

            with open(self.moves_path, 'r', encoding='utf-8') as f:
                moves_raw = json.load(f)

            for move_id, move_data in moves_raw.items():
                nombre = move_data.get('name', move_id.title())
                processed = {
                    'nombre': nombre,
                    'nombre_id': move_id,
                    'tipo': self.tipo_map.get(
                        move_data.get('type') or move_data.get('flags', {}).get('type', 'Normal'),
                        'Normal'
                    ),
                    'categoria': self.categoria_map.get(move_data.get('category', 'Status'), 'Estado'),
                    'poder': move_data.get('basePower', 0),
                    'precision': move_data.get('accuracy', True),
                    'pp': move_data.get('pp', 10),
                    'prioridad': move_data.get('priority', 0),
                    'contact': move_data.get('flags', {}).get('contact', False),
                    'protect': move_data.get('flags', {}).get('protect', True),
                    'sound': move_data.get('flags', {}).get('sound', False),
                    'punch': move_data.get('flags', {}).get('punch', False),
                    'bite': move_data.get('flags', {}).get('bite', False),
                    'status': move_data.get('status'),
                    'volatileStatus': move_data.get('volatileStatus'),
                    'secondary': move_data.get('secondary'),
                    'self': move_data.get('self'),
                    'heal': move_data.get('heal'),
                    'recoil': move_data.get('recoil'),
                    'drain': move_data.get('drain'),
                    'multihit': move_data.get('multihit'),
                    'desc': move_data.get('desc', ''),
                    'shortDesc': move_data.get('shortDesc', '')
                }
                nombre_str = str(nombre).lower() if nombre else ""
                move_id_str = str(move_id).lower() if move_id else ""
                if nombre_str:
                    self.movimientos[nombre_str] = processed
                if move_id_str:
                    self.movimientos[move_id_str] = processed

            logger.info(f"✅ {len(moves_raw)} movimientos cargados desde moves.json")

        except Exception as e:
            logger.error(f"❌ Error cargando movimientos: {e}")
            self._crear_movimientos_fallback()

    def _crear_movimientos_fallback(self):
        self.movimientos = {
            "tackle": {
                "nombre": "Tackle", "tipo": "Normal", "categoria": "Físico",
                "poder": 40, "precision": 100, "pp": 35, "prioridad": 0, "contact": True
            },
            "thunderbolt": {
                "nombre": "Thunderbolt", "tipo": "Eléctrico", "categoria": "Especial",
                "poder": 90, "precision": 100, "pp": 15, "prioridad": 0
            },
            "flamethrower": {
                "nombre": "Flamethrower", "tipo": "Fuego", "categoria": "Especial",
                "poder": 90, "precision": 100, "pp": 15, "prioridad": 0
            },
            "surf": {
                "nombre": "Surf", "tipo": "Agua", "categoria": "Especial",
                "poder": 90, "precision": 100, "pp": 15, "prioridad": 0
            },
        }
        logger.warning("⚠️ Usando movimientos fallback")

    def obtener_movimiento(self, nombre: str) -> Optional[Dict]:
        """
        Obtiene datos de un movimiento.
        Busca primero por nombre display, luego por move_id (ambos en lowercase).
        """
        nombre_lower = nombre.lower().strip().replace(' ', '')
        # Búsqueda 1: nombre tal cual (puede incluir espacios)
        result = self.movimientos.get(nombre.lower().strip())
        if result:
            return result
        # Búsqueda 2: sin espacios (formato move_id del JSON)
        return self.movimientos.get(nombre_lower)

    # =========================================================================
    # SISTEMA DE LEARNSETS — CASCADA Gen9 → Regional
    # =========================================================================

    @staticmethod
    def _normalizar_nombre(nombre: str) -> str:
        """
        Normaliza un nombre de Pokémon al formato de clave del JSON de learnsets:
        lowercase, sin tildes, sin espacios, sin guiones, sin puntos, sin apóstrofes.
        Ej: "Mr. Mime" → "mrmime", "Nidoran♀" → "nidoranf"
        """
        if not nombre:
            return ""
        tildes = str.maketrans("áéíóúàèìòùâêîôûãñü", "aeiouaeiouaeiouanu")
        n = nombre.lower().strip().translate(tildes)
        # Quitar caracteres no alfanuméricos excepto letras/dígitos
        n = ''.join(c for c in n if c.isalnum())
        return n

    def _nombre_normalizado(self, pokemon_id: int) -> str:
        """Obtiene el nombre normalizado de un Pokémon por ID desde la Pokédex."""
        try:
            from pokemon.services.pokedex_service import pokedex_service
            nombre = pokedex_service.obtener_nombre(pokemon_id)
            if nombre and not nombre.startswith("Pokémon #"):
                return self._normalizar_nombre(nombre)
        except Exception:
            pass
        return ""

    def _cargar_gen9_data(self) -> Dict[str, Any]:
        """Carga el JSON Gen9 en memoria una sola vez (lazy load)."""
        if not self._gen9_data:  # vacío o no cargado aún
            if self.learnsets_gen9_path.exists():
                try:
                    with open(self.learnsets_gen9_path, 'r', encoding='utf-8') as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        self._gen9_data = loaded
                        logger.debug(f"[LEARNSET] Gen9 cargado: {len(self._gen9_data)} entradas")
                except Exception as e:
                    logger.error(f"[LEARNSET] Error cargando Gen9: {e}")
            else:
                logger.warning(f"[LEARNSET] Archivo Gen9 no encontrado: {self.learnsets_gen9_path}")
        return self._gen9_data

    @staticmethod
    def _normalizar_move_key(move_name: str) -> str:
        """Normaliza un nombre de movimiento a clave canónica: lowercase, sin espacios ni guiones."""
        return move_name.lower().replace(" ", "").replace("-", "")

    @staticmethod
    def _parsear_entry(entry: Dict) -> Optional[Dict[int, List[str]]]:
        """
        Parsea una entrada de learnset al formato interno {nivel: [moves]}.
        Todas las claves de movimiento se normalizan a lowercase sin espacios
        para evitar duplicados por diferencias de capitalización o formato.

        Soporta DOS formatos:
          Formato A (gen9_total.json):
            {"tackle": ["Nivel 1"], "vinewhip": ["Nivel 3", "MT/MO"], ...}

          Formato B (archivos regionales legacy):
            {"nivel": {"1": ["Tackle", "VineWhip"], "7": "Growl"}, ...}
        """
        if not entry or not isinstance(entry, dict):
            return None

        def _norm(name: str) -> str:
            return name.lower().replace(" ", "").replace("-", "")

        # ── Formato B: tiene clave 'nivel' como wrapper ──────────────────────
        if 'nivel' in entry:
            nivel_data = entry['nivel']
            if isinstance(nivel_data, dict):
                learnset: Dict[int, List[str]] = {}
                for lvl_str, moves in nivel_data.items():
                    try:
                        lvl = int(lvl_str)
                        raw = [moves] if isinstance(moves, str) else list(moves)
                        # Normalizar y deduplicar
                        seen: set = set()
                        normalized: List[str] = []
                        for m in raw:
                            mk = _norm(str(m))
                            if mk and mk not in seen:
                                seen.add(mk)
                                normalized.append(mk)
                        if normalized:
                            learnset[lvl] = normalized
                    except (ValueError, TypeError):
                        pass
                return learnset if learnset else None

        # ── Formato A: {move_name: [methods]} ───────────────────────────────
        sample = next(iter(entry.values()), None)
        if isinstance(sample, list):
            learnset: Dict[int, List[str]] = {}
            for move_name, methods in entry.items():
                if not isinstance(methods, list):
                    continue
                move_key = _norm(move_name)   # ← normalizar ANTES del dedup
                if not move_key:
                    continue
                for method in methods:
                    if isinstance(method, str) and method.startswith('Nivel '):
                        try:
                            lvl = int(method.split(' ', 1)[1])
                            learnset.setdefault(lvl, [])
                            if move_key not in learnset[lvl]:   # ← compara normalizado
                                learnset[lvl].append(move_key)
                        except (ValueError, IndexError):
                            pass
            return learnset if learnset else None

        return None

    def _buscar_en_data(self, data: Dict, pokemon_id: int, nombre_norm: str) -> Optional[Dict]:
        """
        Busca la entrada de un Pokémon en un dict de learnset con 3 estrategias:
          1. Clave = nombre normalizado (más común)
          2. Clave = ID numérico como string
          3. Recorrido lineal buscando campo nombre/name dentro del entry
        """
        if not data:
            return None

        # 1. Por nombre normalizado
        if nombre_norm:
            entry = data.get(nombre_norm)
            if entry:
                return entry

        # 2. Por ID numérico
        entry = data.get(str(pokemon_id))
        if entry:
            return entry

        # 3. Recorrido lineal — campo interno nombre/name
        if nombre_norm:
            for val in data.values():
                if not isinstance(val, dict):
                    continue
                internal_name = str(val.get('nombre', val.get('name', ''))).lower()
                if self._normalizar_nombre(internal_name) == nombre_norm:
                    return val

        return None

    def _cargar_learnset_gen9(self, pokemon_id: int, nombre_norm: str = "") -> Optional[Dict]:
        """Intenta cargar el learnset desde el JSON Gen9 total."""
        try:
            data = self._cargar_gen9_data()
            entry = self._buscar_en_data(data, pokemon_id, nombre_norm)
            if entry is None:
                return None
            result = self._parsear_entry(entry)
            if result:
                logger.debug(f"[LEARNSET] Gen9: Pokémon {pokemon_id} ({nombre_norm}) → {len(result)} niveles")
            return result
        except Exception as e:
            logger.debug(f"[LEARNSET] Error Gen9 para {pokemon_id}: {e}")
            return None

    def _cargar_learnset_region(self, pokemon_id: int, nombre_norm: str = "") -> Optional[Dict]:
        """Intenta cargar el learnset desde el archivo regional correspondiente."""
        try:
            if pokemon_id <= 386:
                archivo = self.learnsets_archivos["GEN3"]
            elif pokemon_id <= 493:
                archivo = self.learnsets_archivos["SINNOH"]
            elif pokemon_id <= 649:
                archivo = self.learnsets_archivos["TESELIA"]
            elif pokemon_id <= 721:
                archivo = self.learnsets_archivos["KALOS"]
            elif pokemon_id <= 809:
                archivo = self.learnsets_archivos["ALOLA"]
            else:
                return None

            if not archivo.exists():
                logger.debug(f"[LEARNSET] Archivo regional no encontrado: {archivo}")
                return None

            with open(archivo, 'r', encoding='utf-8') as f:
                data = json.load(f)

            entry = self._buscar_en_data(data, pokemon_id, nombre_norm)
            if entry is None:
                return None

            result = self._parsear_entry(entry)
            if result:
                logger.debug(f"[LEARNSET] Regional: Pokémon {pokemon_id} ({nombre_norm}) → {len(result)} niveles")
            return result

        except Exception as e:
            logger.debug(f"[LEARNSET] Error regional para {pokemon_id}: {e}")
            return None

    # ── Rangos aproximados de pokemonID por generación (inclusivos) ──────────────
_GEN_RANGES = [
    (1,   151),   # Gen 1
    (152, 251),   # Gen 2
    (252, 386),   # Gen 3
    (387, 493),   # Gen 4
    (494, 649),   # Gen 5
    (650, 721),   # Gen 6
    (722, 809),   # Gen 7
    (810, 905),   # Gen 8
    (906, 10000), # Gen 9+
]
 
 
def _gen_de_pokemon(pokemon_id: int) -> int:
    """Retorna el número de generación (1-9) al que pertenece pokemon_id."""
    for gen, (lo, hi) in enumerate(_GEN_RANGES, start=1):
        if lo <= pokemon_id <= hi:
            return gen
    return 9
 
 
def _obtener_base_evolutiva(pokemon_id: int) -> List[int]:
    """
    Retorna una lista con los IDs de la cadena evolutiva previa (hacia atrás).
    Ejemplo: Charizard(6) → [5, 4]
    Retorna [] si no se puede determinar.
    """
    candidatos: List[int] = []
    try:
        from pokemon.services.evolucion_service import evolucion_service
        # Recorrer todas las entradas buscando quién evoluciona a este ID
        visited: set = set()
        current = pokemon_id
        for _ in range(5):  # máximo 5 pasos hacia atrás
            if current in visited:
                break
            visited.add(current)
            encontrado = False
            for pre_id_str, evos in evolucion_service.evoluciones.items():
                for evo in evos:
                    if int(evo.get("evoluciona_a", -1)) == current:
                        pre_id = int(pre_id_str)
                        candidatos.append(pre_id)
                        current = pre_id
                        encontrado = True
                        break
                if encontrado:
                    break
            if not encontrado:
                break
    except Exception as e:
        logger.debug(f"[LEARNSET_FALLBACK] No se pudo obtener cadena evolutiva: {e}")
    return candidatos
 
 
def obtener_learnset_con_fallback(
    self_or_module,
    pokemon_id: int,
    *,
    _learnsets_attr: str = "learnsets",
) -> Dict[int, List[str]]:
    """
    Versión mejorada de obtener_learnset con fallback generacional.
 
    Estrategia:
    1. Intentar con pokemon_id directo.
    2. Si vacío, intentar con cada forma previa de la cadena evolutiva.
    3. Si aún vacío, intentar con IDs de generaciones anteriores cercanas
       (útil para Pokémon con formas regionales o IDs altos).
 
    Retorna el primer learnset no vacío encontrado, o {} si ninguno tiene datos.
    """
    # ── Helper: acceder al dict de learnsets ──────────────────────────────────
    def _raw_learnset(pid: int) -> Dict[int, List[str]]:
        """Obtiene el learnset crudo del servicio, sin fallback."""
        try:
            # Si es una clase con atributo learnsets
            learnsets = getattr(self_or_module, _learnsets_attr, None)
            if learnsets is not None:
                return learnsets.get(str(pid), learnsets.get(pid, {}))
        except Exception:
            pass
        try:
            # Si el módulo expone una función _obtener_learnset_raw
            fn = getattr(self_or_module, "_obtener_learnset_raw", None)
            if fn:
                return fn(pid) or {}
        except Exception:
            pass
        return {}
 
    # ── 1. Intento directo ────────────────────────────────────────────────────
    resultado = _raw_learnset(pokemon_id)
    if resultado:
        return resultado
 
    logger.debug(f"[LEARNSET_FALLBACK] {pokemon_id}: sin datos directos, buscando en cadena previa.")
 
    # ── 2. Cadena evolutiva previa ────────────────────────────────────────────
    for pre_id in _obtener_base_evolutiva(pokemon_id):
        resultado = _raw_learnset(pre_id)
        if resultado:
            logger.debug(f"[LEARNSET_FALLBACK] {pokemon_id}: datos encontrados en pre-evo {pre_id}.")
            return resultado
 
    logger.debug(f"[LEARNSET_FALLBACK] {pokemon_id}: sin datos en cadena previa, intentando gen anterior.")
 
    # ── 3. Fallback por generación (busca la especie base de cada gen anterior) ─
    # Útil para formas regionales de Gen 8/9 con IDs > 900 que comparten learnset
    # con su contraparte original.
    gen_actual = _gen_de_pokemon(pokemon_id)
    for gen_fallback in range(gen_actual - 1, 0, -1):
        lo, hi = _GEN_RANGES[gen_fallback - 1]
        # Intentar el mismo pokemon_id reducido al rango de esa gen (heurístico)
        candidate_id = max(lo, min(hi, pokemon_id - ((_GEN_RANGES[gen_actual - 1][0]) - lo)))
        if candidate_id != pokemon_id:
            resultado = _raw_learnset(candidate_id)
            if resultado:
                logger.debug(
                    f"[LEARNSET_FALLBACK] {pokemon_id}: datos encontrados "
                    f"en fallback gen {gen_fallback} id {candidate_id}."
                )
                return resultado
 
    logger.warning(f"[LEARNSET_FALLBACK] {pokemon_id}: no se encontró learnset en ninguna generación.")
    return {}

    def obtener_movimientos_nivel(self, pokemon_id: int, nivel: int) -> List[str]:
        """
        Movimientos que aprende exactamente en ese nivel.
        Aplica dedup final normalizado como defensa ante datos inconsistentes.
        """
        raw = self.obtener_learnset(pokemon_id).get(nivel, [])
        seen: set = set()
        result: List[str] = []
        for m in raw:
            mk = m.lower().replace(" ", "").replace("-", "")
            if mk and mk not in seen:
                seen.add(mk)
                result.append(m)
        return result
    
    def puede_aprender_por_mt(self, pokemon_id: int, move_key: str) -> bool:
        """
        Retorna True si el Pokémon puede aprender el movimiento por MT/MO.
        Lee el learnset Gen9 (Formato A) donde los métodos incluyen "MT/MO".
        """
        try:
            nombre_norm = self._nombre_normalizado(pokemon_id)
            data        = self._cargar_gen9_data()
            entry       = self._buscar_en_data(data, pokemon_id, nombre_norm)
            if not entry or not isinstance(entry, dict):
                return False

            mk = self._normalizar_move_key(move_key)
            for move_name, methods in entry.items():
                if self._normalizar_move_key(move_name) == mk:
                    if isinstance(methods, list):
                        return any(
                            isinstance(m, str) and "MT" in m.upper()
                            for m in methods
                        )
            return False
        except Exception as e:
            logger.debug(
                f"[MT] Error verificando MT para #{pokemon_id} / {move_key}: {e}")
            return False




    def obtener_todos_movimientos_hasta_nivel(self, pokemon_id: int, nivel: int) -> List[str]:
        """
        Todos los movimientos aprendibles hasta un nivel, devuelve los últimos 4
        (simulando el sistema de movimientos de los juegos oficiales).
        """
        learnset = self.obtener_learnset(pokemon_id)

        movimientos: List[str] = []
        for lvl in sorted(learnset.keys()):
            if lvl <= nivel:
                for move in learnset[lvl]:
                    if move not in movimientos:
                        movimientos.append(move)

        # Mantener los últimos 4 (los más recientes/fuertes al máximo nivel)
        if len(movimientos) > 4:
            movimientos = movimientos[-4:]

        if not movimientos:
            movimientos = ["tackle"]

        logger.debug(f"[MOVIMIENTOS] #{pokemon_id} Nv.{nivel} → {movimientos}")
        return movimientos

    # =========================================================================
    # CÁLCULO DE DAÑO Y EFECTIVIDAD
    # =========================================================================

    def obtener_precision(self, movimiento: str) -> int:
        move_data = self.obtener_movimiento(movimiento)
        if not move_data:
            return 100
        precision = move_data.get('precision', True)
        if precision is True:
            return 999
        return int(precision)

    def calcular_dano(self, movimiento: str, atacante_stats: Dict,
                      defensor_stats: Dict, nivel_atacante: int,
                      tipo_atacante: List[str], tipo_defensor: List[str],
                      clima: Optional[str] = None) -> int:
        move_data = self.obtener_movimiento(movimiento)
        if not move_data or move_data['categoria'] == 'Estado':
            return 0

        poder = move_data['poder']
        tipo_movimiento = move_data['tipo']

        if move_data['categoria'] == 'Físico':
            ataque = atacante_stats['atq']
            defensa = defensor_stats['def']
        else:
            ataque = atacante_stats['atq_sp']
            defensa = defensor_stats['def_sp']

        if defensa == 0:
            defensa = 1

        dano_base = (((2 * nivel_atacante / 5 + 2) * poder * ataque / defensa) / 50) + 2
        stab = 1.5 if tipo_movimiento in tipo_atacante else 1.0
        efectividad = self._calcular_efectividad(tipo_movimiento, tipo_defensor)
        modificador_clima = self._aplicar_clima(tipo_movimiento, clima or "")

        dano_final = int(dano_base * stab * efectividad * modificador_clima)
        return max(1, dano_final)

    def _calcular_efectividad(self, tipo_ataque: str, tipos_defensor: List[str]) -> float:
        efectividades = {
            ("Fuego",    "Planta"): 2.0, ("Fuego",    "Hielo"):   2.0,
            ("Fuego",    "Bicho"):  2.0, ("Fuego",    "Acero"):   2.0,
            ("Fuego",    "Agua"):   0.5, ("Fuego",    "Roca"):    0.5,
            ("Fuego",    "Fuego"):  0.5, ("Fuego",    "Dragón"):  0.5,
            ("Agua",     "Fuego"):  2.0, ("Agua",     "Tierra"):  2.0,
            ("Agua",     "Roca"):   2.0, ("Agua",     "Planta"):  0.5,
            ("Agua",     "Agua"):   0.5, ("Agua",     "Dragón"):  0.5,
            ("Planta",   "Agua"):   2.0, ("Planta",   "Tierra"):  2.0,
            ("Planta",   "Roca"):   2.0, ("Planta",   "Fuego"):   0.5,
            ("Planta",   "Planta"): 0.5, ("Planta",   "Veneno"):  0.5,
            ("Planta",   "Volador"): 0.5,("Planta",   "Bicho"):   0.5,
            ("Planta",   "Dragón"): 0.5, ("Planta",   "Acero"):   0.5,
            ("Eléctrico","Agua"):   2.0, ("Eléctrico","Volador"):  2.0,
            ("Eléctrico","Planta"): 0.5, ("Eléctrico","Eléctrico"):0.5,
            ("Eléctrico","Dragón"): 0.5, ("Eléctrico","Tierra"):   0.0,
            ("Hielo",    "Planta"): 2.0, ("Hielo",    "Tierra"):  2.0,
            ("Hielo",    "Volador"): 2.0,("Hielo",    "Dragón"):  2.0,
            ("Hielo",    "Agua"):   0.5, ("Hielo",    "Hielo"):   0.5,
            ("Lucha",    "Normal"): 2.0, ("Lucha",    "Hielo"):   2.0,
            ("Lucha",    "Roca"):   2.0, ("Lucha",    "Siniestro"):2.0,
            ("Lucha",    "Acero"):  2.0, ("Lucha",    "Veneno"):  0.5,
            ("Lucha",    "Bicho"):  0.5, ("Lucha",    "Psíquico"):0.5,
            ("Lucha",    "Volador"): 0.5,("Lucha",    "Fantasma"): 0.0,
            ("Veneno",   "Planta"): 2.0, ("Veneno",   "Hada"):    2.0,
            ("Veneno",   "Veneno"): 0.5, ("Veneno",   "Tierra"):  0.5,
            ("Veneno",   "Roca"):   0.5, ("Veneno",   "Fantasma"): 0.5,
            ("Veneno",   "Acero"):  0.0,
            ("Tierra",   "Fuego"):  2.0, ("Tierra",   "Eléctrico"):2.0,
            ("Tierra",   "Veneno"): 2.0, ("Tierra",   "Roca"):    2.0,
            ("Tierra",   "Acero"):  2.0, ("Tierra",   "Planta"):  0.5,
            ("Tierra",   "Bicho"):  0.5, ("Tierra",   "Volador"):  0.0,
            ("Volador",  "Planta"): 2.0, ("Volador",  "Lucha"):   2.0,
            ("Volador",  "Bicho"):  2.0, ("Volador",  "Eléctrico"):0.5,
            ("Volador",  "Roca"):   0.5, ("Volador",  "Acero"):   0.5,
            ("Psíquico", "Lucha"):  2.0, ("Psíquico", "Veneno"):  2.0,
            ("Psíquico", "Psíquico"):0.5,("Psíquico", "Acero"):   0.5,
            ("Psíquico", "Siniestro"):0.0,
            ("Bicho",    "Planta"): 2.0, ("Bicho",    "Psíquico"):2.0,
            ("Bicho",    "Siniestro"):2.0,("Bicho",   "Fuego"):   0.5,
            ("Bicho",    "Lucha"):  0.5, ("Bicho",    "Volador"):  0.5,
            ("Bicho",    "Fantasma"):0.5,("Bicho",    "Acero"):   0.5,
            ("Bicho",    "Hada"):   0.5,
            ("Roca",     "Fuego"):  2.0, ("Roca",     "Hielo"):   2.0,
            ("Roca",     "Volador"): 2.0,("Roca",     "Bicho"):   2.0,
            ("Roca",     "Lucha"):  0.5, ("Roca",     "Tierra"):  0.5,
            ("Roca",     "Acero"):  0.5,
            ("Fantasma", "Psíquico"):2.0,("Fantasma", "Fantasma"):2.0,
            ("Fantasma", "Normal"): 0.0, ("Fantasma", "Siniestro"):0.5,
            ("Fantasma", "Acero"):  0.5,
            ("Dragón",   "Dragón"): 2.0, ("Dragón",   "Acero"):   0.5,
            ("Dragón",   "Hada"):   0.0,
            ("Siniestro","Psíquico"):2.0,("Siniestro","Fantasma"): 2.0,
            ("Siniestro","Lucha"):  0.5, ("Siniestro","Siniestro"):0.5,
            ("Siniestro","Hada"):   0.5,
            ("Acero",    "Hielo"):  2.0, ("Acero",    "Roca"):    2.0,
            ("Acero",    "Hada"):   2.0, ("Acero",    "Fuego"):   0.5,
            ("Acero",    "Agua"):   0.5, ("Acero",    "Eléctrico"):0.5,
            ("Acero",    "Acero"):  0.5,
            ("Hada",     "Lucha"):  2.0, ("Hada",     "Dragón"):  2.0,
            ("Hada",     "Siniestro"):2.0,("Hada",    "Fuego"):   0.5,
            ("Hada",     "Veneno"): 0.5, ("Hada",     "Acero"):   0.5,
        }
        multiplicador = 1.0
        for tipo_def in tipos_defensor:
            multiplicador *= efectividades.get((tipo_ataque, tipo_def), 1.0)
        return multiplicador

    def _aplicar_clima(self, tipo_movimiento: str, clima: str) -> float:
        if clima == "SOL":
            if tipo_movimiento == "Fuego":
                return 1.5
            if tipo_movimiento == "Agua":
                return 0.5
        elif clima == "LLUVIA":
            if tipo_movimiento == "Agua":
                return 1.5
            if tipo_movimiento == "Fuego":
                return 0.5
        return 1.0


# Instancia global del servicio
movimientos_service = MovimientosService()
