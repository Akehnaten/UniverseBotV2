# -*- coding: utf-8 -*-
"""
funciones/mercado_service.py
════════════════════════════════════════════════════════════════════════════════
Motor del Mercado de Cosmos — UniverseBot V2.0

Novedades v3 (CEO):
  · Supply fijo por grupo → base del sistema CEO
  · CEO: usuario con ≥51% de las acciones de un grupo
  · CEO recibe +50% de bonus en dividendos
  · Hostile takeover: anuncio dramático si alguien derroca al CEO
  · Migración automática: nadie queda como CEO el día 0
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import math
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, date
from typing import Callable, Dict, List, Optional, Tuple

from database import db_manager
from funciones import economy_service
try:
    from funciones.mercado_events import EVENTOS_POSITIVOS, EVENTOS_NEGATIVOS
except ImportError:
    logger.warning("[MERCADO] mercado_events.py no encontrado — eventos K-pop desactivados.")
    EVENTOS_POSITIVOS = []
    EVENTOS_NEGATIVOS = []

logger = logging.getLogger(__name__)

# ─── Constantes ───────────────────────────────────────────────────────────────

INTERVALO_PRECIOS   = 3600
INTERVALO_DIVIDENDO = 86400
PROB_EVENTO         = 0.20
PRECIO_MINIMO_ABS   = 10
CIRCUIT_BREAKER     = 0.50
COMPRA_MIN          = 1
COMPRA_MAX          = 10_000
CEO_UMBRAL          = 0.51    # 51% para ser CEO
CEO_DIVIDENDO_BONUS = 0.50    # +50% sobre el yield base

TIER_EMOJI = {"HYPER": "💎", "LARGE": "🥇", "MID": "🥈", "SMALL": "🥉"}

# ─── Supply total fijo por grupo ──────────────────────────────────────────────
# CEO de HYPER necesita ~102 accs × precio actual
# CEO de SMALL necesita ~1021 accs × precio actual

_SUPPLY_TOTAL: Dict[str, int] = {
    "BTS": 200,   "BLINK": 200,                                           # HYPER
    "ONCE": 500,  "CARAT": 500,  "NWJNS": 500,  "EXOL": 500,             # LARGE
    "LSSF": 500,  "RVLV": 500,   "MOA": 500,
    "AESPA": 1000, "IVE": 1000,  "SKZ": 1000,  "GIDLE": 1000,           # MID
    "ENGN": 1000,  "MIDZY": 1000, "MOOMOO": 1000,
    "ATINY": 2000, "NMIXX": 2000, "ILLIT": 2000,                         # SMALL
}

# ─── Catálogo inicial de activos ──────────────────────────────────────────────

_ACTIVOS_SEED = [
    {"simbolo": "BTS",    "nombre": "BTS",         "precio": 8000, "vol": 0.08, "yield_d": 0.006, "tier": "HYPER"},
    {"simbolo": "BLINK",  "nombre": "BLACKPINK",   "precio": 6500, "vol": 0.10, "yield_d": 0.007, "tier": "HYPER"},
    {"simbolo": "ONCE",   "nombre": "TWICE",        "precio": 3500, "vol": 0.12, "yield_d": 0.009, "tier": "LARGE"},
    {"simbolo": "CARAT",  "nombre": "SEVENTEEN",   "precio": 3200, "vol": 0.13, "yield_d": 0.009, "tier": "LARGE"},
    {"simbolo": "NWJNS",  "nombre": "NewJeans",    "precio": 2800, "vol": 0.14, "yield_d": 0.010, "tier": "LARGE"},
    {"simbolo": "EXOL",   "nombre": "EXO",          "precio": 2600, "vol": 0.15, "yield_d": 0.010, "tier": "LARGE"},
    {"simbolo": "LSSF",   "nombre": "LE SSERAFIM", "precio": 2400, "vol": 0.15, "yield_d": 0.010, "tier": "LARGE"},
    {"simbolo": "RVLV",   "nombre": "Red Velvet",  "precio": 2200, "vol": 0.14, "yield_d": 0.010, "tier": "LARGE"},
    {"simbolo": "MOA",    "nombre": "TXT",           "precio": 2000, "vol": 0.15, "yield_d": 0.011, "tier": "LARGE"},
    {"simbolo": "AESPA",  "nombre": "aespa",        "precio": 1500, "vol": 0.17, "yield_d": 0.013, "tier": "MID"},
    {"simbolo": "IVE",    "nombre": "IVE",           "precio": 1300, "vol": 0.18, "yield_d": 0.013, "tier": "MID"},
    {"simbolo": "SKZ",    "nombre": "Stray Kids",  "precio": 1100, "vol": 0.19, "yield_d": 0.014, "tier": "MID"},
    {"simbolo": "GIDLE",  "nombre": "(G)I-DLE",    "precio": 1000, "vol": 0.18, "yield_d": 0.014, "tier": "MID"},
    {"simbolo": "ENGN",   "nombre": "ENHYPEN",      "precio":  900, "vol": 0.20, "yield_d": 0.015, "tier": "MID"},
    {"simbolo": "MIDZY",  "nombre": "ITZY",          "precio":  800, "vol": 0.20, "yield_d": 0.015, "tier": "MID"},
    {"simbolo": "MOOMOO", "nombre": "MAMAMOO",      "precio":  700, "vol": 0.19, "yield_d": 0.015, "tier": "MID"},
    {"simbolo": "ATINY",  "nombre": "ATEEZ",         "precio":  600, "vol": 0.23, "yield_d": 0.020, "tier": "SMALL"},
    {"simbolo": "NMIXX",  "nombre": "NMIXX",         "precio":  500, "vol": 0.24, "yield_d": 0.020, "tier": "SMALL"},
    {"simbolo": "ILLIT",  "nombre": "ILLIT",         "precio":  400, "vol": 0.26, "yield_d": 0.022, "tier": "SMALL"},
]


# ─── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class Activo:
    simbolo:         str
    nombre:          str
    precio_actual:   float
    precio_anterior: float
    volatilidad:     float
    yield_diario:    float
    tier:            str
    precio_maximo:   float
    precio_minimo:   float
    precio_apertura: float
    supply_total:    int

    @property
    def variacion_pct(self) -> float:
        if self.precio_anterior == 0:
            return 0.0
        return ((self.precio_actual - self.precio_anterior) / self.precio_anterior) * 100

    @property
    def variacion_diaria_pct(self) -> float:
        if self.precio_apertura == 0:
            return 0.0
        return ((self.precio_actual - self.precio_apertura) / self.precio_apertura) * 100

    @property
    def emoji_tendencia(self) -> str:
        v = self.variacion_diaria_pct
        if v > 10: return "🚀"
        if v > 2:  return "📈"
        if v < -10: return "💥"
        if v < -2:  return "📉"
        return "➡️"

    @property
    def tier_emoji(self) -> str:
        return TIER_EMOJI.get(self.tier, "")

    @property
    def acciones_minimas_ceo(self) -> int:
        return math.ceil(self.supply_total * CEO_UMBRAL)


@dataclass
class Posicion:
    simbolo:       str
    nombre:        str
    cantidad:      int
    costo_total:   float
    precio_actual: float
    yield_diario:  float
    supply_total:  int
    es_ceo:        bool = False

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

    @property
    def porcentaje_supply(self) -> float:
        if self.supply_total == 0:
            return 0.0
        return (self.cantidad / self.supply_total) * 100

    @property
    def yield_efectivo(self) -> float:
        """Yield con bonus CEO si aplica."""
        return self.yield_diario * (1 + CEO_DIVIDENDO_BONUS) if self.es_ceo else self.yield_diario

    @property
    def dividendo_diario_estimado(self) -> int:
        return max(1, int(self.valor_actual * self.yield_efectivo))


# ─── Servicio ─────────────────────────────────────────────────────────────────

class MercadoService:
    """Singleton thread-safe. Gestiona precios, CEO, dividendos y reportes."""

    def __init__(self) -> None:
        self._lock    = threading.Lock()
        self._running = False
        self._notif_cb: Optional[Callable] = None
        self._init_db()
        self._migrate_db()
        self._seed_activos()
        self._init_supply()

    # ── DB ────────────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        db_manager.execute_update("""
            CREATE TABLE IF NOT EXISTS MERCADO_ACTIVOS (
                simbolo           TEXT PRIMARY KEY,
                nombre            TEXT NOT NULL,
                precio_actual     REAL NOT NULL,
                precio_anterior   REAL NOT NULL,
                precio_apertura   REAL NOT NULL DEFAULT 0,
                volatilidad       REAL NOT NULL DEFAULT 0.15,
                yield_diario      REAL NOT NULL DEFAULT 0.01,
                tier              TEXT NOT NULL DEFAULT 'MID',
                precio_maximo     REAL,
                precio_minimo     REAL,
                supply_total      INTEGER NOT NULL DEFAULT 1000,
                ultima_actualizacion TEXT
            )
        """)
        db_manager.execute_update("""
            CREATE TABLE IF NOT EXISTS MERCADO_PORTFOLIO (
                userID      INTEGER NOT NULL,
                simbolo     TEXT    NOT NULL,
                cantidad    INTEGER NOT NULL DEFAULT 0,
                costo_total REAL    NOT NULL DEFAULT 0,
                PRIMARY KEY (userID, simbolo)
            )
        """)
        db_manager.execute_update("""
            CREATE TABLE IF NOT EXISTS MERCADO_CONFIG (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            )
        """)
        db_manager.execute_update("""
            CREATE TABLE IF NOT EXISTS MERCADO_EVENTOS_LOG (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                fecha       TEXT    NOT NULL,
                simbolo     TEXT    NOT NULL,
                nombre      TEXT    NOT NULL,
                evento_texto TEXT   NOT NULL,
                impacto_pct REAL    NOT NULL,
                es_positivo INTEGER NOT NULL
            )
        """)
        db_manager.execute_update("""
            CREATE TABLE IF NOT EXISTS MERCADO_CEO (
                simbolo     TEXT PRIMARY KEY,
                user_id     INTEGER NOT NULL,
                nombre      TEXT    NOT NULL,
                fecha_desde TEXT    NOT NULL,
                mensaje     TEXT    DEFAULT NULL
            )
        """)

    def _migrate_db(self) -> None:
        cols = [
            ("yield_diario",    "REAL NOT NULL DEFAULT 0.01"),
            ("tier",            "TEXT NOT NULL DEFAULT 'MID'"),
            ("precio_maximo",   "REAL"),
            ("precio_minimo",   "REAL"),
            ("precio_apertura", "REAL NOT NULL DEFAULT 0"),
            ("supply_total",    "INTEGER NOT NULL DEFAULT 1000"),
        ]
        for col, defn in cols:
            try:
                db_manager.execute_update(f"ALTER TABLE MERCADO_ACTIVOS ADD COLUMN {col} {defn}")
            except Exception:
                pass

    def _seed_activos(self) -> None:
        for a in _ACTIVOS_SEED:
            supply = _SUPPLY_TOTAL.get(a["simbolo"], 1000)
            existente = db_manager.execute_query(
                "SELECT precio_actual FROM MERCADO_ACTIVOS WHERE simbolo=?", (a["simbolo"],)
            )
            if existente:
                db_manager.execute_update(
                    "UPDATE MERCADO_ACTIVOS SET volatilidad=?, yield_diario=?, tier=? WHERE simbolo=?",
                    (a["vol"], a["yield_d"], a["tier"], a["simbolo"]),
                )
            else:
                db_manager.execute_update(
                    """INSERT INTO MERCADO_ACTIVOS
                       (simbolo, nombre, precio_actual, precio_anterior, precio_apertura,
                        volatilidad, yield_diario, tier, precio_maximo, precio_minimo,
                        supply_total, ultima_actualizacion)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (a["simbolo"], a["nombre"], a["precio"], a["precio"], a["precio"],
                     a["vol"], a["yield_d"], a["tier"],
                     a["precio"], a["precio"], supply,
                     datetime.now().isoformat()),
                )

    def _init_supply(self) -> None:
        """
        Establece supply_total por primera vez, respetando holdings existentes.
        Para cada grupo: supply = max(supply_seed, total_holdings × 3)
        Esto garantiza que nadie empiece como CEO el día 0.
        """
        for simbolo, supply_seed in _SUPPLY_TOTAL.items():
            rows = db_manager.execute_query(
                "SELECT COALESCE(SUM(cantidad), 0) as total FROM MERCADO_PORTFOLIO WHERE simbolo=?",
                (simbolo,),
            )
            total_held = int(rows[0]["total"]) if rows else 0
            supply = max(supply_seed, total_held * 3 + 1)
            db_manager.execute_update(
                "UPDATE MERCADO_ACTIVOS SET supply_total=? WHERE simbolo=? AND supply_total=1000",
                (supply, simbolo),
            )

    # ── Config ────────────────────────────────────────────────────────────────

    def _get_config(self, clave: str, default: str = "") -> str:
        rows = db_manager.execute_query("SELECT valor FROM MERCADO_CONFIG WHERE clave=?", (clave,))
        return rows[0]["valor"] if rows else default

    def _set_config(self, clave: str, valor: str) -> None:
        db_manager.execute_update(
            "INSERT OR REPLACE INTO MERCADO_CONFIG (clave, valor) VALUES (?,?)", (clave, valor)
        )

    # ── CEO ───────────────────────────────────────────────────────────────────

    def _check_ceo(
        self, simbolo: str, user_id: int, nombre_usuario: str
    ) -> Optional[Dict]:
        """
        Verifica si el usuario alcanzó/perdió el CEO tras una operación.
        Retorna un dict con el evento, o None si no hubo cambio.
        """
        rows_a = db_manager.execute_query(
            "SELECT supply_total, nombre FROM MERCADO_ACTIVOS WHERE simbolo=?", (simbolo,)
        )
        if not rows_a:
            return None
        supply      = int(rows_a[0]["supply_total"])
        nombre_grupo = rows_a[0]["nombre"]

        rows_h = db_manager.execute_query(
            "SELECT COALESCE(cantidad, 0) as cant FROM MERCADO_PORTFOLIO WHERE userID=? AND simbolo=?",
            (user_id, simbolo),
        )
        cantidad = int(rows_h[0]["cant"]) if rows_h else 0
        pct = cantidad / supply if supply > 0 else 0

        rows_ceo = db_manager.execute_query(
            "SELECT user_id, nombre FROM MERCADO_CEO WHERE simbolo=?", (simbolo,)
        )
        ceo_actual = rows_ceo[0] if rows_ceo else None

        if pct >= CEO_UMBRAL:
            if ceo_actual and int(ceo_actual["user_id"]) == user_id:
                return None  # Ya era CEO, sin cambio

            tipo = "takeover" if ceo_actual else "nuevo"
            old_nombre = ceo_actual["nombre"] if ceo_actual else None

            db_manager.execute_update(
                "INSERT OR REPLACE INTO MERCADO_CEO (simbolo, user_id, nombre, fecha_desde, mensaje) VALUES (?,?,?,?,?)",
                (simbolo, user_id, nombre_usuario, datetime.now().isoformat(), None),
            )
            return {
                "tipo":           tipo,
                "simbolo":        simbolo,
                "nombre_grupo":   nombre_grupo,
                "nuevo_nombre":   nombre_usuario,
                "old_nombre":     old_nombre,
                "porcentaje":     pct * 100,
            }
        else:
            if ceo_actual and int(ceo_actual["user_id"]) == user_id:
                db_manager.execute_update("DELETE FROM MERCADO_CEO WHERE simbolo=?", (simbolo,))
                return {
                    "tipo":         "perdida",
                    "simbolo":      simbolo,
                    "nombre_grupo": nombre_grupo,
                    "old_nombre":   nombre_usuario,
                    "porcentaje":   pct * 100,
                }
            return None

    def get_ceo(self, simbolo: str) -> Optional[Dict]:
        rows = db_manager.execute_query(
            "SELECT * FROM MERCADO_CEO WHERE simbolo=?", (simbolo.upper(),)
        )
        if not rows:
            return None
        r = rows[0]
        # Calcular porcentaje actual
        rows_a = db_manager.execute_query(
            "SELECT supply_total FROM MERCADO_ACTIVOS WHERE simbolo=?", (simbolo.upper(),)
        )
        rows_h = db_manager.execute_query(
            "SELECT COALESCE(cantidad,0) as cant FROM MERCADO_PORTFOLIO WHERE userID=? AND simbolo=?",
            (int(r["user_id"]), simbolo.upper()),
        )
        supply   = int(rows_a[0]["supply_total"]) if rows_a else 1
        cantidad = int(rows_h[0]["cant"]) if rows_h else 0
        return {
            "user_id":     int(r["user_id"]),
            "nombre":      r["nombre"],
            "fecha_desde": r["fecha_desde"],
            "mensaje":     r["mensaje"],
            "porcentaje":  cantidad / supply * 100 if supply > 0 else 0,
            "cantidad":    cantidad,
        }

    def get_ceos_de_usuario(self, user_id: int) -> List[Dict]:
        """Retorna todos los grupos donde el usuario es CEO."""
        rows = db_manager.execute_query(
            """SELECT c.simbolo, a.nombre
               FROM MERCADO_CEO c
               JOIN MERCADO_ACTIVOS a ON c.simbolo = a.simbolo
               WHERE c.user_id = ?
               ORDER BY a.precio_actual DESC""",
            (user_id,),
        )
        return [{"simbolo": r["simbolo"], "nombre": r["nombre"]} for r in rows]

    def set_mensaje_ceo(
        self, user_id: int, simbolo: str, mensaje: str
    ) -> Tuple[bool, str]:
        simbolo = simbolo.upper()
        rows = db_manager.execute_query(
            "SELECT user_id FROM MERCADO_CEO WHERE simbolo=?", (simbolo,)
        )
        if not rows:
            return False, f"No hay CEO de {simbolo} actualmente."
        if int(rows[0]["user_id"]) != user_id:
            return False, "No sos el CEO de este grupo."
        if len(mensaje) > 200:
            return False, "El mensaje no puede superar los 200 caracteres."
        db_manager.execute_update(
            "UPDATE MERCADO_CEO SET mensaje=? WHERE simbolo=?", (mensaje, simbolo)
        )
        return True, ""

    def get_acciones_disponibles(self, simbolo: str) -> int:
        rows_a = db_manager.execute_query(
            "SELECT supply_total FROM MERCADO_ACTIVOS WHERE simbolo=?", (simbolo.upper(),)
        )
        if not rows_a:
            return 0
        supply = int(rows_a[0]["supply_total"])
        rows_h = db_manager.execute_query(
            "SELECT COALESCE(SUM(cantidad),0) as total FROM MERCADO_PORTFOLIO WHERE simbolo=?",
            (simbolo.upper(),),
        )
        total_held = int(rows_h[0]["total"]) if rows_h else 0
        return max(0, supply - total_held)

    # ── Loops ─────────────────────────────────────────────────────────────────

    def iniciar_loop(self, notif_callback: Optional[Callable] = None) -> None:
        if self._running:
            return
        self._running  = True
        self._notif_cb = notif_callback
        threading.Thread(target=self._loop_precios,    daemon=True).start()
        threading.Thread(target=self._loop_dividendos, daemon=True).start()
        threading.Thread(target=self._loop_reporte,    daemon=True).start()
        logger.info("[MERCADO] Loops iniciados.")

    def _loop_precios(self) -> None:
        next_tick = time.time() + INTERVALO_PRECIOS
        while self._running:
            sleep = next_tick - time.time()
            if sleep > 0:
                time.sleep(min(sleep, 30))
                continue
            try:
                self._actualizar_precios()
            except Exception as exc:
                logger.error("[MERCADO] _actualizar_precios: %s", exc, exc_info=True)
            next_tick = time.time() + INTERVALO_PRECIOS

    def _loop_dividendos(self) -> None:
        next_tick = time.time() + INTERVALO_DIVIDENDO
        while self._running:
            sleep = next_tick - time.time()
            if sleep > 0:
                time.sleep(min(sleep, 60))
                continue
            try:
                self._pagar_dividendos()
            except Exception as exc:
                logger.error("[MERCADO] _pagar_dividendos: %s", exc, exc_info=True)
            next_tick = time.time() + INTERVALO_DIVIDENDO

    def _loop_reporte(self) -> None:
        while self._running:
            time.sleep(1800)
            try:
                hoy    = date.today().isoformat()
                ultimo = self._get_config("ultimo_reporte_fecha", "")
                if hoy != ultimo:
                    self._enviar_reporte_diario()
                    self._set_config("ultimo_reporte_fecha", hoy)
                    self._resetear_precio_apertura()
            except Exception as exc:
                logger.error("[MERCADO] _loop_reporte: %s", exc, exc_info=True)

    # ── Actualización de precios ──────────────────────────────────────────────

    def _actualizar_precios(self) -> None:
        rows  = db_manager.execute_query("SELECT * FROM MERCADO_ACTIVOS")
        ahora = datetime.now().isoformat()
        hoy   = date.today().isoformat()

        for row in rows:
            simbolo    = row["simbolo"]
            nombre     = row["nombre"]
            precio_ant = float(row["precio_actual"])
            vol        = float(row["volatilidad"])
            p_max      = float(row["precio_maximo"] or precio_ant)
            p_min      = float(row["precio_minimo"] or precio_ant)
            p_apertura = float(row["precio_apertura"] or precio_ant)

            z      = random.gauss(0, 1)
            factor = math.exp(vol * z)

            evento_texto = None
            impacto_pct  = 0.0
            es_positivo  = True

            if random.random() < PROB_EVENTO and (EVENTOS_POSITIVOS or EVENTOS_NEGATIVOS):
                if random.random() < 0.5 and EVENTOS_POSITIVOS:
                    ev, es_positivo = random.choice(EVENTOS_POSITIVOS), True
                elif EVENTOS_NEGATIVOS:
                    ev, es_positivo = random.choice(EVENTOS_NEGATIVOS), False
                else:
                    ev = None
                if ev:
                    impacto_pct  = random.uniform(*ev.impacto) / 100
                    evento_texto = ev.texto
                    factor      *= (1 + impacto_pct) if es_positivo else (1 - impacto_pct)

            factor       = max(1 - CIRCUIT_BREAKER, min(1 + CIRCUIT_BREAKER, factor))
            precio_nuevo = max(PRECIO_MINIMO_ABS, round(precio_ant * factor, 2))
            p_max = max(p_max, precio_nuevo)
            p_min = min(p_min, precio_nuevo)

            db_manager.execute_update(
                """UPDATE MERCADO_ACTIVOS
                   SET precio_anterior=?, precio_actual=?, precio_apertura=?,
                       precio_maximo=?, precio_minimo=?, ultima_actualizacion=?
                   WHERE simbolo=?""",
                (precio_ant, precio_nuevo, p_apertura, p_max, p_min, ahora, simbolo),
            )

            if evento_texto:
                db_manager.execute_update(
                    """INSERT INTO MERCADO_EVENTOS_LOG
                       (timestamp, fecha, simbolo, nombre, evento_texto, impacto_pct, es_positivo)
                       VALUES (?,?,?,?,?,?,?)""",
                    (ahora, hoy, simbolo, nombre, evento_texto,
                     impacto_pct * 100 * (1 if es_positivo else -1),
                     1 if es_positivo else 0),
                )
                if self._notif_cb:
                    try:
                        self._notif_cb(simbolo, nombre, evento_texto, impacto_pct * 100, es_positivo)
                    except Exception as exc:
                        logger.warning("[MERCADO] notif_cb evento: %s", exc)

        logger.info("[MERCADO] Precios actualizados.")

    def _resetear_precio_apertura(self) -> None:
        db_manager.execute_update("UPDATE MERCADO_ACTIVOS SET precio_apertura=precio_actual")

    # ── Dividendos ────────────────────────────────────────────────────────────

    def _pagar_dividendos(self) -> None:
        rows = db_manager.execute_query(
            """SELECT p.userID, p.simbolo, p.cantidad, a.precio_actual, a.yield_diario
               FROM MERCADO_PORTFOLIO p
               JOIN MERCADO_ACTIVOS a ON p.simbolo = a.simbolo
               WHERE p.cantidad > 0"""
        )
        # Set de CEOs para el bonus
        ceo_rows = db_manager.execute_query("SELECT simbolo, user_id FROM MERCADO_CEO")
        ceos = {(int(r["user_id"]), r["simbolo"]) for r in ceo_rows}

        pagos: Dict[int, int] = {}
        for row in rows:
            uid     = int(row["userID"])
            simbolo = row["simbolo"]
            cant    = int(row["cantidad"])
            precio  = float(row["precio_actual"])
            yield_d = float(row["yield_diario"])

            # Bonus CEO
            if (uid, simbolo) in ceos:
                yield_d *= (1 + CEO_DIVIDENDO_BONUS)

            div = max(1, int(cant * precio * yield_d))
            economy_service.add_credits(uid, div, f"dividendo_{simbolo}")
            pagos[uid] = pagos.get(uid, 0) + div

        if pagos and self._notif_cb:
            try:
                self._notif_cb(
                    "__DIVIDENDO__", "Mercado",
                    f"💰 Dividendos pagados a {len(pagos)} inversores. "
                    f"Total: {sum(pagos.values()):,} ✨\n"
                    f"<i>Los CEOs recibieron +50% de bonus.</i>",
                    0.0, True,
                )
            except Exception:
                pass
        logger.info("[MERCADO] Dividendos: %d usuarios.", len(pagos))

    # ── Reporte diario ────────────────────────────────────────────────────────

    def _enviar_reporte_diario(self) -> None:
        if not self._notif_cb:
            return
        ayer    = date.today().isoformat()
        eventos = db_manager.execute_query(
            """SELECT simbolo, nombre, evento_texto, impacto_pct, es_positivo
               FROM MERCADO_EVENTOS_LOG WHERE fecha=?
               ORDER BY ABS(impacto_pct) DESC""",
            (ayer,),
        )
        activos = {a.simbolo: a for a in self.get_activos()}

        if not eventos:
            reporte = "📊 <b>REPORTE DIARIO DEL MERCADO</b>\n\nHoy no hubo noticias relevantes."
        else:
            subidas = [e for e in eventos if e["es_positivo"] == 1]
            bajadas = [e for e in eventos if e["es_positivo"] == 0]
            lineas  = ["📊 <b>REPORTE DIARIO DEL MERCADO</b>\n"]

            if subidas:
                lineas.append("📈 <b>NOTICIAS POSITIVAS:</b>")
                vistos = set()
                for e in subidas:
                    k = (e["simbolo"], e["evento_texto"])
                    if k in vistos: continue
                    vistos.add(k)
                    a   = activos.get(e["simbolo"])
                    var = f" ({a.variacion_diaria_pct:+.1f}% hoy)" if a else ""
                    lineas.append(
                        f"🚀 <b>{e['nombre']} ({e['simbolo']})</b>{var}\n"
                        f"   📰 {e['evento_texto']}\n"
                        f"   Impacto: <b>+{abs(e['impacto_pct']):.1f}%</b>"
                    )

            if bajadas:
                lineas.append("\n📉 <b>NOTICIAS NEGATIVAS:</b>")
                vistos = set()
                for e in bajadas:
                    k = (e["simbolo"], e["evento_texto"])
                    if k in vistos: continue
                    vistos.add(k)
                    a   = activos.get(e["simbolo"])
                    var = f" ({a.variacion_diaria_pct:+.1f}% hoy)" if a else ""
                    lineas.append(
                        f"💥 <b>{e['nombre']} ({e['simbolo']})</b>{var}\n"
                        f"   📰 {e['evento_texto']}\n"
                        f"   Impacto: <b>-{abs(e['impacto_pct']):.1f}%</b>"
                    )

            con_noticia = {e["simbolo"] for e in eventos}
            sin_noticia = [a for s, a in activos.items() if s not in con_noticia]
            if sin_noticia:
                lineas.append(
                    "\n➡️ <b>Sin noticias:</b> "
                    + ", ".join(f"{a.nombre} ({a.variacion_diaria_pct:+.1f}%)" for a in sin_noticia)
                )
            reporte = "\n".join(lineas)

        try:
            self._notif_cb("__REPORTE__", "Mercado", reporte, 0.0, True)
        except Exception as exc:
            logger.warning("[MERCADO] reporte: %s", exc)

        db_manager.execute_update(
            "DELETE FROM MERCADO_EVENTOS_LOG WHERE fecha < date('now', '-7 days')"
        )

    # ── Consultas ─────────────────────────────────────────────────────────────

    def get_activos(self) -> List[Activo]:
        rows = db_manager.execute_query("SELECT * FROM MERCADO_ACTIVOS ORDER BY precio_actual DESC")
        return [self._to_activo(r) for r in rows]

    def get_activo(self, simbolo: str) -> Optional[Activo]:
        rows = db_manager.execute_query(
            "SELECT * FROM MERCADO_ACTIVOS WHERE simbolo=?", (simbolo.upper(),)
        )
        return self._to_activo(rows[0]) if rows else None

    @staticmethod
    def _to_activo(r) -> Activo:
        p = float(r["precio_actual"])
        return Activo(
            simbolo=r["simbolo"], nombre=r["nombre"],
            precio_actual=p, precio_anterior=float(r["precio_anterior"]),
            precio_apertura=float(r["precio_apertura"] or p),
            volatilidad=float(r["volatilidad"]), yield_diario=float(r["yield_diario"]),
            tier=r["tier"], precio_maximo=float(r["precio_maximo"] or p),
            precio_minimo=float(r["precio_minimo"] or p),
            supply_total=int(r["supply_total"] or 1000),
        )

    def get_portfolio(self, user_id: int) -> List[Posicion]:
        rows = db_manager.execute_query(
            """SELECT p.simbolo, p.cantidad, p.costo_total,
                      a.nombre, a.precio_actual, a.yield_diario, a.supply_total
               FROM MERCADO_PORTFOLIO p
               JOIN MERCADO_ACTIVOS a ON p.simbolo = a.simbolo
               WHERE p.userID=? AND p.cantidad > 0
               ORDER BY (a.precio_actual * p.cantidad) DESC""",
            (user_id,),
        )
        ceo_simbolos = {r["simbolo"] for r in db_manager.execute_query(
            "SELECT simbolo FROM MERCADO_CEO WHERE user_id=?", (user_id,)
        ) or []}
        return [
            Posicion(
                simbolo=r["simbolo"], nombre=r["nombre"],
                cantidad=int(r["cantidad"]), costo_total=float(r["costo_total"]),
                precio_actual=float(r["precio_actual"]), yield_diario=float(r["yield_diario"]),
                supply_total=int(r["supply_total"] or 1000),
                es_ceo=r["simbolo"] in ceo_simbolos,
            )
            for r in rows
        ]

    def get_ranking(self, top_n: int = 10) -> List[Dict]:
        rows = db_manager.execute_query(
            """SELECT p.userID,
                      SUM(p.cantidad * a.precio_actual) AS valor_total,
                      SUM(p.costo_total) AS costo_total
               FROM MERCADO_PORTFOLIO p
               JOIN MERCADO_ACTIVOS a ON p.simbolo = a.simbolo
               WHERE p.cantidad > 0
               GROUP BY p.userID ORDER BY valor_total DESC LIMIT ?""",
            (top_n,),
        )
        resultado = []
        for r in rows:
            uid  = r["userID"]
            nrow = db_manager.execute_query("SELECT nombre FROM USUARIOS WHERE userID=?", (uid,))
            ceos = self.get_ceos_de_usuario(uid)
            resultado.append({
                "user_id":     uid,
                "nombre":      nrow[0]["nombre"] if nrow else str(uid),
                "valor_total": float(r["valor_total"]),
                "costo_total": float(r["costo_total"]),
                "ganancia":    float(r["valor_total"]) - float(r["costo_total"]),
                "ceos":        ceos,
            })
        return resultado

    # ── Operaciones ───────────────────────────────────────────────────────────

    def comprar(
        self, user_id: int, simbolo: str, cantidad: int, nombre_usuario: str = ""
    ) -> Tuple[bool, str, Optional[float], Optional[Dict]]:
        simbolo = simbolo.upper()
        if not (COMPRA_MIN <= cantidad <= COMPRA_MAX):
            return False, f"Cantidad entre {COMPRA_MIN} y {COMPRA_MAX:,}.", None, None

        activo = self.get_activo(simbolo)
        if not activo:
            return False, f"Activo <b>{simbolo}</b> no encontrado. Usá /mercado.", None, None

        # Verificar supply disponible
        disponibles = self.get_acciones_disponibles(simbolo)
        if cantidad > disponibles:
            return False, (
                f"No hay suficientes acciones disponibles.\n"
                f"Disponibles: <b>{disponibles}</b>  |  Querés comprar: <b>{cantidad}</b>\n"
                f"<i>Acercate al CEO si querés negociar.</i>"
            ), None, None

        costo = math.ceil(activo.precio_actual * cantidad)
        saldo = economy_service.get_balance(user_id)
        if saldo < costo:
            return False, f"Saldo insuficiente.\nCosto: <b>{costo:,} ✨</b>  |  Tenés: <b>{saldo:,} ✨</b>", None, None

        if not economy_service.subtract_credits(user_id, costo, f"mercado_compra_{simbolo}"):
            return False, "Error al descontar cosmos.", None, None

        db_manager.execute_update(
            """INSERT INTO MERCADO_PORTFOLIO (userID, simbolo, cantidad, costo_total)
               VALUES (?,?,?,?)
               ON CONFLICT(userID, simbolo) DO UPDATE SET
                   cantidad=cantidad+excluded.cantidad,
                   costo_total=costo_total+excluded.costo_total""",
            (user_id, simbolo, cantidad, float(costo)),
        )

        ceo_event = self._check_ceo(simbolo, user_id, nombre_usuario)
        return True, "", float(costo), ceo_event

    def vender(
        self, user_id: int, simbolo: str, cantidad: int, nombre_usuario: str = ""
    ) -> Tuple[bool, str, Optional[float], Optional[Dict]]:
        simbolo = simbolo.upper()
        activo  = self.get_activo(simbolo)
        if not activo:
            return False, f"Activo <b>{simbolo}</b> no encontrado.", None, None

        rows = db_manager.execute_query(
            "SELECT cantidad, costo_total FROM MERCADO_PORTFOLIO WHERE userID=? AND simbolo=?",
            (user_id, simbolo),
        )
        disponibles = int(rows[0]["cantidad"]) if rows else 0
        if disponibles < cantidad:
            return False, f"Tenés <b>{disponibles}</b> acciones, querés vender <b>{cantidad}</b>.", None, None

        ingreso    = int(activo.precio_actual * cantidad)
        costo_prop = (cantidad / disponibles) * float(rows[0]["costo_total"])

        if cantidad == disponibles:
            db_manager.execute_update(
                "DELETE FROM MERCADO_PORTFOLIO WHERE userID=? AND simbolo=?", (user_id, simbolo)
            )
        else:
            db_manager.execute_update(
                "UPDATE MERCADO_PORTFOLIO SET cantidad=cantidad-?, costo_total=costo_total-? WHERE userID=? AND simbolo=?",
                (cantidad, costo_prop, user_id, simbolo),
            )

        economy_service.add_credits(user_id, ingreso, f"mercado_venta_{simbolo}")
        ceo_event = self._check_ceo(simbolo, user_id, nombre_usuario)
        return True, "", float(ingreso), ceo_event


# ─── Singleton ────────────────────────────────────────────────────────────────

mercado_service = MercadoService()
