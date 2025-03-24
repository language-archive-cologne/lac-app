import { modalManager } from '../../modal.js';
import { formatTime } from '../utils.js';

function createELANViewerTemplate(audioUrl, fileData) {
    return `
        <div class="elan-viewer bg-white rounded-lg shadow-lg p-6 max-w-full">
            <h3 class="text-xl font-bold mb-4 text-gray-800">ELAN File Viewer</h3>
            
            <!-- Audio player container -->
            <div id="audioPlayerContainer" class="fixed top-0 left-0 right-0 bg-white z-50 pb-4 shadow-md mx-auto" style="max-width: 1200px; left: 50%; transform: translateX(-50%);">
                <div class="bg-gray-50 p-4 rounded-lg">
                    <audio 
                        id="audioPlayer" 
                        controls 
                        class="w-full focus:outline-none"
                        preload="metadata">
                        <source src="${audioUrl}" type="${fileData.type}">
                        Your browser does not support the audio element.
                    </audio>
                </div>
            </div>

            <div class="annotation-list mt-32">
                <h4 class="text-lg font-semibold mb-3 text-gray-700">Annotations</h4>
                <div class="max-h-96 overflow-auto rounded-lg border border-gray-200" id="annotationList">
                    <table class="w-full border-collapse table-auto">
                        <tbody class="divide-y divide-gray-200">
                        </tbody>
                    </table>
                </div>
            </div>
            
            <div class="mt-6 space-y-1 text-sm text-gray-500 bg-gray-50 p-4 rounded-lg">
                <p><span class="font-medium">File Type:</span> ${fileData.type}</p>
                <p><span class="font-medium">Last Modified:</span> ${fileData.last_modified}</p>
                <p><span class="font-medium">Size:</span> ${fileData.size} bytes</p>
            </div>
        </div>
    `;
}

function renderAnnotations(annotations) {
    const annotationList = document.getElementById('annotationList');

    // Get all unique tier IDs
    const allTiers = new Set();
    annotations.forEach(annotation => {
        Object.keys(annotation.tiers).forEach(tier => allTiers.add(tier));
    });
    const tierArray = Array.from(allTiers);

    // Create table header
    const tableHeader = `
        <thead class="bg-gray-50 sticky top-0">
            <tr>
                <th class="text-center px-4 py-2 text-sm font-semibold text-gray-600 whitespace-nowrap">Time</th>
                ${tierArray.map(tier => `<th class="text-center px-4 py-2 text-sm font-semibold text-gray-600 whitespace-nowrap">${tier}</th>`).join('')}
                <th class="text-center px-4 py-2 text-sm font-semibold text-gray-600 whitespace-nowrap">Actions</th>
            </tr>
        </thead>
    `;

    // Group annotations by start and end time
    const groupedAnnotations = {};
    annotations.forEach(annotation => {
        const key = `${annotation.start}-${annotation.end}`;
        if (!groupedAnnotations[key]) {
            groupedAnnotations[key] = {
                start: annotation.start,
                end: annotation.end,
                tiers: {}
            };
        }
        Object.assign(groupedAnnotations[key].tiers, annotation.tiers);
    });

    // Create table rows
    const tableBody = Object.values(groupedAnnotations).map((group) => {
        const startSeconds = parseFloat(group.start) / 1000;
        const endSeconds = parseFloat(group.end) / 1000;

        return `
            <tr class="border-t hover:bg-gray-50 transition-colors">
                <td class="px-4 py-2 text-xs text-gray-500 text-center">
                    ${formatTime(startSeconds)} - ${formatTime(endSeconds)}
                </td>
                ${tierArray.map(tier => `
                    <td class="px-4 py-2 text-sm text-center">${group.tiers[tier] || ''}</td>
                `).join('')}
                <td class="px-4 py-2 text-center space-x-2">
                    <button class="inline-flex items-center justify-center w-8 h-8 rounded-full bg-blue-100 hover:bg-blue-200 text-blue-600 transition-colors" 
                            onclick="playAnnotation(${startSeconds})"
                            title="Play this segment">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clip-rule="evenodd" />
                        </svg>
                    </button>
                    <button class="inline-flex items-center justify-center w-8 h-8 rounded-full bg-blue-100 hover:bg-blue-200 text-blue-600 transition-colors" 
                            onclick="pauseAudio()"
                            title="Pause audio">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM7 8a1 1 0 012 0v4a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v4a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
                        </svg>
                    </button>
                </td>
            </tr>
        `;
    }).join('');

    // Combine header and body into a table
    const tableHtml = `
        <table class="w-full border-collapse table-auto">
            ${tableHeader}
            <tbody class="divide-y divide-gray-200">
                ${tableBody}
            </tbody>
        </table>
    `;

    annotationList.innerHTML = tableHtml;
}

export function renderELANViewer(fileData) {
    const { annotations, media_file } = fileData.content;
    const { bucket_type, path } = fileData;
    const folderPath = path.substring(0, path.lastIndexOf('/') + 1);
    const audioUrl = `/archivist/stream/${bucket_type}/${folderPath}${media_file}`;

    const audioType = media_file.toLowerCase().endsWith('.wav') ? 'audio/wav' 
                   : media_file.toLowerCase().endsWith('.mp3') ? 'audio/mpeg'
                   : media_file.toLowerCase().endsWith('.ogg') ? 'audio/ogg'
                   : 'audio/mpeg';

    const html = createELANViewerTemplate(audioUrl, {
        ...fileData,
        type: audioType
    });
    
    modalManager.setContent(html);

    const audioPlayer = document.getElementById('audioPlayer');

    // Show player and render annotations when metadata is loaded
    audioPlayer.addEventListener('loadedmetadata', () => {
        renderAnnotations(annotations);
    });

    // Handle errors
    audioPlayer.addEventListener('error', (e) => {
        console.error('Audio loading error:', e);
        modalManager.setContent(modalManager.modalContent.innerHTML + `
            <div class="mt-2 text-red-500">Error loading audio file: ${media_file}. Please try again.</div>
        `);
    });

    // Setup playback and pause for annotations
    window.playAnnotation = (start) => {
        audioPlayer.currentTime = start;
        audioPlayer.play();
    };

    window.pauseAudio = () => {
        audioPlayer.pause();
    };
}
