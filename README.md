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
- An actual session total backed by a durable, idempotent conversation ledger.
- Optional context packing with a preview that you explicitly choose whether to apply.

## Two operating modes

### Live estimate

The extension automatically calls `POST /analyze` after a short typing pause. This path is fast and lightweight: it counts tokens, estimates output, and calculates context risk without loading sentence-transformer embeddings. It remains available even when the optional optimization model is missing.

### Context optimization

Select **Optimize context** when you want the richer packing pipeline. Only that explicit action calls `POST /optimize`; ordinary typing never does. Optimization may initialize the configured local sentence-transformers model, so its first run can take longer and the model must already be available when working offline. The packed prompt is shown as a preview and is never placed into the draft unless you select **Apply optimized prompt**.

## Estimated versus actual usage

The widget deliberately shows two different views of the conversation:

- **Live draft estimate** is calculated before sending. It combines the current committed session total with the draft input and predicted reply size. The reply portion is a heuristic and can be higher or lower than the answer ChatGPT eventually produces.
- **Actual session total** is calculated after messages appear in the conversation. The backend tokenizes each user turn and each stable, completed assistant turn, records it in SQLite, and returns the corrected total. Assistant edits or regenerations update the existing ledger entry instead of adding the message again.

Ledger synchronization is asynchronous and never blocks typing or sending. The widget and popup show **Session synced**, **Waiting for response to finish**, or a queued-event count. If the local backend is unavailable, events remain in Chrome local storage and retry every 15 seconds, when connectivity returns, and after a page reload.

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
5. DOM message identifiers, roles, and content are sent to `/events`; the backend performs authoritative token counting and idempotently updates the SQLite ledger.
6. Assistant turns are recorded only after streaming indicators disappear and their content remains unchanged for 2.5 seconds.
7. If requested, `/optimize` runs the separate embedding-backed context packing flow.

## Built with

- Backend: Python Flask API for token counting and risk scoring.
- Tokenization: `tiktoken` with `cl100k_base` encoding.
- Chrome extension: content script + popup UI for live feedback.
- Shared config: thresholds and window size in [shared/config.json](shared/config.json).

## Project layout

- [backend/app.py](backend/app.py) - Flask API endpoints.
- [backend/tokenizer.py](backend/tokenizer.py) - Token counting via `tiktoken`.
- [backend/storage/session_store.py](backend/storage/session_store.py) - Durable sessions and the idempotent conversation ledger.
- [backend/predictor.py](backend/predictor.py) - Output prediction + risk rules.
- [backend/tests/](backend/tests/) - Offline backend unit and API contract tests.
- [extension/content.js](extension/content.js) - Floating widget and page hooks.
- [extension/content_controller.js](extension/content_controller.js) - Debounced analysis and explicit optimization control.
- [extension/conversation_tracker.js](extension/conversation_tracker.js) - Stable-response detection, local queueing, and ledger retries.
- [extension/popup.html](extension/popup.html) - Popup layout.
- [extension/popup.js](extension/popup.js) - Popup logic + reset action.
- [extension/tests/](extension/tests/) - Node tests and ChatGPT DOM compatibility fixtures.
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

2. Run the backend in local development mode (listens on `127.0.0.1:5000`):

PowerShell:

```bash
$env:AI_USAGE_ENV = "development"
python backend/app.py
```

macOS/Linux:

```bash
AI_USAGE_ENV=development python backend/app.py
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

The runner sets Hugging Face and Transformers offline flags, uses fake tokenization and embeddings, checks every extension JavaScript file with `node --check`, and validates the MV3 manifest. It does not download tokenizer encodings or embedding models.

## Continuous integration

[.github/workflows/ci.yml](.github/workflows/ci.yml) runs for every pull request and every push to `main`. CI tests Python 3.11 and 3.13 with Node.js 22, caches pip downloads, installs the declared Python dependencies, and runs:

- The complete offline suite through `python run_tests.py`.
- The extension Node tests as an explicit guardrail.
- Syntax checks for every JavaScript file under `extension/`.
- JSON and Manifest V3 validation for `extension/manifest.json`.

Offline environment flags make accidental sentence-transformers model access fail instead of downloading a model. API and optimization tests inject fake encoders and embedding providers, so CI does not need a populated local model cache.

## Updating ChatGPT DOM compatibility

Selector behavior is captured in small, non-sensitive HTML files under [extension/tests/fixtures/](extension/tests/fixtures/). When ChatGPT changes its composer or conversation markup:

1. Add or update a minimal fixture containing only the relevant input, send button, and message-role structure. Do not copy real conversation content or account data.
2. Update [extension/dom/selectors.js](extension/dom/selectors.js) with the narrowest stable selector, preferring `data-*` or accessible attributes over generated classes.
3. Update [extension/tests/dom_fixtures.test.js](extension/tests/dom_fixtures.test.js) if the expected structure or extraction behavior changed.
4. Update or add tracker scenarios in [extension/tests/conversation_tracker.test.js](extension/tests/conversation_tracker.test.js), including stable turn identifiers and streaming markers.
5. Run `python run_tests.py`, then manually load the unpacked extension and verify typing, sending, response completion, regeneration, optimization, and applying a packed prompt on each supported ChatGPT host.

The fixture tests deliberately use a small dependency-free DOM implementation rather than browser automation. This keeps CI fast, but visual layout and real-site event behavior still require that final manual browser check.

## Development and production startup

Running `python backend/app.py` with no environment variables uses production-safe defaults: `127.0.0.1:5000`, debug mode disabled, and no cross-origin browser origins allowed unless explicitly configured. For an installed extension, set a comma-separated exact allowlist:

```text
AI_USAGE_ALLOWED_ORIGINS=chrome-extension://<extension-id>
```

`AI_USAGE_ENV=development` allows loopback web origins and syntactically valid unpacked Chrome extension origins. Debug mode remains off unless `AI_USAGE_DEBUG=1` is also set. `AI_USAGE_PORT` changes the port; `AI_USAGE_HOST` can change the bind address, but exposing the backend beyond loopback is not recommended.

The server caps request bodies at 1 MiB and both `/analyze` messages and `/events` text at 100,000 characters. Operational error logs contain structured status, route, method, and exception type fields but never request payloads.

## API endpoints (local)

- `GET /config` - Returns shared config values used by the extension.
- `GET /models` - Returns available model profiles and context windows.
- `GET /session/<id>` - Fetches the durable session state.
- `POST /session/<id>/reset` - Resets a durable session.
- `POST /analyze` - Returns input tokens, predicted output tokens, projected total, risk, context window, reserved output, available context, and utilization.
- `POST /events` - Records or updates one user/assistant message, counts its tokens in the backend, and returns its ledger status plus the corrected session/context/risk data.
- `POST /commit` - Adds token deltas to a durable session.
- `POST /optimize` - Runs the optimization pipeline for a session.

## Notes and constraints

- The backend must be running at `http://localhost:5000` for live updates.
- Backend session totals persist locally in SQLite and recover after restarts.
- Output prediction uses heuristics, so treat it as an estimate, not an exact count.
- Duplicate prevention uses the SQLite primary key `(session_id, event_id)`. Identical content is returned as `unchanged`; changed content under the same event ID replaces its previous token count and adjusts the total by the difference.
- Assistant completion detection is DOM-based. The extension honors known streaming/stop markers, then requires 2.5 seconds of stable content. A quiet streaming pause or a ChatGPT DOM change can cause an early or delayed sync; a later observation of the same event corrects the ledger rather than double-counting it.
- Stable ChatGPT turn IDs are preferred over generated CSS classes. If the page exposes no stable turn/message ID, the fallback role/index identity is less reliable across structural DOM changes. Multiple hidden regeneration variants in the DOM may also require selector/fixture updates.
- Tokenizer encoding initialization is lazy. If `cl100k_base` is not already available and cannot be fetched, the backend returns an intentional service error instead of failing during import. Tests inject a fake tokenizer and never require network access.
- SQLite files, Python/Node caches, virtual environments, and downloaded model artifacts are ignored and should remain local.
- The backend has no authentication or TLS. Its security model assumes a trusted local machine, a loopback bind, and an explicitly restricted extension-origin allowlist.
- CORS is a browser boundary, not authentication. Local processes can still call the loopback API, and the SQLite session database is not encrypted.
