# -*- coding: utf-8 -*-
"""
Sistema de Base de Datos
"""

from database.db_manager import Database
from database.db_operations import crear_todas_las_tablas, verificar_tablas
from config import DATABASE_PATH

# Instancia global
db_manager = Database(DATABASE_PATH)

# ── Migración de tablas faltantes (safe: usa IF NOT EXISTS) ──────────────────
# Garantiza que tablas añadidas después de la creación inicial existan en BDs
# ya existentes, sin tocar ningún dato.
def _migrate_missing_tables() -> None:
    _MISSING = [
        """
        CREATE TABLE IF NOT EXISTS POKEDEX_USUARIO (
            userID        INTEGER NOT NULL,
            pokemonID     INTEGER NOT NULL,
            avistado      INTEGER DEFAULT 1,
            capturado     INTEGER DEFAULT 0,
            fecha_vista   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fecha_captura TIMESTAMP,
            PRIMARY KEY (userID, pokemonID),
            FOREIGN KEY (userID) REFERENCES USUARIOS(userID)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_pokedex_user ON POKEDEX_USUARIO(userID)",
    ]
    import sqlite3, logging as _logging
    _log = _logging.getLogger(__name__)
    try:
        conn = sqlite3.connect(str(DATABASE_PATH))
        for stmt in _MISSING:
            conn.execute(stmt)
        conn.commit()
        conn.close()
        _log.info("[MIGRATE] POKEDEX_USUARIO verificada/creada correctamente.")
    except Exception as _e:
        _log.error(f"[MIGRATE] Error en migración de tablas: {_e}")

_migrate_missing_tables()

__all__ = ['db_manager', 'Database', 'crear_todas_las_tablas', 'verificar_tablas']
