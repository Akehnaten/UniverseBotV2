# -*- coding: utf-8 -*-
"""
funciones/pokedex_usuario.py
════════════════════════════════════════════════════════════════════════════════
Servicio de Pokédex personal del usuario.

Responsabilidades:
  · registrar_avistado(user_id, pokemon_id)   — al aparecer en combate
  · registrar_capturado(user_id, pokemon_id)  — al capturar
  · obtener_progreso(user_id)                 — % completado en la región
  · verificar_pokedex_completa(user_id, bot)  — entrega Amuleto Iris si completa
  · get_shiny_multiplier(user_id)             — x3 si tiene Amuleto Iris

La región se lee de config.POKEMON_REGION_SERVIDOR para ser consistente
con el resto del sistema.
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from database import db_manager
from config import POKEMON_REGION_SERVIDOR

logger = logging.getLogger(__name__)

# ── Rangos de IDs nativos por región ─────────────────────────────────────────
_RANGOS_REGION: dict[str, tuple[int, int]] = {
    "KANTO":   (1,    151),
    "JOHTO":   (152,  251),
    "HOENN":   (252,  386),
    "SINNOH":  (387,  493),
    "TESELIA": (494,  649),
    "KALOS":   (650,  721),
    "ALOLA":   (722,  809),
    "GALAR":   (810,  905),
    "PALDEA":  (906, 1025),
}

# ── Profesor de cada región ───────────────────────────────────────────────────
_PROFESOR_REGION: dict[str, str] = {
    "KANTO":   "Profesor Oak",
    "JOHTO":   "Profesor Elm",
    "HOENN":   "Profesor Birch",
    "SINNOH":  "Profesor Rowan",
    "TESELIA": "Profesora Juniper",
    "KALOS":   "Profesor Sycamore",
    "ALOLA":   "Profesor Kukui",
    "GALAR":   "Profesor Magnolia",
    "PALDEA":  "Profesor Olim",
}

# ── Clave interna del Amuleto Iris en BD ──────────────────────────────────────
_FLAG_AMULETO = "amuleto_iris"


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _ids_region(region: str) -> tuple[int, int]:
    """Devuelve (id_min, id_max) para la región."""
    return _RANGOS_REGION.get(region.upper(), (1, 151))


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRO
# ─────────────────────────────────────────────────────────────────────────────

def registrar_avistado(user_id: int, pokemon_id: int) -> None:
    """
    Marca un Pokémon como avistado en la Pokédex del usuario.
    Idempotente: si ya existe el registro lo deja intacto.
    Llamar cuando el Pokémon aparece en el encuentro/batalla.
    """
    try:
        db_manager.execute_update(
            """
            INSERT INTO POKEDEX_USUARIO
                (userID, pokemonID, avistado, capturado, fecha_vista)
            VALUES (?, ?, 1, 0, ?)
            ON CONFLICT(userID, pokemonID) DO UPDATE SET
                avistado = 1
            """,
            (user_id, pokemon_id, datetime.now().isoformat()),
        )
    except Exception as e:
        logger.error(
            f"[POKEDEX] registrar_avistado error ({user_id}, {pokemon_id}): {e}"
        )


def registrar_capturado(
    user_id:   int,
    pokemon_id: int,
    bot=None,
    chat_id:   Optional[int] = None,
    thread_id: Optional[int] = None,
) -> None:
    """
    Marca un Pokémon como capturado en la Pokédex del usuario.
    También lo marca como avistado si no lo estaba.
    Tras registrar, dispara la verificación de Pokédex completa.

    Args:
        user_id:    Telegram ID del usuario.
        pokemon_id: ID del Pokémon capturado.
        bot:        Instancia del bot (para enviar el mensaje del Amuleto Iris).
        chat_id:    Chat donde enviar el mensaje (normalmente el grupo principal).
        thread_id:  Thread/hilo del chat (opcional).
    """
    try:
        now = datetime.now().isoformat()
        db_manager.execute_update(
            """
            INSERT INTO POKEDEX_USUARIO
                (userID, pokemonID, avistado, capturado, fecha_vista, fecha_captura)
            VALUES (?, ?, 1, 1, ?, ?)
            ON CONFLICT(userID, pokemonID) DO UPDATE SET
                avistado      = 1,
                capturado     = 1,
                fecha_captura = COALESCE(POKEDEX_USUARIO.fecha_captura,
                                         excluded.fecha_captura)
            """,
            (user_id, pokemon_id, now, now),
        )
        if bot and chat_id:
            verificar_pokedex_completa(user_id, bot, chat_id, thread_id)
    except Exception as e:
        logger.error(
            f"[POKEDEX] registrar_capturado error ({user_id}, {pokemon_id}): {e}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# PROGRESO
# ─────────────────────────────────────────────────────────────────────────────

def obtener_progreso(user_id: int, region: str = None) -> dict:
    """
    Devuelve el progreso de la Pokédex del usuario en la región indicada.

    Returns:
        {
            "region":     str,
            "total":      int,   # Pokémon nativos de la región
            "avistados":  int,
            "capturados": int,
            "completa":   bool,  # True si capturó todos los de la región
        }
    """
    region = (region or POKEMON_REGION_SERVIDOR).upper()
    id_min, id_max = _ids_region(region)
    total = id_max - id_min + 1

    try:
        rows = db_manager.execute_query(
            """
            SELECT COALESCE(SUM(avistado),  0) AS av,
                   COALESCE(SUM(capturado), 0) AS cap
            FROM POKEDEX_USUARIO
            WHERE userID    = ?
              AND pokemonID >= ?
              AND pokemonID <= ?
            """,
            (user_id, id_min, id_max),
        )
        av  = int(rows[0]["av"])  if rows else 0
        cap = int(rows[0]["cap"]) if rows else 0
    except Exception as e:
        logger.error(f"[POKEDEX] obtener_progreso error ({user_id}): {e}")
        av = cap = 0

    return {
        "region":     region,
        "total":      total,
        "avistados":  av,
        "capturados": cap,
        "completa":   cap >= total,
    }


# ─────────────────────────────────────────────────────────────────────────────
# AMULETO IRIS
# ─────────────────────────────────────────────────────────────────────────────

def tiene_amuleto_iris(user_id: int) -> bool:
    """True si el usuario ya obtuvo el Amuleto Iris."""
    try:
        row = db_manager.execute_query(
            "SELECT cantidad FROM INVENTARIO_USUARIO "
            "WHERE userID = ? AND item_nombre = ?",
            (user_id, _FLAG_AMULETO),
        )
        return bool(row and int(row[0]["cantidad"]) > 0)
    except Exception:
        return False


def _otorgar_amuleto(user_id: int) -> bool:
    """
    Inserta el Amuleto Iris en INVENTARIO_USUARIO del usuario.
    Returns True si es la primera entrega.
    """
    if tiene_amuleto_iris(user_id):
        return False
    try:
        db_manager.execute_update(
            """
            INSERT INTO INVENTARIO_USUARIO (userID, item_nombre, cantidad)
            VALUES (?, ?, 1)
            ON CONFLICT(userID, item_nombre) DO UPDATE SET cantidad = 1
            """,
            (user_id, _FLAG_AMULETO),
        )
        logger.info(f"[POKEDEX] Amuleto Iris otorgado a user {user_id}")
        return True
    except Exception as e:
        logger.error(f"[POKEDEX] Error otorgando Amuleto Iris a {user_id}: {e}")
        return False


def verificar_pokedex_completa(
    user_id:   int,
    bot,
    chat_id:   int,
    thread_id: Optional[int] = None,
) -> None:
    """
    Comprueba si el usuario completó la Pokédex regional y, si es la primera
    vez, otorga el Amuleto Iris y envía el mensaje del Profesor.
    """
    region = POKEMON_REGION_SERVIDOR.upper()
    progreso = obtener_progreso(user_id, region)

    if not progreso["completa"]:
        return

    primera_vez = _otorgar_amuleto(user_id)
    if not primera_vez:
        return  # Ya lo tenía — no repetir el mensaje

    # ── Obtener nombre del usuario ────────────────────────────────────────────
    nombre_usuario = "Entrenador"
    try:
        row = db_manager.execute_query(
            "SELECT nombre FROM USUARIOS WHERE userID = ?", (user_id,)
        )
        if row:
            nombre_usuario = row[0]["nombre"] or nombre_usuario
    except Exception:
        pass

    profesor = _PROFESOR_REGION.get(region, "el Profesor Pokémon")

    texto = (
        f"🎊 <b>¡Pokédex de {region} completada!</b>\n\n"
        f"📞 <i>Llamada entrante: {profesor}...</i>\n\n"
        f"<b>{profesor}:</b>  ¡{nombre_usuario}! ¡No puedo creerlo!\n"
        f"Has visto y capturado a <b>todos los Pokémon</b> de nuestra región.\n"
        f"Eres el/la primer/a Entrenador/a en lograrlo. ¡Extraordinario!\n\n"
        f"Como pequeña muestra de mi admiración, te envío este obsequio:\n\n"
        f"🌈 <b>¡{nombre_usuario} recibió el Amuleto Iris!</b>\n"
        f"<i>Un amuleto tejido con escamas de Pokémon raros que atrae "
        f"a los Pokémon de colores inusuales...</i>\n\n"
        f"✨ <b>Efecto activo:</b>  ×3 probabilidad de encontrar Pokémon Shiny.\n"
        f"<code>({1/4096:.6f} → {3/4096:.6f} por encuentro)</code>"
    )

    try:
        kwargs: dict = {"parse_mode": "HTML"}
        if thread_id:
            kwargs["message_thread_id"] = thread_id
        bot.send_message(chat_id, texto, **kwargs)
    except Exception as e:
        logger.error(f"[POKEDEX] Error enviando mensaje Amuleto Iris: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# MULTIPLICADOR SHINY
# ─────────────────────────────────────────────────────────────────────────────

def get_shiny_multiplier(user_id: int) -> float:
    """
    Devuelve el multiplicador de probabilidad shiny para el usuario.
      · Sin Amuleto Iris: 1.0  (probabilidad base de config)
      · Con Amuleto Iris: 3.0  (×3 más probable)
    """
    return 3.0 if tiene_amuleto_iris(user_id) else 1.0
