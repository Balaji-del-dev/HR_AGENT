"""Object storage behind one small interface.

Development stores files on local disk under OBJECT_STORAGE_ROOT, using the
same bucket and key layout as production:
``<bucket>/tenant/<tenant_id>/candidates/<candidate_id>/<document_id>``.
A production deployment swaps in an S3 or Azure Blob implementation of the
same four methods.
"""

from pathlib import Path
from typing import Protocol
from uuid import UUID

from django.conf import settings

QUARANTINE = "quarantine"
DOCUMENTS = "documents"
EXPORTS = "exports"
BUCKETS = (QUARANTINE, DOCUMENTS, EXPORTS)


def document_key(tenant_id: UUID, candidate_id: UUID, document_id: UUID) -> str:
    return f"tenant/{tenant_id}/candidates/{candidate_id}/{document_id}"


class ObjectStorage(Protocol):
    def put(self, bucket: str, key: str, data: bytes) -> None: ...
    def get(self, bucket: str, key: str) -> bytes: ...
    def move(self, source_bucket: str, target_bucket: str, key: str) -> None: ...
    def delete(self, bucket: str, key: str) -> None: ...


class LocalObjectStorage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, bucket: str, key: str) -> Path:
        if bucket not in BUCKETS:
            raise ValueError(f"Unknown bucket {bucket!r}")
        path = (self.root / bucket / key).resolve()
        if not path.is_relative_to((self.root / bucket).resolve()):
            raise ValueError("Key escapes the bucket.")
        return path

    def put(self, bucket: str, key: str, data: bytes) -> None:
        path = self._path(bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o600)

    def get(self, bucket: str, key: str) -> bytes:
        return self._path(bucket, key).read_bytes()

    def move(self, source_bucket: str, target_bucket: str, key: str) -> None:
        source = self._path(source_bucket, key)
        target = self._path(target_bucket, key)
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)

    def delete(self, bucket: str, key: str) -> None:
        self._path(bucket, key).unlink(missing_ok=True)


def get_storage() -> ObjectStorage:
    return LocalObjectStorage(settings.OBJECT_STORAGE_ROOT)
