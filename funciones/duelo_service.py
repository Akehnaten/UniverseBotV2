# -*- coding: utf-8 -*-
"""
funciones/duelo_service.py
════════════════════════════════════════════════════════════════════════════════
Motor de Duelos para UniverseBot V2.0

La aleatoriedad la maneja Telegram vía send_dice() — el servicio solo
gestiona el ciclo de vida del duelo (creación, aceptación, cancelación)
y la transferencia de cosmos.
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_APUESTA_MIN = 50
_APUESTA_MAX = 100_000


@dataclass
class DueloPendiente:
    retador_id:  int
    retado_id:   int
    apuesta:     int
    chat_id:     int
    thread_id:   Optional[int]
    timer:       Optional[threading.Timer] = field(default=None, repr=False)


class DueloService:
    """
    Gestiona duelos pendientes de aceptación.
    La lógica de dados y pagos vive en el handler para poder
    usar send_dice() de Telegram con animación real.
    """

    def __init__(self) -> None:
        self._pendientes: Dict[int, DueloPendiente] = {}   # retado_id → duelo
        self._lock = threading.Lock()

    # ── Propiedades expuestas ─────────────────────────────────────────────────

    @property
    def apuesta_min(self) -> int:
        return _APUESTA_MIN

    @property
    def apuesta_max(self) -> int:
        return _APUESTA_MAX

    # ── Crear duelo ───────────────────────────────────────────────────────────

    def crear_duelo(
        self,
        retador_id:          int,
        retado_id:           int,
        apuesta:             int,
        chat_id:             int,
        thread_id:           Optional[int],
        on_timeout_callback,
    ) -> Tuple[bool, str]:
        """
        Registra un duelo pendiente de aceptación.
        El retado tiene 60 s para usar /aceptar_duelo.
        """
        with self._lock:
            for duelo in self._pendientes.values():
                if retador_id in (duelo.retador_id, duelo.retado_id):
                    return False, "Ya tenés un duelo pendiente."
                if retado_id in (duelo.retador_id, duelo.retado_id):
                    return False, "Ese usuario ya tiene un duelo pendiente."

            timer = threading.Timer(60.0, on_timeout_callback)
            timer.daemon = True
            self._pendientes[retado_id] = DueloPendiente(
                retador_id=retador_id,
                retado_id=retado_id,
                apuesta=apuesta,
                chat_id=chat_id,
                thread_id=thread_id,
                timer=timer,
            )
            timer.start()
            return True, ""

    # ── Consultar ─────────────────────────────────────────────────────────────

    def get_duelo_para(self, retado_id: int) -> Optional[DueloPendiente]:
        with self._lock:
            return self._pendientes.get(retado_id)

    # ── Aceptar duelo: devuelve los datos y limpia el estado ──────────────────

    def aceptar_duelo(self, retado_id: int) -> Tuple[Optional[DueloPendiente], str]:
        """
        Elimina el duelo del mapa de pendientes y cancela el timer.
        Devuelve los datos del duelo para que el handler ejecute la animación.
        """
        with self._lock:
            duelo = self._pendientes.pop(retado_id, None)
            if not duelo:
                return None, "No tenés ningún duelo pendiente."
            if duelo.timer:
                duelo.timer.cancel()
            return duelo, ""

    # ── Cancelar duelo ────────────────────────────────────────────────────────

    def cancelar_duelo(self, retado_id: int) -> Optional[DueloPendiente]:
        with self._lock:
            duelo = self._pendientes.pop(retado_id, None)
            if duelo and duelo.timer:
                duelo.timer.cancel()
            return duelo


# ─── Singleton ────────────────────────────────────────────────────────────────

duelo_service = DueloService()
