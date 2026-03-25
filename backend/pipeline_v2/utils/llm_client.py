"""
LLM Client — Azure OpenAI wrapper with retry, JSON mode, and per-call logging.
"""

import asyncio
import json
import logging
import time
from typing import Optional

from openai import AsyncAzureOpenAI

from pipeline_v2.config import v2_settings
from config import settings as base_settings

logger = logging.getLogger(__name__)


class LLMCallError(Exception):
    pass


def _make_client() -> AsyncAzureOpenAI:
    endpoint = v2_settings.v2_azure_openai_endpoint or base_settings.azure_openai_endpoint
    api_key = v2_settings.v2_azure_openai_api_key or base_settings.azure_openai_api_key
    api_version = v2_settings.v2_azure_openai_api_version or base_settings.azure_openai_api_version
    return AsyncAzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)


async def call_llm(
    system_prompt: str,
    user_message: str,
    stage_name: str,
    model: str = "large",           # "large" | "small"
    json_mode: bool = True,
    max_tokens: int = 2000,
    case_id: Optional[str] = None,
    timeout: float = 60.0,
) -> dict:
    """
    Call Azure OpenAI with retry (3 attempts, exponential backoff).
    Returns parsed JSON dict if json_mode=True, else {"text": raw_response}.
    Raises LLMCallError after all retries fail.
    """
    client = _make_client()
    # V2-specific deployment → fall back to base AZURE_OPENAI_DEPLOYMENT
    deployment = (
        (v2_settings.v2_azure_openai_deployment_large or base_settings.azure_openai_deployment)
        if model == "large"
        else (v2_settings.v2_azure_openai_deployment_small or base_settings.azure_openai_deployment)
    )

    kwargs = {
        "model": deployment,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    start = time.time()
    last_err = None

    for attempt in range(3):
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(**kwargs),
                timeout=timeout,
            )
            raw = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            duration = time.time() - start
            tokens = response.usage.total_tokens if response.usage else 0
            logger.info(
                f"[LLM][{stage_name}] model={deployment} tokens={tokens} "
                f"finish_reason={finish_reason} duration={duration:.1f}s case={case_id or '-'}"
            )
            if finish_reason == "length":
                logger.warning(
                    f"[LLM][{stage_name}] Response hit max_tokens={max_tokens} — "
                    f"output was truncated. Fields near end of JSON may be missing. "
                    f"Consider raising v2_max_tokens_extraction in config."
                )
            return json.loads(raw) if json_mode else {"text": raw}

        except asyncio.TimeoutError as e:
            last_err = e
            logger.warning(f"[LLM][{stage_name}] attempt {attempt+1} timed out")
        except json.JSONDecodeError as e:
            logger.error(f"[LLM][{stage_name}] JSON parse error: {e}")
            raise LLMCallError(f"[{stage_name}] LLM returned invalid JSON: {e}")
        except Exception as e:
            last_err = e
            logger.warning(f"[LLM][{stage_name}] attempt {attempt+1} failed: {e}")

        if attempt < 2:
            await asyncio.sleep(2 ** attempt)

    raise LLMCallError(f"[{stage_name}] LLM call failed after 3 attempts: {last_err}")
