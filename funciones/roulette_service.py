# -*- coding: utf-8 -*-
"""
funciones/roulette_service.py
════════════════════════════════════════════════════════════════════════════════
Servicio de Ruleta Europea para UniverseBot V2.0

Responsabilidades:
  - Mantener el estado de la ruleta (activa/inactiva, ronda actual)
  - Registrar y validar apuestas por usuario
  - Ejecutar el giro y calcular pagos
  - Gestionar el timer automático de 5 minutos

Diseño:
  - Singleton thread-safe via Lock interno
  - Lógica pura: sin llamadas al bot ni a Telegram
  - Los cosmos se descuentan en el handler al confirmar apuesta;
    este servicio solo devuelve cuánto cobrar/pagar al girar
════════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import random
import threading
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Constantes de la ruleta europea ─────────────────────────────────────────

# Números rojos según la distribución estándar del paño de ruleta
NUMEROS_ROJOS: frozenset = frozenset({
    1, 3, 5, 7, 9, 12, 14, 16, 18,
    19, 21, 23, 25, 27, 30, 32, 34, 36,
})

# Columnas del paño (col 1 = fila inferior: 1, 4, 7, …, 34)
COLUMNA_1: frozenset = frozenset({1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34})
COLUMNA_2: frozenset = frozenset({2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35})
COLUMNA_3: frozenset = frozenset({3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36})

# Docenas
DOCENA_1: frozenset = frozenset(range(1, 13))
DOCENA_2: frozenset = frozenset(range(13, 25))
DOCENA_3: frozenset = frozenset(range(25, 37))

# Multiplicadores de ganancia (sin incluir la devolución de la apuesta).
# Pago total al ganador = apuesta × (PAGOS[tipo] + 1)
PAGOS: Dict[str, int] = {
    "pleno":   35,   # 1 número exacto
    "caballo": 17,   # 2 números adyacentes (split)
    "calle":   11,   # 3 números en una fila del paño
    "cuadro":  8,    # 4 números en bloque 2×2
    "linea":   5,    # 6 números (doble calle)
    "columna": 2,    # 12 números (columna del paño)
    "docena":  2,    # 12 números (docena)
    "color":   1,    # 18 números (rojo o negro)
    "paridad": 1,    # 18 números (par o impar)
    "mitad":   1,    # 18 números (1-18 o 19-36)
}

# Descripción legible para la UI
TIPOS_APUESTA: Dict[str, str] = {
    "pleno":   "Pleno — 1 número exacto (paga 35×)",
    "caballo": "Caballo / Split — 2 números adyacentes (paga 17×)",
    "calle":   "Calle — 3 números en fila (paga 11×)",
    "cuadro":  "Cuadro / Corner — 4 números 2×2 (paga 8×)",
    "linea":   "Línea doble — 6 números, 2 filas (paga 5×)",
    "columna": "Columna — 12 números (paga 2×)",
    "docena":  "Docena — 12 números (paga 2×)",
    "color":   "Color — Rojo o Negro (paga 1×)",
    "paridad": "Par o Impar (paga 1×)",
    "mitad":   "Baja (1-18) o Alta (19-36) (paga 1×)",
}

# Intervalo entre giros automáticos (segundos)
INTERVALO_GIRO: int = 300  # 5 minutos


# ─── Funciones auxiliares de geometría del paño ───────────────────────────────

def color_numero(n: int) -> str:
    """Retorna 'rojo', 'negro' o 'verde' para el número dado."""
    if n == 0:
        return "verde"
    return "rojo" if n in NUMEROS_ROJOS else "negro"


def numeros_adyacentes(n: int) -> List[int]:
    """
    Retorna todos los números adyacentes a `n` en el paño de ruleta.

    Layout del paño (12 columnas × 3 filas):
        Fila 3 (tope):  3,  6,  9, 12, …, 36
        Fila 2 (medio): 2,  5,  8, 11, …, 35
        Fila 1 (base):  1,  4,  7, 10, …, 34

    Adyacencia horizontal (misma columna, filas contiguas):
      n ↔ n+1  si  n % 3 != 0  (n no es el tope de su grupo de 3)
      n ↔ n-1  si  (n-1) % 3 != 0

    Adyacencia vertical (misma fila, columnas contiguas):
      n ↔ n+3  y  n ↔ n-3
    """
    if not (1 <= n <= 36):
        return []
    adyacentes = []
    if n + 3 <= 36:
        adyacentes.append(n + 3)
    if n - 3 >= 1:
        adyacentes.append(n - 3)
    if n % 3 != 0 and n + 1 <= 36:
        adyacentes.append(n + 1)
    if n > 1 and (n - 1) % 3 != 0:
        adyacentes.append(n - 1)
    return sorted(adyacentes)


def _cuadro_desde_n(n: int) -> Optional[List[int]]:
    """
    Retorna los 4 números del cuadro (corner) cuyo número inferior-izquierdo es `n`.
    Cuadro = {n, n+1, n+3, n+4}.
    Válido solo si n%3 != 0 y n+4 <= 36.
    """
    if n < 1 or n > 32 or n % 3 == 0:
        return None
    nums = [n, n + 1, n + 3, n + 4]
    return nums if all(1 <= x <= 36 for x in nums) else None


def cuadros_validos() -> List[Tuple[int, List[int]]]:
    """Retorna lista de (n_inicio, [4 números]) para todos los cuadros válidos."""
    return [(n, nums) for n in range(1, 33) if (nums := _cuadro_desde_n(n))]


# ─── Servicio (singleton thread-safe) ────────────────────────────────────────

class RouletteService:
    """
    Servicio singleton de la ruleta europea.

    Thread-safe: todas las mutaciones sobre estado interno se hacen bajo _lock.

    Ciclo de vida:
        activar()  →  [jugadores apuestan vía handler]  →  girar()
                   →  [handler distribuye pagos]        →  activar() (nueva ronda)
        desactivar() cancela el timer y devuelve cosmos pendientes.
    """

    _instance: Optional["RouletteService"] = None

    def __new__(cls) -> "RouletteService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup()
        return cls._instance

    # ── Inicialización ────────────────────────────────────────────────────────

    def _setup(self) -> None:
        self._lock = threading.Lock()
        self._activa: bool = False
        self._ronda: int = 0

        self._chat_id: Optional[int] = None
        self._thread_id: Optional[int] = None
        self._mensaje_anuncio_id: Optional[int] = None

        # Apuestas de la ronda en curso: {user_id: [{"tipo", "detalle", "cosmos"}]}
        self._apuestas: Dict[int, List[Dict[str, Any]]] = {}
        # Nombres para el mensaje de resultados: {user_id: display_name}
        self._usernames: Dict[int, str] = {}

        # Snapshot del último giro (para construir el mensaje de resultados)
        self._last_apuestas: Dict[int, List[Dict[str, Any]]] = {}
        self._last_usernames: Dict[int, str] = {}

        self._timer: Optional[threading.Timer] = None

    # ── Propiedades de solo lectura ───────────────────────────────────────────

    @property
    def activa(self) -> bool:
        return self._activa

    @property
    def ronda(self) -> int:
        return self._ronda

    @property
    def chat_id(self) -> Optional[int]:
        return self._chat_id

    @property
    def thread_id(self) -> Optional[int]:
        return self._thread_id

    @property
    def mensaje_anuncio_id(self) -> Optional[int]:
        return self._mensaje_anuncio_id

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def activar(self, chat_id: int, thread_id: Optional[int]) -> bool:
        """
        Activa la ruleta.

        Returns:
            True si se activó correctamente, False si ya estaba activa.
        """
        with self._lock:
            if self._activa:
                return False
            self._activa = True
            self._ronda += 1
            self._chat_id = chat_id
            self._thread_id = thread_id
            self._apuestas.clear()
            self._usernames.clear()
            logger.info("[RULETA] Activada — Ronda #%d", self._ronda)
            return True

    def desactivar(self) -> Tuple[bool, Dict[int, int]]:
        """
        Desactiva la ruleta y cancela el timer.

        Returns:
            (ok, pendientes) donde `pendientes` es {user_id: cosmos_a_devolver}
            para las apuestas que ya fueron descontadas pero no giraron.
        """
        with self._lock:
            if not self._activa:
                return False, {}

            pendientes: Dict[int, int] = {
                uid: sum(a["cosmos"] for a in bets)
                for uid, bets in self._apuestas.items()
                if bets
            }
            self._activa = False
            self._apuestas.clear()
            self._usernames.clear()
            self._cancelar_timer()
            logger.info(
                "[RULETA] Desactivada. %d usuarios con cosmos a devolver.", len(pendientes)
            )
            return True, pendientes

    def nueva_ronda(self) -> bool:
        """
        Avanza a la siguiente ronda sin desactivar/reactivar la ruleta.

        Incrementa el contador de ronda y limpia las apuestas de la ronda
        anterior, conservando ``_activa = True`` y los IDs de chat/thread
        almacenados.

        Debe llamarse desde el handler justo después de ejecutar el giro,
        en lugar de la secuencia ``desactivar() → activar()`` que en este
        flujo resulta incorrecta porque ``girar()`` no cambia ``_activa``.

        Returns:
            True si avanzó correctamente, False si la ruleta no estaba activa.
        """
        with self._lock:
            if not self._activa:
                return False
            self._ronda += 1
            self._apuestas.clear()
            self._usernames.clear()
            logger.info("[RULETA] Nueva ronda #%d", self._ronda)
            return True
    
    def set_mensaje_anuncio(self, msg_id: int) -> None:
        """Almacena el ID del mensaje de anuncio del canal."""
        self._mensaje_anuncio_id = msg_id

    # ── Apuestas ──────────────────────────────────────────────────────────────

    def registrar_apuesta(
        self,
        user_id: int,
        username: str,
        tipo: str,
        detalle: str,
        cosmos: int,
    ) -> Tuple[bool, str]:
        """
        Registra una apuesta.
        Los cosmos ya deben haber sido descontados antes de llamar este método.

        Returns:
            (ok, mensaje_de_error) — mensaje vacío si ok es True.
        """
        with self._lock:
            if not self._activa:
                return False, "❌ La ruleta ya no está activa."
            if cosmos < 1:
                return False, "❌ La apuesta mínima es 1 Cosmos."
            if tipo not in PAGOS:
                return False, f"❌ Tipo de apuesta desconocido: '{tipo}'."

            ok, err = self._validar_detalle(tipo, detalle)
            if not ok:
                return False, err

            self._apuestas.setdefault(user_id, []).append(
                {"tipo": tipo, "detalle": detalle, "cosmos": cosmos}
            )
            self._usernames[user_id] = username
            logger.info(
                "[RULETA] Ronda #%d — %s (%d): %s/%s — %d cosmos",
                self._ronda, username, user_id, tipo, detalle, cosmos,
            )
            return True, ""

    def _validar_detalle(self, tipo: str, detalle: str) -> Tuple[bool, str]:
        """Valida el campo `detalle` según el tipo de apuesta."""
        try:
            if tipo == "pleno":
                n = int(detalle)
                return (True, "") if 0 <= n <= 36 else (False, "❌ Pleno: número entre 0 y 36.")

            if tipo == "caballo":
                partes = detalle.split("-")
                if len(partes) != 2:
                    return False, "❌ Caballo: formato 'A-B' (ej: 14-15)."
                a, b = int(partes[0]), int(partes[1])
                if not (1 <= a <= 36 and 1 <= b <= 36):
                    return False, "❌ Caballo: ambos números deben estar entre 1 y 36."
                if b not in numeros_adyacentes(a):
                    return False, "❌ Caballo: los números no son adyacentes en el paño."
                return True, ""

            if tipo == "calle":
                n = int(detalle)
                if 1 <= n <= 34 and n % 3 == 1:
                    return True, ""
                return False, "❌ Calle: número de inicio de fila (1, 4, 7, …, 34)."

            if tipo == "cuadro":
                nums = _cuadro_desde_n(int(detalle))
                return (True, "") if nums else (False, "❌ Cuadro: número inferior-izquierdo de un bloque 2×2 válido.")

            if tipo == "linea":
                n = int(detalle)
                if 1 <= n <= 31 and n % 3 == 1:
                    return True, ""
                return False, "❌ Línea: número de inicio (1, 4, 7, …, 31)."

            if tipo == "columna":
                return (True, "") if detalle in ("1", "2", "3") else (False, "❌ Columna: 1, 2 o 3.")

            if tipo == "docena":
                return (True, "") if detalle in ("1", "2", "3") else (False, "❌ Docena: 1, 2 o 3.")

            if tipo == "color":
                return (True, "") if detalle in ("rojo", "negro") else (False, "❌ Color: 'rojo' o 'negro'.")

            if tipo == "paridad":
                return (True, "") if detalle in ("par", "impar") else (False, "❌ Paridad: 'par' o 'impar'.")

            if tipo == "mitad":
                return (True, "") if detalle in ("baja", "alta") else (False, "❌ Mitad: 'baja' o 'alta'.")

        except (ValueError, TypeError):
            pass
        return False, f"❌ Detalle inválido para tipo '{tipo}'."

    # ── Estadísticas de la ronda actual ──────────────────────────────────────

    def contar_apuestas(self) -> int:
        """Total de apuestas individuales en la ronda."""
        with self._lock:
            return sum(len(v) for v in self._apuestas.values())

    def contar_jugadores(self) -> int:
        """Jugadores con al menos una apuesta en la ronda."""
        with self._lock:
            return len(self._apuestas)

    def cosmos_en_juego(self) -> int:
        """Total de cosmos apostados en la ronda actual."""
        with self._lock:
            return sum(a["cosmos"] for bets in self._apuestas.values() for a in bets)

    # ── Giro ──────────────────────────────────────────────────────────────────

    def girar(self) -> Tuple[int, str, Dict[int, Dict[str, Any]]]:
        """
        Ejecuta el giro de la ruleta y calcula los pagos.

        Returns:
            (numero, color, resultados) donde resultados es:
            {
                user_id: {
                    "pago":     int,   # cosmos a ABONAR al usuario (0 si perdió todo)
                    "apostado": int,   # total descontado en esta ronda
                    "gano":     bool,  # True si al menos una apuesta fue ganadora
                }
            }

        El campo "pago" incluye la devolución de la apuesta + ganancia.
        Si "pago" == 0 el usuario perdió; sus cosmos ya estaban descontados.
        """
        with self._lock:
            numero = random.randint(0, 36)
            color = color_numero(numero)

            resultados: Dict[int, Dict[str, Any]] = {}

            for user_id, apuestas in self._apuestas.items():
                total_pago = 0
                total_apostado = 0
                alguna_gano = False

                for apuesta in apuestas:
                    cosmos = apuesta["cosmos"]
                    total_apostado += cosmos
                    if self._evaluar_apuesta(numero, apuesta["tipo"], apuesta["detalle"]):
                        # Devolución completa: apuesta + ganancia
                        total_pago += cosmos * (PAGOS[apuesta["tipo"]] + 1)
                        alguna_gano = True

                resultados[user_id] = {
                    "pago":     total_pago,
                    "apostado": total_apostado,
                    "gano":     alguna_gano,
                }

            # Guardar snapshot para el mensaje de resultados
            self._last_apuestas  = {uid: list(bets) for uid, bets in self._apuestas.items()}
            self._last_usernames = dict(self._usernames)

            # Limpiar ronda (la ronda se incrementa en activar() de la siguiente)
            self._apuestas.clear()
            self._usernames.clear()

            logger.info(
                "[RULETA] Giro: %d (%s) | %d jugadores", numero, color, len(resultados)
            )
            return numero, color, resultados

    def _evaluar_apuesta(self, numero: int, tipo: str, detalle: str) -> bool:
        """Retorna True si la apuesta gana para el número sorteado."""
        try:
            if tipo == "pleno":
                return numero == int(detalle)
            if tipo == "caballo":
                p = detalle.split("-")
                return numero in (int(p[0]), int(p[1]))
            if tipo == "calle":
                inicio = int(detalle)
                return inicio <= numero <= inicio + 2
            if tipo == "cuadro":
                nums = _cuadro_desde_n(int(detalle))
                return nums is not None and numero in nums
            if tipo == "linea":
                inicio = int(detalle)
                return inicio <= numero <= inicio + 5
            if tipo == "columna":
                col = int(detalle)
                return numero in {1: COLUMNA_1, 2: COLUMNA_2, 3: COLUMNA_3}.get(col, frozenset())
            if tipo == "docena":
                d = int(detalle)
                return numero in {1: DOCENA_1, 2: DOCENA_2, 3: DOCENA_3}.get(d, frozenset())
            if tipo == "color":
                return numero != 0 and color_numero(numero) == detalle
            if tipo == "paridad":
                return numero != 0 and (numero % 2 == 0) == (detalle == "par")
            if tipo == "mitad":
                return numero != 0 and (
                    (1 <= numero <= 18) if detalle == "baja" else (19 <= numero <= 36)
                )
        except Exception as exc:
            logger.error("[RULETA] Error evaluando apuesta tipo=%s: %s", tipo, exc)
        return False

    # ── Snapshots del último giro ────────────────────────────────────────────

    def get_last_usernames(self) -> Dict[int, str]:
        """Nombres de los jugadores del último giro."""
        return dict(self._last_usernames)

    def get_last_apuestas(self) -> Dict[int, List[Dict[str, Any]]]:
        """Apuestas del último giro (copia defensiva)."""
        return {uid: list(bets) for uid, bets in self._last_apuestas.items()}

    # ── Timer automático ──────────────────────────────────────────────────────

    def iniciar_timer(self, callback: Callable[[], None]) -> None:
        """
        (Re)inicia el timer de giro automático con el intervalo configurado.

        Args:
            callback: función sin argumentos que ejecuta el giro.
        """
        self._cancelar_timer()
        self._timer = threading.Timer(INTERVALO_GIRO, callback)
        self._timer.daemon = True
        self._timer.start()
        logger.info("[RULETA] Timer iniciado (%ds)", INTERVALO_GIRO)

    def _cancelar_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    # ── Repetir ultima bet ──────────────────────────────────────────────────────

    def get_last_apuestas_by_user(self, user_id: int) -> list:
        """Retorna las últimas apuestas del usuario (para 'Repetir apuesta')."""
        with self._lock:
            return list(self._last_apuestas.get(user_id, []))
        
# ── Instancia global del servicio ────────────────────────────────────────────
roulette_service = RouletteService()
