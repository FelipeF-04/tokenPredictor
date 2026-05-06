import tiktoken

_ENCODING_NAME = "cl100k_base"
_ENCODING = tiktoken.get_encoding(_ENCODING_NAME)


def count_tokens(text):
    if not text:
        return 0
    return len(_ENCODING.encode(text))
