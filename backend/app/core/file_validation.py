"""
File content validation for TrustVault.

Validates file contents by inspecting magic bytes (file signatures)
rather than trusting client-supplied MIME types or filename extensions.
This prevents attackers from disguising malicious files by spoofing
the Content-Type header or renaming the file extension.

Each supported format is defined by one or more byte-signature prefixes,
a canonical MIME type, and a canonical file extension.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FileFormat:
    """Describes a validated file format detected from magic bytes."""
    mime_type: str
    extension: str      # includes the leading dot, e.g. ".pdf"
    label: str          # human-readable label for error messages


# ---------------------------------------------------------------------------
# Signature table: (byte_prefix, FileFormat)
#
# Order matters – more specific signatures must appear before shorter
# generic ones (e.g. DOCX/XLSX before generic ZIP).
# ---------------------------------------------------------------------------

_SIGNATURES: list[tuple[bytes, FileFormat]] = [
    # PDF
    (b"%PDF", FileFormat("application/pdf", ".pdf", "PDF")),

    # PNG
    (b"\x89PNG\r\n\x1a\n", FileFormat("image/png", ".png", "PNG")),

    # JPEG (JFIF / Exif – both start with FF D8 FF)
    (b"\xff\xd8\xff", FileFormat("image/jpeg", ".jpg", "JPEG")),

    # Office Open XML (.docx, .xlsx) – ZIP-based; must come before
    # a generic ZIP check (which we don't allow).
    # We detect the PK header here and further disambiguate by
    # checking the [Content_Types].xml inside the ZIP.
    # Since we cannot unzip in a simple prefix check we also accept
    # the standard Office Open XML byte prefix (PK\x03\x04).
    # Disambiguation between .docx and .xlsx happens in a second pass.

    # Legacy MS Word (.doc) – Compound Binary File format (OLE2)
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", FileFormat("application/msword", ".doc", "Word (legacy)")),
]

# Office Open XML formats share the same ZIP signature; we need to peek
# inside the ZIP to tell .docx from .xlsx.  We handle this in _detect_ooxml.
_OOXML_FORMATS: dict[str, FileFormat] = {
    "word/": FileFormat(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
        "Word",
    ),
    "xl/": FileFormat(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
        "Excel",
    ),
}

# Plain text is validated heuristically (see _is_plausible_text).
_TEXT_FORMAT = FileFormat("text/plain", ".txt", "Plain text")


def _detect_ooxml(content: bytes) -> FileFormat | None:
    """
    Attempt to classify an Office Open XML file (ZIP-based) by scanning
    for well-known directory names within the first 2 KiB of content.

    Returns a FileFormat for .docx or .xlsx, or None if unrecognised.
    """
    import zipfile
    import io

    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
            names = zf.namelist()
    except (zipfile.BadZipFile, Exception):
        return None

    for prefix, fmt in _OOXML_FORMATS.items():
        if any(n.startswith(prefix) for n in names):
            return fmt

    return None


def _is_plausible_text(content: bytes) -> bool:
    """
    Heuristic check: treat the file as plausible plain text if:
    - It is entirely decodable as UTF-8 (or ASCII), AND
    - It contains no NULL bytes (which would indicate a binary file).

    This is intentionally conservative – we would rather reject an
    unusual text file than accept a disguised binary.
    """
    if b"\x00" in content:
        return False
    try:
        content.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def validate_file_content(content: bytes) -> FileFormat | None:
    """
    Validate file content by inspecting magic bytes.

    Returns a ``FileFormat`` describing the detected format,
    or ``None`` if the content does not match any supported format.
    """
    # 1. Check fixed magic-byte signatures
    for signature, fmt in _SIGNATURES:
        if content[:len(signature)] == signature:
            return fmt

    # 2. Check for ZIP-based Office Open XML
    if content[:4] == b"PK\x03\x04":
        ooxml = _detect_ooxml(content)
        if ooxml is not None:
            return ooxml
        # A generic ZIP is not permitted
        return None

    # 3. Fall back to plain-text heuristic
    if _is_plausible_text(content):
        return _TEXT_FORMAT

    return None
