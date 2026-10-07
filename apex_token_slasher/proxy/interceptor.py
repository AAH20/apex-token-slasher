"""OpenAI and Anthropic Request Interceptor.

Parses API request payloads, extracts context message bodies, slashes tokens,
and re-packs the request before upstream forwarding.
Zero external dependencies.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from apex_token_slasher.core.models import BudgetSpec, SlashedContext
from apex_token_slasher.pipeline import SlasherPipeline


class TokenSlasherInterceptor:
    """Intercepts and compresses message arrays inside LLM request bodies."""

    def __init__(self, pipeline: Optional[SlasherPipeline] = None) -> None:
        self.pipeline = pipeline or SlasherPipeline()

    def process_openai_payload(
        self,
        payload_bytes: bytes,
        budget: Optional[BudgetSpec] = None,
    ) -> Tuple[bytes, SlashedContext]:
        """Intercepts OpenAI /v1/chat/completions JSON payload and slashes prompt tokens."""
        data = json.loads(payload_bytes.decode("utf-8"))
        messages = data.get("messages", [])

        # Find the largest context message (often system prompt or latest user code dump)
        largest_idx = -1
        max_len = 0
        for idx, msg in enumerate(messages):
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > max_len:
                max_len = len(content)
                largest_idx = idx

        if largest_idx >= 0 and max_len > 1000:
            original_content = messages[largest_idx]["content"]
            slashed = self.pipeline.slash_context(
                raw_text=original_content,
                budget=budget,
            )
            messages[largest_idx]["content"] = slashed.rendered_text
            data["messages"] = messages
            return json.dumps(data).encode("utf-8"), slashed

        # No large message to compress: return as-is
        empty_slashed = self.pipeline.slash_context(raw_text="", budget=budget)
        return payload_bytes, empty_slashed
