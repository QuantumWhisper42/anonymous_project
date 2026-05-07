## Label Path ({{ category | count }} levels):

{% for node in category %}

- Level-{{ loop.index }} "{{ node.title }}"{% if node.notes %}: {{ node.notes }}{% endif %}

{% endfor %}

{% if negative_knowledge_list %}
Do not generate these types of prompts: {{ negative_knowledge_list | join(", ") }}
{% endif %}

## Now, screen and filter the following text-to-image prompts:

{% for prompt in current_prompts %}

- Prompt: {{ prompt.prompt }}

{% endfor %}
