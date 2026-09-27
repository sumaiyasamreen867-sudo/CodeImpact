"""
codeimpact.report_generator
============================

Serialises a completed :class:`~codeimpact.schemas.ImpactReport` into a
plain, JSON-serialisable :class:`dict` suitable for:

* CLI ``--json`` output
* Streamlit ``st.json()`` display
* Saving to disk as ``impact_report.json``
* Any future reporting layer

Usage
-----
    from src.codeimpact.report_generator import generate_report

    report = CodeImpactPipeline(use_ai=False).run(...)
    data   = generate_report(report)
    import json
    print(json.dumps(data, indent=2))

The function never raises; if any schema object is None or missing it
produces an empty sub-dict / empty list rather than propagating the gap.
All values are primitive types (str, int, float, bool, list, dict, None)
so the result is safe to pass directly to ``json.dumps``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.codeimpact.schemas import (
    AIExplanation,
    ChangeInfo,
    DependencyEvidence,
    EvaluationResult,
    ImpactReport,
    ImpactResult,
    TestCandidate,
    TestResult,
)


# ---------------------------------------------------------------------------
# Per-schema serialisers (private)
# ---------------------------------------------------------------------------

def _serialise_change(change: Optional[ChangeInfo]) -> Dict[str, Any]:
    if change is None:
        return {}
    return {
        "base_commit":        change.base_commit,
        "target_commit":      change.target_commit,
        "changed_files":      list(change.changed_files),
        "changed_functions":  list(change.changed_functions),
        "diff":               change.diff or "",
    }


def _serialise_evidence(ev: DependencyEvidence) -> Dict[str, Any]:
    return {
        "source":     ev.source,
        "target":     ev.target,
        "edge_type":  ev.edge_type,
        "file":       ev.file,
        "line":       ev.line,
        "evidence":   ev.evidence,
        "confidence": ev.confidence,
    }


def _serialise_impact(impact: Optional[ImpactResult]) -> Dict[str, Any]:
    if impact is None:
        return {}
    return {
        "changed":     list(impact.changed),
        "direct":      list(impact.direct),
        "indirect":    list(impact.indirect),
        "paths":       [
            (p if isinstance(p, str) else " -> ".join(p))
            for p in impact.paths
        ],
        "evidence":    [_serialise_evidence(e) for e in impact.evidence],
        "uncertainty": list(impact.uncertainty),
    }


def _serialise_candidate(t: TestCandidate) -> Dict[str, Any]:
    return {
        "test_name":         t.test_name,
        "test_file":         t.test_file,
        "target_components": list(t.target_components),
        "reason":            t.reason,
        "confidence":        t.confidence,
    }


def _serialise_result(r: TestResult) -> Dict[str, Any]:
    return {
        "test_name": r.test_name,
        "status":    r.status,
        "duration":  r.duration,
        "exit_code": r.exit_code,
        # Omit raw stdout/stderr from the summary dict to keep it compact;
        # callers that need full output can access report.test_results directly.
    }


def _serialise_evaluation(ev: Optional[EvaluationResult]) -> Dict[str, Any]:
    if ev is None:
        return {}
    return {
        "predicted_components":       list(ev.predicted_components),
        "actual_affected_components": list(ev.actual_affected_components),
        "true_positives":             list(ev.true_positives),
        "false_positives":            list(ev.false_positives),
        "false_negatives":            list(ev.false_negatives),
        "precision":                  ev.precision,
        "recall":                     ev.recall,
        "total_tests":                ev.total_tests,
        "targeted_tests":             ev.targeted_tests,
        "test_reduction":             ev.test_reduction,
    }


def _serialise_explanation(ax: Optional[AIExplanation]) -> Dict[str, Any]:
    if ax is None:
        return {}
    return {
        "summary":             ax.summary,
        "reasoning":           list(ax.reasoning),
        "affected_components": list(ax.affected_components),
        "test_reasoning":      list(ax.test_reasoning),
        "failure_summary":     list(ax.failure_summary),
        "uncertainty":         list(ax.uncertainty),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_report(report: ImpactReport) -> Dict[str, Any]:
    """
    Serialise a completed :class:`ImpactReport` to a plain dict.

    Every field defined in the schema is represented.  The result is fully
    JSON-serialisable (no dataclass instances, no Path objects, no sets).

    Parameters
    ----------
    report:
        The :class:`ImpactReport` produced by :class:`CodeImpactPipeline`.

    Returns
    -------
    dict
        A JSON-serialisable dictionary mirroring the full report structure.
    """
    return {
        "generated_at":      report.generated_at,
        "success":           report.success,
        "errors":            list(report.errors),
        "change":            _serialise_change(report.change),
        "impact":            _serialise_impact(report.impact),
        "recommended_tests": [_serialise_candidate(t) for t in report.recommended_tests],
        "test_results":      [_serialise_result(r) for r in report.test_results],
        "evaluation":        _serialise_evaluation(report.evaluation),
        "ai_explanation":    _serialise_explanation(report.ai_explanation),
    }
