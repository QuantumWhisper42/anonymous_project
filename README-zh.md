# 🌏 KnowVis：用于诊断文生图模型世界知识定位能力的双视角基准

## 📖 概述

文生图（T2I）模型在视觉真实性、美学质量和指令跟随方面已取得显著进展。然而，现实世界中的提示词往往超越了显式的视觉描述，还要求模型具备隐式事实、结构化知识和领域常识的理解能力。现有评估工作主要聚焦于显式提示词与图像的语义对齐，或特定知识子领域，缺乏一个统一的、具有诊断性的框架来评估 T2I 模型的世界知识定位能力。

我们提出 **KnowVis**，一个面向 T2I 生成中世界知识定位能力的双视角诊断基准。KnowVis 基于层次化知识分类体系构建，包含样本级标注，并涵盖两个互补视角：**技能树基准**（Skill-Tree Benchmark）用于细粒度原子知识评估，**泛化基准**（Generalized Benchmark）用于开放式知识组合与表达评估。

我们进一步设计了一套基于多模态大语言模型（MLLM）的 VQA 评判协议，用于可靠评估和错误归因。该协议在技能树基准中使用"必答 VQA"评估原子知识的正确性；在泛化基准中，则将必答项、选答项和动态发现的知识表达与人工评判协作评估相结合。实验表明，KnowVis 能够揭示现有 T2I 模型在世界知识定位方面的显著差距，为评估和改进知识密集型图像生成提供了统一基础。

---

# ℹ️ 项目简介

本项目是 [QuantumWhisper42/anonymous_dataset](https://huggingface.co/datasets/QuantumWhisper42/anonymous_dataset) 的配套代码，实现了一个四阶段评测框架：

1. **评测集生成和自动过滤** — 根据给定类目树生成世界知识文生图提示词。
2. **提示词分析** — 将 T2I 提示词分解为 VQA（视觉问答）核查单，识别需要验证的视觉元素。
3. **图像分析** — 根据实际生成的图像生成额外的 VQA 项，捕捉提示词分析未预见的失败情况。
4. **评判** — LLM-as-a-Judge 模块，对每个 VQA 项给出判定（通过/不通过/不适用）及推理过程，输出结构化评测结果。

每个阶段以 **pydantic-graph** 工作流实现，支持基于 SQLite 的状态持久化，具备容错与可恢复执行能力。

## 📂 项目结构

```
.
├── data/template/                      # System Prompt 和 Message 模板
├── example/
├── lib
│   ├── agents
│   │   ├── analysis
│   │   │   ├── image_analysis.py       # 图像 → 额外 VQA 流水线
│   │   │   └── prompt_analysis.py      # 提示词 → VQA 核查单流水线
│   │   ├── generate/generate_prompt.py # 提示词生成 + 筛选流水线
│   │   └── judge/judge_model_image.py  # MLLM-as-a-Judge VQA 评测
│   ├── models/                         # Pydantic 模型（VQA、评判等）
│   ├── tools/                          # 图像搜索工具
│   └── utils/                          # 工具函数
├── main.py                             # 入口
├── pyproject.toml                      # 依赖与项目配置
├── README-zh.md
├── README.md
└── uv.lock
```

## 👁️ 核心概念

### 🧐 VQA 核查单

评测的核心单元是 **VQA 核查单**——一组从提示词语义需求中提取的二元（是/否）视觉问题：

- **组件类型**：`ENTITY`（实体）、`ENTITY_TRAIT`（实体特征）、`ATTRIBUTE_BINDING`（属性绑定）、`ENTITY_RELATION`（实体关系）、`ANNOTATION`（标注）、`ANNOTATION_BINDING`（标注绑定）、`ANNOTATION_RELATION`（标注关系）
- **评测类型**：`VISUAL`（世界知识视觉载体）、`KNOWLEDGE`（世界知识内容逻辑）、`INSTRUCTION`（非知识类指令遵循）
- **判定类型**：`REQUIRED`（必须出现） vs `OPTIONAL`（模型可选发挥）

### 📚 分类体系

- **L1**：顶级领域
- **L2**：子领域
- **L3**：具体主题
- **L4**：知识点及标注规则

### 🤖 评判模式

评判模块支持多种消融模式，用于受控实验：

| 模式 | 说明 |
|------|------|
| `baseline` | 完整流水线，包含标签、知识提示和视觉锚定 |
| `skip_label` | 移除分类体系标签上下文 |
| `skip_knowledge_hint` | 移除世界知识补充 |
| `skip_visual_grounding` | 移除参考图像证据 |
| `skip_all` | 移除所有外部上下文 |
| `general` | 通用评测模式 |

## 🗂️ 依赖

- **Python 3.13+**
- **pydantic-ai** + **pydantic-graph** — Agent 与图框架
- **Google Gemini**（Vertex AI）— LLM 后端
- **mwclient** — Wikimedia Commons API
- **minijinja** — 模板渲染

完整依赖列表见 `pyproject.toml`。

## 🤝 约定：

- `task_name`: 代表一个数据合成和评测任务。`output/<task_name>/` 是一个任务的根目录。
- `images`: `output/<task_name>/images/` 目录下应包含所有用于评测的图像 assets。图像的文件名一定是 `{case_id}_{N}.png` 格式。N 为从 1 开始的正整数。如果文生图模型支持组图生成，那么应当按照顺序，从1开始编号，以得到更置信的评测结果。
- `case_id`: UUIDv5，从 prompt 中计算得出，用于唯一标识一个评测案例。

## 🔖 环境变量

- `WIKIMEDIA_COMMONS_USER_AGENT`: 参考 [Wikimedia Foundation User-Agent Policy](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy), 提供符合要求的 User-Agent 字符串。
- `GOOGLE_APPLICATION_CREDENTIALS`: 指向 Google Cloud 凭据文件的路径，用于 Vertex AI 访问。
- `GOOGLE_CLOUD_PROJECT`: Google Cloud 项目 ID，用于 Vertex AI 访问。
- `GOOGLE_CLOUD_LOCATION`: Google Cloud 地区，用于 Vertex AI 访问。当前必须为 `global`，未来可能可选更多地区。

## 🚀 使用方法

1. **安装依赖**

本项目使用 uv 管理依赖。

```bash
uv sync
source .venv/bin/activate # 激活环境
```

2. **从 Hugging Face 下载全量数据集**

```bash
python main.py init # 默认从QuantumWhisper42/anonymous_dataset下载
# 除此之外，还可以选择：
python main.py init --assets # 包含图像资产
python main.py init --repo-id=your-repo-id # 从其他仓库下载
python main.py init --repo-id=your-repo-id --repo-type=dataset # 指定仓库类型
```

3. **初始化任务**

```bash
python main.py seed <task_name> --language=<en|zh> --kind=<all|images|taxonomy|vqa_checklist|judge_performance> --split=<generalized|skill_tree> --judge-performance-split=<test|val> --source=<hf|example>
```

说明：
- `task_name`：任务名称，将被创建在 `output/<task_name>` 目录下
- `language`：语言，支持 `en` 和 `zh`。默认为 `en`
- `kind`：种子类型，支持 `all`、`images`、`taxonomy`、`vqa_checklist`、`judge_performance`
  - `all`: 如果自动种子化所有类型。
  - `images`: 种子化图像。从 `source` 复制 `assets` 目录下的文件，到 `output/<task_name>/images` 目录下，用于人机一致性验证。
  - `taxonomy`: 种子化分类体系。从 `source` 复制 `taxonomy_tree.json` 文件到 `output/<task_name>/taxonomy_tree.json`。
  - `vqa_checklist`: 种子化VQA核查单。从 `source` 复制 `data/{split}_{language}.json` 文件到 `output/<task_name>/vqa_checklist.jsonl`。
  - `judge_performance`: 种子化额外VQA核查单。从 `source` 复制 `data/{judge_performance_split}_{language}.json` 文件到 `output/<task_name>/additional_vqa_checklist.jsonl`，用于人机一致性验证。
- `split`：VQA 核查单划分方式，支持 `generalized` 和 `skill_tree`
- `judge_performance_split`：评测性能数据划分方式，支持 `test` 和 `val`
- `source`：源类型，支持 `hf` 和 `example`

> 如果选择 `source=example`，则会从 `example/` 目录下复制文件，而不会从 Hugging Face 下载。*适用于快速上手和演示*
> 我们强烈建议先从 `source=example` 开始测试，再从 `source=hf` 获取真实数据进行评测。

4. **执行任务1: 评测集生成和自动过滤**

当 `output/<task_name>/taxonomy_tree.json` 存在时，即可执行任务1。

```bash
python main.py generate-prompt <task_name> --language=<en|zh> --size=<int>
```

说明：
- `task_name`：任务名称
- `language`：语言，支持 `en` 和 `zh`。默认为 `en`
- `size`：每个分类下生成的 prompt 数量。默认为 10

执行完成后，生成的 prompt 将被保存在 `output/<task_name>/generated_prompt_{language}.jsonl` 文件中。

5. **执行任务2: VQA checklist 拆解**

当  `output/<task_name>/generated_prompt_{language}.jsonl` 存在时，即可执行任务2。

```bash
python main.py analyze-prompt <task_name> --language=<en|zh> --mode=<skill_tree|general>
```

说明：
- `task_name`：任务名称
- `language`：语言，支持 `en` 和 `zh`。默认为 `en`
- `mode`：拆解模式，支持 `skill_tree` 和 `general`。默认为 `skill_tree`。 `general` 模式下，会额外添加非知识类基础视觉指令遵循的 VQA checklist 拆解

执行完成后，生成的 VQA checklist 将被保存在 `output/<task_name>/vqa_checklist_{language}.jsonl` 文件中。

6. **执行任务3: Additional VQA checklist 生成**

这一步不是必选项。只有需要进一步进行图像质量评估，包含合理性和丰富程度的 case study，才需要执行此步骤。

当 `output/<task_name>/vqa_checklist_{language}.jsonl` 存在，且 `images/` 目录下存在所有case的图像文件时，即可执行任务3。

```bash
python main.py analyze-image <task_name> --language=<en|zh>
```

说明：
- `task_name`：任务名称
- `language`：语言，支持 `en` 和 `zh`。默认为 `en`

执行完成后，生成的评测结果将被保存在 `output/<task_name>/additional_vqa_checklist_{language}.jsonl` 文件中。

7. **执行任务4: 评测性能**

当 `output/<task_name>/vqa_checklist_{language}.jsonl` 或者 `output/<task_name>/additional_vqa_checklist_{language}.jsonl` 存在时，即可执行任务4。

```bash
python main.py judge <task_name> --language=<en|zh> --use-additional=<true|false> --mode=<baseline|skip_label|skip_knowledge_hint|skip_visual_grounding|skip_all|general>
```

说明：
- `task_name`：任务名称
- `language`：语言，支持 `en` 和 `zh`。默认为 `en`
- `use_additional`：是否使用额外的 VQA checklist。默认为 `false`
- `mode`：评测模式。用于消融实验和区分基础技能树和泛化评测集，支持 `baseline`、`skip_label`、`skip_knowledge_hint`、`skip_visual_grounding`、`skip_all` 和 `general`。默认为 `baseline`

执行完成后，生成的评测结果将被保存在 `output/<task_name>/judged_vqa_checklist_{language}.jsonl` 文件中。

## 📜 许可证

本项目使用 MIT 许可证，请参阅 [LICENSE](LICENSE) 文件获取详细信息。

---

## 🤝 贡献

欢迎反馈与贡献。如发现问题或有改进建议，请提交 Issue。