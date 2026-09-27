"""
CodeImpact – Streamlit Dashboard
=================================
Presentation layer only.  All analysis is delegated to the existing
CodeImpactPipeline; nothing is duplicated or re-implemented here.

Run from the CodeImpact repository root:
    streamlit run ui/dashboard.py
"""

from __future__ import annotations

import os
import sys
import time

# ---------------------------------------------------------------------------
# Path setup — make "src.codeimpact.*" importable when Streamlit is launched
# from the CodeImpact repo root (or any sub-directory).
# ---------------------------------------------------------------------------
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

# Also ensure the 'src' directory is on the path so 'codeimpact.*' style
# imports inside ai_reasoner.py resolve to the same modules.
_src_dir = os.path.join(_repo_root, "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import streamlit as st

from src.codeimpact.pipeline import CodeImpactPipeline
from src.codeimpact.report_generator import generate_report
from src.codeimpact.schemas import ImpactReport

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CodeImpact",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Minimal custom CSS — keeps it clean without overriding Streamlit internals
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .ci-hero-title  { font-size: 2.4rem; font-weight: 800; margin-bottom: 0; }
    .ci-hero-sub    { font-size: 1.05rem; color: #57606a; margin-top: 0.2rem; }
    .ci-section     { font-size: 1.15rem; font-weight: 700; margin-top: 1.2rem; margin-bottom: 0.3rem; }
    .ci-badge-pass  { background:#d1fae5; color:#065f46; border-radius:6px; padding:2px 10px; font-weight:600; font-size:0.88rem; }
    .ci-badge-fail  { background:#fee2e2; color:#991b1b; border-radius:6px; padding:2px 10px; font-weight:600; font-size:0.88rem; }
    .ci-badge-error { background:#fef3c7; color:#92400e; border-radius:6px; padding:2px 10px; font-weight:600; font-size:0.88rem; }
    .ci-pill        { display:inline-block; background:#eff6ff; color:#1d4ed8; border-radius:999px;
                      padding:2px 12px; font-size:0.82rem; margin:2px; }
    .ci-pill-indirect { background:#faf5ff; color:#6d28d9; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(
    '<p class="ci-hero-title">🔍 CodeImpact</p>'
    '<p class="ci-hero-sub">AI-powered change impact analysis and test intelligence — '
    'know exactly which functions are affected and which tests to run, before you merge.</p>',
    unsafe_allow_html=True,
)
st.divider()


# ---------------------------------------------------------------------------
# Sidebar / input panel
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Analysis Settings")
    repo_path = st.text_input(
        "Repository path",
        value="demo_repo/ecommerce",
        help="Path relative to the CodeImpact project root, or an absolute path.",
    )
    base_commit = st.text_input("Base commit", value="HEAD~1")
    target_commit = st.text_input("Target commit", value="HEAD")
    use_ai = st.toggle(
        "Enable IBM watsonx.ai",
        value=False,
        help="Requires WATSONX_APIKEY, WATSONX_PROJECT_ID, and WATSONX_URL in the environment.",
    )
    run_button = st.button("🚀 Analyze Impact", type="primary", use_container_width=True)

# Also expose a prominent button in the main area for first-time visitors
if "report" not in st.session_state:
    col_btn, _ = st.columns([2, 3])
    with col_btn:
        main_run = st.button(
            "🚀 Analyze Impact",
            type="primary",
            use_container_width=True,
            key="main_run_btn",
        )
    run_button = run_button or main_run

# ---------------------------------------------------------------------------
# Run the pipeline
# ---------------------------------------------------------------------------
if run_button:
    with st.spinner("Running CodeImpact pipeline…"):
        t0 = time.perf_counter()
        try:
            pipeline = CodeImpactPipeline(use_ai=use_ai)
            report: ImpactReport = pipeline.run(
                repo_path=repo_path,
                base_commit=base_commit,
                target_commit=target_commit,
            )
            data = generate_report(report)
            elapsed = time.perf_counter() - t0
            st.session_state["report"] = report
            st.session_state["data"] = data
            st.session_state["elapsed"] = elapsed
        except Exception as exc:
            st.error(f"**Pipeline raised an unexpected exception:** {type(exc).__name__}: {exc}")
            st.stop()

# ---------------------------------------------------------------------------
# Display results (only when a report is in session state)
# ---------------------------------------------------------------------------
if "report" not in st.session_state:
    st.info("Configure the repository path and commits in the **⚙️ sidebar**, then click **Analyze Impact**.")
    st.stop()

report: ImpactReport = st.session_state["report"]
data: dict = st.session_state["data"]
elapsed: float = st.session_state.get("elapsed", 0.0)


# ── Pipeline status banner ────────────────────────────────────────────────
if report.success:
    st.success(f"✅ Analysis complete in {elapsed:.1f}s  —  generated at {report.generated_at}")
else:
    st.warning(
        f"⚠️ Analysis finished with {len(report.errors)} error(s) "
        f"in {elapsed:.1f}s — partial results shown below."
    )

if report.errors:
    with st.expander("🔴 Pipeline errors", expanded=False):
        for err in report.errors:
            st.error(err)


# ===========================================================================
# SECTION 1 — Git Change
# ===========================================================================
st.markdown('<p class="ci-section">📝 Git Change</p>', unsafe_allow_html=True)

ch = data.get("change", {})
c1, c2, c3 = st.columns(3)
c1.metric("Base commit", ch.get("base_commit") or "—")
c2.metric("Target commit", ch.get("target_commit") or "—")
c3.metric("Changed files", len(ch.get("changed_files", [])))

col_files, col_fns = st.columns(2)

with col_files:
    st.markdown("**Changed files**")
    files = ch.get("changed_files", [])
    if files:
        for f in files:
            st.markdown(f"- `{f}`")
    else:
        st.caption("None detected")

with col_fns:
    st.markdown("**Changed functions**")
    fns = ch.get("changed_functions", [])
    if fns:
        for fn in fns:
            st.markdown(f"- `{fn}`")
    else:
        st.caption("None resolved (file-level change only)")

diff_text = ch.get("diff", "")
if diff_text:
    with st.expander("📄 View diff"):
        st.code(diff_text, language="diff")


# ===========================================================================
# SECTION 2 — Impact Analysis
# ===========================================================================
st.markdown('<p class="ci-section">💥 Impact Analysis</p>', unsafe_allow_html=True)

im = data.get("impact", {})
direct   = im.get("direct", [])
indirect = im.get("indirect", [])
changed  = im.get("changed", [])

m1, m2, m3, m4 = st.columns(4)
m1.metric("Seed nodes (changed)", len(changed))
m2.metric("Directly impacted",    len(direct))
m3.metric("Indirectly impacted",  len(indirect))
m4.metric("Evidence edges",       len(im.get("evidence", [])))

col_d, col_i = st.columns(2)

with col_d:
    st.markdown("**Direct impact** — functions that call or import a changed symbol")
    if direct:
        for node in direct:
            st.markdown(
                f'<span class="ci-pill">📌 {node}</span>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("None")

with col_i:
    st.markdown("**Indirect impact** — transitively reachable functions")
    if indirect:
        for node in indirect:
            st.markdown(
                f'<span class="ci-pill ci-pill-indirect">🔗 {node}</span>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("None")

# Uncertainty
uncertainty = im.get("uncertainty", [])
if uncertainty:
    st.info("**Uncertainty notes:** " + " | ".join(uncertainty))

# Evidence table
evidence = im.get("evidence", [])
src_evidence = [
    e for e in evidence
    if not e.get("source", "").replace("\\", "/").startswith("tests/")
    and not e.get("target", "").replace("\\", "/").startswith("tests/")
]
if src_evidence:
    with st.expander(f"🔬 Dependency evidence ({len(src_evidence)} source edges)"):
        import pandas as pd
        rows = [
            {
                "Source": e["source"],
                "→ Target": e["target"],
                "Type": e["edge_type"],
                "File": f"{e.get('file','')}:{e.get('line','')}",
                "Confidence": e.get("confidence", 1.0),
            }
            for e in src_evidence
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# Key paths
paths = im.get("paths", [])
if paths:
    # Filter to source-only paths (no test/ or container-only nodes)
    src_paths = [
        p for p in paths
        if not any(
            n.replace("\\", "/").startswith("tests/") or (":" not in n)
            for n in (p.split(" -> ") if isinstance(p, str) else p)
        )
    ]
    if src_paths:
        with st.expander(f"🗺️ Key dependency paths ({len(src_paths)} chains)"):
            for path in src_paths[:20]:
                chain = path if isinstance(path, str) else " -> ".join(path)
                st.markdown(f"- `{chain}`")
            if len(src_paths) > 20:
                st.caption(f"… and {len(src_paths) - 20} more")


# ===========================================================================
# SECTION 3 — Recommended Tests
# ===========================================================================
st.markdown('<p class="ci-section">🧪 Recommended Tests</p>', unsafe_allow_html=True)

candidates = data.get("recommended_tests", [])
results    = {r["test_name"]: r for r in data.get("test_results", [])}

if not candidates:
    st.caption("No test candidates identified.")
else:
    st.caption(f"{len(candidates)} test(s) recommended by CodeImpact based on dependency analysis.")

    # Build enriched table
    import pandas as pd

    def _status_label(test_name: str) -> str:
        r = results.get(test_name)
        if r is None:
            return "—"
        s = r["status"].upper()
        if s == "PASSED":
            return "✅ PASSED"
        if s == "FAILED":
            return "❌ FAILED"
        if s == "ERROR":
            return "⚠️ ERROR"
        return s

    def _duration(test_name: str) -> str:
        r = results.get(test_name)
        return f"{r['duration']:.3f}s" if r else "—"

    rows = []
    for t in candidates:
        rows.append({
            "Test function": t["test_name"],
            "File": t["test_file"],
            "Covers": ", ".join(t["target_components"]) if t["target_components"] else "—",
            "Reason": t["reason"] or "—",
            "Confidence": f"{t['confidence']:.0%}",
            "Result": _status_label(t["test_name"]),
            "Duration": _duration(t["test_name"]),
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Confidence": st.column_config.TextColumn(width="small"),
            "Duration":   st.column_config.TextColumn(width="small"),
            "Result":     st.column_config.TextColumn(width="medium"),
        },
    )


# ===========================================================================
# SECTION 4 — Test Execution Results
# ===========================================================================
st.markdown('<p class="ci-section">🏃 Test Execution Results</p>', unsafe_allow_html=True)

test_results_list = data.get("test_results", [])
if not test_results_list:
    st.caption("No tests were executed.")
else:
    passed  = [r for r in test_results_list if r["status"].upper() == "PASSED"]
    failed  = [r for r in test_results_list if r["status"].upper() in {"FAILED", "ERROR"}]
    skipped = [r for r in test_results_list if r["status"].upper() == "SKIPPED"]

    cm1, cm2, cm3, cm4 = st.columns(4)
    cm1.metric("Total run", len(test_results_list))
    cm2.metric("✅ Passed",  len(passed),  delta=None)
    cm3.metric("❌ Failed",  len(failed),  delta=None)
    cm4.metric("⏭️ Skipped", len(skipped), delta=None)

    # Per-test cards
    for r in test_results_list:
        status = r["status"].upper()
        if status == "PASSED":
            icon, colour = "✅", "normal"
        elif status in {"FAILED", "ERROR"}:
            icon, colour = "❌", "inverse"
        else:
            icon, colour = "⏭️", "off"

        label = f"{icon} {r['test_name']}  —  {r['duration']:.3f}s"
        with st.expander(label, expanded=(status != "PASSED")):
            st.caption(f"Status: **{status}**  |  Exit code: {r.get('exit_code', '—')}")

            # Show the failing assertion line (pulled from stdout since pytest
            # captures to stdout by default)
            raw = (r.get("stderr") or r.get("stdout") or "").strip()
            if raw:
                # Extract just the short-form failure lines for readability
                relevant = []
                for line in raw.splitlines():
                    ls = line.strip()
                    if ls.startswith("FAILED") or ls.startswith("assert ") or ls.startswith("E "):
                        relevant.append(ls.lstrip("E").strip())
                if relevant:
                    st.code("\n".join(relevant), language="python")
                else:
                    st.code(raw[:600], language="text")


# ===========================================================================
# SECTION 5 — Evaluation Metrics
# ===========================================================================
st.markdown('<p class="ci-section">📊 Evaluation Metrics</p>', unsafe_allow_html=True)

ev = data.get("evaluation", {})
if not ev:
    st.caption("Evaluation not available.")
else:
    e1, e2, e3, e4 = st.columns(4)
    prec = ev.get("precision")
    rec  = ev.get("recall")
    red  = ev.get("test_reduction")
    e1.metric(
        "Precision",
        f"{prec:.0%}" if prec is not None else "—",
        help="Fraction of recommended tests that actually surfaced failures.",
    )
    e2.metric(
        "Recall",
        f"{rec:.0%}" if rec is not None else "—",
        help="Fraction of failing tests that CodeImpact correctly recommended.",
    )
    e3.metric(
        "Targeted tests",
        ev.get("targeted_tests", "—"),
        help="Number of tests CodeImpact selected to run.",
    )
    e4.metric(
        "Test reduction",
        f"{red:.0%}" if red is not None else "—",
        help="Fraction of tests skipped vs. running the full suite.",
    )

    with st.expander("📋 Prediction breakdown"):
        col_tp, col_fp, col_fn = st.columns(3)
        col_tp.markdown("**True positives** ✅\n_(recommended & failed)_")
        for x in ev.get("true_positives", []):
            col_tp.markdown(f"- `{x}`")

        col_fp.markdown("**False positives** 🟡\n_(recommended & passed)_")
        for x in ev.get("false_positives", []):
            col_fp.markdown(f"- `{x}`")

        col_fn.markdown("**False negatives** 🔴\n_(missed failing tests)_")
        fn_list = ev.get("false_negatives", [])
        if fn_list:
            for x in fn_list:
                col_fn.markdown(f"- `{x}`")
        else:
            col_fn.markdown("_None — full recall achieved_ 🎯")


# ===========================================================================
# SECTION 6 — AI Explanation
# ===========================================================================
st.markdown('<p class="ci-section">🤖 AI Explanation</p>', unsafe_allow_html=True)

ax = data.get("ai_explanation", {})
if not ax or not ax.get("summary"):
    st.caption("No AI explanation available.")
else:
    # Summary card
    st.info(ax["summary"])

    col_reas, col_comp = st.columns([3, 2])

    with col_reas:
        with st.expander("🧠 Reasoning steps", expanded=True):
            for step in ax.get("reasoning", []):
                st.markdown(f"- {step}")

    with col_comp:
        with st.expander("🎯 Affected components", expanded=True):
            for comp in ax.get("affected_components", []):
                st.markdown(f"- `{comp}`")

    with st.expander("🧪 Test reasoning"):
        for tr in ax.get("test_reasoning", []):
            st.markdown(f"- {tr}")

    failure_sum = ax.get("failure_summary", [])
    if failure_sum:
        with st.expander("💥 Failure analysis", expanded=True):
            for fs in failure_sum:
                st.error(fs)

    uncertainty = ax.get("uncertainty", [])
    if uncertainty:
        with st.expander("⚠️ Uncertainty & caveats"):
            for u in uncertainty:
                st.warning(u)


# ===========================================================================
# SECTION 7 — Raw JSON (for debugging / CLI parity)
# ===========================================================================
with st.expander("🗂️ Raw report JSON"):
    import json
    st.json(json.dumps(data, indent=2))

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()
st.caption(
    "CodeImpact · AI-powered change impact analysis · "
    "Offline mode active (no IBM credentials required) · "
    f"Report generated at {report.generated_at or '—'}"
)
