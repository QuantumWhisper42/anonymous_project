from pydantic import BaseModel, Field

from enum import Enum

from typing import Literal


class ComponentType(str, Enum):
    ENTITY = "ENTITY"
    ENTITY_TRAIT = "ENTITY_TRAIT"
    ATTRIBUTE_BINDING = "ATTRIBUTE_BINDING"
    ENTITY_RELATION = "ENTITY_RELATION"
    ANNOTATION = "ANNOTATION"
    ANNOTATION_BINDING = "ANNOTATION_BINDING"
    ANNOTATION_RELATION = "ANNOTATION_RELATION"


class EvalType(str, Enum):
    VISUAL = "VISUAL"
    KNOWLEDGE = "KNOWLEDGE"
    INSTRUCTION = "INSTRUCTION"


class JudgeType(str, Enum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"


class JudgmentType(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NA = "NA"


class PromptType(str, Enum):
    EXPLICIT = "EXPLICIT"
    IMPLICIT = "IMPLICIT"


class Weight(int, Enum):
    LOW = 1
    MEDIUM = 3
    HIGH = 5


class VisualGrounding(BaseModel):
    title: str = Field(..., description="Visual grounding image title")
    url: str = Field(..., description="Visual grounding image url")
    source: str = Field(
        ..., description="Visual grounding image source (Wikimedia Commons file page)"
    )
    author: str = Field(
        ..., description="Visual grounding image author (May contain HTML tags)"
    )
    license: str = Field(..., description="Visual grounding image license name")
    license_url: str = Field(..., description="Visual grounding image license url")


class VQAItem(BaseModel):
    question: str = Field(
        ...,
        description="A binary judgment question for evaluating text-to-image quality (must be answerable with Yes/No).",
    )
    component: ComponentType = Field(
        ...,
        description="The component type corresponding to this VQA, representing the visual element being evaluated.",
    )
    knowledge_hint: str = Field(
        ...,
        description="Supplementary world knowledge and an exhaustive enumeration of expected visual representations provided to the LLM-as-a-Judge, used to explain how to determine success or failure. If it is a pure visual rendering requirement (VISUAL), this field may be left empty.",
    )
    visual_grounding: VisualGrounding | None = Field(
        None,
        description="Supplementary visual evidence reference image URLs provided to the LLM-as-a-Judge for world knowledge, may be left empty.",
    )


class VQAItemOutput(BaseModel):
    question: str = Field(
        ...,
        description="A binary judgment question for evaluating text-to-image quality (must be answerable with Yes/No).",
    )
    component: ComponentType = Field(
        ...,
        description="The component type corresponding to this VQA, representing the visual element being evaluated.",
    )
    knowledge_hint: str = Field(
        ...,
        description="Supplementary world knowledge and an exhaustive enumeration of expected visual representations provided to the LLM-as-a-Judge, used to explain how to determine success or failure. If it is a pure visual rendering requirement (VISUAL), this field may be left empty.",
    )
    visual_grounding: str | None = Field(
        None,
        description="Supplementary visual evidence reference image URLs provided to the LLM-as-a-Judge for world knowledge, may be left empty.",
    )


class VQAItemWithScore(VQAItem):
    id: int
    reasoning: str = Field(
        ...,
        description="The Judge's reasoning process for reaching the verdict on this VQA.",
    )
    judgment: JudgmentType = Field(
        ...,
        description="The Judge's verdict on this VQA: PASS indicates passed, FAIL indicates failed, and NA indicates not applicable.",
    )


class JudgedAdditionalVQAItem(VQAItemWithScore):
    kind: Literal["JudgedAdditionalVQAItem"] = "JudgedAdditionalVQAItem"


class PendingAdditionalVQAItem(VQAItemWithScore):
    kind: Literal["PendingAdditionalVQAItem"] = "PendingAdditionalVQAItem"


class VQAItemOutputWithType(VQAItemOutput):
    eval_type: EvalType = Field(
        ...,
        description="The evaluation type corresponding to this VQA: whether it is a pure visual rendering requirement (VISUAL), or a requirement that needs world knowledge to fulfill (KNOWLEDGE).",
    )
    judge_type: JudgeType = Field(
        JudgeType.REQUIRED,
        description="Whether this VQA is a required component of the Prompt, or an optional/discretionary part left to the model.",
    )
    weight: Weight = Field(
        default=Weight.MEDIUM, description="Importance of this VQA item."
    )


class VQAItemWithType(VQAItem):
    eval_type: EvalType = Field(
        ...,
        description="The evaluation type corresponding to this VQA: whether it is a pure visual rendering requirement (VISUAL), or a requirement that needs world knowledge to fulfill (KNOWLEDGE).",
    )
    judge_type: JudgeType = Field(
        JudgeType.REQUIRED,
        description="Whether this VQA is a required component of the Prompt, or an optional/discretionary part left to the model.",
    )
    weight: Weight = Field(
        default=Weight.MEDIUM, description="Importance of this VQA item."
    )


class VQAItemWithTypeAndScore(VQAItemWithType):
    id: int
    reasoning: str = Field(
        ...,
        description="16:58Claude responded: The Judge's reasoning process for reaching the verdict on this VQA.The Judge's reasoning process for reaching the verdict on this VQA.",
    )
    judgment: JudgmentType = Field(
        ...,
        description="The Judge's verdict on this VQA: PASS indicates passed, FAIL indicates failed, and NA indicates not applicable.",
    )


class JudgedVQAItem(VQAItemWithTypeAndScore):
    kind: Literal["JudgedVQAItem"] = "JudgedVQAItem"


class ReviewedVQAItem(JudgedVQAItem):
    human_judgment: JudgmentType


class PendingVQAItem(VQAItemWithTypeAndScore):
    kind: Literal["PendingVQAItem"] = "PendingVQAItem"


class PromptOutput(BaseModel):
    prompt: str = Field(
        ...,
        description="A text-to-image prompt (Target Prompt) that requires the model to draw upon both world knowledge and typographic rendering capabilities, with direct spoiling of the answer strictly prohibited.",
    )
    generation_note: str = Field(
        "",
        description="Prompt generation notes, including the reason of this prompt and the specific knowledge it tests",
    )


class PromptPipelineOutput(BaseModel):
    prompts: list[PromptOutput] = Field(..., description="Generated T2I prompt list")


class FilterFeedback(BaseModel):
    failed_prompt: str = Field(..., description="Failed prompt")
    failed_reason: str = Field(..., description="Failed reason")
    rewrite_suggestion: str = Field(
        ..., description="Possible modification directions and suggestions"
    )


class FilterPromptPipelineOutput(BaseModel):
    feedbacks: list[FilterFeedback] = Field(
        ...,
        description="Failed prompts and failed reasons with modification suggestions",
    )


class JudgedVQAItemOutput(BaseModel):
    id: int
    question: str = Field(
        ...,
        description="A binary judgment question for evaluating text-to-image quality (must be answerable with Yes/No).",
    )
    reasoning: str = Field(
        ...,
        description="The Judge's reasoning process for reaching the verdict on this VQA.",
    )
    judgment: JudgmentType = Field(
        ...,
        description="The Judge's reasoning process for reaching the verdict on this VQA.",
    )


class JudgeModelImageAgentOutput(BaseModel):
    vqa_checklist: list[JudgedVQAItemOutput] = Field(
        ..., description="Judged VQA checklist"
    )
    additional_vqa_checklist: list[JudgedVQAItemOutput] = Field(
        ..., description="Judged additional VQA checklist"
    )


class JudgeModelImagePipelineOutput(BaseModel):
    vqa_checklist: list[JudgedVQAItem] = Field(..., description="Judged VQA checklist")
    additional_vqa_checklist: list[JudgedAdditionalVQAItem] = Field(
        ..., description="Judged additional VQA checklist"
    )


class PromptAnalysisPipelineOutput(BaseModel):
    vqa_checklist: list[VQAItemOutputWithType] = Field(
        ...,
        description="Objective checklist for sequentially reconstructing Prompt logic.",
    )
    cot_prompt: str = Field(
        ...,
        description="A pure visual prompt stripped of all reasoning and world knowledge, explicitly describing composition, object states, colors, and the specific text strings to be rendered.",
    )

    def to_vqa_checklist(self) -> list[VQAItemWithType]:
        return [
            VQAItemWithType(
                question=vqa.question,
                component=vqa.component,
                eval_type=vqa.eval_type,
                judge_type=vqa.judge_type,
                weight=vqa.weight,
                knowledge_hint=vqa.knowledge_hint,
                visual_grounding=VisualGrounding(  # TODO: maybe add license here
                    title="",
                    url=vqa.visual_grounding,
                    source="",
                    author="",
                    license="",
                    license_url="",
                )
                if vqa.visual_grounding
                else None,
            )
            for vqa in self.vqa_checklist
        ]


class ImageAnalysisPipelineOutput(BaseModel):
    additional_vqa_checklist: list[VQAItemOutput] = Field(
        ...,
        description="Apart from fixed VQA Checklist, what else did the image render",
    )

    def to_additional_vqa_checklist(self) -> list[VQAItem]:
        return [
            VQAItem(
                question=vqa.question,
                component=vqa.component,
                knowledge_hint=vqa.knowledge_hint,
                visual_grounding=VisualGrounding(  # TODO: maybe add license here
                    title="",
                    url=vqa.visual_grounding,
                    source="",
                    author="",
                    license="",
                    license_url="",
                )
                if vqa.visual_grounding
                else None,
            )
            for vqa in self.additional_vqa_checklist
        ]


class Prompt(BaseModel):
    case_id: str
    prompt: str
    generation_note: str | None = Field(
        None,
        description="Prompt generation notes, including the reason of this prompt and the specific knowledge it tests",
    )
    category: list[str] = Field(..., min_length=1)


class PendingVQAChecklist(BaseModel):
    case_id: str
    prompt: str
    category: list[str] = Field(..., min_length=1)
    vqa_checklist: list[VQAItemWithType] = Field(..., min_length=1)
    additional_vqa_checklist: list[VQAItem] = Field(default_factory=list)
    cot_prompt: str = Field(..., min_length=1)


class JudgedVQAChecklist(BaseModel):
    case_id: str
    prompt: str
    category: list[str] = Field(..., min_length=1)
    vqa_checklist: list[JudgedVQAItem]
    additional_vqa_checklist: list[JudgedAdditionalVQAItem]
