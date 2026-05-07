{% if category %}
## 标签路径（共 {{ category | count }} 层）：

{% for node in category %}
- 层级-{{ loop.index }}「{{ node.title }}」{% if node.notes %}: {{ node.notes }}{% endif %}
{% endfor %}
{% endif %}

## Prompt: 
{{ prompt }}

{% if vqa_checklist %}
## VQA Checklist:
{{ vqa_checklist }}
{% endif %}

{% if additional_vqa_checklist %}
## 额外 VQA Checklist:
{{ additional_vqa_checklist }}
{% endif %}