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
    "mt001": "takedown",            # Derribo
    "mt002": "charm",               # Encanto
    "mt003": "faketears",           # Llanto Falso
    "mt004": "agility",             # Agilidad
    "mt005": "mudslap",             # Bofetón Lodo
    "mt006": "scaryface",           # Cara Susto
    "mt007": "protect",             # Protección
    "mt008": "firefang",            # Colmillo Ígneo
    "mt009": "thunderfang",         # Colmillo Rayo
    "mt010": "icefang",             # Colmillo Hielo
    "mt011": "waterpulse",          # Hidropulso
    "mt012": "lowkick",             # Patada Baja
    "mt013": "acidspray",           # Bomba Ácida
    "mt014": "acrobatics",          # Acróbata
    "mt015": "strugglebug",         # Estoicismo
    "mt016": "psybeam",             # Psicorrayo
    "mt017": "confuseray",          # Rayo Confuso
    "mt018": "thief",               # Ladrón
    "mt019": "disarmingvoice",      # Voz Cautivadora
    "mt020": "trailblaze",          # Abrecaminos
    "mt021": "pounce",              # Brinco
    "mt022": "chillingwater",       # Agua Fría
    "mt023": "chargebeam",          # Rayo Carga
    "mt024": "firespin",            # Giro Fuego
    "mt025": "facade",              # Imagen
    "mt026": "poisontail",          # Cola Veneno
    "mt027": "aerialace",           # Golpe Aéreo
    "mt028": "bulldoze",            # Terratemblor
    "mt029": "hex",                 # Infortunio
    "mt030": "snarl",               # Alarido
    "mt031": "metalclaw",           # Garra Metal
    "mt032": "swift",               # Rapidez
    "mt033": "magicalleaf",         # Hoja Mágica
    "mt034": "icywind",             # Viento Hielo
    "mt035": "mudshot",             # Disparo Lodo
    "mt036": "rocktomb",            # Tumba Rocas
    "mt037": "drainingkiss",        # Beso Drenaje
    "mt038": "flamecharge",         # Nitrocarga
    "mt039": "lowsweep",            # Puntapié
    "mt040": "aircutter",           # Aire Afilado
    "mt041": "storedpower",         # Poder Reserva
    "mt042": "nightshade",          # Tinieblas
    "mt043": "fling",               # Lanzamiento
    "mt044": "dragontail",          # Cola Dragón
    "mt045": "venoshock",           # Carga Tóxica
    "mt046": "avalanche",           # Alud
    "mt047": "endure",              # Aguante
    "mt048": "voltswitch",          # Voltiocambio
    "mt049": "sunnyday",            # Día Soleado
    "mt050": "raindance",           # Danza Lluvia
    "mt051": "sandstorm",           # Tormenta Arena
    "mt052": "snowscape",           # Paisaje Nevado
    "mt053": "smartstrike",         # Cuerno Certero
    "mt054": "psyshock",            # Psicocarga
    "mt055": "dig",                 # Excavación
    "mt056": "bulletseed",          # Recurrente
    "mt057": "falseswipe",          # Falsotortazo
    "mt058": "slash",               # Cuchillada
    "mt059": "zenheadbutt",         # Cabezazo Zen
    "mt060": "uturn",               # Ida y Vuelta
    "mt061": "shadowclaw",          # Garra Sombría
    "mt062": "foulplay",            # Juego Sucio
    "mt063": "psychicfangs",        # Psicocolmillo
    "mt064": "bulkup",              # Corpulencia
    "mt065": "airslash",            # Tajo Aéreo
    "mt066": "bodypress",           # Plancha Corporal
    "mt067": "firepunch",           # Puño Fuego
    "mt068": "thunderpunch",        # Puño Trueno
    "mt069": "icepunch",            # Puño Hielo
    "mt070": "sleeptalk",           # Sonámbulo
    "mt071": "seedbomb",            # Bomba Germen
    "mt072": "electroball",         # Electrobola
    "mt073": "drainpunch",          # Puño Drenaje
    "mt074": "reflect",             # Reflejo
    "mt075": "lightscreen",         # Pantalla de Luz
    "mt076": "rockblast",           # Pedrada
    "mt077": "waterfall",           # Cascada
    "mt078": "dragonclaw",          # Garra Dragón
    "mt079": "dazzlinggleam",       # Brillo Mágico
    "mt080": "metronome",           # Metrónomo
    "mt081": "grassknot",           # Hierba Lazo
    "mt082": "thunderwave",         # Onda Trueno
    "mt083": "poisonjab",           # Puya Nociva
    "mt084": "stompingtantrum",     # Pataleta
    "mt085": "rest",                # Descanso
    "mt086": "rockslide",           # Avalancha
    "mt087": "taunt",               # Mofa
    "mt088": "swordsdance",         # Danza Espada
    "mt089": "bodyslam",            # Golpe Cuerpo
    "mt090": "spikes",              # Púas
    "mt091": "toxicspikes",         # Púas Tóxicas
    "mt092": "imprison",            # Sellado
    "mt093": "flashcannon",         # Foco Resplandor
    "mt094": "darkpulse",           # Pulso Umbrío
    "mt095": "leechlife",           # Chupavidas
    "mt096": "eerieimpulse",        # Onda Anómala
    "mt097": "fly",                 # Vuelo
    "mt098": "skillswap",           # Intercambio
    "mt099": "ironhead",            # Cabeza de Hierro
    "mt100": "dragondance",         # Danza Dragón
    "mt101": "powergem",            # Joya de Luz
    "mt102": "gunkshot",            # Lanzamugre
    "mt103": "substitute",          # Sustituto
    "mt104": "irondefense",         # Defensa Férrea
    "mt105": "xscissor",            # Tijera X
    "mt106": "drillrun",            # Taladradora
    "mt107": "willowisp",           # Fuego Fatuo
    "mt108": "crunch",              # Triturar
    "mt109": "trick",               # Truco
    "mt110": "liquidation",         # Hidroariete
    "mt111": "gigadrain",           # Gigadrenado
    "mt112": "aurasphere",          # Esfera Aural
    "mt113": "tailwind",            # Viento Afín
    "mt114": "shadowball",          # Bola Sombra
    "mt115": "dragonpulse",         # Pulso Dragón
    "mt116": "stealthrock",         # Trampa Rocas
    "mt117": "hypervoice",          # Vozarrón
    "mt118": "heatwave",            # Onda Ígnea
    "mt119": "energyball",          # Energibola
    "mt120": "psychic",             # Psíquico
    "mt121": "heavyslam",           # Cuerpo Pesado
    "mt122": "encore",              # Otra Vez
    "mt123": "surf",                # Surf
    "mt124": "icespinner",          # Pirueta Helada
    "mt125": "flamethrower",        # Lanzallamas
    "mt126": "thunderbolt",         # Rayo
    "mt127": "playrough",           # Carantoña
    "mt128": "amnesia",             # Amnesia
    "mt129": "calmmind",            # Paz Mental
    "mt130": "helpinghand",         # Refuerzo
    "mt131": "pollenpuff",          # Bola Polen
    "mt132": "batonpass",           # Relevo
    "mt133": "earthquake",          # Terremoto
    "mt134": "reversal",            # Inversión
    "mt135": "icebeam",             # Rayo Hielo
    "mt136": "electricterrain",     # Campo Eléctrico
    "mt137": "grassyterrain",       # Campo de Hierba
    "mt138": "mistyterrain",        # Campo de Niebla
    "mt139": "psychicterrain",      # Campo Psíquico
    "mt140": "nastyplot",           # Maquinación
    "mt141": "fireblast",           # Llamarada
    "mt142": "hydropump",           # Hidrobomba
    "mt143": "blizzard",            # Ventisca
    "mt144": "firepledge",          # Voto Fuego
    "mt145": "waterpledge",         # Voto Agua
    "mt146": "grasspledge",         # Voto Planta
    "mt147": "wildcharge",          # Voltio Cruel
    "mt148": "sludgebomb",          # Bomba Lodo
    "mt149": "earthpower",          # Tierra Viva
    "mt150": "leafstorm",           # Llave de Hojas
    "mt151": "phantomforce",        # Golpe Fantasma
    "mt152": "gigaimpact",          # Gigaimpacto
    "mt153": "energyball",          # Energibola (Dup)
    "mt154": "hydropump",           # Hidrobomba (Dup)
    "mt155": "outrage",             # Enfado
    "mt156": "hurricane",           # Vendaval
    "mt157": "overheat",            # Sofoco
    "mt158": "focusblast",          # Onda Certera
    "mt159": "leafstorm",           # Llave de Hojas (Dup)
    "mt160": "hurricane",           # Vendaval (Dup)
    "mt161": "trickroom",           # Espacio Raro
    "mt162": "bugbuzz",             # Zumbido
    "mt163": "hyperbeam",           # Hiperrayo
    "mt164": "bravebird",           # Envite Ígneo (Volador)
    "mt165": "flareblitz",          # Envite Ígneo (Fuego)
    "mt166": "thunder",             # Trueno
    "mt167": "closecombat",         # A Bocajarro
    "mt168": "solarbeam",           # Rayo Solar
    "mt169": "dracometeor",         # Cometa Draco
    "mt170": "steelbeam",           # Metaláser
    "mt171": "terablast",           # Teraexplosión
    "mt172": "roar",                # Rugido
    "mt173": "charge",              # Carga
    "mt174": "haze",                # Niebla
    "mt175": "toxic",               # Tóxico
    "mt176": "sandtomb",            # Bucle Arena
    "mt177": "spite",               # Rencor
    "mt178": "gravity",             # Gravedad
    "mt179": "smackdown",           # Antiaéreo
    "mt180": "gyroball",            # Giro Bola
    "mt181": "knockoff",            # Desarme
    "mt182": "bugbite",             # Picadura
    "mt183": "superfang",           # Superdiente
    "mt184": "vacuumwave",          # Onda Vacío
    "mt185": "lunge",               # Plancha
    "mt186": "highhorsepower",      # Fuerza Equina
    "mt187": "iciclespear",         # Carámbano
    "mt188": "scald",               # Escaldar
    "mt189": "heatcrash",           # Cuerpo Pesado (Fuego)
    "mt190": "solarblade",          # Cuchilla Solar
    "mt191": "uproar",              # Alboroto
    "mt192": "focuspunch",          # Puño Certero
    "mt193": "weatherball",         # Meteorobola
    "mt194": "grassyglide",         # Fitoimpulso
    "mt195": "burningjealousy",     # Envidia Ardiente
    "mt196": "flipturn",            # Viraje
    "mt197": "dualwingbeat",        # Ala de Acero
    "mt198": "poltergeist",         # Poltergeist
    "mt199": "lashout",             # Desahogo
    "mt200": "scaleshot",           # Ráfaga Escamas
    "mt201": "mistyexplosion",      # Explosión Bruma
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