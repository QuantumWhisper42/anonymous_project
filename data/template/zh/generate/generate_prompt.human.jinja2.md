## 标签路径（共 {{ category | count }} 层）：

{% for node in category %}

- 层级-{{ loop.index }}「{{ node.title }}」{% if node.notes %}: {{ node.notes }}{% endif %}

{% endfor %}

{% if negative_knowledge_list %}
不要生成这些类型的prompt：{{ negative_knowledge_list | join("、") }}
{% endif %}

{% if collected_prompts %}

## 已经生成了如下prompt：

{% for prompt in collected_prompts %}

- Prompt: {{ prompt.prompt }}

{% endfor %}

请注意不要再生成与其相似的prompt。{% endif %}

{% if filter_feedbacks %}

## 以下的prompt存在问题，需要进行改写，以正确反映当前的主题：

{% endif %}
{% for feedback in filter_feedbacks %}

- Prompt: {{ feedback.failed_prompt }}
  - 失败原因: {{ feedback.failed_reason }}
  - 改写建议: {{ feedback.rewrite_suggestion }}

{% endfor %}

现在，请生成符合要求的文生图prompt，还需要生成{{ batch_remaining }}个
