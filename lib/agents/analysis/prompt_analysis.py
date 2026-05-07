import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from pydantic_ai import Agent, RunContext
from pydantic_ai.output import ToolOutput
from pydantic_ai.usage import RunUsage
from pydantic_graph import BaseNode, End, Graph, GraphRunContext
from pydantic_graph.graph import GraphRunResult

from lib.models.prompt import Prompt, PromptAnalysisPipelineOutput
from lib.models.taxonomy import LabelTreeNode
from lib.tools.image_search.wikimedia_commons_image_search import (
    wikimedia_commons_image_search_tool,
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


# ---------------------------------------------------------------------------
# Graph state & deps
# ---------------------------------------------------------------------------


@dataclass
class PromptAnalysisState:
    """Mutable graph state threaded through every node."""

    category_path: list[LabelTreeNode]
    prompt: Prompt
    prompt_analysis_usage: RunUsage = field(default_factory=RunUsage)


class PromptAnalysisMode(str, Enum):
    SKILL_TREE = "skill_tree"
    GENERAL = "general"


@dataclass
class PromptAnalysisAgentDeps:
    language: Language
    mode: PromptAnalysisMode = field(default=PromptAnalysisMode.SKILL_TREE)


@dataclass
class PromptAnalysisDeps:
    """Runtime dependencies injected into every node."""

    task_name: str
    prompt_analysis_agent: Agent[PromptAnalysisAgentDeps, PromptAnalysisPipelineOutput]
    prompt_analysis_user_message_template: Callable[[dict[str, Any]], str]
    prompt_analysis_agent_deps: PromptAnalysisAgentDeps = field(
        default_factory=lambda: PromptAnalysisAgentDeps(
            language="en", mode=PromptAnalysisMode.SKILL_TREE
        )
    )


# ---------------------------------------------------------------------------
# Graph node
# ---------------------------------------------------------------------------


@dataclass
class AnalysisNode(
    BaseNode[PromptAnalysisState, PromptAnalysisDeps, PromptAnalysisPipelineOutput]
):
    """
    Single node that renders prompts and calls the LLM.
    """

    async def run(
        self, ctx: GraphRunContext[PromptAnalysisState, PromptAnalysisDeps]
    ) -> End[PromptAnalysisPipelineOutput]:
        state = ctx.state
        deps = ctx.deps

        template_ctx = {
            "category": state.category_path,
            "prompt": state.prompt.prompt,
        }

        user_prompt = deps.prompt_analysis_user_message_template(template_ctx)

        result = await deps.prompt_analysis_agent.run(
            user_prompt=user_prompt,
            deps=deps.prompt_analysis_agent_deps,
        )

        state.prompt_analysis_usage += result.usage()

        return End(result.output)


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

prompt_analysis_graph = Graph(nodes=[AnalysisNode], name="prompt_analysis")


async def prompt_analysis_run_persistent(
    start_node: AnalysisNode,
    state: PromptAnalysisState,
    deps: PromptAnalysisDeps,
) -> GraphRunResult[PromptAnalysisState, PromptAnalysisPipelineOutput]:
    persistence = SQLite3StatePersistence[
        PromptAnalysisState, PromptAnalysisPipelineOutput
    ](
        db_path=get_persistance_db("prompt_analysis"),
        run_id=f"{deps.task_name}#{state.prompt.case_id}",
    )

    result = await run_persistent(
        graph=prompt_analysis_graph,
        start_node=start_node,
        persistence=persistence,
        state=state,
        deps=deps,
        infer_name=True,
        reset_error_or_running_snapshots=True,
    )

    return result


@sync
async def prompt_analysis(
    task_name: str,
    language: Language = "en",
    mode: PromptAnalysisMode = PromptAnalysisMode.SKILL_TREE,
) -> None:
    import logfire
    from genai_prices import calc_price
    from rich import print as rprint

    logfire.configure(send_to_logfire=False)
    logfire.instrument_pydantic_ai()
    logfire.instrument_httpx(capture_all=True)

    from lib.models.prompt import PendingVQAChecklist
    from lib.models.taxonomy import build_label_tree_node_path_from_str
    from lib.utils.datasets import (
        load_taxonomy,
        load_prompt,
        dump_prompt_analysis_results,
    )

    mode = PromptAnalysisMode(mode)

    T2I_TAXONOMY_ROOTS = load_taxonomy(task_name, language)

    prompts = load_prompt(task_name=task_name, language=language)

    prompt_analysis_agent = build_gemini_agent(
        model_name="gemini-3.1-pro-preview-customtools",
        output_type=ToolOutput(PromptAnalysisPipelineOutput),
        system_prompt="",
        deps_type=PromptAnalysisAgentDeps,
        tools=[
            wikimedia_commons_image_search_tool(),
        ],
    )

    @prompt_analysis_agent.system_prompt
    async def prompt_analysis_system_prompt(
        ctx: RunContext[PromptAnalysisAgentDeps],
    ) -> str:
        return load_raw_file(
            get_template_file(
                f"analysis/prompt_analysis.{ctx.deps.mode.value}.system.md",
                language=ctx.deps.language,
            )
        )

    prompt_analysis_deps = PromptAnalysisDeps(
        task_name=task_name,
        prompt_analysis_agent=prompt_analysis_agent,
        prompt_analysis_user_message_template=build_message_template(
            get_template_file(
                "analysis/prompt_analysis.human.jinja2.md", language=language
            )
        ),
        prompt_analysis_agent_deps=PromptAnalysisAgentDeps(
            language=language,
            mode=mode,
        ),
    )

    graph_run_results = await asyncio.gather(
        *[
            prompt_analysis_run_persistent(
                start_node=AnalysisNode(),
                deps=prompt_analysis_deps,
                state=PromptAnalysisState(
                    category_path=build_label_tree_node_path_from_str(
                        prompt.category,
                        T2I_TAXONOMY_ROOTS,
                    ),
                    prompt=prompt,
                ),
            )
            for prompt in prompts
        ],
        return_exceptions=True,
    )

    prompt_analysis_usages = [
        graph_run_result.state.prompt_analysis_usage
        for graph_run_result in graph_run_results
        if not isinstance(graph_run_result, BaseException)
    ]

    if len(prompt_analysis_usages) > 0:
        total_prompt_analysis_usage = sum(
            prompt_analysis_usages, prompt_analysis_usages[0]
        )

        rprint(
            "Total prompt analysis cost: ",
            calc_price(
                usage=total_prompt_analysis_usage,
                model_ref="gemini-3.1-pro-preview",
            ),
        )

    rprint(
        "Exceptions:",
        [result for result in graph_run_results if isinstance(result, BaseException)],
    )

    dumped_prompt_analysis_results_file = dump_prompt_analysis_results(
        [
            PendingVQAChecklist(
                **graph_run_result.state.prompt.model_dump(),
                vqa_checklist=graph_run_result.output.to_vqa_checklist(),
                cot_prompt=graph_run_result.output.cot_prompt,
            )
            for graph_run_result in graph_run_results
            if not isinstance(graph_run_result, BaseException)
        ],
        task_name=task_name,
        language=language,
    )

    rprint(
        "Model prompt analysis results dumped to:",
        dumped_prompt_analysis_results_file,
    )
