AI Usage Predictor — local MVP

Backend (Python Flask)

Quick start

1. Create a venv and install deps:

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

2. Run the backend (binds to port 5000):

```bash
python backend/app.py
```

3. Quick analyze test (from repo root):

```bash
python backend/test_backend.py
```

Chrome extension

- Load `extension/` using chrome://extensions → Load unpacked
- Ensure backend is running and reachable at `http://localhost:5000`
- Open ChatGPT-like page, type messages and observe the floating widget.

Notes

- Tokenization uses `cl100k_base` via `tiktoken`.
- Heuristic multipliers: 1.2 (short), 1.5 (default), 1.8 (code).
- Output estimation is skipped for messages below `output_estimate_min_tokens` (default 30).
- Session token state is held in-memory on the backend and in `chrome.storage.local` for the extension; resetting the popup sends a reset to the backend.
