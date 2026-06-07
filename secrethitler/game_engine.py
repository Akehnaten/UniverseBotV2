# -*- coding: utf-8 -*-
"""
secrethitler/game_engine.py
════════════════════════════════════════════════════════════════════════════════
Motor PURO de Secret Hitler. No conoce Telegram: solo reglas, estado y
transiciones. Todo lo que devuelve son datos; quien renderiza y envía DMs
es el handler.

Reglas implementadas (edición base, 5-10 jugadores):
  • Reparto de roles según tabla oficial.
  • Conocimiento fascista: 5-6 jug. todos se ven; 7+ Hitler no ve a su equipo.
  • Mazo de políticas: 6 Liberales + 11 Fascistas. Reshuffle del descarte
    cuando quedan <3 cartas en el mazo de robo.
  • Tablero de poderes presidenciales según nº de jugadores.
  • Condiciones de victoria (políticas, Hitler canciller, Hitler ejecutado).
  • Regla del Hitler-canciller: a partir de 3 políticas fascistas, elegir a
    Hitler como canciller hace ganar a los fascistas.
  • Límite de elegibles a canciller (último presidente y canciller electos
    quedan term-limited, con la excepción de ≤5 jugadores vivos).
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Enumeraciones
# ─────────────────────────────────────────────────────────────────────────────

class Rol(str, Enum):
    LIBERAL = "liberal"
    FASCISTA = "fascista"
    HITLER = "hitler"


class Politica(str, Enum):
    LIBERAL = "liberal"
    FASCISTA = "fascista"


class Poder(str, Enum):
    INVESTIGAR = "investigar"        # ver lealtad de partido de un jugador
    ELECCION_ESPECIAL = "eleccion"   # presidente elige al próximo presidente
    PEEK = "peek"                    # mirar las próximas 3 cartas del mazo
    EJECUTAR = "ejecutar"            # matar a un jugador


class Fase(str, Enum):
    LOBBY = "lobby"
    NOMINACION = "nominacion"        # presidente nomina canciller
    VOTACION = "votacion"            # todos votan Ja/Nein
    LEGISLATIVA_PRES = "leg_pres"    # presidente descarta 1 de 3
    LEGISLATIVA_CANC = "leg_canc"    # canciller descarta 1 de 2
    VETO = "veto"                    # canciller propuso veto; espera al presidente
    PODER = "poder"                  # poder ejecutivo en curso
    TERMINADA = "terminada"


# ─────────────────────────────────────────────────────────────────────────────
# Tablas oficiales
# ─────────────────────────────────────────────────────────────────────────────

# nº jugadores -> (nº liberales, nº fascistas-sin-Hitler).  Hitler siempre es 1.
_REPARTO = {
    5:  (3, 1),
    6:  (4, 1),
    7:  (4, 2),
    8:  (5, 2),
    9:  (5, 3),
    10: (6, 3),
}

# Tablero fascista: poder que se activa al promulgar la N-ésima política
# fascista (índice 0 = 1ª política fascista). None = sin poder.
# Varía con el nº de jugadores.
_TABLERO_PODERES = {
    # 5-6 jugadores
    "small": [None, None, Poder.PEEK, Poder.EJECUTAR, Poder.EJECUTAR],
    # 7-8 jugadores
    "medium": [None, Poder.INVESTIGAR, Poder.ELECCION_ESPECIAL,
               Poder.EJECUTAR, Poder.EJECUTAR],
    # 9-10 jugadores
    "large": [Poder.INVESTIGAR, Poder.INVESTIGAR, Poder.ELECCION_ESPECIAL,
              Poder.EJECUTAR, Poder.EJECUTAR],
}

POLITICAS_LIBERALES_PARA_GANAR = 5
POLITICAS_FASCISTAS_PARA_GANAR = 6
# A partir de esta cantidad de fascistas, Hitler-canciller = victoria fascista.
FASCISTAS_PELIGRO_HITLER = 3
# A partir de esta cantidad de fascistas se desbloquea el poder de veto.
FASCISTAS_DESBLOQUEO_VETO = 5


def _clave_tablero(n_jugadores: int) -> str:
    if n_jugadores <= 6:
        return "small"
    if n_jugadores <= 8:
        return "medium"
    return "large"


# ─────────────────────────────────────────────────────────────────────────────
# Modelos
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Jugador:
    uid: int
    nombre: str
    rol: Optional[Rol] = None
    vivo: bool = True
    # Para la regla de "investigado una sola vez" (opcional, no forzada aquí).
    investigado: bool = False


@dataclass
class ResultadoPromulgacion:
    """Lo que ocurre tras promulgar una política."""
    politica: Politica
    poder_activado: Optional[Poder] = None
    fin_juego: bool = False
    ganador: Optional[str] = None        # "liberal" | "fascista"
    motivo: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Motor
# ─────────────────────────────────────────────────────────────────────────────

class SecretHitlerGame:
    """
    Estado y reglas de UNA partida. Métodos sin efectos de red.
    El handler llama a estos métodos y traduce los resultados a mensajes.
    """

    def __init__(self, jugadores: list[Jugador]):
        if not (5 <= len(jugadores) <= 10):
            raise ValueError("Secret Hitler requiere entre 5 y 10 jugadores.")

        self.jugadores: list[Jugador] = jugadores
        self.fase: Fase = Fase.LOBBY

        # Tablero
        self.politicas_liberales = 0
        self.politicas_fascistas = 0
        self.estado_caos = 0  # contador de elecciones fallidas consecutivas

        # Mazo
        self.mazo: list[Politica] = []
        self.descarte: list[Politica] = []
        self.mano_presidente: list[Politica] = []  # 3 cartas robadas
        self.mano_canciller: list[Politica] = []    # 2 cartas pasadas

        # Gobierno
        self.idx_presidente: int = 0     # índice en self.jugadores (orden de turno)
        self.uid_presidente: Optional[int] = None
        self.uid_canciller: Optional[int] = None
        self.uid_presidente_anterior: Optional[int] = None
        self.uid_canciller_anterior: Optional[int] = None
        self.presidente_especial: Optional[int] = None  # por elección especial

        # Votación en curso: {uid: True(Ja)/False(Nein)}
        self.votos: dict[int, bool] = {}

        # Poder en curso
        self.poder_pendiente: Optional[Poder] = None

    # ── Helpers de jugadores ────────────────────────────────────────────────

    @property
    def n_jugadores(self) -> int:
        return len(self.jugadores)

    @property
    def vivos(self) -> list[Jugador]:
        return [j for j in self.jugadores if j.vivo]

    def jugador(self, uid: int) -> Optional[Jugador]:
        return next((j for j in self.jugadores if j.uid == uid), None)

    def _fascistas_sin_hitler(self) -> int:
        return _REPARTO[self.n_jugadores][1]

    # ── Reparto de roles ──────────────────────────────────────────────────────

    def repartir_roles(self) -> None:
        """Asigna roles aleatoriamente según la tabla oficial."""
        n_lib, n_fac = _REPARTO[self.n_jugadores]
        roles = (
            [Rol.LIBERAL] * n_lib
            + [Rol.FASCISTA] * n_fac
            + [Rol.HITLER]
        )
        random.shuffle(roles)
        for jug, rol in zip(self.jugadores, roles):
            jug.rol = rol

        # Orden de turno = orden actual (ya barajable antes de llamar a esto)
        self.idx_presidente = 0
        self.uid_presidente = self.jugadores[0].uid
        self.fase = Fase.NOMINACION
        self._construir_mazo()

    def info_revelacion(self, uid: int) -> dict:
        """
        Qué ve cada jugador al inicio (para su DM de rol).
        Devuelve: {rol, companeros: [(uid,nombre,rol)], ve_companeros: bool}
        """
        jug = self.jugador(uid)
        if jug is None:
            return {}

        ve_companeros = False
        companeros: list[tuple[int, str, Rol]] = []

        if jug.rol in (Rol.FASCISTA, Rol.HITLER):
            es_partida_chica = self.n_jugadores <= 6
            if jug.rol == Rol.FASCISTA:
                # Los fascistas siempre ven a sus compañeros y a Hitler.
                ve_companeros = True
            elif jug.rol == Rol.HITLER and es_partida_chica:
                # Hitler solo ve a su equipo en partidas de 5-6.
                ve_companeros = True

            if ve_companeros:
                for otro in self.jugadores:
                    if otro.uid == uid:
                        continue
                    if otro.rol in (Rol.FASCISTA, Rol.HITLER):
                        companeros.append((otro.uid, otro.nombre, otro.rol))

        return {
            "rol": jug.rol,
            "ve_companeros": ve_companeros,
            "companeros": companeros,
        }

    # ── Mazo de políticas ──────────────────────────────────────────────────────

    def _construir_mazo(self) -> None:
        self.mazo = [Politica.LIBERAL] * 6 + [Politica.FASCISTA] * 11
        random.shuffle(self.mazo)
        self.descarte = []

    def _asegurar_mazo(self) -> None:
        """Si quedan menos de 3 cartas, baraja el descarte de vuelta al mazo."""
        if len(self.mazo) < 3:
            self.mazo.extend(self.descarte)
            self.descarte = []
            random.shuffle(self.mazo)

    # ── Nominación + votación ────────────────────────────────────────────────

    def elegibles_canciller(self) -> list[Jugador]:
        """Jugadores que el presidente puede nominar como canciller."""
        presi = self.uid_presidente
        bloqueados = set()
        # El último canciller electo siempre queda bloqueado.
        if self.uid_canciller_anterior is not None:
            bloqueados.add(self.uid_canciller_anterior)
        # El último presidente electo queda bloqueado salvo que queden ≤5 vivos.
        if len(self.vivos) > 5 and self.uid_presidente_anterior is not None:
            bloqueados.add(self.uid_presidente_anterior)

        return [
            j for j in self.vivos
            if j.uid != presi and j.uid not in bloqueados
        ]

    def nominar(self, uid_canciller: int) -> None:
        self.uid_canciller = uid_canciller
        self.votos = {}
        self.fase = Fase.VOTACION

    def registrar_voto(self, uid: int, ja: bool) -> None:
        if self.jugador(uid) and self.jugador(uid).vivo:
            self.votos[uid] = ja

    def votacion_completa(self) -> bool:
        return len(self.votos) >= len(self.vivos)

    def resolver_votacion(self) -> dict:
        """
        Cuenta los votos. Mayoría simple de Ja => gobierno aprobado.
        Devuelve dict con resultado y posible victoria por Hitler-canciller.
        Empate = rechazo.
        """
        ja = sum(1 for v in self.votos.values() if v)
        nein = sum(1 for v in self.votos.values() if not v)
        aprobado = ja > nein

        resultado = {
            "aprobado": aprobado,
            "ja": ja,
            "nein": nein,
            "fin_juego": False,
            "ganador": None,
            "motivo": "",
        }

        if aprobado:
            self.estado_caos = 0
            # ¿Hitler elegido canciller con ≥3 fascistas?
            canc = self.jugador(self.uid_canciller)
            if (self.politicas_fascistas >= FASCISTAS_PELIGRO_HITLER
                    and canc and canc.rol == Rol.HITLER):
                resultado.update(
                    fin_juego=True,
                    ganador="fascista",
                    motivo="Hitler fue elegido Canciller.",
                )
                self.fase = Fase.TERMINADA
                return resultado
            # Gobierno válido => fase legislativa
            self._iniciar_legislativa()
        else:
            self._eleccion_fallida(resultado)

        return resultado

    def _eleccion_fallida(self, resultado: dict) -> None:
        self.estado_caos += 1
        self.uid_canciller = None
        if self.estado_caos >= 3:
            self._promulgar_por_caos(resultado)
        else:
            self._avanzar_presidencia()

    def _promulgar_por_caos(self, resultado: dict) -> None:
        """
        Frustración del país: se promulga la carta superior del mazo sin poderes
        y se reinician los límites de mandato. Reutilizado por elección fallida
        y por veto aceptado tras 3 fracasos consecutivos.
        """
        self._asegurar_mazo()
        carta = self.mazo.pop(0)
        resultado["caos"] = True
        resultado["carta_caos"] = carta
        res = self._aplicar_politica(carta, por_caos=True)
        resultado["fin_juego"] = res.fin_juego
        resultado["ganador"] = res.ganador
        resultado["motivo"] = res.motivo
        # El caos reinicia los límites de mandato.
        self.uid_presidente_anterior = None
        self.uid_canciller_anterior = None
        self.estado_caos = 0
        if not res.fin_juego:
            self._avanzar_presidencia()

    # ── Fase legislativa ───────────────────────────────────────────────────────

    def _iniciar_legislativa(self) -> None:
        self._asegurar_mazo()
        self.mano_presidente = [self.mazo.pop(0) for _ in range(3)]
        self.fase = Fase.LEGISLATIVA_PRES

    def presidente_descarta(self, indice: int) -> None:
        """El presidente descarta 1 de las 3 cartas; pasa 2 al canciller."""
        carta = self.mano_presidente.pop(indice)
        self.descarte.append(carta)
        self.mano_canciller = list(self.mano_presidente)
        self.mano_presidente = []
        self.fase = Fase.LEGISLATIVA_CANC

    def canciller_promulga(self, indice: int) -> ResultadoPromulgacion:
        """El canciller descarta 1 de 2; promulga la otra."""
        descartada = self.mano_canciller.pop(indice)
        self.descarte.append(descartada)
        promulgada = self.mano_canciller.pop(0)
        self.mano_canciller = []
        return self._aplicar_politica(promulgada, por_caos=False)

    # ── Poder de veto (se desbloquea con 5 políticas fascistas) ────────────────

    def veto_disponible(self) -> bool:
        """True si el veto está activo (5+ políticas fascistas en el tablero)."""
        return self.politicas_fascistas >= FASCISTAS_DESBLOQUEO_VETO

    def canciller_propone_veto(self) -> None:
        """
        El Canciller propone vetar la agenda. Solo válido si el veto está
        desbloqueado y estamos en su fase legislativa. Pasa la decisión al
        Presidente; las 2 cartas quedan retenidas en mano_canciller.
        """
        if not self.veto_disponible():
            raise ValueError("El veto aún no está desbloqueado.")
        if self.fase != Fase.LEGISLATIVA_CANC:
            raise ValueError("No es momento de proponer veto.")
        self.fase = Fase.VETO

    def presidente_responde_veto(self, acepta: bool) -> dict:
        """
        El Presidente acepta o rechaza el veto propuesto por el Canciller.

        acepta=True  -> ambas cartas al descarte, sesión sin promulgar.
                        Cuenta como elección fallida (suma al caos; si llega a
                        3 se promulga la carta superior automáticamente).
        acepta=False -> el Canciller DEBE promulgar; se vuelve a LEGISLATIVA_CANC
                        y el handler le pide de nuevo que elija.

        Devuelve un dict con el mismo formato que resolver_votacion para que el
        handler reutilice el flujo (claves: aceptado, fin_juego, ganador,
        motivo, caos?, carta_caos?).
        """
        if self.fase != Fase.VETO:
            raise ValueError("No hay veto pendiente.")

        resultado = {
            "aceptado": acepta,
            "fin_juego": False,
            "ganador": None,
            "motivo": "",
        }

        if not acepta:
            # Veto rechazado: el canciller está obligado a promulgar.
            self.fase = Fase.LEGISLATIVA_CANC
            return resultado

        # Veto aceptado: descartar ambas cartas.
        self.descarte.extend(self.mano_canciller)
        self.mano_canciller = []
        self.estado_caos += 1
        self.uid_canciller = None
        if self.estado_caos >= 3:
            self._promulgar_por_caos(resultado)
        else:
            self._avanzar_presidencia()
        return resultado

    def _aplicar_politica(self, politica: Politica,
                          por_caos: bool) -> ResultadoPromulgacion:
        res = ResultadoPromulgacion(politica=politica)

        if politica == Politica.LIBERAL:
            self.politicas_liberales += 1
            if self.politicas_liberales >= POLITICAS_LIBERALES_PARA_GANAR:
                res.fin_juego = True
                res.ganador = "liberal"
                res.motivo = "Se promulgaron 5 políticas liberales."
                self.fase = Fase.TERMINADA
                return res
        else:
            self.politicas_fascistas += 1
            if self.politicas_fascistas >= POLITICAS_FASCISTAS_PARA_GANAR:
                res.fin_juego = True
                res.ganador = "fascista"
                res.motivo = "Se promulgaron 6 políticas fascistas."
                self.fase = Fase.TERMINADA
                return res
            # ¿Hay poder presidencial en esta casilla?  (no aplica en caos)
            if not por_caos:
                tablero = _TABLERO_PODERES[_clave_tablero(self.n_jugadores)]
                idx = self.politicas_fascistas - 1
                if 0 <= idx < len(tablero) and tablero[idx] is not None:
                    res.poder_activado = tablero[idx]
                    self.poder_pendiente = tablero[idx]

        # Rotar límites de mandato tras un gobierno exitoso (no en caos).
        if not por_caos:
            self.uid_presidente_anterior = self.uid_presidente
            self.uid_canciller_anterior = self.uid_canciller

        if res.poder_activado:
            self.fase = Fase.PODER
        else:
            self._avanzar_presidencia()

        return res

    # ── Poderes presidenciales ──────────────────────────────────────────────────

    def ejecutar_jugador(self, uid_objetivo: int) -> ResultadoPromulgacion:
        jug = self.jugador(uid_objetivo)
        res = ResultadoPromulgacion(politica=Politica.FASCISTA)
        if jug:
            jug.vivo = False
            # Si matan a Hitler, ganan los liberales.
            if jug.rol == Rol.HITLER:
                res.fin_juego = True
                res.ganador = "liberal"
                res.motivo = "Hitler fue ejecutado."
                self.fase = Fase.TERMINADA
                return res
        self.poder_pendiente = None
        self._avanzar_presidencia()
        return res

    def investigar_jugador(self, uid_objetivo: int) -> Rol:
        """Devuelve la lealtad de PARTIDO (Hitler aparece como fascista)."""
        jug = self.jugador(uid_objetivo)
        jug.investigado = True
        self.poder_pendiente = None
        self._avanzar_presidencia()
        return Rol.LIBERAL if jug.rol == Rol.LIBERAL else Rol.FASCISTA

    def peek_mazo(self) -> list[Politica]:
        """Mira (sin robar) las próximas 3 cartas del mazo."""
        self._asegurar_mazo()
        self.poder_pendiente = None
        cartas = self.mazo[:3]
        self._avanzar_presidencia()
        return list(cartas)

    def fijar_eleccion_especial(self, uid_objetivo: int) -> None:
        """El presidente nombra al próximo presidente (salta la rotación)."""
        self.presidente_especial = uid_objetivo
        self.poder_pendiente = None
        self._avanzar_presidencia()

    # ── Rotación de la presidencia ────────────────────────────────────────────

    def _avanzar_presidencia(self) -> None:
        self.uid_canciller = None
        self.votos = {}

        if self.presidente_especial is not None:
            self.uid_presidente = self.presidente_especial
            self.presidente_especial = None
            # Sincronizar el índice con el jugador elegido.
            for i, j in enumerate(self.jugadores):
                if j.uid == self.uid_presidente:
                    self.idx_presidente = i
                    break
        else:
            # Siguiente jugador VIVO en orden circular.
            n = self.n_jugadores
            for paso in range(1, n + 1):
                cand = self.jugadores[(self.idx_presidente + paso) % n]
                if cand.vivo:
                    self.idx_presidente = (self.idx_presidente + paso) % n
                    self.uid_presidente = cand.uid
                    break

        self.fase = Fase.NOMINACION

    # ── Snapshot del tablero ────────────────────────────────────────────────────

    def poder_en_casilla_actual(self) -> Optional[Poder]:
        tablero = _TABLERO_PODERES[_clave_tablero(self.n_jugadores)]
        idx = self.politicas_fascistas - 1
        if 0 <= idx < len(tablero):
            return tablero[idx]
        return None
