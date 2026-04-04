# -*- coding: utf-8 -*-
"""
Sistema COMPLETO de Items - Integrado de Unibot_old
Base: 1 Pokeball = 1 cosmos
Más de 200 items funcionales
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# ========== POKÉBALLS (1-10 cosmos) ==========
POKEBALLS_DB = {
    # Básicas
    "pokeball": {"precio": 1, "ratio": 1.0, "desc": "Poké Ball estándar"},
    "greatball": {"precio": 3, "ratio": 1.5, "desc": "Super Ball - 1.5x captura"},
    "ultraball": {"precio": 6, "ratio": 2.0, "desc": "Ultra Ball - 2x captura"},
    "masterball": {"precio": 999999, "ratio": 255.0, "desc": "Master Ball - captura garantizada (NO VENDIBLE)"},
    
    # Especiales
    "premierball": {"precio": 1, "ratio": 1.0, "desc": "Honor Ball - cosmética"},
    "cherishball": {"precio": 999999, "ratio": 1.0, "desc": "Gloria Ball - eventos (NO VENDIBLE)"},
    
    # Condicionales (5 cosmos)
    "quickball": {"precio": 5, "ratio": 5.0, "condicion": "primer_turno", "desc": "Veloz Ball - 5x en turno 1"},
    "timerball": {"precio": 5, "ratio": 1.0, "condicion": "turnos", "desc": "Turno Ball - mejora con turnos"},
    "repeatball": {"precio": 5, "ratio": 3.5, "condicion": "capturado", "desc": "Acopio Ball - 3.5x si ya capturaste"},
    "netball": {"precio": 5, "ratio": 3.5, "condicion": "agua_bicho", "desc": "Red Ball - 3.5x vs Agua/Bicho"},
    "nestball": {"precio": 5, "ratio": 1.0, "condicion": "bajo_nivel", "desc": "Nido Ball - mejor vs bajo nivel"},
    "diveball": {"precio": 5, "ratio": 3.5, "condicion": "bajo_agua", "desc": "Buceo Ball - 3.5x bajo agua"},
    "duskball": {"precio": 5, "ratio": 3.5, "condicion": "noche_cueva", "desc": "Ocaso Ball - 3.5x noche/cueva"},
    "luxuryball": {"precio": 5, "ratio": 1.0, "amistad": 2.0, "desc": "Lujo Ball - amistad crece más rápido"},
    "healball": {"precio": 5, "ratio": 1.0, "cura_captura": True, "desc": "Sana Ball - cura al capturar"},
    
    # Apricorn Balls (5 cosmos)
    "levelball": {"precio": 5, "ratio": 8.0, "condicion": "nivel_mayor", "desc": "Nivel Ball - mejor si eres mayor nivel"},
    "lureball": {"precio": 5, "ratio": 5.0, "condicion": "pescado", "desc": "Cebo Ball - 5x pescados"},
    "moonball": {"precio": 5, "ratio": 4.0, "condicion": "piedra_lunar", "desc": "Luna Ball - 4x evos Piedra Lunar"},
    "friendball": {"precio": 5, "ratio": 1.0, "amistad_max": True, "desc": "Amigo Ball - amistad inmediata"},
    "loveball": {"precio": 5, "ratio": 8.0, "condicion": "mismo_sexo", "desc": "Amor Ball - 8x mismo sexo/especie"},
    "heavyball": {"precio": 5, "ratio": 1.0, "condicion": "peso", "desc": "Peso Ball - mejor vs pesados"},
    "fastball": {"precio": 5, "ratio": 4.0, "condicion": "velocidad", "desc": "Rápida Ball - 4x vs rápidos"},
    
    # Especiales raras
    "sportball": {"precio": 999999, "ratio": 1.5, "desc": "Competi Ball (NO VENDIBLE)"},
    "safariball": {"precio": 999999, "ratio": 1.5, "desc": "Safari Ball (NO VENDIBLE)"},
    "parkball": {"precio": 999999, "ratio": 255.0, "desc": "Parque Ball (NO VENDIBLE)"},
    "dreamball": {"precio": 10, "ratio": 4.0, "condicion": "dormido", "desc": "Ensueño Ball - 4x vs dormidos"},
    "beastball": {"precio": 10, "ratio": 5.0, "condicion": "ultraente", "desc": "Ente Ball - 5x vs Ultraentes"},
}

# ========== MEDICINAS (2-50 cosmos) ==========
MEDICINAS_DB = {
    # Pociones HP
    "potion": {"precio": 2, "cura_hp": 20, "desc": "Poción - restaura 20 HP"},
    "superpotion": {"precio": 4, "cura_hp": 60, "desc": "Superpoción - restaura 60 HP"},
    "hyperpotion": {"precio": 8, "cura_hp": 120, "desc": "Hiperpoción - restaura 120 HP"},
    "maxpotion": {"precio": 13, "cura_hp": 9999, "desc": "Poción Máxima - restaura todo el HP"},
    "fullrestore": {"precio": 15, "cura_hp": 9999, "cura_estado": True, "desc": "Restaurar Todo - cura HP y estado"},
    "berryjuice": {"precio": 5, "cura_hp": 20, "desc": "Zumo de Baya - restaura 20 HP"},
    
    # Revivir
    "revive": {"precio": 10, "revive": 0.5, "desc": "Revivir - revive con 50% HP"},
    "maxrevive": {"precio": 20, "revive": 1.0, "desc": "Revivir Máximo - revive con HP completo"},
    "sacredash": {"precio": 50, "revive_todos": True, "desc": "Ceniza Sagrada - revive todo el equipo"},
    
    # Curar Estados
    "antidote": {"precio": 1, "cura_estado": "envenenado", "desc": "Antídoto - cura envenenamiento"},
    "awakening": {"precio": 2, "cura_estado": "dormido", "desc": "Despertar - cura sueño"},
    "burnheal": {"precio": 2, "cura_estado": "quemado", "desc": "Antiquemar - cura quemaduras"},
    "paralyzeheal": {"precio": 2, "cura_estado": "paralizado", "desc": "Antiparalizar - cura parálisis"},
    "iceheal": {"precio": 2, "cura_estado": "congelado", "desc": "Antihielo - descongela"},
    "fullheal": {"precio": 3, "cura_todos_estados": True, "desc": "Cura Total - cura todos los estados"},
    "lavacookie": {"precio": 3, "cura_todos_estados": True, "desc": "Galleta Lava - cura todos los estados"},
    "oldgateau": {"precio": 3, "cura_todos_estados": True, "desc": "Barquillos - cura todos los estados"},
    
    # PP
    "ether": {"precio": 6, "pp": 10, "desc": "Éter - restaura 10 PP a un movimiento"},
    "maxether": {"precio": 12, "pp": 999, "desc": "Éter Máximo - restaura PP completo a un move"},
    "elixir": {"precio": 15, "pp_todos": 10, "desc": "Elixir - restaura 10 PP a todos los moves"},
    "maxelixir": {"precio": 30, "pp_todos": 999, "desc": "Elixir Máximo - restaura PP completo a todos"},
    "ppup": {"precio": 50, "pp_max": 3, "desc": "Más PP - +3 PP máximo permanente"},
    "ppmax": {"precio": 150, "pp_max": 9, "desc": "PP Máximos - +9 PP máximo permanente"},
}

# ========== VITAMINAS (50-500 cosmos) ==========
VITAMINAS_DB = {
    # Vitaminas base (50 cosmos)
    "hpup": {"precio": 50, "ev": "hp", "cantidad": 10,"tipo": "vitamina", "desc": "Más PS - +10 EVs HP"},
    "protein": {"precio": 50, "ev": "atq", "cantidad": 10,"tipo": "vitamina", "desc": "Proteína - +10 EVs Ataque"},
    "iron": {"precio": 50, "ev": "def", "cantidad": 10,"tipo": "vitamina", "desc": "Hierro - +10 EVs Defensa"},
    "calcium": {"precio": 50, "ev": "atq_sp", "cantidad": 10,"tipo": "vitamina", "desc": "Calcio - +10 EVs At. Esp"},
    "zinc": {"precio": 50, "ev": "def_sp", "cantidad": 10,"tipo": "vitamina", "desc": "Zinc - +10 EVs Def. Esp"},
    "carbos": {"precio": 50, "ev": "vel", "cantidad": 10,"tipo": "vitamina", "desc": "Carburante - +10 EVs Velocidad"},
    
    # Plumas (10 cosmos)
    "healthfeather": {"precio": 10, "ev": "hp",     "cantidad": 1, "tipo": "vitamina", "desc": "Pluma Salud - +1 EV HP"},
    "musclefeather": {"precio": 10, "ev": "atq",    "cantidad": 1, "tipo": "vitamina", "desc": "Pluma Músculo - +1 EV Ataque"},
    "resistfeather": {"precio": 10, "ev": "def",    "cantidad": 1, "tipo": "vitamina", "desc": "Pluma Resistencia - +1 EV Defensa"},
    "geniusfeather": {"precio": 10, "ev": "atq_sp", "cantidad": 1, "tipo": "vitamina", "desc": "Pluma Intelecto - +1 EV At. Esp"},
    "cleverfeather": {"precio": 10, "ev": "def_sp", "cantidad": 1, "tipo": "vitamina", "desc": "Pluma Mente - +1 EV Def. Esp"},
    "swiftfeather":  {"precio": 10, "ev": "vel",    "cantidad": 1, "tipo": "vitamina", "desc": "Pluma Ímpetu - +1 EV Velocidad"},
    
    # Items especiales
    "abilitycapsule": {"precio": 1000, "cambia_habilidad": True,"tipo": "utilidad_especial", "desc": "Cápsula Habilidad - cambia habilidad"},
    "abilitypatch": {"precio": 2000, "habilidad_oculta": True,"tipo": "utilidad_especial", "desc": "Parche Habilidad - da habilidad oculta"},
    "bottlecap": {"precio": 500, "maximiza_iv": 1,"tipo": "utilidad_especial", "desc": "Chapa Plateada - maximiza 1 IV"},
    "goldbottlecap": {"precio": 3000, "maximiza_todos_iv": True,"tipo": "utilidad_especial", "desc": "Chapa Dorada - maximiza todos los IVs"},
    "expcandyxs": {"precio": 10,   "exp": 100,   "tipo": "utilidad_especial", "desc": "Caramelo Exp XS - +100 EXP"},
    "expcandys":  {"precio": 30,   "exp": 800,   "tipo": "utilidad_especial", "desc": "Caramelo Exp S - +800 EXP"},
    "expcandym":  {"precio": 100,  "exp": 3000,  "tipo": "utilidad_especial", "desc": "Caramelo Exp M - +3000 EXP"},
    "expcandyl":  {"precio": 300,  "exp": 10000, "tipo": "utilidad_especial", "desc": "Caramelo Exp L - +10000 EXP"},
    "expcandyxl": {"precio": 1000, "exp": 30000, "tipo": "utilidad_especial", "desc": "Caramelo Exp XL - +30000 EXP"},
    "rarecandy":  {"precio": 500,  "sube_nivel": 1, "tipo": "utilidad_especial", "desc": "Caramelo Raro - sube 1 nivel"},

    # ── Sueros reductores de EV (30 cosmos) ───────────────────────────────────
    "berryjuicehp":    {"precio": 30, "reduce_ev": "hp",     "cantidad": 10, "tipo": "vitamina", "desc": "Suero PS - -10 EVs HP"},
    "berryjuiceatq":   {"precio": 30, "reduce_ev": "atq",    "cantidad": 10, "tipo": "vitamina", "desc": "Suero Ataque - -10 EVs Ataque"},
    "berryjuicedef":   {"precio": 30, "reduce_ev": "def",    "cantidad": 10, "tipo": "vitamina", "desc": "Suero Defensa - -10 EVs Defensa"},
    "berryjuiceatqsp": {"precio": 30, "reduce_ev": "atq_sp", "cantidad": 10, "tipo": "vitamina", "desc": "Suero At.Esp - -10 EVs At. Esp"},
    "berryjuicedefsp": {"precio": 30, "reduce_ev": "def_sp", "cantidad": 10, "tipo": "vitamina", "desc": "Suero Df.Esp - -10 EVs Def. Esp"},
    "berryjuicevel":   {"precio": 30, "reduce_ev": "vel",    "cantidad": 10, "tipo": "vitamina", "desc": "Suero Velocidad - -10 EVs Velocidad"},
}

# ========== PIEDRAS EVOLUTIVAS (15-25 cosmos) ==========
PIEDRAS_EVOLUTIVAS_DB = {
    "firestone": {"precio": 15, "tipo": "evolucion", "desc": "Piedra Fuego - evoluciona tipo Fuego"},
    "waterstone": {"precio": 15, "tipo": "evolucion", "desc": "Piedra Agua - evoluciona tipo Agua"},
    "thunderstone": {"precio": 15, "tipo": "evolucion", "desc": "Piedra Trueno - evoluciona tipo Eléctrico"},
    "leafstone": {"precio": 15, "tipo": "evolucion", "desc": "Piedra Hoja - evoluciona tipo Planta"},
    "moonstone": {"precio": 15, "tipo": "evolucion", "desc": "Piedra Lunar - evoluciona ciertos Pokémon"},
    "sunstone": {"precio": 15, "tipo": "evolucion", "desc": "Piedra Solar - evoluciona ciertos Pokémon"},
    "shinystone": {"precio": 20, "tipo": "evolucion", "desc": "Piedra Día - evoluciona ciertos Pokémon"},
    "duskstone": {"precio": 20, "tipo": "evolucion", "desc": "Piedra Noche - evoluciona ciertos Pokémon"},
    "dawnstone": {"precio": 20, "tipo": "evolucion", "desc": "Piedra Alba - evoluciona ciertos Pokémon"},
    "icestone": {"precio": 20, "tipo": "evolucion", "desc": "Piedra Hielo - evoluciona tipo Hielo"},
    "ovalstone": {"precio": 15, "tipo": "evolucion", "desc": "Piedra Oval - evoluciona Chansey"},
}

# ========== OBJETOS DE INTERCAMBIO (25-40 cosmos) ==========
OBJETOS_INTERCAMBIO_DB = {
    "deepseatooth": {"precio": 25, "intercambio_clamperl": "huntail", "desc": "Diente Marino - Clamperl→Huntail"},
    "deepseascale": {"precio": 25, "intercambio_clamperl": "gorebyss", "desc": "Escama Marina - Clamperl→Gorebyss"},
    "dragonscale": {"precio": 25, "intercambio_seadra": "kingdra", "desc": "Escama Dragón - Seadra→Kingdra"},
    "electirizer": {"precio": 30, "intercambio_electabuzz": "electivire", "desc": "Electrizador - Electabuzz→Electivire"},
    "kingsrock": {"precio": 25, "intercambio_slowpoke_poliwhirl": True, "desc": "Roca del Rey - evoluciona varios"},
    "magmarizer": {"precio": 30, "intercambio_magmar": "magmortar", "desc": "Magmatizador - Magmar→Magmortar"},
    "metalcoat": {"precio": 25, "intercambio_onix_scyther": True, "desc": "Revestimiento Metálico - evoluciona Acero"},
    "prismscale": {"precio": 25, "intercambio_feebas": "milotic", "desc": "Escama Bella - Feebas→Milotic"},
    "protector": {"precio": 30, "intercambio_rhydon": "rhyperior", "desc": "Protector - Rhydon→Rhyperior"},
    "reapercloth": {"precio": 30, "intercambio_dusclops": "dusknoir", "desc": "Tela Terrible - Dusclops→Dusknoir"},
    "upgrade": {"precio": 25, "intercambio_porygon": "porygon2", "desc": "Mejora - Porygon→Porygon2"},
    "dubiousdisc": {"precio": 30, "intercambio_porygon2": "porygonz", "desc": "Disco Extraño - Porygon2→Porygon-Z"},
}

# ========== CRIANZA (20-100 cosmos) ==========
CRIANZA_DB = {
    "everstone": {"precio": 20, "hereda_naturaleza": True, "desc": "Piedra Eterna - hereda naturaleza"},
    "destinyknot": {"precio": 50, "hereda_5ivs": True, "desc": "Lazo Destino - hereda 5 IVs"},
    "powerweight":  {"precio": 30, "hereda_iv": "hp",     "ev_bonus": "hp",     "desc": "Pesa Recia — +8 EVs PS por batalla"},
    "powerbracer":  {"precio": 30, "hereda_iv": "atq",    "ev_bonus": "atq",    "desc": "Brazal Recio — +8 EVs Ataque por batalla"},
    "powerbelt":    {"precio": 30, "hereda_iv": "def",    "ev_bonus": "def",    "desc": "Cinto Recio — +8 EVs Defensa por batalla"},
    "powerlens":    {"precio": 30, "hereda_iv": "atq_sp", "ev_bonus": "atq_sp", "desc": "Lente Recia — +8 EVs At.Esp por batalla"},
    "powerband":    {"precio": 30, "hereda_iv": "def_sp", "ev_bonus": "def_sp", "desc": "Banda Recia — +8 EVs Def.Esp por batalla"},
    "poweranklet":  {"precio": 30, "hereda_iv": "vel",    "ev_bonus": "vel",    "desc": "Franja Recia — +8 EVs Velocidad por batalla"},
    "ovalcharm": {"precio": 100, "mas_huevos": True, "desc": "Amuleto Oval - más probabilidad de huevos"},
    "shinycharm": {"precio": 999999, "mas_shiny": True, "desc": "Amuleto Iris - más shiny (NO VENDIBLE)"},
}

# ========== OBJETOS DE COMBATE - CHOICE (40 cosmos) ==========
CHOICE_ITEMS_DB = {
    "choiceband": {"precio": 40, "boost": {"atq": 1.5}, "lock": True, "desc": "Cinta Elección - 1.5x Ataque (queda bloqueado)"},
    "choicescarf": {"precio": 40, "boost": {"vel": 1.5}, "lock": True, "desc": "Pañuelo Elección - 1.5x Velocidad (queda bloqueado)"},
    "choicespecs": {"precio": 40, "boost": {"atq_sp": 1.5}, "lock": True, "desc": "Gafas Elección - 1.5x At.Esp (queda bloqueado)"},
}

# ========== OBJETOS DE COMBATE - POWER (35-70 cosmos) ==========
POWER_ITEMS_DB = {
    "lifeorb": {"precio": 70, "boost_daño": 1.3, "recoil": 0.1, "desc": "Vidasfera - 1.3x daño, pierde 10% HP"},
    "focussash": {"precio": 40, "sobrevive_1hp": True, "consumible": True, "desc": "Banda Focus - sobrevive con 1 HP"},
    "assaultvest": {"precio": 50, "boost": {"def_sp": 1.5}, "no_estado": True, "desc": "Chaleco Asalto - 1.5x Def.Esp, no mueve estado"},
    "expertbelt": {"precio": 35, "boost_superefectivo": 1.2, "desc": "Cinta Experto - 1.2x vs super efectivo"},
    "wiseglasses": {"precio": 35, "boost": {"atq_sp": 1.1}, "desc": "Gafas Especiales - 1.1x At. Esp"},
    "muscleband": {"precio": 35, "boost": {"atq": 1.1}, "desc": "Cinta Fuerte - 1.1x Ataque físico"},
    "scopelens": {"precio": 35, "boost_critico": 1, "desc": "Periscopio - +1 crítico"},
    "razorclaw": {"precio": 35, "boost_critico": 1, "desc": "Garra Afilada - +1 crítico"},
    "metronome": {"precio": 50, "boost_repeticion": 1.2, "desc": "Metrónomo - 1.2x si repites move"},
    "repartidor_exp": {"precio": 10000,"tipo": "utilidad_especial","equipable": True,"desc": "Reparte la EXP ganada entre TODO el equipo al equiparlo al líder."},
}

# ========== OBJETOS DEFENSIVOS (30-60 cosmos) ==========
DEFENSIVE_ITEMS_DB = {
    "leftovers": {"precio": 60, "heal_turno": 0.0625, "desc": "Restos - cura 1/16 HP por turno"},
    "blacksludge": {"precio": 50, "heal_turno_veneno": 0.0625, "daño_no_veneno": 0.125, "desc": "Lodo Negro - cura 1/16 (Veneno) o daña 1/8"},
    "shellbell": {"precio": 40, "heal_daño": 0.125, "desc": "Campana Concha - cura 1/8 del daño hecho"},
    "rockyhelmet": {"precio": 50, "daño_contacto": 0.167, "desc": "Casco Dentado - daña 1/6 HP al contacto"},
    "weaknesspolicy": {"precio": 60, "boost_tras_debilidad": {"atq": 2, "atq_sp": 2}, "consumible": True, "desc": "Seguro - +2 Atq/AtqSp tras super efectivo"},
    "airballoon": {"precio": 45, "inmune_tierra": True, "consumible": True, "desc": "Globo Helio - inmune a Tierra hasta recibir golpe"},
}

# ========== OBJETOS SITUACIONALES (30-90 cosmos) ==========
SITUATIONAL_ITEMS_DB = {
    "whiteherb": {"precio": 30, "restaura_debuffs": True, "consumible": True, "desc": "Hierba Blanca - restaura stats"},
    "mentalherb": {"precio": 30, "cura_atraccion": True, "consumible": True, "desc": "Hierba Mental - cura atracción"},
    "powerherb": {"precio": 40, "skip_carga": True, "consumible": True, "desc": "Hierba Única - salta turno de carga"},
    "safetygoggles": {"precio": 50, "inmune_clima": True, "inmune_polvos": True, "desc": "Gafas Protectoras - inmune clima y polvos"},
    "heavydutyboots": {"precio": 60, "inmune_hazards": True, "desc": "Botas Gruesas - inmune entry hazards"},
    "protectivepads": {"precio": 50, "ignora_contacto": True, "desc": "Paracontacto - ignora efectos de contacto"},
    "terrainextender": {"precio": 60, "extiende_terreno": True, "desc": "Piedra Tierra - terreno dura 8 turnos"},
    "roomservice": {"precio": 45, "baja_vel_trick_room": True, "consumible": True, "desc": "Servicio Raro - -1 Vel en Trick Room"},
    "electricseed": {"precio": 35, "boost_electric_terrain": {"def": 1}, "consumible": True, "desc": "Sem. Electrica - +1 Def en Campo Eléctrico"},
    "grassyseed": {"precio": 35, "boost_grassy_terrain": {"def": 1}, "consumible": True, "desc": "Sem. Hierba - +1 Def en Campo de Hierba"},
    "mistyseed": {"precio": 35, "boost_misty_terrain": {"def_sp": 1}, "consumible": True, "desc": "Sem. Bruma - +1 DefSp en Campo de Niebla"},
    "psychicseed": {"precio": 35, "boost_psychic_terrain": {"def_sp": 1}, "consumible": True, "desc": "Sem. Psíquica - +1 DefSp en Campo Psíquico"},
    "ejectbutton": {"precio": 40, "cambia_al_golpe": True, "consumible": True, "desc": "Botón Escape - cambia al ser golpeado"},
    "redcard": {"precio": 35, "expulsa_al_golpe": True, "consumible": True, "desc": "Tarjeta Roja - expulsa al que golpea"},
    "ejectpack": {"precio": 40, "cambia_si_bajan_stats": True, "consumible": True, "desc": "Mochila Escape - cambia si bajan stats"},
    "keeberry": {"precio": 40, "boost_def_fisico": True, "consumible": True, "desc": "Baya Kebia - +1 Def tras golpe físico"},
    "marangaberry": {"precio": 40, "boost_defsp_especial": True, "consumible": True, "desc": "Baya Maranga - +1 DefSp tras golpe especial"},
}

# ========== BAYAS (8-40 cosmos) ==========
BAYAS_DB = {
    # Curación HP
    "sitrusberry": {"precio": 15, "cura_hp_porcentaje": 0.25, "trigger_hp": 0.5, "desc": "Baya Zanama - cura 25% HP < 50%"},
    "oranberry": {"precio": 8, "cura_hp": 10, "trigger_hp": 0.5, "desc": "Baya Aranja - cura 10 HP < 50%"},
    "figyberry": {"precio": 12, "cura_hp_porcentaje": 0.33, "confunde_si_odia": "picante", "desc": "Baya Higog - cura 33% (confunde si odia picante)"},
    "wikiberry": {"precio": 12, "cura_hp_porcentaje": 0.33, "confunde_si_odia": "seco", "desc": "Baya Wiki - cura 33% (confunde si odia seco)"},
    "magoberry": {"precio": 12, "cura_hp_porcentaje": 0.33, "confunde_si_odia": "dulce", "desc": "Baya Ango - cura 33% (confunde si odia dulce)"},
    "aguavberry": {"precio": 12, "cura_hp_porcentaje": 0.33, "confunde_si_odia": "amargo", "desc": "Baya Guaya - cura 33% (confunde si odia amargo)"},
    "iapapaberry": {"precio": 12, "cura_hp_porcentaje": 0.33, "confunde_si_odia": "acido", "desc": "Baya Pabaya - cura 33% (confunde si odia ácido)"},
    
    # Curación de estados
    "lumberry": {"precio": 20, "cura_todos_estados": True, "desc": "Baya Lum - cura cualquier estado"},
    "persimberry": {"precio": 12, "cura_estado": "confuso", "desc": "Baya Caquic - cura confusión"},
    "cherryberry": {"precio": 12, "cura_estado": "paralizado", "desc": "Baya Zreza - cura parálisis"},
    "chestoberry": {"precio": 12, "cura_estado": "dormido", "desc": "Baya Atania - despierta"},
    "rawstberry": {"precio": 12, "cura_estado": "quemado", "desc": "Baya Frambu - cura quemadura"},
    "aspearberry": {"precio": 12, "cura_estado": "congelado", "desc": "Baya Perasi - descongela"},
    "pechaberry": {"precio": 12, "cura_estado": "envenenado", "desc": "Baya Meloc - cura veneno"},
    
    # Reducir daño de tipos
    "occaberry": {"precio": 15, "reduce_tipo": "fuego", "desc": "Baya Caoca - reduce Fuego 50%"},
    "passhoberry": {"precio": 15, "reduce_tipo": "agua", "desc": "Baya Pasio - reduce Agua 50%"},
    "wacanberry": {"precio": 15, "reduce_tipo": "electrico", "desc": "Baya Gualot - reduce Eléctrico 50%"},
    "rindoberry": {"precio": 15, "reduce_tipo": "planta", "desc": "Baya Acardo - reduce Planta 50%"},
    "yacheberry": {"precio": 15, "reduce_tipo": "hielo", "desc": "Baya Yecana - reduce Hielo 50%"},
    "chopleberry": {"precio": 15, "reduce_tipo": "lucha", "desc": "Baya Pomaro - reduce Lucha 50%"},
    "kebiaberry": {"precio": 15, "reduce_tipo": "veneno", "desc": "Baya Kebia - reduce Veneno 50%"},
    "shucaberry": {"precio": 15, "reduce_tipo": "tierra", "desc": "Baya Kouba - reduce Tierra 50%"},
    "cobaberry": {"precio": 15, "reduce_tipo": "volador", "desc": "Baya Payapa - reduce Volador 50%"},
    "payapaberry": {"precio": 15, "reduce_tipo": "psiquico", "desc": "Baya Ibano - reduce Psíquico 50%"},
    "tangaberry": {"precio": 15, "reduce_tipo": "bicho", "desc": "Baya Tanga - reduce Bicho 50%"},
    "chartiberry": {"precio": 15, "reduce_tipo": "roca", "desc": "Baya Charti - reduce Roca 50%"},
    "kasibberry": {"precio": 15, "reduce_tipo": "fantasma", "desc": "Baya Kasib - reduce Fantasma 50%"},
    "habanberry": {"precio": 15, "reduce_tipo": "dragon", "desc": "Baya Draco - reduce Dragón 50%"},
    "colburberry": {"precio": 15, "reduce_tipo": "siniestro", "desc": "Baya Babiri - reduce Siniestro 50%"},
    "babiriberry": {"precio": 15, "reduce_tipo": "acero", "desc": "Baya Colbur - reduce Acero 50%"},
    "chilanberry": {"precio": 15, "reduce_tipo": "normal", "desc": "Baya Chilan - reduce Normal 50%"},
    "roseliberry": {"precio": 15, "reduce_tipo": "hada", "desc": "Baya Hibis - reduce Hada 50%"},
    
    # Boost de stats
    "liechiberry": {"precio": 40, "boost_stat": {"atq": 1}, "trigger_hp": 0.25, "desc": "Baya Lichi - +1 Atq < 25% HP"},
    "ganlonberry": {"precio": 40, "boost_stat": {"def": 1}, "trigger_hp": 0.25, "desc": "Baya Gonlan - +1 Def < 25% HP"},
    "salacberry": {"precio": 40, "boost_stat": {"vel": 1}, "trigger_hp": 0.25, "desc": "Baya Safre - +1 Vel < 25% HP"},
    "petayaberry": {"precio": 40, "boost_stat": {"atq_sp": 1}, "trigger_hp": 0.25, "desc": "Baya Petaya - +1 AtqSp < 25% HP"},
    "apicotberry": {"precio": 40, "boost_stat": {"def_sp": 1}, "trigger_hp": 0.25, "desc": "Baya Aricot - +1 DefSp < 25% HP"},
    "starfberry": {"precio": 80, "boost_stat_random": 2, "trigger_hp": 0.25, "desc": "Baya Arabol - +2 stat random < 25% HP"},
    "enigmaberry": {"precio": 40, "cura_super_efectivo": True, "desc": "Baya Enigma - cura 25% tras super efectivo"},
    "micleberry": {"precio": 40, "boost_precision": True, "trigger_hp": 0.25, "desc": "Baya Lagro - +20% precisión < 25% HP"},
    "custapberry": {"precio": 40, "prioridad": True, "trigger_hp": 0.25, "desc": "Baya Chiri - prioridad < 25% HP"},
}

# ========== CLIMA Y TERRENO (50-70 cosmos) ==========
CLIMA_TERRENO_DB = {
    # Rocas de clima
    "heatrock": {"precio": 50, "extiende": "sol", "turnos": 8, "desc": "Roca Calor - Sol dura 8 turnos"},
    "damprock": {"precio": 50, "extiende": "lluvia", "turnos": 8, "desc": "Roca Lluvia - Lluvia dura 8 turnos"},
    "smoothrock": {"precio": 50, "extiende": "tormenta_arena", "turnos": 8, "desc": "Roca Lisa - Tormenta Arena dura 8 turnos"},
    "icyrock": {"precio": 50, "extiende": "granizo", "turnos": 8, "desc": "Roca Hielo - Granizo dura 8 turnos"},
    
    # Items de clima
    "utilityumbrella": {"precio": 60, "ignora_clima": True, "desc": "Parasol - ignora efectos del clima"},
    
    # Terreno
    "terrainextender": {"precio": 60, "extiende_terreno": True, "desc": "Piedra Tierra - terreno dura 8 turnos"},
}

# ========== POTENCIADORES DE TIPO (25-35 cosmos) ==========
TYPE_BOOST_DB = {
    "silkscarf": {"precio": 25, "boost_tipo": "normal", "multiplicador": 1.2, "desc": "Pañuelo Seda - 1.2x Normal"},
    "charcoal": {"precio": 25, "boost_tipo": "fuego", "multiplicador": 1.2, "desc": "Carbón - 1.2x Fuego"},
    "mysticwater": {"precio": 25, "boost_tipo": "agua", "multiplicador": 1.2, "desc": "Agua Mística - 1.2x Agua"},
    "magnet": {"precio": 25, "boost_tipo": "electrico", "multiplicador": 1.2, "desc": "Imán - 1.2x Eléctrico"},
    "miracleseed": {"precio": 25, "boost_tipo": "planta", "multiplicador": 1.2, "desc": "Semilla Milagro - 1.2x Planta"},
    "nevermeltice": {"precio": 25, "boost_tipo": "hielo", "multiplicador": 1.2, "desc": "Antiderretir - 1.2x Hielo"},
    "blackbelt": {"precio": 25, "boost_tipo": "lucha", "multiplicador": 1.2, "desc": "Cinturón Negro - 1.2x Lucha"},
    "poisonbarb": {"precio": 25, "boost_tipo": "veneno", "multiplicador": 1.2, "desc": "Flecha Venenosa - 1.2x Veneno"},
    "softsand": {"precio": 25, "boost_tipo": "tierra", "multiplicador": 1.2, "desc": "Arena Fina - 1.2x Tierra"},
    "sharpbeak": {"precio": 25, "boost_tipo": "volador", "multiplicador": 1.2, "desc": "Pico Afilado - 1.2x Volador"},
    "twistedspoon": {"precio": 25, "boost_tipo": "psiquico", "multiplicador": 1.2, "desc": "Cuchara Torcida - 1.2x Psíquico"},
    "silverpowder": {"precio": 25, "boost_tipo": "bicho", "multiplicador": 1.2, "desc": "Polvo Plata - 1.2x Bicho"},
    "hardstone": {"precio": 25, "boost_tipo": "roca", "multiplicador": 1.2, "desc": "Piedra Dura - 1.2x Roca"},
    "spelltag": {"precio": 25, "boost_tipo": "fantasma", "multiplicador": 1.2, "desc": "Hechizo - 1.2x Fantasma"},
    "dragonfang": {"precio": 25, "boost_tipo": "dragon", "multiplicador": 1.2, "desc": "Colmillo Dragón - 1.2x Dragón"},
    "blackglasses": {"precio": 25, "boost_tipo": "siniestro", "multiplicador": 1.2, "desc": "Gafas de Sol - 1.2x Siniestro"},
    "metalcoat": {"precio": 25, "boost_tipo": "acero", "multiplicador": 1.2, "desc": "Rev. Metálico - 1.2x Acero"},
    "fairyfeather": {"precio": 25, "boost_tipo": "hada", "multiplicador": 1.2, "desc": "Pluma Hada - 1.2x Hada"},
}

# ========== INCIENSOS (30 cosmos) ==========
INCIENSOS_DB = {
    "laxincense": {"precio": 30, "reduce_precision": 0.9, "desc": "Incienso Suave - rival 90% precisión"},
    "oddincense": {"precio": 30, "boost_tipo": "psiquico", "multiplicador": 1.2, "desc": "Incienso Raro - 1.2x Psíquico"},
    "rockincense": {"precio": 30, "boost_tipo": "roca", "multiplicador": 1.2, "desc": "Incienso Roca - 1.2x Roca"},
    "roseincense": {"precio": 30, "boost_tipo": "planta", "multiplicador": 1.2, "desc": "Incienso Flor - 1.2x Planta"},
    "seaincense": {"precio": 30, "boost_tipo": "agua", "multiplicador": 1.2, "desc": "Incienso Marino - 1.2x Agua"},
    "waveincense": {"precio": 30, "boost_tipo": "agua", "multiplicador": 1.2, "desc": "Incienso Aqua - 1.2x Agua"},
}

# ========== MEGASTONES (NO VENDIBLES) ==========
MEGASTONES_DB = {
    "venusaurite": {"precio": 999999, "megaevolucion": "Venusaur", "desc": "Venusaurita (NO VENDIBLE)"},
    "charizarditex": {"precio": 999999, "megaevolucion": "Charizard-X", "desc": "Charizardita X (NO VENDIBLE)"},
    "charizarditey": {"precio": 999999, "megaevolucion": "Charizard-Y", "desc": "Charizardita Y (NO VENDIBLE)"},
    "blastoisinite": {"precio": 999999, "megaevolucion": "Blastoise", "desc": "Blastoisita (NO VENDIBLE)"},
    "alakazite": {"precio": 999999, "megaevolucion": "Alakazam", "desc": "Alakazamita (NO VENDIBLE)"},
    "gengarite": {"precio": 999999, "megaevolucion": "Gengar", "desc": "Gengarita (NO VENDIBLE)"},
    "kangaskhanite": {"precio": 999999, "megaevolucion": "Kangaskhan", "desc": "Kangaskhanita (NO VENDIBLE)"},
    "gyaradosite": {"precio": 999999, "megaevolucion": "Gyarados", "desc": "Gyaradosita (NO VENDIBLE)"},
    "aerodactylite": {"precio": 999999, "megaevolucion": "Aerodactyl", "desc": "Aerodactylita (NO VENDIBLE)"},
    "mewtwonite": {"precio": 999999, "megaevolucion": "Mewtwo-X", "desc": "Mewtwonita X (NO VENDIBLE)"},
    "mewtwonitey": {"precio": 999999, "megaevolucion": "Mewtwo-Y", "desc": "Mewtwonita Y (NO VENDIBLE)"},
}

MT_ITEMS_DB = {
    "mt001": {"precio": 80, "tipo": "mt", "mt_move": "takedown", "desc": "📀 MT001 — Derribo · Físico Normal · Poder 90"},
    "mt002": {"precio": 80, "tipo": "mt", "mt_move": "charm", "desc": "📀 MT002 — Encanto · Estado Hada · Baja Atq"},
    "mt003": {"precio": 80, "tipo": "mt", "mt_move": "faketears", "desc": "📀 MT003 — Llanto Falso · Estado Siniestro · -2 DefEsp"},
    "mt004": {"precio": 80, "tipo": "mt", "mt_move": "agility", "desc": "📀 MT004 — Agilidad · Estado Psíquico · +2 Vel"},
    "mt005": {"precio": 80, "tipo": "mt", "mt_move": "mudslap", "desc": "📀 MT005 — Bofetón Lodo · Especial Tierra · Poder 20"},
    "mt006": {"precio": 80, "tipo": "mt", "mt_move": "scaryface", "desc": "📀 MT006 — Cara Susto · Estado Normal · -2 Vel"},
    "mt007": {"precio": 80, "tipo": "mt", "mt_move": "protect", "desc": "📀 MT007 — Protección · Estado Normal · Evita daño"},
    "mt008": {"precio": 80, "tipo": "mt", "mt_move": "firefang", "desc": "📀 MT008 — Colmillo Ígneo · Físico Fuego · Poder 65"},
    "mt009": {"precio": 80, "tipo": "mt", "mt_move": "thunderfang", "desc": "📀 MT009 — Colmillo Rayo · Físico Eléctrico · Poder 65"},
    "mt010": {"precio": 80, "tipo": "mt", "mt_move": "icefang", "desc": "📀 MT010 — Colmillo Hielo · Físico Hielo · Poder 65"},
    "mt011": {"precio": 80, "tipo": "mt", "mt_move": "waterpulse", "desc": "📀 MT011 — Hidropulso · Especial Agua · Poder 60"},
    "mt012": {"precio": 80, "tipo": "mt", "mt_move": "lowkick", "desc": "📀 MT012 — Patada Baja · Físico Lucha · Poder Var."},
    "mt013": {"precio": 80, "tipo": "mt", "mt_move": "acidspray", "desc": "📀 MT013 — Bomba Ácida · Especial Veneno · Poder 40"},
    "mt014": {"precio": 80, "tipo": "mt", "mt_move": "acrobatics", "desc": "📀 MT014 — Acróbata · Físico Volador · Poder 55"},
    "mt015": {"precio": 80, "tipo": "mt", "mt_move": "strugglebug", "desc": "📀 MT015 — Estoicismo · Especial Bicho · Poder 50"},
    "mt016": {"precio": 80, "tipo": "mt", "mt_move": "psybeam", "desc": "📀 MT016 — Psicorrayo · Especial Psíquico · Poder 65"},
    "mt017": {"precio": 80, "tipo": "mt", "mt_move": "confuseray", "desc": "📀 MT017 — Rayo Confuso · Estado Fantasma · Confunde"},
    "mt018": {"precio": 80, "tipo": "mt", "mt_move": "thief", "desc": "📀 MT018 — Ladrón · Físico Siniestro · Poder 60"},
    "mt019": {"precio": 80, "tipo": "mt", "mt_move": "disarmingvoice", "desc": "📀 MT019 — Voz Cautivadora · Especial Hada · Poder 40"},
    "mt020": {"precio": 80, "tipo": "mt", "mt_move": "trailblaze", "desc": "📀 MT020 — Abrecaminos · Físico Planta · Poder 50"},
    "mt021": {"precio": 80, "tipo": "mt", "mt_move": "pounce", "desc": "📀 MT021 — Brinco · Físico Bicho · Poder 50"},
    "mt022": {"precio": 80, "tipo": "mt", "mt_move": "chillingwater", "desc": "📀 MT022 — Agua Fría · Especial Agua · Poder 50"},
    "mt023": {"precio": 80, "tipo": "mt", "mt_move": "chargebeam", "desc": "📀 MT023 — Rayo Carga · Especial Eléctrico · Poder 50"},
    "mt024": {"precio": 80, "tipo": "mt", "mt_move": "firespin", "desc": "📀 MT024 — Giro Fuego · Especial Fuego · Poder 35"},
    "mt025": {"precio": 80, "tipo": "mt", "mt_move": "facade", "desc": "📀 MT025 — Imagen · Físico Normal · Poder 70"},
    "mt026": {"precio": 80, "tipo": "mt", "mt_move": "poisontail", "desc": "📀 MT026 — Cola Veneno · Físico Veneno · Poder 50"},
    "mt027": {"precio": 80, "tipo": "mt", "mt_move": "aerialace", "desc": "📀 MT027 — Golpe Aéreo · Físico Volador · Poder 60"},
    "mt028": {"precio": 80, "tipo": "mt", "mt_move": "bulldoze", "desc": "📀 MT028 — Terratemblor · Físico Tierra · Poder 60"},
    "mt029": {"precio": 80, "tipo": "mt", "mt_move": "hex", "desc": "📀 MT029 — Infortunio · Especial Fantasma · Poder 65"},
    "mt030": {"precio": 80, "tipo": "mt", "mt_move": "snarl", "desc": "📀 MT030 — Alarido · Especial Siniestro · Poder 55"},
    "mt031": {"precio": 80, "tipo": "mt", "mt_move": "metalclaw", "desc": "📀 MT031 — Garra Metal · Físico Acero · Poder 50"},
    "mt032": {"precio": 80, "tipo": "mt", "mt_move": "swift", "desc": "📀 MT032 — Rapidez · Especial Normal · Poder 60"},
    "mt033": {"precio": 80, "tipo": "mt", "mt_move": "magicalleaf", "desc": "📀 MT033 — Hoja Mágica · Especial Planta · Poder 60"},
    "mt034": {"precio": 80, "tipo": "mt", "mt_move": "icywind", "desc": "📀 MT034 — Viento Hielo · Especial Hielo · Poder 55"},
    "mt035": {"precio": 80, "tipo": "mt", "mt_move": "mudshot", "desc": "📀 MT035 — Disparo Lodo · Especial Tierra · Poder 55"},
    "mt036": {"precio": 80, "tipo": "mt", "mt_move": "rocktomb", "desc": "📀 MT036 — Tumba Rocas · Físico Roca · Poder 60"},
    "mt037": {"precio": 80, "tipo": "mt", "mt_move": "drainingkiss", "desc": "📀 MT037 — Beso Drenaje · Especial Hada · Poder 50"},
    "mt038": {"precio": 80, "tipo": "mt", "mt_move": "flamecharge", "desc": "📀 MT038 — Nitrocarga · Físico Fuego · Poder 50"},
    "mt039": {"precio": 80, "tipo": "mt", "mt_move": "lowsweep", "desc": "📀 MT039 — Puntapié · Físico Lucha · Poder 65"},
    "mt040": {"precio": 80, "tipo": "mt", "mt_move": "aircutter", "desc": "📀 MT040 — Aire Afilado · Especial Volador · Poder 60"},
    "mt041": {"precio": 80, "tipo": "mt", "mt_move": "storedpower", "desc": "📀 MT041 — Poder Reserva · Especial Psíquico · Poder 20"},
    "mt042": {"precio": 80, "tipo": "mt", "mt_move": "nightshade", "desc": "📀 MT042 — Tinieblas · Especial Fantasma · Daño=Nivel"},
    "mt043": {"precio": 80, "tipo": "mt", "mt_move": "fling", "desc": "📀 MT043 — Lanzamiento · Físico Siniestro · Daño=Objeto"},
    "mt044": {"precio": 80, "tipo": "mt", "mt_move": "dragontail", "desc": "📀 MT044 — Cola Dragón · Físico Dragón · Poder 60"},
    "mt045": {"precio": 80, "tipo": "mt", "mt_move": "venoshock", "desc": "📀 MT045 — Carga Tóxica · Especial Veneno · Poder 65"},
    "mt046": {"precio": 80, "tipo": "mt", "mt_move": "avalanche", "desc": "📀 MT046 — Alud · Físico Hielo · Poder 60"},
    "mt047": {"precio": 80, "tipo": "mt", "mt_move": "endure", "desc": "📀 MT047 — Aguante · Estado Normal · Resiste 1 HP"},
    "mt048": {"precio": 80, "tipo": "mt", "mt_move": "voltswitch", "desc": "📀 MT048 — Voltiocambio · Especial Eléctrico · Poder 70"},
    "mt049": {"precio": 80, "tipo": "mt", "mt_move": "sunnyday", "desc": "📀 MT049 — Día Soleado · Estado Fuego · Clima Sol"},
    "mt050": {"precio": 80, "tipo": "mt", "mt_move": "raindance", "desc": "📀 MT050 — Danza Lluvia · Estado Agua · Clima Lluvia"},
    "mt051": {"precio": 80, "tipo": "mt", "mt_move": "sandstorm", "desc": "📀 MT051 — Tormenta Arena · Estado Roca · Clima Arena"},
    "mt052": {"precio": 80, "tipo": "mt", "mt_move": "snowscape", "desc": "📀 MT052 — Paisaje Nevado · Estado Hielo · Clima Nieve"},
    "mt053": {"precio": 80, "tipo": "mt", "mt_move": "smartstrike", "desc": "📀 MT053 — Cuerno Certero · Físico Acero · Poder 70"},
    "mt054": {"precio": 80, "tipo": "mt", "mt_move": "psyshock", "desc": "📀 MT054 — Psicocarga · Especial Psíquico · Poder 80"},
    "mt055": {"precio": 80, "tipo": "mt", "mt_move": "dig", "desc": "📀 MT055 — Excavación · Físico Tierra · Poder 80"},
    "mt056": {"precio": 80, "tipo": "mt", "mt_move": "bulletseed", "desc": "📀 MT056 — Recurrente · Físico Planta · Poder 25"},
    "mt057": {"precio": 80, "tipo": "mt", "mt_move": "falseswipe", "desc": "📀 MT057 — Falsotortazo · Físico Normal · Poder 40"},
    "mt058": {"precio": 80, "tipo": "mt", "mt_move": "slash", "desc": "📀 MT058 — Cuchillada · Físico Normal · Poder 70"},
    "mt059": {"precio": 80, "tipo": "mt", "mt_move": "zenheadbutt", "desc": "📀 MT059 — Cabezazo Zen · Físico Psíquico · Poder 80"},
    "mt060": {"precio": 80, "tipo": "mt", "mt_move": "uturn", "desc": "📀 MT060 — Ida y Vuelta · Físico Bicho · Poder 70"},
    "mt061": {"precio": 80, "tipo": "mt", "mt_move": "shadowclaw", "desc": "📀 MT061 — Garra Sombría · Físico Fantasma · Poder 70"},
    "mt062": {"precio": 80, "tipo": "mt", "mt_move": "foulplay", "desc": "📀 MT062 — Juego Sucio · Físico Siniestro · Poder 95"},
    "mt063": {"precio": 80, "tipo": "mt", "mt_move": "psychicfangs", "desc": "📀 MT063 — Psicocolmillo · Físico Psíquico · Poder 85"},
    "mt064": {"precio": 80, "tipo": "mt", "mt_move": "bulkup", "desc": "📀 MT064 — Corpulencia · Estado Lucha · +Atq +Def"},
    "mt065": {"precio": 80, "tipo": "mt", "mt_move": "airslash", "desc": "📀 MT065 — Tajo Aéreo · Especial Volador · Poder 75"},
    "mt066": {"precio": 80, "tipo": "mt", "mt_move": "bodypress", "desc": "📀 MT066 — Plancha Corporal · Físico Lucha · Poder 80"},
    "mt067": {"precio": 80, "tipo": "mt", "mt_move": "firepunch", "desc": "📀 MT067 — Puño Fuego · Físico Fuego · Poder 75"},
    "mt068": {"precio": 80, "tipo": "mt", "mt_move": "thunderpunch", "desc": "📀 MT068 — Puño Trueno · Físico Eléctrico · Poder 75"},
    "mt069": {"precio": 80, "tipo": "mt", "mt_move": "icepunch", "desc": "📀 MT069 — Puño Hielo · Físico Hielo · Poder 75"},
    "mt070": {"precio": 80, "tipo": "mt", "mt_move": "sleeptalk", "desc": "📀 MT070 — Sonámbulo · Estado Normal · Ataca dormido"},
    "mt071": {"precio": 80, "tipo": "mt", "mt_move": "seedbomb", "desc": "📀 MT071 — Bomba Germen · Físico Planta · Poder 80"},
    "mt072": {"precio": 80, "tipo": "mt", "mt_move": "electroball", "desc": "📀 MT072 — Electrobola · Especial Eléctrico · Poder Var."},
    "mt073": {"precio": 80, "tipo": "mt", "mt_move": "drainpunch", "desc": "📀 MT073 — Puño Drenaje · Físico Lucha · Poder 75"},
    "mt074": {"precio": 80, "tipo": "mt", "mt_move": "reflect", "desc": "📀 MT074 — Reflejo · Estado Psíquico · Reduce daño Fís."},
    "mt075": {"precio": 80, "tipo": "mt", "mt_move": "lightscreen", "desc": "📀 MT075 — Pantalla de Luz · Estado Psíquico · Reduce Esp."},
    "mt076": {"precio": 80, "tipo": "mt", "mt_move": "rockblast", "desc": "📀 MT076 — Pedrada · Físico Roca · Poder 25"},
    "mt077": {"precio": 80, "tipo": "mt", "mt_move": "waterfall", "desc": "📀 MT077 — Cascada · Físico Agua · Poder 80"},
    "mt078": {"precio": 80, "tipo": "mt", "mt_move": "dragonclaw", "desc": "📀 MT078 — Garra Dragón · Físico Dragón · Poder 80"},
    "mt079": {"precio": 80, "tipo": "mt", "mt_move": "dazzlinggleam", "desc": "📀 MT079 — Brillo Mágico · Especial Hada · Poder 80"},
    "mt080": {"precio": 80, "tipo": "mt", "mt_move": "metronome", "desc": "📀 MT080 — Metrónomo · Estado Normal · Ataque al azar"},
    "mt081": {"precio": 80, "tipo": "mt", "mt_move": "grassknot", "desc": "📀 MT081 — Hierba Lazo · Especial Planta · Poder Var."},
    "mt082": {"precio": 80, "tipo": "mt", "mt_move": "thunderwave", "desc": "📀 MT082 — Onda Trueno · Estado Eléctrico · Paraliza"},
    "mt083": {"precio": 80, "tipo": "mt", "mt_move": "poisonjab", "desc": "📀 MT083 — Puya Nociva · Físico Veneno · Poder 80"},
    "mt084": {"precio": 80, "tipo": "mt", "mt_move": "stompingtantrum", "desc": "📀 MT084 — Pataleta · Físico Tierra · Poder 75"},
    "mt085": {"precio": 80, "tipo": "mt", "mt_move": "rest", "desc": "📀 MT085 — Descanso · Estado Psíquico · Cura y duerme"},
    "mt086": {"precio": 80, "tipo": "mt", "mt_move": "rockslide", "desc": "📀 MT086 — Avalancha · Físico Roca · Poder 75"},
    "mt087": {"precio": 80, "tipo": "mt", "mt_move": "taunt", "desc": "📀 MT087 — Mofa · Estado Siniestro · Solo ataques"},
    "mt088": {"precio": 80, "tipo": "mt", "mt_move": "swordsdance", "desc": "📀 MT088 — Danza Espada · Estado Normal · +2 Atq"},
    "mt089": {"precio": 80, "tipo": "mt", "mt_move": "bodyslam", "desc": "📀 MT089 — Golpe Cuerpo · Físico Normal · Poder 85"},
    "mt090": {"precio": 80, "tipo": "mt", "mt_move": "spikes", "desc": "📀 MT090 — Púas · Estado Tierra · Daño al cambio"},
    "mt091": {"precio": 80, "tipo": "mt", "mt_move": "toxicspikes", "desc": "📀 MT091 — Púas Tóxicas · Estado Veneno · Envenena"},
    "mt092": {"precio": 80, "tipo": "mt", "mt_move": "imprison", "desc": "📀 MT092 — Sellado · Estado Psíquico · Bloquea movs"},
    "mt093": {"precio": 80, "tipo": "mt", "mt_move": "flashcannon", "desc": "📀 MT093 — Foco Resplandor · Especial Acero · Poder 80"},
    "mt094": {"precio": 80, "tipo": "mt", "mt_move": "darkpulse", "desc": "📀 MT094 — Pulso Umbrío · Especial Siniestro · Poder 85"},
    "mt095": {"precio": 80, "tipo": "mt", "mt_move": "leechlife", "desc": "📀 MT095 — Chupavidas · Físico Bicho · Poder 80"},
    "mt096": {"precio": 80, "tipo": "mt", "mt_move": "eerieimpulse", "desc": "📀 MT096 — Onda Anómala · Estado Eléctrico · -2 Atq.Esp"},
    "mt097": {"precio": 80, "tipo": "mt", "mt_move": "fly", "desc": "📀 MT097 — Vuelo · Físico Volador · Poder 90"},
    "mt098": {"precio": 80, "tipo": "mt", "mt_move": "skillswap", "desc": "📀 MT098 — Intercambio · Estado Psíquico · Cambia hab."},
    "mt099": {"precio": 80, "tipo": "mt", "mt_move": "ironhead", "desc": "📀 MT099 — Cabeza de Hierro · Físico Acero · Poder 80"},
    "mt100": {"precio": 80, "tipo": "mt", "mt_move": "dragondance", "desc": "📀 MT100 — Danza Dragón · Estado Dragón · +Atq +Vel"},
    "mt101": {"precio": 150, "tipo": "mt", "mt_move": "powergem", "desc": "📀 MT101 — Joya de Luz · Especial Roca · Poder 80"},
    "mt102": {"precio": 150, "tipo": "mt", "mt_move": "gunkshot", "desc": "📀 MT102 — Lanzamugre · Físico Veneno · Poder 120"},
    "mt103": {"precio": 150, "tipo": "mt", "mt_move": "substitute", "desc": "📀 MT103 — Sustituto · Estado Normal · Crea señuelo"},
    "mt104": {"precio": 150, "tipo": "mt", "mt_move": "irondefense", "desc": "📀 MT104 — Defensa Férrea · Estado Acero · +2 Def"},
    "mt105": {"precio": 150, "tipo": "mt", "mt_move": "xscissor", "desc": "📀 MT105 — Tijera X · Físico Bicho · Poder 80"},
    "mt106": {"precio": 150, "tipo": "mt", "mt_move": "drillrun", "desc": "📀 MT106 — Taladradora · Físico Tierra · Poder 80"},
    "mt107": {"precio": 150, "tipo": "mt", "mt_move": "willowisp", "desc": "📀 MT107 — Fuego Fatuo · Estado Fuego · Quema"},
    "mt108": {"precio": 150, "tipo": "mt", "mt_move": "crunch", "desc": "📀 MT108 — Triturar · Físico Siniestro · Poder 80"},
    "mt109": {"precio": 150, "tipo": "mt", "mt_move": "trick", "desc": "📀 MT109 — Truco · Estado Psíquico · Cambia objeto"},
    "mt110": {"precio": 150, "tipo": "mt", "mt_move": "liquidation", "desc": "📀 MT110 — Hidroariete · Físico Agua · Poder 85"},
    "mt111": {"precio": 150, "tipo": "mt", "mt_move": "gigadrain", "desc": "📀 MT111 — Gigadrenado · Especial Planta · Poder 75"},
    "mt112": {"precio": 150, "tipo": "mt", "mt_move": "aurasphere", "desc": "📀 MT112 — Esfera Aural · Especial Lucha · Poder 80"},
    "mt113": {"precio": 150, "tipo": "mt", "mt_move": "tailwind", "desc": "📀 MT113 — Viento Afín · Estado Volador · +Vel equipo"},
    "mt114": {"precio": 150, "tipo": "mt", "mt_move": "shadowball", "desc": "📀 MT114 — Bola Sombra · Especial Fantasma · Poder 80"},
    "mt115": {"precio": 150, "tipo": "mt", "mt_move": "dragonpulse", "desc": "📀 MT115 — Pulso Dragón · Especial Dragón · Poder 85"},
    "mt116": {"precio": 150, "tipo": "mt", "mt_move": "stealthrock", "desc": "📀 MT116 — Trampa Rocas · Estado Roca · Daño entrada"},
    "mt117": {"precio": 150, "tipo": "mt", "mt_move": "hypervoice", "desc": "📀 MT117 — Vozarrón · Especial Normal · Poder 90"},
    "mt118": {"precio": 150, "tipo": "mt", "mt_move": "heatwave", "desc": "📀 MT118 — Onda Ígnea · Especial Fuego · Poder 95"},
    "mt119": {"precio": 150, "tipo": "mt", "mt_move": "energyball", "desc": "📀 MT119 — Energibola · Especial Planta · Poder 90"},
    "mt120": {"precio": 150, "tipo": "mt", "mt_move": "psychic", "desc": "📀 MT120 — Psíquico · Especial Psíquico · Poder 90"},
    "mt121": {"precio": 150, "tipo": "mt", "mt_move": "heavyslam", "desc": "📀 MT121 — Cuerpo Pesado · Físico Acero · Poder Var."},
    "mt122": {"precio": 150, "tipo": "mt", "mt_move": "encore", "desc": "📀 MT122 — Otra Vez · Estado Normal · Repite mov"},
    "mt123": {"precio": 150, "tipo": "mt", "mt_move": "surf", "desc": "📀 MT123 — Surf · Especial Agua · Poder 90"},
    "mt124": {"precio": 150, "tipo": "mt", "mt_move": "icebeam", "desc": "📀 MT124 — Rayo Hielo · Especial Hielo · Poder 90"},
    "mt125": {"precio": 150, "tipo": "mt", "mt_move": "flamethrower", "desc": "📀 MT125 — Lanzallamas · Especial Fuego · Poder 90"},
    "mt126": {"precio": 150, "tipo": "mt", "mt_move": "thunderbolt", "desc": "📀 MT126 — Rayo · Especial Eléctrico · Poder 90"},
    "mt127": {"precio": 150, "tipo": "mt", "mt_move": "playrough", "desc": "📀 MT127 — Carantoña · Físico Hada · Poder 90"},
    "mt128": {"precio": 150, "tipo": "mt", "mt_move": "amnesia", "desc": "📀 MT128 — Amnesia · Estado Psíquico · +2 DefEsp"},
    "mt129": {"precio": 150, "tipo": "mt", "mt_move": "calmmind", "desc": "📀 MT129 — Paz Mental · Estado Psíquico · +AtSp+DfSp"},
    "mt130": {"precio": 150, "tipo": "mt", "mt_move": "helpinghand", "desc": "📀 MT130 — Refuerzo · Estado Normal · Ayuda aliado"},
    "mt131": {"precio": 150, "tipo": "mt", "mt_move": "pollenpuff", "desc": "📀 MT131 — Bola Polen · Especial Bicho · Poder 90"},
    "mt132": {"precio": 150, "tipo": "mt", "mt_move": "batonpass", "desc": "📀 MT132 — Relevo · Estado Normal · Pasa mejoras"},
    "mt133": {"precio": 150, "tipo": "mt", "mt_move": "earthquake", "desc": "📀 MT133 — Terremoto · Físico Tierra · Poder 100"},
    "mt134": {"precio": 150, "tipo": "mt", "mt_move": "reversal", "desc": "📀 MT134 — Inversión · Físico Lucha · Daño baja HP"},
    "mt135": {"precio": 150, "tipo": "mt", "mt_move": "hardpress", "desc": "📀 MT135 — Carga con Derribo · Físico Acero · Poder Var."},
    "mt136": {"precio": 150, "tipo": "mt", "mt_move": "electricterrain", "desc": "📀 MT136 — Campo Eléctrico · Estado Eléctrico · Campo"},
    "mt137": {"precio": 150, "tipo": "mt", "mt_move": "grassyterrain", "desc": "📀 MT137 — Campo de Hierba · Estado Planta · Campo"},
    "mt138": {"precio": 150, "tipo": "mt", "mt_move": "mistyterrain", "desc": "📀 MT138 — Campo de Niebla · Estado Hada · Campo"},
    "mt139": {"precio": 150, "tipo": "mt", "mt_move": "psychicterrain", "desc": "📀 MT139 — Campo Psíquico · Estado Psíquico · Campo"},
    "mt140": {"precio": 150, "tipo": "mt", "mt_move": "nastyplot", "desc": "📀 MT140 — Maquinación · Estado Siniestro · +2 AtqEsp"},
    "mt141": {"precio": 150, "tipo": "mt", "mt_move": "fireblast", "desc": "📀 MT141 — Llamarada · Especial Fuego · Poder 110"},
    "mt142": {"precio": 150, "tipo": "mt", "mt_move": "hydropump", "desc": "📀 MT142 — Hidrobomba · Especial Agua · Poder 110"},
    "mt143": {"precio": 150, "tipo": "mt", "mt_move": "blizzard", "desc": "📀 MT143 — Ventisca · Especial Hielo · Poder 110"},
    "mt144": {"precio": 150, "tipo": "mt", "mt_move": "firepledge", "desc": "📀 MT144 — Voto Fuego · Especial Fuego · Poder 80"},
    "mt145": {"precio": 150, "tipo": "mt", "mt_move": "waterpledge", "desc": "📀 MT145 — Voto Agua · Especial Agua · Poder 80"},
    "mt146": {"precio": 150, "tipo": "mt", "mt_move": "grasspledge", "desc": "📀 MT146 — Voto Planta · Especial Planta · Poder 80"},
    "mt147": {"precio": 150, "tipo": "mt", "mt_move": "wildcharge", "desc": "📀 MT147 — Voltio Cruel · Físico Eléctrico · Poder 90"},
    "mt148": {"precio": 150, "tipo": "mt", "mt_move": "sludgebomb", "desc": "📀 MT148 — Bomba Lodo · Especial Veneno · Poder 90"},
    "mt149": {"precio": 150, "tipo": "mt", "mt_move": "earthpower", "desc": "📀 MT149 — Tierra Viva · Especial Tierra · Poder 90"},
    "mt150": {"precio": 150, "tipo": "mt", "mt_move": "mindblown", "desc": "📀 MT150 — Cabeza Sorpresa · Especial Fuego · Poder 150"},
    "mt151": {"precio": 150, "tipo": "mt", "mt_move": "phantomforce", "desc": "📀 MT151 — Golpe Fantasma · Físico Fantasma · Poder 90"},
    "mt152": {"precio": 150, "tipo": "mt", "mt_move": "gigaimpact", "desc": "📀 MT152 — Gigaimpacto · Físico Normal · Poder 150"},
    "mt153": {"precio": 150, "tipo": "mt", "mt_move": "skyattack", "desc": "📀 MT153 — Ataque Celestial · Físico Volador · Poder 140"},
    "mt154": {"precio": 150, "tipo": "mt", "mt_move": "hydrocannon", "desc": "📀 MT154 — Hidrocañón · Especial Agua · Poder 150"},
    "mt155": {"precio": 150, "tipo": "mt", "mt_move": "frenzyplant", "desc": "📀 MT155 — Planta Feroz · Especial Planta · Poder 150"},
    "mt156": {"precio": 150, "tipo": "mt", "mt_move": "blastburn", "desc": "📀 MT156 — Anillo Ígneo · Especial Fuego · Poder 150"},
    "mt157": {"precio": 150, "tipo": "mt", "mt_move": "overheat", "desc": "📀 MT157 — Sofoco · Especial Fuego · Poder 130"},
    "mt158": {"precio": 150, "tipo": "mt", "mt_move": "focusblast", "desc": "📀 MT158 — Onda Certera · Especial Lucha · Poder 120"},
    "mt159": {"precio": 150, "tipo": "mt", "mt_move": "leafstorm", "desc": "📀 MT159 — Lluevehojas · Especial Planta · Poder 130"},
    "mt160": {"precio": 150, "tipo": "mt", "mt_move": "hurricane", "desc": "📀 MT160 — Vendaval · Especial Volador · Poder 110"},
    "mt161": {"precio": 150, "tipo": "mt", "mt_move": "trickroom", "desc": "📀 MT161 — Espacio Raro · Estado Psíquico · Invierte Vel."},
    "mt162": {"precio": 150, "tipo": "mt", "mt_move": "bugbuzz", "desc": "📀 MT162 — Zumbido · Especial Bicho · Poder 90"},
    "mt163": {"precio": 150, "tipo": "mt", "mt_move": "hyperbeam", "desc": "📀 MT163 — Hiperrayo · Especial Normal · Poder 150"},
    "mt164": {"precio": 150, "tipo": "mt", "mt_move": "bravebird", "desc": "📀 MT164 — Envite Ígneo · Físico Volador · Poder 120"},
    "mt165": {"precio": 150, "tipo": "mt", "mt_move": "flareblitz", "desc": "📀 MT165 — Envite Ígneo · Físico Fuego · Poder 120"},
    "mt166": {"precio": 150, "tipo": "mt", "mt_move": "thunder", "desc": "📀 MT166 — Trueno · Especial Eléctrico · Poder 110"},
    "mt167": {"precio": 150, "tipo": "mt", "mt_move": "closecombat", "desc": "📀 MT167 — A Bocajarro · Físico Lucha · Poder 120"},
    "mt168": {"precio": 150, "tipo": "mt", "mt_move": "solarbeam", "desc": "📀 MT168 — Rayo Solar · Especial Planta · Poder 120"},
    "mt169": {"precio": 150, "tipo": "mt", "mt_move": "dracometeor", "desc": "📀 MT169 — Cometa Draco · Especial Dragón · Poder 130"},
    "mt170": {"precio": 150, "tipo": "mt", "mt_move": "steelbeam", "desc": "📀 MT170 — Metaláser · Especial Acero · Poder 140"},
    "mt171": {"precio": 150, "tipo": "mt", "mt_move": "terablast", "desc": "📀 MT171 — Teraexplosión · Especial Normal · Poder 80"},
    "mt172": {"precio": 150, "tipo": "mt", "mt_move": "roar", "desc": "📀 MT172 — Rugido · Estado Normal · Fuerza cambio"},
    "mt173": {"precio": 150, "tipo": "mt", "mt_move": "charge", "desc": "📀 MT173 — Carga · Estado Eléctrico · Sube Def.Esp"},
    "mt174": {"precio": 150, "tipo": "mt", "mt_move": "haze", "desc": "📀 MT174 — Niebla · Estado Hielo · Reinicia stats"},
    "mt175": {"precio": 150, "tipo": "mt", "mt_move": "toxic", "desc": "📀 MT175 — Tóxico · Estado Veneno · Veneno grave"},
    "mt176": {"precio": 150, "tipo": "mt", "mt_move": "sandtomb", "desc": "📀 MT176 — Bucle Arena · Físico Tierra · Poder 35"},
    "mt177": {"precio": 150, "tipo": "mt", "mt_move": "spite", "desc": "📀 MT177 — Rencor · Estado Fantasma · Baja PP"},
    "mt178": {"precio": 150, "tipo": "mt", "mt_move": "gravity", "desc": "📀 MT178 — Gravedad · Estado Psíquico · Baja voladores"},
    "mt179": {"precio": 150, "tipo": "mt", "mt_move": "smackdown", "desc": "📀 MT179 — Antiaéreo · Físico Roca · Poder 50"},
    "mt180": {"precio": 150, "tipo": "mt", "mt_move": "gyroball", "desc": "📀 MT180 — Giro Bola · Físico Acero · Poder Var."},
    "mt181": {"precio": 150, "tipo": "mt", "mt_move": "knockoff", "desc": "📀 MT181 — Desarme · Físico Siniestro · Poder 65"},
    "mt182": {"precio": 150, "tipo": "mt", "mt_move": "bugbite", "desc": "📀 MT182 — Picadura · Físico Bicho · Poder 60"},
    "mt183": {"precio": 150, "tipo": "mt", "mt_move": "superfang", "desc": "📀 MT183 — Superdiente · Físico Normal · Mitad HP"},
    "mt184": {"precio": 150, "tipo": "mt", "mt_move": "vacuumwave", "desc": "📀 MT184 — Onda Vacío · Especial Lucha · Poder 40"},
    "mt185": {"precio": 150, "tipo": "mt", "mt_move": "lunge", "desc": "📀 MT185 — Plancha · Físico Bicho · Poder 80"},
    "mt186": {"precio": 150, "tipo": "mt", "mt_move": "highhorsepower", "desc": "📀 MT186 — Fuerza Equina · Físico Tierra · Poder 95"},
    "mt187": {"precio": 150, "tipo": "mt", "mt_move": "iciclespear", "desc": "📀 MT187 — Carámbano · Físico Hielo · Poder 25"},
    "mt188": {"precio": 150, "tipo": "mt", "mt_move": "scald", "desc": "📀 MT188 — Escaldar · Especial Agua · Poder 80"},
    "mt189": {"precio": 150, "tipo": "mt", "mt_move": "heatcrash", "desc": "📀 MT189 — Cuerpo Pesado Fuego · Físico Fuego · Poder Var."},
    "mt190": {"precio": 150, "tipo": "mt", "mt_move": "solarblade", "desc": "📀 MT190 — Cuchilla Solar · Físico Planta · Poder 125"},
    "mt191": {"precio": 150, "tipo": "mt", "mt_move": "uproar", "desc": "📀 MT191 — Alboroto · Especial Normal · Poder 90"},
    "mt192": {"precio": 150, "tipo": "mt", "mt_move": "focuspunch", "desc": "📀 MT192 — Puño Certero · Físico Lucha · Poder 150"},
    "mt193": {"precio": 150, "tipo": "mt", "mt_move": "weatherball", "desc": "📀 MT193 — Meteorobola · Especial Normal · Poder 50"},
    "mt194": {"precio": 150, "tipo": "mt", "mt_move": "grassyglide", "desc": "📀 MT194 — Fitoimpulso · Físico Planta · Poder 55"},
    "mt195": {"precio": 150, "tipo": "mt", "mt_move": "burningjealousy", "desc": "📀 MT195 — Envidia Ardiente · Especial Fuego · Poder 70"},
    "mt196": {"precio": 150, "tipo": "mt", "mt_move": "flipturn", "desc": "📀 MT196 — Viraje · Físico Agua · Poder 60"},
    "mt197": {"precio": 150, "tipo": "mt", "mt_move": "dualwingbeat", "desc": "📀 MT197 — Ala Bis · Físico Volador · Poder 40 x2"},
    "mt198": {"precio": 150, "tipo": "mt", "mt_move": "poltergeist", "desc": "📀 MT198 — Poltergeist · Físico Fantasma · Poder 110"},
    "mt199": {"precio": 150, "tipo": "mt", "mt_move": "lashout", "desc": "📀 MT199 — Desahogo · Físico Siniestro · Poder 75"},
    "mt200": {"precio": 150, "tipo": "mt", "mt_move": "scaleshot", "desc": "📀 MT200 — Ráfaga Escamas · Físico Dragón · Poder 25"},
    "mt201": {"precio": 150, "tipo": "mt", "mt_move": "mistyexplosion", "desc": "📀 MT201 — Explosión Bruma · Especial Hada · Poder 100"},

}

# ========== MENTAS (100 cosmos) ==========
MENTA_ITEMS_DB = {
    "timidmint":   {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Tímida — cambia naturaleza a Timid (+Vel/-Atq)"},
    "modestmint":  {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Modesta — cambia naturaleza a Modest (+AtqSp/-Atq)"},
    "adamantmint": {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Adamante — cambia naturaleza a Adamant (+Atq/-AtqSp)"},
    "boldmint":    {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Osada — cambia naturaleza a Bold (+Def/-Atq)"},
    "jollymint":   {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Alegre — cambia naturaleza a Jolly (+Vel/-AtqSp)"},
    "calmmint":    {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Serena — cambia naturaleza a Calm (+DefSp/-Atq)"},
    "impishmint":  {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Impish — cambia naturaleza a Impish (+Def/-AtqSp)"},
    "carefulmint": {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Cuidadosa — cambia naturaleza a Careful (+DefSp/-AtqSp)"},
    "hastymint":   {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Activa — cambia naturaleza a Hasty (+Vel/-Def)"},
    "naivemint":   {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Ingenua — cambia naturaleza a Naive (+Vel/-DefSp)"},
    "relaxedmint": {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Relajada — cambia naturaleza a Relaxed (+Def/-Vel)"},
    "quietmint":   {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Quieta — cambia naturaleza a Quiet (+AtqSp/-Vel)"},
    "rashmint":    {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Alocada — cambia naturaleza a Rash (+AtqSp/-DefSp)"},
    "gentlemint":  {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Gentil — cambia naturaleza a Gentle (+DefSp/-Def)"},
    "sassymint":   {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Grosera — cambia naturaleza a Sassy (+DefSp/-Vel)"},
    "bravemint":   {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Audaz — cambia naturaleza a Brave (+Atq/-Vel)"},
    "lonelymint":  {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Solitaria — cambia naturaleza a Lonely (+Atq/-Def)"},
    "naughtymint": {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Pícara — cambia naturaleza a Naughty (+Atq/-DefSp)"},
    "laxmint":     {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Floja — cambia naturaleza a Lax (+Def/-DefSp)"},
    "mildmint":    {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Suave — cambia naturaleza a Mild (+AtqSp/-Def)"},
    "seriousmint": {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Seria — cambia naturaleza a Serious (neutral)"},
    "hardymint":   {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Resistente — cambia naturaleza a Hardy (neutral)"},
    "bashfulmint": {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Tímida — cambia naturaleza a Bashful (neutral)"},
    "quirkymint":  {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Rara — cambia naturaleza a Quirky (neutral)"},
    "docilmint":   {"precio": 100, "tipo": "menta", "desc": "🌿 Menta Dócil — cambia naturaleza a Docile (neutral)"},
}

# ========== CONSOLIDAR TODO ==========
ITEMS_COMPLETOS_DB = {
    **POKEBALLS_DB,
    **MEDICINAS_DB,
    **VITAMINAS_DB,
    **PIEDRAS_EVOLUTIVAS_DB,
    **OBJETOS_INTERCAMBIO_DB,
    **CRIANZA_DB,
    **CHOICE_ITEMS_DB,
    **POWER_ITEMS_DB,
    **DEFENSIVE_ITEMS_DB,
    **SITUATIONAL_ITEMS_DB,
    **BAYAS_DB,
    **CLIMA_TERRENO_DB,
    **TYPE_BOOST_DB,
    **INCIENSOS_DB,
    **MEGASTONES_DB,
    **MT_ITEMS_DB,
    **MENTA_ITEMS_DB,
}

# ========== CATEGORÍAS PARA TIENDA ==========
CATEGORIAS_TIENDA = {
    "pokeballs": {
        "nombre": "⚪ Pokéballs",
        "items": [k for k, v in POKEBALLS_DB.items() if v["precio"] < 999999],
        "orden": 1
    },
    "medicinas": {
        "nombre": "💊 Medicinas y Curaciones",
        "items": list(MEDICINAS_DB.keys()),
        "orden": 2
    },
    "vitaminas": {
        "nombre": "💪 Vitaminas y EV Training",
        "items": [k for k, v in VITAMINAS_DB.items() if v["precio"] < 999999],
        "orden": 3
    },
    "piedras": {
        "nombre": "💎 Piedras Evolutivas",
        "items": list(PIEDRAS_EVOLUTIVAS_DB.keys()),
        "orden": 4
    },
    "intercambio": {
        "nombre": "🔄 Objetos de Intercambio",
        "items": list(OBJETOS_INTERCAMBIO_DB.keys()),
        "orden": 5
    },
    "crianza": {
        "nombre": "🥚 Crianza",
        "items": [k for k, v in CRIANZA_DB.items() if v["precio"] < 999999],
        "orden": 6
    },
    "combate_choice": {
        "nombre": "⚔️ Choice Items",
        "items": list(CHOICE_ITEMS_DB.keys()),
        "orden": 7
    },
    "combate_power": {
        "nombre": "💥 Power Items",
        "items": list(POWER_ITEMS_DB.keys()),
        "orden": 8
    },
    "combate_defensivo": {
        "nombre": "🛡️ Items Defensivos",
        "items": list(DEFENSIVE_ITEMS_DB.keys()),
        "orden": 9
    },
    "combate_situacional": {
        "nombre": "🎯 Items Situacionales",
        "items": list(SITUATIONAL_ITEMS_DB.keys()),
        "orden": 10
    },
    "bayas": {
        "nombre": "🍓 Bayas",
        "items": list(BAYAS_DB.keys()),
        "orden": 11
    },
    "clima": {
        "nombre": "🌤️ Clima y Terreno",
        "items": list(CLIMA_TERRENO_DB.keys()),
        "orden": 12
    },
    "type_boost": {
        "nombre": "🔥 Potenciadores de Tipo",
        "items": list(TYPE_BOOST_DB.keys()),
        "orden": 13
    },
    "inciensos": {
        "nombre": "🌸 Inciensos",
        "items": list(INCIENSOS_DB.keys()),
        "orden": 14
    },
    "MT/MO": {
        "nombre": "💿 MT/MO",
        "items": ["mt001", "mt002", "mt003", "mt004", "mt005", "mt006", "mt007", "mt008", "mt009", "mt010", "mt011", "mt012", "mt013", "mt014", "mt015", "mt016", "mt017", "mt018", "mt019", "mt020", "mt021", "mt022", "mt023", "mt024", "mt025", "mt026", "mt027", "mt028", "mt029", "mt030", "mt031", "mt032", "mt033", "mt034", "mt035", "mt036", "mt037", "mt038", "mt039", "mt040", "mt041", "mt042", "mt043", "mt044", "mt045", "mt046", "mt047", "mt048", "mt049", "mt050", "mt051", "mt052", "mt053", "mt054", "mt055", "mt056", "mt057", "mt058", "mt059", "mt060", "mt061", "mt062", "mt063", "mt064", "mt065", "mt066", "mt067", "mt068", "mt069", "mt070", "mt071", "mt072", "mt073", "mt074", "mt075", "mt076", "mt077", "mt078", "mt079", "mt080", "mt081", "mt082", "mt083", "mt084", "mt085", "mt086", "mt087", "mt088", "mt089", "mt090", "mt091", "mt092", "mt093", "mt094", "mt095", "mt096", "mt097", "mt098", "mt099", "mt100", "mt101", "mt102", "mt103", "mt104", "mt105", "mt106", "mt107", "mt108", "mt109", "mt110", "mt111", "mt112", "mt113", "mt114", "mt115", "mt116", "mt117", "mt118", "mt119", "mt120", "mt121", "mt122", "mt123", "mt124", "mt125", "mt126", "mt127", "mt128", "mt129", "mt130", "mt131", "mt132", "mt133", "mt134", "mt135", "mt136", "mt137", "mt138", "mt139", "mt140", "mt141", "mt142", "mt143", "mt144", "mt145", "mt146", "mt147", "mt148", "mt149", "mt150", "mt151", "mt152", "mt153", "mt154", "mt155", "mt156", "mt157", "mt158", "mt159", "mt160", "mt161", "mt162", "mt163", "mt164", "mt165", "mt166", "mt167", "mt168", "mt169", "mt170", "mt171", "mt172", "mt173", "mt174", "mt175", "mt176", "mt177", "mt178", "mt179", "mt180", "mt181", "mt182", "mt183", "mt184", "mt185", "mt186", "mt187", "mt188", "mt189", "mt190", "mt191", "mt192", "mt193", "mt194", "mt195", "mt196", "mt197", "mt198", "mt199", "mt200", "mt201", "mt202", "mt203", "mt204", "mt205", "mt206", "mt207", "mt208", "mt209", "mt210", "mt211", "mt212", "mt213", "mt214", "mt215", "mt216", "mt217", "mt218", "mt219", "mt220", "mt221", "mt222", "mt223", "mt224", "mt225", "mt226", "mt227", "mt228", "mt229"],
        "orden": 15
    },
    "mentas": {
        "nombre": "🌿 Mentas (Naturaleza)",
        "items": list(MENTA_ITEMS_DB.keys()),
        "orden": 16,
    },
}

# ========== FUNCIONES HELPER ==========

def obtener_item_info(item_id: str) -> Dict[str, Any]:
    """Obtiene información completa de un item"""
    return ITEMS_COMPLETOS_DB.get(item_id.lower(), {})

def obtener_precio(item_id: str) -> int:
    """Obtiene el precio de un item"""
    item = obtener_item_info(item_id)
    return item.get('precio', 0)

def es_vendible(item_id: str) -> bool:
    """Verifica si un item se puede comprar en tienda"""
    precio = obtener_precio(item_id)
    return 0 < precio < 999999

def obtener_items_categoria(categoria: str) -> list:
    """Obtiene todos los items de una categoría"""
    cat_info = CATEGORIAS_TIENDA.get(categoria, {})
    return cat_info.get('items', [])

def buscar_item(query: str) -> list:
    """Busca items que contengan el texto dado"""
    query = query.lower()
    return [
        nombre for nombre in ITEMS_COMPLETOS_DB.keys()
        if query in nombre.lower() and es_vendible(nombre)
    ]

def obtener_total_items() -> int:
    """Retorna el total de items en la base de datos"""
    return len(ITEMS_COMPLETOS_DB)

def obtener_items_vendibles() -> int:
    """Retorna el total de items vendibles"""
    return len([k for k in ITEMS_COMPLETOS_DB.keys() if es_vendible(k)])


# ========== EXPORTAR ==========
__all__ = [
    'ITEMS_COMPLETOS_DB',
    'CATEGORIAS_TIENDA',
    'obtener_item_info',
    'obtener_precio',
    'es_vendible',
    'obtener_items_categoria',
    'buscar_item',
    'obtener_total_items',
    'obtener_items_vendibles',
]