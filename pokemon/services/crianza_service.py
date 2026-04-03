"""
Servicio de Crianza Pokémon
Sistema completo: guardería, huevos, herencia de IVs/naturaleza/movimientos,
pasos por caracteres escritos, eclosión con notificación y mote.
"""

import json
import logging
import random
from typing import Optional, Dict, List, Tuple
from database import db_manager

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ──────────────────────────────────────────────────────────────────────────────

DITTO_ID = 132

# Pasos (palabras escritas en el grupo) necesarios para que la guardería
# produzca un huevo con los dos Pokémon depositados.
# Amuleto Iris duplica los pasos que cuentan hacia este umbral.
PASOS_PARA_PRODUCIR_HUEVO: int = 250
PASOS_BASE_ECLOSION:       int = 1280   # 25 % de 5120
# Factor reductor a aplicar si usas cálculos dinámicos de pasos:
FACTOR_REDUCCION_PASOS: float = 0.25

def aplicar_reduccion_pasos_guarderia() -> None:
    """
    Aplica la reducción de pasos al módulo crianza_service en tiempo de
    ejecución, sin modificar el archivo fuente.
 
    Llamar una sola vez al arrancar el bot (ej. en UniverseBot.py después
    de importar todos los módulos):
 
        from pokemon.services.crianza_service_steps_patch import aplicar_reduccion_pasos_guarderia
        aplicar_reduccion_pasos_guarderia()
    """
    try:
        from pokemon.services import crianza_service as _cs
 
        # ── Constantes de producción ──────────────────────────────────────────
        for attr in (
            "PASOS_PARA_PRODUCIR_HUEVO",
            "PASOS_PRODUCCION",
            "PASOS_GUARDERIA",
            "PASOS_HUEVO",
        ):
            val = getattr(_cs, attr, None)
            if val is not None and isinstance(val, (int, float)):
                nuevo = max(50, int(val * FACTOR_REDUCCION_PASOS))
                setattr(_cs, attr, nuevo)
                import logging as _log
                _log.getLogger(__name__).info(
                    f"[CRIANZA_PATCH] {attr}: {val} → {nuevo}"
                )
 
        # ── Constantes de eclosión ────────────────────────────────────────────
        for attr in (
            "PASOS_BASE_ECLOSION",
            "PASOS_ECLOSION",
            "CICLOS_ECLOSION",
            "PASOS_CICLO",
        ):
            val = getattr(_cs, attr, None)
            if val is not None and isinstance(val, (int, float)):
                nuevo = max(50, int(val * FACTOR_REDUCCION_PASOS))
                setattr(_cs, attr, nuevo)
                import logging as _log
                _log.getLogger(__name__).info(
                    f"[CRIANZA_PATCH] {attr}: {val} → {nuevo}"
                )
 
        # ── Si usa un dict de pasos por especie / grupo ───────────────────────
        for attr in ("PASOS_POR_GRUPO", "PASOS_POR_ESPECIE", "EGG_STEPS"):
            d = getattr(_cs, attr, None)
            if d is not None and isinstance(d, dict):
                for k in d:
                    if isinstance(d[k], (int, float)):
                        d[k] = max(50, int(d[k] * FACTOR_REDUCCION_PASOS))
                import logging as _log
                _log.getLogger(__name__).info(
                    f"[CRIANZA_PATCH] {attr}: reducido al 25 %"
                )
 
    except Exception as e:
        import logging as _log
        _log.getLogger(__name__).error(f"[CRIANZA_PATCH] Error aplicando reducción: {e}")

# Pokémon que no pueden criar (legendarios y asexuados especiales)
POKEMON_UNDISCOVERED: set = {
    144, 145, 146, 150, 151,
    243, 244, 245, 249, 250, 251,
    377, 378, 379, 380, 381, 382, 383, 384, 385, 386,
    480, 481, 482, 483, 484, 485, 486, 487, 488, 489, 490, 491, 492, 493,
    638, 639, 640, 641, 642, 643, 644, 645, 646, 647, 648, 649,
    716, 717, 718, 719, 720, 721,
    785, 786, 787, 788, 789, 790, 791, 792, 800, 801, 802,
    888, 889, 890, 891, 892, 893, 894, 895, 896, 897, 898,
}

# 100% macho
SOLO_MACHO: set = {32, 33, 34, 106, 107, 128, 236, 237}

# 100% hembra
SOLO_HEMBRA: set = {29, 30, 31, 115, 238, 241}

# Sin género — incluye Ditto, Magnemite, Voltorb, Staryu, Porygon, etc.
SIN_GENERO: set = {
    81, 82,          # Magnemite, Magneton
    100, 101,        # Voltorb, Electrode
    120, 121,        # Staryu, Starmie
    132,             # Ditto
    137, 233, 474,   # Porygon, Porygon2, Porygon-Z
    343, 344,        # Baltoy, Claydol
    374, 375, 376,   # Beldum, Metang, Metagross
}

# Grupos de huevos por pokemonID (Gen 1-4 completo + más comunes Gen 5+)
GRUPOS_HUEVOS: Dict[int, List[str]] = {
    # ── GEN 1 ─────────────────────────────────────────────────────────────────
    1: ["Monster", "Grass"], 2: ["Monster", "Grass"], 3: ["Monster", "Grass"],
    4: ["Monster", "Dragon"], 5: ["Monster", "Dragon"], 6: ["Monster", "Dragon"],
    7: ["Monster", "Water1"], 8: ["Monster", "Water1"], 9: ["Monster", "Water1"],
    10: ["Bug"], 11: ["Bug"], 12: ["Bug"],
    13: ["Bug"], 14: ["Bug"], 15: ["Bug"],
    16: ["Flying"], 17: ["Flying"], 18: ["Flying"],
    19: ["Field"], 20: ["Field"],
    21: ["Flying"], 22: ["Flying"],
    23: ["Field"], 24: ["Field"],
    25: ["Field", "Fairy"], 26: ["Field", "Fairy"],
    27: ["Field"], 28: ["Field"],
    29: ["Field"], 30: ["Field"], 31: ["Field"],
    32: ["Field"], 33: ["Field"], 34: ["Field"],
    35: ["Fairy"], 36: ["Fairy"],
    37: ["Field"], 38: ["Field"],
    39: ["Fairy"], 40: ["Fairy"],
    41: ["Flying"], 42: ["Flying"],
    43: ["Grass"], 44: ["Grass"], 45: ["Grass"],
    46: ["Bug", "Grass"], 47: ["Bug", "Grass"],
    48: ["Bug"], 49: ["Bug"],
    50: ["Field"], 51: ["Field"],
    52: ["Field"], 53: ["Field"],
    54: ["Field", "Water1"], 55: ["Field", "Water1"],
    56: ["Field"], 57: ["Field"],
    58: ["Field"], 59: ["Field"],
    60: ["Water1"], 61: ["Water1"], 62: ["Water1"],
    63: ["Human-Like"], 64: ["Human-Like"], 65: ["Human-Like"],
    66: ["Human-Like"], 67: ["Human-Like"], 68: ["Human-Like"],
    69: ["Grass"], 70: ["Grass"], 71: ["Grass"],
    72: ["Water3"], 73: ["Water3"],
    74: ["Mineral"], 75: ["Mineral"], 76: ["Mineral"],
    77: ["Field"], 78: ["Field"],
    79: ["Monster", "Water1"], 80: ["Monster", "Water1"],
    81: ["Mineral"], 82: ["Mineral"],
    83: ["Flying", "Field"],
    84: ["Flying"], 85: ["Flying"],
    86: ["Water1"], 87: ["Water1"],
    88: ["Amorphous"], 89: ["Amorphous"],
    90: ["Water3"], 91: ["Water3"],
    92: ["Amorphous"], 93: ["Amorphous"], 94: ["Amorphous"],
    95: ["Mineral"],
    96: ["Human-Like"], 97: ["Human-Like"],
    98: ["Water3"], 99: ["Water3"],
    100: ["Mineral"], 101: ["Mineral"],
    102: ["Grass"], 103: ["Grass"],
    104: ["Monster"], 105: ["Monster"],
    106: ["Human-Like"], 107: ["Human-Like"],
    108: ["Monster"],
    109: ["Amorphous"], 110: ["Amorphous"],
    111: ["Monster", "Field"], 112: ["Monster", "Field"],
    113: ["Fairy"],
    114: ["Grass"],
    115: ["Monster"],
    116: ["Water1", "Dragon"], 117: ["Water1", "Dragon"],
    118: ["Water2"], 119: ["Water2"],
    120: ["Water3"], 121: ["Water3"],
    122: ["Human-Like"],
    123: ["Bug"],
    124: ["Human-Like"],
    125: ["Human-Like"],
    126: ["Human-Like"],
    127: ["Bug"],
    128: ["Field"],
    129: ["Water2", "Dragon"], 130: ["Water2", "Dragon"],
    131: ["Monster", "Water1"],
    132: ["Ditto"],
    133: ["Field"],
    134: ["Field"], 135: ["Field"], 136: ["Field"],  # Eeveelutions
    137: ["Mineral"],
    138: ["Water3"], 139: ["Water3"],
    140: ["Water3"], 141: ["Water3"],
    142: ["Flying"],
    143: ["Monster"],
    144: ["Undiscovered"], 145: ["Undiscovered"], 146: ["Undiscovered"],
    147: ["Water1", "Dragon"], 148: ["Water1", "Dragon"], 149: ["Water1", "Dragon"],
    150: ["Undiscovered"], 151: ["Undiscovered"],
    # ── GEN 2 ─────────────────────────────────────────────────────────────────
    152: ["Monster", "Grass"], 153: ["Monster", "Grass"], 154: ["Monster", "Grass"],
    155: ["Monster", "Field"], 156: ["Monster", "Field"], 157: ["Monster", "Field"],
    158: ["Monster", "Water1"], 159: ["Monster", "Water1"], 160: ["Monster", "Water1"],
    161: ["Field"], 162: ["Field"],
    163: ["Flying"], 164: ["Flying"],
    165: ["Bug", "Flying"], 166: ["Bug", "Flying"],
    167: ["Bug"], 168: ["Bug"],
    169: ["Flying"],
    170: ["Water2"], 171: ["Water2"],
    172: ["Field", "Fairy"],   # Pichu baby
    173: ["Fairy"],            # Cleffa baby
    174: ["Fairy"],            # Igglybuff baby
    175: ["Fairy"], 176: ["Fairy"],
    177: ["Flying"], 178: ["Flying"],
    179: ["Field"], 180: ["Field"], 181: ["Field"],
    182: ["Grass"],
    183: ["Water1", "Fairy"], 184: ["Water1", "Fairy"],
    185: ["Mineral"],
    186: ["Water1"],
    187: ["Grass"], 188: ["Grass"], 189: ["Grass"],
    190: ["Field"],
    191: ["Grass"], 192: ["Grass"],
    193: ["Bug"], 194: ["Water1", "Field"], 195: ["Water1", "Field"],
    196: ["Field"], 197: ["Field"],
    198: ["Flying"],
    199: ["Monster", "Water1"],
    200: ["Amorphous"],
    201: ["Mineral"],            # Unown
    202: ["Amorphous"],
    203: ["Field"],
    204: ["Bug"], 205: ["Bug"],
    206: ["Field"],
    207: ["Bug"],
    208: ["Mineral", "Field"],   # Steelix
    209: ["Field", "Fairy"], 210: ["Field", "Fairy"],
    211: ["Water2"],
    212: ["Bug"],                # Scizor
    213: ["Bug"],
    214: ["Bug"],
    215: ["Field"],
    216: ["Field"], 217: ["Field"],
    218: ["Amorphous"], 219: ["Amorphous"],
    220: ["Field"], 221: ["Field"],
    222: ["Water3"],
    223: ["Water2"], 224: ["Water2"],
    225: ["Water2"],
    226: ["Water1"], 227: ["Flying"],
    228: ["Field"], 229: ["Field"],
    230: ["Water1", "Dragon"],   # Kingdra
    231: ["Field"], 232: ["Field"],
    233: ["Mineral"],
    234: ["Field"],
    235: ["Field"],
    236: ["Human-Like"], 237: ["Human-Like"],
    238: ["Human-Like"],
    239: ["Human-Like"],         # Elekid baby
    240: ["Human-Like"],         # Magby baby
    241: ["Field"],
    242: ["Fairy"],
    243: ["Undiscovered"], 244: ["Undiscovered"], 245: ["Undiscovered"],
    246: ["Monster", "Dragon"], 247: ["Monster", "Dragon"], 248: ["Monster", "Dragon"],
    249: ["Undiscovered"], 250: ["Undiscovered"], 251: ["Undiscovered"],
    # ── GEN 3 ─────────────────────────────────────────────────────────────────
    252: ["Monster", "Dragon"], 253: ["Monster", "Dragon"], 254: ["Monster", "Dragon"],
    255: ["Monster", "Field"],  256: ["Monster", "Field"],  257: ["Monster", "Field"],
    258: ["Monster", "Water1"], 259: ["Monster", "Water1"], 260: ["Monster", "Water1"],
    261: ["Field"], 262: ["Field"],
    263: ["Field"], 264: ["Field"],
    265: ["Bug"], 266: ["Bug"], 267: ["Bug"], 268: ["Bug"], 269: ["Bug"],
    270: ["Water1", "Grass"], 271: ["Water1", "Grass"], 272: ["Water1", "Grass"],
    273: ["Grass"], 274: ["Grass"], 275: ["Grass"],
    276: ["Flying"], 277: ["Flying"],
    278: ["Flying", "Water1"], 279: ["Flying", "Water1"],
    280: ["Amorphous"], 281: ["Amorphous"], 282: ["Amorphous"],
    283: ["Bug", "Water1"], 284: ["Bug", "Water1"],
    285: ["Grass"], 286: ["Grass"],
    287: ["Field"], 288: ["Field"], 289: ["Field"],
    290: ["Bug"], 291: ["Bug"], 292: ["Undiscovered"],
    293: ["Field", "Mineral"], 294: ["Field", "Mineral"], 295: ["Field", "Mineral"],
    296: ["Human-Like"], 297: ["Human-Like"],
    298: ["Water1", "Fairy"],    # Azurill baby
    299: ["Mineral"],
    300: ["Field", "Fairy"], 301: ["Field", "Fairy"],
    302: ["Amorphous"],
    303: ["Fairy"],
    304: ["Mineral"], 305: ["Mineral"], 306: ["Mineral"],
    307: ["Human-Like"], 308: ["Human-Like"],
    309: ["Field"], 310: ["Field"],
    311: ["Fairy"], 312: ["Fairy"],
    313: ["Bug"], 314: ["Bug"],
    315: ["Grass", "Fairy"],
    316: ["Amorphous"], 317: ["Amorphous"],
    318: ["Water2"], 319: ["Water2"],
    320: ["Water2"], 321: ["Water2"],
    322: ["Field"], 323: ["Field"],
    324: ["Field"],
    325: ["Field"], 326: ["Field"],
    327: ["Field"],
    328: ["Bug"], 329: ["Bug"], 330: ["Bug"],
    331: ["Grass"], 332: ["Grass"],
    333: ["Flying"], 334: ["Flying"],
    335: ["Field"], 336: ["Field"],
    337: ["Mineral"], 338: ["Mineral"],
    339: ["Water2"], 340: ["Water2"],
    341: ["Water3"], 342: ["Water3"],
    343: ["Mineral"], 344: ["Mineral"],
    345: ["Water3", "Grass"], 346: ["Water3", "Grass"],
    347: ["Water3", "Bug"], 348: ["Water3", "Bug"],
    349: ["Water2"], 350: ["Water2"],
    351: ["Amorphous"],
    352: ["Field"],
    353: ["Amorphous"], 354: ["Amorphous"],
    355: ["Amorphous"], 356: ["Amorphous"],
    357: ["Grass"],
    358: ["Amorphous"],
    359: ["Field"],
    360: ["Water1", "Fairy"],    # Wynaut baby
    361: ["Mineral"], 362: ["Mineral"],
    363: ["Water1"], 364: ["Water1"], 365: ["Water1"],
    366: ["Water3"], 367: ["Water3"],
    368: ["Water3"],
    369: ["Water2"],
    370: ["Water1"],
    371: ["Monster", "Dragon"], 372: ["Monster", "Dragon"], 373: ["Monster", "Dragon"],
    374: ["Mineral"], 375: ["Mineral"], 376: ["Mineral"],
    377: ["Undiscovered"], 378: ["Undiscovered"], 379: ["Undiscovered"],
    380: ["Undiscovered"], 381: ["Undiscovered"], 382: ["Undiscovered"],
    383: ["Undiscovered"], 384: ["Undiscovered"],
    385: ["Undiscovered"], 386: ["Undiscovered"],
    # ── GEN 4 ─────────────────────────────────────────────────────────────────
    387: ["Monster", "Grass"], 388: ["Monster", "Grass"], 389: ["Monster", "Grass"],
    390: ["Field"],            391: ["Field"],            392: ["Field"],
    393: ["Water1"],           394: ["Water1"],           395: ["Water1"],
    396: ["Flying"],           397: ["Flying"],           398: ["Flying"],
    399: ["Field"],            400: ["Field"],
    401: ["Bug"],              402: ["Bug"],
    403: ["Field"],            404: ["Field"],            405: ["Field"],
    406: ["Fairy", "Grass"],   # Budew baby
    407: ["Fairy", "Grass"],
    408: ["Monster"],          409: ["Monster"],
    410: ["Monster"],          411: ["Monster"],
    412: ["Bug"],              413: ["Bug"],              414: ["Bug"],
    415: ["Bug"],              416: ["Bug"],
    417: ["Field"],
    418: ["Water1", "Field"], 419: ["Water1", "Field"],
    420: ["Fairy", "Grass"], 421: ["Fairy", "Grass"],
    422: ["Water1", "Amorphous"], 423: ["Water1", "Amorphous"],
    424: ["Field"],
    425: ["Amorphous"], 426: ["Amorphous"],
    427: ["Field"],    428: ["Field"],
    429: ["Amorphous"],
    430: ["Flying"],
    431: ["Field"],    432: ["Field"],
    433: ["Mineral"],            # Chingling baby
    434: ["Field"],    435: ["Field"],
    436: ["Mineral"],  437: ["Mineral"],
    438: ["Mineral"],            # Bonsly baby
    439: ["Human-Like"],         # Mime Jr. baby
    440: ["Fairy"],              # Happiny baby
    441: ["Flying"],
    442: ["Amorphous"],
    443: ["Monster", "Dragon"], 444: ["Monster", "Dragon"], 445: ["Monster", "Dragon"],
    446: ["Monster"],            # Munchlax baby
    447: ["Field", "Human-Like"],# Riolu
    448: ["Field", "Human-Like"],# Lucario
    449: ["Field"],  450: ["Field"],
    451: ["Bug"],    452: ["Bug"],
    453: ["Water1"], 454: ["Water1"],
    455: ["Grass"],
    456: ["Water2"], 457: ["Water2"],
    458: ["Water1"],
    459: ["Grass"],  460: ["Grass"],
    461: ["Field"],
    462: ["Mineral"],
    463: ["Field"],
    464: ["Monster", "Field"],
    465: ["Grass"],
    466: ["Human-Like"],
    467: ["Human-Like"],
    468: ["Flying", "Fairy"],
    469: ["Bug"],
    470: ["Field"],  471: ["Field"],
    472: ["Bug"],
    473: ["Field"],
    474: ["Mineral"],
    475: ["Human-Like", "Amorphous"],
    476: ["Mineral"],
    477: ["Amorphous"],
    478: ["Fairy"],
    479: ["Mineral"],
    480: ["Undiscovered"], 481: ["Undiscovered"], 482: ["Undiscovered"],
    483: ["Undiscovered"], 484: ["Undiscovered"], 485: ["Undiscovered"],
    486: ["Undiscovered"], 487: ["Undiscovered"], 488: ["Undiscovered"],
    489: ["Undiscovered"], 490: ["Undiscovered"], 491: ["Undiscovered"],
    492: ["Undiscovered"], 493: ["Undiscovered"],
    # ── GEN 5 ─────────────────────────────────────────────────────────────────
    495: ["Grass"],  496: ["Grass"],  497: ["Grass"],
    498: ["Field"],  499: ["Field"],  500: ["Field"],
    501: ["Field", "Water1"], 502: ["Field", "Water1"], 503: ["Field", "Water1"],
    504: ["Field"],  505: ["Field"],
    506: ["Field"],  507: ["Field"],  508: ["Field"],
    509: ["Field"],  510: ["Field"],
    511: ["Grass"],  512: ["Grass"],
    513: ["Field"],  514: ["Field"],
    515: ["Water1"], 516: ["Water1"],
    517: ["Field"],  518: ["Field"],
    519: ["Flying"], 520: ["Flying"], 521: ["Flying"],
    522: ["Field"],  523: ["Field"],
    524: ["Mineral"],525: ["Mineral"],526: ["Mineral"],
    527: ["Field"],  528: ["Field"],
    529: ["Field"],  530: ["Field"],
    531: ["Field"],
    532: ["Human-Like"],533: ["Human-Like"],534: ["Human-Like"],
    535: ["Water1"], 536: ["Water1"], 537: ["Water1"],
    538: ["Human-Like"],
    539: ["Human-Like"],
    540: ["Bug", "Grass"],541: ["Bug", "Grass"],542: ["Bug", "Grass"],
    543: ["Bug"],    544: ["Bug"],    545: ["Bug"],
    546: ["Grass", "Fairy"],547: ["Grass", "Fairy"],
    548: ["Grass", "Fairy"],549: ["Grass", "Fairy"],
    550: ["Water2"],
    551: ["Field"],  552: ["Field"],  553: ["Field"],
    554: ["Field"],  555: ["Field"],
    556: ["Grass"],
    557: ["Water3"], 558: ["Water3"],
    559: ["Human-Like"],560: ["Human-Like"],
    561: ["Flying"],
    562: ["Amorphous"],563: ["Amorphous"],
    564: ["Water3"], 565: ["Water3"],
    566: ["Flying"], 567: ["Flying"],
    568: ["Amorphous"],569: ["Amorphous"],
    570: ["Field"],  571: ["Field"],
    572: ["Field"],  573: ["Field"],
    574: ["Human-Like"],575: ["Human-Like"],576: ["Human-Like"],
    577: ["Amorphous"],578: ["Amorphous"],579: ["Amorphous"],
    580: ["Water1"], 581: ["Water1"],
    582: ["Mineral"],583: ["Mineral"],584: ["Mineral"],
    585: ["Field"],  586: ["Field"],
    587: ["Flying"],
    588: ["Bug"],    589: ["Bug"],
    590: ["Grass"],  591: ["Grass"],
    592: ["Water1", "Amorphous"],593: ["Water1", "Amorphous"],
    594: ["Water1"],
    595: ["Bug"],    596: ["Bug"],
    597: ["Grass"],  598: ["Grass"],
    599: ["Mineral"],600: ["Mineral"],601: ["Mineral"],
    602: ["Amorphous"],603: ["Amorphous"],604: ["Amorphous"],
    605: ["Amorphous"],606: ["Amorphous"],
    607: ["Amorphous"],608: ["Amorphous"],609: ["Amorphous"],
    610: ["Dragon"], 611: ["Dragon"], 612: ["Dragon"],
    613: ["Field"],  614: ["Field"],
    615: ["Mineral"],
    616: ["Bug"],    617: ["Bug"],
    618: ["Water2"],
    619: ["Human-Like"],620: ["Human-Like"],
    621: ["Dragon"],
    622: ["Mineral"],623: ["Mineral"],
    624: ["Field"],  625: ["Field"],
    626: ["Field"],
    627: ["Flying"], 628: ["Flying"],
    629: ["Flying"], 630: ["Flying"],
    631: ["Field"],  632: ["Bug"],
    633: ["Dragon"], 634: ["Dragon"], 635: ["Dragon"],
    636: ["Bug"],    637: ["Bug"],
    638: ["Undiscovered"],639: ["Undiscovered"],640: ["Undiscovered"],
    641: ["Undiscovered"],642: ["Undiscovered"],643: ["Undiscovered"],
    644: ["Undiscovered"],645: ["Undiscovered"],646: ["Undiscovered"],
    647: ["Undiscovered"],648: ["Undiscovered"],649: ["Undiscovered"],
    # ── GEN 6 ─────────────────────────────────────────────────────────────────
    650: ["Field"],  651: ["Field"],  652: ["Field"],
    653: ["Field"],  654: ["Field"],  655: ["Field"],
    656: ["Water1"], 657: ["Water1"], 658: ["Water1"],
    659: ["Field"],  660: ["Field"],
    661: ["Flying"], 662: ["Flying"], 663: ["Flying"],
    664: ["Bug"],    665: ["Bug"],    666: ["Bug"],
    667: ["Field"],  668: ["Field"],
    669: ["Fairy", "Grass"],670: ["Fairy", "Grass"],671: ["Fairy", "Grass"],
    672: ["Field"],  673: ["Field"],
    674: ["Field"],  675: ["Field"],
    676: ["Field"],
    677: ["Field"],  678: ["Field"],
    679: ["Mineral"],680: ["Mineral"],681: ["Mineral"],
    682: ["Amorphous"],683: ["Amorphous"],
    684: ["Fairy"],  685: ["Fairy"],
    686: ["Water2"], 687: ["Water2"],
    688: ["Water3"], 689: ["Water3"],
    690: ["Water3"], 691: ["Water3"],
    692: ["Water3"], 693: ["Water3"],
    694: ["Bug"],    695: ["Bug"],
    696: ["Monster", "Dragon"],697: ["Monster", "Dragon"],
    698: ["Field"],  699: ["Field"],
    700: ["Fairy"],
    701: ["Fairy"],  702: ["Fairy"],
    703: ["Mineral"],
    704: ["Dragon"], 705: ["Dragon"], 706: ["Dragon"],
    707: ["Mineral"],
    708: ["Grass"],  709: ["Grass"],
    710: ["Amorphous"],711: ["Amorphous"],
    712: ["Mineral"],713: ["Mineral"],
    714: ["Flying"], 715: ["Flying"],
    716: ["Undiscovered"],717: ["Undiscovered"],718: ["Undiscovered"],
    719: ["Undiscovered"],720: ["Undiscovered"],721: ["Undiscovered"],
    # ── GEN 7 ─────────────────────────────────────────────────────────────────
    722: ["Flying"], 723: ["Flying"], 724: ["Flying"],
    725: ["Field"],  726: ["Field"],  727: ["Field"],
    728: ["Water1"], 729: ["Water1"], 730: ["Water1"],
    731: ["Flying"], 732: ["Flying"], 733: ["Flying"],
    734: ["Field"],  735: ["Field"],
    736: ["Bug"],    737: ["Bug"],    738: ["Bug"],
    739: ["Water3"], 740: ["Water3"],
    741: ["Flying"],
    742: ["Fairy"],  743: ["Fairy"],
    744: ["Field"],  745: ["Field"],
    746: ["Water2"],
    747: ["Water3"], 748: ["Water3"],
    749: ["Field"],  750: ["Field"],
    751: ["Bug", "Water3"],752: ["Bug", "Water3"],
    753: ["Grass"],  754: ["Grass"],
    755: ["Grass"],  756: ["Grass"],
    757: ["Field"],  758: ["Field"],
    759: ["Field"],  760: ["Field"],
    761: ["Grass"],  762: ["Grass"],  763: ["Grass"],
    764: ["Fairy", "Grass"],
    765: ["Field"],
    766: ["Field"],
    767: ["Bug"],    768: ["Bug"],
    769: ["Amorphous"],770: ["Amorphous"],
    771: ["Water3"],
    772: ["Undiscovered"],773: ["Field"],
    774: ["Mineral"],
    775: ["Field"],
    776: ["Monster", "Dragon"],
    777: ["Amorphous"],
    778: ["Amorphous"],
    779: ["Water2"],
    780: ["Dragon"],
    781: ["Water3"],
    782: ["Dragon"], 783: ["Dragon"], 784: ["Dragon"],
    785: ["Undiscovered"],786: ["Undiscovered"],
    787: ["Undiscovered"],788: ["Undiscovered"],
    789: ["Undiscovered"],790: ["Undiscovered"],
    791: ["Undiscovered"],792: ["Undiscovered"],
    793: ["Undiscovered"],794: ["Undiscovered"],795: ["Undiscovered"],
    796: ["Undiscovered"],797: ["Undiscovered"],798: ["Undiscovered"],
    799: ["Undiscovered"],800: ["Undiscovered"],
    801: ["Undiscovered"],802: ["Undiscovered"],
    # ── GEN 8 ─────────────────────────────────────────────────────────────────
    810: ["Grass"],  811: ["Grass"],  812: ["Grass"],
    813: ["Field"],  814: ["Field"],  815: ["Field"],
    816: ["Water1"], 817: ["Water1"], 818: ["Water1"],
    819: ["Field"],  820: ["Field"],
    821: ["Flying"], 822: ["Flying"], 823: ["Flying"],
    824: ["Bug"],    825: ["Amorphous"],826: ["Amorphous"],
    827: ["Field"],  828: ["Field"],
    829: ["Grass"],  830: ["Grass"],
    831: ["Field"],  832: ["Field"],
    833: ["Monster","Water1"],834: ["Monster","Water1"],
    835: ["Bug"],    836: ["Bug"],
    837: ["Mineral"],838: ["Mineral"],839: ["Mineral"],
    840: ["Grass"],  841: ["Grass"],  842: ["Grass"],
    843: ["Field"],  844: ["Field"],
    845: ["Flying","Water1"],
    846: ["Water2"], 847: ["Water2"],
    848: ["Bug"],    849: ["Bug"],
    850: ["Water3"], 851: ["Water3"],
    852: ["Human-Like"],853: ["Human-Like"],
    854: ["Amorphous"],855: ["Amorphous"],
    856: ["Amorphous"],857: ["Amorphous"],858: ["Amorphous"],
    859: ["Field"],  860: ["Field"],  861: ["Field"],
    862: ["Field"],
    863: ["Field"],
    864: ["Amorphous"],
    865: ["Field"],
    866: ["Human-Like"],
    867: ["Mineral"],
    868: ["Amorphous"],869: ["Amorphous"],
    870: ["Bug", "Human-Like"],
    871: ["Water3"],
    872: ["Bug"],    873: ["Bug"],
    874: ["Mineral"],
    875: ["Mineral"],
    876: ["Amorphous"],
    877: ["Field"],
    878: ["Mineral"],879: ["Mineral"],
    880: ["Monster","Dragon"],881: ["Monster","Dragon"],
    882: ["Monster","Dragon"],883: ["Monster","Dragon"],
    884: ["Mineral","Dragon"],
    885: ["Dragon"], 886: ["Dragon"], 887: ["Dragon"],
    888: ["Undiscovered"],889: ["Undiscovered"],890: ["Undiscovered"],
    891: ["Human-Like"],892: ["Human-Like"],
    893: ["Grass"],
    894: ["Undiscovered"],895: ["Undiscovered"],
    896: ["Undiscovered"],897: ["Undiscovered"],898: ["Undiscovered"],
}

PASOS_POR_GRUPO: Dict[str, int] = {
    "Monster": 5120, "Water1": 5120, "Bug": 3840, "Flying": 5120,
    "Field": 5120, "Fairy": 3840, "Grass": 5120, "Human-Like": 5120,
    "Water3": 5120, "Mineral": 5120, "Amorphous": 5120, "Water2": 5120,
    "Ditto": 5120, "Dragon": 10240, "Undiscovered": 999999,
}

PASOS_ESPECIALES: Dict[int, int] = {
    131: 10240,  # Lapras
    133: 8960,   # Eevee
    143: 10240,  # Snorlax
}

NATURALEZAS: List[str] = [
    "Hardy", "Lonely", "Brave", "Adamant", "Naughty",
    "Bold", "Docile", "Relaxed", "Impish", "Lax",
    "Timid", "Hasty", "Serious", "Jolly", "Naive",
    "Modest", "Mild", "Quiet", "Bashful", "Rash",
    "Calm", "Gentle", "Sassy", "Careful", "Quirky",
]

HABILIDAD_CUERPO_LLAMA = "cuerpo llama"


# ──────────────────────────────────────────────────────────────────────────────
# HELPER PÚBLICO: sexo
# ──────────────────────────────────────────────────────────────────────────────

def determinar_sexo(pokemon_id: int) -> Optional[str]:
    """
    Determina el sexo aleatorio de un Pokémon según las mecánicas oficiales.

    Returns:
        'M', 'F' o None (asexuado)
    """
    if pokemon_id in SIN_GENERO or pokemon_id in POKEMON_UNDISCOVERED:
        return None
    if pokemon_id in SOLO_MACHO:
        return "M"
    if pokemon_id in SOLO_HEMBRA:
        return "F"
    # Starters y pseudo-legendarios: 87.5% macho
    starters_y_pseudo = {
        1, 2, 3, 4, 5, 6, 7, 8, 9,
        147, 148, 149,
        246, 247, 248,
        443, 444, 445,
    }
    if pokemon_id in starters_y_pseudo:
        return "M" if random.random() < 0.875 else "F"
    return "M" if random.random() < 0.5 else "F"


# ──────────────────────────────────────────────────────────────────────────────
# SERVICIO
# ──────────────────────────────────────────────────────────────────────────────

class CrianzaService:
    """Servicio completo de crianza de Pokémon"""

    def __init__(self):
        self.db = db_manager
        self._migrar_tabla_huevos()

    def _migrar_tabla_huevos(self) -> None:
        """
        Agrega columnas nuevas a HUEVOS y POKEMON_USUARIO si no existen.
        SQLite no permite IF NOT EXISTS en ALTER TABLE, por eso se usa
        try/except: si la columna ya existe la excepción se ignora silenciosamente.

        Columnas añadidas a HUEVOS:
          - en_equipo          : obsoleto (se mantiene por compatibilidad)
          - es_shiny           : shiny pre-determinado al crear el huevo
          - placeholder_pokemon_id : id_unico del row de POKEMON_USUARIO
                                     que representa al huevo en el equipo

        Columnas añadidas a POKEMON_USUARIO:
          - es_huevo  : 1 si el row es un placeholder de huevo
          - huevo_ref : id del huevo en HUEVOS (FK lógica)
        """
        migraciones = [
            # HUEVOS
            ("HUEVOS.en_equipo",
             "ALTER TABLE HUEVOS ADD COLUMN en_equipo INTEGER DEFAULT 0"),
            ("HUEVOS.es_shiny",
             "ALTER TABLE HUEVOS ADD COLUMN es_shiny INTEGER DEFAULT 0"),
            ("HUEVOS.placeholder_pokemon_id",
             "ALTER TABLE HUEVOS ADD COLUMN placeholder_pokemon_id INTEGER DEFAULT NULL"),
            # POKEMON_USUARIO
            ("POKEMON_USUARIO.es_huevo",
             "ALTER TABLE POKEMON_USUARIO ADD COLUMN es_huevo INTEGER DEFAULT 0"),
            ("POKEMON_USUARIO.huevo_ref",
             "ALTER TABLE POKEMON_USUARIO ADD COLUMN huevo_ref INTEGER DEFAULT NULL"),
            ("POKEMON_USUARIO.fecha_captura",
             "ALTER TABLE POKEMON_USUARIO ADD COLUMN fecha_captura TIMESTAMP DEFAULT NULL"),
        ]
        for descripcion, sql in migraciones:
            try:
                self.db.execute_update(sql)
                logger.info("[CRIANZA] Columna '%s' agregada.", descripcion)
            except Exception:
                pass  # ya existe — comportamiento normal en arranques posteriores

    # ══════════════════════════════════════════════
    # GUARDERÍA
    # ══════════════════════════════════════════════

    def obtener_pokemon_guarderia(self, user_id: int) -> Dict:
        """
        Retorna el estado de la guardería como diccionario de slots.

        Returns:
            Dict con estructura:
                {
                    "poke1": Pokemon | None,  # objeto Pokemon o None si el slot está vacío
                    "poke2": Pokemon | None,
                }
        Siempre devuelve ambas claves aunque estén vacías.
        """
        from pokemon.services.pokemon_service import pokemon_service as _ps

        resultados = self.db.execute_query(
            "SELECT slot, pokemon_id FROM GUARDERIA WHERE userID = ? ORDER BY slot",
            (user_id,)
        ) or []

        guarderia: Dict[str, object] = {"poke1": None, "poke2": None}
        for row in resultados:
            slot = row.get("slot") or "poke1"
            pid  = row.get("pokemon_id")
            if slot in guarderia and pid:
                poke = _ps.obtener_pokemon(int(pid))
                guarderia[slot] = poke  # puede ser None si el Pokémon fue borrado

        return guarderia

    def obtener_pokemon_guarderia_lista(self, user_id: int) -> List:
        """
        Versión de compatibilidad que devuelve lista de Pokémon presentes
        (omite slots vacíos).  Útil para lógica de crianza que espera list.
        """
        d = self.obtener_pokemon_guarderia(user_id)
        return [p for p in d.values() if p is not None]

    def depositar_en_guarderia(self, user_id: int, pokemon_id: int) -> Tuple[bool, str]:
        """
        Deposita un Pokémon en la guardería usando el primer slot libre.

        Reglas:
          - Máximo 2 Pokémon (slots poke1 y poke2).
          - No se aceptan legendarios / grupo Undiscovered.
          - El Pokémon se saca del equipo (en_equipo = 0).
          - Al llenar el segundo slot se intenta producir un huevo si
            los dos Pokémon son compatibles.

        Returns:
            (exito, mensaje)
        """
        try:
            from pokemon.services.pokemon_service import pokemon_service

            # ── Validaciones básicas ──────────────────────────────────────────
            poke = pokemon_service.obtener_pokemon(pokemon_id)
            if not poke:
                return False, "❌ Pokémon no encontrado."
            if poke.usuario_id != user_id:
                return False, "❌ Ese Pokémon no te pertenece."

            grupos = GRUPOS_HUEVOS.get(poke.pokemonID, ["Undiscovered"])
            if "Undiscovered" in grupos or poke.pokemonID in POKEMON_UNDISCOVERED:
                return False, f"❌ {poke.nombre} no puede quedarse en la guardería."

            # ── Determinar slot libre ─────────────────────────────────────────
            guarderia = self.obtener_pokemon_guarderia(user_id)

            # Verificar que no esté ya depositado
            for slot_poke in guarderia.values():
                if slot_poke and getattr(slot_poke, "id_unico", None) == pokemon_id:
                    return False, f"❌ {poke.nombre} ya está en la guardería."

            if guarderia["poke1"] is None:
                slot_libre = "poke1"
            elif guarderia["poke2"] is None:
                slot_libre = "poke2"
            else:
                return False, "❌ La guardería ya tiene 2 Pokémon. Retira uno primero."

            # ── Sacar del equipo y registrar ──────────────────────────────────
            self.db.execute_update(
                "UPDATE POKEMON_USUARIO SET en_equipo = 0 WHERE id_unico = ?",
                (pokemon_id,)
            )
            self.db.execute_update(
                "INSERT INTO GUARDERIA (userID, pokemon_id, slot) VALUES (?, ?, ?)",
                (user_id, pokemon_id, slot_libre)
            )

            logger.info(
                f"🏡 {poke.nombre} (slot {slot_libre}) depositado "
                f"en guardería por usuario {user_id}"
            )

            # ── Si el segundo slot acaba de llenarse, verificar compatibilidad ─
            # El huevo NO se produce de inmediato: hay que escribir en el grupo
            # para acumular PASOS_PARA_PRODUCIR_HUEVO pasos de guardería.
            # El Amuleto Iris duplica esos pasos.
            guarderia_nueva = self.obtener_pokemon_guarderia(user_id)
            p1 = guarderia_nueva["poke1"]
            p2 = guarderia_nueva["poke2"]
            msg_compatibilidad = ""
            if p1 and p2:
                pueden, msg_compat = self.pueden_criar(p1.id_unico, p2.id_unico)
                if pueden:
                    msg_compatibilidad = (
                        f"\n💕 ¡{p1.nombre} y {p2.nombre} son compatibles!\n"
                        f"Escribí en el grupo para que la guardería produzca el huevo "
                        f"({PASOS_PARA_PRODUCIR_HUEVO} palabras necesarias)."
                    )
                else:
                    msg_compatibilidad = f"\n❌ {msg_compat}"

            return True, (
                f"✅ {poke.nombre} fue dejado en la guardería (slot {slot_libre})."
                f"{msg_compatibilidad}"
            )

        except Exception as e:
            logger.error(f"❌ Error depositando en guardería: {e}")
            return False, f"Error: {str(e)}"

    def retirar_de_guarderia(self, user_id: int, pokemon_id: int) -> Tuple[bool, str]:
        """
        Retira un Pokémon de la guardería liberando su slot.
        Lo devuelve al equipo si hay lugar, o al PC si está lleno.

        Returns:
            (exito, mensaje)
        """
        try:
            from pokemon.services.pokemon_service import pokemon_service

            # Verificar que esté realmente en la guardería
            fila = self.db.execute_query(
                "SELECT id, slot FROM GUARDERIA WHERE userID = ? AND pokemon_id = ?",
                (user_id, pokemon_id)
            )
            if not fila:
                return False, "❌ Ese Pokémon no está en la guardería."

            # Liberar el slot
            self.db.execute_update(
                "DELETE FROM GUARDERIA WHERE userID = ? AND pokemon_id = ?",
                (user_id, pokemon_id)
            )

            # Devolver al equipo o al PC
            equipo = pokemon_service.obtener_equipo(user_id)
            if len(equipo) < 6:
                self.db.execute_update(
                    "UPDATE POKEMON_USUARIO SET en_equipo = 1 WHERE id_unico = ?",
                    (pokemon_id,)
                )
                destino = "devuelto a tu equipo"
            else:
                destino = "guardado en el PC (equipo lleno)"

            poke   = pokemon_service.obtener_pokemon(pokemon_id)
            nombre = poke.nombre if poke else f"Pokémon #{pokemon_id}"
            slot   = fila[0].get("slot", "?")
            logger.info(
                f"🏡 {nombre} (slot {slot}) retirado de guardería "
                f"por usuario {user_id}"
            )
            return True, f"✅ {nombre} fue retirado ({slot}). Fue {destino}."

        except Exception as e:
            logger.error(f"❌ Error retirando de guardería: {e}")
            return False, f"Error: {str(e)}"

    # ══════════════════════════════════════════════
    # COMPATIBILIDAD
    # ══════════════════════════════════════════════

    def pueden_criar(self, pokemon1_id: int, pokemon2_id: int) -> Tuple[bool, str]:
        """
        Verifica compatibilidad de cría.

        Reglas oficiales:
        - No puede criar consigo mismo.
        - Ditto cría con cualquiera que no sea Undiscovered.
        - Sin Ditto: sexos opuestos + grupo de huevo compartido.
        - Asexuados solo pueden criar con Ditto.
        """
        try:
            from pokemon.services.pokemon_service import pokemon_service

            if pokemon1_id == pokemon2_id:
                return False, "Un Pokémon no puede criar consigo mismo."

            poke1 = pokemon_service.obtener_pokemon(pokemon1_id)
            poke2 = pokemon_service.obtener_pokemon(pokemon2_id)
            if not poke1 or not poke2:
                return False, "Uno o ambos Pokémon no existen."

            id1, id2 = poke1.pokemonID, poke2.pokemonID
            grupos1 = GRUPOS_HUEVOS.get(id1, ["Undiscovered"])
            grupos2 = GRUPOS_HUEVOS.get(id2, ["Undiscovered"])

            if "Undiscovered" in grupos1 or id1 in POKEMON_UNDISCOVERED:
                return False, f"{poke1.nombre} no puede tener crías."
            if "Undiscovered" in grupos2 or id2 in POKEMON_UNDISCOVERED:
                return False, f"{poke2.nombre} no puede tener crías."

            if id1 == DITTO_ID or id2 == DITTO_ID:
                return True, "✅ Compatibles (con Ditto)"

            # Sin Ditto: verificar sexo
            sexo1 = poke1.sexo
            sexo2 = poke2.sexo
            if sexo1 is None or sexo2 is None:
                return False, "Los Pokémon asexuados solo pueden criar con Ditto."
            if sexo1 == sexo2:
                return False, "Los Pokémon deben ser de sexos opuestos."

            comunes = set(grupos1) & set(grupos2)
            if not comunes:
                return False, f"{poke1.nombre} y {poke2.nombre} no comparten grupo de huevo."

            return True, f"✅ Compatibles (Grupo: {', '.join(comunes)})"

        except Exception as e:
            logger.error(f"❌ Error verificando compatibilidad: {e}")
            return False, f"Error: {str(e)}"

    # ══════════════════════════════════════════════
    # PRODUCCIÓN DE HUEVOS
    # ══════════════════════════════════════════════

    def intentar_producir_huevo(self, user_id: int) -> Tuple[bool, str, Optional[int]]:
        """
        Intenta producir un huevo con los 2 Pokémon en guardería.
        Llamar al depositar el segundo Pokémon.

        Regla: solo puede haber 1 huevo activo (no eclosionado) por usuario.

        Returns:
            (producido, mensaje, huevo_id)
        """
        # ── Límite de 1 huevo activo por usuario ─────────────────────────────
        huevo_existente = self.db.execute_query(
            "SELECT id FROM HUEVOS WHERE userID = ? AND eclosionado = 0 LIMIT 1",
            (user_id,),
        )
        if huevo_existente:
            return (
                False,
                "🥚 Ya tenés un huevo activo. "
                "Retiralo al equipo y esperá a que eclosione antes de crear otro.",
                None,
            )

        guardados_dict = self.obtener_pokemon_guarderia(user_id)
        guardados = [p for p in guardados_dict.values() if p is not None]
        if len(guardados) < 2:
            return False, "Se necesitan 2 Pokémon en la guardería.", None

        pueden, msg = self.pueden_criar(guardados[0].id_unico, guardados[1].id_unico)
        if not pueden:
            return False, msg, None

        return self._crear_huevo(user_id, guardados[0].id_unico, guardados[1].id_unico)

    def _crear_huevo(self, user_id: int, p1_id: int, p2_id: int) -> Tuple[bool, str, Optional[int]]:
        """
        Crea un huevo en BD con todos los datos heredados.

        El huevo nace en la guardería (en_equipo=0).  El usuario debe
        retirarlo con retirar_huevo() para que empiece a acumular pasos.
        El shiny se pre-determina aquí para que sea consistente.
        """
        try:
            from pokemon.services.pokemon_service import pokemon_service

            poke1 = pokemon_service.obtener_pokemon(p1_id)
            poke2 = pokemon_service.obtener_pokemon(p2_id)
            if not poke1 or not poke2:
                return False, "Pokémon no encontrado.", None

            p1, p2 = vars(poke1), vars(poke2)
            especie    = self._determinar_especie_huevo(p1, p2)
            pasos      = self._calcular_pasos_necesarios(especie)
            ivs        = self._calcular_ivs_heredados(p1, p2)
            naturaleza = self._determinar_naturaleza(p1, p2)
            habilidad  = self._determinar_habilidad(especie)
            movimientos = self._calcular_movimientos_huevo(p1, p2, especie)

            # Pre-determinar shiny con multiplicador del Amuleto Iris
            try:
                from funciones.pokedex_usuario import get_shiny_multiplier
                from config import POKEMON_SPAWN_CONFIG
                _prob = POKEMON_SPAWN_CONFIG.get("probabilidad_shiny", 1 / 4096)
                _prob *= get_shiny_multiplier(user_id)
            except Exception:
                _prob = 1 / 4096
            es_shiny = 1 if random.random() < _prob else 0

            self.db.execute_update(
                """
                INSERT INTO HUEVOS (
                    userID, pokemon_id, ivs_heredados, naturaleza,
                    habilidad, movimientos_huevo, pasos_necesarios,
                    es_shiny, pasos_actuales, en_equipo, eclosionado
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0)
                """,
                (
                    user_id, especie, json.dumps(ivs), naturaleza,
                    habilidad, json.dumps(movimientos), pasos, es_shiny,
                )
            )

            id_r = self.db.execute_query("SELECT last_insert_rowid() AS id")
            huevo_id: Optional[int] = id_r[0]['id'] if id_r else None

            nombre = self._obtener_nombre_especie(especie)
            logger.info(
                "[CRIANZA] 🥚 Huevo %s creado para user %s "
                "(especie=%s, pasos=%s, shiny=%s)",
                huevo_id, user_id, especie, pasos, bool(es_shiny),
            )
            return True, (
                f"🥚 ¡La guardería tiene un huevo!\n"
                f"Especie: {nombre}\n"
                f"Pasos necesarios: {pasos}\n\n"
                f"Retirá el huevo de la guardería para empezar a incubarlo."
            ), huevo_id

        except Exception as e:
            logger.error(f"❌ Error creando huevo: {e}")
            return False, f"Error: {str(e)}", None

    # ══════════════════════════════════════════════
    # SISTEMA DE PASOS
    # ══════════════════════════════════════════════

    def _tiene_amuleto_iris(self, user_id: int) -> bool:
        """True si el usuario tiene el Amuleto Iris (duplica pasos globalmente)."""
        try:
            from funciones.pokedex_usuario import tiene_amuleto_iris
            return tiene_amuleto_iris(user_id)
        except Exception:
            return False

    def _tiene_cuerpo_llama(self, user_id: int) -> bool:
        """True si hay un Pokémon con habilidad Cuerpo Llama en el equipo."""
        try:
            from pokemon.services.pokemon_service import pokemon_service
            equipo = pokemon_service.obtener_equipo(user_id)
            return any(
                p.habilidad and p.habilidad.lower() == HABILIDAD_CUERPO_LLAMA
                for p in equipo
            )
        except Exception:
            return False

    def retirar_huevo(self, user_id: int, huevo_id: int) -> Tuple[bool, str]:
        """
        Retira un huevo de la guardería al equipo del usuario.

        El huevo ocupa un slot real en POKEMON_USUARIO (es_huevo=1, en_equipo=1)
        y por tanto cuenta para el límite de 6.  Los pasos solo se acumulan
        mientras el huevo esté en el equipo.

        Returns:
            (exito, mensaje)
        """
        try:
            fila = self.db.execute_query(
                """
                SELECT id, pokemon_id, pasos_necesarios, es_shiny,
                       placeholder_pokemon_id
                FROM HUEVOS
                WHERE id = ? AND userID = ? AND eclosionado = 0
                """,
                (huevo_id, user_id),
            )
            if not fila:
                return False, "❌ Huevo no encontrado."

            huevo = fila[0]

            # Si ya tiene placeholder creado y en equipo, no crear otro
            if huevo.get('placeholder_pokemon_id'):
                en_equipo = self.db.execute_query(
                    "SELECT en_equipo FROM POKEMON_USUARIO WHERE id_unico = ?",
                    (huevo['placeholder_pokemon_id'],),
                )
                if en_equipo and en_equipo[0].get('en_equipo'):
                    return False, "❌ Ese huevo ya está en tu equipo."

            # ── Verificar espacio en el equipo (máx 6 incluyendo huevos) ─────
            slots_ocupados = self.db.execute_query(
                "SELECT COUNT(*) AS total FROM POKEMON_USUARIO "
                "WHERE userID = ? AND en_equipo = 1",
                (user_id,),
            )
            if slots_ocupados and slots_ocupados[0].get('total', 0) >= 6:
                return (
                    False,
                    "❌ Tu equipo está lleno (6/6). "
                    "Mové un Pokémon al PC antes de llevar el huevo."
                )

            especie_id = int(huevo['pokemon_id'])
            nombre     = self._obtener_nombre_especie(especie_id)

            # ── Crear fila placeholder en POKEMON_USUARIO ─────────────────────
            # Todos los stats en 0 / hp_actual 0 — no puede combatir
            placeholder_id = self.db.execute_insert(
                """
                INSERT INTO POKEMON_USUARIO (
                    userID, pokemonID, nivel, naturaleza,
                    iv_hp, iv_atq, iv_def, iv_atq_sp, iv_def_sp, iv_vel,
                    ev_hp, ev_atq, ev_def, ev_atq_sp, ev_def_sp, ev_vel,
                    ps, atq, def, atq_sp, def_sp, vel, hp_actual,
                    exp, region, habilidad, sexo,
                    move1, move2, move3, move4,
                    shiny, en_equipo, es_huevo, huevo_ref,
                    apodo
                ) VALUES (
                    ?, ?, 0, 'Hardy',
                    0,0,0,0,0,0,
                    0,0,0,0,0,0,
                    0,0,0,0,0,0, 0,
                    0, 'KANTO', NULL, NULL,
                    NULL, NULL, NULL, NULL,
                    ?, 1, 1, ?,
                    ?
                )
                """,
                (
                    user_id, especie_id,
                    int(huevo.get('es_shiny', 0)),
                    huevo_id,
                    f"Huevo de {nombre}",
                ),
            )

            if not placeholder_id:
                return False, "❌ Error al crear el slot del huevo. Intenta de nuevo."

            # ── Vincular huevo ↔ placeholder ──────────────────────────────────
            self.db.execute_update(
                "UPDATE HUEVOS SET placeholder_pokemon_id = ? WHERE id = ?",
                (placeholder_id, huevo_id),
            )

            logger.info(
                "[CRIANZA] User %s retiró huevo %s (%s) → placeholder_id=%s",
                user_id, huevo_id, nombre, placeholder_id,
            )
            return True, (
                f"🥚 Llevás el huevo de <b>{nombre}</b> contigo "
                f"({huevo['pasos_necesarios']} pasos para eclosionar).\n"
                f"¡Escribí en el grupo para que avance!"
            )

        except Exception as e:
            logger.error("[CRIANZA] Error retirando huevo %s: %s", huevo_id, e)
            return False, f"Error: {str(e)}"

    def sumar_pasos_produccion(
        self,
        user_id:   int,
        palabras:  int,
        chat_id:   Optional[int] = None,
        thread_id: Optional[int] = None,
    ) -> Optional[Dict]:
        """
        Suma pasos hacia la PRODUCCIÓN de un huevo (fase de guardería).

        Solo se ejecuta si el usuario tiene exactamente dos Pokémon
        compatibles en la guardería Y aún no tiene un huevo activo.

        Multiplicador:
          - Amuleto Iris activo: ×2 pasos contados.
          - Cuerpo Llama:        NO aplica aquí (es para eclosión).

        Usa la columna pasos_guarderia de USUARIOS como contador.
        Al alcanzar PASOS_PARA_PRODUCIR_HUEVO el huevo se crea y el
        contador se resetea a 0.

        Args:
            user_id:   Telegram ID del usuario.
            palabras:  Palabras escritas en el mensaje del grupo.
            chat_id:   Chat donde notificar si el huevo aparece.
            thread_id: Thread/topic del chat.

        Returns:
            Dict con datos del huevo producido, o None si no ocurrió nada.
        """
        try:
            # Solo actuar si hay 2 Pokémon en la guardería y no hay huevo activo
            guarderia = self.obtener_pokemon_guarderia(user_id)
            guardados = [p for p in guarderia.values() if p is not None]
            if len(guardados) < 2:
                return None

            huevo_activo = self.db.execute_query(
                "SELECT id FROM HUEVOS WHERE userID = ? AND eclosionado = 0 LIMIT 1",
                (user_id,),
            )
            if huevo_activo:
                return None  # ya hay un huevo en curso, no producir otro

            # Verificar compatibilidad antes de gastar pasos
            pueden, _ = self.pueden_criar(guardados[0].id_unico, guardados[1].id_unico)
            if not pueden:
                return None

            mult = 2 if self._tiene_amuleto_iris(user_id) else 1
            pasos_a_sumar = palabras * mult

            # Leer contador actual de pasos de producción
            fila = self.db.execute_query(
                "SELECT COALESCE(pasos_guarderia, 0) AS total FROM USUARIOS WHERE userID = ?",
                (user_id,),
            )
            pasos_actuales = int(fila[0]["total"]) if fila else 0
            pasos_nuevos   = pasos_actuales + pasos_a_sumar

            self.db.execute_update(
                "UPDATE USUARIOS SET pasos_guarderia = ? WHERE userID = ?",
                (pasos_nuevos, user_id),
            )

            if pasos_nuevos < PASOS_PARA_PRODUCIR_HUEVO:
                return None  # aún no se alcanzó el umbral

            # ── Umbral alcanzado: producir el huevo ───────────────────────────
            ok, mensaje, huevo_id = self._crear_huevo(
                user_id, guardados[0].id_unico, guardados[1].id_unico
            )

            # Resetear contador de producción
            self.db.execute_update(
                "UPDATE USUARIOS SET pasos_guarderia = 0 WHERE userID = ?",
                (user_id,),
            )

            if ok and huevo_id:
                logger.info(
                    "[CRIANZA] Huevo %s producido para user %s tras %s pasos de guardería.",
                    huevo_id, user_id, pasos_nuevos,
                )
                return {
                    "huevo_id": huevo_id,
                    "mensaje":  mensaje,
                    "chat_id":  chat_id,
                    "thread_id": thread_id,
                }

            return None

        except Exception as e:
            logger.error("[CRIANZA] Error en sumar_pasos_produccion (user %s): %s", user_id, e)
            return None

    def sumar_pasos(
        self,
        user_id:   int,
        palabras:  int,
        chat_id:   Optional[int] = None,
        thread_id: Optional[int] = None,
    ) -> List[Dict]:
        """
        Suma pasos hacia la ECLOSIÓN de los huevos que el usuario lleva
        en su equipo (placeholder en_equipo=1).

        Multiplicador:
          - Cuerpo Llama (Pokémon en equipo): ×2 pasos contados.
          - Amuleto Iris:                     NO aplica aquí
                                              (es para producción del huevo).

        Args:
            user_id:   Telegram ID del usuario.
            palabras:  Palabras escritas en el mensaje del grupo.
            chat_id:   Chat donde notificar la eclosión.
            thread_id: Thread/topic del chat.

        Returns:
            Lista de dicts con datos de cada eclosión producida.
        """
        try:
            # Buscar huevos en equipo via join con POKEMON_USUARIO
            huevos = self.db.execute_query(
                """
                SELECT h.*
                FROM HUEVOS h
                INNER JOIN POKEMON_USUARIO pu
                        ON pu.id_unico = h.placeholder_pokemon_id
                WHERE h.userID = ?
                  AND h.eclosionado = 0
                  AND pu.en_equipo = 1
                  AND pu.es_huevo  = 1
                """,
                (user_id,),
            )
            if not huevos:
                return []

            # Solo Cuerpo Llama — Amuleto Iris NO aplica en eclosión
            mult_cuerpo_llama = 2 if self._tiene_cuerpo_llama(user_id) else 1
            pasos_a_sumar     = palabras * mult_cuerpo_llama

            eclosionados: List[Dict] = []

            for row in huevos:
                huevo        = dict(row)
                pasos_nuevos = huevo.get('pasos_actuales', 0) + pasos_a_sumar

                self.db.execute_update(
                    "UPDATE HUEVOS SET pasos_actuales = ? WHERE id = ?",
                    (pasos_nuevos, huevo['id']),
                )

                if pasos_nuevos >= huevo['pasos_necesarios']:
                    huevo['pasos_actuales'] = pasos_nuevos
                    resultado = self._eclosionar_huevo(huevo['id'], huevo)
                    if resultado:
                        resultado['chat_id']   = chat_id
                        resultado['thread_id'] = thread_id
                        eclosionados.append(resultado)

            return eclosionados

        except Exception as e:
            logger.error("[CRIANZA] Error sumando pasos (user %s): %s", user_id, e)
            return []

    def _eclosionar_huevo(self, huevo_id: int, huevo: Dict) -> Optional[Dict]:
        """
        Eclosiona el huevo: convierte el row placeholder de POKEMON_USUARIO
        en el Pokémon real (UPDATE, no INSERT) y marca el huevo como eclosionado.

        Al usar UPDATE sobre el placeholder:
          - El id_unico queda igual → la posición en el equipo se mantiene.
          - No hace falta un paso extra para "agregar al equipo".
          - El handler puede luego pedir mote al usuario (finalizar_eclosion).

        Returns:
            Dict con datos del nuevo Pokémon, o None si falla.
        """
        try:
            from database import db_manager as _db
            from pokemon.services.pokedex_service import pokedex_service as _pdex

            ivs:        Dict = json.loads(huevo.get('ivs_heredados') or '{}')
            naturaleza: str  = huevo.get('naturaleza') or 'Hardy'
            especie_id: int  = int(huevo['pokemon_id'])
            es_shiny:   bool = bool(huevo.get('es_shiny', 0))
            habilidad:  str  = huevo.get('habilidad') or ''
            sexo = determinar_sexo(especie_id)
            sexo_texto = {"M": "♂", "F": "♀"}.get(sexo or "", "◯")

            placeholder_id: Optional[int] = huevo.get('placeholder_pokemon_id')
            if not placeholder_id:
                logger.error(
                    "[CRIANZA] Huevo %s sin placeholder_pokemon_id — no se puede eclosionar.",
                    huevo_id,
                )
                return None

            # ── Calcular stats reales con los IVs heredados ───────────────────
            evs_cero = {s: 0 for s in ("hp", "atq", "def", "atq_sp", "def_sp", "vel")}
            stats = _pdex.calcular_stats(especie_id, 1, ivs, evs_cero, naturaleza)

            # ── Obtener movimientos iniciales de nivel 1 ──────────────────────
            movimientos_huevo: List[str] = json.loads(
                huevo.get('movimientos_huevo') or '[]'
            )
            if movimientos_huevo:
                moves = (movimientos_huevo + [None, None, None, None])[:4]
            else:
                from pokemon.services import movimientos_service
                movs_nivel = movimientos_service.obtener_todos_movimientos_hasta_nivel(
                    especie_id, 1
                )
                movs_nivel = movs_nivel[:4] if movs_nivel else ["placaje"]
                moves = (movs_nivel + [None, None, None, None])[:4]

            # ── Convertir el placeholder en el Pokémon real ───────────────────
            campos_iv = (
                "iv_hp = ?, iv_atq = ?, iv_def = ?, "
                "iv_atq_sp = ?, iv_def_sp = ?, iv_vel = ?"
            )
            _db.execute_update(
                f"""
                UPDATE POKEMON_USUARIO SET
                    pokemonID  = ?,
                    nivel      = 1,
                    naturaleza = ?,
                    sexo       = ?,
                    habilidad  = ?,
                    shiny      = ?,
                    {campos_iv},
                    ps         = ?,  atq    = ?,  def    = ?,
                    atq_sp     = ?,  def_sp = ?,  vel    = ?,
                    hp_actual  = ?,
                    move1 = ?, move2 = ?, move3 = ?, move4 = ?,
                    es_huevo   = 0,
                    huevo_ref  = NULL,
                    apodo      = NULL
                WHERE id_unico = ?
                """,
                (
                    especie_id,
                    naturaleza,
                    sexo,
                    habilidad or None,
                    int(es_shiny),
                    ivs.get("hp", 0),     ivs.get("atq", 0),    ivs.get("def", 0),
                    ivs.get("atq_sp", 0), ivs.get("def_sp", 0), ivs.get("vel", 0),
                    stats["hp"],  stats["atq"],    stats["def"],
                    stats["atq_sp"], stats["def_sp"], stats["vel"],
                    stats["hp"],  # hp_actual = máximo al nacer
                    moves[0], moves[1], moves[2], moves[3],
                    placeholder_id,
                ),
            )

            # fecha_captura en query separada — tolerante a BD antiguas que
            # aún no tienen la columna (la migración la agrega al arrancar,
            # pero si por alguna razón falló este UPDATE no debe romper todo)
            try:
                _db.execute_update(
                    "UPDATE POKEMON_USUARIO SET fecha_captura = CURRENT_TIMESTAMP "
                    "WHERE id_unico = ?",
                    (placeholder_id,),
                )
            except Exception as _fc_err:
                logger.warning(
                    "[CRIANZA] No se pudo setear fecha_captura (id=%s): %s",
                    placeholder_id, _fc_err,
                )

            # ── Marcar huevo como eclosionado ─────────────────────────────────
            self.db.execute_update(
                "UPDATE HUEVOS SET eclosionado = 1, pokemon_nacido_id = ? WHERE id = ?",
                (placeholder_id, huevo_id),
            )

            nombre   = self._obtener_nombre_especie(especie_id)
            iv_total = sum(ivs.values())
            shiny_tag = " ✨" if es_shiny else ""

            logger.info(
                "[CRIANZA] 🐣 Huevo %s → %s (id_unico=%s, shiny=%s)",
                huevo_id, nombre, placeholder_id, es_shiny,
            )

            return {
                'huevo_id':   huevo_id,
                'pokemon_id': placeholder_id,  # mismo id_unico que tenía el placeholder
                'especie_id': especie_id,
                'nombre':     nombre,
                'nivel':      1,
                'naturaleza': naturaleza,
                'sexo':       sexo,
                'sexo_texto': sexo_texto,
                'shiny':      es_shiny,
                'ivs':        ivs,
                'iv_total':   iv_total,
                'mensaje': (
                    f"🎉 ¡El huevo ha eclosionado!\n"
                    f"{'✨ ' if es_shiny else ''}🐣 <b>{nombre}</b>{shiny_tag} "
                    f"{sexo_texto} Nv.1\n"
                    f"🌿 Naturaleza: {naturaleza}\n"
                    f"💎 IVs totales: {iv_total}/186"
                ),
            }

        except Exception as e:
            logger.error("[CRIANZA] Error eclosionando huevo %s: %s", huevo_id, e)
            return None

    def finalizar_eclosion(self, user_id: int, pokemon_id: int,
                           mote: Optional[str]) -> Tuple[bool, str]:
        """
        Aplica el mote (opcional) al Pokémon recién eclosionado.

        No necesita mover al equipo: el placeholder ya estaba en_equipo=1
        y _eclosionar_huevo lo convirtió en el Pokémon real in-place.

        Args:
            user_id:    Telegram ID del usuario.
            pokemon_id: id_unico del Pokémon (era el placeholder).
            mote:       Apodo deseado, o None para no poner apodo.

        Returns:
            (exito, mensaje)
        """
        try:
            from pokemon.services.pokemon_service import pokemon_service
            from database import db_manager as _db

            if mote:
                _db.execute_update(
                    "UPDATE POKEMON_USUARIO SET apodo = ? WHERE id_unico = ?",
                    (mote, pokemon_id),
                )

            poke = pokemon_service.obtener_pokemon(pokemon_id)
            nombre_display = mote or (poke.nombre if poke else f"#{pokemon_id}")
            return True, f"✅ <b>{nombre_display}</b> ya es parte de tu equipo."

        except Exception as e:
            logger.error("[CRIANZA] Error finalizando eclosión: %s", e)
            return False, f"Error: {str(e)}"

    # ══════════════════════════════════════════════
    # HELPERS DE HERENCIA
    # ══════════════════════════════════════════════

    def _obtener_especie_base(self, especie_id: int) -> int:
        """
        Recorre la cadena evolutiva hacia atrás para encontrar la forma base.

        Construye un mapa inverso (quien_evoluciona_a → desde_quien) usando
        evolucion_service.evoluciones, luego sube hasta el tope.

        Ejemplos:
            Gengar (94)   → Gastly (92)
            Blastoise (9) → Squirtle (7)
            Kingdra (230) → Horsea (116)
            Scizor (212)  → Scyther (123)

        Límite de 10 pasos para evitar bucles infinitos en datos corruptos.
        """
        try:
            from pokemon.services.evolucion_service import evolucion_service

            # Construir mapa inverso: {id_evolucionado: id_preevolucion}
            inverso: Dict[int, int] = {}
            for pre_id_str, evo_list in evolucion_service.evoluciones.items():
                pre_id = int(pre_id_str)
                for evo in evo_list:
                    try:
                        evo_a = int(evo.get("evoluciona_a", 0))
                        if evo_a:
                            inverso[evo_a] = pre_id
                    except (ValueError, TypeError):
                        pass

            # Subir por la cadena hasta encontrar la raíz
            actual = especie_id
            for _ in range(10):
                padre = inverso.get(actual)
                if padre is None:
                    break
                actual = padre

            return actual

        except Exception as e:
            logger.warning(
                "[CRIANZA] No se pudo obtener especie base de %s: %s — usando la misma",
                especie_id, e,
            )
            return especie_id

    def _determinar_especie_huevo(self, p1: Dict, p2: Dict) -> int:
        """
        Determina la especie del huevo según las reglas oficiales:
          1. Si uno de los padres es Ditto, la especie es la del otro.
          2. Sin Ditto: la hembra determina la especie.
          3. La especie resultante es siempre la FORMA BASE de la cadena
             evolutiva (Gastly de Gengar, Squirtle de Blastoise, etc.)
        """
        id1 = int(p1.get('pokemonID') or p1.get('pokemon_id', 0))
        id2 = int(p2.get('pokemonID') or p2.get('pokemon_id', 0))

        if id1 == DITTO_ID:
            especie = id2
        elif id2 == DITTO_ID:
            especie = id1
        elif p1.get('sexo') == 'F':
            especie = id1
        elif p2.get('sexo') == 'F':
            especie = id2
        else:
            especie = id1  # fallback

        return self._obtener_especie_base(especie)

    def _calcular_ivs_heredados(self, p1: Dict, p2: Dict) -> Dict:
        """
        Hereda 3 IVs de los padres (5 con Nudo Destino).
        El resto son aleatorios.
        """
        stats = ['hp', 'atq', 'def', 'atq_sp', 'def_sp', 'vel']
        iv_col = {
            'hp': 'iv_hp', 'atq': 'iv_atq', 'def': 'iv_def',
            'atq_sp': 'iv_atq_sp', 'def_sp': 'iv_def_sp', 'vel': 'iv_vel'
        }

        ivs1 = {s: int(p1.get(iv_col[s]) or 0) for s in stats}
        ivs2 = {s: int(p2.get(iv_col[s]) or 0) for s in stats}

        item1 = str(p1.get('objeto') or '').lower()
        item2 = str(p2.get('objeto') or '').lower()
        n = 5 if ('nudo destino' in item1 or 'nudo destino' in item2) else 3

        resultado: Dict = {}
        for stat in random.sample(stats, n):
            resultado[stat] = ivs1[stat] if random.random() < 0.5 else ivs2[stat]
        for stat in stats:
            if stat not in resultado:
                resultado[stat] = random.randint(0, 31)

        return resultado

    def _determinar_naturaleza(self, p1: Dict, p2: Dict) -> str:
        """Hereda naturaleza si alguno lleva Piedra Eterna, sino aleatoria."""
        item1 = str(p1.get('objeto') or '').lower()
        item2 = str(p2.get('objeto') or '').lower()
        if 'piedra eterna' in item1:
            return str(p1.get('naturaleza') or random.choice(NATURALEZAS))
        if 'piedra eterna' in item2:
            return str(p2.get('naturaleza') or random.choice(NATURALEZAS))
        return random.choice(NATURALEZAS)

    def _determinar_habilidad(self, especie_id: int) -> str:
      """
      Selecciona habilidad de la especie con pesos canónicos Gen 5+.
      La lista viene del pokedex.json; la lógica de pesos vive en habilidades_service.
      """
      try:
          from pokemon.services.pokedex_service import pokedex_service
          from pokemon.services.habilidades_service import habilidades_service
          habs = pokedex_service.obtener_habilidades(especie_id)
          return habilidades_service.seleccionar_habilidad(habs)
      except Exception:
          return "overgrow"  # fallback inocuo

    def _calcular_movimientos_huevo(self, p1: Dict, p2: Dict, especie_id: int) -> List[str]:
        """
        Calcula los movimientos huevo del nuevo Pokémon.

        Un movimiento es un "movimiento huevo" si:
          1. Al menos uno de los padres lo conoce en este momento.
          2. La especie hijo puede aprenderlo según su learnset.

        Los movimientos se normalizan (lowercase, sin espacios ni guiones)
        para coincidir con el formato de la BD.

        Returns:
            Lista de hasta 4 movimientos normalizados.
        """
        try:
            from pokemon.services import movimientos_service

            def _norm(m: str) -> str:
                return m.lower().replace(" ", "").replace("-", "")

            # Movimientos actuales de los padres
            movs_p1 = [_norm(m) for m in (p1.get('movimientos') or []) if m]
            movs_p2 = [_norm(m) for m in (p2.get('movimientos') or []) if m]
            movs_padres = set(movs_p1 + movs_p2)

            if not movs_padres:
                return []

            # Learnset completo de la especie hijo (todos los niveles)
            learnset = movimientos_service.obtener_learnset(especie_id)
            if not learnset:
                return []

            movs_especie: set = set()
            for movs_nivel in learnset.values():
                for m in movs_nivel:
                    movs_especie.add(_norm(m))

            # Intersección: movimientos que un padre conoce Y la especie puede aprender
            movs_huevo = [m for m in movs_padres if m in movs_especie]

            logger.debug(
                "[CRIANZA] Movimientos huevo para especie %s: %s",
                especie_id, movs_huevo[:4],
            )
            return movs_huevo[:4]

        except Exception as e:
            logger.error("[CRIANZA] Error calculando movimientos huevo: %s", e)
            return []

    def _calcular_pasos_necesarios(self, especie_id: int) -> int:
        """Pasos según grupo de huevo de la especie."""
        if especie_id in PASOS_ESPECIALES:
            return PASOS_ESPECIALES[especie_id]
        grupos = GRUPOS_HUEVOS.get(especie_id, ["Field"])
        return PASOS_POR_GRUPO.get(grupos[0], 5120)

    def _obtener_nombre_especie(self, especie_id: int) -> str:
        try:
            from pokemon.services.pokedex_service import pokedex_service
            return pokedex_service.obtener_nombre(especie_id)
        except Exception:
            return f"Pokémon #{especie_id}"

    # ══════════════════════════════════════════════
    # CONSULTAS
    # ══════════════════════════════════════════════

    def obtener_huevos_usuario(self, user_id: int) -> List[Dict]:
        """
        Huevos pendientes del usuario con progreso calculado.

        Usa pasos_actuales (por huevo) en vez del sistema de offsets global.
        """
        try:
            results = self.db.execute_query(
                "SELECT * FROM HUEVOS WHERE userID = ? AND eclosionado = 0 ORDER BY id",
                (user_id,)
            )
            huevos = []
            for row in (results or []):
                h = dict(row)
                pasos_act = h.get('pasos_actuales', 0) or 0
                pasos_nec = h.get('pasos_necesarios', 1) or 1
                h['pasos_efectivos'] = pasos_act
                h['progreso_pct']    = min(100.0, round(pasos_act / pasos_nec * 100, 1))
                h['nombre']          = self._obtener_nombre_especie(h['pokemon_id'])
                h['en_equipo']       = bool(h.get('en_equipo', 0))
                huevos.append(h)
            return huevos
        except Exception as e:
            logger.error(f"❌ Error obteniendo huevos: {e}")
            return []

    
# Instancia global
crianza_service = CrianzaService()