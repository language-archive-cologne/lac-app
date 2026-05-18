/**
 * IMDI Viewer – client-side XML tree browser.
 *
 * Self-initialises on elements carrying `[data-imdi-viewer]`.
 * Reads `data-access-token`, `data-root-key` and `data-xml-url` from the
 * container, fetches the raw XML from the Django endpoint, parses it
 * with DOMParser and renders a two-panel collapsible tree + detail view
 * using DaisyUI / Tailwind utility classes.
 */

/* ------------------------------------------------------------------ */
/*  Icon SVG strings (ported from node_icon.html)                     */
/* ------------------------------------------------------------------ */

const ICONS = {
  Corpus: {
    color: "text-primary",
    svg: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />',
  },
  CorpusLink: {
    color: "text-primary",
    svg: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />',
  },
  Session: {
    color: "text-info",
    svg: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />',
  },
  Actor: {
    color: "text-secondary",
    svg: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />',
  },
  MediaFile: {
    color: "text-success",
    svg: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />',
  },
  WrittenResource: {
    color: "text-warning",
    svg: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />',
  },
  Location: {
    color: "text-error",
    svg: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />',
  },
  Project: {
    color: "text-accent",
    svg: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />',
  },
};

const DEFAULT_ICON = {
  color: "text-base-content/50",
  svg: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />',
};

function iconHtml(nodeType, size) {
  const spec = ICONS[nodeType] || DEFAULT_ICON;
  const cls =
    size === "lg"
      ? "h-6 w-6"
      : size === "xs"
        ? "h-3 w-3"
        : "h-4 w-4";
  return `<svg xmlns="http://www.w3.org/2000/svg" class="${cls} ${spec.color} shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">${spec.svg}</svg>`;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

/** Strip namespace prefix from a tag name. */
function localName(el) {
  return el.localName || el.tagName.replace(/^.*:/, "");
}

/** Containers that are transparent – their children are promoted. */
const TRANSPARENT = new Set([
  "METATRANSCRIPT",
  "MDGroup",
  "Actors",
  "Resources",
  "Content",
  "Keys",
]);

/** Return child *elements* of `el`, skipping text / comment nodes. */
function childElements(el) {
  return Array.from(el.children);
}

/** True when element has no child elements AND no meaningful text. */
function isEmpty(el) {
  if (el.children.length > 0) return false;
  const txt = (el.textContent || "").trim();
  if (txt) return false;
  // Check for meaningful attributes (skip xmlns-like noise)
  for (const attr of el.attributes) {
    if (!attr.name.startsWith("xmlns") && attr.name !== "Type") return false;
  }
  return true;
}

/** True when element is a leaf (text-only, no child elements). */
function isLeaf(el) {
  return el.children.length === 0;
}

/** Determine the best display label for an element. */
function labelFor(el) {
  const tag = localName(el);

  // Use Name child text if present
  for (const ch of el.children) {
    const n = localName(ch);
    if (n === "Name" || n === "Title") {
      const t = (ch.textContent || "").trim();
      if (t) return t;
    }
  }

  // Fallback to attribute hints
  const nameAttr = el.getAttribute("Name") || el.getAttribute("name");
  if (nameAttr) return nameAttr;

  const archiveHandle = el.getAttribute("ArchiveHandle");
  if (archiveHandle) return archiveHandle;

  return tag;
}

/**
 * Resolve a relative CorpusLink path against the parent S3 key.
 * Uses URL resolution logic: treat parent key as path, resolve relative.
 */
function resolveKey(parentKey, relativePath) {
  const base = "https://d/" + parentKey;
  return new URL(relativePath, base).pathname.slice(1);
}

function buildXmlRequestUrl(xmlUrl, accessToken, key = null) {
  const params = new URLSearchParams({ token: accessToken });
  if (key) params.set("key", key);
  return `${xmlUrl}?${params.toString()}`;
}

/* ------------------------------------------------------------------ */
/*  Flatten (promote transparent container children)                  */
/* ------------------------------------------------------------------ */

/**
 * Return the "visible" children of an element, promoting children of
 * transparent containers and filtering empties.
 */
function visibleChildren(el) {
  const result = [];
  for (const ch of childElements(el)) {
    const tag = localName(ch);
    if (TRANSPARENT.has(tag)) {
      result.push(...visibleChildren(ch));
    } else if (!isEmpty(ch)) {
      result.push(ch);
    }
  }
  return result;
}

/* ------------------------------------------------------------------ */
/*  Tree rendering                                                    */
/* ------------------------------------------------------------------ */

/**
 * Build the tree panel `<ul class="menu ...">` from an XML root element.
 */
function buildTree(rootEl, ctx) {
  const ul = document.createElement("ul");
  ul.className = "menu menu-xs w-full";

  const topChildren = visibleChildren(rootEl);
  for (const ch of topChildren) {
    ul.appendChild(buildNode(ch, ctx, true));
  }
  return ul;
}

/**
 * Build a single `<li>` tree node.
 *
 * - Branch nodes (with child elements) render as `<details><summary>`.
 * - Leaf nodes render as a clickable `<span>` with inline value.
 * - CorpusLink nodes are lazy-loaded on expand.
 */
function buildNode(el, ctx, open) {
  const tag = localName(el);
  const li = document.createElement("li");

  const children = visibleChildren(el);
  const corpusLink = getCorpusLink(el);

  if (corpusLink) {
    // CorpusLink: collapsible, lazy-loaded on first expand
    const details = document.createElement("details");
    if (open) details.open = true;
    const summary = document.createElement("summary");
    summary.className = "cursor-pointer select-none";
    summary.style.width = "fit-content";
    summary.innerHTML =
      iconHtml("CorpusLink") +
      `<span>${esc(labelFor(el))}</span>` +
      `<span class="badge badge-xs badge-ghost ml-1">link</span>`;

    summary.addEventListener("click", (e) => {
      e.preventDefault();
      selectNode(el, tag, ctx);
      // Toggle open manually after our handler
      details.open = !details.open;
    });

    details.appendChild(summary);

    // Lazy load placeholder
    const placeholder = document.createElement("ul");
    placeholder.style.paddingInlineStart = "0.75rem";
    placeholder.innerHTML = `<li class="pl-4"><span class="loading loading-spinner loading-xs text-primary"></span></li>`;
    details.appendChild(placeholder);

    let loaded = false;
    details.addEventListener("toggle", () => {
      if (details.open && !loaded) {
        loaded = true;
        loadCorpusLink(corpusLink, ctx.parentKey, ctx, placeholder, details);
      }
    });

    li.appendChild(details);
  } else if (children.length > 0) {
    // Branch node: collapsible
    const details = document.createElement("details");
    if (open) details.open = true;
    const summary = document.createElement("summary");
    summary.className = "cursor-pointer select-none";
    summary.style.width = "fit-content";
    summary.innerHTML = iconHtml(tag) + `<span>${esc(labelFor(el))}</span>`;

    summary.addEventListener("click", (e) => {
      e.preventDefault();
      selectNode(el, tag, ctx);
      details.open = !details.open;
    });

    details.appendChild(summary);

    const childUl = document.createElement("ul");
    childUl.style.paddingInlineStart = "0.75rem";
    for (const ch of children) {
      childUl.appendChild(buildNode(ch, ctx, false));
    }
    details.appendChild(childUl);
    li.appendChild(details);
  } else if (isLeaf(el)) {
    // Leaf node: inline tag: value
    const text = (el.textContent || "").trim();
    const span = document.createElement("span");
    span.className = "cursor-pointer select-none flex items-center gap-1 justify-start text-left";
    span.innerHTML =
      iconHtml(tag, "xs") +
      `<span class="text-base-content/70 shrink-0">${esc(tag)}:</span>` +
      `<span class="truncate">${esc(text)}</span>`;
    span.addEventListener("click", () => selectNode(el, tag, ctx));
    li.appendChild(span);
  }

  // Store element ref for active-state tracking
  li._xmlEl = el;
  return li;
}

/** Extract CorpusLink text from an element (if present). */
function getCorpusLink(el) {
  for (const ch of el.children) {
    if (localName(ch) === "CorpusLink") {
      return (ch.textContent || "").trim();
    }
  }
  return null;
}

/** Lazy-load a CorpusLink: fetch its XML, render subtree. */
async function loadCorpusLink(relativePath, parentKey, ctx, placeholder, details) {
  const resolvedKey = resolveKey(parentKey, relativePath);
  try {
    const url = buildXmlRequestUrl(ctx.xmlUrl, ctx.accessToken, resolvedKey);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const xmlText = await resp.text();
    const doc = new DOMParser().parseFromString(xmlText, "text/xml");

    if (doc.querySelector("parsererror")) {
      throw new Error("XML parse error");
    }

    const root = doc.documentElement;
    const childCtx = { ...ctx, parentKey: resolvedKey };
    const children = visibleChildren(root);

    const ul = document.createElement("ul");
    ul.style.paddingInlineStart = "0.75rem";
    for (const ch of children) {
      ul.appendChild(buildNode(ch, childCtx, false));
    }
    details.replaceChild(ul, placeholder);
  } catch (err) {
    placeholder.innerHTML = `<li><span class="text-error text-xs">Failed to load: ${esc(err.message)}</span></li>`;
  }
}

/* ------------------------------------------------------------------ */
/*  Detail panel                                                      */
/* ------------------------------------------------------------------ */

/** Render the detail panel for a selected XML element. */
function renderDetail(el, nodeType, container) {
  const label = labelFor(el);
  const attrs = [];
  for (const attr of el.attributes) {
    if (!attr.name.startsWith("xmlns")) {
      attrs.push({ name: attr.name, value: attr.value });
    }
  }

  const textContent = isLeaf(el) ? (el.textContent || "").trim() : "";
  const children = visibleChildren(el);

  let html = "";

  // Header
  html += `<div class="flex items-center gap-3 mb-4">`;
  html += iconHtml(nodeType, "lg");
  html += `<div>`;
  html += `<h2 class="text-lg font-semibold text-base-content">${esc(label)}</h2>`;
  html += `<span class="badge badge-primary badge-sm">${esc(nodeType)}</span>`;
  html += `</div></div>`;

  // Attributes table
  if (attrs.length > 0) {
    html += `<table class="table table-sm w-full mb-4">`;
    html += `<thead><tr><th class="w-1/3">Attribute</th><th>Value</th></tr></thead><tbody>`;
    for (const a of attrs) {
      html += `<tr class="hover:bg-base-200"><td class="font-mono text-xs text-base-content/70">@${esc(a.name)}</td><td class="break-all">${esc(a.value)}</td></tr>`;
    }
    html += `</tbody></table>`;
  }

  // Text content
  if (textContent) {
    html += `<div class="mb-4"><div class="text-xs text-base-content/50 mb-1">Text content</div>`;
    html += `<div class="bg-base-200 rounded-lg p-3 text-sm break-all">${esc(textContent)}</div></div>`;
  }

  // Leaf children (direct text children shown as mini-table)
  const leafChildren = [];
  const branchChildren = [];
  for (const ch of children) {
    if (isLeaf(ch) && (ch.textContent || "").trim()) {
      leafChildren.push(ch);
    } else if (!isEmpty(ch)) {
      branchChildren.push(ch);
    }
  }

  if (leafChildren.length > 0) {
    html += `<table class="table table-sm w-full mb-4">`;
    html += `<thead><tr><th class="w-1/3">Field</th><th>Value</th></tr></thead><tbody>`;
    for (const ch of leafChildren) {
      const val = (ch.textContent || "").trim();
      html += `<tr class="hover:bg-base-200"><td class="font-mono text-xs text-base-content/70">${esc(localName(ch))}</td><td class="break-all">${esc(val)}</td></tr>`;
    }
    html += `</tbody></table>`;
  }

  // Branch children summary
  if (branchChildren.length > 0) {
    html += `<div><div class="text-xs text-base-content/50 mb-2">Sub-elements (${branchChildren.length})</div>`;
    html += `<div class="flex flex-wrap gap-1">`;
    for (const ch of branchChildren) {
      const chTag = localName(ch);
      html += `<span class="badge badge-outline badge-sm">${iconHtml(chTag, "xs")} ${esc(labelFor(ch))}</span>`;
    }
    html += `</div></div>`;
  }

  container.innerHTML = html;
}

/* ------------------------------------------------------------------ */
/*  Active state tracking                                             */
/* ------------------------------------------------------------------ */

let _activeItem = null;

function selectNode(el, nodeType, ctx) {
  // Remove previous active state
  if (_activeItem) _activeItem.classList.remove("active");

  // Find the <li> that owns this element
  const treePanel = ctx.container.querySelector("[data-imdi-tree]");
  if (treePanel) {
    const items = treePanel.querySelectorAll("li");
    for (const li of items) {
      if (li._xmlEl === el) {
        li.classList.add("active");
        _activeItem = li;
        break;
      }
    }
  }

  // Render detail
  const detailPanel = ctx.container.querySelector("[data-imdi-detail]");
  if (detailPanel) {
    renderDetail(el, nodeType, detailPanel);
  }
}

/* ------------------------------------------------------------------ */
/*  Escape helper                                                     */
/* ------------------------------------------------------------------ */

const _escEl = document.createElement("span");
function esc(str) {
  _escEl.textContent = str || "";
  return _escEl.innerHTML;
}

/* ------------------------------------------------------------------ */
/*  Initialisation                                                    */
/* ------------------------------------------------------------------ */

async function initViewer(container) {
  const accessToken = container.dataset.accessToken;
  const rootKey = container.dataset.rootKey;
  const xmlUrl = container.dataset.xmlUrl;

  if (!accessToken || !rootKey || !xmlUrl) return;
  // Prevent double-init
  if (container._imdiInitialised) return;
  container._imdiInitialised = true;

  try {
    const url = buildXmlRequestUrl(xmlUrl, accessToken);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const xmlText = await resp.text();
    const doc = new DOMParser().parseFromString(xmlText, "text/xml");

    if (doc.querySelector("parsererror")) {
      throw new Error("Invalid XML returned by server");
    }

    const root = doc.documentElement;
    const ctx = { accessToken, parentKey: rootKey, xmlUrl, container };

    // Build two-panel layout
    container.innerHTML = "";

    // Inject resizer styles once (CSS var drives panel widths on lg+)
    if (!document.getElementById("imdi-resizer-styles")) {
      const style = document.createElement("style");
      style.id = "imdi-resizer-styles";
      style.textContent =
        "@media (min-width: 1024px) {" +
        " [data-imdi-wrapper] > [data-imdi-tree] { flex: 0 0 var(--imdi-tree-width, 66.6667%); }" +
        " [data-imdi-wrapper] > [data-imdi-detail] { flex: 1 1 0; }" +
        "}";
      document.head.appendChild(style);
    }

    const wrapper = document.createElement("div");
    wrapper.className = "flex flex-col lg:flex-row min-h-[58vh]";
    wrapper.setAttribute("data-imdi-wrapper", "");

    const STORAGE_KEY = "imdi-tree-width";
    const savedWidth = localStorage.getItem(STORAGE_KEY);
    if (savedWidth) wrapper.style.setProperty("--imdi-tree-width", savedWidth);

    // Tree panel (wider – leaves show inline values)
    const treePanel = document.createElement("div");
    treePanel.className =
      "min-w-0 border-b lg:border-b-0 border-base-300 overflow-y-auto overflow-x-auto max-h-[72vh] p-4";
    treePanel.setAttribute("data-imdi-tree", "");
    const tree = buildTree(root, ctx);
    treePanel.appendChild(tree);

    // Draggable vertical divider (lg only)
    const divider = document.createElement("div");
    divider.className =
      "hidden lg:block shrink-0 cursor-col-resize bg-base-300 hover:bg-primary/50 transition-colors";
    divider.style.width = "4px";
    divider.style.touchAction = "none";
    divider.setAttribute("role", "separator");
    divider.setAttribute("aria-orientation", "vertical");
    divider.title = "Drag to resize";

    divider.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      const rect = wrapper.getBoundingClientRect();
      try { divider.setPointerCapture(e.pointerId); } catch (_) {}
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";

      const onMove = (ev) => {
        const pct = ((ev.clientX - rect.left) / rect.width) * 100;
        const clamped = Math.max(15, Math.min(85, pct));
        wrapper.style.setProperty("--imdi-tree-width", clamped.toFixed(2) + "%");
      };
      const onUp = () => {
        try { divider.releasePointerCapture(e.pointerId); } catch (_) {}
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        document.removeEventListener("pointermove", onMove);
        document.removeEventListener("pointerup", onUp);
        const w = wrapper.style.getPropertyValue("--imdi-tree-width");
        if (w) localStorage.setItem(STORAGE_KEY, w);
      };
      document.addEventListener("pointermove", onMove);
      document.addEventListener("pointerup", onUp);
    });

    // Detail panel (scrollable)
    const detailPanel = document.createElement("div");
    detailPanel.className = "min-w-0 p-6 overflow-y-auto max-h-[72vh]";
    detailPanel.setAttribute("data-imdi-detail", "");

    // Render initial detail for root content element
    const topChildren = visibleChildren(root);
    if (topChildren.length > 0) {
      const first = topChildren[0];
      renderDetail(first, localName(first), detailPanel);
    } else {
      renderDetail(root, localName(root), detailPanel);
    }

    wrapper.appendChild(treePanel);
    wrapper.appendChild(divider);
    wrapper.appendChild(detailPanel);
    container.appendChild(wrapper);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-error"><span>Failed to load IMDI data: ${esc(err.message)}</span></div>`;
  }
}

function initAll() {
  document.querySelectorAll("[data-imdi-viewer]").forEach(initViewer);
}

document.addEventListener("DOMContentLoaded", initAll);
document.addEventListener("htmx:afterSwap", initAll);
