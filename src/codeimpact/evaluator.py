from typing import List, Optional
from .schemas import TestCandidate, TestResult, EvaluationResult

# The runner produces "PASSED" (uppercase) for a clean exit.
# Timeout/exception paths write lowercase "error".
# Any status that is not a passing status is treated as relevant
# (the test surfaced a real problem and should have been selected).
_PASSING_STATUS = "passed"


def _is_passing(status: str) -> bool:
    return status.strip().lower() == _PASSING_STATUS


class Evaluator:
    """
    Compares TestMapper predictions (List[TestCandidate]) against
    TestRunner results (List[TestResult]) and produces a populated
    EvaluationResult with precision / recall metrics.

    Terminology
    -----------
    predicted   - test_names the mapper recommended running
    relevant    - test_names whose result was not a passing status
                  (i.e. FAILED / ERROR / error / skipped / anything non-passing)

    true_positives  (TP)  - predicted ∩ relevant
    false_positives (FP)  - predicted − relevant  (mapper flagged a test that passed)
    false_negatives (FN)  - relevant − predicted  (failing test the mapper missed)

    precision  = |TP| / |predicted|   (what fraction of selected tests mattered)
    recall     = |TP| / |relevant|    (what fraction of failing tests were caught)
    """

    def evaluate(
        self,
        candidates: List[TestCandidate],
        results: List[TestResult],
    ) -> EvaluationResult:
        """
        Parameters
        ----------
        candidates : output of TestMapper.map_affected_tests()
        results    : output of TestRunner.run_tests()

        Returns
        -------
        EvaluationResult with all metrics populated.
        """
        predicted: set = {c.test_name for c in candidates}
        relevant: set = {
            r.test_name for r in results if not _is_passing(r.status)
        }

        tp = sorted(predicted & relevant)
        fp = sorted(predicted - relevant)
        fn = sorted(relevant - predicted)

        precision: Optional[float]
        if predicted:
            precision = round(len(tp) / len(predicted), 4)
        else:
            precision = None

        recall: Optional[float]
        if relevant:
            recall = round(len(tp) / len(relevant), 4)
        else:
            recall = None

        total = len(results)
        targeted = len(candidates)

        test_reduction: Optional[float]
        if total > 0:
            test_reduction = round(1.0 - targeted / total, 4)
        else:
            test_reduction = None

        return EvaluationResult(
            predicted_components=sorted(predicted),
            actual_affected_components=sorted(relevant),
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
            precision=precision,
            recall=recall,
            total_tests=total,
            targeted_tests=targeted,
            test_reduction=test_reduction,
        )
