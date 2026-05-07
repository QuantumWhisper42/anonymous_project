import base64
from dataclasses import dataclass
from typing import assert_never, cast

from google.genai.types import (
    BlobDict,
    CodeExecutionResultDict,
    ContentDict,
    ContentUnionDict,
    ExecutableCodeDict,
    FileSearchDict,
    FunctionCallDict,
    FunctionResponseDict,
    FunctionResponsePartDict,
    GoogleSearchDict,
    ImageConfigDict,
    PartDict,
    ToolCodeExecutionDict,
    ToolDict,
    UrlContextDict,
)
from pydantic_ai import (
    CodeExecutionTool,
    FileSearchTool,
    ImageGenerationTool,
    WebFetchTool,
    WebSearchTool,
)
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import (
    BuiltinToolCallPart,
    BuiltinToolReturnPart,
    FilePart,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.google import (
    GoogleModel,
    ModelRequestParameters,
    _function_declaration_from_tool,
)
from pydantic_ai.profiles.google import GoogleModelProfile
from pydantic_ai.settings import ModelSettings


@dataclass(init=False)
class MyGoogleModel(GoogleModel):
    def _get_tools(
        self, model_request_parameters: ModelRequestParameters
    ) -> tuple[list[ToolDict] | None, ImageConfigDict | None]:
        tools: list[ToolDict] = [
            ToolDict(function_declarations=[_function_declaration_from_tool(t)])
            for t in model_request_parameters.tool_defs.values()
        ]

        image_config: ImageConfigDict | None = None

        if model_request_parameters.builtin_tools:
            for tool in model_request_parameters.builtin_tools:
                if isinstance(tool, WebSearchTool):
                    tools.append(ToolDict(google_search=GoogleSearchDict()))
                elif isinstance(tool, WebFetchTool):
                    tools.append(ToolDict(url_context=UrlContextDict()))
                elif isinstance(tool, CodeExecutionTool):
                    tools.append(ToolDict(code_execution=ToolCodeExecutionDict()))
                elif isinstance(tool, FileSearchTool):
                    file_search_config = FileSearchDict(
                        file_search_store_names=list(tool.file_store_ids)
                    )
                    tools.append(ToolDict(file_search=file_search_config))
                elif isinstance(tool, ImageGenerationTool):  # pragma: no branch
                    if not self.profile.supports_image_output:
                        raise UserError(
                            "`ImageGenerationTool` is not supported by this model. Use a model with 'image' in the name instead."
                        )
                    image_config = self._build_image_config(tool)
                else:  # pragma: no cover
                    raise UserError(
                        f"`{tool.__class__.__name__}` is not supported by `GoogleModel`. If it should be, please file an issue."
                    )
        return tools or None, image_config

    async def _map_messages(  # noqa: C901
        self,
        messages: list[ModelMessage],
        model_request_parameters: ModelRequestParameters,
    ) -> tuple[ContentDict | None, list[ContentUnionDict]]:
        contents: list[ContentUnionDict] = []
        system_parts: list[PartDict] = []

        for m in messages:
            if isinstance(m, ModelRequest):
                message_parts: list[PartDict] = []

                for part in m.parts:
                    if isinstance(part, SystemPromptPart):
                        system_parts.append({"text": part.content})
                    elif isinstance(part, UserPromptPart):
                        message_parts.extend(await self._map_user_prompt(part))
                    elif isinstance(part, ToolReturnPart):
                        message_parts.extend(await self._map_tool_return(part))
                    elif isinstance(part, RetryPromptPart):
                        if part.tool_name is None:
                            message_parts.append({"text": part.model_response()})
                        else:
                            message_parts.append(
                                {
                                    "function_response": {
                                        "name": part.tool_name,
                                        "response": {"error": part.model_response()},
                                        # "id": part.tool_call_id,
                                    }
                                }
                            )
                    else:
                        assert_never(part)

                # Work around a Gemini bug where content objects containing functionResponse parts are treated as
                # role=model even when role=user is explicitly specified.
                #
                # We build `message_parts` first, then split into multiple content objects whenever we transition
                # between function_response and non-function_response parts.
                #
                # TODO: Remove workaround when https://github.com/pydantic/pydantic-ai/issues/4210 is resolved
                if message_parts:
                    content_parts: list[PartDict] = []

                    for part in message_parts:
                        if (
                            content_parts
                            and "function_response" in content_parts[-1]
                            and "function_response" not in part
                        ):
                            contents.append({"role": "user", "parts": content_parts})
                            content_parts = []

                        content_parts.append(part)

                    contents.append({"role": "user", "parts": content_parts})
            elif isinstance(m, ModelResponse):
                maybe_content = _content_model_response(m, self.system)
                if maybe_content:
                    contents.append(maybe_content)
            else:
                assert_never(m)

        # Google GenAI requires at least one user part in the message, and that function call turns
        # come immediately after a user turn or after a function response turn.
        if not contents or contents[0].get("role") == "model":  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
            contents.insert(0, {"role": "user", "parts": [{"text": ""}]})

        if instructions := self._get_instructions(messages, model_request_parameters):
            system_parts.append({"text": instructions})
        system_instruction = (
            ContentDict(role="user", parts=system_parts) if system_parts else None
        )

        return system_instruction, contents

    async def _map_tool_return(self, part: ToolReturnPart) -> list[PartDict]:
        """Map a `ToolReturnPart` to Google API format, handling multimodal content.

        For Gemini 3+ models with supported MIME types, files are sent inside
        `function_response.parts` for efficiency. Unsupported types become separate
        parts after the function_response (fallback strategy).
        See: https://ai.google.dev/gemini-api/docs/function-calling?example=meeting#multimodal
        """
        supported_mime_types = GoogleModelProfile.from_profile(
            self.profile
        ).google_supported_mime_types_in_tool_returns

        function_response_parts: list[FunctionResponsePartDict] = []
        fallback_parts: list[PartDict] = []
        fallback_refs: list[str] = []

        for file in part.files:
            if file.media_type in supported_mime_types:
                fr_part = await self._map_file_to_function_response_part(file)
                function_response_parts.append(fr_part)
            else:
                fallback_refs.append(f"See file {file.identifier}.")
                fallback_parts.append({"text": f"This is file {file.identifier}:"})
                file_part = await self._map_file_to_part(file)
                fallback_parts.append(file_part)

        response = part.model_response_object()
        if fallback_refs:
            response = {"output": [response, *fallback_refs]}

        function_response_dict: FunctionResponseDict = {
            "name": part.tool_name,
            "response": response,
            # "id": part.tool_call_id,
        }
        if function_response_parts:
            function_response_dict["parts"] = function_response_parts

        result: list[PartDict] = [{"function_response": function_response_dict}]
        result.extend(fallback_parts)

        return result

    def prepare_request(
        self,
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> tuple[ModelSettings | None, ModelRequestParameters]:
        return super(GoogleModel, self).prepare_request(
            model_settings, model_request_parameters
        )


def _content_model_response(m: ModelResponse, provider_name: str) -> ContentDict | None:  # noqa: C901
    parts: list[PartDict] = []
    thinking_part_signature: str | None = None
    function_call_requires_signature: bool = True
    for item in m.parts:
        part: PartDict = {}
        if (
            item.provider_details
            and (thought_signature := item.provider_details.get("thought_signature"))
            and (
                m.provider_name == provider_name or item.provider_name == provider_name
            )
        ):
            part["thought_signature"] = base64.b64decode(thought_signature)
        elif thinking_part_signature:
            part["thought_signature"] = base64.b64decode(thinking_part_signature)
        thinking_part_signature = None

        if isinstance(item, ToolCallPart):
            function_call = FunctionCallDict(
                name=item.tool_name, args=item.args_as_dict()
            )  # , id=item.tool_call_id)
            part["function_call"] = function_call
            if function_call_requires_signature and not part.get("thought_signature"):
                # Per https://ai.google.dev/gemini-api/docs/thought-signatures#faqs:
                # > You can set the following dummy signatures of either "context_engineering_is_the_way_to_go"
                # > or "skip_thought_signature_validator"
                # Per https://cloud.google.com/vertex-ai/generative-ai/docs/thought-signatures#using-rest-or-manual-handling:
                # > You can set thought_signature to skip_thought_signature_validator
                # We use "skip_thought_signature_validator" as it works for both Gemini API and Vertex AI.
                part["thought_signature"] = b"skip_thought_signature_validator"
            # Only the first function call requires a signature
            function_call_requires_signature = False
        elif isinstance(item, TextPart):
            part["text"] = item.content
        elif isinstance(item, ThinkingPart):
            if item.provider_name == provider_name and item.signature:
                # The thought signature is to be included on the _next_ part, not the thinking part itself
                thinking_part_signature = item.signature

            if item.content:
                part["text"] = item.content
                part["thought"] = True
        elif isinstance(item, BuiltinToolCallPart):
            if item.provider_name == provider_name:
                if item.tool_name == CodeExecutionTool.kind:
                    part["executable_code"] = cast(
                        ExecutableCodeDict, item.args_as_dict()
                    )
                elif item.tool_name == WebSearchTool.kind:
                    # Web search calls are not sent back
                    pass
        elif isinstance(item, BuiltinToolReturnPart):
            if item.provider_name == provider_name:
                if item.tool_name == CodeExecutionTool.kind and isinstance(
                    item.content, dict
                ):
                    part["code_execution_result"] = cast(
                        CodeExecutionResultDict, item.content
                    )  # pyright: ignore[reportUnknownMemberType]
                elif item.tool_name == WebSearchTool.kind:
                    # Web search results are not sent back
                    pass
        elif isinstance(item, FilePart):
            content = item.content
            inline_data_dict: BlobDict = {
                "data": content.data,
                "mime_type": content.media_type,
            }
            part["inline_data"] = inline_data_dict
        else:
            assert_never(item)

        if part:
            parts.append(part)

    if not parts:
        return None
    return ContentDict(role="model", parts=parts)
