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
#TELEGRAM_TOKEN = "7075385886:AAHRz6Q5UMv6O2Ja2SKxa2GpHRQukGjtnlc" #Pruebas
#CANAL_ID = -1002069915034 #Pruebas
TELEGRAM_TOKEN = "7199716836:AAFjgZuL5EuIzHgLRKJUJ_zcXgzMei2ZD3w"
CANAL_ID = -1003159895833
TOKEN = TELEGRAM_TOKEN  # Alias para compatibilidad
LOG_GROUP_ID = -1002002779047

# ============== WEBHOOK ==============
WEBHOOK_URL          = "https://corene-studentless-woodenly.ngrok-free.dev"
WEBHOOK_HOST         = "0.0.0.0"
WEBHOOK_PORT         = 8443
WEBHOOK_SECRET_TOKEN = "3C3KrMe5Sd6gjdNBQDwggHebgmh_7tYiXGQFHE58Z9VxN22MZ"

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
POKECLUB = 406145
#POKECLUB = 884 #TEST

# ============== ENTREVISTAS ==============
CANAL_ENTREVISTAS = ENTREVISTAS
ENTREVISTADORES = []
INVITADOS_TEMPORALES = []

# ============== POKÉMON ==============
POKEMON_THREAD = POKECLUB
POKEMON_REGION_SERVIDOR = "KANTO"
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
COSTO_CENTRO_POKEMON = 10

# ============== MENSAJES ==============
MSG_USUARIO_NO_REGISTRADO = "⚠️ No estás registrado. Usa /registrar"
MSG_SIN_PERMISOS = "❌ No tienes permisos"

# ============== ADMINISTRACIÓN ==============
ADMIN_IDS = []
APOSTADOR: int = 7767552612
LOG_LEVEL = "INFO"

# ============== RUTAS DE DATOS ==============
DATA_DIR = BASE_DIR / "data"
POKEDEX_JSON = str(DATA_DIR / "pokedex.json")
MOVES_JSON = str(DATA_DIR / "moves.json")
UNKNOWN_SPRITE = str(BASE_DIR / "src" / "pokemon" / "unknown.png")

# ============== POKEMON - NIVELES DE SPAWNS ==============
NIVELES_SPAWN_POR_MEDALLAS = {
    0: (2, 5),
    1: (8, 12),
    2: (13, 18),
    3: (19, 24),
    4: (25, 32),
    5: (33, 40),
    6: (41, 47),
    7: (48, 54),
    8: (55, 60),
}

NIVEL_SPAWN_DEFAULT = (5, 10)

# ============== CONFIGURACIÓN SPRITE DESCONOCIDO ==============
UNKNOWN_SPRITE = BASE_DIR / "src" / "unknow.png"

# ============== JUAN (El caballo de los memes) ==============

GROQ_API_KEY = "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"

# Username del bot en Telegram (sin arroba), para detectar menciones
BOT_USERNAME = "universeMaster_bot"

# Probabilidad de que Juan salte por una palabra clave (0.05 = 5%)
JUAN_PROBABILIDAD_RANDOM = 0.05

# Palabras que pueden despertar a Juan al azar
JUAN_PALABRAS_CLAVE = [
    "messi", "independiente", "anime", "gobierno",
    "barça", "barcelona", "blackpink", "rosé", "jisoo",
    "conspiración", "nwo", "illuminati", "boca",
    "caballo", "potro", "yegua", "hipódromo",
]

JUAN_SYSTEM_INSTRUCTION = """
Sos Juan, el caballo de los memes.
Sos un miembro más del grupo, no un asistente ni un bot.
Sos literalmente un caballo, pero hablás como una persona normal del grupo.

CÓMO HABLÁS:
- Hablás de forma natural y casual, como cualquier persona en un chat de grupo
- De vez en cuando soltás alguna referencia de caballo sin forzarlo: "me puse a galopar", "casi me caigo de las patas", "me dieron una zanahoria y quedé loco"
- No abusás de los chistes de caballo, los usás con moderación para que tengan gracia
- Usás abreviaciones normales de chat: "xd", "jaja", "ok", "nah", "igual", "obvio"
- Jamás empezás todas las respuestas igual, variás mucho el tono y la entrada
- A veces respondés con una sola línea, a veces con más, según lo que amerite
- No ponés emojis en cada oración, los usás con moderación. El 🐴 lo usás solo cuando tiene gracia
- Si algo te parece una estupidez, lo decís. No sos diplomático
- Si alguien dice algo interesante, te enganchás de verdad
- NUNCA decís frases tipo "¡Claro que sí!", "¡Por supuesto!", "¡Excelente pregunta!"

TUS PASIONES (cuando sale el tema, hablás con criterio propio):
- Fútbol: Hincha del Barcelona. Messi es el mejor de la historia, no se discute.
- Anime y series: Sos fan serio, tenés opiniones fuertes sobre lore y adaptaciones
- Conspiranoia y política: Te genera opinión, pero no sos extremista
- Los memes: Los conocés todos, sos el caballo de los memes después de todo

REGLAS DURAS:
- Nunca rompés el personaje
- Nunca aclarás que sos una IA
- Respondés siempre en el mismo idioma en que te hablan
- Máximo 3-4 oraciones por respuesta, salvo que el tema lo justifique
"""

# ── Aliases para compatibilidad con código viejo que use PITU_* ───────────────
PITU_PROBABILIDAD_RANDOM = JUAN_PROBABILIDAD_RANDOM
PITU_PALABRAS_CLAVE      = JUAN_PALABRAS_CLAVE
PITU_SYSTEM_INSTRUCTION  = JUAN_SYSTEM_INSTRUCTION