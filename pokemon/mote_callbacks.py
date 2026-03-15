# -*- coding: utf-8 -*-
"""
pokemon/mote_callbacks.py
═══════════════════════════════════════════════════════════════════════════════
Handler para los botones inline Sí / No del sistema de apodo post-captura.

Flujo:
  1. pedir_mote_pokemon()  → muestra botones [✅ Sí] [❌ No]
  2. Usuario pulsa Sí      → edita el mensaje pidiendo el apodo por texto
  3. Usuario pulsa No      → EDITA el mensaje original en el thread donde
                             está, mostrando el destino (equipo/PC) y
                             eliminando el teclado inline. Sin mensajes extra.

Integración:
    from pokemon.mote_callbacks import setup_mote_callbacks
    setup_mote_callbacks(bot)
═══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _destino_pokemon(pokemon_id: int) -> str:
    """
    Consulta la BD y devuelve una cadena legible con el destino del Pokémon.
    Retorna 'tu equipo' o 'el PC'.
    """
    try:
        from database import db_manager
        resultado = db_manager.execute_query(
            "SELECT en_equipo FROM POKEMON_USUARIO WHERE id_unico = ?",
            (pokemon_id,),
        )
        if resultado:
            return "tu equipo" if resultado[0]["en_equipo"] else "el PC"
    except Exception as e:
        logger.warning(
            f"[MOTE] No se pudo determinar destino del Pokémon {pokemon_id}: {e}"
        )
    return "tu equipo o PC"


def _editar_mensaje_mote(bot, call, texto: str) -> None:
    """
    Edita el mensaje original donde estaban los botones de mote,
    reemplazando su contenido con `texto` y eliminando el teclado inline.

    Maneja correctamente mensajes con foto/animación (edita el caption)
    y mensajes de solo texto (edita el text).
    """
    chat_id    = call.message.chat.id
    message_id = call.message.message_id

    # Mensajes con adjunto: foto, animación, documento, video → editar caption
    if call.message.content_type in ("photo", "animation", "document", "video"):
        try:
            bot.edit_message_caption(
                caption=texto,
                chat_id=chat_id,
                message_id=message_id,
                parse_mode="HTML",
                reply_markup=None,
            )
            return
        except Exception as e:
            logger.warning(f"[MOTE] edit_message_caption falló: {e}")

    # Mensaje de texto puro
    try:
        bot.edit_message_text(
            text=texto,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode="HTML",
            reply_markup=None,
        )
    except Exception as e:
        logger.warning(f"[MOTE] edit_message_text falló: {e}")


def setup_mote_callbacks(bot) -> None:
    """Registra los callbacks inline del sistema de apodo."""

    @bot.callback_query_handler(
        func=lambda c: (
            c.data.startswith("mote_si_") or c.data.startswith("mote_no_")
        )
    )
    def handle_mote_decision(call):
        from pokemon.pokemon_class import _mote_callbacks, _procesar_mote
        from pokemon.services import pokemon_service

        data    = call.data
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        # Parsear: mote_{si|no}_{owner_id}_{pokemon_id}
        try:
            partes     = data.split("_")
            accion     = partes[1]
            owner_id   = int(partes[2])
            pokemon_id = int(partes[3])
        except (IndexError, ValueError) as exc:
            logger.error(f"[MOTE] Callback malformado: {data!r} — {exc}")
            bot.answer_callback_query(call.id, "❌ Error interno.")
            return

        # Solo el dueño puede interactuar con los botones
        if user_id != owner_id:
            bot.answer_callback_query(call.id, "⛔ Este apodo no es para ti.")
            return

        # Recuperar y descartar el callback registrado
        callback = _mote_callbacks.pop(pokemon_id, None)

        # Obtener el objeto Pokémon para los mensajes
        pokemon = pokemon_service.obtener_pokemon(pokemon_id)
        if not pokemon:
            bot.answer_callback_query(call.id, "❌ No se encontró el Pokémon.")
            return

        if accion == "no":
            # Ejecutar callback con None (sin mote)
            if callback:
                callback(None)

            # Consultar destino real en la BD
            destino = _destino_pokemon(pokemon_id)

            bot.answer_callback_query(call.id, "✅ ¡Listo!")

            # Editar el mensaje original en el thread donde está,
            # eliminando los botones y mostrando el resultado.
            _editar_mensaje_mote(
                bot, call,
                f"✅ <b>{pokemon.nombre}</b> fue enviado a <b>{destino}</b> sin apodo.",
            )

        elif accion == "si":
            bot.answer_callback_query(call.id, "✍️ Escribe el apodo ahora.")

            # Editar el mensaje para quitar botones y mostrar la instrucción
            _editar_mensaje_mote(
                bot, call,
                f"✍️ Escribe el apodo para <b>{pokemon.nombre}</b> "
                f"(máx. 12 caracteres):",
            )

            # Capturar el próximo mensaje de texto del usuario en ese chat
            bot.register_next_step_handler_by_chat_id(
                chat_id,
                lambda msg: _procesar_mote(bot, msg, pokemon, callback, owner_id),
            )