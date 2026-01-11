"""Article fetching services for Wikipedia and Grokipedia"""
import requests
import os
from urllib.parse import urlparse
from app.utils.url_parser import extract_article_title
from app.utils.sdk_manager import get_sdk_client, is_sdk_available, ArticleNotFound, RequestError

# Firecrawl API configuration
FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY', 'fc-bb448f06d5394f32a108a8c24deb4f0e')
FIRECRAWL_API_URL = "https://api.firecrawl.dev/v1/scrape"


def scrape_with_firecrawl(url):
    """Scrape a URL using Firecrawl API and return clean markdown."""
    try:
        payload = {
            "url": url,
            "onlyMainContent": True,
            "formats": ["markdown"]
        }
        
        headers = {
            "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(FIRECRAWL_API_URL, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        if data.get('success') and data.get('data'):
            return {
                'markdown': data['data'].get('markdown', ''),
                'title': data['data'].get('metadata', {}).get('title', ''),
                'description': data['data'].get('metadata', {}).get('description', ''),
                'url': url
            }
        return None
    except Exception as e:
        print(f"Firecrawl error: {e}")
        return None


def scrape_wikipedia(url):
    """Fetch content from Wikipedia using official APIs for reliability.

    Returns dict with title, intro, sections (list[str]), url, and full_text (entire plaintext article).
    """
    try:
        headers = {
            'User-Agent': 'Grokipedia-Comparator/1.0 (contact: example@example.com)'
        }

        # Extract the page title from URL
        title = extract_article_title(url)
        if not title:
            return None

        # 1) Fetch summary via REST API
        summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
        summary_resp = requests.get(summary_url, headers=headers, timeout=30)
        if summary_resp.status_code == 404:
            return None
        summary_resp.raise_for_status()
        summary_data = summary_resp.json()
        title_text = summary_data.get('title') or title.replace('_', ' ')
        intro_text = summary_data.get('extract', '').strip()

        # 2) Fetch sections via Action API
        sections_url = (
            "https://en.wikipedia.org/w/api.php?action=parse&prop=sections&format=json&page="
            + title
        )
        sections_resp = requests.get(sections_url, headers=headers, timeout=30)
        sections = []
        if sections_resp.ok:
            try:
                sections_json = sections_resp.json()
                for s in sections_json.get('parse', {}).get('sections', [])[:10]:
                    line = s.get('line')
                    if line and line.lower() not in {"references", "external links", "see also", "notes"}:
                        sections.append(line)
            except Exception:
                pass

        # 3) Fetch full plaintext extract for comparison context
        extract_url = (
            "https://en.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&redirects=1&format=json&titles="
            + title
        )
        full_text = ''
        extract_resp = requests.get(extract_url, headers=headers, timeout=30)
        if extract_resp.ok:
            try:
                q = extract_resp.json()
                pages = q.get('query', {}).get('pages', {})
                if pages:
                    first = next(iter(pages.values()))
                    full_text = (first.get('extract') or '').strip()
            except Exception:
                pass

        return {
            'title': title_text,
            'intro': intro_text,
            'sections': sections[:5],
            'url': url,
            'full_text': full_text
        }
    except Exception as e:
        print(f"Error fetching Wikipedia via API: {e}")
        return None


def fetch_grokipedia_article(url):
    """Fetch Grokipedia article using Firecrawl API.

    Uses Firecrawl to get clean markdown content from grokipedia.com.
    Falls back to SDK if Firecrawl fails.
    """
    # Try Firecrawl first for clean markdown
    firecrawl_result = scrape_with_firecrawl(url)
    if firecrawl_result and firecrawl_result.get('markdown'):
        markdown = firecrawl_result['markdown']
        title = firecrawl_result.get('title', '')
        
        # Clean up title - remove " | Grokipedia" suffix if present
        if ' | Grokipedia' in title:
            title = title.split(' | Grokipedia')[0].strip()
        elif ' - Grokipedia' in title:
            title = title.split(' - Grokipedia')[0].strip()
        
        # Extract summary from first paragraph of markdown
        lines = markdown.split('\n')
        summary = ''
        for line in lines:
            line = line.strip()
            # Skip headers, empty lines, and short lines
            if line and not line.startswith('#') and len(line) > 100:
                summary = line[:500]  # First substantial paragraph
                break
        
        return {
            'title': title,
            'summary': summary,
            'sections': [],  # Firecrawl doesn't provide TOC separately
            'url': url,
            'full_text': markdown  # Clean markdown!
        }
    
    # Fallback to SDK if Firecrawl fails
    print("Firecrawl failed, falling back to SDK...")
    if not is_sdk_available():
        print("Grokipedia SDK not available")
        return None

    try:
        # Extract slug from URL (format: https://grokipedia.com/page/Article_Name)
        parsed = urlparse(url)
        slug = parsed.path.split('/page/')[-1].strip('/')
        if not slug:
            return None

        client = get_sdk_client()
        try:
            article = client.get_article(slug)
            return {
                'title': article.title,
                'summary': article.summary,
                'sections': article.table_of_contents[:5],
                'url': str(article.url),
                'full_text': article.full_content
            }
        except ArticleNotFound:
            resolved_slug = client.find_slug(slug)
            if resolved_slug and resolved_slug != slug:
                try:
                    article = client.get_article(resolved_slug)
                    return {
                        'title': article.title,
                        'summary': article.summary,
                        'sections': article.table_of_contents[:5],
                        'url': str(article.url),
                        'full_text': article.full_content
                    }
                except (ArticleNotFound, RequestError):
                    print(f"Could not fetch article even after resolving slug: {resolved_slug}")
                    return None
            else:
                print(f"Article not found: {slug}")
                return None
        except RequestError as e:
            print(f"Error fetching Grokipedia article: {e}")
            return None
        finally:
            client.close()
    except Exception as e:
        print(f"Error initializing SDK or fetching article: {e}")
        return None

