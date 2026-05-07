## Label Path ({{ category | count }} levels):

{% for node in category %}

- Level-{{ loop.index }} "{{ node.title }}"{% if node.notes %}: {{ node.notes }}{% endif %}

{% endfor %}

{% if negative_knowledge_list %}
Do not generate these types of prompts: {{ negative_knowledge_list | join(", ") }}
{% endif %}

{% if collected_prompts %}

## The following prompts have already been generated:

{% for prompt in collected_prompts %}

- Prompt: {{ prompt.prompt }}

{% endfor %}

Do not generate prompts similar to the above.{% endif %}

{% if filter_feedbacks %}

## The following prompts have problems and need to be rewritten to correctly reflect the current topic:

{% endif %}
{% for feedback in filter_feedbacks %}

- Prompt: {{ feedback.failed_prompt }}
  - Failure reason: {{ feedback.failed_reason }}
  - Rewrite suggestion: {{ feedback.rewrite_suggestion }}

{% endfor %}

Now, generate text-to-image prompts that meet the requirements. You still need to generate {{ batch_remaining }} prompt(s).
