import os
import csv
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.api.routes.networks import parse_gdf_to_cytoscape, _load_sgd_sys_to_gene_map


router = APIRouter(tags=["proteins"], prefix="/proteins")


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
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(current_dir, "..", "..", "data", network_name)
    data_path = os.path.abspath(data_path)
    if not os.path.exists(data_path):
        raise HTTPException(status_code=404, detail=f"Network '{network_name}' not found")
    if not os.path.isdir(data_path):
        raise HTTPException(status_code=400, detail=f"'{network_name}' is not a directory")
    return data_path


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


@router.get("/{network_name}", response_model=PagedProteins)
def get_proteins(
    network_name: str,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    q: str | None = Query(default=None, description="Space-separated protein names to filter by"),
    selected: str | None = Query(default=None, description="Space-separated selected proteins; return only proteins that co-occur in same components across files"),
    name_mode: Literal["systematic", "gene"] = Query("systematic"),
) -> Any:
    """
    Aggregate unique proteins across all GDFs in a network.

    - Extract tokens from the node 'label' field (split by whitespace). If no 'label'
      field exists, fall back to 'name' or the first column.
    - Return a paginated list of unique proteins with the list of GDF files they appear in.
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
            for token, types in token_types_map.items():
                if token not in protein_to_files:
                    protein_to_files[token] = set()
                protein_to_files[token].add(filename)
                if token not in protein_to_types:
                    protein_to_types[token] = set()
                protein_to_types[token].update(types)

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

        # Optional filtering by space-separated exact tokens
        if q:
            terms = [t for t in (q.split() if q else []) if t]
            if terms:
                term_set = set(terms)
                all_proteins = [p for p in all_proteins if p in term_set]
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


@router.post("/{network_name}/components", response_model=ComponentsResponse)
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


@router.get("/{network_name}/components/{filename}/{component_id}", response_model=SubgraphGraph)
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


