"""STRING-DB API client for fetching protein interaction and functional data."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

# Import shared models from uniprot_client to avoid duplication
from app.uniprot_client import (
    ProteinFeature,
    GOTerm,
    GOTermsByDomain,
    ProteinFeatureData,
)

logger = logging.getLogger(__name__)


class StringDBCache:
    """Simple in-memory cache for STRING-DB responses with TTL."""

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
_stringdb_cache = StringDBCache(ttl_hours=24)


class StringDBClient:
    """Client for fetching protein data from STRING-DB API."""

    BASE_URL = "https://string-db.org/api"
    TIMEOUT = 10.0  # seconds
    MAX_RETRIES = 2
    
    # Map strain-specific NCBI IDs to species-level IDs that STRING-DB uses
    ORGANISM_MAP = {
        "559292": "4932",  # S. cerevisiae S288C strain -> S. cerevisiae species
        "9606": "9606",    # H. sapiens (no change)
    }

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
        Fetch protein data from STRING-DB.

        Args:
            protein_id: Protein identifier (systematic name or gene name)
            organism_id: NCBI taxonomy ID (default: 559292 for S. cerevisiae)

        Returns:
            ProteinFeatureData with available data, or error message
        """
        # Check cache first
        cached = _stringdb_cache.get(protein_id)
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

        try:
            # Map organism ID to STRING-DB format (species-level, not strain-level)
            stringdb_organism = self.ORGANISM_MAP.get(organism_id, organism_id)
            
            # Use resolve endpoint which is more reliable
            url = f"{self.BASE_URL}/json/resolve"
            params = {
                "identifier": protein_id,
                "species": stringdb_organism,
            }

            logger.info(f"Querying STRING-DB for {protein_id} (organism: {stringdb_organism})")
            response = await self._client.post(url, data=params)
            logger.info(f"STRING-DB response status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                
                if not data or len(data) == 0:
                    result = ProteinFeatureData(
                        protein=protein_id,
                        sequence_length=None,
                        features=[],
                        error="Protein not found in STRING-DB",
                    )
                    _stringdb_cache.set(protein_id, result)
                    return result

                # Extract basic info
                protein_info = data[0]
                string_id = protein_info.get("stringId", "")
                annotation = protein_info.get("annotation", "")
                
                # Fetch enrichment data for GO terms
                go_terms = await self._fetch_go_terms(string_id, stringdb_organism)
                
                # STRING-DB doesn't provide detailed sequence features like domains
                # We return basic info with GO terms
                result = ProteinFeatureData(
                    protein=protein_id,
                    sequence_length=None,  # STRING-DB doesn't provide sequence length directly
                    features=[],  # No detailed features from STRING-DB
                    go_terms=go_terms,
                    error=None,
                )
                
                _stringdb_cache.set(protein_id, result)
                return result

            elif response.status_code == 429:
                # Rate limited
                logger.warning(f"Rate limited by STRING-DB")
                await asyncio.sleep(2)
                
            elif response.status_code >= 500:
                logger.warning(f"STRING-DB server error {response.status_code}")

        except httpx.TimeoutException as e:
            logger.warning(f"Timeout fetching data for {protein_id}: {str(e)}")
        except Exception as e:
            logger.error(f"Error fetching data for {protein_id}: {str(e)}", exc_info=True)

        # No results found after all attempts
        result = ProteinFeatureData(
            protein=protein_id,
            sequence_length=None,
            features=[],
            error="Failed to fetch data from STRING-DB",
        )
        _stringdb_cache.set(protein_id, result)
        return result

    async def _fetch_go_terms(
        self, string_id: str, organism_id: str
    ) -> GOTermsByDomain | None:
        """Fetch GO annotations from STRING-DB."""
        if not self._client:
            return None

        try:
            # Use functional annotation endpoint for single proteins
            url = f"{self.BASE_URL}/json/functional_annotation"
            params = {
                "identifiers": string_id,
                "species": organism_id,
            }

            response = await self._client.post(url, data=params)
            
            if response.status_code != 200:
                logger.warning(f"STRING-DB GO terms request failed: {response.status_code}")
                return None

            data = response.json()
            
            biological_process: list[GOTerm] = []
            cellular_component: list[GOTerm] = []
            molecular_function: list[GOTerm] = []
            
            # STRING-DB returns annotations grouped by category
            for item in data:
                category = item.get("category", "")
                term_id = item.get("term", "")
                description = item.get("description", "")
                
                # Skip non-GO terms
                if not term_id or not term_id.startswith("GO:"):
                    continue
                
                # Extract p-value if available (from functional_annotation endpoint)
                p_value = item.get("p_value") or item.get("fdr")
                if p_value is not None:
                    try:
                        p_value = float(p_value)
                    except (ValueError, TypeError):
                        p_value = None
                
                go_term = GOTerm(
                    id=term_id,
                    name=description,
                    parents=[],
                    evidence=None,  # STRING-DB doesn't provide evidence codes
                    p_value=p_value,
                )
                
                # Categorize by GO domain
                if "Process" in category or "Biological Process" in category:
                    biological_process.append(go_term)
                elif "Component" in category or "Cellular Component" in category:
                    cellular_component.append(go_term)
                elif "Function" in category:
                    molecular_function.append(go_term)
            
            if not biological_process and not cellular_component and not molecular_function:
                return None
            
            return GOTermsByDomain(
                biological_process=biological_process,
                cellular_component=cellular_component,
                molecular_function=molecular_function,
            )
        
        except Exception as e:
            logger.error(f"Error fetching GO terms from STRING-DB: {str(e)}")
            return None


async def fetch_multiple_proteins(
    protein_ids: list[str], organism_id: str = "559292"
) -> list[ProteinFeatureData]:
    """
    Fetch protein features for multiple proteins in parallel from STRING-DB.

    Args:
        protein_ids: List of protein identifiers
        organism_id: NCBI taxonomy ID (default: 559292 for S. cerevisiae)

    Returns:
        List of ProteinFeatureData, one per protein (includes errors for failed fetches)
    """
    async with StringDBClient() as client:
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
