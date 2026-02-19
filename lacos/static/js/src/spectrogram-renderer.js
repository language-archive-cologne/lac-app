/**
 * SpectrogramRenderer — vanilla canvas renderer for precomputed spectrogram data.
 *
 * Renders a 2D uint8 spectrogram array (igray colormap) onto a <canvas> that is
 * appended to the WaveSurfer wrapper, scrolling in sync with the waveform.
 *
 * Usage:
 *   const renderer = new SpectrogramRenderer(wavesurfer, data, { height: 256 });
 *   // later…
 *   renderer.destroy();
 *
 * @param {Object} wavesurfer - WaveSurfer instance (must already be created)
 * @param {number[][]} data - [n_frames][n_bins] uint8 spectrogram values
 * @param {Object} [opts]
 * @param {number} [opts.height=256] - Display height in CSS pixels
 */
(function () {
  'use strict';

  var MAX_CANVAS_WIDTH = 16384;

  function SpectrogramRenderer(wavesurfer, data, opts) {
    opts = opts || {};
    this._ws = wavesurfer;
    this._data = data;
    this._height = opts.height || 256;
    this._wrapper = null;
    this._canvas = null;
    this._offscreen = null;
    this._unsubs = [];
    this._destroyed = false;

    this._offscreen = this._createOffscreenImage(data);
    this._mount();
    this.render();
    this._listen();
  }

  /**
   * Build an off-screen canvas at native data resolution.
   * Each pixel column = one frame, each row = one frequency bin.
   * Y is flipped so low frequencies are at the bottom.
   */
  SpectrogramRenderer.prototype._createOffscreenImage = function (data) {
    var nFrames = data.length;
    var nBins = data[0].length;
    var canvas = document.createElement('canvas');
    canvas.width = nFrames;
    canvas.height = nBins;
    var ctx = canvas.getContext('2d');
    var img = ctx.createImageData(nFrames, nBins);
    var pixels = img.data;

    for (var frame = 0; frame < nFrames; frame++) {
      var col = data[frame];
      for (var bin = 0; bin < nBins; bin++) {
        // Flip Y: bin 0 (lowest freq) → bottom row
        var y = nBins - 1 - bin;
        var idx = (y * nFrames + frame) * 4;
        var v = col[bin];
        pixels[idx] = v;
        pixels[idx + 1] = v;
        pixels[idx + 2] = v;
        pixels[idx + 3] = 255;
      }
    }

    ctx.putImageData(img, 0, 0);
    return canvas;
  };

  /** Create DOM elements and append to WaveSurfer wrapper. */
  SpectrogramRenderer.prototype._mount = function () {
    var wsWrapper = this._ws.getWrapper();
    if (!wsWrapper) return;

    var wrapper = document.createElement('div');
    wrapper.style.position = 'relative';
    wrapper.style.width = '100%';
    wrapper.style.height = this._height + 'px';
    wrapper.style.overflow = 'hidden';

    var canvas = document.createElement('canvas');
    canvas.style.position = 'absolute';
    canvas.style.top = '0';
    canvas.style.left = '0';
    canvas.style.height = '100%';

    wrapper.appendChild(canvas);
    wsWrapper.appendChild(wrapper);

    this._wrapper = wrapper;
    this._canvas = canvas;
  };

  /** Draw from off-screen canvas to display canvas, scaled to WaveSurfer width. */
  SpectrogramRenderer.prototype.render = function () {
    if (this._destroyed || !this._canvas || !this._offscreen || !this._ws) return;

    var wsWrapper = this._ws.getWrapper();
    if (!wsWrapper) return;

    // scrollWidth gives the full content width (respects zoom)
    var fullWidth = wsWrapper.scrollWidth;
    var pixelWidth = Math.min(fullWidth, MAX_CANVAS_WIDTH);

    this._canvas.width = pixelWidth;
    this._canvas.height = this._height;
    // CSS width must match the scrollable content width for alignment
    this._canvas.style.width = fullWidth + 'px';

    var ctx = this._canvas.getContext('2d');
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(this._offscreen, 0, 0, pixelWidth, this._height);
  };

  /** Subscribe to WaveSurfer events that require a re-render. */
  SpectrogramRenderer.prototype._listen = function () {
    var self = this;
    var redraw = function () { self.render(); };

    var unsub = this._ws.on('redraw', redraw);
    this._unsubs.push(unsub);
  };

  /** Clean up DOM and event subscriptions. */
  SpectrogramRenderer.prototype.destroy = function () {
    if (this._destroyed) return;
    this._destroyed = true;

    for (var i = 0; i < this._unsubs.length; i++) {
      if (typeof this._unsubs[i] === 'function') {
        this._unsubs[i]();
      }
    }
    this._unsubs = [];

    if (this._wrapper && this._wrapper.parentNode) {
      this._wrapper.parentNode.removeChild(this._wrapper);
    }

    this._wrapper = null;
    this._canvas = null;
    this._offscreen = null;
    this._ws = null;
    this._data = null;
  };

  window.SpectrogramRenderer = SpectrogramRenderer;
})();
