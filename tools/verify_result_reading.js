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
const round = Math.round;
for (const d of data.domains) {
  for (const pct of [0.1, 29.9, 30, 30.4, 30.6, 33, 50, 66, 69.4, 69.6, 70, 70.1, 99.9]) {
    const r = {pct, facets:[44, 88, 2, 51, 60, 75].map(pct => ({pct}))};
    const before = JSON.stringify(r);
    const text = domainReading(d, r);
    assert.equal(JSON.stringify(r), before, 'Reading must not mutate scores');
    // Bands follow the displayed integer, the same rule as level() and bandOf(): 69.6 shows as 70 and reads as high.
    if (round(pct) <= 30) assert.equal(text.summary, copy[d.key].low);
    else if (round(pct) >= 70) assert.equal(text.summary, copy[d.key].high);
    else assert.ok(text.summary.includes('中间范围'));
    assert.ok(text.evidence.includes('最高的是「' + data.facets[d.key][1][0] + '」（88），最低的是「' + data.facets[d.key][2][0] + '」（2）'));
    // Boundary note only when the displayed score is fewer than 5 points from 30 or 70 (same rule as the profile).
    const gap = Math.min(Math.abs(round(pct) - 30), Math.abs(round(pct) - 70));
    assert.equal(text.evidence.includes('两档的描述都值得参考'), gap < 5, 'boundary note rule at ' + pct);
    if (gap === 0) assert.ok(text.evidence.includes('正好落在'));
    if (pct < 0.5) assert.ok(text.evidence.includes('最低的 1% 以内'));
    else if (pct > 99.5) assert.ok(text.evidence.includes('最高的 1% 以内'));
    else assert.ok(text.evidence.includes('高于约 ' + round(pct) + '% 的同组参考者'));
    assert.equal(text.prompt, '对照生活：' + copy[d.key].prompt);
    cases++;
  }
  const tied = {pct:50, facets:Array.from({length:6}, () => ({pct:50}))};
  assert.ok(domainReading(d, tied).evidence.includes('几乎一样'));
  const allLow = {pct:10, facets:[30.4, 5, 2, 12, 20, 1].map(pct => ({pct}))};
  assert.ok(domainReading(d, allLow).evidence.includes('6 个子面向都偏低，相对最高的是「' + data.facets[d.key][0][0] + '」（30）'));
  const allHigh = {pct:90, facets:[69.6, 95, 88, 80, 77, 99.7].map(pct => ({pct}))};
  assert.ok(domainReading(d, allHigh).evidence.includes('6 个子面向都偏高，相对最低的是「' + data.facets[d.key][0][0] + '」（70）'));
  assert.ok(domainReading(d, {pct:50, facets:[99.7, 50, 50, 50, 50, 0.2].map(pct => ({pct}))}).evidence.includes('（>99）'));
}
assert.ok(!html.includes('概率实测只有 47.2%'));
assert.ok(!html.includes('下面的百分位请当作偏乐观的估计'));
console.log(`PASS: ${cases} score-to-copy mappings, displayed-integer bands, boundary notes, all-low/high and tie wording, unchanged scores.`);
