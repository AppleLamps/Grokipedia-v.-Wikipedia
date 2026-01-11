"""Main application routes"""
from flask import Blueprint, render_template, request, jsonify
from app.utils.url_parser import (
    detect_source,
    convert_to_other_source,
    resolve_local_slug_if_available
)
from app.utils.sdk_manager import get_cached_client
from app.services.article_fetcher import scrape_wikipedia, fetch_grokipedia_article
from app.services.comparison_service import (
    compare_articles,
    generate_grokipedia_tldr,
    generate_grokipedia_article,
    generate_wikipedia_summary
)
from app.services.edits_service import generate_edit_suggestions, XAIRateLimitError


bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    """Serve the main HTML page"""
    return render_template('index.html')


@bp.route('/search', methods=['GET'])
def search_articles():
    """Search for Grokipedia articles by keyword - optimized for speed"""
    from app.utils.sdk_manager import is_sdk_available
    from app.utils.url_parser import detect_source, extract_article_title
    
    query = request.args.get('q', '').strip()
    limit = int(request.args.get('limit', 10))
    
    if not query:
        return jsonify({'results': []})
    
    # Check if query is a Wikipedia or Grokipedia URL - extract slug
    source = detect_source(query)
    if source in ('wikipedia', 'grokipedia'):
        slug = extract_article_title(query)
        if slug:
            # Search for this exact slug
            query = slug.replace('_', ' ')
    
    if not is_sdk_available():
        return jsonify({'error': 'SDK not available'}), 500
    
    try:
        client = get_cached_client()
        if not client:
            return jsonify({'error': 'SDK client unavailable'}), 500

        query_length = len(query)
        if query_length <= 2:
            prefix_query = query.replace(' ', '_')
            slugs = client.list_available_articles(prefix=prefix_query, limit=limit)
        else:
            # Use exact search first, fall back to fuzzy only if needed
            slugs = client.search_slug(query, limit=limit, fuzzy=False)

            # Only do fuzzy search if exact search returns too few results
            if len(slugs) < limit:
                fuzzy_slugs = client.search_slug(query, limit=limit, fuzzy=True)
                # Merge without duplicates, exact matches first
                seen = set(slugs)
                for slug in fuzzy_slugs:
                    if slug not in seen and len(slugs) < limit:
                        slugs.append(slug)
                        seen.add(slug)
        
        # Convert to response format directly - SDK already sorted by relevance
        results = [
            {'slug': slug, 'title': slug.replace('_', ' '), 'url': f"https://grokipedia.com/page/{slug}"}
            for slug in slugs
        ]
        
        return jsonify({'results': results})
    except Exception as e:
        print(f"Error searching articles: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/compare', methods=['POST'])
def compare():
    """Handle article comparison requests"""
    try:
        data = request.json
        article_url = data.get('article_url', '').strip()
        
        if not article_url:
            return jsonify({'error': 'Please provide an article URL'}), 400
        
        # Detect source and get the other URL
        source = detect_source(article_url)
        if not source:
            # If it's not a URL from known domains, try to interpret it as a name/slug using local index
            # This lets users paste "Comcast" or a near match and we resolve to a Grokipedia page
            resolved_slug = resolve_local_slug_if_available(article_url)
            if resolved_slug:
                article_url = f"https://grokipedia.com/page/{resolved_slug}"
                source = 'grokipedia'
            else:
                return jsonify({'error': 'Invalid input. Provide a Grokipedia/Wikipedia URL or a recognizable article name.'}), 400
        
        other_url = convert_to_other_source(article_url)
        if not other_url:
            return jsonify({'error': 'Could not extract article title from URL'}), 400
        
        results = {}
        
        # Fetch article from the source provided
        if source == 'grokipedia':
            grokipedia_data = fetch_grokipedia_article(article_url)
            results['grokipedia'] = grokipedia_data
            results['grokipedia_url'] = article_url
            
            # Fetch corresponding Wikipedia article
            wikipedia_data = scrape_wikipedia(other_url)
            results['wikipedia'] = wikipedia_data
            results['wikipedia_url'] = other_url
        else:  # wikipedia
            wikipedia_data = scrape_wikipedia(article_url)
            results['wikipedia'] = wikipedia_data
            results['wikipedia_url'] = article_url
            
            # Fetch corresponding Grokipedia article
            grokipedia_data = fetch_grokipedia_article(other_url)
            results['grokipedia'] = grokipedia_data
            results['grokipedia_url'] = other_url
        
        # Compare articles if both were found
        if grokipedia_data and wikipedia_data:
            comparison = compare_articles(grokipedia_data, wikipedia_data)
            results['comparison'] = comparison
            
            # Generate TLDR for Grokipedia article
            grokipedia_tldr = generate_grokipedia_tldr(grokipedia_data)
            if grokipedia_tldr:
                grokipedia_data['tldr'] = grokipedia_tldr
            
            # Generate summary about Wikipedia article
            wikipedia_summary = generate_wikipedia_summary(wikipedia_data)
            if wikipedia_summary:
                wikipedia_data['article_summary'] = wikipedia_summary
        else:
            results['comparison'] = None
            missing = []
            if not grokipedia_data:
                missing.append('Grokipedia article not found')
            if not wikipedia_data:
                missing.append('Wikipedia article not found')
            results['comparison_error'] = ' and '.join(missing) if missing else None
        
        return jsonify(results)
        
    except Exception as e:
        print(f"Error in compare endpoint: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@bp.route('/edits', methods=['POST'])
def edits():
    """Handle edit suggestion requests for Grokipedia articles."""
    try:
        data = request.json or {}
        article_url = (data.get('article_url') or '').strip()

        if not article_url:
            return jsonify({'error': 'Please provide an article URL'}), 400

        source = detect_source(article_url)
        grokipedia_url = None

        if source == 'grokipedia':
            grokipedia_url = article_url
        elif source == 'wikipedia':
            grokipedia_url = convert_to_other_source(article_url)
            if not grokipedia_url:
                return jsonify({'error': 'Could not extract Grokipedia slug from URL'}), 400
        else:
            resolved_slug = resolve_local_slug_if_available(article_url)
            if resolved_slug:
                grokipedia_url = f"https://grokipedia.com/page/{resolved_slug}"
            else:
                return jsonify({'error': 'Provide a Grokipedia URL or recognizable article name'}), 400

        grokipedia_data = fetch_grokipedia_article(grokipedia_url)
        if not grokipedia_data:
            return jsonify({'error': 'Grokipedia article not found'}), 404

        grokipedia_tldr = generate_grokipedia_tldr(grokipedia_data)
        if grokipedia_tldr:
            grokipedia_data['tldr'] = grokipedia_tldr

        edits_output = generate_edit_suggestions(grokipedia_data)

        return jsonify({
            'grokipedia': grokipedia_data,
            'grokipedia_url': grokipedia_url,
            'edits': edits_output
        })

    except XAIRateLimitError as e:
        payload = {'error': str(e)}
        if getattr(e, 'retry_after_seconds', None) is not None:
            payload['retry_after_seconds'] = e.retry_after_seconds
        return jsonify(payload), 429
    except (RuntimeError, ValueError) as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"Error in edits endpoint: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@bp.route('/create', methods=['POST'])
def create():
    """Handle Grokipedia article creation from Wikipedia."""
    from app.utils.sdk_manager import is_sdk_available
    from app.utils.url_parser import extract_article_title
    
    try:
        data = request.json or {}
        article_url = (data.get('article_url') or '').strip()

        if not article_url:
            return jsonify({'error': 'Please provide a Wikipedia URL'}), 400

        source = detect_source(article_url)
        wikipedia_url = None
        search_slug = None

        if source == 'wikipedia':
            wikipedia_url = article_url
            search_slug = extract_article_title(article_url)
        elif source == 'grokipedia':
            wikipedia_url = convert_to_other_source(article_url)
            search_slug = extract_article_title(article_url)
            if not wikipedia_url:
                return jsonify({'error': 'Could not extract Wikipedia title from URL'}), 400
        else:
            resolved_slug = resolve_local_slug_if_available(article_url)
            if resolved_slug:
                search_slug = resolved_slug
                wikipedia_url = convert_to_other_source(
                    f"https://grokipedia.com/page/{resolved_slug}"
                )
            else:
                # Use the input directly as the search term
                search_slug = article_url.replace(' ', '_')
                # Try to construct a Wikipedia URL from the input
                wikipedia_url = f"https://en.wikipedia.org/wiki/{search_slug}"

        # Check if Grokipedia already has this article
        if search_slug and is_sdk_available():
            try:
                client = get_cached_client()
                if client:
                    # Search for exact match first
                    search_term = search_slug.replace('_', ' ')
                    slugs = client.search_slug(search_term, limit=5, fuzzy=False)
                    
                    # Check for exact match (case-insensitive)
                    exact_match = None
                    normalized_search = search_slug.lower().replace('_', ' ')
                    for slug in slugs:
                        if slug.lower().replace('_', ' ') == normalized_search:
                            exact_match = slug
                            break
                    
                    if exact_match:
                        # Grokipedia already has this article - fetch it
                        grokipedia_url = f"https://grokipedia.com/page/{exact_match}"
                        grokipedia_data = fetch_grokipedia_article(grokipedia_url)
                        
                        if grokipedia_data:
                            # Generate TLDR for the existing article
                            grokipedia_tldr = generate_grokipedia_tldr(grokipedia_data)
                            if grokipedia_tldr:
                                grokipedia_data['tldr'] = grokipedia_tldr
                            
                            return jsonify({
                                'existing_article': True,
                                'grokipedia': grokipedia_data,
                                'grokipedia_url': grokipedia_url,
                                'message': f'Grokipedia already has an article on "{exact_match.replace("_", " ")}"'
                            })
            except Exception as e:
                print(f"Error checking for existing article: {e}")
                # Continue to generation if check fails

        # No existing article found - generate a new one
        wikipedia_data = scrape_wikipedia(wikipedia_url)
        if not wikipedia_data:
            return jsonify({'error': 'Wikipedia article not found'}), 404

        grokipedia_draft = generate_grokipedia_article(wikipedia_data, wikipedia_url)
        if not grokipedia_draft:
            return jsonify({'error': 'Failed to generate Grokipedia draft'}), 502

        return jsonify({
            'existing_article': False,
            'wikipedia': wikipedia_data,
            'wikipedia_url': wikipedia_url,
            'grokipedia_draft': grokipedia_draft
        })

    except Exception as e:
        print(f"Error in create endpoint: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

