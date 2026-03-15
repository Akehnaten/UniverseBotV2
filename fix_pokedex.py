# -*- coding: utf-8 -*-
"""
fix_pokedex.py
══════════════════════════════════════════════════════════════════════════════
Corrige las stats de todos los Pokémon en data/pokedex.json usando los datos
oficiales de PokeAPI, y agrega las formas fusión de Calyrex que faltan.

EJECUTAR desde la raíz del proyecto:
    python3 fix_pokedex.py

Requiere:
    pip install requests

Crea un backup antes de modificar: data/pokedex.json.backup
══════════════════════════════════════════════════════════════════════════════
"""

import json
import shutil
import time
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ Falta la librería 'requests'. Instalala con:  pip install requests")
    sys.exit(1)

# ── Rutas ─────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent
POKEDEX_JSON = BASE_DIR / "data" / "pokedex.json"
BACKUP_PATH  = BASE_DIR / "data" / "pokedex.json.backup"

# ── Mapeo de stats: PokeAPI → claves internas del bot ─────────────────────────
_STAT_MAP = {
    "hp":              "hp",
    "attack":          "atq",
    "defense":         "def",
    "special-attack":  "atq_sp",
    "special-defense": "def_sp",
    "speed":           "vel",
}

# ── Formas especiales que PokeAPI sirve con un nombre de endpoint distinto ────
# Formato: id_numerico_en_json → nombre_en_pokeapi
_FORMAS_ESPECIALES = {
    "10195": "calyrex-shadow",
    "10196": "calyrex-ice",
}

# ── Datos de las formas nuevas a agregar (metadatos que PokeAPI no incluye) ──
_NUEVAS_FORMAS = {
    "10195": {
        "nombre": "Calyrex-Shadow",
        "tipos":  ["Psychic", "Ghost"],
        "ratio_captura": 45,
        "habilidades": [],
        "sprite": (
            "https://raw.githubusercontent.com/PokeAPI/sprites/master/"
            "sprites/pokemon/10195.png"
        ),
    },
    "10196": {
        "nombre": "Calyrex-Ice",
        "tipos":  ["Psychic", "Ice"],
        "ratio_captura": 45,
        "habilidades": [],
        "sprite": (
            "https://raw.githubusercontent.com/PokeAPI/sprites/master/"
            "sprites/pokemon/10196.png"
        ),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_stats(pokemon_name_or_id: str) -> dict | None:
    """
    Consulta PokeAPI y devuelve las 6 stats del Pokémon como dict interno.
    Devuelve None si la petición falla.
    """
    url = f"https://pokeapi.co/api/v2/pokemon/{pokemon_name_or_id}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 404:
            print(f"  ⚠️  404 para '{pokemon_name_or_id}' — se omite")
            return None
        resp.raise_for_status()
        data = resp.json()
        stats = {}
        for s in data["stats"]:
            key = _STAT_MAP.get(s["stat"]["name"])
            if key:
                stats[key] = s["base_stat"]
        return stats
    except Exception as exc:
        print(f"  ❌ Error fetching '{pokemon_name_or_id}': {exc}")
        return None


def _aplanar(raw: dict) -> dict:
    """Aplana la estructura {REGION: {id: entry}} a {id: entry}."""
    plano = {}
    for val in raw.values():
        if isinstance(val, dict):
            plano.update(val)
    return plano


def _reconstruir(raw: dict, plano_modificado: dict) -> dict:
    """
    Reconstruye el JSON con estructura por regiones a partir del dict plano
    modificado, conservando las claves de región originales.
    """
    reconstruido = {}
    for region, entries in raw.items():
        reconstruido[region] = {}
        for pk_id in entries:
            reconstruido[region][pk_id] = plano_modificado.get(pk_id, entries[pk_id])
    return reconstruido


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    if not POKEDEX_JSON.exists():
        print(f"❌ No se encontró {POKEDEX_JSON}")
        sys.exit(1)

    # 1. Backup
    shutil.copy(POKEDEX_JSON, BACKUP_PATH)
    print(f"✅ Backup creado en {BACKUP_PATH}")

    # 2. Cargar JSON
    with open(POKEDEX_JSON, encoding="utf-8") as f:
        raw = json.load(f)

    plano = _aplanar(raw)
    print(f"📦 {len(plano)} Pokémon cargados.")

    corregidos  = 0
    sin_cambios = 0
    errores     = 0

    # 3. Corregir stats de los 1025 Pokémon existentes
    print("\n🔧 Corrigiendo stats con datos de PokeAPI...")
    for pk_id, entry in plano.items():
        # Determinar el nombre/id a consultar en PokeAPI
        if pk_id in _FORMAS_ESPECIALES:
            api_key = _FORMAS_ESPECIALES[pk_id]
        else:
            api_key = pk_id  # PokeAPI acepta el ID numérico directamente

        stats_nuevas = _fetch_stats(api_key)
        if stats_nuevas is None:
            errores += 1
            continue

        stats_actuales = entry.get("stats_base", {})
        if stats_nuevas == stats_actuales:
            sin_cambios += 1
        else:
            plano[pk_id]["stats_base"] = stats_nuevas
            corregidos += 1
            print(
                f"  📝 ID {pk_id} {entry.get('nombre','?')}: "
                f"{stats_actuales} → {stats_nuevas}"
            )

        # Pausa breve para no saturar la API (60 req/min es el límite gratuito)
        time.sleep(0.05)

    print(f"\n📊 Resultados: {corregidos} corregidos | {sin_cambios} sin cambios | {errores} errores")

    # 4. Agregar formas nuevas (Calyrex-Shadow, Calyrex-Ice)
    print("\n➕ Agregando formas fusión faltantes...")
    for pk_id, meta in _NUEVAS_FORMAS.items():
        if pk_id in plano:
            print(f"  ℹ️  ID {pk_id} ({meta['nombre']}) ya existe — actualizando stats")
        else:
            print(f"  ✨ Agregando ID {pk_id}: {meta['nombre']}")

        stats_nuevas = _fetch_stats(_FORMAS_ESPECIALES[pk_id])
        if stats_nuevas is None:
            print(f"  ⚠️  No se pudieron obtener stats para {meta['nombre']} — se usarán valores de respaldo")
            # Valores de respaldo verificados manualmente
            stats_nuevas = (
                {"hp": 100, "atq": 85, "def": 80, "atq_sp": 165, "def_sp": 100, "vel": 150}
                if pk_id == "10195"
                else {"hp": 100, "atq": 165, "def": 150, "atq_sp": 85, "def_sp": 130, "vel": 50}
            )

        plano[pk_id] = {
            "nombre":        meta["nombre"],
            "tipos":         meta["tipos"],
            "stats_base":    stats_nuevas,
            "ratio_captura": meta["ratio_captura"],
            "habilidades":   meta["habilidades"],
            "sprite":        meta["sprite"],
        }

    # 5. Agregar las formas nuevas a la sección GALAR del JSON original
    #    (son Pokémon de Galar, forma lógica de ubicarlos)
    reconstruido = _reconstruir(raw, plano)
    for pk_id in _NUEVAS_FORMAS:
        if pk_id not in reconstruido.get("GALAR", {}):
            reconstruido["GALAR"][pk_id] = plano[pk_id]

    # 6. Guardar JSON actualizado
    with open(POKEDEX_JSON, "w", encoding="utf-8") as f:
        json.dump(reconstruido, f, ensure_ascii=False, indent=2)

    total_final = sum(len(v) for v in reconstruido.values())
    print(f"\n✅ pokedex.json actualizado. Total Pokémon: {total_final}")
    print("   (backup conservado en data/pokedex.json.backup)")


if __name__ == "__main__":
    main()
