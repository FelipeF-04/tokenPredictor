from . import Strategy


BALANCED_STRATEGY = Strategy(
    name="balanced",
    min_relevance=0.2,
    dedup_threshold=0.9,
    description="Blend relevance trimming with conservative compression.",
    compression_weight=0.35,
)
