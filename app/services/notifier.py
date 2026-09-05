"""Notificación de leads al asesor humano (Fase 4, planning.md §Fase 4.4).

Cuando un lead queda calificado (o el cliente pide hablar con un humano), el
bot "pausa" la IA para ese número y notifica al asesor con el resumen del caso.

Canales:
  1. Log estructurado en consola (siempre).
  2. Mensaje de WhatsApp al número `ADVISOR_NOTIFY_WHATSAPP` (si está configurado).
"""

from __future__ import annotations

import logging

from app.config import get_settings
from app.services import whatsapp as whatsapp_service

logger = logging.getLogger("multibot.notifier")


class AdvisorNotifier:
    """Notifica los leads calificados al asesor humano.

    En multi-tenant, cada tenant tiene su propio asesor y envía la
    notificación DESDE su número de WhatsApp (phone_number_id/token propios).
    """

    def __init__(
        self,
        advisor_number: str = "",
        sender_phone_number_id: str = "",
        sender_access_token: str = "",
    ) -> None:
        self._advisor_number = advisor_number or get_settings().advisor_notify_whatsapp
        self._sender_phone_number_id = sender_phone_number_id
        self._sender_access_token = sender_access_token

    async def notify_lead(self, wa_id: str, profile: dict, partial: bool = False) -> None:
        """Envía el resumen del lead (perfil capturado) al asesor.

        Args:
            wa_id: número de WhatsApp del cliente (formato internacional).
            profile: campos capturados del lead (tipo, marca/modelo, año, ciudad).
            partial: True si el cliente pidió humano a mitad del flujo.
        """
        header = "LEAD PARCIAL (pidió humano)" if partial else "LEAD CALIFICADO"
        lines = [
            f"=== {header} ===",
            f"Cliente (wa_id): {wa_id}",
        ]
        if profile:
            for key, value in profile.items():
                lines.append(f"  {key}: {value}")
        else:
            lines.append("  (sin datos capturados aún)")
        summary = "\n".join(lines)

        # Canal 1: consola / logs (siempre).
        logger.info("\n%s\n", summary)

        # Canal 2: WhatsApp al asesor (opcional).
        if self._advisor_number:
            try:
                await whatsapp_service.send_text_message(
                    self._advisor_number,
                    summary,
                    phone_number_id=self._sender_phone_number_id,
                    access_token=self._sender_access_token,
                )
                logger.info("Lead notificado al asesor por WhatsApp.")
            except Exception as exc:  # noqa: BLE001 - no bloquear el chat del cliente
                logger.error("No se pudo notificar al asesor: %s", exc)
