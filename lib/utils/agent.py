from types import NoneType
from typing import Sequence

from google.genai import Client
from google.genai.types import (
    HttpOptions,
    HarmBlockThreshold,
    HarmCategory,
    SafetySettingDict,
    ThinkingConfigDict,
    ThinkingLevel,
)
from httpx import (
    AsyncClient,
    HTTPStatusError,
    TimeoutException,
    ConnectError,
    ReadError,
)
from pydantic_ai import Agent, WebFetchTool, WebSearchTool
from pydantic_ai.models.concurrency import ConcurrencyLimitedModel
from pydantic_ai import ConcurrencyLimiter
from pydantic_ai.builtin_tools import AbstractBuiltinTool
from pydantic_ai.models.google import GoogleModelSettings
from pydantic_ai.output import OutputDataT, OutputSpec
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.retries import AsyncTenacityTransport, RetryConfig, wait_retry_after
from pydantic_ai.tools import AgentDepsT, BuiltinToolFunc, Tool, ToolFuncEither
from pydantic_ai.toolsets import AbstractToolset, ToolsetFunc
from tenacity import retry_if_exception_type, stop_after_attempt, wait_exponential

from lib.utils.google_model_fix import MyGoogleModel
import httpx
from urllib.request import getproxies


def create_rate_limit_network_resilient_client():
    """Create a client that respects Retry-After headers from rate limiting responses."""
    proxy_map = getproxies()
    proxy_url = proxy_map.get("https", proxy_map.get("http"))

    transport = AsyncTenacityTransport(
        wrapped=httpx.AsyncHTTPTransport(
            proxy=(httpx.Proxy(proxy_url) if proxy_url else None)
        ),
        config=RetryConfig(
            retry=retry_if_exception_type(
                (
                    HTTPStatusError,
                    TimeoutException,
                    ConnectError,
                    ReadError,
                )
            ),
            wait=wait_retry_after(
                fallback_strategy=wait_exponential(multiplier=1, max=60),
                max_wait=300,  # Don't wait more than 5 minutes
            ),
            stop=stop_after_attempt(10),
            reraise=True,
        ),
        validate_response=lambda r: (
            r.raise_for_status()
        ),  # Raises HTTPStatusError for 4xx/5xx
    )
    return AsyncClient(transport=transport, timeout=30.0)


rate_limit_network_resilient_client = create_rate_limit_network_resilient_client()


shared_limiter = ConcurrencyLimiter(max_running=30, name="gemini-pool")


def build_gemini_agent(
    model_name: str,
    system_prompt: str | Sequence[str],
    output_type: OutputSpec[OutputDataT] = str,
    deps_type: type[AgentDepsT] = NoneType,
    builtin_tools: Sequence[AbstractBuiltinTool | BuiltinToolFunc[AgentDepsT]] = [
        WebSearchTool(),
        WebFetchTool(),
    ],
    tools: Sequence[Tool[AgentDepsT] | ToolFuncEither[AgentDepsT, ...]] = (),
    toolsets: Sequence[AbstractToolset[AgentDepsT] | ToolsetFunc[AgentDepsT]]
    | None = None,
    thinking_level: ThinkingLevel = ThinkingLevel.HIGH,
):
    return Agent(
        model=ConcurrencyLimitedModel(
            MyGoogleModel(
                model_name=model_name,
                provider=GoogleProvider(
                    client=Client(
                        vertexai=True,
                        http_options=HttpOptions(
                            api_version="v1",
                            httpx_async_client=rate_limit_network_resilient_client,
                        ),
                    )
                ),
            ),
            limiter=shared_limiter,
        ),
        deps_type=deps_type,
        output_type=output_type,
        system_prompt=system_prompt,
        model_settings=GoogleModelSettings(
            google_safety_settings=[
                SafetySettingDict(
                    category=HarmCategory.HARM_CATEGORY_HARASSMENT,
                    threshold=HarmBlockThreshold.OFF,
                ),
                SafetySettingDict(
                    category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    threshold=HarmBlockThreshold.OFF,
                ),
                SafetySettingDict(
                    category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                    threshold=HarmBlockThreshold.OFF,
                ),
                SafetySettingDict(
                    category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                    threshold=HarmBlockThreshold.OFF,
                ),
            ],
            google_thinking_config=ThinkingConfigDict(thinking_level=thinking_level),
        ),
        builtin_tools=builtin_tools,
        tools=tools,
        toolsets=toolsets,
    )
