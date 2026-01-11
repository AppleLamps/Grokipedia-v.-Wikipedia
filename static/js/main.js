/**
 * Main Application Module - Initializes and coordinates all modules
 */

import { compareArticles, requestEdits, requestCreate } from './api.js';
import {
    showLoading,
    hideLoading,
    updateLoadingMessage,
    showError,
    clearError,
    showResultsView,
    displayArticle,
    displayComparison,
    displayCreatedArticle,
    setButtonDisabled
} from './ui.js';
import { initSearch, handleEnterKey } from './search.js';
import { copyToClipboard, buildArticleCopy, escapeHtml } from './utils.js';
import { saveComparison } from './storage.js';
import { initSidebar, updateSidebarBadge } from './sidebar.js';
import { getComparisonById } from './storage.js';

// Global state
let lastGrokCopyText = '';
let lastWikiCopyText = '';
let lastEditsCopyText = '';
let lastCreateCopyText = '';
let currentComparisonData = null;
let currentMode = 'create';

/**
 * Initialize the application
 */
export function init() {
    const articleInput = document.getElementById('article-url');
    const compareBtn = document.getElementById('compareBtn');
    const newSearchBtn = document.getElementById('newSearchBtn');
    const suggestionsContainer = document.getElementById('suggestions');
    const copyBtn = document.getElementById('copyBtn');
    const rawToggle = document.getElementById('rawToggle');
    const copyGrokBtn = document.getElementById('copyGrokBtn');
    const copyWikiBtn = document.getElementById('copyWikiBtn');
    const comparisonRaw = document.getElementById('comparison-raw');
    const saveBtn = document.getElementById('saveBtn');
    const homeLink = document.getElementById('homeLink');
    const resultsHomeLink = document.getElementById('resultsHomeLink');
    const modeButtons = document.querySelectorAll('[data-mode]');
    const copyEditsBtn = document.getElementById('copyEditsBtn');
    const copyCreateBtn = document.getElementById('copyCreateBtn');

    if (!articleInput || !compareBtn) {
        console.error('Required elements not found');
        return;
    }

    // Initialize sidebar
    initSidebar();

    // Update sidebar badge on load
    updateSidebarBadge();

    // Home link click handlers
    if (homeLink) {
        homeLink.addEventListener('click', resetToSearchView);
    }
    if (resultsHomeLink) {
        resultsHomeLink.addEventListener('click', resetToSearchView);
    }

    // Initialize search/autocomplete
    initSearch(articleInput, suggestionsContainer, () => {
        handleAnalyzeRequest();
    });

    // Compare button click
    compareBtn.addEventListener('click', handleAnalyzeRequest);

    // New Search button
    if (newSearchBtn) {
        newSearchBtn.addEventListener('click', () => {
            resetToSearchView();
        });
    }

    // Enter key handler
    articleInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            if (!handleEnterKey(suggestionsContainer, () => handleAnalyzeRequest())) {
                handleAnalyzeRequest();
            }
        }
    });

    // Copy buttons
    if (copyBtn) {
        copyBtn.addEventListener('click', async () => {
            const text = window.lastComparisonMarkdown ||
                (document.getElementById('comparison-content')?.innerText ?? '');
            await copyToClipboard(text, copyBtn);
        });
    }

    if (copyEditsBtn) {
        copyEditsBtn.addEventListener('click', async () => {
            await copyToClipboard(lastEditsCopyText, copyEditsBtn);
        });
    }

    if (copyCreateBtn) {
        copyCreateBtn.addEventListener('click', async () => {
            await copyToClipboard(lastCreateCopyText, copyCreateBtn);
        });
    }

    if (copyGrokBtn) {
        copyGrokBtn.addEventListener('click', async () => {
            await copyToClipboard(lastGrokCopyText, copyGrokBtn);
        });
    }

    if (copyWikiBtn) {
        copyWikiBtn.addEventListener('click', async () => {
            await copyToClipboard(lastWikiCopyText, copyWikiBtn);
        });
    }

    // Raw toggle
    if (rawToggle) {
        rawToggle.addEventListener('click', () => {
            const isOn = rawToggle.getAttribute('aria-pressed') === 'true';
            const next = !isOn;
            rawToggle.setAttribute('aria-pressed', String(next));
            const comparisonContent = document.getElementById('comparison-content');
            if (comparisonContent) {
                comparisonContent.classList.toggle('hidden', next);
            }
            if (comparisonRaw) {
                comparisonRaw.classList.toggle('hidden', !next);
            }
        });
    }

    // Save button
    if (saveBtn) {
        saveBtn.addEventListener('click', handleSaveComparison);
    }

    if (modeButtons.length > 0) {
        modeButtons.forEach((button) => {
            button.addEventListener('click', () => {
                const nextMode = button.getAttribute('data-mode');
                if (nextMode) {
                    currentMode = nextMode;
                    updateModeUI();
                }
            });
        });
    }

    // Focus input on load
    articleInput.focus();
    updateModeUI();
}

/**
 * Handle saving comparison
 */
async function handleSaveComparison() {
    if (!currentComparisonData) {
        showError('No comparison data to save');
        return;
    }

    try {
        // Get article title for the saved item
        const title = currentComparisonData.grokipedia?.title ||
            currentComparisonData.wikipedia?.title ||
            'Untitled Comparison';

        const dataToSave = {
            ...currentComparisonData,
            title
        };

        saveComparison(dataToSave);

        // Update sidebar badge
        updateSidebarBadge();

        // Show feedback
        const saveBtn = document.getElementById('saveBtn');
        if (saveBtn) {
            const originalHTML = saveBtn.innerHTML;
            saveBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3.5 7L6 9.5L10.5 4.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg> Saved';
            saveBtn.style.background = 'rgba(87, 200, 255, 0.2)';
            saveBtn.style.borderColor = 'rgba(95, 200, 255, 0.4)';

            setTimeout(() => {
                saveBtn.innerHTML = originalHTML;
                saveBtn.style.background = '';
                saveBtn.style.borderColor = '';
            }, 2000);
        }
    } catch (error) {
        console.error('Error saving comparison:', error);
        showError('Failed to save comparison');
    }
}

/**
 * Load a saved comparison
 * @param {string} id - ID of the saved comparison
 */
export function loadSavedComparison(id) {
    const saved = getComparisonById(id);
    if (!saved) {
        showError('Saved comparison not found');
        return;
    }

    currentMode = 'compare';

    // Set current comparison data
    currentComparisonData = {
        grokipedia: saved.grokipedia,
        wikipedia: saved.wikipedia,
        comparison: saved.comparison,
        comparison_error: saved.comparison_error,
        grokipedia_url: saved.grokipedia_url,
        wikipedia_url: saved.wikipedia_url
    };

    // Display the saved comparison
    displayResults(currentComparisonData);
}

// Listen for load comparison events (from sidebar)
window.addEventListener('loadComparison', (e) => {
    loadSavedComparison(e.detail.id);
});

/**
 * Reset to search view
 */
export function resetToSearchView() {
    currentComparisonData = null;
    const body = document.body;
    const mainContainer = document.getElementById('mainContainer');
    const initialView = document.getElementById('initialView');
    const resultsContainer = document.getElementById('results-container');
    const articleInput = document.getElementById('article-url');
    const editsContent = document.getElementById('edits-content');
    const editsBox = document.getElementById('edits-box');
    const createContent = document.getElementById('create-content');
    const createBox = document.getElementById('create-box');

    if (body) body.classList.remove('has-results');
    if (body) body.classList.remove('create-mode-results');
    if (mainContainer) mainContainer.classList.remove('has-results');
    if (initialView) initialView.style.minHeight = '60vh';
    if (resultsContainer) resultsContainer.classList.add('hidden');
    if (articleInput) {
        articleInput.value = '';
        articleInput.focus();
    }
    if (editsContent) editsContent.textContent = '';
    if (editsBox) editsBox.classList.add('hidden');
    lastEditsCopyText = '';
    if (createContent) createContent.textContent = '';
    if (createBox) createBox.classList.add('hidden');
    lastCreateCopyText = '';

    clearError();
    hideLoading();
    updateModeUI();
}

/**
 * Handle article analysis based on current mode
 */
async function handleAnalyzeRequest() {
    const articleInput = document.getElementById('article-url');
    const articleUrl = articleInput?.value.trim();

    if (!articleUrl) {
        showError('Please provide an article URL');
        return;
    }

    const loadingMessage = currentMode === 'edits'
        ? 'Preparing Grok Editor...'
        : currentMode === 'create'
            ? 'Preparing Grokipedia draft...'
            : 'Fetching articles...';
    showLoading(loadingMessage);
    const resultsContainer = document.getElementById('results-container');
    if (resultsContainer) {
        resultsContainer.classList.add('hidden');
    }
    clearError();
    setButtonDisabled('compareBtn', true);

    try {
        if (currentMode === 'edits') {
            await runEditsFlow(articleUrl);
        } else if (currentMode === 'create') {
            await runCreateFlow(articleUrl);
        } else {
            await runComparisonFlow(articleUrl);
        }
    } catch (error) {
        showError(error.message);
    } finally {
        hideLoading();
        setButtonDisabled('compareBtn', false);
    }
}

async function runComparisonFlow(articleUrl) {
    setTimeout(() => {
        updateLoadingMessage('Fetching articles...');
    }, 500);

    setTimeout(() => {
        updateLoadingMessage('Analyzing content...');
    }, 1500);

    setTimeout(() => {
        updateLoadingMessage('Comparing articles...');
    }, 2500);

    const data = await compareArticles(articleUrl);
    displayResults(data);
}

async function runEditsFlow(articleUrl) {
    setTimeout(() => {
        updateLoadingMessage('Fetching Grokipedia article...');
    }, 500);

    setTimeout(() => {
        updateLoadingMessage('Reviewing content...');
    }, 1500);

    setTimeout(() => {
        updateLoadingMessage('Compiling edit list...');
    }, 2500);

    const data = await requestEdits(articleUrl);
    displayEditsResults(data);
}

async function runCreateFlow(articleUrl) {
    const messages = [
        'Fetching Wikipedia article...',
        'Searching the web for sources...',
        'Scanning X for recent posts...',
        'Cross-referencing facts...',
        'Drafting Grokipedia article...',
        'Verifying information...',
        'Removing bias...',
        'Polishing structure...',
        'Formatting references...',
        'Applying galactic standards...',
        'Final review in progress...',
        'Almost there...',
        'Compiling entry...',
        'Double-checking sources...',
        'Optimizing for clarity...'
    ];

    let messageIndex = 0;
    const messageInterval = setInterval(() => {
        if (messageIndex < messages.length) {
            updateLoadingMessage(messages[messageIndex]);
            messageIndex++;
        } else {
            // Loop back through messages if still loading
            messageIndex = Math.floor(messages.length / 2);
        }
    }, 2000);

    try {
        const data = await requestCreate(articleUrl);
        clearInterval(messageInterval);
        displayCreateResults(data);
    } catch (error) {
        clearInterval(messageInterval);
        throw error;
    }
}

/**
 * Display comparison results
 * @param {Object} data - Comparison data
 */
function displayResults(data) {
    // Store current comparison data
    currentComparisonData = data;

    // Display Grokipedia content
    displayArticle('grokipedia-content', data.grokipedia, 'summary');
    lastGrokCopyText = buildArticleCopy('Grokipedia', data.grokipedia);

    // Display Wikipedia content
    displayArticle('wikipedia-content', data.wikipedia, 'intro');
    lastWikiCopyText = buildArticleCopy('Wikipedia', data.wikipedia);

    // Display comparison
    displayComparison(data.comparison, data.comparison_error);

    // Update layout for results view
    showResultsView();
    updateModeUI();
}

function displayEditsResults(data) {
    currentComparisonData = null;
    displayArticle('grokipedia-content', data.grokipedia, 'summary');
    lastGrokCopyText = buildArticleCopy('Grokipedia', data.grokipedia);

    const editsContent = document.getElementById('edits-content');
    if (editsContent) {
        const content = data.edits || 'No edits returned.';
        const html = parseEditSuggestions(content);
        editsContent.innerHTML = html;
        lastEditsCopyText = content;
        editsContent.scrollTop = 0;
    }

    const editsBox = document.getElementById('edits-box');
    if (editsBox) {
        editsBox.classList.remove('hidden');
    }

    showResultsView();
    updateModeUI();
}

function displayCreateResults(data) {
    currentComparisonData = null;
    document.body.classList.add('create-mode-results');

    // Check if this is an existing article from Grokipedia
    if (data.existing_article && data.grokipedia) {
        // Display existing Grokipedia article
        const articleData = data.grokipedia;
        const title = articleData.title || '';
        const tldr = articleData.tldr || '';

        // Content is now clean markdown from Firecrawl
        let content = articleData.full_text || articleData.summary || '';

        // Build final formatted content
        let formattedContent = '';

        // Only add title if content doesn't already start with a header
        if (!content.trim().startsWith('#')) {
            formattedContent = `# ${title}\n\n`;
        }

        if (tldr) {
            formattedContent += `**TLDR:** ${tldr}\n\n---\n\n`;
        }
        formattedContent += content;

        displayCreatedArticle(formattedContent, {
            timeLabel: 'existing article',
            isExisting: true,
            grokipediaUrl: data.grokipedia_url,
            message: data.message
        });
        lastCreateCopyText = formattedContent;
    } else {
        // Display newly generated draft
        const draft = data.grokipedia_draft || '';
        displayCreatedArticle(draft, {
            timeLabel: 'just now'
        });
        lastCreateCopyText = draft;
    }

    const createBox = document.getElementById('create-box');
    if (createBox) {
        createBox.classList.remove('hidden');
    }

    showResultsView();
    updateModeUI();
}

/**
 * Parse edit suggestions from API response and render as structured HTML
 * @param {string} text - Raw edit suggestions text
 * @returns {string} HTML string
 */
function parseEditSuggestions(text) {
    if (!text) return '<p class="no-edits">No edits returned.</p>';

    // Check for "No edits required" message
    if (text.includes('No edits required') || text.match(/No edits required/i)) {
        return '<div class="edit-decision"><p class="no-edits-message">No edits required — article is fully accurate, up-to-date, and optimally written.</p></div>';
    }

    // Extract EDIT DECISION section
    const decisionMatch = text.match(/=== EDIT DECISION ===\s*\n(.+?)(?=\n===|$)/is);
    let decisionHtml = '';
    if (decisionMatch) {
        const decision = decisionMatch[1].trim();
        decisionHtml = `<div class="edit-decision"><p class="decision-text">${escapeHtml(decision)}</p></div>`;
    }

    // Extract all edit suggestions
    const editBlocks = text.match(/---EDIT START---([\s\S]*?)---EDIT END---/g);

    if (!editBlocks || editBlocks.length === 0) {
        // Fallback: try to parse old format or return raw text
        return decisionHtml + '<div class="edit-suggestions"><pre class="raw-edits">' + escapeHtml(text) + '</pre></div>';
    }

    let suggestionsHtml = '<div class="edit-suggestions">';

    editBlocks.forEach((block, index) => {
        const summaryMatch = block.match(/SUMMARY:\s*(.+?)(?=\nLOCATION:|$)/is);
        const locationMatch = block.match(/LOCATION:\s*(.+?)(?=\nEDIT CONTENT:|$)/is);
        const editContentMatch = block.match(/EDIT CONTENT:\s*(.+?)(?=\nREASON:|$)/is);
        const reasonMatch = block.match(/REASON:\s*(.+?)(?=\nSOURCES:|$)/is);
        const sourcesMatch = block.match(/SOURCES:\s*([\s\S]+?)(?=\n---EDIT END---|$)/is);

        const summary = summaryMatch ? summaryMatch[1].trim() : '';
        const location = locationMatch ? locationMatch[1].trim() : '';
        const editContent = editContentMatch ? editContentMatch[1].trim() : '';
        const reason = reasonMatch ? reasonMatch[1].trim() : '';
        const sourcesText = sourcesMatch ? sourcesMatch[1].trim() : '';

        // Parse sources (one per line, filter out "None" or empty)
        const sources = sourcesText
            .split('\n')
            .map(s => s.trim())
            .filter(s => s && s.toLowerCase() !== 'none' && s.length > 0);

        suggestionsHtml += `
            <div class="edit-suggestion" data-index="${index + 1}">
                <div class="edit-header">
                    <span class="edit-number">${index + 1}</span>
                    <h4 class="edit-summary">${escapeHtml(summary || 'Edit suggestion')}</h4>
                </div>
                ${location ? `<div class="edit-location"><strong>Location:</strong> <span class="location-text">${escapeHtml(location)}</span></div>` : ''}
                <div class="edit-content-section">
                    <label class="edit-label">Edit content:</label>
                    <div class="edit-content-text">${escapeHtml(editContent).replace(/\n/g, '<br>')}</div>
                </div>
                ${reason ? `<div class="edit-reason"><strong>Reason:</strong> ${escapeHtml(reason)}</div>` : ''}
                ${sources.length > 0 ? `
                    <div class="edit-sources">
                        <strong>Supporting sources:</strong>
                        <ul class="sources-list">
                            ${sources.map(source => `<li><a href="${escapeHtml(source)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source)}</a></li>`).join('')}
                        </ul>
                    </div>
                ` : ''}
            </div>
        `;
    });

    suggestionsHtml += '</div>';

    return decisionHtml + suggestionsHtml;
}

function updateModeUI() {
    const compareBtn = document.getElementById('compareBtn');
    const resultsGrid = document.getElementById('resultsGrid');
    const grokipediaBox = document.getElementById('grokipedia-box');
    const wikipediaBox = document.getElementById('wikipedia-box');
    const comparisonBox = document.getElementById('comparison-box');
    const copyBtn = document.getElementById('copyBtn');
    const rawToggle = document.getElementById('rawToggle');
    const copyEditsBtn = document.getElementById('copyEditsBtn');
    const saveBtn = document.getElementById('saveBtn');
    const comparisonRaw = document.getElementById('comparison-raw');
    const editsBox = document.getElementById('edits-box');
    const createBox = document.getElementById('create-box');
    const createContent = document.getElementById('create-content');
    const articleInput = document.getElementById('article-url');
    const modeButtons = document.querySelectorAll('[data-mode]');

    if (compareBtn) {
        const label = currentMode === 'edits'
            ? 'Generate edit suggestions'
            : currentMode === 'create'
                ? 'Create Grokipedia article'
                : 'Compare articles';
        compareBtn.setAttribute('aria-label', label);
        compareBtn.setAttribute('title', label);
    }

    if (resultsGrid) {
        resultsGrid.classList.toggle('edits-mode', currentMode === 'edits');
        resultsGrid.classList.toggle('hidden', currentMode === 'create');
    }

    const hideComparison = currentMode !== 'compare';
    if (grokipediaBox) {
        grokipediaBox.classList.toggle('hidden', currentMode === 'create');
    }
    if (wikipediaBox) {
        wikipediaBox.classList.toggle('hidden', hideComparison);
    }
    if (comparisonBox) {
        comparisonBox.classList.toggle('hidden', hideComparison);
    }
    if (copyBtn) {
        copyBtn.classList.toggle('hidden', hideComparison);
    }
    if (rawToggle) {
        rawToggle.classList.toggle('hidden', hideComparison);
    }
    if (copyEditsBtn) {
        copyEditsBtn.classList.toggle('hidden', currentMode !== 'edits');
    }
    if (saveBtn) {
        saveBtn.classList.toggle('hidden', currentMode !== 'compare');
    }
    if (comparisonRaw && hideComparison) {
        comparisonRaw.classList.add('hidden');
        const rawToggleBtn = document.getElementById('rawToggle');
        if (rawToggleBtn) {
            rawToggleBtn.setAttribute('aria-pressed', 'false');
        }
    }
    if (currentMode !== 'edits' && editsBox) {
        editsBox.classList.add('hidden');
    }

    if (createBox) {
        const hasCreateContent = Boolean(createContent && createContent.innerHTML);
        createBox.classList.toggle('hidden', currentMode !== 'create' || !hasCreateContent);
    }

    if (articleInput) {
        const placeholders = {
            compare: 'Enter article URL or name...',
            edits: 'Enter Grokipedia URL or name...',
            create: 'Enter Wikipedia URL...'
        };
        articleInput.placeholder = placeholders[currentMode] || placeholders.compare;
    }

    if (modeButtons.length > 0) {
        modeButtons.forEach((button) => {
            const mode = button.getAttribute('data-mode');
            const isActive = mode === currentMode;
            button.classList.toggle('is-active', isActive);
            button.setAttribute('aria-checked', String(isActive));
        });
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

