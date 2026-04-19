# -*- coding: utf-8 -*-
"""
funciones/photocards_service.py
INVENTARIOS: userID INTEGER, album VARCHAR(20), cartaID INTEGER
Una fila por copia. Sin columna cantidad.
"""

from __future__ import annotations

import os
import hashlib
import logging
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from database import db_manager

logger = logging.getLogger(__name__)

COSTO_SOBRE: int = 500

# Probabilidad de God Pack (todas legendarias). 0.003 = 0.3% ≈ 1 en 333 sobres.
PROB_GOD_PACK: float = 0.003


class Photocard:
    _EMOJI: Dict[str, str] = {"comun": "⚪", "rara": "🔵", "legendaria": "🟡"}

    def __init__(self, id_num: int, nombre: str, rareza: str, album: str, path: str) -> None:
        self.id     = id_num
        self.nombre = nombre
        self.rareza = rareza
        self.album  = album
        self.path   = path

    @property
    def es_video(self) -> bool:
        """True si la carta es un video (.mp4)."""
        return self.path.lower().endswith(".mp4")

    @property
    def nombre_display(self) -> str:
        """Nombre limpio: sin prefijo del album ni numeros finales."""
        import re
        nombre = self.nombre
        prefijo = re.escape(self.album.capitalize())
        nombre = re.sub(rf"^{prefijo}_?", "", nombre, flags=re.IGNORECASE)
        nombre = re.sub(r"\d+$", "", nombre)
        nombre = nombre.strip("_ ").replace("_", " ").strip()
        return nombre.capitalize() if nombre else self.nombre

    def __str__(self) -> str:
        return f"{self._EMOJI.get(self.rareza, '')} [#{self.id}] {self.nombre_display}"


class PhotocardsService:
    RAREZAS: Tuple[str, ...] = ("comun", "rara", "legendaria")

    # Pesos por rareza: orden debe coincidir con RAREZAS = (comun, rara, legendaria).
    # Se aplican igual a TODOS los álbumes — solo hay que tocarlos acá.
    PESOS_RAREZA: Tuple[int, ...] = (80, 19, 1)

    def __init__(self) -> None:
        self.db = db_manager

        # Ruta relativa al archivo del módulo, no al CWD del proceso.
        self.ruta_recursos = Path(__file__).resolve().parent.parent / "src"

        # config_albums se construye automáticamente en _descubrir_albums().
        # No hace falta tocar código al agregar una colección nueva:
        # alcanza con crear la carpeta src/<album>/{comun,rara,legendaria}/.
        self.config_albums: Dict[str, Dict] = {}

        self.precios_venta: Dict[str, int] = {
            "comun":      2,
            "rara":       COSTO_SOBRE // 2,
            "legendaria": COSTO_SOBRE * 10,
        }

        self.biblioteca: Dict[str, Dict[str, List[Photocard]]] = {}
        self.todas_las_cartas: Dict[int, Photocard] = {}

        self._migrar_inventarios()
        self._descubrir_albums()
        self._indexar_photocards()
        self._migrar_ids_secuenciales()
        self._crear_tabla_intercambios_photocards()

    # ══════════════════════════════════════════════════════════════════════════
    # MIGRACIÓN
    # ══════════════════════════════════════════════════════════════════════════

    def _migrar_inventarios(self) -> None:
        """
        Migración idempotente: convierte INVENTARIOS de 'una fila por copia'
        a 'una fila por (userID, cartaID) con columna cantidad'.
        Se ejecuta al iniciar el servicio; si ya está migrado, no hace nada.
        """
        try:
            info = self.db.execute_query("PRAGMA table_info(INVENTARIOS)")
            cols = []
            for row in info:
                r = {k.lower(): v for k, v in row.items()}
                cols.append(r.get("name", ""))
            if "cantidad" in cols:
                return  # ya migrado

            logger.info("[MIGRACIÓN] INVENTARIOS: consolidando filas y agregando columna cantidad…")
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("DROP TABLE IF EXISTS INVENTARIOS_NEW")
                cur.execute("""
                    CREATE TABLE INVENTARIOS_NEW (
                        userID   INTEGER,
                        album    VARCHAR(20),
                        cartaID  INTEGER,
                        cantidad INTEGER NOT NULL DEFAULT 1,
                        PRIMARY KEY (userID, cartaID)
                    )
                """)
                cur.execute("""
                    INSERT OR REPLACE INTO INVENTARIOS_NEW (userID, album, cartaID, cantidad)
                    SELECT userID, album, cartaID, COUNT(*) AS cantidad
                    FROM   INVENTARIOS
                    GROUP  BY userID, cartaID
                """)
                cur.execute("DROP TABLE INVENTARIOS")
                cur.execute("ALTER TABLE INVENTARIOS_NEW RENAME TO INVENTARIOS")
                conn.commit()
            logger.info("[MIGRACIÓN] INVENTARIOS migrado: columna 'cantidad' agregada y filas consolidadas.")
        except Exception as exc:
            logger.error(f"[MIGRACIÓN] Error en _migrar_inventarios: {exc}", exc_info=True)

    # ══════════════════════════════════════════════════════════════════════════
    # DESCUBRIMIENTO DE ÁLBUMES
    # ══════════════════════════════════════════════════════════════════════════

    def _migrar_ids_secuenciales(self) -> None:
        """
        Migración idempotente: detecta cartaIDs secuenciales del sistema anterior
        (enteros pequeños: 1, 2, 3…) en INVENTARIOS y los remapea a los IDs hash
        deterministas del sistema actual.

        El sistema anterior asignaba IDs correlativos recorriendo:
            sorted(config_albums) → RAREZAS → sorted(archivos)
        Esta función reconstruye ese mismo orden para obtener el mapping viejo→nuevo.

        Debe ejecutarse DESPUÉS de _indexar_photocards() porque necesita
        todas_las_cartas ya construido para calcular los nuevos IDs.

        Manejo de conflictos: si un usuario ya tiene el nuevo hash ID en DB
        (compró cartas con el sistema nuevo), se suman las cantidades con
        ON CONFLICT DO UPDATE para no perder nada.
        """
        if not self.todas_las_cartas:
            return

        # ── 1. Reconstruir mapping: id_secuencial → id_hash ──────────────────
        # Misma lógica de recorrido que usaba el sistema anterior.
        old_to_new: Dict[int, int] = {}
        seq = 1
        for album_key in sorted(self.config_albums):
            for rareza in self.RAREZAS:
                ruta = self.ruta_recursos / album_key / rareza
                if not ruta.exists():
                    continue
                archivos = sorted(
                    f for f in os.listdir(ruta)
                    if f.lower().endswith((".png", ".jpg", ".jpeg"))
                )
                for archivo in archivos:
                    nombre   = os.path.splitext(archivo)[0].capitalize()
                    new_id   = self._generar_carta_id(album_key, rareza, nombre)
                    old_to_new[seq] = new_id
                    seq += 1

        if not old_to_new:
            return

        # ── 2. Detectar filas en DB que aún tienen IDs secuenciales ──────────
        old_ids     = tuple(old_to_new.keys())
        placeholders = ",".join("?" * len(old_ids))
        try:
            filas_viejas = self.db.execute_query(
                f"SELECT DISTINCT cartaID FROM INVENTARIOS WHERE cartaID IN ({placeholders})",
                old_ids,
            )
        except Exception as exc:
            logger.error(f"[MIGRACIÓN IDs] Error al consultar IDs secuenciales: {exc}", exc_info=True)
            return

        if not filas_viejas:
            return  # nada que migrar — idempotente

        ids_a_migrar = [
            int({k.lower(): v for k, v in row.items()}["cartaid"])
            for row in filas_viejas
        ]
        logger.info(
            f"[MIGRACIÓN IDs] Detectados {len(ids_a_migrar)} cartaID(s) secuenciales "
            f"→ migrando a IDs hash: {ids_a_migrar}"
        )

        # ── 3. Remap: insert con merge + eliminar fila vieja ─────────────────
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                for old_id in ids_a_migrar:
                    new_id = old_to_new[old_id]
                    # Copiar la fila con el nuevo ID; si ya existe, sumar cantidad.
                    cur.execute(
                        """
                        INSERT INTO INVENTARIOS (userID, album, cartaID, cantidad)
                        SELECT userID, album, ?, cantidad
                        FROM   INVENTARIOS
                        WHERE  cartaID = ?
                        ON CONFLICT(userID, cartaID)
                            DO UPDATE SET cantidad = cantidad + excluded.cantidad
                        """,
                        (new_id, old_id),
                    )
                    cur.execute(
                        "DELETE FROM INVENTARIOS WHERE cartaID = ?",
                        (old_id,),
                    )
                conn.commit()
            logger.info("[MIGRACIÓN IDs] Completada: IDs secuenciales actualizados a hash.")
        except Exception as exc:
            logger.error(f"[MIGRACIÓN IDs] Error al migrar filas: {exc}", exc_info=True)

    def _descubrir_albums(self) -> None:
        """
        Escanea src/ y registra como álbum cada subdirectorio que contenga
        al menos una de las carpetas de rareza (comun/rara/legendaria).
        No hace falta tocar el código al agregar una colección nueva.
        """
        if not self.ruta_recursos.exists():
            logger.warning(f"⚠️  ruta_recursos no existe: {self.ruta_recursos}")
            return

        for entrada in sorted(self.ruta_recursos.iterdir()):
            if not entrada.is_dir():
                continue
            album_key = entrada.name.lower()
            # Solo registrar si tiene al menos una subcarpeta de rareza
            tiene_rareza = any((entrada / r).is_dir() for r in self.RAREZAS)
            if not tiene_rareza:
                continue
            self.config_albums[album_key] = {
                "name":         entrada.name.capitalize(),
                "weights":      list(self.PESOS_RAREZA),
                "total_cartas": 0,
            }
            logger.info(f"📁 Álbum descubierto: '{album_key}'")

        if not self.config_albums:
            logger.warning("⚠️  No se encontró ningún álbum en src/")
        else:
            logger.info(f"📚 {len(self.config_albums)} álbum(es) registrados: {list(self.config_albums)}")

    # ══════════════════════════════════════════════════════════════════════════
    # INDEXACIÓN
    # Recorre src/<album>/<rareza>/*.jpg|png
    # Asigna IDs secuenciales y guarda en todas_las_cartas.
    # total_cartas = cantidad de archivos encontrados por álbum.
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _generar_carta_id(album: str, rareza: str, nombre: str) -> int:
        """
        ID determinista basado en (album, rareza, nombre).
        Estable entre reinicios independientemente del orden de los álbumes.
        Rango: 1 – 2_147_483_647 (INT positivo SQLite).
        Colisiones son estadísticamente imposibles para colecciones pequeñas.
        """
        clave = f"{album}:{rareza}:{nombre}".lower()
        return int(hashlib.md5(clave.encode()).hexdigest()[:8], 16) % 2_147_483_647 + 1

    def _indexar_photocards(self) -> None:
        colisiones = 0

        for album_key in self.config_albums:
            self.biblioteca[album_key] = {r: [] for r in self.RAREZAS}

            for rareza in self.RAREZAS:
                ruta = self.ruta_recursos / album_key / rareza
                if not ruta.exists():
                    logger.warning(f"⚠️  Ruta no existe: {ruta}")
                    continue
                archivos = sorted(
                    f for f in os.listdir(ruta)
                    if f.lower().endswith((".png", ".jpg", ".jpeg"))
                )
                for archivo in archivos:
                    nombre = os.path.splitext(archivo)[0].capitalize()
                    carta_id = self._generar_carta_id(album_key, rareza, nombre)
                    if carta_id in self.todas_las_cartas:
                        colisiones += 1
                        logger.error(
                            f"💥 Colisión de ID {carta_id} entre "
                            f"'{self.todas_las_cartas[carta_id].nombre}' y '{nombre}' — revisá los nombres."
                        )
                        continue
                    pc = Photocard(
                        id_num=carta_id,
                        nombre=nombre,
                        rareza=rareza,
                        album=album_key,
                        path=str(ruta / archivo),
                    )
                    self.biblioteca[album_key][rareza].append(pc)
                    self.todas_las_cartas[carta_id] = pc

            total = sum(len(v) for v in self.biblioteca[album_key].values())
            self.config_albums[album_key]["total_cartas"] = total
            logger.info(f"📂 '{album_key}': {total} cartas indexadas")

        if colisiones:
            logger.warning(f"⚠️  {colisiones} colisión(es) de ID detectadas durante el indexado.")
        logger.info(f"📦 Total global: {len(self.todas_las_cartas)} photocards indexadas.")

    # ══════════════════════════════════════════════════════════════════════════
    # CONSULTAS — simples y directas
    # ══════════════════════════════════════════════════════════════════════════

    def get_total_album(self, album_key: str) -> int:
        """Total de cartas únicas en el álbum, contado al indexar."""
        return self.config_albums.get(album_key, {}).get("total_cartas", 0)

    def get_albums_usuario(self, user_id: int) -> List[str]:
        """
        Álbumes distintos del usuario.
        Lee la columna 'album' directamente en SQL — no depende del
        índice en memoria (todas_las_cartas). Funciona aunque las
        imágenes no estén disponibles al arrancar el bot.
        """
        try:
            rows = self.db.execute_query(
                "SELECT DISTINCT album FROM INVENTARIOS WHERE userID = ?",
                (user_id,),
            )
            albums: set = set()
            for row in rows:
                r   = {k.lower(): v for k, v in row.items()}
                alb = r.get("album")
                if alb and alb in self.config_albums:
                    albums.add(alb)
            logger.info(f"get_albums_usuario uid={user_id} → {albums}")
            return sorted(albums)
        except Exception as exc:
            logger.error(f"❌ get_albums_usuario: {exc}")
            return []

    def get_cartas_usuario_en_album(self, user_id: int, album_key: str) -> Dict[int, int]:
        """
        {cartaID: cantidad} para el usuario en el álbum dado.
        Filtra por la columna 'album' directamente en SQL — no depende del
        índice en memoria. SUM(cantidad) es compatible con el esquema anterior
        (una fila por copia) y el actual (columna cantidad).
        """
        try:
            rows = self.db.execute_query(
                """
                SELECT cartaID, SUM(cantidad) AS cantidad
                FROM   INVENTARIOS
                WHERE  userID = ? AND album = ?
                GROUP  BY cartaID
                """,
                (user_id, album_key),
            )
            result: Dict[int, int] = {}
            for row in rows:
                r    = {k.lower(): v for k, v in row.items()}
                cid  = r.get("cartaid")
                cant = r.get("cantidad", 0)
                if cid is not None:
                    result[int(cid)] = int(cant)
            logger.info(f"get_cartas_usuario_en_album uid={user_id} album={album_key} → {len(result)} cartas")
            return result
        except Exception as exc:
            logger.error(f"❌ get_cartas_usuario_en_album: {exc}")
            return {}

    def get_carta_by_id(self, carta_id: int) -> Optional[Photocard]:
        return self.todas_las_cartas.get(carta_id)

    def get_cantidad_carta(self, user_id: int, carta_id: int) -> int:
        """SUM(cantidad) con `or 0` maneja el NULL que SQLite devuelve si no hay filas."""
        try:
            rows = self.db.execute_query(
                "SELECT SUM(cantidad) AS c FROM INVENTARIOS WHERE userID = ? AND cartaID = ?",
                (user_id, carta_id),
            )
            if not rows:
                return 0
            r = {k.lower(): v for k, v in rows[0].items()}
            return int(r.get("c") or 0)
        except Exception as exc:
            logger.error(f"❌ get_cantidad_carta: {exc}")
            return 0

    # ══════════════════════════════════════════════════════════════════════════
    # MODIFICACIONES
    # ══════════════════════════════════════════════════════════════════════════

    def agregar_photocard(self, user_id: int, carta_id: int, cantidad: int = 1) -> Tuple[bool, str]:
        """
        UPSERT: inserta si no existe, o incrementa cantidad si ya existe.
        Una sola operación SQL en lugar de N INSERTs.
        Requiere el schema con PRIMARY KEY (userID, cartaID).
        """
        carta = self.get_carta_by_id(carta_id)
        if carta is None:
            return False, f"Carta #{carta_id} no existe en el índice."
        try:
            self.db.execute_update(
                """
                INSERT INTO INVENTARIOS (userID, album, cartaID, cantidad)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(userID, cartaID) DO UPDATE SET cantidad = cantidad + excluded.cantidad
                """,
                (user_id, carta.album, carta_id, cantidad),
            )
            return True, f"✅ +{cantidad}× {carta.nombre}"
        except Exception as exc:
            logger.error(f"❌ agregar_photocard: {exc}")
            return False, f"Error: {exc}"

    def vender_photocard(self, user_id: int, carta_id: int, cantidad: int) -> Tuple[bool, str, int]:
        disponible = self.get_cantidad_carta(user_id, carta_id)
        if disponible < cantidad:
            return False, "No tenés suficientes cartas.", 0
        carta = self.get_carta_by_id(carta_id)
        if carta is None:
            return False, "Carta no encontrada.", 0
        precio_unit  = self.precios_venta.get(carta.rareza, 2)
        cosmos_total = precio_unit * cantidad
        try:
            self.db.execute_update(
                "UPDATE INVENTARIOS SET cantidad = cantidad - ? WHERE userID = ? AND cartaID = ?",
                (cantidad, user_id, carta_id),
            )
            self.db.execute_update(
                "DELETE FROM INVENTARIOS WHERE userID = ? AND cartaID = ? AND cantidad <= 0",
                (user_id, carta_id),
            )
            from funciones import economy_service
            economy_service.add_credits(user_id, cosmos_total, f"Venta {cantidad}× {carta.nombre}")
            return True, f"✅ Vendiste {cantidad}× {carta.nombre}\n💰 +{cosmos_total} cosmos", cosmos_total
        except Exception as exc:
            logger.error(f"❌ vender_photocard: {exc}")
            return False, f"Error: {exc}", 0

    # ══════════════════════════════════════════════════════════════════════════
    # SOBRES
    # ══════════════════════════════════════════════════════════════════════════

    def abrir_sobre(
        self, user_id: int, album: str, cantidad: int = 5
    ) -> Tuple[bool, str, List[Photocard], bool]:
        """
        Abre un sobre.
        Retorna (exito, mensaje, cartas, god_pack).
        god_pack=True significa que todas las cartas son legendarias (evento raro).
        """
        if album not in self.config_albums or album not in self.biblioteca:
            return False, "Álbum no disponible.", [], False

        nombre_a = self.config_albums[album]["name"]
        pool_leg = self.biblioteca[album].get("legendaria", [])

        # ── Tirar God Pack ────────────────────────────────────────────────────
        god_pack = (
            len(pool_leg) > 0
            and random.random() < PROB_GOD_PACK
        )

        obtenidas: List[Photocard] = []
        try:
            if god_pack:
                # Todas las cartas son legendarias (con repetición permitida)
                for _ in range(cantidad):
                    carta = random.choice(pool_leg)
                    obtenidas.append(carta)
                    self.agregar_photocard(user_id, carta.id, 1)
            else:
                weights = self.config_albums[album].get("weights", [80, 19, 1])
                for _ in range(cantidad):
                    rareza = random.choices(list(self.RAREZAS), weights=weights)[0]
                    pool   = self.biblioteca[album][rareza]
                    if not pool:
                        continue
                    carta = random.choice(pool)
                    obtenidas.append(carta)
                    self.agregar_photocard(user_id, carta.id, 1)

            if not obtenidas:
                return False, "No se encontraron cartas.", [], False

            lineas = "\n".join(str(c) for c in obtenidas)
            if god_pack:
                msg = f"✨ ¡GOD PACK de {nombre_a}!\n\n{lineas}"
            else:
                msg = f"📦 ¡Abriste un sobre de {nombre_a}!\n\n{lineas}"
            return True, msg, obtenidas, god_pack

        except Exception as exc:
            logger.error(f"❌ abrir_sobre: {exc}")
            return False, f"Error: {exc}", [], False

    def obtener_albums_disponibles(self) -> List[Dict]:
        return [
            {"key": k, "name": v["name"], "total_cartas": v.get("total_cartas", 0)}
            for k, v in self.config_albums.items()
        ]
    # ══════════════════════════════════════════════════════════════════════════
    # INTERCAMBIOS DE PHOTOCARDS — mercado P2P
    # ══════════════════════════════════════════════════════════════════════════

    def _crear_tabla_intercambios_photocards(self) -> None:
        """Crea INTERCAMBIOS_PHOTOCARDS si no existe. Idempotente."""
        try:
            with self.db.get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS INTERCAMBIOS_PHOTOCARDS (
                        id               INTEGER PRIMARY KEY AUTOINCREMENT,
                        ofertante_id     INTEGER NOT NULL,
                        carta_ofrecida   INTEGER NOT NULL,
                        carta_solicitada INTEGER,
                        destinatario_id  INTEGER,
                        estado           TEXT    NOT NULL DEFAULT 'disponible',
                        timestamp        REAL    NOT NULL
                    )
                """)
                conn.commit()
        except Exception as exc:
            logger.error(f"❌ _crear_tabla_intercambios_photocards: {exc}", exc_info=True)

    def listar_photocard_para_intercambio(
        self,
        ofertante_id: int,
        carta_id: int,
        carta_solicitada: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Lista una photocard en el mercado público de intercambios.
        Una misma carta solo puede tener un listado activo a la vez.

        Returns:
            (exito, mensaje)
        """
        import time as _time

        if self.get_cantidad_carta(ofertante_id, carta_id) < 1:
            return False, "❌ No tenés esa carta."
        try:
            rows = self.db.execute_query(
                """
                SELECT id FROM INTERCAMBIOS_PHOTOCARDS
                WHERE  ofertante_id = ? AND carta_ofrecida = ? AND estado = 'disponible'
                """,
                (ofertante_id, carta_id),
            )
            if rows:
                return False, "⚠️ Ya tenés esa carta listada para intercambio."
            self.db.execute_update(
                """
                INSERT INTO INTERCAMBIOS_PHOTOCARDS
                    (ofertante_id, carta_ofrecida, carta_solicitada, destinatario_id, estado, timestamp)
                VALUES (?, ?, ?, NULL, 'disponible', ?)
                """,
                (ofertante_id, carta_id, carta_solicitada, _time.time()),
            )
            return True, "✅ Carta listada en el mercado de intercambios."
        except Exception as exc:
            logger.error(f"❌ listar_photocard_para_intercambio: {exc}", exc_info=True)
            return False, f"❌ Error: {exc}"

    def cancelar_listado_photocard(self, ofertante_id: int, listado_id: int) -> Tuple[bool, str]:
        """
        Cancela un listado activo del ofertante.

        Returns:
            (exito, mensaje)
        """
        try:
            rows = self.db.execute_query(
                """
                SELECT id FROM INTERCAMBIOS_PHOTOCARDS
                WHERE  id = ? AND ofertante_id = ? AND estado = 'disponible'
                """,
                (listado_id, ofertante_id),
            )
            if not rows:
                return False, "❌ Listado no encontrado o ya no está activo."
            self.db.execute_update(
                "UPDATE INTERCAMBIOS_PHOTOCARDS SET estado = 'cancelado' WHERE id = ?",
                (listado_id,),
            )
            return True, "✅ Listado cancelado."
        except Exception as exc:
            logger.error(f"❌ cancelar_listado_photocard: {exc}", exc_info=True)
            return False, f"❌ Error: {exc}"

    def obtener_mercado_photocards(self, user_id: int) -> List[Dict]:
        """
        Listados disponibles de otros usuarios, ordenados por recientes.
        Excluye los propios para no mostrárselos al mismo ofertante.

        Returns:
            Lista de dicts con claves: id, ofertante_id, carta_ofrecida,
            carta_solicitada, timestamp.
        """
        try:
            rows = self.db.execute_query(
                """
                SELECT id, ofertante_id, carta_ofrecida, carta_solicitada, timestamp
                FROM   INTERCAMBIOS_PHOTOCARDS
                WHERE  estado = 'disponible' AND ofertante_id != ?
                ORDER  BY timestamp DESC
                LIMIT  20
                """,
                (user_id,),
            )
            result: List[Dict] = []
            for row in rows:
                r = {k.lower(): v for k, v in row.items()}
                result.append({
                    "id":               int(r["id"]),
                    "ofertante_id":     int(r["ofertante_id"]),
                    "carta_ofrecida":   int(r["carta_ofrecida"]),
                    "carta_solicitada": r.get("carta_solicitada"),
                    "timestamp":        r.get("timestamp", 0.0),
                })
            return result
        except Exception as exc:
            logger.error(f"❌ obtener_mercado_photocards: {exc}", exc_info=True)
            return []

    def obtener_mis_listados_photocards(self, user_id: int) -> List[Dict]:
        """
        Listados activos del propio usuario.

        Returns:
            Lista de dicts con claves: id, carta_ofrecida, carta_solicitada.
        """
        try:
            rows = self.db.execute_query(
                """
                SELECT id, carta_ofrecida, carta_solicitada
                FROM   INTERCAMBIOS_PHOTOCARDS
                WHERE  ofertante_id = ? AND estado = 'disponible'
                ORDER  BY timestamp DESC
                """,
                (user_id,),
            )
            result: List[Dict] = []
            for row in rows:
                r = {k.lower(): v for k, v in row.items()}
                result.append({
                    "id":               int(r["id"]),
                    "carta_ofrecida":   int(r["carta_ofrecida"]),
                    "carta_solicitada": r.get("carta_solicitada"),
                })
            return result
        except Exception as exc:
            logger.error(f"❌ obtener_mis_listados_photocards: {exc}", exc_info=True)
            return []

    def aceptar_listado_photocard(
        self,
        listado_id: int,
        aceptante_id: int,
        carta_del_aceptante: int,
    ) -> Tuple[bool, str]:
        """
        Ejecuta el intercambio: el aceptante entrega ``carta_del_aceptante``
        y recibe ``carta_ofrecida`` del listado. Ambas partes pierden
        una copia de su carta y ganan una copia de la del otro.

        Pre-condiciones verificadas internamente:
          - El listado sigue activo.
          - Ninguno puede aceptar su propio listado.
          - Si el listado tenía ``carta_solicitada``, debe coincidir.
          - Ambos usuarios deben poseer sus respectivas cartas.

        Returns:
            (exito, mensaje_html)
        """
        try:
            rows = self.db.execute_query(
                "SELECT * FROM INTERCAMBIOS_PHOTOCARDS WHERE id = ? AND estado = 'disponible'",
                (listado_id,),
            )
            if not rows:
                return False, "❌ Ese listado ya no está disponible."

            row          = {k.lower(): v for k, v in rows[0].items()}
            ofertante_id = int(row["ofertante_id"])
            carta_ofrecida = int(row["carta_ofrecida"])
            carta_solicitada = row.get("carta_solicitada")
            if carta_solicitada is not None:
                carta_solicitada = int(carta_solicitada)

            if ofertante_id == aceptante_id:
                return False, "❌ No podés aceptar tu propio listado."

            # Validar carta específica solicitada
            if carta_solicitada is not None and carta_del_aceptante != carta_solicitada:
                pc_sol = self.get_carta_by_id(carta_solicitada)
                nombre_sol = pc_sol.nombre if pc_sol else f"#{carta_solicitada}"
                return False, f"❌ Este listado requiere <b>{nombre_sol}</b>."

            # Verificar disponibilidad en inventario
            if self.get_cantidad_carta(ofertante_id, carta_ofrecida) < 1:
                return False, "❌ El ofertante ya no tiene esa carta."
            if self.get_cantidad_carta(aceptante_id, carta_del_aceptante) < 1:
                return False, "❌ No tenés esa carta."

            # ── Ejecutar el swap ──────────────────────────────────────────────
            # Ofertante entrega carta_ofrecida
            self.db.execute_update(
                "UPDATE INVENTARIOS SET cantidad = cantidad - 1 WHERE userID = ? AND cartaID = ?",
                (ofertante_id, carta_ofrecida),
            )
            self.db.execute_update(
                "DELETE FROM INVENTARIOS WHERE userID = ? AND cartaID = ? AND cantidad <= 0",
                (ofertante_id, carta_ofrecida),
            )
            # Aceptante entrega carta_del_aceptante
            self.db.execute_update(
                "UPDATE INVENTARIOS SET cantidad = cantidad - 1 WHERE userID = ? AND cartaID = ?",
                (aceptante_id, carta_del_aceptante),
            )
            self.db.execute_update(
                "DELETE FROM INVENTARIOS WHERE userID = ? AND cartaID = ? AND cantidad <= 0",
                (aceptante_id, carta_del_aceptante),
            )
            # Ofertante recibe carta del aceptante
            self.agregar_photocard(ofertante_id, carta_del_aceptante, 1)
            # Aceptante recibe carta del ofertante
            self.agregar_photocard(aceptante_id, carta_ofrecida, 1)

            # Marcar como completado
            self.db.execute_update(
                "UPDATE INTERCAMBIOS_PHOTOCARDS SET estado = 'completado', destinatario_id = ? WHERE id = ?",
                (aceptante_id, listado_id),
            )

            pc1 = self.get_carta_by_id(carta_ofrecida)
            pc2 = self.get_carta_by_id(carta_del_aceptante)
            n1  = pc1.nombre if pc1 else f"#{carta_ofrecida}"
            n2  = pc2.nombre if pc2 else f"#{carta_del_aceptante}"
            logger.info(
                f"[TRADE PC] Intercambio #{listado_id} completado: "
                f"{ofertante_id}({n1}) ↔ {aceptante_id}({n2})"
            )
            return True, f"✅ ¡Intercambio completado!\n<b>{n1}</b> ↔ <b>{n2}</b>"

        except Exception as exc:
            logger.error(f"❌ aceptar_listado_photocard: {exc}", exc_info=True)
            return False, f"❌ Error: {exc}"

    def ejecutar_swap_directo(
        self,
        oferente_id: int,
        carta_a_id: int,
        receptor_id: int,
        carta_b_id: int,
    ) -> Tuple[bool, str]:
        """
        Ejecuta un intercambio directo P2P entre dos usuarios.

        A entrega carta_a_id → B.
        B entrega carta_b_id → A.

        No usa la tabla INTERCAMBIOS_PHOTOCARDS (ese flujo es para el
        mercado público). Este método trabaja directamente sobre INVENTARIOS.

        Pre-condiciones verificadas:
          · Ninguno puede intercambiar con sí mismo.
          · Ambos deben poseer al menos 1 copia de su carta.

        Returns:
            (exito, mensaje_html)
        """
        if oferente_id == receptor_id:
            return False, "No podés intercambiar con vos mismo."

        if self.get_cantidad_carta(oferente_id, carta_a_id) < 1:
            return False, "❌ El oferente ya no tiene su carta."
        if self.get_cantidad_carta(receptor_id, carta_b_id) < 1:
            return False, "❌ El receptor ya no tiene su carta."

        try:
            # A entrega carta_a_id
            self.db.execute_update(
                "UPDATE INVENTARIOS SET cantidad = cantidad - 1 WHERE userID = ? AND cartaID = ?",
                (oferente_id, carta_a_id),
            )
            self.db.execute_update(
                "DELETE FROM INVENTARIOS WHERE userID = ? AND cartaID = ? AND cantidad <= 0",
                (oferente_id, carta_a_id),
            )
            # B entrega carta_b_id
            self.db.execute_update(
                "UPDATE INVENTARIOS SET cantidad = cantidad - 1 WHERE userID = ? AND cartaID = ?",
                (receptor_id, carta_b_id),
            )
            self.db.execute_update(
                "DELETE FROM INVENTARIOS WHERE userID = ? AND cartaID = ? AND cantidad <= 0",
                (receptor_id, carta_b_id),
            )
            # A recibe carta_b_id
            self.agregar_photocard(oferente_id, carta_b_id, 1)
            # B recibe carta_a_id
            self.agregar_photocard(receptor_id, carta_a_id, 1)

            pc_a = self.get_carta_by_id(carta_a_id)
            pc_b = self.get_carta_by_id(carta_b_id)
            nom_a = pc_a.nombre if pc_a else f"#{carta_a_id}"
            nom_b = pc_b.nombre if pc_b else f"#{carta_b_id}"

            logger.info(
                f"[SWAP DIRECTO] {oferente_id}({nom_a}) ↔ {receptor_id}({nom_b})"
            )
            return (
                True,
                f"✅ <b>¡Intercambio completado!</b>\n\n"
                f"<b>{nom_a}</b> ↔ <b>{nom_b}</b>\n\n"
                f"Cada uno recibió la carta del otro. 🎉",
            )
        except Exception as exc:
            logger.error(f"❌ ejecutar_swap_directo: {exc}", exc_info=True)
            return False, f"Error interno: {exc}"

photocards_service = PhotocardsService()