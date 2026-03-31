# -*- coding: utf-8 -*-
"""
Configuración de UniverseBot V2.0
"""

from pathlib import Path

# ============== RUTAS ==============
BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = str(BASE_DIR / "database" / "universebot.db")
LOG_FILE = str(BASE_DIR / "universebot.log")

# ============== TELEGRAM ==============
TELEGRAM_TOKEN = "7075385886:AAHRz6Q5UMv6O2Ja2SKxa2GpHRQukGjtnlc" #Pruebas
CANAL_ID = -1002069915034 #Pruebas
#TELEGRAM_TOKEN = "7199716836:AAFjgZuL5EuIzHgLRKJUJ_zcXgzMei2ZD3w"
#CANAL_ID = -1003159895833
TOKEN = TELEGRAM_TOKEN  # Alias para compatibilidad
LOG_GROUP_ID = -1002002779047

# ============== BASE DE DATOS ==============
DB_TIMEOUT = 30.0
DB_CHECK_SAME_THREAD = False

# ============== THREADS ==============
CASINO = 3564 
#CASINO = 884 #Test
ROLES = 735
#ROLES = 2 #TEST 
ENTREVISTAS = 2856
EVENTOS = 2655
DEPORTES = 3056
#POKECLUB = 406145
POKECLUB = 884 #TEST

# ============== ENTREVISTAS ==============
CANAL_ENTREVISTAS = ENTREVISTAS
ENTREVISTADORES = []
INVITADOS_TEMPORALES = []

# ============== POKÉMON ==============
POKEMON_THREAD = POKECLUB
POKEMON_REGION_SERVIDOR = "JHOTO"  # ✅ Agregado para batalla_vgc_service
# Multiplicador de EXP respecto a los juegos oficiales.
# 1.0 = idéntico a los juegos. 2.0 = la mitad de batallas necesarias para subir de nivel.
POKEMON_EXP_MULTIPLIER = 10.0

POKEMON_SPAWN_CONFIG = {
    "habilitado": True,
    "intervalo_minimo": 60,
    "intervalo_maximo": 300,
    "canal_id": CANAL_ID,
    "thread_id": POKECLUB,
    "probabilidad_shiny": 1/4096,
    "nivel_minimo": 5,
    "nivel_maximo": 50,
}

# ============== CAJA MISTERIOSA ==============
PROBABILIDAD_CAJA_MISTERIOSA = 0.01
CAJA_MISTERIOSA_REWARDS = {
    "cosmos_min": 100,
    "cosmos_max": 300,
    "puntos_min": 10,
    "puntos_max": 60
}

# ============== ECONOMÍA ==============
MONEDA_NOMBRE = "cosmos"
MONEDA_SIMBOLO = "✨"
RECOMPENSA_REGISTRO = 1000
RECOMPENSA_DIARIA = 500
RECOMPENSA_DIARIA_P = 100

# ============== CENTRO POKÉMON ==============
COSTO_CENTRO_POKEMON = 100

# ============== MENSAJES ==============
MSG_USUARIO_NO_REGISTRADO = "⚠️ No estás registrado. Usa /registrar"
MSG_SIN_PERMISOS = "❌ No tienes permisos"

# ============== ADMINISTRACIÓN ==============
ADMIN_IDS = []
APOSTADOR: int = 7767552612   # puede abrir/cerrar mesas de apuestas
LOG_LEVEL = "INFO"

# ============== RUTAS DE DATOS ==============
DATA_DIR = BASE_DIR / "data"
POKEDEX_JSON = str(DATA_DIR / "pokedex.json")
MOVES_JSON = str(DATA_DIR / "moves.json")
UNKNOWN_SPRITE = str(BASE_DIR / "src" / "pokemon" / "unknown.png")

# ============== POKEMON - NIVELES DE SPAWNS ==============
# Niveles de Pokémon salvajes según progreso en gimnasios
# Formato: número_de_medallas: (nivel_min, nivel_max)
NIVELES_SPAWN_POR_MEDALLAS = {
    0: (2, 5),      # Sin medallas: Nv. 2-7 (antes de Brock)
    1: (8, 12),     # 1 medalla: Nv. 8-12 (después Brock, antes Misty)
    2: (13, 18),    # 2 medallas: Nv. 13-18 (después Misty, antes Surge)
    3: (19, 24),    # 3 medallas: Nv. 19-24 (después Surge, antes Erika)
    4: (25, 32),    # 4 medallas: Nv. 25-32 (después Erika, antes Koga)
    5: (33, 40),    # 5 medallas: Nv. 33-40 (después Koga, antes Sabrina)
    6: (41, 47),    # 6 medallas: Nv. 41-47 (después Sabrina, antes Blaine)
    7: (48, 54),    # 7 medallas: Nv. 48-54 (después Blaine, antes Giovanni)
    8: (55, 60),    # 8 medallas: Nv. 55-60 (todas las medallas)
}

# Nivel por defecto si hay error
NIVEL_SPAWN_DEFAULT = (5, 10)

# ============== CONFIGURACIÓN SPRITE DESCONOCIDO ==============

# Ruta al sprite desconocido (GIF animado)
UNKNOWN_SPRITE = BASE_DIR / "src" / "unknow.png"
# Si no tienes el sprite, descarga uno o el sistema usará texto como fallback