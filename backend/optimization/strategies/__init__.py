from dataclasses import dataclass
from typing import Dict


@dataclass
class Strategy:
    name: str
    min_relevance: float
    dedup_threshold: float
    description: str
    compression_weight: float


from .lossless import LOSSLESS_STRATEGY
from .balanced import BALANCED_STRATEGY
from .aggressive import AGGRESSIVE_STRATEGY


def get_strategy(name: str) -> Strategy:
    strategies: Dict[str, Strategy] = {
        LOSSLESS_STRATEGY.name: LOSSLESS_STRATEGY,
        BALANCED_STRATEGY.name: BALANCED_STRATEGY,
        AGGRESSIVE_STRATEGY.name: AGGRESSIVE_STRATEGY,
    }
    return strategies.get(name, BALANCED_STRATEGY)


def auto_strategy(budget_pressure: float) -> Strategy:
    if budget_pressure >= 0.85:
        return AGGRESSIVE_STRATEGY
    if budget_pressure >= 0.6:
        return BALANCED_STRATEGY
    return LOSSLESS_STRATEGY
