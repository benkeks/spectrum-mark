const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const { equiv } = require(path.join(root, "equivio/js-api/target/scala-2.13/eqfiddle-api-fastopt/main.js"));
const section = process.argv[2] || "running";
const output = process.argv[3];

function sample(name) {
  const source = fs.readFileSync(path.join(root,
    "equivio/shared/src/main/scala-2.13/io/equiv/eqfiddle/ccs/CCSSamples.scala"), "utf8");
  const match = source.match(new RegExp(`val ${name}\\s*=\\s*"""([\\s\\S]*?)"""`));
  assert.ok(match, `Missing bundled CCS example: ${name}`);
  return match[1].replace(/^[ \t]*\|/gm, "");
}

function analyze(source, left, right, semantics, label) {
  const result = equiv.spectroscopy({ source, left, right, semantics });
  assert.equal(result.status, "complete", JSON.stringify(result.error));
  if (output) {
    fs.mkdirSync(output, { recursive: true });
    fs.writeFileSync(path.join(output, `${label}.json`), JSON.stringify(result, null, 2) + "\n");
    fs.writeFileSync(path.join(output, `${label}.ccs`), source + "\n");
  }
  console.log(`${left}/${right} (${semantics}): ${result.strongestEquivalences.join(", ")}`);
  if (section === "running") {
    for (const pair of result.pairs) {
      console.log(`${pair.left} -> ${pair.right} (strongest preorders): ${pair.preorderings.join(", ")}`);
    }
  }
  return name => {
    const relation = result.relations.find(item => item.name === name);
    assert.ok(relation, `Missing relation: ${name}`);
    return relation;
  };
}

if (section === "running") {
  const source = "P = tau.a + tau.b\nQ = tau.(a + b)";
  const relation = analyze(source, "P", "Q", "strong", "running");
  assert.equal(relation("trace").equivalent, true);
  assert.equal(relation("simulation").leftToRight, true);
  assert.equal(relation("simulation").rightToLeft, false);
  assert.equal(relation("failure").leftToRight, false);
  assert.equal(relation("failure").rightToLeft, true);
  assert.equal(relation("bisimulation").equivalent, false);
} else if (section === "peterson") {
  const source = sample("petersonMutexSilent");
  const original = analyze(source, "Pe", "Mx", "weak", "peterson-mx");
  assert.equal(original("weak-trace").equivalent, true);
  assert.equal(original("weak-simulation").equivalent, true);
  assert.equal(original("weak-bisimulation").equivalent, false);
  const improved = analyze(source, "Pe", "MxIC", "weak", "peterson-mxic");
  for (const name of ["stable-readiness", "eta-simulation", "weak-ready-simulation"]) {
    assert.equal(improved(name).equivalent, true, name);
  }
  assert.equal(improved("weak-bisimulation").equivalent, false);
} else if (section === "hiding") {
  const source = sample("stableUnstableAbstraction");
  const before = analyze(source, "P_e", "P_l", "weak", "hiding-before");
  assert.equal(before("weak-failure").equivalent, true);
  const after = analyze(source, "P_te", "P_tl", "weak", "hiding-after");
  assert.equal(after("weak-failure").leftToRight, false);
  assert.equal(after("weak-failure").rightToLeft, true);
  assert.equal(after("stable-failure").equivalent, true);
} else {
  throw new Error(`Unknown example section: ${section}`);
}
