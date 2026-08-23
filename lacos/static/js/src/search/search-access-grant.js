/**
 * Inline ALTCHA search-access grants.
 *
 * Keeps faceted search on the page instead of bouncing through the
 * /search-access/ interstitial:
 *  - On page load without a valid grant, solves an ALTCHA challenge in the
 *    background and stores the grant cookie via fetch.
 *  - When an HTMX search request is rejected with 403 + "X-Search-Verification:
 *    required" (expired grant), cancels the HX-Redirect, re-verifies inline and
 *    replays the original request into its original target.
 *
 * The interstitial page remains the fallback for no-JS clients and for
 * repeated failures.
 */

const RETRY_MARKER = 'searchAccessRetried';

let inflightGrant = null;

export function resetSearchAccessState() {
  inflightGrant = null;
}

export function getSearchAccessConfig(doc = document) {
  const host = doc.getElementById('search-access-config');
  if (!host) {
    return null;
  }
  return {
    host,
    grantNeeded: host.dataset.grantNeeded === '1',
    challengeUrl: host.dataset.challengeUrl,
    grantUrl: host.dataset.grantUrl,
    csrfToken: host.dataset.csrfToken,
  };
}

export function solveChallenge(config) {
  return new Promise((resolve, reject) => {
    const widget = document.createElement('altcha-widget');
    widget.setAttribute('challengeurl', config.challengeUrl);
    widget.setAttribute('auto', 'onload');
    widget.style.display = 'none';

    const cleanup = () => widget.remove();
    widget.addEventListener('verified', (event) => {
      cleanup();
      resolve(event.detail.payload);
    });
    widget.addEventListener('statechange', (event) => {
      if (event.detail && event.detail.state === 'error') {
        cleanup();
        reject(new Error('ALTCHA challenge failed'));
      }
    });
    config.host.appendChild(widget);
  });
}

export async function acquireGrant(config) {
  const payload = await solveChallenge(config);
  const body = new FormData();
  body.set('altcha', payload);
  body.set('mode', 'inline');
  body.set('csrfmiddlewaretoken', config.csrfToken);

  const response = await fetch(config.grantUrl, {
    method: 'POST',
    body,
    credentials: 'same-origin',
  });
  if (response.status !== 204) {
    throw new Error(`Search grant request failed with status ${response.status}`);
  }
  config.host.dataset.grantNeeded = '0';
}

export function ensureGrant(config) {
  if (!inflightGrant) {
    inflightGrant = acquireGrant(config).finally(() => {
      inflightGrant = null;
    });
  }
  return inflightGrant;
}

export function primeSearchAccess(doc = document) {
  const config = getSearchAccessConfig(doc);
  if (!config || !config.grantNeeded) {
    return null;
  }
  // Failures are non-fatal: the 403 retry path or the interstitial fallback
  // still verifies on the first actual search.
  return ensureGrant(config).catch(() => {});
}

function requestPath(detail) {
  const pathInfo = detail.pathInfo || {};
  return pathInfo.finalRequestPath || pathInfo.requestPath || '';
}

function fallbackToInterstitial(config, path) {
  const next = path || window.location.pathname + window.location.search;
  window.location.assign(`${config.grantUrl}?next=${encodeURIComponent(next)}`);
}

export function handleVerificationRejection(event, doc = document) {
  const detail = event.detail || {};
  const xhr = detail.xhr;
  if (!xhr || xhr.status !== 403) {
    return;
  }
  if (xhr.getResponseHeader('X-Search-Verification') !== 'required') {
    return;
  }
  const config = getSearchAccessConfig(doc);
  const elt = detail.elt;
  if (!config || !elt) {
    return;
  }
  if (elt.dataset[RETRY_MARKER] === '1') {
    // The inline retry was rejected again — let HX-Redirect take over.
    delete elt.dataset[RETRY_MARKER];
    return;
  }

  event.preventDefault();
  elt.dataset[RETRY_MARKER] = '1';
  const path = requestPath(detail);
  ensureGrant(config)
    .then(() => window.htmx.ajax('GET', path, { source: elt }))
    .then(() => {
      delete elt.dataset[RETRY_MARKER];
    })
    .catch(() => {
      delete elt.dataset[RETRY_MARKER];
      fallbackToInterstitial(config, path);
    });
}

export function bindSearchAccess(doc = document) {
  const handler = (event) => handleVerificationRejection(event, doc);
  doc.body.addEventListener('htmx:beforeOnLoad', handler);
  primeSearchAccess(doc);
  return () => doc.body.removeEventListener('htmx:beforeOnLoad', handler);
}

if (typeof document !== 'undefined' && document.getElementById('search-access-config')) {
  bindSearchAccess(document);
}
