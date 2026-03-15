# -*- coding: utf-8 -*-
"""
Servicio de Usuarios
Contiene la lógica de negocio relacionada con usuarios
"""

from typing import Optional, Dict, Any
from datetime import date
import logging

from database import db_manager

logger = logging.getLogger(__name__)


class UserService:
    """Servicio para manejar operaciones de usuarios"""

    def __init__(self):
        self.db = db_manager

    def register_user(self, user_id: int, username: str, nombre: str,
                      clase: str, idol: Optional[str] = None) -> bool:
        """
        Registra un nuevo usuario

        Args:
            user_id: ID de Telegram
            username: @username
            nombre: Nombre del usuario
            clase: 'idol' o 'cliente'
            idol: Idol asignado (opcional)

        Returns:
            True si se registró correctamente
        """
        if self.db.user_exists(user_id):
            logger.warning(f"Usuario {user_id} ya existe")
            return False

        return self.db.insert_user(user_id, username, nombre, clase, idol)

    def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Obtiene información completa de un usuario

        Args:
            user_id: ID del usuario (SIEMPRE usar userID, nunca username)

        Returns:
            Diccionario con la información o None
        """
        return self.db.get_profile(user_id)

    def update_user_field(self, user_id: int, field: str, value: Any) -> bool:
        """
        Actualiza un campo específico del usuario

        Args:
            user_id: ID del usuario
            field: Campo a actualizar
            value: Nuevo valor

        Returns:
            True si se actualizó correctamente
        """
        return self.db.update_field(field, value, 'userID', user_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Sincronización automática de datos de perfil
    # ─────────────────────────────────────────────────────────────────────────
    def sync_user_data(self, user_id: int, username: Optional[str],
                       nombre: str) -> bool:
        """
        Compara los datos actuales de Telegram con los guardados en la BD
        y actualiza SOLO los campos que cambiaron.

        Se llama en cada mensaje del usuario registrado para mantener
        siempre actualizados el username y el nombre sin importar si el
        usuario los cambió en Telegram.

        La clave de búsqueda es SIEMPRE el userID — nunca el username.

        Args:
            user_id:  ID inmutable de Telegram.
            username: @username actual (puede ser None si el usuario no tiene).
            nombre:   Nombre de pila actual (first_name [+ last_name]).

        Returns:
            True si se actualizó algún campo, False si ya estaban en sync.
        """
        try:
            user = self.db.get_user(user_id)
            if not user:
                return False  # No registrado — nada que sincronizar

            cambios: Dict[str, Any] = {}

            # Normalizar username (puede llegar None desde Telegram)
            username_actual = username or ""
            username_guardado = user.get("nombre_usuario") or ""

            if username_guardado != username_actual:
                cambios["nombre_usuario"] = username_actual

            nombre_guardado = user.get("nombre") or ""
            if nombre_guardado != nombre:
                cambios["nombre"] = nombre

            if not cambios:
                return False  # Sin cambios — salir rápido

            # Construir UPDATE dinámico solo con los campos que cambiaron
            sets = ", ".join(f"{col} = ?" for col in cambios)
            valores = tuple(cambios.values()) + (user_id,)
            self.db.execute_update(f"UPDATE USUARIOS SET {sets} WHERE userID = ?", valores)
            logger.info(
                f"[SYNC] Usuario {user_id} — actualizados: {list(cambios.keys())}"
            )
            return True

        except Exception as e:
            logger.error(f"[SYNC] Error sincronizando datos de {user_id}: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Búsqueda por userID (método canónico)
    # ─────────────────────────────────────────────────────────────────────────
    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """
        Obtiene un usuario por su userID (clave primaria e inmutable).
        Usar SIEMPRE este método en lugar de get_user_by_username.
        """
        return self.db.get_user(user_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Búsqueda por username — solo como FALLBACK cuando no hay userID
    # ─────────────────────────────────────────────────────────────────────────
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """
        Obtiene un usuario por username.

        ⚠️  USAR SOLO COMO ÚLTIMO RECURSO cuando no hay otra forma de
        obtener el userID (p.ej. mención de texto sin entity de Telegram).
        El username puede cambiar en cualquier momento; el userID nunca.

        Args:
            username: Username del usuario (con o sin @)

        Returns:
            Diccionario con información del usuario o None
        """
        try:
            username = username.lstrip('@')
            query = "SELECT * FROM USUARIOS WHERE nombre_usuario = ?"
            result = self.db.execute_query(query, (username,))
            return dict(result[0]) if result else None
        except Exception as e:
            logger.error(f"❌ Error obteniendo usuario por username: {e}")
            return None

    def check_user_data(self, user_id: int, username: str, nombre: str) -> bool:
        """
        Verifica si los datos del usuario coinciden con la BD.
        Preferir sync_user_data() que además corrige las diferencias.
        """
        user = self.db.get_user(user_id)
        if not user:
            return False
        if user.get('nombre_usuario') != username:
            return False
        if user.get('nombre') != nombre:
            return False
        return True

    def get_all_usernames(self) -> list:
        """Obtiene todos los usernames registrados"""
        query = "SELECT nombre_usuario FROM USUARIOS"
        results = self.db.execute_query(query)
        return [row['nombre_usuario'] for row in results]

    def set_in_queue(self, user_id: int, in_queue: bool) -> bool:
        value = 1 if in_queue else 0
        return self.db.update_field('encola', value, 'userID', user_id)

    def set_in_role(self, user_id: int, in_role: bool) -> bool:
        value = 1 if in_role else 0
        return self.db.update_field('enrol', value, 'userID', user_id)

    def ban_user(self, user_id: int, motivo: str = "No especificado") -> bool:
        return self.db.move_to_exmembers(user_id, motivo)

    def unban_user(self, user_id: int) -> bool:
        return self.db.restore_from_exmembers(user_id)


# Instancia global del servicio
user_service = UserService()