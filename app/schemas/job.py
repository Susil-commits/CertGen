import uuid
from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.models.job import JobStatus
from app.schemas.certificate import RecipientInput


class JobCreateRequest(BaseModel):
    """Request payload to initiate a bulk certificate generation job."""

    recipients: list[RecipientInput] = Field(
        ...,
        min_length=1,
        description="Non-empty list of recipients to generate certificates for",
    )


class JobCreateResponse(BaseModel):
    """Response returned immediately upon accepting a certificate job."""

    job_id: uuid.UUID = Field(
        validation_alias=AliasChoices("job_id", "id"),
        description="Unique identifier for the bulk generation job",
    )
    status: JobStatus
    total_count: int

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class JobStatusResponse(BaseModel):
    """Full status response for a certificate generation job."""

    job_id: uuid.UUID = Field(
        validation_alias=AliasChoices("job_id", "id"),
        description="Unique identifier for the bulk generation job",
    )
    status: JobStatus
    total_count: int
    success_count: int
    failure_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
