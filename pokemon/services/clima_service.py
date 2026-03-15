"""
Servicio de Clima y Terrenos
Gestiona efectos climáticos y de terreno en batalla
"""

import logging
from typing import Optional, Dict
from enum import Enum

logger = logging.getLogger(__name__)


class Clima(Enum):
    """Tipos de clima"""
    NINGUNO = "ninguno"
    SOL = "sol"
    LLUVIA = "lluvia"
    TORMENTA_ARENA = "tormenta_arena"
    GRANIZO = "granizo"


class Terreno(Enum):
    """Tipos de terreno"""
    NINGUNO = "ninguno"
    ELECTRICO = "electrico"
    PSIQUICO = "psiquico"
    HIERBA = "hierba"
    HADA = "hada"


class ClimaService:
    """Servicio para gestionar clima y terrenos"""
    
    def __init__(self):
        self.climas = self._cargar_climas()
        self.terrenos = self._cargar_terrenos()
    
    def _cargar_climas(self) -> Dict:
        """Base de datos de climas"""
        return {
            "SOL": {
                "nombre": "☀️ Sol Intenso",
                "turnos_default": 5,
                "efectos": {
                    "boost_tipo": "Fuego",
                    "nerf_tipo": "Agua",
                    "multiplicador": 1.5,
                    "reduce_tipo": 0.5
                },
                "efectos_especiales": {
                    "rayo_solar_instantaneo": True,
                    "sintesis_mejora": True,
                    "trueno_precision": 50
                },
                "descripcion": "Potencia Fuego x1.5, reduce Agua x0.5"
            },
            "LLUVIA": {
                "nombre": "🌧️ Lluvia",
                "turnos_default": 5,
                "efectos": {
                    "boost_tipo": "Agua",
                    "nerf_tipo": "Fuego",
                    "multiplicador": 1.5,
                    "reduce_tipo": 0.5
                },
                "efectos_especiales": {
                    "trueno_precision": 100,
                    "huracán_precision": 100,
                    "rayo_solar_debil": True
                },
                "descripcion": "Potencia Agua x1.5, reduce Fuego x0.5"
            },
            "TORMENTA_ARENA": {
                "nombre": "🌪️ Tormenta de Arena",
                "turnos_default": 5,
                "efectos": {
                    "daño_residual": 0.0625,  # 1/16 HP por turno
                    "inmunes": ["Roca", "Tierra", "Acero"],
                    "boost_def_sp_roca": 1.5
                },
                "efectos_especiales": {
                    "def_sp_roca_boost": True
                },
                "descripcion": "Daña 1/16 HP por turno (excepto Roca/Tierra/Acero), Roca +50% Def.Esp"
            },
            "GRANIZO": {
                "nombre": "🧊 Granizo",
                "turnos_default": 5,
                "efectos": {
                    "daño_residual": 0.0625,  # 1/16 HP por turno
                    "inmunes": ["Hielo"],
                },
                "efectos_especiales": {
                    "ventisca_precision": 100,
                    "aurora_velo": True
                },
                "descripcion": "Daña 1/16 HP por turno (excepto Hielo), Ventisca nunca falla"
            }
        }
    
    def _cargar_terrenos(self) -> Dict:
        """Base de datos de terrenos"""
        return {
            "ELECTRICO": {
                "nombre": "⚡ Campo Eléctrico",
                "turnos_default": 5,
                "efectos": {
                    "boost_tipo": "Electrico",
                    "multiplicador": 1.3,
                    "inmunidad_estado": "dormido"
                },
                "efectos_especiales": {
                    "inmune_sleep": True,
                    "naturaleza_potencia": True
                },
                "descripcion": "Potencia Eléctrico x1.3, inmune a Dormir"
            },
            "PSIQUICO": {
                "nombre": "🔮 Campo Psíquico",
                "turnos_default": 5,
                "efectos": {
                    "boost_tipo": "Psiquico",
                    "multiplicador": 1.3,
                    "bloquea_prioridad": True
                },
                "efectos_especiales": {
                    "no_priority": True,
                    "expanded_mind": True
                },
                "descripcion": "Potencia Psíquico x1.3, bloquea movimientos de prioridad"
            },
            "HIERBA": {
                "nombre": "🌿 Campo de Hierba",
                "turnos_default": 5,
                "efectos": {
                    "boost_tipo": "Planta",
                    "multiplicador": 1.3,
                    "recuperacion": 0.0625  # 1/16 HP por turno
                },
                "efectos_especiales": {
                    "curar_1_16": True,
                    "terremotos_debiles": 0.5
                },
                "descripcion": "Potencia Planta x1.3, recupera 1/16 HP por turno"
            },
            "HADA": {
                "nombre": "🧚 Campo de Niebla",
                "turnos_default": 5,
                "efectos": {
                    "boost_tipo": "Hada",
                    "multiplicador": 1.3,
                    "reduce_dragon": 0.5
                },
                "efectos_especiales": {
                    "inmune_estados": True,
                    "dragon_nerf": True
                },
                "descripcion": "Potencia Hada x1.3, reduce Dragón x0.5"
            }
        }
    
    def aplicar_boost_clima(self, clima: str, tipo_movimiento: str) -> float:
        """
        Aplica multiplicador de clima a un movimiento
        
        Returns:
            Multiplicador (1.5, 0.5, o 1.0)
        """
        clima_data = self.climas.get(clima)
        
        if not clima_data:
            return 1.0
        
        efectos = clima_data["efectos"]
        
        # Boost
        if "boost_tipo" in efectos and tipo_movimiento == efectos["boost_tipo"]:
            return efectos["multiplicador"]
        
        # Nerf
        if "nerf_tipo" in efectos and tipo_movimiento == efectos["nerf_tipo"]:
            return efectos["reduce_tipo"]
        
        return 1.0
    
    def aplicar_boost_terreno(self, terreno: str, tipo_movimiento: str, en_suelo: bool = True) -> float:
        """
        Aplica multiplicador de terreno a un movimiento
        Solo afecta si el Pokémon está en el suelo
        
        Returns:
            Multiplicador (1.3 o 1.0)
        """
        if not en_suelo:
            return 1.0
        
        terreno_data = self.terrenos.get(terreno)
        
        if not terreno_data:
            return 1.0
        
        efectos = terreno_data["efectos"]
        
        if "boost_tipo" in efectos and tipo_movimiento == efectos["boost_tipo"]:
            return efectos["multiplicador"]
        
        # Campo de Niebla reduce Dragón
        if terreno == "HADA" and tipo_movimiento == "Dragon":
            return efectos.get("reduce_dragon", 1.0)
        
        return 1.0
    
    def calcular_daño_residual_clima(self, clima: str, pokemon_tipos: list, hp_max: int) -> int:
        """
        Calcula daño residual por clima
        
        Returns:
            Daño a aplicar (0 si es inmune)
        """
        clima_data = self.climas.get(clima)
        
        if not clima_data or "daño_residual" not in clima_data["efectos"]:
            return 0
        
        # Verificar inmunidad
        inmunes = clima_data["efectos"].get("inmunes", [])
        for tipo in pokemon_tipos:
            if tipo in inmunes:
                return 0
        
        daño = int(hp_max * clima_data["efectos"]["daño_residual"])
        return max(1, daño)
    
    def calcular_curacion_terreno(self, terreno: str, hp_max: int, en_suelo: bool = True) -> int:
        """
        Calcula curación por terreno (Campo de Hierba)
        
        Returns:
            HP a restaurar
        """
        if not en_suelo or terreno != "HIERBA":
            return 0
        
        terreno_data = self.terrenos.get(terreno)
        
        if not terreno_data:
            return 0
        
        recuperacion = terreno_data["efectos"].get("recuperacion", 0)
        curacion = int(hp_max * recuperacion)
        
        return max(1, curacion)
    
    def verificar_inmunidad_estado(self, terreno: str, estado: str, en_suelo: bool = True) -> bool:
        """
        Verifica si un terreno da inmunidad a un estado
        
        Returns:
            True si es inmune
        """
        if not en_suelo:
            return False
        
        terreno_data = self.terrenos.get(terreno)
        
        if not terreno_data:
            return False
        
        # Campo Eléctrico: inmune a Dormir
        if terreno == "ELECTRICO" and estado == "dormido":
            return True
        
        # Campo de Niebla: inmune a estados de campo
        if terreno == "HADA":
            return terreno_data["efectos"].get("inmune_estados", False)
        
        return False
    
    def bloquea_prioridad(self, terreno: str, en_suelo: bool = True) -> bool:
        """
        Verifica si Campo Psíquico bloquea movimientos de prioridad

        Returns:
            True si bloquea
        """
        if not en_suelo or terreno != "PSIQUICO":
            return False

        terreno_data = self.terrenos.get(terreno)

        if not terreno_data:
            return False

        return terreno_data["efectos"].get("bloquea_prioridad", False)
    
    def obtener_info_clima(self, clima: str) -> Optional[Dict]:
        """Obtiene información completa de un clima"""
        return self.climas.get(clima)
    
    def obtener_info_terreno(self, terreno: str) -> Optional[Dict]:
        """Obtiene información completa de un terreno"""
        return self.terrenos.get(terreno)


# Instancia global
clima_service = ClimaService()
