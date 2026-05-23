# -*- coding: utf-8 -*-
"""
funciones/duelo_service.py
════════════════════════════════════════════════════════════════════════════════
Motor de Duelos de Dados para UniverseBot V2.0

Mecánica:
  - Usuario A reta a Usuario B con /duelo @B [apuesta]
  - Usuario B tiene 60 segundos para aceptar con /aceptar_duelo
  - Cada jugador lanza 2d6 simultáneamente
  - Mayor suma gana; empate → relanzamiento automático (máx. 3 veces)
  - Ganador recibe la apuesta del perdedor; en caso de triple empate → devuelve cosmos
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import random
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MAX_INTENTOS_EMPATE = 3   # Máximo de relanzamientos en caso de empate


@dataclass
class DueloPendiente:
    retador_id:   int
    retado_id:    int
    apuesta:      int
    chat_id:      int
    thread_id:    Optional[int]
    timer:        Optional[threading.Timer] = field(default=None, repr=False)


@dataclass
class ResultadoDado:
    dados:  List[int]
    total:  int

    def render(self) -> str:
        iconos = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}
        return " ".join(iconos[d] for d in self.dados) + f"  →  <b>{self.total}</b>"


@dataclass
class ResultadoDuelo:
    retador_id:    int
    retado_id:     int
    apuesta:       int
    ganador_id:    Optional[int]         # None = triple empate → devolver cosmos
    rondas:        List[Tuple[ResultadoDado, ResultadoDado]] = field(default_factory=list)
    triple_empate: bool = False


class DueloService:
    """Gestiona duelos de dados entre usuarios. Singleton thread-safe."""

    def __init__(self) -> None:
        # Duelos pendientes de aceptación: retado_id → DueloPendiente
        self._pendientes: Dict[int, DueloPendiente] = {}
        self._lock = threading.Lock()

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _lanzar_dados() -> ResultadoDado:
        dados = [random.randint(1, 6), random.randint(1, 6)]
        return ResultadoDado(dados=dados, total=sum(dados))

    # ── API pública ───────────────────────────────────────────────────────────

    def crear_duelo(
        self,
        retador_id: int,
        retado_id:  int,
        apuesta:    int,
        chat_id:    int,
        thread_id:  Optional[int],
        on_timeout_callback,       # callable sin argumentos
    ) -> Tuple[bool, str]:
        """
        Crea un duelo pendiente.

        Returns:
            (True, "")          — duelo registrado.
            (False, mensaje)    — el usuario ya tiene un duelo pendiente.
        """
        with self._lock:
            # Verificar que ninguno de los dos tenga un duelo pendiente
            for duelo in self._pendientes.values():
                if retador_id in (duelo.retador_id, duelo.retado_id):
                    return False, "Ya tenés un duelo pendiente. Esperá a que se resuelva."
                if retado_id in (duelo.retador_id, duelo.retado_id):
                    return False, "Ese usuario ya tiene un duelo pendiente."

            timer = threading.Timer(60.0, on_timeout_callback)
            timer.daemon = True

            duelo = DueloPendiente(
                retador_id=retador_id,
                retado_id=retado_id,
                apuesta=apuesta,
                chat_id=chat_id,
                thread_id=thread_id,
                timer=timer,
            )
            self._pendientes[retado_id] = duelo
            timer.start()
            return True, ""

    def get_duelo_para(self, retado_id: int) -> Optional[DueloPendiente]:
        with self._lock:
            return self._pendientes.get(retado_id)

    def cancelar_duelo(self, retado_id: int) -> Optional[DueloPendiente]:
        """Cancela el duelo pendiente del retado. Retorna el duelo cancelado o None."""
        with self._lock:
            duelo = self._pendientes.pop(retado_id, None)
            if duelo and duelo.timer:
                duelo.timer.cancel()
            return duelo

    def resolver_duelo(self, retado_id: int) -> Tuple[Optional[ResultadoDuelo], str]:
        """
        Ejecuta el duelo: lanza dados hasta que haya ganador o triple empate.

        Returns:
            (resultado, "")        — duelo resuelto.
            (None, mensaje)        — duelo no encontrado.
        """
        with self._lock:
            duelo = self._pendientes.pop(retado_id, None)
            if not duelo:
                return None, "No hay duelo pendiente para aceptar."
            if duelo.timer:
                duelo.timer.cancel()

        resultado = ResultadoDuelo(
            retador_id=duelo.retador_id,
            retado_id=duelo.retado_id,
            apuesta=duelo.apuesta,
            ganador_id=None,
        )

        for _ in range(MAX_INTENTOS_EMPATE):
            r_retador = self._lanzar_dados()
            r_retado  = self._lanzar_dados()
            resultado.rondas.append((r_retador, r_retado))

            if r_retador.total > r_retado.total:
                resultado.ganador_id = duelo.retador_id
                break
            elif r_retado.total > r_retador.total:
                resultado.ganador_id = duelo.retado_id
                break
            # Empate → siguiente ronda

        else:
            # Agotamos los intentos → triple empate
            resultado.triple_empate = True

        return resultado, ""


# ── Singleton ─────────────────────────────────────────────────────────────────

duelo_service = DueloService()
