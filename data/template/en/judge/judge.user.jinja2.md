{% if category %}
## Label Path ({{ category | count }} levels):

{% for node in category %}
- Level-{{ loop.index }} "{{ node.title }}"{% if node.notes %}: {{ node.notes }}{% endif %}
{% endfor %}
{% endif %}

## Prompt: 
{{ prompt }}

{% if vqa_checklist %}
## VQA Checklist:
{{ vqa_checklist }}
{% endif %}

{% if additional_vqa_checklist %}
## Additional VQA Checklist:
{{ additional_vqa_checklist }}
{% endif %}