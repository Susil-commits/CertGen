import os
import uuid
from pathlib import Path

import pytest

from app.services.certificate_service import generate_certificate
from app.utils.exceptions import CertificateGenerationError


def test_certificate_generation_success() -> None:
    """Test generating a certificate file directly via certificate_service."""
    record_id = uuid.uuid4()
    recipient_dict = {
        "record_id": str(record_id),
        "name": "Katherine Johnson",
        "email": "kjohnson@nasa.gov",
        "course": "Orbital Mechanics Certification",
        "description": "For extraordinary achievements in calculation and mission trajectory design.",
    }

    # Test PDF generation
    pdf_path_str = generate_certificate(recipient_dict, record_id=record_id, output_format="pdf")
    pdf_path = Path(pdf_path_str)

    assert pdf_path.exists()
    assert pdf_path.is_file()
    assert pdf_path.stat().st_size > 0
    assert str(record_id) in pdf_path.name
    assert pdf_path.suffix == ".pdf"

    # Test PNG generation
    png_record_id = uuid.uuid4()
    png_path_str = generate_certificate(
        {"name": "Dorothy Vaughan"},
        record_id=png_record_id,
        output_format="png",
    )
    png_path = Path(png_path_str)

    assert png_path.exists()
    assert png_path.is_file()
    assert png_path.stat().st_size > 0
    assert png_path.suffix == ".png"


def test_certificate_generation_missing_name_error() -> None:
    """Test that missing or empty recipient name raises CertificateGenerationError."""
    with pytest.raises(CertificateGenerationError):
        generate_certificate({"name": "   "})

    with pytest.raises(CertificateGenerationError):
        generate_certificate({"email": "anonymous@example.com"})
