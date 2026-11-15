"""Optional: write a YouTube title/description/tags from the script with Claude.

Needs `pip install anthropic` and an ANTHROPIC_API_KEY (or `ant auth login`).
One call per language, roughly a few cents for a long-form script.
"""

import json
import os

from .job import Meta

DEFAULT_MODEL = os.environ.get("YT_UPLOADER_MODEL", "claude-opus-5-5")

LANG_NAMES = {"ko": "Korean", "en": "English", "ja": "Japanese", "es": "Spanish",
              "zh": "Chinese", "de": "German", "fr": "French", "pt": "Portuguese"}

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "description", "tags"],
    "additionalProperties": False,
}

PROMPT = """You write YouTube metadata for a long-form video. Below is the narration script.

Write in {lang_name}, for viewers whose native language that is (not a literal translation of another language's metadata).
- title: under 70 characters, specific and curiosity-driven, no clickbait claims the script doesn't support. No '<' or '>'.
- description: 2-3 short paragraphs summarising what the viewer will learn, then 3-6 key moments as plain bullet lines. No hashtags spam (at most 3 at the very end). No '<' or '>'. Under 3000 characters.
- tags: 8-15 search terms people in that language would type, most important first.

<script>
{script}
</script>"""


def generate_meta(script: str, language: str, model: str = DEFAULT_MODEL) -> Meta:
    import anthropic  # imported lazily so the uploader works without it

    client = anthropic.Anthropic()
    lang_name = LANG_NAMES.get(language.split("-")[0], language)
    response = client.beta.messages.create(
        model=model,
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": SCHEMA},
        },
        messages=[{"role": "user", "content": PROMPT.format(lang_name=lang_name, script=script)}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to write metadata for this script.")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Metadata response was cut off (max_tokens).")
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)
    return Meta(title=data["title"], description=data["description"], tags=data["tags"])
