# 🌏 KnowVis: A Dual-View Benchmark for Diagnosing World-Knowledge Grounding in Text-to-Image Models

## 📖 Overview

Text-to-image (T2I) models have made substantial progress in visual realism, aesthetic quality, and instruction following. However, real-world prompts often go beyond explicit visual descriptions and require implicit facts, structured knowledge, and domain-specific commonsense. Existing evaluations mainly focus on explicit prompt-to-image semantic alignment or specific knowledge subdomains, lacking a unified and diagnostic framework for evaluating world-knowledge grounding in T2I models.
We introduce **KnowVis**, a dual-view diagnostic benchmark for world-knowledge grounding in T2I generation. KnowVis is built on a hierarchical knowledge taxonomy with case-level annotations, and contains two complementary views: a **Skill-Tree Benchmark** for fine-grained atomic knowledge evaluation and a **Generalized Benchmark** for open-ended knowledge composition and expression.
We further design a shared MLLM-based VQA judge protocol for reliable evaluation and error attribution. The protocol uses Required VQAs to assess atomic knowledge correctness in the Skill-Tree Benchmark, and combines Required, Optional, and dynamically discovered knowledge expressions with human-judge collaborative evaluation in the Generalized Benchmark. Experiments show that KnowVis reveals notable gaps in world-knowledge grounding across existing T2I models, providing a unified basis for evaluating and improving knowledge-intensive image generation.

---

## ℹ️ Project Overview

This project is the companion codebase for [QuantumWhisper42/anonymous_dataset](https://huggingface.co/datasets/QuantumWhisper42/anonymous_dataset)。

This project implements a four-stage evaluation framework:

1. **Benchmark generation and automatic filtering** — Generates world-knowledge T2I prompts from a given taxonomy tree.
2. **Prompt analysis** — Decomposes T2I prompts into VQA checklists that identify visual elements requiring verification.
3. **Image analysis** — Generates additional VQA items from the actual generated images, capturing failure modes not anticipated during prompt analysis.
4. **Judging** — An MLLM-as-a-judge module that produces pass/fail/N.A. verdicts with reasoning for each VQA item, outputting structured evaluation results.

Each stage is implemented as a **pydantic-graph** workflow with SQLite-based state persistence, supporting fault-tolerant and resumable execution.

## 📂 Project Structure

```
.
├── data/template/                      # System prompt and message templates
├── example/
├── lib
│   ├── agents
│   │   ├── analysis
│   │   │   ├── image_analysis.py       # Image → additional VQA pipeline
│   │   │   └── prompt_analysis.py      # Prompt → VQA checklist pipeline
│   │   ├── generate/generate_prompt.py # Prompt generation + filtering pipeline
│   │   └── judge/judge_model_image.py  # MLLM-as-a-judge VQA evaluation
│   ├── models/                         # Pydantic models (VQA, judgments, etc.)
│   ├── tools/                          # Image search tools
│   └── utils/                          # Utility functions
├── main.py                             # Entry point
├── pyproject.toml                      # Dependencies and project configuration
├── README-zh.md
├── README.md
└── uv.lock
```

## 👁️ Core Concepts

### 🧐 VQA Checklist

The core evaluation unit is the **VQA checklist** — a set of binary (yes/no) visual questions extracted from the semantic requirements of a prompt:

- **Component types**: `ENTITY`, `ENTITY_TRAIT`, `ATTRIBUTE_BINDING`, `ENTITY_RELATION`, `ANNOTATION`, `ANNOTATION_BINDING`, `ANNOTATION_RELATION`
- **Evaluation types**: `VISUAL` (world-knowledge visual carrier), `KNOWLEDGE` (world-knowledge content logic), `INSTRUCTION` (non-knowledge visual instruction following)
- **Verdict types**: `REQUIRED` (must appear) vs. `OPTIONAL` (model-discretionary expression)

### 📚 Taxonomy

- **L1**: Top-level domain
- **L2**: Subject
- **L3**: Branch
- **L4**: Atomic knowledge point and annotation rules

### 🤖 Judge Modes

The judge module supports multiple ablation modes for controlled experiments:

| Mode | Description |
|------|-------------|
| `baseline` | Full pipeline with taxonomy labels, knowledge hints, and grounding evidence |
| `skip_label` | Removes taxonomy label context |
| `skip_knowledge_hint` | Removes world-knowledge hints |
| `skip_visual_grounding` | Removes reference image grounding evidence |
| `skip_all` | Removes all external context |
| `general` | General evaluation mode |

## 🗂️ Dependencies

- **Python 3.13+**
- **pydantic-ai** + **pydantic-graph** — Agent and graph framework
- **Google Gemini** (Vertex AI) — LLM backend
- **mwclient** — Wikimedia Commons API
- **minijinja** — Template rendering

See `pyproject.toml` for the full dependency list.

## 🤝 Conventions

- `task_name`: Represents a data synthesis and evaluation task. `output/<task_name>/` is the root directory for a task.
- `images`: The `output/<task_name>/images/` directory should contain all image assets used for evaluation. Image filenames must follow the format `{case_id}_{N}.png`, where N is a positive integer starting from 1. If the T2I model supports batch image generation, images should be numbered sequentially from 1 to obtain more reliable evaluation results.
- `case_id`: A UUIDv5 derived from the prompt, uniquely identifying an evaluation case.

## 🔖 Environment Variables

- `WIKIMEDIA_COMMONS_USER_AGENT`: Provide a compliant User-Agent string as required by the [Wikimedia Foundation User-Agent Policy](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy).
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to the Google Cloud credentials file for Vertex AI access.
- `GOOGLE_CLOUD_PROJECT`: Google Cloud project ID for Vertex AI access.
- `GOOGLE_CLOUD_LOCATION`: Google Cloud region for Vertex AI access. Currently must be set to `global`; additional regions may be supported in the future.

## 🚀 Usage

1. **Install dependencies**

This project uses uv for dependency management.

```bash
uv sync
source .venv/bin/activate # Acitivate environment
```

2. **Download the full dataset from Hugging Face**

```bash
python main.py init # Downloads from QuantumWhisper42/anonymous_dataset by default
# Additional options:
python main.py init --assets # Include image assets
python main.py init --repo-id=your-repo-id # Download from a different repository
python main.py init --repo-id=your-repo-id --repo-type=dataset # Specify repository type
```

3. **Initialize a task**

```bash
python main.py seed <task_name> --language=<en|zh> --kind=<all|images|taxonomy|vqa_checklist|judge_performance> --split=<generalized|skill_tree> --judge-performance-split=<test|val> --source=<hf|example>
```

Parameters:
- `task_name`: Task name. A directory will be created at `output/<task_name>`.
- `language`: Language; supports `en` and `zh`. Default: `en`.
- `kind`: Seed type; supports `all`, `images`, `taxonomy`, `vqa_checklist`, and `judge_performance`.
  - `all`: Automatically seeds all types.
  - `images`: Seeds image assets. Copies files from the `assets` directory of `source` to `output/<task_name>/images`, used for human-judge agreement validation.
  - `taxonomy`: Seeds the taxonomy. Copies `taxonomy_tree.json` from `source` to `output/<task_name>/taxonomy_tree.json`.
  - `vqa_checklist`: Seeds the VQA checklist. Copies `data/{split}_{language}.json` from `source` to `output/<task_name>/vqa_checklist.jsonl`.
  - `judge_performance`: Seeds the additional VQA checklist. Copies `data/{judge_performance_split}_{language}.json` from `source` to `output/<task_name>/additional_vqa_checklist.jsonl`, used for human-judge agreement validation.
- `split`: VQA checklist split; supports `generalized` and `skill_tree`.
- `judge_performance_split`: Judge performance data split; supports `test` and `val`.
- `source`: Source type; supports `hf` and `example`.

> If `source=example` is selected, files are copied from the `example/` directory rather than downloaded from Hugging Face. *Suitable for quick-start and demonstration purposes.*
> We strongly recommend first testing with `source=example` before switching to `source=hf` for evaluation on the full dataset.

4. **Run Stage 1: Benchmark generation and automatic filtering**

This stage requires `output/<task_name>/taxonomy_tree.json` to exist.

```bash
python main.py generate-prompt <task_name> --language=<en|zh> --size=<int>
```

Parameters:
- `task_name`: Task name.
- `language`: Language; supports `en` and `zh`. Default: `en`.
- `size`: Number of prompts to generate per category. Default: 10.

Upon completion, generated prompts are saved to `output/<task_name>/generated_prompt_{language}.jsonl`.

5. **Run Stage 2: VQA checklist decomposition**

This stage requires `output/<task_name>/generated_prompt_{language}.jsonl` to exist.

```bash
python main.py analyze-prompt <task_name> --language=<en|zh> --mode=<skill_tree|general>
```

Parameters:
- `task_name`: Task name.
- `language`: Language; supports `en` and `zh`. Default: `en`.
- `mode`: Decomposition mode; supports `skill_tree` and `general`. Default: `skill_tree`. In `general` mode, VQA checklist decomposition additionally covers non-knowledge basic visual instruction following.

Upon completion, generated VQA checklists are saved to `output/<task_name>/vqa_checklist_{language}.jsonl`.

6. **Run Stage 3: Additional VQA checklist generation**

This stage is optional. It is only required for case studies that need further assessment of image quality, including visual plausibility and knowledge richness.

This stage requires `output/<task_name>/vqa_checklist_{language}.jsonl` to exist and image files for all cases to be present in the `images/` directory.

```bash
python main.py analyze-image <task_name> --language=<en|zh>
```

Parameters:
- `task_name`: Task name.
- `language`: Language; supports `en` and `zh`. Default: `en`.

Upon completion, results are saved to `output/<task_name>/additional_vqa_checklist_{language}.jsonl`.

7. **Run Stage 4: Evaluation**

This stage requires either `output/<task_name>/vqa_checklist_{language}.jsonl` or `output/<task_name>/additional_vqa_checklist_{language}.jsonl` to exist.

```bash
python main.py judge <task_name> --language=<en|zh> --use-additional=<true|false> --mode=<baseline|skip_label|skip_knowledge_hint|skip_visual_grounding|skip_all|general>
```

Parameters:
- `task_name`: Task name.
- `language`: Language; supports `en` and `zh`. Default: `en`.
- `use_additional`: Whether to use the additional VQA checklist. Default: `false`.
- `mode`: Evaluation mode. Used for ablation studies and to distinguish between the Skill-Tree Benchmark and the Generalized Benchmark. Supports `baseline`, `skip_label`, `skip_knowledge_hint`, `skip_visual_grounding`, `skip_all`, and `general`. Default: `baseline`.

Upon completion, evaluation results are saved to `output/<task_name>/judged_vqa_checklist_{language}.jsonl`.

## 📜 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## 🤝 Contributing

Feedback and contributions are welcome. Please open an issue for bug reports or improvement suggestions.