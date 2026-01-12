/**
 * UI Module - Handles DOM manipulation and UI updates
 */

// Import dependencies
import { renderMarkdown } from './markdown.js';
import { escapeHtml } from './utils.js';

/**
 * Show loading state
 * @param {string} message - Optional loading message
 */
export function showLoading(message = 'Analyzing articles...') {
    const loading = document.getElementById('loading');
    const loadingText = document.getElementById('loading-text');
    if (loading) {
        loading.classList.remove('hidden');
    }
    if (loadingText) {
        loadingText.textContent = message;
    }
}

/**
 * Update loading message
 * @param {string} message - Loading message
 */
export function updateLoadingMessage(message) {
    const loadingText = document.getElementById('loading-text');
    if (loadingText) {
        loadingText.style.opacity = '0';
        setTimeout(() => {
            loadingText.textContent = message;
            loadingText.style.opacity = '1';
        }, 150);
    }
}

/**
 * Hide loading state
 */
export function hideLoading() {
    const loading = document.getElementById('loading');
    if (loading) {
        loading.classList.add('hidden');
    }
}

/**
 * Show error message
 * @param {string} message - Error message to display
 * @param {string} guidance - Optional guidance text
 */
export function showError(message, guidance = null) {
    const errorContainer = document.getElementById('error-container');
    if (errorContainer) {
        let guidanceHtml = '';
        if (guidance) {
            guidanceHtml = `<div class="error-guidance">${escapeHtml(guidance)}</div>`;
        }
        // Default guidance for common errors
        if (!guidance) {
            if (message.toLowerCase().includes('network') || message.toLowerCase().includes('fetch')) {
                guidanceHtml = '<div class="error-guidance">Please check your connection and try again.</div>';
            } else if (message.toLowerCase().includes('not found')) {
                guidanceHtml = '<div class="error-guidance">Try searching for a different article or check the URL.</div>';
            } else {
                guidanceHtml = '<div class="error-guidance">Please try again or contact support if the issue persists.</div>';
            }
        }
        errorContainer.innerHTML = `
            <div class="error">
                <div class="error-message">${escapeHtml(message)}</div>
                ${guidanceHtml}
            </div>
        `;
    }
}

/**
 * Clear error message
 */
export function clearError() {
    const errorContainer = document.getElementById('error-container');
    if (errorContainer) {
        errorContainer.innerHTML = '';
    }
}

/**
 * Update UI for results view
 */
export function showResultsView() {
    const body = document.body;
    const mainContainer = document.getElementById('mainContainer');
    const initialView = document.getElementById('initialView');
    const resultsContainer = document.getElementById('results-container');

    if (body) body.classList.add('has-results');
    if (mainContainer) mainContainer.classList.add('has-results');
    if (initialView) initialView.classList.add('hidden');
    if (resultsContainer) resultsContainer.classList.remove('hidden');
}

/**
 * Display article content
 * @param {string} containerId - ID of container element
 * @param {Object} articleData - Article data to display
 * @param {string} contentKey - Key for content (summary/intro)
 */
export function displayArticle(containerId, articleData, contentKey = 'summary') {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (articleData) {
        const title = articleData.title || '';
        const url = articleData.url || '';

        // Determine what content to display based on container type
        let displayContent = '';
        let contentLabel = '';

        if (containerId === 'grokipedia-content') {
            // Show TLDR for Grokipedia
            displayContent = articleData.tldr || articleData[contentKey] || '';
            contentLabel = 'TLDR';
        } else if (containerId === 'wikipedia-content') {
            // Show article summary for Wikipedia
            displayContent = articleData.article_summary || articleData[contentKey] || '';
            contentLabel = 'About this article';
        } else {
            // Default behavior for other containers
            displayContent = articleData[contentKey] || '';
            contentLabel = 'Content';
        }

        const sections = articleData.sections || [];

        const titleHtml = url
            ? `<div class="title"><a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(title)}</a></div>`
            : `<div class="title">${escapeHtml(title)}</div>`;

        const urlHtml = url
            ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" class="article-url">${escapeHtml(url)}</a>`
            : '';

        container.innerHTML = `
            ${titleHtml}
            ${urlHtml}
            <div class="content-label">${escapeHtml(contentLabel)}</div>
            <div class="content">${escapeHtml(displayContent)}</div>
            ${sections.length > 0 ? `
            <div class="sections">
                <strong>Sections:</strong>
                <ul>
                    ${sections.map(s => `<li>• ${escapeHtml(s)}</li>`).join('')}
                </ul>
            </div>
            ` : ''}
        `;

        // Update scroll indicators after content is rendered
        setTimeout(() => {
            updateScrollIndicators(containerId);
            // Add scroll listeners for dynamic updates
            const articleBox = container.closest('.article-box');
            if (articleBox) {
                articleBox.addEventListener('scroll', () => updateScrollIndicators(containerId), { passive: true });
            }
        }, 100);
    } else {
        container.innerHTML = '<div class="content">Article not found</div>';
    }
}

/**
 * Update scroll indicators for article boxes
 * @param {string} containerId - ID of container element
 */
function updateScrollIndicators(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const articleBox = container.closest('.article-box');
    if (!articleBox) return;

    // Use the article box itself for scroll calculations
    const scrollTop = articleBox.scrollTop;
    const scrollHeight = articleBox.scrollHeight;
    const clientHeight = articleBox.clientHeight;

    // Check if scrollable
    const isScrollable = scrollHeight > clientHeight;

    if (isScrollable) {
        // Check top scroll
        if (scrollTop > 10) {
            articleBox.classList.add('scrollable-top');
        } else {
            articleBox.classList.remove('scrollable-top');
        }

        // Check bottom scroll
        if (scrollTop < scrollHeight - clientHeight - 10) {
            articleBox.classList.add('scrollable-bottom');
        } else {
            articleBox.classList.remove('scrollable-bottom');
        }
    } else {
        articleBox.classList.remove('scrollable-top', 'scrollable-bottom');
    }
}

/**
 * Display comparison content
 * @param {string} markdown - Markdown content to render
 * @param {string} error - Error message if comparison failed
 */
export function displayComparison(markdown, error) {
    const comparisonContent = document.getElementById('comparison-content');
    const comparisonRaw = document.getElementById('comparison-raw');

    if (error) {
        const errorText = `Unable to compare: ${error}`;
        if (comparisonContent) comparisonContent.textContent = errorText;
        if (comparisonRaw) comparisonRaw.textContent = errorText;
        return;
    }

    if (!markdown) {
        const noDataText = 'One or both articles were not found.';
        if (comparisonContent) comparisonContent.textContent = noDataText;
        if (comparisonRaw) comparisonRaw.textContent = noDataText;
        return;
    }

    // Store markdown for copy functionality
    window.lastComparisonMarkdown = markdown;

    if (comparisonContent) {
        comparisonContent.innerHTML = renderMarkdown(markdown);
    }
    if (comparisonRaw) {
        comparisonRaw.textContent = markdown;
    }
}

/**
 * Display a generated Grokipedia article draft
 * @param {string} markdown - Markdown content to render
 * @param {Object} meta - Metadata for the draft
 */
export function displayCreatedArticle(markdown, meta = {}) {
    const createContent = document.getElementById('create-content');
    const createMeta = document.getElementById('create-meta');

    if (!createContent) return;

    if (!markdown) {
        createContent.textContent = 'No draft returned.';
        return;
    }

    createContent.innerHTML = renderMarkdown(markdown);

    if (createMeta) {
        const timeLabel = meta.timeLabel || 'just now';

        if (meta.isExisting) {
            // Existing article from Grokipedia - use SVG icon
            const bookIcon = `<svg class="meta-icon existing-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>`;
            let metaHtml = `
                ${bookIcon}
                <span>Found in Grokipedia</span>
                <span class="meta-time">${escapeHtml(timeLabel)}</span>
            `;
            if (meta.grokipediaUrl) {
                metaHtml += `<a href="${escapeHtml(meta.grokipediaUrl)}" target="_blank" class="meta-link">View on Grokipedia ↗</a>`;
            }
            createMeta.innerHTML = metaHtml;
        } else if (meta.customMeta) {
            // Custom meta text (e.g., for biographies)
            const xIcon = `<svg class="meta-icon existing-icon" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>`;
            createMeta.innerHTML = `
                ${xIcon}
                <span>${escapeHtml(meta.customMeta)}</span>
                <span class="meta-time">${escapeHtml(timeLabel)}</span>
            `;
        } else {
            // Newly generated article
            createMeta.innerHTML = `
                <span class="meta-icon">&#10003;</span>
                <span>Fact-checked by Grok</span>
                <span class="meta-time">${escapeHtml(timeLabel)}</span>
            `;
        }
    }
}

/**
 * Set button disabled state
 * @param {string} buttonId - ID of button element
 * @param {boolean} disabled - Disabled state
 */
export function setButtonDisabled(buttonId, disabled) {
    const button = document.getElementById(buttonId);
    if (button) {
        button.disabled = disabled;
    }
}

