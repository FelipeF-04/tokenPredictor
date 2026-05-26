# AI Usage Predictor — Project Description (Detailed)

## One-sentence summary

AI Usage Predictor is a local Chrome extension plus Flask backend that estimates token usage and can compress chat history into a packed prompt, so you can stay inside an LLM context window before you hit send.

## What problem this solves

Chat UIs rarely show token usage. That hides cost and risk: replies can be truncated, and older context can silently drop. This project makes those limits visible and provides an optional optimization step that trims or compresses previous messages to fit the window.

## Core features

- Real-time token estimation and risk color (green/yellow/red) for a draft message.
- Session-level token tracking that increments when you send a message.
- Context optimization that selects the most relevant chunks from recent conversation and returns a packed prompt with confidence metrics.
- Local-only processing: your message text goes to a local Flask server, not a third party.

## Architecture at a glance

Browser page (ChatGPT UI)
	-> content script (floating widget, message capture)
	-> background service worker (HTTP bridge)
	-> local Flask API (tokenization + optimization)
	-> response back to the widget + popup

## End-to-end flows

### 1) Live optimization while typing

1. The content script finds the active input field and collects the latest conversation messages from the DOM (up to 16 messages by default).
2. It debounces input and sends a payload to `POST /optimize`.
3. The backend optimization pipeline:
	 - Chunks messages by semantic boundaries and token size.
	 - Embeds chunks and extracts repeated instructions.
	 - Scores chunks by relevance to the inferred query.
	 - Allocates a token budget based on the selected model profile.
	 - Deduplicates, assigns memory tiers, and selects chunks that fit the budget.
	 - Renders a packed prompt and computes preservation/confidence metrics.
4. The widget shows original vs. optimized tokens, savings, kept chunks, and a preview.

### 2) Commit on send

1. When Enter or the send button is pressed, the extension commits the token delta.
2. The delta is stored in `chrome.storage.local` and sent to `POST /commit` so the backend session total stays in sync.

### 3) Simple estimate API (optional)

`POST /analyze` is a lightweight endpoint that returns input token count, predicted output tokens, projected total, and risk level.

## Optimization pipeline details

The optimization pipeline is implemented in the backend optimization package and returns a structured response:

- **Chunking**: Splits messages into chunks with overlap so meaning is preserved.
- **Embedding + retrieval**: Uses sentence-transformers (default `bge-small-en`) to compute chunk relevance; supports embedding, lexical, or hybrid scoring.
- **Instruction extraction**: Detects repeated instructions across chunks and budgets them separately.
- **Budgeting**: Uses model profiles (context window, output budget, memory ratios) to compute how much conversation can fit.
- **Strategies**:
	- `lossless`: remove near-duplicates only.
	- `balanced`: trim low relevance with moderate compression.
	- `aggressive`: maximize token reduction.
- **Validation + metrics**: Estimates semantic and instruction preservation plus a confidence score.

## Data and state

- Backend session tokens are stored in memory only and reset when the server restarts.
- Extension session tokens are stored in `chrome.storage.local` for the popup UI.
- A randomly generated session id is used for optimization requests to keep per-session trace data consistent.

## Configuration and defaults

Shared backend config lives in `shared/config.json`:

- `token_window`: default 8000
- `risk_thresholds.yellow`: 0.6
- `risk_thresholds.red`: 0.85
- `output_estimate_min_tokens`: 30

Popup thresholds are currently hard-coded in the extension and should be kept in sync with shared config.

Model profiles used by the optimizer are defined in the backend and include:

- `gpt-4o-mini`, `gpt-4.1`, `gpt-5`
- `local-8k`, `local-16k`

## Supported sites

- https://chat.openai.com/*
- https://chatgpt.com/*

## Local API (summary)

### `POST /analyze`

Request:

```json
{ "message": "text" }
```

Response:

```json
{
	"input_tokens": 120,
	"predicted_output_tokens": 180,
	"projected_total_tokens": 300,
	"risk_level": "yellow"
}
```

### `POST /commit`

Request:

```json
{ "delta_tokens": 300 }
```

or

```json
{ "reset": true }
```

Response:

```json
{ "session_tokens": 1200 }
```

### `POST /optimize`

Request (core fields):

```json
{
	"session_id": "uuid",
	"model_profile": "gpt-4o-mini",
	"strategy": "auto",
	"retrieval_mode": "embedding",
	"embedding_provider": "sentence-transformers",
	"embedding_model": "bge-small-en",
	"messages": [{ "role": "user", "content": "..." }]
}
```

Response (high level):

```json
{
	"optimized": {
		"token_counts": { "original": 1200, "optimized": 640 },
		"rendered_prompt": ["USER: ...", "ASSISTANT: ..."]
	},
	"metrics": { "confidence": 0.84 },
	"stats": { "total_chunks": 18, "kept_chunks": 10 }
}
```

## Dependencies

- flask
- tiktoken
- sentence-transformers
- numpy

## Known constraints

- Output prediction is heuristic and meant to be an estimate.
- The backend must be running at `http://localhost:5000` for live updates.
- The DOM selectors depend on current ChatGPT page structure and may require updates.
- CORS is open to all origins for local use.
