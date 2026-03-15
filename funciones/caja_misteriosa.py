# -*- coding: utf-8 -*-
"""
Sistema de Caja Misteriosa Interactivo
Aparece con botón "Abrir Cofre" y recompensas aleatorias
"""

import random
import time
from typing import Dict, Optional
from telebot import types
from funciones import economy_service
import logging

logger = logging.getLogger(__name__)


class CajaMisteriosa:
    """Gestor de cajas misteriosas"""
    
    def __init__(self):
        self.cajas_activas = {}  # {message_id: datos_caja}
        self.tiempo_expiracion = 60  # 60 segundos para abrir
    
    def generar_caja(self, user_id: int, chat_id: int, bot, thread_id: Optional[int] = None) -> bool:
        """
        Genera una caja misteriosa con botón interactivo
        
        Returns:
            True si se generó la caja
        """
        try:
            # Crear botón de abrir
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "🎁 Abrir Cofre 🎁",
                callback_data=f"opencaja_{user_id}"
            ))
            
            # Enviar mensaje con botón
            kwargs = {"reply_markup": markup, "parse_mode": "HTML"}
            if thread_id:
                kwargs["message_thread_id"] = thread_id
            mensaje = bot.send_message(
                chat_id,
                "🎁 <b>¡Un cofre misterioso ha aparecido!</b> 🎁\n\n"
                "✨ Contiene una recompensa especial...\n"
                "⏰ Tienes 60 segundos para abrirlo",
                **kwargs
            )
            
            # Guardar datos de la caja
            self.cajas_activas[mensaje.message_id] = {
                'user_id':   user_id,
                'chat_id':   chat_id,
                'thread_id': thread_id,
                'timestamp': time.time(),
                'abierta':   False,
            }
            
            logger.info(f"[MYSTERY] Caja generada para usuario {user_id}")
            
            # Auto-eliminar después de 60 segundos si no se abre
            import threading
            threading.Timer(
                self.tiempo_expiracion, 
                self._expirar_caja, 
                args=[mensaje.message_id, bot]
            ).start()
            
            return True
            
        except Exception as e:
            logger.error(f"[MYSTERY] Error generando caja: {e}")
            return False
    
    def abrir_caja(self, call, bot) -> Optional[Dict]:
        """
        Abre una caja misteriosa y da la recompensa
        
        Returns:
            Dict con recompensas o None si falló
        """
        try:
            # Extraer datos del callback
            _, user_id_str = call.data.split('_')
            user_id_clickeador = call.from_user.id
            user_id_original = int(user_id_str)
            
            message_id = call.message.message_id
            
            # Verificar que la caja existe
            if message_id not in self.cajas_activas:
                bot.answer_callback_query(
                    call.id,
                    "❌ Este cofre ya no está disponible",
                    show_alert=True
                )
                return None
            
            caja = self.cajas_activas[message_id]
            
            # Verificar que no fue abierta ya
            if caja['abierta']:
                bot.answer_callback_query(
                    call.id,
                    "❌ Este cofre ya fue abierto",
                    show_alert=True
                )
                return None
            
            # Cualquier usuario puede abrir el cofre — el user_id_original
            # solo se usa como semilla del callback_data, no como restricción.
            # La recompensa va al usuario que hace click.
            
            # Marcar como abierta
            caja['abierta'] = True
            
            # Generar recompensas
            recompensas = self._generar_recompensas()
            
            # Aplicar recompensas
            cosmos = recompensas.get('cosmos', 0)
            puntos = recompensas.get('puntos', 0)
            
            if cosmos > 0:
                economy_service.add_credits(
                    user_id_clickeador,
                    cosmos,
                    "Cofre misterioso"
                )
            
            if puntos > 0:
                from database import db_manager
                from funciones.user_experience import aplicar_experiencia_usuario
                db_manager.execute_update(
                    "UPDATE USUARIOS SET puntos = puntos + ? WHERE userID = ?",
                    (puntos, user_id_clickeador),
                )
                thread_id_caja = caja.get('thread_id')
                aplicar_experiencia_usuario(
                    user_id_clickeador, puntos,
                    bot, caja['chat_id'], thread_id_caja,
                )
            
            # Actualizar mensaje
            texto_recompensa = self._formatear_recompensa(recompensas)
            
            bot.edit_message_text(
                f"🎉 <b>¡Cofre Abierto!</b> 🎉\n\n"
                f"👤 {call.from_user.first_name}\n\n"
                f"{texto_recompensa}",
                call.message.chat.id,
                message_id,
                parse_mode="HTML"
            )
            
            bot.answer_callback_query(
                call.id,
                f"¡Obtuviste las recompensas!",
                show_alert=True
            )
            
            logger.info(
                f"[MYSTERY] Usuario {user_id_original} abrió cofre: "
                f"{cosmos} cosmos, {puntos} puntos"
            )
            
            # Limpiar caja
            del self.cajas_activas[message_id]
            
            return recompensas
            
        except Exception as e:
            logger.error(f"[MYSTERY] Error abriendo caja: {e}")
            return None
    
    def _generar_recompensas(self) -> Dict:
        from config import CAJA_MISTERIOSA_REWARDS
        tipo = random.choice(['cosmos', 'puntos', 'ambos'])

        cosmos_min = CAJA_MISTERIOSA_REWARDS["cosmos_min"]
        cosmos_max = CAJA_MISTERIOSA_REWARDS["cosmos_max"]
        puntos_min = CAJA_MISTERIOSA_REWARDS["puntos_min"]
        puntos_max = CAJA_MISTERIOSA_REWARDS["puntos_max"]

        cosmos = 0
        puntos = 0

        if tipo == 'cosmos':
            cosmos = random.randint(cosmos_min, cosmos_max)
        elif tipo == 'puntos':
            puntos = random.randint(puntos_min, puntos_max)
        else:  # ambos
            cosmos = random.randint(cosmos_min, cosmos_max // 2)
            puntos = random.randint(puntos_min, puntos_max // 2)

        return {'cosmos': cosmos, 'puntos': puntos}
    
    def _formatear_recompensa(self, recompensas: Dict) -> str:
        """Formatea el texto de recompensas"""
        partes = []
        
        cosmos = recompensas.get('cosmos', 0)
        puntos = recompensas.get('puntos', 0)
        
        if cosmos > 0:
            partes.append(f"✨ <b>{cosmos} Cosmos</b>")
        
        if puntos > 0:
            partes.append(f"⭐ <b>{puntos} Puntos</b>")
        
        return "\n".join(partes)
    
    def _expirar_caja(self, message_id: int, bot):
        """Expira una caja después de 60 segundos"""
        try:
            if message_id in self.cajas_activas:
                caja = self.cajas_activas[message_id]
                
                if not caja['abierta']:
                    # Eliminar mensaje
                    try:
                        bot.delete_message(caja['chat_id'], message_id)
                    except:
                        pass
                    
                    logger.info(f"[MYSTERY] Caja expirada (message_id: {message_id})")
                
                # Limpiar
                del self.cajas_activas[message_id]
        
        except Exception as e:
            logger.error(f"[MYSTERY] Error expirando caja: {e}")


# Instancia global
caja_misteriosa = CajaMisteriosa()
