"""Exact source-state transaction with fail-closed rollback evidence."""

from __future__ import annotations

from dataclasses import dataclass

from .architecture_state import ArchitectureState


class TransactionError(RuntimeError):
    pass


@dataclass(frozen=True)
class RollbackEvidence:
    source_digest_before: str
    source_digest_after: str
    reason: str

    @property
    def exact(self) -> bool:
        return self.source_digest_before == self.source_digest_after


class ArchitectureTransaction:
    def __init__(self, source: ArchitectureState) -> None:
        self._source = source
        self._working = source
        self._closed = False

    @property
    def source(self) -> ArchitectureState:
        return self._source

    @property
    def working(self) -> ArchitectureState:
        return self._working

    def stage(self, candidate: ArchitectureState) -> None:
        if self._closed:
            raise TransactionError("closed transaction cannot stage")
        if candidate.problem_id != self._source.problem_id:
            raise TransactionError("candidate problem differs from source")
        self._working = candidate

    def commit(self) -> ArchitectureState:
        if self._closed:
            raise TransactionError("transaction already closed")
        self._closed = True
        return self._working

    def rollback(self, reason: str) -> RollbackEvidence:
        if self._closed:
            raise TransactionError("transaction already closed")
        before = self._source.source_digest
        self._working = self._source
        self._closed = True
        evidence = RollbackEvidence(before, self._working.source_digest, reason)
        if not evidence.exact:
            raise TransactionError("rollback did not restore exact source digest")
        return evidence
