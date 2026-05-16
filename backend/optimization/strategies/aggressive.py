from . import Strategy


AGGRESSIVE_STRATEGY = Strategy(
    name="aggressive",
    min_relevance=0.35,
    dedup_threshold=0.88,
    description="Maximize token reduction with aggressive relevance filtering.",
    compression_weight=0.6,
)
