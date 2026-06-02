function getFacetFilterInput(target) {
  if (!target || typeof target.closest !== 'function') {
    return null;
  }
  return target.closest('[data-facet-filter-input]');
}

function normalizeLabel(value) {
  return String(value || '').toLocaleLowerCase();
}

export function filterFacetValues(input) {
  const scope = input.closest('[data-facet-filter-scope]');
  if (!scope) {
    return;
  }

  const query = normalizeLabel(input.value).trim();
  scope.querySelectorAll('[data-facet-label]').forEach((item) => {
    const label = normalizeLabel(item.dataset.facetLabel);
    item.hidden = query !== '' && !label.includes(query);
  });
}

export function bindFacetFilters(root = document) {
  const handler = (event) => {
    const input = getFacetFilterInput(event.target);
    if (!input) {
      return;
    }
    filterFacetValues(input);
  };

  root.addEventListener('input', handler);
  return () => root.removeEventListener('input', handler);
}

if (typeof document !== 'undefined') {
  bindFacetFilters(document);
}
