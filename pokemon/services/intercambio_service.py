from typing import List, Dict, Optional, Tuple
"""
Servicio de Intercambios Pokémon
Sistema completo de trades entre jugadores
"""

import time
import logging
from typing import Optional, Dict, Tuple
from database import db_manager

logger = logging.getLogger(__name__)


class IntercambioService:
    """Servicio para gestionar intercambios de Pokémon"""
    
    def __init__(self):
        self.db = db_manager
        self.intercambios_pendientes = {}  # {intercambio_id: datos}
    
    def crear_oferta(self, user_id: int, pokemon_id: int, 
                    destinatario_id: int, pokemon_solicitado_id: Optional[int] = None) -> Tuple[bool, str, Optional[str]]:
        """
        Crea una oferta de intercambio
        
        Args:
            user_id: ID del usuario que ofrece
            pokemon_id: ID del Pokémon ofrecido
            destinatario_id: ID del usuario destinatario
            pokemon_solicitado_id: ID específico del Pokémon solicitado (opcional)
        
        Returns:
            (exito, mensaje, intercambio_id)
        """
        try:
            from pokemon.services import pokemon_service
            
            # Verificar que el Pokémon pertenece al usuario
            pokemon = pokemon_service.obtener_pokemon(pokemon_id)
            
            if not pokemon or pokemon.usuario_id != user_id:
                return False, "Este Pokémon no te pertenece", None
            
            # Verificar que el destinatario existe
            from funciones import user_service
            if not user_service.get_user_info(destinatario_id):
                return False, "Usuario destinatario no encontrado", None
            
            # Crear ID de intercambio
            intercambio_id = f"trade_{user_id}_{destinatario_id}_{int(time.time())}"
            
            # Crear oferta
            oferta = {
                'id': intercambio_id,
                'ofertante_id': user_id,
                'destinatario_id': destinatario_id,
                'pokemon_ofrecido_id': pokemon_id,
                'pokemon_solicitado_id': pokemon_solicitado_id,
                'estado': 'pendiente',
                'timestamp': time.time()
            }
            
            # Guardar en BD
            query = """
                INSERT INTO INTERCAMBIOS (
                    intercambio_id, ofertante_id, destinatario_id,
                    pokemon_ofrecido_id, pokemon_solicitado_id, estado, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            
            self.db.execute_update(query, (
                intercambio_id,
                user_id,
                destinatario_id,
                pokemon_id,
                pokemon_solicitado_id,
                'pendiente',
                oferta['timestamp']
            ))
            
            # Guardar en memoria
            self.intercambios_pendientes[intercambio_id] = oferta
            
            from pokemon.services import pokedex_service
            nombre_pokemon = pokedex_service.obtener_nombre(pokemon.pokemonID)
            
            mensaje = f"✅ Oferta de intercambio enviada!\n" \
                     f"Ofreciste: {nombre_pokemon} Nv.{pokemon.nivel}"
            
            logger.info(f"🔄 Intercambio {intercambio_id} creado: {user_id} → {destinatario_id}")
            
            return True, mensaje, intercambio_id
            
        except Exception as e:
            logger.error(f"❌ Error creando oferta: {e}")
            return False, f"Error: {str(e)}", None
    
    def obtener_ofertas_recibidas(self, user_id: int) -> list:
        """
        Obtiene las ofertas de intercambio recibidas
        
        Returns:
            Lista de ofertas pendientes
        """
        try:
            query = """
                SELECT * FROM INTERCAMBIOS 
                WHERE destinatario_id = ? AND estado = 'pendiente'
                ORDER BY timestamp DESC
            """
            
            results = self.db.execute_query(query, (user_id,))
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo ofertas: {e}")
            return []
    
    def obtener_ofertas_enviadas(self, user_id: int) -> list:
        """
        Obtiene las ofertas de intercambio enviadas
        
        Returns:
            Lista de ofertas pendientes
        """
        try:
            query = """
                SELECT * FROM INTERCAMBIOS 
                WHERE ofertante_id = ? AND estado = 'pendiente'
                ORDER BY timestamp DESC
            """
            
            results = self.db.execute_query(query, (user_id,))
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo ofertas enviadas: {e}")
            return []
    
    def aceptar_intercambio(
        self,
        intercambio_id: str,
        destinatario_id: int,
        pokemon_id: int,
        bot=None,
    ) -> "Tuple[bool, str, list]":
        """
        Acepta una oferta de intercambio Pokémon.

        Args:
            intercambio_id:  ID del intercambio a aceptar.
            destinatario_id: ID del usuario que acepta (destinatario).
            pokemon_id:      ID del Pokémon que el destinatario ofrece a cambio.
            bot:             Instancia del bot Telegram (opcional).
                             Si se pasa, intenta enviar DM a ambos usuarios.

        Returns:
            (exito, mensaje, ids_sin_dm)
            • exito       — bool, True si el intercambio se completó.
            • mensaje     — str, resumen del resultado para mostrar al destinatario.
            • ids_sin_dm  — list[int], IDs de usuarios a quienes NO se pudo enviar DM.
                            Lista vacía si los DMs llegaron (o si bot=None).
        """
        try:
            # ── Obtener y validar el intercambio ───────────────────────────
            query = "SELECT * FROM INTERCAMBIOS WHERE intercambio_id = ?"
            result = self.db.execute_query(query, (intercambio_id,))

            if not result:
                return False, "Intercambio no encontrado", []

            intercambio = dict(result[0])

            if intercambio["destinatario_id"] != destinatario_id:
                return False, "Este intercambio no es para ti", []

            if intercambio["estado"] != "pendiente":
                return False, "Este intercambio ya no está disponible", []

            # ── Validar que el Pokémon ofrecido pertenece al destinatario ──
            from pokemon.services import pokemon_service

            pokemon_cambio = pokemon_service.obtener_pokemon(pokemon_id)
            if not pokemon_cambio or pokemon_cambio.usuario_id != destinatario_id:
                return False, "Este Pokémon no te pertenece", []

            if intercambio["pokemon_solicitado_id"]:
                if pokemon_id != intercambio["pokemon_solicitado_id"]:
                    return False, "No es el Pokémon solicitado", []

            # ── Ejecutar el swap de propietarios ──────────────────────────
            pokemon_ofrecido_id = intercambio["pokemon_ofrecido_id"]
            ofertante_id        = intercambio["ofertante_id"]

            query_swap1 = "UPDATE POKEMON_USUARIO SET userID = ? WHERE id_unico = ?"
            query_swap2 = "UPDATE POKEMON_USUARIO SET userID = ? WHERE id_unico = ?"

            self.db.execute_update(query_swap1, (destinatario_id, pokemon_ofrecido_id))
            self.db.execute_update(query_swap2, (ofertante_id,    pokemon_id))

            # Marcar como completado en BD
            self.db.execute_update(
                "UPDATE INTERCAMBIOS SET estado = 'completado' WHERE intercambio_id = ?",
                (intercambio_id,),
            )

            # ── Verificar evoluciones por intercambio ─────────────────────
            # IMPORTANTE: usar verificar_evolucion_por_intercambio, NO
            # verificar_evolucion (que solo detecta nivel/amistad/piedra).
            from pokemon.services import evolucion_service, pokedex_service

            mensajes_evo: list[str] = []

            # Pokémon que ahora pertenece al destinatario
            puede_evo1, evo_data1 = (
                evolucion_service.verificar_evolucion_por_intercambio(pokemon_ofrecido_id)
            )
            if puede_evo1 and evo_data1:
                exito_evo1, msg_evo1, _ = evolucion_service.evolucionar_pokemon(
                    pokemon_ofrecido_id,
                    forzar=True,
                    evo_data_override=evo_data1,
                )
                if exito_evo1:
                    mensajes_evo.append(msg_evo1)

            # Pokémon que ahora pertenece al ofertante
            puede_evo2, evo_data2 = (
                evolucion_service.verificar_evolucion_por_intercambio(pokemon_id)
            )
            if puede_evo2 and evo_data2:
                exito_evo2, msg_evo2, _ = evolucion_service.evolucionar_pokemon(
                    pokemon_id,
                    forzar=True,
                    evo_data_override=evo_data2,
                )
                if exito_evo2:
                    mensajes_evo.append(msg_evo2)

            # ── Construir mensaje de resultado ─────────────────────────────
            pokemon_ofrecido = pokemon_service.obtener_pokemon(pokemon_ofrecido_id)
            if pokemon_ofrecido is not None:
                poke_especie    = pokemon_ofrecido.pokemonID
                poke_nivel      = pokemon_ofrecido.nivel
                nombre_recibido = pokedex_service.obtener_nombre(poke_especie)
            else:
                nombre_recibido = "Pokémon"
                poke_nivel      = 1

            mensaje = (
                f"✅ ¡Intercambio completado!\n"
                f"Recibiste: {nombre_recibido} Nv.{poke_nivel}"
            )
            if mensajes_evo:
                mensaje += "\n\n" + "\n".join(mensajes_evo)

            logger.info(f"✅ Intercambio {intercambio_id} completado")

            # Limpiar de pendientes en memoria
            if intercambio_id in self.intercambios_pendientes:
                del self.intercambios_pendientes[intercambio_id]

            # ── Notificar por DM a ambos usuarios (si se pasó bot) ─────────
            ids_sin_dm: list[int] = []

            if bot is not None:
                # Obtener nombre del Pokémon que recibe el ofertante
                pokemon_ofertante = pokemon_service.obtener_pokemon(pokemon_id)
                if pokemon_ofertante:
                    nombre_para_ofertante = pokedex_service.obtener_nombre(
                        pokemon_ofertante.pokemonID
                    )
                    nivel_para_ofertante = pokemon_ofertante.nivel
                else:
                    nombre_para_ofertante = "Pokémon"
                    nivel_para_ofertante  = 1

                msg_ofertante = (
                    f"🔄 ¡Tu intercambio fue aceptado!\n"
                    f"Recibiste: {nombre_para_ofertante} Nv.{nivel_para_ofertante}"
                )
                if mensajes_evo:
                    msg_ofertante += "\n\n" + "\n".join(mensajes_evo)

                dm_ofertante_ok    = self._enviar_dm_intercambio(bot, ofertante_id,    msg_ofertante)
                dm_destinatario_ok = self._enviar_dm_intercambio(bot, destinatario_id, mensaje)

                if not dm_ofertante_ok:
                    ids_sin_dm.append(ofertante_id)
                if not dm_destinatario_ok:
                    ids_sin_dm.append(destinatario_id)

                # Si al destinatario (quien acepta ahora mismo) no le llegó el DM,
                # el mensaje de retorno igual se mostrará en el chat activo, no
                # es necesario incluirlo en ids_sin_dm para ese flujo.

            return True, mensaje, ids_sin_dm

        except Exception as e:
            logger.error(f"❌ Error aceptando intercambio: {e}", exc_info=True)
            return False, f"Error: {str(e)}", []
    
    # ─────────────────────────────────────────────────────────────────────────
    # NUEVO método helper — agregar DESPUÉS de aceptar_intercambio
    # ─────────────────────────────────────────────────────────────────────────

    def _enviar_dm_intercambio(self, bot, user_id: int, mensaje: str) -> bool:
        """
        Intenta enviar un DM al usuario con el resultado del intercambio.

        Returns:
            True  si el mensaje llegó correctamente.
            False si Telegram rechazó el envío (el usuario no inició chat con el bot).
        """
        try:
            bot.send_message(user_id, mensaje, parse_mode="HTML")
            return True
        except Exception as e:
            logger.warning(
                f"[INTERCAMBIO] No se pudo enviar DM a user {user_id}: {e}"
            )
            return False


    def rechazar_intercambio(self, intercambio_id: str, user_id: int) -> Tuple[bool, str]:
        """
        Rechaza una oferta de intercambio
        
        Returns:
            (exito, mensaje)
        """
        try:
            # Verificar que existe
            query = "SELECT * FROM INTERCAMBIOS WHERE intercambio_id = ?"
            result = self.db.execute_query(query, (intercambio_id,))
            
            if not result:
                return False, "Intercambio no encontrado"
            
            intercambio = dict(result[0])
            
            # Verificar que es el destinatario o el ofertante
            if intercambio['destinatario_id'] != user_id and intercambio['ofertante_id'] != user_id:
                return False, "No tienes permiso para rechazar este intercambio"
            
            # Marcar como rechazado
            query_update = "UPDATE INTERCAMBIOS SET estado = 'rechazado' WHERE intercambio_id = ?"
            self.db.execute_update(query_update, (intercambio_id,))
            
            # Limpiar de pendientes
            if intercambio_id in self.intercambios_pendientes:
                del self.intercambios_pendientes[intercambio_id]
            
            logger.info(f"❌ Intercambio {intercambio_id} rechazado por {user_id}")
            
            return True, "Intercambio rechazado"
            
        except Exception as e:
            logger.error(f"❌ Error rechazando intercambio: {e}")
            return False, f"Error: {str(e)}"
    
    def cancelar_intercambio(self, intercambio_id: str, user_id: int) -> Tuple[bool, str]:
        """
        Cancela una oferta de intercambio (solo el ofertante)
        
        Returns:
            (exito, mensaje)
        """
        try:
            query = "SELECT * FROM INTERCAMBIOS WHERE intercambio_id = ?"
            result = self.db.execute_query(query, (intercambio_id,))
            
            if not result:
                return False, "Intercambio no encontrado"
            
            intercambio = dict(result[0])
            
            # Verificar que es el ofertante
            if intercambio['ofertante_id'] != user_id:
                return False, "Solo el ofertante puede cancelar"
            
            # Marcar como cancelado
            query_update = "UPDATE INTERCAMBIOS SET estado = 'cancelado' WHERE intercambio_id = ?"
            self.db.execute_update(query_update, (intercambio_id,))
            
            # Limpiar de pendientes
            if intercambio_id in self.intercambios_pendientes:
                del self.intercambios_pendientes[intercambio_id]
            
            logger.info(f"🚫 Intercambio {intercambio_id} cancelado por {user_id}")
            
            return True, "Intercambio cancelado"
            
        except Exception as e:
            logger.error(f"❌ Error cancelando intercambio: {e}")
            return False, f"Error: {str(e)}"
    
    def obtener_historial(self, user_id: int, limite: int = 10) -> list:
        """
        Obtiene el historial de intercambios del usuario
        
        Returns:
            Lista de intercambios (completados, rechazados, cancelados)
        """
        try:
            query = """
                SELECT * FROM INTERCAMBIOS 
                WHERE (ofertante_id = ? OR destinatario_id = ?) 
                  AND estado != 'pendiente'
                ORDER BY timestamp DESC
                LIMIT ?
            """
            
            results = self.db.execute_query(query, (user_id, user_id, limite))
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo historial: {e}")
            return []


# Instancia global
intercambio_service = IntercambioService()
