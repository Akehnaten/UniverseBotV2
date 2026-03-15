# -*- coding: utf-8 -*-
"""
level_up_handler.py
====================
Orquesta todo lo que ocurre cuando un Pokémon sube de nivel:

1. Stats ya actualizadas por ExperienceSystem._recalcular_stats (llamada
   desde aplicar_experiencia).
2. Por cada nivel subido (en orden):
   a. Chequear movimientos nuevos → preguntar Aprender / Rechazar.
   b. Chequear si puede evolucionar → preguntar Evolucionar / Cancelar.
      Si ya superó el nivel de evolución, seguir preguntando hasta que
      el usuario acepte, rechace, o llegue a nivel 100.

Uso típico desde _handle_victory / _handle_capture_success:

    from pokemon.level_up_handler import LevelUpHandler
    LevelUpHandler.procesar_subida(
        bot=bot,
        user_id=user_id,
        pokemon_id=battle.player_pokemon_id,
        exp_result=exp_result,   # dict devuelto por aplicar_experiencia
    )
"""

import logging
from typing import Optional

from telebot import types

from pokemon.services import pokemon_service, pokedex_service, movimientos_service
from pokemon.services.evolucion_service import evolucion_service
from pokemon.experience_system import ExperienceSystem

logger = logging.getLogger(__name__)

# ── Traducciones de nombres de movimiento (español) ─────────────────────────
# Importamos el mismo dict que usa wild_battle_system para consistencia
from pokemon.battle_engine import MOVE_NAMES_ES


def _nombre_movimiento_es(move_key: str) -> str:
    """Devuelve el nombre en español del movimiento, o el key titulado."""
    key = move_key.lower().replace(" ", "").replace("-", "")
    return MOVE_NAMES_ES.get(key, move_key.replace("-", " ").title())

# Movimientos exclusivos por especie evolucionada (mirror de evolucion_service)
_POST_EVO_EXCLUSIVE: dict[int, list[str]] = {
    212: ["bulletpunch"],      # Scizor:  Puño Bala
    248: ["stoneedge"],        # Tyranitar (opcional)
    445: ["dragonrush"],       # Garchomp  (opcional)
}


def _ofrecer_post_evo_moves(bot, user_id: int, pokemon_id: int,
                             nuevo_sp_id: int, callback_fin) -> None:
    """
    Después de una evolución, ofrece al usuario aprender los movimientos
    exclusivos de la nueva forma que la pre-evolución no puede aprender.
    Si no hay movimientos exclusivos, espera 2 segundos y llama callback_fin.
    """
    import threading
    from pokemon.services import pokemon_service

    movs = _POST_EVO_EXCLUSIVE.get(nuevo_sp_id, [])

    if not movs:
        threading.Timer(2.0, callback_fin).start()
        return

    pokemon = pokemon_service.obtener_pokemon(pokemon_id)
    if not pokemon:
        threading.Timer(2.0, callback_fin).start()
        return

    def _norm(s: str) -> str:
        return s.lower().replace(" ", "").replace("-", "")

    ya_conocidos = {_norm(mv) for mv in (pokemon.movimientos or []) if mv}
    nuevos = [m for m in movs if _norm(m) not in ya_conocidos]

    if not nuevos:
        threading.Timer(2.0, callback_fin).start()
        return

    # Usar el flujo normal de aprendizaje con un delay para que se vea la evo
    def _iniciar():
        LevelUpHandler._preguntar_movimiento(
            bot, user_id, pokemon_id, nuevos, 0, callback_fin
        )
    threading.Timer(2.5, _iniciar).start()

# ============================================================================
# HANDLER PRINCIPAL
# ============================================================================

class LevelUpHandler:
    """
    Gestiona el flujo post-subida de nivel de forma asíncrona usando
    threading.Timer para no bloquear el hilo principal del bot.
    """

    @staticmethod
    def procesar_subida(
        bot,
        user_id: int,
        pokemon_id: int,
        exp_result: dict,
        delay: float = 2.0,
        on_complete=None,
    ) -> None:
        """
        Punto de entrada principal. Se llama justo después de mostrar
        el mensaje de victoria/captura.

        Args:
            bot:        Instancia del bot de Telegram.
            user_id:    ID del usuario (chat privado).
            pokemon_id: id_unico del Pokémon que subió de nivel.
            exp_result: Dict devuelto por ExperienceSystem.aplicar_experiencia().
            delay:      Segundos de espera antes de empezar (para no pisar el
                        mensaje de victoria).
            on_complete: Callable opcional que se ejecuta al terminar todo el
                        flujo (movimientos + evolución de todos los niveles).
                        Usado para encadenar múltiples Pokémon en cola.
        """
        import threading

        niveles = exp_result.get('niveles_subidos', [])
        if not niveles:
            if on_complete:
                on_complete()
            return

        def _iniciar():
            LevelUpHandler._procesar_nivel(bot, user_id, pokemon_id, niveles, 0, on_complete)

        threading.Timer(delay, _iniciar).start()

    @staticmethod
    def _procesar_nivel(
        bot,
        user_id: int,
        pokemon_id: int,
        niveles: list,
        indice: int,
        on_complete=None,
        ya_ofrecidos: Optional[set] = None,
    ) -> None:
        if ya_ofrecidos is None:
            ya_ofrecidos = set()

        if indice >= len(niveles):
            if on_complete:
                on_complete()
            return

        nivel = niveles[indice]

        def _siguiente_nivel():
            LevelUpHandler._procesar_nivel(
                bot, user_id, pokemon_id, niveles, indice + 1, on_complete,
                ya_ofrecidos=ya_ofrecidos,  # ← propagar el set
            )

        def _chequear_movimientos_post_evolucion():
            pokemon = pokemon_service.obtener_pokemon(pokemon_id)
            if not pokemon:
                _siguiente_nivel()
                return

            movimientos_nuevos = ExperienceSystem.obtener_movimientos_nuevos_en_nivel(
                pokemon.pokemonID, nivel
            )

            def _norm(s: str) -> str:
                return s.lower().replace(" ", "").replace("-", "")

            if movimientos_nuevos:
                ya_conocidos = {
                    _norm(mv)
                    for mv in (pokemon.movimientos or [])
                    if mv
                }
                # Filtrar: ni conocidos ni ya ofrecidos en esta sesión
                movimientos_nuevos = [
                    m for m in movimientos_nuevos
                    if _norm(m) not in ya_conocidos
                    and _norm(m) not in ya_ofrecidos
                ]

            if movimientos_nuevos:
                # Marcar como ofrecidos ANTES de preguntar
                for m in movimientos_nuevos:
                    ya_ofrecidos.add(_norm(m))

                LevelUpHandler._preguntar_movimiento(
                    bot, user_id, pokemon_id,
                    movimientos_nuevos, 0,
                    callback_fin=_siguiente_nivel,
                )
            else:
                _siguiente_nivel()

        LevelUpHandler._chequear_evolucion(
            bot, user_id, pokemon_id, nivel,
            callback_fin=_chequear_movimientos_post_evolucion,
        )

    # =========================================================================
    # MOVIMIENTOS NUEVOS
    # =========================================================================

    @staticmethod
    def _preguntar_movimiento(
        bot,
        user_id: int,
        pokemon_id: int,
        movimientos_nuevos: list,
        idx: int,
        callback_fin,
    ) -> None:
        """
        Pregunta si el usuario quiere aprender el movimiento en posición `idx`.
        Cuando termina todos, llama callback_fin.
        """
        if idx >= len(movimientos_nuevos):
            callback_fin()
            return

        move_key = movimientos_nuevos[idx]
        move_nombre_es = _nombre_movimiento_es(move_key)

        pokemon = pokemon_service.obtener_pokemon(pokemon_id)
        if not pokemon:
            callback_fin()
            return

        poke_nombre = pokemon.mote or pokemon.nombre
        move_data   = movimientos_service.obtener_movimiento(move_key)
        move_desc   = ""
        if move_data:
            poder    = move_data.get('poder', 0) or 0
            tipo     = move_data.get('tipo', '?')
            cat      = move_data.get('categoria', '?')
            move_desc = f"\n   Tipo: {tipo} | Cat: {cat} | Poder: {poder}"

        # Obtener sprite del Pokémon
        sprite_url = pokedex_service.obtener_sprite(pokemon.pokemonID)

        texto = (
            f"📚 <b>¡{poke_nombre} quiere aprender {move_nombre_es}!</b>"
            f"{move_desc}\n\n"
            f"🎓 El profesor Oak pregunta:\n"
            f"¿Deseas que {poke_nombre} aprenda <b>{move_nombre_es}</b>?"
        )

        # Callback data compacto para los botones
        cb_aprender = f"lv_learn#{pokemon_id}#{move_key}"
        cb_rechazar = f"lv_skip#{pokemon_id}#{move_key}"

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ Aprender",  callback_data=cb_aprender),
            types.InlineKeyboardButton("❌ Rechazar",  callback_data=cb_rechazar),
        )

        try:
            if sprite_url:
                bot.send_photo(
                    user_id,
                    sprite_url,
                    caption=texto,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
            else:
                bot.send_message(user_id, texto, parse_mode="HTML", reply_markup=markup)
        except Exception as e:
            logger.error(f"[LvUp] Error enviando pregunta de movimiento: {e}")
            callback_fin()
            return

        # Registrar el estado pendiente para el callback handler.
        # Clave compuesta (user_id, pokemon_id) para que dos Pokémon que
        # suban de nivel simultáneamente no se sobreescriban mutuamente.
        _pending_move_learn[(user_id, pokemon_id)] = {
            'pokemon_id':         pokemon_id,
            'move_key':           move_key,
            'movimientos_nuevos': movimientos_nuevos,
            'idx':                idx,
            'callback_fin':       callback_fin,
        }

    @staticmethod
    def _ejecutar_aprender_movimiento(
        bot,
        user_id: int,
        pokemon_id: int,
        move_key: str,
        movimientos_nuevos: list,
        idx: int,
        callback_fin,
        message_id: Optional[int] = None,
    ) -> None:
        """
        Ejecuta la lógica de aprender el movimiento.
        - Si hay slot libre: lo aprende directamente.
        - Si los 4 slots están ocupados: muestra los 4 movimientos
          actuales con botones para sustituir, más "No aprender".
        """
        pokemon = pokemon_service.obtener_pokemon(pokemon_id)
        if not pokemon:
            callback_fin()
            return

        poke_nombre    = pokemon.mote or pokemon.nombre
        move_nombre_es = _nombre_movimiento_es(move_key)
        movimientos_actuales: list = pokemon.movimientos or []

        def _siguiente():
            LevelUpHandler._preguntar_movimiento(
                bot, user_id, pokemon_id,
                movimientos_nuevos, idx + 1, callback_fin
            )

        if len(movimientos_actuales) < 4:
            # Slot libre — aprender directamente
            nuevos_movs = movimientos_actuales + [move_key]
            _guardar_movimientos(pokemon_id, nuevos_movs)
            texto = (
                f"✅ <b>{poke_nombre}</b> aprendió <b>{move_nombre_es}</b>!"
            )
            _editar_o_enviar(bot, user_id, message_id, texto)
            import threading
            threading.Timer(1.5, _siguiente).start()

        else:
            # 4 movimientos llenos — preguntar cuál olvidar
            LevelUpHandler._preguntar_olvidar(
                bot, user_id, pokemon_id,
                move_key, movimientos_actuales,
                _siguiente,
                message_id=message_id,
            )

    @staticmethod
    def _preguntar_olvidar(
        bot,
        user_id: int,
        pokemon_id: int,
        move_nuevo: str,
        movimientos_actuales: list,
        callback_fin,
        message_id: Optional[int] = None,
    ) -> None:
        """
        Muestra los 4 movimientos actuales + botón "No aprender".
        Cada movimiento tiene un botón para ser sustituido.
        """
        pokemon        = pokemon_service.obtener_pokemon(pokemon_id)
        poke_nombre    = (pokemon.mote or pokemon.nombre) if pokemon else "Pokémon"
        nuevo_nombre   = _nombre_movimiento_es(move_nuevo)

        texto = (
            f"⚠️ <b>{poke_nombre} ya sabe 4 movimientos.</b>\n\n"
            f"¿Cuál quieres sustituir por <b>{nuevo_nombre}</b>?\n"
        )
        for i, mv in enumerate(movimientos_actuales, 1):
            texto += f"\n  {i}. {_nombre_movimiento_es(mv)}"

        markup = types.InlineKeyboardMarkup(row_width=2)
        for i, mv in enumerate(movimientos_actuales):
            cb = f"lv_replace#{pokemon_id}#{i}#{move_nuevo}"
            markup.add(types.InlineKeyboardButton(
                f"🔄 Olvidar {_nombre_movimiento_es(mv)}", callback_data=cb
            ))
        markup.add(types.InlineKeyboardButton(
            "🚫 No aprender", callback_data=f"lv_nolearn#{pokemon_id}#{move_nuevo}"
        ))

        _pending_move_replace[(user_id, pokemon_id)] = {
            'pokemon_id':       pokemon_id,
            'move_nuevo':       move_nuevo,
            'movimientos_act':  movimientos_actuales,
            'callback_fin':     callback_fin,
        }

        _editar_o_enviar(bot, user_id, message_id, texto, markup=markup)

    # =========================================================================
    # EVOLUCIÓN
    # =========================================================================

    @staticmethod
    def _chequear_evolucion(
        bot,
        user_id: int,
        pokemon_id: int,
        nivel: int,
        callback_fin,
    ) -> None:
        """
        Verifica si el Pokémon puede evolucionar al nivel dado y, si es así,
        envía el mensaje de confirmación con los botones.
        """
        puede, evo_data = evolucion_service.verificar_evolucion_por_nivel(
            pokemon_id, nivel
        )
        if not puede or evo_data is None:
            callback_fin()
            return

        pokemon = pokemon_service.obtener_pokemon(pokemon_id)
        if not pokemon:
            callback_fin()
            return

        poke_nombre   = pokemon.mote or pokemon.nombre
        nuevo_sp_id   = int(evo_data['evoluciona_a'])
        nombre_nuevo  = pokedex_service.obtener_nombre(nuevo_sp_id)
        sprite_url    = pokedex_service.obtener_sprite(pokemon.pokemonID)

        texto = (
            f"✨ <b>¡{poke_nombre} quiere evolucionar!</b>\n\n"
            f"🌟 <b>{poke_nombre}</b> → <b>{nombre_nuevo}</b>\n\n"
            f"¿Permites que <b>{poke_nombre}</b> evolucione?"
        )

        cb_evolucion = f"lv_evolve#{pokemon_id}#{nuevo_sp_id}"
        cb_cancelar  = f"lv_noevolve#{pokemon_id}"

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🌟 Evolucionar", callback_data=cb_evolucion),
            types.InlineKeyboardButton("✋ Cancelar",    callback_data=cb_cancelar),
        )

        _pending_evolution[user_id] = {
            'pokemon_id':  pokemon_id,
            'nuevo_sp_id': nuevo_sp_id,
            'callback_fin': callback_fin,
        }

        try:
            if sprite_url:
                bot.send_photo(
                    user_id, sprite_url,
                    caption=texto,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
            else:
                bot.send_message(
                    user_id, texto,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
        except Exception as e:
            logger.error(f"[LvUp] Error enviando pregunta de evolución: {e}")
            callback_fin()


# ============================================================================
# ESTADOS PENDIENTES (memoria en proceso)
# ============================================================================

# {user_id: {pokemon_id, move_key, movimientos_nuevos, idx, callback_fin}}
_pending_move_learn:   dict = {}

# {user_id: {pokemon_id, move_nuevo, movimientos_act, callback_fin}}
_pending_move_replace: dict = {}

# {user_id: {pokemon_id, nuevo_sp_id, callback_fin}}
_pending_evolution:    dict = {}


# ============================================================================
# REGISTRO DE CALLBACKS (llamar desde el módulo principal del bot)
# ============================================================================

def registrar_callbacks(bot) -> None:
    """
    Registra todos los callback_query handlers de level-up en el bot.
    Llamar una sola vez al iniciar el bot, después de crear la instancia.

    Ejemplo en main.py / bot.py:
        from pokemon.level_up_handler import registrar_callbacks
        registrar_callbacks(bot)
    """

    # ── Aprender movimiento ──────────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith("lv_learn#"))
    def cb_aprender(call: types.CallbackQuery):
        bot.answer_callback_query(call.id)
        parts      = call.data.split("#")
        pokemon_id = int(parts[1])
        move_key   = parts[2]
        user_id    = call.from_user.id

        pendiente = _pending_move_learn.pop((user_id, pokemon_id), None)
        if not pendiente:
            return

        LevelUpHandler._ejecutar_aprender_movimiento(
            bot, user_id, pokemon_id, move_key,
            pendiente['movimientos_nuevos'],
            pendiente['idx'],
            pendiente['callback_fin'],
            message_id=call.message.message_id,
        )

    # ── Rechazar movimiento ──────────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith("lv_skip#"))
    def cb_rechazar(call: types.CallbackQuery):
        bot.answer_callback_query(call.id)
        parts      = call.data.split("#")
        pokemon_id = int(parts[1])
        user_id    = call.from_user.id

        pendiente = _pending_move_learn.pop((user_id, pokemon_id), None)
        if not pendiente:
            return

        move_key   = pendiente['move_key']
        poke       = pokemon_service.obtener_pokemon(pokemon_id)
        poke_nombre = (poke.mote or poke.nombre) if poke else "Pokémon"
        _editar_o_enviar(
            bot, user_id, call.message.message_id,
            f"🚫 <b>{poke_nombre}</b> no aprendió "
            f"<b>{_nombre_movimiento_es(move_key)}</b>.",
        )
        import threading
        threading.Timer(1.5, lambda: LevelUpHandler._preguntar_movimiento(
            bot, user_id, pokemon_id,
            pendiente['movimientos_nuevos'],
            pendiente['idx'] + 1,
            pendiente['callback_fin'],
        )).start()

    # ── Sustituir movimiento ─────────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith("lv_replace#"))
    def cb_sustituir(call: types.CallbackQuery):
        bot.answer_callback_query(call.id)
        parts       = call.data.split("#")
        pokemon_id  = int(parts[1])
        slot        = int(parts[2])
        move_nuevo  = parts[3]
        user_id     = call.from_user.id

        pendiente = _pending_move_replace.pop((user_id, pokemon_id), None)
        if not pendiente:
            return

        movs_act     = list(pendiente['movimientos_act'])
        olvidado_key = movs_act[slot]
        olvidado_es  = _nombre_movimiento_es(olvidado_key)
        nuevo_es     = _nombre_movimiento_es(move_nuevo)

        movs_act[slot] = move_nuevo
        _guardar_movimientos(pokemon_id, movs_act)

        poke        = pokemon_service.obtener_pokemon(pokemon_id)
        poke_nombre = (poke.mote or poke.nombre) if poke else "Pokémon"

        _editar_o_enviar(
            bot, user_id, call.message.message_id,
            f"🔄 <b>{poke_nombre}</b> olvidó <b>{olvidado_es}</b> "
            f"y aprendió <b>{nuevo_es}</b>!",
        )
        import threading
        threading.Timer(1.5, pendiente['callback_fin']).start()

    # ── No aprender (desde pantalla de sustitución) ──────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith("lv_nolearn#"))
    def cb_no_aprender(call: types.CallbackQuery):
        bot.answer_callback_query(call.id)
        parts      = call.data.split("#")
        pokemon_id = int(parts[1])
        move_nuevo = parts[2]
        user_id    = call.from_user.id

        pendiente = _pending_move_replace.pop((user_id, pokemon_id), None)
        if not pendiente:
            return

        poke        = pokemon_service.obtener_pokemon(pokemon_id)
        poke_nombre = (poke.mote or poke.nombre) if poke else "Pokémon"
        _editar_o_enviar(
            bot, user_id, call.message.message_id,
            f"🚫 <b>{poke_nombre}</b> no aprendió "
            f"<b>{_nombre_movimiento_es(move_nuevo)}</b>.",
        )
        import threading
        threading.Timer(1.5, pendiente['callback_fin']).start()

    # ── Evolucionar ──────────────────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith("lv_evolve#"))
    def cb_evolucionar(call: types.CallbackQuery):
        bot.answer_callback_query(call.id)
        parts      = call.data.split("#")
        pokemon_id = int(parts[1])
        user_id    = call.from_user.id

        pendiente = _pending_evolution.pop(user_id, None)
        if not pendiente or pendiente['pokemon_id'] != pokemon_id:
            return

        exito, mensaje, _ = evolucion_service.evolucionar_pokemon(pokemon_id)

        if exito:
            texto = f"🌟 {mensaje}"
            try:
                poke_nuevo = pokemon_service.obtener_pokemon(pokemon_id)
                if poke_nuevo:
                    sprite_url = pokedex_service.obtener_sprite(poke_nuevo.pokemonID)
                    if sprite_url:
                        if call.message.content_type in ("photo", "animation"):
                            from telebot.types import InputMediaPhoto
                            bot.edit_message_media(
                                media=InputMediaPhoto(sprite_url, caption=texto, parse_mode="HTML"),
                                chat_id=user_id,
                                message_id=call.message.message_id,
                            )
                        else:
                            _editar_o_enviar(bot, user_id, call.message.message_id, texto)
                            bot.send_photo(user_id, sprite_url,
                                           caption=f"✨ ¡<b>{poke_nuevo.nombre}</b>!",
                                           parse_mode="HTML")
                    else:
                        _editar_o_enviar(bot, user_id, call.message.message_id, texto)
                else:
                    _editar_o_enviar(bot, user_id, call.message.message_id, texto)
            except Exception as _e:
                logger.warning(f"[LvUp] Sprite evolución: {_e}")
                _editar_o_enviar(bot, user_id, call.message.message_id, texto)
        else:
            texto = f"❌ No se pudo evolucionar: {mensaje}"
            _editar_o_enviar(bot, user_id, call.message.message_id, texto)

        # Ofrecer movimientos exclusivos de la nueva forma (ej. Puño Bala→Scizor)
        pokemon_actualizado = pokemon_service.obtener_pokemon(pokemon_id)
        nuevo_sp_id = pokemon_actualizado.pokemonID if pokemon_actualizado else 0
        _ofrecer_post_evo_moves(bot, user_id, pokemon_id, nuevo_sp_id, pendiente['callback_fin'])
        nuevo_sp_id = pendiente.get("nuevo_sp_id") or nuevo_sp_id
        _ofrecer_post_evo_moves(
            bot,
            user_id,
            pokemon_id,
            nuevo_sp_id,
            pendiente['callback_fin'],
        )
        # NO llamar threading.Timer aquí: _ofrecer_post_evo_moves
        # llama callback_fin internamente.
        return

    # ── Cancelar evolución ───────────────────────────────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith("lv_noevolve#"))
    def cb_cancelar_evolucion(call: types.CallbackQuery):
        bot.answer_callback_query(call.id)
        parts      = call.data.split("#")
        pokemon_id = int(parts[1])
        user_id    = call.from_user.id

        pendiente = _pending_evolution.pop(user_id, None)
        if not pendiente or pendiente['pokemon_id'] != pokemon_id:
            return

        poke        = pokemon_service.obtener_pokemon(pokemon_id)
        poke_nombre = (poke.mote or poke.nombre) if poke else "Pokémon"

        _editar_o_enviar(
            bot, user_id, call.message.message_id,
            f"✋ Decidiste no evolucionar a <b>{poke_nombre}</b>.",
        )
        import threading
        threading.Timer(1.5, pendiente['callback_fin']).start()


# ============================================================================
# HELPERS PRIVADOS
# ============================================================================

def _guardar_movimientos(pokemon_id: int, movimientos: list) -> None:
    """Persiste la lista de movimientos en BD."""
    from database import db_manager
    try:
        movs = (list(movimientos) + [None, None, None, None])[:4]
        db_manager.execute_update(
            "UPDATE POKEMON_USUARIO SET move1=?, move2=?, move3=?, move4=? WHERE id_unico=?",
            (movs[0], movs[1], movs[2], movs[3], pokemon_id),
        )
    except Exception as e:
        logger.error(f"[LvUp] Error guardando movimientos: {e}")


def _editar_o_enviar(
    bot,
    user_id: int,
    message_id: Optional[int],
    texto: str,
    markup=None,
) -> None:
    """Intenta editar el mensaje; si falla, envía uno nuevo."""
    try:
        if message_id:
            try:
                bot.edit_message_caption(
                    caption=texto,
                    chat_id=user_id,
                    message_id=message_id,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
                return
            except Exception:
                try:
                    bot.edit_message_text(
                        texto,
                        user_id,
                        message_id,
                        parse_mode="HTML",
                        reply_markup=markup,
                    )
                    return
                except Exception:
                    pass
        # Fallback: mensaje nuevo
        bot.send_message(user_id, texto, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logger.error(f"[LvUp] Error editando/enviando mensaje: {e}")
