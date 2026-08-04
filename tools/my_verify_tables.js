/* Independent check of the encoded percentile tables, written without reading
   build_tables.py -- decode the payload and diff every cell against pct_tables.json. */
const fs = require('fs');
const path = require('path');
const OUT = path.join(__dirname, 'out');
const { decodePctTables } = require(path.join(OUT, 'decoder.js'));

const payload = fs.readFileSync(path.join(OUT, 'pct_tables_encoded.txt'), 'utf8').trim();
const ref = JSON.parse(fs.readFileSync(path.join(OUT, 'pct_tables.json'), 'utf8'));
const T = decodePctTables(payload);

console.log('payload chars   :', payload.length);
console.log('payload bytes   :', Buffer.byteLength(payload, 'utf8'));
console.log('cohorts         :', T.cohorts.join(' '));
console.log('scales          :', T.scales.length, '->', T.scales.slice(0, 8).join(' '), '...');
console.log('quantised levels:', T.levels.length, 'from', T.levels[0], 'to', T.levels[T.levels.length - 1]);
console.log('ref top keys    :', Object.keys(ref).join(' '));

const refTables = ref.tables;

let cells = 0, bad = 0, maxDiff = 0, worst = null, nonMono = 0, monoViol = [];
let qErrMax = 0, qErrSum = 0, qWorst = null;
for (const c of T.cohorts) {
  for (const s of T.scales) {
    const dec = T.pct[c][s];
    const r = refTables[c] && refTables[c][s];
    if (!r) { console.log('MISSING in ref:', c, s); bad++; continue; }
    const arr = r.pct_quantised, exact = r.pct_exact;
    if (arr.length !== dec.length) { console.log('LENGTH MISMATCH', c, s, arr.length, dec.length); bad++; continue; }
    for (let i = 0; i < arr.length; i++) {
      cells++;
      const d = Math.abs(arr[i] - dec[i]);
      if (d > maxDiff) { maxDiff = d; worst = [c, s, i, arr[i], dec[i]]; }
      if (d > 1e-9) bad++;
      const q = Math.abs(exact[i] - dec[i]);
      qErrSum += q;
      if (q > qErrMax) { qErrMax = q; qWorst = [c, s, i + r.raw_min, exact[i], dec[i]]; }
      if (i && dec[i] < dec[i - 1]) { nonMono++; if (monoViol.length < 5) monoViol.push([c, s, i, dec[i - 1], dec[i]]); }
    }
  }
}
console.log('\ncells compared             :', cells, '(expected 14610)');
console.log('decoder vs pct_quantised   : differing cells =', bad, ', max abs diff =', maxDiff);
console.log('quantisation error vs exact: max =', qErrMax.toFixed(6), ', mean =', (qErrSum / cells).toFixed(6));
console.log('   worst quantised cell    :', qWorst ? qWorst.join(' / ') : '-');
console.log('monotonicity violations    :', nonMono, monoViol.length ? JSON.stringify(monoViol[0]) : '');

// range sanity
let lo = Infinity, hi = -Infinity;
for (const c of T.cohorts) for (const s of T.scales) for (const v of T.pct[c][s]) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
console.log('percentile range       :', lo.toFixed(4), '..', hi.toFixed(4));
console.log('any exactly 0 or 100   :', lo === 0 || hi === 100);

// what the user sees: does quantisation ever change the rounded display?
let roundChanged = 0;
for (const c of T.cohorts) for (const s of T.scales) {
  const dec = T.pct[c][s], a = refTables[c][s].pct_exact;
  for (let i = 0; i < dec.length; i++) if (Math.round(dec[i]) !== Math.round(a[i])) roundChanged++;
}
console.log('cells whose Math.round differs after quantisation:', roundChanged, '/', cells);
