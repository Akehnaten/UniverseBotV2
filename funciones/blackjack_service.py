# -*- coding: utf-8 -*-
"""
funciones/blackjack_service.py
════════════════════════════════════════════════════════════════════════════════
Motor de Blackjack para UniverseBot V2.0

Lógica pura sin Telegram:
  - Baraja estándar de 52 cartas, rebarajada entre manos
  - El crupier saca en ≤16 y se planta en ≥17
  - Blackjack natural (21 con 2 cartas) paga 1.5× la apuesta (3:2)
  - Doblar: duplica la apuesta, el jugador recibe exactamente 1 carta más
  - Empate (push): la apuesta se devuelve íntegra
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import random
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Constantes ───────────────────────────────────────────────────────────────

PALOS   = ["♠", "♥", "♦", "♣"]
VALORES = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

APUESTA_MINIMA_BJ = 50
APUESTA_MAXIMA_BJ = 50_000


# ─── Estado de la partida ─────────────────────────────────────────────────────

class EstadoBJ(Enum):
    EN_CURSO  = auto()
    GANADO    = auto()
    PERDIDO   = auto()
    EMPATE    = auto()
    BLACKJACK = auto()   # BJ natural del jugador (paga 3:2)


# ─── Carta ────────────────────────────────────────────────────────────────────

@dataclass
class Carta:
    valor:  str
    palo:   str
    oculta: bool = False   # True = boca abajo (segunda carta del crupier)

    def __str__(self) -> str:
        return "🂠" if self.oculta else f"{self.valor}{self.palo}"

    @property
    def puntos(self) -> int:
        if self.valor in ("J", "Q", "K"):
            return 10
        if self.valor == "A":
            return 11
        return int(self.valor)


# ─── Partida ──────────────────────────────────────────────────────────────────

@dataclass
class PartidaBJ:
    user_id:      int
    apuesta:      int
    mano_jugador: List[Carta] = field(default_factory=list)
    mano_crupier: List[Carta] = field(default_factory=list)
    estado:       EstadoBJ   = EstadoBJ.EN_CURSO
    doble:        bool       = False
    message_id:   Optional[int] = None
    chat_id:      Optional[int] = None

    @property
    def apuesta_efectiva(self) -> int:
        """Apuesta real (doble si el jugador dobló)."""
        return self.apuesta * 2 if self.doble else self.apuesta

    @staticmethod
    def _calcular_puntos(mano: List[Carta], incluir_ocultas: bool = False) -> int:
        total, ases = 0, 0
        for carta in mano:
            if carta.oculta and not incluir_ocultas:
                continue
            total += carta.puntos
            if carta.valor == "A":
                ases += 1
        while total > 21 and ases > 0:
            total -= 10
            ases  -= 1
        return total

    @property
    def puntos_jugador(self) -> int:
        return self._calcular_puntos(self.mano_jugador)

    @property
    def puntos_crupier_visible(self) -> int:
        """Puntos del crupier ignorando la carta oculta (para mostrar al jugador)."""
        return self._calcular_puntos(self.mano_crupier, incluir_ocultas=False)

    @property
    def puntos_crupier_total(self) -> int:
        """Puntos reales del crupier (todas las cartas)."""
        return self._calcular_puntos(self.mano_crupier, incluir_ocultas=True)

    def render_mano(self, mano: List[Carta]) -> str:
        """Devuelve las cartas como string legible."""
        return "  ".join(str(c) for c in mano)

    def es_bj_natural(self) -> bool:
        """True si el jugador tiene Blackjack natural (21 con exactamente 2 cartas)."""
        return len(self.mano_jugador) == 2 and self.puntos_jugador == 21


# ─── Servicio ─────────────────────────────────────────────────────────────────

class BlackjackService:
    """
    Motor de Blackjack. Instancia única (singleton al final del módulo).
    Thread-safe mediante Lock interno.
    """

    def __init__(self) -> None:
        self._partidas: Dict[int, PartidaBJ] = {}
        self._lock = threading.Lock()

    # ── Helpers privados ──────────────────────────────────────────────────────

    @staticmethod
    def _nueva_baraja() -> List[Carta]:
        baraja = [Carta(v, p) for p in PALOS for v in VALORES]
        random.shuffle(baraja)
        return baraja

    def _revelar_crupier(self, partida: PartidaBJ) -> None:
        """Revela todas las cartas ocultas del crupier."""
        for carta in partida.mano_crupier:
            carta.oculta = False

    def _turno_crupier(self, partida: PartidaBJ) -> None:
        """
        Turno automático del crupier:
          - Revela su carta oculta
          - Saca cartas mientras tenga ≤16
          - Determina el ganador
        """
        self._revelar_crupier(partida)

        baraja = self._nueva_baraja()
        while partida.puntos_crupier_total < 17:
            partida.mano_crupier.append(baraja.pop())

        pj = partida.puntos_jugador
        pc = partida.puntos_crupier_total

        if pc > 21 or pj > pc:
            partida.estado = EstadoBJ.GANADO
        elif pj < pc:
            partida.estado = EstadoBJ.PERDIDO
        else:
            partida.estado = EstadoBJ.EMPATE

    # ── API pública ───────────────────────────────────────────────────────────

    def nueva_partida(
        self,
        user_id: int,
        apuesta: int,
        chat_id: int,
    ) -> Tuple[Optional[PartidaBJ], str]:
        """
        Inicia una nueva partida.

        Returns:
            (partida, "")      — partida creada con éxito.
            (None,   mensaje)  — error; mensaje describe el problema.
        """
        with self._lock:
            if user_id in self._partidas:
                return None, "Ya tenés una partida en curso. Terminala antes de iniciar otra."

            baraja = self._nueva_baraja()

            # Reparto inicial: J-C-J-C (jugador, crupier, jugador, crupier)
            j1, c1, j2, c2 = baraja.pop(), baraja.pop(), baraja.pop(), baraja.pop()
            c2.oculta = True   # Segunda carta del crupier boca abajo

            partida = PartidaBJ(
                user_id=user_id,
                apuesta=apuesta,
                mano_jugador=[j1, j2],
                mano_crupier=[c1, c2],
                chat_id=chat_id,
            )

            # Blackjack natural → termina de inmediato
            if partida.es_bj_natural():
                partida.estado = EstadoBJ.BLACKJACK
                self._revelar_crupier(partida)

            self._partidas[user_id] = partida
            return partida, ""

    def pedir(self, user_id: int) -> Tuple[Optional[PartidaBJ], str]:
        """El jugador pide una carta más."""
        with self._lock:
            partida = self._partidas.get(user_id)
            if not partida or partida.estado != EstadoBJ.EN_CURSO:
                return None, "No tenés partida activa."

            partida.mano_jugador.append(self._nueva_baraja().pop())

            if partida.puntos_jugador > 21:
                partida.estado = EstadoBJ.PERDIDO
                self._revelar_crupier(partida)
            elif partida.puntos_jugador == 21:
                # 21 exacto → turno del crupier automático
                self._turno_crupier(partida)

            return partida, ""

    def plantarse(self, user_id: int) -> Tuple[Optional[PartidaBJ], str]:
        """El jugador se planta: turno del crupier."""
        with self._lock:
            partida = self._partidas.get(user_id)
            if not partida or partida.estado != EstadoBJ.EN_CURSO:
                return None, "No tenés partida activa."
            self._turno_crupier(partida)
            return partida, ""

    def doblar(self, user_id: int) -> Tuple[Optional[PartidaBJ], str]:
        """
        El jugador dobla:
          - Solo permitido con exactamente 2 cartas en mano
          - Duplica la apuesta, recibe 1 carta, luego turno del crupier
        """
        with self._lock:
            partida = self._partidas.get(user_id)
            if not partida or partida.estado != EstadoBJ.EN_CURSO:
                return None, "No tenés partida activa."
            if len(partida.mano_jugador) != 2:
                return partida, "Solo podés doblar con exactamente 2 cartas."

            partida.doble = True
            partida.mano_jugador.append(self._nueva_baraja().pop())

            if partida.puntos_jugador > 21:
                partida.estado = EstadoBJ.PERDIDO
                self._revelar_crupier(partida)
            else:
                self._turno_crupier(partida)

            return partida, ""

    def get_partida(self, user_id: int) -> Optional[PartidaBJ]:
        with self._lock:
            return self._partidas.get(user_id)

    def cerrar_partida(self, user_id: int) -> None:
        with self._lock:
            self._partidas.pop(user_id, None)

    def calcular_pago(self, partida: PartidaBJ) -> int:
        """
        Pago neto al jugador (ya descontada la apuesta inicial):
          BJ natural → +150% de la apuesta original
          Ganado     → +100% (1:1)
          Empate     →   0   (devuelve la apuesta)
          Perdido    → -100% de la apuesta efectiva
        """
        apuesta = partida.apuesta_efectiva
        match partida.estado:
            case EstadoBJ.BLACKJACK:
                return int(partida.apuesta * 1.5)
            case EstadoBJ.GANADO:
                return apuesta
            case EstadoBJ.EMPATE:
                return 0
            case _:
                return -apuesta


# ─── Singleton ────────────────────────────────────────────────────────────────

blackjack_service = BlackjackService()
