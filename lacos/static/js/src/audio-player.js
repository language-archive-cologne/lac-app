/**
 * AudioPlayer — unified waveform/spectrogram player for Explorer and Dashboard.
 *
 * Decision logic:
 *   1. Peaks + spectrogram available + SpectrogramRenderer → WaveSurfer + spectrogram (analyze mode)
 *   2. Peaks available, no spectrogram → WaveSurfer (simple waveform)
 *   3. No peaks / WaveSurfer missing → native <audio controls> fallback
 *
 * Usage:
 *   const player = new AudioPlayer(container, { height: 128 });
 *   // later…
 *   player.destroy();
 *
 * @param {HTMLElement} container - DOM element containing <audio>, [data-ap-waveform], and controls
 * @param {Object} [opts]
 * @param {number} [opts.height=128] - Waveform height (overridden to 384 in analyze mode)
 * @param {number} [opts.minPxPerSec=100] - Initial zoom level
 */
(function () {
  'use strict';

  function AudioPlayer(container, opts) {
    opts = opts || {};
    this._container = container;
    this._height = opts.height || 128;
    this._minPxPerSec = opts.minPxPerSec || 100;

    this.wavesurfer = null;
    this._spectrogramRenderer = null;
    this._regionsPlugin = null;
    this._activeRegion = null;
    this._selectionMode = false;
    this._disableDragSelection = null;
    this._selectionEndTime = null;
    this._selectionPlaybackActive = false;
    this._selectionPlayStartedAt = 0;
    this._spectrogramFetchController = null;
    this._loadingFallbackTimer = null;
    this._destroyed = false;

    this._init();
  }

  // ─── Helpers ──────────────────────────────────────────────────────────

  AudioPlayer.prototype.formatTime = function (seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) return '0:00.000';
    var mins = Math.floor(seconds / 60);
    var secs = seconds % 60;
    var wholeSecs = Math.floor(secs);
    var ms = Math.floor((secs - wholeSecs) * 1000);
    return mins + ':' + String(wholeSecs).padStart(2, '0') + '.' + String(ms).padStart(3, '0');
  };

  AudioPlayer.prototype._q = function (selector) {
    return this._container.querySelector(selector);
  };

  // ─── Initialization ───────────────────────────────────────────────────

  AudioPlayer.prototype._init = function () {
    var audioEl = this._container.querySelector('audio');
    var waveformEl = this._q('[data-ap-waveform]');
    var audioUrl = this._container.dataset.audioUrl;
    var peaksUrl = this._container.dataset.peaksUrl;
    var spectrogramDataUrl = this._container.dataset.spectrogramDataUrl;
    var playerMode = (this._container.dataset.playerMode || '').toLowerCase();

    // Fallback: no peaks data or WaveSurfer unavailable → native audio
    if (!peaksUrl || typeof WaveSurfer === 'undefined') {
      this._showNativeAudio(audioEl, audioUrl);
      return;
    }

    // Need at least a waveform target and an audio source (element or URL)
    if (!waveformEl || (!audioEl && !audioUrl)) {
      this._showNativeAudio(audioEl, audioUrl);
      return;
    }

    var analyzeMode = Boolean(
      spectrogramDataUrl &&
      typeof SpectrogramRenderer !== 'undefined' &&
      (playerMode === 'analyze' || playerMode === '')
    );
    var height = analyzeMode ? 384 : this._height;

    // Build plugins
    var plugins = [];
    var timelineEl = this._q('[data-ap-timeline]');
    if (timelineEl && typeof WaveSurfer.Timeline !== 'undefined') {
      plugins.push(WaveSurfer.Timeline.create({
        container: timelineEl,
        primaryLabelInterval: 10,
        secondaryLabelInterval: 5,
      }));
    }

    if (typeof WaveSurfer.Regions !== 'undefined') {
      this._regionsPlugin = WaveSurfer.Regions.create();
      plugins.push(this._regionsPlugin);
    }

    this._container.style.position = 'relative';

    this.wavesurfer = WaveSurfer.create({
      container: waveformEl,
      waveColor: analyzeMode ? 'rgba(200,200,200,0.5)' : '#64748b',
      progressColor: analyzeMode ? 'rgba(59,130,246,0.5)' : '#3b82f6',
      cursorColor: '#ef4444',
      cursorWidth: 2,
      height: height,
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      normalize: true,
      minPxPerSec: this._minPxPerSec,
      hideScrollbar: false,
      autoCenter: true,
      autoScroll: true,
      plugins: plugins,
    });

    this._bindControls();
    this._bindEvents();
    this._bindRegions();
    this._loadPeaks(audioUrl, peaksUrl);

    if (analyzeMode) {
      var self = this;
      this.wavesurfer.on('ready', function () {
        if (!self._destroyed) self._loadSpectrogram(spectrogramDataUrl, height);
      });
    }
  };

  // ─── Native audio fallback ────────────────────────────────────────────

  AudioPlayer.prototype._showNativeAudio = function (audioEl, audioUrl) {
    if (!audioEl && audioUrl) {
      // Explorer pattern: no <audio> in container — create one
      audioEl = document.createElement('audio');
      audioEl.src = audioUrl;
      audioEl.preload = 'metadata';
      audioEl.classList.add('w-full');
      this._container.prepend(audioEl);
    }
    if (!audioEl) return;
    audioEl.controls = true;
    audioEl.classList.remove('hidden');
    // Hide waveform player wrapper if present (dashboard pattern)
    var waveformPlayer = this._container.querySelector('[data-ap-waveform-player]');
    if (waveformPlayer) waveformPlayer.remove();
  };

  // ─── Control binding ──────────────────────────────────────────────────

  AudioPlayer.prototype._bindControls = function () {
    var self = this;
    var ws = this.wavesurfer;

    // Play/Pause
    var playPauseBtn = this._q('[data-ap-play-pause]');
    if (playPauseBtn) {
      playPauseBtn.addEventListener('click', function () {
        if (!ws.isPlaying() && self._activeRegion) {
          var start = Math.min(self._activeRegion.start, self._activeRegion.end);
          var end = Math.max(self._activeRegion.start, self._activeRegion.end);
          if (end > start) {
            self._selectionEndTime = end;
            self._selectionPlaybackActive = true;
            self._selectionPlayStartedAt = Date.now();
            ws.play(start);
            return;
          }
        }
        if (!self._selectionPlaybackActive) {
          self._selectionEndTime = null;
        }
        ws.playPause();
      });
    }

    // Stop
    var stopBtn = this._q('[data-ap-stop]');
    if (stopBtn) {
      stopBtn.addEventListener('click', function () {
        self._selectionPlaybackActive = false;
        self._selectionEndTime = null;
        ws.stop();
      });
    }

    // Skip backward
    var skipBackBtn = this._q('[data-ap-skip-back]');
    if (skipBackBtn) {
      var backSecs = Number(skipBackBtn.dataset.apSkipBack) || -10;
      skipBackBtn.addEventListener('click', function () {
        ws.skip(backSecs);
      });
    }

    // Skip forward
    var skipFwdBtn = this._q('[data-ap-skip-forward]');
    if (skipFwdBtn) {
      var fwdSecs = Number(skipFwdBtn.dataset.apSkipForward) || 10;
      skipFwdBtn.addEventListener('click', function () {
        ws.skip(fwdSecs);
      });
    }

    // Zoom slider
    var zoomSlider = this._q('[data-ap-zoom-slider]');
    if (zoomSlider) {
      zoomSlider.addEventListener('input', function (e) {
        ws.zoom(Number(e.target.value));
      });
    }

    // Zoom in / out buttons
    var zoomInBtn = this._q('[data-ap-zoom-in]');
    if (zoomInBtn) {
      zoomInBtn.addEventListener('click', function () {
        if (!zoomSlider) return;
        var val = Math.min(Number(zoomSlider.max) || 2000, Number(zoomSlider.value) + 25);
        zoomSlider.value = val;
        ws.zoom(val);
      });
    }

    var zoomOutBtn = this._q('[data-ap-zoom-out]');
    if (zoomOutBtn) {
      zoomOutBtn.addEventListener('click', function () {
        if (!zoomSlider) return;
        var val = Math.max(Number(zoomSlider.min) || 10, Number(zoomSlider.value) - 25);
        zoomSlider.value = val;
        ws.zoom(val);
      });
    }

    // Speed
    var speedSelect = this._q('[data-ap-speed]');
    if (speedSelect) {
      speedSelect.addEventListener('change', function (e) {
        ws.setPlaybackRate(Number(e.target.value));
      });
    }
  };

  // ─── WaveSurfer events ────────────────────────────────────────────────

  AudioPlayer.prototype._bindEvents = function () {
    var self = this;
    var ws = this.wavesurfer;

    var playPauseBtn = this._q('[data-ap-play-pause]');
    var playIcon = playPauseBtn ? playPauseBtn.querySelector('.play-icon') : null;
    var pauseIcon = playPauseBtn ? playPauseBtn.querySelector('.pause-icon') : null;
    var currentTimeEl = this._q('[data-ap-current-time]');
    var durationEl = this._q('[data-ap-duration]');
    var loadingEl = this._q('[data-ap-loading]');
    var hideLoading = function () {
      if (loadingEl) loadingEl.classList.add('hidden');
      if (self._loadingFallbackTimer) {
        clearTimeout(self._loadingFallbackTimer);
        self._loadingFallbackTimer = null;
      }
    };

    // For dashboard-style text toggle (Play/Pause text button)
    var playToggleText = this._q('[data-ap-play-toggle-text]');

    var updatePlayPauseIcon = function (playing) {
      if (playIcon && pauseIcon) {
        playIcon.classList.toggle('hidden', playing);
        pauseIcon.classList.toggle('hidden', !playing);
      }
      if (playToggleText) {
        playToggleText.textContent = playing ? 'Pause' : 'Play';
      }
    };

    ws.on('ready', function () {
      hideLoading();
      if (durationEl) durationEl.textContent = self.formatTime(ws.getDuration());
    });

    // Some WaveSurfer backends/setups surface usability via decode/timeupdate
    // before emitting ready consistently. Clear overlay as soon as playback data is flowing.
    ws.on('decode', function () { hideLoading(); });

    ws.on('timeupdate', function (time) {
      hideLoading();
      if (currentTimeEl) currentTimeEl.textContent = self.formatTime(time);
      if (self._selectionPlaybackActive && self._selectionEndTime !== null && time >= self._selectionEndTime) {
        // Skip end-check briefly after play(start) to let the seek take effect
        if (Date.now() - self._selectionPlayStartedAt < 150) return;
        self._selectionPlaybackActive = false;
        ws.pause();
      }
    });

    ws.on('play', function () { updatePlayPauseIcon(true); });
    ws.on('pause', function () { updatePlayPauseIcon(false); });

    ws.on('finish', function () {
      updatePlayPauseIcon(false);
      self._selectionPlaybackActive = false;
      self._selectionEndTime = null;
    });

    ws.on('error', function (err) {
      console.error('WaveSurfer error:', err);
      if (loadingEl) {
        loadingEl.innerHTML = '<span class="text-error">Error loading audio</span>';
      }
    });

    // Safety net: never keep the overlay forever if events are delayed/missed.
    this._loadingFallbackTimer = setTimeout(function () {
      hideLoading();
    }, 3000);
  };

  // ─── Regions (selection) ──────────────────────────────────────────────

  AudioPlayer.prototype._bindRegions = function () {
    var self = this;
    var rp = this._regionsPlugin;
    var selectToggleBtn = this._q('[data-ap-select-toggle]');
    var playSelectionBtn = this._q('[data-ap-play-selection]');
    var clearSelectionBtn = this._q('[data-ap-clear-selection]');

    if (!rp) {
      if (selectToggleBtn) selectToggleBtn.disabled = true;
      if (playSelectionBtn) playSelectionBtn.disabled = true;
      if (clearSelectionBtn) clearSelectionBtn.disabled = true;
      return;
    }

    this._selectionMode = true;
    this._disableDragSelection = rp.enableDragSelection({ color: 'rgba(59, 130, 246, 0.2)' });

    var updateSelectionUi = function () {
      if (!selectToggleBtn || !playSelectionBtn || !clearSelectionBtn) return;
      var hasRegion = Boolean(self._activeRegion);
      playSelectionBtn.disabled = !hasRegion;
      clearSelectionBtn.disabled = !hasRegion;
      selectToggleBtn.classList.toggle('btn-active', self._selectionMode);
      selectToggleBtn.setAttribute('aria-pressed', self._selectionMode ? 'true' : 'false');
    };

    var playSelection = function (region) {
      if (!region) return;
      var start = Math.min(region.start, region.end);
      var end = Math.max(region.start, region.end);
      if (end <= start) return;
      self._selectionEndTime = end;
      self._selectionPlaybackActive = true;
      self._selectionPlayStartedAt = Date.now();
      self.wavesurfer.play(start);
    };

    rp.on('region-created', function (region) {
      if (self._activeRegion && self._activeRegion !== region) {
        self._activeRegion.remove();
      }
      self._activeRegion = region;
      updateSelectionUi();
    });

    rp.on('region-updated', function (region) {
      self._activeRegion = region;
      updateSelectionUi();
    });

    rp.on('region-removed', function (region) {
      if (self._activeRegion === region) {
        self._activeRegion = null;
        self._selectionPlaybackActive = false;
        self._selectionEndTime = null;
      }
      updateSelectionUi();
    });

    rp.on('region-clicked', function (region, event) {
      event.stopPropagation();
      self._activeRegion = region;
      updateSelectionUi();
    });

    rp.on('region-double-clicked', function (region, event) {
      event.stopPropagation();
      self._activeRegion = region;
      updateSelectionUi();
      playSelection(region);
    });

    if (selectToggleBtn) {
      selectToggleBtn.addEventListener('click', function () {
        self._selectionMode = !self._selectionMode;
        if (self._selectionMode && !self._disableDragSelection) {
          self._disableDragSelection = rp.enableDragSelection({ color: 'rgba(59, 130, 246, 0.2)' });
        } else if (!self._selectionMode && self._disableDragSelection) {
          self._disableDragSelection();
          self._disableDragSelection = null;
        }
        updateSelectionUi();
      });
    }

    if (playSelectionBtn) {
      playSelectionBtn.addEventListener('click', function () {
        playSelection(self._activeRegion);
      });
    }

    if (clearSelectionBtn) {
      clearSelectionBtn.addEventListener('click', function () {
        if (self._activeRegion) {
          self._activeRegion.remove();
          self._activeRegion = null;
        }
        self._selectionPlaybackActive = false;
        self._selectionEndTime = null;
        updateSelectionUi();
      });
    }

    updateSelectionUi();
  };

  // ─── Data loading ─────────────────────────────────────────────────────

  AudioPlayer.prototype._loadPeaks = function (audioUrl, peaksUrl) {
    var self = this;
    fetch(peaksUrl)
      .then(function (resp) { if (!resp.ok) throw new Error(resp.status); return resp.json(); })
      .then(function (peaksData) {
        if (!self.wavesurfer) return;
        if (Array.isArray(peaksData && peaksData.data) && Number.isFinite(peaksData && peaksData.duration)) {
          self.wavesurfer.load(audioUrl, [peaksData.data], peaksData.duration);
        } else {
          self.wavesurfer.load(audioUrl);
        }
      })
      .catch(function () {
        if (self.wavesurfer) self.wavesurfer.load(audioUrl);
      });
  };

  AudioPlayer.prototype._loadSpectrogram = function (url, height) {
    var self = this;
    if (this._spectrogramFetchController) {
      this._spectrogramFetchController.abort();
      this._spectrogramFetchController = null;
    }

    var cache = AudioPlayer._spectrogramCache || (AudioPlayer._spectrogramCache = new Map());
    var cacheKey = this._spectrogramCacheKey(url);
    var cached = cache.get(cacheKey);
    if (cached) {
      // Keep cache entry hot (simple LRU behavior).
      cache.delete(cacheKey);
      cache.set(cacheKey, cached);
      if (!self.wavesurfer || self._destroyed) return;
      self._spectrogramRenderer = new SpectrogramRenderer(self.wavesurfer, cached, { height: height });
      return;
    }

    if (typeof AbortController !== 'undefined') {
      this._spectrogramFetchController = new AbortController();
    }
    var controller = this._spectrogramFetchController;

    fetch(url, controller ? { signal: controller.signal } : undefined)
      .then(function (resp) { if (!resp.ok) throw new Error(resp.status); return resp.arrayBuffer(); })
      .then(function (buffer) {
        if (!self.wavesurfer || self._destroyed) return;
        var parsed = self._parseSpectrogramBuffer(buffer);
        if (!parsed) return;

        cache.set(cacheKey, parsed);
        // Cap cache size to avoid unbounded memory growth.
        while (cache.size > 3) {
          var oldestKey = cache.keys().next().value;
          cache.delete(oldestKey);
        }

        self._spectrogramRenderer = new SpectrogramRenderer(self.wavesurfer, parsed, { height: height });
      })
      .catch(function (err) {
        if (err && err.name === 'AbortError') return;
        console.warn('Spectrogram data unavailable:', err);
      })
      .finally(function () {
        if (self._spectrogramFetchController === controller) {
          self._spectrogramFetchController = null;
        }
      });
  };

  AudioPlayer.prototype._spectrogramCacheKey = function (url) {
    if (typeof url !== 'string') return String(url);
    var qIdx = url.indexOf('?');
    return qIdx === -1 ? url : url.slice(0, qIdx);
  };

  AudioPlayer.prototype._parseSpectrogramBuffer = function (buffer) {
    if (!buffer || buffer.byteLength < 6) return null;

    var view = new DataView(buffer);
    var nFrames = view.getUint32(0, true);
    var nBins = view.getUint16(4, true);
    if (!nFrames || !nBins) return null;

    var expectedLen = nFrames * nBins;
    var body = new Uint8Array(buffer, 6);
    if (body.byteLength < expectedLen) return null;

    return {
      nFrames: nFrames,
      nBins: nBins,
      flat: body.subarray(0, expectedLen),
    };
  };

  // ─── Cleanup ──────────────────────────────────────────────────────────

  AudioPlayer.prototype.destroy = function () {
    if (this._destroyed) return;
    this._destroyed = true;

    if (this._spectrogramRenderer) {
      this._spectrogramRenderer.destroy();
      this._spectrogramRenderer = null;
    }

    if (this._spectrogramFetchController) {
      this._spectrogramFetchController.abort();
      this._spectrogramFetchController = null;
    }

    if (this.wavesurfer) {
      this.wavesurfer.destroy();
      this.wavesurfer = null;
    }

    this._regionsPlugin = null;
    this._activeRegion = null;
    this._container = null;
  };

  // ─── Export ───────────────────────────────────────────────────────────

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = AudioPlayer;
  } else {
    window.AudioPlayer = AudioPlayer;
  }
})();
