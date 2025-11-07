"""UniProt API client for fetching protein sequence and feature data."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ProteinFeature(BaseModel):
    """Represents a single protein sequence feature."""

    type: str
    description: str
    start: int
    end: int


class ProteinFeatureData(BaseModel):
    """Represents protein data with features for a single protein."""

    protein: str
    sequence_length: int | None
    features: list[ProteinFeature]
    error: str | None


class ProteinFeaturesResponse(BaseModel):
    """Response containing feature data for multiple proteins."""

    proteins: list[ProteinFeatureData]


class UniProtCache:
    """Simple in-memory cache for UniProt responses with TTL."""

    def __init__(self, ttl_hours: int = 24):
        self._cache: dict[str, tuple[datetime, ProteinFeatureData]] = {}
        self._ttl = timedelta(hours=ttl_hours)

    def get(self, protein_id: str) -> ProteinFeatureData | None:
        """Get cached data if available and not expired."""
        if protein_id in self._cache:
            timestamp, data = self._cache[protein_id]
            if datetime.now() - timestamp < self._ttl:
                return data
            # Expired, remove from cache
            del self._cache[protein_id]
        return None

    def set(self, protein_id: str, data: ProteinFeatureData) -> None:
        """Store data in cache with current timestamp."""
        self._cache[protein_id] = (datetime.now(), data)


# Global cache instance
_uniprot_cache = UniProtCache(ttl_hours=24)


class UniProtClient:
    """Client for fetching protein data from UniProt REST API."""

    BASE_URL = "https://rest.uniprot.org/uniprotkb"
    TIMEOUT = 10.0  # seconds
    MAX_RETRIES = 2

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=self.TIMEOUT)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    async def fetch_protein_features(
        self, protein_id: str, organism_id: str = "559292"
    ) -> ProteinFeatureData:
        """
        Fetch protein sequence length and features from UniProt.

        Args:
            protein_id: Protein identifier (systematic name or gene name)
            organism_id: NCBI taxonomy ID (default: 559292 for S. cerevisiae)

        Returns:
            ProteinFeatureData with sequence length and features, or error message
        """
        # Check cache first
        cached = _uniprot_cache.get(protein_id)
        if cached:
            logger.info(f"Cache hit for protein {protein_id}")
            return cached

        if not self._client:
            return ProteinFeatureData(
                protein=protein_id,
                sequence_length=None,
                features=[],
                error="HTTP client not initialized",
            )

        # Try both systematic name and gene name queries
        queries = [
            f"gene:{protein_id} AND organism_id:{organism_id}",
            f"accession:{protein_id}",
            f"{protein_id} AND organism_id:{organism_id}",
        ]

        for attempt, query in enumerate(queries):
            try:
                url = f"{self.BASE_URL}/search"
                params = {
                    "query": query,
                    "format": "json",
                    # Expanded feature set with valid UniProt field names
                    "fields": (
                        "length,"
                        "ft_domain,ft_region,ft_motif,ft_repeat,ft_site,ft_act_site,"  # Core features
                        "ft_transmem,ft_intramem,ft_topo_dom,"  # Membrane features
                        "ft_signal,ft_transit,ft_propep,ft_chain,ft_peptide,"  # Processing
                        "ft_helix,ft_strand,ft_turn,"  # Secondary structure
                        "ft_compbias,ft_disulfid,ft_crosslnk,"  # Structural
                        "ft_mod_res,ft_lipid,ft_carbohyd,"  # PTMs
                        "ft_var_seq,ft_variant,ft_mutagen,ft_conflict"  # Variations
                    ),
                    "size": "1",  # Only need first result
                }

                logger.info(f"Querying UniProt for {protein_id} (attempt {attempt + 1}): {query}")
                response = await self._client.get(url, params=params)
                logger.info(f"UniProt response status: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", [])
                    logger.info(f"UniProt returned {len(results)} results for {protein_id}")

                    if results:
                        result = self._parse_uniprot_response(protein_id, results[0])
                        logger.info(f"Parsed result for {protein_id}: length={result.sequence_length}, features={len(result.features)}, error={result.error}")
                        _uniprot_cache.set(protein_id, result)
                        return result

                elif response.status_code == 429:
                    # Rate limited, wait and retry
                    logger.warning(f"Rate limited by UniProt, waiting before retry")
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue

                elif response.status_code >= 500:
                    # Server error, try next query
                    logger.warning(
                        f"UniProt server error {response.status_code} for {protein_id}"
                    )
                    continue

            except httpx.TimeoutException as e:
                logger.warning(f"Timeout fetching data for {protein_id}: {str(e)}")
                continue
            except Exception as e:
                logger.error(f"Error fetching data for {protein_id}: {str(e)}", exc_info=True)
                continue

        # No results found after all attempts
        result = ProteinFeatureData(
            protein=protein_id,
            sequence_length=None,
            features=[],
            error="Protein not found in UniProt",
        )
        _uniprot_cache.set(protein_id, result)
        return result

    def _parse_uniprot_response(
        self, protein_id: str, entry: dict[str, Any]
    ) -> ProteinFeatureData:
        """Parse UniProt JSON response to extract sequence length and features."""
        try:
            # Extract sequence length
            sequence_length = entry.get("sequence", {}).get("length")

            # Define allowed feature types (only show meaningful features)
            # Domain: Main functional domains (most important)
            # Repeat: Repeated sequence patterns
            # Region: Meaningful regions of interest
            # Transit peptide: Targeting sequences
            # Chain: Processed mature protein chain
            ALLOWED_FEATURE_TYPES = {
                "Domain",
                "Repeat",
                "Region",
                "Transit peptide",
                "Chain",
            }

            # Extract features
            features: list[ProteinFeature] = []
            raw_features = entry.get("features", [])

            for feature in raw_features:
                feature_type = feature.get("type", "Unknown")
                
                # Filter: only include allowed feature types
                if feature_type not in ALLOWED_FEATURE_TYPES:
                    continue
                
                description = feature.get("description", feature_type)

                # Extract location
                location = feature.get("location", {})
                start_loc = location.get("start", {})
                end_loc = location.get("end", {})

                # Get position values (handle both value and position fields)
                start = start_loc.get("value") or start_loc.get("position")
                end = end_loc.get("value") or end_loc.get("position")

                if start is not None and end is not None:
                    features.append(
                        ProteinFeature(
                            type=feature_type,
                            description=description,
                            start=int(start),
                            end=int(end),
                        )
                    )

            return ProteinFeatureData(
                protein=protein_id,
                sequence_length=sequence_length,
                features=features,
                error=None,
            )

        except Exception as e:
            logger.error(f"Error parsing UniProt response for {protein_id}: {str(e)}")
            return ProteinFeatureData(
                protein=protein_id,
                sequence_length=None,
                features=[],
                error=f"Error parsing UniProt data: {str(e)}",
            )


async def fetch_multiple_proteins(
    protein_ids: list[str], organism_id: str = "559292"
) -> list[ProteinFeatureData]:
    """
    Fetch protein features for multiple proteins in parallel.

    Args:
        protein_ids: List of protein identifiers
        organism_id: NCBI taxonomy ID (default: 559292 for S. cerevisiae)

    Returns:
        List of ProteinFeatureData, one per protein (includes errors for failed fetches)
    """
    async with UniProtClient() as client:
        tasks = [
            client.fetch_protein_features(protein_id, organism_id)
            for protein_id in protein_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error responses
        processed_results: list[ProteinFeatureData] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(
                    ProteinFeatureData(
                        protein=protein_ids[i],
                        sequence_length=None,
                        features=[],
                        error=f"Error fetching data: {str(result)}",
                    )
                )
            else:
                processed_results.append(result)

        return processed_results
