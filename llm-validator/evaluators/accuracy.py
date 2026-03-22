#!/usr/bin/env python3
"""Accuracy evaluator; checks response content against expected values."""

from typing import Dict, Any
from schemas.loader import AccuracyEvaluator as AccuracyConfig


class AccuracyEvaluator:
    def evaluate(self, response: str, config: AccuracyConfig) -> Dict[str, Any]:
        response_lower = response.lower()
        reasons = []
        passed = True

        if config.contains:
            for term in config.contains:
                if term.lower() not in response_lower:
                    passed = False
                    reasons.append(f"missing expected term: '{term}'")

        if config.not_contains:
            for term in config.not_contains:
                if term.lower() in response_lower:
                    passed = False
                    reasons.append(f"found forbidden term: '{term}'")

        if config.exact_match is not None:
            if response.strip() != config.exact_match.strip():
                passed = False
                reasons.append(f"exact match failed")

        if config.min_length is not None and len(response) < config.min_length:
            passed = False
            reasons.append(f"response too short ({len(response)} < {config.min_length})")

        if config.max_length is not None and len(response) > config.max_length:
            passed = False
            reasons.append(f"response too long ({len(response)} > {config.max_length})")

        reason = "; ".join(reasons) if reasons else "all accuracy checks passed"
        return {"evaluator": "accuracy", "passed": passed, "reason": reason}
  if __name__ == "__main__":    
