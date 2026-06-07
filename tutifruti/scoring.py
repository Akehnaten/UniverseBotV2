# -*- coding: utf-8 -*-
"""
tutifruti/scoring.py
════════════════════════════════════════════════════════════════════════════════
Lógica PURA de puntuación del Tuti Fruti. Sin Telegram, sin BD: recibe datos
y devuelve puntajes. Fácil de testear.

Categorías fijas (11) y esquema de puntaje:
  • 15 puntos: sos el ÚNICO jugador que respondió esa categoría (con palabra válida).
  • 10 puntos: varios respondieron, pero tu palabra es única (nadie la repitió).
  •  5 puntos: tu palabra está repetida por otro jugador.
  •  0 puntos: respuesta vacía o invalidada por la comunidad (más X que V).
"""
from __future__ import annotations

import unicodedata

CATEGORIAS = [
    "Nombre",
    "País/Provincia",
    "Animal",
    "Color",
    "Cosa",
    "Fruta",
    "Series/Pelis",
    "Deportes",
    "Grupos/Solistas",
    "Marcas",
    "Comidas",
]

PUNTOS_UNICO_ABSOLUTO = 15   # único que contestó la categoría
PUNTOS_UNICO = 10            # varios contestaron, palabra no repetida
PUNTOS_REPETIDO = 5          # palabra repetida
PUNTOS_NULO = 0              # vacío o invalidado


def normalizar(palabra: str) -> str:
    """
    Normaliza para comparar repetidos: minúsculas, sin acentos, sin espacios
    extra. 'Águila' y 'aguila' se consideran iguales.
    """
    if not palabra:
        return ""
    txt = palabra.strip().lower()
    txt = "".join(
        c for c in unicodedata.normalize("NFD", txt)
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(txt.split())


def calcular_puntajes(
    respuestas: dict[int, dict[str, str]],
    validez: dict[int, dict[str, bool]],
) -> dict[int, dict[str, int]]:
    """
    Calcula los puntos de todos los jugadores.

    Parámetros
    ----------
    respuestas : {uid: {categoria: palabra}}
        Lo que escribió cada jugador.
    validez : {uid: {categoria: bool}}
        Resultado de la votación comunitaria. True = válida, False = invalidada.
        Si una palabra no aparece en `validez`, se asume válida (no se votó en
        contra).

    Devuelve
    --------
    {uid: {categoria: puntos}}
    """
    puntajes: dict[int, dict[str, int]] = {uid: {} for uid in respuestas}

    for categoria in CATEGORIAS:
        # Recolectar palabras válidas y no vacías de esta categoría.
        validas: dict[int, str] = {}   # uid -> palabra normalizada
        for uid, fila in respuestas.items():
            palabra = (fila.get(categoria) or "").strip()
            es_valida = validez.get(uid, {}).get(categoria, True)
            if palabra and es_valida:
                validas[uid] = normalizar(palabra)

        if not validas:
            # Nadie respondió válidamente: todos 0 en esta categoría.
            for uid in respuestas:
                puntajes[uid][categoria] = PUNTOS_NULO
            continue

        # Contar repeticiones por palabra normalizada.
        conteo: dict[str, int] = {}
        for w in validas.values():
            conteo[w] = conteo.get(w, 0) + 1

        unico_jugador = len(validas) == 1

        for uid in respuestas:
            if uid not in validas:
                puntajes[uid][categoria] = PUNTOS_NULO
                continue
            w = validas[uid]
            if unico_jugador:
                puntajes[uid][categoria] = PUNTOS_UNICO_ABSOLUTO
            elif conteo[w] == 1:
                puntajes[uid][categoria] = PUNTOS_UNICO
            else:
                puntajes[uid][categoria] = PUNTOS_REPETIDO

    return puntajes


def totales(puntajes: dict[int, dict[str, int]]) -> dict[int, int]:
    """Suma el puntaje total de cada jugador."""
    return {uid: sum(cats.values()) for uid, cats in puntajes.items()}


def palabra_valida_por_votos(votos_v: int, votos_x: int) -> bool:
    """
    Regla de validación comunitaria: más V que X = válida.
    Empate = válida (beneficio de la duda).
    """
    return votos_v >= votos_x
