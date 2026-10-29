import logging
from typing import Tuple
from fastapi import HTTPException, UploadFile, status

logger = logging.getLogger(__name__)

# Allowed MIME types
ALLOWED_MIME_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mpeg",
    "audio/mp3",
    "audio/webm",
    "audio/ogg",
    "audio/flac",
    "video/webm",  # Web browsers often record audio in a WebM container with video/webm MIME
}

# Magic byte signatures
MAGIC_SIGNATURES = [
    (b"RIFF", 0, b"WAVE", 8),    # WAV container
    (b"ID3", 0, None, None),     # MP3 ID3v2 tag
    (b"\xff\xfb", 0, None, None), # MP3 MPEG-1 Layer 3 sync
    (b"\xff\xf3", 0, None, None), # MP3 MPEG-2 Layer 3 sync
    (b"\xff\xf2", 0, None, None), # MP3 MPEG-2.5 Layer 3 sync
    (b"OggS", 0, None, None),    # OGG container
    (b"fLaC", 0, None, None),    # FLAC format
    (b"\x1a\x45\xdf\xa3", 0, None, None), # WebM / Matroska EBML
]

# Prohibited executable / suspicious magic signatures
SUSPICIOUS_SIGNATURES = [
    (b"MZ", 0),          # DOS/Windows PE executable
    (b"\x7fELF", 0),     # Linux ELF executable
    (b"\xca\xfe\xba\xbe", 0), # Java class / Mach-O fat binary
    (b"<!DOCTYPE", 0),   # HTML / Script injection
    (b"<html", 0),
    (b"<?php", 0),
    (b"#!\x2f", 0),       # Shebang executable script
]

MIN_AUDIO_BYTES = 100            # Reject empty or truncated stub recordings
MAX_AUDIO_BYTES = 15 * 1024 * 1024 # 15 Megabytes maximum payload

class AudioValidationError(HTTPException):
    """Exception raised when an audio payload fails defensive validation."""
    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

def validate_audio_payload(audio_bytes: bytes, filename: str = "", content_type: str = "") -> None:
    """
    Defensively validate speech audio input as required by Section 21 of the Architecture PDR.
    Checks payload size, MIME type, format header integrity, and rejects suspicious binaries.
    """
    size = len(audio_bytes)

    # 1. Size bounds check
    if size < MIN_AUDIO_BYTES:
        raise AudioValidationError("Audio file is too small or truncated (minimum 100 bytes required).")

    if size > MAX_AUDIO_BYTES:
        raise AudioValidationError(f"Audio file exceeds maximum allowed limit of {MAX_AUDIO_BYTES // (1024*1024)} MB.")

    # 2. Rejection of malicious / executable headers
    for sig, offset in SUSPICIOUS_SIGNATURES:
        if len(audio_bytes) >= offset + len(sig):
            if audio_bytes[offset:offset + len(sig)].lower() == sig.lower():
                logger.warning(f"SECURITY ALERT: Suspicious file content detected in audio upload '{filename}'.")
                raise AudioValidationError("Uploaded file contains invalid or malicious content signatures.")

    # 3. MIME type inspection (if supplied)
    if content_type:
        clean_mime = content_type.split(";")[0].strip().lower()
        if clean_mime not in ALLOWED_MIME_TYPES and clean_mime != "application/octet-stream":
            raise AudioValidationError(
                f"Unsupported audio format '{clean_mime}'. Supported formats: WAV, MP3, WebM, OGG, FLAC."
            )

    # 4. Magic header verification
    is_valid_audio_header = False
    for primary_sig, primary_offset, secondary_sig, secondary_offset in MAGIC_SIGNATURES:
        if len(audio_bytes) >= primary_offset + len(primary_sig):
            if audio_bytes[primary_offset:primary_offset + len(primary_sig)] == primary_sig:
                if secondary_sig is not None and secondary_offset is not None:
                    if len(audio_bytes) >= secondary_offset + len(secondary_sig):
                        if audio_bytes[secondary_offset:secondary_offset + len(secondary_sig)] == secondary_sig:
                            is_valid_audio_header = True
                            break
                else:
                    is_valid_audio_header = True
                    break

    if not is_valid_audio_header:
        # Check if browser WebM without explicit header offset or raw audio stream
        if not (filename.lower().endswith((".wav", ".mp3", ".webm", ".ogg", ".flac"))):
            raise AudioValidationError("Malformed audio header. Audio stream must be a valid WAV, MP3, WebM, or OGG format.")

async def validate_audio_upload(upload_file: UploadFile) -> bytes:
    """Read and validate an UploadFile instance."""
    audio_bytes = await upload_file.read()
    validate_audio_payload(
        audio_bytes=audio_bytes,
        filename=upload_file.filename or "",
        content_type=upload_file.content_type or "",
    )
    return audio_bytes
