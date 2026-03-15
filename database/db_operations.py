# -*- coding: utf-8 -*-
"""
Operaciones de Base de Datos
Todas las funciones que trabajan con las tablas
"""

import sqlite3
import logging
from typing import List, Optional, Tuple, Any
from database.schema import TODAS_LAS_TABLAS, INDICES, LIDERES_GIMNASIO

logger = logging.getLogger(__name__)


def crear_todas_las_tablas(db_path: str) -> bool:
    """
    Crea todas las tablas e índices en la base de datos
    
    Args:
        db_path: Ruta al archivo de base de datos
        
    Returns:
        True si exitoso, False si error
    """
    try:
        logger.info("="*70)
        logger.info("CREANDO BASE DE DATOS")
        logger.info("="*70)
        logger.info(f"Archivo: {db_path}")
        logger.info(f"Tablas: {len(TODAS_LAS_TABLAS)}")
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 1. Crear todas las tablas
        tablas_creadas = 0
        for i, tabla_sql in enumerate(TODAS_LAS_TABLAS, 1):
            try:
                cursor.execute(tabla_sql)
                tablas_creadas += 1
                
                # Extraer nombre
                import re
                match = re.search(r'CREATE TABLE IF NOT EXISTS (\w+)', tabla_sql)
                nombre = match.group(1) if match else f"Tabla_{i}"
                logger.info(f"✅ [{i:2d}/{len(TODAS_LAS_TABLAS)}] {nombre}")
                
            except Exception as e:
                logger.error(f"❌ [{i:2d}/{len(TODAS_LAS_TABLAS)}] Error: {e}")
        
        conn.commit()
        logger.info(f"Commit: {tablas_creadas}/{len(TODAS_LAS_TABLAS)} tablas creadas")
        
        # 2. Insertar líderes de gimnasio
        try:
            lideres_insertados = 0
            for lider in LIDERES_GIMNASIO:
                cursor.execute("""
                    INSERT OR IGNORE INTO LIDERES_GIMNASIO 
                    (lider_id, nombre, titulo, tipo_especialidad, medalla, 
                     nivel_equipo, recompensa_base, descripcion, activo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, lider)
                if cursor.rowcount > 0:
                    lideres_insertados += 1
            
            conn.commit()
            logger.info(f"✅ {lideres_insertados} líderes insertados")
        except Exception as e:
            logger.error(f"❌ Error líderes: {e}")
        
        # 3. Crear índices
        try:
            indices_creados = 0
            for idx_sql in INDICES:
                cursor.execute(idx_sql)
                indices_creados += 1
            
            conn.commit()
            logger.info(f"✅ {indices_creados} índices creados")
        except Exception as e:
            logger.error(f"❌ Error índices: {e}")
        
        conn.close()
        
        logger.info("="*70)
        logger.info("✅ BASE DE DATOS LISTA")
        logger.info("="*70)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ ERROR FATAL: {e}", exc_info=True)
        return False


def verificar_tablas(db_path: str) -> List[str]:
    """
    Verifica qué tablas existen en la base de datos
    
    Returns:
        Lista de nombres de tablas
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tablas = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tablas
    except Exception as e:
        logger.error(f"Error verificando tablas: {e}")
        return []
