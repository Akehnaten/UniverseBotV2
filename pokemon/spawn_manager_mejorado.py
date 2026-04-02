# -*- coding: utf-8 -*-
"""
Sistema de Spawns Mejorado con Sprite Desconocido
Integrado con wild_battle_system

CAMBIO (fix timer):
    _spawn_loop ahora usa un modelo de "siguiente disparo absoluto"
    (next_spawn_at) en lugar de dormir al inicio de cada iteración.
    Esto garantiza que el temporizador público avance de forma continua
    sin importar si el intento de spawn tuvo éxito, si había un spawn
    activo, o si alguien usó /salvaje (spawn privado).
    Los spawns privados usan canal_id = user_id; los públicos usan
    canal_id = thread_id.  Son claves distintas → nunca se interfieren.
"""

import threading
import time
import random
import logging
from typing import Optional
from pathlib import Path
from telebot import types

from pokemon.services import spawn_service, pokedex_service
from config import CANAL_ID, POKECLUB, POKEMON_SPAWN_CONFIG, UNKNOWN_SPRITE

logger = logging.getLogger(__name__)


class SpawnManager:
    """Gestor de spawns automáticos con sprite desconocido."""

    def __init__(self, bot):
        self.bot = bot
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.canal_id = CANAL_ID
        self.thread_id = POKECLUB
        self.config = POKEMON_SPAWN_CONFIG
        self.sprite_desconocido = Path(UNKNOWN_SPRITE) if UNKNOWN_SPRITE else None
        self.spawn_messages: dict = {}

    # ──────────────────────────────────────────────────────────────────────────
    # CICLO DE VIDA
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Inicia el sistema de spawns automáticos."""
        if not self.config.get("habilitado", False):
            logger.info("[SPAWN] Sistema deshabilitado en configuración.")
            return

        if not self.canal_id or not self.thread_id:
            logger.warning("[SPAWN] Canal/thread no configurado — spawns desactivados.")
            return

        self.running = True
        self.thread = threading.Thread(target=self._spawn_loop, daemon=True)
        self.thread.start()
        logger.info(f"[SPAWN] Sistema iniciado — Canal: {self.canal_id}, Thread: {self.thread_id}")

    def stop(self) -> None:
        """Detiene el sistema de spawns."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("[SPAWN] Sistema detenido.")

    # ──────────────────────────────────────────────────────────────────────────
    # LOOP PRINCIPAL  ← FIX: timer absoluto, independiente de spawns privados
    # ──────────────────────────────────────────────────────────────────────────

    def _spawn_loop(self) -> None:
        """
        Loop de spawns automáticos públicos.

        Temporizador de "siguiente disparo absoluto"
        ─────────────────────────────────────────────
        next_spawn_at avanza de forma continua sin importar si el intento
        de spawn tuvo éxito, si había un spawn activo o si alguien usó
        /salvaje (spawn privado con canal_id = user_id ≠ thread_id).

        • Fallo por spawn activo → se omite el intento, el timer YA avanzó.
        • /salvaje               → usa clave distinta; esta función no la ve.
        • Error de código        → espera 60 s sin tocar next_spawn_at para
                                   no perder la cadencia del ciclo.
        """
        next_spawn_at: float = time.time() + random.randint(
            self.config["intervalo_minimo"],
            self.config["intervalo_maximo"],
        )

        while self.running:
            try:
                remaining = next_spawn_at - time.time()

                if remaining > 0:
                    # Dormir en porciones cortas para reaccionar a stop() rápido.
                    time.sleep(min(remaining, 10))
                    continue

                # Timer expiró → intentar generar spawn público.
                self._generar_spawn_misterioso()

                # Siempre reprogramar el siguiente ciclo, haya spawneado o no.
                next_spawn_at = time.time() + random.randint(
                    self.config["intervalo_minimo"],
                    self.config["intervalo_maximo"],
                )

            except Exception as exc:
                logger.error(f"[SPAWN] Error en loop: {exc}", exc_info=True)
                # Esperar 60 s SIN alterar next_spawn_at para preservar cadencia.
                time.sleep(60)

    # ──────────────────────────────────────────────────────────────────────────
    # GENERACIÓN DE SPAWN MISTERIOSO
    # ──────────────────────────────────────────────────────────────────────────

    def _generar_spawn_misterioso(self) -> bool:
        """
        Genera un spawn público filtrando los Pokémon por la región del servidor.
        Solo pueden aparecer Pokémon válidos para la región actual (config.py).
        """
        try:
            if spawn_service.obtener_spawn_activo(self.thread_id):
                logger.debug("[SPAWN] Spawn público activo — ciclo omitido.")
                return False
 
            # ── Obtener IDs válidos para la región actual ─────────────────
            from config import POKEMON_REGION_SERVIDOR
            from pokemon.region_config import get_wild_ids
 
            ids_validos = get_wild_ids(POKEMON_REGION_SERVIDOR)
            if not ids_validos:
                logger.error("[SPAWN] No hay IDs válidos para la región.")
                return False
 
            import random
            pokemon_id_elegido = random.choice(ids_validos)
 
            # Generar spawn con el ID filtrado por región
            exito, spawn = spawn_service.generar_spawn(
                canal_id   = self.thread_id,
                pokemon_id = pokemon_id_elegido,
            )
 
            if not exito or not spawn:
                return False
 
            shiny_text = " ✨" if spawn.shiny else ""
            caption = (
                f"🌟 <b>¡Un Pokémon salvaje apareció!{shiny_text}</b>\n\n"
                f"❓ Un Pokémon misterioso te está observando...\n"
                f"⚔️ ¿Te atreves a combatirlo?"
            )
 
            from telebot import types
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton(
                    "⚔️ ¡Combatir!",
                    callback_data=f"combatir_{self.thread_id}_{spawn.pokemon_id}",
                )
            )
 
            msg = self._enviar_sprite_o_texto(caption, keyboard)
            if msg:
                self.spawn_messages[self.thread_id] = msg.message_id
                logger.info(
                    f"[SPAWN] #{spawn.pokemon_id} ({spawn.nombre}) "
                    f"en {POKEMON_REGION_SERVIDOR} — thread {self.thread_id}"
                )
                return True
 
            spawn_service.limpiar_spawn(self.thread_id)
            return False
 
        except Exception as exc:
            logger.error(f"[SPAWN] Error en _generar_spawn_misterioso: {exc}", exc_info=True)
            spawn_service.limpiar_spawn(self.thread_id)
            return False

    def _enviar_sprite_o_texto(
        self,
        caption: str,
        keyboard: types.InlineKeyboardMarkup,
    ) -> Optional[types.Message]:
        """
        Envía el sprite desconocido (GIF/foto) o un mensaje de texto como fallback.

        Estrategia de reintento con thread_id:
          1. Intenta enviar sprite con message_thread_id.
          2. Si el sprite falla por hilo inexistente (400 "message thread not found"),
             reintenta el sprite SIN thread_id.
          3. Si el sprite no existe o falla por otro motivo, cae a texto plano.
          4. El fallback de texto también reintenta sin thread_id si el hilo no existe.
        """
        sprite_path = (
            Path(self.sprite_desconocido)
            if isinstance(self.sprite_desconocido, str)
            else self.sprite_desconocido
        )

        def _hilo_no_existe(exc: Exception) -> bool:
            """Detecta si la excepción es un 400 por hilo inexistente."""
            return "message thread not found" in str(exc).lower()

        def _enviar_media(path: Path, thread_id: Optional[int]) -> Optional[types.Message]:
            """Envía GIF o foto desde *path*; thread_id=None omite el hilo."""
            with open(path, "rb") as f:
                is_gif = path.suffix.lower() == ".gif"
                kwargs: dict = dict(
                    chat_id=self.canal_id,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                if thread_id is not None:
                    kwargs["message_thread_id"] = thread_id
                if is_gif:
                    kwargs["animation"] = f
                    return self.bot.send_animation(**kwargs)
                kwargs["photo"] = f
                return self.bot.send_photo(**kwargs)

        # ── Intentar envío con sprite ─────────────────────────────────────────
        # La variable _path captura sprite_path ya verificado como Path (no None)
        # para que el type checker lo vea con tipo concreto dentro de _enviar_media.
        if sprite_path and sprite_path.exists():
            _path: Path = sprite_path
            try:
                return _enviar_media(_path, self.thread_id)
            except Exception as exc:
                if _hilo_no_existe(exc):
                    logger.warning(
                        "[SPAWN] Thread %s no encontrado al enviar sprite — "
                        "reintentando sin thread_id.", self.thread_id
                    )
                    try:
                        return _enviar_media(_path, None)
                    except Exception as exc2:
                        logger.warning(
                            "[SPAWN] Error enviando sprite sin thread_id: %s — usando texto.", exc2
                        )
                else:
                    logger.warning("[SPAWN] Error enviando sprite: %s — usando texto.", exc)

        # ── Fallback a texto plano ────────────────────────────────────────────
        try:
            return self.bot.send_message(
                chat_id=self.canal_id,
                text=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
                message_thread_id=self.thread_id,
            )
        except Exception as exc:
            if _hilo_no_existe(exc):
                logger.warning(
                    "[SPAWN] Thread %s no encontrado en fallback texto — "
                    "reintentando sin thread_id.", self.thread_id
                )
                return self.bot.send_message(
                    chat_id=self.canal_id,
                    text=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            raise

    # ──────────────────────────────────────────────────────────────────────────
    # INICIO DE COMBATE (spawn público)
    # ──────────────────────────────────────────────────────────────────────────

    def iniciar_combate(self, call: types.CallbackQuery, bot) -> None:
        """Inicia combate con el Pokémon salvaje público activo."""
        if not call or not call.data:
            return

        user_id = call.from_user.id
        
        # 1. Validar que exista el mensaje para obtener IDs de chat
        if not call.message:
            bot.answer_callback_query(call.id, "❌ Error: El mensaje original no está disponible.", show_alert=True)
            return

        chat_id = call.message.chat.id
        message_id = call.message.message_id

        try:
            thread_id = int(call.data.split("_")[1])
        except (IndexError, ValueError):
            bot.answer_callback_query(call.id, "❌ Datos inválidos.", show_alert=True)
            return

        spawn = spawn_service.obtener_spawn_activo(thread_id)
        if not spawn:
            bot.answer_callback_query(call.id, "❌ Este Pokémon ya escapó...", show_alert=True)
            try:
                bot.delete_message(chat_id, message_id)
            except Exception:
                pass
            return

        try:
            from pokemon.wild_battle_system import wild_battle_manager

            spawn_data = {
                "pokemon_id": spawn.pokemon_id,
                "nivel":      spawn.nivel,
                "shiny":      spawn.shiny,
            }

            success, message = wild_battle_manager.start_battle(
                user_id=user_id,
                thread_id=thread_id,
                spawn_data=spawn_data,
                bot=bot,
            )

            if not success:
                bot.send_message(user_id, message, parse_mode="HTML")
                return

            battle = wild_battle_manager.get_battle(user_id)
            if battle:
                battle.group_chat_id    = chat_id
                battle.group_message_id = message_id

            try:
                bot.delete_message(chat_id, message_id)
            except Exception:
                pass

        except Exception as exc:
            logger.error(f"[SPAWN] Error iniciando combate: {exc}", exc_info=True)
            try:
                bot.send_message(user_id, "❌ Error iniciando combate. Intenta de nuevo.")
            except Exception:
                pass

# ──────────────────────────────────────────────────────────────────────────────
# INICIALIZACIÓN
# ──────────────────────────────────────────────────────────────────────────────

def inicializar_spawn_manager(bot) -> Optional[SpawnManager]:
    """Inicializa el sistema de spawns y registra el callback de combate."""
    try:
        manager = SpawnManager(bot)
        manager.start()

        @bot.callback_query_handler(func=lambda call: call.data.startswith("combatir_"))
        def callback_combatir(call: types.CallbackQuery) -> None:
            manager.iniciar_combate(call, bot)

        return manager

    except Exception as exc:
        logger.error(f"[SPAWN] Error inicializando SpawnManager: {exc}", exc_info=True)
        return None