"""Local filesystem storage — real, works now. S3 drops in behind the same interface."""
from __future__ import annotations

import hashlib
from pathlib import Path

from ...config import settings
from ..base import Availability, Capability, ProviderInfo, StorageProvider


class LocalFSStorageProvider(StorageProvider):
    info = ProviderInfo(
        name="local_fs", capability=Capability.STORAGE, kind="local",
        free=True, requires_gpu=False,
    )

    def __init__(self) -> None:
        self.root = settings.assets_dir()

    def availability(self) -> Availability:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            return Availability(True)
        except OSError as e:
            return Availability(False, reason=str(e))

    def put(self, data: bytes, *, name: str, subdir: str = "") -> str:
        target_dir = self.root / subdir if subdir else self.root
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / name
        path.write_bytes(data)
        return str(path.relative_to(self.root)).replace("\\", "/")

    def open(self, rel_path: str) -> bytes:
        return (self.root / rel_path).read_bytes()

    def abs_path(self, rel_path: str) -> str:
        return str((self.root / rel_path).resolve())

    @staticmethod
    def sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()
