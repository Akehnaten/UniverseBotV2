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
        Genera un spawn público con sprite desconocido.

        Retorna True si el spawn se generó con éxito, False si se saltó
        (ya había un spawn activo para este thread) o si falló.

        Nota: esta función SOLO comprueba el spawn activo bajo la clave
        self.thread_id.  Los spawns privados (/salvaje) usan la clave
        user_id y no afectan esta comprobación.
        """
        try:
            # Solo verificar spawn PÚBLICO (thread_id).
            # Los privados (user_id) son independientes y no nos importan aquí.
            if spawn_service.obtener_spawn_activo(self.thread_id):
                logger.debug("[SPAWN] Spawn público activo — ciclo omitido.")
                return False

            exito, spawn = spawn_service.generar_spawn(
                canal_id=self.thread_id,
                pokemon_id=None,
            )

            if not exito or not spawn:
                return False

            shiny_text = " ✨" if spawn.shiny else ""
            caption = (
                f"🌟 <b>¡Un Pokémon salvaje apareció!{shiny_text}</b>\n\n"
                f"❓ Un Pokémon misterioso te está observando...\n"
                f"⚔️ ¿Te atreves a combatirlo?"
            )

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
                    f"[SPAWN] Spawn generado — #{spawn.pokemon_id} "
                    f"({spawn.nombre}) en thread {self.thread_id}"
                )
                return True

            # Si no se pudo enviar el mensaje, limpiar el spawn generado
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
        """Envía el sprite desconocido (GIF/foto) o un mensaje de texto como fallback."""
        sprite_path = (
            Path(self.sprite_desconocido)
            if isinstance(self.sprite_desconocido, str)
            else self.sprite_desconocido
        )

        if sprite_path and sprite_path.exists():
            try:
                with open(sprite_path, "rb") as f:
                    is_gif = sprite_path.suffix.lower() == ".gif"
                    if is_gif:
                        return self.bot.send_animation(
                            chat_id=self.canal_id,
                            animation=f,
                            caption=caption,
                            parse_mode="HTML",
                            reply_markup=keyboard,
                            message_thread_id=self.thread_id,
                        )
                    return self.bot.send_photo(
                        chat_id=self.canal_id,
                        photo=f,
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                        message_thread_id=self.thread_id,
                    )
            except Exception as exc:
                logger.warning(f"[SPAWN] Error enviando sprite: {exc} — usando texto.")

        # Fallback a texto plano
        return self.bot.send_message(
            chat_id=self.canal_id,
            text=caption,
            parse_mode="HTML",
            reply_markup=keyboard,
            message_thread_id=self.thread_id,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # INICIO DE COMBATE (spawn público)
    # ──────────────────────────────────────────────────────────────────────────

    def iniciar_combate(self, call: types.CallbackQuery, bot) -> None:
        """Inicia combate con el Pokémon salvaje público activo."""
        user_id = call.from_user.id

        try:
            thread_id = int(call.data.split("_")[1])
        except (IndexError, ValueError):
            bot.answer_callback_query(call.id, "❌ Datos inválidos.", show_alert=True)
            return

        spawn = spawn_service.obtener_spawn_activo(thread_id)
        if not spawn:
            bot.answer_callback_query(
                call.id, "❌ Este Pokémon ya escapó...", show_alert=True
            )
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass
            return

        try:
            bot.answer_callback_query(call.id, "⚔️ ¡Iniciando batalla!", show_alert=False)
        except Exception:
            pass

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
                battle.group_chat_id    = call.message.chat.id
                battle.group_message_id = call.message.message_id

            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
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