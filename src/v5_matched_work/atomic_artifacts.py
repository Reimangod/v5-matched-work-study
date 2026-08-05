"""Canonical finite JSON and atomic exclusive-create artifact publication."""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
from typing import Any


class ArtifactPublicationError(RuntimeError):
    """Raised when an immutable artifact cannot be safely published."""


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize deterministic JSON while rejecting NaN and infinity."""

    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_bytes_exclusive(path: Path, payload: bytes) -> None:
    """Publish bytes atomically and fail if the canonical path already exists.

    A unique same-directory staging file is fully written and fsynced. A hard
    link then publishes the canonical name atomically with exclusive-create
    semantics; unlike ``os.replace``, this can never overwrite existing data.
    """

    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    staging = path.parent / f".staging-{path.name}-{secrets.token_hex(16)}"
    descriptor: int | None = None
    try:
        descriptor = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise ArtifactPublicationError("staging write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.link(staging, path)
        _fsync_directory(path.parent)
    except FileExistsError:
        raise
    except OSError as error:
        raise ArtifactPublicationError(f"artifact publication failed: {path}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            staging.unlink()
        except FileNotFoundError:
            pass


def write_json_exclusive(path: Path, value: Any) -> None:
    write_bytes_exclusive(path, canonical_json_bytes(value))
