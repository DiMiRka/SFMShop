import logging
import os
import sys
from collections.abc import Callable
from typing import Any

from loguru import logger


_is_logging_configured = False


class LogService:
    def __init__(self, alert_handler: Callable[[str, dict[str, Any]], None] | None = None):
        self.alert_handler = alert_handler or self.send_alert

    def debug(self, message: str, **fields: Any) -> None:
        self._log("DEBUG", message, **fields)

    def info(self, message: str, **fields: Any) -> None:
        self._log("INFO", message, **fields)

    def warning(self, message: str, **fields: Any) -> None:
        self._log("WARNING", message, **fields)

    def error(self, message: str, exception: Exception | None = None, **fields: Any) -> None:
        self._log("ERROR", message, exception=exception, **fields)

    def critical(self, message: str, exception: Exception | None = None, **fields: Any) -> None:
        self._log("CRITICAL", message, exception=exception, **fields)
        self.alert_handler(message, fields)

    def _log(
            self,
            level: str,
            message: str,
            exception: Exception | None = None,
            **fields: Any) -> None:
        bound_logger = logger.bind(**fields)
        if exception is not None:
            bound_logger.opt(exception=exception).log(level, message)
            return

        bound_logger.log(level, message)

    @staticmethod
    def send_alert(message: str, fields: dict[str, Any]) -> None:
        logger.bind(alert=True, **fields).critical(f"ALERT: {message}")


log_service = LogService()


def setup_logging(log_dir: str = "logs") -> None:
    global _is_logging_configured

    if _is_logging_configured:
        return

    os.makedirs(log_dir, exist_ok=True)

    logger.remove()

    logging.getLogger("uvicorn.error").disabled = True
    logging.getLogger("uvicorn.access").disabled = True

    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
        "<level>{message}</level> | {extra}"
    )

    file_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | "
        "{name}:{function} - {message} | {extra}"
    )

    logger.add(
        sys.stdout,
        format=console_format,
        colorize=True,
        level="INFO",
        backtrace=False,
        diagnose=False,
    )

    logger.add(
        os.path.join(log_dir, "app.log"),
        level="DEBUG",
        format=file_format,
        rotation="10 MB",
        retention="10 days",
        compression="zip",
        backtrace=True,
        diagnose=False,
    )

    logger.add(
        os.path.join(log_dir, "errors_log.log"),
        level="ERROR",
        format=file_format,
        rotation="10 MB",
        retention="10 days",
        compression="zip",
        backtrace=True,
        diagnose=False,
    )

    _is_logging_configured = True


def configure_sentry(dsn: str | None = None, traces_sample_rate: float = 0.1) -> bool:
    if not dsn:
        log_service.debug("Sentry не настроен")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
    except ImportError:
        log_service.warning("Sentry не установлен")
        return False

    sentry_sdk.init(
        dsn=dsn,
        integrations=[FastApiIntegration()],
        traces_sample_rate=traces_sample_rate,
    )
    log_service.info("Sentry настроен")
    return True
