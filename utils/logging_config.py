# -*- coding: utf-8 -*-
"""
Configuración de Logging Compatible con Windows
Soluciona el problema de emojis en consola Windows (cp1252)
"""

import logging
import sys
from typing import Optional


class SafeFormatter(logging.Formatter):
    """Formatter que maneja emojis de forma segura en Windows"""
    
    def format(self, record):
        # Formatear el mensaje normalmente
        formatted = super().format(record)
        
        # Si estamos en Windows y hay problemas de encoding, limpiar emojis
        try:
            # Intentar codificar a la codificación del sistema
            formatted.encode(sys.stdout.encoding or 'utf-8')
            return formatted
        except (UnicodeEncodeError, AttributeError):
            # Si falla, remover emojis
            return self._remove_emojis(formatted)
    
    def _remove_emojis(self, text: str) -> str:
        """Reemplaza emojis comunes por texto"""
        emoji_map = {
            '✅': '[OK]',
            '❌': '[ERROR]',
            '⚠️': '[WARN]',
            '🚀': '[START]',
            '📦': '[LOAD]',
            '🎉': '[SUCCESS]',
            '💰': '[MONEY]',
            '🎮': '[GAME]',
            '⚔️': '[BATTLE]',
            '🎴': '[CARD]',
            '🥚': '[EGG]',
            '🐣': '[HATCH]',
            '✨': '[SHINY]',
            '🌟': '[STAR]',
            '💎': '[GEM]',
            '🏆': '[TROPHY]',
            '📝': '[NOTE]',
            '🔧': '[CONFIG]',
            '📊': '[STATS]',
            '🎯': '[TARGET]',
            '⭐': '[STAR]',
            '🔥': '[FIRE]',
            '💧': '[WATER]',
            '⚡': '[ELECTRIC]',
            '🌿': '[GRASS]',
        }
        
        for emoji, replacement in emoji_map.items():
            text = text.replace(emoji, replacement)
        
        # Remover cualquier otro emoji que quede
        return text.encode('ascii', 'ignore').decode('ascii')


def setup_logging(level: int = logging.INFO, log_file: Optional[str] = None):
    """
    Configura el sistema de logging de forma compatible con Windows
    
    Args:
        level: Nivel de logging (DEBUG, INFO, WARNING, ERROR)
        log_file: Ruta del archivo de log (opcional)
    """
    # Formato del log
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Crear formatter seguro
    formatter = SafeFormatter(log_format, datefmt=date_format)
    
    # Configurar handler de consola
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    
    # Configurar root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)
    
    # Si se especifica archivo, agregar file handler
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        
        # Para el archivo sí podemos usar UTF-8 completo
        file_formatter = logging.Formatter(log_format, datefmt=date_format)
        file_handler.setFormatter(file_formatter)
        
        root_logger.addHandler(file_handler)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Obtiene un logger configurado de forma segura
    
    Args:
        name: Nombre del logger (usualmente __name__)
    
    Returns:
        Logger configurado
    """
    return logging.getLogger(name)


# Configurar encoding UTF-8 para stdout en Windows
if sys.platform == 'win32':
    try:
        # Intentar configurar UTF-8 en Windows
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'replace')
    except Exception:
        # Si falla, no pasa nada, usaremos SafeFormatter
        pass
