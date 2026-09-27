"""
codeimpact.pipeline
===================

CodeImpactPipeline orchestrates the full analysis workflow:

    Git/change analysis
        → dependency graph construction
        → impact analysis
        → TestMapper   (map_affected_tests)
        → TestRunner   (run_tests)
        → Evaluator    (evaluate)
        → AIReasoner   (explain_impact)
        → ImpactReport

Usage
-----
    from src.codeimpact.pipeline import CodeImpactPipeline

    report = CodeImpactPipeline(use_ai=False).run(
        repo_path="demo_repo/ecommerce",
        base_commit="HEAD~1",
        target_commit="HEAD",
    )

The pipeline never raises; partial results are preserved and all
failures are recorded in ``ImpactReport.errors``.

Known API incompatibilities (do NOT modify the affected modules):
-----------------------------------------------------------------
1. ``impact_analyzer.analyze_impact`` sets ``ImpactResult(uncertainty=<float>)``
   but the schema declares ``uncertainty: List[str]``.  The pipeline
   normalises this after the call so the rest of the pipeline sees a list.

Path-normalisation note:
   ``git -C <repo_path>`` inherits the Python process cwd, so diff paths are
   relative to the Python cwd (e.g. ``demo_repo/ecommerce/pricing.py``).
   ``DependencyGraphBuilder`` walks ``repo_path`` directly and stores paths
   relative to ``repo_path`` (e.g. ``pricing.py``).  The pipeline strips the
   ``repo_path`` prefix from git paths before calling ``analyze_impact`` and
   expands file-level nodes to their contained function nodes so that the
   graph traversal has the right seeds.

2. ``report_generator.py`` is empty — there is no usable existing interface.
   ``ImpactReport`` is returned directly as the report.

3. ``ai_reasoner.py`` imports from ``codeimpact.schemas`` (installed-package
   style) while the rest of the codebase uses ``src.codeimpact.*``.  The
   pipeline adds the ``src/`` directory to ``sys.path`` before importing the
   reasoner so both import styles resolve to the same module.
"""

from __future__ import annotations

import datetime
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ensure both import styles (src.codeimpact.* and codeimpact.*) work.
# ai_reasoner uses "from codeimpact.schemas import …"; the rest uses
# "from src.codeimpact.* import …".  Inserting <project-root>/src into
# sys.path makes "codeimpact" resolvable as a top-level package.
# ---------------------------------------------------------------------------
_src_dir = str(Path(__file__).resolve().parent.parent)  # …/src
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from src.codeimpact.schemas import (  # noqa: E402
    ChangeInfo,
    ImpactReport,
    ImpactResult,
    TestCandidate,
    TestResult,
)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class CodeImpactPipeline:
    """
    Orchestrates the full CodeImpact analysis workflow.

    Parameters
    ----------
    use_ai:
        When *True* (default) the pipeline will use IBM watsonx.ai for the AI
        explanation step if credentials are present in the environment.
        Set to *False* to force offline/deterministic mode — useful for tests
        and CI environments without IBM credentials.
    """

    def __init__(self, *, use_ai: bool = True) -> None:
        self._use_ai = use_ai

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        repo_path: str,
        base_commit: str = "HEAD~1",
        target_commit: str = "HEAD",
    ) -> ImpactReport:
        """
        Execute the full pipeline and return an :class:`ImpactReport`.

        The report is *always* returned even when individual steps fail;
        partial results are preserved and errors are appended to
        ``ImpactReport.errors``.
        """
        report = ImpactReport(generated_at=datetime.datetime.now().isoformat())
        errors: List[str] = []

        # ── Step 1: Git / change analysis ────────────────────────────────
        change: Optional[ChangeInfo] = None
        try:
            from src.codeimpact.git_analyzer import analyze_git_change
            change = analyze_git_change(repo_path, base_commit, target_commit)
            report.change = change
            logger.info(
                "Step 1 complete: %d changed file(s), %d changed function(s)",
                len(change.changed_files),
                len(change.changed_functions),
            )
        except Exception as exc:
            msg = f"Step 1 (git analysis) failed: {type(exc).__name__}: {exc}"
            logger.error(msg)
            errors.append(msg)
            change = ChangeInfo(base_commit=base_commit, target_commit=target_commit)
            report.change = change

        # ── Step 2: Dependency graph construction ────────────────────────
        impact: Optional[ImpactResult] = None
        try:
            from src.codeimpact.dependency_graph import DependencyGraphBuilder
            from src.codeimpact.impact_analyzer import analyze_impact

            builder = DependencyGraphBuilder()
            builder.parse_repository(repo_path)
            graph = builder.get_graph()

            # ── Resolve git paths → graph-relative paths ─────────────────
            # git -C <repo_path> inherits the process cwd, so diff paths are
            # relative to the Python cwd (e.g. "demo_repo/ecommerce/pricing.py").
            # The graph stores paths relative to repo_path ("pricing.py").
            # Normalise by stripping the repo_path prefix (portable: use
            # PurePosixPath-style comparison on both sides).
            repo_prefix = Path(repo_path).resolve()

            def _to_graph_rel(p: str) -> str:
                """Strip repo_path prefix so the key matches graph nodes."""
                try:
                    return str(Path(p).resolve().relative_to(repo_prefix))
                except ValueError:
                    # Already relative or unrelated — return as-is.
                    return p

            graph_files = [_to_graph_rel(f) for f in change.changed_files]
            graph_funcs = [_to_graph_rel(f) for f in change.changed_functions]

            # ── Expand file nodes → contained function nodes ──────────────
            # analyze_impact traverses *reverse* edges from the seed nodes.
            # File nodes in the graph only have "contains" edges pointing
            # *outward* to their functions; reversing those gives no useful
            # upstream dependents.  Seeding with the function nodes directly
            # gives the correct propagation through call/import edges.
            expanded: List[str] = []
            for node in graph.nodes():
                for gf in graph_files:
                    # Match "pricing.py" against "pricing.py", "pricing.py:fn", etc.
                    node_norm = node.replace("\\", "/")
                    gf_norm = gf.replace("\\", "/")
                    if node_norm == gf_norm or node_norm.startswith(gf_norm + ":"):
                        expanded.append(node)
                        break

            # Add any explicitly named function nodes from changed_functions.
            for fn in graph_funcs:
                fn_norm = fn.replace("\\", "/")
                for node in graph.nodes():
                    if node.replace("\\", "/") == fn_norm and node not in expanded:
                        expanded.append(node)

            # Fall back to raw git paths if nothing resolved (avoids empty seed).
            changed_components = expanded if expanded else (
                list(change.changed_files) + list(change.changed_functions)
            )

            impact = analyze_impact(graph, changed_components)

            # ── Normalise uncertainty: impact_analyzer sets a float, schema
            #    expects List[str].  Convert without touching the module.
            if isinstance(impact.uncertainty, float):
                val = impact.uncertainty
                impact.uncertainty = (
                    [f"Uncertainty score: {val:.2f}"] if val else []
                )

            # ── Snapshot full impact for TestMapper before filtering ──────
            # TestMapper.map_affected_tests() matches against bare module
            # names ("checkout", "checkout.py") that only appear when
            # file/container nodes are present in direct/indirect.  The
            # snapshot copies the two lists (impact is a dataclass — the
            # object reference is shared, so lists must be copied explicitly
            # to survive the in-place reassignment below).
            _mapper_direct   = list(impact.direct)
            _mapper_indirect = list(impact.indirect)

            # ── Filter direct/indirect to source-code function nodes only ─
            # Retain only nodes whose graph type is "function" and whose
            # path does not start with "tests/" — i.e. exactly the
            # file.py:function_name entries.  File/container nodes and all
            # test-infrastructure nodes are removed from the reported lists.
            # paths and evidence are left complete for auditing.
            def _is_reportable(node: str) -> bool:
                if graph.nodes.get(node, {}).get("type") != "function":
                    return False
                return not node.replace("\\", "/").startswith("tests/")

            impact.direct = sorted(
                n for n in impact.direct if _is_reportable(n)
            )
            impact.indirect = sorted(
                n for n in impact.indirect if _is_reportable(n)
            )

            # Attach evidence gathered by the graph builder
            impact.evidence = builder.get_evidences()

            # ── Backfill change.changed_functions ─────────────────────────
            # git_analyzer leaves changed_functions=[] when the diff path
            # includes the repo prefix (open() fails silently).  The seed
            # expansion above already resolved the correct function nodes
            # into impact.changed; copy them back so every consumer of
            # ChangeInfo sees accurate function-level data.
            if not change.changed_functions:
                change.changed_functions = [
                    node for node in impact.changed if ":" in node
                ]

            report.impact = impact
            logger.info(
                "Step 2 complete: %d direct, %d indirect impacted component(s)",
                len(impact.direct),
                len(impact.indirect),
            )
        except Exception as exc:
            msg = f"Step 2 (dependency/impact analysis) failed: {type(exc).__name__}: {exc}"
            logger.error(msg)
            errors.append(msg)
            impact = ImpactResult(
                changed=list(change.changed_files),
                uncertainty=["Impact analysis unavailable due to error."],
            )
            report.impact = impact

        # ── Step 3: TestMapper ────────────────────────────────────────────
        candidates: List[TestCandidate] = []
        try:
            from src.codeimpact.test_mapper import TestMapper
            # Restore unfiltered lists into a throw-away ImpactResult so
            # TestMapper receives file/container nodes for matching, while
            # report.impact keeps the clean function-only lists.
            from src.codeimpact.schemas import ImpactResult as _IR
            _impact_for_mapper = _IR(
                changed=list(impact.changed),
                direct=_mapper_direct,
                indirect=_mapper_indirect,
            )
            raw_candidates = TestMapper(repo_path).map_affected_tests(_impact_for_mapper)

            # ── Deduplicate (TestMapper double-globs flat tests/ dirs) ────
            seen: set = set()
            for c in raw_candidates:
                key = (c.test_file, c.test_name)
                if key not in seen:
                    seen.add(key)
                    candidates.append(c)

            # ── Enrich TestCandidate fields from evidence ─────────────────
            # TestMapper leaves target_components=[], reason="", confidence=1.0.
            # Walk the evidence edges: find the edge whose source matches
            # this test function and whose target is a source-code function
            # node (in direct or indirect).  Use that to fill target_components
            # and reason.  Confidence is scaled by path distance: direct
            # impact = 1.0, indirect = 0.9 (one hop removed from direct).
            direct_set   = set(impact.direct)
            indirect_set = set(impact.indirect)
            all_evidence = impact.evidence   # already attached in Step 2

            for cand in candidates:
                # Build the test-function node key as stored in evidence:
                # evidence sources use backslash paths on Windows, e.g.
                # "tests\test_checkout.py:test_checkout_total"
                test_node = cand.test_file + ":" + cand.test_name
                test_node_fwd = cand.test_file.replace("\\", "/") + ":" + cand.test_name

                matched_target: Optional[str] = None
                for ev in all_evidence:
                    src_fwd = ev.source.replace("\\", "/")
                    if src_fwd == test_node_fwd or ev.source == test_node:
                        # Prefer a direct-impact target over indirect
                        if ev.target in direct_set:
                            matched_target = ev.target
                            break
                        if ev.target in indirect_set and matched_target is None:
                            matched_target = ev.target

                if matched_target:
                    cand.target_components = [matched_target]
                    fn = matched_target.split(":")[-1]
                    src_file = matched_target.split(":")[0]
                    tier = "direct" if matched_target in direct_set else "indirect"
                    cand.reason = (
                        f"Calls {fn} ({src_file}), which is a {tier} "
                        f"dependent of the changed functions."
                    )
                    cand.confidence = 1.0 if tier == "direct" else 0.9
                else:
                    # Fallback: infer module from test file name convention
                    stem = cand.test_file.replace("\\", "/").split("/")[-1]
                    module = stem.replace("test_", "").replace(".py", "")
                    cand.target_components = [f"{module}.py"]
                    cand.reason = f"Test file name matches changed module {module}.py."
                    cand.confidence = 0.8

            report.recommended_tests = candidates
            logger.info("Step 3 complete: %d test candidate(s)", len(candidates))
        except Exception as exc:
            msg = f"Step 3 (test mapping) failed: {type(exc).__name__}: {exc}"
            logger.error(msg)
            errors.append(msg)

        # ── Step 4: TestRunner ────────────────────────────────────────────
        results: List[TestResult] = []
        try:
            from src.codeimpact.test_runner import TestRunner
            results = TestRunner(repo_path).run_tests(candidates)
            report.test_results = results
            passed = sum(1 for r in results if r.status.lower() == "passed")
            logger.info(
                "Step 4 complete: %d/%d test(s) passed",
                passed,
                len(results),
            )
        except Exception as exc:
            msg = f"Step 4 (test runner) failed: {type(exc).__name__}: {exc}"
            logger.error(msg)
            errors.append(msg)

        # ── Step 5: Evaluator ─────────────────────────────────────────────
        try:
            from src.codeimpact.evaluator import Evaluator
            evaluation = Evaluator().evaluate(candidates, results)
            report.evaluation = evaluation
            logger.info(
                "Step 5 complete: precision=%s, recall=%s",
                f"{evaluation.precision:.2f}" if evaluation.precision is not None else "n/a",
                f"{evaluation.recall:.2f}" if evaluation.recall is not None else "n/a",
            )
        except Exception as exc:
            msg = f"Step 5 (evaluation) failed: {type(exc).__name__}: {exc}"
            logger.error(msg)
            errors.append(msg)

        # ── Step 6: AIReasoner ────────────────────────────────────────────
        try:
            from src.codeimpact.ai_reasoner import AIReasoner
            explanation = AIReasoner(use_ai=self._use_ai).explain_impact(
                change, impact, candidates, results
            )
            report.ai_explanation = explanation
            logger.info("Step 6 complete: AI explanation generated")
        except Exception as exc:
            msg = f"Step 6 (AI reasoner) failed: {type(exc).__name__}: {exc}"
            logger.error(msg)
            errors.append(msg)

        # ── Finalise ──────────────────────────────────────────────────────
        report.errors = errors
        report.success = len(errors) == 0
        return report
