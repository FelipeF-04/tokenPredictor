from typing import Dict

from .models import ModelProfile, TokenBudget


def compute_budget(profile: ModelProfile, overrides: Dict) -> TokenBudget:
    output_budget = int(overrides.get("max_output_tokens", profile.max_output_tokens))
    total_available = max(profile.context_window - output_budget, 0)

    system_budget = int(total_available * profile.system_ratio)
    instruction_budget = int(total_available * profile.instruction_ratio)
    memory_budget = int(total_available * profile.memory_ratio)
    retrieval_budget = int(total_available * profile.retrieval_ratio)

    remaining = total_available - (system_budget + instruction_budget + memory_budget + retrieval_budget)
    if remaining < 0:
        overflow = abs(remaining)
        memory_budget = max(memory_budget - overflow, 0)
        remaining = total_available - (system_budget + instruction_budget + memory_budget + retrieval_budget)
    conversation_budget = max(remaining, 0)

    return TokenBudget(
        total_available=total_available,
        system_budget=system_budget,
        instruction_budget=instruction_budget,
        memory_budget=memory_budget,
        retrieval_budget=retrieval_budget,
        output_budget=output_budget,
        conversation_budget=conversation_budget,
    )
