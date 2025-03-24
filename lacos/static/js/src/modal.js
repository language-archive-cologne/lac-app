class ModalManager {
    constructor() {
        // Initialize immediately if document is already loaded
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.init());
        } else {
            this.init();
        }
    }

    init() {
        console.log('Initializing ModalManager');
        this.modal = document.getElementById('fileModal');
        this.modalContent = document.getElementById('modalContent');
        
        if (!this.modal || !this.modalContent) {
            console.error('Modal elements not found!');
            return;
        }
        
        this.setupEventListeners();
    }

    setupEventListeners() {
        console.log('Setting up event listeners');
        
        // Close modal when clicking outside
        this.modal.addEventListener('click', (e) => {
            if (e.target === this.modal) {
                console.log('Clicked modal background');
                this.close();
            }
        });

        // Close modal when clicking the X button
        const closeButton = this.modal.querySelector('.modal-close');
        console.log('Found close button:', closeButton);
        
        if (closeButton) {
            closeButton.addEventListener('click', (e) => {
                console.log('Close button clicked!');
                e.stopPropagation();
                this.close();
            });
        } else {
            console.error('Close button not found!');
        }
    }

    open() {
        console.log('Opening modal');
        this.modal.classList.remove('opacity-0', 'pointer-events-none');
        this.modal.classList.add('opacity-100', 'pointer-events-auto');
    }

    close() {
        console.log('Closing modal');
        this.modal.classList.remove('opacity-100', 'pointer-events-auto');
        this.modal.classList.add('opacity-0', 'pointer-events-none');

        // Stop media playback
        const audioElement = this.modal.querySelector('audio');
        if (audioElement) {
            audioElement.pause();
            audioElement.currentTime = 0;
        }

        const videoElement = this.modal.querySelector('video');
        if (videoElement) {
            videoElement.pause();
            videoElement.currentTime = 0;
        }

        // Stop WaveSurfer if exists
        if (window.wavesurfer) {
            window.wavesurfer.pause();
            window.wavesurfer.destroy();
            window.wavesurfer = null;
        }

        this.modalContent.innerHTML = '';
    }

    setContent(content) {
        this.modalContent.innerHTML = content;
        // Get the viewer type from the content
        const viewerType = this._detectViewerType(content);
        this.modal.setAttribute('data-viewer-type', viewerType);
    }

    _detectViewerType(content) {
        if (content.includes('audioPlayer')) return 'audio';
        if (content.includes('videoPlayer')) return 'video';
        if (content.includes('elan-viewer')) return 'elan';
        // Add more viewer types as needed
        return 'default';
    }
}

// Create and export the modal manager instance
const modalManager = new ModalManager();
export { modalManager };
