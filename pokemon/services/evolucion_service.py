# -*- coding: utf-8 -*-
"""
Servicio de Evoluciones Pokémon — TODAS LAS GENERACIONES (Gen 1-9)
FIX: imports de pokemon_service y pokedex_service son LAZY (dentro de métodos)
     para evitar circular import con pokemon/services/__init__.py
"""

import logging
import datetime
from typing import Optional, Dict, List, Tuple, Any
from database import db_manager

# NO importar pokemon_service/pokedex_service aquí arriba — causa circular import.
# Cada método hace: from pokemon.services.pokemon_service import pokemon_service

logger = logging.getLogger(__name__)

# Movimientos que una especie SOLO puede aprender tras evolucionar.
# Se ofrecen al jugador inmediatamente después de confirmar la evolución.
# Formato: nuevo_pokemonID (ndex) → [lista de move_keys en inglés]
POST_EVO_EXCLUSIVE_MOVES: dict[int, list[str]] = {
    212: ["bulletpunch"],      # Scizor:  Puño Bala
    248: ["stoneedge"],        # Tyranitar: Roca Afilada (opcional)
    445: ["dragonrush"],       # Garchomp: Dragón Buceo (opcional)
    # ────────────────────────────────────────────────
    # Agregar más pares según sea necesario:
    #  <ndex>: ["<move_key>"],
}

class EvolucionService:

    def __init__(self):
        self.db = db_manager
        self.evoluciones: Dict[str, List[Dict[str, Any]]] = self._cargar_evoluciones()
        self._registrar_evoluciones_intercambio()

    # =========================================================================
    # TABLA DE EVOLUCIONES GEN 1-9
    # =========================================================================
    def _cargar_evoluciones(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            # ── GEN 1 KANTO ──────────────────────────────────────────────────
            "1":   [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "2"}],
            "2":   [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "3"}],
            "4":   [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "5"}],
            "5":   [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "6"}],
            "7":   [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "8"}],
            "8":   [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "9"}],
            "10":  [{"metodo": "nivel", "nivel": 7,  "evoluciona_a": "11"}],
            "11":  [{"metodo": "nivel", "nivel": 10, "evoluciona_a": "12"}],
            "13":  [{"metodo": "nivel", "nivel": 7,  "evoluciona_a": "14"}],
            "14":  [{"metodo": "nivel", "nivel": 10, "evoluciona_a": "15"}],
            "16":  [{"metodo": "nivel", "nivel": 18, "evoluciona_a": "17"}],
            "17":  [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "18"}],
            "19":  [{"metodo": "nivel", "nivel": 20, "evoluciona_a": "20"}],
            "21":  [{"metodo": "nivel", "nivel": 20, "evoluciona_a": "22"}],
            "23":  [{"metodo": "nivel", "nivel": 22, "evoluciona_a": "24"}],
            "25":  [{"metodo": "piedra", "piedra": "piedra trueno", "evoluciona_a": "26"}],
            "27":  [{"metodo": "nivel", "nivel": 22, "evoluciona_a": "28"}],
            "29":  [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "30"}],
            "30":  [{"metodo": "piedra", "piedra": "piedra lunar",  "evoluciona_a": "31"}],
            "32":  [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "33"}],
            "33":  [{"metodo": "piedra", "piedra": "piedra lunar",  "evoluciona_a": "34"}],
            "35":  [{"metodo": "piedra", "piedra": "piedra lunar",  "evoluciona_a": "36"}],
            "37":  [{"metodo": "piedra", "piedra": "piedra fuego",  "evoluciona_a": "38"}],
            "39":  [{"metodo": "piedra", "piedra": "piedra lunar",  "evoluciona_a": "40"}],
            "41":  [{"metodo": "nivel", "nivel": 22, "evoluciona_a": "42"}],
            "42":  [{"metodo": "amistad", "nivel_min": 1, "evoluciona_a": "169"}],        # Crobat
            "113": [{"metodo": "amistad", "nivel_min": 1, "evoluciona_a": "242"}],        # Blissey
            "43":  [{"metodo": "nivel", "nivel": 21, "evoluciona_a": "44"}],
            "44":  [{"metodo": "piedra", "piedra": "piedra hoja",   "evoluciona_a": "45"}],
            "46":  [{"metodo": "nivel", "nivel": 24, "evoluciona_a": "47"}],
            "48":  [{"metodo": "nivel", "nivel": 31, "evoluciona_a": "49"}],
            "50":  [{"metodo": "nivel", "nivel": 26, "evoluciona_a": "51"}],
            "52":  [{"metodo": "nivel", "nivel": 28, "evoluciona_a": "53"}],
            "54":  [{"metodo": "nivel", "nivel": 33, "evoluciona_a": "55"}],
            "56":  [{"metodo": "nivel", "nivel": 28, "evoluciona_a": "57"}],
            "58":  [{"metodo": "piedra", "piedra": "piedra fuego",  "evoluciona_a": "59"}],
            "60":  [{"metodo": "nivel", "nivel": 25, "evoluciona_a": "61"}],
            "61":  [{"metodo": "piedra", "piedra": "piedra agua",   "evoluciona_a": "62"}],
            "63":  [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "64"}],
            "64":  [],   # Kadabra → Alakazam solo por intercambio (ver _registrar_evoluciones_intercambio)
            "66":  [{"metodo": "nivel", "nivel": 28, "evoluciona_a": "67"}],
            "67":  [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "68"}],
            "69":  [{"metodo": "nivel", "nivel": 21, "evoluciona_a": "70"}],
            "70":  [{"metodo": "piedra", "piedra": "piedra hoja",   "evoluciona_a": "71"}],
            "72":  [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "73"}],
            "74":  [{"metodo": "nivel", "nivel": 25, "evoluciona_a": "75"}],
            "75":  [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "76"}],
            "77":  [{"metodo": "nivel", "nivel": 40, "evoluciona_a": "78"}],
            "79":  [{"metodo": "nivel", "nivel": 37, "evoluciona_a": "80"}],
            "81":  [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "82"}],
            "82":  [{"metodo": "piedra", "piedra": "piedra trueno", "evoluciona_a": "462"}],   # Magneton → Magnezone
            "299": [{"metodo": "piedra", "piedra": "piedra trueno", "evoluciona_a": "476"}],   # Nosepass → Probopass
            "84":  [{"metodo": "nivel", "nivel": 31, "evoluciona_a": "85"}],
            "86":  [{"metodo": "nivel", "nivel": 34, "evoluciona_a": "87"}],
            "88":  [{"metodo": "nivel", "nivel": 38, "evoluciona_a": "89"}],
            "90":  [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "91"}],
            "92":  [{"metodo": "nivel", "nivel": 25, "evoluciona_a": "93"}],
            "93":  [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "94"}],
            "96":  [{"metodo": "nivel", "nivel": 26, "evoluciona_a": "97"}],
            "98":  [{"metodo": "nivel", "nivel": 28, "evoluciona_a": "99"}],
            "100": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "101"}],
            "102": [{"metodo": "piedra", "piedra": "piedra hoja",   "evoluciona_a": "103"}],
            "104": [{"metodo": "nivel", "nivel": 28, "evoluciona_a": "105"}],
            "109": [{"metodo": "nivel", "nivel": 35, "evoluciona_a": "110"}],
            "111": [{"metodo": "nivel", "nivel": 42, "evoluciona_a": "112"}],
            "116": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "117"}],
            "118": [{"metodo": "nivel", "nivel": 33, "evoluciona_a": "119"}],
            "120": [{"metodo": "piedra", "piedra": "piedra agua",   "evoluciona_a": "121"}],
            "129": [{"metodo": "nivel", "nivel": 20, "evoluciona_a": "130"}],
            "133": [
                {"metodo": "piedra",   "piedra": "piedra agua",                    "evoluciona_a": "134"},   # Vaporeon
                {"metodo": "piedra",   "piedra": "piedra trueno",                  "evoluciona_a": "135"},   # Jolteon
                {"metodo": "piedra",   "piedra": "piedra fuego",                   "evoluciona_a": "136"},   # Flareon
                # Espeon: amistad + hora de día (00:00–11:59)
                {"metodo": "amistad", "nivel_min": 1, "condicion": "dia",          "evoluciona_a": "196"},   # Espeon
                # Umbreon: amistad + hora de noche (12:00–23:59)
                {"metodo": "amistad", "nivel_min": 1, "condicion": "noche",        "evoluciona_a": "197"},   # Umbreon
                {"metodo": "piedra",   "piedra": "piedra hoja",                    "evoluciona_a": "470"},   # Leafeon
                {"metodo": "piedra",   "piedra": "piedra hielo",                   "evoluciona_a": "471"},   # Glaceon
                # Sylveon: amistad + conoce al menos un movimiento tipo Hada
                {"metodo": "amistad", "nivel_min": 1, "condicion": "movimiento_hada", "evoluciona_a": "700"},   # Sylveon
            ],
            "138": [{"metodo": "nivel", "nivel": 40, "evoluciona_a": "139"}],
            "140": [{"metodo": "nivel", "nivel": 40, "evoluciona_a": "141"}],
            "147": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "148"}],
            "148": [{"metodo": "nivel", "nivel": 55, "evoluciona_a": "149"}],
            # ── GEN 2 JOHTO ──────────────────────────────────────────────────
            "152": [{"metodo": "nivel", "nivel": 18, "evoluciona_a": "153"}],
            "153": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "154"}],
            "155": [{"metodo": "nivel", "nivel": 14, "evoluciona_a": "156"}],
            "156": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "157"}],
            "158": [{"metodo": "nivel", "nivel": 18, "evoluciona_a": "159"}],
            "159": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "160"}],
            "161": [{"metodo": "nivel", "nivel": 15, "evoluciona_a": "162"}],
            "163": [{"metodo": "nivel", "nivel": 20, "evoluciona_a": "164"}],
            "165": [{"metodo": "nivel", "nivel": 24, "evoluciona_a": "166"}],
            "167": [{"metodo": "nivel", "nivel": 22, "evoluciona_a": "168"}],
            "177": [{"metodo": "nivel", "nivel": 25, "evoluciona_a": "178"}],
            "179": [{"metodo": "nivel", "nivel": 15, "evoluciona_a": "180"}],
            "180": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "181"}],
            "183": [{"metodo": "nivel", "nivel": 18, "evoluciona_a": "184"}],
            "187": [{"metodo": "nivel", "nivel": 18, "evoluciona_a": "188"}],
            "188": [{"metodo": "nivel", "nivel": 27, "evoluciona_a": "189"}],
            "191": [{"metodo": "piedra", "piedra": "piedra solar",  "evoluciona_a": "192"}],
            # GEN 2 — evoluciones por amistad
            "172": [{"metodo": "amistad", "nivel_min": 1, "evoluciona_a": "25"}],         # Pichu→Pikachu
            "173": [{"metodo": "amistad", "nivel_min": 1, "evoluciona_a": "35"}],         # Cleffa→Clefairy
            "174": [{"metodo": "amistad", "nivel_min": 1, "evoluciona_a": "39"}],         # Igglybuff→Jigglypuff
            "175": [{"metodo": "amistad", "nivel_min": 1, "evoluciona_a": "176"}],        # Togepi→Togetic
            "204": [{"metodo": "nivel", "nivel": 31, "evoluciona_a": "205"}],
            "209": [{"metodo": "amistad", "nivel_min": 1, "evoluciona_a": "210"}],        # Snubbull→Granbull
            "298": [{"metodo": "amistad", "nivel_min": 1, "evoluciona_a": "183"}],        # Azurill→Marill
            "216": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "217"}],
            "218": [{"metodo": "nivel", "nivel": 38, "evoluciona_a": "219"}],
            "220": [{"metodo": "nivel", "nivel": 33, "evoluciona_a": "221"}],
            "223": [{"metodo": "nivel", "nivel": 20, "evoluciona_a": "224"}],
            "228": [{"metodo": "nivel", "nivel": 24, "evoluciona_a": "229"}],
            "231": [{"metodo": "nivel", "nivel": 25, "evoluciona_a": "232"}],
            "246": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "247"}],
            "247": [{"metodo": "nivel", "nivel": 55, "evoluciona_a": "248"}],
            # ── GEN 3 HOENN ──────────────────────────────────────────────────
            "252": [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "253"}],
            "253": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "254"}],
            "255": [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "256"}],
            "256": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "257"}],
            "258": [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "259"}],
            "259": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "260"}],
            "261": [{"metodo": "nivel", "nivel": 18, "evoluciona_a": "262"}],
            "263": [{"metodo": "nivel", "nivel": 20, "evoluciona_a": "264"}],
            "270": [{"metodo": "nivel", "nivel": 14, "evoluciona_a": "271"}],
            "271": [{"metodo": "piedra", "piedra": "piedra hoja",   "evoluciona_a": "272"}],
            "273": [{"metodo": "nivel", "nivel": 14, "evoluciona_a": "274"}],
            "274": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "275"}],
            "276": [{"metodo": "nivel", "nivel": 22, "evoluciona_a": "277"}],
            "278": [{"metodo": "nivel", "nivel": 25, "evoluciona_a": "279"}],
            "280": [{"metodo": "nivel", "nivel": 18, "evoluciona_a": "281"}],
            "281": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "282"}],
            "285": [{"metodo": "nivel", "nivel": 23, "evoluciona_a": "286"}],
            "287": [{"metodo": "nivel", "nivel": 18, "evoluciona_a": "288"}],
            "288": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "289"}],
            "293": [{"metodo": "nivel", "nivel": 20, "evoluciona_a": "294"}],
            "294": [{"metodo": "nivel", "nivel": 40, "evoluciona_a": "295"}],
            "296": [{"metodo": "nivel", "nivel": 24, "evoluciona_a": "297"}],
            "300": [{"metodo": "piedra", "piedra": "piedra lunar",  "evoluciona_a": "301"}],
            "304": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "305"}],
            "305": [{"metodo": "nivel", "nivel": 42, "evoluciona_a": "306"}],
            "307": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "308"}],
            "309": [{"metodo": "nivel", "nivel": 26, "evoluciona_a": "310"}],
            "316": [{"metodo": "nivel", "nivel": 26, "evoluciona_a": "317"}],
            "318": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "319"}],
            "320": [{"metodo": "nivel", "nivel": 40, "evoluciona_a": "321"}],
            "325": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "326"}],
            "328": [{"metodo": "nivel", "nivel": 35, "evoluciona_a": "329"}],
            "329": [{"metodo": "nivel", "nivel": 45, "evoluciona_a": "330"}],
            "331": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "332"}],
            "333": [{"metodo": "nivel", "nivel": 22, "evoluciona_a": "334"}],
            "339": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "340"}],
            "341": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "342"}],
            "343": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "344"}],
            "345": [{"metodo": "nivel", "nivel": 40, "evoluciona_a": "346"}],
            "347": [{"metodo": "nivel", "nivel": 40, "evoluciona_a": "348"}],
            "349": [{"metodo": "nivel", "nivel": 20, "evoluciona_a": "350"}],
            "353": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "354"}],
            "355": [{"metodo": "nivel", "nivel": 37, "evoluciona_a": "356"}],
            "361": [{"metodo": "nivel", "nivel": 42, "evoluciona_a": "362"}],
            "363": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "364"}],
            "364": [{"metodo": "nivel", "nivel": 44, "evoluciona_a": "365"}],
            "371": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "372"}],
            "372": [{"metodo": "nivel", "nivel": 50, "evoluciona_a": "373"}],
            "374": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "375"}],
            "375": [{"metodo": "nivel", "nivel": 45, "evoluciona_a": "376"}],
            # ── GEN 4 SINNOH ─────────────────────────────────────────────────
            "387": [{"metodo": "nivel", "nivel": 18, "evoluciona_a": "388"}],
            "388": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "389"}],
            "390": [{"metodo": "nivel", "nivel": 14, "evoluciona_a": "391"}],
            "391": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "392"}],
            "393": [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "394"}],
            "394": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "395"}],
            "396": [{"metodo": "nivel", "nivel": 14, "evoluciona_a": "397"}],
            "397": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "398"}],
            "399": [{"metodo": "nivel", "nivel": 15, "evoluciona_a": "400"}],
            "401": [{"metodo": "nivel", "nivel": 10, "evoluciona_a": "402"}],
            "403": [{"metodo": "nivel", "nivel": 15, "evoluciona_a": "404"}],
            "404": [{"metodo": "nivel", "nivel": 42, "evoluciona_a": "405"}],
            "408": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "409"}],
            "410": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "411"}],
            "415": [{"metodo": "nivel", "nivel": 21, "evoluciona_a": "416"}],
            "418": [{"metodo": "nivel", "nivel": 26, "evoluciona_a": "419"}],
            "420": [{"metodo": "piedra", "piedra": "piedra hoja",   "evoluciona_a": "421"}],
            "422": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "423"}],
            "425": [{"metodo": "nivel", "nivel": 28, "evoluciona_a": "426"}],
            "406": [{"metodo": "amistad", "nivel_min": 1, "condicion": "dia", "evoluciona_a": "315"}], # Budew→Roselia (día)
            "427": [{"metodo": "amistad", "nivel_min": 1, "evoluciona_a": "428"}],        # Buneary→Lopunny
            "440": [{"metodo": "amistad", "nivel_min": 1, "evoluciona_a": "113"}],        # Happiny→Chansey
            "446": [{"metodo": "amistad", "nivel_min": 1, "evoluciona_a": "143"}],        # Munchlax→Snorlax
            "431": [{"metodo": "nivel", "nivel": 38, "evoluciona_a": "432"}],
            "434": [{"metodo": "nivel", "nivel": 34, "evoluciona_a": "435"}],
            "436": [{"metodo": "nivel", "nivel": 33, "evoluciona_a": "437"}],
            "443": [{"metodo": "nivel", "nivel": 24, "evoluciona_a": "444"}],
            "444": [{"metodo": "nivel", "nivel": 48, "evoluciona_a": "445"}],
            "447": [{"metodo": "amistad", "nivel_min": 1, "condicion": "dia", "evoluciona_a": "448"}], # Riolu→Lucario (día)
            "449": [{"metodo": "nivel", "nivel": 34, "evoluciona_a": "450"}],
            "451": [{"metodo": "nivel", "nivel": 40, "evoluciona_a": "452"}],
            "453": [{"metodo": "nivel", "nivel": 37, "evoluciona_a": "454"}],
            "456": [{"metodo": "nivel", "nivel": 27, "evoluciona_a": "457"}],
            "459": [{"metodo": "nivel", "nivel": 40, "evoluciona_a": "460"}],
            # ── GEN 5 UNOVA ──────────────────────────────────────────────────
            "495": [{"metodo": "nivel", "nivel": 17, "evoluciona_a": "496"}],
            "496": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "497"}],
            "498": [{"metodo": "nivel", "nivel": 17, "evoluciona_a": "499"}],
            "499": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "500"}],
            "501": [{"metodo": "nivel", "nivel": 17, "evoluciona_a": "502"}],
            "502": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "503"}],
            "504": [{"metodo": "nivel", "nivel": 20, "evoluciona_a": "505"}],
            "506": [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "507"}],
            "507": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "508"}],
            "509": [{"metodo": "nivel", "nivel": 20, "evoluciona_a": "510"}],
            "519": [{"metodo": "nivel", "nivel": 21, "evoluciona_a": "520"}],
            "520": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "521"}],
            "522": [{"metodo": "nivel", "nivel": 26, "evoluciona_a": "523"}],
            "524": [{"metodo": "nivel", "nivel": 25, "evoluciona_a": "525"}],
            "525": [{"metodo": "nivel", "nivel": 38, "evoluciona_a": "526"}],
            "527": [{"metodo": "amistad", "nivel_min": 1, "evoluciona_a": "528"}],        # Woobat→Swoobat
            "529": [{"metodo": "nivel", "nivel": 31, "evoluciona_a": "530"}],
            "532": [{"metodo": "nivel", "nivel": 25, "evoluciona_a": "533"}],
            "533": [{"metodo": "nivel", "nivel": 40, "evoluciona_a": "534"}],
            "535": [{"metodo": "nivel", "nivel": 25, "evoluciona_a": "536"}],
            "536": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "537"}],
            "540": [{"metodo": "nivel", "nivel": 20, "evoluciona_a": "541"}],
            "541": [{"metodo": "amistad", "nivel_min": 1, "evoluciona_a": "542"}],        # Swadloon→Leavanny
            "543": [{"metodo": "nivel", "nivel": 22, "evoluciona_a": "544"}],
            "544": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "545"}],
            "546": [{"metodo": "nivel", "nivel": 20, "evoluciona_a": "547"}],
            "548": [{"metodo": "piedra", "piedra": "piedra solar",  "evoluciona_a": "549"}],
            "551": [{"metodo": "nivel", "nivel": 29, "evoluciona_a": "552"}],
            "552": [{"metodo": "nivel", "nivel": 40, "evoluciona_a": "553"}],
            "554": [{"metodo": "nivel", "nivel": 35, "evoluciona_a": "555"}],
            "556": [],
            "557": [{"metodo": "nivel", "nivel": 38, "evoluciona_a": "558"}],
            "559": [{"metodo": "nivel", "nivel": 38, "evoluciona_a": "560"}],
            "561": [],
            "562": [{"metodo": "nivel", "nivel": 34, "evoluciona_a": "563"}],
            "564": [{"metodo": "nivel", "nivel": 37, "evoluciona_a": "565"}],
            "566": [{"metodo": "nivel", "nivel": 38, "evoluciona_a": "567"}],
            "568": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "569"}],
            "570": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "571"}],
            "572": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "573"}],
            "574": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "575"}],
            "575": [{"metodo": "nivel", "nivel": 42, "evoluciona_a": "576"}],
            "577": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "578"}],
            "578": [{"metodo": "nivel", "nivel": 42, "evoluciona_a": "579"}],
            "580": [{"metodo": "nivel", "nivel": 35, "evoluciona_a": "581"}],
            "582": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "583"}],
            "583": [{"metodo": "nivel", "nivel": 47, "evoluciona_a": "584"}],
            "585": [],
            "587": [],
            "588": [{"metodo": "nivel", "nivel": 20, "evoluciona_a": "589"}],
            "590": [{"metodo": "piedra", "piedra": "piedra solar",  "evoluciona_a": "591"}],
            "592": [{"metodo": "nivel", "nivel": 38, "evoluciona_a": "593"}],
            "595": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "596"}],
            "597": [{"metodo": "nivel", "nivel": 38, "evoluciona_a": "598"}],
            "599": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "600"}],
            "600": [{"metodo": "nivel", "nivel": 38, "evoluciona_a": "601"}],
            "602": [{"metodo": "nivel", "nivel": 26, "evoluciona_a": "603"}],
            "603": [{"metodo": "nivel", "nivel": 40, "evoluciona_a": "604"}],
            "607": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "608"}],
            "608": [{"metodo": "nivel", "nivel": 48, "evoluciona_a": "609"}],
            "610": [{"metodo": "nivel", "nivel": 38, "evoluciona_a": "611"}],
            "611": [{"metodo": "nivel", "nivel": 50, "evoluciona_a": "612"}],
            "613": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "614"}],
            "615": [],
            "616": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "617"}],
            "618": [],
            "619": [{"metodo": "nivel", "nivel": 35, "evoluciona_a": "620"}],
            "621": [],
            "624": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "625"}],
            "626": [],
            "627": [{"metodo": "nivel", "nivel": 54, "evoluciona_a": "628"}],
            "629": [{"metodo": "nivel", "nivel": 48, "evoluciona_a": "630"}],
            "631": [],
            "632": [],
            "633": [{"metodo": "nivel", "nivel": 50, "evoluciona_a": "634"}],
            "634": [{"metodo": "nivel", "nivel": 64, "evoluciona_a": "635"}],
            "636": [{"metodo": "nivel", "nivel": 59, "evoluciona_a": "637"}],
            # ── GEN 6 KALOS ──────────────────────────────────────────────────
            "650": [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "651"}],
            "651": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "652"}],
            "653": [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "654"}],
            "654": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "655"}],
            "656": [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "657"}],
            "657": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "658"}],
            "659": [{"metodo": "nivel", "nivel": 20, "evoluciona_a": "660"}],
            "661": [{"metodo": "nivel", "nivel": 17, "evoluciona_a": "662"}],
            "662": [{"metodo": "nivel", "nivel": 35, "evoluciona_a": "663"}],
            "664": [{"metodo": "nivel", "nivel": 9,  "evoluciona_a": "665"}],
            "665": [{"metodo": "nivel", "nivel": 12, "evoluciona_a": "666"}],
            "667": [{"metodo": "nivel", "nivel": 35, "evoluciona_a": "668"}],
            "669": [{"metodo": "piedra", "piedra": "piedra brillante", "evoluciona_a": "670"}],
            "672": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "673"}],
            "674": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "675"}],
            "677": [{"metodo": "nivel", "nivel": 25, "evoluciona_a": "678"}],
            "679": [{"metodo": "nivel", "nivel": 35, "evoluciona_a": "680"}],
            "680": [{"metodo": "nivel", "nivel": 45, "evoluciona_a": "681"}],
            "682": [{"metodo": "nivel", "nivel": 29, "evoluciona_a": "683"}],
            "684": [{"metodo": "nivel", "nivel": 29, "evoluciona_a": "685"}],
            "686": [{"metodo": "nivel", "nivel": 38, "evoluciona_a": "687"}],
            "688": [{"metodo": "nivel", "nivel": 40, "evoluciona_a": "689"}],
            "690": [{"metodo": "nivel", "nivel": 48, "evoluciona_a": "691"}],
            "692": [{"metodo": "nivel", "nivel": 28, "evoluciona_a": "693"}],
            "694": [{"metodo": "nivel", "nivel": 38, "evoluciona_a": "695"}],
            "696": [{"metodo": "nivel", "nivel": 39, "evoluciona_a": "697"}],
            "698": [{"metodo": "nivel", "nivel": 42, "evoluciona_a": "699"}],
            "702": [],
            "703": [],
            "704": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "705"}],
            "705": [{"metodo": "nivel", "nivel": 42, "evoluciona_a": "706"}],
            "707": [],
            "708": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "709"}],
            "710": [],
            "712": [{"metodo": "nivel", "nivel": 37, "evoluciona_a": "713"}],
            "714": [{"metodo": "nivel", "nivel": 48, "evoluciona_a": "715"}],
            # ── GEN 7 ALOLA ──────────────────────────────────────────────────
            "722": [{"metodo": "nivel", "nivel": 17, "evoluciona_a": "723"}],
            "723": [{"metodo": "nivel", "nivel": 34, "evoluciona_a": "724"}],
            "725": [{"metodo": "nivel", "nivel": 17, "evoluciona_a": "726"}],
            "726": [{"metodo": "nivel", "nivel": 34, "evoluciona_a": "727"}],
            "728": [{"metodo": "nivel", "nivel": 17, "evoluciona_a": "729"}],
            "729": [{"metodo": "nivel", "nivel": 34, "evoluciona_a": "730"}],
            "734": [{"metodo": "nivel", "nivel": 20, "evoluciona_a": "735"}],
            "736": [{"metodo": "nivel", "nivel": 20, "evoluciona_a": "737"}],
            "737": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "738"}],
            "742": [{"metodo": "nivel", "nivel": 24, "evoluciona_a": "743"}],
            "744": [{"metodo": "nivel", "nivel": 25, "evoluciona_a": "745"}],
            "747": [{"metodo": "nivel", "nivel": 22, "evoluciona_a": "748"}],
            "749": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "750"}],
            "751": [{"metodo": "nivel", "nivel": 28, "evoluciona_a": "752"}],
            "753": [{"metodo": "nivel", "nivel": 24, "evoluciona_a": "754"}],
            "755": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "756"}],
            "757": [{"metodo": "nivel", "nivel": 22, "evoluciona_a": "758"}],
            "759": [{"metodo": "nivel", "nivel": 28, "evoluciona_a": "760"}],
            "761": [{"metodo": "nivel", "nivel": 18, "evoluciona_a": "762"}],
            "762": [{"metodo": "nivel", "nivel": 34, "evoluciona_a": "763"}],
            "764": [],
            "765": [],
            "766": [],
            "767": [{"metodo": "nivel", "nivel": 22, "evoluciona_a": "768"}],
            "769": [{"metodo": "nivel", "nivel": 42, "evoluciona_a": "770"}],
            "771": [],
            "776": [],
            "777": [{"metodo": "nivel", "nivel": 38, "evoluciona_a": "778"}],
            "780": [],
            "781": [],
            "782": [{"metodo": "nivel", "nivel": 35, "evoluciona_a": "783"}],
            "783": [{"metodo": "nivel", "nivel": 45, "evoluciona_a": "784"}],
            "785": [], "786": [], "787": [], "788": [],
            # ── GEN 8 GALAR ──────────────────────────────────────────────────
            "810": [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "811"}],
            "811": [{"metodo": "nivel", "nivel": 34, "evoluciona_a": "812"}],
            "813": [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "814"}],
            "814": [{"metodo": "nivel", "nivel": 34, "evoluciona_a": "815"}],
            "816": [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "817"}],
            "817": [{"metodo": "nivel", "nivel": 34, "evoluciona_a": "818"}],
            "819": [{"metodo": "nivel", "nivel": 20, "evoluciona_a": "820"}],
            "821": [{"metodo": "nivel", "nivel": 18, "evoluciona_a": "822"}],
            "822": [{"metodo": "nivel", "nivel": 38, "evoluciona_a": "823"}],
            "824": [{"metodo": "nivel", "nivel": 25, "evoluciona_a": "825"}],
            "825": [{"metodo": "nivel", "nivel": 35, "evoluciona_a": "826"}],
            "827": [{"metodo": "nivel", "nivel": 18, "evoluciona_a": "828"}],
            "829": [{"metodo": "nivel", "nivel": 15, "evoluciona_a": "830"}],
            "831": [{"metodo": "nivel", "nivel": 24, "evoluciona_a": "832"}],
            "833": [{"metodo": "nivel", "nivel": 22, "evoluciona_a": "834"}],
            "835": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "836"}],
            "837": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "838"}],
            "838": [{"metodo": "nivel", "nivel": 42, "evoluciona_a": "839"}],
            "840": [{"metodo": "nivel", "nivel": 25, "evoluciona_a": "841"}],
            "843": [{"metodo": "nivel", "nivel": 34, "evoluciona_a": "844"}],
            "845": [],
            "846": [{"metodo": "nivel", "nivel": 28, "evoluciona_a": "847"}],
            "848": [{"metodo": "nivel", "nivel": 28, "evoluciona_a": "849"}],
            "850": [{"metodo": "nivel", "nivel": 29, "evoluciona_a": "851"}],
            "852": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "853"}],
            "854": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "855"}],
            "856": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "857"}],
            "859": [{"metodo": "nivel", "nivel": 18, "evoluciona_a": "860"}],
            "860": [{"metodo": "nivel", "nivel": 35, "evoluciona_a": "861"}],
            "862": [],
            "863": [],
            "864": [],
            "865": [],
            "867": [],
            "868": [{"metodo": "nivel", "nivel": 26, "evoluciona_a": "869"}],
            "870": [],
            "871": [],
            "872": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "873"}],
            "874": [],
            "875": [],
            "876": [],
            "877": [],
            "878": [{"metodo": "nivel", "nivel": 35, "evoluciona_a": "879"}],
            "880": [],
            "881": [],
            "882": [],
            "883": [],
            "884": [],
            # ── GEN 9 PALDEA ─────────────────────────────────────────────────
            "906": [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "907"}],
            "907": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "908"}],
            "909": [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "910"}],
            "910": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "911"}],
            "912": [{"metodo": "nivel", "nivel": 16, "evoluciona_a": "913"}],
            "913": [{"metodo": "nivel", "nivel": 36, "evoluciona_a": "914"}],
            "915": [{"metodo": "nivel", "nivel": 18, "evoluciona_a": "916"}],
            "921": [{"metodo": "nivel", "nivel": 25, "evoluciona_a": "922"}],
            "924": [{"metodo": "nivel", "nivel": 28, "evoluciona_a": "925"}],
            "926": [],
            "927": [{"metodo": "nivel", "nivel": 25, "evoluciona_a": "928"}],
            "929": [{"metodo": "nivel", "nivel": 18, "evoluciona_a": "930"}],
            "931": [],
            "932": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "933"}],
            "935": [{"metodo": "nivel", "nivel": 30, "evoluciona_a": "936"}],
            "938": [{"metodo": "nivel", "nivel": 25, "evoluciona_a": "939"}],
            "940": [{"metodo": "nivel", "nivel": 25, "evoluciona_a": "941"}],
            "942": [{"metodo": "nivel", "nivel": 28, "evoluciona_a": "943"}],
            "944": [{"metodo": "nivel", "nivel": 29, "evoluciona_a": "945"}],
            "945": [{"metodo": "nivel", "nivel": 49, "evoluciona_a": "946"}],
            "947": [{"metodo": "nivel", "nivel": 35, "evoluciona_a": "948"}],
            "949": [],
            "950": [],
            "951": [],
            "953": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "954"}],
            "955": [{"metodo": "nivel", "nivel": 18, "evoluciona_a": "956"}],
            "956": [{"metodo": "nivel", "nivel": 38, "evoluciona_a": "957"}],
            "958": [{"metodo": "nivel", "nivel": 28, "evoluciona_a": "959"}],
            "959": [{"metodo": "nivel", "nivel": 38, "evoluciona_a": "960"}],
            "961": [{"metodo": "nivel", "nivel": 18, "evoluciona_a": "962"}],
            "963": [{"metodo": "nivel", "nivel": 28, "evoluciona_a": "964"}],
            "965": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "966"}],
            "967": [{"metodo": "nivel", "nivel": 32, "evoluciona_a": "968"}],
        }

    # =========================================================================
    # VERIFICAR EVOLUCIÓN
    # =========================================================================

    def _get_pokemon(self, pokemon_id: int):
        """Lazy import de pokemon_service para evitar circular import."""
        from pokemon.services.pokemon_service import pokemon_service as _ps
        return _ps.obtener_pokemon(pokemon_id)

    def _registrar_evoluciones_intercambio(self) -> None:
        """
        Añade (o actualiza) entradas de evolución por intercambio al dict
        self.evoluciones.  Se llama al final de __init__ para no contaminar
        el bloque principal de datos.

        Formato de cada entrada:
          {"metodo": "intercambio", "evoluciona_a": "<id>"}
          {"metodo": "intercambio", "item": "<item_key>", "evoluciona_a": "<id>"}

        La clave "item" es OPCIONAL: si está presente el Pokémon debe llevar
        ese objeto equipado para que se produzca la evolución.

        Pokémon con 'metodo: intercambio' SIN item requerido:
          Kadabra (64)  → Alakazam (65)
          Machoke (67)  → Machamp (68)
          Graveler (75) → Golem (76)
          Haunter (93)  → Gengar (94)

        Pokémon con item requerido (objeto equipado al intercambiar):
          Onix     (95)  + metalcoat    → Steelix  (208)
          Scyther  (123) + metalcoat    → Scizor   (212)
          Porygon  (137) + upgrade      → Porygon2 (233)
          Seadra   (117) + dragonscale  → Kingdra  (230)
          Slowpoke (79)  + kingsrock    → Slowking (199)
          Poliwhirl(61)  + kingsrock    → Politoed (186)
          Feebas   (349) + prismscale   → Milotic  (350)
          Clamperl (366) + deepseatooth → Huntail  (367)
          Clamperl (366) + deepseascale → Gorebyss (368)
          Porygon2 (233) + dubiousdisc  → Porygon-Z(474)
          Dusclops (356) + reapercloth  → Dusknoir (477)
          Electabuzz(125)+ electirizer  → Electivire(466)
          Magmar   (126) + magmarizer   → Magmortar(467)
          Rhydon   (112) + protector    → Rhyperior(464)
        """
        # ── Intercambio simple (sin item) ──────────────────────────────────
        _simples: list[tuple[str, str]] = [
            ("64", "65"),   # Kadabra  → Alakazam
            ("67", "68"),   # Machoke  → Machamp
            ("75", "76"),   # Graveler → Golem
            ("93", "94"),   # Haunter  → Gengar
        ]
        for sp_id, evo_id in _simples:
            entrada = {"metodo": "intercambio", "evoluciona_a": evo_id}
            if sp_id not in self.evoluciones:
                self.evoluciones[sp_id] = [entrada]
            elif not any(
                e.get("metodo") == "intercambio" and e.get("evoluciona_a") == evo_id
                for e in self.evoluciones[sp_id]
            ):
                self.evoluciones[sp_id].append(entrada)

        # ── Intercambio con item requerido ─────────────────────────────────
        _con_item: list[tuple[str, str, str]] = [
            # (especie_id, item_key, evo_id)
            ("95",  "metalcoat",    "208"),  # Onix      → Steelix
            ("123", "metalcoat",    "212"),  # Scyther   → Scizor
            ("137", "upgrade",      "233"),  # Porygon   → Porygon2
            ("117", "dragonscale",  "230"),  # Seadra    → Kingdra
            ("79",  "kingsrock",    "199"),  # Slowpoke  → Slowking
            ("61",  "kingsrock",    "186"),  # Poliwhirl → Politoed
            ("349", "prismscale",   "350"),  # Feebas    → Milotic
            ("366", "deepseatooth", "367"),  # Clamperl  → Huntail
            ("366", "deepseascale", "368"),  # Clamperl  → Gorebyss
            ("233", "dubiousdisc",  "474"),  # Porygon2  → Porygon-Z
            ("356", "reapercloth",  "477"),  # Dusclops  → Dusknoir
            ("125", "electirizer",  "466"),  # Electabuzz→ Electivire
            ("126", "magmarizer",   "467"),  # Magmar    → Magmortar
            ("112", "protector",    "464"),  # Rhydon    → Rhyperior
        ]
        for sp_id, item_key, evo_id in _con_item:
            entrada = {"metodo": "intercambio", "item": item_key, "evoluciona_a": evo_id}
            if sp_id not in self.evoluciones:
                self.evoluciones[sp_id] = [entrada]
            elif not any(
                e.get("metodo") == "intercambio"
                and e.get("item") == item_key
                and e.get("evoluciona_a") == evo_id
                for e in self.evoluciones[sp_id]
            ):
                self.evoluciones[sp_id].append(entrada)

    def verificar_evolucion(
        self, pokemon_id: int
    ) -> Tuple[bool, Optional[Dict]]:
        try:
            pokemon = self._get_pokemon(pokemon_id)
            if not pokemon:
                return False, None
            movs = getattr(pokemon, "movimientos", None) or []
            return self.verificar_evolucion_por_nivel(
                pokemon_id, pokemon.nivel,
                movimientos_actuales=movs,
            )
        except Exception as e:
            logger.error(f"❌ Error verificando evolución: {e}")
            return False, None

    def verificar_evolucion_por_intercambio(
        self,
        pokemon_id: int,
    ) -> "Tuple[bool, Optional[Dict]]":
        """
        Determina si un Pokémon puede evolucionar al ser intercambiado.

        Reglas (en orden de prioridad):
          1. Si el Pokémon lleva una 'piedra eterna' (everstone) equipada,
             la evolución NUNCA se produce, se devuelve (False, None).
          2. Si la especie tiene entradas con metodo='intercambio':
             a. Si la entrada NO requiere item  → evoluciona siempre.
             b. Si la entrada REQUIERE item     → solo evoluciona si el
                Pokémon lleva ESE item equipado.
          3. Si no se encuentra ninguna entrada compatible → (False, None).

        Returns:
            (puede_evolucionar, evo_data)
            evo_data es el dict de evolución seleccionado, o None.
        """
        try:
            pokemon = self._get_pokemon(pokemon_id)
            if not pokemon:
                return False, None

            # ── 1. Everstone bloquea cualquier evolución por intercambio ───
            objeto_equipado = (getattr(pokemon, "objeto", None) or "").lower().strip()
            if objeto_equipado in ("everstone", "piedra eterna"):
                logger.debug(
                    f"[EVO] Pokémon {pokemon_id} lleva everstone → sin evolución"
                )
                return False, None

            especies_id = str(pokemon.pokemonID)
            evoluciones = self.evoluciones.get(especies_id, [])

            for evo in evoluciones:
                if evo.get("metodo") != "intercambio":
                    continue

                item_requerido = evo.get("item")

                if item_requerido is None:
                    # Sin requisito de item: evoluciona por intercambio simple
                    return True, evo

                # Con item: verificar que el Pokémon lo lleva equipado
                if objeto_equipado == item_requerido.lower():
                    return True, evo

            return False, None

        except Exception as e:
            logger.error(
                f"[EVO] Error en verificar_evolucion_por_intercambio "
                f"(pokemon_id={pokemon_id}): {e}"
            )
            return False, None
        
    def verificar_evolucion_por_nivel(
        self,
        pokemon_id: int,
        nivel_alcanzado: int,
        movimientos_actuales: "list | None" = None,
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Verifica si un Pokémon puede evolucionar dado su nivel (y condiciones extra).
        """
        try:
            pokemon = self._get_pokemon(pokemon_id)
            if not pokemon:
                return False, None

            # Piedra Eterna bloquea evolución por nivel
            objeto_equipado = (getattr(pokemon, "objeto", None) or "").lower().strip()
            if objeto_equipado in ("everstone", "piedra eterna"):
                return False, None

            especies_id = str(pokemon.pokemonID)
            evoluciones = self.evoluciones.get(especies_id, [])
            hora_actual = datetime.datetime.now().hour

            # Obtenemos los movimientos directamente del objeto pokemon
            # Si no se pasan movimientos_actuales, usamos los del objeto
            movs_lista = movimientos_actuales if movimientos_actuales is not None else getattr(pokemon, "movimientos", [])

            for evo in evoluciones:
                metodo = evo.get("metodo")

                # ── Evolución por nivel ────────────────────────────────────
                if metodo == "nivel" and nivel_alcanzado >= evo.get("nivel", 999):
                    return True, evo

                # ── Evolución por amistad ──────────────────────────────────
                elif metodo == "amistad":
                    nivel_min = evo.get("nivel_min", 1)
                    if nivel_alcanzado < nivel_min:
                        continue 

                    condicion = evo.get("condicion")

                    if condicion is None:
                        return True, evo

                    elif condicion == "dia":
                        if 0 <= hora_actual < 12:
                            return True, evo

                    elif condicion == "noche":
                        if hora_actual >= 12:
                            return True, evo

                    elif condicion == "movimiento_hada":
                        # Verificamos si alguno de los movimientos en el objeto es tipo Hada
                        # Nota: Se asume que 'movs_lista' contiene objetos o dicts con la info del tipo
                        for mv in movs_lista:
                            if not mv:
                                continue
                            
                            # Ajusta 'mv.get("tipo")' según la estructura real de tus movimientos
                            tipo_mov = mv.get("tipo") if isinstance(mv, dict) else getattr(mv, "tipo", None)
                            
                            if tipo_mov == "Hada":
                                return True, evo

            return False, None

        except Exception as e:
            logger.error(f"❌ Error en verificar_evolucion_por_nivel: {e}")
            return False, None

    # =========================================================================
    # EVOLUCIONAR POKÉMON
    # =========================================================================

    def evolucionar_pokemon(
        self,
        pokemon_id: int,
        forzar: bool = False,
        evo_data_override: "dict | None" = None,
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Evoluciona un Pokémon.

        Args:
            pokemon_id:        ID único del Pokémon.
            forzar:            Si True, omite la validación de nivel/amistad.
            evo_data_override: Dict de evolución a usar directamente.
                               Cuando se pasa, se ignoran verificar_evolucion
                               y el fallback a evos[0].  Imprescindible para
                               usar_piedra_evolutiva, que ya buscó la evo
                               correcta antes de llamar aquí.
        """
        try:
            from pokemon.services.pokedex_service import pokedex_service as _pokedex

            pokemon = self._get_pokemon(pokemon_id)
            if not pokemon:
                return False, "Pokémon no encontrado", None

            # Override explícito → saltarse toda verificación
            if evo_data_override is not None:
                evo_data = evo_data_override
            else:
                puede, evo_data = self.verificar_evolucion(pokemon_id)
                if not puede and not forzar:
                    return False, "No puede evolucionar", None

                if forzar and not evo_data:
                    evos = self.evoluciones.get(str(pokemon.pokemonID), [])
                    evo_data = evos[0] if evos else None

            if not evo_data:
                return False, "No hay datos de evolución", None

            nuevo_sp_id  = int(evo_data["evoluciona_a"])
            nombre_antes = pokemon.mote or pokemon.nombre
            nombre_nuevo = _pokedex.obtener_nombre(nuevo_sp_id)

            self.db.execute_update(
                "UPDATE POKEMON_USUARIO SET pokemonID = ? WHERE id_unico = ?",
                (nuevo_sp_id, pokemon_id),
            )

            # Si la evolución requería un item equipado, consumirlo (quitar del Pokémon).
            # El item ya cumplió su función; no debe quedar equipado en la nueva forma.
            if evo_data and evo_data.get("item"):
                try:
                    self.db.execute_update(
                        "UPDATE POKEMON_USUARIO SET objeto = NULL WHERE id_unico = ?",
                        (pokemon_id,),
                    )
                    logger.debug(
                        f"[EVO] Item '{evo_data['item']}' consumido tras evolución "
                        f"de poke#{pokemon_id}"
                    )
                except Exception as e:
                    logger.warning(f"[EVO] No se pudo limpiar objeto tras evolución: {e}")

            try:
                from pokemon.experience_system import ExperienceSystem
                ExperienceSystem._recalcular_stats(pokemon_id, pokemon.nivel)
            except Exception as e:
                logger.warning(f"[EVO] No se pudieron recalcular stats: {e}")

            # Guardar movimientos exclusivos post-evolución para ofrecerlos
            # en level_up_handler después de mostrar la animación.
            post_moves = POST_EVO_EXCLUSIVE_MOVES.get(nuevo_sp_id, [])
            if post_moves:
                try:
                    self.db.execute_update(
                        "UPDATE POKEMON_USUARIO SET post_evo_moves_pending = ? "
                        "WHERE id_unico = ?",
                        (",".join(post_moves), pokemon_id),
                    )
                except Exception as _e:
                    logger.debug(f"[EVO] No se pudo guardar post_evo_moves_pending: {_e}")
                    # Si la columna no existe, lo manejamos con el sistema de memoria
                    # en level_up_handler usando _POST_EVO_EXCLUSIVE directamente.
                    
            logger.info(f"✨ {nombre_antes} → {nombre_nuevo} (id={pokemon_id})")
            return True, f"✨ ¡{nombre_antes} evolucionó a {nombre_nuevo}!", nuevo_sp_id

        except Exception as e:
            logger.error(f"❌ Error evolucionando: {e}")
            return False, f"Error: {str(e)}", None

    def usar_piedra_evolutiva(
        self, pokemon_id: int, piedra: str, user_id: int
    ) -> Tuple[bool, str]:
        try:
            from pokemon.services.items_service import items_service as _items

            pokemon = self._get_pokemon(pokemon_id)
            if not pokemon:
                return False, "Pokémon no encontrado"

            inventario = _items.obtener_inventario(user_id)
            if inventario.get(piedra, 0) < 1:
                return False, f"No tienes {piedra}"

            especies_id  = str(pokemon.pokemonID)
            evo_correcta = next(
                (e for e in self.evoluciones.get(especies_id, [])
                 if e["metodo"] == "piedra" and e.get("piedra") == piedra),
                None,
            )
            if not evo_correcta:
                return False, "Esta piedra no funciona con este Pokémon"

            _items.usar_item(user_id, piedra, 1)
            # FIX: pasar evo_correcta como override para no depender del
            # fallback a evos[0], que devolvería la primera evolución de la
            # lista independientemente de la piedra usada.
            exito, mensaje, _ = self.evolucionar_pokemon(
                pokemon_id,
                forzar=True,
                evo_data_override=evo_correcta,
            )
            if exito:
                return True, f"💎 Usaste {piedra}!\n{mensaje}"
            _items.agregar_item(user_id, piedra, 1)
            return False, "Error al evolucionar"
        except Exception as e:
            logger.error(f"❌ Error usando piedra: {e}")
            return False, f"Error: {str(e)}"

    def obtener_linea_evolutiva(self, pokemon_id: int) -> List[int]:
        pre_evos = [
            int(esp)
            for esp, evos in self.evoluciones.items()
            for evo in evos if evo.get("evoluciona_a") == str(pokemon_id)
        ]
        post_evos = [
            int(e["evoluciona_a"])
            for e in self.evoluciones.get(str(pokemon_id), [])
        ]
        return pre_evos + [pokemon_id] + post_evos


# Instancia global
evolucion_service = EvolucionService()