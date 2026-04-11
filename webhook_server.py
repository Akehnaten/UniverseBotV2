# -*- coding: utf-8 -*-
"""
webhook_server.py
════════════════════════════════════════════════════════════════════════════════
Servidor de Webhook para UniverseBot V2.0

Reemplaza el infinity_polling por un servidor Flask liviano que recibe
actualizaciones directamente desde los servidores de Telegram (push).

Ventajas sobre polling:
  - Sin loop activo: Telegram notifica al bot cuando hay algo.
  - Menor uso de CPU y red en estado idle.
  - Menor latencia de respuesta.
  - Sin límites de requests por segundo del lado del cliente.

Requisitos:
  - Una URL pública HTTPS accesible desde Internet.
  - Para hosting en PC local: usar ngrok (ver instrucciones en WEBHOOK_SETUP.md).
  - Flask instalado: pip install flask

Configuración (en config.py):
  WEBHOOK_URL          → URL pública HTTPS (ej: https://xxxx.ngrok-free.app)
  WEBHOOK_PORT         → Puerto local donde escucha Flask (default: 8443)
  WEBHOOK_HOST         → Interfaz de red local (default: "0.0.0.0")
  WEBHOOK_SECRET_TOKEN → Token secreto para validar requests de Telegram
════════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
import time

import telebot
from flask import Flask, abort, request

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# FACTORY DE LA APP FLASK
# ─────────────────────────────────────────────────────────────────────────────

def _create_flask_app(bot: telebot.TeleBot, secret_token: str) -> Flask:
    """
    Construye y retorna la aplicación Flask con las rutas necesarias.

    Rutas registradas:
      POST /<bot_token>  → Punto de entrada de updates de Telegram.
      GET  /health       → Health-check para monitoreo externo.

    Args:
        bot          : Instancia de TeleBot ya configurada con handlers.
        secret_token : Token secreto para validar la cabecera
                       X-Telegram-Bot-Api-Secret-Token. Vacío = sin validación.
    """
    app = Flask(__name__)

    # Silenciar el logger interno de Werkzeug para no contaminar los logs
    # del bot (Flask loguea cada request por defecto).
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    # ── Endpoint principal de Telegram ────────────────────────────────────────
    @app.route(f"/{bot.token}", methods=["POST"])
    def telegram_webhook() -> tuple[str, int]:
        # 1. Validar el token secreto si está configurado
        if secret_token:
            incoming = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if incoming != secret_token:
                logger.warning("[WEBHOOK] Request rechazado: token secreto inválido.")
                abort(403)

        # 2. Validar Content-Type
        if request.content_type != "application/json":
            logger.warning("[WEBHOOK] Request rechazado: Content-Type inesperado: %s",
                           request.content_type)
            abort(415)

        # 3. Deserializar y procesar el update
        try:
            json_string = request.get_data(as_text=True)
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
        except Exception as exc:
            # Nunca retornar un error 5xx a Telegram: reintentaría el update
            # indefinidamente. Logueamos y respondemos 200 igualmente.
            logger.exception("[WEBHOOK] Error procesando update: %s", exc)

        return "OK", 200

    # ── Health-check ──────────────────────────────────────────────────────────
    @app.route("/health", methods=["GET"])
    def health_check() -> tuple[str, int]:
        return "OK", 200

    return app


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN PÚBLICA DE ARRANQUE
# ─────────────────────────────────────────────────────────────────────────────

def start_webhook(
    bot: telebot.TeleBot,
    webhook_url: str,
    host: str = "0.0.0.0",
    port: int = 8443,
    secret_token: str = "",
) -> None:
    """
    Registra el webhook en Telegram y arranca el servidor Flask.

    Este método bloquea hasta que el proceso sea interrumpido (SIGINT/SIGTERM).

    Args:
        bot          : Instancia de TeleBot configurada con todos sus handlers.
        webhook_url  : URL pública HTTPS base (sin trailing slash).
                       Ejemplo: "https://xxxx.ngrok-free.app"
        host         : Interfaz local donde escucha Flask.
        port         : Puerto local de Flask.
        secret_token : Token opcional para validar requests de Telegram.
    """
    # 1. Eliminar webhook anterior para evitar conflictos
    logger.info("[WEBHOOK] Eliminando webhook previo (si existe)...")
    try:
        bot.remove_webhook()
    except Exception as exc:
        logger.warning("[WEBHOOK] No se pudo eliminar webhook previo: %s", exc)

    # Pequeña pausa recomendada por la API de Telegram entre remove y set
    time.sleep(0.5)

    # 2. Registrar el nuevo webhook
    full_url = f"{webhook_url.rstrip('/')}/{bot.token}"
    logger.info("[WEBHOOK] Registrando webhook en: %s", full_url)

    webhook_kwargs: dict = {"url": full_url}
    if secret_token:
        webhook_kwargs["secret_token"] = secret_token

    try:
        bot.set_webhook(**webhook_kwargs)
    except Exception as exc:
        logger.critical("[WEBHOOK] No se pudo registrar el webhook: %s", exc)
        raise

    logger.info("[WEBHOOK] ✅ Webhook registrado correctamente.")

    # 3. Crear y arrancar la app Flask
    app = _create_flask_app(bot, secret_token)

    logger.info("[WEBHOOK] Servidor Flask escuchando en http://%s:%d", host, port)
    logger.info("[WEBHOOK] Telegram enviará updates a: %s", full_url)

    # threaded=True permite procesar múltiples updates concurrentemente
    app.run(host=host, port=port, debug=False, threaded=True)
