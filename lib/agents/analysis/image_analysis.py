import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic_ai import Agent, RunContext
from pydantic_ai.output import ToolOutput
from pydantic_ai.usage import RunUsage
from pydantic_graph import BaseNode, End, Graph, GraphRunContext
from pydantic_graph.graph import GraphRunResult

from lib.models.prompt import ImageAnalysisPipelineOutput, PendingVQAChecklist
from lib.models.taxonomy import LabelTreeNode
from lib.tools.image_search.wikimedia_commons_image_search import (
    wikimedia_commons_image_search_tool,
)
from lib.types import Language
from lib.utils.agent import build_gemini_agent
from lib.utils.common import sync
from lib.utils.image import load_images_from_task
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
class ImageAnalysisState:
    """Mutable graph state threaded through every node."""

    category_path: list[LabelTreeNode]
    pending_vqa_checklist: PendingVQAChecklist
    image_analysis_usage: RunUsage = field(default_factory=RunUsage)


@dataclass
class ImageAnalysisAgentDeps:
    language: Language


@dataclass
class ImageAnalysisDeps:
    """Runtime dependencies injected into every node."""

    task_name: str
    image_analysis_agent: Agent[ImageAnalysisAgentDeps, ImageAnalysisPipelineOutput]
    image_analysis_user_message_template: Callable[[dict[str, Any]], str]
    image_analysis_agent_deps: ImageAnalysisAgentDeps


# ---------------------------------------------------------------------------
# Graph node
# ---------------------------------------------------------------------------


@dataclass
class AnalysisNode(
    BaseNode[ImageAnalysisState, ImageAnalysisDeps, ImageAnalysisPipelineOutput]
):
    """
    Single node that renders prompts and calls the LLM.
    """

    async def run(
        self, ctx: GraphRunContext[ImageAnalysisState, ImageAnalysisDeps]
    ) -> End[ImageAnalysisPipelineOutput]:
        state = ctx.state
        deps = ctx.deps

        template_ctx = {
            "category": state.category_path,
            "prompt": state.pending_vqa_checklist.prompt,
            "vqa_checklist": json.dumps(
                [
                    item.model_dump(exclude={"reasoning", "judgment"})
                    for item in state.pending_vqa_checklist.vqa_checklist
                ],
                ensure_ascii=False,
                indent=2,
            ),
        }
        user_message = deps.image_analysis_user_message_template(template_ctx)

        input_images = load_images_from_task(
            task_name=deps.task_name, case_id=state.pending_vqa_checklist.case_id
        )

        if not input_images:
            raise ValueError(
                f"{state.pending_vqa_checklist.case_id} does not have input images"
            )

        result = await deps.image_analysis_agent.run(
            user_prompt=input_images + [user_message],
            deps=deps.image_analysis_agent_deps,
        )

        state.image_analysis_usage += result.usage()

        return End(result.output)


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

image_analysis_graph = Graph(nodes=[AnalysisNode], name="image_analysis")


async def image_analysis_run_persistent(
    start_node: AnalysisNode,
    state: ImageAnalysisState,
    deps: ImageAnalysisDeps,
) -> GraphRunResult[ImageAnalysisState, ImageAnalysisPipelineOutput]:
    persistence = SQLite3StatePersistence[
        ImageAnalysisState, ImageAnalysisPipelineOutput
    ](
        db_path=get_persistance_db("image_analysis"),
        run_id=f"{deps.task_name}#{state.pending_vqa_checklist.case_id}",
    )

    result = await run_persistent(
        graph=image_analysis_graph,
        start_node=start_node,
        persistence=persistence,
        state=state,
        deps=deps,
        infer_name=True,
        reset_error_or_running_snapshots=True,
    )

    return result


@sync
async def image_analysis(
    task_name: str,
    language: Language = "en",
) -> None:
    import logfire
    from genai_prices import calc_price
    from rich import print as rprint

    logfire.configure(send_to_logfire=False)
    logfire.instrument_pydantic_ai()
    logfire.instrument_httpx(capture_all=True)

    from lib.models.taxonomy import build_label_tree_node_path_from_str
    from lib.utils.datasets import (
        load_taxonomy,
        load_vqa_checklist,
        dump_image_analysis_results,
    )

    T2I_TAXONOMY_ROOTS = load_taxonomy(task_name, language)

    pending_vqa_checklists = load_vqa_checklist(task_name=task_name, language=language)

    image_analysis_agent = build_gemini_agent(
        model_name="gemini-3.1-pro-preview-customtools",
        output_type=ToolOutput(ImageAnalysisPipelineOutput),
        system_prompt="",
        deps_type=ImageAnalysisAgentDeps,
        tools=[
            wikimedia_commons_image_search_tool(),
        ],
    )

    @image_analysis_agent.system_prompt
    async def image_analysis_system_prompt(
        ctx: RunContext[ImageAnalysisAgentDeps],
    ) -> str:
        return load_raw_file(
            get_template_file(
                "analysis/image_analysis.system.md",
                language=ctx.deps.language,
            )
        )

    image_analysis_deps = ImageAnalysisDeps(
        task_name=task_name,
        image_analysis_agent=image_analysis_agent,
        image_analysis_user_message_template=build_message_template(
            get_template_file(
                "analysis/image_analysis.human.jinja2.md", language=language
            )
        ),
        image_analysis_agent_deps=ImageAnalysisAgentDeps(language=language),
    )

    graph_run_results = await asyncio.gather(
        *[
            image_analysis_run_persistent(
                start_node=AnalysisNode(),
                deps=image_analysis_deps,
                state=ImageAnalysisState(
                    category_path=build_label_tree_node_path_from_str(
                        pending_vqa_checklist.category,
                        T2I_TAXONOMY_ROOTS,
                    ),
                    pending_vqa_checklist=pending_vqa_checklist,
                ),
            )
            for pending_vqa_checklist in pending_vqa_checklists
        ],
        return_exceptions=True,
    )

    image_analysis_usages = [
        graph_run_result.state.image_analysis_usage
        for graph_run_result in graph_run_results
        if not isinstance(graph_run_result, BaseException)
    ]

    if len(image_analysis_usages) > 0:
        total_image_analysis_usage = sum(
            image_analysis_usages, image_analysis_usages[0]
        )

        rprint(
            "Total image analysis cost: ",
            calc_price(
                usage=total_image_analysis_usage,
                model_ref="gemini-3.1-pro-preview",
            ),
        )

    rprint(
        "Exceptions:",
        [result for result in graph_run_results if isinstance(result, BaseException)],
    )

    dumped_image_analysis_results_file = dump_image_analysis_results(
        [
            PendingVQAChecklist(
                **graph_run_result.state.pending_vqa_checklist.model_dump(
                    exclude={"additional_vqa_checklist"}
                ),
                additional_vqa_checklist=graph_run_result.output.to_additional_vqa_checklist(),
            )
            for graph_run_result in graph_run_results
            if not isinstance(graph_run_result, BaseException)
        ],
        task_name=task_name,
        language=language,
    )

    rprint(
        "Model image analysis results dumped to:",
        dumped_image_analysis_results_file,
    )
