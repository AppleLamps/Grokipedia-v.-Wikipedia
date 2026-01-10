/**
 * API Module - Handles all API calls
 */

/**
 * Search for articles
 * @param {string} query - Search query
 * @param {number} limit - Maximum number of results
 * @returns {Promise<Array>} Array of search results
 */
export async function searchArticles(query, limit = 8) {
    try {
        const response = await fetch(`/search?q=${encodeURIComponent(query)}&limit=${limit}`);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Search failed');
        }
        return data.results || [];
    } catch (error) {
        console.error('Search error:', error);
        throw error;
    }
}

/**
 * Request edit suggestions for a Grokipedia article
 * @param {string} articleUrl - URL or slug reference
 * @returns {Promise<Object>} Edit suggestion payload
 */
export async function requestEdits(articleUrl) {
    try {
        const response = await fetch('/edits', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                article_url: articleUrl
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to generate edit suggestions');
        }

        return await response.json();
    } catch (error) {
        console.error('Edits error:', error);
        throw error;
    }
}

/**
 * Request Grokipedia article creation from Wikipedia
 * @param {string} articleUrl - Wikipedia URL or title
 * @returns {Promise<Object>} Creation payload
 */
export async function requestCreate(articleUrl) {
    try {
        const response = await fetch('/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                article_url: articleUrl
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to create Grokipedia article');
        }

        return await response.json();
    } catch (error) {
        console.error('Create error:', error);
        throw error;
    }
}

/**
 * Compare articles
 * @param {string} articleUrl - URL of the article to compare
 * @returns {Promise<Object>} Comparison data
 */
export async function compareArticles(articleUrl) {
    try {
        const response = await fetch('/compare', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                article_url: articleUrl
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to compare articles');
        }

        return await response.json();
    } catch (error) {
        console.error('Compare error:', error);
        throw error;
    }
}

