# -*- coding: utf-8 -*-
"""
funciones/user_experience.py
════════════════════════════════════════════════════════════════════════════════
Sistema de experiencia y niveles de usuario.

Curva de XP en tres tramos:
  Tramo 1 (niveles  1–10): fácil            — crece ×1.5  por nivel, base 200
  Tramo 2 (niveles 11–20): muy difícil      — crece ×2.5  por nivel
  Tramo 3 (niveles 21+  ): extremadamente   — crece ×5.0  por nivel

Regla de overflow:
  Si al ganar XP se supera el umbral, se pasa de nivel y SOLO se conserva
  el excedente (no se acumula la exp bruta).  Soporta multi-level-up en un
  solo step (por ejemplo si una recompensa enorme supera varios umbrales).
════════════════════════════════════════════════════════════════════════════════
"""

import logging
import random
from typing import Optional

logger = logging.getLogger(__name__)

# ── Mensajes de felicitación (se elige uno al azar) ───────────────────────────
_MENSAJES_NIVEL = [
    "¡Sigue así, eres imparable! 💪🔥",
    "¡El universo entero te aplaude! 🌌✨",
    "¡Cada paso cuenta, y tú no paras! 🚀⭐",
    "¡Nada te detiene, leyenda en construcción! 👑🌟",
    "¡Estás en llamas! ¡A por el siguiente nivel! 🔥💫",
    "¡Tu dedicación no pasa desapercibida! 💖🏆",
    "¡Subiendo alto, como siempre! 🌠🎯",
    "¡La comunidad está orgullosa de ti! 🎊💝",
]


# Nivel máximo alcanzable por el usuario.
NIVEL_MAXIMO_USUARIO: int = 30


def exp_requerida_usuario(nivel: int) -> int:
    """
    XP necesaria para pasar de ``nivel`` a ``nivel + 1``.

    Curva exponencial suave con ratio 1.15 — aproximadamente 3× más
    difícil que el sistema anterior (lineal), con nivel 30 como techo.

    Ejemplos:
        nivel 1  →   200 XP   (~1 rol)
        nivel 10 →   702 XP   (~3 rols)
        nivel 20 →  2.864 XP  (~12 rols)
        nivel 29 → 10.172 XP  (~42 rols)
        Total hasta nivel 30: ~87.000 XP (~363 rols máximos)
    """
    if nivel < 1:
        return 200
    if nivel >= NIVEL_MAXIMO_USUARIO:
        return 0  # Ya está en el techo — no se puede seguir subiendo
    return round(200 * (1.15 ** (nivel - 1)))


def aplicar_experiencia_usuario(
    user_id:   int,
    exp_ganada: int,
    bot,
    chat_id:   int,
    thread_id: Optional[int] = None,
) -> dict:
    """
    Aplica ``exp_ganada`` al usuario, gestiona multi-level-up con overflow
    correcto y envía mensaje de felicitación al grupo si sube de nivel.

    Regla de overflow:
        Al superar el umbral de un nivel, el excedente pasa al siguiente —
        NO se conserva la exp bruta.

    Args:
        user_id:    ID de Telegram del usuario.
        exp_ganada: Cantidad de experiencia a otorgar (debe ser > 0).
        bot:        Instancia del bot de Telegram.
        chat_id:    ID del chat donde se enviará la felicitación.
        thread_id:  ID del hilo (None en chats privados o sin hilo).

    Returns:
        {
            "subio_nivel":    bool,
            "nivel_anterior": int,
            "nivel_nuevo":    int,
            "exp_actual":     int,
            "exp_siguiente":  int,
        }
    """
    from database import db_manager

    _FALLBACK = {"subio_nivel": False, "nivel_anterior": 1, "nivel_nuevo": 1,
                 "exp_actual": 0, "exp_siguiente": 200}

    if exp_ganada <= 0:
        return _FALLBACK

    try:
        row = db_manager.execute_query(
            "SELECT nivel, experiencia, nombre FROM USUARIOS WHERE userID = ?",
            (user_id,),
        )
        if not row:
            return _FALLBACK

        nivel_actual = int(row[0]["nivel"]       or 1)
        exp_actual   = int(row[0]["experiencia"] or 0)
        nombre       = row[0]["nombre"] or "Usuario"

        exp_actual  += exp_ganada
        nivel_nuevo  = nivel_actual
        niveles_subidos: list[int] = []

       # ── Loop de multi-level-up con overflow ───────────────────────────────
        while nivel_nuevo < NIVEL_MAXIMO_USUARIO:
            umbral = exp_requerida_usuario(nivel_nuevo)
            if exp_actual >= umbral:
                exp_actual  -= umbral   # conservar solo el excedente
                nivel_nuevo += 1
                niveles_subidos.append(nivel_nuevo)
            else:
                break

        # Al llegar al nivel máximo, la exp sobrante se descarta
        if nivel_nuevo >= NIVEL_MAXIMO_USUARIO:
            nivel_nuevo = NIVEL_MAXIMO_USUARIO
            exp_actual  = 0

        # ── Persistir ─────────────────────────────────────────────────────────
        db_manager.execute_update(
            "UPDATE USUARIOS SET nivel = ?, experiencia = ? WHERE userID = ?",
            (nivel_nuevo, exp_actual, user_id),
        )

        logger.info(
            "[USER_EXP] user=%s +%s exp → nv.%s→%s (exp_actual=%s)",
            user_id, exp_ganada, nivel_actual, nivel_nuevo, exp_actual,
        )

        # ── Notificación de subida de nivel ───────────────────────────────────
        if niveles_subidos:
            _notificar_subida(
                bot        = bot,
                chat_id    = chat_id,
                thread_id  = thread_id,
                user_id    = user_id,
                nombre     = nombre,
                nivel_nuevo = nivel_nuevo,
            )

        return {
            "subio_nivel":    bool(niveles_subidos),
            "nivel_anterior": nivel_actual,
            "nivel_nuevo":    nivel_nuevo,
            "exp_actual":     exp_actual,
            "exp_siguiente":  exp_requerida_usuario(nivel_nuevo),
        }

    except Exception as exc:
        logger.error("[USER_EXP] Error aplicando experiencia a user %s: %s", user_id, exc,
                     exc_info=True)
        return _FALLBACK


# ─────────────────────────────────────────────────────────────────────────────
# Helpers privados
# ─────────────────────────────────────────────────────────────────────────────

def _notificar_subida(
    bot,
    chat_id:    int,
    thread_id:  Optional[int],
    user_id:    int,
    nombre:     str,
    nivel_nuevo: int,
) -> None:
    """Envía el mensaje de felicitación al grupo. Nunca lanza excepción."""
    try:
        # Construir mención (funciona con o sin @username)
        from database import db_manager
        u_row = db_manager.execute_query(
            "SELECT nombre_usuario FROM USUARIOS WHERE userID = ?", (user_id,)
        )
        username = (u_row[0]["nombre_usuario"] if u_row else None) or ""
        mencion  = (
            f"@{username}"
            if username
            else f'<a href="tg://user?id={user_id}">{nombre}</a>'
        )

        frase = random.choice(_MENSAJES_NIVEL)

        # Decoración variable según rango de nivel
        if nivel_nuevo <= 10:
            deco_top = "🌟✨🌟"
            deco_mid = "⭐"
        elif nivel_nuevo <= 20:
            deco_top = "💫🔥💫"
            deco_mid = "🔥"
        else:
            deco_top = "👑🌌👑"
            deco_mid = "💎"

        texto = (
            f"{deco_top} <b>¡¡SUBISTE DE NIVEL!!</b> {deco_top}\n\n"
            f"{deco_mid} ¡Felicitaciones, {mencion}! {deco_mid}\n"
            f"🎊 Alcanzaste el <b>Nivel {nivel_nuevo}</b> 🎊\n\n"
            f"{frase}"
        )

        kwargs: dict = {"parse_mode": "HTML"}
        if thread_id:
            kwargs["message_thread_id"] = thread_id

        bot.send_message(chat_id, texto, **kwargs)

    except Exception as exc:
        logger.warning("[USER_EXP] No se pudo enviar notificación de nivel: %s", exc)