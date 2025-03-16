import { modalManager } from '../../modal.js';
import { escapeHtml } from '../utils.js';

export function renderErrorContent(response) {
    const html = `
        <div class="overflow-x-auto">
            <pre class="whitespace-pre-wrap break-words">${escapeHtml(response)}</pre>
        </div>
    `;
    
    modalManager.setContent(html);
}
