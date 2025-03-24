// Project-specific JavaScript

// Initialize mobile menu toggle
document.addEventListener('DOMContentLoaded', function() {
  // Mobile menu toggle
  const mobileMenuButton = document.querySelector('[aria-controls="mobile-menu"]');
  const mobileMenu = document.getElementById('mobile-menu');
  
  if (mobileMenuButton && mobileMenu) {
    mobileMenuButton.addEventListener('click', function() {
      const expanded = this.getAttribute('aria-expanded') === 'true';
      this.setAttribute('aria-expanded', !expanded);
      
      // Toggle visibility of menu
      mobileMenu.classList.toggle('hidden');
      
      // Toggle icons
      const openIcon = this.querySelector('.block');
      const closeIcon = this.querySelector('.hidden');
      
      if (openIcon && closeIcon) {
        openIcon.classList.toggle('block');
        openIcon.classList.toggle('hidden');
        closeIcon.classList.toggle('block');
        closeIcon.classList.toggle('hidden');
      }
    });
  }
  
  // Initialize Prism.js for syntax highlighting if needed
  if (typeof Prism !== 'undefined') {
    Prism.highlightAll();
  }
  
  // Initialize any WaveSurfer instances if needed
  initializeWaveSurfer();
});

// Function to initialize WaveSurfer instances
function initializeWaveSurfer() {
  const wavesurferContainers = document.querySelectorAll('.wavesurfer-container');
  
  wavesurferContainers.forEach(container => {
    const audioUrl = container.dataset.audioUrl;
    if (!audioUrl) return;
    
    const wavesurfer = WaveSurfer.create({
      container: container,
      waveColor: '#4a83ff',
      progressColor: '#1a56db',
      height: 80,
      responsive: true,
      barWidth: 2,
      barGap: 1,
      cursorWidth: 1
    });
    
    wavesurfer.load(audioUrl);
    
    // Add play/pause button functionality
    const playButton = container.parentElement.querySelector('.wavesurfer-play');
    if (playButton) {
      playButton.addEventListener('click', function() {
        wavesurfer.playPause();
        this.innerHTML = wavesurfer.isPlaying() ? 
          '<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>' : 
          '<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>';
      });
    }
  });
}
