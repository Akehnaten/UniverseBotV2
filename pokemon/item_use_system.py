# -*- coding: utf-8 -*-
"""
pokemon/item_use_system.py
══════════════════════════════════════════════════════════════════════════════
Sistema unificado de uso de ítems que requieren seleccionar un Pokémon.

Ítems gestionados aquí:
  · Piedras evolutivas  → firestone, waterstone, thunderstone, leafstone,
                          moonstone, sunstone, shinystone, duskstone,
                          dawnstone, icestone, ovalstone   (+ aliases en español)
  · Cápsula Habilidad   → abilitycapsule  (cambia a otra habilidad NO oculta)
  · Parche Habilidad    → abilitypatch    (cambia a la habilidad OCULTA)
  · Mentas              → timidmint, modestmint, adamantmint, boldmint,
                          jollyмint, calmмint, impishмint, carefulмint,
                          hastymint, naivemint, relaxedmint, quietmint,
                          rashмint, gentlemint, sassymint, braveмint,
                          lonelymint, naughtymint, laxmint, mildmint
                          (también variantes en español: menta_timida, etc.)

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
# Soporta tanto claves en inglés (items_database_complete) como español
# (items_service legacy).
# ─────────────────────────────────────────────────────────────────────────────
MENTA_A_NATURALEZA: dict[str, str] = {
    # ── inglés (claves de items_database_complete) ───────────────────────────
    "timidmint":    "Timid",
    "modestmint":   "Modest",
    "adamantmint":  "Adamant",
    "boldmint":     "Bold",
    "jollymint":    "Jolly",
    "calmmint":     "Calm",
    "impishмint":   "Impish",    # обратите внимание: la м es cirílica en algunos nombres
    "impíshmint":   "Impish",
    "impishmint":   "Impish",
    "carefulмint":  "Careful",
    "carefulмint":  "Careful",
    "carefulмint":  "Careful",
    "carefulмint":  "Careful",
    "carefulмint":  "Careful",
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
    "docilемint":   "Docile",
    "basiliskmint": "Bashful",   # bashful
    "bashfulmint":  "Bashful",
    "quirkyмint":   "Quirky",
    "quirkymint":   "Quirky",
    # ── español (items_service legacy) ───────────────────────────────────────
    "menta_timida":   "Timid",
    "menta_modesta":  "Modest",
    "menta_adamante": "Adamant",
    "menta_osada":    "Bold",
    "menta_alegre":   "Jolly",
    "menta_serena":   "Calm",
    "menta_impish":   "Impish",
    "menta_cuidadosa":"Careful",
    "menta_activa":   "Hasty",
    "menta_ingenua":  "Naive",
    "menta_relajada": "Relaxed",
    "menta_quieta":   "Quiet",
    "menta_alocada":  "Rash",
    "menta_gentil":   "Gentle",
    "menta_grosera":  "Sassy",
    "menta_audaz":    "Brave",
    "menta_solitaria":"Lonely",
    "menta_pícara":   "Naughty",
    "menta_floja":    "Lax",
    "menta_suave":    "Mild",
    "menta_seria":    "Serious",
    "menta_resistente":"Hardy",
    "menta_docil":    "Docile",
    "menta_tmida":    "Timid",
}

# Traducción: clave inglesa (items_database_complete) → nombre en español
# que usa evolucion_service en el campo "piedra" de su tabla de evoluciones.
_PIEDRA_EN_A_ES: dict[str, str] = {
    "firestone":    "piedra fuego",
    "waterstone":   "piedra agua",
    "thunderstone": "piedra trueno",
    "leafstone":    "piedra hoja",
    "moonstone":    "piedra lunar",
    "sunstone":     "piedra solar",
    "shinystone":   "piedra brillante",   # también "piedra dia" en algunos registros
    "duskstone":    "piedra noche",
    "dawnstone":    "piedra alba",
    "icestone":     "piedra hielo",
    "ovalstone":    "piedra oval",
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

# Piedras evolutivas — claves reconocidas (inglés y español legacy)
# REEMPLAZAR la definición de _PIEDRAS:
_PIEDRAS: frozenset = frozenset(_PIEDRA_EN_A_ES.keys())

# Ítems de habilidad
_HABILIDAD_ITEMS = {"abilitycapsule", "abilitypatch"}


# ─────────────────────────────────────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────────────────────────────────────

def es_piedra_evolutiva(item_id: str) -> bool:
    """Devuelve True si el ítem es una piedra evolutiva conocida."""
    return item_id.lower() in _PIEDRAS


def es_item_habilidad(item_id: str) -> bool:
    """Devuelve True si el ítem afecta la habilidad del Pokémon."""
    return item_id.lower() in _HABILIDAD_ITEMS


def es_menta(item_id: str) -> bool:
    """Devuelve True si el ítem es una menta (cambia naturaleza)."""
    key = item_id.lower().replace(" ", "_")
    return key in MENTA_A_NATURALEZA or item_id.lower() in MENTA_A_NATURALEZA


_ITEMS_CON_SELECTOR = frozenset({
    "abilitycapsule", "abilitypatch", "bottlecap", "goldbottlecap",
    # Caramelos EXP y rarecandy
    "expcandyxs", "expcandys", "expcandym", "expcandyl", "expcandyxl",
    "rarecandy",
})

def necesita_selector_pokemon(item_id: str) -> bool:
    key = item_id.lower()
    if es_piedra_evolutiva(key) or es_item_habilidad(key) or es_menta(key):
        return True
    if key in _ITEMS_CON_SELECTOR:
        return True
    # Vitaminas: cualquier item con campo "ev" en su data
    data = _get_item_data(key)
    return "ev" in data or "reduce_ev" in data


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
    Para piedras evolutivas, filtra adicionalmente los Pokémon compatibles.
    """
    from pokemon.services import pokemon_service
    from pokemon.services import items_service as _items

    equipo = pokemon_service.obtener_equipo(user_id)
    if not equipo:
        _responder(message, bot, user_id,
                   "❌ No tienes Pokémon en tu equipo.",
                   _boton_volver_mochila(user_id))
        return

    item_data     = _items.obtener_item(item_nombre) or {}
    nombre_display = _nombre_display(item_nombre, item_data)

    # Para piedras, filtrar solo Pokémon que pueden evolucionar con esa piedra
    if es_piedra_evolutiva(item_nombre):
        candidatos = _filtrar_compatibles_piedra(equipo, item_nombre)
        if not candidatos:
            _responder(
                message, bot, user_id,
                f"💎 <b>{nombre_display}</b>\n\n"
                f"❌ Ningún Pokémon de tu equipo puede evolucionar con esta piedra.",
                _boton_volver_mochila(user_id),
            )
            return
    elif es_menta(item_nombre):
        # Excluir Pokémon que ya tienen esa naturaleza
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
        candidatos = equipo  # cualquier Pokémon del equipo
    elif "revive" in item_data:
        candidatos = [p for p in equipo if p.hp_actual <= 0]
        if not candidatos:
            _responder(message, bot, user_id,
                       "💊 Ningún Pokémon está debilitado.",
                       _boton_volver_mochila(user_id))
            return
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
    elif "cura_estado" in item_data or "cura_todos_estados" in item_data:
        candidatos = [p for p in equipo if p.hp_actual > 0]
    elif _get_item_data(item_nombre).get("tipo") in ("baya_combate", "baya_mitigacion"):
        candidatos = equipo
    elif "ev" in _get_item_data(item_nombre) or "reduce_ev" in _get_item_data(item_nombre):
        # Vitaminas y sueros: solo Pokémon vivos
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
        label = (
            f"{nombre_poke}{sexo_emoji}{shiny_emoji} Nv.{poke.nivel}"
            f"{nat_info}{hab_info}"
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

    # ── Verificar stock ───────────────────────────────────────────────────────
    item_data = _get_item_data(item_nombre)   # usa fallback a items_database_complete
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

    elif any(k in item_data for k in ("cura_hp", "revive", "cura_estado", "cura_todos_estados")):
        _aplicar_medicina_revivir(user_id, item_nombre, item_data, poke, nombre_poke, message, bot, _items)

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
        # Bayas: se dan al Pokémon para usar en combate automáticamente
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

    # La BD almacena EVs en columnas individuales: ev_hp, ev_atq, etc.
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
    """
    Intenta evolucionar al Pokémon con la piedra indicada.

    El inventario puede tener claves en inglés ('firestone') mientras que
    evolucion_service usa claves en español ('piedra fuego').  Esta función:
      1. Traduce la clave al nombre interno de evolucion_service.
      2. Verifica la compatibilidad y ejecuta la evolución directamente
         (sin delegar el consumo a usar_piedra_evolutiva para evitar
         que intente consumir una clave que no existe en el inventario).
      3. Consume el ítem del inventario original SOLO si la evolución tuvo éxito.
    """
    from pokemon.services.evolucion_service import evolucion_service
    from database import db_manager

    # Normalizar nombre a la clave interna de evolucion_service
    piedra_interna = _PIEDRA_EN_A_ES.get(item_nombre.lower(), item_nombre.lower())

    # Verificar compatibilidad manualmente para evitar el ciclo consumo↔devolución
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

    # Ejecutar evolución (forzada, ya verificamos la piedra)
    exito, mensaje, _ = evolucion_service.evolucionar_pokemon(
        poke.id_unico,
        forzar=True,
        evo_data_override=evo_correcta,   # ← CRÍTICO para Eevee y cualquier
    )

    if exito:
        # Consumir el ítem con la clave ORIGINAL del inventario
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
    """
    Parche Habilidad: asigna la habilidad OCULTA del Pokémon.
    Si ya tiene la oculta, informa que no es necesario.
    Consume el ítem si se aplicó correctamente.
    """
    from pokemon.services.pokedex_service import pokedex_service
    from database import db_manager

    habilidades = pokedex_service.obtener_habilidades(poke.pokemonID)

    # La convención del proyecto: última de la lista = oculta
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

    # Aplicar en BD
    db_manager.execute_update(
        "UPDATE POKEMON_USUARIO SET habilidad = ? WHERE id_unico = ?",
        (hab_oculta, poke.id_unico),
    )

    # Consumir ítem
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
    """
    Cápsula Habilidad: rota entre las habilidades NO ocultas del Pokémon,
    eligiendo una distinta a la actual.
    Consume el ítem si se aplicó correctamente.
    """
    from pokemon.services.pokedex_service import pokedex_service
    from database import db_manager
    import random

    habilidades = pokedex_service.obtener_habilidades(poke.pokemonID)

    if not habilidades:
        _responder(message, bot, user_id,
                   f"❌ No se encontraron habilidades para <b>{nombre_poke}</b>.",
                   _boton_volver_mochila(user_id))
        return

    # Habilidades normales = todas menos la última (oculta)
    # Si solo hay 1 habilidad, no hay nada que cambiar
    habs_normales = habilidades[:-1] if len(habilidades) > 1 else habilidades

    # Filtrar habilidades distintas a la actual
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

    # Aplicar en BD
    db_manager.execute_update(
        "UPDATE POKEMON_USUARIO SET habilidad = ? WHERE id_unico = ?",
        (nueva_hab, poke.id_unico),
    )

    # Consumir ítem
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

    # La BD almacena IVs en columnas individuales: iv_hp, iv_atq, etc.
    _COL = {
        "hp":     "iv_hp",
        "atq":    "iv_atq",
        "def":    "iv_def",
        "atq_sp": "iv_atq_sp",
        "def_sp": "iv_def_sp",
        "vel":    "iv_vel",
    }
    IVS = list(_COL.keys())

    # Leer IVs actuales directamente de las columnas
    ivs_actuales = {
        s: int(getattr(poke, _COL[s], 0) or 0) for s in IVS
    }

    if maximiza_todos:
        cambios = {s: 31 for s in IVS}
        desc = "todos los IVs a <b>31</b>"
    else:
        # Maximizar el IV más bajo
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
    """
    Menta: cambia la naturaleza del Pokémon a la correspondiente.
    Recalcula las stats en la BD.
    Consume el ítem si se aplicó correctamente.
    """
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

    # Actualizar naturaleza en BD
    db_manager.execute_update(
        "UPDATE POKEMON_USUARIO SET naturaleza = ? WHERE id_unico = ?",
        (naturaleza_nueva, poke.id_unico),
    )

    # Recalcular stats con la nueva naturaleza
    try:
        ExperienceSystem._recalcular_stats(poke.id_unico, poke.nivel)
    except Exception as exc:
        logger.warning(f"[MENTA] No se pudieron recalcular stats: {exc}")

    # Consumir ítem
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

def _aplicar_medicina_revivir(user_id, item_nombre, item_data, poke, nombre_poke, message, bot, _items):
    """Aplica pociones, revivir y cura-estado al Pokémon elegido."""
    from database import db_manager
    efectos = []

    if "revive" in item_data:
        if poke.hp_actual > 0:
            _responder(message, bot, user_id,
                       f"❌ <b>{nombre_poke}</b> no está debilitado.",
                       _boton_volver_mochila(user_id))
            return
        hp_max   = poke.stats.get("hp", 100)
        nuevo_hp = max(1, int(hp_max * item_data["revive"]))
        db_manager.execute_update(
            "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
            (nuevo_hp, poke.id_unico),
        )
        efectos.append(f"revivió con {nuevo_hp} HP")

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
        curar    = min(int(item_data["cura_hp"]), hp_max - poke.hp_actual)
        nuevo_hp = poke.hp_actual + curar
        db_manager.execute_update(
            "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
            (nuevo_hp, poke.id_unico),
        )
        efectos.append(f"recuperó {curar} HP")

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

    texto  = f"💊 <b>{nombre_poke}</b> {', '.join(efectos)}! ✅"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
    ))
    _responder(message, bot, user_id, texto, markup)

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS INTERNOS
# ─────────────────────────────────────────────────────────────────────────────

def _naturaleza_de_menta(item_id: str) -> Optional[str]:
    """Devuelve la naturaleza asociada a una menta, o None si no se reconoce."""
    key = item_id.lower().replace(" ", "_")
    return MENTA_A_NATURALEZA.get(key) or MENTA_A_NATURALEZA.get(item_id.lower())

def _filtrar_compatibles_piedra(equipo: list, piedra_nombre: str) -> list:
    """Filtra Pokémon que pueden evolucionar con la piedra dada."""
    from pokemon.services.evolucion_service import evolucion_service
    # Traducir clave inglesa → nombre español de la piedra
    nombre_piedra_es = _PIEDRA_EN_A_ES.get(piedra_nombre.lower(), piedra_nombre)
    # Alias adicionales por si el metodo usa variantes
    aliases = {nombre_piedra_es.lower()}
    # Algunos registros almacenan "Piedra Fuego" otros "piedrafuego" etc.
    alias_sin_espacio = nombre_piedra_es.lower().replace(" ", "")
    alias_guion = nombre_piedra_es.lower().replace(" ", "-")
    aliases.update([alias_sin_espacio, alias_guion,
                    piedra_nombre.lower(), "stone " + piedra_nombre.lower().replace("stone","").strip()])

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
    """Nombre legible del ítem."""
    if item_data:
        for key in ("nombre", "name", "nombre_es"):
            val = item_data.get(key)
            if val:
                return str(val)
    return item_id.replace("_", " ").title()


def _descripcion_item(item_id: str, item_data: dict) -> str:
    """Descripción corta del ítem."""
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
    """Edita el mensaje existente o envía uno nuevo si no se puede editar.
    Maneja correctamente mensajes con foto/animación (edita caption).
    """
    # Mensajes con adjunto: intentar editar el caption primero
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

    # Mensaje de texto puro
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

    item_data = _items.obtener_item(item_nombre) or {}
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

    # Disparar level-up handler si subió de nivel
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

    # Dar la EXP necesaria para subir exactamente 1 nivel
    exp_necesaria = ExperienceSystem.exp_necesaria_para_nivel(poke.nivel)
    exp_faltante  = exp_necesaria - poke.exp if hasattr(poke, "exp") else exp_necesaria
    resultado = ExperienceSystem.aplicar_experiencia(poke.id_unico, max(1, exp_faltante))
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
    """
    Bayas de combate/mitigación: se equipan al Pokémon como objeto.
    Se consumen automáticamente en batalla (ya implementado en battle_engine).
    """
    from database import db_manager

    objeto_previo = getattr(poke, "objeto", None)
    if objeto_previo:
        # Devolver objeto previo al inventario
        _items.agregar_item(user_id, objeto_previo, 1)

    # Consumir la baya del inventario y equiparla
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

    @bot.callback_query_handler(func=lambda c: c.data.startswith("itemuse_sel_"))
    def _cb_selector(call: types.CallbackQuery):
        """
        Formato: itemuse_sel_{user_id}_{item_nombre~con~tildes}
        Separamos con maxsplit=3 para preservar ítems con nombres compuestos.
        """
        try:
            partes = call.data.split("_", 3)
            # partes: ['itemuse', 'sel', uid, item_encoded]
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

    @bot.callback_query_handler(func=lambda c: c.data.startswith("itemuse_apk_"))
    def _cb_aplicar(call: types.CallbackQuery):
        """
        Formato: itemuse_apk_{user_id}_{item_encoded}_{pokemon_id}
        El pokemon_id es siempre el ÚLTIMO segmento (entero).
        """
        try:
            # split con maxsplit=3 → ['itemuse', 'apk', uid, 'item~encoded_pokemon_id']
            partes = call.data.split("_", 3)
            if len(partes) < 4:
                bot.answer_callback_query(call.id, "❌ Datos inválidos.", show_alert=True)
                return

            user_id = int(partes[2])
            resto   = partes[3]  # "item~encoded_pokemon_id"

            # El pokemon_id es el último token separado por "_"
            ultimo_sep = resto.rfind("_")
            if ultimo_sep == -1:
                bot.answer_callback_query(call.id, "❌ Datos inválidos.", show_alert=True)
                return

            item_encoded = resto[:ultimo_sep]
            pokemon_id   = int(resto[ultimo_sep + 1:])
            item_nombre  = item_encoded.replace("~", " ")

            if call.from_user.id != user_id:
                bot.answer_callback_query(call.id, "❌ Este menú no es tuyo.", show_alert=True)
                return

            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass

            aplicar_item_a_pokemon(user_id, item_nombre, pokemon_id, call.message, bot)

        except Exception as exc:
            logger.error(f"[ITEM_USE] Error en _cb_aplicar: {exc}", exc_info=True)
            try:
                bot.answer_callback_query(call.id, "❌ Error interno.", show_alert=True)
            except Exception:
                pass

    logger.info("[ITEM_USE] Callbacks de uso de ítems registrados.")
