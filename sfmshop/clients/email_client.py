from collections.abc import Awaitable, Callable
from email.message import EmailMessage
from typing import Any

import aiosmtplib

from sfmshop.core.config import AppSettings


class EmailClient:
    def __init__(
            self,
            host: str,
            port: int,
            sender: str,
            username: str | None = None,
            password: str | None = None,
            start_tls: bool = True,
            timeout: float = 10.0,
            transport: Callable[..., Awaitable[Any]] = aiosmtplib.send):
        self.host = host
        self.port = port
        self.sender = sender
        self.username = username
        self.password = password
        self.start_tls = start_tls
        self.timeout = timeout
        self.transport = transport

    async def send(self, message: EmailMessage) -> None:
        message["From"] = self.sender
        await self.transport(
            message,
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            start_tls=self.start_tls,
            timeout=self.timeout,
        )


def create_email_client(settings: AppSettings) -> EmailClient | None:
    if not settings.smtp_host:
        return None

    return EmailClient(
        host=settings.smtp_host,
        port=settings.smtp_port,
        sender=settings.smtp_from,
        username=settings.smtp_username,
        password=settings.smtp_password,
        start_tls=settings.smtp_start_tls,
        timeout=settings.smtp_timeout,
    )
