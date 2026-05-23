# -*- coding: utf-8 -*-
"""
funciones/mercado_events.py
════════════════════════════════════════════════════════════════════════════════
Catálogo de eventos del Mercado de Cosmos.

Cada evento tiene:
  texto      — descripción que se publica en el grupo
  impacto    — rango (min%, max%) del movimiento de precio
               positivo  → sube precio
               negativo  → baja precio

El servicio elige aleatoriamente un evento y un impacto dentro del rango.
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Evento:
    texto:   str
    impacto: Tuple[float, float]   # (min%, max%) — ambos positivos; el servicio aplica el signo


# ─── 50 eventos positivos ─────────────────────────────────────────────────────

EVENTOS_POSITIVOS = [
    Evento("¡Sold out mundial! Todas las fechas de la gira agotadas en minutos.", (12, 30)),
    Evento("Nuevo álbum rompe el récord de Spotify: 100M de streams en las primeras 24 h.", (15, 35)),
    Evento("Nominación al Grammy como Mejor Álbum de Pop Global confirmada.", (10, 25)),
    Evento("Colaboración sorpresa con artista internacional de primer nivel anunciada.", (18, 40)),
    Evento("Netflix confirma un documental exclusivo sobre la banda.", (8, 20)),
    Evento("El MV supera los 500 millones de vistas en YouTube en tiempo récord.", (10, 22)),
    Evento("Contrato millonario firmado como embajadores de marca de lujo global.", (12, 28)),
    Evento("Discurso en la ONU se viraliza en todo el mundo y recibe elogios.", (8, 18)),
    Evento("Actuación en el Super Bowl confirmada para la próxima temporada.", (20, 45)),
    Evento("Debut número 1 en el Billboard Hot 100 con su más reciente single.", (15, 32)),
    Evento("Fan meeting en estadio lleno: 80.000 personas en una sola noche.", (7, 16)),
    Evento("Arrasan en los premios: Daesang en todos los shows musicales del mes.", (10, 24)),
    Evento("Fechas adicionales en Europa por demanda masiva de entradas.", (6, 14)),
    Evento("Miembro principal gana el premio al mejor actor del año.", (8, 18)),
    Evento("Nuevo álbum ocupa el top 10 en 50 países de forma simultánea.", (12, 26)),
    Evento("Concierto online bate récord mundial de audiencia en streaming.", (10, 22)),
    Evento("Marca propia de moda lanzada con ventas explosivas en las primeras horas.", (14, 30)),
    Evento("Miembro debuta como solista y supera todas las expectativas del mercado.", (16, 35)),
    Evento("OST para videojuego Triple A genera millones en ventas digitales.", (9, 20)),
    Evento("Portada de la revista Time: 'Los artistas más influyentes del año'.", (11, 24)),
    Evento("Canción elegida como himno oficial de los Juegos Olímpicos.", (18, 38)),
    Evento("Nuevo récord Guinness por mayor número de streams simultáneos en la historia.", (20, 42)),
    Evento("Película de concierto estrenada en cines a nivel mundial con lleno total.", (12, 26)),
    Evento("Alianza exclusiva con plataforma de streaming por cifra récord.", (10, 22)),
    Evento("Edición limitada de photocards agotada en menos de 60 segundos.", (7, 15)),
    Evento("Aparición sorpresa y ovacionada en el festival de Coachella.", (14, 32)),
    Evento("Single certificado Diamante por la RIAA en Estados Unidos.", (12, 28)),
    Evento("Fan café oficial supera los 10 millones de miembros registrados.", (6, 13)),
    Evento("Comeback anunciado con concepto completamente innovador que revoluciona el género.", (15, 34)),
    Evento("Miembro regresa del servicio militar con energía renovada y nuevo proyecto.", (10, 22)),
    Evento("Actuación de Año Nuevo en Times Square vista por 2 millones de personas.", (9, 20)),
    Evento("Múltiples marcas compiten por los derechos de uso de sus canciones.", (8, 18)),
    Evento("Álbum certificado Platino en 15 países durante la primera semana.", (14, 30)),
    Evento("Gira en Latinoamérica agota estadios en tiempo récord histórico.", (11, 25)),
    Evento("Premio especial a la trayectoria entregado por la industria musical global.", (9, 20)),
    Evento("Colaboración con orquesta filarmónica internacional aclamada por la crítica.", (7, 15)),
    Evento("Reality show propio anunciado en plataforma premium con temporada garantizada.", (10, 22)),
    Evento("Miembro lanza perfume propio que agota stock en 3 horas de preventa.", (8, 18)),
    Evento("Outfit viral en la Met Gala: 200 millones de impresiones en redes.", (9, 20)),
    Evento("Campaña publicitaria global firmada con empresa del Fortune 500.", (12, 26)),
    Evento("Nuevo lightstick oficial agotado en preventa con lista de espera de miles.", (6, 13)),
    Evento("Invitados especiales en el concierto de un artista legendario del pop.", (8, 17)),
    Evento("Pop-up store oficial en 10 ciudades simultáneas con colas de madrugada.", (7, 15)),
    Evento("Canción seleccionada como himno de competencia deportiva internacional.", (8, 18)),
    Evento("Miembro protagoniza blockbuster de Hollywood con distribución mundial.", (16, 36)),
    Evento("Expansión histórica: primera gira en África y Oceanía con sold out total.", (12, 28)),
    Evento("Sub-unit sorpresa lanza álbum debut que supera todas las expectativas.", (13, 29)),
    Evento("Ranking global los corona como el grupo más popular del año por tercer año consecutivo.", (10, 22)),
    Evento("Colaboración benéfica viral recauda millones y eleva su imagen global.", (8, 16)),
    Evento("Pre-venta de nuevo álbum bate récord mundial en menos de 1 hora.", (18, 40)),
]

# ─── 50 eventos negativos ─────────────────────────────────────────────────────

EVENTOS_NEGATIVOS = [
    Evento("Miembro hospitalizado por agotamiento extremo tras intensa gira mundial.", (12, 30)),
    Evento("Concierto cancelado de urgencia por amenaza de bomba en el recinto.", (15, 35)),
    Evento("Escándalo de citas filtrado en redes sociales desata furia entre fandoms.", (18, 40)),
    Evento("Acusaciones de plagio en la canción más popular del álbum, caso en estudio.", (10, 25)),
    Evento("Agencia bajo investigación fiscal por irregularidades contables.", (14, 32)),
    Evento("Salida de miembro confirmada: abandona el grupo por 'diferencias creativas'.", (20, 45)),
    Evento("Lesión grave de miembro principal: recuperación estimada de 6 meses.", (16, 36)),
    Evento("Incendio en sede central daña material inédito de próximo álbum.", (12, 28)),
    Evento("Álbum filtrado antes del lanzamiento oficial provoca crisis de imagen.", (10, 22)),
    Evento("Polémica por letra de canción considerada ofensiva en múltiples países.", (8, 20)),
    Evento("Gira cancelada en región clave por brote sanitario imprevisto.", (15, 33)),
    Evento("Caída masiva de seguidores tras declaraciones polémicas en entrevista.", (10, 24)),
    Evento("Fansite oficial hackeado: datos personales de fans expuestos.", (8, 18)),
    Evento("Rumores de conflictos internos graves entre miembros del grupo.", (9, 20)),
    Evento("Demanda legal de ex-agencia por incumplimiento de contrato millonario.", (12, 28)),
    Evento("Cancelación masiva de fans tras video de comportamiento en aeropuerto.", (14, 30)),
    Evento("Boicot organizado por fans rivales afecta ventas del nuevo single.", (8, 18)),
    Evento("Ventas de merchandising caen 40% en el último trimestre.", (10, 22)),
    Evento("Miembro acusado de bullying durante etapa de trainee genera crisis viral.", (16, 36)),
    Evento("Actuación criticada masivamente por falta de energía en festival clave.", (8, 18)),
    Evento("Fecha de comeback postergada indefinidamente sin explicación oficial.", (12, 26)),
    Evento("Agencia anuncia reestructuración y despidos masivos de personal creativo.", (14, 30)),
    Evento("Incidente en concierto deja fans heridos; agencia enfrenta demandas.", (18, 38)),
    Evento("Video viral muestra comportamiento inapropiado de miembro en evento privado.", (16, 35)),
    Evento("Accidente de tránsito durante gira deja miembros con lesiones que suspenden shows.", (12, 28)),
    Evento("Críticas internacionales por respuesta tardía a desastre natural en su país.", (10, 22)),
    Evento("Playlist de Spotify eliminada por conflicto de licencias con distribuidora.", (7, 15)),
    Evento("Retraso de dos meses en envío de álbumes físicos; fans piden reembolsos.", (6, 13)),
    Evento("Escándalo de reventa de entradas vinculado a la propia agencia.", (10, 24)),
    Evento("Miembro citado a declarar en juicio mediático de alto perfil.", (12, 26)),
    Evento("Ventas del álbum más bajas que el anterior por primera vez en su carrera.", (10, 22)),
    Evento("Estadio dañado por inclemencias climáticas cancela última fecha de gira.", (8, 18)),
    Evento("Agencia pierde batalla legal contra marca que usó su imagen sin permiso.", (9, 20)),
    Evento("Miembro expuesto fumando en aeropuerto; campaña publicitaria suspendida.", (8, 17)),
    Evento("Críticas virales por sincronía de labios en programa en vivo nacional.", (7, 15)),
    Evento("Ex-miembro revela detalles negativos del grupo en entrevista exclusiva.", (14, 30)),
    Evento("Problemas técnicos en concierto online dejan a 500.000 fans sin señal.", (10, 22)),
    Evento("Fan meeting cancelado por escasez de personal de seguridad certificado.", (6, 14)),
    Evento("Investigación de plagio abre proceso legal formal en tribunal coreano.", (12, 28)),
    Evento("Imagen de marca dañada tras asociación con empresa cuestionada éticamente.", (10, 22)),
    Evento("Gira europea reduce fechas por ventas insuficientes en mercados secundarios.", (8, 18)),
    Evento("Miembro en servicio militar enfrenta denuncia interna que se filtra a prensa.", (14, 30)),
    Evento("Agencia pierde a su productor estrella por conflictos creativos irresolubles.", (10, 22)),
    Evento("Actuación criticada en premiación por uso excesivo de playback.", (8, 16)),
    Evento("Acusaciones anónimas de trato abusivo a staff durante grabaciones.", (12, 26)),
    Evento("Estudio de grabación destruido por inundación; material de próximo álbum perdido.", (15, 33)),
    Evento("Miembro vinculado a escándalo político genera boicot en mercado asiático.", (16, 36)),
    Evento("Ventas del lightstick nuevo decepcionan por graves problemas de calidad.", (7, 15)),
    Evento("Comeback cancelado a último momento por desacuerdos creativos con la agencia.", (14, 30)),
    Evento("Denuncia de ex-trainee expone condiciones laborales abusivas en la empresa.", (18, 40)),
]
