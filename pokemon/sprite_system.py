# -*- coding: utf-8 -*-
"""
pokemon/sprite_system.py
════════════════════════════════════════════════════════════════════════════════
Sistema de Sprites Pokémon — Official Artwork (PokeAPI)

Cambio respecto a la versión anterior:
  - Se eliminó la prioridad de GIFs animados de Gen 5 (Black/White).
  - Todos los sprites usan Official Artwork de alta resolución (~475×475 PNG).
  - Los sprites shiny usan Official Artwork Shiny (disponible desde Gen 8;
    para generaciones anteriores hace fallback al sprite estático shiny).
  - get_sprite_url() siempre retorna es_animado=False, por lo que todo el
    código consumidor usará send_photo() automáticamente sin cambios.

URLs base:
  Normal: https://raw.githubusercontent.com/PokeAPI/sprites/master/
          sprites/pokemon/other/official-artwork/<id>.png
  Shiny:  https://raw.githubusercontent.com/PokeAPI/sprites/master/
          sprites/pokemon/other/official-artwork/shiny/<id>.png
  Fallback estático:
    Normal: .../sprites/pokemon/<id>.png
    Shiny:  .../sprites/pokemon/shiny/<id>.png
════════════════════════════════════════════════════════════════════════════════
"""

import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class SpriteSystem:
    """Sistema para obtener sprites de Pokémon desde PokeAPI (Official Artwork)."""

    # Raíz del repositorio de sprites de PokeAPI en GitHub
    BASE_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon"

    # URL base de Official Artwork
    ARTWORK_URL = f"{BASE_URL}/other/official-artwork"

    # ── URLs públicas ─────────────────────────────────────────────────────────

    @staticmethod
    def get_sprite_url(pokemon_id: int, shiny: bool = False, front: bool = True) -> Tuple[str, bool]:
        """
        Retorna la URL del Official Artwork para el Pokémon indicado.

        Para sprites shiny intenta primero el artwork shiny oficial; si el
        Pokémon es de una generación sin artwork shiny (pre-Gen 8 en algunos
        casos) el fallback es el sprite estático shiny de los juegos DS/3DS.

        Args:
            pokemon_id: Número nacional del Pokémon.
            shiny:      True para la variante shiny.
            front:      Ignorado — Official Artwork solo tiene vista frontal.
                        Se mantiene el parámetro para compatibilidad con
                        llamadas existentes.

        Returns:
            (url, es_animado)
            es_animado siempre es False; el código consumidor usará send_photo.
        """
        try:
            if shiny:
                url = SpriteSystem._get_artwork_shiny(pokemon_id)
            else:
                url = SpriteSystem._get_artwork(pokemon_id)
            return url, False

        except Exception as e:
            logger.error("[SPRITE] Error obteniendo sprite #%s: %s", pokemon_id, e)
            # Fallback de último recurso: sprite estático clásico
            return f"{SpriteSystem.BASE_URL}/{pokemon_id}.png", False

    @staticmethod
    def _get_artwork(pokemon_id: int) -> str:
        """Official Artwork normal."""
        return f"{SpriteSystem.ARTWORK_URL}/{pokemon_id}.png"

    @staticmethod
    def _get_artwork_shiny(pokemon_id: int) -> str:
        """
        Official Artwork shiny.

        PokeAPI tiene artwork shiny para todos los Pokémon del repositorio.
        Si por alguna razón el archivo no existe en el CDN, Telegram mostrará
        la imagen rota; en ese caso el consumidor puede llamar con shiny=False
        como fallback adicional.
        """
        return f"{SpriteSystem.ARTWORK_URL}/shiny/{pokemon_id}.png"

    @staticmethod
    def _get_static_sprite(pokemon_id: int, shiny: bool) -> str:
        """
        Sprite estático clásico (PNG ~96×96) de los juegos DS/3DS.
        Se usa únicamente como fallback de último recurso.
        """
        if shiny:
            return f"{SpriteSystem.BASE_URL}/shiny/{pokemon_id}.png"
        return f"{SpriteSystem.BASE_URL}/{pokemon_id}.png"

    @staticmethod
    def get_unknown_sprite() -> str:
        """
        Sprite del Pokémon desconocido para el spawn misterioso.

        Retorna el artwork del huevo de Pokémon (ID 0 no existe en PokeAPI;
        usamos el sprite del huevo genérico o el de Missingno como sustituto
        visual para el spawn misterioso).
        """
        # El huevo genérico (egg) tiene su propia URL en PokeAPI
        return f"{SpriteSystem.BASE_URL}/other/official-artwork/egg.png"

    # ── Helpers de envío ─────────────────────────────────────────────────────

    @staticmethod
    def enviar_sprite(
        bot,
        chat_id: int,
        pokemon_id: int,
        caption: str = "",
        shiny: bool = False,
        reply_markup=None,
        message_thread_id: Optional[int] = None,
    ):
        """
        Envía el sprite de un Pokémon como foto al chat indicado.

        Siempre usa send_photo (Official Artwork es PNG estático).
        En caso de error envía un mensaje de texto como fallback.

        Args:
            bot:               Instancia de telebot.TeleBot.
            chat_id:           ID del chat/usuario destino.
            pokemon_id:        Número nacional del Pokémon.
            caption:           Texto del pie de foto (HTML).
            shiny:             True para la variante shiny.
            reply_markup:      InlineKeyboardMarkup opcional.
            message_thread_id: Topic ID para supergrupos con foros.
        """
        try:
            sprite_url, _ = SpriteSystem.get_sprite_url(pokemon_id, shiny)

            logger.info("[SPRITE] Enviando artwork #%s (shiny=%s): %s", pokemon_id, shiny, sprite_url)

            kwargs = {
                "caption":      caption,
                "reply_markup": reply_markup,
                "parse_mode":   "HTML",
            }
            if message_thread_id is not None:
                kwargs["message_thread_id"] = message_thread_id

            return bot.send_photo(chat_id, sprite_url, **kwargs)

        except Exception as e:
            logger.error("[SPRITE] Error enviando sprite #%s: %s", pokemon_id, e)
            kwargs_fallback = {
                "reply_markup": reply_markup,
                "parse_mode":   "HTML",
            }
            if message_thread_id is not None:
                kwargs_fallback["message_thread_id"] = message_thread_id
            return bot.send_message(
                chat_id,
                caption or "⚠️ Error cargando sprite",
                **kwargs_fallback,
            )

    @staticmethod
    def enviar_unknown_sprite(
        bot,
        chat_id: int,
        caption: str = "",
        reply_markup=None,
        message_thread_id: Optional[int] = None,
    ):
        """
        Envía el sprite del Pokémon desconocido (spawn misterioso).

        Args:
            bot:               Instancia de telebot.TeleBot.
            chat_id:           ID del chat/usuario destino.
            caption:           Texto del pie de foto (HTML).
            reply_markup:      InlineKeyboardMarkup opcional.
            message_thread_id: Topic ID para supergrupos con foros.
        """
        try:
            sprite_url = SpriteSystem.get_unknown_sprite()

            kwargs = {
                "caption":      caption,
                "reply_markup": reply_markup,
                "parse_mode":   "HTML",
            }
            if message_thread_id is not None:
                kwargs["message_thread_id"] = message_thread_id

            return bot.send_photo(chat_id, sprite_url, **kwargs)

        except Exception as e:
            logger.error("[SPRITE] Error enviando sprite unknown: %s", e)
            kwargs_fallback = {
                "reply_markup": reply_markup,
                "parse_mode":   "HTML",
            }
            if message_thread_id is not None:
                kwargs_fallback["message_thread_id"] = message_thread_id
            return bot.send_message(chat_id, caption, **kwargs_fallback)


# ─── Instancia global ─────────────────────────────────────────────────────────
sprite_system = SpriteSystem()