"""
GO Hierarchy Client

Fetches Gene Ontology term hierarchy information from external sources.
Uses the QuickGO API from EMBL-EBI to retrieve parent-child relationships.
"""

import logging
from typing import Any
import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class GORelation(BaseModel):
    """Represents a relationship between GO terms."""
    
    id: str  # Target term ID
    relation: str  # is_a, part_of, regulates, etc.


class GOTermHierarchy(BaseModel):
    """GO term with full hierarchy information."""
    
    id: str
    name: str
    parents: list[GORelation] = []  # Parent terms with relationship types
    children: list[GORelation] = []  # Child terms with relationship types
    ancestors: list[str] = []  # All ancestors up to root (IDs only)
    aspect: str | None = None  # biological_process, molecular_function, cellular_component
    all_relations: list[GORelation] = []  # All relationships (not just is_a)


class GOHierarchyResponse(BaseModel):
    """Response containing GO term hierarchy."""
    
    terms: dict[str, GOTermHierarchy]  # Keyed by GO ID
    root_terms: list[str]  # Terms with no parents


class GOHierarchyClient:
    """Client for fetching GO term hierarchy from QuickGO API."""
    
    def __init__(self):
        self.base_url = "https://www.ebi.ac.uk/QuickGO/services"
        self.timeout = 30.0
        
    async def fetch_term_hierarchy(self, go_ids: list[str]) -> GOHierarchyResponse:
        """
        Fetch hierarchy information for a list of GO terms.
        
        Args:
            go_ids: List of GO IDs (e.g., ["GO:0006936", "GO:0003012"])
            
        Returns:
            GOHierarchyResponse with hierarchy information
        """
        if not go_ids:
            return GOHierarchyResponse(terms={}, root_terms=[])
        
        # Remove duplicates and clean IDs
        unique_ids = list(set(go_id.strip() for go_id in go_ids if go_id.strip()))
        
        if not unique_ids:
            return GOHierarchyResponse(terms={}, root_terms=[])
        
        logger.info(f"Fetching GO hierarchy for {len(unique_ids)} terms")
        
        terms_dict: dict[str, GOTermHierarchy] = {}
        
        # Fetch in batches to avoid overwhelming the API
        batch_size = 50
        for i in range(0, len(unique_ids), batch_size):
            batch = unique_ids[i:i + batch_size]
            batch_terms = await self._fetch_batch(batch)
            terms_dict.update(batch_terms)
        
        # Compute direct parents from ancestors
        self._compute_direct_parents(terms_dict)
        
        # Identify root terms (no parents)
        root_terms = [
            term_id for term_id, term in terms_dict.items()
            if not term.parents
        ]
        
        return GOHierarchyResponse(terms=terms_dict, root_terms=root_terms)
    
    def _compute_direct_parents(self, terms_dict: dict[str, GOTermHierarchy]) -> None:
        """
        Compute direct parents for each term.
        Now handles all relationship types, not just is_a.
        """
        # Build parent relationships from children (all relationship types)
        for term_id, term in terms_dict.items():
            # For each child of this term, add this term as a parent with the relationship type
            for child_rel in term.children:
                child_term = terms_dict.get(child_rel.id)
                if child_term:
                    # Check if this parent relationship already exists (check both id and relation)
                    if not any(p.id == term_id and p.relation == child_rel.relation for p in child_term.parents):
                        child_term.parents.append(GORelation(id=term_id, relation=child_rel.relation))
                    # Also add to all_relations (avoiding duplicates)
                    if not any(r.id == term_id and r.relation == child_rel.relation for r in child_term.all_relations):
                        child_term.all_relations.append(GORelation(id=term_id, relation=child_rel.relation))
        
        # Build ancestors list (only is_a relationships for backward compatibility)
        for term_id, term in terms_dict.items():
            is_a_ancestors: set[str] = set()
            
            def collect_ancestors(current_id: str, visited: set[str]) -> None:
                if current_id in visited:
                    return
                visited.add(current_id)
                
                current_term = terms_dict.get(current_id)
                if not current_term:
                    return
                
                for parent_rel in current_term.parents:
                    # Only follow is_a relationships for ancestors
                    if parent_rel.relation == "is_a":
                        is_a_ancestors.add(parent_rel.id)
                        collect_ancestors(parent_rel.id, visited)
            
            collect_ancestors(term_id, set())
            term.ancestors = list(is_a_ancestors)
    
    async def _fetch_batch(self, go_ids: list[str]) -> dict[str, GOTermHierarchy]:
        """Fetch a batch of GO terms."""
        terms_dict: dict[str, GOTermHierarchy] = {}
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for go_id in go_ids:
                try:
                    term_data = await self._fetch_single_term(client, go_id)
                    if term_data:
                        terms_dict[go_id] = term_data
                except Exception as e:
                    logger.warning(f"Failed to fetch hierarchy for {go_id}: {e}")
                    # Add minimal entry
                    terms_dict[go_id] = GOTermHierarchy(
                        id=go_id,
                        name=go_id,
                        parents=[],
                        children=[],
                        ancestors=[],
                        all_relations=[],
                    )
        
        return terms_dict
    
    async def _fetch_single_term(
        self, client: httpx.AsyncClient, go_id: str
    ) -> GOTermHierarchy | None:
        """Fetch a single GO term with hierarchy."""
        try:
            # Fetch term info with ancestors
            url = f"{self.base_url}/ontology/go/terms/{go_id}/ancestors"
            response = await client.get(url)
            
            if response.status_code != 200:
                logger.warning(f"QuickGO returned {response.status_code} for {go_id}")
                return None
            
            data = response.json()
            
            if "results" not in data or not data["results"]:
                return None
            
            result = data["results"][0]
            
            # Extract basic info
            term_id = result.get("id", go_id)
            name = result.get("name", go_id)
            aspect = result.get("aspect")
            
            # Extract children (terms that have this as parent) - ALL relationship types
            children: list[GORelation] = []
            all_relations: list[GORelation] = []
            if "children" in result:
                for child_rel in result["children"]:
                    if isinstance(child_rel, dict):
                        child_id = child_rel.get("id")
                        relation = child_rel.get("relation", "is_a")
                        if child_id:
                            rel = GORelation(id=child_id, relation=relation)
                            children.append(rel)
                            all_relations.append(rel)
            
            # Get all ancestors
            ancestors_list = result.get("ancestors", [])
            logger.info(f"Term {go_id}: ancestors_list = {ancestors_list}")
            # Remove self from ancestors
            ancestors = [a for a in ancestors_list if a != term_id]
            logger.info(f"Term {go_id}: filtered ancestors = {ancestors}")
            
            # For direct parents, we'll infer them later when we have all terms
            # For now, store all ancestors and we'll compute direct parents
            # by finding ancestors that are not ancestors of other ancestors
            parents: list[GORelation] = []
            
            return GOTermHierarchy(
                id=term_id,
                name=name,
                parents=parents,  # Will be computed later
                children=children,
                ancestors=ancestors,
                aspect=aspect,
                all_relations=all_relations,
            )
            
        except Exception as e:
            logger.error(f"Error fetching term {go_id}: {e}")
            return None
    
    async def fetch_complete_hierarchy(
        self, go_ids: list[str], include_ancestors: bool = True
    ) -> GOHierarchyResponse:
        """
        Fetch complete hierarchy including all ancestors.
        
        Args:
            go_ids: Initial list of GO IDs
            include_ancestors: If True, also fetch all ancestor terms
            
        Returns:
            GOHierarchyResponse with complete hierarchy
        """
        # First fetch the requested terms
        initial_response = await self.fetch_term_hierarchy(go_ids)
        
        if not include_ancestors:
            return initial_response
        
        # Collect all ancestor IDs
        all_ancestor_ids: set[str] = set()
        for term in initial_response.terms.values():
            all_ancestor_ids.update(term.ancestors)
        
        # Remove IDs we already have
        new_ids = all_ancestor_ids - set(initial_response.terms.keys())
        
        if not new_ids:
            return initial_response
        
        logger.info(f"Fetching {len(new_ids)} ancestor terms")
        
        # Fetch ancestor terms
        ancestor_response = await self.fetch_term_hierarchy(list(new_ids))
        
        # Merge results
        all_terms = {**initial_response.terms, **ancestor_response.terms}
        
        # Recalculate root terms
        root_terms = [
            term_id for term_id, term in all_terms.items()
            if not term.parents
        ]
        
        return GOHierarchyResponse(terms=all_terms, root_terms=root_terms)


# Singleton instance
_client: GOHierarchyClient | None = None


def get_go_hierarchy_client() -> GOHierarchyClient:
    """Get or create the GO hierarchy client singleton."""
    global _client
    if _client is None:
        _client = GOHierarchyClient()
    return _client
