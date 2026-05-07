import re
from functools import lru_cache
from pathlib import Path
from minijinja import Environment
from lib.types import Language

JINJA_SUFFIX_RE = re.compile(r"\.(jinja2?|j2)(\.|$)", re.IGNORECASE)

TEMPLATE_DIR = Path(__file__).parent.parent.parent / "data" / "template"


def is_jinja_template(str_or_path: str | Path) -> bool:
    return (
        False
        if isinstance(str_or_path, str)
        else bool(JINJA_SUFFIX_RE.search(str_or_path.name))
    )


def get_template_file(name: str, language: Language) -> Path:
    return TEMPLATE_DIR / language / name


@lru_cache
def load_raw_file(str_or_path: str | Path) -> str:
    return (
        str_or_path
        if isinstance(str_or_path, str)
        else str_or_path.read_text(encoding="utf-8")
    )


_jinja_env = Environment()


def render_template(content: str, ctx: dict) -> str:
    return _jinja_env.render_str(content, **ctx)


def build_message_template(message_template: str | Path):
    message_template_content = load_raw_file(message_template)

    return (
        (lambda template_ctx: render_template(message_template_content, template_ctx))
        if is_jinja_template(message_template)
        else lambda _: message_template_content
    )
