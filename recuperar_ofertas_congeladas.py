#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recuperar_ofertas_congeladas.py
════════════════════════════════════════════════════════════════════════════════
Script de mantenimiento — UniverseBot V2.0

Libera las acciones congeladas por ofertas directas que quedaron 'activa'
para siempre (sin forma de rechazarlas antes del fix).

Qué hace:
  1. Lista todas las ofertas DIRECTAS (comprador_id IS NOT NULL) en estado
     'activa', separando las ya vencidas (> OFERTA_EXPIRA_HORAS) de las
     todavía vigentes.
  2. Te pregunta qué liberar:
       · Solo las vencidas  → estado 'expirada'
       · TODAS las directas activas → estado 'cancelada'
  3. Aplica el cambio solo tras tu confirmación explícita.

Es reversible: solo cambia la columna 'estado'. No borra filas ni mueve
acciones ni cosmos. Si te arrepentís, podés volver a poner 'activa' a mano.

USO (desde la carpeta raíz del bot, donde está database.py):
    python3 recuperar_ofertas_congeladas.py

Hacé un backup del .db antes, por las dudas:
    cp universebot.db universebot.db.bak
════════════════════════════════════════════════════════════════════════════════
"""
import sys
from datetime import datetime, timedelta

try:
    from database import db_manager
except Exception as exc:
    print(f"❌ No pude importar database.db_manager: {exc}")
    print("   Corré este script desde la carpeta raíz del bot (donde está database.py).")
    sys.exit(1)

OFERTA_EXPIRA_HORAS = 48


def _fmt(o: dict) -> str:
    return (
        f"  #{o['id']}  {o['simbolo']} ×{o['cantidad']} @ {float(o['precio_unit']):,.0f} ✨  |  "
        f"vendedor={o['vendedor_nombre']} ({o['vendedor_id']}) → "
        f"comprador={o.get('comprador_nombre') or '?'} ({o['comprador_id']})  |  "
        f"creada={o['fecha_creacion']}"
    )


def main() -> None:
    rows = db_manager.execute_query(
        """SELECT * FROM MERCADO_OFERTAS
           WHERE estado='activa' AND comprador_id IS NOT NULL
           ORDER BY fecha_creacion ASC"""
    )
    ofertas = [dict(r) for r in rows] if rows else []

    if not ofertas:
        print("✅ No hay ofertas directas activas. Nada que liberar.")
        return

    ahora  = datetime.now()
    limite = timedelta(hours=OFERTA_EXPIRA_HORAS)
    vencidas, vigentes = [], []
    for o in ofertas:
        try:
            creada = datetime.fromisoformat(o["fecha_creacion"])
            (vencidas if (ahora - creada > limite) else vigentes).append(o)
        except Exception:
            vencidas.append(o)  # fecha ilegible → tratarla como vencida

    print(f"\n📊 Ofertas directas ACTIVAS encontradas: {len(ofertas)}")
    print(f"   · Vencidas (> {OFERTA_EXPIRA_HORAS}h): {len(vencidas)}")
    print(f"   · Vigentes:                 {len(vigentes)}\n")

    if vencidas:
        print("── VENCIDAS ──")
        for o in vencidas:
            print(_fmt(o))
    if vigentes:
        print("\n── VIGENTES (aún dentro del plazo) ──")
        for o in vigentes:
            print(_fmt(o))

    print(
        "\n¿Qué querés liberar?\n"
        "  [1] Solo las VENCIDAS  → estado 'expirada'\n"
        "  [2] TODAS las directas activas → estado 'cancelada'\n"
        "  [0] Salir sin tocar nada"
    )
    opcion = input("Opción: ").strip()

    if opcion == "1":
        objetivo, nuevo_estado = vencidas, "expirada"
    elif opcion == "2":
        objetivo, nuevo_estado = ofertas, "cancelada"
    else:
        print("Sin cambios.")
        return

    if not objetivo:
        print("No hay ofertas en esa categoría. Sin cambios.")
        return

    conf = input(
        f"\nVas a marcar {len(objetivo)} oferta(s) como '{nuevo_estado}'. "
        f"Escribí SI para confirmar: "
    ).strip()
    if conf != "SI":
        print("Cancelado. Sin cambios.")
        return

    ts = ahora.isoformat()
    for o in objetivo:
        db_manager.execute_update(
            "UPDATE MERCADO_OFERTAS SET estado=?, fecha_cierre=? WHERE id=?",
            (nuevo_estado, ts, int(o["id"])),
        )
    print(f"\n✅ Listo. {len(objetivo)} oferta(s) marcadas como '{nuevo_estado}'.")
    print("   Las acciones de esos vendedores ya están disponibles de nuevo.")


if __name__ == "__main__":
    main()
