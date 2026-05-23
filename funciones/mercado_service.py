# -*- coding: utf-8 -*-
"""
funciones/mercado_service.py
════════════════════════════════════════════════════════════════════════════════
Motor del Mercado de Cosmos para UniverseBot V2.0

Funcionamiento:
  - N activos K-pop con precios en cosmos que fluctúan cada hora
  - Precio = random walk con sesgo neutro y volatilidad por activo
  - Usuarios compran/venden "acciones" con cosmos
  - /mercado          → precios actuales + variación
  - /comprar X N      → compra N acciones del activo X
  - /vender X N       → vende N acciones del activo X
  - /portfolio        → holdings + valor actual + P&L
  - /ranking_mercado  → top 5 por valor de portfolio

Tablas DB (creadas automáticamente si no existen):
  MERCADO_ACTIVOS   — catálogo de activos y precios
  MERCADO_PORTFOLIO — posiciones de cada usuario
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import math
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from database import db_manager
from funciones import economy_service

logger = logging.getLogger(__name__)

# ─── Catálogo inicial de activos ──────────────────────────────────────────────

_ACTIVOS_SEED = [
    {"simbolo": "BTS",    "nombre": "BTS",         "precio": 1200, "volatilidad": 0.12},
    {"simbolo": "BLINK",  "nombre": "BLACKPINK",   "precio": 950,  "volatilidad": 0.18},
    {"simbolo": "ONCE",   "nombre": "TWICE",        "precio": 700,  "volatilidad": 0.14},
    {"simbolo": "ATINY",  "nombre": "ATEEZ",        "precio": 450,  "volatilidad": 0.22},
    {"simbolo": "STAY",   "nombre": "Stray Kids",   "precio": 600,  "volatilidad": 0.17},
    {"simbolo": "CARAT",  "nombre": "SEVENTEEN",    "precio": 500,  "volatilidad": 0.15},
    {"simbolo": "NWJNS",  "nombre": "NewJeans",     "precio": 820,  "volatilidad": 0.20},
    {"simbolo": "AESPA",  "nombre": "aespa",        "precio": 680,  "volatilidad": 0.19},
    {"simbolo": "IVE",    "nombre": "IVE",          "precio": 560,  "volatilidad": 0.16},
    {"simbolo": "SKZ",    "nombre": "Stray Kids",   "precio": 490,  "volatilidad": 0.21},
]

INTERVALO_ACTUALIZACION = 3600   # segundos (1 hora)
PRECIO_MINIMO           = 10     # cosmos mínimos que puede valer un activo
PRECIO_MAXIMO           = 10_000
COMPRA_MINIMA           = 1      # Mínimo de acciones a comprar
COMPRA_MAXIMA           = 1_000


# ─── Dataclass de posición ────────────────────────────────────────────────────

@dataclass
class Posicion:
    simbolo:       str
    nombre:        str
    cantidad:      int
    costo_total:   float    # Total pagado por estas acciones
    precio_actual: float

    @property
    def precio_promedio(self) -> float:
        return self.costo_total / self.cantidad if self.cantidad > 0 else 0

    @property
    def valor_actual(self) -> float:
        return self.precio_actual * self.cantidad

    @property
    def ganancia_neta(self) -> float:
        return self.valor_actual - self.costo_total

    @property
    def ganancia_pct(self) -> float:
        if self.costo_total == 0:
            return 0.0
        return (self.ganancia_neta / self.costo_total) * 100


@dataclass
class Activo:
    simbolo:        str
    nombre:         str
    precio_actual:  float
    precio_anterior: float
    volatilidad:    float

    @property
    def variacion_pct(self) -> float:
        if self.precio_anterior == 0:
            return 0.0
        return ((self.precio_actual - self.precio_anterior) / self.precio_anterior) * 100

    @property
    def emoji_tendencia(self) -> str:
        if self.variacion_pct > 1:
            return "📈"
        if self.variacion_pct < -1:
            return "📉"
        return "➡️"


# ─── Servicio ─────────────────────────────────────────────────────────────────

class MercadoService:
    """Gestiona activos, precios y portfolios. Singleton con loop de actualización."""

    def __init__(self) -> None:
        self._lock    = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._init_db()
        self._seed_activos()

    # ── Init DB ───────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        db_manager.execute_update("""
            CREATE TABLE IF NOT EXISTS MERCADO_ACTIVOS (
                simbolo          TEXT PRIMARY KEY,
                nombre           TEXT NOT NULL,
                precio_actual    REAL NOT NULL,
                precio_anterior  REAL NOT NULL,
                volatilidad      REAL NOT NULL DEFAULT 0.15,
                ultima_actualizacion TEXT
            )
        """)
        db_manager.execute_update("""
            CREATE TABLE IF NOT EXISTS MERCADO_PORTFOLIO (
                userID          INTEGER NOT NULL,
                simbolo         TEXT    NOT NULL,
                cantidad        INTEGER NOT NULL DEFAULT 0,
                costo_total     REAL    NOT NULL DEFAULT 0,
                PRIMARY KEY (userID, simbolo)
            )
        """)

    def _seed_activos(self) -> None:
        """Inserta activos iniciales si la tabla está vacía."""
        rows = db_manager.execute_query("SELECT COUNT(*) as c FROM MERCADO_ACTIVOS")
        if rows and rows[0]["c"] > 0:
            return
        for a in _ACTIVOS_SEED:
            db_manager.execute_update(
                """
                INSERT OR IGNORE INTO MERCADO_ACTIVOS
                    (simbolo, nombre, precio_actual, precio_anterior, volatilidad, ultima_actualizacion)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (a["simbolo"], a["nombre"], a["precio"], a["precio"],
                 a["volatilidad"], datetime.now().isoformat()),
            )
        logger.info("[MERCADO] Activos inicializados: %d activos.", len(_ACTIVOS_SEED))

    # ── Loop de precios ───────────────────────────────────────────────────────

    def iniciar_loop(self) -> None:
        """Arranca el hilo de actualización de precios cada hora."""
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._precio_loop, daemon=True)
        self._thread.start()
        logger.info("[MERCADO] Loop de precios iniciado (cada %d s).", INTERVALO_ACTUALIZACION)

    def _precio_loop(self) -> None:
        next_update = time.time() + INTERVALO_ACTUALIZACION
        while self._running:
            remaining = next_update - time.time()
            if remaining > 0:
                time.sleep(min(remaining, 30))
                continue
            try:
                self._actualizar_precios()
            except Exception as exc:
                logger.error("[MERCADO] Error en _actualizar_precios: %s", exc)
            next_update = time.time() + INTERVALO_ACTUALIZACION

    def _actualizar_precios(self) -> None:
        """
        Actualiza todos los precios usando un random walk log-normal.
        Precio_nuevo = Precio_actual × exp(σ × Z)
        donde Z ~ N(0,1) y σ es la volatilidad del activo.
        """
        rows = db_manager.execute_query("SELECT * FROM MERCADO_ACTIVOS")
        ahora = datetime.now().isoformat()

        for row in rows:
            simbolo     = row["simbolo"]
            precio_ant  = float(row["precio_actual"])
            volatilidad = float(row["volatilidad"])

            z           = random.gauss(0, 1)
            factor      = math.exp(volatilidad * z)
            precio_nuevo = max(PRECIO_MINIMO, min(PRECIO_MAXIMO, precio_ant * factor))
            precio_nuevo = round(precio_nuevo, 2)

            db_manager.execute_update(
                """
                UPDATE MERCADO_ACTIVOS
                SET precio_anterior = precio_actual,
                    precio_actual   = ?,
                    ultima_actualizacion = ?
                WHERE simbolo = ?
                """,
                (precio_nuevo, ahora, simbolo),
            )

        logger.info("[MERCADO] Precios actualizados.")

    # ── Consultas ─────────────────────────────────────────────────────────────

    def get_activos(self) -> List[Activo]:
        rows = db_manager.execute_query(
            "SELECT * FROM MERCADO_ACTIVOS ORDER BY precio_actual DESC"
        )
        return [
            Activo(
                simbolo=r["simbolo"],
                nombre=r["nombre"],
                precio_actual=float(r["precio_actual"]),
                precio_anterior=float(r["precio_anterior"]),
                volatilidad=float(r["volatilidad"]),
            )
            for r in rows
        ]

    def get_activo(self, simbolo: str) -> Optional[Activo]:
        rows = db_manager.execute_query(
            "SELECT * FROM MERCADO_ACTIVOS WHERE simbolo = ?", (simbolo.upper(),)
        )
        if not rows:
            return None
        r = rows[0]
        return Activo(
            simbolo=r["simbolo"],
            nombre=r["nombre"],
            precio_actual=float(r["precio_actual"]),
            precio_anterior=float(r["precio_anterior"]),
            volatilidad=float(r["volatilidad"]),
        )

    def get_portfolio(self, user_id: int) -> List[Posicion]:
        rows = db_manager.execute_query(
            """
            SELECT p.simbolo, p.cantidad, p.costo_total, a.nombre, a.precio_actual
            FROM MERCADO_PORTFOLIO p
            JOIN MERCADO_ACTIVOS a ON p.simbolo = a.simbolo
            WHERE p.userID = ? AND p.cantidad > 0
            ORDER BY a.precio_actual * p.cantidad DESC
            """,
            (user_id,),
        )
        return [
            Posicion(
                simbolo=r["simbolo"],
                nombre=r["nombre"],
                cantidad=int(r["cantidad"]),
                costo_total=float(r["costo_total"]),
                precio_actual=float(r["precio_actual"]),
            )
            for r in rows
        ]

    # ── Operaciones ───────────────────────────────────────────────────────────

    def comprar(
        self, user_id: int, simbolo: str, cantidad: int
    ) -> Tuple[bool, str, Optional[float]]:
        """
        Compra `cantidad` acciones del activo `simbolo`.

        Returns:
            (True,  "",       costo_total)  — éxito
            (False, mensaje,  None)         — error
        """
        simbolo = simbolo.upper()

        if cantidad < COMPRA_MINIMA or cantidad > COMPRA_MAXIMA:
            return False, f"Cantidad debe ser entre {COMPRA_MINIMA} y {COMPRA_MAXIMA}.", None

        activo = self.get_activo(simbolo)
        if not activo:
            return False, f"Activo <b>{simbolo}</b> no encontrado. Usá /mercado para ver los disponibles.", None

        costo = activo.precio_actual * cantidad
        costo_int = int(math.ceil(costo))   # redondeamos arriba para el cobro

        saldo = economy_service.get_balance(user_id)
        if saldo < costo_int:
            return False, (
                f"Saldo insuficiente.\n"
                f"Necesitás: <b>{costo_int:,} ✨</b>  |  Tenés: <b>{saldo:,} ✨</b>"
            ), None

        if not economy_service.subtract_credits(user_id, costo_int, f"mercado_compra_{simbolo}"):
            return False, "Error al descontar cosmos.", None

        # UPSERT en portfolio
        db_manager.execute_update(
            """
            INSERT INTO MERCADO_PORTFOLIO (userID, simbolo, cantidad, costo_total)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(userID, simbolo) DO UPDATE SET
                cantidad   = cantidad   + excluded.cantidad,
                costo_total = costo_total + excluded.costo_total
            """,
            (user_id, simbolo, cantidad, costo_int),
        )

        logger.info(
            "[MERCADO] Compra | uid=%s | %s × %d | costo=%d ✨",
            user_id, simbolo, cantidad, costo_int,
        )
        return True, "", float(costo_int)

    def vender(
        self, user_id: int, simbolo: str, cantidad: int
    ) -> Tuple[bool, str, Optional[float]]:
        """
        Vende `cantidad` acciones del activo `simbolo`.

        Returns:
            (True,  "",       ingreso_total)  — éxito
            (False, mensaje,  None)           — error
        """
        simbolo = simbolo.upper()

        if cantidad < COMPRA_MINIMA:
            return False, f"Cantidad mínima: {COMPRA_MINIMA}.", None

        activo = self.get_activo(simbolo)
        if not activo:
            return False, f"Activo <b>{simbolo}</b> no encontrado.", None

        rows = db_manager.execute_query(
            "SELECT cantidad, costo_total FROM MERCADO_PORTFOLIO WHERE userID = ? AND simbolo = ?",
            (user_id, simbolo),
        )
        if not rows or rows[0]["cantidad"] < cantidad:
            disponibles = rows[0]["cantidad"] if rows else 0
            return False, (
                f"No tenés suficientes acciones.\n"
                f"Tenés: <b>{disponibles}</b>  |  Querés vender: <b>{cantidad}</b>"
            ), None

        ingreso = int(activo.precio_actual * cantidad)

        # Calcular el costo proporcional a eliminar
        total_cantidad  = int(rows[0]["cantidad"])
        total_costo     = float(rows[0]["costo_total"])
        costo_proporcional = (cantidad / total_cantidad) * total_costo

        if cantidad == total_cantidad:
            db_manager.execute_update(
                "DELETE FROM MERCADO_PORTFOLIO WHERE userID = ? AND simbolo = ?",
                (user_id, simbolo),
            )
        else:
            db_manager.execute_update(
                """
                UPDATE MERCADO_PORTFOLIO
                SET cantidad    = cantidad    - ?,
                    costo_total = costo_total - ?
                WHERE userID = ? AND simbolo = ?
                """,
                (cantidad, costo_proporcional, user_id, simbolo),
            )

        economy_service.add_credits(user_id, ingreso, f"mercado_venta_{simbolo}")

        logger.info(
            "[MERCADO] Venta | uid=%s | %s × %d | ingreso=%d ✨",
            user_id, simbolo, cantidad, ingreso,
        )
        return True, "", float(ingreso)

    # ── Ranking ───────────────────────────────────────────────────────────────

    def get_ranking(self, top_n: int = 10) -> List[Dict]:
        """
        Devuelve los top N usuarios por valor total de portfolio.
        """
        rows = db_manager.execute_query(
            """
            SELECT p.userID,
                   SUM(p.cantidad * a.precio_actual) AS valor_total,
                   SUM(p.costo_total)                AS costo_total
            FROM MERCADO_PORTFOLIO p
            JOIN MERCADO_ACTIVOS a ON p.simbolo = a.simbolo
            WHERE p.cantidad > 0
            GROUP BY p.userID
            ORDER BY valor_total DESC
            LIMIT ?
            """,
            (top_n,),
        )
        resultado = []
        for r in rows:
            uid = r["userID"]
            nombre_row = db_manager.execute_query(
                "SELECT nombre FROM USUARIOS WHERE userID = ?", (uid,)
            )
            nombre = nombre_row[0]["nombre"] if nombre_row else str(uid)
            resultado.append({
                "user_id":    uid,
                "nombre":     nombre,
                "valor_total": float(r["valor_total"]),
                "costo_total": float(r["costo_total"]),
                "ganancia":   float(r["valor_total"]) - float(r["costo_total"]),
            })
        return resultado


# ─── Singleton ────────────────────────────────────────────────────────────────

mercado_service = MercadoService()
