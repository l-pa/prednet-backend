import math
import os
from functools import lru_cache
from typing import Any, Literal

import networkx as nx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["networks"], prefix="/networks")


class NetworkInfo(BaseModel):
    name: str
    file_count: int


class CytoscapeNode(BaseModel):
    data: dict[str, Any]


class CytoscapeEdge(BaseModel):
    data: dict[str, Any]


class CytoscapeGraph(BaseModel):
    nodes: list[CytoscapeNode]
    edges: list[CytoscapeEdge]


class NodeSize(BaseModel):
    width: float
    height: float


@router.get("/", response_model=list[NetworkInfo])
def get_networks() -> Any:
    """
    Get list of available networks from the data folder.
    Returns network names and GDF file counts for each network.
    """
    try:
        # Get the path to the data directory relative to this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        data_path = os.path.join(current_dir, "..", "..", "data")
        data_path = os.path.abspath(data_path)

        if not os.path.exists(data_path):
            raise HTTPException(status_code=404, detail="Data directory not found")

        networks = []

        # Get all directories in the data folder
        for item in os.listdir(data_path):
            item_path = os.path.join(data_path, item)

            # Only include directories
            if os.path.isdir(item_path):
                # Count only GDF files in the directory
                gdf_files = [f for f in os.listdir(item_path) if f.endswith('.gdf')]
                file_count = len(gdf_files)

                networks.append(NetworkInfo(
                    name=item,
                    file_count=file_count
                ))

        # Sort networks by name for consistent ordering
        networks.sort(key=lambda x: x.name)

        return networks

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading networks: {str(e)}")


@lru_cache(maxsize=1)
def _load_sgd_sys_to_gene_map() -> dict[str, str]:
    """
    Load SGD features mapping from systematic name (column 4) to gene name (column 5).
    If the gene name is missing, fall back to the systematic name.
    The result is cached for the process lifetime.
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sgd_path = os.path.join(current_dir, "..", "..", "data", "SGD_features.tab")
        sgd_path = os.path.abspath(sgd_path)
        mapping: dict[str, str] = {}
        if not os.path.exists(sgd_path):
            return mapping
        with open(sgd_path, encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\n")
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) < 5:
                    continue
                sys_name = (parts[3] or "").strip()
                gene_name = (parts[4] or "").strip()
                if not sys_name:
                    continue
                # Skip header rows if present
                if sys_name.lower() in {"systematic name", "systematic_name"}:
                    continue
                if not gene_name:
                    gene_name = sys_name
                mapping[sys_name.upper()] = gene_name
        return mapping
    except Exception:
        return {}


@router.get("/{network_name}/files", response_model=list[str])
def get_network_files(network_name: str) -> Any:
    """
    Get list of GDF files for a specific network.
    """
    try:
        # Get the path to the data directory relative to this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        data_path = os.path.join(current_dir, "..", "..", "data", network_name)
        data_path = os.path.abspath(data_path)

        if not os.path.exists(data_path):
            raise HTTPException(status_code=404, detail=f"Network '{network_name}' not found")

        if not os.path.isdir(data_path):
            raise HTTPException(status_code=400, detail=f"'{network_name}' is not a directory")

        # Get only GDF files in the network directory
        gdf_files = [f for f in os.listdir(data_path) if f.endswith('.gdf') and os.path.isfile(os.path.join(data_path, f))]
        gdf_files.sort()  # Sort for consistent ordering

        return gdf_files

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading network files: {str(e)}")


def parse_gdf_to_cytoscape(gdf_content: str) -> CytoscapeGraph:
    """
    Parse GDF content and convert to Cytoscape.js format.
    """
    lines = gdf_content.strip().split('\n')

    nodes = []
    edges = []
    node_attributes = []
    edge_attributes = []
    in_edges = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith('nodedef>'):
            # Parse node definition
            node_def = line[8:]  # Remove 'nodedef>'
            node_attributes = [attr.split()[0] for attr in node_def.split(',')]
            continue

        elif line.startswith('edgedef>'):
            # Parse edge definition
            edge_def = line[8:]  # Remove 'edgedef>'
            edge_attributes = [attr.split()[0] for attr in edge_def.split(',')]
            in_edges = True
            continue

        elif in_edges:
            # Parse edge data
            edge_data = line.split(',')
            if len(edge_data) >= 2:
                edge_info = {}
                for i, attr in enumerate(edge_attributes):
                    if i < len(edge_data):
                        value = edge_data[i].strip()
                        # Try to convert to appropriate type
                        if value.replace('.', '').replace('-', '').isdigit():
                            try:
                                edge_info[attr] = float(value) if '.' in value else int(value)
                            except ValueError:
                                edge_info[attr] = value
                        else:
                            edge_info[attr] = value

                # Convert GDF edge format to Cytoscape format
                if 'node1' in edge_info and 'node2' in edge_info:
                    # Create Cytoscape edge with source and target
                    # Ensure source and target are strings to match node IDs
                    source_id = str(edge_info['node1'])
                    target_id = str(edge_info['node2'])

                    cytoscape_edge = {
                        'data': {
                            'id': f"{source_id}-{target_id}",
                            'source': source_id,
                            'target': target_id,
                            **{k: v for k, v in edge_info.items() if k not in ['node1', 'node2']}
                        }
                    }
                    edges.append(CytoscapeEdge(data=cytoscape_edge['data']))
                else:
                    # Fallback if node1/node2 not found - log warning
                    # print(f"Warning: Edge missing node1/node2 fields: {edge_info}")
                    edges.append(CytoscapeEdge(data=edge_info))
        else:
            # Parse node data
            node_data = line.split(',')
            if len(node_data) >= 1:
                node_info = {}
                for i, attr in enumerate(node_attributes):
                    if i < len(node_data):
                        value = node_data[i].strip()
                        # Remove quotes if present
                        if value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        # Try to convert to appropriate type
                        if value.replace('.', '').replace('-', '').isdigit():
                            try:
                                node_info[attr] = float(value) if '.' in value else int(value)
                            except ValueError:
                                node_info[attr] = value
                        else:
                            node_info[attr] = value

                # Ensure node has an id field for Cytoscape
                # The first field in GDF is typically the node ID (numeric)
                # In GDF format, the first field is usually the ID, regardless of its name in the header
                if 'name' in node_info:
                    # The 'name' field contains the actual node ID
                    node_info['id'] = str(node_info['name'])
                elif 'id' not in node_info:
                    # Use the first field as id if no name/id field
                    first_key = list(node_info.keys())[0]
                    node_info['id'] = str(node_info[first_key])

                # Also add a label field for display if not present
                if 'label' not in node_info and 'name' in node_info:
                    node_info['label'] = str(node_info['name'])
                elif 'label' not in node_info:
                    node_info['label'] = str(node_info['id'])

                # Enrich with SGD naming for labels (map each systematic token to gene name)
                try:
                    sgd_map = _load_sgd_sys_to_gene_map()
                    raw_label = node_info.get('label')
                    if isinstance(raw_label, str) and raw_label.strip():
                        sys_tokens = [tok.strip() for tok in raw_label.split() if tok.strip()]
                        gene_tokens = []
                        for tok in sys_tokens:
                            mapped = sgd_map.get(tok.upper(), tok)
                            gene_tokens.append(mapped)
                        node_info['label_sys'] = ' '.join(sys_tokens)
                        node_info['label_gene'] = ' '.join(gene_tokens)
                        # Provide generic fields as well
                        node_info['sys_name'] = node_info.get('label_sys')
                        node_info['gene_name'] = node_info.get('label_gene')
                    else:
                        # Fallback to single identifier mapping using 'name' or 'id'
                        sys_candidate_val = node_info.get('name', node_info.get('id'))
                        sys_candidate = str(sys_candidate_val) if sys_candidate_val is not None else ''
                        sys_upper = sys_candidate.strip().upper()
                        gene_name = sgd_map.get(sys_upper, sys_candidate)
                        node_info['sys_name'] = sys_candidate
                        node_info['gene_name'] = gene_name
                except Exception:
                    # Best-effort enrichment only
                    pass

                nodes.append(CytoscapeNode(data=node_info))

    return CytoscapeGraph(nodes=nodes, edges=edges)


@router.get("/{network_name}/gdf/{filename}", response_model=CytoscapeGraph)
def get_gdf_file(network_name: str, filename: str) -> Any:
    """
    Read a GDF file and convert it to Cytoscape.js format.
    """
    try:
        # Get the path to the GDF file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, "..", "..", "data", network_name, filename)
        file_path = os.path.abspath(file_path)

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"File '{filename}' not found in network '{network_name}'")

        if not filename.endswith('.gdf'):
            raise HTTPException(status_code=400, detail="File must be a GDF file")

        # Read the GDF file
        with open(file_path, encoding='utf-8') as f:
            gdf_content = f.read()

        # Parse and convert to Cytoscape.js format
        cytoscape_graph = parse_gdf_to_cytoscape(gdf_content)

        # Debug logging
        # print(f"Parsed graph: {len(cytoscape_graph.nodes)} nodes, {len(cytoscape_graph.edges)} edges")

        return cytoscape_graph

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading GDF file: {str(e)}")


class LayoutRequest(BaseModel):
    graph: CytoscapeGraph
    seed: int | None = None
    scale: float | None = 1.0
    iterations: int | None = 50
    # Optional per-node radii (in same coordinate units as layout)
    node_radii: dict[str, float] | None = None
    # Optional per-node sizes from client: nodeSizes[id] = { width, height }
    node_sizes: dict[str, NodeSize] | None = Field(default=None, alias="nodeSizes")
    # Extra spacing added on top of touching radii
    padding: float | None = 2.0
    # Max iterations for anti-overlap adjustment
    anti_overlap_iterations: int | None = 80
    # Target coverage (sum of disc areas / bbox area) before iterative separation
    spread_target_coverage: float | None = 0.12


class LayoutResponse(BaseModel):
    positions: dict[str, dict[str, float]]


@router.post("/layout/spring", response_model=LayoutResponse)
def compute_spring_layout(req: LayoutRequest) -> Any:
    """
    Compute a force-directed (spring) layout on the backend using NetworkX.
    Returns a dict mapping node id to {x, y} positions.
    """
    try:
        G = nx.Graph()

        # Add nodes with ids as strings
        for node in req.graph.nodes:
            node_id = str(node.data.get("id"))
            if not node_id:
                continue
            G.add_node(node_id)

        # Add edges using source/target; default weight 1 if present
        for edge in req.graph.edges:
            data = edge.data or {}
            source = data.get("source")
            target = data.get("target")
            if source is None or target is None:
                continue
            source_id = str(source)
            target_id = str(target)
            weight = data.get("weight", 1.0)
            try:
                weight_val = float(weight)
            except Exception:
                weight_val = 1.0
            G.add_edge(source_id, target_id, weight=weight_val)

        if G.number_of_nodes() == 0:
            return {"positions": {}}

        # Try ForceAtlas2 if available, then Kamada-Kawai, then a tuned spring layout
        pos = None

        forceatlas2 = getattr(nx, "forceatlas2_layout", None)
        if callable(forceatlas2):
            try:
                pos = forceatlas2(  # type: ignore[misc]
                    G,
                    weight="weight",
                    scale=req.scale if req.scale is not None else 1.0,
                    seed=req.seed,
                    iterations=req.iterations if req.iterations is not None else 200,
                )
            except TypeError:
                # Fallback to minimal signature if API differs
                try:
                    pos = forceatlas2(G)  # type: ignore[misc]
                except Exception:
                    pos = None
            except Exception:
                pos = None

        if pos is None:
            try:
                pos = nx.kamada_kawai_layout(
                    G,
                    weight="weight",
                    scale=req.scale if req.scale is not None else 1.0,
                )
            except Exception:
                pos = None

        if pos is None:
            # Tuned spring layout with a larger k to spread nodes
            n_nodes = max(1, G.number_of_nodes())
            k_default = (req.scale if req.scale is not None else 1.0) * 2.0 / (n_nodes ** 0.5)
            pos = nx.spring_layout(
                G,
                seed=req.seed,
                weight="weight",
                scale=req.scale if req.scale is not None else 1.0,
                iterations=req.iterations if req.iterations is not None else 100,
                k=k_default,
            )

        # Optional anti-overlap adjustment using rectangle sizes or fallback radii
        pad = req.padding if req.padding is not None else 2.0
        max_iters = req.anti_overlap_iterations if req.anti_overlap_iterations is not None else 80

        # Prepare rectangle sizes
        rect_sizes: dict[str, tuple[float, float]] = {}
        if req.node_sizes:
            for node_id, size in req.node_sizes.items():
                try:
                    w = float(size.width)
                    h = float(size.height)
                except Exception:
                    w, h = 10.0, 10.0
                rect_sizes[str(node_id)] = (max(0.0, w), max(0.0, h))

        # Prepare circle radii fallback
        radii: dict[str, float] = {}
        default_radius = 5.0
        if req.node_radii:
            for node_id, r in req.node_radii.items():
                try:
                    rv = float(r)
                except Exception:
                    rv = default_radius
                radii[str(node_id)] = max(0.0, rv)
        else:
            for node in req.graph.nodes:
                node_id = str(node.data.get("id"))
                size_val = node.data.get("radius", node.data.get("size", default_radius))
                try:
                    rv = float(size_val)
                except Exception:
                    rv = default_radius
                radii[node_id] = max(0.0, rv)

        # Global pre-spread based on coverage relative to bbox (use rectangles if available)
        if pos:
            xs = [coords[0] for coords in pos.values()]
            ys = [coords[1] for coords in pos.values()]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            width = max(max_x - min_x, 1e-6)
            height = max(max_y - min_y, 1e-6)
            bbox_area = width * height
            if rect_sizes:
                shapes_area = sum((rect_sizes.get(str(n), (10.0, 10.0))[0] * rect_sizes.get(str(n), (10.0, 10.0))[1]) for n in pos)
            else:
                shapes_area = sum(math.pi * (radii.get(str(n), default_radius) ** 2) for n in pos)
            target_cov = req.spread_target_coverage if req.spread_target_coverage is not None else 0.12
            current_cov = shapes_area / bbox_area if bbox_area > 0 else 1.0
            if current_cov > target_cov:
                cx = (min_x + max_x) / 2.0
                cy = (min_y + max_y) / 2.0
                scale_out = (current_cov / max(target_cov, 1e-6)) ** 0.5
                for n in pos:
                    x, y = pos[n]
                    pos[n] = (cx + (x - cx) * scale_out, cy + (y - cy) * scale_out)

        # Iterative separation using rectangles if available, else circles
        node_ids = list(pos.keys())
        for _ in range(max(0, max_iters)):
            moved_any = False
            for i in range(len(node_ids)):
                a = node_ids[i]
                ax, ay = pos[a]
                for j in range(i + 1, len(node_ids)):
                    b = node_ids[j]
                    bx, by = pos[b]
                    if rect_sizes:
                        aw, ah = rect_sizes.get(str(a), (10.0, 10.0))
                        bw, bh = rect_sizes.get(str(b), (10.0, 10.0))
                        half_w = (aw + bw) / 2.0 + pad
                        half_h = (ah + bh) / 2.0 + pad
                        dx = bx - ax
                        dy = by - ay
                        overlap_x = half_w - abs(dx)
                        overlap_y = half_h - abs(dy)
                        if overlap_x > 0 and overlap_y > 0:
                            # Resolve along the axis of smaller penetration
                            if overlap_x < overlap_y:
                                shift = overlap_x / 2.0
                                sx = 1.0 if dx >= 0 else -1.0
                                ax -= sx * shift
                                bx += sx * shift
                            else:
                                shift = overlap_y / 2.0
                                sy = 1.0 if dy >= 0 else -1.0
                                ay -= sy * shift
                                by += sy * shift
                            pos[a] = (ax, ay)
                            pos[b] = (bx, by)
                            moved_any = True
                    else:
                        ra = radii.get(str(a), default_radius)
                        rb = radii.get(str(b), default_radius)
                        dx = bx - ax
                        dy = by - ay
                        dist = math.hypot(dx, dy)
                        min_dist = ra + rb + pad
                        if dist == 0.0:
                            dx = (hash(str(a)) % 3 - 1) or 1
                            dy = (hash(str(b)) % 3 - 1) or -1
                            dist = math.hypot(dx, dy)
                        if dist < min_dist:
                            overlap = (min_dist - dist) / 2.0
                            ux = dx / dist
                            uy = dy / dist
                            pos[a] = (ax - ux * overlap, ay - uy * overlap)
                            pos[b] = (bx + ux * overlap, by + uy * overlap)
                            moved_any = True
                            ax, ay = pos[a]
                            bx, by = pos[b]
            if not moved_any:
                break

        # Convert to serializable structure
        positions: dict[str, dict[str, float]] = {
            str(node): {"x": float(coords[0]), "y": float(coords[1])}
            for node, coords in pos.items()
        }

        return {"positions": positions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error computing layout: {str(e)}")


class ComponentProteinCount(BaseModel):
    protein: str
    count: int
    # counts of this protein by node type within the component
    type_counts: dict[str, int] | None = None
    # fraction of component nodes containing this protein (0-1)
    ratio: float | None = None
    # per-type fractions relative to this protein's total occurrences (0-1)
    type_ratios: dict[str, float] | None = None
    # in how many other components (graph/file scope) this protein also appears
    other_components: int | None = None


class ByNodeRequest(BaseModel):
    node_id: str = Field(alias="node_id")
    graph: CytoscapeGraph
    network: str | None = None
    filename: str | None = None
    # Optional: how to interpret protein tokens ('systematic' or 'gene')
    name_mode: Literal["systematic", "gene"] | None = Field(default=None, alias="name_mode")


class ByNodeResponse(BaseModel):
    component_id: int
    size: int
    protein_counts: list[ComponentProteinCount]


@router.post("/components/by-node", response_model=ByNodeResponse)
def get_component_proteins_by_node(req: ByNodeRequest) -> Any:
    try:
        name_mode = req.name_mode or "systematic"
        sgd_map = _load_sgd_sys_to_gene_map()

        def tokenize_label(label_text: str) -> set[str]:
            tokens = {tok.strip() for tok in label_text.split() if tok.strip()}
            if name_mode == "gene":
                mapped = {sgd_map.get(tok.upper(), tok) for tok in tokens}
                return {t for t in mapped if t}
            return {t for t in tokens if t}

        # Collect node ids and labels
        node_ids: list[str] = []
        node_to_label: dict[str, str] = {}
        node_to_type: dict[str, str] = {}
        for n in getattr(req.graph, "nodes", []):
            data = getattr(n, "data", {}) or {}
            raw_id = data.get("id")
            if raw_id is None:
                continue
            nid = str(raw_id)
            node_ids.append(nid)
            # choose label based on requested name type
            if name_mode == "gene":
                label_val = data.get("label_gene") or data.get("label")
            else:
                label_val = data.get("label_sys") or data.get("label")
            if not isinstance(label_val, str) or not label_val:
                label_val = str(data.get("name", nid))
            node_to_label[nid] = label_val
            node_type_val = data.get("type")
            node_to_type[nid] = str(node_type_val) if node_type_val is not None else "unknown"

        # Early return if node not present
        target_id = str(req.node_id)
        if target_id not in node_to_label:
            raise HTTPException(status_code=404, detail=f"Node '{target_id}' not found in graph")

        # Collect edges
        edges: list[tuple[str, str]] = []
        for e in getattr(req.graph, "edges", []):
            data = getattr(e, "data", {}) or {}
            s = data.get("source")
            t = data.get("target")
            if s is None or t is None:
                continue
            edges.append((str(s), str(t)))

        # Disjoint Set Union (Union-Find) to compute components
        parent: dict[str, str] = {n: n for n in node_ids}
        size_map: dict[str, int] = {n: 1 for n in node_ids}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            if a not in parent or b not in parent:
                return
            ra, rb = find(a), find(b)
            if ra == rb:
                return
            if size_map[ra] < size_map[rb]:
                ra, rb = rb, ra
            parent[rb] = ra
            size_map[ra] += size_map[rb]

        for a, b in edges:
            union(a, b)

        # Assign compact component ids
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

        if target_id not in node_to_comp:
            raise HTTPException(status_code=404, detail=f"Node '{target_id}' not found in components")

        target_cid = node_to_comp[target_id]

        # Collect protein tokens from labels within the target component
        protein_counts: dict[str, int] = {}
        protein_type_counts: dict[str, dict[str, int]] = {}
        component_nodes: list[str] = [n for n in node_ids if node_to_comp.get(n) == target_cid]
        for n in component_nodes:
            label_text = node_to_label.get(n, "")
            node_type = node_to_type.get(n, "unknown")
            # Count unique tokens per node to avoid multiple increments from repeated tokens in one label
            tokens = tokenize_label(label_text)
            for token in tokens:
                protein_counts[token] = protein_counts.get(token, 0) + 1
                if token not in protein_type_counts:
                    protein_type_counts[token] = {}
                protein_type_counts[token][node_type] = protein_type_counts[token].get(node_type, 0) + 1

        # Build token -> set of component ids across the provided graph (fallback basis)
        token_to_comp_set_graph: dict[str, set[int]] = {}
        for n in node_ids:
            cid_n = node_to_comp.get(n)
            if cid_n is None:
                continue
            label_text = node_to_label.get(n, "")
            tokens_n = tokenize_label(label_text)
            for tok in tokens_n:
                if tok not in token_to_comp_set_graph:
                    token_to_comp_set_graph[tok] = set()
                token_to_comp_set_graph[tok].add(cid_n)

        # Optionally, if network and filename are provided, build token -> component ids from the original GDF file
        token_to_comp_set_file: dict[str, set[int]] | None = None
        target_file_cid: int | None = None
        try:
            if req.network and req.filename:
                current_dir = os.path.dirname(os.path.abspath(__file__))
                file_path = os.path.join(current_dir, "..", "..", "data", str(req.network), str(req.filename))
                file_path = os.path.abspath(file_path)
                if os.path.exists(file_path) and file_path.endswith(".gdf"):
                    # minimal parse for components and tokens
                    # read nodes and edges
                    node_ids_f: list[str] = []
                    edges_f: list[tuple[str, str]] = []
                    node_to_tokens_f: dict[str, set[str]] = {}
                    with open(file_path, encoding="utf-8") as fh:
                        in_nodes_f = False
                        in_edges_f = False
                        node_attr_names_f: list[str] = []
                        edge_attr_names_f: list[str] = []
                        label_index_f: int | None = None
                        id_index_f: int | None = None
                        node1_index_f: int | None = None
                        node2_index_f: int | None = None
                        import csv as _csv
                        for raw_line in fh:
                            line = raw_line.strip()
                            if not line:
                                continue
                            if line.startswith("nodedef>"):
                                in_nodes_f = True
                                in_edges_f = False
                                header = line[len("nodedef>") :]
                                parts = [part.strip() for part in header.split(",")]
                                node_attr_names_f = []
                                for p in parts:
                                    first = p.split()[0]
                                    first = first.split(":")[0]
                                    node_attr_names_f.append(first)
                                label_index_f = node_attr_names_f.index("label") if "label" in node_attr_names_f else (node_attr_names_f.index("name") if "name" in node_attr_names_f else None)
                                id_index_f = node_attr_names_f.index("name") if "name" in node_attr_names_f else (node_attr_names_f.index("id") if "id" in node_attr_names_f else 0)
                                continue
                            if line.startswith("edgedef>"):
                                in_nodes_f = False
                                in_edges_f = True
                                header = line[len("edgedef>") :]
                                parts = [part.strip() for part in header.split(",")]
                                edge_attr_names_f = []
                                for p in parts:
                                    first = p.split()[0]
                                    first = first.split(":")[0]
                                    edge_attr_names_f.append(first)
                                node1_index_f = edge_attr_names_f.index("node1") if "node1" in edge_attr_names_f else None
                                node2_index_f = edge_attr_names_f.index("node2") if "node2" in edge_attr_names_f else None
                                continue
                            if in_nodes_f and node_attr_names_f:
                                for row in _csv.reader([line], delimiter=",", quotechar="'", skipinitialspace=True):
                                    if id_index_f is None or id_index_f >= len(row):
                                        continue
                                    nid_f = str(row[id_index_f].strip().strip("'"))
                                    node_ids_f.append(nid_f)
                                    tokens_set: set[str] = set()
                                    if label_index_f is not None and label_index_f < len(row):
                                        label_val_f = row[label_index_f].strip().strip("'")
                                        if label_val_f:
                                            base_tokens = {tok.strip() for tok in label_val_f.split() if tok.strip()}
                                            if name_mode == "gene":
                                                tokens_set = {sgd_map.get(t.upper(), t) for t in base_tokens}
                                            else:
                                                tokens_set = base_tokens
                                    node_to_tokens_f[nid_f] = tokens_set
                                continue
                            if in_edges_f and edge_attr_names_f and node1_index_f is not None and node2_index_f is not None:
                                for row in _csv.reader([line], delimiter=",", quotechar="'", skipinitialspace=True):
                                    if node1_index_f < len(row) and node2_index_f < len(row):
                                        n1 = row[node1_index_f].strip().strip("'")
                                        n2 = row[node2_index_f].strip().strip("'")
                                        if n1 and n2:
                                            edges_f.append((str(n1), str(n2)))

                    # union-find on file
                    parent_f: dict[str, str] = {n: n for n in node_ids_f}
                    size_f: dict[str, int] = {n: 1 for n in node_ids_f}
                    def find_f(x: str) -> str:
                        while parent_f[x] != x:
                            parent_f[x] = parent_f[parent_f[x]]
                            x = parent_f[x]
                        return x
                    def union_f(a: str, b: str) -> None:
                        if a not in parent_f or b not in parent_f:
                            return
                        ra, rb = find_f(a), find_f(b)
                        if ra == rb:
                            return
                        if size_f[ra] < size_f[rb]:
                            ra, rb = rb, ra
                        parent_f[rb] = ra
                        size_f[ra] += size_f[rb]
                    for a, b in edges_f:
                        union_f(a, b)
                    root_to_comp_f: dict[str, int] = {}
                    node_to_comp_f: dict[str, int] = {}
                    next_id_f = 0
                    for n in node_ids_f:
                        r = find_f(n)
                        if r not in root_to_comp_f:
                            root_to_comp_f[r] = next_id_f
                            next_id_f += 1
                        node_to_comp_f[n] = root_to_comp_f[r]

                    # target file component id
                    target_file_cid = node_to_comp_f.get(str(req.node_id))
                    token_to_comp_set_file = {}
                    for nid_f, toks in node_to_tokens_f.items():
                        cidf = node_to_comp_f.get(nid_f)
                        if cidf is None:
                            continue
                        for tok in toks:
                            token_to_comp_set_file.setdefault(tok, set()).add(cidf)
        except Exception:
            token_to_comp_set_file = None
            target_file_cid = None

        # Build sorted list with ratios, type breakdowns, and other components
        comp_size = comp_sizes.get(target_cid, 0)
        protein_counts_list = []
        for protein, total in protein_counts.items():
            tcounts = protein_type_counts.get(protein, {})
            # ratios
            ratio = float(total) / float(comp_size) if comp_size > 0 else 0.0
            trate: dict[str, float] = {}
            if total > 0:
                for t, c in tcounts.items():
                    trate[t] = float(c) / float(total)
            # other components: prefer file scope if available, else graph scope
            other_graph = 0
            comp_set_g = token_to_comp_set_graph.get(protein, set())
            if comp_set_g:
                other_graph = max(0, len(comp_set_g) - (1 if target_cid in comp_set_g else 0))
            other_file = None
            if token_to_comp_set_file is not None:
                comp_set_f = token_to_comp_set_file.get(protein, set())
                other_file = max(0, len(comp_set_f) - (1 if (target_file_cid is not None and target_file_cid in comp_set_f) else 0))
            protein_counts_list.append(
                ComponentProteinCount(
                    protein=protein,
                    count=total,
                    type_counts=dict(sorted(tcounts.items(), key=lambda kv: (-kv[1], kv[0]))) if tcounts else None,
                    ratio=ratio,
                    type_ratios=dict(sorted(trate.items(), key=lambda kv: (-kv[1], kv[0]))) if trate else None,
                    other_components=other_file if other_file is not None else other_graph,
                )
            )
        protein_counts_list.sort(key=lambda x: (-x.count, x.protein))

        return ByNodeResponse(
            component_id=target_cid,
            size=comp_sizes.get(target_cid, 0),
            protein_counts=protein_counts_list,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error computing component proteins: {str(e)}")




# end of file
