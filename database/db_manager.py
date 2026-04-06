"""
Gestor de Base de Datos - SQLite con Context Manager
import re
Maneja todas las operaciones de base de datos de forma segura y profesional
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, date
from typing import Optional, List, Tuple, Any, Dict
import logging
from pathlib import Path

# Importar configuración
import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import (
    DATABASE_PATH,
    DB_TIMEOUT,
    DB_CHECK_SAME_THREAD
)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mensajes de error de SQLite que son esperados durante migraciones idempotentes
# y no deben registrarse como ERROR (solo como DEBUG).
_EXPECTED_SQLITE_ERRORS = (
    "duplicate column name",
)


class Database:
    """
    Gestor de Base de Datos con Context Manager para SQLite
    Garantiza el cierre automático de conexiones y previene bloqueos
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Inicializa el gestor de base de datos

        Args:
            db_path: Ruta a la base de datos (por defecto usa config.DATABASE_PATH)
        """
        self.db_path = db_path or str(DATABASE_PATH)
        self._ensure_db_directory()

    def _ensure_db_directory(self):
        """Crea el directorio de base de datos si no existe"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def create_tables(self):
        """Crea todas las tablas usando db_operations"""
        from database.db_operations import crear_todas_las_tablas
        return crear_todas_las_tablas(self.db_path)

    @contextmanager
    def get_connection(self):
        """
        Context Manager para obtener conexión a la base de datos.
        Garantiza el cierre automático de la conexión.

        Manejo de errores:
          • Errores esperados de migración idempotente (ej. "duplicate column name")
            se registran en DEBUG para no contaminar los logs de producción.
          • Cualquier otro error de SQLite se registra en ERROR como de costumbre.

        Usage:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM USUARIOS")
        """
        conn = None
        try:
            conn = sqlite3.connect(
                self.db_path,
                timeout=DB_TIMEOUT,
                check_same_thread=DB_CHECK_SAME_THREAD
            )
            # Permite acceso por nombre de columna (row["campo"])
            conn.row_factory = lambda c, r: dict(
                zip([col[0] for col in c.description], r)
            )
            yield conn
            conn.commit()
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            err_lower = str(e).lower()
            if any(expected in err_lower for expected in _EXPECTED_SQLITE_ERRORS):
                # Error esperado durante una migración que ya fue aplicada.
                # Registrar como DEBUG para no alarmar en los logs de producción.
                logger.debug(f"SQLite error esperado (migración ya aplicada): {e}")
            else:
                logger.error(f"Error en base de datos: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """
        Ejecuta una consulta SELECT y retorna los resultados

        Args:
            query: Consulta SQL
            params: Parámetros para la consulta (opcional)

        Returns:
            Lista de resultados
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.fetchall()

    def execute_update(self, query: str, params: Optional[tuple] = None) -> int:
        """
        Ejecuta una consulta INSERT/UPDATE/DELETE

        Args:
            query: Consulta SQL
            params: Parámetros para la consulta (opcional)

        Returns:
            Número de filas afectadas
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.rowcount

    def initialize_database(self):
        """
        Crea todas las tablas del sistema
        IMPORTANTE: Sin columna 'cosmos' - solo usa 'wallet' (créditos)
        """
        logger.info("Inicializando base de datos...")

        tables = {
            "USUARIOS": """
                CREATE TABLE IF NOT EXISTS USUARIOS(
                    userID INTEGER PRIMARY KEY,
                    nombre_usuario VARCHAR(30),
                    nombre VARCHAR(30),
                    clase VARCHAR(15),
                    idol VARCHAR(15),
                    puntos INTEGER DEFAULT 0,
                    material VARCHAR(15),
                    registro DATE,
                    wallet INTEGER DEFAULT 0,
                    jugando INTEGER DEFAULT 0,
                    encola INTEGER DEFAULT 0,
                    enrol INTEGER DEFAULT 0,
                    nickname VARCHAR(30),
                    passwd VARCHAR(30),
                    rol_hist INTEGER DEFAULT 0,
                    nivel INTEGER DEFAULT 1,
                    experiencia INTEGER DEFAULT 0
                )
            """,

            "ROLES": """
                CREATE TABLE IF NOT EXISTS ROLES(
                    rolID INTEGER PRIMARY KEY,
                    estado VARCHAR(15),
                    idolID INTEGER,
                    clienteID VARCHAR(100),
                    comienzo DATETIME,
                    final DATETIME,
                    tiempo TIME,
                    validez VARCHAR(15)
                )
            """,

            "RECORDS": """
                CREATE TABLE IF NOT EXISTS RECORDS(
                    userID INTEGER PRIMARY KEY,
                    record VARCHAR(15),
                    valor VARCHAR(15)
                )
            """,

            "SOLICITUDES": """
                CREATE TABLE IF NOT EXISTS SOLICITUDES(
                    solID INTEGER PRIMARY KEY,
                    request VARCHAR(255),
                    user VARCHAR(30),
                    taken VARCHAR(30),
                    bounty INTEGER,
                    estado VARCHAR(15)
                )
            """,

            "EXMIEMBROS": """
                CREATE TABLE IF NOT EXISTS EXMIEMBROS(
                    userID INTEGER PRIMARY KEY,
                    nombre_usuario VARCHAR(30),
                    nombre VARCHAR(30),
                    clase VARCHAR(15),
                    idol VARCHAR(15),
                    puntos INTEGER DEFAULT 0,
                    material VARCHAR(15),
                    registro DATE,
                    wallet INTEGER DEFAULT 0,
                    jugando INTEGER DEFAULT 0,
                    encola INTEGER DEFAULT 0,
                    enrol INTEGER DEFAULT 0,
                    nickname VARCHAR(30),
                    passwd VARCHAR(30),
                    rol_hist INTEGER DEFAULT 0,
                    motivo VARCHAR(30)
                )
            """,

            "APUESTAS": """
                CREATE TABLE IF NOT EXISTS APUESTAS(
                    betID INTEGER PRIMARY KEY,
                    deporte VARCHAR(30),
                    equipoA VARCHAR(30),
                    equipoB VARCHAR(30),
                    winA FLOAT,
                    draw FLOAT,
                    winB FLOAT,
                    horario DATE,
                    participantes VARCHAR(255) DEFAULT 'None'
                )
            """,

            "MISIONES": """
                CREATE TABLE IF NOT EXISTS MISIONES(
                    userID INTEGER PRIMARY KEY,
                    idol VARCHAR(50) DEFAULT '0',
                    dias VARCHAR(50) DEFAULT '0',
                    post VARCHAR(50) DEFAULT '0',
                    roles VARCHAR(50) DEFAULT '0',
                    win_casino VARCHAR(50) DEFAULT '0',
                    win_bet VARCHAR(50) DEFAULT '0'
                )
            """,

            "INVENTARIOS": """
                CREATE TABLE IF NOT EXISTS INVENTARIOS(
                    userID   INTEGER,
                    album    VARCHAR(20),
                    cartaID  INTEGER,
                    cantidad INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (userID, cartaID)
                )
            """,

            # ============== TABLAS POKÉMON ==============

            "POKEMON_USUARIO": """
                CREATE TABLE IF NOT EXISTS POKEMON_USUARIO (
                    id_unico INTEGER PRIMARY KEY AUTOINCREMENT,
                    userID INTEGER,
                    pokemonID INTEGER,
                    nivel INTEGER DEFAULT 5,
                    iv_atq INTEGER,
                    iv_def INTEGER,
                    iv_vel INTEGER,
                    iv_hp INTEGER,
                    iv_atq_sp INTEGER,
                    iv_def_sp INTEGER,
                    ev_atq INTEGER DEFAULT 0,
                    ev_def INTEGER DEFAULT 0,
                    ev_vel INTEGER DEFAULT 0,
                    ev_hp INTEGER DEFAULT 0,
                    ev_atq_sp INTEGER DEFAULT 0,
                    ev_def_sp INTEGER DEFAULT 0,
                    naturaleza VARCHAR(20),
                    en_equipo INTEGER DEFAULT 0,
                    objeto VARCHAR(30),
                    apodo VARCHAR(30),
                    shiny INTEGER DEFAULT 0,
                    hp_actual INTEGER,
                    exp INTEGER DEFAULT 0,
                    region VARCHAR(20) DEFAULT 'KANTO',
                    move1 VARCHAR(30),
                    move2 VARCHAR(30),
                    move3 VARCHAR(30),
                    move4 VARCHAR(30),
                    habilidad VARCHAR(30),
                    pp_data TEXT,
                    sexo            TEXT    DEFAULT NULL,
                    pasos_guarderia INTEGER DEFAULT 0,
                    ps      INTEGER DEFAULT 0,
                    atq     INTEGER DEFAULT 0,
                    def     INTEGER DEFAULT 0,
                    atq_sp  INTEGER DEFAULT 0,
                    def_sp  INTEGER DEFAULT 0,
                    vel     INTEGER DEFAULT 0,
                    FOREIGN KEY (userID) REFERENCES USUARIOS(userID)
                )
            """,

            "INVENTARIO_USUARIO": """
                CREATE TABLE IF NOT EXISTS INVENTARIO_USUARIO (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    userID INTEGER,
                    item_nombre TEXT,
                    cantidad INTEGER DEFAULT 1,
                    UNIQUE(userID, item_nombre),
                    FOREIGN KEY (userID) REFERENCES USUARIOS(userID)
                )
            """,

            "INTERCAMBIOS_HISTORIAL": """
                CREATE TABLE IF NOT EXISTS INTERCAMBIOS_HISTORIAL (
                    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    emisor_id INTEGER,
                    receptor_id INTEGER,
                    pokemon_emisor TEXT,
                    pokemon_receptor TEXT,
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (emisor_id) REFERENCES USUARIOS(userID),
                    FOREIGN KEY (receptor_id) REFERENCES USUARIOS(userID)
                )
            """,

            "LOGROS_USUARIOS": """
                CREATE TABLE IF NOT EXISTS LOGROS_USUARIOS (
                    userID INTEGER,
                    logroID TEXT,
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (userID, logroID),
                    FOREIGN KEY (userID) REFERENCES USUARIOS(userID)
                )
            """,

            "HUEVOS": """
            CREATE TABLE IF NOT EXISTS HUEVOS (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                userID            INTEGER NOT NULL,
                pokemon_id        INTEGER NOT NULL,
                madre_id          INTEGER DEFAULT NULL,
                padre_id          INTEGER DEFAULT NULL,
                ivs_heredados     TEXT    DEFAULT NULL,
                naturaleza        TEXT    DEFAULT NULL,
                habilidad         TEXT    DEFAULT NULL,
                movimientos_huevo TEXT    DEFAULT NULL,
                es_shiny          INTEGER DEFAULT 0,
                region            TEXT    DEFAULT 'KANTO',
                pasos_necesarios  INTEGER DEFAULT 5120,
                pasos_offset      INTEGER DEFAULT 0,
                pasos_actuales    INTEGER DEFAULT 0,
                eclosionado       INTEGER DEFAULT 0,
                pokemon_nacido_id INTEGER DEFAULT NULL,
                fecha_obtencion   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (userID) REFERENCES USUARIOS(userID)
            )
            """,

            "POKEDEX_USUARIO": """
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

            "GUARDERIA": """
                CREATE TABLE IF NOT EXISTS GUARDERIA (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    userID     INTEGER NOT NULL,
                    pokemon_id INTEGER NOT NULL,
                    fecha      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    slot TEXT DEFAULT 'poke1',
                    FOREIGN KEY (userID)     REFERENCES USUARIOS(userID),
                    FOREIGN KEY (pokemon_id) REFERENCES POKEMON_USUARIO(id_unico)
                )
            """,
        }

        with self.get_connection() as conn:
            cursor = conn.cursor()
            for table_name, table_sql in tables.items():
                cursor.execute(table_sql)
                logger.info(f"✅ Tabla {table_name} creada/verificada")

        # Ejecutar migración de cosmos a wallet
        self._migrate_cosmos_to_wallet()

        logger.info("✅ Base de datos inicializada correctamente")

    def _migrate_cosmos_to_wallet(self):
        """
        Migración crítica: Convierte cosmos a créditos
        1 cosmo = 100 créditos se suma al wallet existente
        """
        logger.info("Iniciando migración de cosmos a wallet...")

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Verificar si la columna cosmos existe
                cursor.execute("PRAGMA table_info(USUARIOS)")
                columns = [column[1] for column in cursor.fetchall()]

                if 'cosmos' in columns:
                    logger.info("Columna 'cosmos' encontrada. Migrando a wallet...")

                    # Mover cosmos a wallet directamente (1 cosmos = 1 wallet)
                    cursor.execute("""
                        UPDATE USUARIOS
                        SET wallet = COALESCE(wallet, 0) + COALESCE(cosmos, 0)
                        WHERE cosmos > 0
                    """)

                    rows_affected = cursor.rowcount
                    logger.info(f"[OK] {rows_affected} usuarios migrados (cosmos -> wallet)")

                    # Eliminar la columna cosmos
                    # SQLite no soporta DROP COLUMN directamente en versiones antiguas
                    # Usamos el método de recrear la tabla

                    # 1. Crear tabla temporal sin cosmos
                    cursor.execute("""
                        CREATE TABLE USUARIOS_NEW(
                            userID INTEGER PRIMARY KEY,
                            nombre_usuario VARCHAR(30),
                            nombre VARCHAR(30),
                            clase VARCHAR(15),
                            idol VARCHAR(15),
                            puntos INTEGER DEFAULT 0,
                            material VARCHAR(15),
                            registro DATE,
                            wallet INTEGER DEFAULT 0,
                            jugando INTEGER DEFAULT 0,
                            encola INTEGER DEFAULT 0,
                            enrol INTEGER DEFAULT 0,
                            nickname VARCHAR(30),
                            passwd VARCHAR(30),
                            rol_hist INTEGER DEFAULT 0,
                            nivel INTEGER DEFAULT 1,
                            experiencia INTEGER DEFAULT 0
                        )
                    """)

                    # 2. Copiar datos (sin cosmos)
                    cursor.execute("""
                        INSERT INTO USUARIOS_NEW
                        SELECT userID, nombre_usuario, nombre, clase, idol, puntos,
                               material, registro, wallet, jugando, encola, enrol,
                               nickname, passwd, rol_hist, nivel, experiencia
                        FROM USUARIOS
                    """)

                    # 3. Eliminar tabla vieja y renombrar
                    cursor.execute("DROP TABLE USUARIOS")
                    cursor.execute("ALTER TABLE USUARIOS_NEW RENAME TO USUARIOS")

                    logger.info("✅ Columna 'cosmos' eliminada exitosamente")

                    # Hacer lo mismo para EXMIEMBROS si tiene cosmos
                    cursor.execute("PRAGMA table_info(EXMIEMBROS)")
                    ex_columns = [column[1] for column in cursor.fetchall()]

                    if 'cosmos' in ex_columns:
                        cursor.execute("""
                            UPDATE EXMIEMBROS
                            SET wallet = COALESCE(wallet, 0) + COALESCE(cosmos, 0)
                            WHERE cosmos > 0
                        """)

                        # Recrear tabla EXMIEMBROS sin cosmos
                        cursor.execute("""
                            CREATE TABLE EXMIEMBROS_NEW(
                                userID INTEGER PRIMARY KEY,
                                nombre_usuario VARCHAR(30),
                                nombre VARCHAR(30),
                                clase VARCHAR(15),
                                idol VARCHAR(15),
                                puntos INTEGER DEFAULT 0,
                                material VARCHAR(15),
                                registro DATE,
                                wallet INTEGER DEFAULT 0,
                                jugando INTEGER DEFAULT 0,
                                encola INTEGER DEFAULT 0,
                                enrol INTEGER DEFAULT 0,
                                nickname VARCHAR(30),
                                passwd VARCHAR(30),
                                rol_hist INTEGER DEFAULT 0,
                                motivo VARCHAR(30)
                            )
                        """)

                        cursor.execute("""
                            INSERT INTO EXMIEMBROS_NEW
                            SELECT userID, nombre_usuario, nombre, clase, idol, puntos,
                                   material, registro, wallet, jugando, encola, enrol,
                                   nickname, passwd, rol_hist, motivo
                            FROM EXMIEMBROS
                        """)

                        cursor.execute("DROP TABLE EXMIEMBROS")
                        cursor.execute("ALTER TABLE EXMIEMBROS_NEW RENAME TO EXMIEMBROS")

                        logger.info("✅ EXMIEMBROS migrado correctamente")

                else:
                    logger.info("✅ Migración no necesaria. Base de datos ya actualizada.")

        except Exception as e:
            logger.error(f"❌ Error en migración: {e}")
            raise

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Obtiene un usuario por su ID

        Args:
            user_id: ID del usuario

        Returns:
            Datos del usuario o None si no existe
        """
        query = "SELECT * FROM USUARIOS WHERE userID = ?"
        results = self.execute_query(query, (user_id,))
        return results[0] if results else None

    def user_exists(self, user_id: int) -> bool:
        """Verifica si un usuario existe en la base de datos"""
        query = "SELECT 1 FROM USUARIOS WHERE userID = ?"
        results = self.execute_query(query, (user_id,))
        return len(results) > 0

    def get_wallet_balance(self, user_id: int) -> int:
        """
        Obtiene el saldo de cosmos de un usuario

        Args:
            user_id: ID del usuario

        Returns:
            Cantidad de cosmos (0 si el usuario no existe)
        """
        query = "SELECT wallet FROM USUARIOS WHERE userID = ?"
        results = self.execute_query(query, (user_id,))
        return results[0]['wallet'] if results else 0

    def update_wallet(self, user_id: int, amount: int, operation: str = 'add') -> bool:
        """
        Actualiza el wallet de un usuario

        Args:
            user_id: ID del usuario
            amount: Cantidad a sumar/restar
            operation: 'add' para sumar, 'subtract' para restar, 'set' para establecer

        Returns:
            True si la operación fue exitosa
        """
        if operation == 'add':
            query = "UPDATE USUARIOS SET wallet = wallet + ? WHERE userID = ?"
        elif operation == 'subtract':
            query = "UPDATE USUARIOS SET wallet = wallet - ? WHERE userID = ?"
        elif operation == 'set':
            query = "UPDATE USUARIOS SET wallet = ? WHERE userID = ?"
        else:
            raise ValueError(f"Operación inválida: {operation}")

        rows_affected = self.execute_update(query, (amount, user_id))
        return rows_affected > 0

    # ==================== MÉTODOS DE USUARIOS ====================

    def insert_user(self, user_id: int, nombre_usuario: str, nombre: str,
                   clase: str, idol: Optional[str] = None, registro: Optional[date] = None) -> bool:
        """
        Inserta un nuevo usuario en la base de datos

        Args:
            user_id: ID del usuario de Telegram
            nombre_usuario: Username (@usuario)
            nombre: Nombre del usuario
            clase: 'idol' o 'cliente'
            idol: Idol asignado (opcional)
            registro: Fecha de registro (por defecto hoy)

        Returns:
            True si se insertó correctamente
        """
        if registro is None:
            registro = date.today()

        if idol:
            query = """
                INSERT INTO USUARIOS (userID, nombre_usuario, nombre, clase, idol, registro, nickname)
                VALUES (?, ?, ?, ?, ?, ?, 'VIP')
            """
            params = (user_id, nombre_usuario, nombre, clase, idol, registro)
        else:
            query = """
                INSERT INTO USUARIOS (userID, nombre_usuario, nombre, clase, registro, nickname)
                VALUES (?, ?, ?, ?, ?, 'VIP')
            """
            params = (user_id, nombre_usuario, nombre, clase, registro)

        try:
            self.execute_update(query, params)
            logger.info(f"✅ Usuario {nombre_usuario} ({user_id}) insertado correctamente")
            return True
        except Exception as e:
            logger.error(f"❌ Error insertando usuario: {e}")
            return False

    def update_field(self, field: str, value: Any, column: str, identifier: Any) -> bool:
        """
        Actualiza un campo específico de un usuario

        Args:
            field: Campo a actualizar
            value: Nuevo valor
            column: Columna de búsqueda
            identifier: Valor de búsqueda

        Returns:
            True si se actualizó correctamente
        """
        query = f"UPDATE USUARIOS SET {field} = ? WHERE {column} = ?"
        rows_affected = self.execute_update(query, (value, identifier))
        return rows_affected > 0

    def get_leaderboard(self, limit: int = 0) -> str:
        """
        Obtiene el ranking de usuarios por wallet (antes cosmos)

        Args:
            limit: Número de usuarios a mostrar (0 = todos)

        Returns:
            Texto formateado con el ranking
        """
        # Ranking de idols
        if limit == 0:
            query_idols = "SELECT nombre, wallet FROM USUARIOS WHERE clase='idol' ORDER BY wallet DESC"
        else:
            query_idols = f"SELECT nombre, wallet FROM USUARIOS WHERE clase='idol' ORDER BY wallet DESC LIMIT {limit}"

        idols = self.execute_query(query_idols)

        texto = "<b><u>Lista de idols y sus cosmos:</u></b>\n\n"
        for idol in idols:
            texto += f'<b>{idol["nombre"]}:</b> {idol["wallet"]} cosmos\n'

        # Ranking de clientes
        if limit == 0:
            query_clientes = "SELECT nombre, wallet FROM USUARIOS WHERE clase='cliente' ORDER BY wallet DESC"
        else:
            query_clientes = f"SELECT nombre, wallet FROM USUARIOS WHERE clase='cliente' ORDER BY wallet DESC LIMIT {limit}"

        clientes = self.execute_query(query_clientes)

        texto += "\n<b><u>Lista de clientes y sus cosmos:</u></b>\n\n"
        for cliente in clientes:
            texto += f'<b>{cliente["nombre"]}:</b> {cliente["wallet"]} cosmos\n'

        return texto

    def get_ranking_by_points(self, limit: int = 0) -> str:
        """
        Obtiene el ranking de usuarios por puntos

        Args:
            limit: Número de usuarios a mostrar (0 = todos)

        Returns:
            Texto formateado con el ranking
        """
        if limit == 0:
            query = "SELECT nombre, puntos FROM USUARIOS ORDER BY puntos DESC"
        else:
            query = f"SELECT nombre, puntos FROM USUARIOS ORDER BY puntos DESC LIMIT {limit}"

        users = self.execute_query(query)

        texto = "<b><u>Lista de usuarios y sus Puntos:</u></b>\n\n"
        for user in users:
            texto += f'<b>{user["nombre"]}:</b> {user["puntos"]} puntos\n'

        return texto if users else "<b><u>Lista de usuarios y sus Puntos:</u></b>\n\n"

    def get_user_stats(self, nombre_usuario: str) -> str:
        """
        Obtiene las estadísticas de un usuario

        Args:
            nombre_usuario: Username del usuario

        Returns:
            Texto formateado con las estadísticas
        """
        query = "SELECT puntos, wallet FROM USUARIOS WHERE nombre_usuario = ?"
        results = self.execute_query(query, (nombre_usuario,))

        if results:
            user = results[0]
            return f"<b><u>Estadísticas de {nombre_usuario}:</u></b>\n\n" \
                   f"Puntos: {user['puntos']}\n" \
                   f"Cosmos: {user['wallet']}\n"
        else:
            return 'Usuario no registrado en base de datos.'

    def get_profile(self, user_id: int) -> Optional[dict]:
        """
        Obtiene el perfil completo de un usuario

        Args:
            user_id: ID del usuario

        Returns:
            Diccionario con los datos del usuario
        """
        user = self.get_user(user_id)
        if user:
            return dict(user)
        return None

    # ==================== MÉTODOS DE ROLES ====================

    def create_role(self, idol_id: int, cliente_id: str) -> int:
        """
        Crea un nuevo rol en la base de datos

        Args:
            idol_id: ID del idol
            cliente_id: ID del cliente

        Returns:
            ID del rol creado
        """
        comienzo = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        query = """
            INSERT INTO ROLES (estado, idolID, clienteID, comienzo)
            VALUES ('en curso', ?, ?, ?)
        """
        self.execute_update(query, (idol_id, cliente_id, comienzo))

        # Obtener el ID del rol recién creado
        return self.get_last_role_id()

    def get_last_role_id(self) -> int:
        """
        Obtiene el ID del último rol creado

        Returns:
            ID del último rol
        """
        query = "SELECT rolID FROM ROLES ORDER BY rolID DESC LIMIT 1"
        results = self.execute_query(query)
        return results[0]['rolID'] if results else 0

    def close_role(self, rol_id: int, final: str, tiempo: str, validez: str) -> bool:
        """
        Cierra un rol

        Args:
            rol_id: ID del rol
            final: Fecha/hora de finalización
            tiempo: Tiempo total del rol
            validez: 'valido' o 'no valido'

        Returns:
            True si el rol era válido, False si no
        """
        if validez == "no valido":
            self.delete_row(rol_id, 'ROLES')
            return False
        else:
            query = """
                UPDATE ROLES
                SET estado='finalizado', final=?, tiempo=?, validez=?
                WHERE rolID=?
            """
            self.execute_update(query, (final, tiempo, validez, rol_id))
            return True

    def get_queue(self) -> List[Tuple[str, str]]:
        """
        Obtiene la lista de usuarios en cola

        Returns:
            Lista de tuplas (idol, nombre_usuario)
        """
        query = "SELECT idol, nombre_usuario FROM USUARIOS WHERE encola = 1"
        results = self.execute_query(query)
        return [(row['idol'], row['nombre_usuario']) for row in results]

    def calculate_points(self, user_id: int, tiempo: int, fiesta: int = 0) -> tuple[int, int]:
        """
        Calcula y actualiza los puntos de un usuario después de un rol.

        La gestión de experiencia y nivel de usuario NO ocurre aquí —
        está delegada a ``funciones.user_experience.aplicar_experiencia_usuario()``.

        Args:
            user_id: ID del usuario.
            tiempo:  Duración del rol en segundos.
            fiesta:  Multiplicador de evento (0 = sin evento).

        Returns:
            (nuevos_puntos, puntos_ganados)
        """
        # Obtener datos del usuario
        query = "SELECT puntos, wallet, nickname FROM USUARIOS WHERE userID = ?"
        results = self.execute_query(query, (user_id,))

        if not results:
            return 0, 0

        user = results[0]
        puntos  = user['puntos']
        wallet  = user['wallet']
        account = user['nickname']
        # nivel y experiencia ya no se gestionan aquí —
        # delegado a funciones.user_experience.aplicar_experiencia_usuario()

        # Calcular modificador de puntos
        if tiempo > 14400:  # +4 horas
            modificador = 240
        elif tiempo > 600:  # +10 minutos
            modificador = tiempo / 60
        else:
            modificador = 0  # No aumenta

        # Aplicar bonus VIP
        if account == "VIP":
            # Calcular créditos (antes cosmos y wallet)
            modificador_vip = modificador * 1.25
            creditos_ganados = round(modificador_vip + 0.01)

            # Aplicar multiplicador de fiesta si existe
            if fiesta != 0:
                puntos_ganados   = round(modificador * fiesta * 0.5 * 1.25 + 0.01)
                creditos_ganados = round(modificador_vip * fiesta * 0.5 + 0.01)
            else:
                puntos_ganados = round(modificador * 1.25 + 0.01)

            nuevos_puntos   = puntos + puntos_ganados
            nuevos_creditos = wallet + creditos_ganados

            # Actualizar puntos y créditos
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE USUARIOS SET puntos = ? WHERE userID = ?",
                    (nuevos_puntos, user_id),
                )
                cursor.execute(
                    "UPDATE USUARIOS SET wallet = ? WHERE userID = ?",
                    (nuevos_creditos, user_id),
                )

            return nuevos_puntos, puntos_ganados
        else:
            # Sin bonus VIP
            creditos_ganados = round(modificador + 0.01)

            if fiesta != 0:
                puntos_ganados   = round(modificador * fiesta * 0.5 + 0.01)
                creditos_ganados = round(modificador * fiesta * 0.5 + 0.01)
            else:
                puntos_ganados = round(modificador + 0.01)

            nuevos_puntos   = puntos + puntos_ganados
            nuevos_creditos = wallet + creditos_ganados

            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE USUARIOS SET puntos = ? WHERE userID = ?",
                    (nuevos_puntos, user_id),
                )
                cursor.execute(
                    "UPDATE USUARIOS SET wallet = ? WHERE userID = ?",
                    (nuevos_creditos, user_id),
                )

            return nuevos_puntos, puntos_ganados

    def increment_roles(self, user_id: int) -> int:
        """
        Incrementa el contador de roles de un usuario

        Args:
            user_id: ID del usuario

        Returns:
            Nuevo contador de roles jugando
        """
        query = "SELECT jugando, rol_hist FROM USUARIOS WHERE userID = ?"
        results = self.execute_query(query, (user_id,))

        if results:
            user = results[0]
            jug  = user['jugando'] + 1
            hist = user['rol_hist'] + 1

            update_query = "UPDATE USUARIOS SET rol_hist = ?, jugando = ? WHERE userID = ?"
            self.execute_update(update_query, (hist, jug, user_id))

            return jug
        return 0

    def get_active_roles(self, user_id: int, clase: str) -> int:
        """
        Obtiene el número de roles activos de un usuario

        Args:
            user_id: ID del usuario
            clase: 'idol' o 'cliente'

        Returns:
            Número de roles activos
        """
        if clase == 'idol':
            query = "SELECT COUNT(*) as count FROM ROLES WHERE idolID = ? AND estado = 'en curso'"
        else:
            query = "SELECT COUNT(*) as count FROM ROLES WHERE clienteID = ? AND estado = 'en curso'"

        results = self.execute_query(query, (user_id,))
        return results[0]['count'] if results else 0

    # ==================== MÉTODOS DE APUESTAS ====================

    def create_bet(self, deporte: str, equipoA: str, equipoB: str,
                   winA: float, draw: float, winB: float, horario: str) -> bool:
        """
        Crea una nueva apuesta

        Args:
            deporte: Tipo de deporte
            equipoA: Nombre del equipo A
            equipoB: Nombre del equipo B
            winA: Cuota victoria equipo A
            draw: Cuota empate
            winB: Cuota victoria equipo B
            horario: Fecha y hora del evento

        Returns:
            True si se creó correctamente
        """
        query = """
            INSERT INTO APUESTAS (deporte, equipoA, equipoB, winA, draw, winB, horario)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        try:
            self.execute_update(query, (deporte, equipoA, equipoB, winA, draw, winB, horario))
            return True
        except Exception as e:
            logger.error(f"Error creando apuesta: {e}")
            return False

    def close_bet(self, bet_id: int, winner: str) -> List[str]:
        """
        Cierra una apuesta y reparte ganancias

        Args:
            bet_id: ID de la apuesta
            winner: Ganador ('A', 'D', 'B')

        Returns:
            Lista de ganadores
        """
        query = "SELECT participantes, winA, draw, winB FROM APUESTAS WHERE betID = ?"
        results = self.execute_query(query, (bet_id,))

        if not results:
            return []

        bet_data      = results[0]
        participantes = bet_data['participantes']

        if participantes == "None":
            self.delete_row(bet_id, 'APUESTAS')
            return ["vacio"]

        # Procesar ganadores
        ganadores    = []
        modificadores = {
            'A': bet_data['winA'],
            'D': bet_data['draw'],
            'B': bet_data['winB'],
        }

        # Parsear participantes: formato [(username,creditos,apuesta)]
        for participante_str in participantes[2:-1].split("("):
            if not participante_str:
                continue

            try:
                parts    = participante_str.rstrip(')').split(",")
                username = parts[0]
                creditos_apostados = int(parts[1])
                apuesta  = parts[2].strip()[0]

                if apuesta == winner.upper():
                    ganadores.append(username)

                    # Obtener wallet actual
                    user_query  = "SELECT wallet FROM USUARIOS WHERE nombre_usuario = ?"
                    user_result = self.execute_query(user_query, (username,))

                    if user_result:
                        wallet_actual = user_result[0]['wallet']
                        modificador   = modificadores[apuesta]

                        # Calcular ganancia
                        ganancia   = int(creditos_apostados * modificador)
                        nuevo_wallet = wallet_actual + ganancia

                        # Actualizar wallet
                        update_query = "UPDATE USUARIOS SET wallet = ? WHERE nombre_usuario = ?"
                        self.execute_update(update_query, (nuevo_wallet, username))
            except Exception as e:
                logger.error(f"Error procesando participante: {e}")
                continue

        # Eliminar apuesta
        self.delete_row(bet_id, 'APUESTAS')

        return ganadores

    def add_bet_participant(self, bet_id: int, username: str, creditos: int, bet: str) -> str:
        """
        Añade un participante a una apuesta

        Args:
            bet_id: ID de la apuesta
            username: Nombre de usuario
            creditos: Cosmos apostados
            bet: Apuesta ('A', 'D', 'B')

        Returns:
            'cargada' si se añadió correctamente, 'tarde' si ya comenzó
        """
        query   = "SELECT participantes, horario FROM APUESTAS WHERE betID = ?"
        results = self.execute_query(query, (bet_id,))

        if not results:
            return "error"

        bet_data = results[0]

        # Verificar si ya empezó el evento
        hora_evento = datetime.strptime(bet_data['horario'], "%Y-%m-%d %H:%M")
        if hora_evento <= datetime.now():
            return "tarde"

        # Añadir a la lista de participantes
        participantes = bet_data['participantes']
        if participantes != "None":
            nueva_lista = participantes[:-1] + f',({username},{creditos},{bet})]'
        else:
            nueva_lista = f'[({username},{creditos},{bet})]'

        update_query = "UPDATE APUESTAS SET participantes = ? WHERE betID = ?"
        self.execute_update(update_query, (nueva_lista, bet_id))

        return "cargada"

    def get_available_bets(self) -> List[dict]:
        """
        Obtiene todas las apuestas disponibles

        Returns:
            Lista de diccionarios con datos de apuestas
        """
        query   = "SELECT * FROM APUESTAS"
        results = self.execute_query(query)
        return [dict(row) for row in results]

    # ==================== MÉTODOS GENERALES ====================

    def delete_row(self, id: int, tabla: str = 'USUARIOS') -> bool:
        """
        Elimina una fila de una tabla

        Args:
            id: ID a eliminar
            tabla: Nombre de la tabla

        Returns:
            True si se eliminó correctamente
        """
        # Mapeo de tablas a sus columnas ID
        id_columns = {
            'ROLES':       'rolID',
            'APUESTAS':    'betID',
            'SOLICITUDES': 'solID',
            'EXMIEMBROS':  'userID',
            'USUARIOS':    'userID',
        }

        # Obtener el nombre de la columna ID para esta tabla
        id_column = id_columns.get(tabla, 'userID')

        query        = f"DELETE FROM {tabla} WHERE {id_column} = ?"
        rows_affected = self.execute_update(query, (id,))
        return rows_affected > 0

    def move_to_exmembers(self, user_id: int, motivo: str = "No especificado") -> bool:
        """
        Mueve un usuario de USUARIOS a EXMIEMBROS, preservando todos sus datos.

        Campos preservados: userID, nombre_usuario, nombre, clase, idol,
            puntos, material, registro, wallet, jugando, encola, enrol,
            nickname, passwd, rol_hist, nivel, experiencia.
        Campo añadido: motivo (razón de salida).

        Returns:
            True si se completó correctamente.
        """
        user_data = self.get_user(user_id)
        if not user_data:
            logger.warning(f"[DB] move_to_exmembers: usuario {user_id} no encontrado.")
            return False

        try:
            # INSERT OR REPLACE por si ya existe en EXMIEMBROS (ej: registros huérfanos)
            self.execute_update(
                """
                INSERT OR REPLACE INTO EXMIEMBROS (
                    userID, nombre_usuario, nombre, clase, idol,
                    puntos, material, registro, wallet,
                    jugando, encola, enrol, nickname, passwd,
                    rol_hist, nivel, experiencia, motivo
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    user_data["userID"],
                    user_data.get("nombre_usuario", ""),
                    user_data.get("nombre", ""),
                    user_data.get("clase", "cliente"),
                    user_data.get("idol"),
                    user_data.get("puntos", 0),
                    user_data.get("material"),
                    user_data.get("registro"),
                    user_data.get("wallet", 0),
                    user_data.get("jugando", 0),
                    user_data.get("encola", 0),
                    user_data.get("enrol", 0),
                    user_data.get("nickname"),
                    user_data.get("passwd"),
                    user_data.get("rol_hist", 0),
                    user_data.get("nivel", 1),
                    user_data.get("experiencia", 0),
                    motivo,
                ),
            )
            # Eliminar de USUARIOS solo tras confirmar el INSERT
            self.delete_row(user_id, "USUARIOS")
            logger.info(f"[DB] Usuario {user_id} movido a EXMIEMBROS. Motivo: {motivo!r}")
            return True

        except Exception as exc:
            logger.error(f"[DB] Error en move_to_exmembers({user_id}): {exc}")
            return False

    def restore_from_exmembers(self, user_id: int) -> bool:
        """
        Restaura un usuario de EXMIEMBROS a USUARIOS con todos sus datos.

        Campos restaurados: todos los presentes en EXMIEMBROS, mapeados a
        USUARIOS. Los campos exclusivos de USUARIOS que no existen en
        EXMIEMBROS (pasos_guarderia, ultima_recompensa_diaria) se inicializan
        a sus valores por defecto (0 y NULL).

        Los estados transitorios (jugando, encola, enrol) se resetean a 0
        para evitar que el usuario quede en un estado inconsistente.

        Returns:
            True si se completó correctamente.
        """
        try:
            resultado = self.execute_query(
                "SELECT * FROM EXMIEMBROS WHERE userID = ?",
                (user_id,),
            )
            if not resultado:
                logger.warning(
                    f"[DB] restore_from_exmembers: {user_id} no encontrado en EXMIEMBROS."
                )
                return False

            ex = dict(resultado[0])

            # INSERT OR REPLACE en USUARIOS (por si el usuario se re-registró
            # manualmente sin haber sido eliminado de EXMIEMBROS)
            self.execute_update(
                """
                INSERT OR REPLACE INTO USUARIOS (
                    userID, nombre_usuario, nombre, clase, idol,
                    puntos, material, registro, wallet,
                    jugando, encola, enrol, nickname, passwd,
                    rol_hist, nivel, experiencia,
                    pasos_guarderia, ultima_recompensa_diaria
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    0, 0, 0, ?, ?,
                    ?, ?, ?,
                    0, NULL
                )
                """,
                (
                    ex["userID"],
                    ex.get("nombre_usuario", ""),
                    ex.get("nombre", ""),
                    ex.get("clase", "cliente"),
                    ex.get("idol"),
                    ex.get("puntos", 0),
                    ex.get("material"),
                    ex.get("registro"),
                    ex.get("wallet", 0),
                    # jugando=0, encola=0, enrol=0 → estados reseteados
                    ex.get("nickname"),
                    ex.get("passwd"),
                    ex.get("rol_hist", 0),
                    ex.get("nivel", 1),
                    ex.get("experiencia", 0),
                    # pasos_guarderia=0, ultima_recompensa_diaria=NULL
                ),
            )

            # Eliminar de EXMIEMBROS solo tras confirmar el INSERT
            self.execute_update(
                "DELETE FROM EXMIEMBROS WHERE userID = ?",
                (user_id,),
            )

            logger.info(f"[DB] Usuario {user_id} restaurado de EXMIEMBROS a USUARIOS.")
            return True

        except Exception as exc:
            logger.error(f"[DB] Error en restore_from_exmembers({user_id}): {exc}")
            return False

    def user_in_exmembers(self, user_id: int) -> bool:
        """
        Verifica si un usuario está en EXMIEMBROS

        Args:
            user_id: ID del usuario

        Returns:
            True si está en EXMIEMBROS
        """
        try:
            query  = "SELECT userID FROM EXMIEMBROS WHERE userID = ?"
            result = self.execute_query(query, (user_id,))
            return len(result) > 0
        except Exception:
            return False

    def execute_insert(self, query: str, params: Optional[tuple] = None) -> Optional[int]:
        """
        Ejecuta un INSERT y retorna el ID autogenerado (lastrowid).
        Usar en lugar de execute_update cuando se necesita el ID del nuevo registro.

        Returns:
            lastrowid del registro insertado, o None si falla.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.lastrowid if cursor.lastrowid else None


# Instancia global del gestor de base de datos
db_manager = Database()


if __name__ == "__main__":
    # Test del sistema
    print("🔧 Inicializando base de datos...")
    db_manager.initialize_database()
    print("✅ Base de datos lista para usar")
