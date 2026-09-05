// Exercise score-to-copy mappings without a browser or personal answer data.
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const html = fs.readFileSync(path.join(__dirname, '../site/index.optimized.html'), 'utf8');
const data = JSON.parse(/const DATA = (\{[\s\S]*?\});\s*\n/.exec(html)[1]);
const start = html.indexOf('const DOMAIN_READING =');
const end = html.indexOf('const COLOR =', start);
assert.ok(start >= 0 && end > start, 'Result explanation module must exist');
const {domainReading, copy} = new Function('DATA', html.slice(start, end) +
  '\nreturn {domainReading, copy:DOMAIN_READING};')(data);

let cases = 0;
for (const d of data.domains) {
  for (const pct of [0.1, 29.9, 30, 30.1, 50, 69.9, 70, 70.1, 99.9]) {
    const r = {pct, facets:[44, 88, 2, 51, 60, 75].map(pct => ({pct}))};
    const before = JSON.stringify(r);
    const text = domainReading(d, r);
    assert.equal(JSON.stringify(r), before, 'Reading must not mutate scores');
    if (pct <= 30) assert.equal(text.summary, copy[d.key].low);
    else if (pct >= 70) assert.equal(text.summary, copy[d.key].high);
    else assert.ok(text.summary.includes('中间范围'));
    assert.ok(text.evidence.includes('「' + data.facets[d.key][1][0] + '」的百分位相对较高（88）'));
    assert.ok(text.evidence.includes('「' + data.facets[d.key][2][0] + '」相对较低（2）'));
    assert.ok(!text.evidence.includes('估计区间跨过'));
    assert.equal(text.prompt, '对照生活：' + copy[d.key].prompt);
    cases++;
  }
  const tied = {pct:50, facets:Array.from({length:6}, () => ({pct:50})), ci:[40,60]};
  assert.ok(domainReading(d, tied).evidence.includes('不突出最高或最低项'));
  assert.ok(!domainReading(d, tied).evidence.includes('估计区间跨过'));
  for (const ci of [[20,30], [65,75], [10,90]]) {
    assert.ok(domainReading(d, {...tied, ci}).evidence.includes('估计区间跨过'));
  }
}
assert.ok(!html.includes('概率实测只有 47.2%'));
assert.ok(!html.includes('下面的百分位请当作偏乐观的估计'));
console.log(`PASS: ${cases} score-to-copy mappings, facet order, ties, interval boundaries, and unchanged scores.`);
