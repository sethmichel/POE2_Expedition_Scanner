"""Transcribes reward names from a screenshot with Claude."""
import base64
import io
import json
from pathlib import Path

import anthropic

PROMPT = (
    "This is a cropped screenshot of the Expedition reward list in Path of Exile 2. "
    "Each row is one reward option, with its text right-aligned on the row. "
    "Ignore the rune symbol icons; only read the text. "
    "Transcribe the text of every row whose text is fully visible, top to bottom, "
    "exactly as displayed, including any quantity prefix like '3x' and any label "
    "prefix like 'Support:' or 'Skill:'. Skip rows whose text is cut off. "
    "Do not guess, correct, or add names."
)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["items"],
    "additionalProperties": False,
}


class ItemReader:
    def __init__(self, api_key_path, model):
        path = Path(api_key_path)
        if not path.is_file():
            raise FileNotFoundError(f"Claude API key file not found: {path}")
        api_key = path.read_text(encoding="utf-8").strip()
        if not api_key:
            raise ValueError(f"Claude API key file is empty: {path}")
        self.client = anthropic.Anthropic(api_key=api_key, timeout=30.0, max_retries=1)
        self.model = model

    def read(self, image):
        """Return the reward lines visible in a PIL image, top to bottom."""
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        image_data = base64.standard_b64encode(buffer.getvalue()).decode("utf-8")

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": image_data},
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }],
            output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        )
        if response.stop_reason != "end_turn":
            raise RuntimeError(f"Claude stopped early ({response.stop_reason})")
        text = next(block.text for block in response.content if block.type == "text")
        return [line.strip() for line in json.loads(text)["items"] if line.strip()]
