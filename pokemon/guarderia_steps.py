# -*- coding: utf-8 -*-
"""
pokemon/guarderia_steps.py
══════════════════════════════════════════════════════════════════════════════
Lógica de pasos de guardería disparada por mensajes en el grupo.

Diseño:
  - sumar_pasos_mensaje() se llama desde el handler de mensajes de GRUPO
    registrado en PokemonHandlers._register_handlers().
  - interceptar_mote() se llama desde el handler de mensajes PRIVADOS para
    capturar el apodo tras la eclosión.
  - La notificación de eclosión va al grupo donde el usuario habló
    (con fallback al DM si el grupo no está disponible).

Multiplicadores de pasos (se apilan):
  - Amuleto Iris (usuario):         x2 a todos los huevos.
  - Cuerpo Llama (Pokémon en equipo): x2 a todos los huevos.
  - Con ambos activos:              x4 total.
"""

import logging
from telebot import types

logger = logging.getLogger(__name__)

# Estado temporal de espera de mote: {user_id: {'pokemon_id': int, 'nombre': str}}
# También importado desde guarderia_callbacks.py para limpiarlo al pulsar "Sin apodo"
_esperando_mote: dict = {}


def sumar_pasos_mensaje(bot, message) -> None:
    """
    Llamar en cada mensaje de texto de un usuario registrado EN EL GRUPO.

    Gestiona dos sistemas de pasos completamente independientes:

    1. PRODUCCIÓN del huevo (fase de guardería):
       - Acumula pasos mientras los Pokémon están en la guardería.
       - Multiplicador: ×2 si el usuario tiene el Amuleto Iris.
       - Al llegar a PASOS_PARA_PRODUCIR_HUEVO aparece el huevo.

    2. ECLOSIÓN del huevo (huevo en el equipo):
       - Acumula pasos mientras el huevo está en el equipo del usuario.
       - Multiplicador: ×2 si hay un Pokémon con Cuerpo Llama en el equipo.
       - Nunca usa el Amuleto Iris.

    Los dos sistemas nunca se mezclan ni hay efecto ×4.
    """
    from pokemon.services.crianza_service import crianza_service
    from funciones import user_service

    if not message.text:
        return
    if not user_service.get_user_info(message.from_user.id):
        return

    user_id   = message.from_user.id
    palabras  = len(message.text.split())
    chat_id   = message.chat.id
    thread_id = getattr(message, 'message_thread_id', None) or None

    # ── Sistema 1: producción del huevo (Amuleto Iris, solo en guardería) ─────
    resultado_produccion = crianza_service.sumar_pasos_produccion(
        user_id, palabras, chat_id=chat_id, thread_id=thread_id
    )
    if resultado_produccion:
        _notificar_huevo_producido(bot, user_id, resultado_produccion)

    # ── Sistema 2: eclosión del huevo (Cuerpo Llama, solo en equipo) ──────────
    eclosionados = crianza_service.sumar_pasos(
        user_id, palabras, chat_id=chat_id, thread_id=thread_id
    )
    for datos in eclosionados:
        _notificar_eclosion(bot, user_id, datos)


def _notificar_huevo_producido(bot, user_id: int, datos: dict) -> None:
    """
    Notifica al usuario (en el grupo y en el DM) que la guardería produjo
    un huevo.  El usuario debe retirarlo para empezar a eclosionarlo.
    """
    chat_id   = datos.get('chat_id')
    thread_id = datos.get('thread_id')
    mensaje   = datos.get('mensaje', '🥚 ¡La guardería tiene un huevo!')

    # Notificación en el grupo
    if chat_id and chat_id != user_id:
        try:
            bot.send_message(
                chat_id,
                f"🥚 <a href='tg://user?id={user_id}'>¡Tu guardería tiene un huevo!</a>\n"
                f"Retiralo desde /pokemon → Guardería para empezar a eclosionarlo.",
                parse_mode="HTML",
                message_thread_id=thread_id,
            )
        except Exception as exc:
            logger.warning("[GUARDERÍA] No se pudo notificar huevo en grupo: %s", exc)

    # Notificación en el DM con el detalle completo
    try:
        bot.send_message(user_id, mensaje, parse_mode="HTML")
    except Exception as exc:
        logger.warning("[GUARDERÍA] No se pudo notificar huevo en DM: %s", exc)


def _notificar_eclosion(bot, user_id: int, datos: dict) -> None:
    """
    Notifica la eclosión de un huevo.

    Envía el mensaje primero al grupo donde el usuario estaba hablando
    (chat_id del dict de datos).  Si no hay chat_id, lo envía al DM.
    Siempre envía también al DM para pedir el apodo.
    """
    especie_id = datos['especie_id']
    sprite_url = (
        f"https://raw.githubusercontent.com/PokeAPI/sprites/master/"
        f"sprites/pokemon/versions/generation-v/black-white/animated/"
        f"{'shiny/' if datos.get('shiny') else ''}{especie_id}.gif"
    )

    chat_id   = datos.get('chat_id')
    thread_id = datos.get('thread_id')

    # ── Mensaje al grupo (solo info, sin botones de mote) ─────────────────────
    if chat_id and chat_id != user_id:
        try:
            bot.send_photo(
                chat_id,
                photo=sprite_url,
                caption=datos['mensaje'],
                parse_mode="HTML",
                message_thread_id=thread_id,
            )
        except Exception:
            try:
                bot.send_message(
                    chat_id,
                    datos['mensaje'],
                    parse_mode="HTML",
                    message_thread_id=thread_id,
                )
            except Exception as exc:
                logger.warning(
                    "[GUARDERÍA] No se pudo notificar eclosión en grupo %s: %s",
                    chat_id, exc,
                )

    # ── Mensaje al DM con botón para apodo ───────────────────────────────────
    texto_dm = (
        f"{datos['mensaje']}\n\n"
        f"¿Querés ponerle un apodo a <b>{datos['nombre']}</b>?\n"
        f"Escribí el apodo ahora, o pulsá <i>Sin apodo</i>."
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "Sin apodo",
        callback_data=f"mote_no_{user_id}_{datos['pokemon_id']}",
    ))

    _esperando_mote[user_id] = {
        'pokemon_id': datos['pokemon_id'],
        'nombre':     datos['nombre'],
    }

    try:
        bot.send_photo(
            user_id,
            photo=sprite_url,
            caption=texto_dm,
            parse_mode="HTML",
            reply_markup=markup,
        )
    except Exception:
        try:
            bot.send_message(
                user_id,
                texto_dm,
                parse_mode="HTML",
                reply_markup=markup,
            )
        except Exception as exc:
            logger.warning(
                "[GUARDERÍA] No se pudo notificar eclosión al DM de user %s: %s",
                user_id, exc,
            )


def interceptar_mote(bot, message) -> bool:
    """
    Si el usuario espera poner mote a un Pokémon recién nacido, consume el mensaje.

    Retorna True  si el mensaje fue consumido (era el mote).
    Retorna False si el mensaje debe procesarse normalmente.

    Llamar ANTES del procesado normal de comandos en el handler privado.
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
    bot.send_message(user_id, msg, parse_mode="HTML")
    return True