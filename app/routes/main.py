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
    """Search for Grokipedia articles by keyword with smart ranking"""
    from app.utils.sdk_manager import is_sdk_available
    
    query = request.args.get('q', '').strip()
    limit = int(request.args.get('limit', 10))
    
    if not query:
        return jsonify({'results': []})
    
    if not is_sdk_available():
        print("ERROR: SDK not available")
        return jsonify({'error': 'SDK not available'}), 500
    
    try:
        # Use cached client (much faster - no reloading index)
        client = get_cached_client()
        if not client:
            print("ERROR: SDK client unavailable")
            return jsonify({'error': 'SDK client unavailable'}), 500
        
        # Use non-fuzzy search first for better relevance
        # Fuzzy search is too aggressive and returns irrelevant results
        exact_slugs = client.search_slug(query, limit=limit * 3, fuzzy=False)
        
        # If we get very few results, try fuzzy as fallback
        if len(exact_slugs) < 5:
            fuzzy_slugs = client.search_slug(query, limit=limit * 5, fuzzy=True)
            # Combine, removing duplicates
            all_slugs = exact_slugs + [s for s in fuzzy_slugs if s not in exact_slugs]
        else:
            all_slugs = exact_slugs
        
        # Smart ranking: prioritize exact matches, prefix matches, and word matches
        query_lower = query.lower()
        query_words = query_lower.split()
        
        scored_results = []
        for slug in all_slugs:
            slug_lower = slug.lower().replace('_', ' ')
            slug_words = slug_lower.split()
            score = 0
            
            # Exact match (highest priority)
            if slug_lower == query_lower:
                score = 10000
            # Starts with query (very high priority)
            elif slug_lower.startswith(query_lower):
                score = 5000
            # Any word in slug exactly matches query
            elif query_lower in slug_words:
                score = 3000
            # Contains query as substring in any word
            elif any(query_lower in word for word in slug_words):
                score = 1000
            # Contains query as whole phrase anywhere
            elif query_lower in slug_lower:
                score = 500
            # Word-based matching (less strict)
            else:
                # Check if any query word is in any slug word
                matching_words = 0
                for qw in query_words:
                    for sw in slug_words:
                        if qw in sw:
                            matching_words += 1
                            # Bonus if word starts match
                            if sw.startswith(qw):
                                matching_words += 0.5
                            break
                
                if matching_words > 0:
                    score = 100 * matching_words
                else:
                    # Very low relevance - skip
                    continue
            
            # Prefer shorter titles (more specific)
            length_penalty = len(slug_words) * 2
            score = score - length_penalty
            
            # Prefer titles where query word appears earlier
            try:
                first_match_position = next(i for i, word in enumerate(slug_words) 
                                           if query_lower in word.lower())
                position_bonus = max(0, 100 - (first_match_position * 20))
                score += position_bonus
            except StopIteration:
                pass
            
            scored_results.append({
                'slug': slug,
                'title': slug.replace('_', ' '),
                'url': f"https://grokipedia.com/page/{slug}",
                'score': score
            })
        
        # Sort by score and take top results
        scored_results.sort(key=lambda x: x['score'], reverse=True)
        results = [{'slug': r['slug'], 'title': r['title'], 'url': r['url']} 
                  for r in scored_results[:limit]]
        
        return jsonify({'results': results})
    except Exception as e:
        print(f"Error searching articles: {e}")
        import traceback
        traceback.print_exc()
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
    try:
        data = request.json or {}
        article_url = (data.get('article_url') or '').strip()

        if not article_url:
            return jsonify({'error': 'Please provide a Wikipedia URL'}), 400

        source = detect_source(article_url)
        wikipedia_url = None

        if source == 'wikipedia':
            wikipedia_url = article_url
        elif source == 'grokipedia':
            wikipedia_url = convert_to_other_source(article_url)
            if not wikipedia_url:
                return jsonify({'error': 'Could not extract Wikipedia title from URL'}), 400
        else:
            resolved_slug = resolve_local_slug_if_available(article_url)
            if resolved_slug:
                wikipedia_url = convert_to_other_source(
                    f"https://grokipedia.com/page/{resolved_slug}"
                )
            else:
                return jsonify({'error': 'Provide a Wikipedia URL or recognizable article name'}), 400

        wikipedia_data = scrape_wikipedia(wikipedia_url)
        if not wikipedia_data:
            return jsonify({'error': 'Wikipedia article not found'}), 404

        grokipedia_draft = generate_grokipedia_article(wikipedia_data, wikipedia_url)
        if not grokipedia_draft:
            return jsonify({'error': 'Failed to generate Grokipedia draft'}), 502

        return jsonify({
            'wikipedia': wikipedia_data,
            'wikipedia_url': wikipedia_url,
            'grokipedia_draft': grokipedia_draft
        })

    except Exception as e:
        print(f"Error in create endpoint: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

