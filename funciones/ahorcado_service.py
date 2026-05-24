# -*- coding: utf-8 -*-
"""
funciones/ahorcado_service.py
════════════════════════════════════════════════════════════════════════════════
Motor de Ahorcado — UniverseBot V2.0

Fuentes de palabras (en orden de prioridad):
  1. Palabra específica del iniciador  (/ahorcado PALABRA)
  2. Generador Groq                    (/ahorcado ia)
  3. Banco estático de 863 palabras    (/ahorcado)

Banco: 15 categorías — kpop, animales, países, comidas, deportes,
tecnología, historia, ciencia, música, películas, videojuegos,
mitología, profesiones, arquitectura, palabras difíciles.

Anti-repetición: se lleva un registro de palabras ya usadas por thread.
Cuando se agotan todas, el registro se reinicia automáticamente.
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import random
import threading
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from funciones.ahorcado_words import BANCO, TODAS

logger = logging.getLogger(__name__)

# ─── Constantes ───────────────────────────────────────────────────────────────

MAX_ERRORES     = 6
RECOMPENSA_BASE = 1    # Cosmos por letra correcta acertada


# ─── ASCII Art del muñeco ─────────────────────────────────────────────────────

HORCA_FRAMES = [
    "  _____  \n |     | \n |       \n |       \n |       \n_|_      ",
    "  _____  \n |     | \n |     O \n |       \n |       \n_|_      ",
    "  _____  \n |     | \n |     O \n |     | \n |       \n_|_      ",
    "  _____  \n |     | \n |     O \n |    /| \n |       \n_|_      ",
    "  _____  \n |     | \n |     O \n |    /|\\\n |       \n_|_      ",
    "  _____  \n |     | \n |     O \n |    /|\\\n |    /  \n_|_      ",
    "  _____  \n |     | \n |     O \n |    /|\\\n |    / \\\n_|_      ",
]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _normalizar(texto: str) -> str:
    """Convierte a mayúsculas y elimina tildes/diacríticos."""
    nfkd = unicodedata.normalize("NFD", texto.upper())
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


# ─── Partida ──────────────────────────────────────────────────────────────────

@dataclass
class PartidaAhorcado:
    thread_id:          int
    palabra:            str
    categoria:          str
    iniciador_id:       int
    iniciador_nombre:   str
    letras_correctas:   Set[str]          = field(default_factory=set)
    letras_incorrectas: Set[str]          = field(default_factory=set)
    participantes:      Dict[int, int]    = field(default_factory=dict)
    activa:             bool              = True
    message_id:         Optional[int]     = None
    generada_por_ia:    bool              = False

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
        return " ".join(
            c if (c in self.letras_correctas or c == " ") else "_"
            for c in self.palabra
        )

    def render_frame(self) -> str:
        return HORCA_FRAMES[self.errores]

    def render_panel(self) -> str:
        horca           = self.render_frame()
        palabra_display = self.display_palabra()
        correctas       = " ".join(sorted(self.letras_correctas)) or "—"
        incorrectas     = " ".join(sorted(self.letras_incorrectas)) or "—"
        vidas           = MAX_ERRORES - self.errores
        cat_txt         = f"  <i>Categoría: {self.categoria}</i>" if self.categoria else ""
        ia_txt          = "  <i>✨ Generada por IA</i>" if self.generada_por_ia else ""

        return (
            f"🔤 <b>AHORCADO — Universe Bot</b>{cat_txt}{ia_txt}\n"
            f"<i>Iniciado por {self.iniciador_nombre}</i>\n\n"
            f"<code>{horca}</code>\n\n"
            f"📝 Palabra:  <code>{palabra_display}</code>\n\n"
            f"✅ Correctas:    {correctas}\n"
            f"❌ Incorrectas: {incorrectas}\n"
            f"❤️ Vidas: <b>{'🟥' * self.errores}{'🟩' * vidas}</b>\n\n"
            f"<i>Usá <code>/letra X</code> para proponer una letra</i>"
        )


# ─── Servicio ─────────────────────────────────────────────────────────────────

class AhorcadoService:
    """Gestiona partidas de Ahorcado (una por thread). Singleton thread-safe."""

    def __init__(self) -> None:
        self._partidas:      Dict[int, PartidaAhorcado] = {}
        self._usadas:        Dict[int, Set[str]]        = {}   # {thread_id: palabras ya usadas}
        self._lock = threading.Lock()

    # ── Selección de palabra ──────────────────────────────────────────────────

    def _palabra_del_banco(self, thread_id: int) -> Tuple[str, str]:
        """
        Elige una palabra no usada del banco estático.
        Cuando se agotan todas, reinicia el registro del thread.
        Retorna (palabra, categoria).
        """
        usadas = self._usadas.setdefault(thread_id, set())

        # Filtrar disponibles
        disponibles = [(p, cat) for cat, words in BANCO.items()
                       for p in words if p not in usadas]

        # Si se agotaron, reiniciar
        if not disponibles:
            logger.info("[AHORCADO] Thread %s: banco agotado, reiniciando.", thread_id)
            self._usadas[thread_id] = set()
            disponibles = [(p, cat) for cat, words in BANCO.items() for p in words]

        palabra, categoria = random.choice(disponibles)
        self._usadas[thread_id].add(palabra)
        return palabra, categoria

    def _palabra_groq(self) -> Tuple[str, str]:
        """
        Genera una palabra aleatoria usando Groq.
        Retorna (palabra_normalizada, "IA").
        Si Groq falla, cae al banco estático.
        """
        try:
            from config import GROQ_API_KEY
            from groq import Groq

            categorias = [
                "animal", "país", "ciudad", "comida", "deporte",
                "película", "serie de TV", "videojuego", "ciencia",
                "profesión", "instrumento musical", "personaje histórico",
                "mitología", "tecnología", "planta o flor",
            ]
            categoria = random.choice(categorias)
            client = Groq(api_key=GROQ_API_KEY)

            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{
                    "role": "user",
                    "content": (
                        f"Dame UNA SOLA palabra en español de la categoría: {categoria}. "
                        "Requisitos: entre 4 y 15 letras, en mayúsculas, sin tildes, "
                        "sin explicación ni texto adicional, solo la palabra. "
                        "Puede ser un nombre propio. No uses artículos."
                    ),
                }],
                max_tokens=20,
                temperature=1.0,
            )
            raw = (resp.choices[0].message.content or "").strip()
            # Tomar solo la primera palabra si devolvió varias
            palabra = raw.split()[0] if raw else ""
            palabra = _normalizar(palabra)

            if 4 <= len(palabra) <= 20 and palabra.replace(" ", "").isalpha():
                logger.info("[AHORCADO] Groq generó: %s (%s)", palabra, categoria)
                return palabra, f"IA — {categoria}"

        except Exception as exc:
            logger.warning("[AHORCADO] Groq falló, usando banco estático: %s", exc)

        return self._palabra_del_banco(0)   # fallback

    # ── API pública ───────────────────────────────────────────────────────────

    def nueva_partida(
        self,
        thread_id:        int,
        iniciador_id:     int,
        iniciador_nombre: str,
        palabra:          Optional[str] = None,
        usar_ia:          bool = False,
    ) -> Tuple[Optional[PartidaAhorcado], str]:
        with self._lock:
            if thread_id in self._partidas and self._partidas[thread_id].activa:
                return None, "Ya hay una partida activa. Terminala primero con /cancelar_ahorcado."

            generada_por_ia = False

            if palabra:
                # Palabra manual del iniciador
                palabra_norm = _normalizar(palabra.strip())
                categoria    = "personalizada"
            elif usar_ia:
                palabra_norm, categoria = self._palabra_groq()
                generada_por_ia = True
            else:
                palabra_norm, categoria = self._palabra_del_banco(thread_id)

            if not palabra_norm or len(palabra_norm) < 2:
                return None, "La palabra no es válida."

            partida = PartidaAhorcado(
                thread_id=thread_id,
                palabra=palabra_norm,
                categoria=categoria,
                iniciador_id=iniciador_id,
                iniciador_nombre=iniciador_nombre,
                generada_por_ia=generada_por_ia,
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
        with self._lock:
            partida = self._partidas.get(thread_id)
            if not partida or not partida.activa:
                return None, "No hay partida activa en este canal.", False

            letra = _normalizar(letra).strip()

            if len(letra) != 1 or not letra.isalpha():
                return partida, "❌ Solo se aceptan letras individuales (A-Z).", False

            if letra in partida.letras_correctas or letra in partida.letras_incorrectas:
                return partida, f"⚠️ La letra <b>{letra}</b> ya fue propuesta.", False

            es_correcta = letra in partida.palabra

            if es_correcta:
                partida.letras_correctas.add(letra)
                partida.participantes[user_id] = partida.participantes.get(user_id, 0) + 1
                apariciones = partida.palabra.count(letra)
                if partida.ganada:
                    partida.activa = False
                return partida, f"✅ <b>{letra}</b> — ¡Correcta! Aparece <b>{apariciones}</b> vez/veces.", True
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

    def palabras_disponibles(self, thread_id: int) -> int:
        """Cuántas palabras del banco quedan sin usar en este thread."""
        usadas = self._usadas.get(thread_id, set())
        return len(TODAS) - len(usadas)


# ─── Singleton ────────────────────────────────────────────────────────────────

ahorcado_service = AhorcadoService()
