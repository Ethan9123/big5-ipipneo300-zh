/* Node round-trip verification for the empirical percentile tables.
   Decodes tools/out/pct_tables_encoded.txt with tools/out/decoder.js and compares
   against tools/out/pct_tables.json cell by cell.  Run: node tools/verify_tables.js */
const fs = require("fs");
const path = require("path");

const OUT = path.join(__dirname, "out");
const { decodePctTables } = require(path.join(OUT, "decoder.js"));

const payload = fs.readFileSync(path.join(OUT, "pct_tables_encoded.txt"), "utf8");
const ref = JSON.parse(fs.readFileSync(path.join(OUT, "pct_tables.json"), "utf8"));

const t0 = process.hrtime.bigint();
const T = decodePctTables(payload);
const t1 = process.hrtime.bigint();

let cells = 0, bad = 0, worst = 0, worstAt = null;
let badRound = 0, badTrunc = 0;
const firstBad = [];

if (T.cohorts.join(",") !== ref.cohorts.join(",")) throw new Error("cohort list mismatch");
if (T.scales.join(",") !== ref.scales.join(",")) throw new Error("scale list mismatch");
if (T.levels.length !== ref.quantisation.n_levels)
  throw new Error("level count mismatch: " + T.levels.length + " vs " + ref.quantisation.n_levels);

for (const g of ref.cohorts) {
  for (const s of ref.scales) {
    const want = ref.tables[g][s].pct_quantised;
    const rawMin = ref.tables[g][s].raw_min;
    const got = T.pct[g][s];
    if (got.length !== want.length)
      throw new Error("length mismatch " + g + "/" + s + ": " + got.length + " vs " + want.length);
    for (let i = 0; i < want.length; i++) {
      cells++;
      const d = Math.abs(got[i] - want[i]);
      if (d > worst) { worst = d; worstAt = g + "/" + s + "/raw" + (rawMin + i); }
      if (d > 1e-9) {
        bad++;
        if (firstBad.length < 5)
          firstBad.push(g + "/" + s + " raw=" + (rawMin + i) + " got=" + got[i] + " want=" + want[i]);
      }
      // the lookup() accessor must agree with the decoded row
      if (T.lookup(g, s, rawMin + i) !== got[i]) throw new Error("lookup() disagrees at " + g + "/" + s);
      // display parity against the UNQUANTISED value
      const ex = ref.tables[g][s].pct_exact[i];
      if (Math.round(ex) !== Math.round(got[i])) badRound++;
      if (Math.trunc(ex) !== Math.trunc(got[i])) badTrunc++;
    }
  }
}

// monotonicity of the decoded rows
let nonMono = 0;
for (const g of ref.cohorts)
  for (const s of ref.scales) {
    const a = T.pct[g][s];
    for (let i = 1; i < a.length; i++) if (a[i] < a[i - 1]) nonMono++;
  }

// norms companion
let normBad = 0, normWorst = 0;
for (const g of ref.cohorts)
  for (const s of ref.scales) {
    const w = ref.norms[g][s], gt = T.norms[g][s];
    const dm = Math.abs(gt.mean - w.mean_encoded), ds = Math.abs(gt.sd - w.sd_encoded);
    normWorst = Math.max(normWorst, dm, ds);
    if (dm > 1e-9 || ds > 1e-9) normBad++;
  }

// T score sanity: reproduce 50 + 10*(raw-mu)/sd
const tsErr = Math.abs(T.tscore("M_lt21", "N", 180) -
  (50 + 10 * (180 - ref.norms.M_lt21.N.mean_encoded) / ref.norms.M_lt21.N.sd_encoded));

console.log("payload bytes            :", Buffer.byteLength(payload, "utf8"));
console.log("decode time              :", Number(t1 - t0) / 1e6, "ms");
console.log("cells compared           :", cells);
console.log("cell mismatches          :", bad, bad ? firstBad : "");
console.log("worst abs cell diff      :", worst, worstAt ? "(at " + worstAt + ")" : "");
console.log("non-monotone steps       :", nonMono);
console.log("norm cells               :", ref.cohorts.length * ref.scales.length,
            "mismatches:", normBad, "worst:", normWorst);
console.log("tscore() reconstruction  :", tsErr);
console.log("Math.round(exact)!=round(decoded) :", badRound);
console.log("Math.trunc(exact)!=trunc(decoded) :", badTrunc);
console.log(bad === 0 && nonMono === 0 && normBad === 0 && cells === 14610
  ? "ROUND-TRIP: PASS" : "ROUND-TRIP: FAIL");
process.exit(bad === 0 && nonMono === 0 && normBad === 0 && cells === 14610 ? 0 : 1);
