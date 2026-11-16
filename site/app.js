"use strict";
/* Renders data/summary.json. No libraries. Text goes in with textContent only. */

const NS = "http://www.w3.org/2000/svg";
const $ = (id) => document.getElementById(id);

function el(tag, attrs = {}, text) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}
function svg(tag, attrs = {}, text) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  if (text !== undefined) node.textContent = text;
  return node;
}
function table(headers, rows) {
  const t = el("table");
  const head = el("tr");
  headers.forEach((h) => head.appendChild(el("th", { scope: "col" }, h)));
  t.appendChild(el("thead")).appendChild(head);
  const body = el("tbody");
  rows.forEach((r) => {
    const tr = el("tr");
    r.forEach((c) => tr.appendChild(el("td", {}, c === null || c === undefined ? "n/a" : String(c))));
    body.appendChild(tr);
  });
  t.appendChild(body);
  const wrap = el("div", { class: "scroll" });
  wrap.appendChild(t);
  return wrap;
}
const fmt = (n) => Number(n).toLocaleString("en-AU");

function renderBanner(s) {
  const b = $("banner");
  b.textContent = "";
  if (s.data_label === "synthetic") {
    b.className = "banner synthetic";
    b.appendChild(el("span", { class: "big" }, "SYNTHETIC DATA"));
    b.appendChild(el("span", {}, "These numbers come from a generator with a fixed seed. They show how the pipeline works, not real traffic. "));
  } else {
    b.className = "banner";
    b.appendChild(el("span", { class: "big" }, "Real data"));
  }
  b.appendChild(el("span", {}, `Source: ${s.source}. Period: ${s.period.start} to ${s.period.end}.`));
}

function renderBusiest(s) {
  const rows = s.top_sites;
  const w = 720, rowH = 22, left = 70, right = 90, h = rows.length * rowH + 10;
  const max = Math.max(1, ...rows.map((r) => r.total_volume));
  const root = svg("svg", { viewBox: `0 0 ${w} ${h}`, role: "img", "aria-label": `Bar chart of total vehicles for the top ${rows.length} sites` });
  rows.forEach((r, i) => {
    const y = i * rowH + 4;
    const len = ((w - left - right) * r.total_volume) / max;
    root.appendChild(svg("text", { x: left - 6, y: y + 14, "text-anchor": "end" }, r.site_id));
    root.appendChild(svg("rect", { x: left, y, width: Math.max(1, len), height: rowH - 6, class: "bar" }));
    root.appendChild(svg("text", { x: left + len + 6, y: y + 14, class: "muted" }, fmt(r.total_volume)));
  });
  $("busiest-chart").replaceChildren(root);
  $("busiest-table").replaceChildren(table(["Rank", "Site", "Total vehicles"], rows.map((r) => [r.rank, r.site_id, fmt(r.total_volume)])));
}

function mix(t) {
  const css = getComputedStyle(document.documentElement);
  const a = css.getPropertyValue("--heat0").trim(), b = css.getPropertyValue("--heat1").trim();
  const p = (c) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
  const [r0, g0, b0] = p(a), [r1, g1, b1] = p(b);
  const m = (x, y) => Math.round(x + (y - x) * t);
  return `rgb(${m(r0, r1)},${m(g0, g1)},${m(b0, b1)})`;
}

function renderHeatmap(s) {
  const hm = s.heatmap;
  $("heat-note").textContent = `${hm.unit}. Local time is read as AEST (UTC+10).`;
  const flat = hm.values.flat().filter((v) => v !== null);
  const max = Math.max(1, ...flat);
  const cell = 28, left = 40, top = 22;
  const w = left + 24 * cell + 4, h = top + 7 * cell + 4;
  const root = svg("svg", { viewBox: `0 0 ${w} ${h}`, role: "img", "aria-label": "Heat map of mean vehicles per site by weekday and hour" });
  hm.hours.forEach((hr) => {
    if (hr % 3 === 0) root.appendChild(svg("text", { x: left + hr * cell + cell / 2, y: 14, "text-anchor": "middle", class: "muted" }, String(hr)));
  });
  hm.weekdays.forEach((d, i) => {
    root.appendChild(svg("text", { x: left - 6, y: top + i * cell + 18, "text-anchor": "end" }, d));
    hm.hours.forEach((hr) => {
      const v = hm.values[i][hr];
      const rect = svg("rect", { x: left + hr * cell, y: top + i * cell, width: cell - 1, height: cell - 1, fill: v === null ? "none" : mix(v / max), stroke: "var(--line)", "stroke-width": 0.5 });
      rect.appendChild(svg("title", {}, `${d} ${String(hr).padStart(2, "0")}:00, ${v === null ? "no data" : fmt(v)}`));
      root.appendChild(rect);
    });
  });
  const wrap = el("div", { class: "scroll" });
  wrap.appendChild(root);
  $("heatmap").replaceChildren(wrap);
  const headers = ["Weekday", ...hm.hours.map((h) => String(h))];
  $("heat-table").replaceChildren(table(headers, hm.weekdays.map((d, i) => [d, ...hm.values[i]])));
}

function renderForecast(s) {
  const fc = s.forecast, sel = $("fc-site");
  sel.replaceChildren();
  if (!fc.available) {
    $("fc-mae").textContent = fc.reason;
    $("fc-chart").replaceChildren();
    $("fc-table").replaceChildren();
    sel.disabled = true;
    return;
  }
  fc.sites.forEach((site) => sel.appendChild(el("option", { value: site.site_id }, `Site ${site.site_id}`)));
  const draw = () => {
    const site = fc.sites.find((x) => x.site_id === sel.value) || fc.sites[0];
    const m = site.mae_15min;
    $("fc-mae").textContent = `Mean absolute error per 15-minute interval (${site.mae_label}): same hour last week ${m.seasonal_naive ?? "n/a"}, four-week mean ${m.trailing_mean_4w ?? "n/a"} vehicles.`;
    const pts = site.points, w = 720, h = 260, l = 50, r = 10, t = 10, b = 30;
    const vals = pts.flatMap((p) => [p.actual, p.seasonal_naive, p.trailing_mean_4w]).filter((v) => v !== null);
    const max = Math.max(1, ...vals);
    const x = (i) => l + ((w - l - r) * i) / Math.max(1, pts.length - 1);
    const y = (v) => t + (h - t - b) * (1 - v / max);
    const root = svg("svg", { viewBox: `0 0 ${w} ${h}`, role: "img", "aria-label": `Line chart of actual and forecast vehicles per hour for site ${site.site_id}` });
    root.appendChild(svg("line", { x1: l, y1: h - b, x2: w - r, y2: h - b, class: "axis" }));
    root.appendChild(svg("line", { x1: l, y1: t, x2: l, y2: h - b, class: "axis" }));
    root.appendChild(svg("text", { x: l - 6, y: t + 10, "text-anchor": "end", class: "muted" }, fmt(Math.round(max))));
    root.appendChild(svg("text", { x: l - 6, y: h - b, "text-anchor": "end", class: "muted" }, "0"));
    [0, Math.floor(pts.length / 2), pts.length - 1].forEach((i) => {
      if (pts[i]) root.appendChild(svg("text", { x: x(i), y: h - 10, "text-anchor": i === 0 ? "start" : i === pts.length - 1 ? "end" : "middle", class: "muted" }, pts[i].hour_start.slice(0, 10)));
    });
    const path = (key, cls) => {
      let d = "", pen = false;
      pts.forEach((p, i) => {
        if (p[key] === null) { pen = false; return; }
        d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(p[key]).toFixed(1)} `;
        pen = true;
      });
      root.appendChild(svg("path", { d, class: cls }));
    };
    path("trailing_mean_4w", "line-tm");
    path("seasonal_naive", "line-sn");
    path("actual", "line-actual");
    $("fc-chart").replaceChildren(root);
    const legend = el("div", { class: "legend" });
    legend.appendChild(el("span", { class: "a" }, "Actual"));
    legend.appendChild(el("span", { class: "s" }, "Same hour last week"));
    legend.appendChild(el("span", { class: "t" }, "Four-week mean"));
    $("fc-chart").appendChild(legend);
    $("fc-table").replaceChildren(table(["Hour start (UTC)", "Actual", "Last week", "4-week mean"], pts.map((p) => [p.hour_start, p.actual, p.seasonal_naive, p.trailing_mean_4w])));
  };
  sel.disabled = false;
  sel.onchange = draw;
  draw();
}

function renderCompleteness(s) {
  const rows = s.completeness.map((c) => [c.site_id, `${(c.completeness * 100).toFixed(1)}%`, c.detector_days]);
  $("completeness").replaceChildren(table(["Site", "Completeness", "Detector-days"], rows));
}

function renderRest(s) {
  $("map-note").textContent = s.map.shown ? "" : s.map.reason;
  $("attribution").textContent = s.attribution.join(" ");
  $("generated").textContent = `Generated ${s.generated_at}.`;
}

fetch("data/summary.json")
  .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
  .then((s) => { renderBanner(s); renderBusiest(s); renderHeatmap(s); renderForecast(s); renderCompleteness(s); renderRest(s); })
  .catch((err) => {
    const b = $("banner");
    b.className = "banner synthetic";
    b.textContent = `Could not load data/summary.json (${err.message}). Run "make site" first.`;
  });
