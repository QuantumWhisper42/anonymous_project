## Label Path ({{ category | count }} levels):

{% for node in category %}

- Level-{{ loop.index }} "{{ node.title }}"{% if node.notes %}: {{ node.notes }}{% endif %}

{% endfor %}

## Prompt

{{ prompt }}

Now, perform a world-knowledge VQA Checklist breakdown for the Prompt and rewrite it as a CoT Prompt.
