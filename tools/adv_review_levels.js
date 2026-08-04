const fs=require("fs"),path=require("path");
const OUT=path.join(__dirname,"out");
const {decodePctTables}=require(path.join(OUT,"decoder.js"));
const T=decodePctTables(fs.readFileSync(path.join(OUT,"pct_tables_encoded.txt"),"ascii"));
const py=JSON.parse(fs.readFileSync(path.join(OUT,"_adv_levels868.json"),"utf8"));
let bad=0,worst=0,at=-1;
if(py.length!==T.levels.length) console.log("LENGTH MISMATCH "+py.length+" vs "+T.levels.length);
for(let i=0;i<py.length;i++){const d=Math.abs(py[i]-T.levels[i]); if(d!==0){bad++; if(d>worst){worst=d;at=i;}}}
console.log("868 levels: JS vs Python not-bit-exact = "+bad+"  worst "+worst+(at>=0?" at index "+at:""));
// exhaustive display-boundary proof over the whole ladder
let vio=0;
for(let i=0;i<T.levels.length;i++){
  const v=T.levels[i];
  if(Math.abs(v*2-Math.round(v*2))<1e-9) vio++;
}
console.log("levels on a .0/.5 boundary: "+vio);
