"""Offline tests for ResilientLLMChain retry and fallback behavior."""

import asyncio
from unittest.mock import AsyncMock, patch
import pytest
from pydantic import SecretStr

from kawach_demo.llm_chain import ResilientLLMChain
from kawach_fix.clients.llm import LLMClientError


def test_llm_chain_groq_first_success():
    async def _test():
        chain = ResilientLLMChain(
            groq_api_key=SecretStr("gsk_mock_groq"),
            gemini_api_key=SecretStr("AIza_mock_gemini"),
            max_retries=1,
        )

        with patch.object(chain, "_call_groq", new_callable=AsyncMock) as mock_groq, \
             patch.object(chain, "_call_gemini", new_callable=AsyncMock) as mock_gemini:
            mock_groq.return_value = '{"can_fix": true}'

            resp = await chain.generate("sys", "user")

            assert resp == '{"can_fix": true}'
            assert chain.last_provider == "Groq"
            assert mock_groq.await_count == 1
            assert mock_gemini.await_count == 0

    asyncio.run(_test())


def test_llm_chain_groq_fails_gemini_fallback():
    async def _test():
        chain = ResilientLLMChain(
            groq_api_key=SecretStr("gsk_mock_groq"),
            gemini_api_key=SecretStr("AIza_mock_gemini"),
            max_retries=1,
        )

        with patch.object(chain, "_call_groq", new_callable=AsyncMock) as mock_groq, \
             patch.object(chain, "_call_gemini", new_callable=AsyncMock) as mock_gemini, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_groq.side_effect = Exception("Groq 429 Rate Limit")
            mock_gemini.return_value = '{"can_fix": true, "fallback": true}'

            resp = await chain.generate("sys", "user")

            assert resp == '{"can_fix": true, "fallback": true}'
            assert chain.last_provider == "Gemini"
            # 1 initial + 1 retry = 2 calls to groq
            assert mock_groq.await_count == 2
            assert mock_gemini.await_count == 1

    asyncio.run(_test())


def test_llm_chain_all_fail_raises():
    async def _test():
        chain = ResilientLLMChain(
            groq_api_key=SecretStr("gsk_mock_groq"),
            gemini_api_key=SecretStr("AIza_mock_gemini"),
            max_retries=0,
        )

        with patch.object(chain, "_call_groq", new_callable=AsyncMock) as mock_groq, \
             patch.object(chain, "_call_gemini", new_callable=AsyncMock) as mock_gemini:
            mock_groq.side_effect = Exception("Groq down")
            mock_gemini.side_effect = Exception("Gemini down")

            with pytest.raises(LLMClientError):
                await chain.generate("sys", "user")

    asyncio.run(_test())
