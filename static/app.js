const $ = (id) => document.getElementById(id);

const scannerState = {
  rows: [],
  view: "all",
  query: "",
  sortKey: "change_pct",
  sortDirection: "desc",
  page: 1,
  pageSize: 10,
  checkedCount: 0,
  maxDifference: 10,
  priceRangeActive: false,
  sectorId: "all",
  sectorDetailMode: false,
  scanAsOf: null,
  quoteAsOf: null,
  instrumentStatus: {},
  unavailableSymbols: [],
  universe: null,
  watchlist: [],
  hasScan: false,
  kiteConnected: false,
  marketPolling: false,
};

const sectorPageState = { groupId: null, view: "all", query: "", sortKey: "change_pct", sortDirection: "desc" };

// Exact 16 x 10 user-supplied membership comes from one JSON source shared by
// the browser and backend. Repeated names remain in each group; quote symbols
// are deduplicated before the provider request.
let referenceGroups = [];
let referenceStockSymbols = [];
let referenceScanSymbols = [];
let referenceStockKeys = new Set();
let referenceEntryCount = 0;
let referenceOccurrences = new Map();

let mobileStickyHeader = null;

const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));

function formatPrice(value) {
  if (value === null || value === undefined || value === "" || !Number.isFinite(Number(value))) return "—";
  return Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatNumber(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
  return Number(value).toLocaleString("en-IN");
}

function showNotice(message, kind = "info") {
  const notice = $("notice");
  notice.textContent = message;
  notice.className = `notice ${kind}`;
  const detailNotice = $("sectorPageNotice");
  if (detailNotice) {
    detailNotice.textContent = message;
    detailNotice.className = `sector-page-notice ${kind}`;
  }
}

async function loadReferenceUniverse() {
  const response = await fetch("/static/sector-universe.json?v=2", { cache: "no-store" });
  if (!response.ok) throw new Error("Could not load the configured sector stock list.");
  const data = await response.json();
  if (!Array.isArray(data.groups) || data.groups.length !== 16 || data.groups.some((group) => !Array.isArray(group.stocks) || group.stocks.length !== 10)) {
    throw new Error("The sector list must contain exactly 16 groups with 10 entries each.");
  }
  referenceGroups = data.groups;
  const allStocks = referenceGroups.flatMap((group) => group.stocks);
  referenceEntryCount = allStocks.length;
  referenceStockSymbols = [...new Set(allStocks.map(([symbol]) => symbol))];
  referenceScanSymbols = [...new Set(allStocks.filter((stock) => stock[3] !== "suspended").map(([symbol]) => symbol))];
  referenceStockKeys = new Set(referenceStockSymbols.map((symbol) => `NSE:${symbol}`));
  referenceOccurrences = new Map();
  referenceGroups.forEach((group) => group.stocks.forEach(([symbol, name]) => {
    const occurrences = referenceOccurrences.get(symbol) || [];
    occurrences.push({ group: group.name, name });
    referenceOccurrences.set(symbol, occurrences);
  }));
}

function isExactMatch(row) {
  const difference = rowDifference(row);
  return row.data_available !== false
    && difference !== null
    && Number.isFinite(Number(difference))
    && (row?.open !== null && row?.open !== undefined && row?.prev_close !== null && row?.prev_close !== undefined
      ? Number(row.open) === Number(row.prev_close)
      : Number(difference) === 0);
}

function rowDifference(row) {
  if (row?.difference !== null && row?.difference !== undefined && row?.difference !== "" && Number.isFinite(Number(row.difference))) {
    return Number(row.difference);
  }
  if (row?.open === null || row?.open === undefined || row?.open === "" || row?.prev_close === null || row?.prev_close === undefined || row?.prev_close === "") return null;
  const open = Number(row?.open);
  const previousClose = Number(row?.prev_close);
  return Number.isFinite(open) && Number.isFinite(previousClose) ? open - previousClose : null;
}

function isNearMatch(row) {
  if (isExactMatch(row)) return false;
  const difference = rowDifference(row);
  if (difference === null || !Number.isFinite(difference)) return false;
  if (typeof row?.near_match === "boolean") return row.near_match;
  return Math.abs(difference) <= scannerState.maxDifference;
}

function rowDirection(row) {
  if (row?.prev_close === null || row?.prev_close === undefined || row?.ltp === null || row?.ltp === undefined || row?.ltp === "") {
    const rawChange = row?.change_pct;
    if (rawChange === null || rawChange === undefined || rawChange === "") return null;
    const change = Number(rawChange);
    return Number.isFinite(change) ? Math.sign(change) : null;
  }
  const previousClose = Number(row?.prev_close);
  const lastPrice = Number(row?.ltp);
  if (Number.isFinite(previousClose) && previousClose > 0 && Number.isFinite(lastPrice)) {
    return Math.sign(lastPrice - previousClose);
  }
  const change = row?.change_pct === null || row?.change_pct === undefined || row?.change_pct === "" ? NaN : Number(row.change_pct);
  return Number.isFinite(change) ? Math.sign(change) : null;
}

function rowsForSymbols(symbols) {
  const keys = new Set(symbols.map((symbol) => `NSE:${symbol}`));
  return scannerState.rows.filter((row) => keys.has(stockKey(row.symbol)) && isReferenceStock(row) && row.data_available !== false);
}

function stockKey(value) {
  const raw = String(value || "").trim().toUpperCase();
  const separator = raw.indexOf(":");
  return separator < 0 ? `NSE:${raw}` : `${raw.slice(0, separator)}:${raw.slice(separator + 1)}`;
}

function isReferenceStock(row) {
  return referenceStockKeys.has(stockKey(row?.symbol));
}

function groupStockKeys(group) {
  return new Set(group.stocks.map(([symbol]) => `NSE:${symbol}`));
}

function referenceEntryNote(group, index, symbol, suppliedNote = "") {
  if (suppliedNote) return suppliedNote;
  const occurrences = referenceOccurrences.get(symbol) || [];
  if (occurrences.length < 2) return "";
  const otherGroups = [...new Set(occurrences.filter((entry) => entry.group !== group.name).map((entry) => entry.group))];
  if (otherGroups.length) return `Also listed in ${otherGroups.join(", ")}; one quote request.`;
  return index > 0 ? "Duplicate requested entry; fetched once." : "Repeated entry in this group; fetched once.";
}

function currentReferenceRows() {
  return scannerState.rows.filter(isReferenceStock);
}

function stockCell(row) {
  return `<div class="stock-name">${escapeHtml(row.name || row.symbol || "Unknown stock")}</div><div class="stock-symbol">${escapeHtml(row.symbol || "")}</div>`;
}

function cell(label, value, className = "") {
  return `<td data-label="${label}" class="${className}">${value}</td>`;
}

function installScannerControls() {
  const scanner = $("scanner");
  const table = scanner?.querySelector("table");
  if (!scanner || !table) return;

  const scannerDescription = scanner.querySelector(".scanner-heading p:not(.kicker)");
  if (scannerDescription) scannerDescription.textContent = "Explore every returned quote, isolate exact opens, and compare near matches or live market breadth.";
  const checkedCard = document.querySelector(".stats-grid .stat-card:nth-child(2)");
  if (checkedCard) checkedCard.querySelector(".stat-label").textContent = "STOCKS CHECKED";
  const windowCard = document.querySelector(".stats-grid .stat-card:last-child");
  if (windowCard) windowCard.querySelector("strong").id = "activeWindowValue";

  const notice = $("notice");
  notice?.insertAdjacentHTML("afterend", `
    <div class="scanner-controls" aria-label="Stock results controls">
      <div class="view-tabs" role="tablist" aria-label="Filter stock results">
        <button type="button" class="view-tab" role="tab" id="view-all" aria-selected="true" data-view="all">All Stocks <span id="allCount">0</span></button>
        <button type="button" class="view-tab" role="tab" id="view-matched" aria-selected="false" data-view="matched">Exact Matches <span id="matchedCount">0</span></button>
        <button type="button" class="view-tab" role="tab" id="view-near" aria-selected="false" data-view="near">Near Matches <span id="nearCount">0</span></button>
        <button type="button" class="view-tab" role="tab" id="view-bullish" aria-selected="false" data-view="bullish">Bullish <span id="bullishCount">0</span></button>
        <button type="button" class="view-tab" role="tab" id="view-bearish" aria-selected="false" data-view="bearish">Bearish <span id="bearishCount">0</span></button>
      </div>
      <div class="table-tools">
        <label class="search-control">Search stocks<input id="stockSearch" type="search" placeholder="Name or symbol" autocomplete="off"></label>
        <label class="page-size-control">Rows per page<select id="pageSize"><option value="10" selected>10</option><option value="25">25</option><option value="50">50</option></select></label>
        <button type="button" class="export-button" id="exportExcel" title="Download the current results as an Excel-compatible CSV" disabled>Export Excel</button>
        <span id="exportStatus" class="export-status" aria-live="polite"></span>
        <p id="resultCount" class="result-count" aria-live="polite">Waiting for scan data</p>
      </div>
    </div>`);

  table.querySelector("thead").innerHTML = `<tr>
    <th scope="col" data-column="name"><button type="button" class="sort-button" data-sort="name">Stock Name</button></th>
    <th scope="col" data-column="symbol"><button type="button" class="sort-button" data-sort="symbol">NSE Symbol</button></th>
    <th scope="col" data-column="prev_close"><button type="button" class="sort-button" data-sort="prev_close">Previous Close</button></th>
    <th scope="col" data-column="open"><button type="button" class="sort-button" data-sort="open">Today Open</button></th>
    <th scope="col" data-column="difference"><button type="button" class="sort-button" data-sort="difference">Difference</button></th>
    <th scope="col" data-column="ltp"><button type="button" class="sort-button" data-sort="ltp">Last Price</button></th>
    <th scope="col" data-column="change_pct"><button type="button" class="sort-button" data-sort="change_pct">Change</button></th>
    <th scope="col" data-column="status"><button type="button" class="sort-button" data-sort="status">Status</button></th>
  </tr>`;
  table.querySelector("tbody").innerHTML = `<tr><td colspan="8" class="empty">Connect Kite and run a scan to see stock quotes.</td></tr>`;
  mobileStickyHeader = document.createElement("div");
  mobileStickyHeader.className = "mobile-sticky-head";
  mobileStickyHeader.id = "mobileStickyHeader";
  mobileStickyHeader.setAttribute("aria-hidden", "true");
  mobileStickyHeader.inert = true;
  mobileStickyHeader.hidden = true;
  mobileStickyHeader.innerHTML = '<table class="mobile-sticky-table"><thead></thead></table>';
  document.body.appendChild(mobileStickyHeader);
  scanner.querySelector(".table-wrap").addEventListener("scroll", syncMobileStickyHeader, { passive: true });
  window.addEventListener("scroll", syncMobileStickyHeader, { passive: true });
  window.addEventListener("resize", syncMobileStickyHeader);

  // Match tabs replace the older checkbox so there is one clear filter model.
  document.querySelector("#matchesOnly")?.closest("label")?.remove();
  const filtersHeading = document.querySelector(".filters-block .section-heading h2");
  if (filtersHeading) filtersHeading.textContent = "Optional difference range";

  scanner.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => {
    scannerState.view = button.dataset.view;
    if (scannerState.view === "bearish") {
      scannerState.sortKey = "change_pct";
      scannerState.sortDirection = "asc";
    } else if (scannerState.view === "all" || scannerState.view === "near" || scannerState.view === "bullish") {
      scannerState.sortKey = "change_pct";
      scannerState.sortDirection = "desc";
    } else {
      scannerState.sortKey = "name";
      scannerState.sortDirection = "asc";
    }
    scannerState.page = 1;
    renderRows();
  }));
  scanner.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("keydown", (event) => {
    const tabs = [...scanner.querySelectorAll("[data-view]")];
    const index = tabs.indexOf(button);
    const next = event.key === "ArrowRight" ? (index + 1) % tabs.length
      : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length
        : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : -1;
    if (next < 0) return;
    event.preventDefault();
    tabs[next].focus();
    tabs[next].click();
  }));
  scanner.querySelectorAll("[data-sort]").forEach((button) => button.addEventListener("click", () => {
    const key = button.dataset.sort;
    scannerState.sortDirection = scannerState.sortKey === key && scannerState.sortDirection === "asc" ? "desc" : "asc";
    scannerState.sortKey = key;
    renderRows();
  }));
  $("stockSearch").addEventListener("input", (event) => {
    scannerState.query = event.target.value.trim().toLocaleLowerCase();
    scannerState.page = 1;
    renderRows();
  });
  $("pageSize").addEventListener("change", (event) => {
    scannerState.pageSize = Number(event.target.value);
    scannerState.page = 1;
    renderRows();
  });
  $("exportExcel").addEventListener("click", exportCurrentRows);
}

function getPriceWindow() {
  const minRaw = $("minDiff")?.value ?? "0";
  const maxRaw = $("maxDiff")?.value ?? String(scannerState.maxDifference);
  const min = minRaw === "" ? 0 : Math.max(0, Number(minRaw));
  const max = maxRaw === "" ? Infinity : Math.max(0, Number(maxRaw));
  return { min: Number.isFinite(min) ? min : 0, max: Number.isFinite(max) ? max : Infinity };
}

function getViewRows() {
  const activeGroup = scannerState.sectorId === "all"
    ? null
    : referenceGroups.find((group) => group.id === scannerState.sectorId);
  const allowedGroupKeys = activeGroup ? groupStockKeys(activeGroup) : referenceStockKeys;
  let inWindow = scannerState.rows.filter((row) => {
    if (!isReferenceStock(row) || !allowedGroupKeys.has(stockKey(row.symbol))) return false;
    return row.data_available !== false && rowDifference(row) !== null;
  });
  if (scannerState.priceRangeActive) {
    const { min, max } = getPriceWindow();
    inWindow = inWindow.filter((row) => {
      const difference = rowDifference(row);
      return difference !== null && Math.abs(difference) >= min && Math.abs(difference) <= max;
    });
  }
  const query = scannerState.query;
  const searchedWindow = query ? inWindow.filter((row) => `${row.name || ""} ${row.symbol || ""}`.toLocaleLowerCase().includes(query)) : inWindow;
  const exactCount = searchedWindow.filter(isExactMatch).length;
  const nearCount = searchedWindow.filter(isNearMatch).length;
  const bullishCount = searchedWindow.filter((row) => rowDirection(row) > 0).length;
  const bearishCount = searchedWindow.filter((row) => rowDirection(row) < 0).length;
  const selected = searchedWindow.filter((row) => {
    if (scannerState.view === "matched") return isExactMatch(row);
    if (scannerState.view === "near") return isNearMatch(row);
    if (scannerState.view === "bullish") return rowDirection(row) > 0;
    if (scannerState.view === "bearish") return rowDirection(row) < 0;
    return true;
  });
  const key = scannerState.sortKey;
  const direction = scannerState.sortDirection === "asc" ? 1 : -1;
  const sorted = selected.map((row, index) => ({ row, index })).sort((left, right) => {
    const statusRank = (row) => isExactMatch(row) ? 0 : isNearMatch(row) ? 1 : 2;
    const a = key === "name" ? `${left.row.name || ""} ${left.row.symbol || ""}` : key === "symbol" ? String(left.row.symbol || "") : key === "status" ? statusRank(left.row) : Number(left.row[key]);
    const b = key === "name" ? `${right.row.name || ""} ${right.row.symbol || ""}` : key === "symbol" ? String(right.row.symbol || "") : key === "status" ? statusRank(right.row) : Number(right.row[key]);
    const comparison = typeof a === "string" ? a.localeCompare(b, "en", { sensitivity: "base" }) : (Number.isFinite(a) ? a : -Infinity) - (Number.isFinite(b) ? b : -Infinity);
    return comparison === 0 ? left.index - right.index : comparison * direction;
  }).map(({ row }) => row);
  return { inWindow, exactCount, nearCount, bullishCount, bearishCount, rows: sorted };
}

function updateSortIndicators() {
  document.querySelectorAll("#scanner th[data-column]").forEach((heading) => {
    const active = heading.dataset.column === scannerState.sortKey;
    heading.setAttribute("aria-sort", active ? (scannerState.sortDirection === "asc" ? "ascending" : "descending") : "none");
    const button = heading.querySelector(".sort-button");
    if (button) button.dataset.direction = active ? scannerState.sortDirection : "none";
  });
}

function rowsForGroup(group) {
  const keys = groupStockKeys(group);
  return scannerState.rows.filter((row) => {
    if (!keys.has(stockKey(row.symbol)) || !isReferenceStock(row)) return false;
    return row.data_available !== false && rowDifference(row) !== null;
  });
}

function referenceStockStatus(symbol) {
  const key = `NSE:${symbol}`;
  const row = scannerState.rows.find((item) => stockKey(item.symbol) === key && isReferenceStock(item));
  const entry = referenceGroups.flatMap((group) => group.stocks).find(([candidate]) => candidate === symbol);
  if (entry?.[3] === "suspended") {
    return { row: null, className: "suspended", label: "SUSPENDED" };
  }
  if (row) {
    const exact = isExactMatch(row);
    const near = isNearMatch(row);
    return {
      row,
      className: exact ? "match" : near ? "near" : "no-result",
      label: exact ? "MATCH" : near ? "NEAR" : "NO MATCH",
    };
  }
  if (!scannerState.hasScan) {
    return { row: null, className: "watching", label: scannerState.kiteConnected ? "AWAITING SCAN" : "CONNECT KITE" };
  }
  return scannerState.instrumentStatus[key] === "unavailable"
    ? { row: null, className: "suspended", label: "UNAVAILABLE" }
    : { row: null, className: "no-result", label: "NO QUOTE" };
}

function renderSectorGroupsLegacy() {
  const container = $("sectorGroups");
  if (!container) return;

  const activeGroup = referenceGroups.find((group) => group.id === scannerState.sectorId);
  const allButton = $("allReferenceGroups");
  if (allButton) allButton.setAttribute("aria-pressed", String(!activeGroup));
  const activeLabel = $("activeSectorName");
  if (activeLabel) activeLabel.textContent = activeGroup ? activeGroup.name : "All reference stocks";
  const universeCount = $("referenceUniverseCount");
  if (universeCount) universeCount.textContent = String(referenceStockSymbols.length);

  container.innerHTML = referenceGroups.map((group) => {
    const rows = rowsForGroup(group);
    const exact = rows.filter(isExactMatch).length;
    const near = rows.length - exact;
    const active = scannerState.sectorId === group.id;
    const stockRows = group.stocks.map(([symbol, name]) => {
      const result = referenceStockStatus(symbol);
      const price = result.row ? formatPrice(result.row.ltp) : "—";
      const change = result.row && result.row.change_pct !== null && result.row.change_pct !== undefined && Number.isFinite(Number(result.row.change_pct))
        ? `${Number(result.row.change_pct) > 0 ? "+" : ""}${Number(result.row.change_pct).toFixed(2)}%`
        : "";
      return `<li><button type="button" class="sector-stock-button" data-sector-stock="${escapeHtml(symbol)}" data-parent-sector="${escapeHtml(group.id)}" aria-label="Filter scanner to ${escapeHtml(name)}"><span class="sector-stock-identity"><strong>${escapeHtml(name)}</strong><small>NSE:${escapeHtml(symbol)}</small></span><span class="sector-stock-quote">${price === "—" ? "" : `₹${price}`} ${change ? `<small>${change}</small>` : ""}</span><span class="sector-stock-status ${result.className}">${result.label}</span></button></li>`;
    }).join("");
    return `<article class="sector-card sector-${group.accent}${active ? " is-active" : ""}" data-group-kind="${group.kind.toLowerCase()}">
      <div class="sector-card-heading"><span class="sector-card-icon" aria-hidden="true">${group.kind === "INDEX" ? "⌁" : String(referenceGroups.indexOf(group) + 1).padStart(2, "0")}</span><div class="sector-card-title"><span>${group.kind}</span><h3>${escapeHtml(group.name)}</h3>${group.subtitle ? `<small>${escapeHtml(group.subtitle)}</small>` : ""}</div><span class="sector-group-stat"><strong>${exact}</strong><small>exact</small></span></div>
      <button type="button" class="sector-filter-button" data-sector-filter="${escapeHtml(group.id)}" aria-pressed="${active}">Show this group <span aria-hidden="true">→</span></button>
      <ul class="sector-stock-list">${stockRows}</ul>
      <p class="sector-card-footnote">${exact} exact <span aria-hidden="true">·</span> ${near} near in current scan</p>
    </article>`;
  }).join("");
}

const sectorGlyphs = {
  banking: "M3 9 12 4l9 5M5 10v8m4-8v8m6-8v8m4-8v8M3 20h18",
  "it-services": "M8 7 3 12l5 5m8-10 5 5-5 5m-3-12-2 14",
  "oil-gas": "M12 3C9 8 6 11 6 15a6 6 0 0 0 12 0c0-4-3-7-6-12Z",
  automobile: "M4 14h16l-2-6H7l-3 6Zm0 0v4h2m12 0h2v-4m-13 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4Zm10 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4Z",
  fmcg: "M12 21c5-3 8-7 8-12-5 0-9 2-11 6-2 4 0 6 3 6ZM4 20c1-5 4-9 10-12",
  "pharma-healthcare": "M10 3h4v7h7v4h-7v7h-4v-7H3v-4h7z",
  "metals-mining": "m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Zm0 0v9m8-4.5-8 4.5-8-4.5m8 4.5V21",
  "power-infra": "M13 2 5 13h6l-1 9 9-13h-6z",
  realty: "M4 21V5l8-3v19m0-12h8v12M8 7h1m-1 4h1m-1 4h1m8-1h1m-1 4h1M2 21h20",
  "consumer-durables": "M5 4h14v16H5zM9 8h6m-6 4h6m-6 4h3",
  chemicals: "M9 3h6m-5 0v6l-5 8a3 3 0 0 0 3 4h8a3 3 0 0 0 3-4l-5-8V3m-7 11h12",
  telecom: "M5 9a10 10 0 0 1 14 0M8 12a6 6 0 0 1 8 0m-5 4a2 2 0 1 0 0 4 2 2 0 0 0 0-4Z",
  media: "M4 6h16v12H4zM9 3l3 3m6-3-3 3m-6 4 6 2-6 2z",
  textiles: "M4 5h16M4 9h16M4 13h16M4 17h16M7 3v16m5-16v16m5-16v16",
  defence: "M12 3 20 6v5c0 5-3 8-8 10-5-2-8-5-8-10V6l8-3Zm-3 9 2 2 4-5",
  "nifty-top-liquid": "M3 18 9 12l4 3 8-9m-6 0h6v6",
};

function sectorIllustration(group) {
  const glyph = sectorGlyphs[group.id] || "M4 18 9 12l4 3 7-9";
  return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="${glyph}"/></svg>`;
}

function sectorMetrics(group) {
  const keys = groupStockKeys(group);
  const uniqueRows = new Map();
  scannerState.rows.forEach((row) => {
    const key = stockKey(row.symbol);
    if (keys.has(key) && row.data_available !== false && !uniqueRows.has(key)) uniqueRows.set(key, row);
  });
  const rows = [...uniqueRows.values()];
  const changes = rows.map((row) => row.change_pct)
    .filter((value) => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value)))
    .map(Number);
  return {
    rows,
    quotedEntries: group.stocks.filter(([symbol]) => uniqueRows.has(`NSE:${symbol}`)).length,
    validChanges: changes.length,
    average: changes.length ? changes.reduce((sum, value) => sum + value, 0) / changes.length : null,
    exact: rows.filter(isExactMatch).length,
    near: rows.filter(isNearMatch).length,
    up: rows.filter((row) => rowDirection(row) > 0).length,
    down: rows.filter((row) => rowDirection(row) < 0).length,
  };
}

function sectorAverageMarkup(metrics) {
  if (metrics.average === null) return '<span class="sector-average neutral">--</span>';
  const value = metrics.average;
  const tone = value > 0 ? "positive" : value < 0 ? "negative" : "neutral";
  const arrow = value > 0 ? "↑ " : value < 0 ? "↓ " : "";
  return `<span class="sector-average ${tone}">${arrow}${value > 0 ? "+" : ""}${value.toFixed(2)}%</span>`;
}

function formatMarketTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "time unavailable";
  return `${new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: true }).format(date)} IST`;
}

function parseKiteTimestamp(value) {
  if (!value) return null;
  const raw = String(value).trim();
  const normalized = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(raw) ? `${raw.replace(" ", "T")}+05:30` : raw;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

function updateSectorOverview() {
  const overview = $("sectorOverviewMetrics");
  if (!overview) return;
  const quoted = currentReferenceRows().filter((row) => row.data_available !== false && rowDifference(row) !== null);
  const exact = quoted.filter(isExactMatch).length;
  const advances = quoted.filter((row) => rowDirection(row) > 0).length;
  const declines = quoted.filter((row) => rowDirection(row) < 0).length;
  const flatOrUnknown = quoted.length - advances - declines;
  const scanLabel = scannerState.hasScan
    ? scannerState.scanAsOf ? `Scan ${formatMarketTime(scannerState.scanAsOf)}`
      : scannerState.quoteAsOf ? `Latest quote ${formatMarketTime(scannerState.quoteAsOf)}` : "Scan timestamp unavailable"
    : "Waiting for Kite scan";
  overview.innerHTML = [
    ["SECTOR GROUPS", String(referenceGroups.length), "Exactly as supplied"],
    ["LIST ENTRIES", String(referenceEntryCount), `${referenceStockSymbols.length} unique symbols; duplicates retained`],
    ["QUOTES LOADED", String(quoted.length), scannerState.hasScan ? `From ${scannerState.checkedCount} valid unique NSE symbols` : "Run the sector scan to load quotes"],
    ["EXACT MATCHES", String(exact), quoted.length ? `${advances} up · ${declines} down · ${flatOrUnknown} flat/unknown` : scanLabel],
  ].map(([label, value, note]) => `<article class="sector-metric"><span>${label}</span><strong>${value}</strong><small>${escapeHtml(note)}</small></article>`).join("");
  const updated = $("sectorUpdated");
  if (updated) updated.textContent = scanLabel;
}

function renderSectorGroups() {
  const container = $("sectorGroups");
  if (!container) return;
  container.innerHTML = referenceGroups.map((group, index) => {
    const metrics = sectorMetrics(group);
    return `<a class="sector-card sector-${group.accent}" data-sector-open="${escapeHtml(group.id)}" href="#sector/${encodeURIComponent(group.id)}" aria-label="View ${escapeHtml(group.name)} sector"><div class="sector-card-top"><span class="sector-art" aria-hidden="true">${sectorIllustration(group)}</span></div><div class="sector-card-title"><h3>${escapeHtml(group.name)}</h3><small>${group.stocks.length} stock entries</small></div><div class="sector-card-performance"><span>Avg. Stock Change</span>${sectorAverageMarkup(metrics)}<small>${metrics.validChanges} valid ${metrics.validChanges === 1 ? "stock" : "stocks"}</small></div><div class="sector-card-action">View Sector <span aria-hidden="true">↗</span></div></a>`;
  }).join("");
  updateSectorOverview();
  renderMarketSummary();
}

function renderMarketSummary() {
  const summary = $("marketSummaryCards");
  if (!summary) return;
  const rows = currentReferenceRows().filter((row) => row.data_available !== false);
  const count = (predicate) => scannerState.hasScan && rows.length ? String(rows.filter(predicate).length) : "—";
  const scanDate = parseKiteTimestamp(scannerState.scanAsOf);
  const headingNote = document.querySelector(".market-summary-heading > span");
  if (headingNote) headingNote.textContent = scannerState.hasScan ? "Latest available scan" : "Awaiting scan";
  const cards = [
    ["Total Sectors", String(referenceGroups.length), "◎", "Sector groups"],
    ["Configured Entries", String(referenceEntryCount), "▦", "Across all sectors"],
    ["Unique Stocks Tracked", String(referenceStockSymbols.length), "◈", "Configured symbols"],
    ["Exact Matches", count(isExactMatch), "✓", "Open equals previous close"],
    ["Near Matches", count(isNearMatch), "≋", "Within configured tolerance"],
    ["Bullish Stocks", count((row) => rowDirection(row) > 0), "↗", "Above previous close"],
    ["Bearish Stocks", count((row) => rowDirection(row) < 0), "↘", "Below previous close"],
    ["Last Scan", scanDate ? formatMarketTime(scanDate) : "Not run", "◷", scanDate ? new Intl.DateTimeFormat("en-IN", {timeZone:"Asia/Kolkata", day:"2-digit", month:"short", year:"numeric"}).format(scanDate) : "Awaiting scan data"],
  ];
  summary.innerHTML = cards.map(([label, value, icon, detail]) => `<article class="market-summary-card"><span class="market-summary-icon" aria-hidden="true">${icon}</span><span class="market-summary-label">${label}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`).join("");
}

function sectorEntryRows(group) {
  return group.stocks.map(([symbol, name, suppliedNote = ""], index) => {
    const status = referenceStockStatus(symbol);
    const row = status.row?.data_available === false ? null : status.row;
    return { symbol, name, index, row, status: status.row && !row ? { label: "NO QUOTE", className: "no-result" } : status,
      note: referenceEntryNote(group, index, symbol, suppliedNote) };
  });
}

function renderSectorDetail() {
  const group = referenceGroups.find((item) => item.id === sectorPageState.groupId);
  const container = $("sectorDetailView");
  if (!container || !group) return;
  const metrics = sectorMetrics(group);
  const entries = sectorEntryRows(group);
  const matching = entries.filter(({ name, symbol, row }) => {
    if (sectorPageState.query && !`${name} ${symbol}`.toLocaleLowerCase().includes(sectorPageState.query)) return false;
    if (sectorPageState.view === "matched") return row && isExactMatch(row);
    if (sectorPageState.view === "near") return row && isNearMatch(row);
    if (sectorPageState.view === "bullish") return row && rowDirection(row) > 0;
    if (sectorPageState.view === "bearish") return row && rowDirection(row) < 0;
    return true;
  });
  const sortValue = (entry) => {
    const value = sectorPageState.sortKey === "difference" ? (entry.row ? rowDifference(entry.row) : null) : entry.row?.[sectorPageState.sortKey];
    return value === null || value === undefined || value === "" || !Number.isFinite(Number(value)) ? null : Number(value);
  };
  matching.sort((a, b) => {
    const left = sortValue(a), right = sortValue(b);
    if (left === null || right === null) return left === right ? a.index - b.index : left === null ? 1 : -1;
    return (left - right) * (sectorPageState.sortDirection === "asc" ? 1 : -1) || a.index - b.index;
  });
  const timestamp = parseKiteTimestamp(scannerState.quoteAsOf || scannerState.scanAsOf);
  $("sectorPageTitle").textContent = group.name;
  $("sectorPageBreadcrumb").textContent = group.name;
  $("sectorPageArt").innerHTML = sectorIllustration(group);
  $("sectorPageNumber").textContent = String(referenceGroups.indexOf(group) + 1).padStart(2, "0");
  $("sectorPageAverage").innerHTML = sectorAverageMarkup(metrics);
  $("sectorPageCoverage").textContent = `${metrics.validChanges} valid ${metrics.validChanges === 1 ? "stock" : "stocks"} · equal-weight average`;
  $("sectorPageStocks").textContent = String(group.stocks.length);
  $("sectorPageBullish").textContent = metrics.rows.length ? String(metrics.up) : "—";
  $("sectorPageBearish").textContent = metrics.rows.length ? String(metrics.down) : "—";
  $("sectorPageExact").textContent = metrics.rows.length ? String(metrics.exact) : "—";
  $("sectorPageNear").textContent = metrics.rows.length ? String(metrics.near) : "—";
  $("sectorPageUpdated").textContent = timestamp ? `${new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "numeric" }).format(timestamp)} · ${formatMarketTime(timestamp)}` : "No market update yet";
  container.querySelectorAll("[data-sector-view]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.sectorView === sectorPageState.view)));
  $("sectorPageResultCount").textContent = `${matching.length} of ${group.stocks.length} entries`;
  $("sectorPageBody").innerHTML = matching.length ? matching.map(({ symbol, name, row, status, note }) => {
    const change = row?.change_pct;
    const hasChange = change !== null && change !== undefined && change !== "" && Number.isFinite(Number(change));
    const tone = hasChange && Number(change) > 0 ? "positive" : hasChange && Number(change) < 0 ? "negative" : "neutral";
    const changeText = hasChange ? `${Number(change) > 0 ? "+" : ""}${Number(change).toFixed(2)}%` : "—";
    return `<tr><td><strong>${escapeHtml(name)}</strong>${note ? `<small class="detail-stock-note">${escapeHtml(note)}</small>` : ""}</td><td>NSE:${escapeHtml(symbol)}</td><td>${formatPrice(row?.prev_close)}</td><td>${formatPrice(row?.open)}</td><td>${formatPrice(row ? rowDifference(row) : null)}</td><td>${formatPrice(row?.ltp)}</td><td class="${tone}">${changeText}</td><td><span class="sector-stock-status ${status.className}">${escapeHtml(status.label)}</span></td></tr>`;
  }).join("") : '<tr><td colspan="8" class="sector-empty">No stocks match this filter or search.</td></tr>';
}

function installSectorDetail() {
  const market = $("marketPulse");
  if (!market) return;
  market.insertAdjacentHTML("afterend", `<section class="sector-page" id="sectorDetailView" aria-labelledby="sectorPageTitle" hidden>
    <nav class="sector-breadcrumb" aria-label="Breadcrumb"><a href="#overview">Dashboard</a><span>›</span><a href="#marketPulse">Sectors</a><span>›</span><span id="sectorPageBreadcrumb"></span></nav>
    <div class="sector-page-hero"><div class="sector-page-title"><div class="sector-page-art" id="sectorPageArt" aria-hidden="true"></div><div><p class="kicker">SECTOR <span id="sectorPageNumber"></span></p><h1 id="sectorPageTitle"></h1><p>Opening matches and market movement</p></div></div><div class="sector-page-performance"><span>Avg. Stock Change</span><div id="sectorPageAverage"></div><small id="sectorPageCoverage"></small></div><a class="sector-back-button" href="#marketPulse">← Back to Sectors</a>
    <div class="sector-page-metrics"><div><strong id="sectorPageStocks">10</strong><span>Stock entries</span></div><div><strong id="sectorPageBullish" class="positive">0</strong><span>Bullish</span></div><div><strong id="sectorPageBearish" class="negative">0</strong><span>Bearish</span></div><div><strong id="sectorPageExact">0</strong><span>Exact matches</span></div><div><strong id="sectorPageNear">0</strong><span>Near matches</span></div><div class="sector-page-update"><strong id="sectorPageUpdated">No market update yet</strong><span>Last market update</span></div></div></div>
    <div class="sector-table-panel"><div class="sector-table-heading"><div><p class="kicker">SECTOR SCANNER</p><h2>Stock overview</h2></div><button type="button" id="sectorPageRefresh" class="sector-load-button">↻ Refresh market data</button></div><div id="sectorPageNotice" class="sector-page-notice" role="status">Connect Kite and run a scan to load market data.</div>
    <div class="sector-page-controls"><div class="sector-page-filters" aria-label="Filter sector stocks"><button type="button" data-sector-view="all" aria-pressed="true">All Stocks</button><button type="button" data-sector-view="matched" aria-pressed="false">Exact Matches</button><button type="button" data-sector-view="near" aria-pressed="false">Near Matches</button><button type="button" data-sector-view="bullish" aria-pressed="false">Bullish</button><button type="button" data-sector-view="bearish" aria-pressed="false">Bearish</button></div><div class="sector-page-tools"><label>Search<input id="sectorPageSearch" type="search" placeholder="Stock name or symbol" autocomplete="off"></label><label>Sort by<select id="sectorPageSort"><option value="change_pct:desc">Change % · high to low</option><option value="change_pct:asc">Change % · low to high</option><option value="difference:asc">Opening difference · low to high</option><option value="difference:desc">Opening difference · high to low</option><option value="ltp:desc">Last price · high to low</option><option value="ltp:asc">Last price · low to high</option></select></label><span id="sectorPageResultCount" aria-live="polite"></span></div></div>
    <div class="sector-table-scroll" tabindex="0" aria-label="Sector stock table, scroll to see all columns and rows"><table class="sector-page-table"><thead><tr><th>Stock Name</th><th>NSE Symbol</th><th>Previous Close</th><th>Today Open</th><th>Difference</th><th>Last Price</th><th>Change %</th><th>Match Status</th></tr></thead><tbody id="sectorPageBody"></tbody></table></div></div></section>`);
  const container = $("sectorDetailView");
  container.addEventListener("click", (event) => {
    const filter = event.target.closest("[data-sector-view]");
    if (filter) { sectorPageState.view = filter.dataset.sectorView; renderSectorDetail(); }
  });
  $("sectorPageSearch").addEventListener("input", (event) => { sectorPageState.query = event.target.value.trim().toLocaleLowerCase(); renderSectorDetail(); });
  $("sectorPageSort").addEventListener("change", (event) => { [sectorPageState.sortKey, sectorPageState.sortDirection] = event.target.value.split(":"); renderSectorDetail(); });
  $("sectorPageRefresh").addEventListener("click", runScan);
}

function handleDashboardRoute() {
  const match = location.hash.match(/^#sector\/([^/]+)$/);
  let group = null;
  if (match) {
    try { group = referenceGroups.find((item) => item.id === decodeURIComponent(match[1])); } catch (_) { /* Invalid URL: show dashboard. */ }
  }
  const detail = Boolean(group);
  const changed = sectorPageState.groupId !== (group?.id || null);
  sectorPageState.groupId = group?.id || null;
  document.body.classList.toggle("is-sector-detail", detail);
  $("sectorDetailView").hidden = !detail;
  if (detail && changed) {
    sectorPageState.view = "all";
    sectorPageState.query = "";
    sectorPageState.sortKey = "change_pct";
    sectorPageState.sortDirection = "desc";
    $("sectorPageSearch").value = "";
    $("sectorPageSort").value = "change_pct:desc";
    renderSectorDetail();
    window.scrollTo({ top: 0, behavior: "auto" });
  }
  const active = detail ? "#marketPulse" : (["#marketPulse", "#scanner", "#history", "#settings"].includes(location.hash) ? location.hash : "#overview");
  document.querySelectorAll("#primaryNav a").forEach((link) => {
    const selected = link.getAttribute("href") === active;
    link.classList.toggle("nav-active", selected);
    if (selected) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
  });
  document.title = detail ? `${group.name} · Divine Code 369` : "Divine Code 369 · Market Intelligence";
  if (!detail && changed && location.hash) requestAnimationFrame(() => document.getElementById(location.hash.slice(1))?.scrollIntoView());
}

function selectSector(groupId, symbol = "", detail = false) {
  scannerState.sectorId = groupId || "all";
  scannerState.query = symbol.toLocaleLowerCase();
  scannerState.sectorDetailMode = detail;
  scannerState.page = 1;
  scannerState.view = "all";
  scannerState.sortKey = "change_pct";
  scannerState.sortDirection = "desc";
  document.body.classList.toggle("is-sector-detail", detail);
  const group = referenceGroups.find((item) => item.id === scannerState.sectorId);
  const detailTitle = $("sectorDetailName");
  const detailMeta = $("sectorDetailMeta");
  if (detailTitle) detailTitle.textContent = group?.name || "All sectors";
  if (detailMeta) detailMeta.textContent = group ? `${group.stocks.length} reference stocks · ${scannerState.hasScan ? "Kite scan data" : "awaiting Kite scan"}` : "All reference sectors";
  const scannerTitle = document.querySelector(".scanner-heading h2");
  if (scannerTitle) scannerTitle.textContent = group ? `${group.name} scanner` : "Opening match scanner";
  const scannerDescription = document.querySelector(".scanner-heading p:not(.kicker)");
  if (scannerDescription) scannerDescription.textContent = group ? `Quotes and opening-match status for ${group.name}. Positive change is ranked first.` : "Explore quotes by sector, isolate exact opens, or compare near matches.";
  if (detail) history.replaceState(null, "", `#sector/${encodeURIComponent(groupId)}`);
  else if (location.hash.startsWith("#sector/")) history.replaceState(null, "", "#overview");
  const search = $("stockSearch");
  if (search) search.value = symbol;
  renderRows();
}

function prepareReferenceUniverse() {
  const symbols = referenceStockSymbols.map((symbol) => `NSE:${symbol}`);
  $("symbolsInput").value = symbols.join("\n");
  showNotice(`Prepared ${symbols.length} NSE stocks from your sector reference. Review the list and choose Save list to replace your active watchlist, then run a scan.`);
  $("settings").scrollIntoView({ behavior: "smooth", block: "start" });
  window.setTimeout(() => $("symbolsInput").focus({ preventScroll: true }), 250);
}

function csvText(value) {
  const text = String(value ?? "");
  const safeText = /^[=+\-@\t\r]/.test(text) ? `'${text}` : text;
  return `"${safeText.replace(/"/g, '""')}"`;
}

function csvNumber(value) {
  if (value === null || value === undefined || value === "" || !Number.isFinite(Number(value))) return "";
  return Number(value).toFixed(2);
}

function exportCurrentRows() {
  const rows = getViewRows().rows;
  if (!scannerState.hasScan || !rows.length) return;

  const columns = ["Stock Name", "Symbol", "Previous Close", "Today Open", "Difference", "Last Price", "Change (%)", "Status"];
  const lines = [columns.map(csvText).join(",")];
  rows.forEach((row) => {
    const values = [
      csvText(row.name || row.symbol || "Unknown stock"),
      csvText(row.symbol || ""),
      csvNumber(row.prev_close),
      csvNumber(row.open),
      csvNumber(row.difference),
      csvNumber(row.ltp),
      csvNumber(row.change_pct),
      csvText(isExactMatch(row) ? "MATCH" : isNearMatch(row) ? "NEAR MATCH" : "NO MATCH"),
    ];
    lines.push(values.join(","));
  });

  const blob = new Blob([`\uFEFF${lines.join("\r\n")}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `open-match-${scannerState.view}-${new Date().toISOString().slice(0, 10)}.csv`;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  $("exportStatus").textContent = `Exported ${rows.length} ${rows.length === 1 ? "stock" : "stocks"} as an Excel-compatible CSV.`;
}

function syncMobileStickyHeader() {
  if (!mobileStickyHeader) return;
  const wrapper = document.querySelector("#scanner .table-wrap");
  const table = wrapper?.querySelector("table");
  const scanner = $("scanner");
  const media = window.matchMedia("(max-width: 1100px)");
  if (!wrapper || !table || !scanner || !media.matches || document.body.classList.contains("is-sector-detail")) {
    mobileStickyHeader.hidden = true;
    return;
  }
  const header = table.tHead;
  const headerRect = header.getBoundingClientRect();
  const scannerRect = scanner.getBoundingClientRect();
  const visible = headerRect.bottom <= 0 && scannerRect.bottom > 54;
  mobileStickyHeader.hidden = !visible;
  if (!visible) return;

  const wrapperRect = wrapper.getBoundingClientRect();
  const cloneTable = mobileStickyHeader.querySelector("table");
  const cloneHead = cloneTable.tHead;
  cloneHead.innerHTML = header.innerHTML;
  cloneHead.querySelectorAll("button").forEach((button) => button.tabIndex = -1);
  cloneHead.querySelectorAll("th").forEach((heading, index) => {
    const width = header.rows[0].cells[index]?.getBoundingClientRect().width;
    if (width) heading.style.width = `${width}px`;
  });
  mobileStickyHeader.style.left = `${wrapperRect.left}px`;
  mobileStickyHeader.style.width = `${wrapperRect.width}px`;
  cloneTable.style.width = `${table.getBoundingClientRect().width}px`;
  cloneTable.style.transform = `translateX(-${wrapper.scrollLeft}px)`;
}

function renderRowsLegacy() {
  const { inWindow, exactCount, nearCount, rows } = getViewRows();
  const pageCount = Math.max(1, Math.ceil(rows.length / scannerState.pageSize));
  scannerState.page = Math.min(scannerState.page, pageCount);
  const start = (scannerState.page - 1) * scannerState.pageSize;
  const pageRows = rows.slice(start, start + scannerState.pageSize);
  const body = $("matchBody");

  $("matchCount").textContent = String(currentReferenceRows().filter(isExactMatch).length);
  $("checkedCount").textContent = String(rows.length);
  const checkedNote = document.querySelector(".stats-grid .stat-card:nth-child(2) small");
  if (checkedNote) checkedNote.textContent = scannerState.hasScan ? "In the current sector and price view" : "Waiting for scan data";
  const windowValue = $("activeWindowValue");
  if (windowValue) {
    const { min, max } = getPriceWindow();
    windowValue.textContent = `\u20B9${formatPrice(min)}–${max === Infinity ? "open" : `\u20B9${formatPrice(max)}`}`;
  }
  $("allCount").textContent = String(inWindow.length);
  $("matchedCount").textContent = String(exactCount);
  $("nearCount").textContent = String(nearCount);
  const exportButton = $("exportExcel");
  if (exportButton) exportButton.disabled = !scannerState.hasScan || rows.length === 0;
  $("resultCount").textContent = rows.length
    ? `Showing ${start + 1}–${Math.min(start + pageRows.length, rows.length)} of ${rows.length} ${scannerState.sectorId === "all" ? "reference stocks" : "stocks in this group"}`
    : `0 stocks in ${({ all: "All Stocks", matched: "Exact Matches", near: "Near Matches", bullish: "Bullish", bearish: "Bearish" })[scannerState.view] || "this view"}`;

  document.querySelectorAll(".view-tab").forEach((button) => {
    const selected = button.dataset.view === scannerState.view;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  updateSortIndicators();
  renderExactMatchPreview();

  if (!pageRows.length) {
    const message = !scannerState.hasScan
      ? "Connect Kite and run the exact 160-entry sector scan to see live matches."
      : scannerState.query
        ? "No stocks match this search. Try another name or symbol."
        : scannerState.view === "matched"
          ? "No exact ₹0.00 matches in this scan. Check Near Matches to see stocks within the price window."
          : scannerState.view === "near"
            ? "No near matches in the current price window."
            : "No stocks are in the current price window.";
    body.innerHTML = `<tr><td colspan="7" class="empty">${message}</td></tr>`;
  } else {
    body.innerHTML = pageRows.map((row) => {
      const exact = isExactMatch(row);
      const change = row.change_pct === null || row.change_pct === undefined || !Number.isFinite(Number(row.change_pct))
        ? "—"
        : `${Number(row.change_pct) > 0 ? "+" : ""}${Number(row.change_pct).toFixed(2)}%`;
      const changeClass = row.change_pct === null || row.change_pct === undefined ? "neutral" : Number(row.change_pct) >= 0 ? "positive" : "negative";
      const status = exact ? '<span class="tag match">MATCH</span>' : '<span class="tag no">NEAR / NO MATCH</span>';
      return `<tr data-symbol="${escapeHtml(row.symbol || "")}">${cell("Stock / Symbol", stockCell(row))}${cell("Previous Close", formatPrice(row.prev_close))}${cell("Today Open", formatPrice(row.open))}${cell("Difference", formatPrice(row.difference))}${cell("Last Price", formatPrice(row.ltp))}${cell("Change", change, changeClass)}${cell("Status", status)}</tr>`;
    }).join("");
  }

  const existingPagination = $("tablePagination");
  if (existingPagination) existingPagination.remove();
  const pagination = document.createElement("div");
  pagination.id = "tablePagination";
  pagination.className = "table-pagination";
  pagination.innerHTML = `<button type="button" class="ghost" data-page="previous" ${scannerState.page <= 1 ? "disabled" : ""}>Previous</button><span>Page ${scannerState.page} of ${pageCount}</span><button type="button" class="ghost" data-page="next" ${scannerState.page >= pageCount ? "disabled" : ""}>Next</button>`;
  $("scanner").querySelector(".table-wrap").after(pagination);
  pagination.querySelectorAll("[data-page]").forEach((button) => button.addEventListener("click", () => {
    scannerState.page += button.dataset.page === "next" ? 1 : -1;
    renderRows();
  }));
  renderSectorGroups();
  renderSectorDetail();
  syncMobileStickyHeader();
}

function renderRows() {
  const { inWindow, exactCount, nearCount, bullishCount, bearishCount, rows } = getViewRows();
  const pageCount = Math.max(1, Math.ceil(rows.length / scannerState.pageSize));
  scannerState.page = Math.min(scannerState.page, pageCount);
  const start = (scannerState.page - 1) * scannerState.pageSize;
  const pageRows = rows.slice(start, start + scannerState.pageSize);
  const body = $("matchBody");
  const exactTotal = currentReferenceRows().filter(isExactMatch).length;
  $("matchCount").textContent = String(exactTotal);
  $("checkedCount").textContent = scannerState.hasScan ? String(scannerState.checkedCount) : "—";
  const checkedNote = document.querySelector(".stats-grid .stat-card:nth-child(2) small");
  if (checkedNote) checkedNote.textContent = scannerState.hasScan ? "Valid unique NSE symbols; repeats fetched once" : "Awaiting a sector scan";
  const windowValue = $("activeWindowValue");
  if (windowValue) {
    const { min, max } = getPriceWindow();
    windowValue.textContent = `₹${formatPrice(min)}–${max === Infinity ? "open" : `₹${formatPrice(max)}`}`;
  }
  $("allCount").textContent = String(inWindow.length);
  $("matchedCount").textContent = String(exactCount);
  $("nearCount").textContent = String(nearCount);
  $("bullishCount").textContent = String(bullishCount);
  $("bearishCount").textContent = String(bearishCount);
  const exportButton = $("exportExcel");
  if (exportButton) exportButton.disabled = !scannerState.hasScan || rows.length === 0;
  const resultCount = $("resultCount");
  if (resultCount) resultCount.textContent = rows.length
    ? `Showing ${start + 1}–${Math.min(start + pageRows.length, rows.length)} of ${rows.length} ${scannerState.sectorId === "all" ? "reference stocks" : "stocks in this sector"}`
    : `0 stocks in ${({ all: "All Stocks", matched: "Exact Matches", near: "Near Matches", bullish: "Bullish", bearish: "Bearish" })[scannerState.view] || "this view"}`;

  document.querySelectorAll(".view-tab").forEach((button) => {
    const selected = button.dataset.view === scannerState.view;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  updateSortIndicators();
  renderExactMatchPreview();

  if (!pageRows.length) {
    const message = !scannerState.hasScan
      ? "Connect Kite and run the exact 160-entry sector scan to load quotes."
      : scannerState.query
        ? "No stocks match this search. Try another name or symbol."
        : scannerState.view === "matched"
            ? "No exact ₹0.00 matches in this scan. Near matches are available in the next tab."
            : scannerState.view === "near"
              ? "No near matches within the configured tolerance."
              : scannerState.view === "bullish"
                ? "No advancing stocks were returned in this sector scan."
                : scannerState.view === "bearish"
                  ? "No declining stocks were returned in this sector scan."
                  : "Kite returned no quoted stocks for this sector and scan.";
    body.innerHTML = `<tr><td colspan="8" class="empty">${escapeHtml(message)}</td></tr>`;
  } else {
    body.innerHTML = pageRows.map((row) => {
      const exact = isExactMatch(row);
      const near = isNearMatch(row);
      const rawChange = row.change_pct;
      const change = rawChange === null || rawChange === undefined || rawChange === "" || !Number.isFinite(Number(rawChange))
        ? "—"
        : `${Number(rawChange) > 0 ? "+" : ""}${Number(rawChange).toFixed(2)}%`;
      const direction = rowDirection(row);
      const changeClass = direction > 0 ? "positive" : direction < 0 ? "negative" : "neutral";
      const status = exact ? '<span class="tag match">MATCH</span>' : near ? '<span class="tag near">NEAR MATCH</span>' : '<span class="tag no">NO MATCH</span>';
      return `<tr data-symbol="${escapeHtml(row.symbol || "")}">${cell("Stock Name", `<span class="stock-name">${escapeHtml(row.name || row.symbol || "Unknown stock")}</span>`)}${cell("NSE Symbol", `<span class="stock-symbol">${escapeHtml(row.symbol || "")}</span>`)}${cell("Previous Close", formatPrice(row.prev_close))}${cell("Today Open", formatPrice(row.open))}${cell("Difference", formatPrice(rowDifference(row)))}${cell("Last Price", formatPrice(row.ltp))}${cell("Change", change, changeClass)}${cell("Status", status)}</tr>`;
    }).join("");
  }

  const existingPagination = $("tablePagination");
  if (existingPagination) existingPagination.remove();
  const pagination = document.createElement("div");
  pagination.id = "tablePagination";
  pagination.className = "table-pagination";
  pagination.innerHTML = `<button type="button" class="ghost" data-page="previous" ${scannerState.page <= 1 ? "disabled" : ""}>Previous</button><span>Page ${scannerState.page} of ${pageCount}</span><button type="button" class="ghost" data-page="next" ${scannerState.page >= pageCount ? "disabled" : ""}>Next</button>`;
  $("scanner").querySelector(".table-wrap").after(pagination);
  pagination.querySelectorAll("[data-page]").forEach((button) => button.addEventListener("click", () => {
    scannerState.page += button.dataset.page === "next" ? 1 : -1;
    renderRows();
  }));
  const group = referenceGroups.find((item) => item.id === scannerState.sectorId);
  const detailMetrics = group ? sectorMetrics(group) : null;
  if ($("sectorDetailQuoted")) $("sectorDetailQuoted").textContent = String(detailMetrics?.rows.length || 0);
  if ($("sectorDetailExact")) $("sectorDetailExact").textContent = String(detailMetrics?.exact || 0);
  if ($("sectorDetailNear")) $("sectorDetailNear").textContent = String(detailMetrics?.near || 0);
  renderSectorGroups();
  renderSectorDetail();
  syncMobileStickyHeader();
}

const sectorIcons = {
  "NIFTY 50": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z"/></svg>',
  "NIFTY BANK": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 9 9-5 9 5M5 10v8m5-8v8m4-8v8m5-8v8M3 20h18M4 10h16"/></svg>',
  "NIFTY IT": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 7-5 5 5 5m8-10 5 5-5 5m-3-12-2 14"/></svg>',
  "NIFTY AUTO": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 11 2-5h10l2 5 2 2v5h-2m-14 0H3v-5l2-2Zm0 0h14M7 18a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm10 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"/></svg>',
  "NIFTY PHARMA": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 3h4v7h7v4h-7v7h-4v-7H3v-4h7z"/></svg>',
  "NIFTY FMCG": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21c5-3 8-7 8-12-5 0-9 2-11 6-2 4 0 6 3 6ZM4 20c1-5 4-9 10-12"/></svg>',
  "NIFTY METAL": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Zm0 0v9m8-4.5-8 4.5-8-4.5m8 4.5V21"/></svg>',
  "NIFTY REALTY": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 21V5l8-3v19m0-12h8v12M8 7h1m-1 4h1m-1 4h1m8-1h1m-1 4h1M2 21h20"/></svg>',
  "NIFTY PSU BANK": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 8 9-5 9 5M4 10h16M6 10v8m4-8v8m4-8v8m4-8v8M3 20h18"/></svg>',
  "NIFTY MIDCAP 50": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 18 9 12l4 3 8-9m-6 0h6v6"/></svg>',
  "INDIA VIX": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m13 2-9 12h7l-1 8 10-13h-7z"/></svg>',
  "SENSEX": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 18V6m6 12V9m6 9V4m6 14v-7M2 21h20"/></svg>',
};

function marketTimestamp(value) {
  if (!value) return "Kite timestamp unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Kite timestamp unavailable";
  return `Live via Kite · ${new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(date)} IST`;
}

function updateConnectionState(connected) {
  const indicator = document.querySelector(".live-state");
  if (!indicator) return;
  indicator.classList.toggle("offline", !connected);
  indicator.innerHTML = `<i aria-hidden="true"></i>${connected ? "KITE CONNECTED" : "KITE DISCONNECTED"}`;
  const heroStatus = $("heroConnectionText");
  if (heroStatus) heroStatus.textContent = connected ? "Kite data connection ready" : "Kite disconnected · connect for live data";
}

function renderMarketLegacy(cards, asOf, errorMessage = "") {
  const container = $("marketCards");
  $("marketUpdated").textContent = errorMessage ? "Kite data unavailable" : marketTimestamp(asOf);
  if (!cards?.length) {
    const detail = errorMessage || "Kite returned no index quotes for this update.";
    container.innerHTML = `<div class="market-placeholder" role="status"><span aria-hidden="true">◌</span>${escapeHtml(detail)}</div>`;
    return;
  }
  container.innerHTML = cards.map((index) => {
    const fullName = String(index.symbol || "");
    const name = fullName.includes(":") ? fullName.slice(fullName.indexOf(":") + 1) : fullName;
    const hasChange = index.change_pct !== null && index.change_pct !== undefined && Number.isFinite(Number(index.change_pct));
    const change = hasChange ? Number(index.change_pct) : null;
    const direction = change === null ? "neutral" : change >= 0 ? "up" : "down";
    const changeText = change === null ? "—" : `${change > 0 ? "+" : ""}${change.toFixed(2)}%`;
    return `<article class="market-card"><header><span class="index-name"><i class="sector-icon">${sectorIcons[name] || sectorIcons["NIFTY 50"]}</i>${escapeHtml(name)}</span><span class="index-change ${direction}">${changeText}</span></header><strong>${formatPrice(index.price)}</strong><small>Open ${formatPrice(index.open)} · Prev close ${formatPrice(index.prev_close)}</small></article>`;
  }).join("");
}

function updateClock() {
  const now = new Date();
  $("liveClock").innerHTML = `${new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(now)} <small>IST</small>`;
  $("clockDate").textContent = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", weekday: "short", day: "2-digit", month: "short", year: "numeric" }).format(now);
}

function updateHistoryOptions(symbols) {
  const select = $("historySymbol");
  const previous = select.value;
  select.innerHTML = symbols.length
    ? symbols.map((symbol) => `<option value="${escapeHtml(symbol)}">${escapeHtml(symbol)}</option>`).join("")
    : '<option value="">No symbols in watchlist</option>';
  if (symbols.includes(previous)) select.value = previous;
}

function applyScanResultLegacy(data) {
  scannerState.rows = Array.isArray(data.rows) ? data.rows : [];
  scannerState.checkedCount = Number(data.checked_count ?? scannerState.rows.length);
  scannerState.hasScan = true;
  scannerState.page = 1;
  renderRows();
  if (data.as_of) {
    const date = new Date(data.as_of);
    $("lastScan").textContent = Number.isNaN(date.getTime()) ? "Available" : new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: true }).format(date);
    $("lastScanDate").textContent = Number.isNaN(date.getTime()) ? "Last result" : `${new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "numeric" }).format(date)} · IST`;
  }
}

async function loadStatusLegacy() {
  try {
    const response = await fetch("/api/status");
    const status = await response.json();
    if (!response.ok) throw new Error(status.detail || "Could not load scanner status.");
    scannerState.kiteConnected = Boolean(status.token_configured);
    updateConnectionState(scannerState.kiteConnected);
    scannerState.watchlist = Array.isArray(status.watchlist) ? status.watchlist : [];
    $("symbolsInput").value = scannerState.watchlist.join("\n");
    updateHistoryOptions(scannerState.watchlist);
    if (status.max_difference !== null && status.max_difference !== undefined) {
      scannerState.maxDifference = Number(status.max_difference);
      $("maxDiff").value = scannerState.maxDifference.toFixed(2);
      $("toleranceText").textContent = `Near-match limit: ₹${formatPrice(scannerState.maxDifference)}`;
    }
    if (status.latest && status.latest.as_of) {
      applyScanResult({ ...status.latest, checked_count: status.latest.checked_count ?? scannerState.watchlist.length });
      showNotice(status.error || status.latest.message || "Scan data loaded.", status.error ? "error" : "info");
    } else {
      scannerState.checkedCount = 0;
      renderRows();
      showNotice(status.error || (status.token_configured ? "Kite is connected. Run a live scan when ready." : "Connect your Zerodha Kite account to load live stock and index data."), status.error ? "error" : "info");
    }
    if (scannerState.kiteConnected) {
      await loadMarket();
      if (!scannerState.marketPolling) {
        scannerState.marketPolling = true;
        window.setInterval(loadMarket, 15000);
      }
    } else {
      renderMarket([], null, "Connect Zerodha Kite to view live index quotes.");
    }
  } catch (error) {
    scannerState.kiteConnected = false;
    updateConnectionState(false);
    renderMarket([], null, "Could not confirm Kite connection. Check the scanner backend and try again.");
    showNotice(error.message || "Could not connect to the scanner backend.", "error");
  }
}

function applyScanResult(data) {
  scannerState.rows = Array.isArray(data.rows) ? data.rows : [];
  scannerState.checkedCount = Number(data.checked_count ?? scannerState.rows.length);
  scannerState.instrumentStatus = data.instrument_status && typeof data.instrument_status === "object" ? data.instrument_status : {};
  scannerState.unavailableSymbols = Array.isArray(data.unavailable_symbols) ? data.unavailable_symbols : [];
  scannerState.universe = data.universe || null;
  scannerState.scanAsOf = data.as_of || null;
  const quoteDates = scannerState.rows.map((row) => parseKiteTimestamp(row.last_trade_at)).filter(Boolean);
  scannerState.quoteAsOf = quoteDates.length ? new Date(Math.max(...quoteDates.map((date) => date.getTime()))).toISOString() : null;
  scannerState.hasScan = true;
  scannerState.page = 1;
  renderRows();
  const scanDate = parseKiteTimestamp(data.as_of);
  const quoteDate = scanDate ? null : parseKiteTimestamp(scannerState.quoteAsOf);
  const shownDate = scanDate || quoteDate;
  const label = document.querySelector(".stats-grid .stat-card:nth-child(3) .stat-label");
  if (label) label.textContent = scanDate ? "LAST SCAN" : quoteDate ? "LATEST QUOTE" : "LAST SCAN";
  $("lastScan").textContent = shownDate ? new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: true }).format(shownDate) : "Unavailable";
  $("lastScanDate").textContent = shownDate
    ? `${scanDate ? (data.as_of_source === "scan_fetch" ? "Scan fetched" : "Kite timestamp") : "Kite quote timestamp"} · ${new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "numeric" }).format(shownDate)} IST`
    : "Stored quotes · timestamp unavailable";
}

async function loadStatus() {
  try {
    const response = await fetch("/api/status");
    const status = await response.json();
    if (!response.ok) throw new Error(status.detail || "Could not load scanner status.");
    scannerState.kiteConnected = Boolean(status.token_configured);
    updateConnectionState(scannerState.kiteConnected);
    scannerState.watchlist = Array.isArray(status.watchlist) ? status.watchlist : [];
    $("symbolsInput").value = scannerState.watchlist.join("\n");
    updateHistoryOptions(scannerState.watchlist);
    if (status.max_difference !== null && status.max_difference !== undefined) {
      scannerState.maxDifference = Number(status.max_difference);
      $("maxDiff").value = scannerState.maxDifference.toFixed(2);
      $("toleranceText").textContent = `Near-match limit: ₹${formatPrice(scannerState.maxDifference)}`;
    }
    const latest = status.latest;
    const hasStoredResult = latest?.universe === "reference" && Array.isArray(latest.rows)
      && (latest.rows.length > 0 || latest.as_of || Number(latest.checked_count) > 0);
    if (hasStoredResult) {
      applyScanResult({ ...latest, checked_count: latest.checked_count ?? scannerState.watchlist.length });
      const restoredMessage = latest.as_of
        ? (latest.message || "Previously saved Kite scan data restored.")
        : "Previously saved Kite quote rows restored. The latest quote time is shown separately; the original scan time is unavailable.";
      showNotice(status.error || restoredMessage, status.error ? "error" : "info");
    } else {
      scannerState.rows = [];
      scannerState.hasScan = false;
      scannerState.instrumentStatus = {};
      scannerState.unavailableSymbols = [];
      scannerState.universe = null;
      scannerState.checkedCount = 0;
      scannerState.scanAsOf = null;
      scannerState.quoteAsOf = null;
      $("lastScan").textContent = "Not run";
      $("lastScanDate").textContent = "Awaiting live data";
      renderRows();
      showNotice(status.error || (status.token_configured ? "Kite is connected. Run the exact 160-entry sector scan when ready." : "Connect your Zerodha Kite account to load real stock quotes."), status.error ? "error" : "info");
    }
  } catch (error) {
    scannerState.kiteConnected = false;
    updateConnectionState(false);
    showNotice(error.message || "Could not connect to the scanner backend.", "error");
  }
}

async function loadMarketLegacy() {
  if (!scannerState.kiteConnected) {
    renderMarket([], null, "Connect Zerodha Kite to view live index quotes.");
    return;
  }
  try {
    const response = await fetch("/api/market-overview");
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Market data unavailable. Reconnect Kite and try again.");
    renderMarket(data.cards || [], data.as_of);
  } catch (error) {
    renderMarket([], null, error.message || "Market data unavailable. Reconnect Kite and try again.");
  }
}

async function runScan() {
  const button = $("refreshBtn");
  const sectorButton = $("sectorPageRefresh");
  button.disabled = true;
  button.textContent = "Scanning…";
  if (sectorButton) { sectorButton.disabled = true; sectorButton.textContent = "Scanning…"; }
  showNotice("Requesting live quotes from Kite…");
  try {
    const response = await fetch("/api/scan", { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Scan failed.");
    applyScanResult(data);
    const unavailableCount = data.unavailable_symbols?.length || 0;
    showNotice(data.rows?.length
      ? `Sector scan complete: ${data.rows.length} quotes returned from ${data.checked_count} valid unique NSE symbols (${referenceEntryCount} requested entries; repeats fetched once). ${unavailableCount} symbols unavailable. MATCH requires an exact ₹0 difference; near matches stay within ₹${formatPrice(scannerState.maxDifference)}.`
      : `${data.message || "The scan completed, but Kite returned no quote rows."}${unavailableCount ? ` ${unavailableCount} symbols were unavailable in the Kite instrument master.` : ""}`);
  } catch (error) {
    showNotice(error.message || "Scan failed.", "error");
  } finally {
    button.disabled = false;
    button.textContent = "↻ Run live scan";
    if (sectorButton) { sectorButton.disabled = false; sectorButton.textContent = "↻ Refresh market data"; }
  }
}

async function saveWatchlist() {
  const button = $("saveBtn");
  button.disabled = true;
  button.textContent = "Saving…";
  try {
    const response = await fetch("/api/watchlist", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbols: $("symbolsInput").value }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not save watchlist.");
    scannerState.watchlist = Array.isArray(data.symbols) ? data.symbols : [];
    $("symbolsInput").value = data.symbols.join("\n");
    updateHistoryOptions(scannerState.watchlist);
    renderRows();
    showNotice(`Saved ${data.count} symbols. Run a live scan when ready.`);
  } catch (error) {
    showNotice(error.message || "Could not save watchlist.", "error");
  } finally {
    button.disabled = false;
    button.textContent = "Save list";
  }
}

async function loadHistory() {
  const symbol = $("historySymbol").value;
  if (!symbol) {
    $("historyNotice").textContent = "Add and save stock symbols first.";
    return;
  }
  const button = $("historyBtn");
  button.disabled = true;
  button.textContent = "Loading…";
  $("historyNotice").textContent = `Requesting daily history for ${symbol}…`;
  try {
    const response = await fetch(`/api/history/${encodeURIComponent(symbol)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not load history.");
    $("historyBody").innerHTML = data.data?.length
      ? data.data.map((row) => `<tr>${cell("Date", escapeHtml(row.date))}${cell("Open", formatPrice(row.open))}${cell("Close", formatPrice(row.close))}${cell("High", formatPrice(row.high))}${cell("Low", formatPrice(row.low))}${cell("Volume", formatNumber(row.volume))}</tr>`).join("")
      : '<tr><td colspan="6" class="empty">No historical bars returned.</td></tr>';
    $("historyNotice").textContent = `Loaded ${data.data?.length || 0} sessions for ${symbol}.`;
  } catch (error) {
    $("historyNotice").textContent = error.message || "Could not load history.";
  } finally {
    button.disabled = false;
    button.textContent = "Load history";
  }
}

async function loadUniverse(button) {
  button.disabled = true;
  button.textContent = "Loading universe…";
  try {
    const response = await fetch("/api/watchlist/universe", { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not load market universe.");
    $("symbolsInput").value = data.symbols.join("\n");
    updateHistoryOptions(data.symbols);
    showNotice(`Loaded ${data.nse_count} NSE + ${data.bse_count} BSE equities. Save the list, then run a scan.`);
  } catch (error) {
    showNotice(error.message || "Could not load market universe.", "error");
  } finally {
    button.disabled = false;
    button.textContent = "Load 150 NSE + BSE";
  }
}

const sectorArtwork = {
  "NIFTY 50": "nifty-50",
  "NIFTY BANK": "nifty-bank",
  "NIFTY IT": "nifty-it",
  "NIFTY AUTO": "nifty-auto",
  "NIFTY PHARMA": "nifty-pharma",
  "NIFTY FMCG": "nifty-fmcg",
  "NIFTY METAL": "nifty-metal",
  "NIFTY REALTY": "nifty-realty",
  "NIFTY PSU BANK": "nifty-psu-bank",
  "NIFTY MIDCAP 50": "nifty-midcap-50",
  "INDIA VIX": "india-vix",
  SENSEX: "sensex",
};

function renderExactMatchPreviewLegacy() {
  const preview = $("exactMatchPreview");
  if (!preview) return;
  const exactRows = currentReferenceRows().filter(isExactMatch);
  const count = $("exactPanelCount");
  if (count) count.textContent = String(exactRows.length);
  if (!scannerState.hasScan) {
    preview.innerHTML = '<div class="exact-empty" role="status">Connect Kite and run a scan to see verified exact opening matches here.</div>';
    return;
  }
  if (!exactRows.length) {
    preview.innerHTML = '<div class="exact-empty" role="status">No exact matches in the latest scan. Near matches remain available in the scanner below.</div>';
    return;
  }
  preview.innerHTML = exactRows.slice(0, 4).map((row) => `<article class="exact-match-row" data-symbol="${escapeHtml(row.symbol || "")}"><div class="exact-match-identity"><strong>${escapeHtml(row.name || row.symbol || "Unknown stock")}</strong><small>${escapeHtml(row.symbol || "")}</small></div><div class="exact-match-prices"><span><small>PREVIOUS CLOSE</small><strong>${formatPrice(row.prev_close)}</strong></span><span><small>TODAY OPEN</small><strong>${formatPrice(row.open)}</strong></span><span class="exact-difference"><small>DIFFERENCE</small><strong>${formatPrice(row.difference)}</strong></span></div><span class="tag match">MATCH</span></article>`).join("");
}

function installDashboardEnhancementsLegacy() {
  const topbar = document.querySelector(".topbar");
  const nav = topbar?.querySelector("nav");
  if (topbar && nav) {
    nav.id = "primaryNav";
    nav.setAttribute("aria-label", "Primary navigation");
    nav.innerHTML = [["Dashboard", "#overview"], ["Sector map", "#marketPulse"], ["Exact matches", "#exactMatches"], ["Scanner", "#scanner"], ["History", "#history"], ["Settings", "#settings"]]
      .map(([label, href], index) => `<a${index === 0 ? ' class="nav-active"' : ""} href="${href}">${label}</a>`).join("");
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.id = "navToggle";
    toggle.className = "nav-toggle";
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-controls", "primaryNav");
    toggle.setAttribute("aria-label", "Open navigation");
    toggle.innerHTML = "<span></span><span></span><span></span>";
    topbar.insertBefore(toggle, nav);
    toggle.addEventListener("click", () => {
      const open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
      nav.classList.toggle("is-open", open);
    });
    nav.addEventListener("click", (event) => {
      const link = event.target.closest("a");
      if (!link) return;
      nav.querySelectorAll("a").forEach((item) => item.classList.toggle("nav-active", item === link));
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-label", "Open navigation");
      nav.classList.remove("is-open");
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        toggle.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-label", "Open navigation");
        nav.classList.remove("is-open");
      }
    });
  }

  const heroAction = document.querySelector(".hero-action");
  const heroTitle = document.querySelector(".hero h1");
  if (heroTitle) heroTitle.innerHTML = "Explore the Market.<br><em>One Sector at a Time.</em>";
  const heroCopy = document.querySelector(".hero-copy");
  if (heroCopy) heroCopy.textContent = "A sector-first NSE dashboard built from your reference list. Scan status and market quotes stay tied to your Kite data.";
  const heroLink = document.querySelector(".hero-buttons .text-link");
  if (heroLink) {
    heroLink.href = "#marketPulse";
    heroLink.innerHTML = "Explore sectors <span aria-hidden=\"true\">↓</span>";
  }
  if (heroAction) {
    heroAction.insertAdjacentHTML("afterbegin", '<svg class="hero-market-visual" viewBox="0 0 520 210" aria-hidden="true" focusable="false"><defs><linearGradient id="chartGlow" x1="0" x2="1"><stop offset="0" stop-color="#d4ad60" stop-opacity="0"/><stop offset=".42" stop-color="#e9c875" stop-opacity=".8"/><stop offset="1" stop-color="#65c9d5" stop-opacity=".3"/></linearGradient></defs><g class="hero-grid"><path d="M0 40H520M0 90H520M0 140H520M45 0V210M145 0V210M245 0V210M345 0V210M445 0V210"/></g><g class="hero-candles"><path d="M82 116v37m0-29h18v18H82zM157 82v47m0-37h18v25h-18zM233 102v54m0-42h18v27h-18zM308 50v58m0-45h18v31h-18zM383 65v48m0-39h18v27h-18zM458 34v60m0-48h18v32h-18z"/></g><path class="hero-chart-line" d="M20 161 86 139l49 13 53-49 47 18 63-54 48 13 54-32 48 17 54-42"/></svg>');
    const session = heroAction.querySelector(".session-line span");
    if (session) session.id = "heroConnectionText";
  }

  const trust = document.querySelector(".trust-strip");
  if (trust && !$("marketSummaryCards")) trust.insertAdjacentHTML("afterend", '<section class="market-summary" aria-labelledby="marketSummaryTitle"><div class="market-summary-heading"><div><p class="kicker">YOUR MARKET AT A GLANCE</p><h2 id="marketSummaryTitle">Market overview</h2></div><span>Live scanner insights</span></div><div id="marketSummaryCards" class="market-summary-grid"></div></section>');
  const stats = document.querySelector(".stats-grid");
  if (stats && !$("exactMatches")) {
    stats.insertAdjacentHTML("afterend", '<section class="section-block exact-match-panel" id="exactMatches"><div class="section-heading exact-panel-heading"><div><p class="kicker">ZERO-DEVIATION WATCH</p><h2>Exact opening matches</h2><p>Previous close equals today’s open. Only verified zero-difference rows appear here.</p></div><div class="exact-panel-actions"><span class="exact-count"><strong id="exactPanelCount">0</strong><small>EXACT MATCHES</small></span><button id="openExactMatches" class="secondary" type="button">View in scanner <span aria-hidden="true">&#8594;</span></button></div></div><div id="exactMatchPreview" class="exact-match-list" aria-live="polite"></div></section>');
    $("openExactMatches").addEventListener("click", () => {
      scannerState.view = "matched";
      scannerState.page = 1;
      renderRows();
      $("scanner").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }
  const market = document.querySelector(".market-block");
  if (market) {
    market.id = "marketPulse";
    const kicker = market.querySelector(".section-heading .kicker");
    const title = market.querySelector(".section-heading h2");
    if (kicker) kicker.textContent = "REFERENCE UNIVERSE";
    if (title) title.textContent = "Sector & index dashboard";
    const cards = $("marketCards");
    const watchlistNote = $("symbolsInput")?.nextElementSibling;
    if (watchlistNote) watchlistNote.textContent = `${referenceStockSymbols.length} NSE reference stocks across the sector and index groups above.`;
    cards?.insertAdjacentHTML("beforebegin", `
      <div class="sector-dashboard-intro">
        <div><span class="sector-intro-label">20 GROUPS <i aria-hidden="true"></i> ${referenceStockSymbols.length} UNIQUE NSE STOCKS</span><p>Membership follows the stocks shown in your image. Tiles display only Kite scan results; no sample prices or indicators are used.</p></div>
        <span class="sector-selection-label">Viewing <strong id="activeSectorName">All reference stocks</strong></span>
      </div>
      <div class="sector-dashboard-actions">
        <button type="button" id="allReferenceGroups" class="sector-all-button" aria-pressed="true">All reference stocks <span id="referenceUniverseCount">${referenceStockSymbols.length}</span></button>
        <button type="button" id="prepareReferenceUniverse" class="sector-load-button">Prepare these NSE stocks <span aria-hidden="true">↗</span></button>
        <span class="sector-action-note">Review and save the prepared list before it replaces your active watchlist.</span>
      </div>
      <div id="sectorGroups" class="sector-grid" aria-label="Reference sectors and index groups"></div>`);
    cards?.insertAdjacentHTML("beforebegin", '<div class="live-index-heading"><span class="eyebrow">LIVE MARKET PULSE</span><h3>Index quotes</h3><p>Live values and timestamps from your connected Kite provider.</p></div>');

    $("allReferenceGroups")?.addEventListener("click", () => {
      selectSector("all");
      $("scanner").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    $("prepareReferenceUniverse")?.addEventListener("click", prepareReferenceUniverse);
    $("sectorGroups")?.addEventListener("click", (event) => {
      const stockButton = event.target.closest("[data-sector-stock]");
      const groupButton = event.target.closest("[data-sector-filter]");
      if (stockButton) {
        selectSector(stockButton.dataset.parentSector, stockButton.dataset.sectorStock);
      } else if (groupButton) {
        selectSector(groupButton.dataset.sectorFilter);
      } else {
        return;
      }
      $("scanner").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    renderSectorGroups();
  }
  const filters = document.querySelector(".filters-block");
  if (filters) filters.id = "settings";
}

function renderExactMatchPreview() {
  const preview = $("exactMatchPreview");
  if (!preview) return;
  const exactRows = currentReferenceRows().filter(isExactMatch).sort((left, right) => Number(right.change_pct || 0) - Number(left.change_pct || 0));
  const count = $("exactPanelCount");
  if (count) count.textContent = String(exactRows.length);
  if (!scannerState.hasScan) {
    preview.innerHTML = '<div class="exact-empty" role="status">Connect Kite and run a scan to see verified exact opening matches here.</div>';
    return;
  }
  if (!exactRows.length) {
    preview.innerHTML = '<div class="exact-empty" role="status">No exact matches in the latest scan. Near matches remain available in the scanner below.</div>';
    return;
  }
  preview.innerHTML = exactRows.slice(0, 4).map((row) => {
    const change = Number.isFinite(Number(row.change_pct)) ? `${Number(row.change_pct) > 0 ? "+" : ""}${Number(row.change_pct).toFixed(2)}%` : "—";
    const tone = rowDirection(row) > 0 ? "positive" : rowDirection(row) < 0 ? "negative" : "neutral";
    return `<article class="exact-match-row" data-symbol="${escapeHtml(row.symbol || "")}"><div class="exact-match-identity"><strong>${escapeHtml(row.name || row.symbol || "Unknown stock")}</strong><small>${escapeHtml(row.symbol || "")}</small></div><div class="exact-match-prices"><span><small>PREVIOUS CLOSE</small><strong>${formatPrice(row.prev_close)}</strong></span><span><small>TODAY OPEN</small><strong>${formatPrice(row.open)}</strong></span><span><small>LAST PRICE</small><strong>${formatPrice(row.ltp)}</strong></span></div><span class="exact-change ${tone}">${change}</span><span class="tag match">MATCH</span></article>`;
  }).join("");
}

function installDashboardEnhancements() {
  const topbar = document.querySelector(".topbar");
  const nav = topbar?.querySelector("nav");
  if (topbar && nav) {
    nav.id = "primaryNav";
    nav.setAttribute("aria-label", "Primary navigation");
    nav.innerHTML = [["Dashboard", "#overview"], ["Sectors", "#marketPulse"], ["Scanner", "#scanner"], ["History", "#history"], ["Settings", "#settings"]]
      .map(([label, href], index) => `<a${index === 0 ? ' class="nav-active"' : ""} href="${href}">${label}</a>`).join("");
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.id = "navToggle";
    toggle.className = "nav-toggle";
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-controls", "primaryNav");
    toggle.setAttribute("aria-label", "Open navigation");
    toggle.innerHTML = "<span></span><span></span><span></span>";
    topbar.insertBefore(toggle, nav);
    toggle.addEventListener("click", () => {
      const open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
      nav.classList.toggle("is-open", open);
    });
    nav.addEventListener("click", (event) => {
      const link = event.target.closest("a");
      if (!link) return;
      nav.querySelectorAll("a").forEach((item) => item.classList.toggle("nav-active", item === link));
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-label", "Open navigation");
      nav.classList.remove("is-open");
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        toggle.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-label", "Open navigation");
        nav.classList.remove("is-open");
      }
    });
  }

  const heroTitle = document.querySelector(".hero h1");
  if (heroTitle) heroTitle.innerHTML = "Explore the Market.<br><em>One Sector at a Time.</em>";
  const heroCopy = document.querySelector(".hero-copy");
  if (heroCopy) heroCopy.textContent = "A sector-first market scanner built from your reference list. Quotes, opening matches, and breadth stay tied to Kite data.";
  const heroLink = document.querySelector(".hero-buttons .text-link");
  if (heroLink) {
    heroLink.href = "#marketPulse";
    heroLink.innerHTML = 'Explore sectors <span aria-hidden="true">↓</span>';
  }
  const heroAction = document.querySelector(".hero-action");
  if (heroAction && !heroAction.querySelector(".hero-market-visual")) {
    heroAction.insertAdjacentHTML("afterbegin", '<svg class="hero-market-visual" viewBox="0 0 520 210" aria-hidden="true" focusable="false"><defs><linearGradient id="chartGlow" x1="0" x2="1"><stop offset="0" stop-color="#c69c49" stop-opacity="0"/><stop offset=".45" stop-color="#c69c49" stop-opacity=".65"/><stop offset="1" stop-color="#2a6fb0" stop-opacity=".28"/></linearGradient></defs><g class="hero-grid"><path d="M0 40H520M0 90H520M0 140H520M45 0V210M145 0V210M245 0V210M345 0V210M445 0V210"/></g><g class="hero-candles"><path d="M82 116v37m0-29h18v18H82zM157 82v47m0-37h18v25h-18zM233 102v54m0-42h18v27h-18zM308 50v58m0-45h18v31h-18zM383 65v48m0-39h18v27h-18zM458 34v60m0-48h18v32h-18z"/></g><path class="hero-chart-line" d="M20 161 86 139l49 13 53-49 47 18 63-54 48 13 54-32 48 17 54-42"/></svg>');
    heroAction.insertAdjacentHTML("afterbegin", '<svg class="market-landscape" viewBox="0 0 520 170" aria-hidden="true" focusable="false"><path class="landscape-line" d="M0 148h520M12 148v-34h22v34m8 0V94h28v54m9 0V78h35v70m8 0V102h22v46m12 0V65h39v83m12 0V91h27v57m12 0V111h22v37"/><path class="landscape-bull" d="M300 118c-10-17-6-34 5-46l-12-12 16 4 8 9c12-5 31-3 43 5l18-2 9 9-8 5-12-2-5 14 5 21-10 2-8-16-13 1-7 16h-10l4-21-11-4-5 22h-10z"/><path class="landscape-bear" d="M407 111c-3-15 4-30 17-35 9-4 23-3 30 3l12-2 11 8-3 8-13 1-4 15 5 15h-10l-7-11-18 1-5 11h-10l3-17z"/></svg>');
    const session = heroAction.querySelector(".session-line span");
    if (session) session.id = "heroConnectionText";
  }

  const trust = document.querySelector(".trust-strip");
  if (trust && !$("marketSummaryCards")) trust.insertAdjacentHTML("afterend", '<section class="market-summary" aria-labelledby="marketSummaryTitle"><div class="market-summary-heading"><div><p class="kicker">YOUR MARKET AT A GLANCE</p><h2 id="marketSummaryTitle">Market overview</h2></div><span>Live scanner insights</span></div><div id="marketSummaryCards" class="market-summary-grid"></div></section>');
  const stats = document.querySelector(".stats-grid");
  if (stats && !$("exactMatches")) {
    stats.insertAdjacentHTML("afterend", '<section class="section-block exact-match-panel" id="exactMatches"><div class="section-heading exact-panel-heading"><div><p class="kicker">ZERO-DEVIATION WATCH</p><h2>Exact opening matches</h2><p>Previous close equals today\'s open. Only verified zero-difference rows appear here.</p></div><div class="exact-panel-actions"><span class="exact-count"><strong id="exactPanelCount">0</strong><small>EXACT MATCHES</small></span><button id="openExactMatches" class="secondary" type="button">View in scanner <span aria-hidden="true">→</span></button></div></div><div id="exactMatchPreview" class="exact-match-list" aria-live="polite"></div></section>');
    $("openExactMatches").addEventListener("click", () => {
      selectSector("all", "", false);
      scannerState.view = "matched";
      scannerState.page = 1;
      renderRows();
      $("scanner").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  const market = document.querySelector(".market-block");
  if (market) {
    market.id = "marketPulse";
    market.innerHTML = `<div class="section-heading"><div><p class="kicker">REFERENCE UNIVERSE</p><h2>Sixteen sectors. One live scan.</h2><p>Exactly 160 supplied entries. Quotes use each unique, verified NSE symbol once; repeats and unavailable securities remain flagged.</p></div><span class="muted" id="sectorUpdated">Waiting for Kite scan</span></div><div id="sectorOverviewMetrics" class="sector-overview-metrics" aria-live="polite"></div><div class="sector-dashboard-actions"><button type="button" id="allReferenceGroups" class="sector-all-button">View all 160 entries <span>${referenceEntryCount}</span></button><button type="button" id="runSectorScan" class="sector-load-button">Run sector scan <span aria-hidden="true">↗</span></button><span class="sector-action-note">Only the supplied sector list is scanned. Your separate personal watchlist is preserved.</span></div><div id="sectorGroups" class="sector-grid" aria-label="Sector stock groups"></div>`;
    installSectorDetail();
    const watchlistNote = $("symbolsInput")?.nextElementSibling;
    if (watchlistNote) watchlistNote.textContent = "This separate personal list is preserved; the dashboard scanner uses only the 160 supplied sector entries.";
    $("allReferenceGroups")?.addEventListener("click", () => {
      selectSector("all", "", false);
      $("scanner").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    $("runSectorScan")?.addEventListener("click", runScan);
    renderSectorGroups();
  }
  const filters = document.querySelector(".filters-block");
  if (filters) filters.id = "settings";
  const trustItems = document.querySelectorAll(".trust-strip > div");
  if (trustItems.length > 2) trustItems[2].querySelector("span").textContent = "16 sector groups from your image";
}

function renderMarket(cards, asOf, errorMessage = "") {
  const container = $("marketCards");
  const updated = $("marketUpdated");
  if (updated) updated.textContent = errorMessage ? "Kite data unavailable" : marketTimestamp(asOf);
  if (!cards?.length) {
    const detail = errorMessage || "Kite returned no index quotes for this update.";
    container.innerHTML = `<div class="market-placeholder" role="status"><span aria-hidden="true">&#9675;</span>${escapeHtml(detail)}</div>`;
    return;
  }
  const providerTime = asOf && !Number.isNaN(new Date(asOf).getTime())
    ? new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date(asOf)) + " IST"
    : "Provider timestamp unavailable";
  container.innerHTML = cards.map((index) => {
    const fullName = String(index.symbol || "");
    const name = fullName.includes(":") ? fullName.slice(fullName.indexOf(":") + 1) : fullName;
    const hasChange = index.change_pct !== null && index.change_pct !== undefined && Number.isFinite(Number(index.change_pct));
    const change = hasChange ? Number(index.change_pct) : null;
    const direction = change === null ? "neutral" : change >= 0 ? "up" : "down";
    const changeText = change === null ? "&#8212;" : `${change > 0 ? "+" : ""}${change.toFixed(2)}%`;
    const art = sectorArtwork[name];
    const artMarkup = art ? `<img class="market-art" src="/static/market-art/${art}.png" alt="" aria-hidden="true" loading="lazy" decoding="async" width="156" height="120">` : "";
    return `<article class="market-card">${artMarkup}<header><span class="index-name">${escapeHtml(name)}</span><span class="index-change ${direction}">${changeText}</span></header><strong class="market-value">${formatPrice(index.price)}</strong><small class="market-meta">Open ${formatPrice(index.open)} <span aria-hidden="true">&middot;</span> Prev close ${formatPrice(index.prev_close)}</small><small class="provider-time">Data as of ${escapeHtml(providerTime)}</small></article>`;
  }).join("");
}

async function initializeDashboard() {
  try {
    await loadReferenceUniverse();
  } catch (error) {
    showNotice(error.message || "Could not load the supplied stock groups.", "error");
  }
  installDashboardEnhancements();
  installScannerControls();
  $("refreshBtn").addEventListener("click", runScan);
  $("saveBtn").addEventListener("click", saveWatchlist);
  $("historyBtn").addEventListener("click", loadHistory);
  $("applyFiltersBtn").addEventListener("click", () => { scannerState.priceRangeActive = true; scannerState.page = 1; renderRows(); });
  $("clearFiltersBtn").addEventListener("click", () => {
    $("minDiff").value = "0";
    $("maxDiff").value = String(scannerState.maxDifference);
    scannerState.priceRangeActive = false;
    scannerState.page = 1;
    renderRows();
  });
  window.addEventListener("hashchange", handleDashboardRoute);
  handleDashboardRoute();
  await loadStatus();
  updateClock();
  window.setInterval(updateClock, 1000);
}

initializeDashboard();
