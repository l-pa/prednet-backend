import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
