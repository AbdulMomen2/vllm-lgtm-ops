import tiktoken

class TokenService:
    def __init__(self, model_name: str = "gpt-3.5-turbo"):
        # We use gpt-3.5-turbo encoder as it's very close to Llama/Mistral
        try:
            self.encoder = tiktoken.encoding_for_model(model_name)
        except KeyError:
            self.encoder = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))

token_service = TokenService()