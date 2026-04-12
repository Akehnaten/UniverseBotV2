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
    import sqlite3
    import logging as _logging

    _log = _logging.getLogger(__name__)

    # Sentencias idempotentes por diseño (IF NOT EXISTS)
    _CREATE_STMTS = [
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
        """
        CREATE TABLE IF NOT EXISTS JUAN_MIEMBROS (
            user_id     INTEGER PRIMARY KEY,
            nombre      TEXT NOT NULL,
            username    TEXT,
            descripcion TEXT
        )
        """,
    ]

    # Columnas a añadir con ALTER TABLE.
    # Formato: { nombre_tabla: [(columna, definicion_sql), ...] }
    # Solo se ejecuta el ALTER si la columna no existe todavía; de este modo
    # la operación es completamente idempotente y no genera ruido en los logs.
    _ALTER_COLUMNS: dict = {
        "USUARIOS":   [("titulo", "TEXT DEFAULT NULL")],
        "EXMIEMBROS": [("titulo", "TEXT DEFAULT NULL")],
    }

    try:
        conn = sqlite3.connect(str(DATABASE_PATH))

        # 1. CREATE TABLE / INDEX — idempotentes por diseño
        for stmt in _CREATE_STMTS:
            try:
                conn.execute(stmt)
            except Exception as _e:
                _log.warning(f"[MIGRATE] CREATE stmt falló (puede ser esperado): {_e}")

        # 2. ALTER TABLE — solo si la columna aún no existe en el esquema
        for tabla, cols in _ALTER_COLUMNS.items():
            # Leer las columnas actuales de la tabla con PRAGMA
            try:
                cursor = conn.execute(f"PRAGMA table_info({tabla})")
                # row[1] es el nombre de la columna en el resultado de PRAGMA
                existing_cols = {row[1] for row in cursor.fetchall()}
            except Exception as _e:
                _log.warning(
                    f"[MIGRATE] No se pudo leer PRAGMA table_info({tabla}): {_e}"
                )
                existing_cols = set()

            for columna, definicion in cols:
                if columna in existing_cols:
                    _log.debug(
                        f"[MIGRATE] Columna '{columna}' en {tabla} ya existe — omitida."
                    )
                    continue

                try:
                    conn.execute(
                        f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}"
                    )
                    _log.info(
                        f"[MIGRATE] Columna '{columna}' añadida a {tabla}."
                    )
                except Exception as _e:
                    err_lower = str(_e).lower()
                    if "duplicate column name" in err_lower:
                        # Doble salvaguarda: PRAGMA falló pero la columna ya existía.
                        # SQLite lo comunica con este mensaje — es inofensivo.
                        _log.debug(
                            f"[MIGRATE] '{columna}' en {tabla}: "
                            f"duplicate column name (PRAGMA no la detectó). OK."
                        )
                    else:
                        _log.error(
                            f"[MIGRATE] ALTER TABLE {tabla} ADD COLUMN {columna} "
                            f"falló inesperadamente: {_e}"
                        )

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
        _log.error(f"[LEADERS] Error sincronizando líderes: {_e}")


_sync_all_leaders()

__all__ = ['db_manager', 'Database', 'crear_todas_las_tablas', 'verificar_tablas']