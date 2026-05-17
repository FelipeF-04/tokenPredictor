# AI Usage Predictor

AI Usage Predictor estimates token usage before you send a message in a ChatGPT-style UI and warns you when a conversation is approaching a model's context limit. It is useful when you want to avoid surprises like truncated responses or lost context, while keeping everything local.

## What it solves

- Gives a live preview of input tokens, predicted output tokens, and projected total.
- Shows a simple risk indicator (green/yellow/red) for how close you are to the context window.
- Helps you decide when to shorten a prompt, split a task, or reset a session.

## How it works (end to end)

1. A Chrome extension injects a floating widget into ChatGPT-style pages.
2. As you type, the content script sends your current message to a local Flask backend.
3. The backend tokenizes the input and predicts output tokens using small heuristics.
4. A risk score is calculated using configured thresholds for the context window.
5. The widget updates live, and the popup shows session totals.
6. When you send a message, the extension commits the projected total to keep the session count accurate.

## Architecture

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

## Quick start (Windows)

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

## Configuration

- Backend thresholds and window size live in [shared/config.json](shared/config.json).
- Popup thresholds are currently defined in [extension/popup.js](extension/popup.js). Keep these aligned with the shared config when you change window sizes or risk levels.

## API endpoints (local)

- `POST /analyze` - Returns input tokens, predicted output tokens, projected total, and risk.
- `POST /commit` - Adds the projected total to the session counter.
- `POST /reset` - Resets the backend session total.

## Notes and constraints

- The backend must be running at `http://localhost:5000` for live updates.
- Backend session totals reset when the server restarts.
- Output prediction uses heuristics, so treat it as an estimate, not an exact count.

## Why this is useful

- Prevents overlong prompts that blow past context limits.
- Makes token usage visible in a workflow that normally hides it.
- Keeps everything local so your prompts are not sent to third-party services beyond the page you are already using.
