"""
codeimpact.ai_reasoner
======================

AIReasoner: generates natural-language explanations for a code-change's
impact, recommended tests, and (optionally) observed test results.

Two operating modes
-------------------
1. **IBM watsonx.ai / Granite** — used automatically when the environment
   variables WATSONX_APIKEY, WATSONX_PROJECT_ID, and WATSONX_URL are all
   present.  The model can be overridden via WATSONX_MODEL_ID (default:
   ``ibm/granite-3-3-8b-instruct``).
2. **Offline / deterministic fallback** — used when IBM credentials are
   absent or when every live call fails.  The explanation is assembled
   directly from the supplied evidence with no network call; no LLM
   involvement is claimed.

The public surface is intentionally narrow: one method, ``explain_impact``,
always returns a fully populated :class:`~codeimpact.schemas.AIExplanation`.
"""

from __future__ import annotations

import json
import logging
import os
import textwrap
from typing import Any

from codeimpact.schemas import (
    AIExplanation,
    ChangeInfo,
    DependencyEvidence,
    ImpactResult,
    TestCandidate,
    TestResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_MODEL = "ibm/granite-3-3-8b-instruct"
_REQUEST_TIMEOUT = 60  # seconds


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _env(key: str) -> str | None:
    """Return stripped env-var value, or None when absent/empty."""
    v = os.environ.get(key, "").strip()
    return v if v else None


def _has_watsonx_credentials() -> bool:
    """True only when all three mandatory watsonx credentials are set."""
    return bool(_env("WATSONX_APIKEY") and _env("WATSONX_PROJECT_ID") and _env("WATSONX_URL"))


def _fmt_list(items: list[str], indent: int = 4) -> str:
    """Format a list of strings as a bullet-pointed block."""
    pad = " " * indent
    return "\n".join(f"{pad}- {item}" for item in items) if items else f"{' ' * indent}(none)"


def _fmt_paths(paths: list[list[str]]) -> str:
    """Format dependency paths as numbered chains.

    Each entry in *paths* may be either a list of component strings or a
    pre-formatted string (e.g. ``"a -> b -> c"``).  Both forms are handled
    so that joining is never applied character-by-character to a string.
    """
    if not paths:
        return "    (no paths recorded)"
    lines = []
    for i, path in enumerate(paths, 1):
        if isinstance(path, str):
            chain = path
        else:
            chain = " -> ".join(path)
        lines.append(f"    {i}. {chain}")
    return "\n".join(lines)


def _fmt_evidence(evidence: list[DependencyEvidence]) -> str:
    """Format dependency evidence entries concisely."""
    if not evidence:
        return "    (no evidence)"
    lines = []
    for ev in evidence:
        loc = f" [{ev.file}:{ev.line}]" if ev.file else ""
        lines.append(
            f"    {ev.source} --[{ev.edge_type}]--> {ev.target}{loc}"
            + (f"  confidence={ev.confidence:.2f}" if ev.confidence < 1.0 else "")
        )
    return "\n".join(lines)


def _fmt_test_results(results: list[TestResult]) -> str:
    """Summarise test results as a compact table-like block."""
    if not results:
        return "    (no results)"
    lines = []
    for r in results:
        duration = f"{r.duration:.3f}s" if r.duration else "?"
        lines.append(f"    [{r.status.upper():8s}] {r.test_name}  ({duration})")
        if r.status in {"failed", "error"} and (r.stdout or r.stderr):
            excerpt = (r.stderr or r.stdout)[:300].strip()
            lines.append(f"             output: {excerpt}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _build_prompt(
    change: ChangeInfo,
    impact: ImpactResult,
    tests: list[TestCandidate],
    test_results: list[TestResult] | None,
) -> str:
    """Construct the structured system+user prompt sent to the LLM."""

    test_results = test_results or []

    changed_files_block = _fmt_list(change.changed_files)
    changed_funcs_block = _fmt_list(change.changed_functions)
    direct_block = _fmt_list(impact.direct)
    indirect_block = _fmt_list(impact.indirect)
    paths_block = _fmt_paths(impact.paths)
    evidence_block = _fmt_evidence(impact.evidence)
    impact_uncertainty_block = _fmt_list(impact.uncertainty)

    tests_block = _fmt_list(
        [
            f"{t.test_name} (file={t.test_file}, "
            f"covers={', '.join(t.target_components) or 'unknown'}, "
            f"reason={t.reason or 'n/a'}, confidence={t.confidence:.2f})"
            for t in tests
        ]
    )

    results_block = _fmt_test_results(test_results)

    has_results = bool(test_results)
    result_instruction = (
        "Actual test results are provided above. "
        "Use them verbatim; do NOT invent statuses, durations, or output."
        if has_results
        else "No test results are available yet. "
        "Do NOT fabricate any test outcomes or statuses."
    )

    prompt = textwrap.dedent(
        f"""\
        You are a senior software-engineering assistant producing a structured
        impact analysis explanation.  Your job is to INTERPRET the evidence
        below — never to invent files, functions, APIs, tests, or dependencies
        that are not explicitly listed.

        ════════════════════════ EVIDENCE ════════════════════════

        CHANGED FILES:
        {changed_files_block}

        CHANGED FUNCTIONS / SYMBOLS:
        {changed_funcs_block}

        DIFF EXCERPT (first 800 chars):
        {(change.diff or '(no diff supplied)')[:800]}

        DIRECT IMPACT (callers / importers of changed symbols):
        {direct_block}

        INDIRECT IMPACT (transitively reached components):
        {indirect_block}

        DEPENDENCY PATHS (primary evidence — these are the exact call chains
        that connect changed symbols to impacted components):
        {paths_block}

        DEPENDENCY EVIDENCE DETAILS:
        {evidence_block}

        IMPACT UNCERTAINTY NOTES:
        {impact_uncertainty_block}

        RECOMMENDED TESTS:
        {tests_block}

        ACTUAL TEST RESULTS:
        {results_block}

        ══════════════════════ INSTRUCTIONS ══════════════════════

        {result_instruction}

        Dependency paths are the primary evidence.  Only describe components
        that appear in the paths, evidence, changed files, or test lists above.
        If evidence is insufficient to make a claim, say so explicitly in the
        "uncertainty" field instead of guessing.

        Return ONLY a single valid JSON object — no markdown fences, no prose
        before or after — with exactly these keys:

        {{
          "summary": "<one-paragraph plain-English explanation of what changed
                       and why the listed components are affected>",
          "reasoning": [
            "<step-by-step reasoning point derived from the dependency paths
             and evidence — one string per logical step>"
          ],
          "affected_components": [
            "<fully-qualified component that is demonstrably impacted,
             exactly as it appears in the evidence>"
          ],
          "test_reasoning": [
            "<one entry per recommended test explaining which impacted
             component it covers and why it was selected>"
          ],
          "failure_summary": [
            "<one entry per FAILED or ERROR test result describing what
             went wrong — leave the list empty when all tests passed or
             when no results are available>"
          ],
          "uncertainty": [
            "<anything you cannot determine from the supplied evidence,
             or any caveat about confidence>"
          ]
        }}
        """
    )
    return prompt


# ---------------------------------------------------------------------------
# JSON → AIExplanation parsing
# ---------------------------------------------------------------------------


def _parse_llm_response(raw: str) -> AIExplanation:
    """
    Parse the LLM's raw text response into an :class:`AIExplanation`.

    Tries to extract a JSON object even when the model wraps it in
    markdown fences or adds surrounding prose.
    """
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # drop opening fence (may be ```json) and closing fence
        inner = []
        for line in lines[1:]:
            if line.strip().startswith("```"):
                break
            inner.append(line)
        text = "\n".join(inner).strip()

    # Locate the outermost JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in LLM response")

    data: dict[str, Any] = json.loads(text[start : end + 1])

    def _strlist(key: str) -> list[str]:
        val = data.get(key, [])
        if isinstance(val, list):
            return [str(v) for v in val]
        if isinstance(val, str):
            return [val] if val else []
        return []

    return AIExplanation(
        summary=str(data.get("summary", "")),
        reasoning=_strlist("reasoning"),
        affected_components=_strlist("affected_components"),
        test_reasoning=_strlist("test_reasoning"),
        failure_summary=_strlist("failure_summary"),
        uncertainty=_strlist("uncertainty"),
    )


# ---------------------------------------------------------------------------
# Offline / deterministic fallback — helpers
# ---------------------------------------------------------------------------


def _parse_diff_for_default_changes(diff: str) -> list[str]:
    """Extract -old / +new pairs from a unified diff for inline summary use.

    Returns a list of human-readable change descriptions, e.g.
    ``["rate=0.10 → rate=0.20"]``.  Only lines that have both a removal (-)
    and an addition (+) touching the same token are included; pure
    insertions/deletions are not described to avoid fabrication.
    """
    removed: list[str] = []
    added: list[str] = []
    for line in diff.splitlines():
        # Skip diff headers (---, +++, @@, diff --git …)
        if line.startswith("---") or line.startswith("+++") or line.startswith("@@") or line.startswith("diff"):
            continue
        if line.startswith("-"):
            removed.append(line[1:].strip())
        elif line.startswith("+"):
            added.append(line[1:].strip())

    descriptions: list[str] = []
    for old, new in zip(removed, added):
        if old != new:
            descriptions.append(f"{old!r} -> {new!r}")
    return descriptions


def _changed_functions_from_impact(
    change: ChangeInfo,
    impact: ImpactResult,
) -> list[str]:
    """Return the list of changed function nodes to use in the explanation.

    ``change.changed_functions`` is populated by git_analyzer only when the
    file path resolution succeeds.  When it is empty (e.g. because the git
    diff path includes the repo prefix and the file-open attempt fails),
    fall back to the function-level nodes from ``impact.changed``, which
    are populated by the pipeline's seed-expansion step and are always
    correct.
    """
    if change.changed_functions:
        return list(change.changed_functions)
    # impact.changed contains the full seed set: file node + function nodes.
    # Filter to the file.py:function_name entries only.
    return [c for c in impact.changed if ":" in c]


def _source_file_from_changed(change: ChangeInfo, impact: ImpactResult) -> str:
    """Return a display-friendly name for the changed source file.

    Strips any repo-path prefix that git may have prepended so that the
    summary reads 'pricing.py' rather than 'demo_repo/ecommerce/pricing.py'.
    """
    # Prefer the function-node file part if available (always repo-relative)
    fn_nodes = [c for c in impact.changed if ":" in c]
    if fn_nodes:
        return fn_nodes[0].split(":")[0]
    # Fall back to the last path component of the first changed file
    if change.changed_files:
        return change.changed_files[0].replace("\\", "/").split("/")[-1]
    return "(unknown file)"


def _relevant_evidence(
    impact: ImpactResult,
    changed_fns: list[str],
) -> list[DependencyEvidence]:
    """Return only evidence edges that connect changed or impacted source
    functions — excluding test-infrastructure edges to keep reasoning concise.
    """
    reportable = set(changed_fns) | set(impact.direct) | set(impact.indirect)
    return [
        ev for ev in impact.evidence
        if (ev.source in reportable or ev.target in reportable)
        and not ev.source.replace("\\", "/").startswith("tests/")
        and not ev.target.replace("\\", "/").startswith("tests/")
    ]


def _key_paths(impact: ImpactResult, changed_fns: list[str]) -> list[str]:
    """Return the shortest, non-redundant dependency paths that connect
    changed function nodes to impacted source functions.

    Only paths whose every node is either a changed function, a direct
    impact, or an indirect impact (i.e. all source-code function nodes) are
    included.  Paths that pass through test nodes or file/container nodes
    are skipped.
    """
    reportable = set(changed_fns) | set(impact.direct) | set(impact.indirect)
    seen_chains: set[str] = set()
    result: list[str] = []

    for path in impact.paths:
        nodes: list[str] = path.split(" -> ") if isinstance(path, str) else path
        # Keep only paths whose every hop is a source function node
        if not all(
            n in reportable or ":" in n and not n.replace("\\", "/").startswith("tests/")
            for n in nodes
        ):
            continue
        if any(n.replace("\\", "/").startswith("tests/") for n in nodes):
            continue
        # Deduplicate by chain string
        chain = " -> ".join(nodes)
        if chain not in seen_chains:
            seen_chains.add(chain)
            result.append(chain)

    return result


def _derive_test_covered_component(
    test: TestCandidate,
    impact: ImpactResult,
    evidence: list[DependencyEvidence],
) -> str:
    """Derive the source component a test covers from the evidence graph.

    Looks for an evidence edge where the test function calls a source
    function that appears in the impact result.  Falls back to the module
    name inferred from the test file name.
    """
    if test.target_components:
        return ", ".join(test.target_components)

    # Build test node id as it appears in evidence (backslash-normalised)
    test_node_variants = {
        f"{test.test_file}::{test.test_name}",
        f"{test.test_file}:{test.test_name}",
        test.test_file.replace("\\", "/") + "::" + test.test_name,
        test.test_file.replace("\\", "/") + ":" + test.test_name,
    }
    reportable = set(impact.direct) | set(impact.indirect)
    for ev in evidence:
        src_norm = ev.source.replace("\\", "/")
        src_with_colon = ev.source.replace("\\", "/").replace("::", ":")
        if any(
            src_norm == v.replace("\\", "/") or src_with_colon == v.replace("\\", "/")
            for v in test_node_variants
        ):
            if ev.target in reportable or ":" in ev.target:
                return ev.target
    # Fallback: derive module from test file name convention
    stem = test.test_file.replace("\\", "/").split("/")[-1]  # e.g. test_checkout.py
    module = stem.replace("test_", "").replace(".py", "")     # e.g. checkout
    return f"{module}.py (inferred)"


# ---------------------------------------------------------------------------
# Offline / deterministic fallback
# ---------------------------------------------------------------------------


def _offline_explanation(
    change: ChangeInfo,
    impact: ImpactResult,
    tests: list[TestCandidate],
    test_results: list[TestResult] | None,
    extra_uncertainty: list[str] | None = None,
) -> AIExplanation:
    """
    Build an :class:`AIExplanation` purely from the supplied evidence,
    without any LLM call.  The result is deterministic and honest about
    not using AI.
    """
    test_results = test_results or []

    # ── Derive the core facts we'll use throughout ───────────────────────────
    changed_fns   = _changed_functions_from_impact(change, impact)
    source_file   = _source_file_from_changed(change, impact)
    diff_changes  = _parse_diff_for_default_changes(change.diff or "")
    key_paths     = _key_paths(impact, changed_fns)
    rel_evidence  = _relevant_evidence(impact, changed_fns)

    n_direct   = len(impact.direct)
    n_indirect = len(impact.indirect)

    # ── Summary ─────────────────────────────────────────────────────────────
    fn_names = [fn.split(":")[-1] for fn in changed_fns]
    fn_phrase = (
        f"functions {', '.join(fn_names)}"
        if fn_names
        else f"file {source_file}"
    )
    change_detail = (
        f" ({'; '.join(diff_changes)})" if diff_changes else ""
    )
    direct_names  = [d.split(":")[-1] for d in impact.direct]
    indirect_names = [i.split(":")[-1] for i in impact.indirect]
    impact_phrase = (
        f"Directly impacted: {', '.join(direct_names) or 'none'}. "
        f"Indirectly impacted: {', '.join(indirect_names) or 'none'}."
    )
    failed_names = [
        r.test_name for r in test_results
        if r.status.strip().upper() in {"FAILED", "ERROR"}
    ]
    result_phrase = (
        f" Tests confirm impact: {', '.join(failed_names)} failed."
        if failed_names
        else (
            " All recommended tests passed."
            if test_results
            else ""
        )
    )

    summary = (
        f"A change was made to {fn_phrase} in {source_file}{change_detail}. "
        f"{impact_phrase}"
        f"{result_phrase} "
        f"(Explanation generated offline from dependency evidence; no LLM was used.)"
    )

    # ── Reasoning ───────────────────────────────────────────────────────────
    reasoning: list[str] = []

    # 1. What changed
    if changed_fns:
        reasoning.append(
            f"The following functions were modified: {', '.join(changed_fns)}."
        )
    else:
        reasoning.append(f"The file {source_file} was modified.")
    if diff_changes:
        reasoning.append(
            f"Diff shows: {'; '.join(diff_changes)}."
        )

    # 2. Direct impact — one sentence per direct function, citing evidence
    ev_by_target: dict[str, list[DependencyEvidence]] = {}
    for ev in rel_evidence:
        ev_by_target.setdefault(ev.target, []).append(ev)

    for node in impact.direct:
        fn_name = node.split(":")[-1]
        file_name = node.split(":")[0]
        callers = [
            ev.source.split(":")[-1]
            for ev in rel_evidence
            if ev.target == node
        ]
        if callers:
            reasoning.append(
                f"{fn_name} ({file_name}) directly depends on "
                f"{', '.join(callers)} — it calls or imports a changed symbol."
            )
        else:
            reasoning.append(
                f"{fn_name} ({file_name}) is directly impacted by the change."
            )

    # 3. Indirect impact — trace the shortest key path to each indirect node
    for node in impact.indirect:
        fn_name  = node.split(":")[-1]
        file_name = node.split(":")[0]
        # Find the shortest key path that ends at this node
        for path_chain in sorted(key_paths, key=lambda p: p.count("->")):
            nodes_in_path = [s.strip() for s in path_chain.split("->")]
            if nodes_in_path[-1] == node:
                reasoning.append(
                    f"{fn_name} ({file_name}) is indirectly impacted via: {path_chain}."
                )
                break
        else:
            reasoning.append(
                f"{fn_name} ({file_name}) is transitively reachable from the changed symbols."
            )

    # 4. Key dependency paths (source-function level, deduplicated)
    if key_paths:
        reasoning.append(
            f"Key call chains: {' | '.join(key_paths[:5])}"
            + (" (and more)" if len(key_paths) > 5 else "") + "."
        )

    # 5. Relevant evidence edges
    for ev in rel_evidence:
        loc = f" [{ev.file}:{ev.line}]" if ev.file else ""
        reasoning.append(
            f"Evidence: {ev.source} calls {ev.target}{loc}."
        )

    # ── Affected components ─────────────────────────────────────────────────
    seen_aff: set[str] = set()
    affected: list[str] = []
    for component in impact.direct + impact.indirect:
        if component not in seen_aff:
            seen_aff.add(component)
            affected.append(component)

    # ── Test reasoning ───────────────────────────────────────────────────────
    test_reasoning: list[str] = []
    for t in tests:
        covered = _derive_test_covered_component(t, impact, impact.evidence)
        result_for_test = next(
            (r for r in test_results if r.test_name == t.test_name), None
        )
        status_phrase = (
            f" — ran and {result_for_test.status.upper()}"
            if result_for_test
            else " — not yet run"
        )
        test_reasoning.append(
            f"{t.test_name} (in {t.test_file}) covers {covered}{status_phrase}."
        )

    # ── Failure summary ──────────────────────────────────────────────────────
    failure_summary: list[str] = []
    for r in test_results:
        if r.status.strip().upper() in {"FAILED", "ERROR"}:
            # Extract the assertion line from pytest's stderr output
            raw_output = (r.stderr or r.stdout or "").strip()
            # Look for the AssertionError line in pytest output
            excerpt = ""
            for line in raw_output.splitlines():
                line_s = line.strip()
                if line_s.startswith("AssertionError") or line_s.startswith("assert ") or line_s.startswith("E "):
                    excerpt = line_s.lstrip("E").strip()
                    break
            if not excerpt:
                excerpt = raw_output[:200].strip()
            failure_summary.append(
                f"{r.test_name} [{r.status.upper()}]: {excerpt}"
            )

    # ── Uncertainty ──────────────────────────────────────────────────────────
    uncertainty: list[str] = list(impact.uncertainty)
    uncertainty.append(
        "This explanation was produced offline from structured dependency "
        "evidence without an LLM; nuanced semantic reasoning is not available."
    )
    if not rel_evidence and not key_paths:
        uncertainty.append(
            "No relevant dependency evidence or paths were found; "
            "impact assessment may be incomplete."
        )
    if not test_results:
        uncertainty.append(
            "No test results were provided; failures cannot be assessed."
        )
    if not changed_fns and not diff_changes:
        uncertainty.append(
            "Changed functions could not be resolved from the diff; "
            "impact is inferred from file-level changes only."
        )
    if extra_uncertainty:
        uncertainty.extend(extra_uncertainty)

    return AIExplanation(
        summary=summary,
        reasoning=reasoning,
        affected_components=affected,
        test_reasoning=test_reasoning,
        failure_summary=failure_summary,
        uncertainty=uncertainty,
    )


# ---------------------------------------------------------------------------
# watsonx.ai client
# ---------------------------------------------------------------------------


def _call_watsonx(prompt: str) -> str:
    """
    Send *prompt* to IBM watsonx.ai and return the raw text response.

    Raises
    ------
    ImportError
        When the ``ibm-watsonx-ai`` package is not installed.
    Exception
        Propagated from the SDK on authentication or API errors.
    """
    from ibm_watsonx_ai import APIClient, Credentials  # type: ignore[import]
    from ibm_watsonx_ai.foundation_models import ModelInference  # type: ignore[import]

    api_key = _env("WATSONX_APIKEY")
    project_id = _env("WATSONX_PROJECT_ID")
    url = _env("WATSONX_URL")
    model_id = _env("WATSONX_MODEL_ID") or _DEFAULT_MODEL

    credentials = Credentials(url=url, api_key=api_key)
    client = APIClient(credentials=credentials, project_id=project_id)

    model = ModelInference(
        model_id=model_id,
        api_client=client,
        params={
            "max_new_tokens": 1200,
            "temperature": 0.0,
        },
    )

    response = model.generate_text(prompt=prompt)
    return response  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# AIReasoner
# ---------------------------------------------------------------------------


class AIReasoner:
    """
    Generates AI-powered (or offline-deterministic) impact explanations.

    Parameters
    ----------
    use_ai:
        When *True* (default), attempt to call IBM watsonx.ai if credentials
        are available.  Set to *False* to force offline mode in tests.
    """

    def __init__(self, *, use_ai: bool = True) -> None:
        self._use_ai = use_ai

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def explain_impact(
        self,
        change: ChangeInfo,
        impact: ImpactResult,
        tests: list[TestCandidate],
        test_results: list[TestResult] | None = None,
    ) -> AIExplanation:
        """
        Produce an :class:`~codeimpact.schemas.AIExplanation` for the supplied
        change, impact assessment, and test information.

        This method **always** returns a valid :class:`AIExplanation`; errors
        are surfaced through the ``uncertainty`` field rather than raising.

        Parameters
        ----------
        change:
            What changed (files, functions, diff).
        impact:
            Dependency analysis result (direct/indirect components, paths,
            evidence).
        tests:
            Recommended test candidates produced by the test-mapper module.
        test_results:
            Optional list of actual test-execution results.  When provided
            the LLM is instructed to incorporate them verbatim.

        Returns
        -------
        AIExplanation
            Fully populated explanation dataclass.
        """
        if self._use_ai and _has_watsonx_credentials():
            return self._explain_with_watsonx(change, impact, tests, test_results)
        return _offline_explanation(change, impact, tests, test_results)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _explain_with_watsonx(
        self,
        change: ChangeInfo,
        impact: ImpactResult,
        tests: list[TestCandidate],
        test_results: list[TestResult] | None,
    ) -> AIExplanation:
        """Attempt a watsonx.ai call; fall back to offline on any error."""
        extra_uncertainty: list[str] = []
        try:
            prompt = _build_prompt(change, impact, tests, test_results)
            logger.debug("Sending prompt to watsonx.ai (%d chars)", len(prompt))
            raw = _call_watsonx(prompt)
            logger.debug("Received watsonx.ai response (%d chars)", len(raw))
            return _parse_llm_response(raw)

        except ImportError:
            msg = (
                "ibm-watsonx-ai package is not installed; "
                "falling back to offline explanation."
            )
            logger.warning(msg)
            extra_uncertainty.append(msg)

        except json.JSONDecodeError as exc:
            msg = f"LLM returned non-JSON response ({exc}); falling back to offline explanation."
            logger.warning(msg)
            extra_uncertainty.append(msg)

        except Exception as exc:  # noqa: BLE001
            msg = f"watsonx.ai call failed ({type(exc).__name__}: {exc}); falling back to offline explanation."
            logger.warning(msg)
            extra_uncertainty.append(msg)

        return _offline_explanation(change, impact, tests, test_results, extra_uncertainty)
