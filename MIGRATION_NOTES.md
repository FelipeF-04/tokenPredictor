# Migration Notes (May 2026)

## Summary

This release introduces unified configuration delivery, durable session storage, hardened DOM integration, incremental optimization, and model profile selection in the extension.

## Config synchronization

- Shared config remains in shared/config.json.
- Backend now serves config via GET /config.
- Extension loads config from the backend and falls back to extension/shared/config.json when offline.
- Config includes version and defaults for risk thresholds, token window, and model profile.

## Durable sessions

- Backend session tokens are persisted in SQLite (backend/storage/ai_usage.db by default).
- New endpoints:
  - GET /session/<id>
  - POST /session/<id>/reset
- /commit now accepts session_id and model_profile (still supports reset).
- Extension stores per-conversation session ids and syncs totals with the backend.

## Model profiles

- Backend exposes model profiles via GET /models.
- Popup allows selecting model profile; selection is persisted in extension storage.
- Floating widget displays the active model.

## DOM hardening

- DOM selectors centralized in extension/dom/.
- Mutation observers include backoff and health checks.
- Compatibility detection for chat.openai.com and chatgpt.com.

## Optimization pipeline

- Incremental chunking reuses cached message chunks when content is unchanged.
- Embeddings are cached with session-aware keys and LRU eviction.
- Profiling metrics added (latency, cache hit rates, reuse percentages).

## Backwards compatibility

- Existing /analyze, /commit, /optimize endpoints remain.
- Extension continues to function offline but will show stale values until backend is available.
