import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image, ImageDraw, ImageFont

from app.config import settings
from app.utils.exceptions import CertificateGenerationError

# Set up Jinja2 environment pointing to app/templates
TEMPLATES_DIR = settings.BASE_DIR / "app" / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _load_font(font_name: str, size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Attempt to load a TrueType font from system font paths with graceful fallback."""
    search_dirs = [
        Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts",
        Path("/usr/share/fonts"),
        Path("/usr/share/fonts/truetype"),
        Path("/Library/Fonts"),
    ]
    for directory in search_dirs:
        font_path = directory / font_name
        if font_path.exists():
            try:
                return ImageFont.truetype(str(font_path), size)
            except Exception:
                pass

    # Fallback to default bitmap font if no TTF font could be loaded
    try:
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def render_html_template(context: dict[str, Any]) -> str:
    """Render the Jinja2 certificate HTML template with given context."""
    try:
        template = jinja_env.get_template("certificate.html")
        return template.render(**context)
    except Exception as exc:
        raise CertificateGenerationError(f"Failed to render HTML template: {exc}") from exc


def generate_certificate(
    recipient: dict[str, Any],
    record_id: uuid.UUID | str | None = None,
    output_format: str = "pdf",
) -> str:
    """Generate a certificate file (PDF or PNG) for a recipient.

    Parameters:
        recipient: Dictionary containing recipient info (name, optional email, etc.)
        record_id: Unique record identifier. If not provided, taken from recipient or generated.
        output_format: Output file extension, either 'pdf' or 'png'.

    Returns:
        Absolute string path to the generated certificate file.
    """
    # Resolve record_id
    if record_id is None:
        rec_id = recipient.get("record_id") or recipient.get("id") or str(uuid.uuid4())
    else:
        rec_id = str(record_id)

    # Validate recipient name
    name = recipient.get("name") or recipient.get("recipient_name")
    if not name or not str(name).strip():
        raise CertificateGenerationError(f"Recipient name is required to generate certificate (record: {rec_id})")

    clean_name = str(name).strip()

    # Allow simulated error for failure isolation testing
    if recipient.get("force_failure") is True or clean_name == "__FORCE_FAIL__":
        raise CertificateGenerationError(f"Simulated generation error for recipient '{clean_name}'")

    issue_date = recipient.get("issue_date") or datetime.now(timezone.utc).strftime("%B %d, %Y")
    course_name = recipient.get("course") or "Advanced Professional Training"
    description = (
        recipient.get("description")
        or f"For successful completion and exemplary mastery of {course_name}."
    )

    # Exercise and validate Jinja2 template rendering
    template_context = {
        "record_id": rec_id,
        "recipient_name": clean_name,
        "recipient_email": recipient.get("email"),
        "issue_date": issue_date,
        "course": course_name,
        "description": description,
    }
    render_html_template(template_context)

    # Output directory and target filepath
    output_dir = settings.get_output_dir()
    normalized_format = output_format.lower().lstrip(".")
    if normalized_format not in {"pdf", "png"}:
        normalized_format = "pdf"
    file_path = output_dir / f"{rec_id}.{normalized_format}"

    # Render Certificate Image with Pillow
    try:
        width, height = 1600, 1100
        # Background: Warm off-white / parchment tone
        img = Image.new("RGB", (width, height), color=(253, 252, 248))
        draw = ImageDraw.Draw(img)

        # Decorative borders
        # Outer gold border
        gold = (180, 115, 34)
        gold_light = (217, 160, 80)
        slate_dark = (15, 23, 42)
        slate_gray = (71, 85, 105)

        draw.rectangle([(30, 30), (width - 30, height - 30)], outline=gold, width=8)
        draw.rectangle([(44, 44), (width - 44, height - 44)], outline=gold_light, width=2)
        draw.rectangle([(60, 60), (width - 60, height - 60)], outline=gold, width=3)

        # Corner corner ornaments
        corner_size = 40
        for cx, cy in [(75, 75), (width - 75, 75), (75, height - 75), (width - 75, height - 75)]:
            draw.line([(cx - 15, cy), (cx + 15, cy)], fill=gold, width=3)
            draw.line([(cx, cy - 15), (cx, cy + 15)], fill=gold, width=3)

        # Typography
        title_font = _load_font("georgia.ttf", 46)
        sub_font = _load_font("arial.ttf", 22)
        name_font = _load_font("georgia.ttf", 56)
        body_font = _load_font("georgia.ttf", 24)
        meta_font = _load_font("arial.ttf", 16)

        # Header Title
        title_text = "CERTIFICATE OF ACHIEVEMENT"
        draw.text((width / 2, 170), title_text, fill=gold, font=title_font, anchor="mm")

        # Subtitle
        sub_text = "THIS IS PROUDLY PRESENTED TO"
        draw.text((width / 2, 250), sub_text, fill=slate_gray, font=sub_font, anchor="mm")

        # Recipient Name
        draw.text((width / 2, 380), clean_name, fill=slate_dark, font=name_font, anchor="mm")
        # Underline for recipient name
        bbox = draw.textbbox((width / 2, 380), clean_name, font=name_font, anchor="mm")
        line_w = max(400, (bbox[2] - bbox[0]) + 80)
        draw.line(
            [(width / 2 - line_w / 2, 430), (width / 2 + line_w / 2, 430)],
            fill=gold_light,
            width=3,
        )

        # Description / Body
        draw.text((width / 2, 530), description, fill=slate_dark, font=body_font, anchor="mm")

        # Ribbon / Badge Emblem
        badge_y = 690
        badge_radius = 50
        draw.ellipse(
            [
                (width / 2 - badge_radius, badge_y - badge_radius),
                (width / 2 + badge_radius, badge_y + badge_radius),
            ],
            fill=gold,
            outline=gold_light,
            width=3,
        )
        draw.text((width / 2, badge_y), "★ VERIFIED ★", fill=(255, 255, 255), font=meta_font, anchor="mm")

        # Signatures & Verification Info
        sig_y = 900
        # Left signature
        draw.line([(180, sig_y), (480, sig_y)], fill=slate_gray, width=2)
        draw.text((330, sig_y + 25), "Authorized Signatory", fill=slate_gray, font=meta_font, anchor="mm")

        # Center verification meta
        draw.text((width / 2, sig_y - 15), f"Issued: {issue_date}", fill=slate_gray, font=meta_font, anchor="mm")
        draw.text((width / 2, sig_y + 15), f"ID: {rec_id}", fill=slate_gray, font=meta_font, anchor="mm")

        # Right signature
        draw.line([(width - 480, sig_y), (width - 180, sig_y)], fill=slate_gray, width=2)
        draw.text((width - 330, sig_y + 25), "Program Director", fill=slate_gray, font=meta_font, anchor="mm")

        # Save output in chosen format
        if normalized_format == "pdf":
            img.convert("RGB").save(str(file_path), "PDF", resolution=150.0)
        else:
            img.save(str(file_path), "PNG")

        return str(file_path)

    except Exception as exc:
        if isinstance(exc, CertificateGenerationError):
            raise
        raise CertificateGenerationError(f"Failed to generate certificate image for '{clean_name}': {exc}") from exc
