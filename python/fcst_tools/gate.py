# SPDX-License-Identifier: MIT OR Apache-2.0
"""Exact collected coverage, shared by local verification and CI aggregation."""
def evaluate(expected: list[str], records: list[dict]) -> dict:
    ids = [row["id"] for row in records]
    problems = []
    if not expected or len(expected) != len(set(expected)):
        problems.append("invalid_expected_coverage")
    if len(ids) != len(set(ids)):
        problems.append("duplicate_results")
    if set(expected) != set(ids):
        problems.append("missing_or_unexpected_coverage")
    if any(row.get("status") != "passed" for row in records):
        problems.append("required_case_not_passed")
    return {"status": "failed" if problems else "passed", "problems": problems,
            "expected": len(expected), "collected": len(records)}
