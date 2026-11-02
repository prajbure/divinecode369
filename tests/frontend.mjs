import assert from 'node:assert/strict';
import { openingDifference } from '../static/financial-format.js';

const cases = [
  ['positive opening difference', {difference:.05, difference_display:'0.05'}, /positive.*▲.*\+₹0\.05/s],
  ['negative opening difference', {difference:-.05, difference_display:'-0.05'}, /negative.*▼.*−₹0\.05/s],
  ['exact zero badge', {difference:0, match:true}, /exact.*₹0\.00.*EXACT OPEN/s],
  ['missing difference', {difference:null}, /missing.*>--</s],
  ['non-finite difference', {difference:NaN}, /missing.*>--</s],
  ['unavailable data is never exact', {difference:0, data_available:false}, /missing.*>--</s],
  ['sub-paise data is not rounded to an exact zero', {difference:.001, difference_display:'0.001'}, /positive.*₹0\.001/s],
  ['exponential values stay nonzero', {difference:1e-9}, /positive.*₹0\.000000001/s],
  ['inconsistent display text cannot create a false zero', {difference:.05, difference_display:'0.00'}, /positive.*₹0\.05/s],
  ['Indian grouping and sign', {difference:123456.75}, /positive.*₹1,23,456\.75/s]
];
for (const [name, row, pattern] of cases) {
  const before = JSON.stringify(row);
  assert.match(openingDifference(row), pattern, name);
  assert.equal(JSON.stringify(row), before, 'Formatting must not mutate scanner data');
  console.log('PASS ' + name);
}
console.log(`${cases.length} financial formatting checks passed.`);
