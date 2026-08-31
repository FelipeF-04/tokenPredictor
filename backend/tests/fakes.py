class FakeEncoding:
    def encode(self, text):
        return text.split()


class FakeEmbeddingProvider:
    name = "fake"
    model_name = "fake-offline-embedding"
    deterministic = True

    def embed_texts(self, texts):
        vectors = []
        for text in texts:
            checksum = sum(ord(character) for character in text)
            vectors.append(
                [
                    (checksum % 997) / 997,
                    (len(text) % 127) / 127,
                    1.0,
                ]
            )
        return vectors
