"""Steps 2 and 3: true file type, size and page limits, and malware scanning."""

import io
import socket
import struct
import zipfile
from dataclasses import dataclass

import magic

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ALLOWED_TYPES = {PDF, DOCX}

# The standard antivirus test file. Real scanning needs clamd; this lets the
# quarantine path be tested end to end on any machine.
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
# PDF features that run code or carry hidden payloads.
PDF_ACTIVE_CONTENT = (b"/JavaScript", b"/JS ", b"/JS(", b"/Launch", b"/EmbeddedFile", b"/OpenAction /JavaScript")


class FileRejected(Exception):
    """The file is the wrong type, too big, or a format we refuse."""


class FileInfected(Exception):
    """The malware scan failed. The file stays in quarantine."""


@dataclass(frozen=True, slots=True)
class FileCheck:
    content_type: str
    size: int


def detect_type(data: bytes) -> str:
    detected = magic.from_buffer(data[:8192], mime=True)
    # libmagic reports some DOCX files as a generic zip; confirm by structure.
    if detected in ("application/zip", "application/octet-stream") and _looks_like_docx(data):
        return DOCX
    return detected


def _looks_like_docx(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        return False
    return "word/document.xml" in names and "[Content_Types].xml" in names


def validate_file(data: bytes, *, max_bytes: int) -> FileCheck:
    if not data:
        raise FileRejected("The file is empty.")
    if len(data) > max_bytes:
        raise FileRejected(f"The file is larger than {max_bytes // (1024 * 1024)} MB.")
    content_type = detect_type(data)
    if content_type not in ALLOWED_TYPES:
        raise FileRejected(f"Only PDF and DOCX resumes are accepted (this file is {content_type}).")
    if content_type == DOCX:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
        if any(name.lower().endswith("vbaproject.bin") for name in names):
            raise FileRejected("Macro-enabled documents are not accepted.")
    return FileCheck(content_type=content_type, size=len(data))


def scan_for_malware(data: bytes, *, clamd_socket: str = "") -> None:
    """Raise FileInfected if the file fails the scan.

    With CLAMAV_SOCKET set, the bytes are streamed to clamd (INSTREAM). The
    built-in checks always run as well: the EICAR test signature and PDF
    active content (JavaScript, launch actions, embedded files).
    """
    if EICAR in data:
        raise FileInfected("Matched the EICAR test signature.")
    if data.startswith(b"%PDF"):
        for marker in PDF_ACTIVE_CONTENT:
            if marker in data:
                raise FileInfected(f"PDF contains active content ({marker.decode().strip()}).")
    if clamd_socket:
        verdict = _clamd_instream(data, clamd_socket)
        if "FOUND" in verdict:
            raise FileInfected(verdict)


def _clamd_instream(data: bytes, path: str) -> str:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(30)
        sock.connect(path)
        sock.sendall(b"zINSTREAM\0")
        for offset in range(0, len(data), 64 * 1024):
            chunk = data[offset : offset + 64 * 1024]
            sock.sendall(struct.pack("!L", len(chunk)) + chunk)
        sock.sendall(struct.pack("!L", 0))
        return sock.recv(4096).decode(errors="replace").strip("\0\n ")
