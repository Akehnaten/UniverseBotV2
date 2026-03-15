"""
Servicio de Roles
Maneja la lógica de negocio de roles entre idols y clientes
"""

from typing import Optional, List, Tuple
from datetime import datetime, timedelta
import logging

from database import db_manager
from funciones.economy_service import economy_service
from funciones.user_service import user_service

logger = logging.getLogger(__name__)


class RoleService:
    """Servicio para manejar roles"""
    
    def __init__(self):
        self.db = db_manager
    
    def start_role(self, idol_id: int, cliente_id: str) -> int:
        """
        Inicia un nuevo rol
        
        Args:
            idol_id: ID del idol
            cliente_id: ID del cliente
        
        Returns:
            ID del rol creado
        """
        # Marcar usuarios en rol
        user_service.set_in_role(idol_id, True)
        
        # Crear el rol en la BD
        rol_id = self.db.create_role(idol_id, cliente_id)
        
        logger.info(f"✅ Rol iniciado: ID {rol_id} (Idol: {idol_id}, Cliente: {cliente_id})")
        
        return rol_id
    
    def end_role(
        self,
        rol_id:          int,
        tiempo_segundos: int,
        validez:         str = "valido",
    ) -> tuple[bool, int]:
        """
        Finaliza un rol y calcula los puntos del idol.

        Args:
            rol_id:          ID del rol.
            tiempo_segundos: Duración en segundos.
            validez:         ``'valido'`` o ``'no valido'``.

        Returns:
            (is_valid, puntos_ganados)  — puntos_ganados es 0 si el rol no es válido.
        """
        # Obtener datos del rol
        query = "SELECT idolID, clienteID FROM ROLES WHERE rolID = ?"
        results = self.db.execute_query(query, (rol_id,))
        
        if not results:
            logger.error(f"Rol {rol_id} no encontrado")
            return False,0
        
        rol_data = results[0]
        idol_id = rol_data['idolID']
        
        # Calcular tiempo formateado
        final = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tiempo = self._format_time(tiempo_segundos)
        
        # Cerrar el rol
        is_valid = self.db.close_role(rol_id, final, tiempo, validez)
        
        # Si es válido, calcular y asignar puntos
        puntos_ganados = 0
        if is_valid:
            _, puntos_ganados = self.db.calculate_points(idol_id, tiempo_segundos)
            logger.info(
                "✅ Rol %s finalizado. Puntos ganados por idol %s: %s",
                rol_id, idol_id, puntos_ganados,
            )
        else:
            logger.info("⚠️ Rol %s finalizado como NO VÁLIDO", rol_id)

        # Quitar marca de "en rol"
        user_service.set_in_role(idol_id, False)

        return is_valid, puntos_ganados
    
    def get_queue(self) -> List[Tuple[str, str]]:
        """
        Obtiene la cola de espera
        
        Returns:
            Lista de tuplas (idol, nombre_usuario)
        """
        return self.db.get_queue()
    
    def add_to_queue(self, user_id: int) -> bool:
        """
        Añade un usuario a la cola
        
        Args:
            user_id: ID del usuario
        
        Returns:
            True si se añadió correctamente
        """
        return user_service.set_in_queue(user_id, True)
    
    def remove_from_queue(self, user_id: int) -> bool:
        """
        Quita un usuario de la cola
        
        Args:
            user_id: ID del usuario
        
        Returns:
            True si se quitó correctamente
        """
        return user_service.set_in_queue(user_id, False)
    
    def get_active_roles_count(self, user_id: int, clase: str) -> int:
        """
        Obtiene el número de roles activos de un usuario
        
        Args:
            user_id: ID del usuario
            clase: 'idol' o 'cliente'
        
        Returns:
            Número de roles activos
        """
        return self.db.get_active_roles(user_id, clase)
    
    def can_start_role(self, idol_id: int, cliente_id: int) -> Tuple[bool, str]:
        """
        Verifica si se puede iniciar un rol
        
        Args:
            idol_id: ID del idol
            cliente_id: ID del cliente
        
        Returns:
            (puede_iniciar, mensaje_error)
        """
        # Verificar que ambos usuarios existen
        if not self.db.user_exists(idol_id):
            return False, "El idol no está registrado"
        
        if not self.db.user_exists(cliente_id):
            return False, "El cliente no está registrado"
        
        # Verificar que el idol no está en otro rol
        idol_roles = self.get_active_roles_count(idol_id, 'idol')
        if idol_roles > 0:
            return False, "El idol ya está en un rol activo"
        
        # Verificar que el cliente no está en otro rol
        cliente_roles = self.get_active_roles_count(cliente_id, 'cliente')
        if cliente_roles > 0:
            return False, "El cliente ya está en un rol activo"
        
        return True, ""
    
    def _format_time(self, seconds: int) -> str:
        """
        Formatea segundos a HH:MM:SS
        
        Args:
            seconds: Segundos a formatear
        
        Returns:
            String en formato HH:MM:SS
        """
        hours = seconds // 3600
        remaining = seconds % 3600
        minutes = remaining // 60
        secs = remaining % 60
        
        return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d}"


# Instancia global del servicio
role_service = RoleService()
