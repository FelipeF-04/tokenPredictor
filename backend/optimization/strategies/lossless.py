from . import Strategy


LOSSLESS_STRATEGY = Strategy(
    name="lossless",
    min_relevance=0.05,
    dedup_threshold=0.92,
    description="Remove only semantic duplicates and retain nearly all content.",
    compression_weight=0.1,
)
