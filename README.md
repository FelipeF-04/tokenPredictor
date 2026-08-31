# AI Usage Predictor

AI Usage Predictor is a small, local companion for ChatGPT-style UIs. It estimates token usage before you hit send, so you can avoid clipped replies, surprise context loss, or guessing how big a prompt really is.

## Purpose

Most chat UIs hide token counts. This project makes them visible in real time and keeps the decision in your hands: shorten a prompt, split a task, or reset a session before you run into limits.

## Real-world use cases

- You are writing a long prompt and want to know if it is getting too large before you send it.
- You are building a multi-step conversation and want to avoid losing context halfway through.
- You are sending code or technical details and want a rough estimate of how expensive the message is.
- You are managing multiple prompts in one session and want a simple way to stay under the context window.

## What you get

- Live input token count, predicted output estimate, projected session total, and available context.
- A simple risk color (green/yellow/red) for the current session.
- A session total that updates when you send messages.
- Optional context packing with a preview that you explicitly choose whether to apply.

## Two operating modes

### Live estimate

The extension automatically calls `POST /analyze` after a short typing pause. This path is fast and lightweight: it counts tokens, estimates output, and calculates context risk without loading sentence-transformer embeddings. It remains available even when the optional optimization model is missing.

### Context optimization

Select **Optimize context** when you want the richer packing pipeline. Only that explicit action calls `POST /optimize`; ordinary typing never does. Optimization may initialize the configured local sentence-transformers model, so its first run can take longer and the model must already be available when working offline. The packed prompt is shown as a preview and is never placed into the draft unless you select **Apply optimized prompt**.

## What it looks like

This is a lightweight overlay that appears near the message box and gives you a quick read before you send:

```text
-------------------------------------------------
AI Usage Predictor                                 
-------------------------------------------------
Input tokens:        84                            
Predicted output:    132                           
Projected total:     216                           
Risk:                yellow                       
-------------------------------------------------
```

The popup gives you the same idea at a session level, so you can see how the conversation is trending over time.

## How it works (end to end)

1. A Chrome extension injects a small floating widget near the message box.
2. As you type, the content script sends your draft to the local `/analyze` endpoint after a 300 ms debounce.
3. The backend tokenizes input, estimates output, and calculates available context with light heuristics.
4. A risk score is computed using the selected model profile and configurable thresholds.
5. When you send a message, the session total is committed.
6. If requested, `/optimize` runs the separate embedding-backed context packing flow.

## Built with

- Backend: Python Flask API for token counting and risk scoring.
- Tokenization: `tiktoken` with `cl100k_base` encoding.
- Chrome extension: content script + popup UI for live feedback.
- Shared config: thresholds and window size in [shared/config.json](shared/config.json).

## Project layout

- [backend/app.py](backend/app.py) - Flask API endpoints.
- [backend/tokenizer.py](backend/tokenizer.py) - Token counting via `tiktoken`.
- [backend/predictor.py](backend/predictor.py) - Output prediction + risk rules.
- [extension/content.js](extension/content.js) - Floating widget and page hooks.
- [extension/content_controller.js](extension/content_controller.js) - Debounced analysis and explicit optimization control.
- [extension/popup.html](extension/popup.html) - Popup layout.
- [extension/popup.js](extension/popup.js) - Popup logic + reset action.
- [shared/config.json](shared/config.json) - Token window and thresholds.

## Configuration

- Shared config lives in [shared/config.json](shared/config.json).
- The backend serves config via `GET /config` and the extension consumes it at startup.
- If the backend is unavailable, the extension falls back to its bundled copy at [extension/shared/config.json](extension/shared/config.json).
- Model profile defaults, risk thresholds, and token window are sourced from config to keep backend + UI synchronized.

## Run it locally (optional)

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. Run the backend (listens on port 5000):

```bash
python backend/app.py
```

3. Load the extension:

- Open `chrome://extensions`
- Enable Developer mode
- Click Load unpacked and select the [extension/](extension/) folder

4. Open ChatGPT or a compatible page and type a message. A floating widget should appear.

5. Run the complete test suite:

```bash
python run_tests.py
```

That single command runs the complete Python backend and JavaScript extension test suite. Node.js must be installed for the extension tests.

## API endpoints (local)

- `GET /config` - Returns shared config values used by the extension.
- `GET /models` - Returns available model profiles and context windows.
- `GET /session/<id>` - Fetches the durable session state.
- `POST /session/<id>/reset` - Resets a durable session.
- `POST /analyze` - Returns input tokens, predicted output tokens, projected total, risk, context window, reserved output, available context, and utilization.
- `POST /commit` - Adds token deltas to a durable session.
- `POST /optimize` - Runs the optimization pipeline for a session.

## Notes and constraints

- The backend must be running at `http://localhost:5000` for live updates.
- Backend session totals persist locally in SQLite and recover after restarts.
- Output prediction uses heuristics, so treat it as an estimate, not an exact count.
- Tokenizer encoding initialization is lazy. If `cl100k_base` is not already available and cannot be fetched, the backend returns an intentional service error instead of failing during import. Tests inject a fake tokenizer and never require network access.
- SQLite files, Python/Node caches, virtual environments, and downloaded model artifacts are ignored and should remain local.
