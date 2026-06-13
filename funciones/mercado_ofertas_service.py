# -*- coding: utf-8 -*-
"""
funciones/mercado_ofertas_service.py
════════════════════════════════════════════════════════════════════════════════
Sistema P2P de Ofertas de Acciones — UniverseBot V2.0

Permite a los usuarios vender acciones directamente a otros a precio acordado,
sin pasar por el sistema de precios del mercado.

Tipos de oferta:
  · Pública   — visible para todos, cualquiera puede aceptar
  · Directa   — dirigida a un usuario específico, solo él puede aceptar

Tabla DB:
  MERCADO_OFERTAS:
    id, vendedor_id, vendedor_nombre, comprador_id (NULL=pública),
    simbolo, cantidad, precio_unit, estado, fecha_creacion, fecha_cierre
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from database import db_manager
from funciones import economy_service
from funciones.mercado_service import mercado_service

logger = logging.getLogger(__name__)

OFERTA_EXPIRA_HORAS = 48     # Las ofertas directas expiran en 48 h
PRECIO_MIN_UNIT     = 1      # Precio mínimo por acción
PRECIO_MAX_UNIT     = 9_999_999
CANTIDAD_MIN        = 1
CANTIDAD_MAX        = 10_000


class MercadoOfertasService:
    """Gestiona el mercado P2P de acciones. Singleton."""

    def __init__(self) -> None:
        self._init_db()

    # ── DB ────────────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        db_manager.execute_update("""
            CREATE TABLE IF NOT EXISTS MERCADO_OFERTAS (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                vendedor_id      INTEGER NOT NULL,
                vendedor_nombre  TEXT    NOT NULL,
                comprador_id     INTEGER DEFAULT NULL,
                comprador_nombre TEXT    DEFAULT NULL,
                simbolo          TEXT    NOT NULL,
                cantidad         INTEGER NOT NULL,
                precio_unit      REAL    NOT NULL,
                estado           TEXT    NOT NULL DEFAULT 'activa',
                fecha_creacion   TEXT    NOT NULL,
                fecha_cierre     TEXT    DEFAULT NULL
            )
        """)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _shares_en_oferta(self, vendedor_id: int, simbolo: str) -> int:
        """Total de acciones del usuario que ya están en ofertas activas."""
        rows = db_manager.execute_query(
            """SELECT COALESCE(SUM(cantidad), 0) as total
               FROM MERCADO_OFERTAS
               WHERE vendedor_id = ? AND simbolo = ? AND estado = 'activa'""",
            (vendedor_id, simbolo.upper()),
        )
        return int(rows[0]["total"]) if rows else 0

    def _shares_disponibles(self, vendedor_id: int, simbolo: str) -> int:
        """Acciones que el usuario puede poner en oferta (portfolio - ya en oferta)."""
        rows = db_manager.execute_query(
            "SELECT COALESCE(cantidad, 0) as cant FROM MERCADO_PORTFOLIO WHERE userID=? AND simbolo=?",
            (vendedor_id, simbolo.upper()),
        )
        en_portfolio = int(rows[0]["cant"]) if rows else 0
        en_oferta    = self._shares_en_oferta(vendedor_id, simbolo)
        return max(0, en_portfolio - en_oferta)

    def _get_oferta(self, oferta_id: int) -> Optional[Dict]:
        rows = db_manager.execute_query(
            "SELECT * FROM MERCADO_OFERTAS WHERE id = ?", (oferta_id,)
        )
        return dict(rows[0]) if rows else None

    def _expirada(self, oferta: Dict) -> bool:
        """True si la oferta directa tiene más de OFERTA_EXPIRA_HORAS horas."""
        if not oferta.get("comprador_id"):
            return False  # Las públicas no expiran
        try:
            creada = datetime.fromisoformat(oferta["fecha_creacion"])
            return datetime.now() - creada > timedelta(hours=OFERTA_EXPIRA_HORAS)
        except Exception:
            return False

    # ── Crear oferta ──────────────────────────────────────────────────────────

    def crear_oferta(
        self,
        vendedor_id:      int,
        vendedor_nombre:  str,
        simbolo:          str,
        cantidad:         int,
        precio_unit:      float,
        comprador_id:     Optional[int] = None,
        comprador_nombre: Optional[str] = None,
    ) -> Tuple[bool, str, int]:
        """
        Crea una oferta pública (comprador_id=None) o directa.

        Returns:
            (True, "", oferta_id)     — éxito
            (False, mensaje, 0)       — error
        """
        simbolo = simbolo.upper()

        # ── Validaciones básicas ──────────────────────────────────────────────
        if not (CANTIDAD_MIN <= cantidad <= CANTIDAD_MAX):
            return False, f"Cantidad debe ser entre {CANTIDAD_MIN} y {CANTIDAD_MAX:,}.", 0
        if not (PRECIO_MIN_UNIT <= precio_unit <= PRECIO_MAX_UNIT):
            return False, f"Precio inválido.", 0
        if comprador_id and comprador_id == vendedor_id:
            return False, "No podés ofrecerte acciones a vos mismo.", 0

        # ── Verificar que el activo existe ────────────────────────────────────
        activo = mercado_service.get_activo(simbolo)
        if not activo:
            return False, f"Activo <b>{simbolo}</b> no encontrado. Usá /mercado.", 0

        # ── Verificar acciones disponibles ────────────────────────────────────
        disponibles = self._shares_disponibles(vendedor_id, simbolo)
        if cantidad > disponibles:
            en_oferta = self._shares_en_oferta(vendedor_id, simbolo)
            return False, (
                f"No tenés suficientes acciones disponibles.\n"
                f"En portfolio: <b>{disponibles + en_oferta}</b>  |  "
                f"Ya en oferta: <b>{en_oferta}</b>  |  "
                f"Disponibles: <b>{disponibles}</b>"
            ), 0

        # ── Insertar oferta ───────────────────────────────────────────────────
        # Se usa una marca temporal única como huella para poder recuperar la
        # fila exacta si execute_insert no devolviera el ID de forma fiable.
        fecha_creacion = datetime.now().isoformat()
        oferta_id = db_manager.execute_insert(
            """INSERT INTO MERCADO_OFERTAS
               (vendedor_id, vendedor_nombre, comprador_id, comprador_nombre,
                simbolo, cantidad, precio_unit, estado, fecha_creacion)
               VALUES (?,?,?,?,?,?,?,'activa',?)""",
            (vendedor_id, vendedor_nombre, comprador_id, comprador_nombre,
             simbolo, cantidad, float(precio_unit), fecha_creacion),
        )

        # Red de seguridad: si execute_insert devolvió 0/None (p. ej. una versión
        # vieja del gestor de BD o cualquier caso límite), recuperamos el ID REAL
        # de la fila recién insertada por su huella (vendedor + fecha exacta).
        # Así el número que se muestra SIEMPRE coincide con el de la base.
        if not oferta_id:
            rows = db_manager.execute_query(
                """SELECT id FROM MERCADO_OFERTAS
                   WHERE vendedor_id=? AND fecha_creacion=?
                   ORDER BY id DESC LIMIT 1""",
                (vendedor_id, fecha_creacion),
            )
            oferta_id = int(rows[0]["id"]) if rows else 0
            if oferta_id:
                logger.warning(
                    "[OFERTAS] execute_insert devolvió valor vacío; ID recuperado por huella: #%d",
                    oferta_id,
                )

        if not oferta_id:
            logger.error("[OFERTAS] crear_oferta: no se pudo determinar el ID de la nueva oferta.")
            return False, "Error al crear la oferta. Intentá de nuevo.", 0

        tipo = "directa" if comprador_id else "pública"
        logger.info(
            "[OFERTAS] Oferta #%d creada | %s | %s ×%d @ %.0f ✨/acc | tipo=%s",
            oferta_id, vendedor_nombre, simbolo, cantidad, precio_unit, tipo,
        )
        return True, "", oferta_id

    # ── Aceptar oferta ────────────────────────────────────────────────────────

    def aceptar_oferta(
        self,
        comprador_id:     int,
        comprador_nombre: str,
        oferta_id:        int,
    ) -> Tuple[bool, str, Optional[Dict]]:
        """
        El comprador acepta la oferta.

        Flujo:
          1. Validar oferta activa y permisos
          2. Verificar que el vendedor aún tiene las acciones
          3. Verificar cosmos del comprador
          4. Ejecutar: cosmos comprador → vendedor, acciones vendedor → comprador
          5. Marcar oferta como completada

        Returns:
            (True, "", resumen_dict)   — éxito
            (False, mensaje, None)     — error
        """
        # Serializar con las operaciones del mercado: comparten MERCADO_PORTFOLIO.
        # Reusar el lock del servicio principal evita races entre /comprar,
        # /vender y aceptar ofertas P2P (incl. dos compradores a la vez).
        with mercado_service._lock:
            return self._aceptar_oferta_locked(comprador_id, comprador_nombre, oferta_id)

    def _aceptar_oferta_locked(
        self,
        comprador_id:     int,
        comprador_nombre: str,
        oferta_id:        int,
    ) -> Tuple[bool, str, Optional[Dict]]:
        oferta = self._get_oferta(oferta_id)
        if not oferta:
            return False, f"Oferta #{oferta_id} no encontrada.", None
        if oferta["estado"] != "activa":
            return False, f"La oferta #{oferta_id} ya no está activa (estado: {oferta['estado']}).", None
        if self._expirada(oferta):
            db_manager.execute_update(
                "UPDATE MERCADO_OFERTAS SET estado='expirada', fecha_cierre=? WHERE id=?",
                (datetime.now().isoformat(), oferta_id),
            )
            return False, "Esta oferta expiró.", None

        # ── Permisos ──────────────────────────────────────────────────────────
        if oferta["comprador_id"] and int(oferta["comprador_id"]) != comprador_id:
            return False, "Esta oferta no es para vos.", None
        if int(oferta["vendedor_id"]) == comprador_id:
            return False, "No podés comprar tu propia oferta.", None

        simbolo  = oferta["simbolo"]
        cantidad = int(oferta["cantidad"])
        precio_u = float(oferta["precio_unit"])
        total    = math.ceil(precio_u * cantidad)

        # ── Verificar que el vendedor aún tiene las acciones ──────────────────
        rows_v = db_manager.execute_query(
            "SELECT COALESCE(cantidad, 0) as cant FROM MERCADO_PORTFOLIO WHERE userID=? AND simbolo=?",
            (int(oferta["vendedor_id"]), simbolo),
        )
        cant_vendedor = int(rows_v[0]["cant"]) if rows_v else 0
        if cant_vendedor < cantidad:
            db_manager.execute_update(
                "UPDATE MERCADO_OFERTAS SET estado='cancelada', fecha_cierre=? WHERE id=?",
                (datetime.now().isoformat(), oferta_id),
            )
            return False, (
                f"El vendedor ya no tiene suficientes acciones. "
                f"Oferta cancelada automáticamente."
            ), None

        # ── Verificar cosmos del comprador ────────────────────────────────────
        saldo = economy_service.get_balance(comprador_id)
        if saldo < total:
            return False, (
                f"Cosmos insuficientes.\n"
                f"Necesitás: <b>{total:,} ✨</b>  |  Tenés: <b>{saldo:,} ✨</b>"
            ), None

        # ── Ejecutar transacción ──────────────────────────────────────────────
        vendedor_id = int(oferta["vendedor_id"])

        # 1. Descontar cosmos del comprador
        if not economy_service.subtract_credits(comprador_id, total, f"compra_p2p_{simbolo}_{oferta_id}"):
            return False, "Error al descontar cosmos.", None

        # 2-4. Transferencia atómica: pagar al vendedor y mover las acciones.
        # Si algo falla a mitad, revertir TODO para no dejar a nadie sin
        # cosmos ni acciones.
        try:
            economy_service.add_credits(vendedor_id, total, f"venta_p2p_{simbolo}_{oferta_id}")

            costo_prop = 0.0
            rows_costo = db_manager.execute_query(
                "SELECT costo_total FROM MERCADO_PORTFOLIO WHERE userID=? AND simbolo=?",
                (vendedor_id, simbolo),
            )
            if rows_costo:
                costo_total_v = float(rows_costo[0]["costo_total"])
                costo_prop    = (cantidad / cant_vendedor) * costo_total_v

            if cant_vendedor == cantidad:
                db_manager.execute_update(
                    "DELETE FROM MERCADO_PORTFOLIO WHERE userID=? AND simbolo=?",
                    (vendedor_id, simbolo),
                )
            else:
                db_manager.execute_update(
                    "UPDATE MERCADO_PORTFOLIO SET cantidad=cantidad-?, costo_total=costo_total-? WHERE userID=? AND simbolo=?",
                    (cantidad, costo_prop, vendedor_id, simbolo),
                )

            db_manager.execute_update(
                """INSERT INTO MERCADO_PORTFOLIO (userID, simbolo, cantidad, costo_total)
                   VALUES (?,?,?,?)
                   ON CONFLICT(userID, simbolo) DO UPDATE SET
                       cantidad=cantidad+excluded.cantidad,
                       costo_total=costo_total+excluded.costo_total""",
                (comprador_id, simbolo, cantidad, float(total)),
            )
        except Exception as exc:
            logger.error("[MERCADO] aceptar_oferta transfer falló, revirtiendo: %s", exc)
            # Devolver cosmos al comprador y quitar el pago al vendedor.
            try:
                economy_service.add_credits(comprador_id, total, f"reversion_compra_p2p_{oferta_id}")
                economy_service.subtract_credits(vendedor_id, total, f"reversion_venta_p2p_{oferta_id}")
            except Exception as exc2:
                logger.error("[MERCADO] reversión P2P también falló: %s", exc2)
            return False, "Error al ejecutar la transacción. La operación fue revertida.", None

        # 5. Marcar oferta como completada
        db_manager.execute_update(
            """UPDATE MERCADO_OFERTAS
               SET estado='completada', fecha_cierre=?,
                   comprador_id=?, comprador_nombre=?
               WHERE id=?""",
            (datetime.now().isoformat(), comprador_id, comprador_nombre, oferta_id),
        )

        # 6. Verificar cambio de CEO
        ceo_event_v = mercado_service._check_ceo(simbolo, vendedor_id,  oferta["vendedor_nombre"])
        ceo_event_c = mercado_service._check_ceo(simbolo, comprador_id, comprador_nombre)

        resumen = {
            "oferta_id":        oferta_id,
            "simbolo":          simbolo,
            "nombre_activo":    mercado_service.get_activo(simbolo).nombre if mercado_service.get_activo(simbolo) else simbolo,
            "cantidad":         cantidad,
            "precio_unit":      precio_u,
            "total":            total,
            "vendedor_id":      vendedor_id,
            "vendedor_nombre":  oferta["vendedor_nombre"],
            "comprador_id":     comprador_id,
            "comprador_nombre": comprador_nombre,
            "ceo_event":        ceo_event_c or ceo_event_v,
        }
        logger.info(
            "[OFERTAS] #%d completada | %s → %s | %s ×%d @ %.0f ✨",
            oferta_id, oferta["vendedor_nombre"], comprador_nombre,
            simbolo, cantidad, precio_u,
        )
        return True, "", resumen

    # ── Cancelar oferta ───────────────────────────────────────────────────────

    def cancelar_oferta(self, user_id: int, oferta_id: int) -> Tuple[bool, str]:
        oferta = self._get_oferta(oferta_id)
        if not oferta:
            return False, f"Oferta #{oferta_id} no encontrada."
        if int(oferta["vendedor_id"]) != user_id:
            return False, "Solo podés cancelar tus propias ofertas."
        if oferta["estado"] != "activa":
            return False, f"La oferta #{oferta_id} ya no está activa."
        db_manager.execute_update(
            "UPDATE MERCADO_OFERTAS SET estado='cancelada', fecha_cierre=? WHERE id=?",
            (datetime.now().isoformat(), oferta_id),
        )
        return True, ""

    # ── Rechazar oferta ─────────────────────────────────────────────────────────

    def rechazar_oferta(self, user_id: int, oferta_id: int) -> Tuple[bool, str]:
        """
        El destinatario de una oferta DIRECTA la rechaza.

        Al marcarla como 'rechazada' deja de contar en _shares_en_oferta,
        de modo que las acciones del vendedor vuelven a quedar disponibles.

        Returns:
            (True, "")          — rechazada correctamente
            (False, mensaje)    — error
        """
        oferta = self._get_oferta(oferta_id)
        if not oferta:
            return False, f"Oferta #{oferta_id} no encontrada."
        # Solo las ofertas directas tienen destinatario; las públicas no se rechazan.
        if not oferta.get("comprador_id"):
            return False, "Las ofertas públicas no se rechazan; solo el vendedor puede cancelarlas."
        if int(oferta["comprador_id"]) != user_id:
            return False, "Esta oferta directa no es para vos."
        if oferta["estado"] != "activa":
            return False, f"La oferta #{oferta_id} ya no está activa."
        db_manager.execute_update(
            "UPDATE MERCADO_OFERTAS SET estado='rechazada', fecha_cierre=? WHERE id=?",
            (datetime.now().isoformat(), oferta_id),
        )
        logger.info(
            "[OFERTAS] #%d rechazada por destinatario %d | vendedor=%s %s ×%d",
            oferta_id, user_id, oferta["vendedor_nombre"],
            oferta["simbolo"], int(oferta["cantidad"]),
        )
        return True, ""

    # ── Mantenimiento: barrer ofertas vencidas ───────────────────────────────────

    def barrer_expiradas(self) -> int:
        """
        Marca como 'expirada' toda oferta directa activa cuyo plazo venció.

        La expiración antes solo se evaluaba al intentar aceptar una oferta;
        si nadie la tocaba, quedaba 'activa' para siempre y congelaba las
        acciones del vendedor. Este barrido las libera sin intervención.

        Devuelve la cantidad de ofertas expiradas en esta pasada.
        """
        rows = db_manager.execute_query(
            """SELECT id, fecha_creacion FROM MERCADO_OFERTAS
               WHERE estado='activa' AND comprador_id IS NOT NULL""",
        )
        if not rows:
            return 0
        ahora     = datetime.now()
        limite    = timedelta(hours=OFERTA_EXPIRA_HORAS)
        expiradas = 0
        for r in rows:
            try:
                creada = datetime.fromisoformat(r["fecha_creacion"])
            except Exception:
                continue
            if ahora - creada > limite:
                db_manager.execute_update(
                    "UPDATE MERCADO_OFERTAS SET estado='expirada', fecha_cierre=? WHERE id=?",
                    (ahora.isoformat(), int(r["id"])),
                )
                expiradas += 1
        if expiradas:
            logger.info("[OFERTAS] barrer_expiradas: %d oferta(s) marcadas como expiradas.", expiradas)
        return expiradas

    # ── Consultas ─────────────────────────────────────────────────────────────

    def get_ofertas_publicas(self, simbolo: Optional[str] = None) -> List[Dict]:
        """Ofertas públicas activas, ordenadas por precio ascendente."""
        if simbolo:
            rows = db_manager.execute_query(
                """SELECT * FROM MERCADO_OFERTAS
                   WHERE estado='activa' AND comprador_id IS NULL AND simbolo=?
                   ORDER BY precio_unit ASC""",
                (simbolo.upper(),),
            )
        else:
            rows = db_manager.execute_query(
                """SELECT * FROM MERCADO_OFERTAS
                   WHERE estado='activa' AND comprador_id IS NULL
                   ORDER BY simbolo, precio_unit ASC""",
            )
        return [dict(r) for r in rows] if rows else []

    def get_mis_ofertas(self, user_id: int) -> List[Dict]:
        rows = db_manager.execute_query(
            """SELECT * FROM MERCADO_OFERTAS
               WHERE vendedor_id=? AND estado='activa'
               ORDER BY fecha_creacion DESC""",
            (user_id,),
        )
        return [dict(r) for r in rows] if rows else []

    def get_ofertas_recibidas(self, user_id: int) -> List[Dict]:
        """Ofertas directas que llegaron a este usuario y están activas."""
        rows = db_manager.execute_query(
            """SELECT * FROM MERCADO_OFERTAS
               WHERE comprador_id=? AND estado='activa'
               ORDER BY fecha_creacion DESC""",
            (user_id,),
        )
        return [dict(r) for r in rows] if rows else []


# ─── Singleton ────────────────────────────────────────────────────────────────

mercado_ofertas_service = MercadoOfertasService()
