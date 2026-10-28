import os
import re
import time
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

PRICING: dict[str, dict[str, float]] = {
    # Gemini
    "gemini-3.5-flash":        {"input": 0.075,  "output": 0.30},
    "gemini-2.0-flash":        {"input": 0.075,  "output": 0.30},
    "gemini-1.5-flash":        {"input": 0.075,  "output": 0.30},
    "gemini-1.5-pro":          {"input": 1.25,   "output": 5.00},
    # Groq (Llama / OSS)
    "openai/gpt-oss-120b":     {"input": 0.15,   "output": 0.60},
    "qwen/qwen3.8-27b":        {"input": 0.10,   "output": 0.30},
    # NVIDIA NIM
    "meta/llama-3.2-11b-vision-instruct": {"input": 0.20, "output": 0.20},
    "meta/llama-3.2-90b-vision-instruct": {"input": 0.50, "output": 0.50},
}


def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    prices = PRICING.get(model, {"input": 0.15, "output": 0.30})
    return (
        input_tokens  * prices["input"]  / 1_000_000 +
        output_tokens * prices["output"] / 1_000_000
    )


def _clean_sql(raw: str) -> str:
    cleaned = raw.strip()
    match = re.search(r"```(?:sql)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
    else:
        cleaned = re.sub(r"^```(?:sql)?|```$", "", cleaned, flags=re.MULTILINE).strip()
    
    cleaned = cleaned.replace("`", "").strip()
    semicolon_idx = cleaned.rfind(";")
    if semicolon_idx != -1:
        cleaned = cleaned[:semicolon_idx + 1]
    return cleaned.strip()


def _extract_gemini_text(response) -> str:
    try:
        if hasattr(response, "text") and response.text:
            return response.text.strip()
    except Exception:
        pass

    try:
        candidates = getattr(response, "candidates", [])
        if candidates:
            cand = candidates[0]
            content = getattr(cand, "content", None)
            if content and hasattr(content, "parts"):
                collected = [getattr(p, "text", "") for p in content.parts if getattr(p, "text", "")]
                if collected:
                    return "".join(collected).strip()
    except Exception as e:
        logger.warning("Error reading candidate parts: %s", e)

    return ""


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float


def _call_gemini(prompt: str, model: str, temperature: float) -> LLMResult:
    import google.generativeai as genai
    from google.generativeai.types import GenerationConfig, HarmCategory, HarmBlockThreshold

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise EnvironmentError("GEMINI_API_KEY is not set in .env")
    genai.configure(api_key=api_key)

    gemini_model = genai.GenerativeModel(
        model_name=model,
        generation_config=GenerationConfig(
            temperature=temperature,
            max_output_tokens=2048,
            candidate_count=1,
        ),
        safety_settings={
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
    )

    t0 = time.perf_counter()
    response = gemini_model.generate_content(prompt)
    latency_ms = (time.perf_counter() - t0) * 1000

    raw_text = _extract_gemini_text(response)
    if not raw_text:
        raw_text = "SELECT * FROM orders;"

    usage = getattr(response, "usage_metadata", None)
    input_tokens  = getattr(usage, "prompt_token_count", 0) if usage else 0
    output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0

    return LLMResult(
        text=_clean_sql(raw_text),
        provider="gemini",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=_calculate_cost(model, input_tokens, output_tokens),
        latency_ms=round(latency_ms, 2),
    )


def _call_groq(prompt: str, model: str, temperature: float) -> LLMResult:
    from openai import OpenAI

    api_key = os.environ.get("GROK_API_KEY") or os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY is not set in .env")

    # Ultra-fast Groq LPU API
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1"
    )

    t0 = time.perf_counter()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=2048,
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    usage = response.usage
    input_tokens  = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0
    raw_text = response.choices[0].message.content or ""

    return LLMResult(
        text=_clean_sql(raw_text.strip()),
        provider="groq",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=_calculate_cost(model, input_tokens, output_tokens),
        latency_ms=round(latency_ms, 2),
    )


def _call_nvidia(prompt: str, model: str, temperature: float) -> LLMResult:
    from openai import OpenAI

    api_key = os.environ.get("NVIDIA_API_KEY", "")
    if not api_key or api_key == "your_nvidia_api_key_here":
        raise EnvironmentError("NVIDIA_API_KEY is not set in .env")

    client = OpenAI(
        api_key=api_key,
        base_url="https://integrate.api.nvidia.com/v1"
    )

    t0 = time.perf_counter()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=2048,
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    usage = response.usage
    input_tokens  = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0
    raw_text = response.choices[0].message.content or ""

    return LLMResult(
        text=_clean_sql(raw_text.strip()),
        provider="nvidia",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=_calculate_cost(model, input_tokens, output_tokens),
        latency_ms=round(latency_ms, 2),
    )

_PROVIDER_MAP = {
    "gemini": _call_gemini,
    "groq":   _call_groq,
    "grok":   _call_groq,  # support both grok and groq aliases
    "nvidia": _call_nvidia,
}

_DEFAULT_MODELS = {
    "gemini": "gemini-3.5-flash",
    "groq":   "openai/gpt-oss-120b",
    "grok":   "openai/gpt-oss-120b",
    "nvidia": "meta/llama-3.2-11b-vision-instruct",
}


def call_llm(
    prompt: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.05,
) -> LLMResult:
    provider = (provider or os.environ.get("DEFAULT_PROVIDER", "gemini")).lower()
    if provider not in _PROVIDER_MAP:
        raise ValueError(f"Unknown provider '{provider}'. Choose from: {list(_PROVIDER_MAP.keys())}")

    resolved_model = model or os.environ.get(f"{provider.upper()}_MODEL", _DEFAULT_MODELS.get(provider, "openai/gpt-oss-120b"))
    logger.info("LLM call -> provider=%s model=%s", provider, resolved_model)
    result = _PROVIDER_MAP[provider](prompt, resolved_model, temperature)
    logger.info(
        "LLM done -> %d in / %d out / $%.6f / %.0fms",
        result.input_tokens, result.output_tokens, result.cost_usd, result.latency_ms
    )
    return result


def configure_gemini() -> None:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise EnvironmentError("GEMINI_API_KEY is not set. Add it to your .env file.")
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    logger.info("Gemini SDK configured (model: %s)", _DEFAULT_MODELS["gemini"])
