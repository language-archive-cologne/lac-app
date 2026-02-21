/**
 * SpectrogramRenderer — viewport-based canvas renderer for precomputed spectrogram data.
 *
 * Renders only the visible portion of a 2D uint8 spectrogram array directly from
 * raw data, avoiding full-width offscreen canvases that exceed browser limits on
 * long files (131K+ frames).
 *
 * Optimizations:
 * - Flattened data array for cache-friendly access
 * - Sliding-window frame accumulator (incremental, not per-pixel recompute)
 * - Packed 32-bit Inferno LUT writes via Uint32Array
 * - Precomputed Y-to-bin map for vertical scaling + Y-flip
 *
 * @param {Object} wavesurfer - WaveSurfer v7 instance
 * @param {Array<Uint8Array>|number[][]|Object} data
 *   Either [n_frames][n_bins] uint8 values, or:
 *   { nFrames: number, nBins: number, flat: Uint8Array }.
 * @param {Object} [opts]
 * @param {number} [opts.height=384] - Display height in CSS pixels
 */
(function () {
  'use strict';

  /* Inferno colormap LUT — 256 entries of [R, G, B]. */
  /* prettier-ignore */
  var INFERNO_LUT = [
    [0,0,4],[1,0,5],[1,1,6],[1,1,8],[2,1,10],[2,2,12],[2,2,14],[3,2,16],
    [4,3,18],[4,3,20],[5,4,23],[6,4,25],[7,5,27],[8,5,29],[9,6,31],[10,7,34],
    [11,7,36],[12,8,38],[13,8,41],[14,9,43],[16,9,45],[17,10,48],[18,10,50],[20,11,52],
    [21,11,55],[22,11,57],[24,12,60],[25,12,62],[27,12,65],[28,12,67],[30,12,69],[31,12,72],
    [33,12,74],[35,12,76],[36,12,79],[38,12,81],[40,11,83],[41,11,85],[43,11,87],[45,11,89],
    [47,10,91],[49,10,92],[50,10,94],[52,10,95],[54,9,97],[56,9,98],[57,9,99],[59,9,100],
    [61,9,101],[62,9,102],[64,10,103],[66,10,104],[68,10,104],[69,10,105],[71,11,106],[73,11,106],
    [74,12,107],[76,12,107],[77,13,108],[79,13,108],[81,14,108],[82,14,109],[84,15,109],[85,15,109],
    [87,16,110],[89,16,110],[90,17,110],[92,18,110],[93,18,110],[95,19,110],[97,19,110],[98,20,110],
    [100,21,110],[101,21,110],[103,22,110],[105,22,110],[106,23,110],[108,24,110],[109,24,110],[111,25,110],
    [113,25,110],[114,26,110],[116,26,110],[117,27,110],[119,28,109],[120,28,109],[122,29,109],[124,29,109],
    [125,30,109],[127,30,108],[128,31,108],[130,32,108],[132,32,107],[133,33,107],[135,33,107],[136,34,106],
    [138,34,106],[140,35,105],[141,35,105],[143,36,105],[144,37,104],[146,37,104],[147,38,103],[149,38,103],
    [151,39,102],[152,39,102],[154,40,101],[155,41,100],[157,41,100],[159,42,99],[160,42,99],[162,43,98],
    [163,44,97],[165,44,96],[166,45,96],[168,46,95],[169,46,94],[171,47,94],[173,48,93],[174,48,92],
    [176,49,91],[177,50,90],[179,50,90],[180,51,89],[182,52,88],[183,53,87],[185,53,86],[186,54,85],
    [188,55,84],[189,56,83],[191,57,82],[192,58,81],[193,58,80],[195,59,79],[196,60,78],[198,61,77],
    [199,62,76],[200,63,75],[202,64,74],[203,65,73],[204,66,72],[206,67,71],[207,68,70],[208,69,69],
    [210,70,68],[211,71,67],[212,72,66],[213,74,65],[215,75,63],[216,76,62],[217,77,61],[218,78,60],
    [219,80,59],[221,81,58],[222,82,56],[223,83,55],[224,85,54],[225,86,53],[226,87,52],[227,89,51],
    [228,90,49],[229,92,48],[230,93,47],[231,94,46],[232,96,45],[233,97,43],[234,99,42],[235,100,41],
    [235,102,40],[236,103,38],[237,105,37],[238,106,36],[239,108,35],[239,110,33],[240,111,32],[241,113,31],
    [241,115,29],[242,116,28],[243,118,27],[243,120,25],[244,121,24],[245,123,23],[245,125,21],[246,126,20],
    [246,128,19],[247,130,18],[247,132,16],[248,133,15],[248,135,14],[248,137,12],[249,139,11],[249,140,10],
    [249,142,9],[250,144,8],[250,146,7],[250,148,7],[251,150,6],[251,151,6],[251,153,6],[251,155,6],
    [251,157,7],[252,159,7],[252,161,8],[252,163,9],[252,165,10],[252,166,12],[252,168,13],[252,170,15],
    [252,172,17],[252,174,18],[252,176,20],[252,178,22],[252,180,24],[251,182,26],[251,184,29],[251,186,31],
    [251,188,33],[251,190,35],[250,192,38],[250,194,40],[250,196,42],[250,198,45],[249,199,47],[249,201,50],
    [249,203,53],[248,205,55],[248,207,58],[247,209,61],[247,211,64],[246,213,67],[246,215,70],[245,217,73],
    [245,219,76],[244,221,79],[244,223,83],[244,225,86],[243,227,90],[243,229,93],[242,230,97],[242,232,101],
    [242,234,105],[241,236,109],[241,237,113],[241,239,117],[241,241,121],[242,242,125],[242,244,130],[243,245,134],
    [243,246,138],[244,248,142],[245,249,146],[246,250,150],[248,251,154],[249,252,157],[250,253,161],[252,255,164]
  ];

  // Build packed 32-bit LUT for fast pixel writes via Uint32Array.
  var IS_LITTLE_ENDIAN = new Uint8Array(new Uint32Array([0x11223344]).buffer)[0] === 0x44;
  var LUT32 = new Uint32Array(256);
  for (var li = 0; li < 256; li++) {
    var c = INFERNO_LUT[li];
    LUT32[li] = IS_LITTLE_ENDIAN
      ? ((255 << 24) | (c[2] << 16) | (c[1] << 8) | c[0])
      : ((c[0] << 24) | (c[1] << 16) | (c[2] << 8) | 255);
  }

  function SpectrogramRenderer(wavesurfer, data, opts) {
    opts = opts || {};
    this._ws = wavesurfer;
    this._height = (opts.height || 384) | 0;
    this._wrapper = null;
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
    this._imgData = null;
    this._imgW = 0;
    this._imgH = 0;
    this._yToBin = null;

    // Normalize into contiguous flat uint8 data for cache-friendly access.
    if (data && data.flat instanceof Uint8Array) {
      this._nFrames = data.nFrames | 0;
      this._nBins = data.nBins | 0;
      var expectedLen = this._nFrames * this._nBins;
      if (expectedLen <= 0 || data.flat.length < expectedLen) {
        throw new Error('Invalid spectrogram data dimensions');
      }
      this._flat = data.flat.subarray(0, expectedLen);
    } else {
      this._nFrames = data.length;
      this._nBins = data[0].length;
      this._flat = this._flattenData(data);
    }
    this._sums = new Int32Array(this._nBins);

    this._mount();
    this._listen();
    this._scheduleRender(true);
  }

  /** Flatten [nFrames][nBins] into a contiguous Uint8Array. */
  SpectrogramRenderer.prototype._flattenData = function (data) {
    var nF = this._nFrames;
    var nB = this._nBins;

    // Check if already contiguous (subarray views into one buffer).
    var first = data[0];
    if (first.buffer && first.byteOffset !== undefined) {
      var contiguous = true;
      for (var i = 1; i < nF; i++) {
        if (data[i].buffer !== first.buffer ||
            data[i].byteOffset !== first.byteOffset + i * nB) {
          contiguous = false;
          break;
        }
      }
      if (contiguous) {
        return new Uint8Array(first.buffer, first.byteOffset, nF * nB);
      }
    }

    var flat = new Uint8Array(nF * nB);
    for (var f = 0; f < nF; f++) {
      flat.set(data[f], f * nB);
    }
    return flat;
  };

  /** Build Y-pixel to frequency-bin map (with Y-flip: bin 0 at bottom). */
  SpectrogramRenderer.prototype._ensureYMap = function () {
    if (this._yToBin && this._yToBin.length === this._height) return;
    var map = new Uint16Array(this._height);
    for (var y = 0; y < this._height; y++) {
      var flipped = this._height - 1 - y;
      var bin = (flipped * this._nBins / this._height) | 0;
      if (bin >= this._nBins) bin = this._nBins - 1;
      map[y] = bin;
    }
    this._yToBin = map;
  };

  /** Find the actual scrollable parent element. */
  SpectrogramRenderer.prototype._findScrollEl = function (mountEl) {
    if (!mountEl) return null;
    // WaveSurfer v7: getWrapper() returns the content div; its parent is the scroll container.
    var parent = mountEl.parentElement;
    if (parent) {
      var style = window.getComputedStyle(parent);
      var ox = style.overflowX || style.overflow;
      if (ox === 'auto' || ox === 'scroll') return parent;
    }
    return mountEl;
  };

  /** Get content width from WaveSurfer's children, excluding our wrapper. */
  SpectrogramRenderer.prototype._getContentWidth = function () {
    var mountEl = this._wrapper ? this._wrapper.parentElement : null;
    if (!mountEl) return 0;

    // Measure from sibling canvases (WaveSurfer's waveform) to avoid feedback loops.
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

  SpectrogramRenderer.prototype._mount = function () {
    var mountEl = this._ws.getWrapper();
    if (!mountEl) return;

    this._scrollEl = this._findScrollEl(mountEl);

    var wrapper = document.createElement('div');
    wrapper.style.position = 'relative';
    wrapper.style.display = 'block';
    wrapper.style.width = '0px';
    wrapper.style.height = this._height + 'px';
    wrapper.style.overflow = 'hidden';
    wrapper.style.pointerEvents = 'none';

    var canvas = document.createElement('canvas');
    canvas.style.position = 'absolute';
    canvas.style.top = '0';
    canvas.style.left = '0';
    canvas.style.height = '100%';
    canvas.style.display = 'block';

    wrapper.appendChild(canvas);
    mountEl.appendChild(wrapper);

    this._wrapper = wrapper;
    this._canvas = canvas;
    this._ctx = canvas.getContext('2d');
  };

  /**
   * Render the visible viewport of the spectrogram.
   * Uses a sliding-window accumulator over frames for O(width * bins) work.
   */
  SpectrogramRenderer.prototype.render = function () {
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
      this._imgData = null;
    }

    this._ensureYMap();

    if (!this._imgData || this._imgW !== visibleWidth || this._imgH !== this._height) {
      this._imgData = this._ctx.createImageData(visibleWidth, this._height);
      this._imgW = visibleWidth;
      this._imgH = this._height;
    }

    var pixels32 = new Uint32Array(this._imgData.data.buffer);
    this._paintViewport(pixels32, visibleWidth, this._height, viewLeft, fullWidth);
    this._ctx.putImageData(this._imgData, 0, 0);

    return true;
  };

  /** Paint the visible columns using a sliding-window frame accumulator. */
  SpectrogramRenderer.prototype._paintViewport = function (pixels32, width, height, viewLeft, fullWidth) {
    var nBins = this._nBins;
    var nFrames = this._nFrames;
    var flat = this._flat;
    var sums = this._sums;
    var yToBin = this._yToBin;
    var framesPerPx = nFrames / fullWidth;

    // Seed the accumulator for the first pixel column.
    var prevStart = Math.max(0, Math.floor(viewLeft * framesPerPx));
    var prevEnd = Math.min(nFrames, Math.floor((viewLeft + 1) * framesPerPx));
    if (prevEnd <= prevStart) prevEnd = prevStart + 1;
    if (prevEnd > nFrames) prevEnd = nFrames;

    var bin, f, off;
    for (bin = 0; bin < nBins; bin++) sums[bin] = 0;
    for (f = prevStart; f < prevEnd; f++) {
      off = f * nBins;
      for (bin = 0; bin < nBins; bin++) sums[bin] += flat[off + bin];
    }

    for (var px = 0; px < width; px++) {
      if (px > 0) {
        var worldX = viewLeft + px;
        var curStart = Math.max(0, Math.floor(worldX * framesPerPx));
        var curEnd = Math.min(nFrames, Math.floor((worldX + 1) * framesPerPx));
        if (curEnd <= curStart) curEnd = curStart + 1;
        if (curEnd > nFrames) curEnd = nFrames;

        // Slide window: subtract frames that left, add frames that entered.
        for (f = prevStart; f < curStart; f++) {
          off = f * nBins;
          for (bin = 0; bin < nBins; bin++) sums[bin] -= flat[off + bin];
        }
        for (f = prevEnd; f < curEnd; f++) {
          off = f * nBins;
          for (bin = 0; bin < nBins; bin++) sums[bin] += flat[off + bin];
        }

        prevStart = curStart;
        prevEnd = curEnd;
      }

      // Compute averaged color per bin.
      var count = prevEnd - prevStart;
      if (count < 1) count = 1;

      // Fill this x-column (top to bottom), using the precomputed Y-to-bin map.
      var outIdx = px;
      for (var y = 0; y < height; y++) {
        var val = ((sums[yToBin[y]] + (count >> 1)) / count) | 0;
        pixels32[outIdx] = LUT32[val];
        outIdx += width;
      }
    }
  };

  SpectrogramRenderer.prototype._scheduleRender = function (force) {
    if (this._destroyed) return;
    if (force) this._forceNext = true;
    if (this._rafId) return;

    var self = this;
    this._rafId = requestAnimationFrame(function () {
      self._rafId = null;
      var ok = self.render();

      // Retry if WaveSurfer hasn't laid out yet.
      if (!ok && self._retryCount <= 10 && !self._destroyed) {
        if (self._retryTimer) clearTimeout(self._retryTimer);
        self._retryTimer = setTimeout(function () {
          self._retryTimer = null;
          self._scheduleRender(true);
        }, 50);
      }
    });
  };

  SpectrogramRenderer.prototype._listen = function () {
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

  SpectrogramRenderer.prototype.destroy = function () {
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

    for (var i = 0; i < this._unsubs.length; i++) {
      if (typeof this._unsubs[i] === 'function') this._unsubs[i]();
    }
    this._unsubs = [];

    if (this._wrapper && this._wrapper.parentNode) {
      this._wrapper.parentNode.removeChild(this._wrapper);
    }

    this._ws = null;
    this._wrapper = null;
    this._canvas = null;
    this._ctx = null;
    this._scrollEl = null;
    this._flat = null;
    this._sums = null;
    this._yToBin = null;
    this._imgData = null;
    this._lastVP = null;
  };

  window.SpectrogramRenderer = SpectrogramRenderer;
})();
