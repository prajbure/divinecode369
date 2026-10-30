(() => {
  const applyLimitLabels = () => {
    document.querySelectorAll('.universe-hero, .universe-button').forEach((button) => {
      const label = button.classList.contains('universe-hero')
        ? 'Load 150 NSE + BSE stocks ↗'
        : 'Load 150 NSE + BSE';
      if (button.textContent !== label) button.textContent = label;
    });
    const capacity = document.querySelector('.trust-strip > div:nth-child(3) span');
    if (capacity && capacity.textContent !== '150 optionable NSE + BSE stocks') capacity.textContent = '150 optionable NSE + BSE stocks';
    const note = document.querySelector('#symbolsInput')?.nextElementSibling;
    if (note && note.textContent !== '150 optionable stocks · 75 NSE + 75 BSE.') note.textContent = '150 optionable stocks · 75 NSE + 75 BSE.';
  };
  const renderWatchlistNames = (details) => {
    let panel = document.querySelector('#watchlistNames');
    if (!panel) {
      panel = document.createElement('div');
      panel.id = 'watchlistNames';
      panel.className = 'watchlist-names';
      document.querySelector('#symbolsInput')?.parentElement?.appendChild(panel);
    }
    if (!details?.length) {
      panel.innerHTML = '<span class="watchlist-empty">Connect Kite to resolve company names.</span>';
      return;
    }
    const safe = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
    panel.innerHTML = details.map((item) => `<div class="watchlist-name-row"><span><strong>${safe(item.name)}</strong><small>${safe(item.symbol)}</small></span><b>${item.is_equity ? 'EQ' : 'Not equity'}</b></div>`).join('');
  };
  const loadWatchlistNames = async () => {
    try {
      const statusResponse = await fetch('/api/status');
      const status = await statusResponse.json();
      if (!statusResponse.ok || !status.token_configured) {
        renderWatchlistNames([]);
        return;
      }
      const response = await fetch('/api/watchlist/names');
      const data = await response.json();
      renderWatchlistNames(response.ok ? data.details : []);
    } catch (error) {
      renderWatchlistNames([]);
    }
  };
  const smoothRenderMarket = (cards) => {
    const board = document.querySelector('#marketCards');
    if (!board) return;
    if (!cards?.length) {
      board.replaceChildren(Object.assign(document.createElement('div'), {
        className: 'market-placeholder',
        innerHTML: '<span>◌</span> No live index data returned. Check Kite market-data permissions.'
      }));
      return;
    }
    const existing = new Map([...board.querySelectorAll('.market-card')].map((card) => [card.dataset.symbol, card]));
    const visible = new Set();
    cards.forEach((item) => {
      const symbol = String(item.symbol || '');
      visible.add(symbol);
      let card = existing.get(symbol);
      if (!card) {
        card = document.createElement('article');
        card.className = 'market-card';
        card.dataset.symbol = symbol;
        const header = document.createElement('header');
        header.append(document.createElement('span'), document.createElement('span'));
        card.append(header, document.createElement('strong'), document.createElement('small'));
        board.appendChild(card);
      }
      const up = Number(item.change_pct) >= 0;
      const headerSpans = card.querySelectorAll('header span');
      headerSpans[0].textContent = symbol;
      headerSpans[1].textContent = item.change_pct == null ? '—' : `${up ? '+' : ''}${Number(item.change_pct).toFixed(2)}%`;
      headerSpans[1].className = up ? 'up' : 'down';
      card.querySelector('strong').textContent = money(item.price);
      card.querySelector('small').textContent = `Open ${money(item.open)} · Prev close ${money(item.prev_close)}`;
    });
    existing.forEach((card, symbol) => { if (!visible.has(symbol)) card.remove(); });
    const updated = new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date());
    const timestamp = document.querySelector('#marketUpdated');
    if (timestamp) timestamp.textContent = `Live via Kite · ${updated} IST`;
  };
  // app.js owns the live index renderer and scanner's filter/sort/pagination state.
  const refreshStaleWatchlist = async () => {
    try {
      const statusResponse = await fetch('/api/status');
      const status = await statusResponse.json();
      if (!status.token_configured || status.watchlist.length <= 150) return;
      const response = await fetch('/api/watchlist/universe', { method: 'POST' });
      const data = await response.json();
      if (!response.ok) return;
      const input = document.querySelector('#symbolsInput');
      if (input) input.value = data.symbols.join('\n');
      if (typeof updateHistoryOptions === 'function') updateHistoryOptions(data.symbols);
      renderWatchlistNames(await (await fetch('/api/watchlist/names')).json().then((result) => result.details));
      const notice = document.querySelector('#notice');
      if (notice) notice.textContent = `Loaded ${data.nse_count} NSE + ${data.bse_count} BSE optionable equities with company names.`;
    } catch (error) {
      // The regular dashboard remains usable if Kite is not connected.
    }
  };
  const style = document.createElement('style');
  style.textContent = '.watchlist-names{display:grid;gap:8px;margin-top:14px;max-height:260px;overflow:auto}.watchlist-name-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;border:1px solid rgba(218,177,91,.18);border-radius:10px;background:rgba(255,255,255,.035)}.watchlist-name-row strong,.watchlist-name-row small{display:block}.watchlist-name-row strong{color:#f4e2b7}.watchlist-name-row small{margin-top:3px;color:#8f9bb1;font-size:11px}.watchlist-name-row b{color:#76d7ae;font-size:10px;letter-spacing:.08em}.watchlist-name-row b:not(:first-child){white-space:nowrap}.watchlist-empty{color:#8f9bb1;font-size:12px}.market-card,.market-card header span:last-child{animation:none!important}.market-card{transition:none!important}@media(max-width:700px){.table-wrap{overflow:visible}.table-wrap table,.table-wrap tbody{display:block}.table-wrap thead{display:none}.table-wrap tbody{display:grid;gap:12px}.table-wrap tbody tr{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:14px;border:1px solid #34333a;border-radius:12px;background:rgba(18,20,25,.86);animation:none!important}.table-wrap tbody td{display:flex;min-width:0;flex-direction:column;gap:3px;padding:0;border:0;text-align:left}.table-wrap tbody td:before{content:attr(data-label);color:#8f9bb1;font-size:9px;text-transform:uppercase;letter-spacing:.08em}.table-wrap tbody td:first-child,.table-wrap tbody td:last-child{grid-column:1/-1}.table-wrap tbody td:first-child:before{content:"Stock / Symbol"}.table-wrap tbody td:last-child{align-items:flex-start;margin-top:4px}.table-wrap tbody td.empty{display:block;grid-column:1/-1}.stock-name{font-size:14px}.stock-symbol{font-size:10px}.table-wrap tbody tr:has(td.empty){display:block}}';
  // Watchlist styling is in style.css; do not inject legacy mobile table rules here.
  loadWatchlistNames();
  refreshStaleWatchlist();
})();
