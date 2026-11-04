// Presentation only: classifications and opening calculations belong to FastAPI.
export const SCANNER_FILTERS = Object.freeze({
  all: 'Total Stocks', exact: 'Exact Matches', near: 'Near Matches',
  matched: 'Matched Stocks', bull: 'Bullish Stocks', bear: 'Bearish Stocks', live: 'Verified Live'
});
const finite = value => typeof value === 'number' && Number.isFinite(value);
export const scannerFilter = value => Object.hasOwn(SCANNER_FILTERS, value) ? value : 'all';
export function matchesScannerFilter(row, filter) {
  switch (scannerFilter(filter)) {
    case 'exact': return row.match === true;
    case 'near': return row.near_match === true;
    case 'matched': return row.match === true || row.near_match === true;
    case 'bull': return finite(row.change_pct) && row.change_pct > 0;
    case 'bear': return finite(row.change_pct) && row.change_pct < 0;
    case 'live': return row.quote_status === 'live';
    default: return true;
  }
}
export function uniqueScannerRows(groups, snapshot) {
  const quotes = new Map((snapshot.rows || []).map(row => [row.symbol, row]));
  const rows = new Map();
  for (const group of groups) for (const [symbol, name, note, knownStatus] of group.stocks) {
    const key = `NSE:${symbol}`;
    if (!rows.has(key)) {
      const quote = quotes.get(key) || {}, resolution = snapshot.instrument_resolutions?.[key] || {};
      rows.set(key, {...quote, symbol: key, name, knownStatus,
        note: [note, quote.resolution_note || resolution.resolution_note].filter(Boolean).join(' '),
        quote_symbol: quote.quote_symbol || resolution.quote_symbol || key,
        instrumentStatus: snapshot.instrument_status?.[key],
        gap_pct: snapshot.intelligence?.opening?.[key]?.gap_pct ?? null,
        sector_ids: [], sectors: [], membership_count: 0});
    }
    const row = rows.get(key);
    row.membership_count++;
    if (!row.sector_ids.includes(group.id)) {
      row.sector_ids.push(group.id); row.sectors.push(group.name);
    }
  }
  return [...rows.values()];
}
export function scannerCounts(rows) {
  const unique = [...new Map(rows.map(row => [row.symbol, row])).values()];
  return Object.fromEntries(Object.keys(SCANNER_FILTERS).map(filter =>
    [filter, unique.filter(row => matchesScannerFilter(row, filter)).length]));
}
const SORTS = new Set(['match_priority','name','symbol','sector','prev_close','open','difference','gap_pct','ltp','change_pct','volume','status']);
export function scannerLocation(search) {
  const params = new URLSearchParams(search);
  const bound = key => {
    const raw = params.get(key), value = Number(raw);
    return raw !== null && raw !== '' && finite(value) && value >= 0 ? value : null;
  };
  const size = Number(params.get('size')), page = Number(params.get('page'));
  return {filter: scannerFilter(params.get('filter')), query: params.get('q') || '', sector: params.get('sector') || '',
    sort: SORTS.has(params.get('sort')) ? params.get('sort') : 'match_priority',
    direction: params.get('direction') === 'asc' ? 1 : -1,
    size: [10,25,50,160].includes(size) ? size : 25,
    page: Number.isSafeInteger(page) && page > 0 ? page : 1, min: bound('min'), max: bound('max')};
}
export function scannerSearch(state) {
  const params = new URLSearchParams({filter: scannerFilter(state.filter)});
  for (const [key, value] of [['q',state.query],['sector',state.sector],['sort',state.sort === 'match_priority' ? '' : state.sort],
    ['direction',state.direction === 1 ? 'asc' : ''],['size',state.size === 25 ? '' : state.size],
    ['page',state.page === 1 ? '' : state.page],['min',state.min],['max',state.max]]) {
    if (value !== '' && value !== null && value !== undefined) params.set(key, String(value));
  }
  return '?' + params;
}
