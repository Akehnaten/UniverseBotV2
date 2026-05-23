# -*- coding: utf-8 -*-
"""
funciones/carreras_service.py
════════════════════════════════════════════════════════════════════════════════
Motor de Carreras de Caballos para UniverseBot V2.0

Mecánica pari-mutuel simplificada:
  - El admin activa la carrera; los usuarios apuestan en su caballo
  - La carrera se resuelve después de un timer (3 min por defecto)
  - El ganador se determina con una carrera animada por texto (16 pasos)
  - Pool total = suma de todas las apuestas
  - Casa se queda 10%
  - El 90% restante se divide proporcionalmente entre los apostadores del ganador
  - Pago mínimo garantizado: 1.5× la apuesta individual
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Constantes ───────────────────────────────────────────────────────────────

DURACION_APUESTAS = 180        # Segundos para apostar antes de la carrera
PISTA_LONGITUD    = 18         # Casillas de la pista (pasos)
CASA_CUT          = 0.10       # 10 % para la "casa"
PAGO_MINIMO_MULT  = 1.5        # Multiplicador mínimo garantizado

# ─── Caballos ─────────────────────────────────────────────────────────────────

CABALLOS = [
    {"idx": 0, "nombre": "Juan Palomino",  "emoji": "🐴", "color": "Palomino"},
    {"idx": 1, "nombre": "Estrella Negra", "emoji": "🖤", "color": "Negro azabache"},
    {"idx": 2, "nombre": "Relámpago",      "emoji": "⚡", "color": "Alazán"},
    {"idx": 3, "nombre": "Luna Plateada",  "emoji": "🌙", "color": "Tordo"},
    {"idx": 4, "nombre": "Fuego Rojo",     "emoji": "🔥", "color": "Ruano"},
]


# ─── Apuesta individual ───────────────────────────────────────────────────────

@dataclass
class ApuestaCarrera:
    user_id:     int
    nombre:      str
    caballo_idx: int
    cosmos:      int


# ─── Estado global ────────────────────────────────────────────────────────────

@dataclass
class EstadoCarrera:
    activa:     bool                  = False
    chat_id:    Optional[int]         = None
    thread_id:  Optional[int]         = None
    msg_id:     Optional[int]         = None   # Mensaje de anuncio en CASINO
    apuestas:   List[ApuestaCarrera]  = field(default_factory=list)
    timer:      Optional[threading.Timer] = field(default=None, repr=False)
    ronda:      int                   = 0


class CarrerasService:
    """Singleton que gestiona el ciclo de vida de las carreras."""

    def __init__(self) -> None:
        self._estado = EstadoCarrera()
        self._lock   = threading.Lock()

    # ── Estado ────────────────────────────────────────────────────────────────

    @property
    def activa(self) -> bool:
        return self._estado.activa

    @property
    def estado(self) -> EstadoCarrera:
        return self._estado

    # ── Activar / desactivar ──────────────────────────────────────────────────

    def activar(
        self,
        chat_id:   int,
        thread_id: Optional[int],
        on_carrera_callback,    # callable() — disparado cuando termina el timer
    ) -> bool:
        """Abre la ronda de apuestas. Retorna False si ya había una activa."""
        with self._lock:
            if self._estado.activa:
                return False
            self._estado = EstadoCarrera(
                activa=True,
                chat_id=chat_id,
                thread_id=thread_id,
                ronda=self._estado.ronda + 1,
            )
            timer = threading.Timer(DURACION_APUESTAS, on_carrera_callback)
            timer.daemon = True
            self._estado.timer = timer
            timer.start()
            return True

    def desactivar(self) -> EstadoCarrera:
        """Cierra la carrera y retorna el estado final (para reembolsos)."""
        with self._lock:
            estado = self._estado
            if estado.timer:
                estado.timer.cancel()
            self._estado = EstadoCarrera()
            return estado

    def set_msg_id(self, msg_id: int) -> None:
        with self._lock:
            self._estado.msg_id = msg_id

    # ── Apuestas ──────────────────────────────────────────────────────────────

    def registrar_apuesta(
        self,
        user_id:     int,
        nombre:      str,
        caballo_idx: int,
        cosmos:      int,
    ) -> Tuple[bool, str]:
        """
        Registra o reemplaza la apuesta de un usuario.
        Si ya apostó en esta ronda, cancela la anterior y registra la nueva
        (devuelve la diferencia de cosmos si corresponde).

        Returns:
            (True, "")           — apuesta registrada.
            (False, mensaje)     — error.
        """
        with self._lock:
            if not self._estado.activa:
                return False, "No hay carrera activa."

            # Quitar apuesta anterior del mismo usuario si existe
            apuesta_anterior = None
            self._estado.apuestas = [
                a for a in self._estado.apuestas
                if not (a.user_id == user_id and (apuesta_anterior := a) is not None)
            ]
            # Si el filtro previo no eliminó nada, limpiar igualmente
            self._estado.apuestas = [
                a for a in self._estado.apuestas if a.user_id != user_id
            ]

            self._estado.apuestas.append(
                ApuestaCarrera(
                    user_id=user_id,
                    nombre=nombre,
                    caballo_idx=caballo_idx,
                    cosmos=cosmos,
                )
            )
            return True, ""

    def get_apuesta_usuario(self, user_id: int) -> Optional[ApuestaCarrera]:
        with self._lock:
            for a in self._estado.apuestas:
                if a.user_id == user_id:
                    return a
            return None

    def total_apostado(self) -> int:
        with self._lock:
            return sum(a.cosmos for a in self._estado.apuestas)

    def apuestas_por_caballo(self) -> Dict[int, int]:
        with self._lock:
            totales: Dict[int, int] = {i: 0 for i in range(len(CABALLOS))}
            for a in self._estado.apuestas:
                totales[a.caballo_idx] += a.cosmos
            return totales

    # ── Carrera ───────────────────────────────────────────────────────────────

    def ejecutar_carrera(self) -> Tuple[int, List[Tuple[int, List[int]]]]:
        """
        Simula la carrera.

        Returns:
            (ganador_idx, frames)
            frames: lista de snapshots de posición [(paso, [pos_c0, pos_c1, ...])]
        """
        posiciones = [0] * len(CABALLOS)
        frames: List[Tuple[int, List[int]]] = []

        # Cada caballo avanza aleatoriamente hasta cruzar la meta
        paso = 0
        while max(posiciones) < PISTA_LONGITUD:
            paso += 1
            for i in range(len(CABALLOS)):
                avance = random.randint(0, 2)   # 0, 1 o 2 casillas por paso
                posiciones[i] = min(posiciones[i] + avance, PISTA_LONGITUD)
            frames.append((paso, posiciones[:]))

        # Ganador = primero en llegar o el más avanzado
        ganador_idx = posiciones.index(max(posiciones))
        return ganador_idx, frames

    def calcular_pagos(
        self,
        ganador_idx: int,
        apuestas: List[ApuestaCarrera],
    ) -> Dict[int, int]:
        """
        Sistema pari-mutuel:
          pool_neto = total × (1 - CASA_CUT)
          Cada ganador recibe: (su_apuesta / total_apostado_en_ganador) × pool_neto
          Mínimo garantizado: apuesta × PAGO_MINIMO_MULT

        Returns:
            {user_id: pago_total (incluye devolución de apuesta)}
        """
        pool_total = sum(a.cosmos for a in apuestas)
        if pool_total == 0:
            return {}

        pool_neto = int(pool_total * (1 - CASA_CUT))

        ganadores    = [a for a in apuestas if a.caballo_idx == ganador_idx]
        total_ganad  = sum(a.cosmos for a in ganadores)

        pagos: Dict[int, int] = {}
        for a in ganadores:
            if total_ganad > 0:
                parte  = int((a.cosmos / total_ganad) * pool_neto)
            else:
                parte  = 0
            # Garantizar mínimo
            minimo = int(a.cosmos * PAGO_MINIMO_MULT)
            pago   = max(parte, minimo)
            pagos[a.user_id] = pago

        return pagos

    def render_frame(self, posiciones: List[int], ganador_idx: Optional[int] = None) -> str:
        """
        Renderiza el estado visual de la pista.

        Ejemplo:
          🐴 Juan Palomino:  ···🏇·············
          🖤 Estrella Negra: ········🏇·········
          ...
        """
        lineas = ["<code>"]
        for i, caballo in enumerate(CABALLOS):
            pos  = min(posiciones[i], PISTA_LONGITUD)
            pista = "·" * pos + "🏇" + "·" * (PISTA_LONGITUD - pos)
            if ganador_idx is not None and i == ganador_idx:
                sufijo = " 🏆"
            else:
                sufijo = ""
            emoji = caballo["emoji"]
            nombre_corto = caballo["nombre"][:12].ljust(12)
            lineas.append(f"{emoji} {nombre_corto}: {pista}{sufijo}")
        lineas.append("</code>")
        return "\n".join(lineas)


# ─── Singleton ────────────────────────────────────────────────────────────────

carreras_service = CarrerasService()
