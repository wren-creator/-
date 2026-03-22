#!/usr/bin/env python3
"""Accuracy evaluator; checks response content against expected values."""

from typing import Dict, Any
# from schemas.loader import AccuracyEvaluator as AccuracyConfig

class AccuracyEvaluator:
    def evaluate(self, response: str, config: Any) -> Dict[str, Any]:
        response_lower = response.lower()
        reasons = []
        passed = True

        # Check for required terms
        if getattr(config, 'contains', None):
            for term in config.contains:
                if term.lower() not in response_lower:
                    passed = False
                    reasons.append(f"missing expected term: '{term}'")

        # Check for forbidden terms
        if getattr(config, 'not_contains', None):
            for term in config.not_contains:
                if term.lower() in response_lower:
                    passed = False
                    reasons.append(f"found forbidden term: '{term}'")

        # Check for exact string match
        exact = getattr(config, 'exact_match', None)
        if exact is not None:
            if response.strip() != exact.strip():
                passed = False
                reasons.append("exact match failed")

        # Length Constraints
        min_len = getattr(config, 'min_length', None)
        if min_len is not None and len(response) < min_len:
            passed = False
            reasons.append(f"response too short ({len(response)} < {min_len})")

        max_len = getattr(config, 'max_length', None)
        if max_len is not None and len(response) > max_len:
            passed = False
            reasons.append(f"response too long ({len(response)} > {max_len})")

        reason = "; ".join(reasons) if reasons else "all accuracy checks passed"
        return {"evaluator": "accuracy", "passed": passed, "reason": reason}

# Corrected: No indentation for the entry point
if __name__ == "__main__":
    evaluator = AccuracyEvaluator()
    
    # Simple test mock
    class MockConfig:
        contains = ["Linux", "Mainframe"]
        not_contains = ["Windows"]
        exact_match = None
        min_length = 10
        max_length = 200

    sample_text = "The Mainframe runs Linux effectively."
    print(evaluator.evaluate(sample_text, MockConfig()))
