"""Tests for protein features endpoint."""

import pytest
from fastapi.testclient import TestClient


def test_get_protein_features_invalid_network(client: TestClient) -> None:
    """Test that endpoint works even with invalid network name."""
    # The endpoint should still work even if network doesn't exist
    response = client.get(
        "/api/v1/proteins/invalid_network/features",
        params={"proteins": "YAL001C"},
    )
    # Should return 200 with data or error for the protein
    assert response.status_code == 200
    data = response.json()
    assert "proteins" in data
    assert len(data["proteins"]) == 1


def test_get_protein_features_no_proteins(client: TestClient) -> None:
    """Test that endpoint returns 400 when no proteins specified."""
    response = client.get(
        "/api/v1/proteins/BioGRIDCC24Y/features",
        params={"proteins": ""},
    )
    assert response.status_code == 400


def test_get_protein_features_too_many_proteins(client: TestClient) -> None:
    """Test that endpoint returns 400 when too many proteins requested."""
    # Create a list of 51 proteins
    proteins = ",".join([f"PROTEIN{i}" for i in range(51)])
    response = client.get(
        "/api/v1/proteins/BioGRIDCC24Y/features",
        params={"proteins": proteins},
    )
    assert response.status_code == 400


def test_get_protein_features_single_protein(client: TestClient) -> None:
    """Test fetching features for a single protein."""
    response = client.get(
        "/api/v1/proteins/BioGRIDCC24Y/features",
        params={"proteins": "YAL001C"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "proteins" in data
    assert len(data["proteins"]) == 1
    protein_data = data["proteins"][0]
    assert protein_data["protein"] == "YAL001C"
    assert "sequence_length" in protein_data
    assert "features" in protein_data
    assert "error" in protein_data


def test_get_protein_features_multiple_proteins(client: TestClient) -> None:
    """Test fetching features for multiple proteins."""
    response = client.get(
        "/api/v1/proteins/BioGRIDCC24Y/features",
        params={"proteins": "YAL001C,YAL002W,YAL003W"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "proteins" in data
    assert len(data["proteins"]) == 3

    # Check that all proteins are returned
    proteins_returned = {p["protein"] for p in data["proteins"]}
    assert proteins_returned == {"YAL001C", "YAL002W", "YAL003W"}


def test_get_protein_features_with_name_mode(client: TestClient) -> None:
    """Test fetching features with different name modes."""
    response = client.get(
        "/api/v1/proteins/BioGRIDCC24Y/features",
        params={"proteins": "YAL001C", "name_mode": "gene"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "proteins" in data
    assert len(data["proteins"]) == 1
