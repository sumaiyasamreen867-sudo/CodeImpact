import ast
import os
from pathlib import Path
from typing import List, Set, Dict
from .schemas import ImpactResult, TestCandidate


class TestMapper:
    """
    Analyzes test files in a repository, builds mapping between tests and 
    source code components, and identifies candidate tests based on impact analysis.
    """

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def _get_test_files(self, test_dir: str = "tests") -> List[Path]:
        """Locates all test files in the repository."""
        target_dir = self.repo_path / test_dir
        if not target_dir.exists():
            # Fallback to searching the entire repo for test_*.py files
            return list(self.repo_path.glob("**/test_*.py"))
        return list(target_dir.glob("test_*.py")) + list(target_dir.glob("**/test_*.py"))

    def _parse_test_file_dependencies(self, test_file_path: Path) -> Dict[str, Set[str]]:
        """
        Parses a test file with AST to extract function definitions and 
        the imports/module calls made inside them.
        """
        test_deps: Dict[str, Set[str]] = {}
        try:
            with open(test_file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(test_file_path))

            rel_file_path = str(test_file_path.relative_to(self.repo_path))

            # Find all import targets at file level
            imported_modules = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_modules.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported_modules.add(node.module)
                        for alias in node.names:
                            imported_modules.add(f"{node.module}.{alias.name}")

            # Map individual test functions to their imports/calls
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    func_deps = set(imported_modules)
                    # Infer affected file name based on conventions (e.g. test_checkout.py -> checkout.py)
                    impl_module = test_file_path.stem.replace("test_", "")
                    func_deps.add(impl_module)
                    func_deps.add(f"{impl_module}.py")

                    test_id = f"{rel_file_path}::{node.name}"
                    test_deps[test_id] = func_deps

        except Exception as e:
            print(f"Warning: Failed to parse test file {test_file_path}: {e}")

        return test_deps

    def map_affected_tests(self, impact: ImpactResult) -> List[TestCandidate]:
        """
        Given an ImpactResult, finds all tests that touch the directly or 
        indirectly affected components.
        """
        affected_components = set(impact.changed + impact.direct + impact.indirect)
        test_files = self._get_test_files()
        candidates: List[TestCandidate] = []

        for test_file in test_files:
            rel_path = str(test_file.relative_to(self.repo_path))
            test_deps = self._parse_test_file_dependencies(test_file)

            for test_id, deps in test_deps.items():
                func_name = test_id.split("::")[-1]
                
                # Check intersection between test dependencies and affected components
                matched_evidence = []
                for comp in affected_components:
                    # Match by file name, function name, or module prefix
                    comp_clean = comp.replace(".py", "")
                    if any(comp_clean in dep or comp in dep for dep in deps):
                        matched_evidence.append(f"Dependency match: {comp}")

                if matched_evidence:
                    candidate = TestCandidate(
                        test_name=func_name,
                        test_file=rel_path
                    )
                    candidates.append(candidate)

        return candidates