"use strict";

(() => {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const HALF_W = 400;
  const HALF_H = 300;
  const MAX_CONSOLE_CHUNKS = 2000;
  const MAX_CALLERS = 4;
  const STATUS_LABELS = {
    starting: "Starting…",
    running: "Running…",
    finished: "Program finished ✓",
    crashed: "Stopped by an error ✗",
  };

  const $ = (id) => document.getElementById(id);

  const app = {
    run: 0,
    state: "starting",
    nodes: new Map(),
    staleIds: null,
    connected: false,
  };

  window.__playground = {
    get state() { return app.state; },
    get run() { return app.run; },
    get nodes() { return app.nodes; },
  };

  // ---------- small helpers ----------

  function svg(name, attrs) {
    const e = document.createElementNS(SVG_NS, name);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }

  function num(value, fallback) {
    const n = typeof value === "number" ? value : Number(value);
    return Number.isFinite(n) ? n : fallback;
  }

  const fmt = (n) => String(Math.round(n * 1000) / 1000);

  // Geometry and paint are set as attributes (readable, works everywhere) and as CSS
  // properties (so supporting browsers can animate them).
  function geom(e, values) {
    for (const k in values) {
      e.setAttribute(k, fmt(values[k]));
      e.style.setProperty(k, fmt(values[k]) + "px");
    }
  }

  function paint(e, prop, color) {
    e.setAttribute(prop, color);
    e.style.setProperty(prop, color);
  }

  // Run `fn` with transitions off, restoring them on the next animation frame.
  function withoutAnimation(e, fn) {
    e.classList.add("no-anim");
    fn();
    requestAnimationFrame(() => e.classList.remove("no-anim"));
  }

  function post(url, body) {
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? "" : JSON.stringify(body),
      keepalive: true,
    }).catch(() => {});
  }

  // ---------- status, banner, script name ----------

  function setState(state) {
    app.state = state;
    document.body.dataset.state = state;
    const badge = $("status");
    badge.dataset.state = state;
    badge.querySelector(".label").textContent = STATUS_LABELS[state] || state;
  }

  function setRun(run) {
    app.run = run;
    document.body.dataset.run = String(run);
  }

  function setConnected(connected) {
    app.connected = connected;
    document.body.dataset.conn = connected ? "ok" : "lost";
    $("banner").hidden = connected;
  }

  function setScript(name) {
    const e = $("script-name");
    e.textContent = name || "";
    e.hidden = !name;
  }

  // ---------- rendering ----------

  const layers = { shapes: $("shapes"), guides: $("guides") };

  const COMMON = { x: 0, y: 0, rotation: 0, title: "", opacity: 1, visible: true, color: "steelblue" };
  const GUIDE_COMMON = { opacity: 1, visible: true, size: 50, style: "solid" };

  const DEFAULTS = {
    circle: { radius: 50 },
    rectangle: { width: 100, height: 60 },
    triangle: { width: 100, height: 100 },
    line: { x2: 100, y2: 0, width: 3, color: "black" },
    text: { text: "", size: 32, color: "black" },
    grid: { color: "lightgray", width: 1 },
    axis: { color: "gray", width: 3, labels: true },
  };

  function titleSize(minSide) {
    return Math.max(10, Math.min(16, minSide * 0.4));
  }

  function setTitle(node, x, y, minSide) {
    const p = node.props;
    let t = node.title;
    if (!t) {
      t = node.title = svg("text", { class: "title", "text-anchor": "middle", "dominant-baseline": "central" });
      node.el.appendChild(t);
    }
    t.textContent = p.title == null ? "" : String(p.title);
    t.setAttribute("x", fmt(x));
    t.setAttribute("y", fmt(y));
    t.setAttribute("font-size", fmt(titleSize(minSide)));
    t.style.display = t.textContent ? "" : "none";
  }

  function dashFor(style) {
    if (style === "dashed") return { dash: "8 6", cap: "butt" };
    if (style === "dotted") return { dash: "1 5", cap: "round" };
    return { dash: "none", cap: "butt" };
  }

  // Numbers on the axis: no floating point noise (0.30000000000000004 -> 0.3).
  const label = (v) => String(Math.round(v * 10000) / 10000);

  const SHAPES = {
    circle: {
      build(node) {
        node.body = svg("circle");
        node.el.appendChild(node.body);
      },
      apply(node) {
        const p = node.props;
        const r = Math.max(0, num(p.radius, 50));
        geom(node.body, { r });
        paint(node.body, "fill", p.color);
        setTitle(node, 0, 0, r * 2);
      },
    },
    rectangle: {
      build(node) {
        node.body = svg("rect", { rx: 4 });
        node.el.appendChild(node.body);
      },
      apply(node) {
        const p = node.props;
        const w = Math.max(0, num(p.width, 100));
        const h = Math.max(0, num(p.height, 60));
        geom(node.body, { x: -w / 2, y: -h / 2, width: w, height: h });
        paint(node.body, "fill", p.color);
        setTitle(node, 0, 0, Math.min(w, h));
      },
    },
    triangle: {
      build(node) {
        node.body = svg("polygon");
        node.el.appendChild(node.body);
      },
      apply(node) {
        const p = node.props;
        const w = Math.max(0, num(p.width, 100));
        const h = Math.max(0, num(p.height, 100));
        const pts = [[0, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]];
        node.body.setAttribute("points", pts.map(([a, b]) => fmt(a) + "," + fmt(b)).join(" "));
        paint(node.body, "fill", p.color);
        setTitle(node, 0, h * 0.17, Math.min(w, h));
      },
    },
    line: {
      noRotation: true,
      build(node) {
        node.body = svg("line", { x1: 0, y1: 0, "stroke-linecap": "round" });
        node.el.appendChild(node.body);
      },
      apply(node) {
        const p = node.props;
        const dx = num(p.x2, 100) - num(p.x, 0);
        const dy = -(num(p.y2, 0) - num(p.y, 0));
        node.body.setAttribute("x2", fmt(dx));
        node.body.setAttribute("y2", fmt(dy));
        node.body.setAttribute("stroke-width", fmt(num(p.width, 3)));
        paint(node.body, "stroke", p.color);
        setTitle(node, dx / 2, dy / 2, 40);
      },
    },
    text: {
      build(node) {
        node.body = svg("text", { class: "content", "text-anchor": "middle", "dominant-baseline": "central" });
        node.el.appendChild(node.body);
      },
      apply(node) {
        const p = node.props;
        node.body.textContent = p.text == null ? "" : String(p.text);
        node.body.setAttribute("font-size", fmt(num(p.size, 32)));
        paint(node.body, "fill", p.color);
      },
    },
    grid: {
      guide: true,
      build(node) {
        node.body = svg("path", { fill: "none" });
        node.el.appendChild(node.body);
      },
      apply(node) {
        const p = node.props;
        const step = Math.max(2, num(p.size, 50));
        let d = "";
        for (let x = step; x <= HALF_W; x += step) d += `M${fmt(x)} ${-HALF_H}V${HALF_H}M${fmt(-x)} ${-HALF_H}V${HALF_H}`;
        for (let y = step; y <= HALF_H; y += step) d += `M${-HALF_W} ${fmt(y)}H${HALF_W}M${-HALF_W} ${fmt(-y)}H${HALF_W}`;
        d += `M0 ${-HALF_H}V${HALF_H}M${-HALF_W} 0H${HALF_W}`;
        const { dash, cap } = dashFor(p.style);
        node.body.setAttribute("d", d);
        node.body.setAttribute("stroke-width", fmt(num(p.width, 1)));
        node.body.setAttribute("stroke-dasharray", dash);
        node.body.setAttribute("stroke-linecap", cap);
        paint(node.body, "stroke", p.color);
      },
    },
    axis: {
      guide: true,
      build(node) {
        node.lines = svg("path", { fill: "none" });
        node.ticks = svg("path", { fill: "none" });
        node.labels = svg("g");
        node.el.append(node.lines, node.ticks, node.labels);
      },
      apply(node) {
        const p = node.props;
        const size = Math.max(2, num(p.size, 50));
        const width = num(p.width, 3);
        const { dash, cap } = dashFor(p.style);
        node.lines.setAttribute("d", `M${-HALF_W} 0H${HALF_W}M0 ${-HALF_H}V${HALF_H}`);
        node.lines.setAttribute("stroke-dasharray", dash);
        node.lines.setAttribute("stroke-linecap", cap);
        for (const part of [node.lines, node.ticks]) {
          part.setAttribute("stroke-width", fmt(width));
          paint(part, "stroke", p.color);
        }
        paint(node.labels, "fill", p.color);

        const showLabels = p.labels !== false;
        const key = `${size}|${showLabels}|${width}`;
        if (key === node.geomKey) return;
        node.geomKey = key;
        let ticks = "";
        const texts = [];
        const every = Math.ceil(34 / size);
        const off = 11 + width / 2;
        const add = (text, x, y, anchor) => {
          const t = svg("text", { x: fmt(x), y: fmt(y), "text-anchor": anchor, "dominant-baseline": "central", "font-size": 12 });
          t.textContent = text;
          texts.push(t);
        };
        for (const [half, vertical] of [[HALF_W, false], [HALF_H, true]]) {
          for (let k = 1; k * size <= half; k++) {
            for (const v of [k * size, -k * size]) {
              ticks += vertical ? `M-4 ${fmt(-v)}H4` : `M${fmt(v)} -4V4`;
              if (showLabels && k % every === 0 && k * size <= half - 12) {
                if (vertical) add(label(v), -off, -v, "end");
                else add(label(v), v, off + 1, "middle");
              }
            }
          }
        }
        if (showLabels) add("0", -off, off + 1, "end");
        node.ticks.setAttribute("d", ticks);
        node.labels.replaceChildren(...texts);
      },
    },
  };

  function applyNode(node) {
    const p = node.props;
    const def = SHAPES[node.type];
    def.apply(node);
    const g = node.el;
    g.style.opacity = String(num(p.opacity, 1));
    g.style.display = p.visible === false ? "none" : "";
    if (!def.guide) {
      const rot = def.noRotation ? "" : ` rotate(${fmt(-num(p.rotation, 0))}deg)`;
      g.style.transform = `translate(${fmt(num(p.x, 0))}px, ${fmt(-num(p.y, 0))}px)` + rot;
    }
  }

  function createNode(id, type, props) {
    const def = SHAPES[type];
    if (!def) {
      console.warn("Playground: unknown shape type", type);
      return;
    }
    const old = app.nodes.get(id);
    if (app.staleIds) app.staleIds.delete(id);
    if (old && old.type === type) {
      Object.assign(old.props, props);
      applyNode(old);
      return;
    }
    if (old) removeNode(id);
    const el = svg("g", { "data-id": id, "data-type": type });
    el.classList.add(def.guide ? "guide" : "shape");
    const node = { type, el, props: Object.assign({}, def.guide ? GUIDE_COMMON : COMMON, DEFAULTS[type], props) };
    withoutAnimation(el, () => {
      def.build(node);
      applyNode(node);
    });
    (def.guide ? layers.guides : layers.shapes).appendChild(el);
    app.nodes.set(id, node);
  }

  function updateNode(id, props) {
    const node = app.nodes.get(id);
    if (!node) return;
    Object.assign(node.props, props);
    applyNode(node);
  }

  function removeNode(id) {
    const node = app.nodes.get(id);
    if (!node) return;
    node.el.remove();
    app.nodes.delete(id);
    if (app.staleIds) app.staleIds.delete(id);
  }

  function clearNodes() {
    for (const id of [...app.nodes.keys()]) removeNode(id);
  }

  // Keep the DOM in creation (id) order so stacking matches the program.
  function restack() {
    for (const layer of Object.values(layers)) {
      const kids = [...layer.children];
      const sorted = [...kids].sort((a, b) => Number(a.dataset.id) - Number(b.dataset.id));
      if (sorted.every((k, i) => k === kids[i])) continue;
      sorted.forEach((k) => layer.appendChild(k));
    }
  }

  function sweepStale() {
    if (!app.staleIds) return;
    for (const id of [...app.staleIds]) removeNode(id);
    app.staleIds = null;
    restack();
  }

  function applyOps(ops) {
    for (const op of ops || []) {
      if (op.op === "create") createNode(op.id, op.type, op.props || {});
      else if (op.op === "update") updateNode(op.id, op.props || {});
      else if (op.op === "remove") removeNode(op.id);
    }
  }

  function setBackground(color, animate) {
    const bg = $("background");
    if (animate) paint(bg, "fill", color);
    else withoutAnimation(bg, () => paint(bg, "fill", color));
  }

  // ---------- console ----------

  const consoleEl = $("console");
  const consoleStats = { lines: 0, partial: false };
  const countNewlines = (s) => s.split("\n").length - 1;

  function updateConsoleCount() {
    const n = consoleStats.lines + (consoleStats.partial ? 1 : 0);
    const badge = $("console-count");
    badge.textContent = String(n);
    badge.hidden = n === 0;
  }

  function addConsole(text, stream) {
    if (!text) return;
    const stick = consoleEl.scrollHeight - consoleEl.scrollTop - consoleEl.clientHeight < 24;
    const cls = stream === "stderr" ? "stderr" : "stdout";
    const last = consoleEl.lastElementChild;
    if (last && last.className === cls && !last.textContent.endsWith("\n")) {
      last.firstChild.appendData(text);
    } else {
      const span = document.createElement("span");
      span.className = cls;
      span.textContent = text;
      consoleEl.appendChild(span);
      while (consoleEl.childElementCount > MAX_CONSOLE_CHUNKS) {
        const first = consoleEl.firstElementChild;
        consoleStats.lines -= countNewlines(first.textContent);
        first.remove();
      }
    }
    consoleStats.lines += countNewlines(text);
    consoleStats.partial = !text.endsWith("\n");
    updateConsoleCount();
    if (stick) consoleEl.scrollTop = consoleEl.scrollHeight;
  }

  function clearConsole() {
    consoleEl.replaceChildren();
    consoleStats.lines = 0;
    consoleStats.partial = false;
    updateConsoleCount();
  }

  function setConsoleOpen(open) {
    $("console-panel").dataset.open = String(open);
    $("console-toggle").setAttribute("aria-expanded", String(open));
  }

  function initConsole() {
    let open = true;
    try { open = localStorage.getItem("playground.console") !== "closed"; } catch (e) { /* private mode */ }
    setConsoleOpen(open);
    $("console-toggle").addEventListener("click", (e) => {
      const next = $("console-panel").dataset.open !== "true";
      setConsoleOpen(next);
      try { localStorage.setItem("playground.console", next ? "open" : "closed"); } catch (err) { /* ignore */ }
      if (e.detail) e.currentTarget.blur();
    });
    $("console-clear").addEventListener("click", (e) => {
      clearConsole();
      if (e.detail) e.currentTarget.blur();
    });
  }

  // ---------- error panel ----------

  function div(cls, text) {
    const e = document.createElement("div");
    e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function codeLine(entry, hit, last) {
    const row = div("code-line" + (hit ? " hit" : ""));
    row.dataset.line = String(entry.line);
    row.appendChild(div("no", String(entry.line)));
    const src = div("src");
    const code = entry.code == null ? "" : String(entry.code);
    if (hit && last && last.col) {
      const chars = Array.from(code);
      const start = last.col - 1;
      while (chars.length < start + 1) chars.push(" ");
      const end = Math.min(Math.max(last.end_col ? last.end_col - 1 : start + 1, start + 1), chars.length);
      const mark = document.createElement("span");
      mark.className = "mark";
      mark.textContent = chars.slice(start, end).join("");
      src.append(chars.slice(0, start).join(""), mark, chars.slice(end).join(""));
    } else {
      src.textContent = code || " ";
    }
    row.appendChild(src);
    return row;
  }

  function renderError(err) {
    const panel = $("error-panel");
    const frames = Array.isArray(err.frames) ? err.frames : [];
    const last = frames.length ? frames[frames.length - 1] : null;
    const kids = [];

    const title = div("err-title");
    const icon = document.createElement("span");
    icon.className = "err-icon";
    icon.textContent = "⚠";
    const kind = document.createElement("span");
    kind.className = "err-kind";
    kind.textContent = err.kind || "Error";
    title.append(icon, kind);
    kids.push(title, div("err-message", err.message || ""));

    if (frames.length > 1) {
      const list = document.createElement("ul");
      list.className = "err-callers";
      const callers = frames.slice(0, -1);
      for (const f of callers.slice(0, MAX_CALLERS)) {
        const li = document.createElement("li");
        li.textContent = `${f.file}, line ${f.line} in ${f.function}`;
        list.appendChild(li);
      }
      if (callers.length > MAX_CALLERS) {
        const li = document.createElement("li");
        li.textContent = "…";
        list.appendChild(li);
      }
      kids.push(list);
    }

    if (last) {
      const where = div("err-where");
      const strong = document.createElement("strong");
      strong.textContent = `${last.file}, line ${last.line}`;
      where.append("File ", strong);
      kids.push(where);
      let context = Array.isArray(err.context) ? err.context : [];
      if (!context.length && last.code != null) context = [{ line: last.line, code: last.code }];
      if (context.length) {
        const code = div("code");
        for (const entry of context) code.appendChild(codeLine(entry, entry.line === last.line, last));
        kids.push(code);
      }
    }

    panel.replaceChildren(...kids);
    panel.hidden = false;
    document.body.classList.add("has-error");
  }

  function hideError() {
    const panel = $("error-panel");
    panel.hidden = true;
    panel.replaceChildren();
    document.body.classList.remove("has-error");
  }

  // ---------- messages from the host ----------

  function onSnapshot(s) {
    clearNodes();
    app.staleIds = null;
    setRun(s.run || 0);
    setState(s.state || "starting");
    setScript(s.script);
    setBackground(s.background || "white", false);
    for (const o of s.objects || []) createNode(o.id, o.type, o.props || {});
    restack();
    clearConsole();
    for (const c of s.console || []) addConsole(c.text, c.stream);
    if (s.error) renderError(s.error);
    else hideError();
  }

  function onRun(msg) {
    setRun(msg.run);
    app.staleIds = new Set(app.nodes.keys());
    setBackground("white", false);
    clearConsole();
    hideError();
    setState("starting");
  }

  function onStatus(msg) {
    if (msg.run !== undefined && msg.run < app.run) return;
    if (msg.run !== undefined) setRun(msg.run);
    setState(msg.state);
    if (msg.state === "finished" || msg.state === "crashed") sweepStale();
  }

  const HANDLERS = {
    snapshot: onSnapshot,
    run: onRun,
    status: onStatus,
    frame(msg) {
      applyOps(msg.ops);
      sweepStale();
    },
    canvas(msg) {
      setBackground(msg.background || "white", true);
    },
    print(msg) {
      addConsole(msg.text, msg.stream);
    },
    error(msg) {
      renderError(msg);
      sweepStale();
    },
    end() {
      sweepStale();
    },
  };

  function onMessage(msg) {
    const handler = msg && HANDLERS[msg.t];
    if (handler) handler(msg);
  }

  // ---------- connection ----------

  function connect() {
    const source = new EventSource("/events");
    source.onopen = () => setConnected(true);
    source.onmessage = (e) => {
      setConnected(true);
      try {
        onMessage(JSON.parse(e.data));
      } catch (err) {
        console.error("Playground: bad message", err);
      }
    };
    source.onerror = () => {
      setConnected(false);
      if (source.readyState === EventSource.CLOSED) setTimeout(connect, 1000);
    };
  }

  // ---------- input ----------

  function sendEvent(event) {
    if (app.state === "running" && app.connected) post("/event", event);
  }

  function initInput() {
    const canvas = $("canvas");
    canvas.addEventListener("click", (e) => {
      const ctm = canvas.getScreenCTM();
      if (!ctm) return;
      const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
      if (Math.abs(pt.x) > HALF_W || Math.abs(pt.y) > HALF_H) return;
      const hit = e.target instanceof Element ? e.target.closest("[data-id]") : null;
      const target = hit && layers.shapes.contains(hit) ? Number(hit.dataset.id) : null;
      sendEvent({ t: "click", x: Math.round(pt.x), y: Math.round(-pt.y) || 0, target });
    });

    window.addEventListener("keydown", (e) => {
      if (e.ctrlKey || e.altKey || e.metaKey || e.isComposing) return;
      const tag = e.target instanceof Element ? e.target.tagName : "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (tag === "BUTTON" && (e.key === " " || e.key === "Enter")) return;
      const key = e.key === " " ? "Space" : e.key;
      if (key === "Space" || key.startsWith("Arrow")) e.preventDefault();
      sendEvent({ t: "key", key });
    });

    $("restart").addEventListener("click", (e) => {
      post("/restart");
      if (e.detail) e.currentTarget.blur();
    });
  }

  initConsole();
  initInput();
  connect();
})();
