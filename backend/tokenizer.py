import threading
from typing import Callable, Optional, Protocol

import tiktoken


class Encoding(Protocol):
    def encode(self, text: str): ...


class TokenizerUnavailableError(RuntimeError):
    """Raised when the configured tokenizer cannot be loaded locally."""


_ENCODING_NAME = "cl100k_base"
_encoding: Optional[Encoding] = None
_encoding_loader: Callable[[str], Encoding] = tiktoken.get_encoding
_encoding_lock = threading.Lock()


def get_encoding() -> Encoding:
    """Load and cache the encoding on first use, never during module import."""
    global _encoding
    if _encoding is not None:
        return _encoding

    with _encoding_lock:
        if _encoding is None:
            try:
                _encoding = _encoding_loader(_ENCODING_NAME)
            except Exception as exc:
                raise TokenizerUnavailableError(
                    f"Tokenizer encoding '{_ENCODING_NAME}' is unavailable. "
                    "Install or pre-cache it while online, or inject an encoding for tests."
                ) from exc
    return _encoding


def reset_encoding_cache(loader: Optional[Callable[[str], Encoding]] = None) -> None:
    """Clear the cache and optionally inject the loader used by the next token count."""
    global _encoding, _encoding_loader
    with _encoding_lock:
        _encoding = None
        _encoding_loader = loader if loader is not None else tiktoken.get_encoding


def set_encoding(encoding: Encoding) -> None:
    """Inject an already-created encoding, primarily for deterministic offline tests."""
    if encoding is None:
        raise ValueError("encoding is required")
    global _encoding
    with _encoding_lock:
        _encoding = encoding


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(get_encoding().encode(text))
