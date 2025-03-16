import { modalManager } from '../modal.js';
import { renderELANViewer } from './viewers/elan-viewer.js';
import { renderAudioPlayer } from './viewers/audio-viewer.js';
import { renderVideoPlayer } from './viewers/video-viewer.js';
import { renderPDFViewer } from './viewers/pdf-viewer.js';
import { renderImageViewer } from './viewers/image-viewer.js';
import { renderDefaultViewer } from './viewers/default-viewer.js';

export function handleFileViewRequest(evt) {
    try {
        const fileData = JSON.parse(evt.detail.xhr.response);
        
        const viewerMap = {
            'application/eaf+xml': renderELANViewer,
            'audio/': renderAudioPlayer,
            'video/': renderVideoPlayer,
            'application/pdf': renderPDFViewer,
            'image/': renderImageViewer
        }; 

        modalManager.open();
        modalManager.setContent('');
        
        const filename = fileData.path.split('/').pop();
        document.getElementById('modalTitle').textContent = filename;

        const viewer = Object.entries(viewerMap).find(([type, _]) => 
            type.endsWith('/') ? fileData.type.startsWith(type) : fileData.type === type
        );
        
        if (viewer) {
            viewer[1](fileData);
        } else {
            renderDefaultViewer(fileData);
        }
        
    } catch (e) {
        console.error('Error parsing content:', e);
        modalManager.open();
        modalManager.setContent(`<div class="p-4">Error parsing content: ${e.message}</div>`);
    }
}
