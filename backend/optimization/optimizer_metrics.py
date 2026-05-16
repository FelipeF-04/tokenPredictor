from typing import Dict

from .models import OptimizationMetrics


def build_metrics(original_tokens: int, optimized_tokens: int, validation: Dict[str, float]) -> OptimizationMetrics:
    token_reduction = max(original_tokens - optimized_tokens, 0)
    token_reduction_pct = 0.0
    if original_tokens > 0:
        token_reduction_pct = token_reduction / original_tokens

    return OptimizationMetrics(
        original_tokens=original_tokens,
        optimized_tokens=optimized_tokens,
        token_reduction=token_reduction,
        token_reduction_pct=token_reduction_pct,
        semantic_preservation=validation.get("semantic_preservation", 0.0),
        instruction_preservation=validation.get("instruction_preservation", 0.0),
        reasoning_preservation=validation.get("reasoning_preservation", 0.0),
        code_preservation=validation.get("code_preservation", 0.0),
        hallucination_risk=validation.get("hallucination_risk", 1.0),
        confidence=validation.get("confidence", 0.0),
    )
