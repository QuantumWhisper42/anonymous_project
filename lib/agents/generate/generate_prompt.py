import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic_ai import Agent, RunContext
from pydantic_ai.output import ToolOutput
from pydantic_ai.usage import RunUsage
from pydantic_graph import BaseNode, End, Graph, GraphRunContext
from pydantic_graph.graph import GraphRunResult

from lib.models.prompt import (
    FilterFeedback,
    FilterPromptPipelineOutput,
    PromptPipelineOutput,
    PromptOutput,
)
from lib.models.taxonomy import (
    LabelTreeNode,
)
from lib.types import Language
from lib.utils.agent import build_gemini_agent
from lib.utils.common import sync
from lib.utils.persistence import (
    SQLite3StatePersistence,
    get_persistance_db,
    run_persistent,
)
from lib.utils.template import build_message_template, get_template_file, load_raw_file

import uuid

UUID_NAMESPACE = uuid.UUID("e75c6463-f385-4477-b857-823361d1f380")


def _prompt_to_case_id(prompt: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, prompt))


# ---------------------------------------------------------------------------
# Graph state & deps
# ---------------------------------------------------------------------------


@dataclass
class GenerateState:
    """Mutable graph state threaded through every node."""

    category_path: list[LabelTreeNode]
    target_size: int
    current_prompts: list[PromptOutput] = field(default_factory=list)
    filter_feedbacks: list[FilterFeedback] = field(default_factory=list)
    collected_prompts: list[PromptOutput] = field(default_factory=list)
    generate_usage: RunUsage = field(default_factory=RunUsage)
    filter_usage: RunUsage = field(default_factory=RunUsage)
    filter_runs: int = 0

    def __post_init__(self):
        if self.target_size <= 0:
            raise ValueError("target_size MUST be positive")


@dataclass
class GenerateFilterAgentDeps:
    language: Language


@dataclass
class GenerateDeps:
    """Runtime dependencies injected into every node."""

    task_name: str
    generate_prompt_agent: Agent[GenerateFilterAgentDeps, PromptPipelineOutput]
    generate_user_message_template: Callable[[dict[str, Any]], str]
    filter_prompt_agent: Agent[GenerateFilterAgentDeps, FilterPromptPipelineOutput]
    filter_user_message_template: Callable[[dict[str, Any]], str]
    batch_size: int
    max_attempts: int = field(default=5)
    generate_filter_agent_deps: GenerateFilterAgentDeps = field(
        default_factory=lambda: GenerateFilterAgentDeps(language="en")
    )


# ---------------------------------------------------------------------------
# Graph node
# ---------------------------------------------------------------------------


@dataclass
class GenerateNode(BaseNode[GenerateState, GenerateDeps, PromptPipelineOutput]):
    """
    Single node that renders prompts and calls the LLM.
    """

    async def run(
        self, ctx: GraphRunContext[GenerateState, GenerateDeps]
    ) -> "FilterNode":
        state = ctx.state
        deps = ctx.deps

        batch_remaining = min(
            state.target_size - len(state.collected_prompts), deps.batch_size
        )
        template_ctx = {
            "category": state.category_path,
            "negative_knowledge_list": [
                node.title
                for node in state.category_path[-2].children
                if node.title != state.category_path[-1].title
            ],
            "batch_remaining": batch_remaining,
            "collected_prompts": state.collected_prompts,
            "filter_feedbacks": state.filter_feedbacks,
        }
        user_prompt = deps.generate_user_message_template(template_ctx)

        result = await deps.generate_prompt_agent.run(
            user_prompt=user_prompt,
            deps=deps.generate_filter_agent_deps,
        )

        state.generate_usage += result.usage()

        state.current_prompts = result.output.prompts

        return FilterNode()


@dataclass
class FilterNode(BaseNode[GenerateState, GenerateDeps, PromptPipelineOutput]):
    """
    Single node that renders prompts and calls the LLM.
    """

    async def run(
        self, ctx: GraphRunContext[GenerateState, GenerateDeps]
    ) -> "GenerateNode | End[PromptPipelineOutput]":
        state = ctx.state
        deps = ctx.deps

        state.filter_runs += 1

        if state.filter_runs > deps.max_attempts:
            return End(
                PromptPipelineOutput(
                    prompts=state.collected_prompts + state.current_prompts
                )
            )

        template_ctx = {
            "category": state.category_path,
            "negative_knowledge_list": [
                node.title
                for node in state.category_path[-2].children
                if node.title != state.category_path[-1].title
            ],
            "current_prompts": state.current_prompts,
        }
        user_prompt = deps.filter_user_message_template(template_ctx)

        result = await deps.filter_prompt_agent.run(
            user_prompt=user_prompt,
            deps=deps.generate_filter_agent_deps,
        )

        state.filter_usage += result.usage()

        state.filter_feedbacks = result.output.feedbacks

        filtered_prompts = [
            prompt
            for prompt in state.current_prompts
            if prompt.prompt
            not in set(
                feedback.failed_prompt.removeprefix("Prompt: ")
                for feedback in state.filter_feedbacks
            )
        ]

        state.collected_prompts.extend(filtered_prompts)

        if state.target_size - len(state.collected_prompts) <= 0:
            return End(PromptPipelineOutput(prompts=state.collected_prompts))
        else:
            return GenerateNode()


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

generate_graph = Graph(nodes=[GenerateNode, FilterNode], name="generate_prompt")


async def generate_prompt_run_persistent(
    start_node: GenerateNode | FilterNode,
    state: GenerateState,
    deps: GenerateDeps,
) -> GraphRunResult[GenerateState, PromptPipelineOutput]:
    persistence = SQLite3StatePersistence[GenerateState, PromptPipelineOutput](
        db_path=get_persistance_db("generate_prompt"),
        run_id=f"{deps.task_name}#{'-'.join([node.title for node in state.category_path])}#{state.target_size}",
    )

    result = await run_persistent(
        graph=generate_graph,
        start_node=start_node,
        persistence=persistence,
        state=state,
        deps=deps,
        infer_name=True,
        reset_error_or_running_snapshots=True,
    )

    return result


@sync
async def generate_prompt(
    task_name: str,
    language: Language = "en",
    size: int = 10,
) -> None:
    import logfire
    from genai_prices import calc_price
    from rich import print as rprint

    logfire.configure(send_to_logfire=False)
    logfire.instrument_pydantic_ai()
    logfire.instrument_httpx(capture_all=True)

    from lib.models.prompt import Prompt

    from lib.models.taxonomy import extract_paths
    from lib.utils.datasets import load_taxonomy, dump_generate_prompt_results

    T2I_TAXONOMY_ROOTS = load_taxonomy(task_name, language)

    taxonomy_paths = [
        taxonomy_node_path
        for taxonomy_root in T2I_TAXONOMY_ROOTS
        for taxonomy_node_path in extract_paths(taxonomy_root)
    ]

    generate_prompt_agent = build_gemini_agent(
        model_name="gemini-3.1-pro-preview",
        output_type=ToolOutput(PromptPipelineOutput),
        deps_type=GenerateFilterAgentDeps,
        system_prompt="",
    )

    @generate_prompt_agent.system_prompt
    async def generate_prompt_system_prompt(
        ctx: RunContext[GenerateFilterAgentDeps],
    ) -> str:
        return load_raw_file(
            get_template_file(
                "generate/generate_prompt.system.md",
                language=ctx.deps.language,
            )
        )

    filter_prompt_agent = build_gemini_agent(
        model_name="gemini-3-flash-preview",
        output_type=ToolOutput(FilterPromptPipelineOutput),
        deps_type=GenerateFilterAgentDeps,
        system_prompt="",
    )

    @filter_prompt_agent.system_prompt
    async def filter_system_prompt(
        ctx: RunContext[GenerateFilterAgentDeps],
    ) -> str:
        return load_raw_file(
            get_template_file(
                "generate/filter_prompt.system.md",
                language=ctx.deps.language,
            )
        )

    generate_prompt_deps = GenerateDeps(
        task_name=task_name,
        generate_prompt_agent=generate_prompt_agent,
        generate_user_message_template=build_message_template(
            get_template_file(
                "generate/generate_prompt.human.jinja2.md", language=language
            )
        ),
        filter_prompt_agent=filter_prompt_agent,
        filter_user_message_template=build_message_template(
            get_template_file(
                "generate/filter_prompt.human.jinja2.md", language=language
            )
        ),
        batch_size=5,
    )

    graph_run_results = await asyncio.gather(
        *[
            generate_prompt_run_persistent(
                start_node=GenerateNode(),
                deps=generate_prompt_deps,
                state=GenerateState(
                    category_path=taxonomy_path,
                    target_size=size,
                ),
            )
            for taxonomy_path in taxonomy_paths
        ],
        return_exceptions=True,
    )

    generate_prompt_usages = [
        graph_run_result.state.generate_usage
        for graph_run_result in graph_run_results
        if not isinstance(graph_run_result, BaseException)
    ]

    if len(generate_prompt_usages) > 0:
        total_generate_prompt_usage = sum(
            generate_prompt_usages, generate_prompt_usages[0]
        )

        rprint(
            "Total generate prompt cost: ",
            calc_price(
                usage=total_generate_prompt_usage,
                model_ref="gemini-3.1-pro-preview",
            ),
        )

    filter_prompt_usages = [
        graph_run_result.state.filter_usage
        for graph_run_result in graph_run_results
        if not isinstance(graph_run_result, BaseException)
    ]

    if len(filter_prompt_usages) > 0:
        total_filter_prompt_usage = sum(filter_prompt_usages, filter_prompt_usages[0])

        rprint(
            "Total filter prompt cost: ",
            calc_price(
                usage=total_filter_prompt_usage,
                model_ref="gemini-3.1-pro-preview",
            ),
        )

    rprint(
        "Exceptions:",
        [result for result in graph_run_results if isinstance(result, BaseException)],
    )

    dumped_generate_prompt_results_file = dump_generate_prompt_results(
        [
            Prompt(
                **prompt_output.model_dump(),
                case_id=_prompt_to_case_id(prompt_output.prompt),
                category=[node.title for node in graph_run_result.state.category_path],
            )
            for graph_run_result in graph_run_results
            if not isinstance(graph_run_result, BaseException)
            for prompt_output in graph_run_result.output.prompts
        ],
        task_name=task_name,
        language=language,
    )

    rprint(
        "Model generate prompt results dumped to:",
        dumped_generate_prompt_results_file,
    )
