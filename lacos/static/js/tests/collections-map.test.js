/* eslint-env jest */

import {
  escHtml,
  bundleLabel,
  collectionCountLabel,
  markerCollections,
  isMatchMarker,
  toGeoJSON,
  buildPopupHtml,
  readConfig,
} from '../src/collections-map.js';

describe('escHtml', () => {
  test('escapes HTML-significant characters', () => {
    expect(escHtml('<a href="x">a&b\'c</a>')).toBe(
      '&lt;a href=&quot;x&quot;&gt;a&amp;b&#39;c&lt;/a&gt;'
    );
  });

  test('coerces null/undefined to an empty string', () => {
    expect(escHtml(null)).toBe('');
    expect(escHtml(undefined)).toBe('');
  });
});

describe('count labels', () => {
  test('singular vs plural', () => {
    expect(bundleLabel(1)).toBe('1 bundle');
    expect(bundleLabel(3)).toBe('3 bundles');
    expect(collectionCountLabel(1)).toBe('1 collection');
    expect(collectionCountLabel(2)).toBe('2 collections');
  });
});

describe('markerCollections', () => {
  test('returns the grouped collections when present', () => {
    const marker = { collections: [{ title: 'A' }, { title: 'B' }] };
    expect(markerCollections(marker)).toHaveLength(2);
  });

  test('falls back to the marker itself when not grouped', () => {
    const marker = { title: 'Solo' };
    expect(markerCollections(marker)).toEqual([marker]);
  });

  test('treats an empty collections array as not grouped', () => {
    const marker = { title: 'Solo', collections: [] };
    expect(markerCollections(marker)).toEqual([marker]);
  });
});

describe('isMatchMarker', () => {
  test('matches when the active language is in the marker keys', () => {
    expect(isMatchMarker({ language_keys: ['deu', 'eng'] }, 'eng')).toBe(true);
  });

  test('is false without an active language', () => {
    expect(isMatchMarker({ language_keys: ['eng'] }, '')).toBe(false);
  });

  test('is false when the marker has no language keys', () => {
    expect(isMatchMarker({}, 'eng')).toBe(false);
  });
});

describe('toGeoJSON', () => {
  const sample = {
    lng: 10,
    lat: 20,
    title: 'A',
    url: '/a',
    country: 'DE',
    bundles: 2,
    language_keys: ['deu', 'eng'],
    collections: [{ title: 'A' }, { title: 'B' }],
  };

  test('maps markers to features with derived properties', () => {
    const fc = toGeoJSON([sample]);
    expect(fc.type).toBe('FeatureCollection');
    const f = fc.features[0];
    expect(f.geometry.coordinates).toEqual([10, 20]);
    expect(f.properties.idx).toBe(0);
    expect(f.properties.collection_count).toBe(2);
    expect(f.properties.language_keys).toBe('deu|eng');
  });

  test('without an active language, match and active are false', () => {
    const f = toGeoJSON([sample]).features[0];
    expect(f.properties.match).toBe(false);
    expect(f.properties.active).toBe(false);
  });

  test('with an active language, sets match per marker and active globally', () => {
    const features = toGeoJSON(
      [sample, { lng: 1, lat: 1, language_keys: ['fra'] }],
      'eng',
    ).features;
    expect(features[0].properties.match).toBe(true);   // has 'eng'
    expect(features[1].properties.match).toBe(false);  // only 'fra'
    expect(features[0].properties.active).toBe(true);
    expect(features[1].properties.active).toBe(true);
  });
});

describe('buildPopupHtml', () => {
  test('single collection renders a title link and language chips, no list', () => {
    const html = buildPopupHtml({
      title: 'Mongol Tales',
      url: '/c/1',
      country: 'Mongolia',
      bundles: 3,
      languages: [{ display_name: 'Khalkha', iso: 'khk' }],
    });
    expect(html).toContain('<a href="/c/1" class="title">Mongol Tales</a>');
    expect(html).toContain('3 bundles');
    expect(html).toContain('class="chip"');
    expect(html).toContain('[khk]');
    expect(html).not.toContain('collection-list');
  });

  test('grouped marker renders a scrollable list of collection items, no chips', () => {
    const html = buildPopupHtml({
      country: 'Mongolia',
      collections: [
        { title: 'First', url: '/c/1', bundles: 1 },
        { title: 'Second', url: '/c/2', bundles: 4 },
      ],
      languages: [{ display_name: 'Khalkha', iso: 'khk' }],
    });
    expect(html).toContain('<div class="title">2 collections</div>');
    expect(html).toContain('class="collection-list"');
    expect((html.match(/class="collection-item"/g) || [])).toHaveLength(2);
    expect(html).toContain('<a href="/c/1">First</a>');
    expect(html).toContain('1 bundle');
    expect(html).toContain('4 bundles');
    // language chips are suppressed for grouped popups
    expect(html).not.toContain('class="chip"');
  });

  test('escapes untrusted titles and urls', () => {
    const html = buildPopupHtml({ title: '<script>x</script>', url: '"></a>' });
    expect(html).not.toContain('<script>x</script>');
    expect(html).toContain('&lt;script&gt;x&lt;/script&gt;');
  });
});

describe('readConfig', () => {
  test('appends the globe projection param, handling existing query strings', () => {
    const cfg = readConfig({
      dataset: {
        styleUrl: 'https://maps/style.json',
        darkStyleUrl: 'https://maps/dark.json?v=2',
        labelCollection: 'Sammlung',
        labelMatch: 'Treffer',
      },
    });
    expect(cfg.globeStyleUrl).toBe('https://maps/style.json?projection=globe');
    expect(cfg.globeDarkStyleUrl).toBe('https://maps/dark.json?v=2&projection=globe');
    expect(cfg.labels).toEqual({ collection: 'Sammlung', match: 'Treffer' });
  });

  test('falls back to English labels when not provided', () => {
    const cfg = readConfig({ dataset: {} });
    expect(cfg.labels).toEqual({ collection: 'Collection', match: 'Match' });
  });
});
