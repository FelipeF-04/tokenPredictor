# AI Usage Predictor — Project Description

## What this project solves

AI Usage Predictor helps you estimate token usage before you send a message in a ChatGPT-style UI and shows a simple risk indicator for how close a conversation is to a model's context window. It reduces surprises like truncated responses or sudden context loss by giving you a quick, local preview of input tokens, predicted output tokens, and a projected total.

## How it was built

- **Backend**: A lightweight Python Flask service counts tokens and calculates risk. It uses `tiktoken` with the `cl100k_base` encoding to approximate model tokenization.
- **Prediction logic**: A small heuristic model applies multipliers to estimate output tokens based on message length and whether the message looks like code.
- **Chrome extension**: A Manifest V3 extension injects a floating widget into ChatGPT-style pages and provides a popup for session totals and reset.
- **State**: Session totals are stored in memory on the backend and in `chrome.storage.local` for the extension so the popup stays updated.
- **Config**: Shared thresholds and token window live in [shared/config.json](shared/config.json) for backend risk calculations.

## How it works (end to end)

1. **Page detection**: The content script runs on `chat.openai.com` and `chatgpt.com` and looks for visible text inputs or contenteditable fields.
2. **Live analysis**: As you type, the script debounces input and sends the current message to the backend `/analyze` endpoint.
3. **Token counting**: The backend counts input tokens using `tiktoken` and predicts output tokens using heuristic multipliers.
4. **Risk scoring**: The backend combines the current session total with the projected total and maps it to `green`, `yellow`, or `red` based on the configured thresholds.
5. **UI feedback**: The floating widget updates near the input with input, output, total, and risk labels.
6. **Commit on send**: When you press Enter (send), the extension commits the projected total to both local storage and the backend `/commit` endpoint so the session total increments.
7. **Popup summary**: The popup reads the session total from `chrome.storage.local` and renders a meter with the same risk thresholds.

## Key components

- Backend Flask service: [backend/app.py](backend/app.py)
- Tokenization: [backend/tokenizer.py](backend/tokenizer.py)
- Prediction + risk logic: [backend/predictor.py](backend/predictor.py)
- Content script widget: [extension/content.js](extension/content.js)
- Popup UI + reset: [extension/popup.html](extension/popup.html), [extension/popup.js](extension/popup.js)
- Config: [shared/config.json](shared/config.json)

## Build and run (local)

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. Start the backend:

```bash
python backend/app.py
```

3. Load the extension:

- Open `chrome://extensions`
- Enable Developer mode
- Click **Load unpacked** and select the [extension/](extension/) folder

4. Open ChatGPT and type a message. You should see a small floating widget with token estimates.

5. Optional backend sanity check:

```bash
python backend/test_backend.py
```

## Notes and constraints

- The backend listens on `http://localhost:5000` and must be running for the widget to update.
- Backend session totals reset when the server restarts; the extension can also reset totals from the popup.
- The popup uses thresholds defined in [extension/popup.js](extension/popup.js). Keep them in sync with [shared/config.json](shared/config.json) if you change the window or thresholds.
