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


# ── Helpers de sistema de frecuentes ─────────────────────────────────────────

def _crear_tabla_frecuentes() -> None:
    """Crea ROL_FRECUENTES si no existe. Idempotente."""
    try:
        db_manager.execute_update(
            """CREATE TABLE IF NOT EXISTS ROL_FRECUENTES (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                idol_id    INTEGER NOT NULL,
                cliente_id INTEGER NOT NULL,
                mes        TEXT    NOT NULL,
                cantidad   INTEGER DEFAULT 0,
                UNIQUE(idol_id, cliente_id, mes)
            )"""
        )
    except Exception as e:
        logger.warning(f"[FRECUENTES] Error creando tabla: {e}")

_crear_tabla_frecuentes()


def get_frecuencia(idol_id: int, cliente_id: int) -> int:
    """
    Devuelve cuántas veces válidas ha roleado idol con cliente este mes.
    (Antes de contar el rol actual.)
    """
    mes = datetime.now().strftime("%Y-%m")
    try:
        rows = db_manager.execute_query(
            "SELECT cantidad FROM ROL_FRECUENTES WHERE idol_id=? AND cliente_id=? AND mes=?",
            (idol_id, cliente_id, mes),
        ) or []
        return int(rows[0]["cantidad"]) if rows else 0
    except Exception:
        return 0


def registrar_frecuencia(idol_id: int, cliente_id: int) -> int:
    """
    Incrementa el contador de frecuencia entre idol y cliente para el mes actual.
    Devuelve la cantidad NUEVA (ya incrementada).
    """
    mes = datetime.now().strftime("%Y-%m")
    try:
        db_manager.execute_update(
            """INSERT INTO ROL_FRECUENTES (idol_id, cliente_id, mes, cantidad)
               VALUES (?, ?, ?, 1)
               ON CONFLICT(idol_id, cliente_id, mes) DO UPDATE SET
               cantidad = cantidad + 1""",
            (idol_id, cliente_id, mes),
        )
        rows = db_manager.execute_query(
            "SELECT cantidad FROM ROL_FRECUENTES WHERE idol_id=? AND cliente_id=? AND mes=?",
            (idol_id, cliente_id, mes),
        ) or []
        return int(rows[0]["cantidad"]) if rows else 1
    except Exception as e:
        logger.warning(f"[FRECUENTES] Error registrando frecuencia: {e}")
        return 1


def calcular_multiplicador_frecuentes(cantidad_previa: int) -> float:
    """
    Devuelve el multiplicador de puntos según las veces previas que rolearon juntos.
      0 veces previas → 1.0  (sin penalización)
      1 vez previa    → 0.8  (-20%)
      2 veces previas → 0.6  (-40%)
      3 veces previas → 0.4  (-60%)
      4+ veces previas→ 0.2  (-80%, tope)
    """
    penalizacion = min(0.8, cantidad_previa * 0.2)
    return round(1.0 - penalizacion, 2)


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
        clientes_ids:    list = None,
        cazadora:        bool = False,
    ) -> tuple[bool, int, dict]:
        """
        Finaliza un rol y calcula los puntos del idol.

        Args:
            rol_id:          ID del rol.
            tiempo_segundos: Duración en segundos.
            validez:         'valido' o 'no valido'.
            clientes_ids:    Lista de IDs de clientes del rol.
            cazadora:        True si aplica bonus cazadora (x2 puntos).

        Returns:
            (is_valid, puntos_ganados, info_sistemas)
            info_sistemas contiene datos de frecuentes y cazadora para mostrar.
        """
        query = "SELECT idolID, clienteID FROM ROLES WHERE rolID = ?"
        results = self.db.execute_query(query, (rol_id,))

        if not results:
            logger.error(f"Rol {rol_id} no encontrado")
            return False, 0, {}

        rol_data = results[0]
        idol_id  = rol_data["idolID"]

        final  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tiempo = self._format_time(tiempo_segundos)

        is_valid = self.db.close_role(rol_id, final, tiempo, validez)

        puntos_ganados = 0
        info_sistemas  = {}

        if is_valid:
            _, puntos_base = self.db.calculate_points(idol_id, tiempo_segundos)

            # ── Sistema cazadora ──────────────────────────────────────────────
            puntos_cazadora = puntos_base
            if cazadora:
                puntos_cazadora = puntos_base * 2
                info_sistemas["cazadora"] = {
                    "activo":       True,
                    "puntos_bonus": puntos_base,
                }
                logger.info(f"[ROL] #{rol_id} bonus cazadora x2 → {puntos_cazadora} pts")

            # ── Sistema frecuentes (penaliza puntos, no EXP ni cosmos) ────────
            mult_frecuentes = 1.0
            clientes = clientes_ids or []
            if clientes:
                # Tomar el cliente principal (primero de la lista)
                cliente_id     = clientes[0]
                cantidad_previa = get_frecuencia(idol_id, cliente_id)
                mult_frecuentes = calcular_multiplicador_frecuentes(cantidad_previa)

                # Registrar este rol en el historial
                for cid in clientes:
                    registrar_frecuencia(idol_id, cid)

                if cantidad_previa > 0:
                    penalizacion_pct = int(cantidad_previa * 20)
                    info_sistemas["frecuentes"] = {
                        "cantidad_previa": cantidad_previa,
                        "penalizacion_pct": min(80, penalizacion_pct),
                        "multiplicador":   mult_frecuentes,
                    }

            puntos_ganados = max(1, round(puntos_cazadora * mult_frecuentes))

            logger.info(
                "[ROL] #%s finalizado — base=%s cazadora=%s mult_freq=%.2f final=%s",
                rol_id, puntos_base, cazadora, mult_frecuentes, puntos_ganados,
            )
        else:
            logger.info("[ROL] #%s finalizado como NO VÁLIDO", rol_id)

        user_service.set_in_role(idol_id, False)
        return is_valid, puntos_ganados, info_sistemas
    
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
