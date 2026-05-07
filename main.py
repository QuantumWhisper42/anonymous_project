import fire
import fire.core

from lib.agents.generate.generate_prompt import generate_prompt
from lib.agents.analysis.prompt_analysis import prompt_analysis
from lib.agents.analysis.image_analysis import image_analysis
from lib.agents.judge.judge_model_image import judge

from huggingface_hub import snapshot_download

from lib.utils.common import PROJECT_ROOT
from lib.types import Language
from lib.utils.datasets import get_task_root
from typing import Literal
import shutil
import shlex


def _no_pager(lines, out):
    out.write("\n".join(lines) + "\n")


fire.core.Display = _no_pager


HF_PATH = PROJECT_ROOT / "seed"
EXAMPLE_PATH = PROJECT_ROOT / "example"


def _init_dataset(
    repo_id: str = "QuantumWhisper42/anonymous_dataset",
    repo_type: str = "dataset",
    assets: bool = False,
):
    snapshot_download(
        repo_id=repo_id,
        repo_type=repo_type,
        local_dir=HF_PATH,
        ignore_patterns="assets/*" if not assets else None,
    )


def _seed_task(
    task_name: str,
    language: Language = "en",
    kind: Literal[
        "all",
        "images",
        "taxonomy",
        "vqa_checklist",
        "judge_performance",
    ] = "taxonomy",
    split: Literal[
        "generalized",
        "skill_tree",
    ]
    | None = None,
    judge_performance_split: Literal[
        "test",
        "val",
    ]
    | None = None,
    source: Literal["hf", "example"] = "hf",
):
    seed_path = HF_PATH if source == "hf" else EXAMPLE_PATH
    match kind:
        case "all":
            _seed_task(
                task_name,
                language,
                "images",
            )
            _seed_task(
                task_name,
                language,
                "taxonomy",
            )
            _seed_task(
                task_name,
                language,
                "vqa_checklist",
                split=split,
            )
            _seed_task(
                task_name,
                language,
                "judge_performance",
                judge_performance_split=judge_performance_split,
            )
        case "images":
            source_path = seed_path / "assets"
            target_path = get_task_root(task_name=task_name) / "images"
            hint = f"""You can now add some images to {shlex.quote(str(target_path.relative_to(PROJECT_ROOT)))},
and call `python main.py judge {shlex.quote(task_name)} --language={language}` to judge the images.
"""

        case "taxonomy":
            source_path = seed_path / "taxonomy_tree.json"
            target_path = get_task_root(task_name=task_name) / "taxonomy_tree.json"
            hint = f"""You can now call `python main.py generate-prompt {task_name}` to create your own prompt based on the taxonomy tree.
You are suggested to modify taxonomy_tree.json to fit your needs, or use the default file as-is.
"""
        case "vqa_checklist":
            source_path = seed_path / "data" / f"{split}_{language}.jsonl"
            target_path = (
                get_task_root(task_name=task_name) / f"vqa_checklist_{language}.jsonl"
            )
            hint = f"""You can now add some images to {shlex.quote(str((get_task_root(task_name=task_name) / "images").relative_to(PROJECT_ROOT)))},
and call `python main.py judge {shlex.quote(task_name)} --language={language}` to judge the images.
"""
        case "judge_performance":
            source_path = (
                seed_path / "data" / f"{judge_performance_split}_gt_{language}.jsonl"
            )
            target_path = (
                get_task_root(task_name=task_name)
                / f"additional_vqa_checklist_{language}.jsonl"
            )
            hint = f"""You can now add some images to {shlex.quote(str((get_task_root(task_name=task_name) / "images").relative_to(PROJECT_ROOT)))},
and call `python main.py judge {shlex.quote(task_name)} --language={language} --use-additional` to judge the images.
"""

        case _:
            raise ValueError(f"Unknown kind: {kind}")

    if source == "hf" and not source_path.exists():
        print(f"""Cannot find source path: {source_path}
Did you forget to run `python main.py init` to download the dataset from HuggingFace?
""")
        if kind == "images":
            print("""Noted that by default, running `python main.py init` does not retrieve image assets from HuggingFace.
You should add `--assets` to retrieve image assets.
""")
        exit(1)
    if target_path.exists():
        answer = input(f"""Target path already exists: {target_path}
Are you sure you want to overwrite it? (y/N)
""")
        if answer.lower() != "y":
            exit(2)
        print("Overwriting...")
    print(f"Copying {source_path} to {target_path}...")
    if source_path.is_dir():
        shutil.copytree(source_path, target_path, dirs_exist_ok=True)
    else:
        shutil.copy2(source_path, target_path)
    print(f"Successfully seeded {shlex.quote(task_name)} with {kind}.")
    print(hint)


if __name__ == "__main__":
    fire.Fire(
        {
            "init": _init_dataset,
            "seed": _seed_task,
            "generate-prompt": generate_prompt,
            "analyze-prompt": prompt_analysis,
            "analyze-image": image_analysis,
            "judge": judge,
        }
    )
