# -*- coding: utf-8 -*-
"""
funciones/mercado_service.py
════════════════════════════════════════════════════════════════════════════════
Motor del Mercado de Cosmos — UniverseBot V2.0

Novedades v2:
  · 19 grupos K-pop organizados en 4 tiers de capitalización
  · Eventos K-pop (50 positivos + 50 negativos) que disparan cambios de precio
  · Dividendos diarios automáticos para holders
  · Log de eventos (MERCADO_EVENTOS_LOG) para el reporte diario
  · Reporte diario automático con todos los motivos de suba/baja del día
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
from funciones.mercado_events import EVENTOS_POSITIVOS, EVENTOS_NEGATIVOS

logger = logging.getLogger(__name__)

# ─── Constantes ───────────────────────────────────────────────────────────────

INTERVALO_PRECIOS   = 3600    # Actualización de precios cada 1 hora
INTERVALO_DIVIDENDO = 86400   # Dividendos cada 24 horas
PROB_EVENTO         = 0.20    # Probabilidad de evento K-pop por activo por ciclo
PRECIO_MINIMO_ABS   = 10
CIRCUIT_BREAKER     = 0.50    # Máx. movimiento por ciclo (50%)
COMPRA_MIN          = 1
COMPRA_MAX          = 10_000

TIER_EMOJI = {"HYPER": "💎", "LARGE": "🥇", "MID": "🥈", "SMALL": "🥉"}

# ─── Catálogo de activos con tiers ────────────────────────────────────────────
#
# yield_d: % del valor de posición pagado como dividendo cada 24 h
# vol:     desviación estándar del random walk log-normal por ciclo
#
_ACTIVOS_SEED = [
    # ── 💎 HYPER CAP — íconos globales, máxima liquidez ──────────────────────
    {"simbolo": "BTS",   "nombre": "BTS",          "precio": 8000, "vol": 0.08, "yield_d": 0.006, "tier": "HYPER"},
    {"simbolo": "BLINK", "nombre": "BLACKPINK",    "precio": 6500, "vol": 0.10, "yield_d": 0.007, "tier": "HYPER"},
    # ── 🥇 LARGE CAP — grupos establecidos con base fan global ────────────────
    {"simbolo": "ONCE",  "nombre": "TWICE",         "precio": 3500, "vol": 0.12, "yield_d": 0.009, "tier": "LARGE"},
    {"simbolo": "CARAT", "nombre": "SEVENTEEN",     "precio": 3200, "vol": 0.13, "yield_d": 0.009, "tier": "LARGE"},
    {"simbolo": "NWJNS", "nombre": "NewJeans",      "precio": 2800, "vol": 0.14, "yield_d": 0.010, "tier": "LARGE"},
    {"simbolo": "EXOL",  "nombre": "EXO",           "precio": 2600, "vol": 0.15, "yield_d": 0.010, "tier": "LARGE"},
    {"simbolo": "LSSF",  "nombre": "LE SSERAFIM",   "precio": 2400, "vol": 0.15, "yield_d": 0.010, "tier": "LARGE"},
    {"simbolo": "RVLV",  "nombre": "Red Velvet",    "precio": 2200, "vol": 0.14, "yield_d": 0.010, "tier": "LARGE"},
    {"simbolo": "MOA",   "nombre": "TXT",            "precio": 2000, "vol": 0.15, "yield_d": 0.011, "tier": "LARGE"},
    # ── 🥈 MID CAP — grupos en ascenso o consolidados regionalmente ───────────
    {"simbolo": "AESPA", "nombre": "aespa",          "precio": 1500, "vol": 0.17, "yield_d": 0.013, "tier": "MID"},
    {"simbolo": "IVE",   "nombre": "IVE",            "precio": 1300, "vol": 0.18, "yield_d": 0.013, "tier": "MID"},
    {"simbolo": "SKZ",   "nombre": "Stray Kids",     "precio": 1100, "vol": 0.19, "yield_d": 0.014, "tier": "MID"},
    {"simbolo": "GIDLE", "nombre": "(G)I-DLE",       "precio": 1000, "vol": 0.18, "yield_d": 0.014, "tier": "MID"},
    {"simbolo": "ENGN",  "nombre": "ENHYPEN",        "precio":  900, "vol": 0.20, "yield_d": 0.015, "tier": "MID"},
    {"simbolo": "MIDZY", "nombre": "ITZY",           "precio":  800, "vol": 0.20, "yield_d": 0.015, "tier": "MID"},
    {"simbolo": "MOOMOO","nombre": "MAMAMOO",        "precio":  700, "vol": 0.19, "yield_d": 0.015, "tier": "MID"},
    # ── 🥉 SMALL CAP — alto riesgo, alto dividendo, gran potencial ────────────
    {"simbolo": "ATINY", "nombre": "ATEEZ",          "precio":  600, "vol": 0.23, "yield_d": 0.020, "tier": "SMALL"},
    {"simbolo": "NMIXX", "nombre": "NMIXX",          "precio":  500, "vol": 0.24, "yield_d": 0.020, "tier": "SMALL"},
    {"simbolo": "ILLIT", "nombre": "ILLIT",          "precio":  400, "vol": 0.26, "yield_d": 0.022, "tier": "SMALL"},
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
    precio_apertura: float    # Precio al inicio del día (para % diario)

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
        if v > 10:  return "🚀"
        if v > 2:   return "📈"
        if v < -10: return "💥"
        if v < -2:  return "📉"
        return "➡️"

    @property
    def tier_emoji(self) -> str:
        return TIER_EMOJI.get(self.tier, "")


@dataclass
class Posicion:
    simbolo:       str
    nombre:        str
    cantidad:      int
    costo_total:   float
    precio_actual: float
    yield_diario:  float

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
    def dividendo_diario_estimado(self) -> int:
        return max(1, int(self.valor_actual * self.yield_diario))


# ─── Servicio ─────────────────────────────────────────────────────────────────

class MercadoService:
    """Singleton thread-safe. Gestiona precios, eventos, dividendos y reportes."""

    def __init__(self) -> None:
        self._lock    = threading.Lock()
        self._running = False
        self._notif_cb: Optional[Callable] = None
        self._init_db()
        self._migrate_db()
        self._seed_activos()

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

    def _migrate_db(self) -> None:
        """Agrega columnas nuevas si no existen (idempotente)."""
        cols = [
            ("yield_diario",    "REAL NOT NULL DEFAULT 0.01"),
            ("tier",            "TEXT NOT NULL DEFAULT 'MID'"),
            ("precio_maximo",   "REAL"),
            ("precio_minimo",   "REAL"),
            ("precio_apertura", "REAL NOT NULL DEFAULT 0"),
        ]
        for col, defn in cols:
            try:
                db_manager.execute_update(f"ALTER TABLE MERCADO_ACTIVOS ADD COLUMN {col} {defn}")
            except Exception:
                pass

    def _seed_activos(self) -> None:
        for a in _ACTIVOS_SEED:
            existente = db_manager.execute_query(
                "SELECT precio_actual FROM MERCADO_ACTIVOS WHERE simbolo = ?", (a["simbolo"],)
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
                        ultima_actualizacion)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (a["simbolo"], a["nombre"], a["precio"], a["precio"], a["precio"],
                     a["vol"], a["yield_d"], a["tier"], a["precio"], a["precio"],
                     datetime.now().isoformat()),
                )
        logger.info("[MERCADO] Seed completado: %d activos.", len(_ACTIVOS_SEED))

    # ── Config helper ─────────────────────────────────────────────────────────

    def _get_config(self, clave: str, default: str = "") -> str:
        rows = db_manager.execute_query(
            "SELECT valor FROM MERCADO_CONFIG WHERE clave = ?", (clave,)
        )
        return rows[0]["valor"] if rows else default

    def _set_config(self, clave: str, valor: str) -> None:
        db_manager.execute_update(
            "INSERT OR REPLACE INTO MERCADO_CONFIG (clave, valor) VALUES (?,?)",
            (clave, valor),
        )

    # ── Loops ─────────────────────────────────────────────────────────────────

    def iniciar_loop(self, notif_callback: Optional[Callable] = None) -> None:
        """
        Inicia los loops de precios, dividendos y reporte diario.

        notif_callback(simbolo, nombre, texto, impacto_pct, es_positivo)
        """
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
        """Verifica cada 30 min si corresponde enviar el reporte diario."""
        while self._running:
            time.sleep(1800)
            try:
                hoy = date.today().isoformat()
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

            # Si precio_apertura no está seteado para hoy, lo inicializamos
            if p_apertura == 0:
                p_apertura = precio_ant

            # ── Random walk log-normal ────────────────────────────────────────
            z      = random.gauss(0, 1)
            factor = math.exp(vol * z)

            # ── Evento K-pop ──────────────────────────────────────────────────
            evento_texto = None
            impacto_pct  = 0.0
            es_positivo  = True

            if random.random() < PROB_EVENTO:
                if random.random() < 0.5:
                    ev, es_positivo = random.choice(EVENTOS_POSITIVOS), True
                else:
                    ev, es_positivo = random.choice(EVENTOS_NEGATIVOS), False

                impacto_pct  = random.uniform(*ev.impacto) / 100
                evento_texto = ev.texto
                factor      *= (1 + impacto_pct) if es_positivo else (1 - impacto_pct)

            # ── Circuit breaker ───────────────────────────────────────────────
            factor       = max(1 - CIRCUIT_BREAKER, min(1 + CIRCUIT_BREAKER, factor))
            precio_nuevo = max(PRECIO_MINIMO_ABS, round(precio_ant * factor, 2))

            p_max = max(p_max, precio_nuevo)
            p_min = min(p_min, precio_nuevo)

            db_manager.execute_update(
                """UPDATE MERCADO_ACTIVOS
                   SET precio_anterior=?, precio_actual=?, precio_apertura=?,
                       precio_maximo=?, precio_minimo=?, ultima_actualizacion=?
                   WHERE simbolo=?""",
                (precio_ant, precio_nuevo, p_apertura,
                 p_max, p_min, ahora, simbolo),
            )

            # ── Log del evento ────────────────────────────────────────────────
            if evento_texto:
                db_manager.execute_update(
                    """INSERT INTO MERCADO_EVENTOS_LOG
                       (timestamp, fecha, simbolo, nombre, evento_texto, impacto_pct, es_positivo)
                       VALUES (?,?,?,?,?,?,?)""",
                    (ahora, hoy, simbolo, nombre, evento_texto,
                     impacto_pct * 100 * (1 if es_positivo else -1),
                     1 if es_positivo else 0),
                )

                # Notificar en tiempo real
                if self._notif_cb:
                    try:
                        self._notif_cb(simbolo, nombre, evento_texto,
                                       impacto_pct * 100, es_positivo)
                    except Exception as exc:
                        logger.warning("[MERCADO] notif_cb: %s", exc)

        logger.info("[MERCADO] Precios actualizados (%d activos).", len(rows))

    def _resetear_precio_apertura(self) -> None:
        """Al inicio de un nuevo día, el precio actual se convierte en apertura."""
        db_manager.execute_update(
            "UPDATE MERCADO_ACTIVOS SET precio_apertura = precio_actual"
        )

    # ── Dividendos ────────────────────────────────────────────────────────────

    def _pagar_dividendos(self) -> None:
        rows = db_manager.execute_query(
            """SELECT p.userID, p.simbolo, p.cantidad, a.precio_actual, a.yield_diario
               FROM MERCADO_PORTFOLIO p
               JOIN MERCADO_ACTIVOS a ON p.simbolo = a.simbolo
               WHERE p.cantidad > 0"""
        )
        pagos: Dict[int, int] = {}
        for row in rows:
            uid      = int(row["userID"])
            div      = max(1, int(int(row["cantidad"]) * float(row["precio_actual"]) * float(row["yield_diario"])))
            economy_service.add_credits(uid, div, f"dividendo_{row['simbolo']}")
            pagos[uid] = pagos.get(uid, 0) + div

        if pagos and self._notif_cb:
            try:
                self._notif_cb(
                    "__DIVIDENDO__", "Mercado",
                    f"💰 Dividendos pagados a {len(pagos)} inversores. "
                    f"Total: {sum(pagos.values()):,} ✨",
                    0.0, True,
                )
            except Exception:
                pass
        logger.info("[MERCADO] Dividendos pagados: %d usuarios.", len(pagos))

    # ── Reporte diario ────────────────────────────────────────────────────────

    def _enviar_reporte_diario(self) -> None:
        """Genera el reporte del día y lo envía vía notif_cb."""
        if not self._notif_cb:
            return

        ayer = date.today().isoformat()   # Los eventos del día que termina

        # Todos los eventos del día
        eventos = db_manager.execute_query(
            """SELECT simbolo, nombre, evento_texto, impacto_pct, es_positivo
               FROM MERCADO_EVENTOS_LOG
               WHERE fecha = ?
               ORDER BY ABS(impacto_pct) DESC""",
            (ayer,),
        )

        # Precios actuales para el % diario
        activos = {a.simbolo: a for a in self.get_activos()}

        if not eventos:
            reporte = (
                "📊 <b>REPORTE DIARIO DEL MERCADO</b>\n\n"
                "Hoy no hubo noticias relevantes. El mercado operó con calma.\n\n"
            )
        else:
            subidas  = [e for e in eventos if e["es_positivo"] == 1]
            bajadas  = [e for e in eventos if e["es_positivo"] == 0]

            lineas = ["📊 <b>REPORTE DIARIO DEL MERCADO</b>\n"]

            if subidas:
                lineas.append("📈 <b>NOTICIAS POSITIVAS DEL DÍA:</b>")
                # Mostrar todas las noticias únicas del día
                vistos = set()
                for e in subidas:
                    key = (e["simbolo"], e["evento_texto"])
                    if key in vistos:
                        continue
                    vistos.add(key)
                    activo = activos.get(e["simbolo"])
                    var    = f" ({activo.variacion_diaria_pct:+.1f}% hoy)" if activo else ""
                    lineas.append(
                        f"🚀 <b>{e['nombre']} ({e['simbolo']})</b>{var}\n"
                        f"   📰 {e['evento_texto']}\n"
                        f"   Impacto: <b>+{abs(e['impacto_pct']):.1f}%</b>"
                    )

            if bajadas:
                lineas.append("\n📉 <b>NOTICIAS NEGATIVAS DEL DÍA:</b>")
                vistos = set()
                for e in bajadas:
                    key = (e["simbolo"], e["evento_texto"])
                    if key in vistos:
                        continue
                    vistos.add(key)
                    activo = activos.get(e["simbolo"])
                    var    = f" ({activo.variacion_diaria_pct:+.1f}% hoy)" if activo else ""
                    lineas.append(
                        f"💥 <b>{e['nombre']} ({e['simbolo']})</b>{var}\n"
                        f"   📰 {e['evento_texto']}\n"
                        f"   Impacto: <b>-{abs(e['impacto_pct']):.1f}%</b>"
                    )

            # Activos sin noticias
            con_noticia = {e["simbolo"] for e in eventos}
            sin_noticia = [a for s, a in activos.items() if s not in con_noticia]
            if sin_noticia:
                lineas.append(
                    "\n➡️ <b>Sin noticias hoy:</b> "
                    + ", ".join(f"{a.nombre} ({a.variacion_diaria_pct:+.1f}%)" for a in sin_noticia)
                )

            reporte = "\n".join(lineas)

        try:
            self._notif_cb("__REPORTE__", "Mercado", reporte, 0.0, True)
        except Exception as exc:
            logger.warning("[MERCADO] No se pudo enviar reporte: %s", exc)

        # Limpiar logs viejos (más de 7 días)
        db_manager.execute_update(
            "DELETE FROM MERCADO_EVENTOS_LOG WHERE fecha < date('now', '-7 days')"
        )

    # ── Consultas públicas ────────────────────────────────────────────────────

    def get_activos(self) -> List[Activo]:
        rows = db_manager.execute_query(
            "SELECT * FROM MERCADO_ACTIVOS ORDER BY precio_actual DESC"
        )
        return [self._to_activo(r) for r in rows]

    def get_activo(self, simbolo: str) -> Optional[Activo]:
        rows = db_manager.execute_query(
            "SELECT * FROM MERCADO_ACTIVOS WHERE simbolo = ?", (simbolo.upper(),)
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
        )

    def get_portfolio(self, user_id: int) -> List[Posicion]:
        rows = db_manager.execute_query(
            """SELECT p.simbolo, p.cantidad, p.costo_total,
                      a.nombre, a.precio_actual, a.yield_diario
               FROM MERCADO_PORTFOLIO p
               JOIN MERCADO_ACTIVOS a ON p.simbolo = a.simbolo
               WHERE p.userID = ? AND p.cantidad > 0
               ORDER BY (a.precio_actual * p.cantidad) DESC""",
            (user_id,),
        )
        return [
            Posicion(
                simbolo=r["simbolo"], nombre=r["nombre"],
                cantidad=int(r["cantidad"]), costo_total=float(r["costo_total"]),
                precio_actual=float(r["precio_actual"]), yield_diario=float(r["yield_diario"]),
            )
            for r in rows
        ]

    def get_ranking(self, top_n: int = 10) -> List[Dict]:
        rows = db_manager.execute_query(
            """SELECT p.userID,
                      SUM(p.cantidad * a.precio_actual) AS valor_total,
                      SUM(p.costo_total)                AS costo_total
               FROM MERCADO_PORTFOLIO p
               JOIN MERCADO_ACTIVOS a ON p.simbolo = a.simbolo
               WHERE p.cantidad > 0
               GROUP BY p.userID
               ORDER BY valor_total DESC LIMIT ?""",
            (top_n,),
        )
        resultado = []
        for r in rows:
            uid  = r["userID"]
            nrow = db_manager.execute_query("SELECT nombre FROM USUARIOS WHERE userID=?", (uid,))
            resultado.append({
                "user_id":     uid,
                "nombre":      nrow[0]["nombre"] if nrow else str(uid),
                "valor_total": float(r["valor_total"]),
                "costo_total": float(r["costo_total"]),
                "ganancia":    float(r["valor_total"]) - float(r["costo_total"]),
            })
        return resultado

    # ── Operaciones ───────────────────────────────────────────────────────────

    def comprar(self, user_id: int, simbolo: str, cantidad: int) -> Tuple[bool, str, Optional[float]]:
        simbolo = simbolo.upper()
        if not (COMPRA_MIN <= cantidad <= COMPRA_MAX):
            return False, f"Cantidad debe estar entre {COMPRA_MIN} y {COMPRA_MAX:,}.", None
        activo = self.get_activo(simbolo)
        if not activo:
            return False, f"Activo <b>{simbolo}</b> no encontrado. Usá /mercado.", None
        costo = math.ceil(activo.precio_actual * cantidad)
        saldo = economy_service.get_balance(user_id)
        if saldo < costo:
            return False, f"Saldo insuficiente.\nCosto: <b>{costo:,} ✨</b>  |  Tenés: <b>{saldo:,} ✨</b>", None
        if not economy_service.subtract_credits(user_id, costo, f"mercado_compra_{simbolo}"):
            return False, "Error al descontar cosmos.", None
        db_manager.execute_update(
            """INSERT INTO MERCADO_PORTFOLIO (userID, simbolo, cantidad, costo_total)
               VALUES (?,?,?,?)
               ON CONFLICT(userID, simbolo) DO UPDATE SET
                   cantidad=cantidad+excluded.cantidad, costo_total=costo_total+excluded.costo_total""",
            (user_id, simbolo, cantidad, float(costo)),
        )
        return True, "", float(costo)

    def vender(self, user_id: int, simbolo: str, cantidad: int) -> Tuple[bool, str, Optional[float]]:
        simbolo = simbolo.upper()
        activo = self.get_activo(simbolo)
        if not activo:
            return False, f"Activo <b>{simbolo}</b> no encontrado.", None
        rows = db_manager.execute_query(
            "SELECT cantidad, costo_total FROM MERCADO_PORTFOLIO WHERE userID=? AND simbolo=?",
            (user_id, simbolo),
        )
        disponibles = int(rows[0]["cantidad"]) if rows else 0
        if disponibles < cantidad:
            return False, f"Tenés <b>{disponibles}</b> acciones, querés vender <b>{cantidad}</b>.", None
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
        return True, "", float(ingreso)


# ─── Singleton ────────────────────────────────────────────────────────────────

mercado_service = MercadoService()
