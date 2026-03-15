"""
Configuración de Batallas Pokémon
Incluye reglas VGC, movimientos prohibidos, y configuración de región
"""

from pathlib import Path

# ============== CONFIGURACIÓN DE REGIÓN ==============
# Región activa del servidor (determina Pokémon salvajes y gimnasios)
REGION_SERVIDOR = "KANTO"  # Cambiar según servidor

# Regiones disponibles
REGIONES_DISPONIBLES = {
    "KANTO": {
        "pokemon_salvajes": list(range(1, 152)),  # IDs 1-151
        "gimnasios": 8,
        "alto_mando": ["Lorelei", "Bruno", "Agatha", "Lance", "Campeón Blue"],
        "nivel_alto_mando": [52, 53, 54, 56, 60]
    },
    "JOHTO": {
        "pokemon_salvajes": list(range(1, 252)),  # IDs 1-251
        "gimnasios": 8,
        "alto_mando": ["Will", "Koga", "Bruno", "Karen", "Campeón Lance"],
        "nivel_alto_mando": [55, 56, 57, 58, 62]
    },
    "HOENN": {
        "pokemon_salvajes": list(range(1, 387)),  # IDs 1-386
        "gimnasios": 8,
        "alto_mando": ["Sidney", "Phoebe", "Glacia", "Drake", "Campeón Steven"],
        "nivel_alto_mando": [60, 61, 62, 63, 65]
    },
    "SINNOH": {
        "pokemon_salvajes": list(range(1, 494)),  # IDs 1-493
        "gimnasios": 8,
        "alto_mando": ["Aaron", "Bertha", "Flint", "Lucian", "Campeón Cynthia"],
        "nivel_alto_mando": [65, 66, 67, 68, 70]
    },
    "TESELIA": {
        "pokemon_salvajes": list(range(1, 650)),  # IDs 1-649
        "gimnasios": 8,
        "alto_mando": ["Shauntal", "Grimsley", "Caitlin", "Marshal", "Campeón Alder"],
        "nivel_alto_mando": [70, 71, 72, 73, 75]
    },
    "KALOS": {
        "pokemon_salvajes": list(range(1, 722)),  # IDs 1-721
        "gimnasios": 8,
        "alto_mando": ["Malva", "Siebold", "Wikstrom", "Drasna", "Campeón Diantha"],
        "nivel_alto_mando": [75, 76, 77, 78, 80]
    },
    "ALOLA": {
        "pokemon_salvajes": list(range(1, 810)),  # IDs 1-809
        "gimnasios": 0,  # No tiene gimnasios, tiene pruebas
        "alto_mando": ["Kahili", "Olivia", "Acerola", "Molayne", "Campeón Kukui"],
        "nivel_alto_mando": [80, 81, 82, 83, 85]
    },
    "GALAR": {
        "pokemon_salvajes": list(range(1, 899)),  # IDs 1-898
        "gimnasios": 8,
        "alto_mando": [],  # Galar tiene Copa Campeón en vez de Alto Mando
        "nivel_alto_mando": []
    },
    "PALDEA": {
        "pokemon_salvajes": list(range(1, 1011)),  # IDs 1-1010
        "gimnasios": 8,
        "alto_mando": ["Rika", "Poppy", "Larry", "Hassel", "Campeón Geeta"],
        "nivel_alto_mando": [85, 86, 87, 88, 90]
    }
}

# ============== CONFIGURACIÓN DE SPAWN AUTOMÁTICO ==============
SPAWN_CONFIG = {
    "habilitado": True,
    "intervalo_minimo": 60,    # 1 minuto (en segundos)
    "intervalo_maximo": 300,   # 5 minutos (en segundos)
    "probabilidad_shiny": 1/4096,
    "probabilidad_legendario": 0.001,  # 0.1%
    "nivel_minimo": 5,
    "nivel_maximo": 50,
    "cooldown_usuario": 30,  # Segundos entre spawns por usuario
}

# ============== MOVIMIENTOS PROHIBIDOS EN PVP ==============
# Lista de movimientos que NO se pueden usar en batallas PVP
MOVIMIENTOS_PROHIBIDOS_PVP = [
    # Movimientos OHKO (One-Hit KO)
    "Fisura",
    "Guillotina",
    "Cuerno Taladro",
    "Frío Polar",
    
    # Movimientos de evasión excesiva
    "Doble Equipo",
    "Minimizar",
    
    # Movimientos de precisión extrema
    "Movimiento Exacto",  # Always hits
    
    # Movimientos que alteran el juego de forma extrema
    "Espacio Raro",  # Trick Room extremo
    
    # Claves especiales (si quieres prohibir más)
    # "Transformación",  # Depende de tu meta
    # "Mofa",  # Depende de tu meta
]

# Movimientos prohibidos en formato normalizado (lowercase)
MOVIMIENTOS_PROHIBIDOS_PVP_LOWER = [m.lower() for m in MOVIMIENTOS_PROHIBIDOS_PVP]

# ============== CONFIGURACIÓN DE BATALLAS VGC (2v2) ==============
BATALLA_VGC_CONFIG = {
    "formato": "2v2",  # Doubles
    "pokemon_por_equipo": 4,  # Llevas 4, luchas con 2
    "pokemon_activos": 2,  # 2 activos al mismo tiempo
    "timer_turno": 90,  # 90 segundos por turno
    "cambios_permitidos": True,
    "items_duplicados": False,  # No se pueden repetir items
    "limite_nivel": 50,  # Todos los Pokémon se ajustan a nivel 50
    "mega_evolucion_permitida": True,
    "z_moves_permitidos": False,  # Depende de la generación
    "dynamax_permitido": False,   # Depende de la generación
}

# ============== RESTRICCIONES DE POKÉMON EN VGC ==============
# Pokémon que NO se pueden usar en VGC competitivo
POKEMON_PROHIBIDOS_VGC = [
    # Legendarios prohibidos
    150, 151,  # Mewtwo, Mew
    249, 250, 251,  # Lugia, Ho-Oh, Celebi
    382, 383, 384,  # Kyogre, Groudon, Rayquaza
    483, 484, 487, 493,  # Dialga, Palkia, Giratina, Arceus
    643, 644, 646, 649,  # Reshiram, Zekrom, Kyurem, Genesect
    716, 717, 718,  # Xerneas, Yveltal, Zygarde
    789, 790, 791, 792, 800, 801,  # Cosmog, Cosmoem, Solgaleo, Lunala, Necrozma, Magearna
    888, 889, 890,  # Zacian, Zamazenta, Eternatus
    # Agregar más según necesites
]

# ============== REGLAS DE ALTO MANDO ==============
ALTO_MANDO_CONFIG = {
    "equipos_fijos": True,  # Los equipos del Alto Mando son fijos
    "sin_items": False,  # El Alto Mando puede usar items
    "sin_cambios": False,  # El jugador puede cambiar
    "recompensa_victoria": {
        "creditos": 50000,
        "masterball": 1,
        "titulo": "Campeón de {region}",
        "salon_fama": True,
    },
    "requisitos": {
        "medallas": 8,  # Necesitas las 8 medallas
        "nivel_minimo_equipo": 50,  # Nivel mínimo de tu equipo
    }
}

# ============== SALÓN DE LA FAMA ==============
SALON_FAMA_CONFIG = {
    "ruta_imagenes": Path("./src/salon_fama/"),
    "formato_imagen": "png",
    "resolucion": (1920, 1080),
    "incluir_datos": [
        "nombre_usuario",
        "fecha",
        "equipo_pokemon",
        "region",
        "tiempo_jugado"
    ]
}

# ============== FUNCIONES HELPER ==============

def obtener_config_region():
    """Obtiene la configuración de la región activa"""
    return REGIONES_DISPONIBLES.get(REGION_SERVIDOR, REGIONES_DISPONIBLES["KANTO"])

def es_movimiento_prohibido_pvp(movimiento: str) -> bool:
    """Verifica si un movimiento está prohibido en PVP"""
    return movimiento.lower() in MOVIMIENTOS_PROHIBIDOS_PVP_LOWER

def es_pokemon_prohibido_vgc(pokemon_id: int) -> bool:
    """Verifica si un Pokémon está prohibido en VGC"""
    return pokemon_id in POKEMON_PROHIBIDOS_VGC

def puede_desafiar_alto_mando(medallas: int, nivel_equipo: int) -> tuple:
    """
    Verifica si un jugador puede desafiar al Alto Mando
    
    Returns:
        (puede, mensaje_error)
    """
    requisitos = ALTO_MANDO_CONFIG["requisitos"]
    
    if medallas < requisitos["medallas"]:
        return False, f"Necesitas {requisitos['medallas']} medallas (tienes {medallas})"
    
    if nivel_equipo < requisitos["nivel_minimo_equipo"]:
        return False, f"Tu equipo debe tener al menos nivel {requisitos['nivel_minimo_equipo']}"
    
    return True, ""

def validar_equipo_pvp(equipo: list) -> tuple:
    """
    Valida un equipo para batalla PVP
    
    Args:
        equipo: Lista de Pokémon con sus movimientos
    
    Returns:
        (valido, lista_errores)
    """
    errores = []
    
    for pokemon in equipo:
        pokemon_id = pokemon.get('pokemonID')
        movimientos = pokemon.get('movimientos', [])
        
        # Verificar movimientos prohibidos
        for mov in movimientos:
            if es_movimiento_prohibido_pvp(mov):
                nombre = pokemon.get('nombre', f'Pokémon #{pokemon_id}')
                errores.append(f"{nombre} tiene el movimiento prohibido: {mov}")
    
    return len(errores) == 0, errores

def validar_equipo_vgc(equipo: list) -> tuple:
    """
    Valida un equipo para batalla VGC
    
    Args:
        equipo: Lista de Pokémon
    
    Returns:
        (valido, lista_errores)
    """
    errores = []
    
    # Verificar tamaño del equipo
    if len(equipo) < BATALLA_VGC_CONFIG["pokemon_por_equipo"]:
        errores.append(f"Necesitas al menos {BATALLA_VGC_CONFIG['pokemon_por_equipo']} Pokémon")
    
    # Verificar Pokémon prohibidos
    for pokemon in equipo:
        pokemon_id = pokemon.get('pokemonID')
        
        if es_pokemon_prohibido_vgc(pokemon_id):
            nombre = pokemon.get('nombre', f'Pokémon #{pokemon_id}')
            errores.append(f"{nombre} está prohibido en VGC")
    
    # Verificar movimientos prohibidos
    valido_pvp, errores_pvp = validar_equipo_pvp(equipo)
    errores.extend(errores_pvp)
    
    # Verificar items duplicados
    if not BATALLA_VGC_CONFIG["items_duplicados"]:
        items_usados = {}
        for pokemon in equipo:
            item = pokemon.get('item_equipado')
            if item:
                if item in items_usados:
                    errores.append(f"Item duplicado: {item}")
                items_usados[item] = True
    
    return len(errores) == 0, errores


# ============== EXPORTAR ==============
__all__ = [
    'REGION_SERVIDOR',
    'REGIONES_DISPONIBLES',
    'SPAWN_CONFIG',
    'MOVIMIENTOS_PROHIBIDOS_PVP',
    'BATALLA_VGC_CONFIG',
    'POKEMON_PROHIBIDOS_VGC',
    'ALTO_MANDO_CONFIG',
    'SALON_FAMA_CONFIG',
    'obtener_config_region',
    'es_movimiento_prohibido_pvp',
    'es_pokemon_prohibido_vgc',
    'puede_desafiar_alto_mando',
    'validar_equipo_pvp',
    'validar_equipo_vgc'
]
