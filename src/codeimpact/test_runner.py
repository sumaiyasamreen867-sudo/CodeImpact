import subprocess
import time
import sys
from pathlib import Path
from typing import List
from .schemas import TestCandidate, TestResult


class TestRunner:
    """
    Executes targeted pytest test candidates and captures stdout, stderr,
    durations, and exit statuses into standardized TestResult schemas.
    """

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()

    def _resolve_test_target(self, candidate: TestCandidate) -> tuple[str, str]:
        """
        Safely extracts the file path, function name, and full pytest target ID
        from a TestCandidate object regardless of field variations.
        """
        # Retrieve test file path
        test_file = getattr(candidate, "test_file", getattr(candidate, "file", ""))
        
        # Retrieve test function name
        test_name = getattr(candidate, "test_name", getattr(candidate, "function", ""))
        
        # Check if full test_id is already provided directly
        test_id = getattr(candidate, "test_id", None)

        if not test_id:
            if test_file and test_name:
                test_id = f"{test_file}::{test_name}"
            elif test_file:
                test_id = str(test_file)
            else:
                test_id = "unknown_test"

        return test_id, str(test_file)

    def run_tests(self, candidates: List[TestCandidate], timeout_seconds: int = 30) -> List[TestResult]:
        """Runs a targeted list of TestCandidates using pytest in a subprocess."""
        if not candidates:
            return []

        results: List[TestResult] = []

        for candidate in candidates:
            test_id, test_file = self._resolve_test_target(candidate)

            # Build command to run specific pytest target
            cmd = [sys.executable, "-m", "pytest", test_id, "-v", "--tb=short"]

            start_time = time.time()
            try:
                process = subprocess.run(
                    cmd,
                    cwd=str(self.repo_path),
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds
                )
                duration = round(time.time() - start_time, 3)

                # Determine status based on pytest returncode
                if process.returncode == 0:
                    status = "PASSED"
                elif process.returncode == 1:
                    status = "FAILED"
                else:
                    status = "ERROR"

                results.append(
                    TestResult(

    test_name=candidate.test_name,
    status=status,
    duration=duration,
    stdout=process.stdout,
    stderr=process.stderr,
    exit_code=process.returncode
)
                )

            except subprocess.TimeoutExpired:
                duration = round(time.time() - start_time, 3)
                results.append(
                   TestResult(
    test_name=candidate.test_name,
    status="error",
    duration=duration,
    stdout="",
    stderr=f"Execution timed out after {timeout_seconds}s"
)
                )
            except Exception as e:
                duration = round(time.time() - start_time, 3)
                results.append(
                    TestResult(
    test_name=candidate.test_name,
    status="error",
    duration=duration,
    stdout="",
    stderr=str(e)
)
                )

        return results