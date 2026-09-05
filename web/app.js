/* Encore — evidence site.
 *
 * Everything here is ENHANCEMENT. The page is complete before this file runs:
 * the cliff chart, its table, every stat card and all the prose are static
 * markup rendered by `encore web`. If Pyodide never loads, the page loses the
 * live panels and nothing else.
 *
 * Tier A (this file) runs the repository's real wall.py in the browser.
 * Tier B (the chart) is precomputed, because scikit-learn takes 61.7 s to
 * install in Pyodide and a judge opens this page once.
 */
(function () {
  "use strict";

  var PYODIDE_VERSION = "0.28.3";
  var PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v" + PYODIDE_VERSION + "/full/";
  // Order matters: each module is written before anything that imports it.
  var MODULES = ["__init__", "domain", "wall", "audit", "simulator", "policies", "scheduler"];

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  /* ---------------- cliff chart readout ---------------- */
  (function cliffReadout() {
    var readout = document.getElementById("cliff-readout");
    if (!readout) return;
    var bars = document.querySelectorAll(".cliff-chart rect[data-day]");
    if (!bars.length) return;

    var idle = readout.textContent;
    /* Built from DOM nodes rather than innerHTML. These values come from our own
       generated, escaped SVG, but the readout is the one place page text is
       assembled at runtime -- node-based means it can never become an injection
       point if the data source changes. */
    function bold(text) {
      var b = document.createElement("b");
      b.textContent = text;
      return b;
    }
    function show(bar) {
      var tried = Number(bar.getAttribute("data-tried"));
      var won = Number(bar.getAttribute("data-won"));
      var rate = tried ? Math.round((won / tried) * 100) : 0;
      readout.textContent = "";
      readout.append("day ", bold(bar.getAttribute("data-day")), " · ",
                     bar.getAttribute("data-policy"), " · ",
                     bold(String(tried)), " retries · ",
                     bold(String(won)), " recovered · " + rate + "%");
    }
    Array.prototype.forEach.call(bars, function (bar) {
      // focusable so the readout is reachable by keyboard, not mouse only
      bar.setAttribute("tabindex", "0");
      bar.addEventListener("mouseenter", function () { show(bar); });
      bar.addEventListener("focus", function () { show(bar); });
      bar.addEventListener("blur", function () { readout.textContent = idle; });
    });
    document.querySelector(".cliff-chart").addEventListener("mouseleave", function () {
      readout.textContent = idle;
    });
  })();

  /* ---------------- table of contents: mark the section in view ------------ */
  (function activeSection() {
    var links = document.querySelectorAll(".toc-links a[href^='#']");
    if (!links.length || !("IntersectionObserver" in window)) return;
    var byId = {};
    Array.prototype.forEach.call(links, function (a) {
      byId[a.getAttribute("href").slice(1)] = a;
    });

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        Array.prototype.forEach.call(links, function (a) { a.removeAttribute("aria-current"); });
        var link = byId[entry.target.id];
        if (link) link.setAttribute("aria-current", "true");
      });
    }, { rootMargin: "-25% 0px -65% 0px" });

    Object.keys(byId).forEach(function (id) {
      var section = document.getElementById(id);
      if (section) observer.observe(section);
    });
  })();

  /* ---------------- the wall ---------------- */
  var stage = document.getElementById("wall-stage");
  if (!stage) return;

  var elAllowed = document.getElementById("wall-allowed");
  var elDenied = document.getElementById("wall-denied");
  var elEngine = document.getElementById("wall-engine");
  var elTier = document.getElementById("wall-tier");
  var elCaption = document.getElementById("wall-caption-text");
  var elTicker = document.getElementById("ticker-track");
  var elTerminal = document.getElementById("terminal-body");
  var counts = { allowed: 0, denied: 0 };

  function setEngine(text) {
    if (!elEngine) return;
    elEngine.textContent = "engine ";
    var b = document.createElement("b");
    b.textContent = text;
    elEngine.appendChild(b);
  }

  function termLine(kind, tag, text) {
    var line = document.createElement("div");
    line.className = "terminal-line " + kind;
    var t = document.createElement("span");
    t.className = "tag";
    t.textContent = tag;
    var body = document.createElement("span");
    body.textContent = text;
    line.appendChild(t);
    line.appendChild(body);
    return line;
  }

  function pushTerminal(line) {
    if (!elTerminal) return;
    elTerminal.appendChild(line);
    while (elTerminal.children.length > 60) { elTerminal.removeChild(elTerminal.firstChild); }
    elTerminal.scrollTop = elTerminal.scrollHeight;
  }

  function degrade(reason) {
    setEngine("unavailable");
    if (elTier) elTier.textContent = "Wall · unavailable";
    if (elCaption) {
      elCaption.textContent =
        "The live wall could not start (" + reason + "). Every measured figure on this " +
        "page is precomputed and unaffected; run the wall locally with `uv run pytest -q`.";
    }
    if (elTerminal) {
      elTerminal.textContent = "";
      pushTerminal(termLine("is-fail", "[FAIL]", reason));
      pushTerminal(termLine("is-info", "[INFO]",
        "Tier B evidence below is static and complete without this panel."));
    }
    if (elTicker) {
      elTicker.textContent = "";
      var span = document.createElement("span");
      span.className = "ticker-empty";
      span.textContent = "Live wall unavailable — the measured results below are unaffected.";
      elTicker.appendChild(span);
    }
  }

  /* The decision stream is produced in Python by the real wall.decide(), never
     mocked in JavaScript. Reasons are whatever the wall actually returns, so a
     rule change in wall.py shows up here without touching this file. */
  var PY_STREAM = [
    "import json, random",
    "from encore.domain import ActionKind, DeclineCode, ProposedAction",
    "from encore.wall import SequenceState, WallConfig, decide",
    "_cfg = WallConfig()",
    "_rng = random.Random(20260902)",
    "_soft = [DeclineCode.INSUFFICIENT_FUNDS, DeclineCode.ISSUER_DOWN, DeclineCode.GATEWAY_TIMEOUT]",
    "_hard = [DeclineCode.MANDATE_REVOKED, DeclineCode.ACCOUNT_CLOSED, DeclineCode.RISK_DECLINED]",
    "def _batch(n):",
    "    out = []",
    "    for _ in range(n):",
    // A deliberately mixed population so the wall's whole precedence chain is
    // visible, not just the happy path.
    "        hard = _rng.random() < 0.14",
    "        killed = _rng.random() < 0.08",
    "        decline = _rng.choice(_hard if hard else _soft)",
    "        retries = _rng.choice([0, 0, 1, 1, 2, 3])",
    "        last = _rng.choice([None, None, 40, 60]) ",
    "        hour = _rng.randrange(0, 24 * 6)",
    "        state = SequenceState(decline, retries, 0, last, killed)",
    "        action = ProposedAction(ActionKind.RETRY, 'cust_%04d' % _rng.randrange(0, 9999),",
    "                                'cyc_09', _rng.choice([19900, 29900, 49900, 99900]),",
    "                                hour, retries + 1)",
    "        d = decide(action, state, _cfg)",
    "        out.append({'customer': action.customer_id, 'hour': action.execute_at_hour % 24,",
    "                    'attempt': action.attempt_no, 'decline': str(state.original_decline),",
    "                    'allowed': d.allowed, 'reason': d.reason})",
    "    return json.dumps(out)",
    "'ready'"
  ].join("\n");

  /* The ticker is a marquee over a SNAPSHOT, not over a live-mutating list.
     A seamless loop needs the track to hold two identical halves so -50% lands
     exactly one half along; appending decisions into a scrolling track breaks
     that invariant and makes the strip stutter and gap. So decisions accumulate
     in `recent`, and the track is rebuilt from it on a slow cadence. */
  var recent = [];
  var tickerTimer = null;

  function tickerItem(item) {
    var span = document.createElement("span");
    span.className = "ticker-item";
    span.append(label(item) + " ");
    var b = document.createElement("b");
    b.className = item.allowed ? "is-allowed" : "is-denied";
    b.textContent = item.allowed ? "[ALLOWED]" : "[DENIED] " + item.reason;
    span.appendChild(b);
    return span;
  }

  function rebuildTicker() {
    if (!elTicker || !recent.length) return;
    elTicker.textContent = "";
    for (var half = 0; half < 2; half++) {
      var group = document.createElement("div");
      group.className = "ticker-half";
      recent.forEach(function (item) { group.appendChild(tickerItem(item)); });
      elTicker.appendChild(group);
    }
  }

  function scheduleTickerRebuild() {
    // Rebuilding restarts the CSS animation, so once the strip is populated it
    // is deliberately infrequent -- often enough to stay live, rarely enough
    // not to visibly reset the scroll. While the buffer is still filling there
    // is nothing to reset, so it refreshes quickly instead of leaving an empty
    // band for twelve seconds after load.
    if (tickerTimer) return;
    tickerTimer = setTimeout(function () {
      tickerTimer = null;
      rebuildTicker();
    }, recent.length < 10 ? 700 : 12000);
  }

  function label(item) {
    return item.customer + " @" + String(item.hour).padStart(2, "0") + ":00 #" + item.attempt;
  }

  function makeChip(item) {
    var chip = document.createElement("div");
    chip.className = "wall-chip " + (item.allowed ? "is-allowed" : "is-denied");
    var id = document.createElement("span");
    id.textContent = label(item);
    var reason = document.createElement("span");
    reason.className = "chip-reason";
    reason.textContent = item.allowed ? "ALLOWED" : "DENIED · " + item.reason;
    chip.appendChild(id);
    chip.appendChild(reason);
    return chip;
  }

  /* One decision fans out to three surfaces: the ticker, the terminal log and
     the counters. Only the stage animation is optional. */
  function record(item) {
    if (item.allowed) { counts.allowed += 1; } else { counts.denied += 1; }
    if (elAllowed) elAllowed.textContent = counts.allowed;
    if (elDenied) elDenied.textContent = counts.denied;

    pushTerminal(item.allowed
      ? termLine("is-ok", "[OK]", label(item) + " allowed — " + item.decline)
      : termLine("is-fail", "[DENY]", label(item) + " " + item.reason));

    recent.push(item);
    while (recent.length > 12) { recent.shift(); }
    scheduleTickerRebuild();
  }

  /* Log mode: the same real decisions, without travel. Used when motion is
     reduced, and when the renderer produces no animation frames at all -- a
     backgrounded tab, an occluded window, a headless browser. In those cases
     flying chips would sit invisible at their opening keyframe, so falling back
     here keeps the panel truthful rather than blank. */
  var logEl = null;
  function pushStageLog(item) {
    if (!logEl) {
      logEl = document.createElement("div");
      logEl.className = "wall-log";
      stage.appendChild(logEl);
    }
    var chip = makeChip(item);
    chip.classList.add("is-logged");
    logEl.insertBefore(chip, logEl.firstChild);
    while (logEl.children.length > 6) { logEl.removeChild(logEl.lastChild); }
  }

  /* A hard ceiling on chips in flight. onfinish is the normal cleanup path, but
     it never runs while the renderer is not compositing, and without this the
     stage would accumulate DOM nodes for as long as the page is open. */
  var MAX_CHIPS = 12;

  function launch(item) {
    var live = stage.querySelectorAll(".wall-chip");
    for (var i = 0; i <= live.length - MAX_CHIPS; i++) { live[i].remove(); }

    var chip = makeChip(item);
    chip.style.top = (84 + Math.random() * (stage.clientHeight - 150)) + "px";
    stage.appendChild(chip);

    var wallX = stage.clientWidth * 0.58;
    var frames = item.allowed
      ? [{ transform: "translateX(0)", opacity: 0 },
         { transform: "translateX(" + (wallX - 40) + "px)", opacity: 1, offset: 0.35 },
         { transform: "translateX(" + (stage.clientWidth + 240) + "px)", opacity: 0 }]
      : [{ transform: "translateX(0)", opacity: 0 },
         { transform: "translateX(" + (wallX - 230) + "px)", opacity: 1, offset: 0.45 },
         { transform: "translateX(" + (wallX - 212) + "px)", opacity: 1, offset: 0.55 },
         { transform: "translateX(-260px)", opacity: 0 }];

    var animation = chip.animate(frames, {
      duration: item.allowed ? 4200 : 4800,
      easing: item.allowed ? "cubic-bezier(.3,0,.7,1)" : "cubic-bezier(.2,.6,.3,1)"
    });
    animation.onfinish = function () { chip.remove(); };
  }

  function start(pyodide) {
    setEngine("wall.py live");
    if (elTier) elTier.textContent = "Wall · live in this tab";
    if (elTerminal) elTerminal.textContent = "";
    pushTerminal(termLine("is-ok", "[OK]", "Pyodide " + PYODIDE_VERSION + " ready"));
    pushTerminal(termLine("is-ok", "[OK]", "Mounted " + MODULES.length + " modules from encore/"));
    pushTerminal(termLine("is-info", "[INFO]",
      "WallConfig: 3 retries, 24h cooldown, 22:00-07:00 execution window"));
    if (elTicker) elTicker.textContent = "";
    setTimeout(rebuildTicker, 1200);

    var queue = [];
    function next() {
      if (!queue.length) queue = JSON.parse(pyodide.runPython("_batch(24)"));
      return queue.shift();
    }

    function run(useMotion) {
      if (elCaption && !useMotion) {
        elCaption.textContent = reduceMotion.matches
          ? "Motion is reduced, so decisions are listed instead of animated. Each line is a real wall.decide() result."
          : "Listing decisions instead of animating them — this renderer is not producing animation frames. Each line is a real wall.decide() result.";
      }
      (function tick() {
        if (document.hidden) { setTimeout(tick, 900); return; }
        var item = next();
        record(item);
        if (useMotion) { launch(item); } else { pushStageLog(item); }
        setTimeout(tick, useMotion ? 620 + Math.random() * 420 : 900);
      })();
    }

    if (reduceMotion.matches) { run(false); return; }

    /* Probe: start a throwaway animation and see whether its clock actually
       advances. playState alone is not enough -- an animation reports "running"
       while frozen at currentTime 0 in a renderer that never composites, which
       is exactly the case that would leave the stage blank. */
    var probe = document.createElement("div");
    probe.style.cssText = "position:absolute;width:1px;height:1px;opacity:0;pointer-events:none";
    stage.appendChild(probe);
    var probeAnim = probe.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 1000 });
    setTimeout(function () {
      var ticking = Number(probeAnim.currentTime) > 0;
      probeAnim.cancel();
      probe.remove();
      run(ticking);
    }, 220);
  }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = function () { reject(new Error("could not load " + src)); };
      document.head.appendChild(s);
    });
  }

  async function boot() {
    setEngine("loading Python…");
    await loadScript(PYODIDE_URL + "pyodide.js");
    var pyodide = await window.loadPyodide({ indexURL: PYODIDE_URL });

    setEngine("mounting wall.py…");
    // Fetched over HTTP from web/py/ and written into the Pyodide filesystem,
    // then imported normally: no wheel, no micropip, no requires-python
    // negotiation. These are byte-identical copies of src/encore/*.py.
    pyodide.FS.mkdirTree("/home/pyodide/encore");
    var sources = await Promise.all(MODULES.map(function (name) {
      return fetch("py/" + name + ".py").then(function (r) {
        if (!r.ok) throw new Error("py/" + name + ".py returned " + r.status);
        return r.text();
      });
    }));
    MODULES.forEach(function (name, i) {
      pyodide.FS.writeFile("/home/pyodide/encore/" + name + ".py", sources[i]);
    });
    pyodide.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
    pyodide.runPython(PY_STREAM);
    start(pyodide);
  }

  boot().catch(function (err) {
    // Named, not opaque: a 404 on one module is a real deploy risk, because the
    // page depends on web/py/ being published alongside it.
    degrade(err && err.message ? err.message : "unknown error");
  });
})();
