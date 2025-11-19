import csv
import logging
import os
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.api.routes.networks import (
    _load_sgd_sys_to_gene_map,
    parse_gdf_to_cytoscape,
    _resolve_network_dir,
    _data_root,
)
from app.uniprot_client import (
    ProteinFeaturesResponse,
    fetch_multiple_proteins as fetch_uniprot_proteins,
)
from app import stringdb_client
from app.go_hierarchy_client import (
    get_go_hierarchy_client,
    GOHierarchyResponse,
)


router = APIRouter(tags=["proteins"], prefix="/proteins")
logger = logging.getLogger(__name__)


class ProteinItem(BaseModel):
    protein: str
    files: list[str]
    types: list[str]


class PagedProteins(BaseModel):
    items: list[ProteinItem]
    total: int
    page: int
    size: int


def _read_network_dir(network_name: str) -> str:
    try:
        return _resolve_network_dir(network_name)
    except HTTPException:
        # Re-raise preserving the same messages/status codes
        raise


def _iter_gdf_files(dir_path: str) -> list[str]:
    gdf_files = [
        f for f in os.listdir(dir_path)
        if f.endswith(".gdf") and os.path.isfile(os.path.join(dir_path, f))
    ]
    gdf_files.sort()
    return gdf_files


def _strip_quotes(value: str) -> str:
    if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
        return value[1:-1]
    return value


def _collect_proteins_from_gdf(file_path: str, *, name_mode: Literal["systematic", "gene"], sgd_map: dict[str, str]) -> dict[str, set[str]]:
    """Parse a GDF file and return a mapping of protein token -> set of types seen.

    Determine indices for 'label' and optional 'type'. For each node line before
    'edgedef>', split the label by whitespace and collect its tokens. For each token,
    associate the node's 'type' value if present (e.g., 'prediction', 'matched_prediction',
    'reference', 'matched_reference').
    """
    token_to_types: dict[str, set[str]] = {}
    with open(file_path, encoding="utf-8") as fh:
        in_nodes = False
        label_index: int | None = None
        type_index: int | None = None
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("nodedef>"):
                in_nodes = True
                # Parse node attributes; extract attribute names before the first space/colon
                header = line[len("nodedef>") :]
                attrs = [part.strip() for part in header.split(",")]
                attr_names: list[str] = []
                for attr in attrs:
                    # Attribute can be like: name VARCHAR or name VARCHAR default ''
                    # We only need the attribute name (first token up to space/colon)
                    first = attr.split()[0]
                    # Defensive: remove potential type delimiter
                    first = first.split(":")[0]
                    attr_names.append(first)
                # Find label index with fallbacks
                if "label" in attr_names:
                    label_index = attr_names.index("label")
                elif "name" in attr_names:
                    label_index = attr_names.index("name")
                else:
                    label_index = 0 if attr_names else None
                type_index = attr_names.index("type") if "type" in attr_names else None
                continue
            if line.startswith("edgedef>"):
                # Node section is over
                in_nodes = False
                # We can stop scanning further for proteins
                # but continue in case there are multiple nodedef sections (rare)
                continue
            if in_nodes and label_index is not None:
                # Use CSV reader to properly handle quoted values and commas
                for row in csv.reader([line], delimiter=",", quotechar="'", skipinitialspace=True):
                    if label_index < len(row):
                        label_val = _strip_quotes(row[label_index].strip())
                        type_val = None
                        if type_index is not None and type_index < len(row):
                            type_val = _strip_quotes(row[type_index].strip())
                        if label_val:
                            base = [tok.strip() for tok in label_val.split() if tok.strip()]
                            mapped = [sgd_map.get(t.upper(), t) for t in base] if name_mode == "gene" else base
                            for token_clean in mapped:
                                if token_clean:
                                    if token_clean not in token_to_types:
                                        token_to_types[token_clean] = set()
                                    if type_val:
                                        token_to_types[token_clean].add(type_val)
                                    else:
                                        _ = token_to_types[token_clean]
    return token_to_types


# NOTE: Define the generic catch-all route AFTER all more specific routes to avoid shadowing.
# get_proteins route moved below to avoid shadowing specific routes


class ComponentsRequest(BaseModel):
    proteins: list[str]
    name_mode: Literal["systematic", "gene"] | None = None


class ComponentEntry(BaseModel):
    component_id: int
    size: int  # number of nodes
    edges: int  # number of edges within the component
    proteins_count: int  # number of unique protein tokens in the component
    proteins: list[str]  # selected proteins present in the component


class FileComponents(BaseModel):
    filename: str
    components: list[ComponentEntry]


class ComponentsResponse(BaseModel):
    files: list[FileComponents]


def _parse_nodes_and_edges_with_types(file_path: str, *, name_mode: Literal["systematic", "gene"], sgd_map: dict[str, str]) -> tuple[list[str], list[tuple[str, str]], dict[str, set[str]], dict[str, str], list[tuple[str, str, str]], dict[str, str]]:
    """Parse nodes and edges, returning edge types and node types as well.
    
    Returns:
        - node_ids: list of node IDs
        - edges: list of (source, target) tuples
        - node_to_tokens: dict mapping node ID to set of protein tokens
        - node_to_label: dict mapping node ID to label
        - edges_with_types: list of (source, target, type) tuples
        - node_to_type: dict mapping node ID to node type
    """
    node_ids: list[str] = []
    edges: list[tuple[str, str]] = []
    edges_with_types: list[tuple[str, str, str]] = []
    node_to_tokens: dict[str, set[str]] = {}
    node_to_label: dict[str, str] = {}
    node_to_type: dict[str, str] = {}

    with open(file_path, encoding="utf-8") as fh:
        in_nodes = False
        in_edges = False
        node_attr_names: list[str] = []
        edge_attr_names: list[str] = []
        label_index: int | None = None
        id_index: int | None = None
        node_type_index: int | None = None
        node1_index: int | None = None
        node2_index: int | None = None
        edge_type_index: int | None = None

        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("nodedef>"):
                in_nodes = True
                in_edges = False
                header = line[len("nodedef>") :]
                parts = [part.strip() for part in header.split(",")]
                node_attr_names = []
                for p in parts:
                    first = p.split()[0]
                    first = first.split(":")[0]
                    node_attr_names.append(first)
                # Determine indices
                label_index = node_attr_names.index("label") if "label" in node_attr_names else None
                if label_index is None and "name" in node_attr_names:
                    label_index = node_attr_names.index("name")
                id_index = node_attr_names.index("name") if "name" in node_attr_names else (node_attr_names.index("id") if "id" in node_attr_names else 0)
                node_type_index = node_attr_names.index("type") if "type" in node_attr_names else None
                continue
            if line.startswith("edgedef>"):
                in_nodes = False
                in_edges = True
                header = line[len("edgedef>") :]
                parts = [part.strip() for part in header.split(",")]
                edge_attr_names = []
                for p in parts:
                    first = p.split()[0]
                    first = first.split(":")[0]
                    edge_attr_names.append(first)
                node1_index = edge_attr_names.index("node1") if "node1" in edge_attr_names else None
                node2_index = edge_attr_names.index("node2") if "node2" in edge_attr_names else None
                edge_type_index = edge_attr_names.index("type") if "type" in edge_attr_names else None
                continue
            if in_nodes and node_attr_names:
                for row in csv.reader([line], delimiter=",", quotechar="'", skipinitialspace=True):
                    if id_index is None or id_index >= len(row):
                        continue
                    node_id = _strip_quotes(row[id_index].strip())
                    node_id = str(node_id)
                    node_ids.append(node_id)
                    # tokens
                    tokens: set[str] = set()
                    if label_index is not None and label_index < len(row):
                        label_val = _strip_quotes(row[label_index].strip())
                        node_to_label[node_id] = label_val
                        if label_val:
                            base_tokens = [tok.strip() for tok in label_val.split() if tok.strip()]
                            if name_mode == "gene":
                                tokens = {sgd_map.get(t.upper(), t) for t in base_tokens}
                            else:
                                tokens = set(base_tokens)
                    node_to_tokens[node_id] = tokens
                    # node type
                    node_type = "unknown"
                    if node_type_index is not None and node_type_index < len(row):
                        node_type = _strip_quotes(row[node_type_index].strip())
                    node_to_type[node_id] = node_type
                continue
            if in_edges and edge_attr_names and node1_index is not None and node2_index is not None:
                for row in csv.reader([line], delimiter=",", quotechar="'", skipinitialspace=True):
                    if node1_index < len(row) and node2_index < len(row):
                        n1 = _strip_quotes(row[node1_index].strip())
                        n2 = _strip_quotes(row[node2_index].strip())
                        edges.append((str(n1), str(n2)))
                        
                        # Get edge type if available
                        edge_type = "unknown"
                        if edge_type_index is not None and edge_type_index < len(row):
                            edge_type = _strip_quotes(row[edge_type_index].strip())
                        edges_with_types.append((str(n1), str(n2), edge_type))
                continue

    return node_ids, edges, node_to_tokens, node_to_label, edges_with_types, node_to_type


def _parse_nodes_and_edges(file_path: str, *, name_mode: Literal["systematic", "gene"], sgd_map: dict[str, str]) -> tuple[list[str], list[tuple[str, str]], dict[str, set[str]], dict[str, str]]:
    node_ids: list[str] = []
    edges: list[tuple[str, str]] = []
    node_to_tokens: dict[str, set[str]] = {}
    node_to_label: dict[str, str] = {}

    with open(file_path, encoding="utf-8") as fh:
        in_nodes = False
        in_edges = False
        node_attr_names: list[str] = []
        edge_attr_names: list[str] = []
        label_index: int | None = None
        id_index: int | None = None
        node1_index: int | None = None
        node2_index: int | None = None

        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("nodedef>"):
                in_nodes = True
                in_edges = False
                header = line[len("nodedef>") :]
                parts = [part.strip() for part in header.split(",")]
                node_attr_names = []
                for p in parts:
                    first = p.split()[0]
                    first = first.split(":")[0]
                    node_attr_names.append(first)
                # Determine indices
                label_index = node_attr_names.index("label") if "label" in node_attr_names else None
                if label_index is None and "name" in node_attr_names:
                    label_index = node_attr_names.index("name")
                id_index = node_attr_names.index("name") if "name" in node_attr_names else (node_attr_names.index("id") if "id" in node_attr_names else 0)
                continue
            if line.startswith("edgedef>"):
                in_nodes = False
                in_edges = True
                header = line[len("edgedef>") :]
                parts = [part.strip() for part in header.split(",")]
                edge_attr_names = []
                for p in parts:
                    first = p.split()[0]
                    first = first.split(":")[0]
                    edge_attr_names.append(first)
                node1_index = edge_attr_names.index("node1") if "node1" in edge_attr_names else None
                node2_index = edge_attr_names.index("node2") if "node2" in edge_attr_names else None
                continue
            if in_nodes and node_attr_names:
                for row in csv.reader([line], delimiter=",", quotechar="'", skipinitialspace=True):
                    if id_index is None or id_index >= len(row):
                        continue
                    node_id = _strip_quotes(row[id_index].strip())
                    node_id = str(node_id)
                    node_ids.append(node_id)
                    # tokens
                    tokens: set[str] = set()
                    if label_index is not None and label_index < len(row):
                        label_val = _strip_quotes(row[label_index].strip())
                        node_to_label[node_id] = label_val
                        if label_val:
                            base_tokens = [tok.strip() for tok in label_val.split() if tok.strip()]
                            if name_mode == "gene":
                                tokens = {sgd_map.get(t.upper(), t) for t in base_tokens}
                            else:
                                tokens = set(base_tokens)
                    node_to_tokens[node_id] = tokens
                continue
            if in_edges and edge_attr_names and node1_index is not None and node2_index is not None:
                for row in csv.reader([line], delimiter=",", quotechar="'", skipinitialspace=True):
                    if node1_index < len(row) and node2_index < len(row):
                        n1 = _strip_quotes(row[node1_index].strip())
                        n2 = _strip_quotes(row[node2_index].strip())
                        if n1 and n2:
                            edges.append((str(n1), str(n2)))

    return node_ids, edges, node_to_tokens, node_to_label


def _compute_components(node_ids: list[str], edges: list[tuple[str, str]]) -> tuple[dict[str, int], dict[int, int]]:
    parent: dict[str, str] = {n: n for n in node_ids}
    size: dict[str, int] = {n: 1 for n in node_ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if size[ra] < size[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        size[ra] += size[rb]

    for a, b in edges:
        if a in parent and b in parent:
            union(a, b)

    # Compress and assign compact component ids
    root_to_comp: dict[str, int] = {}
    node_to_comp: dict[str, int] = {}
    comp_sizes: dict[int, int] = {}
    next_id = 0
    for n in node_ids:
        r = find(n)
        if r not in root_to_comp:
            root_to_comp[r] = next_id
            comp_sizes[next_id] = 0
            next_id += 1
        cid = root_to_comp[r]
        node_to_comp[n] = cid
        comp_sizes[cid] += 1

    return node_to_comp, comp_sizes


# =============================================================================
# GO Hierarchy Endpoint (must be before /{network_name:path} routes)
# =============================================================================

@router.get("/go-hierarchy", response_model=GOHierarchyResponse)
async def get_go_hierarchy(
    go_ids: str = Query(..., description="Comma-separated list of GO IDs (e.g., GO:0006936,GO:0003012)"),
    include_ancestors: bool = Query(True, description="Include all ancestor terms in the hierarchy"),
) -> Any:
    """
    Fetch GO term hierarchy from QuickGO API.
    
    Returns parent-child relationships and complete hierarchy information
    for the specified GO terms. Optionally includes all ancestor terms
    up to the root of the ontology.
    
    Args:
        go_ids: Comma-separated GO IDs
        include_ancestors: Whether to fetch all ancestor terms
        
    Returns:
        GOHierarchyResponse with hierarchy information
    """
    try:
        # Parse GO IDs
        id_list = [go_id.strip() for go_id in go_ids.split(",") if go_id.strip()]
        
        if not id_list:
            raise HTTPException(status_code=400, detail="No GO IDs provided")
        
        if len(id_list) > 200:
            raise HTTPException(
                status_code=400,
                detail="Too many GO IDs requested (max 200 per request)",
            )
        
        # Fetch hierarchy
        client = get_go_hierarchy_client()
        
        if include_ancestors:
            result = await client.fetch_complete_hierarchy(id_list, include_ancestors=True)
        else:
            result = await client.fetch_term_hierarchy(id_list)
        
        logger.info(f"Fetched hierarchy for {len(result.terms)} GO terms")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching GO hierarchy: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching GO hierarchy: {str(e)}",
        )


# =============================================================================
# Network-specific Endpoints (/{network_name:path})
# =============================================================================

@router.post("/{network_name:path}/components", response_model=ComponentsResponse)
def get_components_membership(network_name: str, body: ComponentsRequest) -> Any:
    try:
        dir_path = _read_network_dir(network_name)
        name_mode: Literal["systematic", "gene"] = body.name_mode or "systematic"
        sgd_map = _load_sgd_sys_to_gene_map()
        gdf_files = _iter_gdf_files(dir_path)
        requested: set[str] = set(body.proteins or [])

        files_out: list[FileComponents] = []
        for filename in gdf_files:
            file_path = os.path.join(dir_path, filename)
            try:
                node_ids, edges, node_to_tokens, _node_to_label = _parse_nodes_and_edges(file_path, name_mode=name_mode, sgd_map=sgd_map)
            except Exception:
                # Skip malformed files
                files_out.append(FileComponents(filename=filename, components=[]))
                continue

            node_to_comp, comp_sizes = _compute_components(node_ids, edges)

            # Build per-component token sets and edge counts
            comp_to_tokens: dict[int, set[str]] = {}
            comp_to_edges_count: dict[int, int] = {}
            for node_id, tokens in node_to_tokens.items():
                cid = node_to_comp.get(node_id)
                if cid is None:
                    continue
                if cid not in comp_to_tokens:
                    comp_to_tokens[cid] = set()
                comp_to_tokens[cid].update(tokens)

            # Count intra-component edges
            for a, b in edges:
                ca = node_to_comp.get(a)
                cb = node_to_comp.get(b)
                if ca is not None and cb is not None and ca == cb:
                    comp_to_edges_count[ca] = comp_to_edges_count.get(ca, 0) + 1

            components: list[ComponentEntry] = []
            for cid in sorted(comp_to_tokens.keys()):
                tokens_in_comp = comp_to_tokens[cid]
                # Only include components containing ALL requested proteins
                if requested and not requested.issubset(tokens_in_comp):
                    continue
                present_selected = sorted(requested.intersection(tokens_in_comp))
                components.append(
                    ComponentEntry(
                        component_id=cid,
                        size=comp_sizes.get(cid, 0),
                        edges=comp_to_edges_count.get(cid, 0),
                        proteins_count=len(tokens_in_comp),
                        proteins=present_selected,
                    )
                )

            files_out.append(FileComponents(filename=filename, components=components))

        return ComponentsResponse(files=files_out)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error computing components: {str(e)}")


class SubgraphNode(BaseModel):
    data: dict[str, Any]


class SubgraphEdge(BaseModel):
    data: dict[str, Any]


class SubgraphGraph(BaseModel):
    nodes: list[SubgraphNode]
    edges: list[SubgraphEdge]


@router.get("/{network_name:path}/components/{filename}/{component_id}", response_model=SubgraphGraph)
def get_component_subgraph(
    network_name: str,
    filename: str,
    component_id: int,
    name_mode: Literal["systematic", "gene"] = Query("systematic"),
) -> Any:
    try:
        dir_path = _read_network_dir(network_name)
        file_path = os.path.join(dir_path, filename)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"File '{filename}' not found")

        # Compute component membership to know which node ids to include
        sgd_map = _load_sgd_sys_to_gene_map()
        node_ids, edges, _node_to_tokens, _node_to_label = _parse_nodes_and_edges(
            file_path, name_mode=name_mode, sgd_map=sgd_map
        )
        node_to_comp, _ = _compute_components(node_ids, edges)
        comp_nodes = {n for n in node_ids if node_to_comp.get(n) == component_id}

        # Parse full GDF to preserve styling attributes (type, weights, similarities, etc.)
        with open(file_path, encoding="utf-8") as f:
            gdf_content = f.read()
        full_graph = parse_gdf_to_cytoscape(gdf_content)

        nodes_out: list[SubgraphNode] = []
        for n in getattr(full_graph, "nodes", []):
            data = getattr(n, "data", {})
            node_id = str(data.get("id", ""))
            if node_id in comp_nodes:
                nodes_out.append(SubgraphNode(data=data))

        comp_node_ids = {str(d.data.get("id", "")) for d in nodes_out}
        edges_out: list[SubgraphEdge] = []
        for e in getattr(full_graph, "edges", []):
            data = getattr(e, "data", {})
            src = str(data.get("source", ""))
            tgt = str(data.get("target", ""))
            if src in comp_node_ids and tgt in comp_node_ids:
                edges_out.append(SubgraphEdge(data=data))

        return SubgraphGraph(nodes=nodes_out, edges=edges_out)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error building subgraph: {str(e)}")


class EdgeTypeStats(BaseModel):
    matched_prediction: int
    matched_reference: int
    prediction: int
    reference: int
    total: int


class ComponentSummary(BaseModel):
    filename: str
    component_id: int
    size: int
    edges: int
    proteins_count: int
    edge_type_stats: EdgeTypeStats | None = None


class PagedComponents(BaseModel):
    items: list[ComponentSummary]
    total: int
    page: int
    size: int


@router.get("/{network_name:path}/components/search", response_model=PagedComponents)
def search_components_by_id(
    network_name: str,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    q: str | None = Query(default=None, description="Search by component ID (exact number or digits)"),
    file: str | None = Query(default=None, description="Optional GDF filename to filter"),
    name_mode: Literal["systematic", "gene"] = Query("systematic"),
    # Node type ratio filters (0.0 to 1.0)
    min_matched_pred: float | None = Query(default=None, ge=0.0, le=1.0, description="Minimum matched prediction node ratio"),
    max_matched_pred: float | None = Query(default=None, ge=0.0, le=1.0, description="Maximum matched prediction node ratio"),
    min_unmatched_pred: float | None = Query(default=None, ge=0.0, le=1.0, description="Minimum unmatched prediction node ratio"),
    max_unmatched_pred: float | None = Query(default=None, ge=0.0, le=1.0, description="Maximum unmatched prediction node ratio"),
    min_matched_ref: float | None = Query(default=None, ge=0.0, le=1.0, description="Minimum matched reference node ratio"),
    max_matched_ref: float | None = Query(default=None, ge=0.0, le=1.0, description="Maximum matched reference node ratio"),
    min_unmatched_ref: float | None = Query(default=None, ge=0.0, le=1.0, description="Minimum unmatched reference node ratio"),
    max_unmatched_ref: float | None = Query(default=None, ge=0.0, le=1.0, description="Maximum unmatched reference node ratio"),
) -> Any:
    try:
        dir_path = _read_network_dir(network_name)
        sgd_map = _load_sgd_sys_to_gene_map()

        files = []
        if file:
            # Validate file exists
            candidate = os.path.join(dir_path, file)
            if not os.path.exists(candidate):
                raise HTTPException(status_code=404, detail=f"File '{file}' not found")
            files = [file]
        else:
            files = list(_iter_gdf_files(dir_path))

        summaries: list[ComponentSummary] = []

        for filename in files:
            file_path = os.path.join(dir_path, filename)
            try:
                node_ids, edges, node_to_tokens, _, edges_with_types, node_to_type = _parse_nodes_and_edges_with_types(file_path, name_mode=name_mode, sgd_map=sgd_map)
            except Exception:
                # Skip malformed files
                continue

            node_to_comp, comp_sizes = _compute_components(node_ids, edges)

            # Build per-component token sets, edge counts, edge type statistics, and node type statistics
            comp_to_tokens: dict[int, set[str]] = {}
            comp_to_edges_count: dict[int, int] = {}
            comp_to_edge_types: dict[int, dict[str, int]] = {}
            comp_to_node_types: dict[int, dict[str, int]] = {}
            
            for node_id, tokens in node_to_tokens.items():
                cid = node_to_comp.get(node_id)
                if cid is None:
                    continue
                if cid not in comp_to_tokens:
                    comp_to_tokens[cid] = set()
                comp_to_tokens[cid].update(tokens)
                
                # Track node types per component
                node_type = node_to_type.get(node_id, "unknown")
                if cid not in comp_to_node_types:
                    comp_to_node_types[cid] = {}
                comp_to_node_types[cid][node_type] = comp_to_node_types[cid].get(node_type, 0) + 1
            
            for a, b, edge_type in edges_with_types:
                ca = node_to_comp.get(a)
                cb = node_to_comp.get(b)
                if ca is not None and cb is not None and ca == cb:
                    comp_to_edges_count[ca] = comp_to_edges_count.get(ca, 0) + 1
                    
                    # Track edge types per component
                    if ca not in comp_to_edge_types:
                        comp_to_edge_types[ca] = {}
                    comp_to_edge_types[ca][edge_type] = comp_to_edge_types[ca].get(edge_type, 0) + 1

            # Filter by q
            q_str = (q or "").strip()
            q_int: int | None = None
            if q_str and q_str.isdigit():
                try:
                    q_int = int(q_str)
                except Exception:
                    q_int = None

            for cid, tokens in comp_to_tokens.items():
                if q_str:
                    if q_int is not None:
                        if cid != q_int:
                            continue
                    else:
                        # substring match on digits representation
                        if q_str not in str(cid):
                            continue

                # Compute edge type statistics for this component (for display)
                edge_types = comp_to_edge_types.get(cid, {})
                edge_type_stats = EdgeTypeStats(
                    matched_prediction=edge_types.get("matched_prediction", 0),
                    matched_reference=edge_types.get("matched_reference", 0),
                    prediction=edge_types.get("prediction", 0),
                    reference=edge_types.get("reference", 0),
                    total=comp_to_edges_count.get(cid, 0),
                )
                
                # Apply node type ratio filters if specified
                if any([min_matched_pred, max_matched_pred, min_unmatched_pred, max_unmatched_pred,
                        min_matched_ref, max_matched_ref, min_unmatched_ref, max_unmatched_ref]):
                    node_types = comp_to_node_types.get(cid, {})
                    total_nodes = comp_sizes.get(cid, 0)
                    
                    # Skip components with no nodes
                    if total_nodes == 0:
                        continue
                    
                    # Get node type counts
                    matched_pred_nodes = node_types.get("matched_prediction", 0)
                    unmatched_pred_nodes = node_types.get("prediction", 0)
                    matched_ref_nodes = node_types.get("matched_reference", 0)
                    unmatched_ref_nodes = node_types.get("reference", 0)
                    
                    total_pred_nodes = matched_pred_nodes + unmatched_pred_nodes
                    total_ref_nodes = matched_ref_nodes + unmatched_ref_nodes
                    
                    # Calculate ratios
                    matched_pred_ratio = matched_pred_nodes / total_pred_nodes if total_pred_nodes > 0 else 0
                    unmatched_pred_ratio = unmatched_pred_nodes / total_pred_nodes if total_pred_nodes > 0 else 0
                    matched_ref_ratio = matched_ref_nodes / total_ref_nodes if total_ref_nodes > 0 else 0
                    unmatched_ref_ratio = unmatched_ref_nodes / total_ref_nodes if total_ref_nodes > 0 else 0
                    
                    # Apply filters
                    if min_matched_pred is not None and matched_pred_ratio < min_matched_pred:
                        continue
                    if max_matched_pred is not None and matched_pred_ratio > max_matched_pred:
                        continue
                    if min_unmatched_pred is not None and unmatched_pred_ratio < min_unmatched_pred:
                        continue
                    if max_unmatched_pred is not None and unmatched_pred_ratio > max_unmatched_pred:
                        continue
                    if min_matched_ref is not None and matched_ref_ratio < min_matched_ref:
                        continue
                    if max_matched_ref is not None and matched_ref_ratio > max_matched_ref:
                        continue
                    if min_unmatched_ref is not None and unmatched_ref_ratio < min_unmatched_ref:
                        continue
                    if max_unmatched_ref is not None and unmatched_ref_ratio > max_unmatched_ref:
                        continue
                
                summaries.append(
                    ComponentSummary(
                        filename=filename,
                        component_id=cid,
                        size=comp_sizes.get(cid, 0),
                        edges=comp_to_edges_count.get(cid, 0),
                        proteins_count=len(tokens),
                        edge_type_stats=edge_type_stats,
                    )
                )

        # Sort consistently by file then id
        summaries.sort(key=lambda s: (s.filename, s.component_id))

        total = len(summaries)
        start = (page - 1) * size
        end = start + size
        if start >= total and total != 0:
            raise HTTPException(status_code=400, detail="Page out of range")

        paged = summaries[start:end]
        return PagedComponents(items=paged, total=total, page=page, size=size)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching components: {str(e)}")



@router.get("/{network_name:path}/features", response_model=ProteinFeaturesResponse)
async def get_protein_features(
    network_name: str,
    proteins: str = Query(..., description="Comma-separated list of protein identifiers"),
    name_mode: Literal["systematic", "gene"] = Query("systematic"),
    organism_id: str = Query("559292", description="NCBI taxonomy ID (default: S. cerevisiae)"),
    source: Literal["uniprot", "stringdb"] = Query("uniprot", description="Data source: uniprot or stringdb"),
) -> Any:
    """
    Fetch protein sequence features from UniProt or STRING-DB for multiple proteins.

    Returns sequence length and feature annotations (domains, regions, motifs, etc.)
    for each requested protein. Handles partial failures gracefully by returning
    error messages for failed proteins while providing data for successful ones.

    Args:
        network_name: Network name (for validation/context)
        proteins: Comma-separated protein identifiers
        name_mode: Whether to use systematic or gene names
        organism_id: NCBI taxonomy ID for organism filtering
        source: Data source to use (uniprot or stringdb)

    Returns:
        ProteinFeaturesResponse with data for each protein
    """
    try:
        # Validate network exists (optional, for consistency with other endpoints)
        try:
            _read_network_dir(network_name)
        except HTTPException:
            # Network validation is optional - we can still fetch UniProt data
            logger.warning(f"Network '{network_name}' not found, proceeding with UniProt fetch")

        # Parse protein list
        protein_list = [p.strip() for p in proteins.split(",") if p.strip()]
        if not protein_list:
            raise HTTPException(status_code=400, detail="No proteins specified")

        if len(protein_list) > 50:
            raise HTTPException(
                status_code=400,
                detail="Too many proteins requested (max 50 per request)",
            )

        # Infer organism by network location when possible (data/{Organism}/{Network})
        organism_effective = organism_id
        try:
            net_dir = _resolve_network_dir(network_name)
            rel = os.path.relpath(net_dir, _data_root())
            org = rel.split(os.sep)[0] if rel and rel != "." else ""
            if org == "Human":
                organism_effective = "9606"
            elif org == "Yeast":
                organism_effective = "559292"
        except HTTPException:
            # If network not found, fall back to provided organism_id
            pass

        # Touch name_mode to satisfy linters; currently not used in data fetch
        _ = name_mode

        # Fetch protein features in parallel from selected source
        logger.info(f"Fetching features for {len(protein_list)} proteins from {source}")
        
        if source == "stringdb":
            results = await stringdb_client.fetch_multiple_proteins(protein_list, organism_effective)
        else:
            results = await fetch_uniprot_proteins(protein_list, organism_effective)

        return ProteinFeaturesResponse(proteins=results)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching protein features: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching protein features: {str(e)}"
        )


@router.get("/{network_name:path}", response_model=PagedProteins)
def get_proteins(
    network_name: str,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    q: str | None = Query(default=None, description="Space-separated protein names to filter by"),
    selected: str | None = Query(default=None, description="Space-separated selected proteins; return only proteins that co-occur in same components across files"),
    name_mode: Literal["systematic", "gene"] = Query("systematic"),
    types: str | None = Query(default=None, description="Comma-separated node types to filter by (e.g., 'prediction,reference')"),
) -> Any:
    """
    Aggregate unique proteins across all GDFs in a network.

    - Extract tokens from the node 'label' field (split by whitespace). If no 'label'
      field exists, fall back to 'name' or the first column.
    - Return a paginated list of unique proteins with the list of GDF files they appear in.
    - Optionally filter by node types (e.g., prediction, matched_prediction, reference, matched_reference).
    """
    try:
        dir_path = _read_network_dir(network_name)
        gdf_files = _iter_gdf_files(dir_path)

        sgd_map = _load_sgd_sys_to_gene_map()
        protein_to_files: dict[str, set[str]] = {}
        protein_to_types: dict[str, set[str]] = {}

        for filename in gdf_files:
            file_path = os.path.join(dir_path, filename)
            try:
                token_types_map = _collect_proteins_from_gdf(file_path, name_mode=name_mode, sgd_map=sgd_map)
            except Exception:
                # Skip malformed files but continue processing others
                # Alternatively, raise a 500; here we choose resilience
                token_types_map = {}
            for token, token_types in token_types_map.items():
                if token not in protein_to_files:
                    protein_to_files[token] = set()
                protein_to_files[token].add(filename)
                if token not in protein_to_types:
                    protein_to_types[token] = set()
                protein_to_types[token].update(token_types)

        all_proteins = sorted(protein_to_files.keys())

        # Optional component-based filtering by selected proteins
        if selected:
            selected_terms = [t for t in selected.split() if t]
            selected_set = set(selected_terms)
            if selected_set:
                allowed_tokens: set[str] = set()
                for filename in gdf_files:
                    file_path = os.path.join(dir_path, filename)
                    try:
                        node_ids, edges, node_to_tokens, _ = _parse_nodes_and_edges(file_path, name_mode=name_mode, sgd_map=sgd_map)
                        node_to_comp, _comp_sizes = _compute_components(node_ids, edges)
                    except Exception:
                        continue

                    # Build comp -> tokens present in that component
                    comp_to_tokens: dict[int, set[str]] = {}
                    for node_id, tokens in node_to_tokens.items():
                        cid = node_to_comp.get(node_id)
                        if cid is None:
                            continue
                        if cid not in comp_to_tokens:
                            comp_to_tokens[cid] = set()
                        comp_to_tokens[cid].update(tokens)
                    # Keep only components that contain ALL selected tokens
                    for _cid, tokens_in_comp in comp_to_tokens.items():
                        if selected_set.issubset(tokens_in_comp):
                            allowed_tokens.update(tokens_in_comp)

                # If no components matched (edge case), fall back to at least showing the selected tokens
                if not allowed_tokens:
                    allowed_tokens = set(selected_set)
                # Intersect proteins with allowed tokens
                all_proteins = [p for p in all_proteins if p in allowed_tokens]

        # Optional filtering by space-separated partial tokens (case-insensitive)
        if q:
            logger.info(f"Searching for proteins: {q}")
            terms = [t.strip().lower() for t in (q.split() if q else []) if t.strip()]
            if terms:
                # Filter proteins that contain any of the search terms in either systematic or gene names
                filtered_proteins = []
                for p in all_proteins:
                    # Check if any search term matches the protein name (case-insensitive)
                    protein_lower = p.lower()
                    gene_name = sgd_map.get(p.upper(), p)
                    gene_name_lower = gene_name.lower()

                    # Check if any term matches either the systematic name or gene name
                    if any(term in protein_lower for term in terms) or any(term in gene_name_lower for term in terms):
                        filtered_proteins.append(p)

                all_proteins = filtered_proteins

        # Optional filtering by node types
        if types:
            type_list = [t.strip() for t in types.split(",") if t.strip()]
            if type_list:
                type_set = set(type_list)
                # Filter proteins that have at least one of the specified types
                all_proteins = [
                    p for p in all_proteins
                    if protein_to_types.get(p, set()) & type_set
                ]

        total = len(all_proteins)

        start = (page - 1) * size
        end = start + size
        if start >= total and total != 0:
            raise HTTPException(status_code=400, detail="Page out of range")

        paged = all_proteins[start:end]
        items = []
        for p in paged:
            files_sorted = sorted(protein_to_files.get(p, set()))
            types_sorted = sorted(protein_to_types.get(p, set()))
            items.append(ProteinItem(protein=p, files=files_sorted, types=types_sorted))

        return PagedProteins(items=items, total=total, page=page, size=size)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error aggregating proteins: {str(e)}")
