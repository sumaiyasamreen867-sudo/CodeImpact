import networkx as nx
from typing import List, Set
from src.codeimpact.schemas import ImpactResult


def analyze_impact(graph: nx.DiGraph, changed_components: List[str]) -> ImpactResult:
    """Traverses the dependency graph in reverse to discover components directly and indirectly impacted by changes."""
    direct_affected: Set[str] = set()
    indirect_affected: Set[str] = set()
    impact_paths: List[List[str]] = []

    # Work on a reversed graph to track dependents (who depends on changed items)
    reversed_graph = graph.reverse(copy=True)

    for component in changed_components:
        if not reversed_graph.has_node(component):
            continue

        # Explore all reachable nodes from the changed component
        for target in nx.single_source_shortest_path(reversed_graph, component):
            if target == component:
                continue

            paths = list(nx.all_simple_paths(reversed_graph, source=component, target=target))
            for path in paths:
                impact_paths.append(path)
                
                # Length of 2 means direct edge: [changed_node, dependent_node]
                if len(path) == 2:
                    direct_affected.add(target)
                elif len(path) > 2:
                    indirect_affected.add(target)

    # Calculate basic uncertainty ratio if dynamically unresolvable edges exist
    total_components = len(direct_affected) + len(indirect_affected)
    uncertainty = 0.0 if total_components > 0 else 0.1

    return ImpactResult(
        changed=changed_components,
        direct=sorted(list(direct_affected)),
        indirect=sorted(list(indirect_affected - direct_affected)),
        paths=impact_paths,
        uncertainty=uncertainty
    )