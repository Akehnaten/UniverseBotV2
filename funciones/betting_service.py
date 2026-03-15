# -*- coding: utf-8 -*-
"""
funciones/betting_service.py
═══════════════════════════════════════════════════════════════════════════════
Servicio de Apuestas Deportivas — Versión 2

Comandos soportados:
  /openbet  deporte/equipoA/equipoB/winA/draw/winB/YYYY-MM-DD HH:MM  (admins)
  /closebet mesa resultado                                             (admins)
  /newbet   mesa cosmos resultado                                      (users)
  /apuestas                                                            (users)
  /misapuestas                                                         (users)

Formato interno de participantes en BD (columna `participantes` de APUESTAS):
  JSON: [{"userID": 123, "username": "juan", "cosmos": 500, "opcion": "A"}, ...]
  Se almacena como texto JSON para evitar el frágil parseo manual anterior.
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from database import db_manager
from funciones.economy_service import economy_service

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS INTERNOS
# ─────────────────────────────────────────────────────────────────────────────

def _parse_participantes(raw: Optional[str]) -> List[Dict]:
    """
    Convierte el campo `participantes` de la BD a lista de dicts.
    Soporta tanto el formato JSON nuevo como el formato legacy
    `[(username,creditos,apuesta)]` para compatibilidad hacia atrás.
    Devuelve lista vacía si el campo es NULL / "None" / inválido.
    """
    if not raw or raw in ("None", "null", ""):
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    # ── Intentar parsear formato legacy ───────────────────────────────────────
    participantes: List[Dict] = []
    # Formato: [(username,creditos,apuesta),(username2,creditos2,apuesta2)]
    inner = raw.strip().lstrip("[").rstrip("]")
    for chunk in inner.split("),("):
        chunk = chunk.strip("()")
        parts = chunk.split(",")
        if len(parts) >= 3:
            try:
                participantes.append({
                    "userID":   None,
                    "username": parts[0].strip(),
                    "cosmos":   int(parts[1].strip()),
                    "opcion":   parts[2].strip()[0].upper(),
                })
            except (ValueError, IndexError):
                continue
    return participantes


def _dump_participantes(lista: List[Dict]) -> str:
    """Serializa la lista de participantes a JSON para almacenar en BD."""
    return json.dumps(lista, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# SERVICIO PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

class BettingService:
    """Servicio para manejar apuestas deportivas."""

    def __init__(self):
        self.db = db_manager

    # ── Crear apuesta (/openbet) ──────────────────────────────────────────────

    def create_bet(
        self,
        deporte: str,
        equipoA: str,
        equipoB: str,
        winA: float,
        draw: float,
        winB: float,
        horario: str,
    ) -> Tuple[bool, str]:
        """
        Crea una nueva mesa de apuestas.

        Args:
            deporte:  Nombre del deporte.
            equipoA:  Nombre del equipo / jugador A.
            equipoB:  Nombre del equipo / jugador B.
            winA:     Multiplicador si gana A  (ej: 1.5).
            draw:     Multiplicador si hay empate  (0 = no aplica).
            winB:     Multiplicador si gana B.
            horario:  Fecha y hora del evento "YYYY-MM-DD HH:MM".

        Returns:
            (True, betID_str) si se creó  |  (False, mensaje_de_error)
        """
        # Validar formato de horario
        try:
            datetime.strptime(horario, "%Y-%m-%d %H:%M")
        except ValueError:
            return False, (
                "❌ Formato de fecha inválido. Usa: <code>YYYY-MM-DD HH:MM</code>\n"
                "Ejemplo: <code>2025-11-25 21:45</code>"
            )

        try:
            self.db.execute_update(
                """
                INSERT INTO APUESTAS
                    (deporte, equipoA, equipoB, winA, draw, winB, horario, participantes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (deporte, equipoA, equipoB, float(winA), float(draw), float(winB),
                 horario, None),
            )
            # Obtener el betID recién insertado
            result = self.db.execute_query(
                "SELECT betID FROM APUESTAS WHERE horario = ? AND equipoA = ? AND equipoB = ? "
                "ORDER BY betID DESC LIMIT 1",
                (horario, equipoA, equipoB),
            )
            bet_id = result[0]["betID"] if result else "?"
            logger.info(
                f"[BET] Mesa #{bet_id} creada: {equipoA} vs {equipoB} ({deporte}) — {horario}"
            )
            return True, str(bet_id)
        except Exception as e:
            logger.error(f"[BET] Error creando apuesta: {e}")
            return False, f"❌ Error al crear la mesa: {e}"

    # ── Apostar (/newbet) ─────────────────────────────────────────────────────

    def place_bet(
        self,
        bet_id: int,
        user_id: int,
        username: str,
        cosmos: int,
        opcion: str,
    ) -> Tuple[bool, str]:
        """
        Registra la apuesta de un usuario en una mesa existente.

        Args:
            bet_id:   ID de la mesa.
            user_id:  Telegram ID del usuario.
            username: @username o nombre del usuario.
            cosmos:   Cantidad de cosmos a apostar (> 0).
            opcion:   "A", "D" o "B".

        Returns:
            (True, mensaje_ok) | (False, mensaje_error)
        """
        opcion = opcion.upper()
        if opcion not in ("A", "D", "B"):
            return False, "❌ Opción inválida. Usa <b>A</b> (equipo A), <b>D</b> (empate) o <b>B</b> (equipo B)."

        if cosmos <= 0:
            return False, "❌ La cantidad debe ser mayor a 0."

        # Obtener datos de la mesa
        rows = self.db.execute_query(
            "SELECT * FROM APUESTAS WHERE betID = ?", (bet_id,)
        )
        if not rows:
            return False, f"❌ No existe la mesa <b>#{bet_id}</b>."

        mesa = rows[0]

        # Verificar que el evento aún no haya comenzado
        try:
            hora_evento = datetime.strptime(str(mesa["horario"]), "%Y-%m-%d %H:%M")
        except ValueError:
            return False, "❌ La mesa tiene un formato de horario inválido."

        if hora_evento <= datetime.now():
            return False, (
                f"⏰ La mesa <b>#{bet_id}</b> ya no acepta apuestas.\n"
                f"El evento comenzó el {mesa['horario']}."
            )

        # Verificar que la opción tiene cuota > 0 (draw puede ser 0 si no aplica)
        cuota_map = {"A": float(mesa["winA"]), "D": float(mesa["draw"]), "B": float(mesa["winB"])}
        if cuota_map[opcion] <= 0:
            return False, f"❌ La opción <b>{opcion}</b> no está disponible en esta mesa (cuota 0)."

        # Verificar saldo
        if not economy_service.has_sufficient_balance(user_id, cosmos):
            saldo = economy_service.get_balance(user_id)
            return False, (
                f"❌ No tienes suficientes cosmos.\n"
                f"Apostás: {cosmos} | Saldo: {saldo}"
            )

        # Verificar si el usuario ya apostó en esta mesa
        participantes = _parse_participantes(mesa.get("participantes"))
        for p in participantes:
            if p.get("userID") == user_id:
                return False, (
                    f"⚠️ Ya apostaste en la mesa <b>#{bet_id}</b>.\n"
                    f"Opción anterior: <b>{p['opcion']}</b> — {p['cosmos']} cosmos."
                )

        # Descontar cosmos
        ok = economy_service.subtract_credits(user_id, cosmos, f"Apuesta mesa #{bet_id}")
        if not ok:
            return False, "❌ Error al descontar los cosmos. Inténtalo de nuevo."

        # Registrar participación
        participantes.append({
            "userID":   user_id,
            "username": username,
            "cosmos":   cosmos,
            "opcion":   opcion,
        })
        self.db.execute_update(
            "UPDATE APUESTAS SET participantes = ? WHERE betID = ?",
            (_dump_participantes(participantes), bet_id),
        )

        nombre_equipo = mesa["equipoA"] if opcion == "A" else (
            "Empate" if opcion == "D" else mesa["equipoB"]
        )
        cuota = cuota_map[opcion]
        ganancia_potencial = int(cosmos * cuota)

        logger.info(
            f"[BET] #{bet_id} — {username} ({user_id}) apostó {cosmos} en {opcion}"
        )
        return True, (
            f"✅ <b>Apuesta registrada</b>\n\n"
            f"🎲 Mesa #{bet_id}: {mesa['equipoA']} vs {mesa['equipoB']}\n"
            f"📌 Tu elección: <b>{nombre_equipo}</b> ({opcion})\n"
            f"💸 Apostado: <b>{cosmos} cosmos</b>\n"
            f"💰 Ganancia potencial: <b>{ganancia_potencial} cosmos</b> (×{cuota})"
        )

    # ── Cerrar mesa (/closebet) ───────────────────────────────────────────────

    def close_bet(
        self, bet_id: int, ganador: str
    ) -> Tuple[bool, List[Dict], str]:
        """
        Cierra una mesa, paga a los ganadores y elimina el registro.

        Args:
            bet_id:  ID de la mesa.
            ganador: "A", "D" o "B".

        Returns:
            (ok, lista_ganadores_con_ganancias, mensaje)
            Cada elemento de lista_ganadores: {"username", "cosmos_apostados", "ganancia"}
        """
        ganador = ganador.upper()
        if ganador not in ("A", "D", "B"):
            return False, [], "❌ Resultado inválido. Usa <b>A</b>, <b>D</b> o <b>B</b>."

        rows = self.db.execute_query(
            "SELECT * FROM APUESTAS WHERE betID = ?", (bet_id,)
        )
        if not rows:
            return False, [], f"❌ No existe la mesa <b>#{bet_id}</b>."

        mesa = rows[0]
        participantes = _parse_participantes(mesa.get("participantes"))

        if not participantes:
            # Sin participantes: solo eliminar
            self.db.execute_update("DELETE FROM APUESTAS WHERE betID = ?", (bet_id,))
            return True, [], f"ℹ️ Mesa #{bet_id} cerrada sin participantes."

        cuotas = {
            "A": float(mesa["winA"]),
            "D": float(mesa["draw"]),
            "B": float(mesa["winB"]),
        }
        cuota_ganador = cuotas[ganador]
        ganadores: List[Dict] = []

        pagos_fallidos: list[str] = []

        for p in participantes:
            uid       = p.get("userID")
            username  = p.get("username", "?")
            cosmos    = int(p.get("cosmos", 0))
            opcion    = p.get("opcion", "?").upper()

            if opcion == ganador and uid is not None:
                ganancia = int(cosmos * cuota_ganador)
                ok = economy_service.add_credits(
                    uid, ganancia, f"Premio apuesta mesa #{bet_id}"
                )
                if ok:
                    ganadores.append({
                        "username":        username,
                        "cosmos_apostados": cosmos,
                        "ganancia":        ganancia,
                        "cuota":           cuota_ganador,
                    })
                    logger.info(
                        f"[BET] #{bet_id} — ganador {username} ({uid}): "
                        f"+{ganancia} cosmos"
                    )
                else:
                    pagos_fallidos.append(username)
                    logger.error(
                        f"[BET] #{bet_id} — PAGO FALLIDO para {username} ({uid}): "
                        f"{ganancia} cosmos NO acreditados. Requiere intervención manual."
                    )

        # Solo eliminar la mesa si no hubo pagos fallidos.
        # Si fallaron pagos, el admin puede reintentar /closebet o compensar manualmente.
        if pagos_fallidos:
            nombres = ", ".join(pagos_fallidos)
            return (
                False,
                ganadores,
                f"⚠️ <b>Error parcial en mesa #{bet_id}</b>\n"
                f"No se pudo acreditar el premio a: <b>{nombres}</b>\n"
                f"La mesa NO fue eliminada. Revisá los logs y compensá manualmente.",
            )

        # Eliminar la mesa de BD solo cuando todos los pagos fueron exitosos.
        self.db.execute_update("DELETE FROM APUESTAS WHERE betID = ?", (bet_id,))

        nombre_ganador_label = {
            "A": mesa["equipoA"],
            "D": "Empate",
            "B": mesa["equipoB"],
        }.get(ganador, ganador)

        mensaje = (
            f"🏆 Mesa #{bet_id} cerrada\n"
            f"Resultado: <b>{nombre_ganador_label}</b> — "
            f"{len(ganadores)} ganador(es)"
        )
        logger.info(f"[BET] Mesa #{bet_id} cerrada. Ganador: {ganador}")
        return True, ganadores, mensaje

    # ── Apuestas disponibles (/apuestas) ─────────────────────────────────────

    def get_available_bets(self) -> List[Dict]:
        """
        Devuelve todas las mesas cuyo horario aún no ha llegado.
        Filtra en Python para evitar problemas de formato de fecha en SQLite.
        """
        rows = self.db.execute_query("SELECT * FROM APUESTAS ORDER BY betID")
        ahora = datetime.now()
        disponibles: List[Dict] = []
        for row in rows:
            try:
                hora = datetime.strptime(str(row["horario"]), "%Y-%m-%d %H:%M")
                if hora > ahora:
                    disponibles.append(dict(row))
            except (ValueError, TypeError):
                pass
        return disponibles

    # ── Mis apuestas (/misapuestas) ───────────────────────────────────────────

    def get_user_bets(self, user_id: int) -> List[Dict]:
        """
        Devuelve todas las mesas en las que el usuario tiene una apuesta activa.
        No filtra por horario (el usuario puede ver sus apuestas aunque el
        evento ya haya comenzado pero la mesa no se haya cerrado aún).
        """
        rows = self.db.execute_query("SELECT * FROM APUESTAS ORDER BY betID")
        mis_apuestas: List[Dict] = []

        for row in rows:
            participantes = _parse_participantes(row.get("participantes"))
            for p in participantes:
                if p.get("userID") == user_id:
                    entry = dict(row)
                    entry["_mi_opcion"]  = p["opcion"]
                    entry["_mi_cosmos"]  = p["cosmos"]
                    mis_apuestas.append(entry)
                    break

        return mis_apuestas

    # ── Formateo de mesa ──────────────────────────────────────────────────────

    def format_mesa(self, mesa: Dict, show_participantes: bool = False) -> str:
        """Formatea una mesa para mostrar al usuario."""
        bet_id   = mesa["betID"]
        deporte  = mesa["deporte"]
        equipoA  = mesa["equipoA"]
        equipoB  = mesa["equipoB"]
        winA     = float(mesa["winA"])
        draw     = float(mesa["draw"])
        winB     = float(mesa["winB"])
        horario  = mesa["horario"]

        participantes = _parse_participantes(mesa.get("participantes"))
        total_apostado = sum(p.get("cosmos", 0) for p in participantes)

        texto = (
            f"🎲 <b>Mesa #{bet_id} — {deporte}</b>\n"
            f"⚽ <b>{equipoA}</b> vs <b>{equipoB}</b>\n"
            f"📅 {horario}\n"
            f"📊 Cuotas:\n"
            f"   • {equipoA} gana (A): <b>{winA}×</b>\n"
        )
        if draw > 0:
            texto += f"   • Empate (D): <b>{draw}×</b>\n"
        texto += (
            f"   • {equipoB} gana (B): <b>{winB}×</b>\n"
            f"💰 Total apostado: <b>{total_apostado} cosmos</b>\n"
            f"👥 Participantes: <b>{len(participantes)}</b>"
        )
        return texto


# ── Instancia global ──────────────────────────────────────────────────────────
betting_service = BettingService()
