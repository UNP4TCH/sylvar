"""Document security guards: magic-byte validation and archive bomb protection.

Enforces:
- File size <= 20MB (TASK-016)
- Supported formats: TXT, MD, DOCX, PDF
- DOCX zip protection: <=500 entries, <=50MB uncompressed, <=100:1 ratio, no path traversal
"""
import io
import zipfile

from app.core.errors import ProblemException

_MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB
_MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # 50 MB
_MAX_ZIP_ENTRIES = 500
_MAX_COMPRESSION_RATIO = 100.0


def validate_file_size(size_bytes: int) -> None:
    if size_bytes > _MAX_FILE_BYTES:
        raise ProblemException(
            status=413,
            code="FILE_TOO_LARGE",
            title="Payload Too Large",
            detail=f"File size exceeds maximum limit of {_MAX_FILE_BYTES // (1024*1024)} MB.",
        )


def detect_file_format(filename: str, content: bytes) -> str:
    """Detect and validate file format using extensions and magic bytes."""
    lower_name = filename.lower()
    if lower_name.endswith(".txt"):
        return "TXT"
    if lower_name.endswith(".md"):
        return "MD"
    if lower_name.endswith(".pdf"):
        if not content.startswith(b"%PDF-"):
            raise ProblemException(
                status=415,
                code="UNSUPPORTED_MEDIA_TYPE",
                title="Unsupported Media Type",
                detail="File claims to be PDF but lacks valid %PDF header.",
            )
        return "PDF"
    if lower_name.endswith(".docx"):
        if not content.startswith(b"PK\x03\x04"):
            raise ProblemException(
                status=415,
                code="UNSUPPORTED_MEDIA_TYPE",
                title="Unsupported Media Type",
                detail="File claims to be DOCX but lacks valid ZIP header.",
            )
        return "DOCX"

    raise ProblemException(
        status=415,
        code="UNSUPPORTED_MEDIA_TYPE",
        title="Unsupported Media Type",
        detail="Only TXT, Markdown (.md), DOCX, and PDF documents are supported.",
    )


def validate_docx_archive_safety(content: bytes) -> None:
    """DOCX archive safety guards (TASK-016)."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            infolist = zf.infolist()
            if len(infolist) > _MAX_ZIP_ENTRIES:
                raise ProblemException(
                    status=422,
                    code="DECOMPRESSION_BOMB_DETECTED",
                    title="Unprocessable Entity",
                    detail=f"DOCX contains too many entries ({len(infolist)} > {_MAX_ZIP_ENTRIES}).",
                )

            total_uncompressed = 0
            for info in infolist:
                # Path traversal check
                if ".." in info.filename or info.filename.startswith("/") or info.filename.startswith("\\"):
                    raise ProblemException(
                        status=422,
                        code="DECOMPRESSION_BOMB_DETECTED",
                        title="Unprocessable Entity",
                        detail="Archive contains unsafe path traversal sequences.",
                    )

                total_uncompressed += info.file_size
                if total_uncompressed > _MAX_UNCOMPRESSED_BYTES:
                    raise ProblemException(
                        status=422,
                        code="DECOMPRESSION_BOMB_DETECTED",
                        title="Unprocessable Entity",
                        detail="Uncompressed document size exceeds safe threshold (50 MB).",
                    )

                compressed_size = max(info.compress_size, 1)
                ratio = info.file_size / compressed_size
                if ratio > _MAX_COMPRESSION_RATIO:
                    raise ProblemException(
                        status=422,
                        code="DECOMPRESSION_BOMB_DETECTED",
                        title="Unprocessable Entity",
                        detail=f"Suspicious compression ratio ({ratio:.1f}:1) detected.",
                    )
    except zipfile.BadZipFile:
        raise ProblemException(
            status=415,
            code="UNSUPPORTED_MEDIA_TYPE",
            title="Unsupported Media Type",
            detail="File is not a valid zip/docx archive.",
        ) from None
