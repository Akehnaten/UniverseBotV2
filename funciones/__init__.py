# -*- coding: utf-8 -*-
"""
Funciones y Servicios
"""

from funciones.user_service import UserService
from funciones.economy_service import EconomyService
from funciones.role_service import RoleService

# Instancias globales
user_service = UserService()
economy_service = EconomyService()
role_service = RoleService()

__all__ = [
    'user_service',
    'economy_service',
    'role_service',  # ✅ AGREGAR
    'UserService',
    'EconomyService',
    'RoleService',   # ✅ AGREGAR
]
