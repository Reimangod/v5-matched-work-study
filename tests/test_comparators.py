from __future__ import annotations
import hashlib
import pytest
from v5_matched_work.atomic_artifacts import canonical_json_bytes
from v5_matched_work.comparators import CatalogSnapshot,ComparatorError,ImmutableSource,StructuralCandidate,catalog_sequence


def test_rebuilding_is_the_only_catalog_difference() -> None:
    source=CatalogSnapshot("source",("a",));builder=lambda child:CatalogSnapshot(child,(child+"-new",))
    assert catalog_sequence(source,("x",),rebuild=False,builder=builder)==(source,source)
    assert catalog_sequence(source,("x",),rebuild=True,builder=builder)[1].candidate_ids==("x-new",)


def test_source_and_structural_pruning_fail_closed() -> None:
    digest=hashlib.sha256(canonical_json_bytes({"coefficients":(0.1,),"indices":(1,)})).hexdigest()
    ImmutableSource("state-v1:"+"0"*64,"problem-v1:"+"1"*64,(0.1,),(1,),digest)
    with pytest.raises(ComparatorError):StructuralCandidate("zero-only",(0,),())
