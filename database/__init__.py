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
        "ALTER TABLE USUARIOS ADD COLUMN titulo TEXT DEFAULT NULL",
        "ALTER TABLE EXMIEMBROS ADD COLUMN titulo TEXT DEFAULT NULL",
    ]
    import sqlite3, logging as _logging
    _log = _logging.getLogger(__name__)
    try:
        conn = sqlite3.connect(str(DATABASE_PATH))
        for stmt in _MISSING:
            try:
                conn.execute(stmt)
            except Exception:
                pass   # columna ya existe — ignorar silenciosamente
        conn.commit()
        conn.close()
        _log.info("[MIGRATE] POKEDEX_USUARIO verificada/creada correctamente.")
    except Exception as _e:
        _log.error(f"[MIGRATE] Error en migración de tablas: {_e}")

_migrate_missing_tables()

def _sync_all_leaders() -> None:
    """
    Sincroniza TODOS los líderes de todas las regiones con la BD.
    Usa INSERT OR IGNORE para no duplicar y no sobreescribir datos existentes.
    Se ejecuta en cada arranque del bot — es idempotente.
    """
    from pokemon.region_config import get_all_leaders_flat
    import sqlite3
    import logging as _logging
    _log = _logging.getLogger(__name__)
    try:
        conn = sqlite3.connect(str(DATABASE_PATH))
        inserted = 0
        for lider in get_all_leaders_flat():
            cur = conn.execute(
                """INSERT OR IGNORE INTO LIDERES_GIMNASIO
                   (lider_id, nombre, titulo, tipo_especialidad, medalla,
                    nivel_equipo, recompensa_base, descripcion, activo)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                lider,
            )
            if cur.rowcount:
                inserted += 1
        conn.commit()
        conn.close()
        if inserted:
            _log.info(f"[LEADERS] {inserted} líderes nuevos insertados en BD.")
        else:
            _log.info("[LEADERS] Todos los líderes ya estaban en BD.")
    except Exception as _e:
        import logging
        logging.getLogger(__name__).error(f"[LEADERS] Error sincronizando líderes: {_e}")
 
_sync_all_leaders()

__all__ = ['db_manager', 'Database', 'crear_todas_las_tablas', 'verificar_tablas']
