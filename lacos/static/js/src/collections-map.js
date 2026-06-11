/*
 * Collections map for the explorer collection-list page.
 *
 * Renders a MapLibre globe with one pin per collection location, groups
 * collocated collections into a single scrollable popup, and reacts to the
 * language filter. Config (style URLs, translated legend labels) is read from
 * `#collections-map` data attributes; marker data comes from the
 * `collections-markers` json_script block. No Django template vars live here.
 */

/* ----------------------------- pure helpers ----------------------------- */

export function escHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function bundleLabel(count) {
  return count === 1 ? `${count} bundle` : `${count} bundles`;
}

export function collectionCountLabel(count) {
  return count === 1 ? `${count} collection` : `${count} collections`;
}

export function markerCollections(marker) {
  return Array.isArray(marker.collections) && marker.collections.length
    ? marker.collections
    : [marker];
}

export function isMatchMarker(marker, activeLang) {
  if (!activeLang) return false;
  return (marker.language_keys || []).includes(activeLang);
}

export function toGeoJSON(markers) {
  return {
    type: 'FeatureCollection',
    features: markers.map((m, i) => ({
      type: 'Feature',
      id: i,
      geometry: { type: 'Point', coordinates: [m.lng, m.lat] },
      properties: {
        idx: i,
        title: m.title || '',
        url: m.url || '',
        country: m.country || '',
        bundles: m.bundles || 0,
        collection_count: markerCollections(m).length,
        language_keys: (m.language_keys || []).join('|'),
      },
    })),
  };
}

/* Build the inner HTML for a marker's popup. Grouped markers (more than one
 * collocated collection) render a scrollable list; single markers render the
 * collection title, meta and language chips. */
export function buildPopupHtml(marker) {
  const collections = markerCollections(marker);
  const isGroup = collections.length > 1;
  const metaParts = [];
  if (marker.country) metaParts.push(escHtml(marker.country));
  if (isGroup) metaParts.push(collectionCountLabel(collections.length));
  if (marker.bundles) {
    metaParts.push(bundleLabel(marker.bundles));
  }
  const meta = metaParts.length
    ? `<div class="meta">${metaParts.map((p, i) => (i > 0 ? '<span class="dot">·</span>' : '') + p).join(' ')}</div>`
    : '';
  const chips = (!isGroup ? (marker.languages || []) : []).slice(0, 5).map(l =>
    `<span class="chip">${escHtml(l.display_name || l.name || '')}${l.iso ? `<span class="iso">[${escHtml(l.iso)}]</span>` : ''}</span>`
  ).join('');
  const chipsHtml = chips ? `<div class="chips">${chips}</div>` : '';
  let bodyHtml;
  if (isGroup) {
    const itemsHtml = collections.map(item => {
      const itemMeta = item.bundles ? `<div class="item-meta">${bundleLabel(item.bundles)}</div>` : '';
      return `<div class="collection-item"><a href="${escHtml(item.url)}">${escHtml(item.title)}</a>${itemMeta}</div>`;
    }).join('');
    bodyHtml = `<div class="title">${collectionCountLabel(collections.length)}</div>` +
      meta +
      `<div class="collection-list">${itemsHtml}</div>`;
  } else {
    const item = collections[0];
    bodyHtml = `<a href="${escHtml(item.url)}" class="title">${escHtml(item.title)}</a>` + meta + chipsHtml;
  }
  return '<div class="lac-popup-body">' + bodyHtml + '</div>';
}

/* Read map config from `#collections-map` data attributes. */
export function readConfig(container) {
  const d = container ? container.dataset : {};
  const styleUrl = d.styleUrl || '';
  const darkStyleUrl = d.darkStyleUrl || '';
  const withGlobe = url => url + (url.includes('?') ? '&' : '?') + 'projection=globe';
  return {
    globeStyleUrl: withGlobe(styleUrl),
    globeDarkStyleUrl: withGlobe(darkStyleUrl),
    labels: {
      collection: d.labelCollection || 'Collection',
      match: d.labelMatch || 'Match',
    },
  };
}

/* --------------------------- map orchestration --------------------------- */

const state = {
  map: null,
  markers: [],
  activeLang: '',
  loaded: false,
  config: null,
  pinsHandlersBound: false,
};

function $(id) { return document.getElementById(id); }

function loadMarkers() {
  const el = $('collections-markers');
  if (!el) return [];
  try { return JSON.parse(el.textContent.trim() || '[]'); } catch { return []; }
}

function currentActiveLang() {
  const s = $('language-filter-state');
  return s ? (s.dataset.languageFilter || '').toLowerCase() : '';
}

function renderLegend() {
  const body = $('lac-legend-body');
  if (!body) return;
  const labels = state.config ? state.config.labels : { collection: 'Collection', match: 'Match' };
  let html = `<span class="lac-legend-row"><span class="lac-legend-swatch" style="background:#005176"></span>${escHtml(labels.collection)}</span>`;
  if (state.activeLang) {
    html += `<span class="lac-legend-row"><span class="lac-legend-swatch" style="background:#ea564f"></span>${escHtml(labels.match)}</span>`;
  }
  body.innerHTML = html;
}

function fitAll(map) {
  if (!state.markers.length) return;
  const bounds = new window.maplibregl.LngLatBounds();
  state.markers.forEach(m => bounds.extend([m.lng, m.lat]));
  if (!bounds.isEmpty()) {
    map.fitBounds(bounds, { padding: 80, maxZoom: 3.2, duration: 900 });
  }
}

function applyMatchStyling() {
  const map = state.map;
  if (!map || !state.loaded) return;
  state.markers.forEach((m, i) => {
    map.setFeatureState(
      { source: 'collections', id: i },
      { match: isMatchMarker(m, state.activeLang), active: !!state.activeLang }
    );
  });
}

function focusMatches() {
  const map = state.map;
  if (!map || !state.markers.length) return;
  if (!state.activeLang) { fitAll(map); return; }
  const matches = state.markers.filter(m => isMatchMarker(m, state.activeLang));
  if (matches.length === 0) { fitAll(map); return; }
  if (matches.length === 1) {
    map.flyTo({ center: [matches[0].lng, matches[0].lat], zoom: 4, duration: 1100 });
    return;
  }
  const bounds = new window.maplibregl.LngLatBounds();
  matches.forEach(m => bounds.extend([m.lng, m.lat]));
  map.fitBounds(bounds, { padding: 100, maxZoom: 4, duration: 1100 });
}

function applyFilter() {
  state.activeLang = currentActiveLang();
  applyMatchStyling();
  renderLegend();
  focusMatches();
}

/* Keep wheel/touch scrolling inside the popup from reaching the map (zoom). */
function containPopupScroll(popup) {
  const element = popup.getElement();
  const content = element ? element.querySelector('.maplibregl-popup-content') : null;
  if (!content) return;
  ['wheel', 'touchstart', 'touchmove'].forEach(eventName => {
    content.addEventListener(eventName, event => {
      event.stopPropagation();
    }, { passive: true });
  });
}

function openPopup(marker, lngLat) {
  const popup = new window.maplibregl.Popup({
    offset: 14,
    closeButton: true,
    className: 'lac-collection-popup',
    maxWidth: '300px',
  })
    .setLngLat(lngLat)
    .setHTML(buildPopupHtml(marker))
    .addTo(state.map);
  containPopupScroll(popup);
}

function addCollectionsLayer() {
  const map = state.map;
  if (!map || map.getLayer('collections-pins')) return;
  if (!map.getSource('collections')) {
    map.addSource('collections', {
      type: 'geojson',
      data: toGeoJSON(state.markers),
      promoteId: 'idx',
    });
  }

  map.addLayer({
    id: 'collections-pins',
    type: 'circle',
    source: 'collections',
    paint: {
      'circle-radius': [
        'interpolate', ['linear'], ['zoom'],
        1, [
          'case',
          ['boolean', ['feature-state', 'match'], false],
          ['case', ['>', ['to-number', ['get', 'collection_count']], 1], 8, 7],
          ['case', ['>', ['to-number', ['get', 'collection_count']], 1], 6, 4.5]
        ],
        6, [
          'case',
          ['boolean', ['feature-state', 'match'], false],
          ['case', ['>', ['to-number', ['get', 'collection_count']], 1], 12, 11],
          ['case', ['>', ['to-number', ['get', 'collection_count']], 1], 9, 7]
        ],
      ],
      'circle-color': [
        'case',
        ['boolean', ['feature-state', 'match'], false], '#ea564f',
        '#005176',
      ],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 1.8,
      'circle-opacity': [
        'case',
        ['boolean', ['feature-state', 'active'], false],
        ['case', ['boolean', ['feature-state', 'match'], false], 1, 0.32],
        1,
      ],
    },
  });

  if (state.pinsHandlersBound) return;
  state.pinsHandlersBound = true;
  map.on('click', 'collections-pins', (e) => {
    if (!e.features || !e.features.length) return;
    const idx = e.features[0].properties.idx;
    const marker = state.markers[idx];
    if (!marker) return;
    openPopup(marker, e.lngLat);
  });
  map.on('mouseenter', 'collections-pins', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'collections-pins', () => { map.getCanvas().style.cursor = ''; });
}

function markerIndexForPk(pk) {
  if (!pk) return -1;
  return state.markers.findIndex(m => {
    if ((m.url || '').includes(pk)) return true;
    return markerCollections(m).some(item => (item.url || '').includes(pk));
  });
}

function focusCollectionOnMap(pk) {
  const idx = markerIndexForPk(pk);
  if (idx < 0) return false;
  const m = state.markers[idx];
  state.map.flyTo({ center: [m.lng, m.lat], zoom: 4.5, duration: 900 });
  state.map.once('moveend', () => openPopup(m, [m.lng, m.lat]));
  return true;
}

export function initCollectionsMap() {
  const container = $('collections-map');
  if (!container || container.dataset.mapInitialized === 'true') return;
  if (!window.maplibregl) return;
  state.markers = loadMarkers();
  if (!state.markers.length) return;
  state.config = readConfig(container);
  state.activeLang = currentActiveLang();
  renderLegend();

  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const map = new window.maplibregl.Map({
    container: container,
    style: isDark ? state.config.globeDarkStyleUrl : state.config.globeStyleUrl,
    center: [115, 5],
    zoom: 1.5,
    attributionControl: false,
    // Disable the default 300ms symbol crossfade — labels pop in/out
    // cleanly at filter thresholds instead of dragging through a fade.
    fadeDuration: 0,
  });

  map.addControl(new window.maplibregl.NavigationControl({ showCompass: false }), 'bottom-left');

  map.on('load', () => {
    state.loaded = true;
    addCollectionsLayer();
    applyMatchStyling();
    if (state.activeLang) focusMatches();
  });

  state.map = map;
  window.__lacMap = map;
  container.dataset.mapInitialized = 'true';

  const re = $('recenter-btn');
  if (re) re.onclick = () => { focusMatches(); };

  if (!window.__lacGlobeThemeObserver) {
    window.__lacGlobeThemeObserver = new MutationObserver(() => {
      const m = state.map;
      if (!m) return;
      const dark = document.documentElement.getAttribute('data-theme') === 'dark';
      const next = dark ? state.config.globeDarkStyleUrl : state.config.globeStyleUrl;
      // Force a full rebuild (diff:false) so the collections source/layer
      // state is fully reset; re-add them cleanly on style.load.
      state.loaded = false;
      m.setStyle(next, { diff: false });
      m.once('style.load', () => {
        if (m.getLayer('collections-pins')) m.removeLayer('collections-pins');
        if (m.getSource('collections')) m.removeSource('collections');
        state.loaded = true;
        addCollectionsLayer();
        applyMatchStyling();
      });
    });
    window.__lacGlobeThemeObserver.observe(document.documentElement, {
      attributes: true, attributeFilter: ['data-theme']
    });
  }
}

function refreshCollectionsMap() {
  if (typeof window.updateCollectionsMap === 'function') window.updateCollectionsMap();
}

/* ------------------------------- bootstrap ------------------------------- */

if (typeof window !== 'undefined') {
  window.updateCollectionsMap = function updateCollectionsMap() { applyFilter(); };
}

if (typeof document !== 'undefined') {
  document.body.addEventListener('click', function(event) {
    const tr = event.target.closest('tr[data-collection-pk]');
    if (!tr) return;
    if (event.target.closest('a, button, input, label')) return;
    if (!state.markers.length) return;
    focusCollectionOnMap(tr.dataset.collectionPk);
  });

  document.body.addEventListener('htmx:afterSettle', function(event) {
    const target = event.detail && event.detail.target ? event.detail.target : event.target;
    if (target && target.id === 'collection-language-shell') refreshCollectionsMap();
  });
  document.body.addEventListener('htmx:historyRestore', refreshCollectionsMap);

  initCollectionsMap();
}
