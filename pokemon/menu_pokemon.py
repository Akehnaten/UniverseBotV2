# -*- coding: utf-8 -*-
"""
Menú Principal Pokémon
======================
Todas las secciones del sistema Pokémon accesibles desde /pokemon.

CORRECCIONES (v2):
- _mostrar_categoria_mochila: html.escape() en descripción para evitar
  error 400 de Telegram cuando desc contiene < > (ej: "cura 25% HP < 50%")
- _mostrar_detalle_item: ídem, html.escape() en descripción
- _mostrar_categoria_mts: filtro cambiado de startswith("mt"|"mo") a
  `item_id in MT_MAP`, evitando que moonstone, modestmint y otros ítems
  cuya clave empieza por "mo" aparezcan en la vista de MTs/MOs.
"""

import html as _html
import math
import logging
from telebot import types

from pokemon.services import pokemon_service
from pokemon.centro_pokemon import centro_pokemon

logger = logging.getLogger(__name__)

# ── Tienda ────────────────────────────────────────────────────────────────────
_SHOP_PAGE_SIZE = 10
_BAG_PAGE_SIZE  = 8

# ── Mochila: tipos de item que muestran el botón "Usar" ──────────────────────
_TIPOS_CONSUMIBLES = {
    "medicina", "curacion", "revivir", "estado", "pp",
    "vitamina", "pokeball",
    "baya", "baya_combate", "baya_mitigacion", "baya_ofensiva",
    "baya_pp", "baya_estado", "baya_hp",
    "evolucion", "evolutivo", "intercambio",
    "utilidad_especial", "utilidad",
    "menta",
}

# ── Índice inverso: item_id → cat_id ─────────────────────────────────────────
from pokemon.items_database_complete import CATEGORIAS_TIENDA as _CATS_TIENDA

_LEGACY_CAT_MAP: dict[str, str] = {
    "pokeballs":        "pokeballs",
    "medicinas":        "medicinas",
    "revivir":          "medicinas",
    "estados":          "medicinas",
    "pp":               "medicinas",
    "vitaminas":        "vitaminas",
    "evolutivos":       "piedras",
    "poder":            "combate_power",
    "defensivos":       "combate_defensivo",
    "situacionales":    "combate_situacional",
    "utilidad":         "combate_situacional",
    "choice":           "combate_choice",
    "bayas_combate":    "bayas",
    "bayas_mitigacion": "bayas",
    "crianza":          "crianza",
    "clima_terreno":    "clima",
    "mts":              "MT/MO",
    "mentas":           "mentas",
}

_ITEM_A_CAT: dict[str, str] = {}

for _cat_id, _cat_data in _CATS_TIENDA.items():
    for _item_id in _cat_data.get("items", []):
        _ITEM_A_CAT[_item_id.lower()] = _cat_id

try:
    from pokemon.services.items_service import items_service as _its_tmp
    items_cats = _its_tmp.categorias or {}
    for _leg_cat, _leg_data in items_cats.items():
        _canon = _LEGACY_CAT_MAP.get(_leg_cat or "", _leg_cat or "")
        items_list = _leg_data.get("items", []) or []
        for _item_id in items_list:
            if _item_id:
                _ITEM_A_CAT[_item_id.lower()] = _canon
except Exception:
    pass


def _cat_de_item(item_id: str, item_data: dict | None = None) -> str:
    return _ITEM_A_CAT.get(item_id.lower(), "otros")


def _nombre_item(item_id: str, item_data: dict) -> str:
    if item_data:
        for key in ("nombre", "name", "nombre_es"):
            val = item_data.get(key)
            if val:
                return str(val)
    return item_id.replace("_", " ").title()


class MenuPokemon:
    """Menú principal del sistema Pokémon."""

    # ──────────────────────────────────────────────────────────────────────────
    # PUNTO DE ENTRADA PRINCIPAL
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def mostrar_menu_principal(user_id: int, bot, message):
        try:
            if message.chat.type in ("group", "supergroup"):
                tid = getattr(message, "message_thread_id", None)
                extra = {"message_thread_id": tid} if tid else {}
                try:
                    MenuPokemon._enviar_menu_privado(user_id, bot)
                    bot.send_message(
                        message.chat.id,
                        "✅ ¡Revisa tu DM!\n\n"
                        "⚠️ Si no llega, envíame /start en privado primero.",
                        **extra,
                    )
                except Exception as e:
                    logger.error(f"[MENU] Error enviando DM: {e}")
                    bot.send_message(
                        message.chat.id,
                        "❌ No puedo enviarte mensajes privados.\n"
                        "📩 Envíame /start en privado para habilitar el menú.",
                        **extra,
                    )
            else:
                MenuPokemon._enviar_menu_privado(user_id, bot)
        except Exception as e:
            logger.error(f"[MENU] Error en mostrar_menu_principal: {e}", exc_info=True)

    # ──────────────────────────────────────────────────────────────────────────
    # CONSTRUCCIÓN DEL MENÚ PRINCIPAL
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _construir_menu(user_id: int):
        equipo = pokemon_service.obtener_equipo(user_id)
        estado = centro_pokemon.verificar_estado_equipo(user_id)

        if equipo:
            texto = (
                "🎮 <b>MENÚ POKÉMON</b>\n\n"
                f"👥 <b>Tu Equipo:</b> {estado['total']}/6\n"
                f"💚 Sanos: {estado['sanos']}   "
                f"💛 Heridos: {estado['heridos']}   "
                f"💀 Debilitados: {estado['debilitados']}\n\n"
                "¿Qué deseas hacer?"
            )
        else:
            texto = (
                "🎮 <b>MENÚ POKÉMON</b>\n\n"
                "❌ No tienes Pokémon todavía.\n"
                "Usa /profesor para obtener tu inicial.\n\n"
                "¿Qué deseas hacer?"
            )

        centro_label = "💚 Centro Pokémon"
        if estado["necesita_curacion"]:
            centro_label += " ❗"

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("💻 Mi PC",      callback_data=f"pokemenu_pc_{user_id}"),
            types.InlineKeyboardButton("👥 Equipo",     callback_data=f"pokemenu_team_{user_id}"),
        )
        markup.add(
            types.InlineKeyboardButton("📖 Pokédex",   callback_data=f"pokemenu_pokedex_{user_id}"),
            types.InlineKeyboardButton("🎒 Mochila",   callback_data=f"pokemenu_bag_{user_id}"),
        )
        markup.add(
            types.InlineKeyboardButton("🏪 Tienda",    callback_data=f"pokemenu_shop_{user_id}"),
            types.InlineKeyboardButton(centro_label,   callback_data=f"pokemenu_center_{user_id}"),
        )
        markup.add(
            types.InlineKeyboardButton("🥚 Guardería", callback_data=f"pokemenu_daycare_{user_id}"),
        )
        markup.add(types.InlineKeyboardButton(
            "📚 Recordador de Movimientos",
            callback_data=f"pokemenu_reminder_{user_id}",
        ))
        markup.add(
            types.InlineKeyboardButton("❌ Cerrar",    callback_data=f"pokemenu_close_{user_id}"),
        )

        return texto, markup

    # ──────────────────────────────────────────────────────────────────────────
    # ENVÍO / EDICIÓN DEL MENÚ
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _enviar_menu_privado(user_id: int, bot):
        texto, markup = MenuPokemon._construir_menu(user_id)
        bot.send_message(user_id, texto, reply_markup=markup, parse_mode="HTML")

    @staticmethod
    def _editar_menu_en_mensaje(user_id: int, message, bot):
        texto, markup = MenuPokemon._construir_menu(user_id)
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    # ──────────────────────────────────────────────────────────────────────────
    # DISPATCHER DE CALLBACKS
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def procesar_callback(call, bot):
        try:
            data = call.data

            if data.startswith("pokebag_"):
                MenuPokemon._procesar_callback_mochila(call, bot)
                return

            if data.startswith("pokeshop_"):
                MenuPokemon._procesar_callback_tienda(call, bot)
                return

            parts = data.split("_")
            if len(parts) < 3:
                return

            if len(parts) == 4 and parts[1] == "poke":
                user_id = int(parts[2])
                pid     = int(parts[3])
                if call.from_user.id != user_id:
                    bot.answer_callback_query(call.id, "❌ Este menú no es tuyo.", show_alert=True)
                    return
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass
                MenuPokemon._mostrar_detalle_pokemon(user_id, pid, call.message, bot)
                return

            if len(parts) >= 5 and parts[1] == "reminder" and parts[2] == "pk":
                user_id   = int(parts[3])
                poke_id_r = int(parts[4])
                if call.from_user.id != user_id:
                    bot.answer_callback_query(call.id, "❌ Este menú no es tuyo.", show_alert=True)
                    return
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass
                from pokemon.move_reminder import mostrar_movimientos_olvidados as _mr_movs
                _mr_movs(user_id, poke_id_r, call.message, bot)
                return

            if len(parts) >= 6 and parts[1] == "reminder" and parts[2] == "mv":
                user_id    = int(parts[3])
                poke_id_r  = int(parts[4])
                move_key_r = parts[5]
                if call.from_user.id != user_id:
                    bot.answer_callback_query(call.id, "❌ Este menú no es tuyo.", show_alert=True)
                    return
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass
                from pokemon.move_reminder import mostrar_selector_slot as _mr_slot
                _mr_slot(user_id, poke_id_r, move_key_r, call.message, bot)
                return

            if len(parts) >= 7 and parts[1] == "reminder" and parts[2] == "sl":
                user_id    = int(parts[3])
                poke_id_r  = int(parts[4])
                move_key_r = parts[5]
                slot_r     = int(parts[6])
                if call.from_user.id != user_id:
                    bot.answer_callback_query(call.id, "❌ Este menú no es tuyo.", show_alert=True)
                    return
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass
                from pokemon.move_reminder import aplicar_desde_callback as _mr_apply
                _mr_apply(user_id, poke_id_r, move_key_r, slot_r, call.message, bot)
                return

            opcion  = parts[1]
            user_id = int(parts[2])

            if call.from_user.id != user_id:
                bot.answer_callback_query(
                    call.id, "❌ Este menú no es tuyo.", show_alert=True
                )
                return

            if call.data.startswith(f"pokemenu_reminder_"):
                parts_r = call.data.split("_")
                sub = parts_r[2] if len(parts_r) > 2 else ""
                if sub == str(user_id):
                    from pokemon.move_reminder import mostrar_selector_pokemon as _mr
                    _mr(user_id, call.message, bot)
                elif sub == "pk":
                    pid_r = int(parts_r[4])
                    from pokemon.move_reminder import mostrar_movimientos_olvidados as _mr
                    _mr(user_id, pid_r, call.message, bot)
                elif sub == "mv":
                    pid_r = int(parts_r[4])
                    mk_r  = parts_r[5]
                    from pokemon.move_reminder import mostrar_selector_slot as _mr
                    _mr(user_id, pid_r, mk_r, call.message, bot)
                elif sub == "sl":
                    pid_r  = int(parts_r[4])
                    mk_r   = parts_r[5]
                    slot_r = int(parts_r[6])
                    from pokemon.move_reminder import aplicar_desde_callback as _mr
                    _mr(user_id, pid_r, mk_r, slot_r, call.message, bot)
                return

            if opcion == "back":
                MenuPokemon._editar_menu_en_mensaje(user_id, call.message, bot)

            elif opcion == "close":
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except Exception:
                    pass

            elif opcion == "heal":
                MenuPokemon._procesar_curacion(user_id, call, bot)

            elif opcion == "pokedex":
                MenuPokemon._mostrar_pokedex(user_id, call.message, bot)

            elif opcion == "bag":
                MenuPokemon._mostrar_mochila(user_id, call.message, bot)

            elif opcion == "pc":
                MenuPokemon._mostrar_pc(user_id, call.message, bot, pagina=0)

            elif opcion == "team":
                MenuPokemon._mostrar_equipo(user_id, call.message, bot)

            elif opcion == "teamfresh":
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except Exception:
                    pass
                texto, markup_eq = MenuPokemon._construir_equipo(user_id)
                bot.send_message(user_id, texto, reply_markup=markup_eq, parse_mode="HTML")

            elif opcion == "shop":
                MenuPokemon._mostrar_tienda(user_id, call.message, bot)

            elif opcion == "daycare":
                MenuPokemon._mostrar_guarderia(user_id, call.message, bot)

            elif opcion == "center":
                MenuPokemon._mostrar_centro(user_id, call.message, bot)

            elif opcion == "unequip":
                if len(parts) < 4:
                    bot.answer_callback_query(call.id, "❌ Datos incorrectos.", show_alert=True)
                    return
                pid_unequip = int(parts[3])
                MenuPokemon._procesar_desequipar_item(user_id, pid_unequip, call, bot)

            elif opcion == "moveup":
                if len(parts) < 4:
                    bot.answer_callback_query(call.id, "❌ Datos incorrectos.", show_alert=True)
                    return
                pid_mover = int(parts[3])
                pokemon_service.mover_posicion_equipo_arriba(user_id, pid_mover)
                MenuPokemon._mostrar_modo_ordenar(user_id, call.message, bot)

            elif opcion == "movedown":
                if len(parts) < 4:
                    bot.answer_callback_query(call.id, "❌ Datos incorrectos.", show_alert=True)
                    return
                pid_mover = int(parts[3])
                pokemon_service.mover_posicion_equipo_abajo(user_id, pid_mover)
                MenuPokemon._mostrar_modo_ordenar(user_id, call.message, bot)

            elif opcion == "ordenar":
                MenuPokemon._mostrar_modo_ordenar(user_id, call.message, bot)

            elif opcion == "pcpage":
                pag = int(parts[3]) if len(parts) > 3 else 0
                MenuPokemon._mostrar_pc(user_id, call.message, bot, pagina=pag)

            elif opcion == "pcpoke":
                if len(parts) < 5:
                    bot.answer_callback_query(call.id, "❌ Datos incorrectos.", show_alert=True)
                    return
                pid_pc = int(parts[3])
                pag_pc = int(parts[4])
                MenuPokemon._mostrar_pc_pokemon(user_id, pid_pc, pag_pc, call.message, bot)

            elif opcion == "pcmoveq":
                if len(parts) < 5:
                    bot.answer_callback_query(call.id, "❌ Datos incorrectos.", show_alert=True)
                    return
                pid_mv = int(parts[3])
                pag_mv = int(parts[4])
                equipo_actual = pokemon_service.obtener_equipo(user_id)
                if len(equipo_actual) < 6:
                    ok, msg = pokemon_service.mover_a_equipo(pid_mv, user_id)
                    bot.answer_callback_query(call.id, msg, show_alert=not ok)
                    if ok:
                        MenuPokemon._mostrar_pc(user_id, call.message, bot, pagina=pag_mv)
                    else:
                        MenuPokemon._mostrar_pc_pokemon(
                            user_id, pid_mv, pag_mv, call.message, bot
                        )
                else:
                    bot.answer_callback_query(call.id)
                    MenuPokemon._mostrar_pc_swap_equipo(
                        user_id, pid_mv, pag_mv, call.message, bot
                    )

            elif opcion == "pcdep":
                if len(parts) < 5:
                    bot.answer_callback_query(call.id, "❌ Datos incorrectos.", show_alert=True)
                    return
                pid_ref = int(parts[3])
                pag_dep = int(parts[4])
                bot.answer_callback_query(call.id)
                MenuPokemon._mostrar_selector_depositar(user_id, pid_ref, pag_dep, call.message, bot)

            elif opcion == "pcdepok":
                if len(parts) < 5:
                    bot.answer_callback_query(call.id, "❌ Datos incorrectos.", show_alert=True)
                    return
                pid_dep = int(parts[3])
                pag_dep = int(parts[4])
                MenuPokemon._procesar_depositar(user_id, pid_dep, pag_dep, call, bot)

            elif opcion == "pclib":
                if len(parts) < 5:
                    bot.answer_callback_query(call.id, "❌ Datos incorrectos.", show_alert=True)
                    return
                pid_lib = int(parts[3])
                pag_lib = int(parts[4])
                bot.answer_callback_query(call.id)
                MenuPokemon._mostrar_pc_liberar_confirm(
                    user_id, pid_lib, pag_lib, call.message, bot
                )

            elif opcion == "pclibera":
                if len(parts) < 5:
                    bot.answer_callback_query(call.id, "❌ Datos incorrectos.", show_alert=True)
                    return
                pid_libera = int(parts[3])
                pag_libera = int(parts[4])
                MenuPokemon._procesar_liberar_desde_pc(
                    user_id, pid_libera, pag_libera, call, bot
                )

            elif opcion == "pcswap":
                if len(parts) < 6:
                    bot.answer_callback_query(call.id, "❌ Datos incorrectos.", show_alert=True)
                    return
                pid_pc     = int(parts[3])
                pid_equipo = int(parts[4])
                pag_swap   = int(parts[5])
                MenuPokemon._procesar_pc_swap(
                    user_id, pid_pc, pid_equipo, pag_swap, call, bot
                )

            elif opcion == "liberarconfirm":
                if len(parts) < 4:
                    bot.answer_callback_query(call.id, "❌ Datos incorrectos.", show_alert=True)
                    return
                pid_lib = int(parts[3])
                p_lib   = pokemon_service.obtener_pokemon(pid_lib)
                nombre_lib = (p_lib.mote or p_lib.nombre) if p_lib else f"#{pid_lib}"
                markup_conf = types.InlineKeyboardMarkup(row_width=2)
                markup_conf.add(
                    types.InlineKeyboardButton(
                        "✅ Sí, liberar",
                        callback_data=f"pokemenu_liberar_{user_id}_{pid_lib}"
                    ),
                    types.InlineKeyboardButton(
                        "❌ Cancelar",
                        callback_data=f"pokemenu_poke_{user_id}_{pid_lib}"
                    ),
                )
                texto_conf = (
                    f"⚠️ ¿Seguro que quieres liberar a <b>{nombre_lib}</b>?\n\n"
                    f"Recibirás <b>{(p_lib.nivel if p_lib else 0) * 10} cosmos</b>. "
                    f"Esta acción no se puede deshacer."
                )
                MenuPokemon._edit_or_send(call.message, bot, user_id, texto_conf, markup_conf)

            elif opcion == "liberar":
                if len(parts) < 4:
                    bot.answer_callback_query(call.id, "❌ Datos incorrectos.", show_alert=True)
                    return
                pid_lib2 = int(parts[3])
                MenuPokemon._procesar_liberar_pokemon(user_id, pid_lib2, call, bot)

            elif opcion == "noop":
                pass

            elif opcion == "reminder":
                from pokemon.move_reminder import mostrar_selector_pokemon as _mr_poke
                _mr_poke(user_id, call.message, bot)

            else:
                bot.answer_callback_query(call.id, "⚙️ Función no implementada aún.")

        except Exception as e:
            logger.error(f"[MENU] Error en procesar_callback: {e}", exc_info=True)
            try:
                bot.answer_callback_query(call.id, "❌ Error interno.", show_alert=True)
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────────────────────
    # HELPER: editar o enviar si editar falla
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _edit_or_send(message, bot, user_id: int, texto: str, markup):
        try:
            bot.edit_message_text(
                texto,
                message.chat.id,
                message.message_id,
                reply_markup=markup,
                parse_mode="HTML",
            )
        except Exception as edit_err:
            if "message is not modified" in str(edit_err):
                return
            logger.debug(f"[MENU] edit_message_text falló ({edit_err}), enviando nuevo.")
            bot.send_message(user_id, texto, reply_markup=markup, parse_mode="HTML")

    # ──────────────────────────────────────────────────────────────────────────
    # SECCIONES DEL MENÚ
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _mostrar_pokedex(user_id: int, message, bot):
        from pokemon.services import pokedex_service
        from database import db_manager

        rows = db_manager.execute_query(
            "SELECT DISTINCT pokemonID FROM POKEMON_USUARIO WHERE userID = ? ORDER BY pokemonID",
            (user_id,)
        ) or []

        texto = "📖 <b>POKÉDEX</b>\n\n"
        if not rows:
            texto += "Aún no has capturado ningún Pokémon.\nUsa /profesor para obtener tu inicial."
        else:
            texto += f"Pokémon registrados: <b>{len(rows)}</b>\n\n"
            for row in rows[:30]:
                pid    = int(row["pokemonID"])
                nombre = pokedex_service.obtener_nombre(pid)
                texto += f"#{pid:03d} {nombre}\n"
            if len(rows) > 30:
                texto += f"\n…y {len(rows) - 30} más."

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Volver", callback_data=f"pokemenu_back_{user_id}"))
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    # ── MOCHILA ───────────────────────────────────────────────────────────────

    @staticmethod
    def _mostrar_mochila(user_id: int, message, bot):
        from pokemon.services import items_service
        from pokemon.items_database_complete import CATEGORIAS_TIENDA

        try:
            inventario = items_service.obtener_inventario(user_id)
        except Exception:
            inventario = {}

        if not inventario:
            texto  = "🎒 <b>MOCHILA</b>\n\nTu mochila está vacía."
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "⬅️ Volver", callback_data=f"pokemenu_back_{user_id}"
            ))
            MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)
            return

        conteo: dict[str, int] = {}
        for item_id, qty in inventario.items():
            if not qty or qty <= 0:
                continue
            cat = _cat_de_item(item_id)
            conteo[cat] = conteo.get(cat, 0) + qty

        total_global = sum(conteo.values())
        texto = (
            f"🎒 <b>MOCHILA</b>\n\n"
            f"<i>Items totales: {total_global}</i>\n\n"
            f"Elige una categoría:"
        )

        cats_ordenadas = sorted(
            CATEGORIAS_TIENDA.items(), key=lambda x: x[1].get("orden", 99)
        )

        markup  = types.InlineKeyboardMarkup(row_width=2)
        botones = []
        for cat_id, cat_data in cats_ordenadas:
            if cat_id in conteo:
                botones.append(types.InlineKeyboardButton(
                    f"{cat_data['nombre']} ({conteo[cat_id]})",
                    callback_data=f"pokebag_cat_{user_id}_{cat_id}_0",
                ))

        if "otros" in conteo:
            botones.append(types.InlineKeyboardButton(
                f"📦 Otros ({conteo['otros']})",
                callback_data=f"pokebag_cat_{user_id}_otros_0",
            ))

        for i in range(0, len(botones), 2):
            markup.row(*botones[i:i + 2])

        markup.add(types.InlineKeyboardButton(
            "⬅️ Volver", callback_data=f"pokemenu_back_{user_id}"
        ))
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    @staticmethod
    def _mostrar_categoria_mochila(
        user_id: int, message, bot, categoria: str, pagina: int = 0
    ):
        from pokemon.services import items_service
        from pokemon.items_database_complete import CATEGORIAS_TIENDA

        try:
            inventario = items_service.obtener_inventario(user_id)
        except Exception:
            inventario = {}

        cat_data   = CATEGORIAS_TIENDA.get(categoria, {})
        cat_nombre = cat_data.get("nombre", "📦 Otros")

        items_user: list = []
        for item_id, qty in inventario.items():
            if not qty or qty <= 0:
                continue
            if _cat_de_item(item_id) == categoria:
                try:
                    item_data = items_service.obtener_item(item_id) or {}
                except Exception:
                    item_data = {}
                items_user.append((item_id, qty, item_data))

        items_user.sort(key=lambda x: x[0])

        if not items_user:
            texto  = f"🎒 <b>{cat_nombre}</b>\n\nNo tienes items en esta categoría."
            markup = types.InlineKeyboardMarkup()
            markup.row(
                types.InlineKeyboardButton(
                    "🎒 Categorías", callback_data=f"pokemenu_bag_{user_id}"
                ),
                types.InlineKeyboardButton(
                    "🏠 Menú", callback_data=f"pokemenu_back_{user_id}"
                ),
            )
            MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)
            return

        total_pags = max(1, math.ceil(len(items_user) / _SHOP_PAGE_SIZE))
        pagina     = max(0, min(pagina, total_pags - 1))
        inicio     = pagina * _SHOP_PAGE_SIZE
        items_pag  = items_user[inicio: inicio + _SHOP_PAGE_SIZE]

        texto = (
            f"🎒 <b>{cat_nombre}</b>\n"
            f"Página {pagina + 1}/{total_pags}\n\n"
        )
        for item_id, cantidad, item_data in items_pag:
            nombre_display = _nombre_item(item_id, item_data)
            _desc_raw = (
                item_data.get("desc")
                or item_data.get("descripcion")
                or "Sin descripción."
            )
            # FIX: escapar la descripción para evitar error 400 de Telegram
            # cuando contiene < > (ej: "cura 25% HP < 50%")
            descripcion = _html.escape(str(_desc_raw))
            texto += f"• <b>{nombre_display}</b> — ×{cantidad}\n  {descripcion}\n\n"

        markup = types.InlineKeyboardMarkup(row_width=1)
        for item_id, cantidad, item_data in items_pag:
            nombre_display = _nombre_item(item_id, item_data)
            markup.add(types.InlineKeyboardButton(
                f"{nombre_display}  ×{cantidad}",
                callback_data=f"pokebag_item_{user_id}_{item_id}",
            ))

        nav_row: list = []
        if pagina > 0:
            nav_row.append(types.InlineKeyboardButton(
                "⬅",
                callback_data=f"pokebag_cat_{user_id}_{categoria}_{pagina - 1}",
            ))
        if pagina < total_pags - 1:
            nav_row.append(types.InlineKeyboardButton(
                "➡",
                callback_data=f"pokebag_cat_{user_id}_{categoria}_{pagina + 1}",
            ))
        if nav_row:
            markup.row(*nav_row)

        markup.row(
            types.InlineKeyboardButton(
                "🎒 Categorías", callback_data=f"pokemenu_bag_{user_id}"
            ),
            types.InlineKeyboardButton(
                "🏠 Menú", callback_data=f"pokemenu_back_{user_id}"
            ),
        )

        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    @staticmethod
    def _mostrar_categoria_mts(user_id: int, message, bot):
        """Lista las MTs del inventario del usuario con su movimiento."""
        from pokemon.services import items_service
        from pokemon.mt_system import MT_MAP
        from pokemon.battle_engine import MOVE_NAMES_ES

        try:
            inventario = items_service.obtener_inventario(user_id)
        except Exception:
            inventario = {}

        # FIX: filtrar usando MT_MAP en lugar de startswith("mt") | startswith("mo").
        # El filtro anterior incluía moonstone, modestmint y cualquier ítem cuya
        # clave empiece por esas letras. Ahora solo se muestran ítems reales de MT.
        mt_items = [
            (item_id, qty)
            for item_id, qty in inventario.items()
            if item_id in MT_MAP and qty > 0
        ]
        mt_items.sort()

        if not mt_items:
            texto  = "📀 <b>MÁQUINAS TÉCNICAS</b>\n\nNo tienes MTs en tu mochila."
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
            ))
            MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)
            return

        texto  = "📀 <b>MÁQUINAS TÉCNICAS</b>\n\nSelecciona una MT para usarla:"
        markup = types.InlineKeyboardMarkup(row_width=1)

        for item_id, qty in mt_items:
            move_key  = MT_MAP.get(item_id, "")
            mk_norm   = move_key.lower().replace(" ", "").replace("-", "")
            nombre_mv = MOVE_NAMES_ES.get(mk_norm, move_key.replace("-", " ").title()) if move_key else "???"
            num       = item_id.upper()
            label     = f"{num} — {nombre_mv}  ×{qty}"
            markup.add(types.InlineKeyboardButton(
                label,
                callback_data=f"pokebag_usemt_{user_id}_{item_id}",
            ))

        markup.add(types.InlineKeyboardButton(
            "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
        ))
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    @staticmethod
    def _mostrar_detalle_item(user_id: int, message, bot, item_nombre: str):
        """Pantalla de detalle: descripción, cantidad, precio de venta y acciones."""
        from pokemon.services import items_service

        try:
            inventario = items_service.obtener_inventario(user_id)
        except Exception:
            inventario = {}

        cantidad = inventario.get(item_nombre, 0)
        if cantidad <= 0:
            try:
                bot.answer_callback_query(message.id, "❌ Ya no tienes ese item.", show_alert=True)
            except Exception:
                pass
            MenuPokemon._mostrar_mochila(user_id, message, bot)
            return

        item_data      = items_service.obtener_item(item_nombre) or {}
        nombre_display = _nombre_item(item_nombre, item_data)

        _desc_raw   = item_data.get("desc") or item_data.get("descripcion") or "Sin descripción."
        # FIX: escapar la descripción para evitar error 400 con chars < > en Telegram
        descripcion = _html.escape(str(_desc_raw))

        precio_compra  = item_data.get("precio", 0) or 0
        precio_venta   = math.ceil(precio_compra * 0.5) if precio_compra > 0 else 0
        tipo           = item_data.get("tipo", "") or ""
        es_consumible  = tipo in _TIPOS_CONSUMIBLES

        texto = (
            f"🎒 <b>{nombre_display}</b>\n\n"
            f"📋 {descripcion}\n\n"
            f"📦 Cantidad: <b>{cantidad}</b>\n"
            f"💰 Precio de venta: <b>{precio_venta} Cosmos</b> c/u\n"
        )

        markup = types.InlineKeyboardMarkup(row_width=1)

        if precio_venta > 0:
            markup.add(types.InlineKeyboardButton(
                f"💰 Vender ×1  (+{precio_venta} Cosmos)",
                callback_data=f"pokebag_sell_{user_id}_{item_nombre}",
            ))

        if es_consumible:
            markup.add(types.InlineKeyboardButton(
                "✅ Usar",
                callback_data=f"pokebag_use_{user_id}_{item_nombre}",
            ))

        markup.add(types.InlineKeyboardButton(
            "🤝 Dar a Pokémon",
            callback_data=f"pokebag_give_{user_id}_{item_nombre}",
        ))

        cat = _cat_de_item(item_nombre, item_data)
        markup.add(types.InlineKeyboardButton(
            "⬅️ Volver",
            callback_data=f"pokebag_cat_{user_id}_{cat}_0",
        ))
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    @staticmethod
    def _procesar_venta_item(user_id: int, message, bot, item_nombre: str):
        from pokemon.services import items_service
        from funciones import economy_service

        try:
            inventario = items_service.obtener_inventario(user_id)
            if inventario.get(item_nombre, 0) <= 0:
                MenuPokemon._edit_or_send(
                    message, bot, user_id,
                    "❌ Ya no tienes ese item.", types.InlineKeyboardMarkup()
                )
                return

            item_data     = items_service.obtener_item(item_nombre) or {}
            precio_compra = item_data.get("precio", 0) or 0
            precio_venta  = math.ceil(precio_compra * 0.5)

            if precio_venta <= 0:
                MenuPokemon._edit_or_send(
                    message, bot, user_id,
                    "❌ Este item no se puede vender.", types.InlineKeyboardMarkup()
                )
                return

            ok, msg = items_service.usar_item(user_id, item_nombre, 1)
            if not ok:
                MenuPokemon._edit_or_send(message, bot, user_id, f"❌ {msg}", types.InlineKeyboardMarkup())
                return

            economy_service.add_credits(user_id, precio_venta, f"Venta item: {item_nombre}")

            nombre_display = _nombre_item(item_nombre, item_data)
            texto = (
                f"✅ <b>Vendiste 1× {nombre_display}</b>\n\n"
                f"💰 Recibiste <b>{precio_venta} Cosmos</b>."
            )
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
            ))
            MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

        except Exception as e:
            logger.error(f"[MOCHILA] Error vendiendo item: {e}", exc_info=True)
            MenuPokemon._edit_or_send(
                message, bot, user_id, "❌ Error al vender el item.", types.InlineKeyboardMarkup()
            )

    @staticmethod
    def _mostrar_dar_item(user_id: int, message, bot, item_nombre: str):
        equipo = pokemon_service.obtener_equipo(user_id)

        if not equipo:
            MenuPokemon._edit_or_send(
                message, bot, user_id,
                "❌ No tienes Pokémon en tu equipo.", types.InlineKeyboardMarkup()
            )
            return

        nombre_item = item_nombre.replace("_", " ").title()
        texto  = f"🤝 <b>Dar {nombre_item} a...</b>\n\nElige un Pokémon:"
        markup = types.InlineKeyboardMarkup(row_width=1)

        for poke in equipo:
            nombre_display = poke.mote or poke.nombre
            sexo_emoji     = {"M": " ♂", "F": " ♀"}.get(getattr(poke, "sexo", None) or "", "")
            shiny_emoji    = " ✨" if getattr(poke, "shiny", False) else ""
            objeto_actual  = f"  [lleva: {poke.objeto}]" if poke.objeto else ""
            markup.add(types.InlineKeyboardButton(
                f"{nombre_display}{sexo_emoji}{shiny_emoji} Nv.{poke.nivel}{objeto_actual}",
                callback_data=f"pokebag_give_pk_{user_id}_{poke.id_unico}_{item_nombre}",
            ))

        markup.add(types.InlineKeyboardButton(
            "⬅️ Volver",
            callback_data=f"pokebag_item_{user_id}_{item_nombre}",
        ))
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    @staticmethod
    def _procesar_dar_item(user_id: int, message, bot, poke_id: int, item_nombre: str):
        """
        Equipa un item a un Pokémon del equipo.
        Si ya llevaba un objeto, lo devuelve al inventario antes de equipar el nuevo.
        """
        from pokemon.services import items_service
        from database import db_manager

        try:
            inventario = items_service.obtener_inventario(user_id)
            if inventario.get(item_nombre, 0) <= 0:
                MenuPokemon._edit_or_send(
                    message, bot, user_id,
                    "❌ Ya no tienes ese item.", types.InlineKeyboardMarkup()
                )
                return

            poke = pokemon_service.obtener_pokemon(poke_id)
            if not poke or poke.usuario_id != user_id:
                MenuPokemon._edit_or_send(
                    message, bot, user_id,
                    "❌ Pokémon no encontrado.", types.InlineKeyboardMarkup()
                )
                return

            objeto_previo = poke.objeto

            if objeto_previo:
                # Devolver objeto previo al inventario directamente en BD
                # para no perder objetos que solo existen en ITEMS_COMPLETOS_DB
                existing = db_manager.execute_query(
                    "SELECT cantidad FROM INVENTARIO_USUARIO WHERE userID = ? AND item_nombre = ?",
                    (user_id, objeto_previo),
                )
                if existing:
                    db_manager.execute_update(
                        "UPDATE INVENTARIO_USUARIO SET cantidad = cantidad + 1 "
                        "WHERE userID = ? AND item_nombre = ?",
                        (user_id, objeto_previo),
                    )
                else:
                    db_manager.execute_update(
                        "INSERT INTO INVENTARIO_USUARIO (userID, item_nombre, cantidad) "
                        "VALUES (?, ?, 1)",
                        (user_id, objeto_previo),
                    )

            items_service.usar_item(user_id, item_nombre, 1)
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET objeto = ? WHERE id_unico = ?",
                (item_nombre, poke_id),
            )

            nombre_poke = poke.mote or poke.nombre
            nombre_item = item_nombre.replace("_", " ").title()

            if objeto_previo:
                nombre_previo = objeto_previo.replace("_", " ").title()
                texto = (
                    f"✅ <b>{nombre_poke}</b> ahora lleva <b>{nombre_item}</b>.\n\n"
                    f"📦 <b>{nombre_previo}</b> fue guardado en la mochila."
                )
            else:
                texto = f"✅ <b>{nombre_poke}</b> ahora lleva <b>{nombre_item}</b>."

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
            ))
            MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

        except Exception as e:
            logger.error(f"[MOCHILA] Error equipando item: {e}", exc_info=True)
            MenuPokemon._edit_or_send(
                message, bot, user_id, "❌ Error al equipar el item.", types.InlineKeyboardMarkup()
            )

    @staticmethod
    def _procesar_callback_mochila(call, bot):
        try:
            data = call.data

            if data.startswith("pokebag_give_pk_"):
                partes      = data.split("_", 5)
                user_id     = int(partes[3])
                poke_id     = int(partes[4])
                item_nombre = partes[5]

                if call.from_user.id != user_id:
                    bot.answer_callback_query(call.id, "❌ Este menú no es tuyo.", show_alert=True)
                    return
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass
                MenuPokemon._procesar_dar_item(user_id, call.message, bot, poke_id, item_nombre)
                return

            partes = data.split("_", 3)
            if len(partes) < 4:
                return

            accion      = partes[1]
            user_id     = int(partes[2])
            payload     = partes[3]

            if call.from_user.id != user_id:
                bot.answer_callback_query(call.id, "❌ Este menú no es tuyo.", show_alert=True)
                return

            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass

            if accion == "cat":
                ultimo_sep = payload.rfind("_")
                if ultimo_sep == -1:
                    cat_id_bag, pagina_bag = payload, 0
                else:
                    cat_id_bag = payload[:ultimo_sep]
                    try:
                        pagina_bag = int(payload[ultimo_sep + 1:])
                    except ValueError:
                        pagina_bag = 0

                if cat_id_bag == "MT/MO":
                    MenuPokemon._mostrar_categoria_mts(user_id, call.message, bot)
                else:
                    MenuPokemon._mostrar_categoria_mochila(
                        user_id, call.message, bot, cat_id_bag, pagina_bag
                    )

            elif accion == "item":
                MenuPokemon._mostrar_detalle_item(user_id, call.message, bot, payload)

            elif accion == "sell":
                MenuPokemon._procesar_venta_item(user_id, call.message, bot, payload)

            elif accion == "use":
                if payload.startswith("mt") or payload.startswith("mo"):
                    from pokemon.mt_system import MT_MAP
                    # Solo abrir selector de MT si es realmente una MT
                    if payload in MT_MAP:
                        from pokemon.mt_system import iniciar_uso_mt
                        iniciar_uso_mt(user_id, payload, call.message, bot)
                        return
                # ── Ítems que requieren seleccionar un Pokémon ──────────────
                from pokemon.item_use_system import (
                    necesita_selector_pokemon,
                    mostrar_selector_pokemon,
                )
                if necesita_selector_pokemon(payload):
                    mostrar_selector_pokemon(user_id, payload, call.message, bot)
                    return
                # ── Ítems de consumo directo (medicinas, vitaminas…) ────────
                from pokemon.services import items_service
                ok, msg = items_service.usar_item(user_id, payload, 1)
                texto   = f"✅ {msg}" if ok else f"❌ {msg}"
                markup  = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(
                    "⬅️ Mochila", callback_data=f"pokemenu_bag_{user_id}"
                ))
                MenuPokemon._edit_or_send(call.message, bot, user_id, texto, markup)

            elif accion == "usemt":
                from pokemon.mt_system import MT_MAP, iniciar_uso_mt
                if payload in MT_MAP:
                    iniciar_uso_mt(user_id, payload, call.message, bot)
                else:
                    # No es una MT real, ignorar silenciosamente
                    logger.warning(f"[MOCHILA] usemt recibido para item no-MT: {payload}")

            elif accion == "give":
                MenuPokemon._mostrar_dar_item(user_id, call.message, bot, payload)

        except Exception as e:
            logger.error(f"[MOCHILA] Error en _procesar_callback_mochila: {e}", exc_info=True)
            try:
                bot.answer_callback_query(call.id, "❌ Error interno.", show_alert=True)
            except Exception:
                pass

    # ── PC ────────────────────────────────────────────────────────────────────

    @staticmethod
    def _mostrar_pc(user_id: int, message, bot, pagina: int = 0):
        PC_COLS = 4
        PC_PAGE = 20

        pc_total   = pokemon_service.obtener_pc(user_id, limit=9999)
        total      = len(pc_total)
        total_pags = max(1, math.ceil(total / PC_PAGE))
        pagina     = max(0, min(pagina, total_pags - 1))

        inicio = pagina * PC_PAGE
        pc     = pc_total[inicio: inicio + PC_PAGE]

        if total:
            texto = (
                f"💻 <b>PC POKÉMON</b>  <i>Pág. {pagina+1}/{total_pags}</i>\n"
                f"Total almacenados: <b>{total}</b>\n\n"
                f"Pulsa un Pokémon para ver sus datos."
            )
        else:
            texto = (
                f"💻 <b>PC POKÉMON</b>  <i>Pág. {pagina+1}/{total_pags}</i>\n\n"
                f"No tienes Pokémon almacenados en el PC."
            )

        markup = types.InlineKeyboardMarkup(row_width=PC_COLS)
        fila   = []
        for p in pc:
            sexo   = {"M": "♂", "F": "♀"}.get(getattr(p, "sexo", None) or "", "")
            shiny  = "✨" if getattr(p, "shiny", False) else ""
            nombre = (p.mote or p.nombre)[:8]
            label  = f"{shiny}{nombre}{sexo}·{p.nivel}"
            fila.append(types.InlineKeyboardButton(
                label,
                callback_data=f"pokemenu_pcpoke_{user_id}_{p.id_unico}_{pagina}"
            ))
            if len(fila) == PC_COLS:
                markup.row(*fila)
                fila = []
        if fila:
            markup.row(*fila)

        nav = []
        if pagina > 0:
            nav.append(types.InlineKeyboardButton(
                "◀️", callback_data=f"pokemenu_pcpage_{user_id}_{pagina - 1}"
            ))
        if pagina < total_pags - 1:
            nav.append(types.InlineKeyboardButton(
                "▶️", callback_data=f"pokemenu_pcpage_{user_id}_{pagina + 1}"
            ))
        if nav:
            markup.row(*nav)

        equipo_actual = pokemon_service.obtener_equipo(user_id)
        if len(equipo_actual) > 1:
            markup.add(types.InlineKeyboardButton(
                "📥 Depositar Pokémon",
                callback_data=f"pokemenu_pcdep_{user_id}_0_{pagina}"
            ))

        markup.add(types.InlineKeyboardButton(
            "⬅️ Volver", callback_data=f"pokemenu_back_{user_id}"
        ))
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    @staticmethod
    def _mostrar_pc_pokemon(user_id: int, pokemon_id: int, pagina: int, message, bot):
        p = pokemon_service.obtener_pokemon(pokemon_id)
        if not p:
            bot.send_message(user_id, "❌ Pokémon no encontrado.")
            return

        sexo   = {"M": " ♂", "F": " ♀"}.get(getattr(p, "sexo", None) or "", "")
        shiny  = " ✨" if getattr(p, "shiny", False) else ""
        nombre = p.mote or p.nombre
        hp_max = p.stats.get("hp", 1) or 1
        nat    = getattr(p, "naturaleza", "—") or "—"
        hab    = getattr(p, "habilidad", "—") or "—"

        from pokemon.services.pokedex_service import pokedex_service as _pdx
        tipos_raw = _pdx.obtener_tipos(p.pokemonID) or []
        tipo_emojis = {
            "Fuego": "🔥", "Agua": "💧", "Planta": "🌿", "Eléctrico": "⚡",
            "Normal": "⭐", "Lucha": "🥊", "Veneno": "☠️", "Tierra": "🌍",
            "Volador": "🦅", "Psíquico": "🔮", "Bicho": "🐛", "Roca": "🪨",
            "Fantasma": "👻", "Dragón": "🐉", "Oscuro": "🌑", "Acero": "⚙️",
            "Hielo": "❄️", "Hada": "🧚",
        }
        tipos_str = "  ".join(
            f"{tipo_emojis.get(t, '')} {t}" for t in tipos_raw
        ) or "—"

        texto = (
            f"💻 <b>{nombre}</b>{sexo}{shiny}  <code>#{p.pokemonID}</code>\n"
            f"Tipo: {tipos_str}\n"
            f"Nat.: {nat}  |  Hab.: {hab}\n\n"
            f"⭐ Nivel <b>{p.nivel}</b>\n"
            f"❤️ HP: {p.hp_actual}/{hp_max}\n"
        )

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(
                "📥 Depositar Pokemon",
                callback_data=f"pokemenu_pcdep_{user_id}_{pokemon_id}_{pagina}"
            ),
            types.InlineKeyboardButton(
                "📤 Retirar Pokemon",
                callback_data=f"pokemenu_pcmoveq_{user_id}_{pokemon_id}_{pagina}"
            ),
        )
        markup.add(
            types.InlineKeyboardButton(
                "🕊️ Liberar por cosmos",
                callback_data=f"pokemenu_pclib_{user_id}_{pokemon_id}_{pagina}"
            ),
        )
        markup.add(types.InlineKeyboardButton(
            "⬅️ Volver al PC",
            callback_data=f"pokemenu_pcpage_{user_id}_{pagina}"
        ))
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    # ── EQUIPO ────────────────────────────────────────────────────────────────

    @staticmethod
    def _construir_equipo(user_id: int):
        equipo = pokemon_service.obtener_equipo(user_id)
        texto  = "👥 <b>TU EQUIPO</b>\n\nToca un Pokémon para ver sus estadísticas.\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)

        if not equipo:
            texto += "No tienes Pokémon en tu equipo."
        else:
            for poke in equipo:
                hp_max = poke.stats.get("hp", 1) or 1
                hp_pct = int(poke.hp_actual / hp_max * 100)
                if poke.hp_actual <= 0:
                    est = "💀"
                elif hp_pct >= 80:
                    est = "💚"
                elif hp_pct >= 40:
                    est = "💛"
                else:
                    est = "🔴"
                sexo   = {"M": " ♂", "F": " ♀"}.get(getattr(poke, "sexo", None) or "", "")
                shiny  = " ✨" if getattr(poke, "shiny", False) else ""
                nombre = poke.mote or poke.nombre
                label = f"{est} {nombre}{sexo}{shiny} Nv.{poke.nivel}  HP:{poke.hp_actual}/{hp_max}"
                markup.add(types.InlineKeyboardButton(
                    label,
                    callback_data=f"pokemenu_poke_{user_id}_{poke.id_unico}"
                ))
        if equipo and len(equipo) > 1:
            markup.add(types.InlineKeyboardButton(
                "🔀 Ordenar", callback_data=f"pokemenu_ordenar_{user_id}"
            ))
        markup.add(types.InlineKeyboardButton(
            "⬅️ Volver", callback_data=f"pokemenu_back_{user_id}"
        ))
        return texto, markup

    @staticmethod
    def _mostrar_equipo(user_id: int, message, bot):
        texto, markup = MenuPokemon._construir_equipo(user_id)
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    @staticmethod
    def _mostrar_modo_ordenar(user_id: int, message, bot):
        equipo = pokemon_service.obtener_equipo(user_id)

        texto  = "🔀 <b>ORDENAR EQUIPO</b>\n\nUsá las flechas para cambiar el orden:"
        markup = types.InlineKeyboardMarkup()

        for i, poke in enumerate(equipo):
            es_primero = (i == 0)
            es_ultimo  = (i == len(equipo) - 1)
            shiny  = "✨" if getattr(poke, "shiny", False) else ""
            nombre = (poke.mote or poke.nombre)[:14]

            markup.row(
                types.InlineKeyboardButton(
                    "▲" if not es_primero else "·",
                    callback_data=f"pokemenu_moveup_{user_id}_{poke.id_unico}"
                    if not es_primero else f"pokemenu_noop_{user_id}"
                ),
                types.InlineKeyboardButton(
                    f"{shiny}{nombre} Nv.{poke.nivel}",
                    callback_data=f"pokemenu_noop_{user_id}"
                ),
                types.InlineKeyboardButton(
                    "▼" if not es_ultimo else "·",
                    callback_data=f"pokemenu_movedown_{user_id}_{poke.id_unico}"
                    if not es_ultimo else f"pokemenu_noop_{user_id}"
                ),
            )

        markup.add(types.InlineKeyboardButton(
            "✅ Listo", callback_data=f"pokemenu_team_{user_id}"
        ))
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    # ── DETALLE POKÉMON ───────────────────────────────────────────────────────

    @staticmethod
    def _mostrar_detalle_pokemon(user_id: int, pokemon_id: int, message, bot):
        from pokemon.experience_system import ExperienceSystem
        from pokemon.services.pokedex_service import pokedex_service as _pdx

        p = pokemon_service.obtener_pokemon(pokemon_id)
        if not p:
            try:
                bot.answer_callback_query(message.id, "❌ Pokémon no encontrado.")
            except Exception:
                pass
            return

        nombre       = p.mote or p.nombre
        especie      = p.nombre if p.mote else ""
        shiny_sym    = "✨ " if getattr(p, "shiny", False) else ""
        sexo_s       = {"M": " ♂", "F": " ♀"}.get(getattr(p, "sexo", None) or "", "")
        nat          = getattr(p, "naturaleza", "—") or "—"
        hab          = getattr(p, "habilidad",  "—") or "—"
        especie_str  = f" <i>({especie})</i>" if especie else ""
        tipos        = _pdx.obtener_tipos(p.pokemonID)
        tipos_str    = " / ".join(tipos)

        exp_actual  = p.exp or 0
        exp_req     = ExperienceSystem.exp_necesaria_para_nivel(p.nivel)
        pct_exp10   = min(10, int(exp_actual / max(1, exp_req) * 10))
        barra_exp   = "█" * pct_exp10 + "░" * (10 - pct_exp10)

        s       = p.stats or {}
        hp_max  = s.get("hp", p.hp_actual) or p.hp_actual
        hp_act  = p.hp_actual
        pct_hp  = min(10, int(hp_act / max(1, hp_max) * 10))
        bloque_hp = "🟩" if pct_hp > 6 else ("🟨" if pct_hp > 3 else "🟥")
        barra_hp  = bloque_hp * pct_hp + "⬛" * (10 - pct_hp)

        iv = p.ivs or {}
        ev = p.evs or {}
        sb = _pdx.obtener_stats_base(p.pokemonID) or {}

        STAT_KEYS = [
            ("hp",     "HP    "),
            ("atq",    "Ataque"),
            ("def",    "Defens"),
            ("atq_sp", "At.Esp"),
            ("def_sp", "Df.Esp"),
            ("vel",    "Veloc."),
        ]

        def _iv_bar(v: int) -> str:
            filled = round(v / 31 * 5)
            return "▰" * filled + "▱" * (5 - filled)

        from pokemon.services.pokedex_service import _NATURALEZAS
        _nat_data   = _NATURALEZAS.get(nat, {})
        _stat_sube  = _nat_data.get("sube")
        _stat_baja  = _nat_data.get("baja")

        rows = ""
        for key, label in STAT_KEYS:
            if key == "hp":
                mod = " "
            elif key == _stat_sube:
                mod = "+"
            elif key == _stat_baja:
                mod = "-"
            else:
                mod = " "
            rows += (
                f"  {label}{mod}{s.get(key,0):>4} "
                f"B:{sb.get(key,0):>3} "
                f"IV:{iv.get(key,0):>2}{_iv_bar(iv.get(key,0))} "
                f"EV:{ev.get(key,0):>3}\n"
            )

        total_iv  = sum(iv.get(k, 0) for k, _ in STAT_KEYS)
        pct_ivs   = round(total_iv / 186 * 100, 1)
        total_ev  = sum(ev.get(k, 0) for k, _ in STAT_KEYS)

        try:
            from pokemon.services.crianza_service import GRUPOS_HUEVOS
            grupos_ids = GRUPOS_HUEVOS.get(p.pokemonID, [])
            grupo_str  = ", ".join(grupos_ids) if grupos_ids else "Desconocido"
        except Exception:
            grupo_str = "—"

        movs = getattr(p, "movimientos", []) or []
        try:
            from pokemon.wild_battle_system import MOVE_NAMES_ES
        except ImportError:
            MOVE_NAMES_ES = {}
        movs_lines = []
        for mv in movs:
            if mv:
                key = mv.lower().replace(" ", "").replace("-", "")
                movs_lines.append(f"  • {MOVE_NAMES_ES.get(key, mv.title())}")
        movs_txt = "\n".join(movs_lines) if movs_lines else "  —"

        objeto     = getattr(p, "objeto", None)
        objeto_txt = (
            f"🎒 <b>Objeto:</b> {objeto.replace('_',' ').title()}"
            if objeto else
            "🎒 <b>Objeto:</b> Ninguno"
        )

        texto = (
            f"{shiny_sym}┌─ <b>{nombre}</b>{especie_str}{sexo_s}  <code>#{p.pokemonID}</code>\n"
            f"├ Tipo: {tipos_str}\n"
            f"├ Nat.: {nat}  |  Hab.: {hab}\n"
            f"└──────────────────────────────\n\n"
            f"⭐ <b>Nivel {p.nivel}</b>\n"
            f"📊 EXP: {exp_actual:,} / {exp_req:,}\n"
            f"   [{barra_exp}] {pct_exp10*10}%\n\n"
            f"❤️ HP: {hp_act:,} / {hp_max:,}\n"
            f"   {barra_hp}\n\n"
            f"<b>STATS</b> <i>(stat | base | IV▰▱ | EV)</i>\n"
            f"<code>{rows}</code>"
            f"🔬 IVs: {total_iv}/186 ({pct_ivs}% perfección)\n"
            f"💪 EVs: {total_ev}/510\n\n"
            f"🥚 <b>Grupo huevo:</b> {grupo_str}\n\n"
            f"<b>Movimientos:</b>\n{movs_txt}\n\n"
            f"{objeto_txt}"
        )

        markup = types.InlineKeyboardMarkup(row_width=1)
        if objeto:
            markup.add(types.InlineKeyboardButton(
                f"❌ Desequipar {objeto.replace('_',' ').title()}",
                callback_data=f"pokemenu_unequip_{user_id}_{pokemon_id}",
            ))
        markup.add(types.InlineKeyboardButton(
            "🕊️ Liberar (recompensa en cosmos)",
            callback_data=f"pokemenu_liberarconfirm_{user_id}_{pokemon_id}"
        ))
        markup.add(types.InlineKeyboardButton(
            "⬅️ Equipo", callback_data=f"pokemenu_teamfresh_{user_id}"
        ))

        sprite_url = p.get_sprite_animado()

        try:
            bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass

        if sprite_url:
            if sprite_url.endswith(".gif"):
                try:
                    import requests as _req, io as _io
                    _r = _req.get(sprite_url, timeout=6)
                    _r.raise_for_status()
                    _buf = _io.BytesIO(_r.content)
                    _buf.name = f"{p.pokemonID}.gif"
                    bot.send_animation(
                        user_id, _buf,
                        caption=texto, parse_mode="HTML",
                        reply_markup=markup,
                        width=96, height=96,
                    )
                    return
                except Exception:
                    pass
            try:
                bot.send_animation(
                    user_id, sprite_url,
                    caption=texto, parse_mode="HTML", reply_markup=markup,
                )
                return
            except Exception:
                pass
            try:
                bot.send_photo(
                    user_id, sprite_url,
                    caption=texto, parse_mode="HTML", reply_markup=markup,
                )
                return
            except Exception:
                pass

        bot.send_message(user_id, texto, parse_mode="HTML", reply_markup=markup)

    @staticmethod
    def _procesar_desequipar_item(user_id: int, pokemon_id: int, call, bot):
        from pokemon.services import items_service as _items_svc
        from database import db_manager

        try:
            poke = pokemon_service.obtener_pokemon(pokemon_id)
            if not poke or poke.usuario_id != user_id:
                try:
                    bot.answer_callback_query(call.id, "❌ Pokémon no encontrado.", show_alert=True)
                except Exception:
                    pass
                return

            objeto = poke.objeto
            if not objeto:
                try:
                    bot.answer_callback_query(call.id, "⚠️ Sin objeto equipado.", show_alert=True)
                except Exception:
                    pass
                return

            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET objeto = NULL WHERE id_unico = ?",
                (pokemon_id,),
            )
            # Devolver al inventario de forma robusta (mismo fix que _procesar_dar_item)
            existing = db_manager.execute_query(
                "SELECT cantidad FROM INVENTARIO_USUARIO WHERE userID = ? AND item_nombre = ?",
                (user_id, objeto),
            )
            if existing:
                db_manager.execute_update(
                    "UPDATE INVENTARIO_USUARIO SET cantidad = cantidad + 1 "
                    "WHERE userID = ? AND item_nombre = ?",
                    (user_id, objeto),
                )
            else:
                db_manager.execute_update(
                    "INSERT INTO INVENTARIO_USUARIO (userID, item_nombre, cantidad) VALUES (?, ?, 1)",
                    (user_id, objeto),
                )

            nombre_obj = objeto.replace("_", " ").title()
            try:
                bot.answer_callback_query(
                    call.id,
                    f"✅ {nombre_obj} guardado en la mochila.",
                )
            except Exception:
                pass

            MenuPokemon._mostrar_detalle_pokemon(user_id, pokemon_id, call.message, bot)

        except Exception as e:
            logger.error(f"[MENU] Error desequipando item: {e}", exc_info=True)
            try:
                bot.answer_callback_query(call.id, "❌ Error al desequipar.", show_alert=True)
            except Exception:
                pass

    # ── TIENDA ────────────────────────────────────────────────────────────────

    @staticmethod
    def _mostrar_tienda(user_id: int, message, bot):
        from pokemon.shop_system import ShopSystem
        from funciones import economy_service

        catalogo = ShopSystem.obtener_catalogo_completo()
        saldo    = economy_service.get_balance(user_id)

        texto  = f"🏪 <b>TIENDA POKÉMON</b>\n\n💰 Saldo: <b>{saldo} Cosmos</b>\n\nElige una categoría:"
        markup = types.InlineKeyboardMarkup(row_width=2)

        cats_ordenadas = sorted(catalogo.items(), key=lambda x: x[1].get("orden", 99))
        botones = [
            types.InlineKeyboardButton(
                data["nombre"],
                callback_data=f"pokeshop_cat_{user_id}_{cat_id}_0",
            )
            for cat_id, data in cats_ordenadas
        ]

        for i in range(0, len(botones), 2):
            markup.row(*botones[i:i + 2])

        markup.add(types.InlineKeyboardButton(
            "⬅️ Volver", callback_data=f"pokemenu_back_{user_id}"
        ))
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    @staticmethod
    def _mostrar_tienda_categoria(user_id: int, message, bot, cat_id: str, pagina: int = 0):
        from pokemon.shop_system import ShopSystem
        from funciones import economy_service

        exito, cat_nombre, items_list = ShopSystem.obtener_categoria(cat_id)
        if not exito:
            bot.answer_callback_query(
                message.id if hasattr(message, "id") else 0,
                "❌ Categoría no encontrada.", show_alert=True
            )
            return

        saldo      = economy_service.get_balance(user_id)
        total_pags = max(1, math.ceil(len(items_list) / _SHOP_PAGE_SIZE))
        pagina     = max(0, min(pagina, total_pags - 1))
        inicio     = pagina * _SHOP_PAGE_SIZE
        items_pag  = items_list[inicio: inicio + _SHOP_PAGE_SIZE]

        texto = (
            f"🏪 <b>{cat_nombre}</b>\n"
            f"💰 Saldo: <b>{saldo} Cosmos</b>\n"
            f"Página {pagina + 1}/{total_pags}\n\n"
        )
        for item in items_pag:
            desc_safe = _html.escape(str(item.get('desc') or ''))
            texto += f"• <b>{_html.escape(str(item['id']))}</b> — {item['precio']} Cosmos\n  {desc_safe}\n\n"

        markup = types.InlineKeyboardMarkup(row_width=3)
        for item in items_pag:
            markup.row(
                types.InlineKeyboardButton(
                    f"{item['id']} ×1",
                    callback_data=f"pokeshop_buy_{user_id}_{cat_id}|{item['id']}_1",
                ),
                types.InlineKeyboardButton(
                    "×5",
                    callback_data=f"pokeshop_buy_{user_id}_{cat_id}|{item['id']}_5",
                ),
                types.InlineKeyboardButton(
                    "×10",
                    callback_data=f"pokeshop_buy_{user_id}_{cat_id}|{item['id']}_10",
                ),
            )

        nav_row = []
        if pagina > 0:
            nav_row.append(types.InlineKeyboardButton(
                "⬅",
                callback_data=f"pokeshop_cat_{user_id}_{cat_id}_{pagina - 1}",
            ))
        if pagina < total_pags - 1:
            nav_row.append(types.InlineKeyboardButton(
                "➡",
                callback_data=f"pokeshop_cat_{user_id}_{cat_id}_{pagina + 1}",
            ))
        if nav_row:
            markup.row(*nav_row)

        markup.row(
            types.InlineKeyboardButton("🏪 Categorías", callback_data=f"pokemenu_shop_{user_id}"),
            types.InlineKeyboardButton("🏠 Menú",        callback_data=f"pokemenu_back_{user_id}"),
        )

        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    @staticmethod
    def _procesar_callback_tienda(call, bot):
        try:
            data = call.data

            if data.startswith("pokeshop_noop_"):
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass
                return

            parts = data.split("_", 3)
            if len(parts) < 4:
                return

            accion  = parts[1]
            user_id = int(parts[2])
            resto   = parts[3]

            if call.from_user.id != user_id:
                bot.answer_callback_query(call.id, "❌ Este menú no es tuyo.", show_alert=True)
                return

            if accion == "cat":
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass
                ultimo_sep = resto.rfind("_")
                if ultimo_sep == -1:
                    cat_id, pagina = resto, 0
                else:
                    cat_id = resto[:ultimo_sep]
                    try:
                        pagina = int(resto[ultimo_sep + 1:])
                    except ValueError:
                        pagina = 0
                MenuPokemon._mostrar_tienda_categoria(user_id, call.message, bot, cat_id, pagina)

            elif accion == "buy":
                try:
                    bot.answer_callback_query(call.id)
                except Exception:
                    pass
                ultimo_sep = resto.rfind("_")
                if ultimo_sep == -1:
                    bot.answer_callback_query(call.id, "❌ Datos de compra inválidos.", show_alert=True)
                    return
                cat_item_str = resto[:ultimo_sep]
                try:
                    qty = int(resto[ultimo_sep + 1:])
                except ValueError:
                    bot.answer_callback_query(call.id, "❌ Cantidad inválida.", show_alert=True)
                    return
                if "|" not in cat_item_str:
                    bot.answer_callback_query(call.id, "❌ Item inválido.", show_alert=True)
                    return
                cat_id, item_id = cat_item_str.split("|", 1)
                MenuPokemon._ejecutar_compra(user_id, call, bot, cat_id, item_id, qty)

        except Exception as e:
            logger.error(f"[SHOP] Error en callback tienda: {e}", exc_info=True)
            try:
                bot.answer_callback_query(call.id, "❌ Error interno.", show_alert=True)
            except Exception:
                pass

    @staticmethod
    def _ejecutar_compra(user_id: int, call, bot, cat_id: str, item_id: str, qty: int):
        from pokemon.shop_system import ShopSystem
        import re
        import threading

        exito, mensaje = ShopSystem.comprar_item(user_id, item_id, qty)

        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass

        texto_limpio = re.sub(r"<[^>]+>", "", mensaje)

        if exito:
            item_info = __import__(
                "pokemon.items_database_complete", fromlist=["obtener_item_info"]
            ).obtener_item_info(item_id)
            precio_u = item_info.get("precio", 0) if item_info else 0
            texto_feedback = (
                f"✅ <b>Compra exitosa</b>\n"
                f"🛒 {qty}× <b>{item_id}</b>\n"
                f"💸 Se te cobraron <b>{precio_u * qty} cosmos</b>"
            )
        else:
            texto_feedback = f"❌ <b>No se pudo completar la compra</b>\n{texto_limpio}"

        try:
            msg = bot.send_message(user_id, texto_feedback, parse_mode="HTML")

            def _borrar():
                try:
                    bot.delete_message(user_id, msg.message_id)
                except Exception:
                    pass
            threading.Timer(6.0, _borrar).start()
        except Exception:
            pass

        try:
            MenuPokemon._mostrar_tienda_categoria(user_id, call.message, bot, cat_id, 0)
        except Exception:
            MenuPokemon._mostrar_tienda(user_id, call.message, bot)

    # ── CENTRO POKÉMON ────────────────────────────────────────────────────────

    @staticmethod
    def _mostrar_centro(user_id: int, message, bot):
        try:
            from pokemon.wild_battle_system import wild_battle_manager
            from pokemon.gym_battle_system import gym_manager
            from pokemon.pvp_battle_system import pvp_manager
            if (
                wild_battle_manager.has_active_battle(user_id)
                or gym_manager.has_active_battle(user_id)
                or pvp_manager.has_active_battle(user_id)
            ):
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(
                    "⬅️ Volver", callback_data=f"pokemenu_back_{user_id}"
                ))
                MenuPokemon._edit_or_send(
                    message, bot, user_id,
                    "⚔️ <b>¡Estás en combate!</b>\n\n"
                    "No puedes usar el Centro Pokémon durante una batalla.\n"
                    "Termina o huye del combate primero.",
                    markup,
                )
                return
        except Exception:
            pass

        estado = centro_pokemon.verificar_estado_equipo(user_id)

        texto = f"⭐ <b>CENTRO POKÉMON</b>\n\n💰 Costo: <b>{centro_pokemon.COSTO_CURACION}</b> cosmos\n\n"

        if estado["total"] == 0:
            texto += "❌ No tienes Pokémon."
        elif not estado["necesita_curacion"]:
            texto += "✅ Tus Pokémon están completamente curados."
        else:
            texto += (
                f"📊 <b>Estado del equipo:</b>\n"
                f"💚 Sanos: {estado['sanos']}\n"
                f"💛 Heridos: {estado['heridos']}\n"
                f"💀 Debilitados: {estado['debilitados']}\n\n"
                "¿Deseas curar a tus Pokémon?"
            )

        markup = types.InlineKeyboardMarkup()
        if estado["necesita_curacion"]:
            markup.add(types.InlineKeyboardButton(
                f"✨ Curar ({centro_pokemon.COSTO_CURACION} cosmos)",
                callback_data=f"pokemenu_heal_{user_id}",
            ))
        markup.add(types.InlineKeyboardButton(
            "⬅️ Volver", callback_data=f"pokemenu_back_{user_id}"
        ))
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    @staticmethod
    def _procesar_curacion(user_id: int, call, bot):
        try:
            from pokemon.wild_battle_system import wild_battle_manager
            from pokemon.gym_battle_system import gym_manager
            from pokemon.pvp_battle_system import pvp_manager
            if (
                wild_battle_manager.has_active_battle(user_id)
                or gym_manager.has_active_battle(user_id)
                or pvp_manager.has_active_battle(user_id)
            ):
                bot.answer_callback_query(
                    call.id,
                    "⚔️ No puedes curar durante un combate.",
                    show_alert=True,
                )
                return
        except Exception:
            pass

        ok, msg = centro_pokemon.curar_equipo(user_id)
        try:
            bot.answer_callback_query(call.id, "✅ Curado!" if ok else "❌ Error", show_alert=False)
        except Exception:
            pass
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "⬅️ Volver", callback_data=f"pokemenu_back_{user_id}"
        ))
        MenuPokemon._edit_or_send(call.message, bot, user_id, msg, markup)

    @staticmethod
    def _procesar_liberar_pokemon(user_id: int, pokemon_id: int, call, bot):
        from funciones import economy_service as _econ
        from database import db_manager as _db
        try:
            p = pokemon_service.obtener_pokemon(pokemon_id)
            if not p:
                bot.answer_callback_query(call.id, "❌ Pokémon no encontrado.", show_alert=True)
                return

            equipo = pokemon_service.obtener_equipo(user_id)
            if len(equipo) <= 1:
                bot.answer_callback_query(
                    call.id, "❌ No puedes liberar a tu último Pokémon.", show_alert=True
                )
                return

            nombre     = p.mote or p.nombre
            recompensa = p.nivel * 10

            _db.execute_update(
                "DELETE FROM POKEMON_USUARIO WHERE id_unico = ? AND userID = ?",
                (pokemon_id, user_id)
            )
            pokemon_service.inicializar_posiciones_equipo(user_id)
            _econ.add_credits(user_id, recompensa, f"Liberación de {nombre}")

            bot.answer_callback_query(call.id, f"🕊️ {nombre} fue liberado.")
            markup_ret = types.InlineKeyboardMarkup()
            markup_ret.add(types.InlineKeyboardButton(
                "⬅️ Equipo", callback_data=f"pokemenu_team_{user_id}"
            ))
            texto_ret = (
                f"🕊️ ¡<b>{nombre}</b> fue liberado!\n"
                f"💰 Recibiste <b>{recompensa} cosmos</b>."
            )
            MenuPokemon._edit_or_send(call.message, bot, user_id, texto_ret, markup_ret)

        except Exception as e:
            logger.error(f"[LIBERAR] Error: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "❌ Error al liberar.", show_alert=True)

    # ── PC: LIBERAR DESDE PC ──────────────────────────────────────────────────

    @staticmethod
    def _mostrar_pc_liberar_confirm(user_id: int, pokemon_id: int, pagina: int, message, bot):
        p = pokemon_service.obtener_pokemon(pokemon_id)
        if not p or p.usuario_id != user_id:
            bot.send_message(user_id, "❌ Pokémon no encontrado.")
            return

        nombre     = p.mote or p.nombre
        recompensa = p.nivel * 10

        texto = (
            f"🕊️ <b>¿Liberar a {nombre}?</b>\n\n"
            f"Nivel: <b>{p.nivel}</b>\n"
            f"Recibirás: <b>{recompensa} cosmos</b>\n\n"
            "⚠️ Esta acción es <b>irreversible</b>."
        )
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(
                "✅ Sí, liberar",
                callback_data=f"pokemenu_pclibera_{user_id}_{pokemon_id}_{pagina}",
            ),
            types.InlineKeyboardButton(
                "❌ Cancelar",
                callback_data=f"pokemenu_pcpoke_{user_id}_{pokemon_id}_{pagina}",
            ),
        )
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    @staticmethod
    def _procesar_liberar_desde_pc(user_id: int, pokemon_id: int, pagina: int, call, bot):
        from funciones import economy_service as _econ
        from database import db_manager as _db

        try:
            p = pokemon_service.obtener_pokemon(pokemon_id)
            if not p or p.usuario_id != user_id:
                bot.answer_callback_query(
                    call.id, "❌ Pokémon no encontrado.", show_alert=True
                )
                return

            if getattr(p, "en_equipo", False):
                bot.answer_callback_query(
                    call.id,
                    "❌ Este Pokémon está en tu equipo, no en el PC.",
                    show_alert=True,
                )
                return

            nombre     = p.mote or p.nombre
            recompensa = p.nivel * 10

            _db.execute_update(
                "DELETE FROM POKEMON_USUARIO WHERE id_unico = ? AND userID = ?",
                (pokemon_id, user_id),
            )
            _econ.add_credits(user_id, recompensa, f"Liberación PC: {nombre}")

            bot.answer_callback_query(call.id, f"🕊️ ¡{nombre} fue liberado!")

            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton(
                    "⬅️ Volver al PC",
                    callback_data=f"pokemenu_pcpage_{user_id}_{pagina}",
                )
            )
            texto = (
                f"🕊️ ¡<b>{nombre}</b> fue liberado!\n"
                f"💰 Recibiste <b>{recompensa} cosmos</b>."
            )
            MenuPokemon._edit_or_send(call.message, bot, user_id, texto, markup)

        except Exception as e:
            logger.error(f"[PC-LIBERAR] Error: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "❌ Error al liberar.", show_alert=True)

    @staticmethod
    def _mostrar_pc_swap_equipo(user_id: int, pid_pc: int, pagina: int, message, bot):
        p_pc   = pokemon_service.obtener_pokemon(pid_pc)
        equipo = pokemon_service.obtener_equipo(user_id)

        if not p_pc or not equipo:
            bot.send_message(user_id, "❌ No se pudo realizar el intercambio.")
            return

        nombre_pc = p_pc.mote or p_pc.nombre
        texto = (
            f"🔄 <b>Equipo lleno</b>\n\n"
            f"Quieres retirar a <b>{nombre_pc}</b> (Nv.{p_pc.nivel}).\n"
            f"Elige cuál Pokémon de tu equipo enviar al PC a cambio:"
        )

        markup = types.InlineKeyboardMarkup(row_width=1)
        for poke in equipo:
            hp_max = poke.stats.get("hp", 1) or 1
            hp_pct = int(poke.hp_actual / hp_max * 100)
            est    = "💀" if poke.hp_actual <= 0 else ("💚" if hp_pct >= 70 else "🔴")
            sexo   = {"M": " ♂", "F": " ♀"}.get(getattr(poke, "sexo", None) or "", "")
            shiny  = " ✨" if getattr(poke, "shiny", False) else ""
            label  = f"{est} {poke.mote or poke.nombre}{sexo}{shiny} Nv.{poke.nivel}"
            markup.add(
                types.InlineKeyboardButton(
                    label,
                    callback_data=(
                        f"pokemenu_pcswap_{user_id}_{pid_pc}_{poke.id_unico}_{pagina}"
                    ),
                )
            )

        markup.add(
            types.InlineKeyboardButton(
                "❌ Cancelar",
                callback_data=f"pokemenu_pcpoke_{user_id}_{pid_pc}_{pagina}",
            )
        )
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    @staticmethod
    def _mostrar_selector_depositar(user_id: int, pid_ref: int, pagina: int, message, bot):
        equipo = pokemon_service.obtener_equipo(user_id)

        if not equipo:
            bot.send_message(user_id, "❌ Tu equipo está vacío.")
            return

        if len(equipo) == 1:
            bot.send_message(
                user_id,
                "❌ No puedes depositar tu último Pokémon.\n"
                "Necesitas al menos uno en el equipo."
            )
            return

        texto  = "📥 <b>¿Cuál Pokémon depositar en el PC?</b>\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)

        for p in equipo:
            hp_max = p.stats.get("hp", 1) or 1
            hp_pct = int(p.hp_actual / hp_max * 100)
            est    = "💀" if p.hp_actual <= 0 else ("💚" if hp_pct >= 70 else "🔴")
            sexo   = {"M": " ♂", "F": " ♀"}.get(getattr(p, "sexo", None) or "", "")
            shiny  = " ✨" if getattr(p, "shiny", False) else ""
            label  = f"{est} {p.mote or p.nombre}{sexo}{shiny} Nv.{p.nivel}"
            markup.add(types.InlineKeyboardButton(
                label,
                callback_data=f"pokemenu_pcdepok_{user_id}_{p.id_unico}_{pagina}"
            ))

        markup.add(types.InlineKeyboardButton(
            "❌ Cancelar",
            callback_data=f"pokemenu_pcpage_{user_id}_{pagina}"
        ))
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    @staticmethod
    def _procesar_depositar(user_id: int, pid_equipo: int, pagina: int, call, bot):
        from database import db_manager as _db

        try:
            equipo = pokemon_service.obtener_equipo(user_id)
            if len(equipo) <= 1:
                bot.answer_callback_query(
                    call.id,
                    "❌ No puedes depositar tu último Pokémon.",
                    show_alert=True,
                )
                return

            p = pokemon_service.obtener_pokemon(pid_equipo)
            if not p or p.usuario_id != user_id:
                bot.answer_callback_query(call.id, "❌ Pokémon no encontrado.", show_alert=True)
                return

            if not getattr(p, "en_equipo", False):
                bot.answer_callback_query(
                    call.id, "❌ Este Pokémon ya está en el PC.", show_alert=True
                )
                return

            _db.execute_update(
                "UPDATE POKEMON_USUARIO SET en_equipo = 0, posicion_equipo = NULL "
                "WHERE id_unico = ? AND userID = ?",
                (pid_equipo, user_id),
            )
            pokemon_service.inicializar_posiciones_equipo(user_id)

            nombre = p.mote or p.nombre
            bot.answer_callback_query(call.id, f"📥 {nombre} fue depositado en el PC.")
            MenuPokemon._mostrar_pc(user_id, call.message, bot, pagina=pagina)

        except Exception as e:
            logger.error(f"[PC-DEPOSITAR] Error: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "❌ Error al depositar.", show_alert=True)

    @staticmethod
    def _procesar_pc_swap(user_id: int, pid_pc: int, pid_equipo: int, pagina: int, call, bot):
        from database import db_manager as _db

        try:
            p_pc     = pokemon_service.obtener_pokemon(pid_pc)
            p_equipo = pokemon_service.obtener_pokemon(pid_equipo)

            if not p_pc or not p_equipo:
                bot.answer_callback_query(
                    call.id, "❌ Pokémon no encontrado.", show_alert=True
                )
                return

            if p_pc.usuario_id != user_id or p_equipo.usuario_id != user_id:
                bot.answer_callback_query(
                    call.id, "❌ Estos Pokémon no te pertenecen.", show_alert=True
                )
                return

            pos_saliente = getattr(p_equipo, "posicion_equipo", 0) or 0

            _db.execute_update(
                "UPDATE POKEMON_USUARIO SET en_equipo = 0, posicion_equipo = NULL "
                "WHERE id_unico = ?",
                (pid_equipo,),
            )
            _db.execute_update(
                "UPDATE POKEMON_USUARIO SET en_equipo = 1, posicion_equipo = ? "
                "WHERE id_unico = ?",
                (pos_saliente, pid_pc),
            )
            pokemon_service.inicializar_posiciones_equipo(user_id)

            nombre_entra = p_pc.mote or p_pc.nombre
            nombre_sale  = p_equipo.mote or p_equipo.nombre

            bot.answer_callback_query(
                call.id,
                f"✅ {nombre_entra} entró al equipo · {nombre_sale} fue al PC",
            )
            MenuPokemon._mostrar_pc(user_id, call.message, bot, pagina=pagina)

        except Exception as e:
            logger.error(f"[PC-SWAP] Error: {e}", exc_info=True)
            bot.answer_callback_query(
                call.id, "❌ Error en el intercambio.", show_alert=True
            )

    # ── GUARDERÍA ─────────────────────────────────────────────────────────────

    @staticmethod
    def _mostrar_guarderia(user_id: int, message, bot):
        from pokemon.services.crianza_service import crianza_service

        guarderia = crianza_service.obtener_pokemon_guarderia(user_id)
        huevos    = crianza_service.obtener_huevos_usuario(user_id)

        texto = "🥚 <b>GUARDERÍA POKÉMON</b>\n\n"
        texto += "📦 <b>Slots:</b>\n"

        _slot_labels = {"poke1": "Slot 1", "poke2": "Slot 2"}
        for slot, poke in guarderia.items():
            etiqueta = _slot_labels.get(slot, slot)
            if poke:
                sexo  = {"M": " ♂", "F": " ♀"}.get(getattr(poke, "sexo", None) or "", "")
                shiny = " ✨" if getattr(poke, "shiny", False) else ""
                texto += f"  {etiqueta}: <b>{poke.mote or poke.nombre}</b>{sexo}{shiny} Nv.{poke.nivel}\n"
            else:
                texto += f"  {etiqueta}: <i>vacío</i>\n"

        texto += "\n"

        if huevos:
            texto += f"🥚 <b>Huevos:</b> {len(huevos)}\n"
            for h in huevos:
                texto += f"  • {h['nombre']} — {h.get('progreso_pct', 0)}%\n"
        else:
            texto += "No tienes huevos incubándose."

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📥 Depositar", callback_data=f"daycare_depositar_{user_id}"),
            types.InlineKeyboardButton("📤 Retirar",   callback_data=f"daycare_retirar_{user_id}"),
        )
        if huevos:
            markup.add(types.InlineKeyboardButton(
                "🥚 Retirar huevo", callback_data=f"daycare_rethuevo_{user_id}"
            ))
        markup.add(types.InlineKeyboardButton(
            "⬅️ Volver", callback_data=f"pokemenu_back_{user_id}"
        ))
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    @staticmethod
    def procesar_callback_guarderia(call, bot):
        try:
            from pokemon.guarderia_callbacks import GuarderiaCallbacks
            gc = GuarderiaCallbacks.__new__(GuarderiaCallbacks)
            gc.bot = bot
            gc._handle_daycare(call)
        except Exception as e:
            logger.error(f"[GUARDERÍA] Error en procesar_callback_guarderia: {e}", exc_info=True)

    @staticmethod
    def _guarderia_depositar(user_id: int, message, bot):
        from pokemon.services.crianza_service import crianza_service

        equipo    = pokemon_service.obtener_equipo(user_id)
        guarderia = crianza_service.obtener_pokemon_guarderia(user_id)
        en_guarderia = {
            getattr(p, "id_unico", None)
            for p in guarderia.values()
            if p is not None
        }

        texto  = "📥 <b>¿Cuál Pokémon depositar?</b>\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)

        if not equipo:
            texto += "No tienes Pokémon en tu equipo."
        else:
            for p in equipo:
                pid  = p.id_unico
                sexo  = {"M": " ♂", "F": " ♀"}.get(getattr(p, "sexo", None) or "", "")
                shiny = " ✨" if getattr(p, "shiny", False) else ""
                label = f"{p.mote or p.nombre}{sexo}{shiny} Nv.{p.nivel}"
                if pid in en_guarderia:
                    label = f"✅ {label} (ya depositado)"
                markup.add(types.InlineKeyboardButton(
                    label,
                    callback_data=f"daycare_dep_{user_id}_{pid}"
                ))

        markup.add(types.InlineKeyboardButton(
            "⬅️ Volver", callback_data=f"daycare_menu_{user_id}"
        ))
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    @staticmethod
    def _guarderia_retirar(user_id: int, message, bot):
        from pokemon.services.crianza_service import crianza_service

        guarderia = crianza_service.obtener_pokemon_guarderia(user_id)
        ocupados  = {slot: poke for slot, poke in guarderia.items() if poke is not None}

        texto  = "📤 <b>¿Cuál Pokémon retirar?</b>\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)

        _slot_labels = {"poke1": "Slot 1", "poke2": "Slot 2"}
        if not ocupados:
            texto += "No tienes Pokémon depositados."
        else:
            for slot, poke in ocupados.items():
                etiqueta = _slot_labels.get(slot, slot)
                sexo  = {"M": " ♂", "F": " ♀"}.get(getattr(poke, "sexo", None) or "", "")
                shiny = " ✨" if getattr(poke, "shiny", False) else ""
                label = f"{etiqueta}: {poke.mote or poke.nombre}{sexo}{shiny} Nv.{poke.nivel}"
                markup.add(types.InlineKeyboardButton(
                    label,
                    callback_data=f"daycare_ret_{user_id}_{poke.id_unico}"
                ))

        markup.add(types.InlineKeyboardButton(
            "⬅️ Volver", callback_data=f"daycare_menu_{user_id}"
        ))
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)

    @staticmethod
    def _guarderia_retirar_huevo(user_id: int, message, bot):
        from pokemon.services.crianza_service import crianza_service
        huevos = crianza_service.obtener_huevos_usuario(user_id)

        texto  = "🥚 <b>¿Qué huevo retirar?</b>\n\n⚠️ Retirarlo lo elimina permanentemente.\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)

        for h in huevos:
            markup.add(types.InlineKeyboardButton(
                f"{h['nombre']} — {h.get('progreso_pct', 0)}%",
                callback_data=f"daycare_delhuevo_{user_id}_{h['id']}",
            ))

        markup.add(types.InlineKeyboardButton(
            "⬅️ Volver", callback_data=f"daycare_menu_{user_id}"
        ))
        MenuPokemon._edit_or_send(message, bot, user_id, texto, markup)


# ──────────────────────────────────────────────────────────────────────────────
# Instancia global
# ──────────────────────────────────────────────────────────────────────────────
menu_pokemon = MenuPokemon()