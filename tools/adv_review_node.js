/* ADVERSARIAL independent node round-trip.
   Does NOT reuse tools/verify_tables.js.  Diffs EVERY cell of the decoded
   payload against pct_tables.json, and independently re-derives the ladder. */
const fs = require("fs");
const path = require("path");
const OUT = path.join(__dirname, "out");
const { decodePctTables } = require(path.join(OUT, "decoder.js"));

const payload = fs.readFileSync(path.join(OUT, "pct_tables_encoded.txt"), "ascii");
const J = JSON.parse(fs.readFileSync(path.join(OUT, "pct_tables.json"), "utf8"));

const t0 = process.hrtime.bigint();
const T = decodePctTables(payload);
const t1 = process.hrtime.bigint();
console.log("node " + process.version + "  decode " + (Number(t1 - t0) / 1e6).toFixed(3) + " ms");

// --- payload structure, measured here ---
const S = payload.split("~");
console.log("payload segments: " + S.length + "  header sizes: magic=" + S[0].length +
  " cohorts=" + S[1].length + " scales=" + S[2].length + " ladder=" + S[3].length +
  " norms=" + S[4].length + " tables=" + S[5].length);
console.log("payload total chars = " + payload.length +
  "  (segments+seps = " + (S.reduce((a, b) => a + b.length, 0) + S.length - 1) + ")");
const nCells = 6 * (5 * 241 + 30 * 41);
console.log("table segment chars = " + S[5].length + " for " + nCells + " cells -> " +
  (S[5].length - nCells) + " two-char cells, " + (S[5].length / nCells).toFixed(5) + " chars/cell");
console.log("norms segment chars = " + S[4].length + " (expect 6*35*2*3 = " + (6 * 35 * 2 * 3) + ")");

// --- cell-by-cell diff ---
let cmp = 0, bad = 0, worst = 0, worstAt = null, nonMono = 0, monoRows = 0;
let exactBits = 0;
for (const g of J.cohorts) {
  for (const nm of J.scales) {
    const want = J.tables[g][nm].pct_quantised;
    const got = T.pct[g][nm];
    if (!got) { console.log("MISSING " + g + " " + nm); bad += want.length; continue; }
    if (got.length !== want.length) { console.log("LEN MISMATCH " + g + " " + nm + " " + got.length + " vs " + want.length); }
    let rowBad = 0;
    for (let i = 0; i < want.length; i++) {
      cmp++;
      const d = Math.abs(got[i] - want[i]);
      if (d > worst) { worst = d; worstAt = g + "/" + nm + "/raw" + (J.tables[g][nm].raw_min + i); }
      if (d !== 0) { bad++; rowBad++; }
      else exactBits++;
      if (i && got[i] < got[i - 1]) nonMono++;
    }
    monoRows++;
    // lookup() accessor must agree with the raw array
    const rmin = J.tables[g][nm].raw_min;
    for (let i = 0; i < want.length; i++) {
      if (T.lookup(g, nm, rmin + i) !== got[i]) { console.log("lookup() disagrees " + g + " " + nm + " " + (rmin + i)); bad++; }
    }
  }
}
console.log("cells compared        : " + cmp);
console.log("cells NOT bit-exact   : " + bad);
console.log("bit-exact cells       : " + exactBits);
console.log("worst |decoded - json|: " + worst + (worstAt ? "  at " + worstAt : ""));
console.log("non-monotone steps in decoded arrays: " + nonMono + " over " + monoRows + " rows");

// --- levels array ---
let lbad = 0;
console.log("decoded levels length : " + T.levels.length + " (json " + J.quantisation.n_levels + ")");
for (let i = 1; i < T.levels.length; i++) if (!(T.levels[i] > T.levels[i - 1])) lbad++;
console.log("levels strictly increasing: " + (lbad === 0));
console.log("levels[0]=" + T.levels[0] + " levels[last]=" + T.levels[T.levels.length - 1]);
// no level on an integer or .5
let onGrid = 0;
for (let i = 0; i < T.levels.length; i++) {
  const v = T.levels[i] * 2;
  if (Math.abs(v - Math.round(v)) < 1e-9) onGrid++;
}
console.log("levels landing exactly on .0/.5: " + onGrid);

// --- norms ---
let nbad = 0, worstMean = 0, worstSd = 0;
for (const g of J.cohorts) for (const nm of J.scales) {
  const n = T.norms[g][nm];
  const jm = J.norms[g][nm];
  const dm = Math.abs(n.mean - jm.mean_encoded), ds = Math.abs(n.sd - jm.sd_encoded);
  if (dm > 1e-9 || ds > 1e-9) nbad++;
  worstMean = Math.max(worstMean, Math.abs(n.mean - jm.mean));
  worstSd = Math.max(worstSd, Math.abs(n.sd - jm.sd));
}
console.log("norm pairs mismatching encoded value: " + nbad + " of " + (6 * 35));
console.log("worst |decoded mean - full-precision mean| = " + worstMean.toFixed(6));
console.log("worst |decoded sd   - full-precision sd  | = " + worstSd.toFixed(6));

// --- tscore accessor ---
let tbad = 0, worstT = 0, worstTat = null;
for (const g of J.cohorts) for (const nm of J.scales) {
  const jm = J.norms[g][nm];
  const rmin = J.tables[g][nm].raw_min, rmax = rmin + J.tables[g][nm].pct_exact.length - 1;
  for (const r of [rmin, rmax, Math.round((rmin + rmax) / 2)]) {
    const got = T.tscore(g, nm, r);
    const truth = 50 + 10 * (r - jm.mean) / jm.sd;
    const d = Math.abs(got - truth);
    if (d > worstT) { worstT = d; worstTat = g + "/" + nm + "/raw" + r; }
    const chk = 50 + 10 * (r - jm.mean_encoded) / jm.sd_encoded;
    if (Math.abs(got - chk) > 1e-9) tbad++;
  }
}
console.log("tscore() disagreements with encoded norms: " + tbad);
console.log("worst T error vs full-precision norms (at raw extremes): " + worstT.toFixed(6) + " at " + worstTat);

console.log(bad === 0 && nonMono === 0 && lbad === 0 ? "ROUND-TRIP: PASS" : "ROUND-TRIP: FAIL");
