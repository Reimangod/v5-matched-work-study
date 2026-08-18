from __future__ import annotations

import pytest

from v5_final.historical_artifact_audit import (
    HistoricalArtifactAuditError,
    manifest_file_matches_artifact_commit,
    parse_sha256_manifest,
)
from v5_final.s11_v2_verifier_design_audit import MANIFEST_PATH, OUTPUT_PATH


def test_historical_manifest_resolves_sources_at_artifact_commit() -> None:
    assert manifest_file_matches_artifact_commit(OUTPUT_PATH, MANIFEST_PATH)


@pytest.mark.parametrize(
    "raw",
    (
        b"",
        b"not-a-digest  file.py\n",
        (b"0" * 64) + b" file.py\n",
        (b"0" * 64) + b"  ../file.py\n",
    ),
)
def test_historical_manifest_parser_rejects_malformed_entries(raw: bytes) -> None:
    with pytest.raises(HistoricalArtifactAuditError):
        parse_sha256_manifest(raw)
