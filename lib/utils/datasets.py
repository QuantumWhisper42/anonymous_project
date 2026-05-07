import json
import shlex

from pathlib import Path
from typing import Sequence

from pydantic import BaseModel

from lib.models.prompt import JudgedVQAChecklist, PendingVQAChecklist, Prompt
from lib.models.taxonomy import LabelTreeNode, parse_label_trees_from_json
from lib.types import Language
from lib.utils.common import PROJECT_ROOT


def get_task_root(task_name: str) -> Path:
    return PROJECT_ROOT / "output" / task_name


def load_taxonomy(task_name: str, language: Language) -> list[LabelTreeNode]:
    try:
        with open(
            get_task_root(task_name) / f"taxonomy_tree.json",
            "r",
            encoding="utf-8",
        ) as f:
            return parse_label_trees_from_json(json.load(f), language).children
    except FileNotFoundError:
        print(
            f"""taxonomy_tree.json does not exist in {str(get_task_root(task_name).relative_to(PROJECT_ROOT))}.

You can run `python main.py init && python main.py seed {shlex.quote(task_name)} --language={language} --kind=taxonomy` to copy the default one from `./seed/`.
"""
        )
        exit(1)


def load_prompt(task_name: str, language: Language) -> list[Prompt]:
    with open(
        get_task_root(task_name) / f"generated_prompt_{language}.jsonl",
        "r",
        encoding="utf-8",
    ) as f:
        return [Prompt.model_validate_json(line) for line in f.readlines()]


def _load_vqa_checklist(
    task_name: str, language: Language, filename_prefix: str
) -> list[PendingVQAChecklist]:
    with open(
        get_task_root(task_name) / f"{filename_prefix}_{language}.jsonl",
        "r",
        encoding="utf-8",
    ) as f:
        return [PendingVQAChecklist.model_validate_json(line) for line in f.readlines()]


def load_vqa_checklist(task_name: str, language: Language) -> list[PendingVQAChecklist]:
    try:
        return _load_vqa_checklist(task_name, language, "vqa_checklist")
    except FileNotFoundError:
        print(
            f"""vqa_checklist_{language}.jsonl does not exist in {str(get_task_root(task_name).relative_to(PROJECT_ROOT))}.

If you want to reuse the prompts and VQA checklists in the KnowVis paper, you can run `python main.py init && python main.py seed {shlex.quote(task_name)} --language={language} --kind=vqa_checklist --split=<generalized|skill_tree>` to copy the default one from `./seed/`.
Or, you can bring yor own prompts and run `python main.py analyze-prompt {shlex.quote(task_name)} --language={language}` to generate your own VQA checklists for your prompts.
"""
        )
        exit(1)


def load_additional_vqa_checklist(
    task_name: str, language: Language
) -> list[PendingVQAChecklist]:
    try:
        return _load_vqa_checklist(task_name, language, "additional_vqa_checklist")
    except FileNotFoundError:
        print(
            f"""additional_vqa_checklist_{language}.jsonl does not exist in {str(get_task_root(task_name).relative_to(PROJECT_ROOT))}.

If you want to reproduce the benchmark results in the KnowVis paper, you can run `python main.py init && python main.py seed {shlex.quote(task_name)} --language={language} --kind=judge_performance --judge-performance-split=<test|val>` to copy the default one from `./seed/`.
Or, you can create your own additional_vqa_checklist_{language}.jsonl by running `python main.py analyze-image {shlex.quote(task_name)} --language={language}` to add "additional_vqa_checklist" to vqa_checklist_{language}.jsonl
"""
        )
        exit(1)


def _dump_results(
    data: Sequence[BaseModel], task_name: str, language: Language, filename_prefix: str
) -> Path:
    output_file = get_task_root(task_name) / f"{filename_prefix}_{language}.jsonl"
    with open(output_file, "w", encoding="utf-8") as f:
        for item in data:
            f.write(item.model_dump_json() + "\n")
    return output_file


def dump_generate_prompt_results(
    data: Sequence[Prompt], task_name: str, language: Language
) -> Path:
    return _dump_results(data, task_name, language, "generated_prompt")


def dump_prompt_analysis_results(
    data: Sequence[PendingVQAChecklist], task_name: str, language: Language
) -> Path:
    return _dump_results(data, task_name, language, "vqa_checklist")


def dump_image_analysis_results(
    data: Sequence[PendingVQAChecklist], task_name: str, language: Language
) -> Path:
    return _dump_results(data, task_name, language, "additional_vqa_checklist")


def dump_judge_image_results(
    data: Sequence[JudgedVQAChecklist], task_name: str, language: Language
) -> Path:
    return _dump_results(data, task_name, language, "judged_vqa_checklist")
