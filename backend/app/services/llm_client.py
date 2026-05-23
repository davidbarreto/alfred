from starlette.concurrency import run_in_threadpool
import ollama


class OllamaClient:
    def __init__(self, base_url: str):
        self.client = ollama.Client(host=base_url)

    async def generate(self, model: str, prompt: str) -> str:
        result = await run_in_threadpool(
            self.client.generate,
            model=model,
            prompt=prompt,
            options={"max_tokens": 256},
        )
        return getattr(result, "completion", str(result))
