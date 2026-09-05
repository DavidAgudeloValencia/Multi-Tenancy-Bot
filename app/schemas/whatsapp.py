"""Modelos Pydantic del payload de la WhatsApp Cloud API (Meta).

Formato oficial:
https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples

Los modelos son deliberadamente tolerantes (`extra="ignore"`): Meta puede
añadir campos nuevos en el futuro sin que el parseo falle.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Profile(BaseModel):
    """Perfil público del contacto (nombre visible en WhatsApp)."""

    model_config = ConfigDict(extra="ignore")

    name: str = ""


class TextMessage(BaseModel):
    """Cuerpo de un mensaje de tipo texto."""

    model_config = ConfigDict(extra="ignore")

    body: str = ""


class Metadata(BaseModel):
    """Metadatos del número de WhatsApp Business que recibe el mensaje."""

    model_config = ConfigDict(extra="ignore")

    display_phone_number: str = ""
    phone_number_id: str = ""


class Contact(BaseModel):
    """Contacto (cliente) que escribió al número de WhatsApp."""

    model_config = ConfigDict(extra="ignore")

    profile: Optional[Profile] = None
    wa_id: str = ""


class Message(BaseModel):
    """Mensaje entrante de WhatsApp.

    En la Fase 2 solo se modela en detalle el tipo `text`; los demás tipos
    (image, document, location, ...) se ignoran sin romper el parseo.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    from_: str = Field(alias="from", default="")
    id: str = ""
    timestamp: str = ""
    type: str = ""
    text: Optional[TextMessage] = None


class Status(BaseModel):
    """Confirmación de entrega/lectura de un mensaje enviado por el bot."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    status: str = ""
    timestamp: str = ""
    recipient_id: str = ""


class ChangeValue(BaseModel):
    """Contenido del evento: mensajes entrantes y/o estados de entrega."""

    model_config = ConfigDict(extra="ignore")

    messaging_product: str = ""
    metadata: Metadata = Field(default_factory=Metadata)
    contacts: list[Contact] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    statuses: list[Status] = Field(default_factory=list)


class Change(BaseModel):
    """Un cambio concreto dentro de una entrada del payload."""

    model_config = ConfigDict(extra="ignore")

    value: ChangeValue = Field(default_factory=ChangeValue)
    field: str = ""


class Entry(BaseModel):
    """Una entrada del payload (una por cuenta de WhatsApp Business)."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    changes: list[Change] = Field(default_factory=list)


class WebhookPayload(BaseModel):
    """Raíz del payload que Meta envía al POST /webhook."""

    model_config = ConfigDict(extra="ignore")

    object: str = ""
    entry: list[Entry] = Field(default_factory=list)
