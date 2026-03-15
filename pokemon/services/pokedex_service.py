# -*- coding: utf-8 -*-
"""
Servicio de Pokédex
===================
Fuente única de verdad para datos de especies Pokémon.

DISEÑO:
- Se carga UNA SOLA VEZ al iniciar el bot (Singleton).
- Fuente: data/pokedex.json  (todos los Pokémon, Gen 1-9).
- Si el JSON no existe, el bot lanza error en startup — no hay fallback
  silencioso con datos falsos que contaminen la partida.
- Los tipos se normalizan al español en el momento de carga,
  por lo que el resto del código siempre trabaja en español.
- La región del servidor NO filtra qué Pokémon se cargan;
  solo afecta spawns, gimnasios y Alto Mando.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapeo de tipos inglés → español (normalización en carga)
# ---------------------------------------------------------------------------
_TIPOS_EN_ES: Dict[str, str] = {
    "Normal":   "Normal",   "Fire":     "Fuego",    "Water":    "Agua",
    "Electric": "Eléctrico","Grass":    "Planta",   "Ice":      "Hielo",
    "Fighting": "Lucha",    "Poison":   "Veneno",   "Ground":   "Tierra",
    "Flying":   "Volador",  "Psychic":  "Psíquico", "Bug":      "Bicho",
    "Rock":     "Roca",     "Ghost":    "Fantasma", "Dragon":   "Dragón",
    "Dark":     "Siniestro","Steel":    "Acero",    "Fairy":    "Hada",
}

def _normalizar_tipo(tipo: str) -> str:
    """Convierte un tipo al español. Si ya está en español lo devuelve tal cual."""
    return _TIPOS_EN_ES.get(tipo, tipo)


def _normalizar_para_busqueda(nombre: str) -> str:
    """
    Normaliza un nombre de Pokémon para búsqueda insensible a formato.

    Convierte a minúsculas, elimina tildes/diéresis y descarta cualquier
    carácter que no sea letra o dígito.  El resultado es una clave compacta
    que hace coincidir variantes como:

        "Calyrex-Shadow"  →  "calyrexshadow"
        "Calyrex Shadow"  →  "calyrexshadow"
        "calyrexshadow"   →  "calyrexshadow"
        "Nidoran♀"        →  "nidoranf"
        "Mr. Mime"        →  "mrmime"
    """
    tildes = str.maketrans(
        "áéíóúàèìòùâêîôûãñüÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÑÜ",
        "aeiouaeiouaeiouanuAEIOUAEIOUAEIOUANU",
    )
    return "".join(
        c for c in nombre.lower().strip().translate(tildes)
        if c.isalnum()
    )


# ---------------------------------------------------------------------------
# Modificadores de naturaleza
# ---------------------------------------------------------------------------
_NATURALEZAS: Dict[str, Dict[str, str]] = {
    "Hardy": {}, "Docile": {}, "Serious": {}, "Bashful": {}, "Quirky": {},
    "Lonely":  {"sube": "atq",    "baja": "def"},
    "Brave":   {"sube": "atq",    "baja": "vel"},
    "Adamant": {"sube": "atq",    "baja": "atq_sp"},
    "Naughty": {"sube": "atq",    "baja": "def_sp"},
    "Bold":    {"sube": "def",    "baja": "atq"},
    "Relaxed": {"sube": "def",    "baja": "vel"},
    "Impish":  {"sube": "def",    "baja": "atq_sp"},
    "Lax":     {"sube": "def",    "baja": "def_sp"},
    "Timid":   {"sube": "vel",    "baja": "atq"},
    "Hasty":   {"sube": "vel",    "baja": "def"},
    "Jolly":   {"sube": "vel",    "baja": "atq_sp"},
    "Naive":   {"sube": "vel",    "baja": "def_sp"},
    "Modest":  {"sube": "atq_sp", "baja": "atq"},
    "Mild":    {"sube": "atq_sp", "baja": "def"},
    "Quiet":   {"sube": "atq_sp", "baja": "vel"},
    "Rash":    {"sube": "atq_sp", "baja": "def_sp"},
    "Calm":    {"sube": "def_sp", "baja": "atq"},
    "Gentle":  {"sube": "def_sp", "baja": "def"},
    "Sassy":   {"sube": "def_sp", "baja": "vel"},
    "Careful": {"sube": "def_sp", "baja": "atq_sp"},
}

# ---------------------------------------------------------------------------

class PokedexService:
    """
    Servicio singleton de Pokédex.
    Se instancia una vez en pokemon/services/__init__.py al arrancar el bot.
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
        self._pokedex: Dict[str, Dict] = {}
        self._cargar()
        self._habilidades: Dict[int, List[str]] = {}
        self._cargar_habilidades()

    # ── Carga ────────────────────────────────────────────────────────────────

    def _cargar(self) -> None:
        """
        Carga data/pokedex.json completo en memoria.
        Normaliza tipos al español en este momento para no repetirlo en runtime.
        Lanza RuntimeError si el archivo no existe, para detectar el problema
        en startup en lugar de silenciosamente.
        """
        try:
            from config import POKEDEX_JSON
        except ImportError:
            from pathlib import Path as _P
            POKEDEX_JSON = str(_P(__file__).resolve().parents[2] / "data" / "pokedex.json")

        path = Path(POKEDEX_JSON)
        if not path.exists():
            raise RuntimeError(
                f"[PokedexService] No se encontró {path}.\n"
                "Descarga el archivo pokedex.json y colócalo en data/.\n"
                "El bot no puede arrancar sin los datos de Pokémon."
            )

        with open(path, encoding="utf-8") as f:
            raw: Dict = json.load(f)

        # El JSON puede tener regiones como wrapper: {"KANTO": {...}, "JOHTO": {...}, ...}
        # Fusionamos TODAS las regiones en un dict plano para soportar todos los Pokémon.
        if raw and not any(k.isdigit() for k in list(raw.keys())[:5]):
            merged   = {}
            regiones = []
            for key, val in raw.items():
                if isinstance(val, dict):
                    merged.update(val)
                    regiones.append(key)
            raw = merged
            logger.info(f"[PokedexService] Regiones detectadas: {', '.join(regiones)}")

        # Normalizar y almacenar
        count = 0
        for pk_id, data in raw.items():
            self._pokedex[str(pk_id)] = self._normalizar_entrada(data)
            count += 1

        logger.info(f"[PokedexService] {count} Pokémon cargados desde {path.name}")

    def _cargar_habilidades(self) -> None:
        """
        Carga data/habilidades.json en self._habilidades.
        Formato del JSON: { "pokemon_id": ["hab_normal", "hab_oculta"] }
        La habilidad oculta es siempre la ÚLTIMA de la lista.
        Si el archivo no existe, continúa sin habilidades (fallback en obtener_habilidades).
        """
        try:
            try:
                from config import BASE_DIR
                path = Path(BASE_DIR) / "data" / "habilidades.json"
            except (ImportError, AttributeError):
                path = Path(__file__).resolve().parents[2] / "data" / "habilidades.json"

            if not path.exists():
                logger.warning(
                    f"[PokedexService] habilidades.json no encontrado en {path}. "
                    "Las habilidades se omitirán."
                )
                return

            with open(path, encoding="utf-8") as f:
                raw: Dict = json.load(f)

            self._habilidades = {int(k): v for k, v in raw.items()}
            logger.info(
                f"[PokedexService] habilidades.json cargado: "
                f"{len(self._habilidades)} especies"
            )

        except Exception as e:
            logger.error(f"[PokedexService] Error cargando habilidades.json: {e}")

    def _normalizar_entrada(self, data: Dict) -> Dict:
        """
        Normaliza una entrada cruda del JSON:
        - Tipos: inglés → español
        - stats_base: garantiza que todas las keys existen
        - habilidades: lista no vacía (fallback genérico si falta)
        """
        # Tipos normalizados
        tipos_raw = data.get("tipos", ["Normal"])
        tipos = [_normalizar_tipo(t) for t in tipos_raw]

        # Stats base — el JSON usa "vel" igual que el sistema
        sb_raw = data.get("stats_base", {})
        stats_base = {
            "hp":     int(sb_raw.get("hp",     50)),
            "atq":    int(sb_raw.get("atq",    50)),
            "def":    int(sb_raw.get("def",    50)),
            "atq_sp": int(sb_raw.get("atq_sp", 50)),
            "def_sp": int(sb_raw.get("def_sp", 50)),
            "vel":    int(sb_raw.get("vel",    50)),
        }

        # Habilidades — el JSON puede no tenerlas; usamos lista vacía
        habilidades = data.get("habilidades", []) or []

        return {
            "nombre":        data.get("nombre", "???"),
            "tipos":         tipos,
            "stats_base":    stats_base,
            "ratio_captura": int(data.get("ratio_captura", 45)),
            "habilidades":   habilidades,
            "sprite":        data.get("sprite", ""),
        }

    # ── API pública ───────────────────────────────────────────────────────────

    def obtener_pokemon(self, pokemon_id: int) -> Optional[Dict]:
        """Datos completos de una especie. Devuelve None si no existe."""
        return self._pokedex.get(str(pokemon_id))

    def obtener_nombre(self, pokemon_id: int) -> str:
        data = self._pokedex.get(str(pokemon_id))
        return data["nombre"] if data else f"Pokémon #{pokemon_id}"

    def obtener_tipos(self, pokemon_id: int) -> List[str]:
        data = self._pokedex.get(str(pokemon_id))
        return data["tipos"] if data else ["Normal"]

    def obtener_stats_base(self, pokemon_id: int) -> Dict[str, int]:
        data = self._pokedex.get(str(pokemon_id))
        if data:
            return data["stats_base"]
        # Fallback seguro — stats 50/50/50 simétricas
        return {"hp": 50, "atq": 50, "def": 50, "atq_sp": 50, "def_sp": 50, "vel": 50}

    def obtener_ratio_captura(self, pokemon_id: int) -> int:
        data = self._pokedex.get(str(pokemon_id))
        return data["ratio_captura"] if data else 45

    def obtener_habilidades(self, pokemon_id: int) -> List[str]:
        """
        Devuelve la lista de habilidades de la especie.
        Fuente: data/habilidades.json  (cargado en self._habilidades).
        Fallback: si el ID no está en el JSON, retorna ["overgrow"]
                  (valor inocuo; habilidades_service.seleccionar_habilidad lo gestiona).
        """
        habs = self._habilidades.get(pokemon_id)
        if habs:
            return habs
        # Fallback: intentar desde el pokedex legacy (por si alguien tiene
        # las habilidades en pokedex.json de todas formas)
        data = self._pokedex.get(str(pokemon_id))
        if data and data.get("habilidades"):
            return data["habilidades"]
        return ["overgrow"]

    def obtener_sprite(self, pokemon_id: int) -> str:
        data = self._pokedex.get(str(pokemon_id))
        return data["sprite"] if data else ""

    def existe(self, pokemon_id: int) -> bool:
        """True si el ID existe en la pokédex cargada."""
        return str(pokemon_id) in self._pokedex

    def total(self) -> int:
        """Cantidad de Pokémon cargados."""
        return len(self._pokedex)

    def es_legendario(self, pokemon_id: int) -> bool:
        """
        Lista de IDs legendarios/míticos para todos los juegos.
        Usada por spawn_service para excluirlos del pool salvaje por defecto.
        """
        legendarios = {
            # Gen 1
            144, 145, 146, 150, 151,
            # Gen 2
            243, 244, 245, 249, 250, 251,
            # Gen 3
            377, 378, 379, 380, 381, 382, 383, 384, 385, 386,
            # Gen 4
            480, 481, 482, 483, 484, 485, 486, 487, 488, 489, 490, 491, 492, 493,
            # Gen 5
            494, 638, 639, 640, 641, 642, 643, 644, 645, 646, 647, 648, 649,
            # Gen 6
            716, 717, 718, 719, 720, 721,
            # Gen 7
            785, 786, 787, 788, 789, 790, 791, 792, 800, 801, 802,
            803, 804, 805, 806, 807,
            # Gen 8
            888, 889, 890, 891, 892, 893, 894, 895, 896, 897, 898,
            # Gen 9
            1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1017, 1024, 1025,
        }
        return pokemon_id in legendarios

    # ── Fórmulas de stats ─────────────────────────────────────────────────────

    def calcular_stats(
        self,
        pokemon_id: int,
        nivel: int,
        ivs: Dict[str, int],
        evs: Dict[str, int],
        naturaleza: str,
    ) -> Dict[str, int]:
        """
        Calcula las stats finales con la fórmula oficial Gen 3+.

        HP:   floor(((2*B + IV + EV//4) * nivel) / 100) + nivel + 10
        Otro: floor(floor(((2*B + IV + EV//4) * nivel) / 100 + 5) * mod_nat)
        """
        sb = self.obtener_stats_base(pokemon_id)
        nat = _NATURALEZAS.get(naturaleza, {})
        resultado: Dict[str, int] = {}

        for stat in ("hp", "atq", "def", "atq_sp", "def_sp", "vel"):
            base = sb[stat]
            iv   = max(0, min(31,  ivs.get(stat, 0)))
            ev   = max(0, min(255, evs.get(stat, 0)))
            inner = (2 * base + iv + ev // 4) * nivel // 100

            if stat == "hp":
                valor = inner + nivel + 10
            else:
                valor = inner + 5
                if nat.get("sube") == stat:
                    valor = int(valor * 1.1)
                elif nat.get("baja") == stat:
                    valor = int(valor * 0.9)

            resultado[stat] = max(1, valor)

        return resultado

    def modificadores_naturaleza(self, naturaleza: str) -> Dict[str, float]:
        """Devuelve dict {stat: multiplicador} para la naturaleza dada."""
        nat = _NATURALEZAS.get(naturaleza, {})
        mods = {s: 1.0 for s in ("atq", "def", "atq_sp", "def_sp", "vel")}
        if nat.get("sube"):
            mods[nat["sube"]] = 1.1
        if nat.get("baja"):
            mods[nat["baja"]] = 0.9
        return mods

    # ── Helpers de región (solo para spawn/gimnasios) ─────────────────────────

    def ids_por_region(self, region: str) -> List[int]:
        """
        IDs de Pokémon nativos de una región para el pool de spawns.
        NO filtra qué Pokémon son válidos para los usuarios — solo para spawns.
        """
        rangos = {
            "KANTO":   (1,   151),
            "JOHTO":   (152, 251),
            "HOENN":   (252, 386),
            "SINNOH":  (387, 493),
            "TESELIA": (494, 649),
            "KALOS":   (650, 721),
            "ALOLA":   (722, 809),
            "GALAR":   (810, 905),
            "PALDEA":  (906, 1025),
        }
        inicio, fin = rangos.get(region.upper(), (1, 151))
        return [i for i in range(inicio, fin + 1) if self.existe(i)]

    def buscar_id_por_nombre(self, nombre: str) -> Optional[int]:
        """
        Busca el ID numérico de una especie Pokémon por nombre.

        La búsqueda es insensible a mayúsculas/minúsculas, tildes y
        separadores (guiones, espacios).  Esto permite encontrar:

            "Calyrex-Shadow"  →  ID si la Pokédex tiene "Calyrex-Shadow"
            "calyrex shadow"  →  ídem
            "Gardevoir"       →  ID independientemente de capitalización

        Recorre self._pokedex linealmente (cargado en memoria al arrancar).
        O(n) aceptable porque este método solo lo invoca el comando admin
        /crearpokemon, nunca en rutas hot de batalla o spawn.

        Args:
            nombre: Nombre de la especie tal como viene del paste de Smogon.

        Returns:
            ID numérico de la especie, o None si no se encontró ninguna
            coincidencia.  Jamás lanza excepción.
        """
        if not nombre or not nombre.strip():
            return None

        busqueda = _normalizar_para_busqueda(nombre)

        for id_str, data in self._pokedex.items():
            nombre_pokedex = data.get("nombre", "")
            if _normalizar_para_busqueda(nombre_pokedex) == busqueda:
                return int(id_str)

        return None


# Instancia global — se crea al importar pokemon/services/__init__.py
pokedex_service = PokedexService()