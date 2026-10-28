const $ = (id) => document.getElementById(id);

const scannerState = {
  rows: [],
  view: "matched",
  query: "",
  sortKey: "name",
  sortDirection: "asc",
  page: 1,
  pageSize: 10,
  checkedCount: 0,
  maxDifference: 10,
  hasScan: false,
  kiteConnected: false,
  marketPolling: false,
};
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
}

function isExactMatch(row) {
  const difference = row.difference;
  return row.data_available !== false
    && difference !== null
    && difference !== undefined
    && difference !== ""
    && Number.isFinite(Number(difference))
    && Number(difference) === 0;
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
  if (scannerDescription) scannerDescription.textContent = "Choose exact opening matches or compare them with near-open stocks in your price window.";
  const shownCard = document.querySelector(".stats-grid .stat-card:nth-child(2)");
  if (shownCard) {
    shownCard.querySelector(".stat-label").textContent = "STOCKS SHOWN";
    shownCard.querySelector("small").textContent = "In the current view";
  }
  const windowCard = document.querySelector(".stats-grid .stat-card:last-child");
  if (windowCard) windowCard.querySelector("strong").id = "activeWindowValue";

  const notice = $("notice");
  notice?.insertAdjacentHTML("afterend", `
    <div class="scanner-controls" aria-label="Stock results controls">
      <div class="view-tabs" role="tablist" aria-label="Filter stocks by match type">
        <button type="button" class="view-tab" role="tab" id="view-all" aria-selected="false" data-view="all">All Stocks <span id="allCount">0</span></button>
        <button type="button" class="view-tab" role="tab" id="view-matched" aria-selected="true" data-view="matched">Matched Only <span id="matchedCount">0</span></button>
        <button type="button" class="view-tab" role="tab" id="view-near" aria-selected="false" data-view="near">Near Matches <span id="nearCount">0</span></button>
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
    <th scope="col" data-column="name"><button type="button" class="sort-button" data-sort="name">Stock / Symbol</button></th>
    <th scope="col" data-column="prev_close"><button type="button" class="sort-button" data-sort="prev_close">Previous Close</button></th>
    <th scope="col" data-column="open"><button type="button" class="sort-button" data-sort="open">Today Open</button></th>
    <th scope="col" data-column="difference"><button type="button" class="sort-button" data-sort="difference">Difference</button></th>
    <th scope="col" data-column="ltp"><button type="button" class="sort-button" data-sort="ltp">Last Price</button></th>
    <th scope="col" data-column="change_pct"><button type="button" class="sort-button" data-sort="change_pct">Change</button></th>
    <th scope="col" data-column="status"><button type="button" class="sort-button" data-sort="status">Status</button></th>
  </tr>`;
  table.querySelector("tbody").innerHTML = `<tr><td colspan="7" class="empty">Connect Kite and run a scan to see matching stocks.</td></tr>`;
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

  // The match tabs replace the older checkbox so there is one clear filter model.
  document.querySelector("#matchesOnly")?.closest("label")?.remove();
  const filtersHeading = document.querySelector(".filters-block .section-heading h2");
  if (filtersHeading) filtersHeading.textContent = "Price difference filters";

  scanner.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => {
    scannerState.view = button.dataset.view;
    if (scannerState.view === "all" || scannerState.view === "near") {
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
  const { min, max } = getPriceWindow();
  const inWindow = scannerState.rows.filter((row) => {
    if (row.data_available === false || row.difference === null || row.difference === undefined || row.difference === "") return false;
    const difference = Number(row.difference);
    return Number.isFinite(difference) && Math.abs(difference) >= min && Math.abs(difference) <= max;
  });
  const exactCount = inWindow.filter(isExactMatch).length;
  const nearCount = inWindow.length - exactCount;
  const selected = inWindow.filter((row) => {
    if (scannerState.view === "matched") return isExactMatch(row);
    if (scannerState.view === "near") return !isExactMatch(row);
    return true;
  });
  const query = scannerState.query;
  const searched = query ? selected.filter((row) => `${row.name || ""} ${row.symbol || ""}`.toLocaleLowerCase().includes(query)) : selected;
  const key = scannerState.sortKey;
  const direction = scannerState.sortDirection === "asc" ? 1 : -1;
  const sorted = searched.map((row, index) => ({ row, index })).sort((left, right) => {
    const a = key === "name" ? `${left.row.name || ""} ${left.row.symbol || ""}` : key === "status" ? (isExactMatch(left.row) ? 0 : 1) : Number(left.row[key]);
    const b = key === "name" ? `${right.row.name || ""} ${right.row.symbol || ""}` : key === "status" ? (isExactMatch(right.row) ? 0 : 1) : Number(right.row[key]);
    const comparison = typeof a === "string" ? a.localeCompare(b, "en", { sensitivity: "base" }) : (Number.isFinite(a) ? a : -Infinity) - (Number.isFinite(b) ? b : -Infinity);
    return comparison === 0 ? left.index - right.index : comparison * direction;
  }).map(({ row }) => row);
  return { inWindow, exactCount, nearCount, rows: sorted };
}

function updateSortIndicators() {
  document.querySelectorAll("#scanner th[data-column]").forEach((heading) => {
    const active = heading.dataset.column === scannerState.sortKey;
    heading.setAttribute("aria-sort", active ? (scannerState.sortDirection === "asc" ? "ascending" : "descending") : "none");
    const button = heading.querySelector(".sort-button");
    if (button) button.dataset.direction = active ? scannerState.sortDirection : "none";
  });
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
      csvText(isExactMatch(row) ? "MATCH" : "NEAR / NO MATCH"),
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
  if (!wrapper || !table || !scanner || !media.matches) {
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

function renderRows() {
  const { inWindow, exactCount, nearCount, rows } = getViewRows();
  const pageCount = Math.max(1, Math.ceil(rows.length / scannerState.pageSize));
  scannerState.page = Math.min(scannerState.page, pageCount);
  const start = (scannerState.page - 1) * scannerState.pageSize;
  const pageRows = rows.slice(start, start + scannerState.pageSize);
  const body = $("matchBody");

  $("matchCount").textContent = String(scannerState.rows.filter(isExactMatch).length);
  $("checkedCount").textContent = String(rows.length);
  const checkedNote = document.querySelector(".stats-grid .stat-card:nth-child(2) small");
  if (checkedNote) checkedNote.textContent = scannerState.hasScan ? `of ${scannerState.checkedCount} instruments checked` : "Waiting for scan data";
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
    ? `Showing ${start + 1}–${Math.min(start + pageRows.length, rows.length)} of ${rows.length} stocks`
    : `0 stocks in ${scannerState.view === "matched" ? "Matched Only" : scannerState.view === "near" ? "Near Matches" : "All Stocks"}`;

  document.querySelectorAll(".view-tab").forEach((button) => {
    const selected = button.dataset.view === scannerState.view;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  updateSortIndicators();
  renderExactMatchPreview();

  if (!pageRows.length) {
    const message = !scannerState.hasScan
      ? "Connect Kite and run a scan to see matching stocks."
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

function applyScanResult(data) {
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

async function loadStatus() {
  try {
    const response = await fetch("/api/status");
    const status = await response.json();
    if (!response.ok) throw new Error(status.detail || "Could not load scanner status.");
    scannerState.kiteConnected = Boolean(status.token_configured);
    updateConnectionState(scannerState.kiteConnected);
    $("symbolsInput").value = (status.watchlist || []).join("\n");
    updateHistoryOptions(status.watchlist || []);
    if (status.max_difference !== null && status.max_difference !== undefined) {
      scannerState.maxDifference = Number(status.max_difference);
      $("maxDiff").value = scannerState.maxDifference.toFixed(2);
      $("toleranceText").textContent = `Near-match limit: ₹${formatPrice(scannerState.maxDifference)}`;
    }
    if (status.latest && status.latest.as_of) {
      applyScanResult({ ...status.latest, checked_count: status.latest.checked_count ?? (status.watchlist || []).length });
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

async function loadMarket() {
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
  button.disabled = true;
  button.textContent = "Scanning…";
  showNotice("Requesting live quotes from Kite…");
  try {
    const response = await fetch("/api/scan", { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Scan failed.");
    applyScanResult(data);
    showNotice(data.message || "Scan complete.");
  } catch (error) {
    showNotice(error.message || "Scan failed.", "error");
  } finally {
    button.disabled = false;
    button.textContent = "↻ Run live scan";
    loadMarket();
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
    $("symbolsInput").value = data.symbols.join("\n");
    updateHistoryOptions(data.symbols);
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

function renderExactMatchPreview() {
  const preview = $("exactMatchPreview");
  if (!preview) return;
  const exactRows = scannerState.rows.filter(isExactMatch);
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

function installDashboardEnhancements() {
  const topbar = document.querySelector(".topbar");
  const nav = topbar?.querySelector("nav");
  if (topbar && nav) {
    nav.id = "primaryNav";
    nav.setAttribute("aria-label", "Primary navigation");
    nav.innerHTML = [["Dashboard", "#overview"], ["Market pulse", "#marketPulse"], ["Exact matches", "#exactMatches"], ["Scanner", "#scanner"], ["History", "#history"], ["Settings", "#settings"]]
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
  if (heroAction) {
    heroAction.insertAdjacentHTML("afterbegin", '<svg class="hero-market-visual" viewBox="0 0 520 210" aria-hidden="true" focusable="false"><defs><linearGradient id="chartGlow" x1="0" x2="1"><stop offset="0" stop-color="#d4ad60" stop-opacity="0"/><stop offset=".42" stop-color="#e9c875" stop-opacity=".8"/><stop offset="1" stop-color="#65c9d5" stop-opacity=".3"/></linearGradient></defs><g class="hero-grid"><path d="M0 40H520M0 90H520M0 140H520M45 0V210M145 0V210M245 0V210M345 0V210M445 0V210"/></g><g class="hero-candles"><path d="M82 116v37m0-29h18v18H82zM157 82v47m0-37h18v25h-18zM233 102v54m0-42h18v27h-18zM308 50v58m0-45h18v31h-18zM383 65v48m0-39h18v27h-18zM458 34v60m0-48h18v32h-18z"/></g><path class="hero-chart-line" d="M20 161 86 139l49 13 53-49 47 18 63-54 48 13 54-32 48 17 54-42"/></svg>');
    const session = heroAction.querySelector(".session-line span");
    if (session) session.id = "heroConnectionText";
  }

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
  if (market) market.id = "marketPulse";
  const filters = document.querySelector(".filters-block");
  if (filters) filters.id = "settings";
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

installDashboardEnhancements();
installScannerControls();
$("refreshBtn").addEventListener("click", runScan);
$("saveBtn").addEventListener("click", saveWatchlist);
$("historyBtn").addEventListener("click", loadHistory);
$("applyFiltersBtn").addEventListener("click", () => { scannerState.page = 1; renderRows(); });
$("clearFiltersBtn").addEventListener("click", () => {
  $("minDiff").value = "0";
  $("maxDiff").value = String(scannerState.maxDifference);
  scannerState.page = 1;
  renderRows();
});
$("saveBtn").parentElement.insertAdjacentHTML("beforeend", '<button type="button" class="ghost universe-button">Load 150 NSE + BSE</button>');
document.querySelector(".universe-button").addEventListener("click", (event) => loadUniverse(event.currentTarget));
document.querySelector(".hero-buttons").insertAdjacentHTML("beforeend", '<button type="button" class="universe-hero">Load 150 NSE + BSE stocks ↗</button>');
document.querySelector(".universe-hero").addEventListener("click", () => document.querySelector(".universe-button").click());

loadStatus();
updateClock();
window.setInterval(updateClock, 1000);
