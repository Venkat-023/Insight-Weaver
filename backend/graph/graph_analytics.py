"""Knowledge graph topology analysis, centrality computation, and sub-network inspection.

Provides analytical utilities for evaluating paper-entity graphs, identifying
central hubs in scientific literature, and detecting isolated components.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any
import xml.etree.ElementTree as ET


def compute_node_degree_centralities(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, float]:
    """Compute normalized degree centrality for all nodes in the knowledge graph.

    Args:
        nodes: List of node dictionaries with 'id'.
        edges: List of edge dictionaries with 'source' and 'target'.

    Returns:
        Mapping from node ID to normalized centrality float (0.0 to 1.0).
    """
    if not nodes:
        return {}

    num_nodes = len(nodes)
    if num_nodes <= 1:
        return {str(n.get("id")): 0.0 for n in nodes}

    degree_counts: dict[str, int] = defaultdict(int)
    for edge in edges:
        src = str(edge.get("source", ""))
        tgt = str(edge.get("target", ""))
        if src:
            degree_counts[src] += 1
        if tgt:
            degree_counts[tgt] += 1

    normalization_factor = num_nodes - 1
    centralities: dict[str, float] = {}

    for node in nodes:
        nid = str(node.get("id", ""))
        deg = degree_counts.get(nid, 0)
        centralities[nid] = round(deg / normalization_factor, 4)

    return centralities


def find_connected_subgraphs(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> list[list[str]]:
    """Partition the knowledge graph into disjoint connected components.

    Useful for isolating dense clusters of scientific topics or separate paper communities.

    Args:
        nodes: List of node dictionaries.
        edges: List of edge dictionaries.

    Returns:
        List of components, where each component is a list of node IDs.
    """
    adj: dict[str, set[str]] = defaultdict(set)
    all_node_ids = {str(n.get("id")) for n in nodes if n.get("id") is not None}

    for edge in edges:
        src = str(edge.get("source", ""))
        tgt = str(edge.get("target", ""))
        if src in all_node_ids and tgt in all_node_ids:
            adj[src].add(tgt)
            adj[tgt].add(src)

    visited: set[str] = set()
    components: list[list[str]] = []

    for nid in all_node_ids:
        if nid not in visited:
            comp: list[str] = []
            queue = deque([nid])
            visited.add(nid)

            while queue:
                curr = queue.popleft()
                comp.append(curr)
                for neighbor in adj[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)

            components.append(sorted(comp))

    return sorted(components, key=len, reverse=True)


def filter_isolated_entities(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Filter out entity nodes that have zero connections to any papers or other entities.

    Args:
        nodes: Full list of node dictionaries.
        edges: Full list of edge dictionaries.

    Returns:
        Filtered list of nodes excluding unlinked singleton entities.
    """
    connected_ids: set[str] = set()
    for edge in edges:
        src = str(edge.get("source", ""))
        tgt = str(edge.get("target", ""))
        if src:
            connected_ids.add(src)
        if tgt:
            connected_ids.add(tgt)

    # Keep papers regardless, but filter out zero-degree entities
    retained: list[dict[str, Any]] = []
    for node in nodes:
        nid = str(node.get("id", ""))
        is_paper = node.get("type") == "paper" or node.get("group") == "paper"
        if is_paper or nid in connected_ids:
            retained.append(node)

    return retained


# ==============================================================================
# UNUSED FUNCTIONS / DEAD CODE CANDIDATES FOR DEAD CODE ANALYSIS TESTING
# ==============================================================================

def _dijkstra_shortest_distance(
    adj_list: dict[str, list[tuple[str, float]]],
    start: str,
    target: str,
) -> float | None:
    """[UNUSED] Internal weighted shortest path calculation between two graph nodes.

    Dead code note: Implemented during initial path finding design, but never called
    internally or referenced anywhere across the graph services.
    """
    if start not in adj_list or target not in adj_list:
        return None

    import heapq

    distances: dict[str, float] = {start: 0.0}
    priority_queue = [(0.0, start)]

    while priority_queue:
        curr_dist, curr_node = heapq.heappop(priority_queue)
        if curr_node == target:
            return curr_dist

        if curr_dist > distances.get(curr_node, float("inf")):
            continue

        for neighbor, weight in adj_list.get(curr_node, []):
            dist = curr_dist + weight
            if dist < distances.get(neighbor, float("inf")):
                distances[neighbor] = dist
                heapq.heappush(priority_queue, (dist, neighbor))

    return None


def export_graph_to_graphml_xml(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> str:
    """[UNUSED] Serialize graph structure into standard GraphML XML format.

    Dead code note: Insight-Weaver uses standard Cytoscape JSON representations
    for its React ForceGraph UI and REST API. This XML generator was never imported
    or invoked by any endpoint.
    """
    root = ET.Element("graphml", xmlns="http://graphml.graphdrawing.org/xmlns")
    graph_elem = ET.SubElement(root, "graph", edgedefault="undirected")

    for node in nodes:
        nid = str(node.get("id", ""))
        n_elem = ET.SubElement(graph_elem, "node", id=nid)
        data_elem = ET.SubElement(n_elem, "data", key="label")
        data_elem.text = str(node.get("name", node.get("label", nid)))

    for i, edge in enumerate(edges):
        src = str(edge.get("source", ""))
        tgt = str(edge.get("target", ""))
        e_elem = ET.SubElement(graph_elem, "edge", id=f"e{i}", source=src, target=tgt)
        if "label" in edge:
            data_elem = ET.SubElement(e_elem, "data", key="relation")
            data_elem.text = str(edge["label"])

    return ET.tostring(root, encoding="utf-8").decode("utf-8")


def calculate_graph_density_ratio(
    node_count: int,
    edge_count: int,
    is_directed: bool = False,
) -> float:
    """[UNUSED] Calculate the edge density ratio of a network graph.

    Dead code note: Standalone theoretical graph metric, never wired to any dashboard
    or analysis service.
    """
    if node_count <= 1:
        return 0.0

    possible_edges = node_count * (node_count - 1)
    if not is_directed:
        possible_edges /= 2.0

    if possible_edges == 0:
        return 0.0

    return round(edge_count / possible_edges, 5)
