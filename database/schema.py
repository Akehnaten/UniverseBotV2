# -*- coding: utf-8 -*-
"""
Schema de Base de Datos - Todas las tablas en un solo lugar
"""

# ============== TABLAS DEL SISTEMA ==============

TABLA_USUARIOS = """
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
    experiencia INTEGER DEFAULT 0,
    pasos_guarderia INTEGER DEFAULT 0,
    ultima_recompensa_diaria TEXT DEFAULT NULL
)
"""

TABLA_EXMIEMBROS = """
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
    nivel INTEGER DEFAULT 1,
    experiencia INTEGER DEFAULT 0,
    motivo VARCHAR(30)
)
"""

TABLA_ROLES = """
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
"""

TABLA_RECORDS = """
CREATE TABLE IF NOT EXISTS RECORDS(
    userID INTEGER PRIMARY KEY,
    record VARCHAR(15),
    valor VARCHAR(15)
)
"""

TABLA_SOLICITUDES = """
CREATE TABLE IF NOT EXISTS SOLICITUDES(
    solID INTEGER PRIMARY KEY,
    request VARCHAR(255),
    user VARCHAR(30),
    taken VARCHAR(30),
    bounty INTEGER,
    estado VARCHAR(15)
)
"""

TABLA_APUESTAS = """
CREATE TABLE IF NOT EXISTS APUESTAS(
    betID INTEGER PRIMARY KEY,
    deporte VARCHAR(30),
    equipoA VARCHAR(30),
    equipoB VARCHAR(30),
    winA FLOAT,
    draw FLOAT,
    winB FLOAT,
    horario DATE,
    participantes VARCHAR(255) DEFAULT NULL
)
"""

TABLA_MISIONES = """
CREATE TABLE IF NOT EXISTS MISIONES(
    userID INTEGER PRIMARY KEY,
    idol VARCHAR(50) DEFAULT '0',
    dias VARCHAR(50) DEFAULT '0',
    post VARCHAR(50) DEFAULT '0',
    roles VARCHAR(50) DEFAULT '0',
    win_casino VARCHAR(50) DEFAULT '0',
    win_bet VARCHAR(50) DEFAULT '0'
)
"""

TABLA_INVENTARIOS = """
CREATE TABLE IF NOT EXISTS INVENTARIOS(
    userID   INTEGER,
    album    VARCHAR(20),
    cartaID  INTEGER,
    cantidad INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (userID, cartaID)
)
"""

# ============== TABLAS POKÉMON ==============

TABLA_POKEMON_USUARIO = """
CREATE TABLE IF NOT EXISTS POKEMON_USUARIO (
    id_unico  INTEGER PRIMARY KEY AUTOINCREMENT,
    userID    INTEGER,
    pokemonID INTEGER,
    nivel     INTEGER DEFAULT 5,

    -- ── Individual Values (inmutables tras la creación, 0-31) ───────────
    iv_hp     INTEGER DEFAULT 0,
    iv_atq    INTEGER DEFAULT 0,
    iv_def    INTEGER DEFAULT 0,
    iv_vel    INTEGER DEFAULT 0,
    iv_atq_sp INTEGER DEFAULT 0,
    iv_def_sp INTEGER DEFAULT 0,

    -- ── Effort Values (0-255 por stat, máximo 510 en total) ─────────────
    ev_hp     INTEGER DEFAULT 0,
    ev_atq    INTEGER DEFAULT 0,
    ev_def    INTEGER DEFAULT 0,
    ev_vel    INTEGER DEFAULT 0,
    ev_atq_sp INTEGER DEFAULT 0,
    ev_def_sp INTEGER DEFAULT 0,

    naturaleza VARCHAR(20),
    en_equipo  INTEGER DEFAULT 0,
    objeto     VARCHAR(30),
    apodo      TEXT DEFAULT NULL,
    shiny      INTEGER DEFAULT 0,

    -- ── Stats calculados — caché de la fórmula Gen 3+ ───────────────────
    -- Se actualizan al: crear, subir de nivel, evolucionar, cambiar EVs.
    -- Fórmula HP:   floor(((2B+IV+floor(EV/4))×nivel)/100) + nivel + 10
    -- Fórmula otro: floor((floor(((2B+IV+floor(EV/4))×nivel)/100)+5)×nat)
    ps        INTEGER DEFAULT 0,   -- Puntos de Salud máximos
    atq       INTEGER DEFAULT 0,   -- Ataque físico
    def       INTEGER DEFAULT 0,   -- Defensa física
    atq_sp    INTEGER DEFAULT 0,   -- Ataque especial
    def_sp    INTEGER DEFAULT 0,   -- Defensa especial
    vel       INTEGER DEFAULT 0,   -- Velocidad
    -- ─────────────────────────────────────────────────────────────────────

    hp_actual  INTEGER,            -- HP actual en combate (≤ ps)
    exp        INTEGER DEFAULT 0,
    region     VARCHAR(20) DEFAULT 'KANTO',
    move1      VARCHAR(30),
    move2      VARCHAR(30),
    move3      VARCHAR(30),
    move4      VARCHAR(30),
    habilidad  VARCHAR(30),
    pp_data    TEXT,
    sexo       TEXT DEFAULT NULL,
    pasos_guarderia INTEGER DEFAULT 0,
    posicion_equipo INTEGER DEFAULT NULL,  -- 0-5 en equipo, NULL en PC,
    FOREIGN KEY (userID) REFERENCES USUARIOS(userID)
)
"""

TABLA_INVENTARIO_USUARIO = """
CREATE TABLE IF NOT EXISTS INVENTARIO_USUARIO (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    userID INTEGER,
    item_nombre TEXT,
    cantidad INTEGER DEFAULT 1,
    UNIQUE(userID, item_nombre),
    FOREIGN KEY (userID) REFERENCES USUARIOS(userID)
)
"""

TABLA_INTERCAMBIOS_HISTORIAL = """
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
"""

TABLA_LOGROS_USUARIOS = """
CREATE TABLE IF NOT EXISTS LOGROS_USUARIOS (
    userID INTEGER,
    logroID TEXT,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (userID, logroID),
    FOREIGN KEY (userID) REFERENCES USUARIOS(userID)
)
"""

TABLA_LADDER_STATS = """
CREATE TABLE IF NOT EXISTS LADDER_STATS (
    userID INTEGER PRIMARY KEY,
    mmr_1v1 INTEGER DEFAULT 1000,
    mmr_2v2 INTEGER DEFAULT 1000,
    mmr_3v3 INTEGER DEFAULT 1000,
    victorias_1v1 INTEGER DEFAULT 0,
    derrotas_1v1 INTEGER DEFAULT 0,
    empates_1v1 INTEGER DEFAULT 0,
    victorias_2v2 INTEGER DEFAULT 0,
    derrotas_2v2 INTEGER DEFAULT 0,
    empates_2v2 INTEGER DEFAULT 0,
    victorias_3v3 INTEGER DEFAULT 0,
    derrotas_3v3 INTEGER DEFAULT 0,
    empates_3v3 INTEGER DEFAULT 0,
    racha_actual INTEGER DEFAULT 0,
    racha_maxima INTEGER DEFAULT 0,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ultima_batalla TIMESTAMP,
    FOREIGN KEY (userID) REFERENCES USUARIOS(userID)
)
"""

TABLA_HISTORIAL_BATALLAS = """
CREATE TABLE IF NOT EXISTS HISTORIAL_BATALLAS (
    batalla_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ganador_id INTEGER,
    perdedor_id INTEGER,
    tipo_batalla VARCHAR(10),
    mmr_ganador_antes INTEGER,
    mmr_ganador_despues INTEGER,
    mmr_perdedor_antes INTEGER,
    mmr_perdedor_despues INTEGER,
    cambio_mmr INTEGER,
    fecha_batalla TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ganador_id) REFERENCES USUARIOS(userID),
    FOREIGN KEY (perdedor_id) REFERENCES USUARIOS(userID)
)
"""

TABLA_LIDERES_GIMNASIO = """
CREATE TABLE IF NOT EXISTS LIDERES_GIMNASIO (
    lider_id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    titulo TEXT,
    tipo_especialidad TEXT NOT NULL,
    medalla TEXT NOT NULL,
    nivel_equipo INTEGER DEFAULT 20,
    recompensa_base INTEGER DEFAULT 2000,
    descripcion TEXT,
    activo INTEGER DEFAULT 1
)
"""

TABLA_MEDALLAS_USUARIOS = """
CREATE TABLE IF NOT EXISTS MEDALLAS_USUARIOS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    userID INTEGER NOT NULL,
    lider_id TEXT NOT NULL,
    fecha_obtencion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    intentos INTEGER DEFAULT 1,
    FOREIGN KEY (userID) REFERENCES USUARIOS(userID),
    FOREIGN KEY (lider_id) REFERENCES LIDERES_GIMNASIO(lider_id),
    UNIQUE(userID, lider_id)
)
"""

TABLA_GUARDERIA = """
CREATE TABLE IF NOT EXISTS GUARDERIA (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    userID     INTEGER NOT NULL,
    pokemon_id INTEGER NOT NULL,
    fecha      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    slot TEXT DEFAULT 'poke1',
    FOREIGN KEY (userID)     REFERENCES USUARIOS(userID),
    FOREIGN KEY (pokemon_id) REFERENCES POKEMON_USUARIO(id_unico)
);
"""

TABLA_CRIANZA = """
CREATE TABLE IF NOT EXISTS CRIANZA (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    userID INTEGER NOT NULL,
    pokemon_padre_id INTEGER NOT NULL,
    pokemon_madre_id INTEGER NOT NULL,
    fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_eclosion TIMESTAMP,
    huevo_eclosionado BOOLEAN DEFAULT 0,
    pasos_necesarios INTEGER DEFAULT 5000,
    pasos_actuales INTEGER DEFAULT 0,
    FOREIGN KEY (userID) REFERENCES USUARIOS(userID),
    FOREIGN KEY (pokemon_padre_id) REFERENCES POKEMON_USUARIO(id_unico),
    FOREIGN KEY (pokemon_madre_id) REFERENCES POKEMON_USUARIO(id_unico)
)
"""

TABLA_HUEVOS = """
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
);
"""

TABLA_POKEDEX_USUARIO = """
CREATE TABLE IF NOT EXISTS POKEDEX_USUARIO (
    userID      INTEGER NOT NULL,
    pokemonID   INTEGER NOT NULL,
    avistado    INTEGER DEFAULT 1,   -- 1 = visto en encuentro/batalla
    capturado   INTEGER DEFAULT 0,   -- 1 = alguna vez capturado
    fecha_vista      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_captura    TIMESTAMP,
    PRIMARY KEY (userID, pokemonID),
    FOREIGN KEY (userID) REFERENCES USUARIOS(userID)
)
"""

# ============== JUAN (El caballo de los memes) ==============

TABLA_JUAN_MIEMBROS = """
CREATE TABLE IF NOT EXISTS JUAN_MIEMBROS (
    user_id     INTEGER PRIMARY KEY,
    nombre      TEXT NOT NULL,
    username    TEXT,
    descripcion TEXT
)
"""

TABLA_JUAN_APRENDIZAJE = """
CREATE TABLE IF NOT EXISTS JUAN_APRENDIZAJE (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria        TEXT NOT NULL,
    frase            TEXT NOT NULL,
    autor            TEXT,
    fuente_username  TEXT,
    fecha            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(categoria, frase)
)
"""

# ============== LISTA DE TODAS LAS TABLAS ==============

TODAS_LAS_TABLAS = [
    TABLA_USUARIOS,
    TABLA_EXMIEMBROS,
    TABLA_ROLES,
    TABLA_RECORDS,
    TABLA_SOLICITUDES,
    TABLA_APUESTAS,
    TABLA_MISIONES,
    TABLA_INVENTARIOS,
    TABLA_POKEMON_USUARIO,
    TABLA_INVENTARIO_USUARIO,
    TABLA_INTERCAMBIOS_HISTORIAL,
    TABLA_LOGROS_USUARIOS,
    TABLA_LADDER_STATS,
    TABLA_HISTORIAL_BATALLAS,
    TABLA_LIDERES_GIMNASIO,
    TABLA_MEDALLAS_USUARIOS,
    TABLA_GUARDERIA,
    TABLA_HUEVOS,
    TABLA_POKEDEX_USUARIO,
    TABLA_JUAN_MIEMBROS,
    TABLA_JUAN_APRENDIZAJE,
]

# ============== ÍNDICES ==============

INDICES = [
    "CREATE INDEX IF NOT EXISTS idx_inventarios_user ON INVENTARIOS(userID)",
    "CREATE INDEX IF NOT EXISTS idx_inventarios_carta ON INVENTARIOS(cartaID)",
    "CREATE INDEX IF NOT EXISTS idx_pokemon_usuario_user ON POKEMON_USUARIO(userID)",
    "CREATE INDEX IF NOT EXISTS idx_pokemon_usuario_equipo ON POKEMON_USUARIO(en_equipo)",
    "CREATE INDEX IF NOT EXISTS idx_inventario_usuario_user ON INVENTARIO_USUARIO(userID)",
    "CREATE INDEX IF NOT EXISTS idx_guarderia_user ON GUARDERIA(userID)",
    "CREATE INDEX IF NOT EXISTS idx_huevos_user_eco ON HUEVOS(userID, eclosionado)",
    "CREATE INDEX IF NOT EXISTS idx_pokemon_sexo ON POKEMON_USUARIO(userID, sexo)",
    "CREATE INDEX IF NOT EXISTS idx_pokedex_user ON POKEDEX_USUARIO(userID)",
]

# ============== DATOS INICIALES ==============

LIDERES_GIMNASIO = [
    ("brock", "Brock", "El Titán Roca", "Roca", "Medalla Roca", 14, 1400, "Especialista en Pokémon tipo Roca", 1),
    ("misty", "Misty", "La Sirena Cascada", "Agua", "Medalla Cascada", 21, 2100, "Especialista en Pokémon tipo Agua", 1),
    ("surge", "Lt. Surge", "El Americano Relámpago", "Eléctrico", "Medalla Trueno", 24, 2400, "Especialista en Pokémon tipo Eléctrico", 1),
    ("erika", "Erika", "La Princesa de la Naturaleza", "Planta", "Medalla Arcoíris", 29, 2900, "Especialista en Pokémon tipo Planta", 1),
    ("koga", "Koga", "El Ninja Venenoso", "Veneno", "Medalla Alma", 43, 4300, "Especialista en Pokémon tipo Veneno", 1),
    ("sabrina", "Sabrina", "La Amo Psíquica", "Psíquico", "Medalla Pantano", 43, 4300, "Especialista en Pokémon tipo Psíquico", 1),
    ("blaine", "Blaine", "El Hombre Llama", "Fuego", "Medalla Volcán", 47, 4700, "Especialista en Pokémon tipo Fuego", 1),
    ("giovanni", "Giovanni", "El Jefe de Team Rocket", "Tierra", "Medalla Tierra", 50, 5000, "Especialista en Pokémon tipo Tierra", 1),
]