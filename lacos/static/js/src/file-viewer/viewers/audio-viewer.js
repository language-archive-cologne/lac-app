import { modalManager } from '../../modal.js';

export function renderAudioPlayer(fileData) {
    const audioUrl = `/archivist/stream/${fileData.bucket_type}/${fileData.path}`;

    const html = `
        <div class="p-4">
            <div class="overflow-x-auto">
                <div id="audioPlayerContainer" class="w-full max-w-xl mx-auto">
                    
                    <!-- File info -->
                    <div class="text-sm text-gray-600 mb-4">
                        <p>
                            File: ${fileData.path}<br>
                            Type: ${fileData.type}
                        </p>
                    </div>
                    
                    <!-- Audio player (initially hidden) -->
                    <audio 
                        id="audioPlayer" 
                        controls 
                        class="hidden w-full"
                        preload="metadata">
                        <source src="${audioUrl}" type="${fileData.type}">
                        Your browser does not support the audio element.
                    </audio>
                </div>
            </div>
        </div>
    `;

    modalManager.setContent(html);

    const audioPlayer = document.getElementById('audioPlayer');

    // Show player and hide loading when metadata is loaded
    audioPlayer.addEventListener('loadedmetadata', () => {
        audioPlayer.classList.remove('hidden');
    });

    // Handle errors
    audioPlayer.addEventListener('error', (e) => {
        console.error('Audio loading error:', e);
        modalManager.setContent(modalManager.modalContent.innerHTML + `
            <div class="mt-2 text-red-500">Error loading audio. Please try again.</div>
        `);
    });
}
