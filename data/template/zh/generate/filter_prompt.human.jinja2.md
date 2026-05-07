## 标签路径（共 {{ category | count }} 层）：

{% for node in category %}

- 层级-{{ loop.index }}「{{ node.title }}」{% if node.notes %}: {{ node.notes }}{% endif %}

{% endfor %}

{% if negative_knowledge_list %}
不要生成这些类型的prompt：{{ negative_knowledge_list | join("、") }}
{% endif %}

## 现在，请对以下的文生图prompt，进行筛选和过滤：

{% for prompt in current_prompts %}

- Prompt: {{ prompt.prompt }}

{% endfor %}
