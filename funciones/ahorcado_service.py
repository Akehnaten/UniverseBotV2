# -*- coding: utf-8 -*-
"""
funciones/ahorcado_service.py
════════════════════════════════════════════════════════════════════════════════
Motor de Ahorcado para UniverseBot V2.0

Características:
  - Una partida activa por thread_id (el grupo debate la letra a probar)
  - Animación ASCII del muñeco que se construye con cada error
  - Solo /letra X puede proponer letras (el comando filtra la interacción)
  - Iniciador puede poner su propia palabra o usar una aleatoria temática
  - Recompensa en cosmos a quienes acertaron letras al ganar la partida
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import random
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ─── Constantes ───────────────────────────────────────────────────────────────

MAX_ERRORES     = 6
RECOMPENSA_BASE = 100   # Cosmos por participar en la victoria

# ─── Palabras temáticas K-pop (ampliable desde config/JSON) ──────────────────

PALABRAS_KPOP = [
    "BLACKPINK", "JENNIE", "JISOO", "ROSE", "LISA",
    "BANGTAN", "JUNGKOOK", "TAEHYUNG", "JIMIN", "NAMJOON", "SUGA", "JHOPE", "JIN",
    "TWICE", "MOMO", "SANA", "MINA", "NAYEON", "JIHYO", "CHAEYOUNG", "TZUYU",
    "STRAY KIDS", "FELIX", "HYUNJIN", "BANGCHAN",
    "ATEEZ", "HONGJOONG", "YUNHO", "WOOYOUNG",
    "SEVENTEEN", "MINGYU", "JEONGHAN", "SEUNGCHEOL",
    "AESPA", "KARINA", "WINTER", "NINGNING", "GISELLE",
    "NEWJEANS", "HANNI", "MINJI", "DANIELLE", "HAERIN", "HYEIN",
    "IVE", "WONYOUNG", "YUJ IN",
    "PHOTOCARD", "COMEBACK", "LIGHTSTICK", "FANSIGN", "DAESANG",
    "IDOL", "TRAINEE", "DEBUT", "MAKNAE", "SASAENG", "SARANGHAE",
    "INKIGAYO", "MUBANK", "MCOUNTDOWN",
]


# ─── ASCII Art del muñeco ─────────────────────────────────────────────────────
# Cada elemento de la lista corresponde a un error (0 = sin errores)

HORCA_FRAMES = [
    # 0 errores — solo la horca vacía
    (
        "  _____  \n"
        " |     | \n"
        " |       \n"
        " |       \n"
        " |       \n"
        "_|_      "
    ),
    # 1 error — cabeza
    (
        "  _____  \n"
        " |     | \n"
        " |     O \n"
        " |       \n"
        " |       \n"
        "_|_      "
    ),
    # 2 errores — cuerpo
    (
        "  _____  \n"
        " |     | \n"
        " |     O \n"
        " |     | \n"
        " |       \n"
        "_|_      "
    ),
    # 3 errores — brazo izquierdo
    (
        "  _____  \n"
        " |     | \n"
        " |     O \n"
        " |    /| \n"
        " |       \n"
        "_|_      "
    ),
    # 4 errores — ambos brazos
    (
        "  _____  \n"
        " |     | \n"
        " |     O \n"
        " |    /|\\n"
        " |       \n"
        "_|_      "
    ),
    # 5 errores — pierna izquierda
    (
        "  _____  \n"
        " |     | \n"
        " |     O \n"
        " |    /|\\\n"
        " |    /  \n"
        "_|_      "
    ),
    # 6 errores — MUERTO 💀
    (
        "  _____  \n"
        " |     | \n"
        " |     O \n"
        " |    /|\\\n"
        " |    / \\\n"
        "_|_      "
    ),
]


# ─── Partida ──────────────────────────────────────────────────────────────────

@dataclass
class PartidaAhorcado:
    thread_id:     int
    palabra:       str                     # Palabra en MAYÚSCULAS sin tildes
    iniciador_id:  int
    iniciador_nombre: str
    letras_correctas: Set[str]             = field(default_factory=set)
    letras_incorrectas: Set[str]           = field(default_factory=set)
    participantes:   Dict[int, int]        = field(default_factory=dict)  # user_id → letras acertadas
    activa:          bool                  = True
    message_id:      Optional[int]         = None   # ID del mensaje del panel en el grupo

    @property
    def errores(self) -> int:
        return len(self.letras_incorrectas)

    @property
    def ganada(self) -> bool:
        return all(c in self.letras_correctas or c == " " for c in self.palabra)

    @property
    def perdida(self) -> bool:
        return self.errores >= MAX_ERRORES

    def display_palabra(self) -> str:
        """Muestra la palabra con guiones bajos en letras no descubiertas."""
        return " ".join(
            c if (c in self.letras_correctas or c == " ") else "_"
            for c in self.palabra
        )

    def render_frame(self) -> str:
        return HORCA_FRAMES[self.errores]

    def render_panel(self) -> str:
        """Genera el texto completo del panel de la partida."""
        horca    = self.render_frame()
        palabra  = self.display_palabra()
        correctas   = " ".join(sorted(self.letras_correctas)) or "—"
        incorrectas = " ".join(sorted(self.letras_incorrectas)) or "—"
        vidas_restantes = MAX_ERRORES - self.errores

        return (
            f"🔤 <b>AHORCADO — Universe Bot</b>\n"
            f"<i>Iniciado por {self.iniciador_nombre}</i>\n\n"
            f"<code>{horca}</code>\n\n"
            f"📝 Palabra: <code>{palabra}</code>\n\n"
            f"✅ Letras correctas:    {correctas}\n"
            f"❌ Letras incorrectas: {incorrectas}\n"
            f"❤️ Vidas: <b>{'🟥' * self.errores}{'🟩' * vidas_restantes}</b>\n\n"
            f"<i>Usá <code>/letra X</code> para proponer una letra</i>"
        )


# ─── Servicio ─────────────────────────────────────────────────────────────────

class AhorcadoService:
    """Gestiona partidas de ahorcado, una por thread. Singleton thread-safe."""

    def __init__(self) -> None:
        self._partidas: Dict[int, PartidaAhorcado] = {}
        self._lock = threading.Lock()

    def nueva_partida(
        self,
        thread_id:        int,
        iniciador_id:     int,
        iniciador_nombre: str,
        palabra:          Optional[str] = None,
    ) -> Tuple[Optional[PartidaAhorcado], str]:
        """
        Inicia una partida nueva en el thread indicado.

        Si palabra es None, se elige una aleatoria del banco K-pop.
        La palabra se normaliza a MAYÚSCULAS.

        Returns:
            (partida, "")           — partida creada.
            (None,   mensaje_error) — ya había una activa.
        """
        with self._lock:
            if thread_id in self._partidas and self._partidas[thread_id].activa:
                return None, "Ya hay una partida activa en este canal. Terminala primero con /cancelar_ahorcado."

            if not palabra:
                palabra = random.choice(PALABRAS_KPOP)

            palabra_norm = palabra.upper().strip()

            partida = PartidaAhorcado(
                thread_id=thread_id,
                palabra=palabra_norm,
                iniciador_id=iniciador_id,
                iniciador_nombre=iniciador_nombre,
            )
            self._partidas[thread_id] = partida
            return partida, ""

    def proponer_letra(
        self,
        thread_id: int,
        user_id:   int,
        nombre:    str,
        letra:     str,
    ) -> Tuple[Optional[PartidaAhorcado], str, bool]:
        """
        Propone una letra.

        Returns:
            (partida, mensaje, es_correcta)
            Si la partida no existe o ya terminó, partida=None y mensaje describe el error.
        """
        with self._lock:
            partida = self._partidas.get(thread_id)
            if not partida or not partida.activa:
                return None, "No hay partida activa en este canal.", False

            letra = letra.upper().strip()

            if len(letra) != 1 or not letra.isalpha():
                return partida, "❌ Solo se aceptan letras individuales (A-Z).", False

            if letra in partida.letras_correctas or letra in partida.letras_incorrectas:
                return partida, f"⚠️ La letra <b>{letra}</b> ya fue propuesta.", False

            es_correcta = letra in partida.palabra

            if es_correcta:
                partida.letras_correctas.add(letra)
                # Registrar participante
                partida.participantes[user_id] = partida.participantes.get(user_id, 0) + 1
                apariciones = partida.palabra.count(letra)
                if partida.ganada:
                    partida.activa = False
                return partida, f"✅ <b>{letra}</b> — ¡Correcta! Aparece {apariciones} vez/veces.", True
            else:
                partida.letras_incorrectas.add(letra)
                if partida.perdida:
                    partida.activa = False
                return partida, f"❌ <b>{letra}</b> — No está en la palabra.", False

    def cancelar_partida(self, thread_id: int) -> Optional[PartidaAhorcado]:
        with self._lock:
            partida = self._partidas.pop(thread_id, None)
            if partida:
                partida.activa = False
            return partida

    def get_partida(self, thread_id: int) -> Optional[PartidaAhorcado]:
        with self._lock:
            return self._partidas.get(thread_id)

    def cerrar_partida(self, thread_id: int) -> None:
        with self._lock:
            self._partidas.pop(thread_id, None)


# ─── Singleton ────────────────────────────────────────────────────────────────

ahorcado_service = AhorcadoService()
