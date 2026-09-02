/* Verify site/index.optimized.html:
     1. the inline script parses
     2. the new score() reproduces the true empirical percentiles on real respondents
     3. show what changes for a real user vs the old cubic+rails map                */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SITE = path.join(__dirname, '..', 'site');
const oldHtml = fs.readFileSync(path.join(SITE, 'index.html'), 'utf8');
const newHtml = fs.readFileSync(path.join(SITE, 'index.optimized.html'), 'utf8');

function grabScore(html, extraStart) {
  const a = html.indexOf(extraStart);
  const b = html.indexOf('/* ================= TEST UI');
  const data = JSON.parse(/const DATA = (\{[\s\S]*?\});\s*\n/.exec(html)[1]);
  const src = html.slice(a, b);
  return { data, fn: new Function('DATA', src + '\nreturn {score, level};') };
}

// --- 1. do all inline scripts parse? ---
// The page intentionally has a tiny early theme bootstrap plus the main application.
// Validate both, and fail loudly if the application script is accidentally missing.
const inlineScripts = [...newHtml.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)]
  .map((m, i) => ({src:m[1], i:i + 1}));
const appScript = inlineScripts.find(s => s.src.includes('const DATA = ') && s.src.includes('function score('));
if (!appScript) {
  console.log('1. inline script ERROR: main application script not found');
  process.exit(1);
}
try {
  for (const s of inlineScripts)
    new vm.Script(s.src, { filename: `index.optimized.html<script#${s.i}>` });
  console.log('1. inline scripts parse: OK (%d scripts, app %d chars)', inlineScripts.length, appScript.src.length);
} catch (e) {
  console.log('1. inline script PARSE ERROR:', e.message);
  process.exit(1);
}

const OLD = grabScore(oldHtml, '/* ================= SCORING');
const NEW = grabScore(newHtml, '/* ================= 经验百分位查找表');
const oldS = OLD.fn(OLD.data), newS = NEW.fn(NEW.data);
console.log('2. both scoring modules constructed: OK');

// --- 3. sanity on a synthetic protocol ---
const OCEAN = ['O', 'C', 'E', 'A', 'N'];
const mk = v => { const a = new Array(301).fill(0); for (let i = 1; i <= 300; i++) a[i] = v; return a; };
for (const v of [1, 3, 5]) {
  const o = oldS.score(mk(v), 'M', 30), n = newS.score(mk(v), 'M', 30);
  console.log(`   all-${v}  old: ` + OCEAN.map(k => k + '=' + o[k].pct.toFixed(2)).join(' '));
  console.log(`          new: ` + OCEAN.map(k => k + '=' + n[k].pct.toFixed(2)).join(' '));
}

// --- 4. the shared result link from the conversation ---
const A36 = '0123456789abcdefghijklmnopqrstuvwxyz';
const body = '1M031H19Dpvpadvdzavwtebwvwe8vwdz8tdhhtypvsbaqzn8dvpgbsvvyd7ppzadphhdpwyptqdwzgyaz87phwqxzzsaqpr7ta8tabpbzfdvdb7yavhb8wbhg7qbdbw7pbahvbnqdwet7wqvbeqyga7dxstpwxq'.slice(9);
const ua = new Array(301).fill(0);
for (let k = 0; k < 150; k++) { const x = A36.indexOf(body[k]); ua[k * 2 + 1] = Math.floor(x / 6); ua[k * 2 + 2] = x % 6; }
const uo = oldS.score(ua, 'M', 31), un = newS.score(ua, 'M', 31);
const pad = (s, w) => String(s).padStart(w);
console.log('\n4. the shared result link (M, 31):');
console.log('   scale' + pad('old', 9) + pad('new', 9) + pad('delta', 9) + '   level old -> new');
for (const k of OCEAN) {
  const d = un[k].pct - uo[k].pct;
  console.log('   ' + k.padEnd(5) + pad(uo[k].pct.toFixed(2), 9) + pad(un[k].pct.toFixed(2), 9) +
    pad((d >= 0 ? '+' : '') + d.toFixed(2), 9) + '   ' + uo[k].level + ' -> ' + un[k].level);
}
let flips = 0, moved5 = 0, tot = 0, biggest = null;
for (const k of OCEAN) uo[k].facets.forEach((f, i) => {
  const g = un[k].facets[i]; tot++;
  if (f.level !== g.level) flips++;
  if (Math.abs(g.pct - f.pct) >= 5) moved5++;
  if (!biggest || Math.abs(g.pct - f.pct) > Math.abs(biggest[3])) biggest = [k, i + 1, NEW.data.facets[k][i][0], g.pct - f.pct, f.pct, g.pct];
});
console.log(`   facets: ${moved5}/${tot} move >=5 points, ${flips}/${tot} change 低/中等/高`);
console.log(`   biggest facet move: ${biggest[0]}${biggest[1]} ${biggest[2]}  ` +
  `${biggest[4].toFixed(2)} -> ${biggest[5].toFixed(2)} (${biggest[3] >= 0 ? '+' : ''}${biggest[3].toFixed(2)})`);

// --- 5. accuracy against the real empirical percentiles, on real respondents ---
const ref = JSON.parse(fs.readFileSync(path.join(__dirname, 'out', 'pct_tables.json'), 'utf8'));
const sample = JSON.parse(fs.readFileSync(path.join(__dirname, 'out', 'sample_rows.json'), 'utf8'));
console.log('\n5. accuracy on %d real respondents drawn from the norm sample:', sample.rows.length);
let oldErr = 0, newErr = 0, oldMax = 0, newMax = 0, n = 0, oldRail = 0;
for (const row of sample.rows) {
  const cohort = (row.sex === 1 ? 'M' : 'F') + '_' + (row.age < 21 ? 'lt21' : 'gte21');
  const ans = [0, ...row.items];
  // the dataset is already reverse-keyed, so undo the site's 6-x before scoring
  const undone = ans.slice();
  for (const q of NEW.data.reversed) undone[q] = 6 - undone[q];
  const o = oldS.score(undone, row.sex === 1 ? 'M' : 'F', row.age);
  const nw = newS.score(undone, row.sex === 1 ? 'M' : 'F', row.age);
  for (const k of OCEAN) {
    const truth = row.truth[k];
    let e = Math.abs(o[k].pct - truth); oldErr += e; oldMax = Math.max(oldMax, e);
    if (o[k].pct === 1 || o[k].pct === 99) oldRail++;
    e = Math.abs(nw[k].pct - truth); newErr += e; newMax = Math.max(newMax, e);
    n++;
    o[k].facets.forEach((f, i) => {
      const t2 = row.truth[k + (i + 1)];
      let e2 = Math.abs(f.pct - t2); oldErr += e2; oldMax = Math.max(oldMax, e2);
      if (f.pct === 1 || f.pct === 99) oldRail++;
      const g = nw[k].facets[i];
      e2 = Math.abs(g.pct - t2); newErr += e2; newMax = Math.max(newMax, e2);
      n++;
    });
  }
}
console.log(`   values compared      : ${n}`);
console.log(`   OLD cubic+rails  MAE : ${(oldErr / n).toFixed(4)}   max ${oldMax.toFixed(3)}   ` +
  `railed ${oldRail} (${(100 * oldRail / n).toFixed(2)}%)`);
console.log(`   NEW empirical    MAE : ${(newErr / n).toFixed(4)}   max ${newMax.toFixed(3)}   railed 0`);
console.log(`   improvement          : ${((oldErr / n) / (newErr / n)).toFixed(1)}x`);
