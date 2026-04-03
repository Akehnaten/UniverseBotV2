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
    "ppup": {"precio": 50, "pp_max": 1, "desc": "Más PP - +1 PP máximo permanente"},
    "ppmax": {"precio": 150, "pp_max": 3, "desc": "PP Máximos - +3 PP máximo permanente"},
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
    # ── Físicos básicos ──────────────────────────────────────────────
    "mt001": {"precio": 3000,  "tipo": "mt", "mt_move": "megapunch",      "desc": "📀 MT001 — Megapuño · Físico Normal · Poder 80"},
    "mt002": {"precio": 2000,  "tipo": "mt", "mt_move": "payback",        "desc": "📀 MT002 — Represalia · Físico Siniestro · Poder 50"},
    "mt003": {"precio": 5000,  "tipo": "mt", "mt_move": "thunderpunch",   "desc": "📀 MT003 — Puño Trueno · Físico Eléctrico · Poder 75"},
    "mt004": {"precio": 5000,  "tipo": "mt", "mt_move": "icepunch",       "desc": "📀 MT004 — Puño Hielo · Físico Hielo · Poder 75"},
    "mt005": {"precio": 5000,  "tipo": "mt", "mt_move": "firepunch",      "desc": "📀 MT005 — Puño Fuego · Físico Fuego · Poder 75"},
    "mt006": {"precio": 5000,  "tipo": "mt", "mt_move": "bulletpunch",    "desc": "📀 MT006 — Puño Bala · Físico Acero · Poder 40 · Prioridad +1"},
    "mt007": {"precio": 3000,  "tipo": "mt", "mt_move": "lowkick",        "desc": "📀 MT007 — Patada Baja · Físico Lucha · Poder varía"},
    "mt008": {"precio": 2000,  "tipo": "mt", "mt_move": "lowsweep",       "desc": "📀 MT008 — Barrido · Físico Lucha · Poder 65"},
    # ── Defensa / Estado ─────────────────────────────────────────────
    "mt017": {"precio": 1500,  "tipo": "mt", "mt_move": "scaryface",      "desc": "📀 MT017 — Cara Susto · Estado Normal"},
    "mt018": {"precio": 2000,  "tipo": "mt", "mt_move": "thief",          "desc": "📀 MT018 — Robo · Físico Siniestro · Poder 60"},
    "mt025": {"precio": 2000,  "tipo": "mt", "mt_move": "protect",        "desc": "📀 MT025 — Protección · Estado Normal"},
    "mt028": {"precio": 3000,  "tipo": "mt", "mt_move": "bulldoze",       "desc": "📀 MT028 — Pisotón · Físico Tierra · Poder 60"},
    "mt029": {"precio": 1500,  "tipo": "mt", "mt_move": "charm",          "desc": "📀 MT029 — Encanto · Estado Hada"},
    "mt030": {"precio": 2000,  "tipo": "mt", "mt_move": "snarl",          "desc": "📀 MT030 — Rugido Oscuro · Especial Siniestro · Poder 55"},
    # ── Ataques medios ───────────────────────────────────────────────
    "mt032": {"precio": 3000,  "tipo": "mt", "mt_move": "swift",          "desc": "📀 MT032 — Rayo Swift · Especial Normal · Poder 60"},
    "mt033": {"precio": 3000,  "tipo": "mt", "mt_move": "magicalleaf",    "desc": "📀 MT033 — Hoja Mágica · Especial Planta · Poder 60"},
    "mt034": {"precio": 3000,  "tipo": "mt", "mt_move": "icywind",        "desc": "📀 MT034 — Viento Hielo · Especial Hielo · Poder 55"},
    "mt035": {"precio": 3000,  "tipo": "mt", "mt_move": "mudshot",        "desc": "📀 MT035 — Lanzolodo · Especial Tierra · Poder 55"},
    "mt036": {"precio": 3000,  "tipo": "mt", "mt_move": "whirlpool",      "desc": "📀 MT036 — Torbellino · Especial Agua · Poder 35"},
    "mt037": {"precio": 2500,  "tipo": "mt", "mt_move": "dragonbreath",   "desc": "📀 MT037 — Aliento Dragón · Especial Dragón · Poder 60"},
    "mt041": {"precio": 5000,  "tipo": "mt", "mt_move": "foulplay",       "desc": "📀 MT041 — Juego Sucio · Físico Siniestro · Poder 95"},
    "mt042": {"precio": 2000,  "tipo": "mt", "mt_move": "nightshade",     "desc": "📀 MT042 — Sombra Noche · Especial Fantasma"},
    "mt043": {"precio": 2500,  "tipo": "mt", "mt_move": "revenge",        "desc": "📀 MT043 — Desquite · Físico Lucha · Poder 60"},
    "mt044": {"precio": 3000,  "tipo": "mt", "mt_move": "electroball",    "desc": "📀 MT044 — Esfera Eléctrica · Especial Eléctrico"},
    "mt045": {"precio": 4000,  "tipo": "mt", "mt_move": "dig",            "desc": "📀 MT045 — Excavar · Físico Tierra · Poder 80"},
    "mt046": {"precio": 4000,  "tipo": "mt", "mt_move": "avalanche",      "desc": "📀 MT046 — Alud · Físico Hielo · Poder 60"},
    "mt047": {"precio": 2000,  "tipo": "mt", "mt_move": "endure",         "desc": "📀 MT047 — Aguante · Estado Normal"},
    # ── Clima ────────────────────────────────────────────────────────
    "mt050": {"precio": 3000,  "tipo": "mt", "mt_move": "raindance",      "desc": "📀 MT050 — Danza Lluvia · Estado Agua"},
    "mt051": {"precio": 3000,  "tipo": "mt", "mt_move": "sandstorm",      "desc": "📀 MT051 — Tormenta Arena · Estado Roca"},
    "mt052": {"precio": 3000,  "tipo": "mt", "mt_move": "snowscape",      "desc": "📀 MT052 — Nevada · Estado Hielo"},
    "mt053": {"precio": 3000,  "tipo": "mt", "mt_move": "sunnyday",       "desc": "📀 MT053 — Día Soleado · Estado Fuego"},
    # ── Pantallas y buffs ─────────────────────────────────────────────
    "mt055": {"precio": 2500,  "tipo": "mt", "mt_move": "brine",          "desc": "📀 MT055 — Salmuera · Especial Agua · Poder 65"},
    "mt056": {"precio": 5000,  "tipo": "mt", "mt_move": "uturn",          "desc": "📀 MT056 — Ida y Vuelta · Físico Bicho · Poder 70"},
    "mt057": {"precio": 2500,  "tipo": "mt", "mt_move": "retaliate",      "desc": "📀 MT057 — Represalia · Físico Normal · Poder 70"},
    "mt058": {"precio": 5000,  "tipo": "mt", "mt_move": "brickbreak",     "desc": "📀 MT058 — Romperrocas · Físico Lucha · Poder 75"},
    "mt059": {"precio": 5000,  "tipo": "mt", "mt_move": "zenheadbutt",    "desc": "📀 MT059 — Cabezazo Zen · Físico Psíquico · Poder 80"},
    "mt061": {"precio": 5000,  "tipo": "mt", "mt_move": "shadowclaw",     "desc": "📀 MT061 — Garra Sombría · Físico Fantasma · Poder 70"},
    "mt062": {"precio": 4000,  "tipo": "mt", "mt_move": "fling",          "desc": "📀 MT062 — Lanzamiento · Físico Siniestro"},
    "mt063": {"precio": 6000,  "tipo": "mt", "mt_move": "psychic",        "desc": "📀 MT063 — Psíquico · Especial Psíquico · Poder 90"},
    "mt064": {"precio": 4000,  "tipo": "mt", "mt_move": "bulkup",         "desc": "📀 MT064 — Corpulencia · Estado Lucha"},
    "mt065": {"precio": 6000,  "tipo": "mt", "mt_move": "drainpunch",     "desc": "📀 MT065 — Puño Drenaje · Físico Lucha · Poder 75"},
    "mt066": {"precio": 3000,  "tipo": "mt", "mt_move": "thunderwave",    "desc": "📀 MT066 — Onda Trueno · Estado Eléctrico"},
    "mt067": {"precio": 8000,  "tipo": "mt", "mt_move": "icebeam",        "desc": "📀 MT067 — Rayo Hielo · Especial Hielo · Poder 90"},
    "mt068": {"precio": 3000,  "tipo": "mt", "mt_move": "firespin",       "desc": "📀 MT068 — Torbellino Fuego · Especial Fuego · Poder 35"},
    "mt069": {"precio": 2000,  "tipo": "mt", "mt_move": "rest",           "desc": "📀 MT069 — Descanso · Estado Psíquico"},
    "mt070": {"precio": 2000,  "tipo": "mt", "mt_move": "sleeptalk",      "desc": "📀 MT070 — Sonámbulo · Estado Normal"},
    "mt074": {"precio": 3000,  "tipo": "mt", "mt_move": "reflect",        "desc": "📀 MT074 — Reflejo · Estado Psíquico"},
    "mt075": {"precio": 3000,  "tipo": "mt", "mt_move": "lightscreen",    "desc": "📀 MT075 — Pantalla de Luz · Estado Eléctrico"},
    "mt077": {"precio": 6000,  "tipo": "mt", "mt_move": "heatwave",       "desc": "📀 MT077 — Ola de Calor · Especial Fuego · Poder 95"},
    "mt078": {"precio": 7000,  "tipo": "mt", "mt_move": "darkpulse",      "desc": "📀 MT078 — Pulso Siniestro · Especial Siniestro · Poder 80"},
    "mt079": {"precio": 8000,  "tipo": "mt", "mt_move": "outrage",        "desc": "📀 MT079 — Furia Dragón · Físico Dragón · Poder 120"},
    "mt080": {"precio": 5000,  "tipo": "mt", "mt_move": "rockslide",      "desc": "📀 MT080 — Avalancha Roca · Físico Roca · Poder 75"},
    "mt081": {"precio": 4000,  "tipo": "mt", "mt_move": "bulletseed",     "desc": "📀 MT081 — Pistón Semilla · Físico Planta · Poder 25×2-5"},
    "mt085": {"precio": 8000,  "tipo": "mt", "mt_move": "thunderbolt",    "desc": "📀 MT085 — Rayo · Especial Eléctrico · Poder 90"},
    "mt086": {"precio": 7000,  "tipo": "mt", "mt_move": "energyball",     "desc": "📀 MT086 — Bola de Energía · Especial Planta · Poder 90"},
    "mt087": {"precio": 7000,  "tipo": "mt", "mt_move": "dragonpulse",    "desc": "📀 MT087 — Pulso Dragón · Especial Dragón · Poder 85"},
    "mt089": {"precio": 4000,  "tipo": "mt", "mt_move": "bodyslam",       "desc": "📀 MT089 — Golpe Cuerpo · Físico Normal · Poder 85"},
    "mt090": {"precio": 7000,  "tipo": "mt", "mt_move": "surf",           "desc": "📀 MT090 — Surf · Especial Agua · Poder 90"},
    "mt091": {"precio": 7000,  "tipo": "mt", "mt_move": "liquidation",    "desc": "📀 MT091 — Hidro Avión · Físico Agua · Poder 85"},
    "mt092": {"precio": 7000,  "tipo": "mt", "mt_move": "shadowball",     "desc": "📀 MT092 — Bola Sombra · Especial Fantasma · Poder 80"},
    "mt094": {"precio": 7000,  "tipo": "mt", "mt_move": "fly",            "desc": "📀 MT094 — Vuelo · Físico Volador · Poder 90"},
    "mt096": {"precio": 10000, "tipo": "mt", "mt_move": "earthquake",     "desc": "📀 MT096 — Terremoto · Físico Tierra · Poder 100"},
    "mt097": {"precio": 6000,  "tipo": "mt", "mt_move": "auroraveil",     "desc": "📀 MT097 — Velo Aurora · Estado Hielo"},
    "mt098": {"precio": 7000,  "tipo": "mt", "mt_move": "flashcannon",    "desc": "📀 MT098 — Cañón Destello · Especial Acero · Poder 80"},
    "mt100": {"precio": 6000,  "tipo": "mt", "mt_move": "nastyplot",      "desc": "📀 MT100 — Maquinación · Estado Siniestro"},
    "mt102": {"precio": 9000,  "tipo": "mt", "mt_move": "hydropump",      "desc": "📀 MT102 — Hidrobomba · Especial Agua · Poder 110"},
    "mt103": {"precio": 9000,  "tipo": "mt", "mt_move": "solarbeam",      "desc": "📀 MT103 — Rayo Solar · Especial Planta · Poder 120"},
    "mt104": {"precio": 6000,  "tipo": "mt", "mt_move": "crunch",         "desc": "📀 MT104 — Triturar · Físico Siniestro · Poder 80"},
    "mt106": {"precio": 7000,  "tipo": "mt", "mt_move": "waterfall",      "desc": "📀 MT106 — Cascada · Físico Agua · Poder 80"},
    "mt108": {"precio": 8000,  "tipo": "mt", "mt_move": "trickroom",      "desc": "📀 MT108 — Sala Trampa · Estado Psíquico"},
    "mt109": {"precio": 8000,  "tipo": "mt", "mt_move": "flamethrower",   "desc": "📀 MT109 — Lanzallamas · Especial Fuego · Poder 90"},
    "mt110": {"precio": 6000,  "tipo": "mt", "mt_move": "grassknot",      "desc": "📀 MT110 — Hierba Lazo · Especial Planta · Poder varía"},
    "mt111": {"precio": 7000,  "tipo": "mt", "mt_move": "gunkshot",       "desc": "📀 MT111 — Tiro Sucio · Físico Veneno · Poder 120"},
    "mt112": {"precio": 8000,  "tipo": "mt", "mt_move": "aurasphere",     "desc": "📀 MT112 — Esfera Aural · Especial Lucha · Poder 80"},
    "mt113": {"precio": 12000, "tipo": "mt", "mt_move": "dracometeor",    "desc": "📀 MT113 — Dracometeoro · Especial Dragón · Poder 130"},
    "mt117": {"precio": 12000, "tipo": "mt", "mt_move": "hyperbeam",      "desc": "📀 MT117 — Hiperrrayo · Especial Normal · Poder 150"},
    "mt118": {"precio": 12000, "tipo": "mt", "mt_move": "gigaimpact",     "desc": "📀 MT118 — Giga Impacto · Físico Normal · Poder 150"},
    "mt119": {"precio": 3000,  "tipo": "mt", "mt_move": "icywind",        "desc": "📀 MT119 — Viento Hielo · Especial Hielo · Poder 55"},
    "mt122": {"precio": 6000,  "tipo": "mt", "mt_move": "swordsdance",    "desc": "📀 MT122 — Danza Espada · Estado Normal"},
    "mt126": {"precio": 6000,  "tipo": "mt", "mt_move": "gigadrain",      "desc": "📀 MT126 — Mega Drenadoras · Especial Planta · Poder 75"},
    "mt128": {"precio": 6000,  "tipo": "mt", "mt_move": "airslash",       "desc": "📀 MT128 — Tajo Aéreo · Especial Volador · Poder 75"},
    "mt129": {"precio": 6000,  "tipo": "mt", "mt_move": "calmmind",       "desc": "📀 MT129 — Mente Zen · Estado Psíquico"},
    "mt130": {"precio": 9000,  "tipo": "mt", "mt_move": "moonblast",      "desc": "📀 MT130 — Fuerza Lunar · Especial Hada · Poder 95"},
    "mt134": {"precio": 10000, "tipo": "mt", "mt_move": "fireblast",      "desc": "📀 MT134 — Deflagración · Especial Fuego · Poder 110"},
    "mt136": {"precio": 10000, "tipo": "mt", "mt_move": "closecombat",    "desc": "📀 MT136 — Combate · Físico Lucha · Poder 120"},
    "mt138": {"precio": 10000, "tipo": "mt", "mt_move": "focusblast",     "desc": "📀 MT138 — Bola de Enfoque · Especial Lucha · Poder 120"},
    "mt140": {"precio": 8000,  "tipo": "mt", "mt_move": "megahorn",       "desc": "📀 MT140 — Megacuerno · Físico Bicho · Poder 120"},
    "mt141": {"precio": 10000, "tipo": "mt", "mt_move": "blizzard",       "desc": "📀 MT141 — Ventisca · Especial Hielo · Poder 110"},
    "mt146": {"precio": 8000,  "tipo": "mt", "mt_move": "highhorsepower", "desc": "📀 MT146 — Fuerza Equina · Físico Tierra · Poder 95"},
    "mt147": {"precio": 5000,  "tipo": "mt", "mt_move": "crosspoison",    "desc": "📀 MT147 — Cruz Veneno · Físico Veneno · Poder 70"},
    "mt149": {"precio": 8000,  "tipo": "mt", "mt_move": "hypervoice",     "desc": "📀 MT149 — Vozarrón · Especial Normal · Poder 90"},
    "mt151": {"precio": 9000,  "tipo": "mt", "mt_move": "hardpress",      "desc": "📀 MT151 — Presión Intensa · Físico Acero · Poder varía"},
    "mt152": {"precio": 7000,  "tipo": "mt", "mt_move": "poisonjab",      "desc": "📀 MT152 — Picotazo Venenoso · Físico Veneno · Poder 80"},
    "mt157": {"precio": 10000, "tipo": "mt", "mt_move": "overheat",       "desc": "📀 MT157 — Sofoco · Especial Fuego · Poder 130"},
    "mt158": {"precio": 9000,  "tipo": "mt", "mt_move": "hurricane",      "desc": "📀 MT158 — Huracán · Especial Volador · Poder 110"},
    "mt160": {"precio": 10000, "tipo": "mt", "mt_move": "flareblitz",     "desc": "📀 MT160 — Llamarada · Físico Fuego · Poder 120"},
    "mt161": {"precio": 8000,  "tipo": "mt", "mt_move": "focuspunch",     "desc": "📀 MT161 — Puño Certero · Físico Lucha · Poder 150"},
    "mt163": {"precio": 9000,  "tipo": "mt", "mt_move": "wavecrash",      "desc": "📀 MT163 — Crujido · Físico Agua · Poder 120"},
    "mt164": {"precio": 4000,  "tipo": "mt", "mt_move": "aquajet",        "desc": "📀 MT164 — Acua Jet · Físico Agua · Poder 40 · Prioridad +1"},
    "mt168": {"precio": 9000,  "tipo": "mt", "mt_move": "bravebird",      "desc": "📀 MT168 — Pájaro Osado · Físico Volador · Poder 120"},
    "mt171": {"precio": 8000,  "tipo": "mt", "mt_move": "ironhead",       "desc": "📀 MT171 — Cabeza de Hierro · Físico Acero · Poder 80"},
    "mt174": {"precio": 8000,  "tipo": "mt", "mt_move": "bodypress",      "desc": "📀 MT174 — Plancha · Físico Lucha · Poder 80"},
    "mt179": {"precio": 5000,  "tipo": "mt", "mt_move": "drainingkiss",   "desc": "📀 MT179 — Beso Drenaje · Especial Hada · Poder 50"},
    "mt180": {"precio": 9000,  "tipo": "mt", "mt_move": "ruination",      "desc": "📀 MT180 — Ruina · Especial Siniestro · Poder varía"},
    "mt182": {"precio": 9000,  "tipo": "mt", "mt_move": "axekick",        "desc": "📀 MT182 — Patada Hacha · Físico Lucha · Poder 120"},
    "mt198": {"precio": 6000,  "tipo": "mt", "mt_move": "icespinner",     "desc": "📀 MT198 — Giro Helado · Físico Hielo · Poder 80"},
    "mt200": {"precio": 12000, "tipo": "mt", "mt_move": "terablast",      "desc": "📀 MT200 — Tera Estallido · Especial/Físico según Tera · Poder 80"},
    "mt205": {"precio": 7000,  "tipo": "mt", "mt_move": "iciclecrash",    "desc": "📀 MT205 — Carámbano · Físico Hielo · Poder 85"},
    "mt206": {"precio": 7000,  "tipo": "mt", "mt_move": "dragonclaw",     "desc": "📀 MT206 — Garra Dragón · Físico Dragón · Poder 80"},
    "mt207": {"precio": 7000,  "tipo": "mt", "mt_move": "psychicfangs",   "desc": "📀 MT207 — Colmillos Psíquicos · Físico Psíquico · Poder 85"},
    "mt208": {"precio": 6000,  "tipo": "mt", "mt_move": "sludgebomb",     "desc": "📀 MT208 — Bomba Lodo · Especial Veneno · Poder 90"},
    "mt210": {"precio": 4000,  "tipo": "mt", "mt_move": "mistyterrain",   "desc": "📀 MT210 — Terreno de Niebla · Estado Hada"},
    "mt211": {"precio": 4000,  "tipo": "mt", "mt_move": "electricterrain","desc": "📀 MT211 — Terreno Eléctrico · Estado Eléctrico"},
    "mt212": {"precio": 4000,  "tipo": "mt", "mt_move": "psychicterrain", "desc": "📀 MT212 — Terreno Psíquico · Estado Psíquico"},
    "mt213": {"precio": 4000,  "tipo": "mt", "mt_move": "grassyterrain",  "desc": "📀 MT213 — Terreno de Hierba · Estado Planta"},
    "mt215": {"precio": 8000,  "tipo": "mt", "mt_move": "expandingforce", "desc": "📀 MT215 — Fuerza Expansiva · Especial Psíquico · Poder 80"},
    "mt220": {"precio": 8000,  "tipo": "mt", "mt_move": "gravapple",      "desc": "📀 MT220 — Manzana Gravity · Físico Planta · Poder 80"},
    "mt227": {"precio": 6000,  "tipo": "mt", "mt_move": "saltcure",       "desc": "📀 MT227 — Cura Sal · Estado Roca"},
    "mt231": {"precio": 12000, "tipo": "mt", "mt_move": "collisioncourse","desc": "📀 MT231 — Calambreado · Físico Lucha · Poder 100"},
    "mt233": {"precio": 9000,  "tipo": "mt", "mt_move": "direclaws",      "desc": "📀 MT233 — Garras Duras · Físico Normal · Poder 80"},
    "mt236": {"precio": 12000, "tipo": "mt", "mt_move": "aerialace",      "desc": "📀 MT236 — Acróbata · Físico Volador · Poder 110"},
    "mt237": {"precio": 12000, "tipo": "mt", "mt_move": "dualwingbeat",   "desc": "📀 MT237 — Ala Bis · Físico Volador · Poder 40"},
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
        "items": list(MT_ITEMS_DB.keys()),
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