# -*- coding: utf-8 -*-
"""
handlers/photocards_handlers.py
Solo el dueño del mensaje puede usar los botones.
"""

from __future__ import annotations

import io
import os
import logging
from typing import List, Optional

import telebot
from telebot import types

from funciones import economy_service
from funciones.photocards_service import photocards_service, COSTO_SOBRE
from database import db_manager

logger = logging.getLogger(__name__)

COLUMNAS          = 2
FILAS_POR_PAGINA  = 5
CARTAS_POR_PAGINA = COLUMNAS * FILAS_POR_PAGINA  # 10

RAREZA_EMOJI = {"comun": "⚪", "rara": "🔵", "legendaria": "🟡"}
ORDEN_RAREZA = {"legendaria": 0, "rara": 1, "comun": 2}


class PhotocardsHandlers:

    def __init__(self, bot: telebot.TeleBot) -> None:
        self.bot = bot
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.bot.register_message_handler(self.cmd_menu, commands=["menu"])
        self.bot.register_callback_query_handler(
            self.handle_callback,
            func=lambda c: c.data.startswith("pc_"),
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    def _answer(self, call: types.CallbackQuery, text: str = "", alert: bool = False) -> None:
        try:
            self.bot.answer_callback_query(call.id, text, show_alert=alert)
        except Exception:
            pass

    def _edit(self, call: types.CallbackQuery, texto: str,
              markup: Optional[types.InlineKeyboardMarkup] = None) -> None:
        try:
            self.bot.edit_message_text(
                texto, call.message.chat.id, call.message.message_id,
                parse_mode="HTML", reply_markup=markup,
            )
        except Exception as exc:
            logger.debug(f"_edit: {exc}")

    def _delete(self, chat_id: int, message_id: int) -> None:
        try:
            self.bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    def _send_text(self, call: types.CallbackQuery, texto: str,
                   markup: Optional[types.InlineKeyboardMarkup] = None) -> None:
        """
        Borra el mensaje actual (puede ser foto o texto) y envía uno nuevo de texto.
        Usar cuando se vuelve de una vista de foto a una vista de texto, ya que
        edit_message_text falla si el mensaje original es una foto.
        """
        thread_id = getattr(call.message, "message_thread_id", None)
        self._delete(call.message.chat.id, call.message.message_id)
        try:
            self.bot.send_message(
                call.message.chat.id,
                texto,
                parse_mode="HTML",
                reply_markup=markup,
                message_thread_id=thread_id,
            )
        except Exception as exc:
            logger.error(f"_send_text: {exc}", exc_info=True)

    def _check_owner(self, call: types.CallbackQuery, owner_id: int) -> bool:
        if call.from_user.id != owner_id:
            self._answer(call, "🚫 Este menú no es tuyo.", alert=True)
            return False
        return True

    def _nombre_usuario(self, call: types.CallbackQuery) -> str:
        """Nombre de pila del dueño del menú para el encabezado."""
        u = call.from_user
        return u.first_name or u.username or "vos"

    # ── /menu ────────────────────────────────────────────────────────────────

    def cmd_menu(self, message: types.Message) -> None:
        if not message.from_user:
            return
        uid = message.from_user.id
        if not db_manager.user_exists(uid):
            self.bot.reply_to(message, "⚠️ Registrate primero con /registrar")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📦 Abrir Sobre",  callback_data=f"pc_sobres:{uid}"),
            types.InlineKeyboardButton("🗂️ Mi Colección", callback_data=f"pc_coleccion:{uid}"),
            types.InlineKeyboardButton("❌ Cerrar",        callback_data=f"pc_cerrar:{uid}"),
        )
        nombre = message.from_user.first_name or message.from_user.username or "vos"
        self.bot.send_message(
            message.chat.id,
            f"👤 <b>Menú de {nombre}</b>\n\n"
            f"🎴 <b>Photocards</b>\n💰 Precio por sobre: <b>{COSTO_SOBRE} cosmos</b> · 5 cartas",
            parse_mode="HTML",
            reply_markup=markup,
            message_thread_id=getattr(message, "message_thread_id", None),
        )

    # ── dispatch ──────────────────────────────────────────────────────────────

    def handle_callback(self, call: types.CallbackQuery) -> None:
        # formato: pc_<accion>:<owner_id>[:<extra1>[:<extra2>]]
        if not call.data or not call.from_user:
            return
        partes = call.data.split(":")
        accion = partes[0]

        try:
            owner_id = int(partes[1])
        except (IndexError, ValueError):
            return

        if not self._check_owner(call, owner_id):
            return

        try:
            if accion == "pc_cerrar":
                self._answer(call)
                self._delete(call.message.chat.id, call.message.message_id)

            elif accion == "pc_menu":
                self._show_menu(call, owner_id)

            elif accion == "pc_sobres":
                self._show_albums_sobre(call, owner_id)

            elif accion == "pc_abrir":
                # pc_abrir:<owner>:<album_key>
                album_key = partes[2] if len(partes) > 2 else ""
                self._abrir_sobre(call, owner_id, album_key)

            elif accion == "pc_coleccion":
                self._show_coleccion(call, owner_id)

            elif accion == "pc_album":
                # pc_album:<owner>:<album_key>:<pagina>[:<from_photo>]
                # from_photo=1 indica que el mensaje actual es una foto (carta detalle)
                # y hay que borrar+enviar en lugar de editar.
                album_key  = partes[2] if len(partes) > 2 else ""
                pagina     = int(partes[3]) if len(partes) > 3 else 0
                from_photo = len(partes) > 4 and partes[4] == "1"
                self._show_cartas_album(call, owner_id, album_key, pagina, from_photo=from_photo)

            elif accion == "pc_carta":
                # pc_carta:<owner>:<carta_id>
                carta_id = int(partes[2]) if len(partes) > 2 else 0
                self._show_carta_detalle(call, owner_id, carta_id)

            elif accion == "pc_vender_todo":
                carta_id = int(partes[2]) if len(partes) > 2 else 0
                self._vender_todo(call, owner_id, carta_id)

            elif accion == "pc_vender_rep":
                carta_id = int(partes[2]) if len(partes) > 2 else 0
                self._vender_repetidas(call, owner_id, carta_id)

            elif accion == "pc_intercambiar":
                carta_id = int(partes[2]) if len(partes) > 2 else 0
                self._intercambiar(call, owner_id, carta_id)

            elif accion == "pc_vrep_alb":
                # pc_vrep_alb:<owner>:<album_key>
                album_key = partes[2] if len(partes) > 2 else ""
                self._vender_repetidas_album(call, owner_id, album_key, incluir_legendarias=True)

            elif accion == "pc_vrep_nleg":
                # pc_vrep_nleg:<owner>:<album_key>
                album_key = partes[2] if len(partes) > 2 else ""
                self._vender_repetidas_album(call, owner_id, album_key, incluir_legendarias=False)

        except Exception as exc:
            logger.error(f"handle_callback ({call.data}): {exc}", exc_info=True)
            self._answer(call, "❌ Error inesperado.", alert=True)

    # ── menú principal ────────────────────────────────────────────────────────

    def _show_menu(self, call: types.CallbackQuery, uid: int) -> None:
        self._answer(call)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📦 Abrir Sobre",  callback_data=f"pc_sobres:{uid}"),
            types.InlineKeyboardButton("🗂️ Mi Colección", callback_data=f"pc_coleccion:{uid}"),
            types.InlineKeyboardButton("❌ Cerrar",        callback_data=f"pc_cerrar:{uid}"),
        )
        nombre = self._nombre_usuario(call)
        self._edit(
            call,
            f"👤 <b>Menú de {nombre}</b>\n\n"
            f"🎴 <b>Photocards</b>\n💰 Precio por sobre: <b>{COSTO_SOBRE} cosmos</b> · 5 cartas",
            markup,
        )

    # ── abrir sobre ───────────────────────────────────────────────────────────

    def _show_albums_sobre(self, call: types.CallbackQuery, uid: int) -> None:
        self._answer(call)
        albums = photocards_service.obtener_albums_disponibles()
        markup = types.InlineKeyboardMarkup(row_width=1)
        for alb in albums:
            markup.add(types.InlineKeyboardButton(
                f"🎴 {alb['name']}  ({alb['total_cartas']} cartas)",
                callback_data=f"pc_abrir:{uid}:{alb['key']}",
            ))
        markup.add(types.InlineKeyboardButton("⬅️ Volver", callback_data=f"pc_menu:{uid}"))
        nombre = self._nombre_usuario(call)
        self._edit(call, f"👤 <b>Menú de {nombre}</b>\n\n📦 <b>Elegí el álbum</b>\nCosto: <b>{COSTO_SOBRE} cosmos</b> · 5 cartas", markup)

    def _abrir_sobre(self, call: types.CallbackQuery, uid: int, album_key: str) -> None:
        self._answer(call)
        volver = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("⬅️ Volver", callback_data=f"pc_sobres:{uid}")
        )
        saldo = economy_service.get_balance(uid)
        if saldo < COSTO_SOBRE:
            self._edit(call, f"❌ Necesitás <b>{COSTO_SOBRE}</b> cosmos, tenés <b>{saldo}</b>.", volver)
            return
        if not economy_service.subtract_credits(uid, COSTO_SOBRE, "Apertura sobre photocards"):
            self._edit(call, "❌ Error al descontar cosmos.", volver)
            return
        resultado = photocards_service.abrir_sobre(uid, album_key)
        exito, _, cartas = resultado[0], resultado[1], resultado[2]
        god_pack = resultado[3] if len(resultado) > 3 else False
        if not exito or not cartas:
            economy_service.add_credits(uid, COSTO_SOBRE, "Reembolso sobre fallido")
            self._edit(call, "❌ Error al abrir el sobre. Cosmos reembolsados.", volver)
            return
        nombre_album = photocards_service.config_albums.get(album_key, {}).get("name", album_key)
        lineas = [f"{RAREZA_EMOJI.get(c.rareza,'⚪')} <b>{c.nombre_display}</b> — {c.rareza.capitalize()}" for c in cartas]
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📦 Otro sobre",   callback_data=f"pc_abrir:{uid}:{album_key}"),
            types.InlineKeyboardButton("🗂️ Mi Colección", callback_data=f"pc_coleccion:{uid}"),
        )
        markup.add(types.InlineKeyboardButton("⬅️ Menú", callback_data=f"pc_menu:{uid}"))

        if god_pack:
            encabezado = (
                f"✨✨✨ <b>¡GOD PACK!</b> ✨✨✨\n"
                f"<i>Conseguiste un sobre completamente legendario</i>\n"
                f"💰 Saldo: <b>{economy_service.get_balance(uid)} cosmos</b>\n\n"
                f"🟡 <b>Cartas legendarias obtenidas:</b>\n"
            )
        else:
            encabezado = (
                f"🎉 <b>¡Sobre de {nombre_album} abierto!</b>\n"
                f"💰 Saldo restante: <b>{economy_service.get_balance(uid)} cosmos</b>\n\n"
                f"🃏 <b>Cartas obtenidas:</b>\n"
            )
        self._edit(call, encabezado + "\n".join(lineas), markup)

    # ── mi colección ──────────────────────────────────────────────────────────

    def _show_coleccion(self, call: types.CallbackQuery, uid: int) -> None:
        self._answer(call)

        albums_usuario = photocards_service.get_albums_usuario(uid)

        if not albums_usuario:
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("📦 Abrir Sobre", callback_data=f"pc_sobres:{uid}"),
                types.InlineKeyboardButton("⬅️ Volver",      callback_data=f"pc_menu:{uid}"),
            )
            nombre = self._nombre_usuario(call)
            self._edit(call, f"👤 <b>Menú de {nombre}</b>\n\n📭 <b>Mi Colección</b>\n\nNo tenés ninguna photocard todavía.", markup)
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        lineas: List[str] = []

        for album_key in albums_usuario:
            nombre_album = photocards_service.config_albums[album_key]["name"]
            # total = archivos contados al indexar
            total        = photocards_service.get_total_album(album_key)
            # obtenidas = cartaIDs distintos del usuario en este álbum
            obtenidas    = len(photocards_service.get_cartas_usuario_en_album(uid, album_key))

            lineas.append(f"📂 <b>{nombre_album}</b>: {obtenidas}/{total}")
            markup.add(types.InlineKeyboardButton(
                f"📂 {nombre_album} ({obtenidas}/{total})",
                callback_data=f"pc_album:{uid}:{album_key}:0",
            ))

        markup.add(types.InlineKeyboardButton("⬅️ Volver", callback_data=f"pc_menu:{uid}"))
        nombre = self._nombre_usuario(call)
        self._edit(call, f"👤 <b>Menú de {nombre}</b>\n\n🗂️ <b>Mi Colección</b>\n\n" + "\n".join(lineas), markup)

    # ── cartas del álbum ──────────────────────────────────────────────────────

    def _show_cartas_album(self, call: types.CallbackQuery, uid: int, album_key: str, pagina: int, from_photo: bool = False) -> None:
        self._answer(call)

        cartas = photocards_service.get_cartas_usuario_en_album(uid, album_key)

        nombre_album = photocards_service.config_albums.get(album_key, {}).get("name", album_key)
        total        = photocards_service.get_total_album(album_key)

        # Elegir el método correcto según el tipo de mensaje origen:
        # Si venimos de una foto (carta detalle), hay que borrar y enviar texto nuevo.
        # Si venimos de texto (paginación), podemos editar directamente.
        render = self._send_text if from_photo else self._edit

        if not cartas:
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton("⬅️ Volver", callback_data=f"pc_coleccion:{uid}"))
            nombre_u = self._nombre_usuario(call)
            render(call, f"👤 <b>Menú de {nombre_u}</b>\n\n📭 No tenés cartas en <b>{nombre_album}</b>.", markup)
            return

        obtenidas = len(cartas)

        # ordenar legendaria → rara → común, A→Z
        def sort_key(cid: int):
            pc = photocards_service.get_carta_by_id(cid)
            return (ORDEN_RAREZA.get(pc.rareza, 9), pc.nombre) if pc else (9, "")

        ids_ordenados = sorted(cartas.keys(), key=sort_key)
        total_pags    = max(1, (len(ids_ordenados) + CARTAS_POR_PAGINA - 1) // CARTAS_POR_PAGINA)
        pagina        = max(0, min(pagina, total_pags - 1))
        ids_pagina    = ids_ordenados[pagina * CARTAS_POR_PAGINA:(pagina + 1) * CARTAS_POR_PAGINA]

        markup = types.InlineKeyboardMarkup(row_width=COLUMNAS)
        fila: List[types.InlineKeyboardButton] = []

        for cid in ids_pagina:
            pc    = photocards_service.get_carta_by_id(cid)
            cant  = cartas[cid]
            if pc is None:
                # ID en DB pero no en índice en memoria: mostrar placeholder
                # para que el usuario pueda verla (puede ocurrir si las imágenes
                # no estaban disponibles al arrancar).
                logger.warning(f"_show_cartas_album: cartaID={cid} no está en todas_las_cartas")
                fila.append(types.InlineKeyboardButton(
                    f"❓ Carta #{cid} ×{cant}",
                    callback_data=f"pc_carta:{uid}:{cid}",
                ))
            else:
                emoji = RAREZA_EMOJI.get(pc.rareza, "⚪")
                fila.append(types.InlineKeyboardButton(
                    f"{emoji} {pc.nombre_display} ×{cant}",
                    callback_data=f"pc_carta:{uid}:{cid}",
                ))
            if len(fila) == COLUMNAS:
                markup.row(*fila)
                fila = []
        if fila:
            markup.row(*fila)

        # paginación
        nav: List[types.InlineKeyboardButton] = []
        if pagina > 0:
            nav.append(types.InlineKeyboardButton("⬅️", callback_data=f"pc_album:{uid}:{album_key}:{pagina-1}"))
        if pagina < total_pags - 1:
            nav.append(types.InlineKeyboardButton("➡️", callback_data=f"pc_album:{uid}:{album_key}:{pagina+1}"))
        if nav:
            markup.row(*nav)

        markup.add(types.InlineKeyboardButton("💸 Vender todas las repetidas",      callback_data=f"pc_vrep_alb:{uid}:{album_key}"))
        markup.add(types.InlineKeyboardButton("💸 Vender repetidas no legendarias", callback_data=f"pc_vrep_nleg:{uid}:{album_key}"))
        markup.add(types.InlineKeyboardButton("⬅️ Volver", callback_data=f"pc_coleccion:{uid}"))

        nombre_u = self._nombre_usuario(call)
        render(call,
            f"👤 <b>Menú de {nombre_u}</b>\n\n"
            f"📂 <b>{nombre_album}</b>  ({obtenidas}/{total})\n"
            f"Página {pagina+1}/{total_pags} — tocá una carta:",
            markup)

    # ── detalle de carta ──────────────────────────────────────────────────────

    def _show_carta_detalle(self, call: types.CallbackQuery, uid: int, carta_id: int) -> None:
        self._answer(call)
        pc = photocards_service.get_carta_by_id(carta_id)
        if pc is None:
            self._edit(call, "❌ Carta no encontrada.")
            return
        cantidad = photocards_service.get_cantidad_carta(uid, carta_id)
        if cantidad == 0:
            self._edit(call, "❌ No tenés esta carta.")
            return

        precio_unit  = photocards_service.precios_venta.get(pc.rareza, 2)
        nombre_album = photocards_service.config_albums.get(pc.album, {}).get("name", pc.album)
        emoji        = RAREZA_EMOJI.get(pc.rareza, "⚪")

        caption = (
            f"{emoji} <b>{pc.nombre_display}</b>\n"
            f"📀 Álbum: <b>{nombre_album}</b>  ·  ✨ <b>{pc.rareza.capitalize()}</b>\n"
            f"🔢 Cantidad: <b>{cantidad}</b>  ·  💰 <b>{precio_unit} cosmos</b> c/u"
        )

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🔄 Intercambiar",  callback_data=f"pc_intercambiar:{uid}:{carta_id}"),
            types.InlineKeyboardButton("💰 Vender ×1",     callback_data=f"pc_vender_todo:{uid}:{carta_id}"),
        )
        if cantidad > 1:
            markup.add(types.InlineKeyboardButton(
                f"🃏 Liquidar repetidas (×{cantidad-1})",
                callback_data=f"pc_vender_rep:{uid}:{carta_id}",
            ))
        markup.add(types.InlineKeyboardButton("⬅️ Volver", callback_data=f"pc_album:{uid}:{pc.album}:0:1"))

        thread_id = getattr(call.message, "message_thread_id", None)
        chat_id   = call.message.chat.id

        MAX_PHOTO_BYTES = 9 * 1024 * 1024  # 9MB — margen bajo el límite de 10MB de Telegram

        try:
            if pc.es_video:
                MAX_VIDEO_BYTES = 50 * 1024 * 1024  # 50MB límite de Telegram
                file_size = os.path.getsize(pc.path)

                if file_size <= MAX_VIDEO_BYTES:
                    # Video dentro del límite: enviar directo
                    with open(pc.path, "rb") as media:
                        self.bot.send_video(
                            chat_id, media,
                            caption=caption, parse_mode="HTML",
                            reply_markup=markup, message_thread_id=thread_id,
                            supports_streaming=True,
                        )
                else:
                    # Video demasiado grande: comprimir con ffmpeg
                    import subprocess, tempfile
                    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                        tmp_path = tmp.name
                    try:
                        subprocess.run([
                            "ffmpeg", "-y", "-i", pc.path,
                            "-vcodec", "libx264", "-crf", "28",
                            "-preset", "fast",
                            "-acodec", "aac", "-b:a", "128k",
                            "-movflags", "+faststart",
                            tmp_path
                        ], check=True, capture_output=True)
                        with open(tmp_path, "rb") as media:
                            self.bot.send_video(
                                chat_id, media,
                                caption=caption, parse_mode="HTML",
                                reply_markup=markup, message_thread_id=thread_id,
                                supports_streaming=True,
                            )
                    except subprocess.CalledProcessError as ffmpeg_err:
                        logger.error(f"[PC] ffmpeg falló: {ffmpeg_err.stderr.decode()}")
                        self._edit(call, caption, markup)
                        return
                    finally:
                        import os as _os
                        try:
                            _os.remove(tmp_path)
                        except Exception:
                            pass
            else:
                file_size = os.path.getsize(pc.path)

                if file_size <= MAX_PHOTO_BYTES:
                    # Imagen pequeña: enviar directamente como foto
                    with open(pc.path, "rb") as media:
                        self.bot.send_photo(
                            chat_id, media,
                            caption=caption, parse_mode="HTML",
                            reply_markup=markup, message_thread_id=thread_id,
                        )
                else:
                    # Imagen grande: comprimir en memoria hasta < 9MB
                    try:
                        from PIL import Image
                        img = Image.open(pc.path).convert("RGB")

                        # Redimensionar si algún lado supera 2560px
                        img.thumbnail((2560, 2560), Image.LANCZOS)

                        buf = io.BytesIO()
                        quality = 90
                        while True:
                            buf.seek(0)
                            buf.truncate()
                            img.save(buf, format="JPEG", quality=quality, optimize=True)
                            if buf.tell() <= MAX_PHOTO_BYTES or quality <= 40:
                                break
                            quality -= 10

                        buf.seek(0)
                        logger.info(
                            f"[PC] '{pc.nombre}' comprimida de "
                            f"{file_size/1024/1024:.1f}MB → "
                            f"{buf.tell()/1024/1024:.1f}MB (quality={quality})"
                        )
                        self.bot.send_photo(
                            chat_id, buf,
                            caption=caption, parse_mode="HTML",
                            reply_markup=markup, message_thread_id=thread_id,
                        )
                    except ImportError:
                        logger.error("[PC] Pillow no instalado — pip install Pillow")
                        self._edit(call, "❌ Error: instalar Pillow en el servidor.", markup)
                        return

            self._delete(chat_id, call.message.message_id)
        except FileNotFoundError:
            logger.warning(f"Archivo no encontrado: {pc.path}")
            self._edit(call, caption, markup)
        except Exception as exc:
            logger.error(f"_show_carta_detalle: {exc}", exc_info=True)
            self._edit(call, caption, markup)

    # ── vender ────────────────────────────────────────────────────────────────

    def _vender_todo(self, call: types.CallbackQuery, uid: int, carta_id: int) -> None:
        self._answer(call)
        cantidad = photocards_service.get_cantidad_carta(uid, carta_id)
        if cantidad == 0:
            self._edit(call, "❌ No tenés esta carta.")
            return
        pc     = photocards_service.get_carta_by_id(carta_id)
        nombre = pc.nombre_display if pc else f"#{carta_id}"
        emoji  = RAREZA_EMOJI.get(pc.rareza, "⚪") if pc else "⚪"
        exito, msg, cosmos = photocards_service.vender_photocard(uid, carta_id, 1)
        if exito:
            saldo = economy_service.get_balance(uid)
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("🗂️ Mi Colección", callback_data=f"pc_coleccion:{uid}"),
                types.InlineKeyboardButton("⬅️ Menú",          callback_data=f"pc_menu:{uid}"),
            )
            nombre_u = self._nombre_usuario(call)
            self._send_text(
                call,
                f"👤 <b>Menú de {nombre_u}</b>\n\n"
                f"💸 <b>Venta completada</b>\n\n"
                f"{emoji} <b>{nombre}</b> — ×1 vendida\n"
                f"💰 Ganaste: <b>+{cosmos} cosmos</b>\n"
                f"💳 Saldo actual: <b>{saldo} cosmos</b>",
                markup,
            )
        else:
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton("⬅️ Volver", callback_data=f"pc_menu:{uid}"))
            self._send_text(call, f"❌ {msg}", markup)

    def _vender_repetidas(self, call: types.CallbackQuery, uid: int, carta_id: int) -> None:
        self._answer(call)
        cantidad = photocards_service.get_cantidad_carta(uid, carta_id)
        pc       = photocards_service.get_carta_by_id(carta_id)
        nombre   = pc.nombre_display if pc else f"#{carta_id}"
        markup   = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🗂️ Mi Colección", callback_data=f"pc_coleccion:{uid}"),
            types.InlineKeyboardButton("⬅️ Menú",          callback_data=f"pc_menu:{uid}"),
        )
        if cantidad <= 1:
            self._edit(call, "ℹ️ Solo tenés 1 copia, no hay repetidas.", markup)
            return
        vender = cantidad - 1
        exito, msg, cosmos = photocards_service.vender_photocard(uid, carta_id, vender)
        if exito:
            precio_unit = photocards_service.precios_venta.get(pc.rareza, 2) if pc else 0
            emoji       = RAREZA_EMOJI.get(pc.rareza, "⚪") if pc else "⚪"
            saldo       = economy_service.get_balance(uid)
            markup_ok   = types.InlineKeyboardMarkup(row_width=1)
            markup_ok.add(
                types.InlineKeyboardButton("🃏 Ver carta actualizada", callback_data=f"pc_carta:{uid}:{carta_id}"),
                types.InlineKeyboardButton("🗂️ Mi Colección",          callback_data=f"pc_coleccion:{uid}"),
                types.InlineKeyboardButton("⬅️ Menú",                   callback_data=f"pc_menu:{uid}"),
            )
            nombre_u = self._nombre_usuario(call)
            self._send_text(
                call,
                f"👤 <b>Menú de {nombre_u}</b>\n\n"
                f"💸 <b>Repetidas liquidadas</b>\n\n"
                f"{emoji} <b>{nombre}</b>\n"
                f"🗑️ Vendidas: <b>×{vender}</b>  ·  {precio_unit} cosmos c/u\n"
                f"💰 Ganaste: <b>+{cosmos} cosmos</b>\n"
                f"📦 Te quedás con: <b>×1</b>\n"
                f"💳 Saldo actual: <b>{saldo} cosmos</b>",
                markup_ok,
            )
        else:
            self._send_text(call, f"❌ {msg}", markup)

    def _vender_repetidas_album(
        self,
        call: types.CallbackQuery,
        uid: int,
        album_key: str,
        incluir_legendarias: bool,
    ) -> None:
        """
        Vende todas las copias extra (cantidad - 1) de las cartas repetidas
        del usuario en el álbum dado.

        Args:
            incluir_legendarias: Si False, omite las cartas de rareza 'legendaria'.
        """
        self._answer(call)

        cartas       = photocards_service.get_cartas_usuario_en_album(uid, album_key)
        nombre_album = photocards_service.config_albums.get(album_key, {}).get("name", album_key)

        vendidas_count = 0
        cosmos_total   = 0
        omitidas_leg   = 0

        for carta_id, cantidad in cartas.items():
            if cantidad <= 1:
                continue  # solo 1 copia → no hay repetidas

            pc = photocards_service.get_carta_by_id(carta_id)

            if not incluir_legendarias and pc and pc.rareza == "legendaria":
                omitidas_leg += 1
                continue

            a_vender = cantidad - 1
            exito, _, cosmos = photocards_service.vender_photocard(uid, carta_id, a_vender)
            if exito:
                vendidas_count += a_vender
                cosmos_total   += cosmos

        saldo  = economy_service.get_balance(uid)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(
                "📂 Volver al álbum",
                callback_data=f"pc_album:{uid}:{album_key}:0",
            ),
            types.InlineKeyboardButton("🗂️ Mi Colección", callback_data=f"pc_coleccion:{uid}"),
        )
        nombre_u = self._nombre_usuario(call)

        if vendidas_count == 0:
            nota_vacia = (
                f" (tenés {omitidas_leg} legendaria(s) repetida(s) no incluidas)"
                if not incluir_legendarias and omitidas_leg > 0
                else ""
            )
            self._edit(
                call,
                f"👤 <b>Menú de {nombre_u}</b>\n\n"
                f"ℹ️ No había copias repetidas para vender en <b>{nombre_album}</b>{nota_vacia}.",
                markup,
            )
            return

        tipo_venta = "Todas las repetidas" if incluir_legendarias else "Repetidas no legendarias"
        nota_leg   = (
            f"\n⚠️ <i>{omitidas_leg} carta(s) legendaria(s) no vendida(s)</i>"
            if not incluir_legendarias and omitidas_leg > 0
            else ""
        )

        self._edit(
            call,
            f"👤 <b>Menú de {nombre_u}</b>\n\n"
            f"💸 <b>Venta masiva — {nombre_album}</b>\n\n"
            f"🗃️ Tipo: <i>{tipo_venta}</i>\n"
            f"🃏 Copias vendidas: <b>×{vendidas_count}</b>\n"
            f"💰 Total ganado: <b>+{cosmos_total} cosmos</b>\n"
            f"💳 Saldo actual: <b>{saldo} cosmos</b>{nota_leg}",
            markup,
        )

    # ── intercambiar ──────────────────────────────────────────────────────────

    def _intercambiar(self, call: types.CallbackQuery, uid: int, carta_id: int) -> None:
        """
        Punto de entrada al flujo de intercambio DIRECTO P2P.

        Pide al usuario A que mencione con quién quiere intercambiar.
        Toda la lógica de sesión y confirmaciones vive en IntercambioHandler
        (_pcd_*). Este método solo arranca el flujo.
        """
        self._answer(call)
        pc = photocards_service.get_carta_by_id(carta_id)
        if pc is None:
            self._edit(call, "❌ Carta no encontrada.")
            return
        emoji = RAREZA_EMOJI.get(pc.rareza, "⚪")

        from handlers.intercambio_handler import _pc_direct_iniciar_oferta
        _pc_direct_iniciar_oferta(
            bot        = self.bot,
            call       = call,
            oferente_id= uid,
            carta_id   = carta_id,
            pc         = pc,
            emoji      = emoji,
        )


def setup(bot: telebot.TeleBot) -> None:
    PhotocardsHandlers(bot)
    logger.info("✅ PhotocardsHandlers registrados.")