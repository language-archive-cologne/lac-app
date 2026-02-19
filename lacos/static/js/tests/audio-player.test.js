/**
 * Tests for the unified AudioPlayer class.
 *
 * Mocks WaveSurfer + SpectrogramRenderer on the global scope and verifies
 * the three decision paths: WaveSurfer+spectrogram, WaveSurfer-only, native fallback.
 */

/* eslint-env jest */

// ─── Mock factories ─────────────────────────────────────────────────────

function createMockWaveSurfer() {
    const eventHandlers = {};
    return {
        create: jest.fn(() => ({
            on: jest.fn((event, handler) => { eventHandlers[event] = handler; }),
            load: jest.fn(),
            destroy: jest.fn(),
            playPause: jest.fn(),
            play: jest.fn(),
            pause: jest.fn(),
            stop: jest.fn(),
            skip: jest.fn(),
            zoom: jest.fn(),
            setTime: jest.fn(),
            setPlaybackRate: jest.fn(),
            getDuration: jest.fn(() => 120),
            isPlaying: jest.fn(() => false),
            getWrapper: jest.fn(() => document.createElement('div')),
            _eventHandlers: eventHandlers,
        })),
        Timeline: { create: jest.fn(() => ({})) },
        Regions: {
            create: jest.fn(() => ({
                on: jest.fn(),
                enableDragSelection: jest.fn(() => jest.fn()),
            })),
        },
    };
}

function createMockSpectrogramRenderer() {
    return jest.fn(function () {
        this.destroy = jest.fn();
    });
}

// ─── DOM helpers ────────────────────────────────────────────────────────

function buildContainer(opts) {
    opts = opts || {};
    const container = document.createElement('div');

    if (opts.audioUrl) container.dataset.audioUrl = opts.audioUrl;
    if (opts.peaksUrl) container.dataset.peaksUrl = opts.peaksUrl;
    if (opts.spectrogramDataUrl) container.dataset.spectrogramDataUrl = opts.spectrogramDataUrl;

    // Audio element (omit with audioElement: false for explorer pattern)
    if (opts.audioElement !== false) {
        const audio = document.createElement('audio');
        audio.src = opts.audioUrl || '';
        container.appendChild(audio);
    }

    // Waveform target
    if (opts.waveform !== false) {
        const waveform = document.createElement('div');
        waveform.setAttribute('data-ap-waveform', '');
        container.appendChild(waveform);
    }

    // Timeline
    if (opts.timeline !== false) {
        const timeline = document.createElement('div');
        timeline.setAttribute('data-ap-timeline', '');
        container.appendChild(timeline);
    }

    // Play/pause button with icons
    if (opts.playPause !== false) {
        const btn = document.createElement('button');
        btn.setAttribute('data-ap-play-pause', '');
        const playIcon = document.createElement('svg');
        playIcon.classList.add('play-icon');
        const pauseIcon = document.createElement('svg');
        pauseIcon.classList.add('pause-icon', 'hidden');
        btn.appendChild(playIcon);
        btn.appendChild(pauseIcon);
        container.appendChild(btn);
    }

    // Stop
    if (opts.stop !== false) {
        const btn = document.createElement('button');
        btn.setAttribute('data-ap-stop', '');
        container.appendChild(btn);
    }

    // Current time / duration
    if (opts.timeDisplay !== false) {
        const ct = document.createElement('span');
        ct.setAttribute('data-ap-current-time', '');
        container.appendChild(ct);

        const dur = document.createElement('span');
        dur.setAttribute('data-ap-duration', '');
        container.appendChild(dur);
    }

    // Zoom
    if (opts.zoom !== false) {
        const slider = document.createElement('input');
        slider.type = 'range';
        slider.setAttribute('data-ap-zoom-slider', '');
        slider.min = '10';
        slider.max = '2000';
        slider.value = '100';
        container.appendChild(slider);

        const zoomIn = document.createElement('button');
        zoomIn.setAttribute('data-ap-zoom-in', '');
        container.appendChild(zoomIn);

        const zoomOut = document.createElement('button');
        zoomOut.setAttribute('data-ap-zoom-out', '');
        container.appendChild(zoomOut);
    }

    // Speed
    if (opts.speed !== false) {
        const select = document.createElement('select');
        select.setAttribute('data-ap-speed', '');
        ['0.5', '1', '1.5', '2'].forEach(v => {
            const opt = document.createElement('option');
            opt.value = v;
            opt.textContent = v + 'x';
            if (v === '1') opt.selected = true;
            select.appendChild(opt);
        });
        container.appendChild(select);
    }

    // Selection controls
    if (opts.selection !== false) {
        const toggle = document.createElement('button');
        toggle.setAttribute('data-ap-select-toggle', '');
        container.appendChild(toggle);

        const playSel = document.createElement('button');
        playSel.setAttribute('data-ap-play-selection', '');
        container.appendChild(playSel);

        const clearSel = document.createElement('button');
        clearSel.setAttribute('data-ap-clear-selection', '');
        container.appendChild(clearSel);
    }

    // Loading overlay
    if (opts.loading !== false) {
        const loading = document.createElement('div');
        loading.setAttribute('data-ap-loading', '');
        container.appendChild(loading);
    }

    return container;
}

// ─── Tests ──────────────────────────────────────────────────────────────

describe('AudioPlayer', () => {
    let AudioPlayer;
    let origFetch;

    beforeEach(() => {
        // Reset module cache so each test gets a clean import
        jest.resetModules();

        // Mock WaveSurfer globally
        global.WaveSurfer = createMockWaveSurfer();
        global.SpectrogramRenderer = createMockSpectrogramRenderer();

        // Mock fetch to resolve with valid peaks data
        origFetch = global.fetch;
        global.fetch = jest.fn(() =>
            Promise.resolve({
                ok: true,
                json: () => Promise.resolve({ data: [0.1, 0.2, 0.3], duration: 120 }),
            })
        );

        // Load the module (it writes to window.AudioPlayer or module.exports)
        AudioPlayer = require('../src/audio-player');
    });

    afterEach(() => {
        global.fetch = origFetch;
        delete global.WaveSurfer;
        delete global.SpectrogramRenderer;
    });

    // ── Happy path: creates WaveSurfer when peaks URL provided ──

    test('creates WaveSurfer when peaks URL is provided', () => {
        const container = buildContainer({
            audioUrl: 'https://example.com/audio.wav',
            peaksUrl: 'https://example.com/peaks.json',
        });

        const player = new AudioPlayer(container);

        expect(global.WaveSurfer.create).toHaveBeenCalledTimes(1);
        expect(player.wavesurfer).toBeTruthy();
        expect(player.wavesurfer.load).not.toHaveBeenCalled(); // load happens async via fetch
    });

    // ── Fallback: native audio when no peaks URL ──

    test('shows native audio when no peaks URL', () => {
        const container = buildContainer({
            audioUrl: 'https://example.com/audio.wav',
        });

        const player = new AudioPlayer(container);
        const audio = container.querySelector('audio');

        expect(global.WaveSurfer.create).not.toHaveBeenCalled();
        expect(player.wavesurfer).toBeNull();
        expect(audio.controls).toBe(true);
    });

    // ── Explorer pattern: no <audio> element, WaveSurfer loads URL directly ──

    test('creates WaveSurfer without an audio element (explorer pattern)', () => {
        const container = buildContainer({
            audioUrl: 'https://example.com/audio.wav',
            peaksUrl: 'https://example.com/peaks.json',
            audioElement: false,
        });

        const player = new AudioPlayer(container);

        expect(global.WaveSurfer.create).toHaveBeenCalledTimes(1);
        expect(player.wavesurfer).toBeTruthy();
        // No <audio> element should have been created (not in fallback)
        expect(container.querySelector('audio')).toBeNull();
    });

    // ── Fallback: creates <audio> dynamically when no element and no peaks ──

    test('creates native audio element dynamically for fallback without existing audio tag', () => {
        const container = buildContainer({
            audioUrl: 'https://example.com/audio.wav',
            audioElement: false,
        });

        const player = new AudioPlayer(container);
        const audio = container.querySelector('audio');

        expect(global.WaveSurfer.create).not.toHaveBeenCalled();
        expect(player.wavesurfer).toBeNull();
        expect(audio).toBeTruthy();
        expect(audio.controls).toBe(true);
        expect(audio.src).toContain('audio.wav');
    });

    // ── Fallback: native audio when WaveSurfer not available ──

    test('shows native audio when WaveSurfer is not available', () => {
        delete global.WaveSurfer;

        // Re-require to pick up missing WaveSurfer
        jest.resetModules();
        const AP = require('../src/audio-player');

        const container = buildContainer({
            audioUrl: 'https://example.com/audio.wav',
            peaksUrl: 'https://example.com/peaks.json',
        });

        const player = new AP(container);
        const audio = container.querySelector('audio');

        expect(player.wavesurfer).toBeNull();
        expect(audio.controls).toBe(true);
    });

    // ── Analyze mode: creates SpectrogramRenderer ──

    test('creates SpectrogramRenderer when spectrogram URL is provided', async () => {
        const container = buildContainer({
            audioUrl: 'https://example.com/audio.wav',
            peaksUrl: 'https://example.com/peaks.json',
            spectrogramDataUrl: 'https://example.com/spectrogram.json',
        });

        const player = new AudioPlayer(container);

        // Wait for async fetch calls to resolve
        await new Promise(resolve => setTimeout(resolve, 0));

        expect(global.SpectrogramRenderer).toHaveBeenCalledTimes(1);
        expect(player._spectrogramRenderer).toBeTruthy();
    });

    // ── Analyze mode: uses 256px height ──

    test('uses 256px height in analyze mode', () => {
        const container = buildContainer({
            audioUrl: 'https://example.com/audio.wav',
            peaksUrl: 'https://example.com/peaks.json',
            spectrogramDataUrl: 'https://example.com/spectrogram.json',
        });

        new AudioPlayer(container);

        const createCall = global.WaveSurfer.create.mock.calls[0][0];
        expect(createCall.height).toBe(256);
    });

    // ── Control binding: play/pause ──

    test('binds play/pause button to WaveSurfer.playPause', () => {
        const container = buildContainer({
            audioUrl: 'https://example.com/audio.wav',
            peaksUrl: 'https://example.com/peaks.json',
        });

        const player = new AudioPlayer(container);
        const btn = container.querySelector('[data-ap-play-pause]');

        btn.click();

        expect(player.wavesurfer.playPause).toHaveBeenCalledTimes(1);
    });

    // ── Control binding: zoom ──

    test('binds zoom slider to WaveSurfer.zoom', () => {
        const container = buildContainer({
            audioUrl: 'https://example.com/audio.wav',
            peaksUrl: 'https://example.com/peaks.json',
        });

        const player = new AudioPlayer(container);
        const slider = container.querySelector('[data-ap-zoom-slider]');

        slider.value = '200';
        slider.dispatchEvent(new Event('input'));

        expect(player.wavesurfer.zoom).toHaveBeenCalledWith(200);
    });

    // ── Control binding: speed ──

    test('binds speed select to WaveSurfer.setPlaybackRate', () => {
        const container = buildContainer({
            audioUrl: 'https://example.com/audio.wav',
            peaksUrl: 'https://example.com/peaks.json',
        });

        const player = new AudioPlayer(container);
        const select = container.querySelector('[data-ap-speed]');

        select.value = '1.5';
        select.dispatchEvent(new Event('change'));

        expect(player.wavesurfer.setPlaybackRate).toHaveBeenCalledWith(1.5);
    });

    // ── Destroy ──

    test('calls SpectrogramRenderer.destroy() and WaveSurfer.destroy()', async () => {
        const container = buildContainer({
            audioUrl: 'https://example.com/audio.wav',
            peaksUrl: 'https://example.com/peaks.json',
            spectrogramDataUrl: 'https://example.com/spectrogram.json',
        });

        const player = new AudioPlayer(container);
        await new Promise(resolve => setTimeout(resolve, 0));

        const wsDestroy = player.wavesurfer.destroy;
        const srDestroy = player._spectrogramRenderer.destroy;

        player.destroy();

        expect(srDestroy).toHaveBeenCalledTimes(1);
        expect(wsDestroy).toHaveBeenCalledTimes(1);
        expect(player.wavesurfer).toBeNull();
        expect(player._spectrogramRenderer).toBeNull();
    });

    // ── No crash on double destroy ──

    test('calling destroy() twice does not throw', async () => {
        const container = buildContainer({
            audioUrl: 'https://example.com/audio.wav',
            peaksUrl: 'https://example.com/peaks.json',
        });

        const player = new AudioPlayer(container);

        player.destroy();
        expect(() => player.destroy()).not.toThrow();
    });

    // ── formatTime ──

    test('formatTime returns correct m:ss.mmm format', () => {
        const container = buildContainer({
            audioUrl: 'https://example.com/audio.wav',
            peaksUrl: 'https://example.com/peaks.json',
        });
        const player = new AudioPlayer(container);

        expect(player.formatTime(0)).toBe('0:00.000');
        expect(player.formatTime(65.123)).toBe('1:05.123');
        expect(player.formatTime(-1)).toBe('0:00.000');
        expect(player.formatTime(NaN)).toBe('0:00.000');
        expect(player.formatTime(Infinity)).toBe('0:00.000');
    });

    // ── Loads peaks via fetch ──

    test('loads audio with peaks data after fetch resolves', async () => {
        const container = buildContainer({
            audioUrl: 'https://example.com/audio.wav',
            peaksUrl: 'https://example.com/peaks.json',
        });

        const player = new AudioPlayer(container);
        await new Promise(resolve => setTimeout(resolve, 0));

        expect(global.fetch).toHaveBeenCalledWith('https://example.com/peaks.json');
        expect(player.wavesurfer.load).toHaveBeenCalledWith(
            'https://example.com/audio.wav',
            [[0.1, 0.2, 0.3]],
            120
        );
    });
});
