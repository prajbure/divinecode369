const number = value => typeof value === 'number' && Number.isFinite(value);
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function decimalText(value) {
  const text = String(value);
  if (!/[eE]/.test(text)) return text;
  const [mantissa, exponent] = text.toLowerCase().split('e');
  const [whole, fraction = ''] = mantissa.split('.');
  const digits = whole + fraction;
  const point = whole.length + Number(exponent);
  if (point <= 0) return '0.' + '0'.repeat(-point) + digits;
  if (point >= digits.length) return digits + '0'.repeat(point - digits.length);
  return digits.slice(0, point) + '.' + digits.slice(point);
}

// Display the backend's Decimal result. Never round prices or differences to
// manufacture an exact match; daily percentage change is a different field.
export function openingDifference(row) {
  const value = row.difference;
  if (!number(value) || row.data_available === false) {
    return '<span class="difference-value missing" aria-label="Opening difference unavailable">--</span>';
  }
  if (value === 0) {
    return '<span class="difference-value exact" aria-label="Exact opening match, zero rupees"><span>₹0.00</span><small>EXACT OPEN</small></span>';
  }
  const supplied = typeof row.difference_display === 'string'
    && /^[+-]?\d+(?:\.\d+)?$/.test(row.difference_display)
    && Number(row.difference_display) === value ? row.difference_display : null;
  const raw = supplied ? supplied.replace(/^[+-]/, '') : decimalText(Math.abs(value));
  const [whole, fraction = ''] = raw.split('.');
  const amount = BigInt(whole || '0').toLocaleString('en-IN') + '.' + fraction.padEnd(2, '0');
  const up = value > 0;
  return `<span class="difference-value ${up ? 'positive' : 'negative'}" aria-label="${up ? 'Positive' : 'Negative'} opening difference ${esc(amount)} rupees"><span class="difference-arrow" aria-hidden="true">${up ? '▲' : '▼'}</span><span>${up ? '+' : '−'}₹${esc(amount)}</span></span>`;
}
