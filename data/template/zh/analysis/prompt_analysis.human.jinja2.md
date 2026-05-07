## 标签路径（共 {{ category | count }} 层）：

{% for node in path %}

- 层级-{{ loop.index }}「{{ node.title }}」{% if node.notes %}: {{ node.notes }}{% endif %}

{% endfor %}

## Prompt

{{ prompt }}

现在，请对 Prompt 进行世界知识VQA Checklist拆解和CoT Prompt改写
