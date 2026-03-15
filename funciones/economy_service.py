"""
Servicio de Economía
Maneja todo lo relacionado con cosmos (wallet) y transacciones del bot
"""

from typing import Optional
import logging

from database import db_manager

logger = logging.getLogger(__name__)


class EconomyService:
    """Servicio para manejar la economía del bot"""
    
    def __init__(self):
        self.db = db_manager
    
    def get_balance(self, user_id: int) -> int:
        """
        Obtiene el saldo de un usuario
        
        Args:
            user_id: ID del usuario
        
        Returns:
            Cantidad de Cosmos
        """
        return self.db.get_wallet_balance(user_id)
    
    def add_credits(self, user_id: int, amount: int, reason: str = "") -> bool:
        """
        Añade Cosmos a un usuario
        
        Args:
            user_id: ID del usuario
            amount: Cantidad a añadir
            reason: Razón de la transacción (para logs)
        
        Returns:
            True si se añadió correctamente
        """
        if amount <= 0:
            logger.warning(f"Intento de añadir cantidad inválida: {amount}")
            return False
        
        success = self.db.update_wallet(user_id, amount, 'add')
        
        if success:
            logger.info(f"✅ {amount} Cosmos añadidos a {user_id}. Razón: {reason}")
        
        return success
    
    def subtract_credits(self, user_id: int, amount: int, reason: str = "") -> bool:
        """
        Resta Cosmos a un usuario
        
        Args:
            user_id: ID del usuario
            amount: Cantidad a restar
            reason: Razón de la transacción (para logs)
        
        Returns:
            True si se restó correctamente
        """
        if amount <= 0:
            logger.warning(f"Intento de restar cantidad inválida: {amount}")
            return False
        
        # Verificar saldo suficiente
        balance = self.get_balance(user_id)
        if balance < amount:
            logger.warning(f"Saldo insuficiente para {user_id}: tiene {balance}, necesita {amount}")
            return False
        
        success = self.db.update_wallet(user_id, amount, 'subtract')
        
        if success:
            logger.info(f"✅ {amount} Cosmos restados de {user_id}. Razón: {reason}")
        
        return success
    
    def set_balance(self, user_id: int, amount: int, reason: str = "") -> bool:
        """
        Establece el saldo de un usuario
        
        Args:
            user_id: ID del usuario
            amount: Nueva cantidad
            reason: Razón del cambio (para logs)
        
        Returns:
            True si se estableció correctamente
        """
        if amount < 0:
            logger.warning(f"Intento de establecer cantidad negativa: {amount}")
            return False
        
        success = self.db.update_wallet(user_id, amount, 'set')
        
        if success:
            logger.info(f"✅ Saldo de {user_id} establecido a {amount}. Razón: {reason}")
        
        return success
    
    def transfer_credits(self, from_user: int, to_user: int, amount: int) -> bool:
        """
        Transfiere Cosmos entre usuarios
        
        Args:
            from_user: ID del remitente
            to_user: ID del destinatario
            amount: Cantidad a transferir
        
        Returns:
            True si se transfirió correctamente
        """
        if amount <= 0:
            logger.warning(f"Intento de transferir cantidad inválida: {amount}")
            return False
        
        # Verificar saldo del remitente
        if not self.has_sufficient_balance(from_user, amount):
            logger.warning(f"Saldo insuficiente para transferencia de {from_user}")
            return False
        
        # Realizar transferencia
        if self.subtract_credits(from_user, amount, f"Transferencia a {to_user}"):
            if self.add_credits(to_user, amount, f"Transferencia de {from_user}"):
                logger.info(f"✅ Transferencia exitosa: {from_user} → {to_user} ({amount} Cosmos)")
                return True
            else:
                # Revertir si falla la adición
                self.add_credits(from_user, amount, "Reversión de transferencia fallida")
                logger.error(f"❌ Error en transferencia, revertida")
                return False
        
        return False
    
    def has_sufficient_balance(self, user_id: int, required_amount: int) -> bool:
        """
        Verifica si un usuario tiene saldo suficiente
        
        Args:
            user_id: ID del usuario
            required_amount: Cantidad requerida
        
        Returns:
            True si tiene saldo suficiente
        """
        balance = self.get_balance(user_id)
        return balance >= required_amount
    
    def get_leaderboard(self, limit: int = 10) -> str:
        """
        Obtiene el ranking de usuarios por Cosmos
        
        Args:
            limit: Número de usuarios a mostrar
        
        Returns:
            Texto formateado del ranking
        """
        return self.db.get_leaderboard(limit)
    
    def get_user_stats_text(self, username: str) -> str:
        """
        Obtiene las estadísticas de un usuario en formato texto
        
        Args:
            username: Username del usuario
        
        Returns:
            Texto formateado con estadísticas
        """
        return self.db.get_user_stats(username)


# Instancia global del servicio

    # Alias para compatibilidad
    def remove_credits(self, user_id: int, amount: int, reason: str = "") -> bool:
        """Alias de subtract_credits para compatibilidad"""
        return self.subtract_credits(user_id, amount, reason)


# Instancia global del servicio
economy_service = EconomyService()
