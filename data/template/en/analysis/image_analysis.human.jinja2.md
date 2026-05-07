## Label Path ({{ category | count }} levels):

{% for node in category %}

- Level-{{ loop.index }} "{{ node.title }}"{% if node.notes %}: {{ node.notes }}{% endif %}

{% endfor %}

## Prompt

{{ prompt }}

## Existing VQA Checklist:

{{ vqa_checklist }}

Now, supplement the Prompt and image with additional world-knowledge VQA Checklist breakdowns.
