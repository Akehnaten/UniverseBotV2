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
    # ── Gen 9 (Escarlata/Púrpura) — lista oficial completa, 201 MTs ────────
    "mt001": "takedown",
    "mt002": "charm",
    "mt003": "faketears",
    "mt004": "agility",
    "mt005": "mudslap",
    "mt006": "scaryface",
    "mt007": "protect",
    "mt010": "icefang",
    "mt008": "firefang",
    "mt009": "thunderfang",
    "mt011": "waterpulse",
    "mt012": "lowkick",
    "mt013": "acidspray",
    "mt014": "acrobatics",
    "mt015": "strugglebug",
    "mt016": "psybeam",
    "mt017": "confuseray",
    "mt018": "thief",
    "mt019": "disarmingvoice",
    "mt020": "trailblaze",
    "mt021": "pounce",
    "mt022": "chillingwater",
    "mt023": "chargebeam",
    "mt024": "firespin",
    "mt025": "facade",
    "mt026": "poisontail",
    "mt027": "aerialace",
    "mt028": "bulldoze",
    "mt029": "hex",
    "mt030": "snarl",
    "mt031": "metalclaw",
    "mt032": "swift",
    "mt033": "magicalleaf",
    "mt034": "icywind",
    "mt035": "mudshot",
    "mt036": "rocktomb",
    "mt037": "drainingkiss",
    "mt038": "flamecharge",
    "mt039": "lowsweep",
    "mt040": "aircutter",
    "mt041": "storedpower",
    "mt042": "nightshade",
    "mt043": "fling",
    "mt044": "dragontail",
    "mt045": "venoshock",
    "mt046": "avalanche",
    "mt047": "endure",
    "mt048": "voltswitch",
    "mt049": "sunnyday",
    "mt050": "raindance",
    "mt051": "sandstorm",
    "mt052": "snowscape",
    "mt053": "smartstrike",
    "mt054": "psyshock",
    "mt055": "dig",
    "mt056": "bulletseed",
    "mt057": "falseswipe",
    "mt058": "slash",
    "mt059": "zenheadbutt",
    "mt060": "uturn",
    "mt061": "shadowclaw",
    "mt062": "foulplay",
    "mt063": "psychicfangs",
    "mt064": "bulkup",
    "mt065": "airslash",
    "mt066": "bodypress",
    "mt067": "firepunch",
    "mt068": "thunderpunch",
    "mt069": "icepunch",
    "mt070": "sleeptalk",
    "mt071": "seedbomb",
    "mt072": "electroball",
    "mt073": "drainpunch",
    "mt074": "reflect",
    "mt075": "lightscreen",
    "mt076": "rockblast",
    "mt077": "waterfall",
    "mt078": "dragonclaw",
    "mt079": "dazzlinggleam",
    "mt080": "metronome",
    "mt081": "grassknot",
    "mt082": "thunderwave",
    "mt083": "poisonjab",
    "mt084": "stompingtantrum",
    "mt085": "rest",
    "mt086": "rockslide",
    "mt087": "taunt",
    "mt088": "swordsdance",
    "mt089": "bodyslam",
    "mt090": "spikes",
    "mt091": "toxicspikes",
    "mt092": "imprison",
    "mt093": "flashcannon",
    "mt094": "darkpulse",
    "mt095": "leechlife",
    "mt096": "eerieimpulse",
    "mt097": "fly",
    "mt098": "skillswap",
    "mt099": "ironhead",
    "mt100": "dragondance",
    "mt101": "powergem",
    "mt102": "gunkshot",
    "mt103": "substitute",
    "mt104": "irondefense",
    "mt105": "xscissor",
    "mt106": "drillrun",
    "mt107": "willowisp",
    "mt108": "crunch",
    "mt109": "trick",
    "mt110": "liquidation",
    "mt111": "gigadrain",
    "mt112": "aurasphere",
    "mt113": "tailwind",
    "mt114": "shadowball",
    "mt115": "dragonpulse",
    "mt116": "stealthrock",
    "mt117": "hypervoice",
    "mt118": "heatwave",
    "mt119": "energyball",
    "mt120": "psychic",
    "mt121": "heavyslam",
    "mt122": "encore",
    "mt123": "surf",
    "mt124": "icebeam",
    "mt125": "flamethrower",
    "mt126": "thunderbolt",
    "mt127": "playrough",
    "mt128": "amnesia",
    "mt129": "calmmind",
    "mt130": "helpinghand",
    "mt131": "pollenpuff",
    "mt132": "batonpass",
    "mt133": "earthquake",
    "mt134": "reversal",
    "mt135": "hardpress",
    "mt136": "electricterrain",
    "mt137": "grassyterrain",
    "mt138": "mistyterrain",
    "mt139": "psychicterrain",
    "mt140": "nastyplot",
    "mt141": "fireblast",
    "mt142": "hydropump",
    "mt143": "blizzard",
    "mt144": "firepledge",
    "mt145": "waterpledge",
    "mt146": "grasspledge",
    "mt147": "wildcharge",
    "mt148": "sludgebomb",
    "mt149": "earthpower",
    "mt150": "mindblown",        # CAMBIO: Cabeza Sorpresa (En lugar de Superfang)
    "mt151": "phantomforce",
    "mt152": "gigaimpact",
    "mt153": "skyattack",
    "mt154": "hydrocannon",
    "mt155": "frenzyplant",
    "mt156": "blastburn",
    "mt157": "overheat",
    "mt158": "focusblast",
    "mt159": "leafstorm",
    "mt160": "hurricane",
    "mt161": "trickroom",
    "mt162": "bugbuzz",
    "mt163": "hyperbeam",
    "mt164": "bravebird",
    "mt165": "flareblitz",
    "mt166": "thunder",
    "mt167": "closecombat",
    "mt168": "solarbeam",
    "mt169": "dracometeor",
    "mt170": "steelbeam",
    "mt171": "terablast",
    "mt172": "roar",
    "mt173": "charge",
    "mt174": "haze",
    "mt175": "toxic",
    "mt176": "sandtomb",
    "mt177": "spite",
    "mt178": "gravity",
    "mt179": "smackdown",
    "mt180": "gyroball",
    "mt181": "knockoff",
    "mt182": "bugbite",
    "mt183": "superfang",      # Se queda aquí (Original Gen 9)
    "mt184": "vacuumwave",
    "mt185": "lunge",
    "mt186": "highhorsepower",
    "mt187": "iciclespear",
    "mt188": "scald",
    "mt189": "heatcrash",
    "mt190": "solarblade",
    "mt191": "uproar",
    "mt192": "focuspunch",
    "mt193": "weatherball",
    "mt194": "grassyglide",
    "mt195": "burningjealousy",
    "mt196": "flipturn",
    "mt197": "dualwingbeat",
    "mt198": "poltergeist",
    "mt199": "lashout",
    "mt200": "scaleshot",
    "mt201": "mistyexplosion"

}

# Versión limpia: solo los más importantes con nombres correctos Gen9
# MT_MAP_LIMPIO: alias de compatibilidad — usar MT_MAP directamente
MT_MAP_LIMPIO: dict[str, str] = MT_MAP


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