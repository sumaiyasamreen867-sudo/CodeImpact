import ast
from typing import Dict, List, Any


class RepositoryParser(ast.NodeVisitor):
    """AST visitor to extract imports, function definitions, and call references from Python source files."""

    def __init__(self, filename: str):
        self.filename = filename
        self.imports: List[Dict[str, Any]] = []
        self.functions: List[Dict[str, Any]] = []
        self.calls: List[Dict[str, Any]] = []
        self._current_function = None

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append({
                "type": "import",
                "name": alias.name,
                "asname": alias.asname,
                "line": node.lineno
            })
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        for alias in node.names:
            self.imports.append({
                "type": "import_from",
                "module": node.module or "",
                "name": alias.name,
                "asname": alias.asname,
                "line": node.lineno
            })
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        previous_function = self._current_function
        self._current_function = node.name
        
        self.functions.append({
            "name": node.name,
            "line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "args": [arg.arg for arg in node.args.args]
        })
        
        self.generic_visit(node)
        self._current_function = previous_function

    def visit_Call(self, node: ast.Call):
        call_name = None
        if isinstance(node.func, ast.Name):
            call_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            call_name = node.func.attr

        if call_name:
            self.calls.append({
                "caller": self._current_function,
                "callee": call_name,
                "line": node.lineno
            })
        self.generic_visit(node)


def parse_code(filename: str, source_code: str) -> Dict[str, Any]:
    """Parses source code into structured definitions, imports, and calls."""
    tree = ast.parse(source_code, filename=filename)
    visitor = RepositoryParser(filename)
    visitor.visit(tree)
    return {
        "filename": filename,
        "imports": visitor.imports,
        "functions": visitor.functions,
        "calls": visitor.calls
    }
    