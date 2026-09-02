/* Encore — evidence site.
 *
 * Everything here is ENHANCEMENT. The page is complete before this file runs:
 * the cliff chart, its table, every figure and all the prose are static markup
 * rendered by `encore web`. If Pyodide never loads, the hero animation
 * degrades to a short explanation and nothing else on the page is affected.
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

  /* ---------------- theme toggle ---------------- */
  (function theme() {
    var button = document.getElementById("theme-toggle");
    if (!button) return;
    button.addEventListener("click", function () {
      var root = document.documentElement;
      var current = root.dataset.theme;
      if (!current) {
        current = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
      }
      var next = current === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      try { localStorage.setItem("encore-theme", next); } catch (e) { /* private mode */ }
    });
  })();

  /* ---------------- cliff chart readout ---------------- */
  (function cliffReadout() {
    var readout = document.getElementById("cliff-readout");
    if (!readout) return;
    var bars = document.querySelectorAll(".cliff-chart rect[data-day]");
    if (!bars.length) return;

    var idle = readout.textContent;
    /* Built from DOM nodes rather than innerHTML. These values come from our own
       generated, escaped SVG, but the readout is the one place page text is
       assembled at runtime -- keeping it node-based means it can never become an
       injection point if the data source changes. */
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

  /* ---------------- the wall ---------------- */
  var stage = document.getElementById("wall-stage");
  if (!stage) return;

  var elAllowed = document.getElementById("wall-allowed");
  var elDenied = document.getElementById("wall-denied");
  var elEngine = document.getElementById("wall-engine");
  var elTier = document.getElementById("wall-tier");
  var elCaption = document.getElementById("wall-caption-text");
  var counts = { allowed: 0, denied: 0 };

  function setEngine(text) {
    if (!elEngine) return;
    elEngine.textContent = "engine ";
    var b = document.createElement("b");
    b.textContent = text;
    elEngine.appendChild(b);
  }

  function degrade(reason) {
    setEngine("unavailable");
    if (elTier) { elTier.textContent = "Tier A · unavailable"; elTier.classList.remove("is-live"); }
    if (elCaption) {
      elCaption.textContent =
        "The live wall could not start (" + reason + "). Everything below is " +
        "precomputed and unaffected — run it locally with `uv run pytest -q`.";
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
    // visible in the hero, not just the happy path.
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
    "                    'attempt': action.attempt_no, 'allowed': d.allowed, 'reason': d.reason})",
    "    return json.dumps(out)",
    "'ready'"
  ].join("\n");

  function makeChip(item) {
    var chip = document.createElement("div");
    chip.className = "wall-chip " + (item.allowed ? "is-allowed" : "is-denied");
    var id = document.createElement("span");
    id.textContent = item.customer + " @" + String(item.hour).padStart(2, "0") + ":00";
    var reason = document.createElement("span");
    reason.className = "chip-reason";
    reason.textContent = item.allowed ? "→ allowed" : "✕ " + item.reason;
    chip.appendChild(id);
    chip.appendChild(reason);
    return chip;
  }

  function tally(item) {
    if (item.allowed) { counts.allowed += 1; } else { counts.denied += 1; }
    if (elAllowed) elAllowed.textContent = counts.allowed;
    if (elDenied) elDenied.textContent = counts.denied;
  }

  /* Log mode: the same real decisions, without travel. Used when motion is
     reduced, and also when the renderer is not producing animation frames at
     all -- a backgrounded tab, an occluded window, or a headless browser. In
     those cases flying chips would sit invisible at their opening keyframe, so
     falling back here keeps the panel truthful rather than blank. */
  var logEl = null;

  function ensureLog() {
    if (logEl) return logEl;
    logEl = document.createElement("div");
    logEl.className = "wall-log";
    stage.appendChild(logEl);
    return logEl;
  }

  function pushLog(item) {
    var log = ensureLog();
    var chip = makeChip(item);
    chip.classList.add("is-logged");
    log.insertBefore(chip, log.firstChild);
    while (log.children.length > 7) { log.removeChild(log.lastChild); }
    tally(item);
  }

  /* A hard ceiling on chips in flight. onfinish is the normal cleanup path, but
     it never runs while the renderer is not compositing -- a backgrounded or
     occluded tab freezes Web Animations at currentTime 0 -- and without this the
     stage would accumulate DOM nodes for as long as the page is open. */
  var MAX_CHIPS = 14;

  function launch(item) {
    var live = stage.querySelectorAll(".wall-chip");
    for (var i = 0; i <= live.length - MAX_CHIPS; i++) {
      live[i].remove();
    }

    var chip = makeChip(item);
    var top = 34 + Math.random() * (stage.clientHeight - 78);
    chip.style.top = top + "px";
    stage.appendChild(chip);
    tally(item);

    var wallX = stage.clientWidth * 0.58;
    var frames = item.allowed
      ? [{ transform: "translateX(0)", opacity: 0 },
         { transform: "translateX(" + (wallX - 40) + "px)", opacity: 1, offset: 0.35 },
         { transform: "translateX(" + (stage.clientWidth + 200) + "px)", opacity: 0 }]
      : [{ transform: "translateX(0)", opacity: 0 },
         { transform: "translateX(" + (wallX - 190) + "px)", opacity: 1, offset: 0.45 },
         { transform: "translateX(" + (wallX - 172) + "px)", opacity: 1, offset: 0.55 },
         { transform: "translateX(-220px)", opacity: 0 }];

    var animation = chip.animate(frames, {
      duration: item.allowed ? 4200 : 4800,
      easing: item.allowed ? "cubic-bezier(.3,0,.7,1)" : "cubic-bezier(.2,.6,.3,1)"
    });
    animation.onfinish = function () { chip.remove(); };
  }

  function start(pyodide) {
    setEngine("wall.py live");
    if (elTier) { elTier.textContent = "Tier A · live in your browser"; elTier.classList.add("is-live"); }

    function pull(n) {
      return JSON.parse(pyodide.runPython("_batch(" + n + ")"));
    }

    var queue = [];
    function next() {
      if (!queue.length) queue = pull(24);
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
        if (useMotion) { launch(next()); } else { pushLog(next()); }
        setTimeout(tick, useMotion ? 620 + Math.random() * 420 : 900);
      })();
    }

    if (reduceMotion.matches) { run(false); return; }

    /* Probe: start a throwaway animation and see whether its clock actually
       advances. playState alone is not enough -- an animation reports
       "running" while frozen at currentTime 0 in a renderer that never
       composites, which is exactly the case that would leave the stage blank. */
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
