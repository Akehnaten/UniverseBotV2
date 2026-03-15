"""
Servicio de Items Pokémon COMPLETO
Base de datos exhaustiva con TODOS los items competitivos
"""

import json
import logging
from typing import Optional, Dict, List, Tuple
from database import db_manager

logger = logging.getLogger(__name__)


class ItemsService:
    """Servicio para gestionar items de Pokémon"""
    
    def __init__(self):
        self.db = db_manager
        self.items_db = self._cargar_items()
        self.categorias = self._cargar_categorias()
    
    def _cargar_items(self) -> Dict:
        """Base de datos COMPLETA de items"""
        return {
            # ========== POKÉBALLS ==========
            "pokeball":    {"precio": 1,      "ratio": 1.0,   "tipo": "pokeball", "desc": "Poké Ball estándar — 1×"},
            "greatball":   {"precio": 3,      "ratio": 1.5,   "tipo": "pokeball", "desc": "Super Ball — 1.5×"},
            "superball":   {"precio": 3,      "ratio": 1.5,   "tipo": "pokeball", "desc": "Super Ball — alias de greatball"},
            "ultraball":   {"precio": 6,      "ratio": 2.0,   "tipo": "pokeball", "desc": "Ultra Ball — 2×"},
            "masterball":  {"precio": 999999, "ratio": 255.0, "tipo": "pokeball", "desc": "Master Ball — captura garantizada"},
            "premierball": {"precio": 1,      "ratio": 1.0,   "tipo": "pokeball", "desc": "Honor Ball — cosmética (1×)"},
            "quickball":   {"precio": 5,      "ratio": 5.0,   "tipo": "pokeball", "condicion": "primer_turno", "desc": "Veloz Ball — 5× turno 1, 1× resto"},
            "timerball":   {"precio": 5,      "ratio": 1.0,   "tipo": "pokeball", "condicion": "turnos",       "desc": "Turno Ball — crece por turno, máx 4×"},
            "nestball":    {"precio": 5,      "ratio": 1.0,   "tipo": "pokeball", "condicion": "nivel_bajo",   "desc": "Nido Ball — mejor contra niveles bajos"},
            "netball":     {"precio": 5,      "ratio": 3.5,   "tipo": "pokeball", "condicion": "agua_bicho",   "desc": "Red Ball — 3.5× vs Agua o Bicho"},
            "repeatball":  {"precio": 5,      "ratio": 3.5,   "tipo": "pokeball", "condicion": "capturado",    "desc": "Acopio Ball — 3.5× si ya capturaste esa especie"},
            "duskball":    {"precio": 5,      "ratio": 3.5,   "tipo": "pokeball", "condicion": "noche",        "desc": "Ocaso Ball — 3.5× de noche (20h–6h)"},
            "diveball":    {"precio": 5,      "ratio": 3.5,   "tipo": "pokeball", "condicion": "agua",         "desc": "Buceo Ball — 3.5×"},
            
            # ========== MEDICINAS HP ==========
            "pocion": {"precio": 2, "cura_hp": 20, "tipo": "medicina", "desc": "Restaura 20 HP"},
            "superpocion": {"precio": 4, "cura_hp": 60, "tipo": "medicina", "desc": "Restaura 60 HP"},
            "hiperpocion": {"precio": 8, "cura_hp": 120, "tipo": "medicina", "desc": "Restaura 120 HP"},
            "pocion maxima": {"precio": 13, "cura_hp": 9999, "tipo": "medicina", "desc": "Restaura todo HP"},
            "restaurar todo": {"precio": 15, "cura_hp": 9999, "cura_estado": True, "tipo": "medicina", "desc": "Cura HP y estado"},
            
            # ========== REVIVIR ==========
            "revivir": {"precio": 10, "revive": 0.5, "tipo": "medicina", "desc": "Revive con 50% HP"},
            "revivir max": {"precio": 20, "revive": 1.0, "tipo": "medicina", "desc": "Revive con HP completo"},
            
            # ========== CURAR ESTADOS ==========
            "antidoto": {"precio": 1, "cura_estado": "envenenado", "tipo": "medicina", "desc": "Cura envenenamiento"},
            "despertar": {"precio": 2, "cura_estado": "dormido", "tipo": "medicina", "desc": "Despierta"},
            "antiquemar": {"precio": 2, "cura_estado": "quemado", "tipo": "medicina", "desc": "Cura quemaduras"},
            "antiparalizar": {"precio": 2, "cura_estado": "paralizado", "tipo": "medicina", "desc": "Cura parálisis"},
            "antihielo": {"precio": 2, "cura_estado": "congelado", "tipo": "medicina", "desc": "Descongela"},
            "cura total": {"precio": 3, "cura_todos_estados": True, "tipo": "medicina", "desc": "Cura todos estados"},
            
            # ========== PP ==========
            "eter": {"precio": 6, "pp": 10, "tipo": "medicina", "desc": "Restaura 10 PP"},
            "eter max": {"precio": 12, "pp": 999, "tipo": "medicina", "desc": "Restaura PP completo"},
            "elixir": {"precio": 15, "pp_todos": 10, "tipo": "medicina", "desc": "10 PP a todos"},
            "elixir max": {"precio": 30, "pp_todos": 999, "tipo": "medicina", "desc": "PP completo a todos"},
            
            # ========== VITAMINAS (EVs) ==========
            "mas ps": {"precio": 50, "ev": "hp", "cantidad": 10, "tipo": "vitamina", "desc": "+10 EVs HP"},
            "proteina": {"precio": 50, "ev": "atq", "cantidad": 10, "tipo": "vitamina", "desc": "+10 EVs Ataque"},
            "hierro": {"precio": 50, "ev": "def", "cantidad": 10, "tipo": "vitamina", "desc": "+10 EVs Defensa"},
            "calcio": {"precio": 50, "ev": "atq_sp", "cantidad": 10, "tipo": "vitamina", "desc": "+10 EVs At.Esp"},
            "zinc": {"precio": 50, "ev": "def_sp", "cantidad": 10, "tipo": "vitamina", "desc": "+10 EVs Def.Esp"},
            "carburante": {"precio": 50, "ev": "vel", "cantidad": 10, "tipo": "vitamina", "desc": "+10 EVs Velocidad"},
            
            # ========== PIEDRAS EVOLUTIVAS ==========
            "piedra fuego": {"precio": 15, "tipo": "evolutivo", "evolucion": "Fuego", "desc": "Evoluciona Pokémon Fuego"},
            "piedra agua": {"precio": 15, "tipo": "evolutivo", "evolucion": "Agua", "desc": "Evoluciona Pokémon Agua"},
            "piedra trueno": {"precio": 15, "tipo": "evolutivo", "evolucion": "Electrico", "desc": "Evoluciona Pokémon Eléctrico"},
            "piedra hoja": {"precio": 15, "tipo": "evolutivo", "evolucion": "Planta", "desc": "Evoluciona Pokémon Planta"},
            "piedra lunar": {"precio": 15, "tipo": "evolutivo", "evolucion": "Luna", "desc": "Evoluciona ciertos Pokémon"},
            "piedra solar": {"precio": 15, "tipo": "evolutivo", "evolucion": "Sol", "desc": "Evoluciona ciertos Pokémon"},
            "piedra alba": {"precio": 20, "tipo": "evolutivo", "evolucion": "Alba", "desc": "Evoluciona ciertos Pokémon"},
            "piedra noche": {"precio": 20, "tipo": "evolutivo", "evolucion": "Noche", "desc": "Evoluciona ciertos Pokémon"},
            
            # ========== ROCAS METEOROLÓGICAS ==========
            "heatrock":   {"precio": 50, "extiende_clima": "sun",  "turnos": 8,
                           "tipo": "clima_terreno",
                           "desc": "☀️ Roca Calorífica — Sol Intenso dura 8 turnos"},
            "damprock":   {"precio": 50, "extiende_clima": "rain", "turnos": 8,
                           "tipo": "clima_terreno",
                           "desc": "🌧️ Roca Húmeda — Lluvia dura 8 turnos"},
            "smoothrock": {"precio": 50, "extiende_clima": "sand", "turnos": 8,
                           "tipo": "clima_terreno",
                           "desc": "🌪️ Roca Lisa — Tormenta de Arena dura 8 turnos"},
            "icyrock":    {"precio": 50, "extiende_clima": "snow", "turnos": 8,
                           "tipo": "clima_terreno",
                           "desc": "❄️ Roca Helada — Nevada dura 8 turnos"},

            # ========== ITEMS DE PODER (OFENSIVOS) ==========
            "vidasfera": {"precio": 80, "tipo": "combate_poder", "efecto": "vida_orb", "boost": 1.3, "recoil": 0.1, "desc": "x1.3 poder, pierde 10% HP"},
            "banda experto": {"precio": 70, "tipo": "combate_poder", "efecto": "expert_belt", "boost": 1.2, "condicion": "super_efectivo", "desc": "x1.2 vs súper efectivo"},
            "gafas sabias": {"precio": 70, "tipo": "combate_poder", "efecto": "wise_glasses", "boost": 1.1, "stat": "atq_sp", "desc": "+10% At.Esp"},
            "banda muscular": {"precio": 70, "tipo": "combate_poder", "efecto": "muscle_band", "boost": 1.1, "stat": "atq", "desc": "+10% Ataque físico"},
            "metrónomo": {"precio": 60, "tipo": "combate_poder", "efecto": "metronome_item", "boost_max": 2.0, "desc": "Boost acumulativo por repetir"},
            "lente zoom": {"precio": 50, "tipo": "combate_poder", "efecto": "zoom_lens", "boost_precision": 1.2, "desc": "+20% precisión si va segundo"},
            
            # ========== ITEMS DEFENSIVOS ==========
            "restos": {"precio": 30, "tipo": "combate_defensivo", "efecto": "leftovers", "recupera": 0.0625, "desc": "Recupera 1/16 HP/turno"},
            "lodo negro": {"precio": 35, "tipo": "combate_defensivo", "efecto": "black_sludge", "recupera": 0.0625, "solo_tipo": "Veneno", "desc": "1/16 HP/turno (solo Veneno)"},
            "casco dentado": {"precio": 50, "tipo": "combate_defensivo", "efecto": "rocky_helmet", "daño_contacto": 0.1667, "desc": "Daña 1/6 al contacto"},
            "púas venenosas": {"precio": 50, "tipo": "combate_defensivo", "efecto": "sticky_barb", "daño_portador": 0.125, "daño_contacto": 0.125, "desc": "Daña 1/8 HP/turno"},
            "bola férrea": {"precio": 40, "tipo": "combate_defensivo", "efecto": "iron_ball", "reduce_vel": 0.5, "anula_inmune": "Tierra", "desc": "-50% Vel, anula inmunidad Tierra"},
            "campana concha": {"precio": 45, "tipo": "combate_defensivo", "efecto": "shell_bell", "cura_daño": 0.125, "desc": "Recupera 1/8 del daño hecho"},
            
            # ========== ITEMS SITUACIONALES ==========
            "banda focus": {"precio": 60, "tipo": "combate_situacional", "efecto": "focus_sash", "sobrevive_1hp": True, "consumible": True, "desc": "Sobrevive 1 golpe con 1 HP"},
            "cinta focus": {"precio": 55, "tipo": "combate_situacional", "efecto": "focus_band", "sobrevive_prob": 0.1, "desc": "10% sobrevivir con 1 HP"},
            "seguro debilidad": {"precio": 70, "tipo": "combate_situacional", "efecto": "weakness_policy", "boost_stats": 2, "consumible": True, "desc": "+2 Atq/At.Esp al recibir súper efectivo"},
            "botón escape": {"precio": 50, "tipo": "combate_situacional", "efecto": "eject_button", "fuerza_cambio": True, "consumible": True, "desc": "Fuerza cambio al ser golpeado"},
            "tarjeta roja": {"precio": 50, "tipo": "combate_situacional", "efecto": "red_card", "fuerza_cambio_rival": True, "consumible": True, "desc": "Expulsa al rival al contacto"},
            "mochila escape": {"precio": 50, "tipo": "combate_situacional", "efecto": "eject_pack", "auto_cambio": True, "consumible": True, "desc": "Cambio automático si bajan stats"},
            "globo": {"precio": 45, "tipo": "combate_situacional", "efecto": "air_balloon", "levita_temporal": True, "consumible": True, "desc": "Inmune Tierra hasta recibir golpe"},
            "bulbo absorbente": {"precio": 40, "tipo": "combate_situacional", "efecto": "absorb_bulb", "boost_stat": "atq_sp", "activador": "Agua", "consumible": True, "desc": "+1 At.Esp al recibir Agua"},
            "batería celular": {"precio": 40, "tipo": "combate_situacional", "efecto": "cell_battery", "boost_stat": "atq", "activador": "Eléctrico", "consumible": True, "desc": "+1 Ataque al recibir Eléctrico"},
            "luminorbe": {"precio": 40, "tipo": "combate_situacional", "efecto": "luminous_moss", "boost_stat": "def_sp", "activador": "Agua", "consumible": True, "desc": "+1 Def.Esp al recibir Agua"},
            "bola nieve": {"precio": 40, "tipo": "combate_situacional", "efecto": "snowball", "boost_stat": "atq", "activador": "Hielo", "consumible": True, "desc": "+1 Ataque al recibir Hielo"},
            
            # ========== ITEMS DE UTILIDAD ==========
            "lente amplia": {"precio": 50, "tipo": "combate_utilidad", "efecto": "wide_lens", "boost_precision": 1.1, "desc": "+10% precisión"},
            "garra rápida": {"precio": 55, "tipo": "combate_utilidad", "efecto": "quick_claw", "prob_primero": 0.2, "desc": "20% ir primero"},
            "cola retardada": {"precio": 40, "tipo": "combate_utilidad", "efecto": "lagging_tail", "siempre_ultimo": True, "desc": "Siempre va último"},
            "nudo destino": {"precio": 100, "tipo": "crianza", "efecto": "destiny_knot", "herencia_5_ivs": True, "desc": "Hereda 5 IVs en cría"},
            "piedra eterna": {"precio": 50, "tipo": "crianza", "efecto": "everstone", "herencia_naturaleza": True, "desc": "Hereda naturaleza en cría"},
            "amuleto oval": {"precio": 80, "tipo": "combate_utilidad", "efecto": "lucky_egg", "exp_boost": 1.5, "desc": "+50% EXP"},
            "moneda amuleto": {"precio": 90, "tipo": "combate_utilidad", "efecto": "amulet_coin", "dinero_boost": 2.0, "desc": "x2 dinero en batalla"},
            "repartidor_exp": {"precio": 150,"tipo": "utilidad","equipable": True,"desc": "Reparte la EXP ganada en batalla entre todo el equipo por igual.",},
            
            # ========== CHOICE ITEMS ==========
            "banda elección": {"precio": 80, "tipo": "combate_choice", "efecto": "choice_band", "boost": 1.5, "stat": "atq", "bloquea": True, "desc": "x1.5 Ataque, bloquea movimiento"},
            "gafas elección": {"precio": 80, "tipo": "combate_choice", "efecto": "choice_specs", "boost": 1.5, "stat": "atq_sp", "bloquea": True, "desc": "x1.5 At.Esp, bloquea movimiento"},
            "pañuelo elección": {"precio": 80, "tipo": "combate_choice", "efecto": "choice_scarf", "boost": 1.5, "stat": "vel", "bloquea": True, "desc": "x1.5 Velocidad, bloquea movimiento"},
            
            # ========== CHALECO ASALTO ==========
            "chaleco asalto": {"precio": 70, "tipo": "combate_defensivo", "efecto": "assault_vest", "boost": 1.5, "stat": "def_sp", "bloquea_estado": True, "desc": "+50% Def.Esp, bloquea movimientos estado"},
            
            # ========== BAYAS COMBATE ==========
            "baya zanama": {"precio": 10, "tipo": "baya_combate", "efecto": "sitrus_berry", "cura_hp": 0.25, "consumible": True, "desc": "Restaura 25% HP al bajar de 50%"},
            "baya ligaya": {"precio": 8, "tipo": "baya_combate", "efecto": "oran_berry", "cura_hp": 10, "consumible": True, "desc": "Restaura 10 HP"},
            "baya latano": {"precio": 12, "tipo": "baya_combate", "efecto": "liechi_berry", "boost_stat": "atq", "activacion_hp": 0.25, "consumible": True, "desc": "+1 Ataque al bajar de 25% HP"},
            "baya gonlan": {"precio": 12, "tipo": "baya_combate", "efecto": "ganlon_berry", "boost_stat": "def", "activacion_hp": 0.25, "consumible": True, "desc": "+1 Defensa al bajar de 25% HP"},
            "baya yapati": {"precio": 12, "tipo": "baya_combate", "efecto": "salac_berry", "boost_stat": "vel", "activacion_hp": 0.25, "consumible": True, "desc": "+1 Velocidad al bajar de 25% HP"},
            "baya actania": {"precio": 12, "tipo": "baya_combate", "efecto": "petaya_berry", "boost_stat": "atq_sp", "activacion_hp": 0.25, "consumible": True, "desc": "+1 At.Esp al bajar de 25% HP"},
            "baya algama": {"precio": 12, "tipo": "baya_combate", "efecto": "apicot_berry", "boost_stat": "def_sp", "activacion_hp": 0.25, "consumible": True, "desc": "+1 Def.Esp al bajar de 25% HP"},
            
            # ========== BAYAS MITIGACIÓN ==========
            "baya aricoc": {"precio": 8, "tipo": "baya_mitigacion", "efecto": "chople_berry", "reduce_tipo": "Lucha", "reduce": 0.5, "consumible": True, "desc": "Reduce Lucha x0.5"},
            "baya kebia": {"precio": 8, "tipo": "baya_mitigacion", "efecto": "kebia_berry", "reduce_tipo": "Veneno", "reduce": 0.5, "consumible": True, "desc": "Reduce Veneno x0.5"},
            "baya magua": {"precio": 8, "tipo": "baya_mitigacion", "efecto": "wacan_berry", "reduce_tipo": "Eléctrico", "reduce": 0.5, "consumible": True, "desc": "Reduce Eléctrico x0.5"},
            "baya payapa": {"precio": 8, "tipo": "baya_mitigacion", "efecto": "payapa_berry", "reduce_tipo": "Psíquico", "reduce": 0.5, "consumible": True, "desc": "Reduce Psíquico x0.5"},
            "baya yecana": {"precio": 8, "tipo": "baya_mitigacion", "efecto": "yache_berry", "reduce_tipo": "Hielo", "reduce": 0.5, "consumible": True, "desc": "Reduce Hielo x0.5"},
            "baya yatay": {"precio": 8, "tipo": "baya_mitigacion", "efecto": "occa_berry", "reduce_tipo": "Fuego", "reduce": 0.5, "consumible": True, "desc": "Reduce Fuego x0.5"},
            "baya charti": {"precio": 8, "tipo": "baya_mitigacion", "efecto": "charti_berry", "reduce_tipo": "Roca", "reduce": 0.5, "consumible": True, "desc": "Reduce Roca x0.5"},
            "baya anjiro": {"precio": 8, "tipo": "baya_mitigacion", "efecto": "passho_berry", "reduce_tipo": "Agua", "reduce": 0.5, "consumible": True, "desc": "Reduce Agua x0.5"},
        }
    
    def _cargar_categorias(self) -> Dict:
        """Categorías para organizar tienda"""
        return {
            "pokeballs": {
                "nombre": "🎾 Pokéballs",
                "items": ["pokeball", "superball", "ultraball", "quickball", "timerball", "repeatball", "netball", "duskball", "diveball", "nestball"],
                "orden": 1
            },
            "medicinas": {
                "nombre": "💊 Medicinas",
                "items": ["pocion", "superpocion", "hiperpocion", "pocion maxima", "restaurar todo"],
                "orden": 2
            },
            "revivir": {
                "nombre": "💚 Revivir",
                "items": ["revivir", "revivir max"],
                "orden": 3
            },
            "estados": {
                "nombre": "🩹 Curar Estados",
                "items": ["antidoto", "despertar", "antiquemar", "antiparalizar", "antihielo", "cura total"],
                "orden": 4
            },
            "pp": {
                "nombre": "💧 PP",
                "items": ["eter", "eter max", "elixir", "elixir max"],
                "orden": 5
            },
            "vitaminas": {
                "nombre": "💪 Vitaminas",
                "items": ["mas ps", "proteina", "hierro", "calcio", "zinc", "carburante"],
                "orden": 6
            },
            "evolutivos": {
                "nombre": "💎 Evolutivos",
                "items": ["piedra fuego", "piedra agua", "piedra trueno", "piedra hoja", "piedra lunar", "piedra solar", "piedra alba", "piedra noche"],
                "orden": 7
            },
            "poder": {
                "nombre": "⚔️ Items de Poder",
                "items": ["vidasfera", "banda experto", "gafas sabias", "banda muscular", "metrónomo", "lente zoom"],
                "orden": 8
            },
            "defensivos": {
                "nombre": "🛡️ Items Defensivos",
                "items": ["restos", "lodo negro", "casco dentado", "púas venenosas", "bola férrea", "campana concha"],
                "orden": 9
            },
            "situacionales": {
                "nombre": "💥 Situacionales",
                "items": ["banda focus", "cinta focus", "seguro debilidad", "botón escape", "tarjeta roja", "mochila escape", "globo", "bulbo absorbente", "batería celular", "luminorbe", "bola nieve"],
                "orden": 10
            },
            "utilidad": {
                "nombre": "🔧 Utilidad",
                "items": ["lente amplia", "garra rápida", "cola retardada", "amuleto oval", "moneda amuleto"],
                "orden": 11
            },
            "choice": {
                "nombre": "🎯 Choice Items",
                "items": ["banda elección", "gafas elección", "pañuelo elección", "chaleco asalto"],
                "orden": 12
            },
            "bayas_combate": {
                "nombre": "🍓 Bayas de Combate",
                "items": ["baya zanama", "baya ligaya", "baya latano", "baya gonlan", "baya yapati", "baya actania", "baya algama"],
                "orden": 13
            },
            "bayas_mitigacion": {
                "nombre": "🍇 Bayas de Mitigación",
                "items": ["baya aricoc", "baya kebia", "baya magua", "baya payapa", "baya yecana", "baya yatay", "baya charti", "baya anjiro"],
                "orden": 14
            },
            "crianza": {
                "nombre": "🥚 Crianza",
                "items": ["nudo destino", "piedra eterna"],
                "orden": 15
            },
            "clima_terreno": {
                "nombre": "🌦️ Clima y Terreno",
                "items": ["heatrock", "damprock", "smoothrock", "icyrock"],
                "orden": 16
            }



        }
    
    def obtener_item(self, nombre: str) -> Optional[Dict]:
        """
        Obtiene datos de un item.
        Busca primero en el items_db propio; si no lo encuentra,
        hace fallback a ITEMS_COMPLETOS_DB (la base de datos completa).
        """
        nombre_lower = nombre.lower()
        result = self.items_db.get(nombre_lower)
        if result is not None:
            return result
        from pokemon.items_database_complete import ITEMS_COMPLETOS_DB
        return ITEMS_COMPLETOS_DB.get(nombre_lower)
    
    def obtener_precio(self, nombre: str) -> int:
        """Obtiene precio de un item"""
        item = self.obtener_item(nombre)
        return item["precio"] if item else 0
    
    def es_vendible(self, nombre: str) -> bool:
        """Verifica si se puede comprar en tienda"""
        precio = self.obtener_precio(nombre)
        return 0 < precio < 999999
    
    def obtener_items_categoria(self, categoria: str) -> List[str]:
        """Obtiene items de una categoría"""
        if categoria == "mts":
            return [k for k, v in self.items_db.items()
                    if v.get("tipo") == "mt"]
        cat_data = self.categorias.get(categoria, {})
        return cat_data.get("items", [])
    
    def obtener_inventario(self, user_id: int) -> Dict[str, int]:
        """
        Obtiene inventario del usuario
        
        Returns:
            {item_nombre: cantidad}
        """
        try:
            query = """
                SELECT item_nombre, cantidad 
                FROM INVENTARIO_USUARIO 
                WHERE userID = ? AND cantidad > 0
            """
            results = self.db.execute_query(query, (user_id,))
            
            return {row['item_nombre']: row['cantidad'] for row in results}
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo inventario: {e}")
            return {}
    
    def agregar_item(self, user_id: int, item_nombre: str, cantidad: int = 1) -> Tuple[bool, str]:
        """Agrega item al inventario"""
        if item_nombre not in self.items_db:
            return False, f"❌ Item '{item_nombre}' no existe"
        
        try:
            # Verificar si ya tiene el item
            query = """
                SELECT cantidad FROM INVENTARIO_USUARIO 
                WHERE userID = ? AND item_nombre = ?
            """
            result = self.db.execute_query(query, (user_id, item_nombre))
            
            if result:
                # Actualizar cantidad
                nueva_cantidad = result[0]['cantidad'] + cantidad
                update_query = """
                    UPDATE INVENTARIO_USUARIO 
                    SET cantidad = ? 
                    WHERE userID = ? AND item_nombre = ?
                """
                self.db.execute_update(update_query, (nueva_cantidad, user_id, item_nombre))
            else:
                # Insertar nuevo
                insert_query = """
                    INSERT INTO INVENTARIO_USUARIO (userID, item_nombre, cantidad)
                    VALUES (?, ?, ?)
                """
                self.db.execute_update(insert_query, (user_id, item_nombre, cantidad))
            
            logger.info(f"✅ {cantidad}x {item_nombre} agregado a inventario de {user_id}")
            return True, f"✅ +{cantidad}x {item_nombre}"
            
        except Exception as e:
            logger.error(f"❌ Error agregando item: {e}")
            return False, f"❌ Error: {str(e)}"
    
    def usar_item(self, user_id: int, item_nombre: str, cantidad: int = 1) -> Tuple[bool, str]:
        """Consume item del inventario"""
        try:
            query = """
                SELECT cantidad FROM INVENTARIO_USUARIO 
                WHERE userID = ? AND item_nombre = ?
            """
            result = self.db.execute_query(query, (user_id, item_nombre))
            
            if not result or result[0]['cantidad'] < cantidad:
                return False, f"❌ No tienes suficiente {item_nombre}"
            
            nueva_cantidad = result[0]['cantidad'] - cantidad
            
            if nueva_cantidad > 0:
                update_query = """
                    UPDATE INVENTARIO_USUARIO 
                    SET cantidad = ? 
                    WHERE userID = ? AND item_nombre = ?
                """
                self.db.execute_update(update_query, (nueva_cantidad, user_id, item_nombre))
            else:
                delete_query = """
                    DELETE FROM INVENTARIO_USUARIO 
                    WHERE userID = ? AND item_nombre = ?
                """
                self.db.execute_update(delete_query, (user_id, item_nombre))
            
            logger.info(f"💊 {cantidad}x {item_nombre} usado por {user_id}")
            return True, f"✅ Usaste {cantidad}x {item_nombre}"
            
        except Exception as e:
            logger.error(f"❌ Error usando item: {e}")
            return False, f"❌ Error: {str(e)}"
    
    def comprar_item(self, user_id: int, item_nombre: str, cantidad: int = 1) -> Tuple[bool, str]:
        """Compra item de la tienda"""
        item_data = self.obtener_item(item_nombre)
        
        if not item_data:
            return False, "❌ Item no existe"
        
        if not self.es_vendible(item_nombre):
            return False, "❌ Este item no está a la venta"
        
        precio_total = item_data["precio"] * cantidad
        
        # Verificar saldo
        from funciones import economy_service
        balance = economy_service.get_balance(user_id)
        
        if balance < precio_total:
            return False, f"❌ Saldo insuficiente. Necesitas {precio_total} Cosmos"
        
        # Realizar compra
        exito = economy_service.subtract_credits(user_id, precio_total, f"Compra {cantidad}x {item_nombre}")
        
        if not exito:
            return False, "❌ Error procesando pago"
        
        # Agregar al inventario
        self.agregar_item(user_id, item_nombre, cantidad)
        
        logger.info(f"🛒 Usuario {user_id} compró {cantidad}x {item_nombre} por {precio_total} Cosmos")
        
        return True, f"✅ Comprado {cantidad}x {item_nombre} por {precio_total} Cosmos"
    
    def aplicar_item_batalla(self, item_nombre: str, pokemon_id: int) -> dict:
        """
        Aplica efecto de item en batalla.
        Trabaja con el objeto Pokemon (dataclass), accediendo por atributos.
        """
        item_data = self.obtener_item(item_nombre)
        if not item_data:
            return {'exito': False, 'mensaje': 'Item no existe'}

        from pokemon.services import pokemon_service
        pokemon = pokemon_service.obtener_pokemon(pokemon_id)

        if not pokemon:
            return {'exito': False, 'mensaje': 'Pokémon no encontrado'}

        resultado = {'exito': True, 'mensaje': '', 'efectos': []}

        # ── Curar HP ──────────────────────────────────────────────────────
        if 'cura_hp' in item_data:
            hp_max    = pokemon.stats.get('hp', 100)  # ✅ atributo, no key
            hp_actual = pokemon.hp_actual              # ✅ atributo, no key

            if hp_actual >= hp_max:
                return {'exito': False, 'mensaje': f'{pokemon.nombre} ya tiene HP completo.'}

            hp_curado = min(item_data['cura_hp'], hp_max - hp_actual)
            nuevo_hp  = hp_actual + hp_curado

            from database import db_manager
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                (nuevo_hp, pokemon_id)
            )
            resultado['efectos'].append(f"Restauró {hp_curado} HP")

        # ── Revivir ───────────────────────────────────────────────────────
        if 'revive' in item_data:
            if pokemon.hp_actual > 0:
                return {'exito': False, 'mensaje': f'{pokemon.nombre} no está debilitado.'}
            hp_max   = pokemon.stats.get('hp', 100)
            nuevo_hp = int(hp_max * item_data['revive'])
            from database import db_manager
            db_manager.execute_update(
                "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                (nuevo_hp, pokemon_id)
            )
            resultado['efectos'].append(f"Revivió con {nuevo_hp} HP")
            resultado['exito'] = True

        # ── Curar estado ──────────────────────────────────────────────────
        if 'cura_estado' in item_data:
            resultado['efectos'].append(f"Curó {item_data['cura_estado']}")

        if 'cura_todos_estados' in item_data:
            resultado['efectos'].append("Curó todos los estados")

        # ── PP ────────────────────────────────────────────────────────────
        if 'pp' in item_data:
            resultado['efectos'].append(f"Restauró {item_data['pp']} PP a un movimiento")

        if 'pp_todos' in item_data:
            resultado['efectos'].append(f"Restauró PP a todos los movimientos")

        if not resultado['efectos']:
            return {'exito': False, 'mensaje': 'Este item no tiene efecto en batalla.'}

        resultado['mensaje'] = ', '.join(resultado['efectos'])
        return resultado


# Instancia global
items_service = ItemsService()
