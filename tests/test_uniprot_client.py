"""Tests for UniProt API client."""

import pytest

from app.uniprot_client import (
    ProteinFeatureData,
    UniProtCache,
    UniProtClient,
    fetch_multiple_proteins,
)


def test_uniprot_cache():
    """Test that cache stores and retrieves data correctly."""
    cache = UniProtCache(ttl_hours=24)

    # Test cache miss
    assert cache.get("TEST_PROTEIN") is None

    # Test cache set and hit
    data = ProteinFeatureData(
        protein="TEST_PROTEIN",
        sequence_length=100,
        features=[],
        error=None,
    )
    cache.set("TEST_PROTEIN", data)
    cached_data = cache.get("TEST_PROTEIN")
    assert cached_data is not None
    assert cached_data.protein == "TEST_PROTEIN"
    assert cached_data.sequence_length == 100


@pytest.mark.asyncio
async def test_fetch_protein_features_not_found():
    """Test fetching a protein that doesn't exist."""
    async with UniProtClient() as client:
        result = await client.fetch_protein_features("NONEXISTENT_PROTEIN_XYZ123")
        assert result.protein == "NONEXISTENT_PROTEIN_XYZ123"
        assert result.error is not None
        assert "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_fetch_multiple_proteins():
    """Test fetching multiple proteins in parallel."""
    # Use a mix of potentially valid and invalid protein IDs
    protein_ids = ["YAL001C", "INVALID_PROTEIN_XYZ"]
    results = await fetch_multiple_proteins(protein_ids)

    assert len(results) == 2
    assert all(isinstance(r, ProteinFeatureData) for r in results)

    # Check that we got results for both proteins (even if errors)
    proteins_returned = {r.protein for r in results}
    assert proteins_returned == set(protein_ids)
