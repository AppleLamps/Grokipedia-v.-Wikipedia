/**
 * Markdown Module - Handles markdown rendering
 */

// Import dependencies
import { escapeHtml } from './utils.js';

/**
 * Render markdown text to HTML
 * @param {string} md - Markdown text
 * @returns {string} HTML string
 */
export function renderMarkdown(md) {
    if (!md) return '';

    const lines = md.split(/\r?\n/);
    let html = '';
    let inList = false;
    let inComparisonPair = false;

    const flushList = () => { if (inList) { html += '</ul>'; inList = false; } };
    const flushComparisonPair = () => { if (inComparisonPair) { html += '</div>'; inComparisonPair = false; } };

    const formatInline = (t) => {
        // Unescape common markdown escapes from scraped content
        t = t.replace(/\\+([\[\]()]|\\)/g, '$1');

        const linkTokens = [];
        t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, text, url) => {
            const token = `___LINK_${linkTokens.length}___`;
            linkTokens.push({ text, url });
            return token;
        });

        // Replace W: and G: patterns with placeholder tokens BEFORE escaping
        t = t.replace(/\bW:\s*/g, '___BADGE_W___');
        t = t.replace(/\bG:\s*/g, '___BADGE_G___');
        t = t.replace(/\(W\)/g, '___BADGE_W___');
        t = t.replace(/\(G\)/g, '___BADGE_G___');
        t = t.replace(/Before\s*\(W\):\s*/gi, '___BADGE_W___ ');
        t = t.replace(/After\s*\(G\):\s*/gi, '___BADGE_G___ ');
        
        // Replace markdown formatting with placeholders
        t = t.replace(/"([^"]+)"/g, '___QUOTE_START___$1___QUOTE_END___');
        t = t.replace(/\*\*(.+?)\*\*/g, '___BOLD_START___$1___BOLD_END___');
        t = t.replace(/\*(.+?)\*/g, '___ITALIC_START___$1___ITALIC_END___');
        
        // NOW escape HTML to prevent XSS
        t = escapeHtml(t);
        
        // Replace placeholders with actual HTML
        t = t.replace(/___BADGE_W___/g, '<span class="source-badge badge-wikipedia">W</span>');
        t = t.replace(/___BADGE_G___/g, '<span class="source-badge badge-grokipedia">G</span>');
        t = t.replace(/___QUOTE_START___/g, '<span class="quote-text">"');
        t = t.replace(/___QUOTE_END___/g, '"</span>');
        t = t.replace(/___BOLD_START___/g, '<strong>');
        t = t.replace(/___BOLD_END___/g, '</strong>');
        t = t.replace(/___ITALIC_START___/g, '<em>');
        t = t.replace(/___ITALIC_END___/g, '</em>');

        linkTokens.forEach((link, index) => {
            const safeText = escapeHtml(link.text);
            const safeUrl = escapeHtml(link.url);
            t = t.replace(
                `___LINK_${index}___`,
                `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${safeText}</a>`
            );
        });

        // Convert numeric citations to superscript
        t = t.replace(/\[(\d{1,3})\]/g, '<sup>[$1]</sup>');

        return t;
    };

    for (const raw of lines) {
        const line = raw.trim();
        if (!line) { flushList(); continue; }

        if (line.match(/^\[\d+\]:\s*\S+/)) {
            flushList();
            flushComparisonPair();
            continue;
        }

        if (line.match(/^---+$/)) {
            flushList();
            flushComparisonPair();
            html += '<hr>';
            continue;
        }

        // Check for Before/After pattern
        const beforeAfterMatch = line.match(/Before\s*\(W\):\s*(.+?)\s*-\s*After\s*\(G\):\s*(.+?)(?:\s*-\s*Change:\s*(.+))?$/i);
        
        // Check for headers (h1-h6)
        const h6 = line.match(/^######\s+(.+)/);
        const h5 = !h6 && line.match(/^#####\s+(.+)/);
        const h4 = !h5 && line.match(/^####\s+(.+)/);
        const h3 = !h4 && line.match(/^###\s+(.+)/);
        const h2 = !h3 && line.match(/^##\s+(.+)/);
        const h1 = !h2 && line.match(/^#\s+(.+)/);
        const ol = line.match(/^\d+\.\s+(.+)/);
        const ul = !ol && line.match(/^[-•]\s+(.+)/);

        if (h6) { 
            flushList(); 
            flushComparisonPair();
            html += `<h4>${formatInline(h6[1])}</h4>`; 
            continue; 
        }
        if (h5) { 
            flushList(); 
            flushComparisonPair();
            html += `<h4>${formatInline(h5[1])}</h4>`; 
            continue; 
        }
        if (h4) { 
            flushList(); 
            flushComparisonPair();
            html += `<h3>${formatInline(h4[1])}</h3>`; 
            continue; 
        }
        if (h3) { 
            flushList(); 
            flushComparisonPair();
            html += `<h3>${formatInline(h3[1])}</h3>`; 
            continue; 
        }
        if (h2) { 
            flushList(); 
            flushComparisonPair();
            html += `<h2>${formatInline(h2[1])}</h2>`; 
            continue; 
        }
        if (h1) { 
            flushList(); 
            flushComparisonPair();
            html += `<h2>${formatInline(h1[1])}</h2>`; 
            continue; 
        }

        // Handle Before/After comparison pairs
        if (beforeAfterMatch) {
            flushList();
            if (!inComparisonPair) {
                html += '<div class="comparison-pair">';
                inComparisonPair = true;
            }
            const beforeText = formatInline(beforeAfterMatch[1]);
            const afterText = formatInline(beforeAfterMatch[2]);
            const changeNote = beforeAfterMatch[3] ? formatInline(beforeAfterMatch[3]) : '';
            
            html += `<div class="before-after"><strong>Before:</strong> ${beforeText}</div>`;
            html += `<div class="before-after"><strong>After:</strong> ${afterText}</div>`;
            if (changeNote) {
                html += `<div class="change-note">Change: ${changeNote}</div>`;
            }
            // Close pair after processing
            flushComparisonPair();
            continue;
        }

        // Check if line contains "Change:" which might be part of a comparison
        if (line.match(/^Change:\s*/i) && inComparisonPair) {
            html += `<div class="change-note">${formatInline(line)}</div>`;
            flushComparisonPair();
            continue;
        }

        if (ol || ul) {
            flushComparisonPair();
            if (!inList) { html += '<ul>'; inList = true; }
            const item = formatInline((ol ? ol[1] : ul[1]));
            html += `<li>${item}</li>`;
            continue;
        }

        flushList();
        flushComparisonPair();
        html += `<p>${formatInline(line)}</p>`;
    }
    flushList();
    flushComparisonPair();
    return html;
}

