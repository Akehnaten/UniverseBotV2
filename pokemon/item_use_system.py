# -*- coding: utf-8 -*-
"""
pokemon/item_use_system.py
══════════════════════════════════════════════════════════════════════════════
Sistema unificado de uso de ítems que requieren seleccionar un Pokémon.

Ítems gestionados aquí:
  · Medicinas / pociones / revivir → muestran selector de Pokémon del equipo
  · Piedras evolutivas
  · Cápsula Habilidad / Parche Habilidad
  · Mentas
  · Vitaminas / Sueros EV
  · Caramelos EXP / Caramelo Raro
  · Chapas (IVs)
  · Bayas de combate (equipar)

CORRECCIONES (2025-07):
  • Bug 3: pociones, super-pociones, hiper-pociones, poción máxima, restaurar
    todo, revivir, antídoto, despertar, antiquemar, antiparalizar, antihielo
    y cura total ahora muestran el selector de Pokémon en lugar de intentar
    consumirse sin objetivo.
  • Bug 2: beast ball y cualquier pokéball del inventario no lanzaban acción
    al usarse desde la mochila. Las pokéballs se usan SÓLO en combate; se
    muestra mensaje explicativo si se intentan usar fuera de él.

Flujo de callbacks:
  itemuse_sel_{uid}_{item}          → pantalla selector de Pokémon del equipo
  itemuse_apk_{uid}_{item}_{poke}   → aplicar ítem al Pokémon elegido

Importante: el ítem se consume ÚNICAMENTE si la aplicación fue exitosa.
══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
from typing import Optional

from telebot import types

logger = logging.getLogger(__name__)


def _get_item_data(item_nombre: str) -> dict:
    """
    Obtiene datos del ítem buscando en items_service (legacy, claves en
    español) y haciendo fallback a items_database_complete (claves en inglés).
    Siempre devuelve un dict, nunca None.
    """
    try:
        from pokemon.services import items_service as _its
        data = _its.obtener_item(item_nombre) or {}
    except Exception:
        data = {}
    if not data:
        try:
            from pokemon.items_database_complete import obtener_item_info
            data = obtener_item_info(item_nombre) or {}
        except Exception:
            data = {}
    return data


# ─────────────────────────────────────────────────────────────────────────────
# MAPEO: nombre interno del ítem → naturaleza destino
# ─────────────────────────────────────────────────────────────────────────────
MENTA_A_NATURALEZA: dict[str, str] = {
    # ── inglés ───────────────────────────────────────────────────────────────
    "timidmint":    "Timid",
    "modestmint":   "Modest",
    "adamantmint":  "Adamant",
    "boldmint":     "Bold",
    "jollymint":    "Jolly",
    "calmmint":     "Calm",
    "impíshmint":   "Impish",
    "impishmint":   "Impish",
    "carefulmint":  "Careful",
    "hastymint":    "Hasty",
    "naivemint":    "Naive",
    "relaxedmint":  "Relaxed",
    "quietmint":    "Quiet",
    "rashmint":     "Rash",
    "gentlemint":   "Gentle",
    "sassymint":    "Sassy",
    "bravemint":    "Brave",
    "lonelymint":   "Lonely",
    "naughtymint":  "Naughty",
    "laxmint":      "Lax",
    "mildmint":     "Mild",
    "seriousmint":  "Serious",
    "hardymint":    "Hardy",
    "bashfulmint":  "Bashful",
    "quirkymint":   "Quirky",
    "docilmint":    "Docile",
    # ── español ───────────────────────────────────────────────────────────────
    "menta_timida":    "Timid",
    "menta_modesta":   "Modest",
    "menta_adamante":  "Adamant",
    "menta_osada":     "Bold",
    "menta_alegre":    "Jolly",
    "menta_serena":    "Calm",
    "menta_impish":    "Impish",
    "menta_cuidadosa": "Careful",
    "menta_activa":    "Hasty",
    "menta_ingenua":   "Naive",
    "menta_relajada":  "Relaxed",
    "menta_quieta":    "Quiet",
    "menta_alocada":   "Rash",
    "menta_gentil":    "Gentle",
    "menta_grosera":   "Sassy",
    "menta_audaz":     "Brave",
    "menta_solitaria": "Lonely",
    "menta_pícara":    "Naughty",
    "menta_floja":     "Lax",
    "menta_suave":     "Mild",
    "menta_seria":     "Serious",
    "menta_resistente": "Hardy",
    "menta_docil":     "Docile",
    "menta_tmida":     "Timid",
}

_PIEDRA_EN_A_ES: dict[str, str] = {
    "firestone":        "piedra fuego",
    "waterstone":       "piedra agua",
    "thunderstone":     "piedra trueno",
    "leafstone":        "piedra hoja",
    "moonstone":        "piedra lunar",
    "sunstone":         "piedra solar",
    "shinystone":       "piedra brillante",
    "duskstone":        "piedra noche",
    "dawnstone":        "piedra alba",
    "icestone":         "piedra hielo",
    "ovalstone":        "piedra oval",
    "piedra fuego":     "piedra fuego",
    "piedra agua":      "piedra agua",
    "piedra trueno":    "piedra trueno",
    "piedra hoja":      "piedra hoja",
    "piedra lunar":     "piedra lunar",
    "piedra solar":     "piedra solar",
    "piedra brillante": "piedra brillante",
    "piedra noche":     "piedra noche",
    "piedra alba":      "piedra alba",
    "piedra hielo":     "piedra hielo",
    "piedra oval":      "piedra oval",
}

_PIEDRAS: frozenset = frozenset(_PIEDRA_EN_A_ES.keys())

_HABILIDAD_ITEMS = {"abilitycapsule", "abilitypatch"}

# ─────────────────────────────────────────────────────────────────────────────
# SET DE POKÉBALLS — se usan sólo en combate, nunca desde la mochila
# ─────────────────────────────────────────────────────────────────────────────
_POKEBALL_TIPOS: frozenset = frozenset({
    "pokeball", "greatball", "ultraball", "masterball",
    "premierball", "cherishball", "quickball", "timerball",
    "repeatball", "netball", "nestball", "diveball", "duskball",
    "luxuryball", "healball", "levelball", "lureball", "moonball",
    "friendball", "loveball", "heavyball", "fastball", "sportball",
    "safariball", "parkball", "dreamball", "beastball",
    # aliases en español
    "pokébola", "superbola", "ultrabola",
})


# ─────────────────────────────────────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────────────────────────────────────

def es_piedra_evolutiva(item_id: str) -> bool:
    return item_id.lower() in _PIEDRAS


def es_item_habilidad(item_id: str) -> bool:
    return item_id.lower() in _HABILIDAD_ITEMS


def es_menta(item_id: str) -> bool:
    key = item_id.lower().replace(" ", "_")
    return key in MENTA_A_NATURALEZA or item_id.lower() in MENTA_A_NATURALEZA


def es_pokeball(item_id: str) -> bool:
    """Devuelve True si el ítem es una Pokéball (tipo pokeball en BD)."""
    key = item_id.lower()
    if key in _POKEBALL_TIPOS:
        return True
    # Comprobar campo "tipo" en la base de datos
    data = _get_item_data(key)
    return data.get("tipo", "") == "pokeball"


_ITEMS_CON_SELECTOR = frozenset({
    "abilitycapsule", "abilitypatch", "bottlecap", "goldbottlecap",
    "expcandyxs", "expcandys", "expcandym", "expcandyl", "expcandyxl",
    "rarecandy",
})

# Claves que indican que el ítem cura/restaura a un Pokémon
_CLAVES_MEDICINA: frozenset = frozenset({
    "cura_hp", "revive", "revive_todos",
    "cura_estado", "cura_todos_estados",
    "pp", "pp_todos",
})


def necesita_selector_pokemon(item_id: str) -> bool:
    """
    Retorna True si usar este ítem requiere seleccionar un Pokémon del equipo.

    CORRECCIÓN Bug 3: se añaden las claves de medicina (cura_hp, revive, etc.)
    para que pociones y similares muestren el selector en lugar de consumirse
    sin objetivo.
    """
    key = item_id.lower()

    # Pokéballs → NO necesitan selector (sólo se usan en combate)
    if es_pokeball(key):
        return False

    if es_piedra_evolutiva(key) or es_item_habilidad(key) or es_menta(key):
        return True

    if key in _ITEMS_CON_SELECTOR:
        return True

    data = _get_item_data(key)

    # ── BUG 3 FIX: cualquier ítem con efecto de medicina necesita selector ──
    for clave_med in _CLAVES_MEDICINA:
        if clave_med in data:
            return True

    # Vitaminas y sueros EV
    if "ev" in data or "reduce_ev" in data:
        return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
# PASO 1 — MOSTRAR SELECTOR DE POKÉMON
# ─────────────────────────────────────────────────────────────────────────────

def mostrar_selector_pokemon(
    user_id: int,
    item_nombre: str,
    message,
    bot,
) -> None:
    """
    Presenta al usuario su equipo para que elija a qué Pokémon aplicar el ítem.
    Solo muestra Pokémon del equipo activo (en_equipo=1).
    Filtra candidatos según el tipo de ítem para mostrar sólo los relevantes.
    """
    from pokemon.services import pokemon_service
    from pokemon.services import items_service as _items

    # ── Bug 2 FIX: las Pokéballs se usan sólo en combate ─────────────────────
    if es_pokeball(item_nombre):
        _responder(
            message, bot, user_id,
            "⚾ <b>Las Pokéballs sólo pueden usarse durante un combate</b>.\n\n"
            "Entra en batalla contra un Pokémon salvaje para poder lanzarla.",
            _boton_volver_mochila(user_id),
        )
        return

    equipo = pokemon_service.obtener_equipo(user_id)
    if not equipo:
        _responder(message, bot, user_id,
                   "❌ No tienes Pokémon en tu equipo.",
                   _boton_volver_mochila(user_id))
        return

    item_data      = _items.obtener_item(item_nombre) or {}
    nombre_display = _nombre_display(item_nombre, item_data)

    # ── Filtrar candidatos según tipo de ítem ─────────────────────────────────
    if es_piedra_evolutiva(item_nombre):
        candidatos = _filtrar_compatibles_piedra(equipo, item_nombre)
        if not candidatos:
            _responder(
                message, bot, user_id,
                f"💎 <b>{nombre_display}</b>\n\n"
                "❌ Ningún Pokémon de tu equipo puede evolucionar con esta piedra.",
                _boton_volver_mochila(user_id),
            )
            return

    elif es_menta(item_nombre):
        naturaleza_destino = _naturaleza_de_menta(item_nombre)
        candidatos = [p for p in equipo if p.naturaleza != naturaleza_destino]
        if not candidatos:
            _responder(
                message, bot, user_id,
                f"🌿 <b>{nombre_display}</b>\n\n"
                f"❌ Todos tus Pokémon ya tienen la naturaleza <b>{naturaleza_destino}</b>.",
                _boton_volver_mochila(user_id),
            )
            return

    elif es_item_habilidad(item_nombre):
        candidatos = equipo

    # ── Revivir: sólo debilitados ─────────────────────────────────────────────
    elif "revive" in item_data or "revive_todos" in item_data:
        candidatos = [p for p in equipo if p.hp_actual <= 0]
        if not candidatos:
            _responder(message, bot, user_id,
                       "💊 Ningún Pokémon está debilitado.",
                       _boton_volver_mochila(user_id))
            return

    # ── Curar HP: sólo heridos y vivos ────────────────────────────────────────
    elif "cura_hp" in item_data:
        candidatos = [
            p for p in equipo
            if p.hp_actual > 0 and p.hp_actual < p.stats.get("hp", p.hp_actual + 1)
        ]
        if not candidatos:
            _responder(message, bot, user_id,
                       "💊 Todos los Pokémon ya tienen HP completo.",
                       _boton_volver_mochila(user_id))
            return

    # ── Curar estado: sólo vivos ──────────────────────────────────────────────
    elif "cura_estado" in item_data or "cura_todos_estados" in item_data:
        candidatos = [p for p in equipo if p.hp_actual > 0]

    elif _get_item_data(item_nombre).get("tipo") in ("baya_combate", "baya_mitigacion"):
        candidatos = equipo

    elif "ev" in _get_item_data(item_nombre) or "reduce_ev" in _get_item_data(item_nombre):
        candidatos = [p for p in equipo if p.hp_actual > 0]
        if not candidatos:
            _responder(message, bot, user_id,
                       "❌ Todos tus Pokémon están debilitados.",
                       _boton_volver_mochila(user_id))
            return

    else:
        candidatos = equipo

    # Encodificar item_nombre para callback (reemplazar espacios por ~)
    item_encoded = item_nombre.replace(" ", "~")

    texto = (
        f"🎒 <b>{nombre_display}</b>\n\n"
        f"{_descripcion_item(item_nombre, item_data)}\n\n"
        f"¿A qué Pokémon quieres usarlo?"
    )
    markup = types.InlineKeyboardMarkup(row_width=1)

    for poke in candidatos:
        nombre_poke = poke.mote or poke.nombre
        sexo_emoji  = {"M": " ♂", "F": " ♀"}.get(getattr(poke, "sexo", None) or "", "")
        shiny_emoji = " ✨" if getattr(poke, "shiny", False) else ""
        hab_info    = f"  [{poke.habilidad}]" if poke.habilidad else ""
        nat_info    = f"  ({poke.naturaleza})" if poke.naturaleza else ""
        hp_max      = poke.stats.get("hp", 1) or 1
        hp_txt      = f"  HP:{poke.hp_actual}/{hp_max}"
        label = (
            f"{nombre_poke}{sexo_emoji}{shiny_emoji} Nv.{poke.nivel}"
            f"{hp_txt}{nat_info}{hab_info}"
        )
        markup.add(types.InlineKeyboardButton(
            label,
            callback_data=f"itemuse_apk_{user_id}_{item_encoded}_{poke.id_unico}",
        ))

    markup.add(types.InlineKeyboardButton(
        "⬅️ Volver",
        callback_data=f"pokebag_item_{user_id}_{item_nombre}",
    ))
    _responder(message, bot, user_id, texto, markup)


# ─────────────────────────────────────────────────────────────────────────────
# PASO 2 — APLICAR ÍTEM AL POKÉMON ELEGIDO
# ─────────────────────────────────────────────────────────────────────────────

def aplicar_item_a_pokemon(
    user_id: int,
    item_nombre: str,
    pokemon_id: int,
    message,
    bot,
) -> None:
    """
    Aplica el efecto del ítem al Pokémon indicado y, solo si tiene éxito,
    consume una unidad del inventario del usuario.
    """
    from pokemon.services import items_service as _items
    from pokemon.services import pokemon_service

    # ── Bug 2 FIX: Pokéballs no se aplican desde mochila ─────────────────────
    if es_pokeball(item_nombre):
        _responder(
            message, bot, user_id,
            "⚾ <b>Las Pokéballs sólo pueden usarse durante un combate</b>.\n\n"
            "Entra en batalla contra un Pokémon salvaje para poder lanzarla.",
            _boton_volver_mochila(user_id),
        )
        return

    # ── Verificar stock ───────────────────────────────────────────────────────
    item_data  = _get_item_data(item_nombre)
    inventario = _items.obtener_inventario(user_id)
    if inventario.get(item_nombre, 0) < 1:
        _responder(message, bot, user_id,
                   f"❌ Ya no tienes <b>{_nombre_display(item_nombre, {})}</b> en la mochila.",
                   _boton_volver_mochila(user_id))
        return

    # ── Obtener Pokémon ───────────────────────────────────────────────────────
    poke = pokemon_service.obtener_pokemon(pokemon_id)
    if not poke or poke.usuario_id != user_id:
        _responder(message, bot, user_id,
                   "❌ Pokémon no encontrado.",
                   _boton_volver_mochila(user_id))
        return

    nombre_poke = poke.mote or poke.nombre

    # ── Enrutar al efecto correcto ────────────────────────────────────────────
    if es_piedra_evolutiva(item_nombre):
        _aplicar_piedra(user_id, item_nombre, poke, nombre_poke, message, bot, _items)

    elif item_nombre.lower() == "abilitypatch":
        _aplicar_parche_habilidad(user_id, item_nombre, poke, nombre_poke, message, bot, _items)

    elif item_nombre.lower() == "abilitycapsule":
        _aplicar_capsula_habilidad(user_id, item_nombre, poke, nombre_poke, message, bot, _items)

    elif es_menta(item_nombre):
        _aplicar_menta(user_id, item_nombre, poke, nombre_poke, message, bot, _items)

    elif any(k in item_data for k in ("cura_hp", "revive", "revive_todos",
                                       "cura_estado", "cura_todos_estados")):
        _aplicar_medicina_revivir(user_id, item_nombre, item_data, poke,
                                   nombre_poke, message, bot, _items)

    elif item_nombre.lower() in ("bottlecap", "goldbottlecap"):
        _aplicar_bottlecap(
            user_id, item_nombre, poke, nombre_poke, message, bot, _items,
            maximiza_todos=(item_nombre.lower() == "goldbottlecap"),
        )

    elif "ev" in item_data:
        _aplicar_vitamina(user_id, item_nombre, poke, nombre_poke, message, bot, _items)

    elif "exp" in item_data:
        _aplicar_caramelo_exp(user_id, item_nombre, poke, nombre_poke,
                               message, bot, _items)

    elif item_data.get("sube_nivel"):
        _aplicar_rarecandy(user_id, item_nombre, poke, nombre_poke,
                            message, bot, _items)

    elif item_data.get("tipo") in ("baya_combate", "baya_mitigacion"):
        _dar_baya_a_pokemon(user_id, item_nombre, poke, nombre_poke,
                             message, bot, _items)

    elif "reduce_ev" in item_data:
        _aplicar_suero_ev(user_id, item_nombre, poke, nombre_poke, message, bot, _items)

    else:
        _responder(message, bot, user_id,
                   f"❌ No se reconoce el efecto de <b>{item_nombre}</b>.",
                   _boton_volver_mochila(user_id))


# ─────────────────────────────────────────────────────────────────────────────
# EFECTOS INDIVIDUALES
# ─────────────────────────────────────────────────────────────────────────────

def _aplicar_suero_ev(user_id, item_nombre, poke, nombre_poke, message, bot, _items):
    """Suero reductor de EVs — baja EVs del stat correspondiente."""
    from database import db_manager

    item_data = _get_item_data(item_nombre)
    stat      = item_data.get("reduce_ev")
    cantidad  = int(item_data.get("cantidad", 10))

    if not stat:
        _responder(message, bot, user_id, "❌ Suero no reconocido.",
                   _boton_volver_mochila(user_id))
        return

    _COL = {
        "hp":     "ev_hp",
        "atq":    "ev_atq",
        "def":    "ev_def",
        "atq_sp": "ev_atq_sp",
        "def_sp": "ev_def_sp",
        "vel":    "ev_vel",
    }
    col_ev = _COL.get(stat)
    if not col_ev:
        _responder(message, bot, user_id, "❌ Stat de suero no reconocida.",
                   _boton_volver_mochila(user_id))
        return

    ev_actual = int(getattr(poke, col_ev, 0) or 0)

    if ev_actual <= 0:
        _responder(message, bot, user_id,
                   f"⚠️ <b>{nombre_poke}</b> ya tiene 0 EVs en <b>{stat.upper()}</b>.",
                   _boton_volver_mochila(user_id))
        return

    ev_nuevo  = max(0, ev_actual - cantidad)
    reducidos = ev_actual - ev_nuevo

    try:
        db_manager.execute_update(
            f"UPDATE POKEMON_USUARIO SET {col_ev} = ? WHERE id_unico = ?",
            (ev_nuevo, poke.id_unico),
        )
        from pokemon.experience_system import ExperienceSystem
        ExperienceSystem._recalcular_stats(poke.id_unico, poke.nivel)
    except Exception as exc:
        logger.error(f"[SUERO] Error: {exc}")
        _responder(message, bot, user_id, "❌ Error al aplicar el suero.",
                   _boton_volver_mochila(user_id))
        return

    _items.usar_item(user_id, item_nombre, 1)
    nombre_item = _nombre_display(item_nombre, item_data)
    texto = (
        f"🧪 <b>{nombre_item}</b> usado en <b>{nombre_poke}</b>.\n\n"
        f"-{reducidos} EV en <b>{stat.upper()}</b>  ({ev_actual} → {ev_nuevo}) ✅\n"
        f"<i>Stats recalculadas.</i>"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
    ))
    _responder(message, bot, user_id, texto, markup)


def _aplicar_piedra(user_id, item_nombre, poke, nombre_poke, message, bot, _items):
    """Intenta evolucionar al Pokémon con la piedra indicada."""
    from pokemon.services.evolucion_service import evolucion_service
    from database import db_manager

    piedra_interna = _PIEDRA_EN_A_ES.get(item_nombre.lower(), item_nombre.lower())

    especie_id   = str(poke.pokemonID)
    evoluciones  = evolucion_service.evoluciones.get(especie_id, [])
    evo_correcta = next(
        (e for e in evoluciones
         if e.get("metodo") == "piedra"
         and e.get("piedra", "").lower() == piedra_interna),
        None,
    )

    if not evo_correcta:
        _responder(
            message, bot, user_id,
            f"❌ Esta piedra no funciona con <b>{nombre_poke}</b>.",
            _boton_volver_mochila(user_id),
        )
        return

    exito, mensaje, _ = evolucion_service.evolucionar_pokemon(
        poke.id_unico,
        forzar=True,
        evo_data_override=evo_correcta,
    )

    if exito:
        _items.usar_item(user_id, item_nombre, 1)
        texto = (
            f"💎 ¡<b>{nombre_poke}</b> usó la piedra!\n\n"
            f"{mensaje}"
        )
    else:
        texto = (
            f"❌ La evolución falló.\n\n"
            f"<i>{mensaje}</i>"
        )

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
    ))
    _responder(message, bot, user_id, texto, markup)


def _aplicar_parche_habilidad(user_id, item_nombre, poke, nombre_poke, message, bot, _items):
    """Parche Habilidad: asigna la habilidad OCULTA del Pokémon."""
    from pokemon.services.pokedex_service import pokedex_service
    from database import db_manager

    habilidades = pokedex_service.obtener_habilidades(poke.pokemonID)

    if not habilidades or len(habilidades) < 2:
        _responder(message, bot, user_id,
                   f"❌ <b>{nombre_poke}</b> no tiene habilidad oculta disponible.",
                   _boton_volver_mochila(user_id))
        return

    hab_oculta = habilidades[-1]

    if poke.habilidad and poke.habilidad.lower() == hab_oculta.lower():
        _responder(message, bot, user_id,
                   f"⚠️ <b>{nombre_poke}</b> ya tiene su habilidad oculta "
                   f"<b>{poke.habilidad}</b>.",
                   _boton_volver_mochila(user_id))
        return

    hab_anterior = poke.habilidad or "desconocida"

    db_manager.execute_update(
        "UPDATE POKEMON_USUARIO SET habilidad = ? WHERE id_unico = ?",
        (hab_oculta, poke.id_unico),
    )

    _items.usar_item(user_id, item_nombre, 1)

    texto = (
        f"🩹 <b>Parche Habilidad</b> aplicado a <b>{nombre_poke}</b>.\n\n"
        f"Habilidad anterior: <s>{hab_anterior}</s>\n"
        f"Nueva habilidad:    <b>{hab_oculta}</b> ✨"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
    ))
    _responder(message, bot, user_id, texto, markup)


def _aplicar_capsula_habilidad(user_id, item_nombre, poke, nombre_poke, message, bot, _items):
    """Cápsula Habilidad: rota entre las habilidades NO ocultas del Pokémon."""
    from pokemon.services.pokedex_service import pokedex_service
    from database import db_manager
    import random

    habilidades = pokedex_service.obtener_habilidades(poke.pokemonID)

    if not habilidades:
        _responder(message, bot, user_id,
                   f"❌ No se encontraron habilidades para <b>{nombre_poke}</b>.",
                   _boton_volver_mochila(user_id))
        return

    habs_normales = habilidades[:-1] if len(habilidades) > 1 else habilidades
    hab_actual    = (poke.habilidad or "").lower()
    candidatas    = [h for h in habs_normales if h.lower() != hab_actual]

    if not candidatas:
        _responder(message, bot, user_id,
                   f"⚠️ <b>{nombre_poke}</b> no tiene otra habilidad disponible "
                   f"con la Cápsula Habilidad.\n\n"
                   f"<i>Para acceder a la habilidad oculta usa el Parche Habilidad.</i>",
                   _boton_volver_mochila(user_id))
        return

    nueva_hab    = random.choice(candidatas)
    hab_anterior = poke.habilidad or "desconocida"

    db_manager.execute_update(
        "UPDATE POKEMON_USUARIO SET habilidad = ? WHERE id_unico = ?",
        (nueva_hab, poke.id_unico),
    )

    _items.usar_item(user_id, item_nombre, 1)

    texto = (
        f"💊 <b>Cápsula Habilidad</b> aplicada a <b>{nombre_poke}</b>.\n\n"
        f"Habilidad anterior: <s>{hab_anterior}</s>\n"
        f"Nueva habilidad:    <b>{nueva_hab}</b> ✅"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
    ))
    _responder(message, bot, user_id, texto, markup)


def _aplicar_bottlecap(user_id, item_nombre, poke, nombre_poke,
                       message, bot, _items, *, maximiza_todos: bool):
    """Chapa Plateada (maximiza 1 IV) / Chapa Dorada (maximiza todos)."""
    from database import db_manager

    _COL = {
        "hp":     "iv_hp",
        "atq":    "iv_atq",
        "def":    "iv_def",
        "atq_sp": "iv_atq_sp",
        "def_sp": "iv_def_sp",
        "vel":    "iv_vel",
    }
    IVS = list(_COL.keys())

    ivs_actuales = {
        s: int(getattr(poke, _COL[s], 0) or 0) for s in IVS
    }

    if maximiza_todos:
        cambios = {s: 31 for s in IVS}
        desc = "todos los IVs a <b>31</b>"
    else:
        stat_baja = min(IVS, key=lambda s: ivs_actuales[s])
        cambios   = {stat_baja: 31}
        desc      = f"IV de <b>{stat_baja.upper()}</b> a <b>31</b>"

    try:
        set_clause = ", ".join(f"{_COL[s]} = ?" for s in cambios)
        valores    = tuple(cambios.values()) + (poke.id_unico,)
        db_manager.execute_update(
            f"UPDATE POKEMON_USUARIO SET {set_clause} WHERE id_unico = ?",
            valores,
        )
        from pokemon.experience_system import ExperienceSystem
        ExperienceSystem._recalcular_stats(poke.id_unico, poke.nivel)
    except Exception as exc:
        logger.error(f"[BOTTLECAP] Error: {exc}")
        _responder(message, bot, user_id, "❌ Error al aplicar la chapa.",
                   _boton_volver_mochila(user_id))
        return

    _items.usar_item(user_id, item_nombre, 1)
    nombre_item = _nombre_display(item_nombre, {})
    texto = (
        f"✨ <b>{nombre_item}</b> aplicada a <b>{nombre_poke}</b>.\n\n"
        f"Se maximizó {desc}.\n"
        f"<i>Stats recalculadas.</i>"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
    ))
    _responder(message, bot, user_id, texto, markup)


def _aplicar_vitamina(user_id, item_nombre, poke, nombre_poke, message, bot, _items):
    """Proteína, Hierro, Calcio, etc. — sube EVs del stat correspondiente."""
    from database import db_manager
    import json

    item_data = _get_item_data(item_nombre)
    stat      = item_data.get("ev")
    cantidad  = int(item_data.get("cantidad", 10))

    if not stat:
        _responder(message, bot, user_id, "❌ Vitamina no reconocida.",
                   _boton_volver_mochila(user_id))
        return

    evs_raw = getattr(poke, "evs", None) or {}
    if isinstance(evs_raw, str):
        evs_raw = json.loads(evs_raw)

    ev_actual = int(evs_raw.get(stat, 0))
    MAX_EV    = 252

    if ev_actual >= MAX_EV:
        _responder(message, bot, user_id,
                   f"⚠️ <b>{nombre_poke}</b> ya tiene el máximo de EVs en <b>{stat.upper()}</b>.",
                   _boton_volver_mochila(user_id))
        return

    ev_nuevo = min(MAX_EV, ev_actual + cantidad)
    ganados  = ev_nuevo - ev_actual
    evs_raw[stat] = ev_nuevo

    try:
        db_manager.execute_update(
            "UPDATE POKEMON_USUARIO SET evs = ? WHERE id_unico = ?",
            (json.dumps(evs_raw), poke.id_unico),
        )
        from pokemon.experience_system import ExperienceSystem
        ExperienceSystem._recalcular_stats(poke.id_unico, poke.nivel)
    except Exception as exc:
        logger.error(f"[VITAMINA] Error: {exc}")
        _responder(message, bot, user_id, "❌ Error al aplicar la vitamina.",
                   _boton_volver_mochila(user_id))
        return

    _items.usar_item(user_id, item_nombre, 1)
    nombre_item = _nombre_display(item_nombre, item_data)
    texto = (
        f"💊 <b>{nombre_item}</b> usada en <b>{nombre_poke}</b>.\n\n"
        f"+{ganados} EV en <b>{stat.upper()}</b>  ({ev_actual} → {ev_nuevo}/252) ✅\n"
        f"<i>Stats recalculadas.</i>"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
    ))
    _responder(message, bot, user_id, texto, markup)


def _aplicar_menta(user_id, item_nombre, poke, nombre_poke, message, bot, _items):
    """Menta: cambia la naturaleza del Pokémon."""
    from database import db_manager
    from pokemon.experience_system import ExperienceSystem

    naturaleza_nueva = _naturaleza_de_menta(item_nombre)
    if not naturaleza_nueva:
        _responder(message, bot, user_id,
                   f"❌ No se reconoce la menta <b>{item_nombre}</b>.",
                   _boton_volver_mochila(user_id))
        return

    naturaleza_anterior = poke.naturaleza or "Hardy"

    if naturaleza_anterior == naturaleza_nueva:
        _responder(message, bot, user_id,
                   f"⚠️ <b>{nombre_poke}</b> ya tiene naturaleza <b>{naturaleza_nueva}</b>.",
                   _boton_volver_mochila(user_id))
        return

    db_manager.execute_update(
        "UPDATE POKEMON_USUARIO SET naturaleza = ? WHERE id_unico = ?",
        (naturaleza_nueva, poke.id_unico),
    )

    try:
        ExperienceSystem._recalcular_stats(poke.id_unico, poke.nivel)
    except Exception as exc:
        logger.warning(f"[MENTA] No se pudieron recalcular stats: {exc}")

    _items.usar_item(user_id, item_nombre, 1)

    nombre_item_display = _nombre_display(item_nombre, {})
    texto = (
        f"🌿 <b>{nombre_item_display}</b> usada en <b>{nombre_poke}</b>.\n\n"
        f"Naturaleza anterior: <s>{naturaleza_anterior}</s>\n"
        f"Nueva naturaleza:    <b>{naturaleza_nueva}</b> 🌟\n\n"
        f"<i>Las stats han sido recalculadas.</i>"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
    ))
    _responder(message, bot, user_id, texto, markup)


def _aplicar_medicina_revivir(user_id, item_nombre, item_data, poke,
                               nombre_poke, message, bot, _items):
    """
    Aplica pociones, revivir y cura-estado al Pokémon elegido.

    Cubre (Bug 3 FIX):
      • cura_hp    → pociones de todos los tipos
      • revive     → revivir / revivir max
      • cura_estado / cura_todos_estados → antídotos, cura total, etc.
    """
    from database import db_manager
    efectos = []

    # ── Revivir ───────────────────────────────────────────────────────────────
    if "revive" in item_data:
        if poke.hp_actual > 0:
            _responder(message, bot, user_id,
                       f"❌ <b>{nombre_poke}</b> no está debilitado.",
                       _boton_volver_mochila(user_id))
            return
        hp_max   = poke.stats.get("hp", 100)
        ratio    = item_data["revive"]
        nuevo_hp = max(1, int(hp_max * ratio))
        db_manager.execute_update(
            "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
            (nuevo_hp, poke.id_unico),
        )
        efectos.append(f"revivió con {nuevo_hp} HP")

    # ── Revivir a todos (ceniza sagrada, etc.) ────────────────────────────────
    elif "revive_todos" in item_data:
        from pokemon.services import pokemon_service
        equipo_completo = pokemon_service.obtener_equipo(user_id)
        revividos = 0
        for p in equipo_completo:
            if p.hp_actual <= 0:
                hp_max = p.stats.get("hp", 100)
                db_manager.execute_update(
                    "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                    (hp_max, p.id_unico),
                )
                revividos += 1
        efectos.append(f"todo el equipo fue revivido ({revividos} Pokémon)")

    # ── Curar HP ──────────────────────────────────────────────────────────────
    elif "cura_hp" in item_data:
        if poke.hp_actual <= 0:
            _responder(message, bot, user_id,
                       f"❌ <b>{nombre_poke}</b> está debilitado. Usa Revivir primero.",
                       _boton_volver_mochila(user_id))
            return
        hp_max   = poke.stats.get("hp", 100)
        if poke.hp_actual >= hp_max:
            _responder(message, bot, user_id,
                       f"⚠️ <b>{nombre_poke}</b> ya tiene HP completo.",
                       _boton_volver_mochila(user_id))
            return
        cura_raw = item_data["cura_hp"]
        # Valor entero = HP fijo; float ≤ 1.0 = porcentaje del máximo
        if isinstance(cura_raw, float) and cura_raw <= 1.0:
            cura = int(hp_max * cura_raw)
        else:
            cura = int(cura_raw)
        curar    = min(cura, hp_max - poke.hp_actual)
        nuevo_hp = poke.hp_actual + curar
        db_manager.execute_update(
            "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
            (nuevo_hp, poke.id_unico),
        )
        efectos.append(f"recuperó {curar} HP ({poke.hp_actual} → {nuevo_hp})")

    # ── Curar estado (antídoto, antiquemar, etc.) ─────────────────────────────
    if "cura_estado" in item_data or "cura_todos_estados" in item_data:
        db_manager.execute_update(
            "UPDATE POKEMON_USUARIO SET estado = NULL WHERE id_unico = ?",
            (poke.id_unico,),
        )
        efectos.append("curó su estado")

    if not efectos:
        _responder(message, bot, user_id, "❌ El ítem no tuvo efecto.",
                   _boton_volver_mochila(user_id))
        return

    _items.usar_item(user_id, item_nombre, 1)

    nombre_item = _nombre_display(item_nombre, item_data)
    texto  = f"💊 <b>{nombre_item}</b> usada en <b>{nombre_poke}</b>.\n\n"
    texto += "\n".join(f"✅ {e}" for e in efectos)

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
    ))
    _responder(message, bot, user_id, texto, markup)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS INTERNOS
# ─────────────────────────────────────────────────────────────────────────────

def _naturaleza_de_menta(item_id: str) -> Optional[str]:
    key = item_id.lower().replace(" ", "_")
    return MENTA_A_NATURALEZA.get(key) or MENTA_A_NATURALEZA.get(item_id.lower())


def _filtrar_compatibles_piedra(equipo: list, piedra_nombre: str) -> list:
    from pokemon.services.evolucion_service import evolucion_service
    nombre_piedra_es = _PIEDRA_EN_A_ES.get(piedra_nombre.lower(), piedra_nombre)
    aliases = {nombre_piedra_es.lower()}
    alias_sin_espacio = nombre_piedra_es.lower().replace(" ", "")
    alias_guion = nombre_piedra_es.lower().replace(" ", "-")
    aliases.update([
        alias_sin_espacio, alias_guion,
        piedra_nombre.lower(),
        "stone " + piedra_nombre.lower().replace("stone", "").strip(),
    ])

    candidatos = []
    for poke in equipo:
        if poke.hp_actual <= 0:
            continue
        especie_id = str(poke.pokemonID)
        evos = evolucion_service.evoluciones.get(especie_id, [])
        for evo in evos:
            if evo.get("metodo", "").lower() != "piedra":
                continue
            piedra_requerida = evo.get("piedra", "").lower()
            if piedra_requerida in aliases or any(a in piedra_requerida for a in aliases):
                candidatos.append(poke)
                break
    return candidatos


def _nombre_display(item_id: str, item_data: dict) -> str:
    if item_data:
        for key in ("nombre", "name", "nombre_es"):
            val = item_data.get(key)
            if val:
                return str(val)
    return item_id.replace("_", " ").title()


def _descripcion_item(item_id: str, item_data: dict) -> str:
    if item_data:
        desc = item_data.get("desc") or item_data.get("descripcion")
        if desc:
            return f"<i>{desc}</i>"
    return ""


def _boton_volver_mochila(user_id: int) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
    ))
    return markup


def _responder(message, bot, user_id: int, texto: str, markup) -> None:
    """Edita el mensaje existente o envía uno nuevo si no se puede editar."""
    if getattr(message, "content_type", None) in ("photo", "animation", "document", "video"):
        try:
            bot.edit_message_caption(
                caption=texto,
                chat_id=message.chat.id,
                message_id=message.message_id,
                parse_mode="HTML",
                reply_markup=markup,
            )
            return
        except Exception:
            pass

    try:
        bot.edit_message_text(
            texto,
            chat_id=message.chat.id,
            message_id=message.message_id,
            parse_mode="HTML",
            reply_markup=markup,
        )
    except Exception:
        try:
            bot.send_message(user_id, texto, parse_mode="HTML", reply_markup=markup)
        except Exception as exc:
            logger.error(f"[ITEM_USE] Error enviando respuesta: {exc}")


def _aplicar_caramelo_exp(user_id, item_nombre, poke, nombre_poke,
                           message, bot, _items):
    """Caramelo Exp XS/S/M/L/XL — otorga EXP directamente al Pokémon."""
    from pokemon.experience_system import ExperienceSystem
    from pokemon.level_up_handler import LevelUpHandler

    item_data   = _items.obtener_item(item_nombre) or {}
    exp_otorgar = int(item_data.get("exp", 0))

    if poke.nivel >= 100:
        _responder(message, bot, user_id,
                   f"⚠️ <b>{nombre_poke}</b> ya está en el nivel máximo.",
                   _boton_volver_mochila(user_id))
        return

    resultado = ExperienceSystem.aplicar_experiencia(poke.id_unico, exp_otorgar)
    _items.usar_item(user_id, item_nombre, 1)

    nombre_item = _nombre_display(item_nombre, item_data)
    nivel_nuevo = resultado.get("nivel_nuevo", poke.nivel)
    texto = (
        f"🍬 <b>{nombre_item}</b> usado en <b>{nombre_poke}</b>.\n\n"
        f"+<b>{exp_otorgar:,}</b> EXP ✨\n"
    )
    if resultado.get("subio_nivel"):
        texto += f"🎉 ¡Subió al nivel <b>{nivel_nuevo}</b>!\n"

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
    ))
    _responder(message, bot, user_id, texto, markup)

    if resultado.get("subio_nivel"):
        try:
            LevelUpHandler.procesar_subida(
                bot=bot, user_id=user_id,
                pokemon_id=poke.id_unico,
                exp_result=resultado,
                delay=1.5,
            )
        except Exception as exc:
            logger.warning(f"[EXP_CANDY] LevelUpHandler error: {exc}")


def _aplicar_rarecandy(user_id, item_nombre, poke, nombre_poke,
                        message, bot, _items):
    """Caramelo Raro — sube 1 nivel al Pokémon."""
    from pokemon.experience_system import ExperienceSystem
    from pokemon.level_up_handler import LevelUpHandler

    if poke.nivel >= 100:
        _responder(message, bot, user_id,
                   f"⚠️ <b>{nombre_poke}</b> ya está en el nivel máximo.",
                   _boton_volver_mochila(user_id))
        return

    exp_necesaria = ExperienceSystem.exp_necesaria_para_nivel(poke.nivel)
    exp_faltante  = exp_necesaria - poke.exp if hasattr(poke, "exp") else exp_necesaria
    resultado     = ExperienceSystem.aplicar_experiencia(poke.id_unico, max(1, exp_faltante))
    _items.usar_item(user_id, item_nombre, 1)

    nivel_nuevo = resultado.get("nivel_nuevo", poke.nivel + 1)
    texto = (
        f"🍬 <b>Caramelo Raro</b> usado en <b>{nombre_poke}</b>.\n\n"
        f"🎉 ¡Subió al nivel <b>{nivel_nuevo}</b>!\n"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
    ))
    _responder(message, bot, user_id, texto, markup)

    if resultado.get("subio_nivel"):
        try:
            LevelUpHandler.procesar_subida(
                bot=bot, user_id=user_id,
                pokemon_id=poke.id_unico,
                exp_result=resultado,
                delay=1.5,
            )
        except Exception as exc:
            logger.warning(f"[RARECANDY] LevelUpHandler error: {exc}")


def _dar_baya_a_pokemon(user_id, item_nombre, poke, nombre_poke,
                         message, bot, _items):
    """Bayas de combate/mitigación: se equipan al Pokémon como objeto."""
    from database import db_manager

    objeto_previo = getattr(poke, "objeto", None)
    if objeto_previo:
        _items.agregar_item(user_id, objeto_previo, 1)

    _items.usar_item(user_id, item_nombre, 1)
    db_manager.execute_update(
        "UPDATE POKEMON_USUARIO SET objeto = ? WHERE id_unico = ?",
        (item_nombre, poke.id_unico),
    )

    nombre_baya = _nombre_display(item_nombre, _items.obtener_item(item_nombre) or {})
    item_data   = _items.obtener_item(item_nombre) or {}
    texto = (
        f"🍓 <b>{nombre_baya}</b> dada a <b>{nombre_poke}</b>.\n\n"
        f"<i>{item_data.get('desc', '')}</i>\n\n"
        "La baya se consumirá automáticamente en combate."
    )
    if objeto_previo:
        texto += f"\n\n📦 <b>{objeto_previo.replace('_',' ').title()}</b> devuelta a la mochila."

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
    ))
    _responder(message, bot, user_id, texto, markup)


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRO DE CALLBACKS
# ─────────────────────────────────────────────────────────────────────────────

def register_item_use_callbacks(bot) -> None:
    """
    Registra los handlers de callback para el flujo de uso de ítems.
    Llamar desde UniverseBot.py tras inicializar el bot.

    Callbacks manejados:
      itemuse_sel_{uid}_{item}          → mostrar selector de Pokémon
      itemuse_apk_{uid}_{item}_{poke}   → aplicar ítem
    """

    @bot.callback_query_handler(func=lambda c: c.data is not None and c.data.startswith("itemuse_sel_"))
    def _cb_selector(call: types.CallbackQuery):
        """Formato: itemuse_sel_{user_id}_{item_encoded}"""
        # Verificación extra de seguridad dentro de la función
        if not call.data:
            return

        try:
            partes = call.data.split("_", 3)
            if len(partes) < 4:
                bot.answer_callback_query(call.id, "❌ Datos inválidos.", show_alert=True)
                return

            user_id      = int(partes[2])
            item_encoded = partes[3]
            item_nombre  = item_encoded.replace("~", " ")

            if call.from_user.id != user_id:
                bot.answer_callback_query(call.id, "❌ Este menú no es tuyo.", show_alert=True)
                return

            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass

            mostrar_selector_pokemon(user_id, item_nombre, call.message, bot)

        except Exception as exc:
            logger.error(f"[ITEM_USE] Error en _cb_selector: {exc}", exc_info=True)
            try:
                bot.answer_callback_query(call.id, "❌ Error interno.", show_alert=True)
            except Exception:
                pass

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("itemuse_apk_"))
    def _cb_aplicar(call: types.CallbackQuery):
        # 1. Verificación de seguridad para evitar el error "None"
        if not call.data:
            return

        try:
            # Dividimos en 4 partes máximo
            partes = call.data.split("_", 3)
            
            if len(partes) < 4:
                bot.answer_callback_query(call.id, "❌ Datos incompletos.", show_alert=True)
                return

            # partes[2] es el user_id según tu formato
            user_id = int(partes[2])
            resto = partes[3]

            # Buscamos el último guion para separar item de pokemon_id
            ultimo_sep = resto.rfind("_")
            if ultimo_sep == -1:
                bot.answer_callback_query(call.id, "❌ Formato de datos erróneo.", show_alert=True)
                return

            item_encoded = resto[:ultimo_sep]
            pokemon_id = int(resto[ultimo_sep + 1:])
            item_nombre = item_encoded.replace("~", " ")

            # 2. Validación de dueño del menú
            if call.from_user.id != user_id:
                bot.answer_callback_query(call.id, "❌ Este menú no es tuyo.", show_alert=True)
                return

            # 3. Responder al callback para quitar el reloj de arena
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass

            aplicar_item_a_pokemon(user_id, item_nombre, pokemon_id, call.message, bot)

        except Exception as exc:
            logger.error(f"[ITEM_USE] Error en _cb_aplicar: {exc}", exc_info=True)
            try:
                bot.answer_callback_query(call.id, "❌ Error al procesar el item.", show_alert=True)
            except Exception:
                pass

    logger.info("[ITEM_USE] Callbacks de uso de ítems registrados.")