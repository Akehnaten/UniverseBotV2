# -*- coding: utf-8 -*-
"""
Sistema de Sprites Pokémon
Prioriza sprites animados (GIF), fallback a estáticos (PNG)
"""

import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class SpriteSystem:
    """Sistema para obtener sprites de Pokémon desde PokeAPI"""
    
    BASE_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon"
    
    @staticmethod
    def get_sprite_url(pokemon_id: int, shiny: bool = False, front: bool = True) -> Tuple[str, bool]:
        """
        Obtiene URL del sprite de un Pokémon
        Prioriza animados (GIF), fallback a estáticos (PNG)
        
        Returns:
            (url, es_animado)
        """
        try:
            # Prioridad 1: Sprites animados Gen 5 (GIF) - solo Gen 1-5 (1-649)
            if pokemon_id <= 649:
                animated_url = SpriteSystem._get_animated_sprite(pokemon_id, shiny)
                if animated_url:
                    return animated_url, True
            
            # Fallback: Sprite estático (PNG)
            static_url = SpriteSystem._get_static_sprite(pokemon_id, shiny)
            return static_url, False
            
        except Exception as e:
            logger.error(f"[SPRITE] Error obteniendo sprite: {e}")
            return f"{SpriteSystem.BASE_URL}/0.png", False
    
    @staticmethod
    def _get_animated_sprite(pokemon_id: int, shiny: bool) -> Optional[str]:
        """Obtiene sprite animado de Gen 5 (Black/White)"""
        if pokemon_id > 649:
            return None
        
        if shiny:
            return f"{SpriteSystem.BASE_URL}/versions/generation-v/black-white/animated/shiny/{pokemon_id}.gif"
        else:
            return f"{SpriteSystem.BASE_URL}/versions/generation-v/black-white/animated/{pokemon_id}.gif"
    
    @staticmethod
    def _get_static_sprite(pokemon_id: int, shiny: bool) -> str:
        """Obtiene sprite estático (PNG)"""
        if shiny:
            return f"{SpriteSystem.BASE_URL}/shiny/{pokemon_id}.png"
        else:
            return f"{SpriteSystem.BASE_URL}/{pokemon_id}.png"
    
    @staticmethod
    def get_unknown_sprite() -> str:
        """Sprite de Pokémon desconocido"""
        return f"{SpriteSystem.BASE_URL}/0.png"
    
    @staticmethod
    def enviar_sprite(bot, chat_id: int, pokemon_id: int, caption: str = "", 
                     shiny: bool = False, reply_markup=None, message_thread_id: Optional[int] = None):
        """
        Envía sprite de Pokémon (animado o estático)
        
        Args:
            message_thread_id: Thread ID opcional para grupos con topics
        """
        try:
            sprite_url, es_animado = SpriteSystem.get_sprite_url(pokemon_id, shiny)
            
            logger.info(f"[SPRITE] Enviando {'GIF' if es_animado else 'PNG'}: {sprite_url}")
            
            kwargs = {
                'caption': caption,
                'reply_markup': reply_markup,
                'parse_mode': "HTML"
            }
            
            if message_thread_id is not None:
                kwargs['message_thread_id'] = message_thread_id
            
            if es_animado:
                msg = bot.send_animation(chat_id, sprite_url, **kwargs)
            else:
                msg = bot.send_photo(chat_id, sprite_url, **kwargs)
            
            return msg
            
        except Exception as e:
            logger.error(f"[SPRITE] Error enviando sprite: {e}")
            kwargs_fallback = {
                'reply_markup': reply_markup,
                'parse_mode': "HTML"
            }
            if message_thread_id is not None:
                kwargs_fallback['message_thread_id'] = message_thread_id
            
            return bot.send_message(chat_id, caption or "⚠️ Error cargando sprite", **kwargs_fallback)
    
    @staticmethod
    def enviar_unknown_sprite(bot, chat_id: int, caption: str = "", 
                            reply_markup=None, message_thread_id: Optional[int] = None):
        """
        Envía sprite de Pokémon desconocido
        
        Args:
            message_thread_id: Thread ID opcional para grupos con topics
        """
        try:
            sprite_url = SpriteSystem.get_unknown_sprite()
            
            kwargs = {
                'caption': caption,
                'reply_markup': reply_markup,
                'parse_mode': "HTML"
            }
            
            if message_thread_id is not None:
                kwargs['message_thread_id'] = message_thread_id
            
            return bot.send_photo(chat_id, sprite_url, **kwargs)
            
        except Exception as e:
            logger.error(f"[SPRITE] Error enviando sprite unknown: {e}")
            kwargs_fallback = {
                'reply_markup': reply_markup,
                'parse_mode': "HTML"
            }
            if message_thread_id is not None:
                kwargs_fallback['message_thread_id'] = message_thread_id
            
            return bot.send_message(chat_id, caption, **kwargs_fallback)


# Instancia global
sprite_system = SpriteSystem()
