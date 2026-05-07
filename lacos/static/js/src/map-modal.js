(function () {
  function getModal() {
    return document.getElementById('map-modal');
  }

  function getContent() {
    return document.getElementById('map-modal-content');
  }

  function isMapTrigger(element) {
    return Boolean(element && element.closest && element.closest('[data-map-modal-trigger]'));
  }

  function ensureScript(src, isReady, key) {
    if (isReady()) return Promise.resolve();

    return new Promise(function (resolve, reject) {
      var existing = document.querySelector('script[data-lac-script="' + key + '"]');
      if (existing) {
        existing.addEventListener('load', function () { resolve(); }, { once: true });
        existing.addEventListener('error', function () {
          reject(new Error('Failed to load ' + src));
        }, { once: true });
        return;
      }

      var script = document.createElement('script');
      script.src = src;
      script.async = false;
      script.dataset.lacScript = key;
      script.onload = function () { resolve(); };
      script.onerror = function () { reject(new Error('Failed to load ' + src)); };
      document.head.appendChild(script);
    });
  }

  function registerPmtilesProtocol() {
    if (window.maplibregl && window.pmtiles && !window.__lacPmtilesRegistered) {
      var protocol = new window.pmtiles.Protocol();
      window.maplibregl.addProtocol('pmtiles', protocol.tile);
      window.__lacPmtilesRegistered = true;
    }
  }

  function initPopupMap(container) {
    if (!container || container.dataset.mapInitialized === 'true') return;

    var lat = parseFloat(container.dataset.lat);
    var lng = parseFloat(container.dataset.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || !window.maplibregl) return;

    container.dataset.mapInitialized = 'true';
    var map = new window.maplibregl.Map({
      container: container,
      style: container.dataset.styleUrl,
      center: [lng, lat],
      zoom: 5,
      maxZoom: 6,
      fadeDuration: 0,
      canvasContextAttributes: { antialias: true },
    });

    map.addControl(new window.maplibregl.NavigationControl({ showCompass: false }));
    map.on('load', function () { map.resize(); });
    requestAnimationFrame(function () { map.resize(); });

    new window.maplibregl.Marker({ color: '#005176' })
      .setLngLat([lng, lat])
      .addTo(map);
  }

  function initPopupMaps(root) {
    var scope = root || document;
    scope.querySelectorAll('[data-map-popup]').forEach(function (container) {
      var maplibreSrc = container.dataset.maplibreSrc;
      var pmtilesSrc = container.dataset.pmtilesSrc;
      ensureScript(maplibreSrc, function () { return Boolean(window.maplibregl); }, 'maplibre')
        .then(function () {
          return ensureScript(pmtilesSrc, function () { return Boolean(window.pmtiles); }, 'pmtiles');
        })
        .then(function () {
          registerPmtilesProtocol();
          initPopupMap(container);
        })
        .catch(function (error) {
          console.error('[lac-map-popup]', error);
        });
    });
  }

  function openModal() {
    var modal = getModal();
    if (!modal) return;

    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('overflow-hidden');
  }

  function closeModal() {
    var modal = getModal();
    var content = getContent();
    if (!modal) return;

    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('overflow-hidden');
    if (content) content.innerHTML = '';
  }

  document.addEventListener('click', function (event) {
    if (event.target.closest('[data-map-modal-close]')) {
      closeModal();
    }
  });

  document.addEventListener('keydown', function (event) {
    var modal = getModal();
    if (event.key === 'Escape' && modal && !modal.classList.contains('hidden')) {
      closeModal();
    }
  });

  document.addEventListener('htmx:beforeRequest', function (event) {
    if (!isMapTrigger(event.detail && event.detail.elt)) return;
    var content = getContent();
    if (content) content.innerHTML = '';
  });

  document.addEventListener('htmx:afterSwap', function (event) {
    if (event.detail && event.detail.target === getContent()) {
      openModal();
      initPopupMaps(event.detail.target);
    }
  });

  window.LacMapModal = {
    open: openModal,
    close: closeModal,
    initPopupMaps: initPopupMaps,
  };
})();
