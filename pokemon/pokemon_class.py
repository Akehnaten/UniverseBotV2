# -*- coding: utf-8 -*-
"""
Clase Pokemon CORREGIDA
=======================

CORRECCIONES:
1. Atributo "mote" (apodo) agregado
2. Método get_sprite_animado() para obtener GIF animado
3. Método pedir_mote() para preguntar apodo al capturar/obtener
"""

import logging
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from database import db_manager
from telebot import types

logger = logging.getLogger(__name__)

# Dict temporal: pokemon_id_unico → callable(mote: str | None)
# Se limpia al resolverse el apodo (sí o no).
_mote_callbacks: dict = {}
_mote_message_ids: dict = {}   # {pokemon_id: (chat_id, message_id)}

@dataclass
class Pokemon:
    """
    Representa un Pokémon del usuario
    ✅ NUEVO: Incluye campo 'mote' (apodo)
    """
    # Identificación
    id_unico: int
    pokemonID: int
    usuario_id: int
    nombre: str  # Nombre de especie (ej: "Charmander")
    mote: Optional[str] = None  # ✅ NUEVO: Apodo personalizado (ej: "Fueguito")
    
    # Stats y combate
    nivel: int = 5
    exp: int = 0
    hp_actual: int = 100
    stats: Dict[str, int] = field(default_factory=dict)
    
    # IVs y EVs
    ivs: Dict[str, int] = field(default_factory=dict)
    evs: Dict[str, int] = field(default_factory=dict)
    
    # Características
    naturaleza: str = "Hardy"
    habilidad: Optional[str] = None
    shiny: bool = False
    sexo: Optional[str] = None
    
    # Movimientos
    movimientos: List[str] = field(default_factory=list)
    
    # Estado
    en_equipo: bool = False
    objeto: Optional[str] = None
    fecha_captura: Optional[str] = None
    
    def __post_init__(self):
        """
        Post-inicialización del dataclass.

        Si `stats` ya viene cargado desde BD (vía _row_a_pokemon), se usa
        directamente sin recalcular. Solo se recalcula cuando el dict está
        vacío, lo que ocurre al construir un Pokemon manualmente en tests
        o código interno que no pasa por _row_a_pokemon.
        """
        if not self.stats:
            self.stats = self._calcular_stats()

        # hp_actual nunca puede superar el PS máximo
        hp_max = self.stats.get("hp", 1)
        if self.hp_actual is None or self.hp_actual > hp_max:
            self.hp_actual = hp_max
    
    def _calcular_stats(self) -> Dict[str, int]:
        """Calcula stats del pokemon""" 
        from pokemon.services.pokedex_service import pokedex_service       
        stats_base = pokedex_service.obtener_stats_base(self.pokemonID)
        
        if not stats_base:
            return {
                'hp': 100,
                'atq': 50,
                'def': 50,
                'atq_sp': 50,
                'def_sp': 50,
                'vel': 50
            }
        
        stats = {}
        for stat in ['hp', 'atq', 'def', 'atq_sp', 'def_sp', 'vel']:
            base = stats_base.get(stat, 50)
            iv = self.ivs.get(stat, 0)
            ev = self.evs.get(stat, 0)
            
            if stat == 'hp':
                # Fórmula HP
                stats[stat] = int(((2 * base + iv + ev // 4) * self.nivel / 100) + self.nivel + 10)
            else:
                # Fórmula otros stats
                stats[stat] = int(((2 * base + iv + ev // 4) * self.nivel / 100) + 5)
        
        return stats
    
    def get_nombre_display(self) -> str:
        """
        ✅ NUEVO: Retorna el nombre a mostrar (mote si existe, sino nombre)
        
        Returns:
            "Fueguito (Charmander)" si tiene mote
            "Charmander" si no tiene mote
        """
        if self.mote:
            return f"{self.mote} ({self.nombre})"
        return self.nombre
    
    def get_sprite_animado(self) -> Optional[str]:
        """
        ✅ NUEVO: Obtiene sprite animado del Pokemon
        
        Prioridad:
        1. Sprites animados de PokeAPI
        2. Sprites de Smogon
        3. Fallback a pokedex.json
        
        Returns:
            URL del sprite animado o None
        """
        try:
            # Intentar PokeAPI primero (tiene GIFs animados)
            pokeapi_url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/versions/generation-v/black-white/animated/{self.pokemonID}.gif"
            
            # Si es shiny, usar sprite shiny
            if self.shiny:
                pokeapi_url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/versions/generation-v/black-white/animated/shiny/{self.pokemonID}.gif"
            
            return pokeapi_url
            
        except Exception as e:
            logger.error(f"Error obteniendo sprite animado: {e}")
            
            # Fallback: sprite estático de pokedex
            try:
                from pokemon.services.pokedex_service import pokedex_service
                pokemon_data = pokedex_service.obtener_pokemon(self.pokemonID)
                
                if pokemon_data and 'sprite' in pokemon_data:
                    return pokemon_data['sprite']
                
            except Exception as e2:
                logger.error(f"Error obteniendo sprite fallback: {e2}")
            
            return None
    
    def guardar(self) -> bool:
        """
        Persiste el estado del Pokémon en POKEMON_USUARIO.

        Escribe tanto el estado de combate (hp_actual, objeto, movimientos)
        como las 6 stats calculadas, manteniendo la BD siempre sincronizada.
        Devuelve True si la fila fue actualizada correctamente.
        """
        movs = (self.movimientos + [None, None, None, None])[:4]

        query = """
            UPDATE POKEMON_USUARIO
            SET nivel     = ?,
                hp_actual = ?,
                exp       = ?,
                ps        = ?,
                atq       = ?,
                def       = ?,
                atq_sp    = ?,
                def_sp    = ?,
                vel       = ?,
                iv_hp     = ?, iv_atq    = ?, iv_def    = ?,
                iv_atq_sp = ?, iv_def_sp = ?, iv_vel    = ?,
                ev_hp     = ?, ev_atq    = ?, ev_def    = ?,
                ev_atq_sp = ?, ev_def_sp = ?, ev_vel    = ?,
                naturaleza = ?,
                en_equipo  = ?,
                objeto     = ?,
                apodo      = ?,
                shiny      = ?,
                move1      = ?, move2 = ?, move3 = ?, move4 = ?,
                habilidad  = ?
            WHERE id_unico = ?
        """
        params = (
            self.nivel,
            self.hp_actual,
            self.exp,
            # stats calculados (caché)
            self.stats.get("hp",     0),
            self.stats.get("atq",    0),
            self.stats.get("def",    0),
            self.stats.get("atq_sp", 0),
            self.stats.get("def_sp", 0),
            self.stats.get("vel",    0),
            # IVs
            self.ivs.get("hp",     0), self.ivs.get("atq",    0), self.ivs.get("def",    0),
            self.ivs.get("atq_sp", 0), self.ivs.get("def_sp", 0), self.ivs.get("vel",    0),
            # EVs
            self.evs.get("hp",     0), self.evs.get("atq",    0), self.evs.get("def",    0),
            self.evs.get("atq_sp", 0), self.evs.get("def_sp", 0), self.evs.get("vel",    0),
            self.naturaleza,
            int(self.en_equipo),
            self.objeto,
            self.mote,
            int(self.shiny),
            movs[0], movs[1], movs[2], movs[3],
            self.habilidad,
            self.id_unico,
        )
        try:
            rows = db_manager.execute_update(query, params)
            return rows > 0
        except Exception as e:
            logger.error(
                f"[Pokemon.guardar] Error al persistir id_unico={self.id_unico}: {e}"
            )
            return False
    
    def curar(self):
        """Cura el Pokémon al máximo HP"""
        self.hp_actual = self.stats['hp']
        self.guardar()
    
    def __repr__(self):
        return f"<Pokemon {self.get_nombre_display()} Nv.{self.nivel}>"


# ============================================================================
# FUNCIÓN PARA PEDIR MOTE AL CAPTURAR
# ============================================================================

def pedir_mote_pokemon(
    bot,
    user_id: int,
    pokemon: "Pokemon",
    mensaje_callback=None,
    chat_id=None,
    message_thread_id=None,
) -> None:
    """
    Pregunta Sí/No antes de pedir texto libre.

    Flujo:
      1. Muestra botones inline [✅ Sí] [❌ No]
      2. Si pulsa Sí  → pide texto con register_next_step_handler
      3. Si pulsa No  → callback(None), confirma sin apodo
    """
    try:
        dest       = chat_id or user_id
        sprite_url = pokemon.get_sprite_animado()
        extra      = {}
        if message_thread_id:
            extra["message_thread_id"] = message_thread_id

        texto = (
            f"✅ <b>¡{pokemon.nombre} capturado!</b>\n\n"
            f"📝 ¿Quieres ponerle un apodo a <b>{pokemon.nombre}</b>?"
        )
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(
                "✅ Sí, ponerle apodo",
                callback_data=f"mote_si_{user_id}_{pokemon.id_unico}",
            ),
            types.InlineKeyboardButton(
                "❌ No, dejarlo así",
                callback_data=f"mote_no_{user_id}_{pokemon.id_unico}",
            ),
        )

        _mote_callbacks[pokemon.id_unico] = mensaje_callback

        msg_enviado = None
        if sprite_url:
            try:
                msg_enviado = bot.send_photo(
                    dest, sprite_url,
                    caption=texto, parse_mode="HTML",
                    reply_markup=markup, **extra,
                )
            except Exception:
                pass
        if not msg_enviado:
            msg_enviado = bot.send_message(
                dest, texto, parse_mode="HTML",
                reply_markup=markup, **extra
            )

        # Guardar message_id para editarlo al recibir el apodo
        _mote_message_ids[pokemon.id_unico] = (dest, msg_enviado.message_id)

    except Exception as e:
        logger.error(f"[MOTE] Error pidiendo mote: {e}")


def _procesar_mote(bot, message, pokemon: Pokemon, callback, owner_id: int):
    try:
        if message.from_user.id != owner_id:
            bot.register_next_step_handler_by_chat_id(
                message.chat.id,
                lambda msg: _procesar_mote(bot, msg, pokemon, callback, owner_id)
            )
            return

        # ✅ Leer el thread del mensaje del usuario
        tid = getattr(message, "message_thread_id", None)

        mote = message.text.strip()

        if mote.lower() in ['no', 'n', 'nada', 'ninguno', 'skip']:
            mote = None
            respuesta = f"✅ {pokemon.nombre} no tendrá apodo."
        else:
            if len(mote) > 12:
                mote = mote[:12]
                respuesta = f"✅ Apodo demasiado largo, se acortó a: <b>{mote}</b>"
            else:
                respuesta = f"✅ {pokemon.nombre} ahora se llama <b>{mote}</b>!"

        pokemon.mote = mote
        if callback:
            callback(mote)

        # Editar el mensaje original (con foto o texto) en lugar de enviar uno nuevo
        chat_id_orig, message_id_orig = _mote_message_ids.pop(pokemon.id_unico, (None, None))
        if chat_id_orig and message_id_orig:
            try:
                bot.edit_message_caption(
                    caption=respuesta,
                    chat_id=chat_id_orig,
                    message_id=message_id_orig,
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except Exception:
                try:
                    bot.edit_message_text(
                        text=respuesta,
                        chat_id=chat_id_orig,
                        message_id=message_id_orig,
                        parse_mode="HTML",
                        reply_markup=None,
                    )
                except Exception:
                    # Fallback: si no se puede editar, enviar normal
                    bot.send_message(
                        message.chat.id, respuesta,
                        parse_mode="HTML",
                        **({"message_thread_id": tid} if tid else {}),
                    )
        else:
            bot.send_message(
                message.chat.id, respuesta,
                parse_mode="HTML",
                **({"message_thread_id": tid} if tid else {}),
            )

    except Exception as e:
        logger.error(f"Error procesando mote: {e}")
        bot.send_message(
            message.chat.id,
            "❌ Error procesando el apodo. El Pokémon quedará sin apodo.",
            **({"message_thread_id": getattr(message, "message_thread_id", None)} 
               if getattr(message, "message_thread_id", None) else {}),
        )