# -*- coding: utf-8 -*-
"""
pokemon/services/habilidades_service.py
═══════════════════════════════════════════════════════════════════════════════
Servicio central de habilidades Pokémon — Generaciones 1-9.

Responsabilidades:
  • Traducciones inglés → español de TODAS las habilidades (Gen 1-9).
  • Efectos en combate de cada habilidad (boost, inmunidad, entrada, contacto…).
  • seleccionar_habilidad(lista)  → selección con pesos 85 % normal / 15 % oculta.

Quién lo usa:
  • pokemon_service.crear_pokemon()     → habilidades_service.seleccionar_habilidad()
  • crianza_service._determinar_habilidad() → ídem
  • battle_engine / wild_battle_system   → aplicar_boost_daño, verificar_inmunidad…

La LISTA de habilidades por especie viene del pokedex.json vía pokedex_service.
Este módulo NO repite esa lista; solo gestiona efectos y selección.
═══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import random
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# PESOS DE SELECCIÓN (mecánica oficial Gen 5+)
# ─────────────────────────────────────────────────────────────────────────────
_PESO_NORMAL: int = 85   # cada habilidad no-oculta
_PESO_OCULTA: int = 15   # siempre la ÚLTIMA de la lista del JSON


class HabilidadesService:
    """Servicio completo de habilidades Pokémon Gen 1-9."""

    def __init__(self) -> None:
        self.traducciones: Dict[str, str] = self._cargar_traducciones()
        self.habilidades:  Dict[str, Dict] = self._cargar_habilidades()

    # ══════════════════════════════════════════════════════════════════════════
    # API PÚBLICA
    # ══════════════════════════════════════════════════════════════════════════

    def seleccionar_habilidad(self, habilidades: List[str]) -> str:
        """
        Selecciona una habilidad de la lista con pesos canónicos Gen 5+.

        Convención del pokedex.json:
          • 1 entrada  → 100 % esa habilidad
          • 2 entradas → 85 % primera (normal), 15 % segunda (oculta)
          • 3 entradas → 42.5 % / 42.5 % / 15 % (última = oculta)

        Args:
            habilidades: Lista procedente de pokedex_service.obtener_habilidades()

        Returns:
            Nombre de la habilidad en inglés (clave del JSON), p.ej. "blaze".
        """
        if not habilidades:
            return "overgrow"   # fallback inocuo; no debería llegar aquí
        if len(habilidades) == 1:
            return habilidades[0]

        pesos = [_PESO_NORMAL] * (len(habilidades) - 1) + [_PESO_OCULTA]
        return random.choices(habilidades, weights=pesos, k=1)[0]

    def traducir(self, habilidad_en: str) -> str:
        """Devuelve el nombre en español. Si no hay traducción, retorna el original."""
        clave = habilidad_en.lower().replace("-", " ").replace("_", " ")
        return self.traducciones.get(clave, habilidad_en.replace("-", " ").title())

    def obtener_habilidad(self, nombre: str) -> Optional[Dict]:
        """
        Busca los datos de efecto de una habilidad por nombre en español o inglés.
        Devuelve None si no está registrada (sin efectos en batalla implementados).
        """
        # Buscar directo por nombre en español
        if nombre in self.habilidades:
            return self.habilidades[nombre]
        # Intentar traducir desde inglés y buscar de nuevo
        nombre_es = self.traducir(nombre)
        return self.habilidades.get(nombre_es)

    # ─── Wrappers de combate (sin cambios de firma respecto a la versión anterior) ───

    def aplicar_boost_daño(
        self,
        habilidad:        str,
        movimiento_tipo:  str,
        poder_movimiento: int,
        hp_actual:        int,
        hp_max:           int,
        es_contacto:      bool = False,
    ) -> float:
        """Multiplicador de daño por habilidad. 1.0 = sin efecto."""
        hab = self.obtener_habilidad(habilidad)
        if not hab:
            return 1.0

        tipo_hab = hab.get("tipo", "")

        if tipo_hab == "boost_hp_bajo":
            if hp_max and (hp_actual / hp_max) <= hab.get("condicion_hp", 0.33):
                if movimiento_tipo == hab.get("boost_tipo"):
                    return hab.get("multiplicador", 1.0)

        elif tipo_hab == "boost_potencia":
            if poder_movimiento <= hab.get("potencia_max", 60):
                return hab.get("multiplicador", 1.0)

        elif tipo_hab == "boost_contacto":
            if es_contacto:
                return hab.get("multiplicador", 1.0)

        elif tipo_hab in ("boost_stab", "boost_sheer_force",
                          "boost_hustle", "boost_categoria"):
            return 1.0   # manejado en los motores específicos

        return 1.0

    def aplicar_efecto_entrada(self, habilidad: str) -> Optional[Dict]:
        """Efectos al entrar en batalla (Intimidación, climas, terrenos…)."""
        hab = self.obtener_habilidad(habilidad)
        if not hab or hab.get("tipo") != "entrada":
            return None
        return {"tipo": hab["efecto"], "data": hab}

    def verificar_inmunidad(
        self, habilidad: str, tipo_ataque: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Comprueba si la habilidad otorga inmunidad al tipo dado.
        Devuelve (es_inmune, efecto_extra).  efecto_extra: 'cura' | 'boost' | None.
        """
        hab = self.obtener_habilidad(habilidad)
        if not hab:
            return False, None

        tipo_hab = hab.get("tipo", "")
        if tipo_hab in ("inmunidad", "inmunidad_cura",
                        "inmunidad_boost", "inmunidad_boost_stat"):
            if tipo_ataque in hab.get("inmune_a", []):
                extra = None
                if tipo_hab == "inmunidad_cura":        extra = "cura"
                elif "boost" in tipo_hab:               extra = "boost"
                return True, extra

        if tipo_hab == "resistencia":
            if tipo_ataque in hab.get("reduce_tipo", []):
                return False, "reduce"

        return False, None

    def aplicar_efecto_contacto(self, habilidad: str) -> Optional[Dict]:
        """Efecto al ser golpeado por un ataque de contacto físico."""
        hab = self.obtener_habilidad(habilidad)
        if not hab:
            return None

        tipo_hab = hab.get("tipo", "")
        if tipo_hab == "contacto":
            if random.random() < hab.get("probabilidad", 0):
                return {"efecto": hab["efecto"], "descripcion": hab["descripcion"]}

        elif tipo_hab == "contacto_multiple":
            if random.random() < hab.get("probabilidad", 0):
                return {
                    "efecto": random.choice(hab["efectos"]),
                    "descripcion": hab["descripcion"],
                }

        elif tipo_hab == "contacto_daño":
            return {"daño": hab["daño"], "descripcion": hab["descripcion"]}

        return None

    # ══════════════════════════════════════════════════════════════════════════
    # DATOS INTERNOS — TRADUCCIONES
    # ══════════════════════════════════════════════════════════════════════════

    def _cargar_traducciones(self) -> Dict[str, str]:
        """
        Mapa completo inglés (clave normalizada) → español, Gen 1-9.
        Clave: lowercase, guiones y underscores convertidos a espacios.
        """
        return {
            # ── Gen 1 ─────────────────────────────────────────────────────────
            "overgrow":              "Espesura",
            "blaze":                 "Mar Llamas",
            "torrent":               "Torrente",
            "swarm":                 "Enjambre",
            "shield dust":           "Polvo Escudo",
            "run away":              "Fuga",
            "shed skin":             "Mudar",
            "compound eyes":         "Ojo Compuesto",
            "tinted lens":           "Lente Tintada",
            "keen eye":              "Vista Lince",
            "tangled feet":          "Pies Torpes",
            "big pecks":             "Pecho Robusto",
            "guts":                  "Agallas",
            "hustle":                "Entusiasmo",
            "intimidate":            "Intimidación",
            "sand veil":             "Velo Arena",
            "sand rush":             "Ímpetu Arena",
            "poison point":          "Punto Tóxico",
            "rivalry":               "Competitividad",
            "cute charm":            "Encanto",
            "magic guard":           "Guardia Mágica",
            "friend guard":          "Guardia Amiga",
            "unaware":               "Ignorancia",
            "flash fire":            "Absorbe Fuego",
            "drought":               "Sequía",
            "chlorophyll":           "Clorofila",
            "leaf guard":            "Hoja Escudo",
            "effect spore":          "Efecto Espora",
            "dry skin":              "Piel Seca",
            "damp":                  "Humedad",
            "arena trap":            "Trampa Arena",
            "sand force":            "Fuerza Arena",
            "pickup":                "Recoger",
            "technician":            "Experto",
            "unnerve":               "Nerviosismo",
            "limber":                "Flexibilidad",
            "water absorb":          "Absorbe Agua",
            "cloud nine":            "Cabeza Hueca",
            "swift swim":            "Nado Rápido",
            "vital spirit":          "Espíritu Vital",
            "anger point":           "Ira",
            "defiant":               "Competidor",
            "flash fire":            "Absorbe Fuego",
            "inner focus":           "Concentración",
            "static":                "Electricidad Estática",
            "lightning rod":         "Pararrayos",
            "volt absorb":           "Absorbe Electricidad",
            "flame body":            "Cuerpo Llama",
            "synchronize":           "Sincronía",
            "trace":                 "Rastreo",
            "download":              "Descarga",
            "analytic":              "Análisis",
            "natural cure":          "Cura Natural",
            "serene grace":          "Dicha",
            "healer":                "Sanador",
            "super luck":            "Supersuerte",
            "pressure":              "Presión",
            "thick fat":             "Sebo",
            "scrappy":               "Aguerrido",
            "own tempo":             "Ritmo Propio",
            "regenerator":           "Regeneración",
            "oblivious":             "Simpleza",
            "magnet pull":           "Imán",
            "sturdy":                "Robustez",
            "forewarn":              "Alerta",
            "early bird":            "Madrugar",
            "insomnia":              "Insomnio",
            "levitate":              "Levitación",
            "rough skin":            "Piel Tosca",
            "rock head":             "Cabeza Roca",
            "illuminate":            "Iluminación",
            "sniper":                "Francotirador",
            "hustle":                "Entusiasmo",
            "adaptability":          "Adaptabilidad",
            "skill link":            "Encadenado",
            "iron fist":             "Puño Férreo",
            "sheer force":           "Potencia Bruta",
            "moxie":                 "Autoestima",
            "drizzle":               "Llovizna",
            "sand stream":           "Chorro Arena",
            "snow warning":          "Nevada",
            "air lock":              "Cierre Aéreo",
            "cloud nine":            "Cabeza Hueca",
            "wonder guard":          "Superguarda",
            "shadow tag":            "Sombra Trampa",
            "arena trap":            "Trampa Arena",
            "magma armor":           "Coraza Magma",
            "water veil":            "Velo Agua",
            "oblivious":             "Simpleza",
            "soundproof":            "Insonorización",
            "minus":                 "Menos",
            "plus":                  "Más",
            "forecast":              "Climatología",
            "sticky hold":           "Pegamento",
            "shed skin":             "Mudar",
            "guts":                  "Agallas",
            "marvel scale":          "Escamas Marav.",
            "liquid ooze":           "Baba Tóxica",
            "overgrow":              "Espesura",
            "illuminate":            "Iluminación",
            "hustle":                "Entusiasmo",
            "cute charm":            "Encanto",
            "plus":                  "Más",
            "minus":                 "Menos",
            "veil":                  "Velo",
            "color change":          "Cambio Color",
            "immunity":              "Inmunidad",
            "flash fire":            "Absorbe Fuego",
            "shield dust":           "Polvo Escudo",
            "own tempo":             "Ritmo Propio",
            "suction cups":          "Ventosas",
            "intimidate":            "Intimidación",
            "shadow tag":            "Sombra Trampa",
            "rough skin":            "Piel Tosca",
            "wonder guard":          "Superguarda",
            "levitate":              "Levitación",
            "effect spore":          "Efecto Espora",
            "synchronize":           "Sincronía",
            "clear body":            "Cuerpo Puro",
            "natural cure":          "Cura Natural",
            "lightning rod":         "Pararrayos",
            "serene grace":          "Dicha",
            "swift swim":            "Nado Rápido",
            "chlorophyll":           "Clorofila",
            "illuminate":            "Iluminación",
            "trace":                 "Rastreo",
            "huge power":            "Potencia",
            "poison point":          "Punto Tóxico",
            "inner focus":           "Concentración",
            "magma armor":           "Coraza Magma",
            "water veil":            "Velo Agua",
            "magnet pull":           "Imán",
            "sturdy":                "Robustez",
            "damp":                  "Humedad",
            "limber":                "Flexibilidad",
            "sand veil":             "Velo Arena",
            "static":                "Electricidad Estática",
            "volt absorb":           "Absorbe Electricidad",
            "water absorb":          "Absorbe Agua",
            "oblivious":             "Simpleza",
            "cloud nine":            "Cabeza Hueca",
            "compound eyes":         "Ojo Compuesto",
            "insomnia":              "Insomnio",
            "color change":          "Cambio Color",
            "immunity":              "Inmunidad",
            "flash fire":            "Absorbe Fuego",
            # ── Gen 3 ─────────────────────────────────────────────────────────
            "speed boost":           "Impulso",
            "battle armor":          "Armadura Batalla",
            "sturdy":                "Robustez",
            "damp":                  "Humedad",
            "limber":                "Flexibilidad",
            "rock head":             "Cabeza Roca",
            "drought":               "Sequía",
            "arena trap":            "Trampa Arena",
            "vital spirit":          "Espíritu Vital",
            "white smoke":           "Humo Blanco",
            "pure power":            "Fuerza Pura",
            "shell armor":           "Coraza",
            "air lock":              "Cierre Aéreo",
            "hyper cutter":          "Corte Supremo",
            "pickup":                "Recoger",
            "truant":                "Flojera",
            "hustle":                "Entusiasmo",
            "cute charm":            "Encanto",
            "plus":                  "Más",
            "minus":                 "Menos",
            "forecast":              "Climatología",
            "sticky hold":           "Pegamento",
            "shed skin":             "Mudar",
            "guts":                  "Agallas",
            "marvel scale":          "Escamas Marav.",
            "liquid ooze":           "Baba Tóxica",
            "overgrow":              "Espesura",
            "thick fat":             "Sebo",
            "early bird":            "Madrugar",
            "flame body":            "Cuerpo Llama",
            "run away":              "Fuga",
            "keen eye":              "Vista Lince",
            "hyper cutter":          "Corte Supremo",
            "pickup":                "Recoger",
            "truant":                "Flojera",
            "pressure":              "Presión",
            "thick fat":             "Sebo",
            "early bird":            "Madrugar",
            "intimidate":            "Intimidación",
            "shadow tag":            "Sombra Trampa",
            "rough skin":            "Piel Tosca",
            "wonder guard":          "Superguarda",
            "levitate":              "Levitación",
            "stench":                "Hedor",
            "drizzle":               "Llovizna",
            "sand stream":           "Chorro Arena",
            "snow warning":          "Nevada",
            "illuminate":            "Iluminación",
            "trace":                 "Rastreo",
            "huge power":            "Potencia",
            "sap sipper":            "Vegetariano",
            "storm drain":           "Colector",
            "motor drive":           "Motor Eléctrico",
            "unburden":              "Ligereza",
            "sniper":                "Francotirador",
            "magic guard":           "Guardia Mágica",
            "no guard":              "Sin Guarda",
            "steadfast":             "Temple",
            "snow cloak":            "Manto Nieve",
            "gluttony":              "Gula",
            "anger point":           "Ira",
            "unaware":               "Ignorancia",
            "ice body":              "Cuerpo de Hielo",
            "solid rock":            "Roca Sólida",
            "snow warning":          "Nevada",
            "honey gather":          "Recoger Miel",
            "frisk":                 "Registro",
            "bad dreams":            "Pesadillas",
            "pickpocket":            "Hurto",
            "sheer force":           "Potencia Bruta",
            "contrary":              "Contrario",
            "unnerve":               "Nerviosismo",
            "defiant":               "Competidor",
            "competitive":           "Competitiva",
            "moxie":                 "Autoestima",
            "justified":             "Justificado",
            "rattled":               "Miedoso",
            "magic bounce":          "Rebote Mágico",
            "sap sipper":            "Vegetariano",
            "prankster":             "Bromista",
            "sand force":            "Fuerza Arena",
            "iron barbs":            "Piel Metálica",
            "zen mode":              "Modo Zen",
            "victory star":          "Estrella Victoria",
            "turboblaze":            "Turbollamas",
            "teravolt":              "Terravoltaje",
            # ── Gen 4 ─────────────────────────────────────────────────────────
            "adaptability":          "Adaptabilidad",
            "skill link":            "Encadenado",
            "hydration":             "Hidratación",
            "solar power":           "Poder Solar",
            "quick feet":            "Pies Rápidos",
            "normalize":             "Normalizar",
            "sniper":                "Francotirador",
            "magic guard":           "Guardia Mágica",
            "no guard":              "Sin Guarda",
            "steadfast":             "Temple",
            "snow cloak":            "Manto Nieve",
            "gluttony":              "Gula",
            "anger point":           "Ira",
            "unaware":               "Ignorancia",
            "ice body":              "Cuerpo de Hielo",
            "solid rock":            "Roca Sólida",
            "honey gather":          "Recoger Miel",
            "frisk":                 "Registro",
            "bad dreams":            "Pesadillas",
            "iron fist":             "Puño Férreo",
            "toxic boost":           "Refuerzo Tóxico",
            "flare boost":           "Refuerzo Llama",
            "leaf guard":            "Hoja Escudo",
            "klutz":                 "Patoso",
            "tangled feet":          "Pies Torpes",
            "motor drive":           "Motor Eléctrico",
            "rivalry":               "Competitividad",
            "steadfast":             "Temple",
            "scrappy":               "Aguerrido",
            "storm drain":           "Colector",
            "ice body":              "Cuerpo de Hielo",
            "solid rock":            "Roca Sólida",
            "snow warning":          "Nevada",
            "honey gather":          "Recoger Miel",
            "frisk":                 "Registro",
            "bad dreams":            "Pesadillas",
            "super luck":            "Supersuerte",
            "aftermath":             "Secuela",
            "anticipation":          "Presentimiento",
            "forewarn":              "Alerta",
            "unburden":              "Ligereza",
            "heatproof":             "Ignífugo",
            "simple":                "Simpleza",
            "dry skin":              "Piel Seca",
            "download":              "Descarga",
            "iron fist":             "Puño Férreo",
            "poison heal":           "Cura Veneno",
            "adaptability":          "Adaptabilidad",
            "skill link":            "Encadenado",
            "hydration":             "Hidratación",
            "solar power":           "Poder Solar",
            "quick feet":            "Pies Rápidos",
            "normalize":             "Normalizar",
            "reckless":              "Imprudente",
            "multitype":             "Multitipo",
            "flower gift":           "Regalo Floral",
            "bad dreams":            "Pesadillas",
            # ── Gen 5 ─────────────────────────────────────────────────────────
            "imposter":              "Impostor",
            "pickpocket":            "Hurto",
            "sheer force":           "Potencia Bruta",
            "contrary":              "Contrario",
            "unnerve":               "Nerviosismo",
            "defiant":               "Competidor",
            "competitive":           "Competitiva",
            "moxie":                 "Autoestima",
            "justified":             "Justificado",
            "rattled":               "Miedoso",
            "magic bounce":          "Rebote Mágico",
            "prankster":             "Bromista",
            "sand force":            "Fuerza Arena",
            "iron barbs":            "Piel Metálica",
            "zen mode":              "Modo Zen",
            "victory star":          "Estrella Victoria",
            "turboblaze":            "Turbollamas",
            "teravolt":              "Terravoltaje",
            "analytic":              "Análisis",
            "illusion":              "Ilusión",
            "infiltrator":           "Infiltrador",
            "mummy":                 "Momia",
            "overcoat":              "Sobretodo",
            "weak armor":            "Armadura Frágil",
            "wonder skin":           "Piel Mágica",
            "sand rush":             "Ímpetu Arena",
            "sap sipper":            "Vegetariano",
            "storm drain":           "Colector",
            "volt absorb":           "Absorbe Electricidad",
            "lightningrod":          "Pararrayos",
            "regenerator":           "Regeneración",
            "multiscale":            "Multiescamas",
            "toxic boost":           "Refuerzo Tóxico",
            "huge power":            "Potencia",
            "pure power":            "Fuerza Pura",
            "flare boost":           "Refuerzo Llama",
            "harvest":               "Cosecha",
            "telepathy":             "Telepatía",
            "moody":                 "Volátil",
            "healer":                "Sanador",
            "friend guard":          "Guardia Amiga",
            "final gambit":          "Baza Final",
            "long reach":            "Largo Alcance",
            "liquid voice":          "Voz Acuosa",
            "triage":                "Triaje",
            # ── Gen 6 ─────────────────────────────────────────────────────────
            "tough claws":           "Garra Dura",
            "mega launcher":         "Megadisparo",
            "grassy surge":          "Herbogénesis",
            "psychic surge":         "Psicogénesis",
            "electric surge":        "Electrogénesis",
            "misty surge":           "Nebulogénesis",
            "aura break":            "Antiaura",
            "fairy aura":            "Aura Hada",
            "dark aura":             "Aura Siniestra",
            "strong jaw":            "Mandíbula Fuerte",
            "symbiosis":             "Simbiosis",
            "stance change":         "Cambio Postura",
            "gale wings":            "Alas Vendaval",
            "mega launcher":         "Megadisparo",
            "grass pelt":            "Piel Vegetal",
            "protean":               "Multicolor",
            "fur coat":              "Pelaje",
            "magician":              "Mago",
            "bulletproof":           "Antibalas",
            "sweet veil":            "Dulce Velo",
            "stance change":         "Cambio Postura",
            "gale wings":            "Alas Vendaval",
            "mega launcher":         "Megadisparo",
            "aerilate":              "Aerodinámica",
            "pixilate":              "Pixilátor",
            "refrigerate":           "Refrigeración",
            "galvanize":             "Galvanizar",
            "oblivious":             "Simpleza",
            "liquid voice":          "Voz Acuosa",
            "triage":                "Triaje",
            "power construct":       "Fusión Total",
            # ── Gen 7 ─────────────────────────────────────────────────────────
            "water bubble":          "Burbuja Acuática",
            "steelworker":           "Siderúrgico",
            "berserk":               "Furia Ciega",
            "slush rush":            "Ímpetu Granizo",
            "long reach":            "Largo Alcance",
            "liquid voice":          "Voz Acuosa",
            "triage":                "Triaje",
            "galvanize":             "Galvanizar",
            "surge surfer":          "Surfista Eléctrico",
            "schooling":             "Cardumen",
            "disguise":              "Disfraz",
            "battle bond":           "Amor Eterno",
            "power construct":       "Fusión Total",
            "corrosion":             "Corrosión",
            "comatose":              "Letargo",
            "queenly majesty":       "Majestad Regia",
            "innards out":           "Entrañas",
            "dancer":                "Danzarín",
            "battery":               "Batería",
            "fluffy":                "Esponjoso",
            "dazzling":              "Deslumbramiento",
            "soul heart":            "Corazón Etéreo",
            "tangling hair":         "Cabello Revuelto",
            "receiver":              "Receptor",
            "power of alchemy":      "Alquimia",
            "beast boost":           "Ultrarefuerzo",
            "rks system":            "Sistema RR",
            "electric surge":        "Electrogénesis",
            "psychic surge":         "Psicogénesis",
            "misty surge":           "Nebulogénesis",
            "grassy surge":          "Herbogénesis",
            "full metal body":       "Cuerpo Férreo",
            "shadow shield":         "Escudo Umbría",
            "prism armor":           "Armadura Prisma",
            "neuroforce":            "Neuroimpacto",
            # ── Gen 8 ─────────────────────────────────────────────────────────
            "intrepid sword":        "Espada Inquebrantable",
            "dauntless shield":      "Escudo Intrépido",
            "libero":                "Libero",
            "ball fetch":            "Recoge Poké Ball",
            "cotton down":           "Pelusa Algodón",
            "propeller tail":        "Cola Hélice",
            "mirror armor":          "Armadura Espejo",
            "gulp missile":          "Tragada Misil",
            "stalwart":              "Inflexible",
            "steam engine":          "Máquina de Vapor",
            "punk rock":             "Punk Rock",
            "sand spit":             "Saliva Arena",
            "ice scales":            "Escamas Hielo",
            "ripen":                 "Madurez",
            "ice face":              "Escudo de Hielo",
            "power spot":            "Punto Álgido",
            "mimicry":               "Mimetismo",
            "screen cleaner":        "Limpiapantallas",
            "steely spirit":         "Ánimo Férreo",
            "perish body":           "Cuerpo Mortal",
            "wandering spirit":      "Espíritu Errante",
            "gorilla tactics":       "Táctica Gorila",
            "neutralizing gas":      "Gas Neutralizante",
            "pastel veil":           "Velo Pastel",
            "hunger switch":         "Modo Hambriento",
            "quick draw":            "Desenfundado",
            "unseen fist":           "Puño Invisible",
            "curious medicine":      "Medicina Curiosa",
            "transistor":            "Transistor",
            "dragons maw":           "Hocico de Dragón",
            "chilling neigh":        "Relincho Gélido",
            "grim neigh":            "Relincho Lúgubre",
            "as one":                "Como Uno",
            "unsheathed":            "Desenfundado",
            "wind rider":            "Jinete del Viento",
            "guard dog":             "Guardián",
            "rocky payload":         "Carga Pétrea",
            "wind power":            "Poder del Viento",
            "zero to hero":          "De Cero a Héroe",
            "commander":             "Comandante",
            "electromorphosis":      "Electromorfosis",
            "protosynthesis":        "Protosíntesis",
            "quark drive":           "Motor Quark",
            "good as gold":          "Puro Oro",
            "vessel of ruin":        "Vasija Funesta",
            "sword of ruin":         "Espada Funesta",
            "tablets of ruin":       "Tablillas Funestas",
            "beads of ruin":         "Cuentas Funestas",
            "orichalcum pulse":      "Pulso Oricalco",
            "hadron engine":         "Motor Hadrón",
            "opportunist":           "Oportunista",
            "cud chew":              "Rumia",
            "sharpness":             "Filo Supremo",
            "supreme overlord":      "Supremo Señor",
            "costar":                "Coprotagonista",
            "toxic debris":          "Escombros Tóxicos",
            "armor tail":            "Cola Escudo",
            "earth eater":           "Comedor de Tierra",
            "mycelium might":        "Poder Micélico",
            # ── Gen 9 ─────────────────────────────────────────────────────────
            "thermal exchange":      "Intercambio Térmico",
            "anger shell":           "Caparazón Iracundo",
            "purifying salt":        "Sal Purificadora",
            "well baked body":       "Cuerpo Bien Cocido",
            "wind rider":            "Jinete del Viento",
            "guard dog":             "Guardián",
            "rocky payload":         "Carga Pétrea",
            "electromorphosis":      "Electromorfosis",
        }

    # ══════════════════════════════════════════════════════════════════════════
    # DATOS INTERNOS — EFECTOS DE COMBATE
    # ══════════════════════════════════════════════════════════════════════════

    def _cargar_habilidades(self) -> Dict[str, Dict]:
        """
        Efectos de combate por nombre en español.
        Solo se registran las habilidades que tienen efecto activo en batalla.
        Las puramente cosméticas o no implementadas no aparecen aquí
        (obtener_habilidad devuelve None → sin efecto → comportamiento neutro).
        """
        return {

            # ══ BOOST HP BAJO (33 % HP → +50 % daño del tipo) ═══════════════
            "Espesura":    {"tipo": "boost_hp_bajo", "condicion_hp": 0.33, "boost_tipo": "Planta",    "multiplicador": 1.5, "descripcion": "Potencia movimientos Planta al ≤33 % HP"},
            "Mar Llamas":  {"tipo": "boost_hp_bajo", "condicion_hp": 0.33, "boost_tipo": "Fuego",     "multiplicador": 1.5, "descripcion": "Potencia movimientos Fuego al ≤33 % HP"},
            "Torrente":    {"tipo": "boost_hp_bajo", "condicion_hp": 0.33, "boost_tipo": "Agua",      "multiplicador": 1.5, "descripcion": "Potencia movimientos Agua al ≤33 % HP"},
            "Enjambre":    {"tipo": "boost_hp_bajo", "condicion_hp": 0.33, "boost_tipo": "Bicho",     "multiplicador": 1.5, "descripcion": "Potencia movimientos Bicho al ≤33 % HP"},
            # Gen 7 Litten line
            "Cuerpo Llama": {"tipo": "boost_hp_bajo", "condicion_hp": 0.33, "boost_tipo": "Fuego",    "multiplicador": 1.5, "descripcion": "Potencia movimientos Fuego al ≤33 % HP"},
            # Gen 7 Primarina line
            "Torrente Marino": {"tipo": "boost_hp_bajo", "condicion_hp": 0.33, "boost_tipo": "Agua",  "multiplicador": 1.5, "descripcion": "Potencia movimientos Agua al ≤33 % HP"},

            # ══ BOOST POTENCIA BAJA ══════════════════════════════════════════
            "Experto": {
                "tipo": "boost_potencia", "potencia_max": 60,
                "multiplicador": 1.5,
                "descripcion": "Potencia movimientos ≤60 BP en 50 %",
            },

            # ══ BOOST STAB ═══════════════════════════════════════════════════
            "Adaptabilidad": {
                "tipo": "boost_stab", "multiplicador": 2.0,
                "descripcion": "STAB sube de 1.5× a 2.0×",
            },

            # ══ BOOST CONTACTO ════════════════════════════════════════════════
            "Garra Dura": {
                "tipo": "boost_contacto", "multiplicador": 1.3,
                "descripcion": "Movimientos de contacto +30 %",
            },
            "Mandíbula Fuerte": {
                "tipo": "boost_categoria",
                "movimientos": ["bite", "crunch", "fire fang", "ice fang",
                                "thunder fang", "psychic fangs", "fishious rend",
                                "jaw lock"],
                "multiplicador": 1.5,
                "descripcion": "Movimientos de mordida +50 %",
            },
            "Puño Férreo": {
                "tipo": "boost_categoria",
                "movimientos": ["fire punch", "ice punch", "thunder punch",
                                "drain punch", "focus punch", "mach punch",
                                "shadow punch", "meteor mash", "bullet punch",
                                "sky uppercut", "comet punch", "hammer arm",
                                "ice hammer", "plasma fists"],
                "multiplicador": 1.2,
                "descripcion": "Movimientos de puño +20 %",
            },

            # ══ SHEER FORCE / HUSTLE ══════════════════════════════════════════
            "Potencia Bruta": {
                "tipo": "boost_sheer_force", "multiplicador": 1.3,
                "elimina_secundarios": True,
                "descripcion": "Elimina efectos secundarios pero +30 % poder",
            },
            "Entusiasmo": {
                "tipo": "boost_hustle", "boost_atq": 1.5, "reducir_precision": 0.8,
                "descripcion": "Ataque físico +50 % pero precisión −20 %",
            },

            # ══ SOLAR POWER ════════════════════════════════════════════════════
            "Poder Solar": {
                "tipo": "boost_sol", "multiplicador": 1.5,
                "coste_hp": 0.125,
                "descripcion": "Bajo sol: At. Esp. +50 % pero pierde 1/8 HP/turno",
            },

            # ══ INMUNIDADES (tipo) ════════════════════════════════════════════
            "Levitación": {
                "tipo": "inmunidad", "inmune_a": ["Tierra"],
                "descripcion": "Inmune a movimientos de tipo Tierra",
            },
            "Absorbe Fuego": {
                "tipo": "inmunidad_cura", "inmune_a": ["Fuego"],
                "descripcion": "Absorbe ataques de Fuego y cura HP",
            },
            "Absorbe Agua": {
                "tipo": "inmunidad_cura", "inmune_a": ["Agua"],
                "descripcion": "Absorbe ataques de Agua y cura HP",
            },
            "Absorbe Electricidad": {
                "tipo": "inmunidad_boost", "inmune_a": ["Eléctrico"],
                "boost_stat": "atq_sp", "boost_cantidad": 1,
                "descripcion": "Absorbe ataques Eléctricos y sube At. Esp.",
            },
            "Pararrayos": {
                "tipo": "inmunidad_boost", "inmune_a": ["Eléctrico"],
                "boost_stat": "atq_sp", "boost_cantidad": 1,
                "descripcion": "Absorbe ataques Eléctricos y sube At. Esp.",
            },
            "Colector": {
                "tipo": "inmunidad_boost", "inmune_a": ["Agua"],
                "boost_stat": "atq_sp", "boost_cantidad": 1,
                "descripcion": "Absorbe ataques de Agua y sube At. Esp.",
            },
            "Vegetariano": {
                "tipo": "inmunidad_boost", "inmune_a": ["Planta"],
                "boost_stat": "atq", "boost_cantidad": 1,
                "descripcion": "Absorbe ataques de Planta y sube Ataque",
            },
            "Superguarda": {
                "tipo": "inmunidad_especial", "solo_super_efectivo": True,
                "descripcion": "Solo recibe daño de ataques súper efectivos",
            },
            "Motor Eléctrico": {
                "tipo": "inmunidad_boost", "inmune_a": ["Eléctrico"],
                "boost_stat": "vel", "boost_cantidad": 1,
                "descripcion": "Absorbe ataques Eléctricos y sube Velocidad",
            },
            # Gen 5 Sap Sipper alias
            "Herbívoro": {
                "tipo": "inmunidad_boost", "inmune_a": ["Planta"],
                "boost_stat": "atq", "boost_cantidad": 1,
                "descripcion": "Absorbe ataques de Planta y sube Ataque",
            },

            # ══ RESISTENCIAS ══════════════════════════════════════════════════
            "Sebo": {
                "tipo": "resistencia", "reduce_tipo": ["Fuego", "Hielo"],
                "multiplicador": 0.5,
                "descripcion": "Reduce daño de Fuego e Hielo a la mitad",
            },
            "Roca Sólida": {
                "tipo": "resistencia_superefectiva", "reduccion": 0.75,
                "descripcion": "Reduce daño súper efectivo recibido a ×0.75",
            },
            "Filtro": {
                "tipo": "resistencia_superefectiva", "reduccion": 0.75,
                "descripcion": "Reduce daño súper efectivo recibido a ×0.75",
            },
            "Armadura Prisma": {
                "tipo": "resistencia_superefectiva", "reduccion": 0.75,
                "descripcion": "Reduce daño súper efectivo recibido a ×0.75",
            },
            "Multiescamas": {
                "tipo": "resistencia_hp_lleno", "reduccion": 0.5,
                "descripcion": "A HP lleno reduce el primer golpe a la mitad",
            },
            "Ignífugo": {
                "tipo": "resistencia", "reduce_tipo": ["Fuego"],
                "multiplicador": 0.5,
                "descripcion": "Reduce daño de Fuego a la mitad",
            },
            "Piel Tosca": {
                "tipo": "contacto_daño", "daño": 1/8,
                "descripcion": "El atacante pierde 1/8 HP al tocar",
            },
            "Piel Metálica": {
                "tipo": "contacto_daño", "daño": 1/8,
                "descripcion": "El atacante pierde 1/8 HP al tocar",
            },

            # ══ AL SER GOLPEADO (contacto) ════════════════════════════════════
            "Electricidad Estática": {
                "tipo": "contacto", "efecto": "paralizar", "probabilidad": 0.30,
                "descripcion": "30 % de paralizar al contacto físico",
            },
            "Cuerpo Llama": {
                "tipo": "contacto", "efecto": "quemar", "probabilidad": 0.30,
                "descripcion": "30 % de quemar al contacto físico",
            },
            "Punto Tóxico": {
                "tipo": "contacto", "efecto": "envenenar", "probabilidad": 0.30,
                "descripcion": "30 % de envenenar al contacto físico",
            },
            "Efecto Espora": {
                "tipo": "contacto_multiple",
                "efectos": ["paralizar", "envenenar", "dormir"], "probabilidad": 0.30,
                "descripcion": "30 % de paralizar/envenenar/dormir al contacto",
            },
            "Mudar": {
                "tipo": "mudar", "probabilidad": 0.33,
                "descripcion": "33 % de eliminar estado al final del turno",
            },

            # ══ ENTRADA EN BATALLA ════════════════════════════════════════════
            "Intimidación": {
                "tipo": "entrada", "efecto": "reducir_stat",
                "stat": "atq", "cantidad": -1,
                "descripcion": "Al entrar reduce Ataque del rival en 1 etapa",
            },
            "Sequía": {
                "tipo": "entrada", "efecto": "clima", "clima": "SOL", "turnos": 5,
                "descripcion": "Al entrar invoca Sol durante 5 turnos",
            },
            "Llovizna": {
                "tipo": "entrada", "efecto": "clima", "clima": "LLUVIA", "turnos": 5,
                "descripcion": "Al entrar invoca Lluvia durante 5 turnos",
            },
            "Chorro Arena": {
                "tipo": "entrada", "efecto": "clima", "clima": "TORMENTA_ARENA", "turnos": 5,
                "descripcion": "Al entrar invoca Tormenta de Arena 5 turnos",
            },
            "Nevada": {
                "tipo": "entrada", "efecto": "clima", "clima": "GRANIZO", "turnos": 5,
                "descripcion": "Al entrar invoca Granizo durante 5 turnos",
            },
            "Electrogénesis": {
                "tipo": "entrada", "efecto": "terreno", "terreno": "ELECTRICO", "turnos": 5,
                "descripcion": "Crea Campo Eléctrico durante 5 turnos",
            },
            "Psicogénesis": {
                "tipo": "entrada", "efecto": "terreno", "terreno": "PSIQUICO", "turnos": 5,
                "descripcion": "Crea Campo Psíquico durante 5 turnos",
            },
            "Herbogénesis": {
                "tipo": "entrada", "efecto": "terreno", "terreno": "HIERBA", "turnos": 5,
                "descripcion": "Crea Campo de Hierba durante 5 turnos",
            },
            "Nebulogénesis": {
                "tipo": "entrada", "efecto": "terreno", "terreno": "NIEBLA", "turnos": 5,
                "descripcion": "Crea Campo de Niebla durante 5 turnos",
            },

            # ══ COPIA / TRANSFORMACIÓN ════════════════════════════════════════
            "Impostor": {
                "tipo": "transformacion", "efecto": "copiar_rival",
                "descripcion": "Al entrar en batalla, copia al rival (Ditto)",
            },
            "Ilusión": {
                "tipo": "ilusion", "efecto": "disfrazarse",
                "descripcion": "Entra disfrazado del último Pokémon del equipo",
            },
            "Rastreo": {
                "tipo": "copia_habilidad", "efecto": "copiar_habilidad_rival",
                "descripcion": "Copia la habilidad del rival al entrar",
            },
            "Mimetismo": {
                "tipo": "mimetismo",
                "descripcion": "Cambia de tipo según el terreno activo",
            },
            "Multicolor": {
                "tipo": "cambio_tipo",
                "descripcion": "Cambia al tipo del movimiento que va a usar",
            },

            # ══ ACELERACIÓN / VELOCIDAD ════════════════════════════════════════
            "Impulso": {
                "tipo": "boost_vel_fin_turno", "incremento": 1,
                "descripcion": "Velocidad sube 1 etapa al final de cada turno",
            },
            "Clorofila": {
                "tipo": "clima_vel", "clima": "SOL", "multiplicador": 2.0,
                "descripcion": "Duplica Velocidad bajo el sol",
            },
            "Nado Rápido": {
                "tipo": "clima_vel", "clima": "LLUVIA", "multiplicador": 2.0,
                "descripcion": "Duplica Velocidad bajo la lluvia",
            },
            "Ímpetu Arena": {
                "tipo": "clima_vel", "clima": "TORMENTA_ARENA", "multiplicador": 2.0,
                "descripcion": "Duplica Velocidad en tormenta de arena",
            },
            "Ímpetu Granizo": {
                "tipo": "clima_vel", "clima": "GRANIZO", "multiplicador": 2.0,
                "descripcion": "Duplica Velocidad bajo el granizo",
            },
            "Pies Rápidos": {
                "tipo": "boost_vel_estado", "multiplicador": 1.5,
                "descripcion": "Velocidad ×1.5 si tiene un estado alterado",
            },
            "Ligereza": {
                "tipo": "boost_vel_sin_objeto", "multiplicador": 2.0,
                "descripcion": "Duplica Velocidad si no lleva objeto",
            },

            # ══ AGALLAS Y VARIANTES ════════════════════════════════════════════
            "Agallas": {
                "tipo": "boost_atq_estado", "multiplicador": 1.5,
                "descripcion": "Ataque ×1.5 si tiene un estado alterado",
            },
            "Refuerzo Tóxico": {
                "tipo": "boost_atq_veneno", "multiplicador": 1.5,
                "descripcion": "Ataque ×1.5 si está envenenado",
            },
            "Refuerzo Llama": {
                "tipo": "boost_atqsp_quemado", "multiplicador": 1.5,
                "descripcion": "At. Esp. ×1.5 si está quemado",
            },

            # ══ ROBUSTEZ / DEFENSA ════════════════════════════════════════════
            "Robustez": {
                "tipo": "sobrevivir_golpe", "hp_minimo": 1,
                "descripcion": "Sobrevive con 1 HP si estaba en HP lleno",
            },
            "Escudo Umbría": {
                "tipo": "sobrevivir_golpe", "hp_minimo": 1,
                "descripcion": "Sobrevive con 1 HP si estaba en HP lleno",
            },
            "Cuerpo Férreo": {
                "tipo": "sin_reduccion_stats",
                "descripcion": "Los stats no pueden ser reducidos por el rival",
            },

            # ══ CLIMA: DEFENSA ════════════════════════════════════════════════
            "Velo Arena": {
                "tipo": "clima_evasion", "clima": "TORMENTA_ARENA",
                "bonus_evasion": 1,
                "descripcion": "Evasión sube 1 etapa en tormenta de arena",
            },
            "Manto Nieve": {
                "tipo": "clima_evasion", "clima": "GRANIZO",
                "bonus_evasion": 1,
                "descripcion": "Evasión sube 1 etapa bajo granizo",
            },
            "Cuerpo de Hielo": {
                "tipo": "clima_cura", "clima": "GRANIZO", "fraccion": 0.0625,
                "descripcion": "Se cura 1/16 HP/turno bajo el granizo",
            },

            # ══ CLIMA: DAÑO FIN DE TURNO ══════════════════════════════════════
            "Fuerza Arena": {
                "tipo": "boost_clima_atq", "clima": "TORMENTA_ARENA",
                "tipos_afectados": ["Roca", "Acero", "Tierra"],
                "multiplicador": 1.3,
                "descripcion": "Bajo arena: Roca/Acero/Tierra +30 %",
            },
            "Poder Solar": {
                "tipo": "boost_sol", "multiplicador": 1.5, "coste_hp": 0.125,
                "descripcion": "Bajo sol: At. Esp. +50 % pero pierde 1/8 HP/turno",
            },
            "Piel Seca": {
                "tipo": "doble_efecto_clima",
                "cura_clima": "LLUVIA", "cura_fraccion": 0.125,
                "daño_clima": "SOL",   "daño_fraccion": 0.125,
                "descripcion": "Lluvia cura; Sol daña",
            },
            "Hidratación": {
                "tipo": "cura_estado_clima", "clima": "LLUVIA",
                "descripcion": "Bajo lluvia elimina estado alterado al fin de turno",
            },

            # ══ RECUPERACIÓN ══════════════════════════════════════════════════
            "Regeneración": {
                "tipo": "cura_al_salir", "fraccion": 0.33,
                "descripcion": "Se cura 1/3 HP al salir de batalla",
            },
            "Cosecha": {
                "tipo": "recuperar_baya", "probabilidad": 0.5,
                "descripcion": "50 % de recuperar la baya consumida al fin de turno",
            },
            "Inmunidad": {
                "tipo": "inmunidad_veneno",
                "descripcion": "Inmune al veneno y la intoxicación",
            },
            "Cura Natural": {
                "tipo": "cura_al_salir_estado",
                "descripcion": "Elimina estado alterado al salir de batalla",
            },

            # ══ ATAQUES ESPECIALES ════════════════════════════════════════════
            "Megadisparo": {
                "tipo": "boost_categoria",
                "movimientos": ["aura sphere", "dark pulse", "dragon pulse",
                                "heal pulse", "origin pulse", "water pulse",
                                "terrain pulse", "nuzzle"],
                "multiplicador": 1.5,
                "descripcion": "Movimientos de pulso/aura +50 %",
            },
            "Aerodinámica": {
                "tipo": "normaliza_tipo", "tipo_destino": "Volador",
                "multiplicador": 1.2,
                "descripcion": "Movimientos Normales → Volador, +20 % poder",
            },
            "Pixilátor": {
                "tipo": "normaliza_tipo", "tipo_destino": "Hada",
                "multiplicador": 1.2,
                "descripcion": "Movimientos Normales → Hada, +20 % poder",
            },
            "Refrigeración": {
                "tipo": "normaliza_tipo", "tipo_destino": "Hielo",
                "multiplicador": 1.2,
                "descripcion": "Movimientos Normales → Hielo, +20 % poder",
            },
            "Galvanizar": {
                "tipo": "normaliza_tipo", "tipo_destino": "Eléctrico",
                "multiplicador": 1.2,
                "descripcion": "Movimientos Normales → Eléctrico, +20 % poder",
            },

            # ══ STAT NEGATIVO → BOOST ═════════════════════════════════════════
            "Contrario": {
                "tipo": "invertir_cambios_stat",
                "descripcion": "Cambios de stat son invertidos (+1 → −1 y viceversa)",
            },

            # ══ AUTOESTIMA / AFTER BOOST ══════════════════════════════════════
            "Autoestima": {
                "tipo": "boost_al_ko", "stat": "atq", "cantidad": 1,
                "descripcion": "Ataque sube 1 etapa al noquear a un rival",
            },
            "Ultrarefuerzo": {
                "tipo": "boost_al_ko_stat_mas_alto", "cantidad": 1,
                "descripcion": "El stat más alto sube 1 etapa al noquear",
            },

            # ══ PRIORIDAD ALTERADA ════════════════════════════════════════════
            "Bromista": {
                "tipo": "prioridad_estado", "incremento": 1,
                "descripcion": "Movimientos de estado tienen prioridad +1",
            },
            "Alas Vendaval": {
                "tipo": "prioridad_tipo", "tipo": "Volador", "incremento": 1,
                "descripcion": "Movimientos de tipo Volador tienen prioridad +1",
            },

            # ══ VARIOS ════════════════════════════════════════════════════════
            "Sin Guarda": {
                "tipo": "precision_perfecta",
                "descripcion": "Todos los movimientos propios y rivales son precisos",
            },
            "Concentración": {
                "tipo": "inmunidad_flinch",
                "descripcion": "Inmune al retroceso (flinch)",
            },
            "Sincronía": {
                "tipo": "reflejar_estado", "probabilidad": 0.5,
                "descripcion": "50 % de transmitir estado al rival al recibirlo",
            },
            "Dicha": {
                "tipo": "boost_efecto_secundario", "multiplicador": 2.0,
                "descripcion": "Dobla la probabilidad de efectos secundarios propios",
            },
            "Presión": {
                "tipo": "pp_extra", "coste_extra": 1,
                "descripcion": "El rival usa 1 PP extra por movimiento",
            },
            "Potencia": {
                "tipo": "boost_fijo", "stat": "atq", "multiplicador": 2.0,
                "descripcion": "Duplica el Ataque",
            },
            "Fuerza Pura": {
                "tipo": "boost_fijo", "stat": "atq", "multiplicador": 2.0,
                "descripcion": "Duplica el Ataque",
            },
            "Fuga": {
                "tipo": "huida_garantizada",
                "descripcion": "Puede huir de cualquier batalla",
            },
            "Vista Lince": {
                "tipo": "sin_reduccion_precision",
                "descripcion": "Precisión no puede ser reducida",
            },
            "Ojo Compuesto": {
                "tipo": "boost_fijo", "stat": "precision", "multiplicador": 1.3,
                "descripcion": "Precisión propia ×1.3",
            },
            "Francotirador": {
                "tipo": "boost_critico", "multiplicador_critico": 2.25,
                "descripcion": "Los golpes críticos hacen ×2.25 de daño",
            },
            "Encadenado": {
                "tipo": "max_multihit",
                "descripcion": "Los movimientos multihit siempre golpean el máximo de veces",
            },
            "Guardián": {
                "tipo": "sin_reduccion_atq",
                "descripcion": "El Ataque no puede ser reducido por el rival",
            },
            "Presentimiento": {
                "tipo": "anticipa_movimiento",
                "descripcion": "Sabe el movimiento del rival antes de que ataque",
            },
            "Rebote Mágico": {
                "tipo": "rebotar_movimientos_estado",
                "descripcion": "Refleja los movimientos de estado del rival",
            },
            "Guardia Mágica": {
                "tipo": "sin_daño_indirecto",
                "descripcion": "Solo recibe daño de ataques directos",
            },
            "Infiltrador": {
                "tipo": "ignorar_pantallas",
                "descripcion": "Los ataques ignoran pantallas y velos",
            },
            "Corrosión": {
                "tipo": "envenenar_cualquier_tipo",
                "descripcion": "Puede envenenar a Pokémon de tipo Acero y Veneno",
            },
            "Neuroimpacto": {
                "tipo": "boost_superefectivo", "multiplicador": 1.25,
                "descripcion": "Golpes súper efectivos +25 % de daño",
            },
            "Transistor": {
                "tipo": "boost_tipo_propio", "tipo": "Eléctrico", "multiplicador": 1.5,
                "descripcion": "Movimientos Eléctricos +50 %",
            },
            "Hocico de Dragón": {
                "tipo": "boost_tipo_propio", "tipo": "Dragón", "multiplicador": 1.5,
                "descripcion": "Movimientos de Dragón +50 %",
            },
            "Filo Supremo": {
                "tipo": "boost_categoria",
                "movimientos": ["slash", "leaf blade", "night slash", "psycho cut",
                                "sacred sword", "secret sword", "razor leaf",
                                "air slash", "razor wind", "cross poison",
                                "cross chop", "fury cutter"],
                "multiplicador": 1.5,
                "descripcion": "Movimientos cortantes +50 %",
            },
            "Burbuja Acuática": {
                "tipo": "boost_tipo_doble_y_reduce_quemadura",
                "tipo_boosteado": "Agua", "multiplicador": 2.0,
                "reduce_quemadura": True,
                "descripcion": "Ataques de Agua ×2; inmune a quemaduras",
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# Instancia global — importar desde aquí
# ─────────────────────────────────────────────────────────────────────────────
habilidades_service = HabilidadesService()