// Runs site/app.js against a tiny fake DOM and a real summary.json. Exits 1 on any thrown error.
// Usage: node tests/site_dom_smoke.js <path to summary.json> <path to app.js>
const fs = require("fs");
const vm = require("vm");

class Node_ {
  constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; this._text = ""; this.className = ""; this.disabled = false; this.value = ""; }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === "value") this.value = String(v); }
  appendChild(c) { this.children.push(c); if (this.tag === "select" && this.children.length === 1) this.value = c.attrs.value; return c; }
  replaceChildren(...cs) { this.children = cs; }
  get firstChild() { return this.children[0]; }
  set textContent(t) { this._text = String(t); this.children = []; }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
}
const ids = {};
const document = {
  getElementById(id) { return (ids[id] ||= new Node_("div#" + id)); },
  createElement(tag) { return new Node_(tag); },
  createElementNS(_ns, tag) { return new Node_(tag); },
  documentElement: {},
};
const summary = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const context = {
  document, console,
  getComputedStyle: () => ({ getPropertyValue: (n) => (n === "--heat0" ? "#eaf2fb" : "#0b3d75") }),
  fetch: async () => ({ ok: true, json: async () => summary }),
  Number, Math, String, Object, Array, parseInt,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[3], "utf8"), context);
setTimeout(() => {
  const banner = document.getElementById("banner").textContent;
  const out = {
    banner,
    busiest: document.getElementById("busiest-chart").children.length,
    heat: document.getElementById("heatmap").children.length,
    forecast: document.getElementById("fc-chart").children.length,
    completeness: document.getElementById("completeness").children.length,
    attribution: document.getElementById("attribution").textContent,
  };
  if (/Could not load/.test(banner)) { console.error("page error: " + banner); process.exit(1); }
  console.log(JSON.stringify(out));
}, 50);
