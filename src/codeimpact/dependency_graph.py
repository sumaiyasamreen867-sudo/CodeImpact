import os
import networkx as nx
from typing import Dict, List
from src.codeimpact.schemas import DependencyEvidence
from src.codeimpact.parser import parse_code


class DependencyGraphBuilder:
    """Builds a NetworkX graph populated with deterministic evidence edges from Python files."""

    def __init__(self):
        self.graph = nx.DiGraph()
        self.evidences: List[DependencyEvidence] = []

    def parse_repository(self, root_dir: str):
        file_ast_data = {}
        
        # 1. Gather AST data for all Python files
        for root, _, files in os.walk(root_dir):
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, root_dir)
                    with open(full_path, "r", encoding="utf-8") as f:
                        file_ast_data[rel_path] = parse_code(rel_path, f.read())

        # 2. Add nodes to graph
        for rel_path, data in file_ast_data.items():
            self.graph.add_node(rel_path, type="file")
            for fn in data["functions"]:
                fn_node = f"{rel_path}:{fn['name']}"
                self.graph.add_node(fn_node, type="function")
                self.graph.add_edge(rel_path, fn_node, edge_type="contains")

        # 3. Add evidence-backed edges based on calls and imports
        for rel_path, data in file_ast_data.items():
            # Process direct calls inside the same file
            for call in data["calls"]:
                caller_fn = call["caller"]
                callee_fn = call["callee"]
                
                if caller_fn:
                    caller_node = f"{rel_path}:{caller_fn}"
                    target_node = f"{rel_path}:{callee_fn}"
                    
                    if self.graph.has_node(target_node):
                        evidence = DependencyEvidence(
                            source=caller_node,
                            target=target_node,
                            edge_type="function_call",
                            file=rel_path,
                            line=call["line"],
                            evidence=f"{caller_fn} calls {callee_fn} on line {call['line']}"
                        )
                        self.evidences.append(evidence)
                        self.graph.add_edge(caller_node, target_node, evidence=evidence)

            # Process imports across modules
            for imp in data["imports"]:
                if imp["type"] == "import_from":
                    module_file = f"{imp['module']}.py"
                    if module_file in file_ast_data:
                        target_func_node = f"{module_file}:{imp['name']}"
                        
                        # Search for usage of this imported symbol in the current file
                        for call in data["calls"]:
                            if call["callee"] == imp["name"] and call["caller"]:
                                caller_node = f"{rel_path}:{call['caller']}"
                                evidence = DependencyEvidence(
                                    source=caller_node,
                                    target=target_func_node if self.graph.has_node(target_func_node) else module_file,
                                    edge_type="cross_module_call",
                                    file=rel_path,
                                    line=call["line"],
                                    evidence=f"Imported call to {imp['name']} from {module_file} at line {call['line']}"
                                )
                                self.evidences.append(evidence)
                                self.graph.add_edge(
                                    caller_node,
                                    target_func_node if self.graph.has_node(target_func_node) else module_file,
                                    evidence=evidence
                                )

    def get_graph(self) -> nx.DiGraph:
        return self.graph

    def get_evidences(self) -> List[DependencyEvidence]:
        return self.evidences