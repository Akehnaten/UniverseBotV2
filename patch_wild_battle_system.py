#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_wild_battle_system.py
═══════════════════════════
Aplica todos los fixes de habilidades a wild_battle_system.py.

Uso:
    python3 patch_wild_battle_system.py [ruta/al/wild_battle_system.py]

Si no se pasa ruta, asume pokemon/wild_battle_system.py relativo al CWD.
Crea una copia de seguridad automática en <archivo>.bak antes de modificar.

Cambios aplicados:
    1. Importa las funciones nuevas de battle_engine
       (get_peso_pokemon, calcular_poder_lowkick, calcular_poder_heavyslam,
        _LOWKICK_MOVES, _HEAVYSLAM_MOVES, tiene_magic_guard, _roll_num_hits)
    2. Magic Guard en _apply_residual_effects
       (bloquea daño de veneno/quemadura/tóxico/clima en el jugador)
    3. Low Kick / Heavy Slam en _execute_wild_turn
       (poder calculado dinámicamente según peso del jugador / salvaje)
    4. Intimidación en _on_pokemon_enter
       (baja el Ataque del salvaje al entrar el Pokémon del jugador)
"""
import sys
import shutil
import ast
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# PARCHES
# Cada parche es una tupla (descripcion, old_str, new_str).
# Se aplica con str.replace(..., 1) — sólo la primera ocurrencia.
# ─────────────────────────────────────────────────────────────────────────────
PATCHES: list[tuple[str, str, str]] = [

    # ── 1. Añadir imports de battle_engine ────────────────────────────────────
    (
        "Imports: get_peso_pokemon / tiene_magic_guard / _roll_num_hits",
        "    # Adaptación al nuevo sistema\n    UniversalSide,",
        """    # Adaptación al nuevo sistema
    UniversalSide,
    # ── Peso, Magic Guard, Skill Link (añadidos en el fix de habilidades) ──
    get_peso_pokemon,
    calcular_poder_lowkick,
    calcular_poder_heavyslam,
    _LOWKICK_MOVES,
    _HEAVYSLAM_MOVES,
    tiene_magic_guard,""",
    ),

    # ── 2. Magic Guard en _apply_residual_effects ─────────────────────────────
    (
        "Magic Guard en _apply_residual_effects",
        """\
    # ── Aplicar resultado a side_b (jugador — persiste en BD) ────────────────
    fx_b = result.side_b
    if player and fx_b.hp_delta != 0:
        # CRÍTICO: no curar ni dañar a un Pokémon ya debilitado (hp == 0).
        # Si hp_delta > 0 y hp_actual == 0, el Pokémon está K.O. y no debe
        # resucitarse con curación de campo de hierba o efectos similares.
        if player.hp_actual > 0 or fx_b.hp_delta < 0:
            new_hp = max(0, min(p_max_hp, player.hp_actual + fx_b.hp_delta))
            player.hp_actual = new_hp
            try:
                db_manager.execute_update(
                    "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                    (new_hp, battle.player_pokemon_id),
                )
            except Exception as _e:
                logger.error(f"Error residual HP jugador: {_e}")""",
        """\
    # ── Aplicar resultado a side_b (jugador — persiste en BD) ────────────────
    fx_b = result.side_b
    if player and fx_b.hp_delta != 0:
        # CRÍTICO: no curar ni dañar a un Pokémon ya debilitado (hp == 0).
        if player.hp_actual > 0 or fx_b.hp_delta < 0:
            # Magic Guard: el jugador es inmune a daño indirecto (veneno, clima…)
            _player_hab = getattr(player, "habilidad", "") or ""
            if fx_b.hp_delta < 0 and tiene_magic_guard(_player_hab):
                pass  # daño indirecto bloqueado por Magic Guard
            else:
                new_hp = max(0, min(p_max_hp, player.hp_actual + fx_b.hp_delta))
                player.hp_actual = new_hp
                try:
                    db_manager.execute_update(
                        "UPDATE POKEMON_USUARIO SET hp_actual = ? WHERE id_unico = ?",
                        (new_hp, battle.player_pokemon_id),
                    )
                except Exception as _e:
                    logger.error(f"Error residual HP jugador: {_e}")""",
    ),

    # ── 3. Low Kick / Heavy Slam en _execute_wild_turn ────────────────────────
    (
        "Low Kick / Heavy Slam en _execute_wild_turn",
        """\
            # ── Movimiento de estado ──────────────────────────────────────────────
            if categoria == "Estado" or poder == 0:""",
        """\
            # ── Poder variable por peso (Low Kick / Heavy Slam del salvaje) ─────
            if move_key_wild in _LOWKICK_MOVES:
                _def_peso_p = get_peso_pokemon(player.pokemonID)
                poder = calcular_poder_lowkick(_def_peso_p)
            elif move_key_wild in _HEAVYSLAM_MOVES:
                _atk_peso_w = get_peso_pokemon(wild.pokemon_id)
                _def_peso_p = get_peso_pokemon(player.pokemonID)
                poder = calcular_poder_heavyslam(_atk_peso_w, _def_peso_p)

            # ── Movimiento de estado ──────────────────────────────────────────────
            if categoria == "Estado" or poder == 0:""",
    ),

    # ── 4. Intimidación en _on_pokemon_enter ──────────────────────────────────
    (
        "Intimidación en _on_pokemon_enter",
        """\
            if hab_str == "impostor":""",
        """\
            # ── Intimidación: baja Ataque del salvaje 1 etapa ─────────────────
            if hab_str in ("intimidacion", "intimidation"):
                wild_p = getattr(battle, "wild_pokemon", None)
                if wild_p:
                    _old_stg = battle.wild_stat_stages.get("atq", 0)
                    battle.wild_stat_stages["atq"] = max(-6, _old_stg - 1)
                    if battle.wild_stat_stages["atq"] < _old_stg:
                        log.append(
                            f"  😤 ¡<b>Intimidación</b> de {nombre} bajó el "
                            f"Ataque de {wild_p.nombre}!\\n"
                        )

            if hab_str == "impostor":""",
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "pokemon/wild_battle_system.py")

    if not target.exists():
        print(f"❌  Archivo no encontrado: {target}")
        sys.exit(1)

    # Backup
    backup = target.with_suffix(".py.bak")
    shutil.copy2(target, backup)
    print(f"📦  Backup guardado en: {backup}")

    src = target.read_text(encoding="utf-8")
    errors = 0

    for descripcion, old, new in PATCHES:
        if old in src:
            src = src.replace(old, new, 1)
            print(f"  ✅  {descripcion}")
        else:
            print(f"  ⚠️   {descripcion}  — bloque no encontrado (puede ya estar aplicado)")
            errors += 1

    # Validar sintaxis antes de escribir
    try:
        ast.parse(src)
    except SyntaxError as e:
        print(f"\n❌  Error de sintaxis tras los parches: {e}")
        print(f"    El archivo original NO fue modificado. Revisa el backup: {backup}")
        sys.exit(1)

    target.write_text(src, encoding="utf-8")
    print(f"\n{'✅  Todos los parches aplicados.' if errors == 0 else f'⚠️   {errors} parche(s) omitidos (probablemente ya estaban).'}")
    print(f"✅  Archivo escrito: {target}")


if __name__ == "__main__":
    main()
