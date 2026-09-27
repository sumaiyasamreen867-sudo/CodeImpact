from src.codeimpact.ai_reasoner import AIReasoner
from src.codeimpact.schemas import (
    ChangeInfo,
    DependencyEvidence,
    ImpactResult,
    TestCandidate,
)

change = ChangeInfo(
    changed_files=["pricing.py"],
    changed_functions=["calculate_discount", "final_price"],
    diff="- rate=0.10\n+ rate=0.20",
    base_commit="HEAD~1",
    target_commit="HEAD",
)

evidence = [
    DependencyEvidence(
        source="pricing.calculate_discount",
        target="pricing.final_price",
        edge_type="calls",
        file="pricing.py",
        line=8,
        evidence="final_price calls calculate_discount",
        confidence=1.0,
    ),
    DependencyEvidence(
        source="pricing.final_price",
        target="checkout.calculate_total",
        edge_type="calls",
        file="checkout.py",
        line=12,
        evidence="calculate_total calls final_price",
        confidence=1.0,
    ),
]

impact = ImpactResult(
    changed=["pricing.calculate_discount", "pricing.final_price"],
    direct=["pricing.final_price", "checkout.calculate_total"],
    indirect=["invoice.generate_invoice"],
    paths=[
        "pricing.calculate_discount -> pricing.final_price -> checkout.calculate_total",
        "checkout.calculate_total -> invoice.generate_invoice",
    ],
    evidence=evidence,
    uncertainty=[],
)

tests = [
    TestCandidate(
        test_name="test_calculate_discount",
        test_file="tests/test_pricing.py",
        target_components=["pricing.calculate_discount"],
        reason="Directly tests the changed discount behavior",
        confidence=1.0,
    ),
    TestCandidate(
        test_name="test_checkout_total",
        test_file="tests/test_checkout.py",
        target_components=["checkout.calculate_total"],
        reason="Checkout depends on the changed pricing calculation",
        confidence=0.9,
    ),
    TestCandidate(
        test_name="test_invoice",
        test_file="tests/test_invoice.py",
        target_components=["invoice.generate_invoice"],
        reason="Invoice depends indirectly on checkout totals",
        confidence=0.8,
    ),
]

reasoner = AIReasoner(use_ai=False)

result = reasoner.explain_impact(
    change=change,
    impact=impact,
    tests=tests,
)

print("\n=== AI REASONER OFFLINE TEST ===\n")
print("SUMMARY:")
print(result.summary)

print("\nREASONING:")
print(result.reasoning)

print("\nAFFECTED COMPONENTS:")
print(result.affected_components)

print("\nTEST REASONING:")
print(result.test_reasoning)

print("\nUNCERTAINTY:")
print(result.uncertainty)

print("\n=== TEST PASSED ===")