from __future__ import annotations

from typing import Any, Dict, Type

from pydantic import BaseModel

from app.core.llm.llm_client import LLMClient


class StructuredLLMRunner:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def run_structured(
        self,
        *,
        user_content: str,
        system_prompt: str,
        pydantic_model: Type[BaseModel],
        use_cache: bool = False,
    ) -> Dict[str, Any]:
        return await self.llm_client.extract_structured_data_with_schema(
            text=user_content,
            system_prompt=system_prompt,
            pydantic_model=pydantic_model,
            use_cache=use_cache,
        )
