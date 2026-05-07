## 标签路径（共 {{ category | count }} 层）：

{% for node in category %}

- 层级-{{ loop.index }}「{{ node.title }}」{% if node.notes %}: {{ node.notes }}{% endif %}

{% endfor %}

## Prompt

{{ prompt }}

## 已有 VQA Checklist:

{{ vqa_checklist }}

现在，请对 Prompt 和图片补充额外的世界知识VQA Checklist拆解
