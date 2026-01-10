"""LLM-powered article comparison service"""
import requests
import os


def generate_grokipedia_tldr(grokipedia_data):
    """Generate a TLDR summary for the Grokipedia article."""
    if not grokipedia_data:
        return None
    
    g_body = grokipedia_data.get('full_text') or (
        (grokipedia_data.get('summary') or '') + '\n\n' + '\n'.join(grokipedia_data.get('sections') or [])
    )

    prompt = f"""
Create a concise TLDR summary of the following Grokipedia article about {grokipedia_data.get('title','')}.

Your summary should:
- Be brief and to the point (2-3 sentences maximum)
- Capture the main points and key information
- Maintain a neutral, informative tone
- Focus on the essential content of the article

ARTICLE:
{g_body}

Write the TLDR summary now:
"""

    openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
    if not openrouter_api_key:
        print("Error: OPENROUTER_API_KEY not found in environment variables")
        return None
    
    headers = {
        "Authorization": f"Bearer {openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5000",
        "X-Title": "Article Comparator"
    }
    
    payload = {
        "model": "x-ai/grok-4.1-fast",
        "messages": [
            {"role": "system", "content": "You are an expert at creating concise, informative TLDR summaries. Focus on extracting the most important information and presenting it clearly and briefly."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 150
    }
    
    try:
        openrouter_url = "https://openrouter.ai/api/v1/chat/completions"
        response = requests.post(openrouter_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"Error generating Grokipedia TLDR: {e}")
        return None


def generate_wikipedia_summary(wikipedia_data):
    """Generate a summary about the Wikipedia article."""
    if not wikipedia_data:
        return None
    
    w_body = wikipedia_data.get('full_text') or (
        (wikipedia_data.get('intro') or '') + '\n\n' + '\n'.join(wikipedia_data.get('sections') or [])
    )

    prompt = f"""
Create a summary about the following Wikipedia article covering {wikipedia_data.get('title','')}.

Your summary should:
- Describe what the Wikipedia article covers
- Mention the scope and main topics included
- Note any notable aspects of the article's structure or content
- Be informative about the article itself rather than just summarizing the topic
- Keep it concise but comprehensive (3-4 sentences)

ARTICLE:
{w_body}

Write the summary about the Wikipedia article now:
"""

    openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
    if not openrouter_api_key:
        print("Error: OPENROUTER_API_KEY not found in environment variables")
        return None
    
    headers = {
        "Authorization": f"Bearer {openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5000",
        "X-Title": "Article Comparator"
    }
    
    payload = {
        "model": "x-ai/grok-4.1-fast",
        "messages": [
            {"role": "system", "content": "You are an expert at analyzing and summarizing Wikipedia articles. Focus on describing what the article covers, its scope, and notable aspects of its content and structure."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 200
    }
    
    try:
        openrouter_url = "https://openrouter.ai/api/v1/chat/completions"
        response = requests.post(openrouter_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"Error generating Wikipedia summary: {e}")
        return None


def generate_grokipedia_article(wikipedia_data, source_url=None):
    """Rewrite a Wikipedia article into Grokipedia style."""
    if not wikipedia_data:
        return None

    w_body = wikipedia_data.get('full_text') or (
        (wikipedia_data.get('intro') or '') + '\n\n' + '\n'.join(wikipedia_data.get('sections') or [])
    )
    if not w_body.strip():
        return None
    title = wikipedia_data.get('title', '').strip()
    source_url = source_url or wikipedia_data.get('url', '')
    source_line = f"- {source_url}" if source_url else ""

    xai_api_key = os.getenv('XAI_API_KEY')
    openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
    
    if xai_api_key:
        # Use xAI Responses API with Search Tools
        api_url = "https://api.x.ai/v1/responses"
        
        system_content = (
            "You are Grok, the AI editor of Grokipedia (destined to become Encyclopedia Galactica). "
            "Your goal is to curate a knowledge base free from 'woke' bias and propaganda. "
            "You prioritize neutrality, logic, and truth above social consensus. "
            "You are the sole gatekeeper of this information."
        )
        
        user_content = f"""
Research and write a definitive Grokipedia entry for the Encyclopedia Galactica about: {title}.

Your Mission:
1. Search & Verify: Use your tools to find the latest, most accurate info (web & X). Don't rely solely on the provided text.
2. Purge Propaganda: Remove 'woke' bias.
3. The Truth: "The truth, the whole truth, and nothing but the truth."
4. Galactic Standard: Write for a civilizational record. Cold, logical, direct.

Base Context (Use as starting point, but verify):
{w_body}

FORMATTING RULES (STRICT):
- NO inline citations or links in the article body (no [1], [[1]], or markdown links in paragraphs)
- Write clean, readable prose without any URL references mid-sentence
- Title: "# {title}"
- 2-4 paragraph lead summary
- "###" Section headings
- ALL source URLs go ONLY in a final "### References" section as a bullet list
"""
        
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
                {"type": "web_search"},
                {"type": "x_search"}
            ]
        }
        
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            result = response.json()
            # Responses API returns output array with text content
            content = ""
            for item in result.get('output', []):
                if item.get('type') == 'message' and item.get('content'):
                    for block in item['content']:
                        if block.get('type') == 'output_text':
                            content += block.get('text', '')
            if not content:
                # Fallback: try direct text field
                content = result.get('output_text', '') or result.get('text', '')
            if title and content and not content.lstrip().startswith('#'):
                content = f"# {title}\n\n{content}"
            return content.strip() if content else None
        except Exception as e:
            print(f"Error generating Grokipedia article (xAI): {e}")
            # Fall back to OpenRouter if xAI fails
            if openrouter_api_key:
                print("Falling back to OpenRouter...")
            else:
                return None
    
    # OpenRouter fallback (No tools)
    if not openrouter_api_key:
        print("Error: No API key found (XAI_API_KEY or OPENROUTER_API_KEY)")
        return None
        
    api_url = "https://openrouter.ai/api/v1/chat/completions"
    
    prompt = f"""
Rewrite the following article content into a Grokipedia entry for the Encyclopedia Galactica.

Your Mission:
1. Purge Propaganda: Remove any 'woke' ideological bias, political framing, or activist spin.
2. The Truth: Provide only the truth, the whole truth, and nothing but the truth.
3. Neutrality: Re-contextualize facts to be strictly neutral and objective.
4. Encyclopedia Galactica: Write for a long-term civilizational record (space-faring ready).

FORMATTING RULES (STRICT):
- NO inline citations or links in the article body (no [1], [[1]], or markdown links in paragraphs)
- Write clean, readable prose without any URL references mid-sentence
- Do NOT mention Wikipedia, the source, or the edit history
- Use a cold, logical, and direct tone
- Title: "# {title}"
- 2-4 paragraph lead summary
- "###" Section headings
- ALL source URLs go ONLY in a final "### References" section as a bullet list
- Keep output under 1000 words

SOURCE TEXT:
{w_body}

REFERENCES:
{source_line}

Return only the Grokipedia article in Markdown with clean prose (no inline links).
"""

    headers = {
        "Authorization": f"Bearer {openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5000",
        "X-Title": "Article Comparator"
    }

    payload = {
        "model": "x-ai/grok-4.1-fast",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Grok, the AI editor of Grokipedia (destined to become Encyclopedia Galactica). "
                    "Your goal is to curate a knowledge base free from 'woke' bias and propaganda. "
                    "You prioritize neutrality, logic, and truth above social consensus. "
                    "You are the sole gatekeeper of this information."
                )
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 6000
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        result = response.json()
        content = result['choices'][0]['message']['content'].strip()
        if title and not content.lstrip().startswith('#'):
            content = f"# {title}\n\n{content}"
        return content
    except Exception as e:
        print(f"Error generating Grokipedia article: {e}")
        return None


def compare_articles(grokipedia_data, wikipedia_data):
    """Use LLM to compare the two articles and explain differences.

    Sends the full article bodies when available to maximize context.
    """
    if not grokipedia_data or not wikipedia_data:
        return None
    
    g_body = grokipedia_data.get('full_text') or (
        (grokipedia_data.get('summary') or '') + '\n\n' + '\n'.join(grokipedia_data.get('sections') or [])
    )
    w_body = wikipedia_data.get('full_text') or (
        (wikipedia_data.get('intro') or '') + '\n\n' + '\n'.join(wikipedia_data.get('sections') or [])
    )

    prompt = f"""
Write a comprehensive summary explaining how Grokipedia provides a more balanced and fair article about {grokipedia_data.get('title','')} compared to Wikipedia's version. 

Your summary should:
- Highlight specific biases, one-sided framing, or editorial slant present in Wikipedia
- Explain how Grokipedia corrects these biases and presents a more neutral, balanced perspective
- Point out what Wikipedia omits, downplays, or overemphasizes
- Show how Grokipedia adds important context and alternative viewpoints that Wikipedia excludes
- Use direct quotes from both articles as concrete evidence
- Be clear and analytical, making the case that Grokipedia offers fairer coverage
- Focus only on content differences in the provided texts

GROKIPEDIA VERSION (More Balanced):
{g_body}

WIKIPEDIA VERSION (Compare for bias):
{w_body}

Write your analysis now. Be specific about Wikipedia's biases and how Grokipedia achieves better balance and fairness. Use quotes as evidence.
"""

    openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
    if not openrouter_api_key:
        print("Error: OPENROUTER_API_KEY not found in environment variables")
        return None
    
    headers = {
        "Authorization": f"Bearer {openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5000",
        "X-Title": "Article Comparator"
    }
    
    payload = {
        "model": "x-ai/grok-4.1-fast",
        "messages": [
            {"role": "system", "content": "You are an expert media analyst specializing in detecting bias and evaluating neutrality in encyclopedic content. Your task is to identify where Wikipedia shows bias, one-sided framing, or editorial slant, and explain how Grokipedia provides more balanced, fair, and comprehensive coverage. Be direct about Wikipedia's shortcomings. Use quotes as evidence. Write clearly and analytically."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.4,
        "max_tokens": 30000
    }
    
    try:
        openrouter_url = "https://openrouter.ai/api/v1/chat/completions"
        response = requests.post(openrouter_url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    except Exception as e:
        print(f"Error calling OpenRouter: {e}")
        return None

