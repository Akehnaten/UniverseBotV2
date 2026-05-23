# -*- coding: utf-8 -*-
"""
utils/juan_utils.py
════════════════════════════════════════════════════════════════════════════════
Tracker de mensajes conversacionales de Juan.

Problema resuelto:
  Juan usaba _es_reply_a_juan() que devolvía True para CUALQUIER reply a
  CUALQUIER mensaje del bot (slots, casino, pokémon, carreras, etc.).
  Los users que respondían a un resultado de slots solo querían comentarlo
  entre ellos, pero Juan interrumpía siempre.

Solución:
  Juan marca SOLO sus propios mensajes conversacionales (cuando habla como
  personaje). Al recibir un reply, verifica si es a uno de esos mensajes.
  Si el reply es a un resultado de slots → silencio.
  Si el reply es a "Neeeigh, eso me pareció gracioso" → Juan responde.

  ✅ No requiere cambios en ningún otro handler.
  ✅ Solo se modifican _es_reply_a_juan y _enviar_respuesta en juan_handler.py.

Integración (3 líneas en juan_handler.py):
  1. Al inicio del archivo, junto con los otros imports:
       from utils.juan_utils import juan_tracker

  2. En _enviar_respuesta, capturar el mensaje enviado y marcarlo:
       m = bot.reply_to(message, respuesta)
       juan_tracker.mark_conversational(chat_id, m.message_id)

  3. En _es_reply_a_juan, agregar el check del tracker:
       return juan_tracker.is_conversational_reply(message)
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
from collections import defaultdict
from threading import Lock

logger = logging.getLogger(__name__)

_MAX_POR_CHAT = 500   # IDs máximos guardados por chat antes de limpiar


class JuanConversationTracker:
    """
    Registra los IDs de los mensajes en los que Juan habla como PERSONAJE
    (respuestas conversacionales generadas por Groq/OpenRouter).

    No registra: resultados de slots, spawns de pokémon, anuncios de casino,
    resultados de carreras, ni ningún otro mensaje de sistema del bot.

    Thread-safe. Los IDs se guardan en memoria (se pierden al reiniciar,
    lo cual es aceptable — Juan podría responder alguna vez de más justo
    después de un reinicio, pero es un caso edge sin consecuencias graves).
    """

    def __init__(self) -> None:
        self._ids:   dict[int, list[int]] = defaultdict(list)
        self._set:   dict[int, set[int]]  = defaultdict(set)
        self._lock   = Lock()

    # ── API pública ───────────────────────────────────────────────────────────

    def mark_conversational(self, chat_id: int, message_id: int) -> None:
        """
        Registra un mensaje como respuesta conversacional de Juan.
        Llamar justo después de bot.reply_to() o bot.send_message() en _enviar_respuesta.

        Ejemplo:
            m = bot.reply_to(message, respuesta)
            juan_tracker.mark_conversational(chat_id, m.message_id)
        """
        with self._lock:
            lista = self._ids[chat_id]
            s     = self._set[chat_id]

            if message_id in s:
                return

            lista.append(message_id)
            s.add(message_id)

            if len(lista) > _MAX_POR_CHAT:
                a_borrar = lista[: len(lista) - _MAX_POR_CHAT]
                for mid in a_borrar:
                    s.discard(mid)
                self._ids[chat_id] = lista[len(a_borrar):]

    def is_conversational_reply(self, message) -> bool:
        """
        Retorna True si el mensaje es un reply a una respuesta conversacional
        de Juan (marcada previamente con mark_conversational).

        Retorna False si el reply es a cualquier otro mensaje del bot
        (slots, casino, pokémon, carreras, etc.).

        Usar en _es_reply_a_juan():
            return juan_tracker.is_conversational_reply(message)
        """
        reply = getattr(message, "reply_to_message", None)
        if not reply:
            return False

        with self._lock:
            return reply.message_id in self._set.get(message.chat.id, set())

    def stats(self) -> dict:
        """Estadísticas del tracker (para debug)."""
        with self._lock:
            return {cid: len(s) for cid, s in self._set.items() if s}


# ─── Singleton ────────────────────────────────────────────────────────────────

juan_tracker = JuanConversationTracker()
