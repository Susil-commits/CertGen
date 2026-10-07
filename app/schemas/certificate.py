import uuid
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.models.certificate import CertificateStatus


class RecipientInput(BaseModel):
    """Input representation of a single certificate recipient."""

    name: str = Field(..., min_length=1, description="Recipient full name")
    email: str | None = Field(default=None, description="Optional recipient email")

    # Allow custom extra fields for template variables (e.g. course, date, description)
    model_config = ConfigDict(extra="allow")


class CertificateRecordResponse(BaseModel):
    """API response schema for an individual certificate generation record."""

    record_id: uuid.UUID = Field(
        validation_alias=AliasChoices("record_id", "id"),
        description="Unique identifier for the certificate record",
    )
    recipient_name: str
    status: CertificateStatus
    error_message: str | None = None
    file_path: str | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
