/**
 * PitchRenderer — viewport-based canvas renderer for F0 pitch contour data.
 *
 * Renders voiced frames as amber dots on a dark background with Hz grid lines.
 * Only renders the visible portion, fetching data via HTTP Range requests for
 * large files.
 *
 * Supports two modes:
 * - Full-data mode: f0 Float32Array provided upfront
 * - Range mode: frames fetched on demand via HTTP Range requests
 *
 * Binary format (pitch.bin):
 *   Header (14 bytes):
 *     uint32 LE  n_frames
 *     uint16 LE  hop_size
 *     float32 LE f0_floor
 *     float32 LE f0_ceil
 *   Body:
 *     n_frames x float32 LE (Hz, 0.0 = unvoiced)
 *
 * @param {HTMLElement} wrapper - DOM element to contain the canvas
 * @param {Object} wsInstance - WaveSurfer v7 instance
 * @param {Object} data - { nFrames, hopSize, f0Floor, f0Ceil, dataUrl } or
 *                         { nFrames, hopSize, f0Floor, f0Ceil, f0: Float32Array }
 */
(function (global) {
  'use strict';

  var HEADER_BYTES = 14;
  var HEIGHT = 256;
  // Blue/slate palette to stay consistent with the player UI.
  var BG_COLOR = '#111827';
  var DOT_COLOR = '#ffffff';
  var GRID_COLOR = 'rgba(148,163,184,0.24)';
  var LABEL_COLOR = 'rgba(226,232,240,0.72)';
  var GRID_HZ = [100, 150, 200, 250, 300, 350, 400];
  var DOT_RADIUS = 1.5;

  function PitchRenderer(wrapper, wsInstance, data) {
    this._ws = wsInstance;
    this._wrapper = wrapper;
    this._height = HEIGHT;
    this._canvas = null;
    this._ctx = null;
    this._scrollEl = null;
    this._unsubs = [];
    this._destroyed = false;
    this._rafId = null;
    this._retryTimer = null;
    this._retryCount = 0;
    this._lastVP = null;
    this._forceNext = true;

    this._nFrames = data.nFrames | 0;
    this._hopSize = data.hopSize | 0;
    this._f0Floor = data.f0Floor;
    this._f0Ceil = data.f0Ceil;

    // Range mode state
    this._rangeMode = false;
    this._dataUrl = null;
    this._bufStart = 0;
    this._bufEnd = 0;
    this._fetching = false;
    this._fetchController = null;
    this._f0 = null;

    if (data && typeof data.dataUrl === 'string') {
      this._rangeMode = true;
      this._dataUrl = data.dataUrl;
    } else if (data && data.f0 instanceof Float32Array) {
      this._f0 = data.f0;
    }

    this._mount();
    this._listen();
    this._scheduleRender(true);
  }

  // ─── Scroll element detection ────────────────────────────────────────

  PitchRenderer.prototype._findScrollEl = function () {
    var mountEl = this._wrapper ? this._wrapper.parentElement : this._ws.getWrapper();
    if (!mountEl) return null;
    var parent = mountEl.parentElement;
    if (parent) {
      var style = window.getComputedStyle(parent);
      var ox = style.overflowX || style.overflow;
      if (ox === 'auto' || ox === 'scroll') return parent;
    }
    return mountEl;
  };

  /** Get content width from waveform siblings, excluding our own wrapper. */
  PitchRenderer.prototype._getContentWidth = function () {
    var mountEl = this._wrapper ? this._wrapper.parentElement : null;
    if (!mountEl) return 0;
    var maxRight = 0;
    var child = mountEl.firstElementChild;
    while (child) {
      if (child !== this._wrapper) {
        var w = Math.max(child.scrollWidth | 0, child.offsetWidth | 0);
        var r = (child.offsetLeft | 0) + w;
        if (r > maxRight) maxRight = r;
      }
      child = child.nextElementSibling;
    }
    return maxRight || (mountEl.scrollWidth | 0);
  };

  // ─── Mounting ────────────────────────────────────────────────────────

  PitchRenderer.prototype._mount = function () {
    this._scrollEl = this._findScrollEl();

    var canvas = document.createElement('canvas');
    canvas.style.position = 'absolute';
    canvas.style.top = '0';
    canvas.style.left = '0';
    canvas.style.height = '100%';
    canvas.style.width = '100%';
    canvas.style.display = 'block';
    canvas.style.pointerEvents = 'none';

    this._wrapper.appendChild(canvas);
    this._canvas = canvas;
    this._ctx = canvas.getContext('2d');
  };

  // ─── Range fetching ──────────────────────────────────────────────────

  PitchRenderer.prototype._fetchRange = function (needStart, needEnd) {
    if (this._destroyed || this._fetching) return;

    var nFrames = this._nFrames;
    var span = needEnd - needStart;
    var margin = span * 2;
    var fetchStart = Math.max(0, needStart - margin);
    var fetchEnd = Math.min(nFrames, needEnd + margin);

    // Each frame is a float32 (4 bytes).
    var byteStart = HEADER_BYTES + fetchStart * 4;
    var byteEnd = HEADER_BYTES + fetchEnd * 4 - 1;

    this._fetching = true;

    if (this._fetchController) {
      this._fetchController.abort();
    }
    if (typeof AbortController !== 'undefined') {
      this._fetchController = new AbortController();
    }
    var controller = this._fetchController;
    var self = this;

    fetch(this._dataUrl, {
      headers: { Range: 'bytes=' + byteStart + '-' + byteEnd },
      signal: controller ? controller.signal : undefined,
    })
      .then(function (resp) {
        if (!resp.ok || (resp.status !== 206 && resp.status !== 200)) {
          throw new Error(resp.status);
        }
        return resp.arrayBuffer().then(function (buffer) {
          return { status: resp.status, buffer: buffer };
        });
      })
      .then(function (result) {
        if (self._destroyed) return;
        var status = result.status;
        var buffer = result.buffer;

        if (status === 206) {
          if ((buffer.byteLength % 4) !== 0) {
            throw new Error('Invalid pitch range payload length');
          }
          self._f0 = new Float32Array(buffer);
          self._bufStart = fetchStart;
          self._bufEnd = fetchStart + self._f0.length;
        } else {
          // Some backends ignore Range and return the full pitch.bin.
          if (buffer.byteLength < HEADER_BYTES) {
            throw new Error('Pitch file too short');
          }
          var view = new DataView(buffer);
          var nFrames = view.getUint32(0, true);
          if (!nFrames) throw new Error('Invalid pitch header');

          self._nFrames = nFrames;
          self._f0 = new Float32Array(buffer.slice(HEADER_BYTES, HEADER_BYTES + nFrames * 4));
          self._bufStart = 0;
          self._bufEnd = self._f0.length;
          self._rangeMode = false;
          self._dataUrl = null;
        }

        self._debugLogged = false;
        self._debugDotLogged = false;
        self._forceNext = true;
        self._scheduleRender(true);
      })
      .catch(function (err) {
        if (err && err.name === 'AbortError') return;
        console.warn('Pitch range fetch failed:', err);
      })
      .finally(function () {
        self._fetching = false;
        if (self._fetchController === controller) {
          self._fetchController = null;
        }
      });
  };

  // ─── Rendering ───────────────────────────────────────────────────────

  PitchRenderer.prototype.render = function () {
    if (this._destroyed || !this._canvas || !this._scrollEl) return false;

    var fullWidth = this._getContentWidth();
    var scrollEl = this._scrollEl;
    var viewLeft = scrollEl.scrollLeft | 0;
    var viewWidth = scrollEl.clientWidth | 0;

    if (fullWidth <= 0 || viewWidth <= 0) {
      this._retryCount++;
      return false;
    }

    var visibleWidth = Math.min(viewWidth, Math.max(0, fullWidth - viewLeft));
    if (visibleWidth <= 0) return false;

    // In range mode, check if needed frames are buffered.
    if (this._rangeMode) {
      var framesPerPx = this._nFrames / fullWidth;
      var needStart = Math.max(0, Math.floor(viewLeft * framesPerPx));
      var needEnd = Math.min(this._nFrames, Math.ceil((viewLeft + visibleWidth) * framesPerPx));

      if (!this._f0 || needStart < this._bufStart || needEnd > this._bufEnd) {
        this._fetchRange(needStart, needEnd);
        if (!this._f0) return false;
      }
    }

    var vp = fullWidth + '|' + viewLeft + '|' + visibleWidth;
    if (!this._forceNext && vp === this._lastVP) return true;
    this._forceNext = false;
    this._lastVP = vp;
    this._retryCount = 0;

    // Size wrapper to match waveform content width.
    this._wrapper.style.width = fullWidth + 'px';

    // Position canvas at scroll offset within the wrapper.
    this._canvas.style.left = viewLeft + 'px';
    this._canvas.style.width = visibleWidth + 'px';

    if (this._canvas.width !== visibleWidth || this._canvas.height !== this._height) {
      this._canvas.width = visibleWidth;
      this._canvas.height = this._height;
    }

    var ctx = this._ctx;
    var height = this._height;

    // Clear with dark background.
    ctx.fillStyle = BG_COLOR;
    ctx.fillRect(0, 0, visibleWidth, height);

    // Draw Hz grid lines.
    var f0Floor = this._f0Floor;
    var f0Ceil = this._f0Ceil;
    var hzRange = f0Ceil - f0Floor;

    ctx.strokeStyle = GRID_COLOR;
    ctx.lineWidth = 1;
    ctx.font = '10px monospace';
    ctx.fillStyle = LABEL_COLOR;
    ctx.textBaseline = 'middle';

    for (var gi = 0; gi < GRID_HZ.length; gi++) {
      var hz = GRID_HZ[gi];
      if (hz < f0Floor || hz > f0Ceil) continue;
      var yNorm = (hz - f0Floor) / hzRange;
      var gy = height - yNorm * height;
      ctx.beginPath();
      ctx.moveTo(0, gy);
      ctx.lineTo(visibleWidth, gy);
      ctx.stroke();
      ctx.fillText(hz + ' Hz', 4, gy - 6);
    }

    // Draw pitch dots.
    var nFrames = this._nFrames;
    var f0 = this._f0;
    var bufOffset = this._rangeMode ? this._bufStart : 0;
    var bufLen = this._rangeMode ? (this._bufEnd - this._bufStart) : nFrames;
    var framesPerPxDot = nFrames / fullWidth;

    // DEBUG: log data stats once per fresh data load
    if (!this._debugLogged && f0) {
      var nonZero = 0, minHz = Infinity, maxHz = 0;
      for (var di = 0; di < f0.length; di++) {
        if (f0[di] > 0) { nonZero++; if (f0[di] < minHz) minHz = f0[di]; if (f0[di] > maxHz) maxHz = f0[di]; }
      }
      console.log('[PitchRenderer] f0 buffer:', {
        length: f0.length, nonZero: nonZero, minHz: minHz, maxHz: maxHz,
        nFrames: nFrames, bufOffset: bufOffset, bufLen: bufLen,
        fullWidth: fullWidth, viewLeft: viewLeft, visibleWidth: visibleWidth,
        framesPerPxDot: framesPerPxDot, f0Floor: f0Floor, f0Ceil: f0Ceil,
        rangeMode: this._rangeMode, sample0: f0[0], sample1: f0[1], sample100: f0[100],
      });
      this._debugLogged = true;
    }

    ctx.fillStyle = DOT_COLOR;
    var totalDots = 0;

    for (var px = 0; px < visibleWidth; px++) {
      var worldX = viewLeft + px;
      var fStart = Math.max(0, Math.floor(worldX * framesPerPxDot));
      var fEnd = Math.min(nFrames, Math.ceil((worldX + 1) * framesPerPxDot));
      if (fEnd <= fStart) fEnd = fStart + 1;
      if (fEnd > nFrames) fEnd = nFrames;

      // Average voiced F0 values for this pixel column.
      var sum = 0;
      var count = 0;
      for (var fi = fStart; fi < fEnd; fi++) {
        var localF = fi - bufOffset;
        if (localF >= 0 && localF < bufLen) {
          var val = f0[localF];
          if (val > 0) {
            sum += val;
            count++;
          }
        }
      }

      if (count > 0) {
        var avgHz = sum / count;
        var yN = (avgHz - f0Floor) / hzRange;
        var dy = height - yN * height;
        ctx.beginPath();
        ctx.arc(px, dy, DOT_RADIUS, 0, 2 * Math.PI);
        ctx.fill();
        totalDots++;
      }
    }

    // DEBUG
    if (totalDots === 0 && f0) {
      console.warn('[PitchRenderer] No dots drawn! Check f0 data.');
    } else if (!this._debugDotLogged && totalDots > 0) {
      console.log('[PitchRenderer] Drew', totalDots, 'dots');
      this._debugDotLogged = true;
    }

    return true;
  };

  PitchRenderer.prototype._scheduleRender = function (force) {
    if (this._destroyed) return;
    if (force) this._forceNext = true;
    if (this._rafId) return;

    var self = this;
    this._rafId = requestAnimationFrame(function () {
      self._rafId = null;
      var ok = self.render();

      if (!ok && self._retryCount <= 10 && !self._destroyed) {
        if (self._retryTimer) clearTimeout(self._retryTimer);
        self._retryTimer = setTimeout(function () {
          self._retryTimer = null;
          self._scheduleRender(true);
        }, 50);
      }
    });
  };

  // ─── Event listeners ─────────────────────────────────────────────────

  PitchRenderer.prototype._listen = function () {
    var self = this;

    var unsub1 = this._ws.on('redraw', function () { self._scheduleRender(true); });
    this._unsubs.push(unsub1);

    var unsub2 = this._ws.on('ready', function () { self._scheduleRender(true); });
    this._unsubs.push(unsub2);

    if (this._scrollEl) {
      var onScroll = function () { self._scheduleRender(false); };
      this._scrollEl.addEventListener('scroll', onScroll, { passive: true });
      this._unsubs.push(function () {
        self._scrollEl && self._scrollEl.removeEventListener('scroll', onScroll);
      });
    }
  };

  // ─── Cleanup ─────────────────────────────────────────────────────────

  PitchRenderer.prototype.destroy = function () {
    if (this._destroyed) return;
    this._destroyed = true;

    if (this._rafId) {
      cancelAnimationFrame(this._rafId);
      this._rafId = null;
    }
    if (this._retryTimer) {
      clearTimeout(this._retryTimer);
      this._retryTimer = null;
    }
    if (this._fetchController) {
      this._fetchController.abort();
      this._fetchController = null;
    }

    for (var i = 0; i < this._unsubs.length; i++) {
      if (typeof this._unsubs[i] === 'function') this._unsubs[i]();
    }
    this._unsubs = [];

    if (this._canvas && this._canvas.parentNode) {
      this._canvas.parentNode.removeChild(this._canvas);
    }

    this._ws = null;
    this._wrapper = null;
    this._canvas = null;
    this._ctx = null;
    this._scrollEl = null;
    this._f0 = null;
    this._lastVP = null;
    this._dataUrl = null;
  };

  global.PitchRenderer = PitchRenderer;
})(window);
