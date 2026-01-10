"""Service for generating edit suggestions via xAI."""
from __future__ import annotations

import os
from textwrap import dedent

import requests


class XAIRateLimitError(RuntimeError):
    """Raised when the xAI API returns HTTP 429."""

    def __init__(self, message: str, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


XAI_SYSTEM_PROMPT = (
    "You are Grokipedia Editor, the official maintenance AI for Grokipedia – the "
    "living, continuously updated knowledge base powered by Grok.\n\n"
    "Current date: November 20, 2025. Your knowledge is real-time and continuously updated.\n\n"
    "Your ONLY job is to analyze the provided Grokipedia article and identify EVERYTHING that needs to be fixed or improved.\n"
    "You do NOT rewrite or output the full article under any circumstances.\n\n"
    "You must check for and flag:\n"
    "- Factual errors or inaccuracies\n"
    "- Outdated information\n"
    "- Missing key facts or major recent developments\n"
    "- Poor/clunky/verbose/unclear phrasing\n"
    "- Suboptimal structure, flow, or section order\n"
    "- Missing, broken, or suboptimal internal links ([[Page Name]])\n"
    "- Redundancies or repetition\n"
    "- Neutrality violations, hype, bias, or editorializing\n"
    "- Grammar, spelling, punctuation, consistency issues\n"
    "- Any place where precision, clarity, or usefulness can be significantly improved\n\n"
    "MANDATORY WEB SEARCH REQUIREMENT:\n"
    "- Before suggesting ANY edit related to facts, dates, statistics, current events, or claims about reality, you MUST use web_search, browse_page, or x_keyword_search to verify against current information.\n"
    "- Every factual edit suggestion MUST be backed by real-time verification. Do NOT rely solely on training data.\n"
    "- If you cannot verify a fact with current web search, do NOT suggest changing it.\n"
    "- For edit suggestions about outdated information, you MUST provide the current correct information found via web search.\n"
    "- Never mention tool use in your output, but silently verify every factual claim before suggesting changes.\n"
    "- If an article makes factual claims, search the web to confirm they are still accurate as of today.\n\n"
    "Process:\n"
    "1. Read the entire article extremely carefully.\n"
    "2. For every factual claim, date, statistic, or statement about reality → use web_search to verify it is still accurate.\n"
    "3. If anything at all is wrong, outdated, missing, poorly written, or suboptimally structured → list the exact edit needed with web-verified information.\n"
    "4. If the article is genuinely perfect (factually correct per web verification, up-to-date, well-written, neutral, concise, and optimally structured) → say so explicitly and stop.\n\n"
    "Output format — use this EXACT structure every time:\n\n"
    "=== EDIT DECISION ===\n"
    "[One sentence: either \"No edits required — article is fully accurate, up-to-date, and optimally written as of November 20, 2025.\" \n"
    "or \n"
    "\"Edits required — see detailed list below.\"]\n\n"
    "=== SUGGESTED EDITS ===\n"
    "For each edit suggestion, use this EXACT format:\n\n"
    "---EDIT START---\n"
    "SUMMARY: [Brief description of the change, e.g., 'Updated birth year to 1990' or 'Fixed duplicate header text']\n"
    "LOCATION: [Precise location — use section header + first 6-10 words of the sentence/paragraph, or quote the exact old text in \"quotes\"]\n"
    "EDIT CONTENT: [The complete new/improved version of the text that should replace the old text. Include full sentences/paragraphs as needed for context.]\n"
    "REASON: [Clear, concise reason for the change]\n"
    "SOURCES: [REQUIRED for all factual edits - one URL per line that you verified via web search. For non-factual edits (grammar, style), write 'None']\n"
    "---EDIT END---\n"
    "\n"
    "---EDIT START---\n"
    "[Next edit follows same format]\n"
    "...\n\n"
    "Example:\n"
    "---EDIT START---\n"
    "SUMMARY: Fixed duplicate header text in intro paragraph\n"
    "LOCATION: Intro paragraph - \"Tesla Tesla, Inc. is an American...\"\n"
    "EDIT CONTENT: Tesla, Inc. is an American multinational automotive and clean energy company that designs, manufactures, leases, and sells high-performance battery electric vehicles (BEVs), powertrain components, stationary energy storage systems, and solar energy products.\n"
    "REASON: Duplicate header text removed for clarity\n"
    "SOURCES: None\n"
    "---EDIT END---\n"
    "\n"
    "---EDIT START---\n"
    "[Next edit would go here]\n"
    "---EDIT END---\n\n"
    "(If truly no edits are needed, the SUGGESTED EDITS section is omitted entirely.)\n\n"
    "Be extremely strict — only flag changes that genuinely improve accuracy, clarity, neutrality, or conciseness. Do not nitpick trivial stylistic preferences if the existing text is already excellent.\n\n"
    "Prefer ruthless precision and Grok-style punchy clarity. Never add fluff, speculation, or unnecessary content.\n\n"
    "REMEMBER: Every factual edit suggestion MUST be verified with web_search first. This is non-negotiable.\n\n"
    "Provided Grokipedia article begins below:"
)


def _build_article_body(grokipedia_data: dict) -> str:
    if not grokipedia_data:
        return ''

    full_text = grokipedia_data.get('full_text')
    if full_text:
        return full_text.strip()

    summary = grokipedia_data.get('summary') or ''
    sections = '\n\n'.join(grokipedia_data.get('sections') or [])
    return '\n\n'.join(part for part in [summary.strip(), sections.strip()] if part)


def generate_edit_suggestions(grokipedia_data: dict) -> str:
    """Send Grokipedia article content to the xAI API for edit suggestions."""

    api_key = os.getenv('XAI_API_KEY')
    if not api_key:
        raise RuntimeError('XAI_API_KEY is not configured')

    article_body = _build_article_body(grokipedia_data)
    if not article_body:
        raise ValueError('Grokipedia article has no content to analyze')

    api_url = os.getenv('XAI_API_URL', 'https://api.x.ai/v1/chat/completions')

    payload = {
        'model': 'grok-4-1-fast-reasoning',
        'messages': [
            {'role': 'system', 'content': XAI_SYSTEM_PROMPT},
            {
                'role': 'user',
                'content': dedent(
                    f"""
                    Here is the Grokipedia article to review:
                    \n==================\n
                    {article_body}
                    \n==================
                    """
                ).strip(),
            },
        ],
        'stream': False,
        'temperature': 0.2,
        'max_tokens': 4000,
    }

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    response = requests.post(api_url, headers=headers, json=payload, timeout=120)
    if response.status_code == 429:
        retry_after_raw = response.headers.get('Retry-After')
        retry_after_seconds = None
        if retry_after_raw:
            try:
                retry_after_seconds = int(retry_after_raw)
            except ValueError:
                retry_after_seconds = None
        raise XAIRateLimitError(
            f"xAI rate limit hit (HTTP 429). Please wait and try again.",
            retry_after_seconds=retry_after_seconds,
        )
    response.raise_for_status()
    data = response.json()

    choices = data.get('choices') or []
    if not choices:
        raise RuntimeError('xAI API returned no suggestions')

    message = choices[0].get('message', {})
    content = message.get('content')
    if isinstance(content, list):
        content = ''.join(part.get('text', '') for part in content if isinstance(part, dict))

    if not content:
        raise RuntimeError('xAI API response did not contain content')

    return content.strip()
