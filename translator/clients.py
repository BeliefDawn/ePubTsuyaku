from __future__ import annotations

from typing import Optional

from .config import PipelineConfig
from .llm import (
    BaseLLMClient,
    MockLLMClient,
    OpenAICompatibleLLMClient,
    SakuraLLMClient,
    TranslationHistory,
)


def build_llm_client(
    config: PipelineConfig,
    translation_history: Optional[TranslationHistory] = None,
) -> BaseLLMClient:
    if config.provider == "mock":
        return MockLLMClient()
    if not config.api_key:
        raise RuntimeError("缺少 API Key。")
    if config.provider == "sakura":
        assistant = None
        if config.assistant_enabled and config.assistant_base_url:
            assistant_model = config.assistant_model or config.model
            assistant = OpenAICompatibleLLMClient(
                api_key=config.assistant_api_key or "sk-no-key-required",
                base_url=config.assistant_base_url,
                model=assistant_model,
                summary_model=assistant_model,
                translation_model=assistant_model,
                review_model=assistant_model,
                no_thinking_prompt=True,
            )
        return SakuraLLMClient(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            assistant_client=assistant,
            translation_history=translation_history,
        )
    return OpenAICompatibleLLMClient(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        summary_model=config.summary_model,
        translation_model=config.translation_model,
        review_model=config.review_model,
    )
