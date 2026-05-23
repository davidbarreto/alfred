from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import openai
from anthropic import Anthropic, HUMAN_PROMPT, AI_PROMPT

from app.core.config import settings
from app.services.llm_client import OllamaClient

router = APIRouter(prefix="/llm", tags=["llm"])

class LLMRequest(BaseModel):
    prompt: str
    model: str = "llama2"

class LLMResponse(BaseModel):
    model: str
    prompt: str
    result: str

@router.post("/ollama", response_model=LLMResponse)
async def generate_with_ollama(request: LLMRequest):
    client = OllamaClient(settings.ollama_url)
    result = await client.generate(request.model, request.prompt)
    return LLMResponse(model=request.model, prompt=request.prompt, result=result)

@router.post("/openai", response_model=LLMResponse)
async def generate_with_openai(request: LLMRequest):
    if not settings.openai_api_key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY is not configured")
    openai.api_key = settings.openai_api_key
    completion = openai.ChatCompletion.create(
        model=request.model,
        messages=[{"role": "user", "content": request.prompt}],
    )
    return LLMResponse(
        model=request.model,
        prompt=request.prompt,
        result=completion.choices[0].message["content"],
    )

@router.post("/claude", response_model=LLMResponse)
async def generate_with_claude(request: LLMRequest):
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=400, detail="ANTHROPIC_API_KEY is not configured")
    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.completions.create(
        model=request.model,
        prompt=HUMAN_PROMPT + request.prompt + AI_PROMPT,
        max_tokens_to_generate=256,
    )
    return LLMResponse(model=request.model, prompt=request.prompt, result=response["completion"])
