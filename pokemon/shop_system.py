# -*- coding: utf-8 -*-
"""
Sistema de Tienda Pokémon - Integrado con items_database_complete
Más de 200 items disponibles

CORRECCIONES:
- comprar_item usa economy_service.subtract_credits (que verifica balance
  internamente) en lugar de un SELECT manual a la tabla USUARIOS, que podía
  causar "Error comprando item: 0" cuando el resultado del query era 0 o None.
- _agregar_a_inventario tiene manejo de error más robusto.
"""

import logging
from typing import Tuple, List, Dict
from database import db_manager
from funciones import economy_service
from pokemon.items_database_complete import (
    ITEMS_COMPLETOS_DB,
    CATEGORIAS_TIENDA,
    obtener_item_info,
    obtener_precio,
    es_vendible,
    obtener_items_categoria,
    obtener_items_vendibles,
)

logger = logging.getLogger(__name__)


class ShopSystem:
    """Sistema de tienda con 200+ items"""

    @staticmethod
    def obtener_catalogo_completo() -> Dict:
        """
        Obtiene catálogo completo organizado por categorías.

        Returns:
            Dict con categorías y sus items.
        """
        catalogo = {}

        for cat_id, cat_data in CATEGORIAS_TIENDA.items():
            items_cat = []

            for item_id in cat_data["items"]:
                item_info = obtener_item_info(item_id)
                if item_info and es_vendible(item_id):
                    items_cat.append(
                        {
                            "id": item_id,
                            "precio": item_info["precio"],
                            "desc": item_info["desc"],
                        }
                    )

            if items_cat:  # Solo categorías con items vendibles
                catalogo[cat_id] = {
                    "nombre": cat_data["nombre"],
                    "items": items_cat,
                    "orden": cat_data["orden"],
                }

        return catalogo

    @staticmethod
    def obtener_categoria(categoria_id: str) -> Tuple[bool, str, List]:
        """
        Obtiene items de una categoría específica.

        Returns:
            (exito, nombre_categoria, lista_items)
        """
        if categoria_id not in CATEGORIAS_TIENDA:
            return False, "", []

        cat_data   = CATEGORIAS_TIENDA[categoria_id]
        items_list = []

        for item_id in cat_data["items"]:
            item_info = obtener_item_info(item_id)
            if item_info and es_vendible(item_id):
                items_list.append(
                    {
                        "id":     item_id,
                        "precio": item_info["precio"],
                        "desc":   item_info["desc"],
                    }
                )

        return True, cat_data["nombre"], items_list

    @staticmethod
    def comprar_item(user_id: int, item_id: str, cantidad: int = 1) -> Tuple[bool, str]:
        """
        Compra un item.

        CORRECCIÓN: usa economy_service.subtract_credits para descontar cosmos.
        Ese método ya verifica internamente si el saldo es suficiente y retorna
        False si no lo es, sin lanzar excepciones.

        Args:
            user_id:  ID del usuario.
            item_id:  ID del item (se normaliza a minúsculas).
            cantidad: Cantidad a comprar (≥ 1).

        Returns:
            (exito, mensaje)
        """
        try:
            # ── Validaciones básicas ──────────────────────────────────────────
            if cantidad < 1:
                return False, "❌ La cantidad debe ser al menos 1."

            item_id = item_id.strip().lower()

            if item_id not in ITEMS_COMPLETOS_DB:
                return False, f"❌ Item '{item_id}' no encontrado en la tienda."

            if not es_vendible(item_id):
                return False, f"❌ '{item_id}' no está disponible para comprar."

            item_info       = obtener_item_info(item_id)
            precio_unitario = item_info["precio"]
            costo_total     = precio_unitario * cantidad

            # ── Verificar saldo antes de intentar descontar ───────────────────
            saldo_actual = economy_service.get_balance(user_id)
            if saldo_actual < costo_total:
                faltante = costo_total - saldo_actual
                return (
                    False,
                    f"❌ Cosmos insuficientes.\n"
                    f"💰 Necesitas: {costo_total}\n"
                    f"💳 Tienes:    {saldo_actual}\n"
                    f"🔻 Te faltan: {faltante}",
                )

            # ── Descontar cosmos ──────────────────────────────────────────────
            # subtract_credits verifica saldo internamente y retorna bool.
            exito = economy_service.subtract_credits(
                user_id,
                costo_total,
                f"Compra tienda: {cantidad}x {item_id}",
            )

            if not exito:
                return False, "❌ No se pudo procesar el pago. Inténtalo de nuevo."

            # ── Agregar al inventario ─────────────────────────────────────────
            ok_inv, msg_inv = ShopSystem._agregar_a_inventario(user_id, item_id, cantidad)
            if not ok_inv:
                # Revertir el cobro si el inventario falla
                economy_service.add_credits(
                    user_id,
                    costo_total,
                    f"Reversión compra fallida: {item_id}",
                )
                logger.error(f"[SHOP] Inventario falló, cosmos revertidos para {user_id}.")
                return False, "❌ Error al añadir el item al inventario. El pago fue revertido."

            logger.info(
                f"[SHOP] {user_id} compró {cantidad}x '{item_id}' por {costo_total} cosmos."
            )

            saldo_nuevo = economy_service.get_balance(user_id)
            return (
                True,
                f"✅ <b>¡Compra exitosa!</b>\n\n"
                f"🛒 {cantidad}× <b>{item_id}</b>\n"
                f"💰 Total: <b>{costo_total} cosmos</b> ({precio_unitario}/u)\n"
                f"📝 {item_info['desc']}\n\n"
                f"💳 Saldo restante: {saldo_nuevo} cosmos",
            )

        except Exception as e:
            logger.error(f"[SHOP] Error comprando item: {e}", exc_info=True)
            return False, f"❌ Error inesperado: {e}"

    @staticmethod
    def _agregar_a_inventario(user_id: int, item_id: str, cantidad: int) -> Tuple[bool, str]:
        """
        Agrega item al inventario del usuario.

        Returns:
            (exito, mensaje)
        """
        try:
            # Verificar si ya tiene el item
            query_sel = """
                SELECT cantidad FROM INVENTARIO_USUARIO
                WHERE userID = ? AND item_nombre = ?
            """
            result = db_manager.execute_query(query_sel, (user_id, item_id))

            if result:
                # Sumar a la cantidad existente
                # execute_query siempre retorna List[Dict] gracias al row_factory del db_manager
                cantidad_actual = result[0]["cantidad"]
                nueva_cantidad  = cantidad_actual + cantidad
                db_manager.execute_update(
                    "UPDATE INVENTARIO_USUARIO SET cantidad = ? WHERE userID = ? AND item_nombre = ?",
                    (nueva_cantidad, user_id, item_id),
                )
            else:
                # Insertar fila nueva
                db_manager.execute_update(
                    "INSERT INTO INVENTARIO_USUARIO (userID, item_nombre, cantidad) VALUES (?, ?, ?)",
                    (user_id, item_id, cantidad),
                )

            return True, "ok"

        except Exception as e:
            logger.error(f"[SHOP] Error agregando a inventario ({user_id}, {item_id}): {e}", exc_info=True)
            return False, str(e)

    @staticmethod
    def obtener_inventario(user_id: int) -> List[Dict]:
        """
        Obtiene el inventario del usuario.

        Returns:
            Lista de dicts {id, cantidad, precio, desc}.
        """
        try:
            query  = """
                SELECT item_nombre, cantidad
                FROM INVENTARIO_USUARIO
                WHERE userID = ? AND cantidad > 0
                ORDER BY item_nombre
            """
            result = db_manager.execute_query(query, (user_id,))

            if not result:
                return []

            inventario = []
            for row in result:
                # execute_query siempre retorna Dict gracias al row_factory
                item_id  = row["item_nombre"]
                cantidad = row["cantidad"]

                item_info = obtener_item_info(item_id)
                if item_info:
                    inventario.append(
                        {
                            "id":       item_id,
                            "cantidad": cantidad,
                            "precio":   item_info.get("precio", 0),
                            "desc":     item_info.get("desc", ""),
                        }
                    )

            return inventario

        except Exception as e:
            logger.error(f"[SHOP] Error obteniendo inventario: {e}")
            return []

    @staticmethod
    def vender_item(user_id: int, item_id: str, cantidad: int = 1) -> Tuple[bool, str]:
        """
        Vende un item (50 % del precio de compra).

        Returns:
            (exito, mensaje)
        """
        try:
            item_id = item_id.strip().lower()

            query_sel = """
                SELECT cantidad FROM INVENTARIO_USUARIO
                WHERE userID = ? AND item_nombre = ?
            """
            result = db_manager.execute_query(query_sel, (user_id, item_id))

            if not result:
                return False, f"❌ No tienes '{item_id}' en tu inventario."

            # execute_query siempre retorna Dict gracias al row_factory
            cant_actual = result[0]["cantidad"]
            if cant_actual < cantidad:
                return False, f"❌ Solo tienes {cant_actual}× '{item_id}'."

            precio_compra = obtener_precio(item_id)
            precio_venta  = max(1, precio_compra // 2)
            ganancia      = precio_venta * cantidad

            # Actualizar inventario
            nueva_cantidad = cant_actual - cantidad
            if nueva_cantidad <= 0:
                db_manager.execute_update(
                    "DELETE FROM INVENTARIO_USUARIO WHERE userID = ? AND item_nombre = ?",
                    (user_id, item_id),
                )
            else:
                db_manager.execute_update(
                    "UPDATE INVENTARIO_USUARIO SET cantidad = ? WHERE userID = ? AND item_nombre = ?",
                    (nueva_cantidad, user_id, item_id),
                )

            economy_service.add_credits(user_id, ganancia, f"Venta: {cantidad}x {item_id}")

            return (
                True,
                f"✅ Vendiste {cantidad}× <b>{item_id}</b>\n"
                f"💰 Ganancia: <b>{ganancia} cosmos</b> ({precio_venta}/u)",
            )

        except Exception as e:
            logger.error(f"[SHOP] Error vendiendo item: {e}", exc_info=True)
            return False, f"❌ Error: {e}"


# Instancia global
shop_system = ShopSystem()