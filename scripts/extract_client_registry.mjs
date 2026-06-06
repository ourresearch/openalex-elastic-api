// Client facetConfigs.js registry extractor (#294; re-homed into elastic-api by
// #331 Phase 3). LOCAL refresh tool for the vendored scripts/client_registry.json
// that scripts/check_client_subset.py reads in CI — run it against a local
// openalex-gui checkout (GUI path below) whenever facetConfigs.js changes, then
// commit the regenerated scripts/client_registry.json. Not run in CI itself (CI
// uses the vendored snapshot — no cross-repo dependency).
//
// Loads facetConfigs.js by stubbing its 3 imports, then calls facetConfigs(entity)
// for every entity and serializes the scalar config props we care about.
import fs from "fs";
import path from "path";
import os from "os";
import vm from "vm";

const GUI = process.env.GUI_FACETCONFIGS
  || path.join(os.homedir(), "Documents/openalex-gui/src/facetConfigs.js");
let src = fs.readFileSync(GUI, "utf8");

// Real entity names that getEntityConfigs() returns (from entityConfigs.js).
const ENTITY_NAMES = [
  "works","awards","authors","sources","publishers","funders","institutions",
  "concepts","keywords","topics","subfields","fields","domains","sdgs",
  "countries","continents","languages","types","source-types",
  "institution-types","licenses","oa-statuses","locations",
];

// Strip the ES imports and the export block; inject stubs.
src = src.replace(/^import .*$/gm, "");
src = src.replace(/export\s*\{[\s\S]*?\}\s*;?\s*$/m, "");

const harness = `
const sortByKey = (arr) => arr;
const uniqueObjects = (arr) => arr;
const unravel = () => "";
const getEntityConfigs = () => (${JSON.stringify(ENTITY_NAMES)}).map(name => ({name}));
const countryCodeLookup = { byIso: () => null, byCountry: () => null };
${src}
globalThis.__facetConfigs = facetConfigs;
`;

const ctx = { console };
vm.createContext(ctx);
vm.runInContext(harness, ctx, { filename: "facetConfigs.js" });
const facetConfigs = ctx.__facetConfigs;

// Entities to pull (entityToFilter values). Use the same entity name list.
const out = {};
for (const entity of ENTITY_NAMES) {
  const configs = facetConfigs(entity);
  const cols = {};
  for (const c of configs) {
    cols[c.key] = {
      key: c.key,
      entityToFilter: c.entityToFilter,
      entityToSelect: c.entityToSelect ?? null,
      displayName: c.displayName ?? null,
      type: c.type ?? null,
      actions: c.actions ?? [],
      actionsPopular: c.actionsPopular ?? null,
      isId: c.isId ?? false,
      hasExport: !!(c.column && c.column.export),
    };
  }
  out[entity] = cols;
}

const outPath = path.join(path.dirname(new URL(import.meta.url).pathname), "client_registry.json");
fs.writeFileSync(outPath, JSON.stringify(out, null, 2));
let total = 0;
for (const e of ENTITY_NAMES) { total += Object.keys(out[e]).length; console.error(`  ${e}: ${Object.keys(out[e]).length} columns`); }
console.error(`\nWrote ${outPath}: ${ENTITY_NAMES.length} entities, ${total} columns`);
