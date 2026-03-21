from __future__ import annotations

from pathlib import Path
from typing import Optional

PDF_EXTENSIONS = {".pdf"}
WORD_EXTENSIONS = {".docx"}
POWERPOINT_EXTENSIONS = {".pptx"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".heif", ".heic"}
ZIP_BASED_OFFICE_EXTENSIONS = WORD_EXTENSIONS | POWERPOINT_EXTENSIONS
SUPPORTED_UPLOAD_EXTENSIONS = PDF_EXTENSIONS | ZIP_BASED_OFFICE_EXTENSIONS | IMAGE_EXTENSIONS

CONTENT_TYPE_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".heif": "image/heif",
    ".heic": "image/heic",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".json": "application/json",
    ".txt": "text/plain",
}

_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}


def get_content_type_for_filename(filename: str) -> str:
    return get_content_type_for_extension(Path(filename).suffix.lower())


def get_content_type_for_extension(extension: str) -> str:
    return CONTENT_TYPE_BY_EXTENSION.get(extension.lower(), "application/octet-stream")


def validate_uploaded_file_signature(file_ext: str, file_bytes: bytes) -> Optional[str]:
    file_ext = (file_ext or "").lower()

    if file_ext == ".pdf":
        if not file_bytes.startswith(b"%PDF-"):
            return "File does not appear to be a valid PDF"
        return None

    if file_ext in ZIP_BASED_OFFICE_EXTENSIONS:
        if not file_bytes.startswith(b"PK"):
            if file_ext == ".docx":
                return "File does not appear to be a valid DOCX file"
            if file_ext == ".pptx":
                return "File does not appear to be a valid PPTX file"
            return "File does not appear to be a valid Office file"
        return None

    if file_ext in {".jpg", ".jpeg"}:
        if not file_bytes.startswith(b"\xFF\xD8\xFF"):
            return "File does not appear to be a valid JPEG image"
        return None

    if file_ext == ".png":
        if not file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "File does not appear to be a valid PNG image"
        return None

    if file_ext == ".bmp":
        if not file_bytes.startswith(b"BM"):
            return "File does not appear to be a valid BMP image"
        return None

    if file_ext in {".tif", ".tiff"}:
        if not (file_bytes.startswith(b"II*\x00") or file_bytes.startswith(b"MM\x00*")):
            return "File does not appear to be a valid TIFF image"
        return None

    if file_ext in {".heif", ".heic"}:
        if len(file_bytes) < 12 or file_bytes[4:8] != b"ftyp" or file_bytes[8:12] not in _HEIF_BRANDS:
            return "File does not appear to be a valid HEIF/HEIC image"
        return None

    return None
