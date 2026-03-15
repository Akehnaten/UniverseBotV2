# -*- coding: utf-8 -*-
"""
Guardería Steps
===============
Suma pasos al contador del usuario por cada carácter que escribe,
verifica si algún huevo eclosionó y envía la notificación con el sprite.

Cómo se integra (ver guía):
    - Se instancia en handlers/pokemon_handlers.py dentro de _register_handlers()
    - La función sumar_pasos_mensaje(bot, message) se registra como handler
      de mensajes de texto sobre TODOS los mensajes del chat privado.
"""

import logging
from telebot import types

logger = logging.getLogger(__name__)

# Estado temporal de espera de mote: {user_id: {'pokemon_id': int, 'nombre': str}}
# Importado también desde guarderia_callbacks.py para limpiarlo al pulsar "Sin apodo"
_esperando_mote: dict = {}


def sumar_pasos_mensaje(bot, message) -> None:
    """
    Llamar en cada mensaje de texto de un usuario registrado.
    Suma pasos y dispara notificaciones de eclosión si corresponde.
    """
    from pokemon.services.crianza_service import crianza_service
    from funciones import user_service

    user_id = message.from_user.id

    # Solo usuarios registrados y solo mensajes de texto
    if not message.text:
        return
    if not user_service.get_user_info(user_id):
        return

    caracteres = len(message.text)
    eclosionados = crianza_service.sumar_pasos(user_id, caracteres)

    for datos in eclosionados:
        _notificar_eclosion(bot, user_id, datos)


def _notificar_eclosion(bot, user_id: int, datos: dict) -> None:
    """Envía el mensaje de eclosión con sprite y botón 'Sin apodo'."""
    especie_id = datos['especie_id']
    sprite_url = (
        f"https://raw.githubusercontent.com/PokeAPI/sprites/master/"
        f"sprites/pokemon/versions/generation-v/black-white/animated/{especie_id}.gif"
    )

    texto = (
        f"{datos['mensaje']}\n\n"
        f"¿Deseas ponerle un apodo a {datos['nombre']}?\n"
        f"Escribe el apodo ahora, o pulsa *Sin apodo*."
    )

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "Sin apodo",
        callback_data=f"mote_no_{user_id}_{datos['pokemon_id']}"
    ))

    # Guardar estado para capturar la respuesta de texto
    _esperando_mote[user_id] = {
        'pokemon_id': datos['pokemon_id'],
        'nombre':     datos['nombre'],
    }

    try:
        bot.send_photo(user_id, photo=sprite_url,
                       caption=texto, parse_mode="Markdown",
                       reply_markup=markup)
    except Exception:
        # El GIF puede no existir para todos los números; fallback texto
        bot.send_message(user_id, texto, parse_mode="Markdown",
                         reply_markup=markup)


def interceptar_mote(bot, message) -> bool:
    """
    Si el usuario está esperando poner un mote, consume el mensaje.
    Retorna True si el mensaje fue consumido (era el mote).
    Retorna False si el mensaje debe procesarse normalmente.

    Llamar ANTES del procesado normal de comandos en pokemon_handlers.
    """
    from pokemon.services.crianza_service import crianza_service

    user_id = message.from_user.id
    if user_id not in _esperando_mote:
        return False

    datos = _esperando_mote.pop(user_id)
    texto = (message.text or "").strip()

    # "no", "-" o vacío = sin mote
    mote_final = None if texto.lower() in ("no", "sin apodo", "-", "") else texto

    ok, msg = crianza_service.finalizar_eclosion(user_id, datos['pokemon_id'], mote_final)
    bot.send_message(user_id, msg)
    return True