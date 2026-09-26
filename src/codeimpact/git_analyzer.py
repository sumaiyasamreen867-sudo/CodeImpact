import ast
import subprocess
from typing import Dict, List, Set, Tuple
from src.codeimpact.schemas import ChangeInfo


def get_git_diff(repo_path: str, base_commit: str = "HEAD~1", target_commit: str = "HEAD") -> str:
    """Executes git diff between two commits and returns the unified diff string."""
    cmd = ["git", "-C", repo_path, "diff", f"{base_commit}..{target_commit}"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout


def extract_changed_line_ranges(diff_text: str) -> Dict[str, List[Tuple[int, int]]]:
    """Parses a unified diff to map modified files to lists of changed line numbers (line_start, line_end)."""
    changed_files_lines: Dict[str, List[Tuple[int, int]]] = {}
    current_file = None
    
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].strip()
            if current_file not in changed_files_lines:
                changed_files_lines[current_file] = []
        elif line.startswith("@@") and current_file:
            # Parse target file line range: @@ -old_start,old_count +new_start,new_count @@
            parts = line.split(" ")
            for part in parts:
                if part.startswith("+"):
                    range_str = part[1:]
                    if "," in range_str:
                        start, count = map(int, range_str.split(","))
                    else:
                        start, count = int(range_str), 1
                    end = start + max(count - 1, 0)
                    changed_files_lines[current_file].append((start, end))
    return changed_files_lines


def map_lines_to_functions(source_code: str, line_ranges: List[Tuple[int, int]]) -> List[str]:
    """Uses AST parsing to find all function definitions spanning any of the changed line ranges."""
    changed_functions: Set[str] = set()
    
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_start = getattr(node, "lineno", 0)
            func_end = getattr(node, "end_lineno", func_start)
            
            for start, end in line_ranges:
                # Check for line range overlap
                if max(func_start, start) <= min(func_end, end):
                    changed_functions.add(node.name)

    return sorted(list(changed_functions))


def analyze_git_change(repo_path: str, base_commit: str = "HEAD~1", target_commit: str = "HEAD") -> ChangeInfo:
    """Ingests a Git commit range and generates a structured ChangeInfo dataclass."""
    diff = get_git_diff(repo_path, base_commit, target_commit)
    changed_line_ranges = extract_changed_line_ranges(diff)
    
    changed_files = list(changed_line_ranges.keys())
    changed_functions = []

    for file_path, line_ranges in changed_line_ranges.items():
        full_path = f"{repo_path}/{file_path}" if not repo_path.endswith("/") else f"{repo_path}{file_path}"
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                code = f.read()
                funcs = map_lines_to_functions(code, line_ranges)
                changed_functions.extend([f"{file_path}:{func}" for func in funcs])
        except FileNotFoundError:
            continue

    return ChangeInfo(
        changed_files=changed_files,
        changed_functions=changed_functions,
        diff=diff,
        base_commit=base_commit,
        target_commit=target_commit
    )