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

- Live input token count and predicted output estimate.
- A simple risk color (green/yellow/red) for the current session.
- A session total that updates when you send messages.

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
2. As you type, the content script sends your draft to a local Flask backend.
3. The backend tokenizes input and estimates output with light heuristics.
4. A risk score is computed using configurable context thresholds.
5. When you send a message, the session total is committed.

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

5. Optional backend sanity check:

```bash
python backend/test_backend.py
```

## API endpoints (local)

- `GET /config` - Returns shared config values used by the extension.
- `GET /models` - Returns available model profiles and context windows.
- `GET /session/<id>` - Fetches the durable session state.
- `POST /session/<id>/reset` - Resets a durable session.
- `POST /analyze` - Returns input tokens, predicted output tokens, projected total, and risk.
- `POST /commit` - Adds token deltas to a durable session.
- `POST /optimize` - Runs the optimization pipeline for a session.

## Notes and constraints

- The backend must be running at `http://localhost:5000` for live updates.
- Backend session totals persist locally in SQLite and recover after restarts.
- Output prediction uses heuristics, so treat it as an estimate, not an exact count.
