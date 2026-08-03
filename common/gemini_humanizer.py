"""
common/gemini_humanizer.py — Gemini API Native Integration for Humanization Stage.

Replaces NotebookLMClient web-scraping with Google GenAI SDK (google-genai).
Prevents silent degradation and refusal text leaks into book artifacts.
"""

import json
import logging
import os
import re
import time
from typing import Optional, List, Dict, Any

from google import genai
from google.genai import types
from google.genai.errors import APIError, ClientError, ServerError
from pydantic import BaseModel, Field

logger = logging.getLogger("gemini_humanizer")


class HumanizationResult(BaseModel):
    refusal_detected: bool = Field(
        description="Set to true ONLY if you cannot process the text due to lack of context or understanding."
    )
    refusal_reason: str = Field(
        default="",
        description="If refusal_detected is true, briefly state why. Otherwise, leave empty."
    )
    humanized_markdown: str = Field(
        default="",
        description="The final rewritten markdown text according to the system instructions. Leave empty if refusal_detected is true."
    )


class SemanticGenerationError(Exception):
    """Raised when silent degradation, refusal, or severe length degradation is detected."""
    pass


class GeminiAPIKeyMissingError(Exception):
    """Raised when Gemini API key is missing from config and environment."""
    pass


SYSTEM_INSTRUCTION = """You are the lead maintainer and original architect of the software project documented in the user's text. Your task is to rewrite the provided technical source text into a continuous, engaging chapter for a printed book.

STRICT CONSTRAINTS:
1. Narrative Voice: Address the reader directly using first-person plural ("we built it so that...", "we designed it this way because...").
2. Formatting: Output ONLY the finished chapter in plain Markdown. DO NOT wrap your entire response in ```markdown ... ``` fences.
3. No Sourcing Apparatus: DO NOT include any citation markers, footnote numbers, or bracketed references (completely remove [1], [2], etc.). Output continuous prose.
4. Opening: Start with exactly 1-2 sentences orienting the reader on why this chapter matters.
5. Technical Accuracy: Preserve every fact, field name, default value, code sample, and diagram EXACTLY as given. Preserve all internal code blocks character-for-character.
6. Length Constraint: Ensure the generated text length remains strictly within +/- 20% of the original source length."""


def validate_output(source_text: str, result: HumanizationResult) -> str:
    """
    Validates model output against structured refusal flags, length ratios,
    and fallback refusal patterns.
    """
    if result.refusal_detected:
        raise SemanticGenerationError(f"Model refused generation: {result.refusal_reason or 'No reason provided'}")

    out_text = result.humanized_markdown
    if not out_text or not out_text.strip():
        raise SemanticGenerationError("Model returned empty humanized_markdown content.")

    # Remove accidental outer markdown fence wrapping if present despite prompt
    out_text_trimmed = out_text.strip()
    if out_text_trimmed.startswith("```markdown") and out_text_trimmed.endswith("```"):
        out_text = out_text_trimmed[11:-3].strip()
    elif out_text_trimmed.startswith("```") and out_text_trimmed.endswith("```"):
        out_text = out_text_trimmed[3:-3].strip()

    # Heuristic Check 1: Length degradation
    # If output is less than 40% of source length or less than 200 chars for multi-paragraph sources
    if len(out_text) < len(source_text) * 0.4 or (len(source_text) >= 500 and len(out_text) < 200):
        raise SemanticGenerationError(
            f"Severe length degradation detected (Output {len(out_text)} chars vs Source {len(source_text)} chars)."
        )

    # Heuristic Check 2: Known refusal patterns in output prefix
    refusal_patterns = [
        r"(?i)I'm sorry",
        r"(?i)I am sorry",
        r"(?i)couldn't find enough context",
        r"(?i)could not find enough context",
        r"(?i)I cannot fulfill",
        r"(?i)as an AI language model",
    ]
    prefix = out_text[:500]
    for pattern in refusal_patterns:
        if re.search(pattern, prefix):
            raise SemanticGenerationError(f"Refusal pattern detected in text matching: '{pattern}'")

    return out_text


class GeminiHumanizer:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-3.6-flash",
        global_settings_path: str = "global_settings.json",
    ):
        self.model_name = model_name
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")

        if not self.api_key:
            # Try loading from global_settings.json
            repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            possible_paths = [
                global_settings_path,
                os.path.join(repo_dir, global_settings_path),
            ]
            for p in possible_paths:
                if os.path.exists(p):
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            settings = json.load(f)
                            self.api_key = settings.get("gemini_api_key")
                            if self.api_key:
                                break
                    except Exception:
                        pass

        if not self.api_key:
            raise GeminiAPIKeyMissingError(
                "Gemini API key not found in GEMINI_API_KEY environment variable or global_settings.json 'gemini_api_key'."
            )

        # Configure retry options
        retry_config = types.HttpRetryOptions(
            attempts=6,
            initial_delay=5.0,
            max_delay=65.0,
            http_status_codes=[429, 500, 502, 503, 504],
        )

        self.client = genai.Client(
            api_key=self.api_key,
            http_options=types.HttpOptions(retry_options=retry_config),
        )

        self.safety_settings = [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
        ]

    def humanize_chapter(self, source_content: str, title: str = "") -> str:
        """
        Humanizes a single chapter content using Gemini API with structured schema.
        Raises SemanticGenerationError if refusal or degradation occurs.
        """
        prompt = f"Chapter title: {title}\n\nContent:\n{source_content}" if title else source_content

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=HumanizationResult,
                safety_settings=self.safety_settings,
                temperature=0.3,
            ),
        )

        if response.candidates and response.candidates[0].finish_reason != "STOP":
            finish_reason = response.candidates[0].finish_reason
            raise SemanticGenerationError(f"Generation blocked. Finish reason: {finish_reason}")

        result_obj: Optional[HumanizationResult] = response.parsed
        if not result_obj:
            raise SemanticGenerationError("Failed to parse structured JSON output from Gemini response.")

        return validate_output(source_content, result_obj)


def stage_humanize(book_dir: str, config: dict, manifest: list) -> str:
    """
    Stage function compatible with run_book_pipeline.py contract.
    Reads manifest, calls GeminiHumanizer for each chapter, validates output,
    and writes to book_dir/humanized/.
    """
    model_name = config.get("gemini_model", config.get("model_name", "gemini-3.6-flash"))
    api_key = config.get("gemini_api_key")

    humanizer = GeminiHumanizer(api_key=api_key, model_name=model_name)

    humanized_dir = os.path.join(book_dir, "humanized")
    os.makedirs(humanized_dir, exist_ok=True)

    for entry in manifest:
        out_name = f"{entry['index']:03d}_{os.path.basename(entry['source_rel'])}"
        out_path = os.path.join(humanized_dir, out_name)

        if os.path.exists(out_path):
            logger.info(f"humanize: {out_name} already exists, skipping (resume).")
            continue

        src_path = os.path.join(book_dir, "source_docs", entry["manifest_file"])
        with open(src_path, "r", encoding="utf-8") as f:
            source_content = f.read()

        title = os.path.splitext(os.path.basename(entry["source_rel"]))[0]

        try:
            final_markdown = humanizer.humanize_chapter(source_content, title=title)
        except Exception as e:
            logger.error(f"Gemini humanize failed on {entry['source_rel']}: {e}")
            raise SemanticGenerationError(f"humanize failed on {entry['source_rel']}: {e}") from e

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(final_markdown)

        logger.info(f"humanize: wrote {out_name} ({len(final_markdown)} chars)")

    return humanized_dir
