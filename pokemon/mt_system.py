# -*- coding: utf-8 -*-
"""
pokemon/mt_system.py
══════════════════════════════════════════════════════════
Sistema de uso de MT desde la mochila.

Flujo:
  1. Usuario usa item "mt001" etc desde la mochila
  2. menu_pokemon._mostrar_detalle_item detecta prefijo "mt" → llama iniciar_uso_mt()
  3. Se filtran Pokémon del equipo que pueden aprender el movimiento por MT
  4. Si ninguno → mensaje sin consumir el item
  5. Si alguno  → selector de Pokémon (inline)
  6. Al elegir Pokémon:
     a. Slots libres → aprende directamente
     b. 4 slots ocupados → selector de movimiento a reemplazar
  7. Confirmar → guardar en BD + consumir item

Callbacks:
  mt_poke_{uid}_{mt_item}_{pokemon_id}
  mt_slot_{uid}_{mt_item}_{pokemon_id}_{slot}
  mt_cancel_{uid}
══════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from telebot import types

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════
# MAPEO COMPLETO MT Gen 9 (Escarlata/Púrpura)
# item_id → move_key (normalizado: lowercase sin espacios)
# ══════════════════════════════════════════════════════════
MT_MAP: dict[str, str] = {
    "mt001": "megapunch",
    "mt002": "payback",
    "mt003": "thunderpunch",
    "mt004": "icepunch",
    "mt005": "firepunch",
    "mt006": "bulletpunch",
    "mt007": "lowkick",
    "mt008": "lowsweep",
    "mt009": "thunder",
    "mt010": "hiddenpower",
    "mt011": "watergun",
    "mt012": "lowsweep",       # alias
    "mt013": "snore",
    "mt014": "acrobatics",
    "mt015": "struggle",       # placeholder
    "mt016": "psybeam",
    "mt017": "scaryface",
    "mt018": "thief",
    "mt019": "telekinesis",
    "mt020": "trailblaze",
    "mt021": "pounce",
    "mt022": "chillwater",
    "mt023": "charge",
    "mt024": "snatch",
    "mt025": "protect",
    "mt026": "poisontail",
    "mt027": "hex",
    "mt028": "bulldoze",
    "mt029": "charm",
    "mt030": "snarl",
    "mt031": "metal",           # metalclaw
    "mt032": "swift",
    "mt033": "magicalleaf",
    "mt034": "icy",             # icywind
    "mt035": "mudshot",
    "mt036": "whirlpool",
    "mt037": "dragonbreath",
    "mt038": "flame",           # flamecharge
    "mt039": "venomdrench",
    "mt040": "acids",           # acidspray
    "mt041": "foulplay",
    "mt042": "nightshade",
    "mt043": "revenge",
    "mt044": "electroball",
    "mt045": "dig",
    "mt046": "avalanche",
    "mt047": "endure",
    "mt048": "play",            # playrough
    "mt049": "syrupbomb",
    "mt050": "raindance",
    "mt051": "sandstorm",
    "mt052": "snowscape",
    "mt053": "sunnyday",
    "mt054": "psych",           # psychup
    "mt055": "brine",
    "mt056": "u-turn",
    "mt057": "retaliate",
    "mt058": "brick",           # brickbreak
    "mt059": "zenheadbutt",
    "mt060": "expimp",          # expandingforce
    "mt061": "shadow",          # shadowclaw
    "mt062": "fling",
    "mt063": "psychic",
    "mt064": "bulkup",
    "mt065": "drainpunch",
    "mt066": "thunderwave",
    "mt067": "icebeam",
    "mt068": "firespin",
    "mt069": "rest",
    "mt070": "sleeptalk",
    "mt071": "snowball",        # placeholder
    "mt072": "magnet",          # magnetrise
    "mt073": "thunder",         # thunderbolt (alias, ver mt085)
    "mt074": "reflect",
    "mt075": "lightscreen",
    "mt076": "round",
    "mt077": "heatwave",
    "mt078": "darkpulse",
    "mt079": "outrage",
    "mt080": "rockslide",
    "mt081": "bulletseed",
    "mt082": "frostbreath",
    "mt083": "chargbeam",       # chargebeam
    "mt084": "weatherball",
    "mt085": "thunderbolt",
    "mt086": "energyball",
    "mt087": "dragonpulse",
    "mt088": "scald",
    "mt089": "bodyslam",
    "mt090": "surf",
    "mt091": "liquidation",
    "mt092": "shadowball",
    "mt093": "flash",           # flashcannon
    "mt094": "fly",
    "mt095": "ic",              # icespinner
    "mt096": "earthquake",
    "mt097": "auroraveil",
    "mt098": "flashcannon",
    "mt099": "mysticalfire",
    "mt100": "nastyplot",
    "mt101": "nightdaze",
    "mt102": "hydrpump",        # hydropump
    "mt103": "solarbeam",
    "mt104": "crunch",
    "mt105": "dig",             # alias mt045
    "mt106": "waterfall",
    "mt107": "poisonpowder",    # placeholder
    "mt108": "trickroom",
    "mt109": "flamethrower",
    "mt110": "grassknot",
    "mt111": "gunkshot",
    "mt112": "aurasp",          # aurasphere
    "mt113": "dracometeor",
    "mt114": "storedpower",
    "mt115": "mystical",        # mysticalpowerflame
    "mt116": "steelbeam",
    "mt117": "hyper",           # hyperbeam
    "mt118": "giga",            # gigaimpact
    "mt119": "icywind",
    "mt120": "psychic",         # alias
    "mt121": "icicle",          # iciclespear
    "mt122": "swordsdance",
    "mt123": "petalblizzard",
    "mt124": "stompingtantrum",
    "mt125": "earthquake",      # alias
    "mt126": "gigadrain",
    "mt127": "play",            # alias playrough
    "mt128": "airslash",
    "mt129": "calmmind",
    "mt130": "moonblast",
    "mt131": "poltergeist",
    "mt132": "poisonpowder",    # placeholder
    "mt133": "aquatail",
    "mt134": "fireblast",
    "mt135": "thunderpunch",    # alias
    "mt136": "closecombat",
    "mt137": "rockpolicer",     # placeholder
    "mt138": "focusblast",
    "mt139": "earth",           # earthpower
    "mt140": "megahorn",
    "mt141": "blizzard",
    "mt142": "draco",           # dracometeor alias
    "mt143": "lastresort",
    "mt144": "infernooverdrive", # placeholder
    "mt145": "rockblast",       # placeholder
    "mt146": "highhorsepower",
    "mt147": "crosspoison",
    "mt148": "surf",            # alias
    "mt149": "hypervoice",
    "mt150": "shadowforce",
    "mt151": "hardpress",
    "mt152": "poisonjab",
    "mt153": "rockpolish",
    "mt154": "scaryface",       # alias
    "mt155": "furycutter",
    "mt156": "outrage",         # alias
    "mt157": "overheat",
    "mt158": "hurricane",
    "mt159": "thunder",         # alias
    "mt160": "flareblitz",
    "mt161": "focuspunch",
    "mt162": "vacuumwave",
    "mt163": "wavecrash",
    "mt164": "aquajet",
    "mt165": "smackdown",
    "mt166": "storedpower",     # alias
    "mt167": "tidy",            # placeholder
    "mt168": "bravebird",
    "mt169": "blazekick",       # blaze kick placeholder
    "mt170": "leafstorm",       # leafstorm placeholder
    "mt171": "ironhead",
    "mt172": "rockwrecker",     # placeholder
    "mt173": "payback",         # alias
    "mt174": "bodypress",
    "mt175": "struggle",        # placeholder
    "mt176": "gunkshot",        # alias
    "mt177": "liquidation",     # alias
    "mt178": "shadowstrike",    # placeholder
    "mt179": "drainingkiss",
    "mt180": "ruination",
    "mt181": "makeitrain",
    "mt182": "axekick",
    "mt183": "kowtowcleave",
    "mt184": "chillyreception",
    "mt185": "populationbomb",
    "mt186": "lashout",
    "mt187": "ragingfury",
    "mt188": "bittermalice",
    "mt189": "headlongrush",
    "mt190": "springtidestorm",
    "mt191": "wildboltstorm",
    "mt192": "sandsearstorm",
    "mt193": "bleakwindstorm",
    "mt194": "mountaingale",
    "mt195": "victorydance",
    "mt196": "lastrespects",
    "mt197": "gigatonhammer",
    "mt198": "icespinner",
    "mt199": "snowscape",       # alias
    "mt200": "terablast",
    "mt201": "hydropump",
    "mt202": "pounce",          # alias
    "mt203": "trailblaze",      # alias
    "mt204": "chillyreception", # alias
    "mt205": "iciclecrash",
    "mt206": "aurasphere",
    "mt207": "psychicfangs",
    "mt208": "fleurcannon",
    "mt209": "pollenuf",        # placeholder
    "mt210": "mistyterrain",
    "mt211": "electricterrain",
    "mt212": "psychicterrain",
    "mt213": "grassyterrain",
    "mt214": "searing",         # searingshot placeholder
    "mt215": "expandingforce",
    "mt216": "risingvoltage",
    "mt217": "steeroller",
    "mt218": "terrainpulse",
    "mt219": "mistyexplosion",
    "mt220": "gravapple",
    "mt221": "courtchange",
    "mt222": "eternabeam",
    "mt223": "fierywrath",
    "mt224": "chilling",        # chillingwater
    "mt225": "psyshieldbash",
    "mt226": "revivalblessing",
    "mt227": "saltcure",
    "mt228": "chloroblast",
    "mt229": "mountaingale",    # alias
    "mt230": "magicpowder",
    "mt231": "collisioncourse",
    "mt232": "electrorift",     # placeholder
    "mt233": "direclaws",
    "mt234": "hardpress",       # alias
    "mt235": "powergemalt",     # placeholder
    "mt236": "aerialace",
    "mt237": "dualwingbeat",
}

# Versión limpia: solo los más importantes con nombres correctos Gen9
MT_MAP_LIMPIO: dict[str, str] = {
    "mt001": "megapunch",
    "mt002": "payback",
    "mt003": "thunderpunch",
    "mt004": "icepunch",
    "mt005": "firepunch",
    "mt006": "bulletpunch",
    "mt007": "lowkick",
    "mt008": "lowsweep",
    "mt014": "acrobatics",
    "mt017": "scaryface",
    "mt018": "thief",
    "mt025": "protect",
    "mt028": "bulldoze",
    "mt029": "charm",
    "mt030": "snarl",
    "mt032": "swift",
    "mt033": "magicalleaf",
    "mt034": "icywind",
    "mt035": "mudshot",
    "mt036": "whirlpool",
    "mt037": "dragonbreath",
    "mt041": "foulplay",
    "mt042": "nightshade",
    "mt043": "revenge",
    "mt044": "electroball",
    "mt045": "dig",
    "mt046": "avalanche",
    "mt047": "endure",
    "mt050": "raindance",
    "mt051": "sandstorm",
    "mt052": "snowscape",
    "mt053": "sunnyday",
    "mt055": "brine",
    "mt056": "uturn",
    "mt057": "retaliate",
    "mt058": "brickbreak",
    "mt059": "zenheadbutt",
    "mt061": "shadowclaw",
    "mt062": "fling",
    "mt063": "psychic",
    "mt064": "bulkup",
    "mt065": "drainpunch",
    "mt066": "thunderwave",
    "mt067": "icebeam",
    "mt068": "firespin",
    "mt069": "rest",
    "mt070": "sleeptalk",
    "mt074": "reflect",
    "mt075": "lightscreen",
    "mt077": "heatwave",
    "mt078": "darkpulse",
    "mt079": "outrage",
    "mt080": "rockslide",
    "mt081": "bulletseed",
    "mt085": "thunderbolt",
    "mt086": "energyball",
    "mt087": "dragonpulse",
    "mt089": "bodyslam",
    "mt090": "surf",
    "mt091": "liquidation",
    "mt092": "shadowball",
    "mt094": "fly",
    "mt096": "earthquake",
    "mt097": "auroraveil",
    "mt098": "flashcannon",
    "mt100": "nastyplot",
    "mt102": "hydropump",
    "mt103": "solarbeam",
    "mt104": "crunch",
    "mt106": "waterfall",
    "mt108": "trickroom",
    "mt109": "flamethrower",
    "mt110": "grassknot",
    "mt111": "gunkshot",
    "mt112": "aurasphere",
    "mt113": "dracometeor",
    "mt117": "hyperbeam",
    "mt118": "gigaimpact",
    "mt119": "icywind",
    "mt122": "swordsdance",
    "mt126": "gigadrain",
    "mt128": "airslash",
    "mt129": "calmmind",
    "mt130": "moonblast",
    "mt134": "fireblast",
    "mt136": "closecombat",
    "mt138": "focusblast",
    "mt140": "megahorn",
    "mt141": "blizzard",
    "mt146": "highhorsepower",
    "mt147": "crosspoison",
    "mt149": "hypervoice",
    "mt151": "hardpress",
    "mt152": "poisonjab",
    "mt157": "overheat",
    "mt158": "hurricane",
    "mt160": "flareblitz",
    "mt161": "focuspunch",
    "mt163": "wavecrash",
    "mt164": "aquajet",
    "mt168": "bravebird",
    "mt171": "ironhead",
    "mt174": "bodypress",
    "mt179": "drainingkiss",
    "mt180": "ruination",
    "mt182": "axekick",
    "mt198": "icespinner",
    "mt200": "terablast",
    "mt205": "iciclecrash",
    "mt206": "aurasphere",
    "mt207": "psychicfangs",
    "mt210": "mistyterrain",
    "mt211": "electricterrain",
    "mt212": "psychicterrain",
    "mt213": "grassyterrain",
    "mt215": "expandingforce",
    "mt220": "gravapple",
    "mt227": "saltcure",
    "mt231": "collisioncourse",
    "mt233": "direclaws",
}


def _move_key_de_mt(item_nombre: str) -> Optional[str]:
    """Dado 'mt085' retorna 'thunderbolt'. Retorna None si no existe."""
    return MT_MAP.get(item_nombre.lower().strip())


def _nombre_movimiento(move_key: str) -> str:
    """Retorna nombre display del movimiento o el key capitalizado."""
    try:
        from pokemon.services.movimientos_service import movimientos_service
        data = movimientos_service.obtener_movimiento(move_key)
        if data:
            return data.get("nombre", move_key.capitalize())
    except Exception:
        pass
    return move_key.replace("_", " ").capitalize()


def _movimientos_actuales(poke) -> list:
    """
    Retorna exactamente 4 slots de movimiento del Pokémon (puede haber None).
    Prioridad:
      1. poke.movimientos  — lista almacenada por pokemon_service._row_a_pokemon
      2. Atributos move1/move2/move3/move4 — fallback para objetos legacy
    """
    movs = getattr(poke, "movimientos", None)
    if movs and isinstance(movs, (list, tuple)):
        normalizado = list(movs[:4])
        while len(normalizado) < 4:
            normalizado.append(None)
        return normalizado
    # Fallback legacy
    return [
        getattr(poke, "move1", None),
        getattr(poke, "move2", None),
        getattr(poke, "move3", None),
        getattr(poke, "move4", None),
    ]


def _nombre_poke(poke) -> str:
    """Nombre display del Pokémon (mote si tiene, sino nombre especie)."""
    mote   = getattr(poke, "mote",   None)
    nombre = getattr(poke, "nombre", None)
    return mote if mote else (nombre if nombre else f"Pokémon #{poke.id_unico}")


def _consumir_mt(user_id: int, item_nombre: str) -> None:
    """Descuenta 1 unidad del item via usar_item de items_service."""
    try:
        from pokemon.services.items_service import items_service
        items_service.usar_item(user_id, item_nombre, 1)
    except Exception as e:
        logger.error(f"[MT] Error consumiendo {item_nombre}: {e}")


# ══════════════════════════════════════════════════════════
# PUNTO DE ENTRADA DESDE LA MOCHILA
# ══════════════════════════════════════════════════════════

def iniciar_uso_mt(user_id: int, item_nombre: str, message, bot) -> Tuple[bool, str]:
    """
    Llamar desde menu_pokemon cuando el usuario usa un item que empieza con 'mt'.
    Retorna (consumir_ahora, mensaje_texto).
    El item NUNCA se consume aquí — se consume solo al confirmar en _aplicar_mt.
    """
    from pokemon.services import pokemon_service
    from pokemon.services.movimientos_service import movimientos_service

    move_key = _move_key_de_mt(item_nombre)
    if not move_key:
        return False, f"❌ No se encontró el movimiento para <b>{item_nombre.upper()}</b>."

    nombre_move = _nombre_movimiento(move_key)
    equipo      = pokemon_service.obtener_equipo(user_id)

    # Pokémon que pueden aprender por MT Y que aún no lo saben
    compatibles = [
        p for p in equipo
        if movimientos_service.puede_aprender_por_mt(p.pokemonID, move_key)
        and move_key not in [m for m in _movimientos_actuales(p) if m]
    ]

    if not compatibles:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "⬅️ Volver", callback_data=f"pokebag_cat_{user_id}_mts"
        ))
        texto = (
            f"📀 <b>{item_nombre.upper()} — {nombre_move}</b>\n\n"
            f"❌ Ningún Pokémon de tu equipo puede aprender\n"
            f"<b>{nombre_move}</b> por MT."
        )
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
                bot.edit_message_caption(
                    caption=texto,
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
            except Exception:
                bot.send_message(user_id, texto, parse_mode="HTML", reply_markup=markup)
        return False, ""

    _mostrar_selector_pokemon(user_id, item_nombre, move_key, nombre_move, compatibles, message, bot)
    return False, ""


def _edit_message(message, bot, user_id: int, texto: str, markup) -> None:
    """Edita el mensaje actual o envía uno nuevo como fallback."""
    try:
        bot.edit_message_text(
            texto,
            chat_id=message.chat.id,
            message_id=message.message_id,
            parse_mode="HTML",
            reply_markup=markup,
        )
        return
    except Exception:
        pass
    try:
        bot.edit_message_caption(
            caption=texto,
            chat_id=message.chat.id,
            message_id=message.message_id,
            parse_mode="HTML",
            reply_markup=markup,
        )
    except Exception:
        bot.send_message(user_id, texto, parse_mode="HTML", reply_markup=markup)


def _mostrar_selector_pokemon(user_id, item_nombre, move_key, nombre_move, compatibles, message, bot):
    texto  = (
        f"📀 <b>{item_nombre.upper()} — {nombre_move}</b>\n\n"
        f"¿A qué Pokémon quieres enseñarle <b>{nombre_move}</b>?"
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    for p in compatibles:
        shiny = "✨" if getattr(p, "shiny", False) else ""
        label = f"{shiny}{_nombre_poke(p)} Nv.{p.nivel}"
        markup.add(types.InlineKeyboardButton(
            label,
            callback_data=f"mt_poke_{user_id}_{item_nombre}_{p.id_unico}",
        ))
    markup.add(types.InlineKeyboardButton(
        "❌ Cancelar", callback_data=f"mt_cancel_{user_id}"
    ))
    _edit_message(message, bot, user_id, texto, markup)


# ══════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════

def handle_mt_callback(call, bot) -> None:
    """
    Dispatcher para callbacks mt_poke_*, mt_slot_*, mt_cancel_*.
    Registrar en pokemon_handlers.py:
        @bot.callback_query_handler(func=lambda c: c.data.startswith("mt_"))
        def cb_mt(call): handle_mt_callback(call, bot)
    """
    data    = call.data or ""
    user_id = call.from_user.id
    parts   = data.split("_")

    try:
        if len(parts) < 2:
            return
        accion = parts[1]

        # ── mt_cancel_{uid} ───────────────────────────────────────────────
        if accion == "cancel":
            uid = int(parts[2]) if len(parts) > 2 else user_id
            if user_id != uid:
                bot.answer_callback_query(call.id, "⛔ No es tu item.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            # Volver a la mochila
            try:
                bot.edit_message_text(
                    "🎒 Operación cancelada.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=types.InlineKeyboardMarkup([[
                        types.InlineKeyboardButton(
                            "⬅️ Mochila", callback_data=f"pokemenu_bag_{uid}"
                        )
                    ]]),
                )
            except Exception:
                pass
            return

        # ── mt_poke_{uid}_{item}_{pokemon_id} ─────────────────────────────
        if accion == "poke":
            uid         = int(parts[2])
            item_nombre = parts[3]
            pokemon_id  = int(parts[4])
            if user_id != uid:
                bot.answer_callback_query(call.id, "⛔ No es tu item.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            _seleccionar_slot(uid, item_nombre, pokemon_id, call.message, bot)
            return

        # ── mt_slot_{uid}_{item}_{pokemon_id}_{slot} ──────────────────────
        if accion == "slot":
            uid         = int(parts[2])
            item_nombre = parts[3]
            pokemon_id  = int(parts[4])
            slot        = parts[5]
            if user_id != uid:
                bot.answer_callback_query(call.id, "⛔ No es tu item.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            _aplicar_mt(uid, item_nombre, pokemon_id, slot, call.message, bot)
            return

    except Exception as e:
        logger.error(f"[MT] Error en handle_mt_callback: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Error interno.", show_alert=True)
        except Exception:
            pass


def _seleccionar_slot(user_id: int, item_nombre: str, pokemon_id: int, message, bot) -> None:
    """Si hay slot libre aprende directo; si no, muestra los 4 para elegir cuál reemplazar."""
    from pokemon.services import pokemon_service

    p = pokemon_service.obtener_pokemon(pokemon_id)
    if p is None:
        bot.send_message(user_id, "❌ Pokémon no encontrado.")
        return

    move_key    = _move_key_de_mt(item_nombre)
    if move_key is None:
        bot.send_message(user_id, "❌ MT no reconocida.")
        return

    nombre_move = _nombre_movimiento(move_key)
    movs        = _movimientos_actuales(p)
    libres      = [i for i, m in enumerate(movs) if not m]

    if libres:
        # Slot libre → aprender sin preguntar
        _aplicar_mt(user_id, item_nombre, pokemon_id, str(libres[0] + 1), message, bot)
        return

    # 4 slots ocupados → preguntar cuál reemplazar
    nombre_poke = _nombre_poke(p)
    texto = (
        f"📀 <b>{item_nombre.upper()} — {nombre_move}</b>\n\n"
        f"<b>{nombre_poke}</b> ya tiene 4 movimientos.\n"
        f"¿Cuál querés reemplazar con <b>{nombre_move}</b>?"
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    for i, mv in enumerate(movs):
        if mv:
            markup.add(types.InlineKeyboardButton(
                f"🔄 {_nombre_movimiento(mv)}",
                callback_data=f"mt_slot_{user_id}_{item_nombre}_{pokemon_id}_{i + 1}",
            ))
    markup.add(types.InlineKeyboardButton(
        "❌ Cancelar", callback_data=f"mt_cancel_{user_id}"
    ))
    _edit_message(message, bot, user_id, texto, markup)


def _aplicar_mt(user_id: int, item_nombre: str, pokemon_id: int, slot: str, message, bot) -> None:
    """Escribe el movimiento en la BD, consume el item, muestra confirmación."""
    from pokemon.services import pokemon_service
    from database import db_manager

    try:
        p = pokemon_service.obtener_pokemon(pokemon_id)
        if p is None:
            bot.send_message(user_id, "❌ Pokémon no encontrado.")
            return

        move_key = _move_key_de_mt(item_nombre)
        if move_key is None:
            bot.send_message(user_id, "❌ MT no reconocida.")
            return

        nombre_move = _nombre_movimiento(move_key)
        slot_idx    = int(slot)          # 1-4
        col         = f"move{slot_idx}"

        movs_viejos    = _movimientos_actuales(p)
        mv_reemplazado = movs_viejos[slot_idx - 1]

        # Guardar en BD
        db_manager.execute_update(
            f"UPDATE POKEMON_USUARIO SET {col} = ? WHERE id_unico = ?",
            (move_key, pokemon_id),
        )

        # Consumir item (usa usar_item que ya existe en items_service)
        _consumir_mt(user_id, item_nombre)

        nombre_poke = _nombre_poke(p)
        if mv_reemplazado:
            texto = (
                f"✅ <b>{nombre_poke}</b> olvidó "
                f"<b>{_nombre_movimiento(mv_reemplazado)}</b>\n"
                f"y aprendió <b>{nombre_move}</b> 📀"
            )
        else:
            texto = f"✅ <b>{nombre_poke}</b> aprendió <b>{nombre_move}</b> 📀"

        markup = types.InlineKeyboardMarkup([[
            types.InlineKeyboardButton(
                "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
            )
        ]])
        _edit_message(message, bot, user_id, texto, markup)

        logger.info(f"[MT] {user_id}: {nombre_poke} aprendió {move_key} via {item_nombre}")

    except Exception as e:
        logger.error(f"[MT] Error aplicando MT: {e}", exc_info=True)
        try:
            bot.send_message(user_id, "❌ Error al enseñar el movimiento.")
        except Exception:
            pass