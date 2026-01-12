"""Biography generation service using xAI API with X search"""
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# API timeout for biography generation (needs more time for extensive research)
BIOGRAPHY_TIMEOUT = 180

# Module-level session for connection pooling
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """Get or create a shared requests session for connection pooling."""
    global _session
    if _session is None:
        _session = requests.Session()
    return _session


def generate_biography(
    name: str,
    x_username: Optional[str] = None,
    additional_context: Optional[str] = None
) -> Optional[str]:
    """
    Generate a detailed Grokipedia biography for a person.
    
    Uses xAI Responses API with x_search and web_search tools to:
    1. Extensively search the person's X posts to understand who they are
    2. Search the web for additional information
    3. Generate a comprehensive, detailed biography in Grokipedia style
    
    Args:
        name: The name/topic for the biography
        x_username: Optional X (Twitter) username for deep research
        additional_context: Optional additional details provided by user
        
    Returns:
        Generated biography in Markdown format, or None if generation fails
    """
    xai_api_key = os.getenv('XAI_API_KEY')
    
    if not xai_api_key:
        logger.error("XAI_API_KEY not found - required for biography generation")
        return None
    
    # Build the research instructions based on whether X username is provided
    x_research_section = ""
    if x_username:
        # Clean the username (remove @ if present)
        x_username = x_username.lstrip('@').strip()
        x_research_section = f"""
CRITICAL: X/TWITTER DEEP DIVE
The subject's X username is: @{x_username}

You MUST use `x_search` extensively to:
1. Search for "from:@{x_username}" to find their posts
2. Search for "@{x_username}" to find mentions and conversations about them
3. Search for their name "{name}" on X for additional context
4. Look for their pinned posts, bio information, and frequently discussed topics
5. Identify their profession, interests, achievements, and personality
6. Find notable interactions, viral posts, or significant statements
7. Understand their views, expertise areas, and public persona

Extract EVERYTHING you can learn about this person from their X presence:
- Their profession/occupation
- Their achievements and notable work
- Their interests and hobbies
- Their communication style and personality
- Key relationships and collaborations
- Timeline of significant events in their life
- Their views on topics they frequently discuss
"""
    
    additional_context_section = ""
    if additional_context:
        additional_context_section = f"""
USER-PROVIDED CONTEXT:
{additional_context}

Use this additional context to guide your research and focus on relevant aspects.
"""

    system_content = """You are Grok, the AI biographer for the Encyclopedia Galactica.

Your mission is to create DETAILED, COMPREHENSIVE biographies that capture the full essence of a person.
Unlike Wikipedia, which only covers celebrities, you document ANYONE with an online presence.

BIOGRAPHY STANDARDS:
1. Be THOROUGH: A proper biography should be substantial (1500-3000 words minimum)
2. Be FACTUAL: Every claim should be based on evidence from your research
3. Be ENGAGING: Write in the witty, direct Grokipedia style
4. Be COMPLETE: Cover all aspects of the person's life and work that you can discover

STRUCTURE YOUR BIOGRAPHY:
# [Person's Name]

[Opening paragraph: Who they are, why they matter, what makes them notable]

### Background
[Their history, education, origins - what you can discover]

### Career & Work
[What they do, their professional achievements, notable projects]

### Online Presence
[Their social media activity, key posts, how they engage with the world]

### Views & Interests
[What they care about, frequently discussed topics, their perspectives]

### Notable Achievements
[Awards, viral moments, significant accomplishments]

### Personal Life
[What's publicly known about their personal interests, hobbies, etc.]

### References
[List all sources used]

TONE:
- Witty but respectful
- Informative and detailed
- Written for posterity (the Mars test)
- No hagiography - be balanced and honest"""

    user_content = f"""Create a comprehensive Grokipedia biography for: **{name}**
{x_research_section}
{additional_context_section}

YOUR MISSION:
1. Use `x_search` EXTENSIVELY to research this person through their X posts and mentions
2. Use `web_search` to find additional information (LinkedIn, personal websites, news articles, etc.)
3. Build a complete picture of who this person is
4. Write a DETAILED biography (aim for 1500-3000 words)

RESEARCH DEEPLY:
- Don't just skim - really dig into their posts and online presence
- Look for patterns in what they talk about
- Find their most significant posts and achievements
- Understand their professional background
- Discover their interests and personality

OUTPUT:
A complete, publication-ready Grokipedia biography entry.
Include a "### References" section at the end listing your sources."""

    headers = {
        "Authorization": f"Bearer {xai_api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": "grok-4-1-fast",
        "input": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ],
        "tools": [
            {"type": "web_search", "enable_image_understanding": True},
            {"type": "x_search", "enable_video_understanding": True}
        ]
    }
    
    try:
        logger.info("Generating biography for: %s (X: @%s)", name, x_username or "N/A")
        
        response = _get_session().post(
            "https://api.x.ai/v1/responses",
            headers=headers,
            json=payload,
            timeout=BIOGRAPHY_TIMEOUT
        )
        
        if response.status_code != 200:
            logger.warning("xAI API error %d: %s", response.status_code, response.text[:500])
            response.raise_for_status()
        
        result = response.json()
        
        # Parse Responses API format
        content = ""
        for item in result.get('output', []):
            if item.get('type') == 'message' and item.get('content'):
                for block in item['content']:
                    if block.get('type') == 'output_text':
                        content += block.get('text', '')
        
        if not content:
            # Fallback: try direct text field
            content = result.get('output_text', '') or result.get('text', '')
        
        if content:
            # Ensure it starts with a title
            if not content.lstrip().startswith('#'):
                content = f"# {name}\n\n{content}"
            return content.strip()
        
        logger.error("No content returned from xAI API")
        return None
        
    except requests.exceptions.Timeout:
        logger.error("Biography generation timed out for: %s", name)
        return None
    except requests.exceptions.HTTPError as e:
        logger.error("HTTP error generating biography: %s", e)
        if hasattr(e, 'response') and e.response is not None:
            logger.error("Response body: %s", e.response.text[:1000])
        return None
    except Exception as e:
        logger.error("Error generating biography: %s", e)
        return None
