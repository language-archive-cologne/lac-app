export function escapeHtml(unsafe) {
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

export function formatTime(timeInSeconds) {
    const minutes = Math.floor(timeInSeconds / 60);
    const seconds = Math.floor(timeInSeconds % 60);
    return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}

export function getLanguage(fileData) {
    // First try to determine language from file type
    if (fileData.type === 'application/json') {
        return 'json';
    }
    if (fileData.type === 'text/xml' || fileData.type === 'application/xml') {
        return 'xml';
    }
    
    // Fallback to extension if needed
    const filename = fileData.path.split('/').pop();
    const extension = filename.split('.').pop().toLowerCase();
    
    const languageMap = {
        'js': 'javascript',
        'py': 'python',
        'html': 'html',
        'css': 'css',
        'json': 'json',
        'xml': 'xml',
        'txt': 'text',
        'md': 'markdown'
    };
    
    return languageMap[extension] || 'text';
}
