"""
Servicio de Cartas Coleccionables Pokémon COMPLETO
Sistema expandible con colecciones periódicas desde src/
"""

import json
import logging
import random
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from datetime import datetime
from database import db_manager

logger = logging.getLogger(__name__)


class CartasService:
    """Servicio completo de cartas coleccionables"""
    
    def __init__(self):
        self.db = db_manager
        self.ruta_recursos = Path("./src/cartas/")
        self.rarezas = {
            "Common": {"peso": 60, "emoji": "⚪"},
            "Uncommon": {"peso": 30, "emoji": "🟢"},
            "Rare": {"peso": 8, "emoji": "🔵"},
            "Holo Rare": {"peso": 1.5, "emoji": "✨"},
            "Ultra Rare": {"peso": 0.4, "emoji": "🌟"},
            "Secret Rare": {"peso": 0.1, "emoji": "💎"}
        }
        self._asegurar_directorios()
    
    def _asegurar_directorios(self):
        """Crea estructura de directorios para cartas"""
        self.ruta_recursos.mkdir(parents=True, exist_ok=True)
        (self.ruta_recursos / "colecciones").mkdir(exist_ok=True)
        (self.ruta_recursos / "iconos").mkdir(exist_ok=True)
    
    # ========== GESTIÓN DE COLECCIONES ==========
    
    def crear_coleccion(self, nombre: str, descripcion: str, 
                       total_cartas: int, fecha_lanzamiento: str,
                       icono: Optional[str] = None) -> Tuple[bool, str]:
        """
        Crea una nueva colección de cartas
        
        Args:
            nombre: Nombre de la colección (ej: "Base Set")
            descripcion: Descripción
            total_cartas: Número total de cartas
            fecha_lanzamiento: Fecha en formato YYYY-MM-DD
            icono: Ruta relativa al icono en src/
        
        Returns:
            (exito, mensaje)
        """
        try:
            query = """
                INSERT INTO COLECCIONES (nombre, descripcion, total_cartas, fecha_lanzamiento, icono)
                VALUES (?, ?, ?, ?, ?)
            """
            
            self.db.execute_update(query, (
                nombre,
                descripcion,
                total_cartas,
                fecha_lanzamiento,
                icono or f"cartas/iconos/{nombre.lower().replace(' ', '_')}.png"
            ))
            
            logger.info(f"✅ Colección '{nombre}' creada")
            
            return True, f"✅ Colección '{nombre}' creada exitosamente"
            
        except Exception as e:
            logger.error(f"❌ Error creando colección: {e}")
            return False, f"Error: {str(e)}"
    
    def agregar_carta(self, card_id: str, nombre: str, coleccion: str,
                     numero: int, rareza: str, tipo: str,
                     pokemon_id: Optional[int] = None,
                     descripcion: Optional[str] = None) -> Tuple[bool, str]:
        """
        Agrega una carta a la base de datos
        
        Args:
            card_id: ID único (ej: "pikachu_base_58")
            nombre: Nombre de la carta
            coleccion: Nombre de la colección
            numero: Número en la colección
            rareza: Common, Uncommon, Rare, etc.
            tipo: Pokemon, Trainer, Energy
            pokemon_id: ID del Pokémon (opcional)
            descripcion: Descripción de la carta
        
        Returns:
            (exito, mensaje)
        """
        try:
            # Ruta de imagen basada en convención
            ruta_imagen = f"cartas/colecciones/{coleccion.lower().replace(' ', '_')}/{card_id}.png"
            
            query = """
                INSERT INTO CARTAS (
                    card_id, nombre, coleccion, numero, rareza, tipo,
                    pokemon_id, ruta_imagen, descripcion, fecha_lanzamiento
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            # Obtener fecha de la colección
            col_query = "SELECT fecha_lanzamiento FROM COLECCIONES WHERE nombre = ?"
            col_result = self.db.execute_query(col_query, (coleccion,))
            fecha = col_result[0]['fecha_lanzamiento'] if col_result else datetime.now().strftime("%Y-%m-%d")
            
            self.db.execute_update(query, (
                card_id,
                nombre,
                coleccion,
                numero,
                rareza,
                tipo,
                pokemon_id,
                ruta_imagen,
                descripcion,
                fecha
            ))
            
            logger.info(f"✅ Carta '{card_id}' agregada")
            
            return True, f"✅ Carta '{nombre}' agregada a '{coleccion}'"
            
        except Exception as e:
            logger.error(f"❌ Error agregando carta: {e}")
            return False, f"Error: {str(e)}"
    
    def cargar_cartas_desde_json(self, coleccion: str, archivo_json: Path) -> Tuple[bool, str, int]:
        """
        Carga múltiples cartas desde un archivo JSON
        
        Formato JSON esperado:
        {
          "cartas": [
            {
              "card_id": "pikachu_base_58",
              "nombre": "Pikachu",
              "numero": 58,
              "rareza": "Common",
              "tipo": "Pokemon",
              "pokemon_id": 25,
              "descripcion": "Ratón eléctrico"
            },
            ...
          ]
        }
        
        Returns:
            (exito, mensaje, cartas_agregadas)
        """
        try:
            with open(archivo_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            cartas = data.get('cartas', [])
            agregadas = 0
            
            for carta in cartas:
                exito, _ = self.agregar_carta(
                    card_id=carta['card_id'],
                    nombre=carta['nombre'],
                    coleccion=coleccion,
                    numero=carta['numero'],
                    rareza=carta['rareza'],
                    tipo=carta['tipo'],
                    pokemon_id=carta.get('pokemon_id'),
                    descripcion=carta.get('descripcion')
                )
                
                if exito:
                    agregadas += 1
            
            logger.info(f"✅ {agregadas}/{len(cartas)} cartas cargadas desde {archivo_json}")
            
            return True, f"✅ {agregadas}/{len(cartas)} cartas cargadas", agregadas
            
        except Exception as e:
            logger.error(f"❌ Error cargando cartas desde JSON: {e}")
            return False, f"Error: {str(e)}", 0
    
    # ========== SISTEMA DE SOBRES ==========
    
    def abrir_sobre(self, user_id: int, coleccion: str) -> Tuple[bool, str, List[Dict]]:
        """
        Abre un sobre de cartas (5 cartas aleatorias)
        
        Returns:
            (exito, mensaje, lista_cartas)
        """
        try:
            # Verificar que la colección existe y está activa
            col_query = "SELECT * FROM COLECCIONES WHERE nombre = ? AND activa = 1"
            col_result = self.db.execute_query(col_query, (coleccion,))
            
            if not col_result:
                return False, "Colección no disponible", []
            
            # Obtener todas las cartas de la colección
            cartas_query = "SELECT * FROM CARTAS WHERE coleccion = ?"
            cartas_disponibles = self.db.execute_query(cartas_query, (coleccion,))
            
            if not cartas_disponibles:
                return False, "No hay cartas disponibles en esta colección", []
            
            # Generar 5 cartas con rareza ponderada
            cartas_obtenidas = []
            
            for _ in range(5):
                carta = self._seleccionar_carta_ponderada(cartas_disponibles)
                cartas_obtenidas.append(carta)
                
                # Agregar carta al inventario del usuario
                self._agregar_carta_usuario(user_id, carta['card_id'])
            
            # Formatear mensaje
            mensaje = f"📦 ¡Abriste un sobre de {coleccion}!\n\n"
            mensaje += "Cartas obtenidas:\n"
            
            for carta in cartas_obtenidas:
                emoji = self.rarezas.get(carta['rareza'], {}).get('emoji', '⚪')
                mensaje += f"{emoji} {carta['nombre']} ({carta['rareza']})\n"
            
            logger.info(f"📦 Usuario {user_id} abrió sobre de {coleccion}")
            
            return True, mensaje, cartas_obtenidas
            
        except Exception as e:
            logger.error(f"❌ Error abriendo sobre: {e}")
            return False, f"Error: {str(e)}", []
    
    def _seleccionar_carta_ponderada(self, cartas_disponibles: List) -> Dict:
        """Selecciona una carta aleatoria con ponderación por rareza"""
        # Crear lista ponderada
        cartas_ponderadas = []
        pesos = []
        
        for carta in cartas_disponibles:
            rareza = carta['rareza']
            peso = self.rarezas.get(rareza, {}).get('peso', 1)
            cartas_ponderadas.append(dict(carta))
            pesos.append(peso)
        
        # Seleccionar con pesos
        carta_seleccionada = random.choices(cartas_ponderadas, weights=pesos, k=1)[0]
        
        return carta_seleccionada
    
    def _agregar_carta_usuario(self, user_id: int, card_id: str):
        """Agrega una carta al inventario del usuario"""
        try:
            # Verificar si ya tiene la carta
            query = "SELECT cantidad FROM CARTAS_USUARIO WHERE userID = ? AND card_id = ?"
            result = self.db.execute_query(query, (user_id, card_id))
            
            if result:
                # Incrementar cantidad
                nueva_cantidad = result[0]['cantidad'] + 1
                update_query = "UPDATE CARTAS_USUARIO SET cantidad = ? WHERE userID = ? AND card_id = ?"
                self.db.execute_update(update_query, (nueva_cantidad, user_id, card_id))
            else:
                # Insertar nueva
                insert_query = """
                    INSERT INTO CARTAS_USUARIO (userID, card_id, cantidad)
                    VALUES (?, ?, 1)
                """
                self.db.execute_update(insert_query, (user_id, card_id))
            
        except Exception as e:
            logger.error(f"❌ Error agregando carta a usuario: {e}")
    
    # ========== GESTIÓN DE COLECCIÓN DEL USUARIO ==========
    
    def obtener_coleccion_usuario(self, user_id: int, coleccion: Optional[str] = None) -> List[Dict]:
        """
        Obtiene todas las cartas que posee un usuario
        
        Args:
            user_id: ID del usuario
            coleccion: Filtrar por colección (opcional)
        
        Returns:
            Lista de cartas con cantidades
        """
        try:
            if coleccion:
                query = """
                    SELECT c.*, cu.cantidad, cu.favorita
                    FROM CARTAS_USUARIO cu
                    JOIN CARTAS c ON cu.card_id = c.card_id
                    WHERE cu.userID = ? AND c.coleccion = ?
                    ORDER BY c.numero
                """
                results = self.db.execute_query(query, (user_id, coleccion))
            else:
                query = """
                    SELECT c.*, cu.cantidad, cu.favorita
                    FROM CARTAS_USUARIO cu
                    JOIN CARTAS c ON cu.card_id = c.card_id
                    WHERE cu.userID = ?
                    ORDER BY c.coleccion, c.numero
                """
                results = self.db.execute_query(query, (user_id,))
            
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo colección: {e}")
            return []
    
    def obtener_progreso_coleccion(self, user_id: int, coleccion: str) -> Dict:
        """
        Obtiene el progreso de completitud de una colección
        
        Returns:
            {
                'total': int,
                'obtenidas': int,
                'porcentaje': float,
                'faltantes': List[int]
            }
        """
        try:
            # Total de cartas en la colección
            total_query = "SELECT total_cartas FROM COLECCIONES WHERE nombre = ?"
            total_result = self.db.execute_query(total_query, (coleccion,))
            total = total_result[0]['total_cartas'] if total_result else 0
            
            # Cartas únicas obtenidas por el usuario
            obtenidas_query = """
                SELECT COUNT(DISTINCT cu.card_id) as obtenidas
                FROM CARTAS_USUARIO cu
                JOIN CARTAS c ON cu.card_id = c.card_id
                WHERE cu.userID = ? AND c.coleccion = ?
            """
            obtenidas_result = self.db.execute_query(obtenidas_query, (user_id, coleccion))
            obtenidas = obtenidas_result[0]['obtenidas'] if obtenidas_result else 0
            
            # Calcular porcentaje
            porcentaje = (obtenidas / total * 100) if total > 0 else 0
            
            # Cartas faltantes
            faltantes_query = """
                SELECT c.numero
                FROM CARTAS c
                WHERE c.coleccion = ?
                  AND c.card_id NOT IN (
                    SELECT card_id FROM CARTAS_USUARIO WHERE userID = ?
                  )
                ORDER BY c.numero
            """
            faltantes_result = self.db.execute_query(faltantes_query, (coleccion, user_id))
            faltantes = [row['numero'] for row in faltantes_result]
            
            return {
                'total': total,
                'obtenidas': obtenidas,
                'porcentaje': round(porcentaje, 2),
                'faltantes': faltantes
            }
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo progreso: {e}")
            return {'total': 0, 'obtenidas': 0, 'porcentaje': 0.0, 'faltantes': []}
    
    # ========== INTERCAMBIOS DE CARTAS ==========
    
    def crear_oferta_intercambio(self, ofertante_id: int, destinatario_id: int,
                                card_id_ofrecida: str,
                                card_id_solicitada: Optional[str] = None) -> Tuple[bool, str, Optional[int]]:
        """
        Crea una oferta de intercambio de cartas

        Returns:
            (exito, mensaje, intercambio_id)
        """
        try:
            # Verificar que el ofertante tiene la carta
            query = "SELECT cantidad FROM CARTAS_USUARIO WHERE userID = ? AND card_id = ?"
            result = self.db.execute_query(query, (ofertante_id, card_id_ofrecida))

            if not result or result[0]['cantidad'] < 1:
                return False, "No tienes esa carta", None

            # Crear oferta
            insert_query = """
                INSERT INTO INTERCAMBIOS_CARTAS (
                    ofertante_id, destinatario_id, card_id_ofrecida, card_id_solicitada
                ) VALUES (?, ?, ?, ?)
            """

            self.db.execute_update(insert_query, (
                ofertante_id,
                destinatario_id,
                card_id_ofrecida,
                card_id_solicitada
            ))

            # Obtener el ID del registro recién insertado
            id_result = self.db.execute_query("SELECT last_insert_rowid() AS id")
            intercambio_id: Optional[int] = id_result[0]['id'] if id_result else None

            logger.info(f"🔄 Oferta de intercambio creada: {intercambio_id}")

            return True, "✅ Oferta de intercambio enviada", intercambio_id

        except Exception as e:
            logger.error(f"❌ Error creando oferta: {e}")
            return False, f"Error: {str(e)}", None
    
    def aceptar_intercambio(self, intercambio_id: int, destinatario_id: int,
                          card_id_ofrecida_cambio: str) -> Tuple[bool, str]:
        """
        Acepta una oferta de intercambio
        
        Returns:
            (exito, mensaje)
        """
        try:
            # Obtener datos del intercambio
            query = "SELECT * FROM INTERCAMBIOS_CARTAS WHERE id = ? AND estado = 'pendiente'"
            result = self.db.execute_query(query, (intercambio_id,))
            
            if not result:
                return False, "Intercambio no encontrado o ya procesado"
            
            intercambio = dict(result[0])
            
            # Verificar que es el destinatario correcto
            if intercambio['destinatario_id'] != destinatario_id:
                return False, "Este intercambio no es para ti"
            
            # Verificar que el destinatario tiene la carta ofrecida
            if intercambio['card_id_solicitada']:
                # Intercambio específico
                card_necesaria = intercambio['card_id_solicitada']
                if card_id_ofrecida_cambio != card_necesaria:
                    return False, "No tienes la carta solicitada"
            else:
                # Intercambio libre
                card_necesaria = card_id_ofrecida_cambio
            
            # Verificar que tiene la carta
            check_query = "SELECT cantidad FROM CARTAS_USUARIO WHERE userID = ? AND card_id = ?"
            check_result = self.db.execute_query(check_query, (destinatario_id, card_necesaria))
            
            if not check_result or check_result[0]['cantidad'] < 1:
                return False, "No tienes esa carta"
            
            # REALIZAR INTERCAMBIO
            # Transferir carta del ofertante al destinatario
            self._transferir_carta(
                intercambio['ofertante_id'],
                destinatario_id,
                intercambio['card_id_ofrecida']
            )
            
            # Transferir carta del destinatario al ofertante
            self._transferir_carta(
                destinatario_id,
                intercambio['ofertante_id'],
                card_necesaria
            )
            
            # Marcar como completado
            update_query = """
                UPDATE INTERCAMBIOS_CARTAS 
                SET estado = 'aceptado', fecha_resolucion = CURRENT_TIMESTAMP
                WHERE id = ?
            """
            self.db.execute_update(update_query, (intercambio_id,))
            
            logger.info(f"✅ Intercambio {intercambio_id} completado")
            
            return True, "✅ ¡Intercambio completado!"
            
        except Exception as e:
            logger.error(f"❌ Error aceptando intercambio: {e}")
            return False, f"Error: {str(e)}"
    
    def _transferir_carta(self, from_user: int, to_user: int, card_id: str):
        """Transfiere una carta entre usuarios"""
        # Restar del usuario origen
        query_from = "UPDATE CARTAS_USUARIO SET cantidad = cantidad - 1 WHERE userID = ? AND card_id = ?"
        self.db.execute_update(query_from, (from_user, card_id))
        
        # Eliminar si cantidad llega a 0
        delete_query = "DELETE FROM CARTAS_USUARIO WHERE userID = ? AND card_id = ? AND cantidad <= 0"
        self.db.execute_update(delete_query, (from_user, card_id))
        
        # Agregar al usuario destino
        self._agregar_carta_usuario(to_user, card_id)


# Instancia global
cartas_service = CartasService()
