#!/usr/bin/env python3
"""Consistency evaluator — measures variance across multiple runs."""

from typing import Dict, Any, List
from schemas.loader import ConsistencyEvaluator as ConsistencyConfig


def _jaccard_similarity(a: str, b: str) -> float:
    """Simple word-level Jaccard similarity between two strings."""
    set_a = set(a.lower().split())
    set_b = set(b.lower().split())
    if not set_a and not set_b:
        return 1.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def _mean_pairwise_similarity(responses: List[str]) -> float:
    """Average pairwise Jaccard similarity across all response pairs."""
    if len(responses) < 2:
        return 1.0
    scores = []
    for i in range(len(responses)):
        for j in range(i + 1, len(responses)):
            scores.append(_jaccard_similarity(responses[i], responses[j]))
    return sum(scores) / len(scores)


class ConsistencyEvaluator:
    def evaluate(self, responses: List[str], config: ConsistencyConfig) -> Dict[str, Any]:
        if not responses:
            return {"evaluator": "consistency", "passed": False, "reason": "no responses collected"}

        similarity = _mean_pairwise_similarity(responses)
        variance = 1.0 - similarity  # higher variance = less consistent

        passed = variance <= config.max_variance
        reason = (
            f"variance={variance:.3f} (threshold={config.max_variance}, "
            f"similarity={similarity:.3f}, runs={len(responses)})"
        )

        return {"evaluator": "consistency", "passed": passed, "reason": reason}
 if __name__ == "__main__":     
