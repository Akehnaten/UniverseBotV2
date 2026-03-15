# -*- coding: utf-8 -*-
"""
funciones/slots_service.py
════════════════════════════════════════════════════════════════════════════════
Motor de Slots K-pop para UniverseBot V2.0

Características:
  - Grilla 3×3 con 5 líneas de pago (3 horizontales + 2 diagonales)
  - 9 símbolos temáticos K-pop con pesos de rareza ajustados a RTP ~75%
  - Comodín (⭐ LIGHTSTICK) que sustituye cualquier símbolo en líneas
  - Símbolo BONUS (🎁 FANMAIL) que otorga giro gratis al salir x3
  - Jackpot por Triple Crown (👑) con multiplicador máximo
  - Animación de giro por fases con edición de mensajes
  - Lógica pura sin dependencias de Telegram (testeable de forma aislada)

RTP objetivo: ~75%  (la casa retiene ~25% a largo plazo)

Diseño:
  - Funciones puras + una dataclass SlotResult inmutable
  - Sin estado global; el handler maneja toda la persistencia
════════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import random
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Símbolos ─────────────────────────────────────────────────────────────────

# Cada entrada: (emoji, nombre_interno, peso_relativo, multiplicador_trio)
# El peso controla la frecuencia de aparición en cada celda.
# Multiplicadores sobre la apuesta cuando salen 3 iguales en una línea.
#
# Cálculo de RTP aproximado (simulado 10M de giros):
#   ~75% con estos pesos y multiplicadores.

SIMBOLOS: List[Tuple[str, str, int, int]] = [
    # emoji     nombre          peso  mult_trio
    # ─────────────────────────────────────────────────────────────────────
    # Pesos y multiplicadores calibrados para un RTP real de ~76%.
    # Simulado con 500.000 giros a apuesta fija.
    # Fórmula de par+wild: round(mult_base * 0.5) — ver _evaluar_linea().
    # ─────────────────────────────────────────────────────────────────────
    # ── Comunes ───────────────────────────────────────────────────────────
    ("💿",     "ALBUM",          32,    2),   # Común      ×2
    ("🎤",     "MICROFONO",      28,    2),   # Común      ×2
    # ── Poco comunes ──────────────────────────────────────────────────────
    ("🪄",     "VARITA",         20,    3),   # Poco común ×3
    ("📸",     "PHOTOCARD",      14,    4),   # Poco común ×4
    # ── Raros ─────────────────────────────────────────────────────────────
    ("💜",     "CORAZON",        10,    5),   # Raro       ×5
    ("🏆",     "TROFEO",          6,    7),   # Raro       ×7
    # ── Muy raros ─────────────────────────────────────────────────────────
    ("💎",     "DIAMANTE",        3,   10),   # Muy raro   ×10
    # ── Especiales ────────────────────────────────────────────────────────
    ("⭐",     "LIGHTSTICK",      7,    0),   # WILD  — peso 7 → RTP ~76%
    ("🎁",     "FANMAIL",         3,   12),   # BONUS — triple = giro gratis + ×12
    ("👑",     "CROWN",           2,   20),   # JACKPOT    ×20
]

# Índices especiales
_EMOJI   = 0
_NOMBRE  = 1
_PESO    = 2
_MULT    = 3

WILD_NOMBRE   = "LIGHTSTICK"
BONUS_NOMBRE  = "FANMAIL"
JACKPOT_NOMBRE = "CROWN"

# Universo de símbolos expandido según peso (para random.choices)
_POOL:   List[str] = []
_PESOS:  List[int] = []

for _emoji, _nombre, _peso, _mult in SIMBOLOS:
    _POOL.append(_nombre)
    _PESOS.append(_peso)

# Diccionario rápido: nombre → (emoji, multiplicador_trio)
SIMBOLO_INFO: dict[str, Tuple[str, int]] = {
    nombre: (emoji, mult)
    for emoji, nombre, _, mult in SIMBOLOS
}

# ─── Líneas de pago ───────────────────────────────────────────────────────────
#
# La grilla es una lista plana de 9 celdas indexadas así:
#
#   0 │ 1 │ 2      ← fila superior
#  ───┼───┼───
#   3 │ 4 │ 5      ← fila central  (línea estrella ★)
#  ───┼───┼───
#   6 │ 7 │ 8      ← fila inferior
#
# Líneas activas (siempre las 5):

LINEAS: List[Tuple[str, Tuple[int, int, int]]] = [
    ("Fila Superior",  (0, 1, 2)),
    ("Fila Central ★", (3, 4, 5)),   # línea principal / más visible
    ("Fila Inferior",  (6, 7, 8)),
    ("Diagonal ↘",     (0, 4, 8)),
    ("Diagonal ↗",     (6, 4, 2)),
]

# ─── Dataclass de resultado ───────────────────────────────────────────────────

@dataclass(frozen=True)
class LineaResultado:
    """Resultado de una línea de pago individual."""
    nombre:      str
    indices:     Tuple[int, int, int]
    simbolos:    Tuple[str, str, str]   # nombres internos
    ganadora:    bool
    descripcion: str                    # texto legible para el mensaje
    multiplicador: int                  # 0 si no gana


@dataclass(frozen=True)
class SlotResult:
    """
    Resultado completo de un giro.

    Attributes:
        grilla:        Lista de 9 nombres internos de símbolos (fila × col).
        lineas:        Evaluación de cada línea de pago.
        apuesta:       Cosmos apostados.
        ganancia_neta: Cosmos ganados (positivo) o perdidos (negativo).
        giro_gratis:   True si salieron 3 FANMAIL en alguna línea.
        jackpot:       True si salieron 3 CROWN en alguna línea.
        rtp_giro:      Ratio ganancia/apuesta de este giro (info/debug).
    """
    grilla:        List[str]
    lineas:        List[LineaResultado]
    apuesta:       int
    ganancia_neta: int
    giro_gratis:   bool
    jackpot:       bool
    rtp_giro:      float


# ─── Motor principal ──────────────────────────────────────────────────────────

def girar(apuesta: int) -> SlotResult:
    """
    Ejecuta un giro completo de la tragaperras.

    Args:
        apuesta: Cosmos apostados (entero positivo).

    Returns:
        SlotResult con toda la información del giro.

    Raises:
        ValueError: Si la apuesta es ≤ 0.
    """
    if apuesta <= 0:
        raise ValueError(f"La apuesta debe ser positiva, recibido: {apuesta}")

    # 1. Generar grilla 3×3
    grilla: List[str] = random.choices(_POOL, weights=_PESOS, k=9)

    # 2. Evaluar cada línea
    lineas_resultado: List[LineaResultado] = []
    ganancia_bruta   = 0
    hay_giro_gratis  = False
    hay_jackpot      = False

    for nombre_linea, (i0, i1, i2) in LINEAS:
        s0, s1, s2 = grilla[i0], grilla[i1], grilla[i2]
        lr = _evaluar_linea(nombre_linea, (i0, i1, i2), (s0, s1, s2), apuesta)
        lineas_resultado.append(lr)

        if lr.ganadora:
            ganancia_bruta += lr.multiplicador * apuesta

            # Detectar bonus especiales
            simbolos_efectivos = _simbolos_sin_wild((s0, s1, s2))
            if simbolos_efectivos and simbolos_efectivos[0] == BONUS_NOMBRE:
                hay_giro_gratis = True
            if simbolos_efectivos and simbolos_efectivos[0] == JACKPOT_NOMBRE:
                hay_jackpot = True

    ganancia_neta = ganancia_bruta - apuesta   # descontamos la apuesta
    rtp            = ganancia_bruta / apuesta if apuesta else 0.0

    logger.debug(
        "Slots | apuesta=%d bruta=%d neta=%d jackpot=%s freeplay=%s",
        apuesta, ganancia_bruta, ganancia_neta, hay_jackpot, hay_giro_gratis,
    )

    return SlotResult(
        grilla        = grilla,
        lineas        = lineas_resultado,
        apuesta       = apuesta,
        ganancia_neta = ganancia_neta,
        giro_gratis   = hay_giro_gratis,
        jackpot       = hay_jackpot,
        rtp_giro      = rtp,
    )


# ─── Evaluación de línea ──────────────────────────────────────────────────────

def _evaluar_linea(
    nombre_linea: str,
    indices: Tuple[int, int, int],
    simbolos: Tuple[str, str, str],
    apuesta: int,
) -> LineaResultado:
    """
    Evalúa una línea de 3 símbolos y retorna su resultado.

    Reglas:
      - WILD (LIGHTSTICK) sustituye cualquier símbolo no-WILD.
      - Trío puro o con wilds → gana con mult del símbolo efectivo.
      - Par + wild → gana con mult del símbolo × 0.6 (redondeado).
      - BONUS × 3 → gana con su propio mult + activa giro gratis.
      - Si todos son WILD → mult del LIGHTSTICK (0) → no gana (evita abuso).
    """
    s0, s1, s2 = simbolos

    # Contar wilds
    wilds = sum(1 for s in simbolos if s == WILD_NOMBRE)

    # Símbolos no-wild presentes
    no_wilds = [s for s in simbolos if s != WILD_NOMBRE]

    # ── Todos wild: no paga (prevent jackpot trivial) ─────────────────────
    if wilds == 3:
        return LineaResultado(
            nombre       = nombre_linea,
            indices      = indices,
            simbolos     = simbolos,
            ganadora     = False,
            descripcion  = "⭐⭐⭐ Triple Wild — sin premio",
            multiplicador= 0,
        )

    # ── Sin wilds o con wilds: necesitamos que los no-wilds sean iguales ──
    simbolo_efectivo = no_wilds[0] if no_wilds else None
    todos_iguales    = all(s == simbolo_efectivo for s in no_wilds)

    if not todos_iguales:
        # Sin combinación
        return LineaResultado(
            nombre       = nombre_linea,
            indices      = indices,
            simbolos     = simbolos,
            ganadora     = False,
            descripcion  = "",
            multiplicador= 0,
        )

    # ── Hay combinación ganadora ───────────────────────────────────────────
    emoji_ef, mult_base = SIMBOLO_INFO[simbolo_efectivo]

    if wilds == 0:
        # Trío puro
        mult        = mult_base
        descripcion = f"🎯 Trío {emoji_ef}{emoji_ef}{emoji_ef} → ×{mult}"
    elif wilds == 1:
        # Par + wild  (factor 0.5 calibrado para RTP ~76%)
        mult        = max(1, round(mult_base * 0.5))
        descripcion = f"⭐ Par+Wild {emoji_ef}{emoji_ef} → ×{mult}"
    else:
        # Un símbolo + dos wilds (trío efectivo con boost moderado)
        mult        = max(1, round(mult_base * 1.1))
        descripcion = f"⭐⭐ Wild Boost {emoji_ef} → ×{mult}"

    # Texto especial para jackpot y bonus
    if simbolo_efectivo == JACKPOT_NOMBRE:
        descripcion = f"👑 ¡¡JACKPOT!! Triple Crown → ×{mult}"
    elif simbolo_efectivo == BONUS_NOMBRE:
        descripcion = f"🎁 ¡BONUS! Triple Fanmail → ×{mult} + Giro Gratis"

    return LineaResultado(
        nombre       = nombre_linea,
        indices      = indices,
        simbolos     = simbolos,
        ganadora     = True,
        descripcion  = descripcion,
        multiplicador= mult,
    )


# ─── Helpers internos ────────────────────────────────────────────────────────

def _simbolos_sin_wild(simbolos: Tuple[str, str, str]) -> List[str]:
    """Retorna los símbolos efectivos (sin wilds) de una terna."""
    return [s for s in simbolos if s != WILD_NOMBRE]


# ─── Renderizado de la grilla ─────────────────────────────────────────────────

def render_grilla(grilla: List[str]) -> str:
    """
    Genera la representación ASCII de la grilla 3×3 para Telegram.

    Ejemplo de salida:
        ┌──────────────────┐
        │  💿  │  🎤  │  🪄  │
        │  📸  │  👑  │  💜  │  ★
        │  🏆  │  💎  │  🎁  │
        └──────────────────┘

    Args:
        grilla: Lista de 9 nombres internos (resultado de girar()).

    Returns:
        String multi-línea listo para enviar a Telegram (sin parse_mode especial).
    """
    emojis = [SIMBOLO_INFO[nombre][0] for nombre in grilla]

    lineas_grilla = [
        f"│ {emojis[0]} │ {emojis[1]} │ {emojis[2]} │",
        f"│ {emojis[3]} │ {emojis[4]} │ {emojis[5]} │  ★",
        f"│ {emojis[6]} │ {emojis[7]} │ {emojis[8]} │",
    ]

    borde_sup = "┌──────────────────┐"
    borde_inf = "└──────────────────┘"

    return "\n".join([borde_sup] + lineas_grilla + [borde_inf])


def render_animacion(fase: int) -> str:
    """
    Genera una grilla de animación para simular el giro.

    Args:
        fase: Número de fase (0, 1, 2). Controla qué columnas "detienen".

    Returns:
        String de grilla en movimiento para editar el mensaje antes del resultado.
    """
    _GIRO = "🌀"
    _STOP = "⬛"

    if fase == 0:
        # Todo girando
        fila = [_GIRO, _GIRO, _GIRO]
    elif fase == 1:
        # Primera columna se detiene (placeholder)
        fila = [_STOP, _GIRO, _GIRO]
    else:
        # Segunda columna se detiene
        fila = [_STOP, _STOP, _GIRO]

    f = fila
    lineas_grilla = [
        f"│ {f[0]} │ {f[1]} │ {f[2]} │",
        f"│ {f[0]} │ {f[1]} │ {f[2]} │  ★",
        f"│ {f[0]} │ {f[1]} │ {f[2]} │",
    ]
    borde_sup = "┌──────────────────┐"
    borde_inf = "└──────────────────┘"

    return "\n".join([borde_sup] + lineas_grilla + [borde_inf])


# ─── Renderizado del mensaje completo ────────────────────────────────────────

def render_mensaje_resultado(result: SlotResult, nombre_usuario: str) -> str:
    """
    Construye el texto completo del mensaje de resultado para publicar en el grupo.

    Args:
        result:         SlotResult del giro.
        nombre_usuario: Nombre del usuario (para personalizar el mensaje).

    Returns:
        String HTML listo para enviar con parse_mode='HTML'.
    """
    lineas_ganadoras = [lr for lr in result.lineas if lr.ganadora]

    # ── Cabecera ──────────────────────────────────────────────────────────
    if result.jackpot:
        cabecera = "👑✨ <b>¡¡ J A C K P O T !!</b> ✨👑"
    elif result.giro_gratis:
        cabecera = "🎁 <b>¡¡ GIRO GRATIS !!</b> 🎁"
    elif lineas_ganadoras:
        cabecera = "🎰 <b>¡¡ GANASTE !!</b> 🎰"
    else:
        cabecera = "🎰 <b>Universe Slots</b> 🎰"

    # ── Grilla ────────────────────────────────────────────────────────────
    grilla_txt = render_grilla(result.grilla)

    # ── Separador y líneas ganadoras ──────────────────────────────────────
    separador = "━" * 20

    if lineas_ganadoras:
        detalle_lineas = "\n".join(
            f"  • <b>{lr.nombre}</b>: {lr.descripcion}"
            for lr in lineas_ganadoras
        )
        seccion_lineas = f"\n{detalle_lineas}\n"
    else:
        seccion_lineas = "\n😔 Sin combinación ganadora\n"

    # ── Resumen económico ─────────────────────────────────────────────────
    if result.ganancia_neta > 0:
        resumen = (
            f"💰 <b>+{result.ganancia_neta:,} ✨</b> ganados\n"
            f"📊 Apuesta: {result.apuesta:,} ✨"
        )
    elif result.ganancia_neta == 0:
        resumen = (
            f"🤝 Recuperaste tu apuesta\n"
            f"📊 Apuesta: {result.apuesta:,} ✨"
        )
    else:
        resumen = (
            f"💸 <b>{result.ganancia_neta:,} ✨</b> perdidos\n"
            f"📊 Apuesta: {result.apuesta:,} ✨"
        )

    # ── Giro gratis ───────────────────────────────────────────────────────
    extra = ""
    if result.giro_gratis and not result.jackpot:
        extra = "\n\n🎁 <i>¡Tu próximo giro es GRATIS!</i>"

    # ── Ensamblado ────────────────────────────────────────────────────────
    return (
        f"{cabecera}\n"
        f"👤 {nombre_usuario}\n"
        f"{separador}\n"
        f"<code>{grilla_txt}</code>\n"
        f"{separador}"
        f"{seccion_lineas}"
        f"{separador}\n"
        f"{resumen}"
        f"{extra}"
    )


def render_mensaje_animacion(fase: int, nombre_usuario: str, apuesta: int) -> str:
    """
    Construye el texto de animación durante el giro.

    Args:
        fase:           Fase de animación (0, 1, 2).
        nombre_usuario: Nombre del usuario.
        apuesta:        Cosmos apostados.

    Returns:
        String HTML para editar el mensaje durante la animación.
    """
    grilla_anim = render_animacion(fase)
    separador   = "━" * 20

    fases_txt = ["Girando...", "Deteniendo...", "¡Casi!"]
    estado    = fases_txt[min(fase, len(fases_txt) - 1)]

    return (
        f"🎰 <b>Universe Slots</b> 🎰\n"
        f"👤 {nombre_usuario}\n"
        f"{separador}\n"
        f"<code>{grilla_anim}</code>\n"
        f"{separador}\n"
        f"🌀 <i>{estado}</i>\n"
        f"📊 Apuesta: {apuesta:,} ✨"
    )


# ─── Tabla de premios (para /slotsinfo) ──────────────────────────────────────

def render_tabla_premios() -> str:
    """
    Genera la tabla de premios formateada para mostrar al usuario.

    Returns:
        String HTML con la tabla completa de símbolos y multiplicadores.
    """
    separador = "━" * 22
    filas = []

    for emoji, nombre, peso, mult in SIMBOLOS:
        if nombre == WILD_NOMBRE:
            desc = "Sustituye cualquier símbolo"
            mult_txt = "WILD"
        elif nombre == BONUS_NOMBRE:
            desc = f"×{mult} + Giro Gratis"
            mult_txt = f"×{mult} 🎁"
        elif nombre == JACKPOT_NOMBRE:
            desc = "JACKPOT"
            mult_txt = f"×{mult} 👑"
        else:
            desc = ""
            mult_txt = f"×{mult}"

        filas.append(f"  {emoji} <b>{mult_txt}</b>  {desc}")

    tabla = "\n".join(filas)

    return (
        f"🎰 <b>UNIVERSE SLOTS — Tabla de Premios</b>\n"
        f"{separador}\n"
        f"{tabla}\n"
        f"{separador}\n"
        f"<b>Líneas activas:</b> 5 (3 horizontales + 2 diagonales)\n"
        f"<b>Wild ⭐:</b> Sustituye cualquier símbolo\n"
        f"<b>Bonus 🎁 × 3:</b> Premio + Giro Gratis\n"
        f"<b>RTP estimado:</b> ~75%\n"
        f"{separador}\n"
        f"<i>Uso: /slots [apuesta] | /slots allin</i>"
    )
