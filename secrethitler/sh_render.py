# -*- coding: utf-8 -*-
"""
secrethitler/sh_render.py
════════════════════════════════════════════════════════════════════════════════
Renderizado de textos HTML para Secret Hitler. Funciones puras: reciben datos
del motor y devuelven strings. No envían nada.
"""
from __future__ import annotations

from secrethitler.game_engine import (
    SecretHitlerGame, Jugador, Rol, Politica, Poder,
    POLITICAS_LIBERALES_PARA_GANAR, POLITICAS_FASCISTAS_PARA_GANAR,
)

LIB = "🔵"
FAS = "🔴"
MUERTO = "💀"


def _mencion(j: Jugador) -> str:
    return f'<a href="tg://user?id={j.uid}">{j.nombre}</a>'


def carta_rol(info: dict) -> str:
    """DM individual con el rol secreto del jugador."""
    rol: Rol = info["rol"]
    if rol == Rol.LIBERAL:
        txt = (
            f"{LIB} <b>Tu rol secreto: LIBERAL</b>\n\n"
            "Tu objetivo es promulgar 5 políticas liberales o ejecutar a Hitler.\n"
            "No sabés quién es nadie. Confiá con cuidado."
        )
        return txt

    if rol == Rol.HITLER:
        base = (
            f"{FAS} <b>Tu rol secreto: HITLER</b>\n\n"
            "Sos el líder oculto fascista. Ganás si se promulgan 6 políticas "
            "fascistas, o si te eligen Canciller con 3+ políticas fascistas en "
            "el tablero. Hacete pasar por liberal."
        )
    else:
        base = (
            f"{FAS} <b>Tu rol secreto: FASCISTA</b>\n\n"
            "Ganás si se promulgan 6 políticas fascistas o si Hitler llega a "
            "Canciller con 3+ fascistas en el tablero. Protegé a Hitler sin "
            "delatarlo."
        )

    if info.get("ve_companeros") and info.get("companeros"):
        lineas = []
        for uid, nombre, rol_c in info["companeros"]:
            etiqueta = "Hitler" if rol_c == Rol.HITLER else "Fascista"
            lineas.append(f"  • {nombre} — <i>{etiqueta}</i>")
        base += "\n\n<b>Tu equipo:</b>\n" + "\n".join(lineas)
    elif rol == Rol.HITLER:
        base += "\n\n<i>En esta partida no conocés a tus compañeros fascistas.</i>"

    return base


def tablero(game: SecretHitlerGame) -> str:
    """Estado público del tablero."""
    lib = LIB * game.politicas_liberales + "▫️" * (
        POLITICAS_LIBERALES_PARA_GANAR - game.politicas_liberales)
    fas = FAS * game.politicas_fascistas + "▫️" * (
        POLITICAS_FASCISTAS_PARA_GANAR - game.politicas_fascistas)

    presi = game.jugador(game.uid_presidente)
    linea_presi = _mencion(presi) if presi else "—"

    vivos = ", ".join(
        (_mencion(j) if j.vivo else f"{MUERTO} {j.nombre}")
        for j in game.jugadores
    )

    return (
        "🏛 <b>SECRET HITLER</b>\n\n"
        f"{LIB} Liberales: {lib}  ({game.politicas_liberales}/5)\n"
        f"{FAS} Fascistas: {fas}  ({game.politicas_fascistas}/6)\n\n"
        f"🗳 Mazo: {len(game.mazo)} cartas · Descarte: {len(game.descarte)}\n"
        f"⚠️ Elecciones fallidas: {game.estado_caos}/3\n\n"
        f"👑 Presidente: {linea_presi}\n"
        f"👥 {vivos}"
    )


def anuncio_nominacion(game: SecretHitlerGame) -> str:
    presi = game.jugador(game.uid_presidente)
    return (
        f"👑 {_mencion(presi)} es el <b>Presidente</b>.\n\n"
        "Elegí a tu Canciller con los botones de abajo."
    )


def anuncio_votacion(game: SecretHitlerGame) -> str:
    presi = game.jugador(game.uid_presidente)
    canc = game.jugador(game.uid_canciller)
    return (
        "🗳 <b>VOTACIÓN DE GOBIERNO</b>\n\n"
        f"👑 Presidente: {_mencion(presi)}\n"
        f"🎖 Canciller: {_mencion(canc)}\n\n"
        "Voten en secreto. Se revelan todos juntos.\n"
        f"Votos: 0/{len(game.vivos)}"
    )


def resultado_votacion(game: SecretHitlerGame, r: dict) -> str:
    detalle = []
    for j in game.vivos:
        v = game.votos.get(j.uid)
        marca = "✅ Ja" if v else ("❌ Nein" if v is not None else "—")
        detalle.append(f"  {j.nombre}: {marca}")

    cab = "✅ <b>GOBIERNO APROBADO</b>" if r["aprobado"] else "❌ <b>GOBIERNO RECHAZADO</b>"
    return (
        f"{cab}\n\n"
        f"Ja: {r['ja']}  ·  Nein: {r['nein']}\n\n"
        + "\n".join(detalle)
    )


def mano_para_descartar(cartas: list[Politica], es_presidente: bool) -> str:
    quien = "Presidente" if es_presidente else "Canciller"
    accion = "descartá 1" if es_presidente else "elegí cuál promulgar (descartá 1)"
    iconos = "  ".join(LIB if c == Politica.LIBERAL else FAS for c in cartas)
    return (
        f"📜 <b>Fase legislativa — {quien}</b>\n\n"
        f"Tenés estas cartas:\n{iconos}\n\n"
        f"{accion.capitalize()} con los botones."
    )


def anuncio_promulgacion(politica: Politica) -> str:
    if politica == Politica.LIBERAL:
        return f"{LIB} Se promulgó una política <b>LIBERAL</b>."
    return f"{FAS} Se promulgó una política <b>FASCISTA</b>."


def propuesta_veto(game: SecretHitlerGame) -> str:
    presi = game.jugador(game.uid_presidente)
    canc = game.jugador(game.uid_canciller)
    return (
        "🚫 <b>¡VETO PROPUESTO!</b>\n\n"
        f"El Canciller {_mencion(canc)} quiere vetar la agenda completa.\n\n"
        f"{_mencion(presi)} (Presidente), ¿aceptás el veto?\n"
        "• Si <b>aceptás</b>: ambas cartas se descartan, no se promulga nada y "
        "cuenta como una elección fallida.\n"
        "• Si <b>rechazás</b>: el Canciller deberá promulgar igual."
    )


def veto_rechazado(game: SecretHitlerGame) -> str:
    canc = game.jugador(game.uid_canciller)
    return (
        "❌ <b>Veto rechazado.</b>\n"
        f"{_mencion(canc)} debe promulgar una política. (en DM)"
    )


def veto_aceptado() -> str:
    return (
        "✅ <b>Veto aceptado.</b>\n"
        "Ambas cartas fueron descartadas. No se promulgó ninguna política y "
        "cuenta como elección fallida."
    )


def anuncio_poder(poder: Poder, game: SecretHitlerGame) -> str:
    presi = game.jugador(game.uid_presidente)
    txt = {
        Poder.INVESTIGAR: "🔍 Investigar lealtad de un jugador",
        Poder.ELECCION_ESPECIAL: "🎯 Elegir al próximo Presidente",
        Poder.PEEK: "👁 Mirar las próximas 3 cartas del mazo",
        Poder.EJECUTAR: "💀 Ejecutar a un jugador",
    }[poder]
    return (
        f"⚡ <b>Poder presidencial activado</b>\n\n"
        f"{_mencion(presi)} debe: {txt}."
    )


def fin_juego(ganador: str, motivo: str, game: SecretHitlerGame) -> str:
    icono = LIB if ganador == "liberal" else FAS
    titulo = "LIBERALES" if ganador == "liberal" else "FASCISTAS"
    roles = []
    for j in game.jugadores:
        et = {Rol.LIBERAL: "Liberal", Rol.FASCISTA: "Fascista",
              Rol.HITLER: "Hitler"}[j.rol]
        marca = "" if j.vivo else f" {MUERTO}"
        roles.append(f"  • {j.nombre}: {et}{marca}")
    return (
        f"{icono} <b>¡GANAN LOS {titulo}!</b>\n\n"
        f"{motivo}\n\n"
        "<b>Roles revelados:</b>\n" + "\n".join(roles)
    )
