/* Course Player runtime.
   Reveals gated content, runs knowledge checks, and reports to the LMS through a
   pluggable runtime that auto-detects:
     - SCORM 1.2 / 2004  (window.API / API_1484_11)
     - cmi5 / xAPI       (launched with endpoint+fetch+registration+activityId params)
     - standalone        (no LMS — preview)
   Every adapter exposes the same surface { init()->Promise<{resumed,finished}>, save,
   complete, quit, isFinished } so the course-flow code below is runtime-agnostic.
   Completion fires when every gate is passed, every KC attempted, every required media
   played, every required card opened — or, for a no-interaction lesson, when the end is
   reached. Graded lessons additionally report a score. */
(function () {
  "use strict";

  /* ===================== suspend_data sizing (SCORM 1.2) =====================
     SCORM 1.2 cmi.suspend_data is CMIString4096 — a 4096-character SPM, which
     LMSs commonly enforce in BYTES. JSON.stringify(state).length counts UTF-16
     code units, so a sort-heavy course can blow past 4096 bytes, the LMS
     silently truncates mid-string, and the next launch's JSON.parse throws ->
     ALL progress is lost. So we measure true UTF-8 bytes and degrade through a
     ladder, each rung still VALID JSON, never a truncated blob. */
  var SUSPEND_MAX_1_2 = 4096;
  var SUSPEND_BUDGET  = SUSPEND_MAX_1_2 - 96;   // margin for LMS-side quoting/overhead
  function utf8len(str){ var n=0,c; for (var i=0;i<str.length;i++){ c=str.charCodeAt(i);
    if (c<0x80) n+=1; else if (c<0x800) n+=2; else if (c>=0xD800 && c<=0xDBFF){ n+=4; i++; } else n+=3; } return n; }
  function packSorts(s){ if(!s) return s; var o={}; Object.keys(s).forEach(function(k){ o[k]={ok:(s[k]&&s[k].ok)?1:0}; }); return o; }   // drop per-item picks
  function packKcs(k){ if(!k) return k; var o={}; Object.keys(k).forEach(function(i){ o[i]={ok:(k[i]&&k[i].ok)?1:0}; }); return o; }     // drop chosen option, keep correctness
  // M12 — drop per-item picks/inputs from a partial-credit block's state, keep ok + got/max
  function packSeen(x){ if(!x) return x; var o={}; Object.keys(x).forEach(function(k){ var v=x[k]||{}; o[k]={ok:v.ok?1:0,got:v.got,max:v.max}; }); return o; }
  // C5 — question-bank randomization (pure + exported so node --test pins determinism).
  // mulberry32 seeded PRNG: a FRESH draw seeds from Date.now(), but the drawn indices +
  // option orders are what get PERSISTED (not the seed), so resume never re-runs the PRNG.
  function makeRng(seed){ var a = seed >>> 0; return function(){
    a = (a + 0x6D2B79F5) | 0;
    var t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
  // Fisher-Yates permutation of [0..n-1] using rng(); returns the new order.
  function seededShuffle(n, rng){ var a = []; for (var i=0;i<n;i++) a.push(i);
    for (var i=n-1;i>0;i--){ var j = Math.floor(rng()*(i+1)); var t=a[i]; a[i]=a[j]; a[j]=t; } return a; }
  // Draw n of poolSize items: the first n of a seeded shuffle, returned SORTED so the drawn
  // subset keeps authored order (option-shuffle supplies per-question variety). n>=pool → all.
  function drawPool(poolSize, n, rng){ var perm = seededShuffle(poolSize, rng);
    return perm.slice(0, Math.min(n, poolSize)).sort(function(a,b){ return a-b; }); }
  // Pack a bank's per-bank state: KEEP the drawn `pick` (resume MUST show the same questions
  // or the graded set changes) but drop the cosmetic option-shuffle order under byte pressure.
  function packBank(bk){ if(!bk) return bk; var o={}; Object.keys(bk).forEach(function(k){ var v=bk[k]||{}; o[k]={pick:v.pick}; }); return o; }
  // speedStreak — GRADED score: answered N of M correctly (identical shape to the other
  // game blocks). `marks` = [bool] one per answered round. Pure + exported.
  function ssScore(marks){ var got=0; for (var k=0;k<marks.length;k++){ if (marks[k]) got++; }
    return { got: got, max: marks.length, ok: marks.length>0 && got===marks.length }; }
  // speedStreak — COSMETIC combo points for ONE answer (never part of the grade). A correct
  // answer scores a base value × a streak-so-far multiplier × an optional speed bonus
  // (fraction of the per-question time still on the clock, 0 when untimed); a wrong answer
  // scores 0 and breaks the streak. Pure + exported so node --test pins the math without a DOM.
  var SS_BASE = 100;
  function ssCombo(correct, streakBefore, timeFrac){
    if (!correct) return 0;
    var mult = 1 + 0.5 * (streakBefore > 0 ? streakBefore : 0);
    var bonus = 1 + (timeFrac > 0 ? timeFrac : 0);
    return Math.round(SS_BASE * mult * bonus);
  }
  // Confetti celebration (gamification #6) — decide whether a `reason` may fire given the
  // course config + whether it already fired. One-shot triggers (pass/complete) fire once;
  // a level-up recurs (each tier crossing is genuine), so it takes no once-guard. Pure +
  // exported so node --test pins the trigger logic (the canvas burst itself is DOM/rAF-only).
  function celebrateAllowed(cfg, reason, fired){
    if (!cfg) return false;
    if (reason === "pass") return !!cfg.pass && !fired;
    if (reason === "complete") return !!cfg.complete && !fired;
    if (reason === "level") return !!cfg.level;
    return false;
  }
  // Return the largest representation of `state` that fits the 1.2 byte budget.
  function fitSuspend(state){
    var rungs = [
      state,                                                                              // full (incl. loc)
      { g:state.g, k:state.k, m:state.m, o:state.o, s:state.s, mt:state.mt, sq:state.sq, fl:state.fl, dd:state.dd, ws:state.ws, cw:state.cw, gs:state.gs, qb:state.qb, ss:state.ss, rf:state.rf, b:state.b },             // drop cosmetic resume pointer
      { g:state.g, k:state.k, m:state.m, o:state.o, s:packSorts(state.s), mt:packSeen(state.mt), sq:packSeen(state.sq), fl:packSeen(state.fl), dd:packSeen(state.dd), ws:packSeen(state.ws), cw:packSeen(state.cw), gs:packSeen(state.gs), qb:packSeen(state.qb), ss:packSeen(state.ss), rf:packSeen(state.rf), b:packBank(state.b) },               // drop sort/match/seq/fill/drag/wordsearch/crossword/gameshow/quizboard/speedstreak picks + reflection text + bank option order
      { g:state.g, k:packKcs(state.k), m:state.m, o:state.o, s:packSorts(state.s), mt:packSeen(state.mt), sq:packSeen(state.sq), fl:packSeen(state.fl), dd:packSeen(state.dd), ws:packSeen(state.ws), cw:packSeen(state.cw), gs:packSeen(state.gs), qb:packSeen(state.qb), ss:packSeen(state.ss), rf:packSeen(state.rf), b:packBank(state.b) }        // drop KC option detail (bank `pick` still kept — resume needs it)
    ];
    var last = "";
    for (var i=0;i<rungs.length;i++){ last = JSON.stringify(rungs[i]); if (utf8len(last) <= SUSPEND_BUDGET) return last; }
    return last;   // smallest rung; still valid JSON even if a pathological course exceeds the budget
  }

  /* ============================ KC scoring (pure) ============================
     Extracted so the multi-select/retry/grading decisions are unit-testable in
     node without a DOM (tests/test_player.js) — the browser handlers below call
     these too, so a test guards the live logic, not a copy. */
  // multi-select is correct iff EVERY option's correctness matches whether it was
  // selected (all the right ones, none of the wrong ones). `corrects[oi]` = true if
  // option oi is a correct answer; `sel` = the list of selected option indexes.
  function multiAllCorrect(corrects, sel){
    return corrects.every(function(c,oi){ return c === (sel.indexOf(oi) >= 0); });
  }
  // a KC answer is terminal (locks) when it's correct, the course is one-shot
  // (maxTries falsy), or the learner has used their last attempt; else it retries.
  function kcLocks(ok, tries, maxTries){ return ok || !maxTries || tries >= maxTries; }
  // graded score as a 0..100 integer percent (0 when there are no KCs).
  function scorePct(correct, total){ return total ? Math.round(correct/total*100) : 0; }
  // parse a packed multi-select rung's `opt` ("0,2") back to option indexes [0,2].
  // A degraded/packed rung (no opt) yields [] — the rung resumes as a bare correct.
  function parseMultiSel(optStr){
    return String(optStr).split(",").filter(function(x){ return x !== ""; }).map(Number);
  }
  // Branching scenario routing (M14): resolve a choice's `data-goto` value to a scene
  // index within `sceneIds`. Returns -1 when the target is empty or unknown — the
  // caller treats that as a terminal/ending choice (no onward scene). Pure + exported
  // so `node --test` can pin the routing without a DOM.
  function resolveScene(gotoVal, sceneIds){
    if (!gotoVal) return -1;
    return (sceneIds || []).indexOf(gotoVal);
  }
  // M13 — aggregate a graded course's KC outcomes into an OVERALL score plus per-section
  // (objective) SUBSCORES. Pure + exported so node tests pin the scoring/gating math
  // without a DOM (the live gradedScore() below feeds it the DOM-derived items).
  //   items:      [{obj:<string|null>, ok:<bool>, got?:<num>, max?:<num>}]  one per graded block
  //   passMark:   overall pass threshold (0..100)
  //   objectives: [{id,name,pass}]  graded sections (pass may be null = report, no gate)
  // When objectives is non-empty, ONLY items carrying an obj are summative (counted) — inline
  // ones are formative; with NO objectives every item counts (pre-M13 graded courses unchanged).
  // An item may carry PARTIAL credit: got/max points (M12 matching/sequencing/fill-in-the-blank);
  // a boolean KC is 1/1. Overall passes iff raw >= passMark AND every threshold'd objective is met.
  function aggregateScore(items, passMark, objectives){
    objectives = objectives || []; items = items || [];
    var hasObj = objectives.length > 0;
    var per = {};
    objectives.forEach(function(o){ per[o.id] = { c:0, t:0 }; });
    var oc = 0, ot = 0;
    items.forEach(function(it){
      var summative = hasObj ? !!it.obj : true;
      if (!summative) return;
      // M12 — fractional partial credit {got,max} when present; a boolean KC is got/max = ok/1.
      var mx = (it.max != null) ? it.max : 1, gt = (it.got != null) ? it.got : (it.ok ? 1 : 0);
      ot += mx; oc += gt;
      if (it.obj && per[it.obj]) { per[it.obj].t += mx; per[it.obj].c += gt; }
    });
    var raw = scorePct(oc, ot);
    var objs = objectives.map(function(o){
      var pb = per[o.id] || { c:0, t:0 };
      var r = scorePct(pb.c, pb.t);
      var pass = (o.pass === null || o.pass === undefined) ? null : o.pass;
      return { id:o.id, name:o.name, raw:r, min:0, max:100, scaled:(r/100).toFixed(2),
               pass:pass, passed:(pass === null || r >= pass) };
    });
    var allObjPass = objs.every(function(o){ return o.passed; });
    return { raw:raw, min:0, max:100, scaled:(raw/100).toFixed(2),
             passed:(raw >= passMark && allObjPass), objectives:objs };
  }
  /* ===================== points/XP overlay (gamification #3) =====================
     A PURELY MOTIVATIONAL layer: it never touches the graded score, the completion
     gate, or the LMS score — it re-derives an XP total + a level TIER from the SAME
     block-state the player already persists in suspend_data (so it survives resume
     for free, no extra state key). Each scorable block earns points weighted by a
     category (check / question / game); partial-credit blocks award pro-rata. Pure +
     exported so node --test pins the math without a DOM. */
  var XP_DEFAULT_W = { check: 10, question: 15, game: 20 };
  var XP_DEFAULT_TIERS = [["Novice", 0.0], ["Proficient", 0.5], ["Skilled", 0.8], ["Expert", 1.0]];
  // Map a block KIND to its XP weight category. KCs + categorize = a "check"; the M12
  // question types = "question"; the word games = "game" (harder → worth more).
  function xpCat(kind){
    if (kind === "kc" || kind === "sort") return "check";
    if (kind === "ws" || kind === "cw" || kind === "gs" || kind === "qb" || kind === "ss") return "game";
    return "question";   // mt, sq, fl, dd
  }
  function xpWeight(kind, weights){ weights = weights || XP_DEFAULT_W; return weights[xpCat(kind)] || 0; }
  // Points earned for ONE resolved block. Partial-credit blocks carry {got,max} →
  // pro-rata; a boolean block ({ok}) is all-or-nothing. A missing result earns 0.
  function xpForResult(kind, res, weights){
    if (!res) return 0;
    var w = xpWeight(kind, weights);
    if (typeof res.got === "number" && typeof res.max === "number" && res.max > 0)
      return Math.round(w * res.got / res.max);
    return res.ok ? w : 0;
  }
  // Sum earned + total-earnable XP across the scorable blocks. `specs` = one entry per
  // block kind: {kind, seen:<the *Seen map>, count:<node count>}. Earnable = weight ×
  // count; earned = the resolved results. Pure + exported.
  function xpTotals(specs, weights){
    specs = specs || []; var earned = 0, possible = 0;
    specs.forEach(function(sp){
      var w = xpWeight(sp.kind, weights);
      possible += w * (sp.count || 0);
      var sm = sp.seen || {};
      Object.keys(sm).forEach(function(k){ earned += xpForResult(sp.kind, sm[k], weights); });
    });
    return { earned: earned, possible: possible };
  }
  // Resolve a completion FRACTION (earned/earnable, 0..1) to a level tier. Returns the
  // highest tier whose threshold the fraction has reached. Pure + exported.
  function tierFor(frac, tiers){
    tiers = (tiers && tiers.length) ? tiers : XP_DEFAULT_TIERS;
    var name = tiers[0][0], index = 0;
    for (var i = 0; i < tiers.length; i++){ if (frac + 1e-9 >= tiers[i][1]){ name = tiers[i][0]; index = i; } }
    return { name: name, index: index };
  }
  // M12 — score an ordered set of picks against their correct answers, elementwise.
  // A blank/null pick is always wrong. Returns PARTIAL credit {got, max, ok}. Pure +
  // exported for node tests; matching and sequencing both use it.
  function tallyExact(picks, answers){
    picks = picks || []; answers = answers || [];
    var max = answers.length, got = 0;
    for (var k=0;k<max;k++){ if (picks[k] != null && picks[k] !== "" && picks[k] === answers[k]) got++; }
    return { got: got, max: max, ok: max > 0 && got === max };
  }
  // M12 fill-in-the-blank — LENIENT normalization: trim, collapse inner whitespace, lowercase.
  function normFill(s){ return String(s == null ? "" : s).trim().replace(/\s+/g, " ").toLowerCase(); }
  // Score text-entry blanks against a per-blank accept-list. A blank input is wrong; a
  // non-empty input is right iff its normalized form is in the normalized accept-list.
  // PARTIAL credit {got, max, ok}. Pure + exported.
  function fillScore(inputs, answerSets){
    inputs = inputs || []; answerSets = answerSets || [];
    var max = answerSets.length, got = 0;
    for (var k=0;k<max;k++){
      var got_in = normFill(inputs[k]);
      if (got_in === "") continue;
      var accept = (answerSets[k] || []).map(normFill);
      if (accept.indexOf(got_in) >= 0) got++;
    }
    return { got: got, max: max, ok: max > 0 && got === max };
  }

  var HAS_DOM = typeof window !== "undefined" && typeof document !== "undefined";

  /* ============================ SCORM 1.2 / 2004 adapter ============================ */
  function makeScorm() {
    var api = null, ver = null, started = 0, finished = false, terminated = false, lastState = null;
    function find(win) {
      var n = 0;
      while (win && n++ < 12) {
        if (win.API_1484_11) { ver = "2004"; return win.API_1484_11; }
        if (win.API)        { ver = "1.2";  return win.API; }
        if (win.parent && win.parent !== win) { win = win.parent; continue; }
        break;
      }
      return null;
    }
    function locate() { api = find(window); if (!api && window.opener) api = find(window.opener); return api; }
    var K = {
      status:  function(){ return ver==="2004" ? "cmi.completion_status" : "cmi.core.lesson_status"; },
      suspend: function(){ return "cmi.suspend_data"; },
      exit:    function(){ return ver==="2004" ? "cmi.exit" : "cmi.core.exit"; },
      time:    function(){ return ver==="2004" ? "cmi.session_time" : "cmi.core.session_time"; },
      sRaw:    function(){ return ver==="2004" ? "cmi.score.raw" : "cmi.core.score.raw"; },
      sMin:    function(){ return ver==="2004" ? "cmi.score.min" : "cmi.core.score.min"; },
      sMax:    function(){ return ver==="2004" ? "cmi.score.max" : "cmi.core.score.max"; }
    };
    function lastErr(){ try { return ver==="2004" ? api.GetLastError() : api.LMSGetLastError(); } catch(e){ return "?"; } }
    function get(k){ try { return (ver==="2004" ? api.GetValue(k) : api.LMSGetValue(k)) || ""; } catch(e){ return ""; } }
    function set(k,v){ try { var ok = ver==="2004" ? api.SetValue(k,String(v)) : api.LMSSetValue(k,String(v));
      var e = lastErr(); if (e && e!=="0") console.warn("[player] SetValue rejected", k, "=", v, "err", e); return ok;
    } catch(e){ console.warn("[player] SetValue threw", k, e); return false; } }
    function commit(){ try { ver==="2004" ? api.Commit("") : api.LMSCommit(""); } catch(e){} }
    function fmtTime(ms){ var s=Math.max(0,Math.round(ms/1000)), h=Math.floor(s/3600), m=Math.floor((s%3600)/60), sec=s%60;
      if (ver==="2004") return "PT"+(h?h+"H":"")+(m?m+"M":"")+sec+"S";
      function p(n){return (n<10?"0":"")+n;} return p(h)+":"+p(m)+":"+p(sec)+".00"; }

    return {
      kind: function(){ return ver ? "scorm "+ver : "scorm"; },
      init: function () {
        if (!locate()) { console.info("[player] no SCORM LMS"); return Promise.resolve(null); }
        started = Date.now();
        try { ver==="2004" ? api.Initialize("") : api.LMSInitialize(""); } catch(e){ console.warn("[player] init", e); }
        var st = get(K.status()).toLowerCase();
        finished = (st==="completed" || st==="passed");
        if (!finished && st!=="incomplete") set(K.status(), "incomplete");
        commit();
        var resumed = null; try { resumed = JSON.parse(get(K.suspend())||"null"); } catch(e){}
        return Promise.resolve({ resumed: resumed, finished: finished });
      },
      isFinished: function(){ return finished; },
      save: function (state) {
        lastState = state;
        // 2004 suspend_data SPM is 64000 — large enough to keep full state; 1.2 must fit ~4096 bytes.
        var s = ver==="2004" ? JSON.stringify(state) : fitSuspend(state);
        set(K.suspend(), s); commit();
      },
      complete: function (score) {
        if (score) { set(K.sRaw(),score.raw); set(K.sMin(),score.min); set(K.sMax(),score.max);
          if (ver==="2004") set("cmi.score.scaled",score.scaled);
          if (ver==="2004"){ set("cmi.completion_status","completed"); set("cmi.success_status", score.passed?"passed":"failed"); }
          else set("cmi.core.lesson_status", score.passed?"passed":"failed");
          // M13 — per-section subscores as SCORM objectives (2004: scaled + success_status; 1.2: raw + status)
          var objs = score.objectives || [];
          for (var oi=0; oi<objs.length; oi++){ var o=objs[oi], op="cmi.objectives."+oi+".";
            set(op+"id", o.id); set(op+"score.raw", o.raw); set(op+"score.min", o.min); set(op+"score.max", o.max);
            if (ver==="2004"){ set(op+"score.scaled", o.scaled); set(op+"success_status", o.passed?"passed":"failed"); set(op+"completion_status","completed"); }
            else set(op+"status", o.passed?"passed":"failed"); }
        } else { if (ver==="2004"){ set("cmi.completion_status","completed"); set("cmi.success_status","passed"); }
          else set("cmi.core.lesson_status","completed"); }
        finished = true; commit();
      },
      interaction: function (n, id, learner, correct) {
        var p = "cmi.interactions."+n+".";
        set(p+"id", id||("kc"+n)); set(p+"type","choice");
        if (ver==="2004"){ set(p+"learner_response",learner); set(p+"result",correct?"correct":"incorrect"); }
        else { set(p+"student_response",learner); set(p+"result",correct?"correct":"wrong"); }
      },
      quit: function () {
        if (!api || terminated) return; terminated = true;
        try { set(K.time(), fmtTime(Date.now()-started));
          set(K.exit(), finished ? (ver==="2004"?"normal":"") : "suspend"); commit();
          ver==="2004" ? api.Terminate("") : api.LMSFinish(""); } catch(e){ console.warn("[player] quit", e); }
      }
    };
  }

  /* ============================ cmi5 / xAPI adapter ============================ */
  var CMI5 = {
    CAT:   "https://w3id.org/xapi/cmi5/context/categories/cmi5",
    MOVEON:"https://w3id.org/xapi/cmi5/context/categories/moveon",
    SID:   "https://w3id.org/xapi/cmi5/context/extensions/sessionid",
    V: { init:"http://adlnet.gov/expapi/verbs/initialized", completed:"http://adlnet.gov/expapi/verbs/completed",
         passed:"http://adlnet.gov/expapi/verbs/passed", failed:"http://adlnet.gov/expapi/verbs/failed",
         terminated:"http://adlnet.gov/expapi/verbs/terminated" },
    EXT_SUBSCORES:"https://course-builder.local/xapi/extensions/subscores"  // M13 per-section subscores
  };
  function cmi5Params() {
    var q = {}; (location.search.replace(/^\?/,"").split("&")).forEach(function(p){
      if (!p) return; var i = p.indexOf("="); var k = decodeURIComponent(p.slice(0,i)); var v = decodeURIComponent(p.slice(i+1)); q[k]=v; });
    if (q.endpoint && q.fetch && q.registration && q.activityId) return q;
    return null;
  }
  function makeCmi5(q) {
    var endpoint = q.endpoint.replace(/\/?$/,"/"), fetchUrl = q.fetch, reg = q.registration, activityId = q.activityId;
    var actor; try { actor = JSON.parse(q.actor); } catch(e){ actor = { account:{ name:q.actor||"learner" } }; }
    var token = "", ctxT = {}, mode = "Normal", mastery = null, returnURL = null;
    var sid = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : (Date.now()+"-"+Math.random().toString(16).slice(2));
    var started = 0, finished = false, terminated = false, completedSent = false, lastState = null;

    function isoDur(ms){ var s=Math.max(0,Math.round(ms/1000)),h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=s%60;
      return "PT"+(h?h+"H":"")+(m?m+"M":"")+sec+"S"; }
    // xAPI Alternate (CORS) Request Syntax: cmi5 content is cross-origin to the LRS, and a
    // normal POST with Authorization/X-Experience-API-Version headers triggers a CORS preflight
    // most LRS endpoints reject — so every call is a form-encoded POST with ?method=<VERB>,
    // and headers/query-params/body ride as form fields. keepalive lets it survive unload.
    function form(p){ var o=[]; Object.keys(p).forEach(function(k){ if (p[k]!=null) o.push(encodeURIComponent(k)+"="+encodeURIComponent(p[k])); }); return o.join("&"); }
    function lrs(method, path, params, content){
      if (!token) return Promise.resolve();   // no valid auth — don't fire malformed (Basic ) requests
      var f = {}; if (params) Object.keys(params).forEach(function(k){ f[k]=params[k]; });
      f.Authorization = token; f["X-Experience-API-Version"] = "1.0.3";
      if (content != null) { f["Content-Type"] = "application/json"; f.content = JSON.stringify(content); }
      return fetch(endpoint + path + "?method=" + method, { method:"POST",
        headers:{ "Content-Type":"application/x-www-form-urlencoded" }, body: form(f), keepalive:true })
        .catch(function(e){ console.warn("[player] LRS " + method + " " + path, e); });
    }
    function stateParams(id){ return { stateId:id, activityId:activityId, agent:JSON.stringify(actor), registration:reg }; }
    function ctx(moveon){ var c = JSON.parse(JSON.stringify(ctxT||{})); c.registration = reg;
      c.contextActivities = c.contextActivities || {};
      var cats = (c.contextActivities.category||[]).slice(); cats.push({id:CMI5.CAT}); if (moveon) cats.push({id:CMI5.MOVEON});
      c.contextActivities.category = cats; c.extensions = c.extensions || {}; c.extensions[CMI5.SID] = sid; return c; }
    function stmt(verb, disp, result, moveon){ var s = { actor:actor, verb:{id:verb, display:{"en-US":disp}},
      object:{ id:activityId, objectType:"Activity" }, context:ctx(moveon), timestamp:new Date().toISOString() };
      if (result) s.result = result; return s; }
    function sendStmt(s){ return lrs("POST", "statements", null, s); }

    return {
      kind: function(){ return "cmi5"; },
      init: function () {
        started = Date.now();
        return fetch(fetchUrl, { method:"POST" }).then(function(r){ return r.json(); }).then(function(j){
          var t = j && (j["auth-token"] || j.token);
          if (!t) {   // single-use token already spent (relaunch of a stale session) or an error response
            console.error("[player] cmi5 fetch returned no auth-token — relaunch with a FRESH registration. Response:", j);
            throw new Error("cmi5: no auth-token");
          }
          token = /^(Basic|Bearer)\s/i.test(t) ? t : ("Basic "+t);          // SCORM Cloud & most LRS: "Basic <token>"
          return lrs("GET", "activities/state", stateParams("LMS.LaunchData"));
        }).then(function(r){ return r && r.ok ? r.json() : {}; }).then(function(ld){
          ctxT = ld.contextTemplate || {}; mode = ld.launchMode || "Normal";
          mastery = (typeof ld.masteryScore==="number") ? ld.masteryScore : null; returnURL = ld.returnURL || null;
          return lrs("GET", "activities/state", stateParams("course.progress"));
        }).then(function(r){ return r && r.ok ? r.json().catch(function(){return null;}) : null; }).then(function(prog){
          finished = !!(prog && prog.done); lastState = prog && prog.state || null;
          return sendStmt(stmt(CMI5.V.init, "initialized")).then(function(){ return { resumed:lastState, finished:finished, mastery:mastery }; });
        }).catch(function(e){ console.warn("[player] cmi5 init failed", e); return { resumed:null, finished:false }; });
      },
      isFinished: function(){ return finished; },
      returnURL: function(){ return returnURL; },
      save: function (state) { lastState = state;
        lrs("PUT", "activities/state", stateParams("course.progress"), { state:state, done:finished }); },
      complete: function (score) {
        if (mode !== "Normal" || completedSent) return; completedSent = true; finished = true;
        var dur = isoDur(Date.now()-started);
        sendStmt(stmt(CMI5.V.completed, "completed", { completion:true, duration:dur }, true));
        if (score) { var sc = { scaled:Number(score.scaled), raw:score.raw, min:score.min, max:score.max };
          var res = { success:!!score.passed, score:sc, duration:dur };
          // M13 — per-section subscores ride as a result extension (cmi5 has no cmi.objectives)
          var objs = score.objectives || [];
          if (objs.length){ var ext = {};
            for (var oi=0; oi<objs.length; oi++){ var o=objs[oi];
              ext[o.id] = { name:o.name, scaled:Number(o.scaled), raw:o.raw, min:o.min, max:o.max, passed:!!o.passed }; }
            res.extensions = {}; res.extensions[CMI5.EXT_SUBSCORES] = ext; }
          sendStmt(stmt(score.passed?CMI5.V.passed:CMI5.V.failed, score.passed?"passed":"failed", res, true)); }
        lrs("PUT", "activities/state", stateParams("course.progress"), { state:lastState, done:true });
      },
      interaction: function(){ /* cmi5 captures KC outcomes in the score/statements; per-item xAPI optional */ },
      quit: function () { if (terminated) return; terminated = true;
        sendStmt(stmt(CMI5.V.terminated, "terminated", { duration:isoDur(Date.now()-started) })); }
    };
  }

  /* ============================ runtime selection ============================ */
  function makeRuntime() {
    var scorm = makeScorm();
    return scorm.init().then(function (s) {
      if (s) return { rt: scorm, info: s };                 // a SCORM LMS answered
      var q = cmi5Params();
      if (q) { var c = makeCmi5(q); return c.init().then(function (i) { return { rt:c, info:i }; }); }
      return { rt: null, info: { resumed:null, finished:false } };   // standalone
    });
  }

  /* ============================ Course flow ============================ */
  function ready(fn){ document.readyState!=="loading" ? fn() : document.addEventListener("DOMContentLoaded", fn); }

  if (HAS_DOM) ready(function () {
    makeRuntime().then(function (sel) {
      var RT = sel.rt, resumed = sel.info && sel.info.resumed;

      // C5 — question-bank pre-pass. BEFORE the collectors below, draw N of each bank's pool
      // and REMOVE the undrawn children, so every existing selector/counter/gradedScore sees
      // exactly the drawn subset with NO further changes. Also shuffle each drawn KC's option
      // order. On resume, reuse the persisted draw + option order (resume-stable); a fresh
      // launch draws anew. (Re-draw on the in-session Retry button is a planned follow-up.)
      var banks = Array.prototype.slice.call(document.querySelectorAll("[data-bank]"));
      var bankState = {};
      if (banks.length) {
        var savedBanks = (resumed && resumed.b) || {};
        banks.forEach(function (bank, bi) {
          var kids = Array.prototype.slice.call(bank.children);
          var draw = parseInt(bank.getAttribute("data-draw") || String(kids.length), 10);
          var saved = savedBanks[bi];
          var pick = (saved && saved.pick) ? saved.pick
            : drawPool(kids.length, draw, makeRng((Date.now() ^ (bi * 0x9E3779B1)) >>> 0));
          var optOrders = (saved && saved.opt) || {};
          var keep = {}; pick.forEach(function (k) { keep[k] = true; });
          kids.forEach(function (node, k) {
            if (!keep[k]) { bank.removeChild(node); return; }
            var opts = Array.prototype.slice.call(node.querySelectorAll(".nv-kc-opt"));
            if (opts.length) {
              var order = optOrders[k] || seededShuffle(opts.length, makeRng((Date.now() ^ (bi * 131 + k * 977)) >>> 0));
              optOrders[k] = order;
              var anchor = opts[opts.length - 1].nextSibling;   // submit/feedback node after the options
              order.forEach(function (oi) { node.insertBefore(opts[oi], anchor); });
            }
          });
          bankState[bi] = { pick: pick, opt: optOrders };
        });
      }

      var gates = Array.prototype.slice.call(document.querySelectorAll(".nv-continue"));
      var kcs   = Array.prototype.slice.call(document.querySelectorAll(".nv-kc"));
      var media = Array.prototype.slice.call(document.querySelectorAll("[data-require='1']"));
      var reqOpens = Array.prototype.slice.call(document.querySelectorAll('[data-require-open="1"]'));
      var sorts = Array.prototype.slice.call(document.querySelectorAll("[data-sort]"));
      var matches = Array.prototype.slice.call(document.querySelectorAll("[data-match]"));  // M12
      var sequences = Array.prototype.slice.call(document.querySelectorAll("[data-seq]"));  // M12
      var fills = Array.prototype.slice.call(document.querySelectorAll("[data-fill]"));  // M12
      var drags = Array.prototype.slice.call(document.querySelectorAll("[data-drag]"));  // dragDrop
      var wordsearches = Array.prototype.slice.call(document.querySelectorAll("[data-wordsearch]"));  // wordSearch
      var crosswords = Array.prototype.slice.call(document.querySelectorAll("[data-crossword]"));  // crossword
      var gameshows = Array.prototype.slice.call(document.querySelectorAll("[data-gameshow]"));  // gameShow
      var quizboards = Array.prototype.slice.call(document.querySelectorAll("[data-quizboard]"));  // quizBoard (Jeopardy)
      var speedstreaks = Array.prototype.slice.call(document.querySelectorAll("[data-speedstreak]"));  // speedStreak (fast run)
      var reflections = Array.prototype.slice.call(document.querySelectorAll("[data-reflection]"));  // C7 reflection (non-graded, completion-only)
      var flips = Array.prototype.slice.call(document.querySelectorAll(".nv-flip"));
      var bar   = document.querySelector(".nv-progress > span");
      var prog  = document.querySelector(".nv-progress");
      var endEl = document.querySelector(".nv-course-end");
      var exitBtn = document.querySelector(".nv-exit");

      var graded = document.body.getAttribute("data-graded") === "1";
      var passMark = parseInt(document.body.getAttribute("data-pass") || "80", 10);
      // Align the graded pass threshold with the LMS masteryScore when one is supplied
      // (cmi5 LaunchData; scaled 0..1 per spec, tolerate a 0..100 value too). Authored
      // data-pass is the fallback when the LMS sends none.
      var lmsMastery = (sel.info && typeof sel.info.mastery === "number") ? sel.info.mastery : null;
      if (lmsMastery !== null) passMark = lmsMastery <= 1 ? Math.round(lmsMastery * 100) : Math.round(lmsMastery);
      var maxTries = parseInt(document.body.getAttribute("data-retry") || "0", 10);  // 0 = one-shot
      // M13 — completion gate (graded courses gate a failing score by default; data-gate="0"
      // = build/author turned it off) + per-section subscore objectives.
      var GATE = document.body.getAttribute("data-gate") !== "0";
      var OBJECTIVES = [];
      try { OBJECTIVES = JSON.parse(document.body.getAttribute("data-objectives") || "[]") || []; }
      catch(e){ OBJECTIVES = []; }
      var lessonIdx = parseInt(document.body.getAttribute("data-lesson") || "1", 10);
      var lessonCount = parseInt(document.body.getAttribute("data-lessons") || "1", 10);
      var notLast = lessonCount > 1 && lessonIdx < lessonCount;

      // points/XP overlay (gamification #3) — a purely motivational HUD, opt-in via the
      // course-level `*Points:* on` directive (render emits data-xp + a hidden .nv-xp HUD).
      // Absent → XP stays null and this whole layer is inert. Config = {w:weights, t:tiers}.
      var XP = null;
      try { var _xj = document.body.getAttribute("data-xp"); if (_xj) XP = JSON.parse(_xj); }
      catch(e){ XP = null; }
      var xpHud = XP ? document.querySelector(".nv-xp") : null;
      var xpPtsEl = xpHud && xpHud.querySelector(".nv-xp-pts");
      var xpTierEl = xpHud && xpHud.querySelector(".nv-xp-tier");
      var xpTierIdx = -1;   // last shown tier index; -1 = not yet rendered (suppresses the resume flourish)

      // confetti celebration overlay (gamification #6) — opt-in via `*Celebrate:* on`
      // (render emits data-celebrate = {pass,level,complete}). Purely cosmetic: a zero-dep
      // canvas burst on the enabled moments, honoring prefers-reduced-motion. Absent → inert.
      var CELEB = null;
      try { var _cj = document.body.getAttribute("data-celebrate"); if (_cj) CELEB = JSON.parse(_cj); }
      catch(e){ CELEB = null; }
      var celebFired = { pass:false, complete:false };   // once-guards; a level-up recurs, no guard
      var confettiActive = false, confettiSeed = 0x1234567;
      var reduceMotion = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

      var hasInteractive = gates.length + kcs.length + media.length + reqOpens.length + sorts.length + matches.length + sequences.length + fills.length + drags.length + wordsearches.length + crosswords.length > 0;
      var kcSeen = {}, kcTries = {}, mediaSeen = {}, openSeen = {}, sortSeen = {}, matchSeen = {}, seqSeen = {}, fillSeen = {}, dragSeen = {}, wsSeen = {}, cwSeen = {}, gsSeen = {}, qbSeen = {}, ssSeen = {}, reflectionSeen = {}, reachedEnd = false, loc = null;
      var gsResetters = [];   // gameShow holds per-block closure state (answered map, revealed slice) → each wiring registers a reset() here for the graded-retry path
      var ssResetters = [];   // speedStreak likewise holds closure state (answered map, streak/score, timer) → reset() registered here for graded-retry
      var qbResetters = [];   // quizBoard likewise holds closure state (answered tiles, open panel) → reset() registered here for graded-retry
      var completed = !!(sel.info && sel.info.finished);
      var restoring = false;

      function save(){ if (restoring || !RT) return;
        var payload = { g:gates.reduce(function(a,g,i){ if(g.dataset.passed==="1")a.push(i); return a; },[]),
          k:kcSeen, m:Object.keys(mediaSeen), o:Object.keys(openSeen), s:sortSeen, mt:matchSeen, sq:seqSeen, fl:fillSeen, dd:dragSeen, ws:wsSeen, cw:cwSeen, gs:gsSeen, qb:qbSeen, ss:ssSeen, rf:reflectionSeen, loc:loc };
        if (banks.length) payload.b = bankState;   // C5 — only bank courses carry `b` (byte-identical otherwise)
        RT.save(payload); }
      function gradedScore(){
        // Feed the pure aggregator one item per KC: its section objective (data-obj) + whether
        // the learner's final answer was correct. With objectives, only tagged KCs are summative.
        var items = kcs.map(function(kc,i){
          return { obj: kc.getAttribute("data-obj") || null, ok: !!(kcSeen[i] && kcSeen[i].ok) }; });
        // M12 — matching/sequencing/fill blocks contribute FRACTIONAL {got,max} credit, but ONLY
        // when tagged into a graded *Section:* (data-obj present). Untagged blocks stay formative.
        function addPartials(nodes, seen, prefix){
          nodes.forEach(function(el,i){ var obj = el.getAttribute("data-obj"); if (!obj) return;
            var r = seen[prefix+i]; if (!r) return;
            items.push({ obj: obj, ok: !!r.ok, got: r.got, max: r.max }); });
        }
        addPartials(matches, matchSeen, "mt");
        addPartials(sequences, seqSeen, "sq");
        addPartials(fills, fillSeen, "fl");
        addPartials(drags, dragSeen, "dd");
        addPartials(wordsearches, wsSeen, "ws");
        addPartials(crosswords, cwSeen, "cw");
        addPartials(gameshows, gsSeen, "gs");
        addPartials(quizboards, qbSeen, "qb");
        addPartials(speedstreaks, ssSeen, "ss");
        return aggregateScore(items, passMark, OBJECTIVES);
      }

      function enableEndButton(){
        if (!exitBtn) return;
        exitBtn.disabled = false;
        // SCORM 1.2 has no next-SCO API, so a multi-SCO "lesson" can't navigate
        // onward from here — don't promise it. Exit cleanly; the LMS menu drives
        // sequencing.
        exitBtn.textContent = notLast ? "Lesson complete — continue from the menu" : "Finish course";
      }
      // Fire a zero-dependency confetti burst (gamification #6). Cosmetic + ephemeral: an
      // ad-hoc full-viewport <canvas> animates ~1.5s then removes itself. Honors reduced-motion
      // (no burst), never persists, and is Math.random-free (a per-fire seed → makeRng), so it
      // touches neither the graded score, the completion gate, nor suspend_data. If a burst is
      // already running, or canvas/rAF is unavailable, it no-ops.
      function confettiColors(){
        var out = [];
        try { var cs = window.getComputedStyle(document.body);
          ["--brand-accent","--brand-correct","--brand-heading","--brand-accent-ink","--brand-light"].forEach(function(v){
            var c = cs.getPropertyValue(v).trim(); if (c) out.push(c); }); } catch(e){}
        return out.length ? out : ["#1EB16A","#f5a623","#4a90d9","#e94b3c","#f8e71c"];
      }
      function fireConfetti(){
        if (!CELEB || reduceMotion || confettiActive) return;
        var body = document.body; if (!body) return;
        var cv = document.createElement("canvas");
        if (!cv.getContext || !window.requestAnimationFrame) return;   // ancient LMS webview → skip silently
        confettiActive = true;
        cv.className = "nv-confetti"; cv.setAttribute("aria-hidden", "true");
        var w = cv.width = window.innerWidth || 800, h = cv.height = window.innerHeight || 600;
        body.appendChild(cv);
        var ctx = cv.getContext("2d");
        var colors = confettiColors();
        confettiSeed = (confettiSeed + 0x9E3779B1) | 0;   // vary each fire, no Math.random
        var rng = makeRng(confettiSeed), parts = [], N = 130;
        for (var i=0;i<N;i++){ parts.push({
          x: w*(0.15 + 0.7*rng()), y: -20 - h*0.25*rng(),
          vx: (rng()-0.5)*6, vy: 3 + rng()*5, sz: 5 + rng()*7,
          rot: rng()*6.283, vr: (rng()-0.5)*0.34, col: colors[i % colors.length] }); }
        var start = null, DUR = 1500;
        function frame(ts){
          if (start === null) start = ts;
          var el = ts - start, a = Math.max(0, 1 - el/DUR);
          ctx.clearRect(0,0,w,h);
          for (var i=0;i<parts.length;i++){ var p = parts[i];
            p.x += p.vx; p.y += p.vy; p.vy += 0.12; p.rot += p.vr;
            ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.rot);
            ctx.globalAlpha = a; ctx.fillStyle = p.col;
            ctx.fillRect(-p.sz/2, -p.sz/2, p.sz, p.sz*0.6); ctx.restore(); }
          if (el < DUR) window.requestAnimationFrame(frame);
          else { if (cv.parentNode) cv.parentNode.removeChild(cv); confettiActive = false; }
        }
        window.requestAnimationFrame(frame);
      }
      // Gate a celebration by config + resume state, then fire. Suppressed entirely during
      // restore (a resumed pass/complete/level must not re-burst — mirrors the XP resume guard).
      function celebrate(reason){
        if (!CELEB || restoring) return;
        var fired = reason === "pass" ? celebFired.pass : (reason === "complete" ? celebFired.complete : false);
        if (!celebrateAllowed(CELEB, reason, fired)) return;
        if (reason === "pass") celebFired.pass = true;
        else if (reason === "complete") celebFired.complete = true;
        fireConfetti();
      }
      // Re-derive the XP total + level tier from the CURRENT block state and paint the HUD.
      // Called after every block resolves (via updateProgress) and once after restore — so
      // resume shows the right total with no persisted XP. A tier increase flashes a subtle
      // level-up (skipped on the first paint / resume, when xpTierIdx is still -1).
      function renderXp(){
        if (!XP || !xpHud) return;
        var t = xpTotals([
          { kind:"kc", seen:kcSeen, count:kcs.length },
          { kind:"sort", seen:sortSeen, count:sorts.length },
          { kind:"mt", seen:matchSeen, count:matches.length },
          { kind:"sq", seen:seqSeen, count:sequences.length },
          { kind:"fl", seen:fillSeen, count:fills.length },
          { kind:"dd", seen:dragSeen, count:drags.length },
          { kind:"ws", seen:wsSeen, count:wordsearches.length },
          { kind:"cw", seen:cwSeen, count:crosswords.length },
          { kind:"gs", seen:gsSeen, count:gameshows.length },
          { kind:"qb", seen:qbSeen, count:quizboards.length },
          { kind:"ss", seen:ssSeen, count:speedstreaks.length }
        ], XP.w);
        if (t.possible <= 0) { xpHud.hidden = true; return; }   // nothing scorable → no dead HUD
        xpHud.hidden = false;
        var tier = tierFor(t.earned / t.possible, XP.t);
        if (xpPtsEl) xpPtsEl.textContent = t.earned;
        if (xpTierEl) xpTierEl.textContent = tier.name;
        if (xpTierIdx >= 0 && tier.index > xpTierIdx){
          xpHud.classList.remove("nv-xp--up");
          void xpHud.offsetWidth;                 // restart the flash if two tiers cross fast
          xpHud.classList.add("nv-xp--up");
          celebrate("level");                     // gamification #6 — confetti on a genuine tier-up (not first paint/resume)
        }
        xpTierIdx = tier.index;
      }
      function updateProgress(){
        var total = gates.length + kcs.length + media.length + reqOpens.length + sorts.length + matches.length + sequences.length + fills.length + drags.length + wordsearches.length + crosswords.length + gameshows.length + quizboards.length + speedstreaks.length + reflections.length || 1;
        var done = gates.filter(function(g){return g.dataset.passed==="1";}).length
          + Object.keys(kcSeen).length + Object.keys(mediaSeen).length + Object.keys(openSeen).length
          + Object.keys(sortSeen).length + Object.keys(matchSeen).length + Object.keys(seqSeen).length + Object.keys(fillSeen).length + Object.keys(dragSeen).length + Object.keys(wsSeen).length + Object.keys(cwSeen).length + Object.keys(gsSeen).length + Object.keys(qbSeen).length + Object.keys(ssSeen).length + Object.keys(reflectionSeen).length;
        var pct = Math.min(100, Math.round(done/total*100));
        if (bar) bar.style.width = pct + "%";
        if (prog) prog.setAttribute("aria-valuenow", pct);
        if (XP) renderXp();
        maybeCelebratePass();
        save(); maybeComplete();
      }
      // gamification #6 — fire confetti the first time a graded course crosses the pass mark.
      // Checked on every progress tick (cheap); the once-guard + `restoring` guard keep it to a
      // single burst and suppress it on resume. Only meaningful when there's something summative.
      function maybeCelebratePass(){
        if (!CELEB || !CELEB.pass || restoring || celebFired.pass) return;
        if (!(graded && (OBJECTIVES.length || kcs.length))) return;
        if (gradedScore().passed) celebrate("pass");
      }
      function maybeComplete(){
        if (completed) { enableEndButton(); return; }
        var ok = gates.every(function(g){return g.dataset.passed==="1";})
          && kcs.length===Object.keys(kcSeen).length && media.length===Object.keys(mediaSeen).length
          && reqOpens.length===Object.keys(openSeen).length && sorts.length===Object.keys(sortSeen).length
          && matches.length===Object.keys(matchSeen).length
          && sequences.length===Object.keys(seqSeen).length
          && fills.length===Object.keys(fillSeen).length
          && drags.length===Object.keys(dragSeen).length
          && wordsearches.length===Object.keys(wsSeen).length
          && crosswords.length===Object.keys(cwSeen).length
          && gameshows.length===Object.keys(gsSeen).length
          && quizboards.length===Object.keys(qbSeen).length
          && speedstreaks.length===Object.keys(ssSeen).length
          && reflections.length===Object.keys(reflectionSeen).length
          && (hasInteractive || reachedEnd);
        if (!ok) return;
        // A graded course that the learner FAILED must not complete (cmi5
        // CompletedAndPassed would never satisfy → they'd be stuck). Offer a
        // retry instead and hold completion until they reach the pass mark.
        // M13 — unless gating is off (data-gate="0"), in which case the course
        // completes regardless of score (the score is still reported).
        // M12→M13 — gate whenever there is something SUMMATIVE to score: any graded
        // objective (a KC or a matching/sequencing/fill block tagged into a graded
        // *Section:*) OR the KC-fallback. The `kcs.length` disjunct keeps a graded course
        // with only formative interactive blocks from gating on an empty score (→ stuck).
        if (graded && GATE && (OBJECTIVES.length || kcs.length) && !gradedScore().passed) { offerRetry(); return; }
        completed = true; if (RT) RT.complete(graded ? gradedScore() : null);
        if (graded && RT && RT.interaction) { var n=0; kcs.forEach(function(kc,i){ var r=kcSeen[i]; if(r) RT.interaction(n++, kc.getAttribute("data-kc-id")||("kc"+i), String(r.opt), r.ok); }); }
        if (bar) bar.style.width = "100%"; if (prog) prog.setAttribute("aria-valuenow", 100); enableEndButton();
        celebrate("complete");                    // gamification #6 — confetti on reaching 100% (suppressed on resume)
      }

      // Graded retry: clear quiz state so the learner can re-attempt to reach mastery.
      var retryBtn = null;
      function resetQuiz(){
        Object.keys(kcSeen).forEach(function(k){ delete kcSeen[k]; });
        Object.keys(kcTries).forEach(function(k){ delete kcTries[k]; });
        Object.keys(sortSeen).forEach(function(k){ delete sortSeen[k]; });
        Object.keys(matchSeen).forEach(function(k){ delete matchSeen[k]; });
        Object.keys(seqSeen).forEach(function(k){ delete seqSeen[k]; });
        Object.keys(fillSeen).forEach(function(k){ delete fillSeen[k]; });
        Object.keys(wsSeen).forEach(function(k){ delete wsSeen[k]; });
        Object.keys(cwSeen).forEach(function(k){ delete cwSeen[k]; });
        Object.keys(gsSeen).forEach(function(k){ delete gsSeen[k]; });
        Object.keys(qbSeen).forEach(function(k){ delete qbSeen[k]; });
        Object.keys(ssSeen).forEach(function(k){ delete ssSeen[k]; });
        Object.keys(dragSeen).forEach(function(k){ delete dragSeen[k]; });
        kcs.forEach(function(kc){
          var isMulti=kc.classList.contains("nv-kc--multi");
          Array.prototype.slice.call(kc.querySelectorAll(".nv-kc-opt")).forEach(function(o){ o.classList.remove("correct","incorrect","is-disabled","is-selected"); o.disabled=false; var mk=o.querySelector(".nv-kc-mark"); if(mk)mk.remove(); if(isMulti)o.setAttribute("aria-pressed","false"); });
          var sub=kc.querySelector(".nv-kc-submit"); if(sub)sub.disabled=false;
          var fb=kc.querySelector(".nv-kc-fb"); if(fb){ fb.classList.remove("show","ok","no"); fb.innerHTML=""; }
        });
        sorts.forEach(function(sort){
          Array.prototype.slice.call(sort.querySelectorAll(".nv-sort-item")).forEach(function(li){ li.classList.remove("correct","incorrect","is-locked"); });
          Array.prototype.slice.call(sort.querySelectorAll(".nv-sort-pick")).forEach(function(p){ p.disabled=false; p.value=""; });
          var b=sort.querySelector(".nv-sort-check"); if(b)b.disabled=false;
          var fb=sort.querySelector(".nv-sort-fb"); if(fb){ fb.classList.remove("show","ok","no"); fb.innerHTML=""; }
        });
        matches.forEach(function(el){
          Array.prototype.slice.call(el.querySelectorAll(".nv-match-item")).forEach(function(li){ li.classList.remove("correct","incorrect","is-locked"); });
          Array.prototype.slice.call(el.querySelectorAll(".nv-match-pick")).forEach(function(p){ p.disabled=false; p.value=""; });
          var b=el.querySelector(".nv-match-check"); if(b)b.disabled=false;
          var fb=el.querySelector(".nv-match-fb"); if(fb){ fb.classList.remove("show","ok","no"); fb.innerHTML=""; }
        });
        sequences.forEach(function(el){
          Array.prototype.slice.call(el.querySelectorAll(".nv-seq-item")).forEach(function(li){ li.classList.remove("correct","incorrect","is-locked"); });
          Array.prototype.slice.call(el.querySelectorAll(".nv-seq-pick")).forEach(function(p){ p.disabled=false; p.value=""; });
          var b=el.querySelector(".nv-seq-check"); if(b)b.disabled=false;
          var fb=el.querySelector(".nv-seq-fb"); if(fb){ fb.classList.remove("show","ok","no"); fb.innerHTML=""; }
        });
        fills.forEach(function(el){
          Array.prototype.slice.call(el.querySelectorAll(".nv-fill-item")).forEach(function(li){ li.classList.remove("correct","incorrect","is-locked"); });
          Array.prototype.slice.call(el.querySelectorAll(".nv-fill-input")).forEach(function(inp){ inp.disabled=false; inp.value=""; });
          var b=el.querySelector(".nv-fill-check"); if(b)b.disabled=false;
          var fb=el.querySelector(".nv-fill-fb"); if(fb){ fb.classList.remove("show","ok","no"); fb.innerHTML=""; }
        });
        drags.forEach(function(el){
          Array.prototype.slice.call(el.querySelectorAll(".nv-drag-item")).forEach(function(li){ li.classList.remove("correct","incorrect","is-locked"); var p=li.querySelector(".nv-drag-pick"); if(p){ p.disabled=false; p.value=""; } });
          Array.prototype.slice.call(el.querySelectorAll(".nv-drag-zone")).forEach(function(z){ z.classList.remove("nv-drag-over","nv-drag-filled"); });
          var b=el.querySelector(".nv-drag-check"); if(b)b.disabled=false;
          var fb=el.querySelector(".nv-drag-fb"); if(fb){ fb.classList.remove("show","ok","no"); fb.innerHTML=""; }
        });
        wordsearches.forEach(function(el){
          Array.prototype.slice.call(el.querySelectorAll(".nv-ws-cell")).forEach(function(c){ c.classList.remove("nv-ws-sel","nv-ws-found"); });
          Array.prototype.slice.call(el.querySelectorAll(".nv-ws-word")).forEach(function(w){ w.classList.remove("found"); });
          var b=el.querySelector(".nv-ws-check"); if(b)b.disabled=false;
          var fb=el.querySelector(".nv-ws-fb"); if(fb){ fb.classList.remove("show","ok","no"); fb.innerHTML=""; }
        });
        crosswords.forEach(function(el){
          Array.prototype.slice.call(el.querySelectorAll(".nv-cw-input")).forEach(function(inp){ inp.disabled=false; inp.value=""; inp.classList.remove("correct","incorrect"); });
          Array.prototype.slice.call(el.querySelectorAll(".nv-cw-clue")).forEach(function(li){ li.classList.remove("solved"); });
          var b=el.querySelector(".nv-cw-check"); if(b)b.disabled=false;
          var fb=el.querySelector(".nv-cw-fb"); if(fb){ fb.classList.remove("show","ok","no"); fb.innerHTML=""; }
        });
        gsResetters.forEach(function(fn){ fn(); });   // gameShow: closure-held answered state + wheel/panels
        qbResetters.forEach(function(fn){ fn(); });   // quizBoard: closure-held answered tiles + open panel
        ssResetters.forEach(function(fn){ fn(); });   // speedStreak: closure-held answered state + streak/score + timer
        completed=false; loc=null; updateProgress();
      }
      function offerRetry(){
        var gs = gradedScore();
        if (!retryBtn){
          retryBtn = document.createElement("button");
          retryBtn.type = "button"; retryBtn.className = "nv-btn nv-retry-quiz";
          retryBtn.addEventListener("click", function(){
            if (retryBtn && retryBtn.parentNode) retryBtn.parentNode.removeChild(retryBtn);
            retryBtn = null; resetQuiz();
            (kcs[0]||document.querySelector(".nv-main")||document.body).scrollIntoView({behavior:"smooth",block:"start"});
          });
        }
        retryBtn.innerHTML = '<span class="nv-sr-only" role="status">You scored '+gs.raw+'%, need '+passMark+'% to pass. </span>Retry quiz';
        if (!retryBtn.parentNode){
          if (exitBtn && exitBtn.parentNode) exitBtn.parentNode.insertBefore(retryBtn, exitBtn);
          else (endEl||document.body).appendChild(retryBtn);
        }
      }

      function revealAfter(gate){ var r = gate.nextElementSibling;
        while (r){ if (r.classList && r.classList.contains("nv-gated")){ r.classList.add("revealed"); break; } r = r.nextElementSibling; } return r; }
      function passGate(gate,i){ gate.dataset.passed="1"; var b=gate.querySelector(".nv-btn"); if(b)b.disabled=true; revealAfter(gate); loc={t:"g",i:i}; }
      // a11y: append an off-screen "(correct answer)"/"(incorrect)" tag to a locked
      // option so a screen-reader user gets the verdict that's otherwise color-only.
      // Idempotent — clears any prior tag first (graded retry re-locks the same options).
      function srMarkOpt(o){ var ex=o.querySelector(".nv-kc-mark"); if(ex)ex.remove();
        var t = o.classList.contains("correct") ? " (correct answer)" : (o.classList.contains("incorrect") ? " (incorrect)" : "");
        if(t){ var s=document.createElement("span"); s.className="nv-sr-only nv-kc-mark"; s.textContent=t; o.appendChild(s); } }
      // terminal KC render: mark choice, reveal correct if wrong, lock, show feedback, record.
      function lockKc(kc,i,oi,ok){ var opts=Array.prototype.slice.call(kc.querySelectorAll(".nv-kc-opt")), fb=kc.querySelector(".nv-kc-fb"), opt=opts[oi];
        if(opt) opt.classList.add(ok?"correct":"incorrect");
        if(!ok) opts.forEach(function(o){ if(o.dataset.correct==="1")o.classList.add("correct"); });
        opts.forEach(function(o){ o.classList.add("is-disabled"); o.disabled=true; srMarkOpt(o); });
        if(fb){ var m = ok?fb.getAttribute("data-fb-correct"):fb.getAttribute("data-fb-incorrect");
          fb.innerHTML='<span class="nv-sr-only">'+(ok?"Correct. ":"Incorrect. ")+'</span>'+(m||""); fb.classList.remove("ok","no"); fb.classList.add("show", ok?"ok":"no"); }
        kcSeen[i]={opt:oi,ok:ok}; loc={t:"kc",i:i}; }
      // terminal multi-select render: reveal the full correct set, flag wrong picks, lock, record.
      function lockKcMulti(kc,i,sel,ok){ var opts=Array.prototype.slice.call(kc.querySelectorAll(".nv-kc-opt")), fb=kc.querySelector(".nv-kc-fb"), submit=kc.querySelector(".nv-kc-submit");
        opts.forEach(function(o,oi){ var want=o.dataset.correct==="1", got=sel.indexOf(oi)>=0;
          o.setAttribute("aria-pressed", got?"true":"false");
          if(want) o.classList.add("correct");                 // always show the correct answers
          else if(got) o.classList.add("incorrect");           // a wrong pick the learner made
          o.classList.add("is-disabled"); o.disabled=true; srMarkOpt(o); });
        if(submit) submit.disabled=true;
        if(fb){ var m = ok?fb.getAttribute("data-fb-correct"):fb.getAttribute("data-fb-incorrect");
          fb.innerHTML='<span class="nv-sr-only">'+(ok?"Correct. ":"Incorrect. ")+'</span>'+(m||""); fb.classList.remove("ok","no"); fb.classList.add("show", ok?"ok":"no"); }
        kcSeen[i]={opt:sel.join(","),ok:ok,multi:1}; loc={t:"kc",i:i}; }

      /* Modals */
      var modals = {}, lastFocus = null;
      var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), video, audio, iframe, [tabindex]:not([tabindex="-1"])';
      Array.prototype.slice.call(document.querySelectorAll(".nv-modal")).forEach(function(m){ modals[m.id]=m; });
      // inert + aria-hidden the page chrome behind an open dialog so AT/Tab can't reach it
      function setInert(el, on){ if(!el)return; if(on){ el.setAttribute("inert",""); el.setAttribute("aria-hidden","true"); } else { el.removeAttribute("inert"); el.removeAttribute("aria-hidden"); } }
      function bgInert(modal, on){
        setInert(document.querySelector(".nv-topbar"), on);
        var main=document.querySelector(".nv-main"); if(!main)return;
        Array.prototype.slice.call(main.children).forEach(function(ch){ if(ch!==modal) setInert(ch, on); });
      }
      function openModal(id){ var m=modals[id]; if(!m)return; lastFocus=document.activeElement; m.hidden=false; document.body.classList.add("nv-modal-open"); bgInert(m, true); var c=m.querySelector(".nv-modal-close"); if(c)c.focus(); }
      function closeModal(m){ if(!m||m.hidden)return; m.hidden=true; bgInert(m, false); if(!document.querySelector(".nv-modal:not([hidden])"))document.body.classList.remove("nv-modal-open");
        var av=m.querySelector("video, audio"); if(av){try{av.pause();}catch(e){}} if(lastFocus){try{lastFocus.focus();}catch(e){}} }
      Array.prototype.slice.call(document.querySelectorAll("[data-modal]")).forEach(function(t){ t.addEventListener("click", function(){ var id=t.getAttribute("data-modal"); openModal(id); if(t.getAttribute("data-require-open")==="1"){ openSeen[id]=true; updateProgress(); } }); });
      Object.keys(modals).forEach(function(id){ var m=modals[id]; m.addEventListener("click", function(e){ if(e.target===m)closeModal(m); });
        var c=m.querySelector(".nv-modal-close"); if(c)c.addEventListener("click", function(){ closeModal(m); });
        m.addEventListener("keydown", function(e){ if(e.key!=="Tab")return;
          var f=Array.prototype.slice.call(m.querySelectorAll(FOCUSABLE)).filter(function(el){ return el.offsetParent!==null || el===document.activeElement; });
          if(!f.length)return; var first=f[0],last=f[f.length-1];
          if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();} else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();} }); });
      document.addEventListener("keydown", function(e){ if(e.key==="Escape")closeModal(document.querySelector(".nv-modal:not([hidden])")); });

      media.forEach(function(el,i){ el.addEventListener("ended", function(){ mediaSeen["m"+i]=true; updateProgress(); }); });
      gates.forEach(function(gate,i){ var b=gate.querySelector(".nv-btn"); if(!b)return; b.addEventListener("click", function(){ passGate(gate,i); var r=revealAfter(gate); updateProgress(); (r||gate).scrollIntoView({behavior:"smooth",block:"start"}); if(r){ try{ r.focus(); }catch(e){} } }); });
      kcs.forEach(function(kc,i){ var opts=Array.prototype.slice.call(kc.querySelectorAll(".nv-kc-opt")), fb=kc.querySelector(".nv-kc-fb");
        if (kc.classList.contains("nv-kc--multi")){                               // multi-select: toggle + submit
          var submit = kc.querySelector(".nv-kc-submit");
          opts.forEach(function(opt){ opt.addEventListener("click", function(){
            if (kcSeen[i]) return;                                                // locked
            var on = opt.getAttribute("aria-pressed")==="true";
            opt.setAttribute("aria-pressed", on?"false":"true"); opt.classList.toggle("is-selected", !on);
          }); });
          if (submit) submit.addEventListener("click", function(){
            if (kcSeen[i]) return;
            var sel=[]; opts.forEach(function(o,oi){ if(o.getAttribute("aria-pressed")==="true") sel.push(oi); });
            if (!sel.length){                                                     // empty submit: prompt politely, don't silently no-op
              if (fb){ fb.textContent="Select at least one option, then choose Submit."; fb.classList.remove("ok","no"); fb.classList.add("show"); }
              return; }
            kcTries[i] = (kcTries[i]||0) + 1;
            var ok = multiAllCorrect(opts.map(function(o){ return o.dataset.correct==="1"; }), sel);
            if (kcLocks(ok, kcTries[i], maxTries)) { lockKcMulti(kc,i,sel,ok); updateProgress(); }
            else {                                                                // retry: keep picks, prompt again
              if (fb){ var left = maxTries - kcTries[i];
                fb.innerHTML = '<span class="nv-sr-only">Incorrect. </span>' +
                  (fb.getAttribute("data-fb-incorrect") || "Not quite.") +
                  ' <em class="nv-kc-retry">Try again — ' + left + ' attempt' + (left===1?'':'s') + ' left.</em>';
                fb.classList.remove("ok"); fb.classList.add("show","no"); }
            }
          });
          return;
        }
        opts.forEach(function(opt,oi){ opt.addEventListener("click", function(){
          if (kcSeen[i] || opt.classList.contains("is-disabled")) return;        // terminal, or an eliminated wrong choice
          kcTries[i] = (kcTries[i]||0) + 1;
          var ok = opt.dataset.correct === "1";
          if (kcLocks(ok, kcTries[i], maxTries)) { lockKc(kc,i,oi,ok); updateProgress(); }   // terminal
          else {                                                                  // retry: eliminate this choice, prompt again
            opt.classList.add("incorrect","is-disabled"); opt.disabled=true; srMarkOpt(opt);
            if (fb){ var left = maxTries - kcTries[i];
              fb.innerHTML = '<span class="nv-sr-only">Incorrect. </span>' +
                (fb.getAttribute("data-fb-incorrect") || "Not quite.") +
                ' <em class="nv-kc-retry">Try again — ' + left + ' attempt' + (left===1?'':'s') + ' left.</em>';
              fb.classList.remove("ok"); fb.classList.add("show","no"); }
          }
        }); }); });

      /* Flashcards — flip toggles aria-pressed (button => Enter/Space free); non-gating.
         The off-screen face is aria-hidden so AT never reads the answer before the flip. */
      flips.forEach(function(fc){ var front=fc.querySelector(".nv-flip-front"), back=fc.querySelector(".nv-flip-back");
        if(back) back.setAttribute("aria-hidden","true");
        fc.addEventListener("click", function(){
          var flipped = fc.getAttribute("aria-pressed")!=="true";
          fc.setAttribute("aria-pressed", flipped ? "true" : "false");
          if(front) front.setAttribute("aria-hidden", flipped ? "true" : "false");
          if(back)  back.setAttribute("aria-hidden", flipped ? "false" : "true");
        }); });

      /* Branching scenarios (M14) — one scene at a time; a choice reveals its feedback,
         then Continue routes to the choice's `data-goto` target scene. A scenario with
         NO targets renders static (no [data-branching]) and is never touched here, so
         linear scenarios keep working. Self-contained: not wired into completion (same
         as the linear scenario, which never gated progress either). */
      Array.prototype.slice.call(document.querySelectorAll(".nv-scenario[data-branching]")).forEach(function(scn){
        var scenes = Array.prototype.slice.call(scn.querySelectorAll(".nv-scn-scene"));
        var sceneIds = scenes.map(function(s){ return s.getAttribute("data-scene-id"); });
        var restart = scn.querySelector(".nv-scn-restart");
        function show(idx){
          scenes.forEach(function(s,i){ s.hidden = (i !== idx); });
          var cur = scenes[idx]; if (!cur) return;
          Array.prototype.slice.call(cur.querySelectorAll(".nv-scn-choice")).forEach(function(b){ b.disabled=false; b.parentNode.classList.remove("is-picked"); });
          Array.prototype.slice.call(cur.querySelectorAll(".nv-scn-fb")).forEach(function(f){ f.hidden=true; });
          var nav = cur.querySelector(".nv-scn-nav"); if (nav) nav.hidden=true;
          cur.scrollIntoView({behavior:"smooth", block:"nearest"});
          try{ cur.focus(); }catch(e){}
        }
        scenes.forEach(function(scene){
          var choices = Array.prototype.slice.call(scene.querySelectorAll(".nv-scn-choice"));
          var nav = scene.querySelector(".nv-scn-nav");
          var contBtn = nav ? nav.querySelector(".nv-scn-continue") : null;
          choices.forEach(function(btn){
            btn.addEventListener("click", function(){
              if (btn.disabled) return;
              choices.forEach(function(o){ o.disabled=true; o.parentNode.classList.remove("is-picked"); });
              btn.parentNode.classList.add("is-picked");
              var fb = btn.parentNode.querySelector(".nv-scn-fb"); if (fb) fb.hidden=false;
              if (restart) restart.hidden=false;             // now that they've started, allow a reset
              var target = resolveScene(btn.getAttribute("data-goto"), sceneIds);
              if (nav && contBtn && target >= 0){            // an onward scene: offer Continue
                nav.hidden=false;
                contBtn.onclick = function(){ show(target); };
              } else if (nav){                               // an ending: no onward scene
                nav.hidden=true;
              }
            });
          });
        });
        if (restart) restart.addEventListener("click", function(){ show(0); });
        // start on the first scene (render emits every scene `hidden`).
        scenes.forEach(function(s,i){ s.hidden = (i !== 0); });
        if (restart) restart.hidden=true;
      });

      /* Categorize / sorting — Check validates each select against its target, then locks + folds into completion */
      function lockSort(sort, i){
        var items = Array.prototype.slice.call(sort.querySelectorAll(".nv-sort-item"));
        var allOk = true;
        items.forEach(function(li){
          var pick = li.querySelector(".nv-sort-pick");
          // An unanswered item (empty value) is always wrong — never let "" === "" (an
          // item authored with no target) auto-pass an untouched select.
          var ok = pick && pick.value !== "" && pick.value === li.getAttribute("data-target");
          li.classList.remove("correct","incorrect"); li.classList.add(ok ? "correct" : "incorrect", "is-locked");
          if (!ok) allOk = false;
        });
        var fb = sort.querySelector(".nv-sort-fb");
        if (fb){ var m = allOk ? fb.getAttribute("data-fb-correct") : fb.getAttribute("data-fb-incorrect");
          fb.innerHTML = '<span class="nv-sr-only">'+(allOk?"Correct. ":"Incorrect. ")+'</span>'+
            (m || (allOk ? "Correct!" : "Some items aren't in the right category.")); fb.classList.remove("ok","no"); fb.classList.add("show", allOk ? "ok" : "no"); }
        var btn = sort.querySelector(".nv-sort-check"); if (btn) btn.disabled = true;
        sortSeen["s"+i] = { ok: allOk, picks: items.map(function(li){ var p=li.querySelector(".nv-sort-pick"); return p?p.value:""; }) };
        loc = { t:"s", i:i };
      }
      // Restore a completed sort WITHOUT re-grading from the DOM — used when suspend_data
      // was degraded (picks dropped to fit the 1.2 budget) so we can't recompute, but the
      // saved `ok` keeps completion + pass/fail intact.
      function markSortDone(sort, i, ok){
        var fb = sort.querySelector(".nv-sort-fb");
        if (fb){ var m = ok ? fb.getAttribute("data-fb-correct") : fb.getAttribute("data-fb-incorrect");
          fb.innerHTML = '<span class="nv-sr-only">'+(ok?"Correct. ":"Incorrect. ")+'</span>'+
            (m || (ok ? "Correct!" : "Some items aren't in the right category.")); fb.classList.remove("ok","no"); fb.classList.add("show", ok ? "ok" : "no"); }
        var btn = sort.querySelector(".nv-sort-check"); if (btn) btn.disabled = true;
        sortSeen["s"+i] = { ok: ok };
      }
      sorts.forEach(function(sort,i){ var btn = sort.querySelector(".nv-sort-check");
        if (btn) btn.addEventListener("click", function(){ if (sortSeen["s"+i]) return; lockSort(sort,i); updateProgress(); }); });

      // M12 — matching: PARTIAL-credit scoring. Each row's pick must equal its data-answer.
      function showMatchFb(el, res){
        var fb = el.querySelector(".nv-match-fb"); if (!fb) return;
        var msg = res.ok ? fb.getAttribute("data-fb-correct") : fb.getAttribute("data-fb-incorrect");
        var tally = (res.got!=null && res.max!=null) ? ("You matched "+res.got+" of "+res.max+" correctly. ") : "";
        fb.innerHTML = '<span class="nv-sr-only">'+(res.ok?"Correct. ":"Incorrect. ")+'</span>'+
          tally + (msg || (res.ok ? "All matched!" : "Some matches aren't right yet."));
        fb.classList.remove("ok","no"); fb.classList.add("show", res.ok ? "ok" : "no");
      }
      function lockMatch(el, i){
        var items = Array.prototype.slice.call(el.querySelectorAll(".nv-match-item"));
        var picks = items.map(function(li){ var p=li.querySelector(".nv-match-pick"); return p?p.value:""; });
        var answers = items.map(function(li){ return li.getAttribute("data-answer"); });
        var res = tallyExact(picks, answers);
        items.forEach(function(li,n){
          var okOne = picks[n] !== "" && picks[n] === answers[n];
          li.classList.remove("correct","incorrect"); li.classList.add(okOne ? "correct" : "incorrect", "is-locked");
        });
        showMatchFb(el, res);
        var btn = el.querySelector(".nv-match-check"); if (btn) btn.disabled = true;
        matchSeen["mt"+i] = { ok: res.ok, got: res.got, max: res.max, picks: picks };
        loc = { t:"mt", i:i };
      }
      // Restore a completed match without re-grading (picks dropped to fit suspend_data).
      function markMatchDone(el, i, rec){
        showMatchFb(el, { ok: !!rec.ok, got: rec.got, max: rec.max });
        var btn = el.querySelector(".nv-match-check"); if (btn) btn.disabled = true;
        matchSeen["mt"+i] = { ok: !!rec.ok, got: rec.got, max: rec.max };
      }
      matches.forEach(function(el,i){ var btn = el.querySelector(".nv-match-check");
        if (btn) btn.addEventListener("click", function(){ if (matchSeen["mt"+i]) return; lockMatch(el,i); updateProgress(); }); });

      // M12 — sequencing: PARTIAL-credit scoring. Each step's picked position must equal data-pos.
      function showSeqFb(el, res){
        var fb = el.querySelector(".nv-seq-fb"); if (!fb) return;
        var msg = res.ok ? fb.getAttribute("data-fb-correct") : fb.getAttribute("data-fb-incorrect");
        var tally = (res.got!=null && res.max!=null) ? ("You placed "+res.got+" of "+res.max+" correctly. ") : "";
        fb.innerHTML = '<span class="nv-sr-only">'+(res.ok?"Correct. ":"Incorrect. ")+'</span>'+
          tally + (msg || (res.ok ? "Correct order!" : "Some steps aren't in the right place yet."));
        fb.classList.remove("ok","no"); fb.classList.add("show", res.ok ? "ok" : "no");
      }
      function lockSeq(el, i){
        var items = Array.prototype.slice.call(el.querySelectorAll(".nv-seq-item"));
        var picks = items.map(function(li){ var p=li.querySelector(".nv-seq-pick"); return p?p.value:""; });
        var answers = items.map(function(li){ return li.getAttribute("data-pos"); });
        var res = tallyExact(picks, answers);
        items.forEach(function(li,n){
          var okOne = picks[n] !== "" && picks[n] === answers[n];
          li.classList.remove("correct","incorrect"); li.classList.add(okOne ? "correct" : "incorrect", "is-locked");
        });
        showSeqFb(el, res);
        var btn = el.querySelector(".nv-seq-check"); if (btn) btn.disabled = true;
        seqSeen["sq"+i] = { ok: res.ok, got: res.got, max: res.max, picks: picks };
        loc = { t:"sq", i:i };
      }
      function markSeqDone(el, i, rec){
        showSeqFb(el, { ok: !!rec.ok, got: rec.got, max: rec.max });
        var btn = el.querySelector(".nv-seq-check"); if (btn) btn.disabled = true;
        seqSeen["sq"+i] = { ok: !!rec.ok, got: rec.got, max: rec.max };
      }
      sequences.forEach(function(el,i){ var btn = el.querySelector(".nv-seq-check");
        if (btn) btn.addEventListener("click", function(){ if (seqSeen["sq"+i]) return; lockSeq(el,i); updateProgress(); }); });

      // M12 — fill-in-the-blank: PARTIAL-credit, LENIENT accept-list matching (normFill).
      function fillAnswers(li){ try { return JSON.parse(li.getAttribute("data-answers") || "[]") || []; } catch(e){ return []; } }
      function showFillFb(el, res){
        var fb = el.querySelector(".nv-fill-fb"); if (!fb) return;
        var msg = res.ok ? fb.getAttribute("data-fb-correct") : fb.getAttribute("data-fb-incorrect");
        var tally = (res.got!=null && res.max!=null) ? ("You answered "+res.got+" of "+res.max+" correctly. ") : "";
        fb.innerHTML = '<span class="nv-sr-only">'+(res.ok?"Correct. ":"Incorrect. ")+'</span>'+
          tally + (msg || (res.ok ? "All correct!" : "Some blanks aren't right yet."));
        fb.classList.remove("ok","no"); fb.classList.add("show", res.ok ? "ok" : "no");
      }
      function lockFill(el, i){
        var items = Array.prototype.slice.call(el.querySelectorAll(".nv-fill-item"));
        var inputs = items.map(function(li){ var inp=li.querySelector(".nv-fill-input"); return inp?inp.value:""; });
        var answerSets = items.map(fillAnswers);
        var res = fillScore(inputs, answerSets);
        items.forEach(function(li,n){
          var got_in = normFill(inputs[n]);
          var okOne = got_in !== "" && answerSets[n].map(normFill).indexOf(got_in) >= 0;
          li.classList.remove("correct","incorrect"); li.classList.add(okOne ? "correct" : "incorrect", "is-locked");
          var inp=li.querySelector(".nv-fill-input"); if(inp) inp.disabled = true;
        });
        showFillFb(el, res);
        var btn = el.querySelector(".nv-fill-check"); if (btn) btn.disabled = true;
        fillSeen["fl"+i] = { ok: res.ok, got: res.got, max: res.max, inputs: inputs };
        loc = { t:"fl", i:i };
      }
      function markFillDone(el, i, rec){
        showFillFb(el, { ok: !!rec.ok, got: rec.got, max: rec.max });
        Array.prototype.slice.call(el.querySelectorAll(".nv-fill-input")).forEach(function(inp){ inp.disabled = true; });
        var btn = el.querySelector(".nv-fill-check"); if (btn) btn.disabled = true;
        fillSeen["fl"+i] = { ok: !!rec.ok, got: rec.got, max: rec.max };
      }
      fills.forEach(function(el,i){ var btn = el.querySelector(".nv-fill-check");
        if (btn) btn.addEventListener("click", function(){ if (fillSeen["fl"+i]) return; lockFill(el,i); updateProgress(); }); });

      /* dragDrop — PARTIAL-credit like matching. The per-label <select> is the source of
         truth (keyboard + touch accessible); native pointer drag just sets it. Each label
         placed in its correct zone (pick === data-target) scores 1 of N. */
      function showDragFb(el, res){
        var fb = el.querySelector(".nv-drag-fb"); if (!fb) return;
        var msg = res.ok ? fb.getAttribute("data-fb-correct") : fb.getAttribute("data-fb-incorrect");
        var tally = (res.got!=null && res.max!=null) ? ("You placed "+res.got+" of "+res.max+" correctly. ") : "";
        fb.innerHTML = '<span class="nv-sr-only">'+(res.ok?"Correct. ":"Incorrect. ")+'</span>'+
          tally + (msg || (res.ok ? "All placed!" : "Some labels aren't on the right target yet."));
        fb.classList.remove("ok","no"); fb.classList.add("show", res.ok ? "ok" : "no");
      }
      function lockDrag(el, i){
        var items = Array.prototype.slice.call(el.querySelectorAll(".nv-drag-item"));
        var picks = items.map(function(li){ var p=li.querySelector(".nv-drag-pick"); return p?p.value:""; });
        var answers = items.map(function(li){ return li.getAttribute("data-target"); });
        var res = tallyExact(picks, answers);
        items.forEach(function(li,n){
          var okOne = picks[n] !== "" && picks[n] === answers[n];
          li.classList.remove("correct","incorrect"); li.classList.add(okOne ? "correct" : "incorrect", "is-locked");
          li.setAttribute("draggable","false");
          var p=li.querySelector(".nv-drag-pick"); if(p) p.disabled = true;
        });
        showDragFb(el, res);
        var btn = el.querySelector(".nv-drag-check"); if (btn) btn.disabled = true;
        dragSeen["dd"+i] = { ok: res.ok, got: res.got, max: res.max, picks: picks };
        loc = { t:"dd", i:i };
      }
      // Restore a completed dragDrop without re-grading (picks dropped to fit suspend_data).
      function markDragDone(el, i, rec){
        showDragFb(el, { ok: !!rec.ok, got: rec.got, max: rec.max });
        Array.prototype.slice.call(el.querySelectorAll(".nv-drag-pick")).forEach(function(p){ p.disabled = true; });
        var btn = el.querySelector(".nv-drag-check"); if (btn) btn.disabled = true;
        dragSeen["dd"+i] = { ok: !!rec.ok, got: rec.got, max: rec.max };
      }
      // Reflect a label's chosen zone into the diagram/zones view (visual only; the <select>
      // stays authoritative). Moves the chip's mirror into the target zone's slot.
      function placeChip(el, li, zid){
        var zones = Array.prototype.slice.call(el.querySelectorAll(".nv-drag-zone"));
        zones.forEach(function(z){
          var slot = z.querySelector(".nv-drag-slot"); if(!slot) return;
          var mine = slot.querySelector('[data-for="'+li.getAttribute("data-cid")+'"]');
          if (mine && z.getAttribute("data-zone") !== zid) { slot.removeChild(mine); z.classList.remove("nv-drag-filled"); }
        });
        if (!zid) return;
        var zone = el.querySelector('.nv-drag-zone[data-zone="'+zid+'"]'); if(!zone) return;
        var slot = zone.querySelector(".nv-drag-slot"); if(!slot) return;
        if (!slot.querySelector('[data-for="'+li.getAttribute("data-cid")+'"]')){
          var tag = document.createElement("span");
          tag.className = "nv-drag-placed"; tag.setAttribute("data-for", li.getAttribute("data-cid"));
          tag.textContent = (li.querySelector(".nv-drag-label")||{}).textContent || "";
          slot.appendChild(tag); zone.classList.add("nv-drag-filled");
        }
      }
      drags.forEach(function(el,i){
        // give each chip a stable id so the visual mirror can track it
        Array.prototype.slice.call(el.querySelectorAll(".nv-drag-item")).forEach(function(li,n){ li.setAttribute("data-cid","c"+n); });
        // keyboard/touch: the <select> drives placement + the visual mirror
        Array.prototype.slice.call(el.querySelectorAll(".nv-drag-item")).forEach(function(li){
          var p=li.querySelector(".nv-drag-pick");
          if(p) p.addEventListener("change", function(){ if(dragSeen["dd"+i]) return; placeChip(el, li, p.value); });
        });
        // pointer drag: dropping a chip on a zone sets that chip's <select> value
        var dragging = null;
        Array.prototype.slice.call(el.querySelectorAll(".nv-drag-item")).forEach(function(li){
          li.addEventListener("dragstart", function(e){ if(dragSeen["dd"+i]){ e.preventDefault(); return; } dragging = li; if(e.dataTransfer){ e.dataTransfer.effectAllowed="move"; try{ e.dataTransfer.setData("text/plain", li.getAttribute("data-cid")); }catch(err){} } });
          li.addEventListener("dragend", function(){ dragging = null; Array.prototype.slice.call(el.querySelectorAll(".nv-drag-zone")).forEach(function(z){ z.classList.remove("nv-drag-over"); }); });
        });
        Array.prototype.slice.call(el.querySelectorAll(".nv-drag-zone")).forEach(function(z){
          z.addEventListener("dragover", function(e){ if(dragSeen["dd"+i]) return; e.preventDefault(); if(e.dataTransfer) e.dataTransfer.dropEffect="move"; z.classList.add("nv-drag-over"); });
          z.addEventListener("dragleave", function(){ z.classList.remove("nv-drag-over"); });
          z.addEventListener("drop", function(e){ if(dragSeen["dd"+i]) return; e.preventDefault(); z.classList.remove("nv-drag-over");
            if(!dragging) return; var p=dragging.querySelector(".nv-drag-pick"); if(p){ p.value = z.getAttribute("data-zone"); placeChip(el, dragging, p.value); } });
        });
        var btn = el.querySelector(".nv-drag-check");
        if (btn) btn.addEventListener("click", function(){ if (dragSeen["dd"+i]) return; lockDrag(el,i); updateProgress(); });
      });

      /* wordSearch — find hidden words in a letter grid. PARTIAL credit (found N of M).
         Two ways to select, both self-contained (no library): drag across a straight run of
         cells (mouse OR touch, via Pointer Events), or click the first letter then the last
         (keyboard-operable — cells are <button>s so Enter fires a click). The player reads the
         letters along the selected line and matches them FORWARD OR REVERSED to a target word;
         placements aren't needed client-side. A Check button locks + scores found/total. */
      function wsScore(found, targets){
        var got = 0; for (var t=0;t<targets.length;t++){ if (found[targets[t]]) got++; }
        return { got: got, max: targets.length, ok: targets.length > 0 && got === targets.length };
      }
      function showWsFb(el, res){
        var fb = el.querySelector(".nv-ws-fb"); if (!fb) return;
        var msg = res.ok ? fb.getAttribute("data-fb-correct") : fb.getAttribute("data-fb-incorrect");
        var tally = (res.got != null && res.max != null) ? ("You found " + res.got + " of " + res.max + ". ") : "";
        fb.innerHTML = '<span class="nv-sr-only">' + (res.ok ? "Correct. " : "Incorrect. ") + '</span>' +
          tally + (msg || (res.ok ? "All found!" : "Some words are still hidden."));
        fb.classList.remove("ok", "no"); fb.classList.add("show", res.ok ? "ok" : "no");
      }
      function markWsWord(el, word){ var li = el.querySelector('.nv-ws-word[data-word="' + word + '"]'); if (li) li.classList.add("found"); }
      function lockWs(el, i, found, targets){
        var res = wsScore(found, targets);
        showWsFb(el, res);
        var btn = el.querySelector(".nv-ws-check"); if (btn) btn.disabled = true;
        wsSeen["ws" + i] = { ok: res.ok, got: res.got, max: res.max, found: Object.keys(found) };
        loc = { t: "ws", i: i };
      }
      // Restore a completed wordSearch without re-grading (the found list may have been dropped
      // to fit suspend_data): re-cross-off whatever found words survived + lock.
      function markWsDone(el, i, rec){
        showWsFb(el, { ok: !!rec.ok, got: rec.got, max: rec.max });
        (rec.found || []).forEach(function(w){ markWsWord(el, w); });
        var btn = el.querySelector(".nv-ws-check"); if (btn) btn.disabled = true;
        wsSeen["ws" + i] = { ok: !!rec.ok, got: rec.got, max: rec.max };
      }
      wordsearches.forEach(function(el, i){
        var gridEl = el.querySelector(".nv-ws-grid"); if (!gridEl) return;
        var cellAt = {};
        Array.prototype.slice.call(el.querySelectorAll(".nv-ws-cell")).forEach(function(c){ cellAt[c.getAttribute("data-r") + "," + c.getAttribute("data-c")] = c; });
        var targets = Array.prototype.slice.call(el.querySelectorAll(".nv-ws-word")).map(function(w){ return w.getAttribute("data-word"); });
        var found = {};           // WORD -> true
        var anchor = null;        // {r,c} first endpoint of a click-to-click selection
        var path = [];            // cells in the current tentative line
        var downRC = null, isDrag = false, justDragged = false;

        function rc(cell){ return { r: +cell.getAttribute("data-r"), c: +cell.getAttribute("data-c") }; }
        function clearSel(){ path.forEach(function(c){ c.classList.remove("nv-ws-sel"); }); path = []; }
        function showPath(cells){ clearSel(); path = cells || []; path.forEach(function(c){ c.classList.add("nv-ws-sel"); }); }
        function lineCells(a, b){
          var dr = b.r - a.r, dc = b.c - a.c, adr = Math.abs(dr), adc = Math.abs(dc);
          if (!(dr === 0 || dc === 0 || adr === adc)) return null;   // must be a straight 8-way line
          var len = Math.max(adr, adc) + 1, sr = (dr > 0 ? 1 : (dr < 0 ? -1 : 0)), sc = (dc > 0 ? 1 : (dc < 0 ? -1 : 0)), out = [];
          for (var k = 0; k < len; k++){ var cc = cellAt[(a.r + sr * k) + "," + (a.c + sc * k)]; if (!cc) return null; out.push(cc); }
          return out;
        }
        function evaluate(){
          if (path.length < 2){ clearSel(); return; }
          var str = ""; path.forEach(function(c){ str += c.textContent; });
          var rev = str.split("").reverse().join(""), hit = null;
          for (var t = 0; t < targets.length; t++){ var w = targets[t]; if (!found[w] && (w === str || w === rev)){ hit = w; break; } }
          if (hit){ found[hit] = true; path.forEach(function(c){ c.classList.add("nv-ws-found"); }); markWsWord(el, hit); }
          clearSel();
        }
        function cellUnder(e){
          var t = e.target && e.target.closest ? e.target.closest(".nv-ws-cell") : null;
          if (t) return t;
          var u = document.elementFromPoint(e.clientX, e.clientY);   // during a fast drag
          return u && u.closest ? u.closest(".nv-ws-cell") : null;
        }
        gridEl.addEventListener("pointerdown", function(e){
          if (wsSeen["ws" + i]) return;
          var cell = cellUnder(e); if (!cell) return;
          downRC = rc(cell); isDrag = false; justDragged = false;
        });
        gridEl.addEventListener("pointermove", function(e){
          if (wsSeen["ws" + i] || !downRC) return;
          var cell = cellUnder(e); if (!cell) return;
          var here = rc(cell);
          if (here.r === downRC.r && here.c === downRC.c) return;    // still on the start cell
          isDrag = true;
          showPath(lineCells(downRC, here) || []);
        });
        document.addEventListener("pointerup", function(){
          if (wsSeen["ws" + i] || !downRC) { downRC = null; return; }
          if (isDrag){ evaluate(); justDragged = true; anchor = null; }
          downRC = null; isDrag = false;
        });
        gridEl.addEventListener("pointercancel", function(){ downRC = null; isDrag = false; clearSel(); });
        gridEl.addEventListener("click", function(e){
          if (wsSeen["ws" + i]) return;
          if (justDragged){ justDragged = false; return; }           // swallow the click a mouse drag emits
          var cell = e.target && e.target.closest ? e.target.closest(".nv-ws-cell") : null; if (!cell) return;
          if (!anchor){ anchor = rc(cell); showPath([cell]); return; }
          showPath(lineCells(anchor, rc(cell)) || []); evaluate(); anchor = null;
        });
        var wbtn = el.querySelector(".nv-ws-check");
        if (wbtn) wbtn.addEventListener("click", function(){ if (wsSeen["ws" + i]) return; lockWs(el, i, found, targets); updateProgress(); });
      });

      /* crossword — type answers into a numbered interlocking grid. PARTIAL credit
         (words solved / total). White cells are native <input>s (keyboard/touch), so the
         interaction needs no library; a Check button reads each clue's cells, compares the
         typed letters to the answer, marks each clue solved/unsolved, then locks. */
      function cwInputs(el){ return Array.prototype.slice.call(el.querySelectorAll(".nv-cw-input")); }
      function cwInputAt(el){ var m={}; cwInputs(el).forEach(function(inp){ m[inp.getAttribute("data-r")+","+inp.getAttribute("data-c")]=inp; }); return m; }
      function cwWordSolved(inputMap, clue){
        var cells = (clue.getAttribute("data-cells")||"").split(" "), answer = clue.getAttribute("data-answer")||"", got = "";
        for (var k=0;k<cells.length;k++){ var inp = inputMap[cells[k]]; got += ((inp && inp.value) || "").toUpperCase().replace(/[^A-Z]/g,""); }
        return got.length===answer.length && got===answer;
      }
      function cwScore(el){
        var inputMap = cwInputAt(el), clues = Array.prototype.slice.call(el.querySelectorAll(".nv-cw-clue")), got = 0;
        clues.forEach(function(c){ if (cwWordSolved(inputMap, c)){ got++; } });
        return { got: got, max: clues.length, ok: clues.length>0 && got===clues.length };
      }
      function showCwFb(el, res){
        var fb = el.querySelector(".nv-cw-fb"); if (!fb) return;
        var msg = res.ok ? fb.getAttribute("data-fb-correct") : fb.getAttribute("data-fb-incorrect");
        var tally = (res.got != null && res.max != null) ? ("You solved " + res.got + " of " + res.max + ". ") : "";
        fb.innerHTML = '<span class="nv-sr-only">' + (res.ok ? "Correct. " : "Incorrect. ") + '</span>' +
          tally + (msg || (res.ok ? "All solved!" : "Some answers are still incomplete."));
        fb.classList.remove("ok", "no"); fb.classList.add("show", res.ok ? "ok" : "no");
      }
      function cwCollect(el){ var m={}; cwInputs(el).forEach(function(inp){ var v=(inp.value||"").toUpperCase().replace(/[^A-Z]/g,""); if(v) m[inp.getAttribute("data-r")+","+inp.getAttribute("data-c")]=v; }); return m; }
      function cwMark(el){
        var inputMap = cwInputAt(el);
        Array.prototype.slice.call(el.querySelectorAll(".nv-cw-clue")).forEach(function(c){
          var ok = cwWordSolved(inputMap, c); c.classList.toggle("solved", ok);
          (c.getAttribute("data-cells")||"").split(" ").forEach(function(rc){ var inp=inputMap[rc]; if(!inp) return;
            if (ok) inp.classList.add("correct");
            else if ((inp.value||"").trim()) inp.classList.add("incorrect"); });
        });
      }
      function lockCw(el, i){
        cwMark(el);
        var res = cwScore(el);
        showCwFb(el, res);
        cwInputs(el).forEach(function(inp){ inp.disabled = true; });
        var btn = el.querySelector(".nv-cw-check"); if (btn) btn.disabled = true;
        cwSeen["cw" + i] = { ok: res.ok, got: res.got, max: res.max, letters: cwCollect(el) };
        loc = { t: "cw", i: i };
      }
      // Restore a completed crossword without re-grading: refill whatever typed letters
      // survived suspend_data (dropped under byte pressure → inputs stay blank), re-mark + lock.
      function markCwDone(el, i, rec){
        var inputMap = cwInputAt(el);
        Object.keys(rec.letters || {}).forEach(function(rc){ var inp=inputMap[rc]; if(inp) inp.value = rec.letters[rc]; });
        if (rec.letters) cwMark(el);
        showCwFb(el, { ok: !!rec.ok, got: rec.got, max: rec.max });
        cwInputs(el).forEach(function(inp){ inp.disabled = true; });
        var btn = el.querySelector(".nv-cw-check"); if (btn) btn.disabled = true;
        cwSeen["cw" + i] = { ok: !!rec.ok, got: rec.got, max: rec.max };
      }
      crosswords.forEach(function(el, i){
        cwInputs(el).forEach(function(inp){
          // Uppercase live + auto-advance to the next input for a fluid fill.
          inp.addEventListener("input", function(){
            if (cwSeen["cw" + i]) return;
            inp.value = (inp.value || "").toUpperCase().replace(/[^A-Za-z]/g, "").slice(0, 1);
            if (inp.value){ var all = cwInputs(el), n = all.indexOf(inp); if (n > -1 && n + 1 < all.length) all[n + 1].focus(); }
          });
        });
        var cbtn = el.querySelector(".nv-cw-check");
        if (cbtn) cbtn.addEventListener("click", function(){ if (cwSeen["cw" + i]) return; lockCw(el, i); updateProgress(); });
      });

      /* gameShow — spin-the-wheel review. Each slice is one MCQ. The learner spins
         (animated wheel + a keyboard/reduced-motion-safe Spin button that lands on the
         next unanswered slice, deterministically — no Math.random), answers the drawn
         question, then spins again. PARTIAL credit (answered N of M correctly). The block
         registers in gsSeen only once EVERY slice is answered — mirroring the single-shot
         game blocks' one-entry-when-done semantics; option order is fixed at build time so
         the correct-answer index (and thus scoring) is resume-stable. */
      function gsScore(marks){       // marks: [bool] one per answered slice
        var got=0; for (var k=0;k<marks.length;k++){ if (marks[k]) got++; }
        return { got: got, max: marks.length, ok: marks.length>0 && got===marks.length };
      }
      function showGsFb(el, res){
        var fb = el.querySelector(".nv-gs-fb"); if (!fb) return;
        var msg = res.ok ? fb.getAttribute("data-fb-correct") : fb.getAttribute("data-fb-incorrect");
        var tally = (res.got != null && res.max != null) ? ("You answered " + res.got + " of " + res.max + " correctly. ") : "";
        fb.innerHTML = '<span class="nv-sr-only">' + (res.ok ? "All correct. " : "Round complete. ") + '</span>' +
          tally + (msg || (res.ok ? "Perfect round!" : "Review the answers above."));
        fb.classList.remove("ok","no"); fb.classList.add("show", res.ok ? "ok" : "no");
      }
      gameshows.forEach(function(el, i){
        var rotor = el.querySelector(".nv-gs-rotor");
        var spinBtn = el.querySelector(".nv-gs-spin");
        var panelWrap = el.querySelector(".nv-gs-panels");
        var panels = Array.prototype.slice.call(el.querySelectorAll(".nv-gs-panel"));
        var segs = Array.prototype.slice.call(el.querySelectorAll(".nv-gs-seg"));
        var n = panels.length, seg = 360/(n||1), turns = 0;
        var answered = {};    // sliceIdx -> ok(bool)
        var current = -1;     // slice currently revealed & awaiting an answer (-1 = none)

        // Unique, panel-scoped radio names → a group is exclusive AND two gameShows can't clash.
        panels.forEach(function(p, qi){
          Array.prototype.slice.call(p.querySelectorAll('input[type="radio"]')).forEach(function(r){ r.name = "gs"+i+"q"+qi; });
        });
        function remaining(){ var out=[]; for (var k=0;k<n;k++){ if (!(k in answered)) out.push(k); } return out; }
        function hidePanels(){ panels.forEach(function(p){ p.hidden = true; }); }
        function markSeg(idx, ok){ if (segs[idx]){ segs[idx].classList.add("nv-gs-done", ok?"nv-gs-ok":"nv-gs-no"); } }
        function pointAt(idx){
          if (!rotor) return;
          turns += 4;                                   // whole extra rotations for the spin effect
          rotor.style.transform = "rotate(" + (turns*360 - (idx+0.5)*seg) + "deg)";   // slice centre → top pointer
        }
        function reveal(idx){
          current = idx; hidePanels();
          var p = panels[idx]; if (!p) return;
          p.hidden = false;
          try { var f = p.querySelector('input[type="radio"]'); if (f) f.focus(); } catch(e){}
        }
        function lockPanel(p, chosen, ok){
          var ansIdx = +p.getAttribute("data-answer");
          Array.prototype.slice.call(p.querySelectorAll(".nv-gs-opt")).forEach(function(lab, oi){
            var r = lab.querySelector('input[type="radio"]'); if (r) r.disabled = true;
            if (oi === ansIdx) lab.classList.add("nv-gs-correct");
            else if (oi === chosen) lab.classList.add("nv-gs-wrong");
          });
          p.classList.add(ok ? "nv-gs-answered-ok" : "nv-gs-answered-no");
          var sub = p.querySelector(".nv-gs-submit"); if (sub) sub.disabled = true;
        }
        function finish(){
          var marks = []; for (var k=0;k<n;k++) marks.push(!!answered[k]);
          var res = gsScore(marks);
          showGsFb(el, res); hidePanels();
          if (spinBtn){ spinBtn.disabled = true; spinBtn.hidden = true; }
          var ans = {}; for (var k2=0;k2<n;k2++) ans[k2] = answered[k2] ? 1 : 0;
          gsSeen["gs"+i] = { ok: res.ok, got: res.got, max: res.max, ans: ans };
          loc = { t:"gs", i:i }; current = -1;
          updateProgress();
        }
        function submit(idx){
          if (gsSeen["gs"+i] || (idx in answered)) return;
          var p = panels[idx]; if (!p) return;
          var chosen = p.querySelector('input[type="radio"]:checked');
          if (!chosen){ if (panelWrap) panelWrap.classList.add("nv-gs-nudge"); return; }
          var ok = (+chosen.value === +p.getAttribute("data-answer"));
          answered[idx] = ok; lockPanel(p, +chosen.value, ok); markSeg(idx, ok); current = -1;
          if (remaining().length){ if (spinBtn){ spinBtn.disabled = false; spinBtn.textContent = "Spin again"; } }
          else finish();
        }
        function spin(){
          if (gsSeen["gs"+i] || current >= 0) return;
          var rem = remaining(); if (!rem.length) return;
          var rng = makeRng((i+1)*0x9E3779B1 + Object.keys(answered).length);   // deterministic + resume-safe (count re-derivable)
          var idx = rem[Math.floor(rng()*rem.length)];
          if (spinBtn) spinBtn.disabled = true;
          pointAt(idx); reveal(idx);
        }
        if (spinBtn) spinBtn.addEventListener("click", spin);
        panels.forEach(function(p, qi){
          var sub = p.querySelector(".nv-gs-submit");
          if (sub) sub.addEventListener("click", function(){ submit(qi); });
          Array.prototype.slice.call(p.querySelectorAll('input[type="radio"]')).forEach(function(r){
            r.addEventListener("change", function(){ if (panelWrap) panelWrap.classList.remove("nv-gs-nudge"); });
          });
        });
        // Restore a completed gameShow without re-scoring: re-mark each slice by its stored
        // correctness (dropped under byte pressure → just the tally), reveal the answers, lock.
        el.__gsRestore = function(rec){
          var ans = rec.ans || null;
          panels.forEach(function(p, qi){
            if (ans && (qi in ans)){ var ok = !!ans[qi]; answered[qi] = ok;
              lockPanel(p, -1, ok); markSeg(qi, ok); p.hidden = false; p.classList.add("nv-gs-restored");
            } else { p.hidden = true; Array.prototype.slice.call(p.querySelectorAll("input,button")).forEach(function(c){ c.disabled = true; }); }
          });
          if (spinBtn){ spinBtn.disabled = true; spinBtn.hidden = true; }
          showGsFb(el, { ok: !!rec.ok, got: rec.got, max: rec.max });
          gsSeen["gs"+i] = { ok: !!rec.ok, got: rec.got, max: rec.max };
        };
        // Graded-retry hook: wipe this block's closure state + DOM (resetQuiz calls it).
        gsResetters.push(function(){
          answered = {}; current = -1; turns = 0;
          if (rotor) rotor.style.transform = "";
          hidePanels();
          panels.forEach(function(p){
            p.classList.remove("nv-gs-answered-ok","nv-gs-answered-no","nv-gs-restored");
            Array.prototype.slice.call(p.querySelectorAll(".nv-gs-opt")).forEach(function(lab){ lab.classList.remove("nv-gs-correct","nv-gs-wrong"); var r=lab.querySelector('input[type="radio"]'); if(r){ r.disabled=false; r.checked=false; } });
            var sub=p.querySelector(".nv-gs-submit"); if(sub) sub.disabled=false;
          });
          segs.forEach(function(s){ s.classList.remove("nv-gs-done","nv-gs-ok","nv-gs-no"); });
          if (spinBtn){ spinBtn.disabled=false; spinBtn.hidden=false; spinBtn.textContent="Spin"; }
          var fb=el.querySelector(".nv-gs-fb"); if(fb){ fb.classList.remove("show","ok","no"); fb.innerHTML=""; }
        });
      });

      /* quizBoard (Jeopardy category board): pick any tile, answer its MCQ, the tile flips
         correct/incorrect. WEIGHTED partial credit — points earned / points possible, so the
         tally reads as a score. Registers in qbSeen only once EVERY tile is answered (single-
         shot, mirroring gameShow); option order is fixed at build time → resume-stable. */
      quizboards.forEach(function(el, i){
        var board = el.querySelector(".nv-qb-board");
        var tiles = Array.prototype.slice.call(el.querySelectorAll(".nv-qb-tile"));
        var panels = Array.prototype.slice.call(el.querySelectorAll(".nv-qb-panel"));
        var panelWrap = el.querySelector(".nv-qb-panels");
        var n = panels.length;
        var answered = {};    // flatIdx -> ok(bool)
        var current = -1;     // tile whose panel is open (-1 = none)
        var tileByIdx = {}; tiles.forEach(function(tl){ tileByIdx[+tl.getAttribute("data-idx")] = tl; });

        // Panels render in flatIdx order (data-idx = array index); tiles render row-major, so
        // they're looked up by data-idx. Unique, panel-scoped radio names keep groups exclusive.
        panels.forEach(function(p, qi){
          Array.prototype.slice.call(p.querySelectorAll('input[type="radio"]')).forEach(function(r){ r.name = "qb"+i+"q"+qi; });
        });
        function score(){
          var got=0, max=0;
          panels.forEach(function(p, qi){ var v=+p.getAttribute("data-value")||0; max+=v; if (answered[qi]) got+=v; });
          return { got:got, max:max, ok: max>0 && got===max };
        }
        function showFb(res){
          var fb = el.querySelector(".nv-qb-fb"); if (!fb) return;
          var msg = res.ok ? fb.getAttribute("data-fb-correct") : fb.getAttribute("data-fb-incorrect");
          var tally = (res.max != null) ? ("You scored " + res.got + " of " + res.max + " points. ") : "";
          fb.innerHTML = '<span class="nv-sr-only">' + (res.ok ? "All correct. " : "Board complete. ") + '</span>' +
            tally + (msg || (res.ok ? "Clean sweep!" : "Review the answers above."));
          fb.classList.remove("ok","no"); fb.classList.add("show", res.ok ? "ok" : "no");
        }
        function hidePanels(){ panels.forEach(function(p){ p.hidden = true; }); }
        function markTile(idx, ok){ var tl=tileByIdx[idx]; if (tl){ tl.classList.add("nv-qb-done", ok?"nv-qb-ok":"nv-qb-no"); tl.disabled=true; } }
        function remaining(){ var c=0; for (var k=0;k<n;k++){ if (!(k in answered)) c++; } return c; }
        function reveal(idx){
          current = idx; hidePanels();
          if (board) board.classList.add("nv-qb-picking");
          var p = panels[idx]; if (!p) return; p.hidden = false;
          try { var f = p.querySelector('input[type="radio"]'); if (f) f.focus(); } catch(e){}
        }
        function lockPanel(p, chosen, ok){
          var ansIdx = +p.getAttribute("data-answer");
          Array.prototype.slice.call(p.querySelectorAll(".nv-qb-opt")).forEach(function(lab, oi){
            var r = lab.querySelector('input[type="radio"]'); if (r) r.disabled = true;
            if (oi === ansIdx) lab.classList.add("nv-qb-correct");
            else if (oi === chosen) lab.classList.add("nv-qb-wrong");
          });
          p.classList.add(ok ? "nv-qb-answered-ok" : "nv-qb-answered-no");
          var sub = p.querySelector(".nv-qb-submit"); if (sub) sub.disabled = true;
        }
        function finish(){
          var res = score(); showFb(res); hidePanels();
          if (board) board.classList.remove("nv-qb-picking");
          var ans = {}; for (var k=0;k<n;k++) ans[k] = answered[k] ? 1 : 0;
          qbSeen["qb"+i] = { ok: res.ok, got: res.got, max: res.max, ans: ans };
          loc = { t:"qb", i:i }; current = -1;
          updateProgress();
        }
        function submit(idx){
          if (qbSeen["qb"+i] || (idx in answered)) return;
          var p = panels[idx]; if (!p) return;
          var chosen = p.querySelector('input[type="radio"]:checked');
          if (!chosen){ if (panelWrap) panelWrap.classList.add("nv-qb-nudge"); return; }
          var ok = (+chosen.value === +p.getAttribute("data-answer"));
          answered[idx] = ok; lockPanel(p, +chosen.value, ok); markTile(idx, ok);
          p.hidden = true; current = -1;
          if (board) board.classList.remove("nv-qb-picking");
          if (!remaining()) finish();          // else: back to the board for the next tile
        }
        tiles.forEach(function(tl){
          tl.addEventListener("click", function(){
            if (qbSeen["qb"+i] || current >= 0) return;
            var idx = +tl.getAttribute("data-idx");
            if (!(idx in answered)) reveal(idx);
          });
        });
        panels.forEach(function(p, qi){
          var sub = p.querySelector(".nv-qb-submit");
          if (sub) sub.addEventListener("click", function(){ submit(qi); });
          Array.prototype.slice.call(p.querySelectorAll('input[type="radio"]')).forEach(function(r){
            r.addEventListener("change", function(){ if (panelWrap) panelWrap.classList.remove("nv-qb-nudge"); });
          });
        });
        // Restore a completed board without re-scoring: re-mark each tile by its stored
        // correctness (dropped under byte pressure → neutral done + just the tally), lock.
        el.__qbRestore = function(rec){
          var ans = rec.ans || null;
          for (var qi=0; qi<n; qi++){
            var known = !!(ans && (qi in ans)), ok = known && !!ans[qi], tl = tileByIdx[qi];
            if (known){ answered[qi] = ok; if (panels[qi]) lockPanel(panels[qi], -1, ok); }
            if (tl){ tl.disabled = true; tl.classList.add("nv-qb-done"); if (known) tl.classList.add(ok?"nv-qb-ok":"nv-qb-no"); }
          }
          hidePanels();
          showFb({ ok: !!rec.ok, got: rec.got, max: rec.max });
          qbSeen["qb"+i] = { ok: !!rec.ok, got: rec.got, max: rec.max };
        };
        // Graded-retry hook: wipe this block's closure state + DOM (resetQuiz calls it).
        qbResetters.push(function(){
          answered = {}; current = -1;
          if (board) board.classList.remove("nv-qb-picking");
          hidePanels();
          tiles.forEach(function(tl){ tl.disabled = false; tl.classList.remove("nv-qb-done","nv-qb-ok","nv-qb-no"); });
          panels.forEach(function(p){
            p.classList.remove("nv-qb-answered-ok","nv-qb-answered-no");
            Array.prototype.slice.call(p.querySelectorAll(".nv-qb-opt")).forEach(function(lab){ lab.classList.remove("nv-qb-correct","nv-qb-wrong"); var r=lab.querySelector('input[type="radio"]'); if(r){ r.disabled=false; r.checked=false; } });
            var sub=p.querySelector(".nv-qb-submit"); if(sub) sub.disabled=false;
          });
          var fb=el.querySelector(".nv-qb-fb"); if(fb){ fb.classList.remove("show","ok","no"); fb.innerHTML=""; }
        });
      });

      /* speedStreak — a fast one-at-a-time MCQ run. The learner presses Start, answers each
         question in sequence (a native radio group), and builds a CONSECUTIVE-CORRECT streak
         shown on a cosmetic scoreboard. An optional per-question countdown (data-timer) drives
         only a cosmetic speed bonus + combo score — the ONLY place a wall-clock enters, and it
         never touches correctness, the graded {got,max}, or the persisted state, so the block
         stays accessible (no WCAG timing-adjustable problem — you can answer after 0) and
         deterministic. Registers in ssSeen only once EVERY round is answered (single-shot,
         mirroring gameShow); option order is fixed at build time → resume-stable. PARTIAL
         credit (answered N of M correctly). */
      function showSsFb(el, res){
        var fb = el.querySelector(".nv-ss-fb"); if (!fb) return;
        var msg = res.ok ? fb.getAttribute("data-fb-correct") : fb.getAttribute("data-fb-incorrect");
        var tally = (res.got != null && res.max != null) ? ("You answered " + res.got + " of " + res.max + " correctly. ") : "";
        fb.innerHTML = '<span class="nv-sr-only">' + (res.ok ? "All correct. " : "Run complete. ") + '</span>' +
          tally + (msg || (res.ok ? "Perfect run!" : "Review the answers above."));
        fb.classList.remove("ok","no"); fb.classList.add("show", res.ok ? "ok" : "no");
      }
      speedstreaks.forEach(function(el, i){
        var panels = Array.prototype.slice.call(el.querySelectorAll(".nv-ss-panel"));
        var n = panels.length;
        var startBtn = el.querySelector(".nv-ss-start");
        var nextBtn = el.querySelector(".nv-ss-next");
        var scoreEl = el.querySelector(".nv-ss-score b");
        var streakEl = el.querySelector(".nv-ss-streak b");
        var progEl = el.querySelector(".nv-ss-progress");
        var timerEl = el.querySelector(".nv-ss-timer b");
        var timerBar = el.querySelector(".nv-ss-timerbar span");
        var TSEC = +(el.getAttribute("data-timer") || 0);
        var answered = {};    // roundIdx -> ok(bool)
        var current = -1;     // round currently revealed & awaiting an answer (-1 = none)
        var streak = 0, score = 0;   // cosmetic only — never part of the grade
        var tHandle = null, tRemain = 0;

        // Unique, panel-scoped radio names → a group is exclusive AND two speedStreaks can't clash.
        panels.forEach(function(p, qi){
          Array.prototype.slice.call(p.querySelectorAll('input[type="radio"]')).forEach(function(r){ r.name = "ss"+i+"q"+qi; });
        });
        function hidePanels(){ panels.forEach(function(p){ p.hidden = true; }); }
        function setProg(){ if (progEl) progEl.textContent = Object.keys(answered).length + " / " + n; }
        function setStreak(){ if (streakEl) streakEl.textContent = streak; }
        function setScore(){ if (scoreEl) scoreEl.textContent = score; }
        function stopTimer(){ if (tHandle){ clearInterval(tHandle); tHandle = null; } }
        function paintTimer(){ if (timerEl) timerEl.textContent = tRemain;
          if (timerBar) timerBar.style.width = (TSEC > 0 ? (tRemain / TSEC * 100) : 0) + "%"; }
        function startTimer(){
          if (!(TSEC > 0)) return;
          stopTimer(); tRemain = TSEC; paintTimer();
          // wall-clock, but COSMETIC ONLY — expiry stops the bonus, never marks the answer or forces an advance.
          tHandle = setInterval(function(){ tRemain -= 1; if (tRemain <= 0){ tRemain = 0; stopTimer(); } paintTimer(); }, 1000);
        }
        function timeFrac(){ return TSEC > 0 ? (tRemain / TSEC) : 0; }   // fraction still on the clock (cosmetic bonus)
        function reveal(idx){
          current = idx; hidePanels();
          var p = panels[idx]; if (!p) return;
          p.hidden = false;
          if (nextBtn) nextBtn.hidden = true;
          startTimer();
          try { var f = p.querySelector('input[type="radio"]'); if (f) f.focus(); } catch(e){}
        }
        function lockPanel(p, chosen, ok){
          var ansIdx = +p.getAttribute("data-answer");
          Array.prototype.slice.call(p.querySelectorAll(".nv-ss-opt")).forEach(function(lab, oi){
            var r = lab.querySelector('input[type="radio"]'); if (r) r.disabled = true;
            if (oi === ansIdx) lab.classList.add("nv-ss-correct");
            else if (oi === chosen) lab.classList.add("nv-ss-wrong");
          });
          p.classList.add(ok ? "nv-ss-answered-ok" : "nv-ss-answered-no");
          var sub = p.querySelector(".nv-ss-submit"); if (sub) sub.disabled = true;
        }
        function finish(){
          var marks = []; for (var k=0;k<n;k++) marks.push(!!answered[k]);
          var res = ssScore(marks);
          showSsFb(el, res); hidePanels();
          if (nextBtn){ nextBtn.disabled = true; nextBtn.hidden = true; }
          if (startBtn){ startBtn.disabled = true; startBtn.hidden = true; }
          var ans = {}; for (var k2=0;k2<n;k2++) ans[k2] = answered[k2] ? 1 : 0;
          ssSeen["ss"+i] = { ok: res.ok, got: res.got, max: res.max, ans: ans };
          loc = { t:"ss", i:i }; current = -1;
          updateProgress();
        }
        function submit(idx){
          if (ssSeen["ss"+i] || (idx in answered)) return;
          var p = panels[idx]; if (!p) return;
          var chosen = p.querySelector('input[type="radio"]:checked');
          if (!chosen){ el.classList.add("nv-ss-nudge"); return; }
          el.classList.remove("nv-ss-nudge");
          var frac = timeFrac(); stopTimer();
          var ok = (+chosen.value === +p.getAttribute("data-answer"));
          score += ssCombo(ok, streak, frac);          // cosmetic combo — never touches the grade
          streak = ok ? streak + 1 : 0;
          answered[idx] = ok; lockPanel(p, +chosen.value, ok); current = -1;
          setProg(); setStreak(); setScore();
          if (Object.keys(answered).length < n){ if (nextBtn){ nextBtn.disabled = false; nextBtn.hidden = false; try{ nextBtn.focus(); }catch(e){} } }
          else finish();
        }
        function nextRound(){
          if (ssSeen["ss"+i] || current >= 0) return;
          for (var k=0;k<n;k++){ if (!(k in answered)){ reveal(k); return; } }
        }
        if (startBtn) startBtn.addEventListener("click", function(){
          if (ssSeen["ss"+i] || current >= 0) return;
          startBtn.disabled = true; startBtn.hidden = true;
          nextRound();
        });
        if (nextBtn) nextBtn.addEventListener("click", nextRound);
        panels.forEach(function(p, qi){
          var sub = p.querySelector(".nv-ss-submit");
          if (sub) sub.addEventListener("click", function(){ submit(qi); });
          Array.prototype.slice.call(p.querySelectorAll('input[type="radio"]')).forEach(function(r){
            r.addEventListener("change", function(){ el.classList.remove("nv-ss-nudge"); });
          });
        });
        // Restore a completed speedStreak without re-scoring: re-mark each round by its stored
        // correctness (dropped under byte pressure → just the tally), reveal the answers, lock.
        // The cosmetic streak/score is NOT restored (motivational only) — just the final tally.
        el.__ssRestore = function(rec){
          stopTimer();
          var ans = rec.ans || null;
          panels.forEach(function(p, qi){
            if (ans && (qi in ans)){ var ok = !!ans[qi]; answered[qi] = ok;
              lockPanel(p, -1, ok); p.hidden = false; p.classList.add("nv-ss-restored");
            } else { p.hidden = true; Array.prototype.slice.call(p.querySelectorAll("input,button")).forEach(function(c){ c.disabled = true; }); }
          });
          if (startBtn){ startBtn.disabled = true; startBtn.hidden = true; }
          if (nextBtn){ nextBtn.disabled = true; nextBtn.hidden = true; }
          setProg();
          showSsFb(el, { ok: !!rec.ok, got: rec.got, max: rec.max });
          ssSeen["ss"+i] = { ok: !!rec.ok, got: rec.got, max: rec.max };
        };
        // Graded-retry hook: wipe this block's closure state + DOM (resetQuiz calls it).
        ssResetters.push(function(){
          stopTimer();
          answered = {}; current = -1; streak = 0; score = 0;
          setProg(); setStreak(); setScore();
          if (timerEl) timerEl.textContent = TSEC || 0;
          if (timerBar) timerBar.style.width = "100%";
          hidePanels();
          panels.forEach(function(p){
            p.classList.remove("nv-ss-answered-ok","nv-ss-answered-no","nv-ss-restored");
            Array.prototype.slice.call(p.querySelectorAll(".nv-ss-opt")).forEach(function(lab){ lab.classList.remove("nv-ss-correct","nv-ss-wrong"); var r=lab.querySelector('input[type="radio"]'); if(r){ r.disabled=false; r.checked=false; } });
            var sub=p.querySelector(".nv-ss-submit"); if(sub) sub.disabled=false;
          });
          el.classList.remove("nv-ss-nudge");
          if (startBtn){ startBtn.disabled=false; startBtn.hidden=false; }
          if (nextBtn){ nextBtn.disabled=true; nextBtn.hidden=true; }
          var fb=el.querySelector(".nv-ss-fb"); if(fb){ fb.classList.remove("show","ok","no"); fb.innerHTML=""; }
        });
      });

      // C7 reflection — free-text / open-response, NON-GRADED (completion-only). The learner
      // types a response and submits; the model answer + rubric (authored at build time — no
      // runtime AI scorer, SCORM is offline) then REVEAL for self-assessment. Marking the block
      // done never touches the graded score, pass gate, or XP (there is no data-obj, and it is
      // never passed to gradedScore()/xpTotals()). Requires a non-empty answer so ticking the
      // box means the learner actually reflected. The typed text persists via the `rf` suspend
      // rung; on resume the guidance is re-revealed and the block locked.
      reflections.forEach(function(el, i){
        var input = el.querySelector(".nv-rf-input");
        var submit = el.querySelector(".nv-rf-submit");
        var answer = el.querySelector(".nv-rf-answer");   // may be absent (no model/criteria authored)
        var done = el.querySelector(".nv-rf-done");
        function lock(){ if (input) input.readOnly = true; if (submit){ submit.disabled = true; submit.hidden = true; } }
        function reveal(){ if (answer) answer.hidden = false; if (done) done.hidden = false; }
        if (submit) submit.addEventListener("click", function(){
          if (reflectionSeen["rf"+i]) return;                 // already submitted
          var txt = input ? input.value.trim() : "";
          if (!txt){ if (input){ el.classList.add("nv-rf-nudge"); input.focus(); } return; }  // need something written
          el.classList.remove("nv-rf-nudge");
          reflectionSeen["rf"+i] = { ok:1, text: txt, rev:1 };
          reveal(); lock();
          updateProgress();
        });
        // Resume: re-fill the typed text (dropped under byte pressure → just the completion
        // flag survives), re-reveal the guidance, and lock. The model answer lives in the DOM,
        // so it is always shown once the block was completed, even if the text was packed away.
        el.__rfRestore = function(rec){
          if (rec && rec.text && input) input.value = rec.text;
          reveal(); lock();
          reflectionSeen["rf"+i] = { ok:1, text: (rec && rec.text) || "", rev:1 };
        };
      });

      /* Completion floor */
      if (endEl && "IntersectionObserver" in window) { var io=new IntersectionObserver(function(es){ es.forEach(function(e){ if(e.isIntersecting){ reachedEnd=true; updateProgress(); } }); }); io.observe(endEl); }
      else { reachedEnd = true; }

      /* End button — disabled until complete (set by render); on click leave/advance */
      if (exitBtn) {
        exitBtn.disabled = true;
        exitBtn.addEventListener("click", function () {
          if (exitBtn.disabled) return;
          if (RT) RT.quit();
          exitBtn.disabled = true;
          var ru = RT && RT.returnURL && RT.returnURL();
          if (ru) { location.href = ru; return; }
          try { window.top.close(); } catch (e) {}
          window.close();
        });
      }

      /* Restore prior progress */
      if (resumed) { restoring = true;
        (resumed.g||[]).forEach(function(gi){ if(gates[gi]) passGate(gates[gi],gi); });
        Object.keys(resumed.k||{}).forEach(function(ki){ var r=resumed.k[ki]; if(kcs[ki]&&r){
          if(r.multi) lockKcMulti(kcs[ki], +ki, parseMultiSel(r.opt), r.ok);
          else lockKc(kcs[ki],+ki,r.opt,r.ok); } });
        (resumed.m||[]).forEach(function(mk){ mediaSeen[mk]=true; });
        (resumed.o||[]).forEach(function(ok){ openSeen[ok]=true; });
        Object.keys(resumed.s||{}).forEach(function(sk){ var idx=+sk.slice(1), st=resumed.s[sk];
          if (sorts[idx] && st){ var picks=st.picks||[];
            if (picks.length){
              Array.prototype.slice.call(sorts[idx].querySelectorAll(".nv-sort-item")).forEach(function(li,n){
                var p=li.querySelector(".nv-sort-pick"); if(p&&picks[n]!=null) p.value=picks[n]; });
              lockSort(sorts[idx], idx);
            } else {
              markSortDone(sorts[idx], idx, !!st.ok);   // picks were dropped to fit suspend_data
            }
          } });
        Object.keys(resumed.mt||{}).forEach(function(mk){ var idx=+mk.slice(2), st=resumed.mt[mk];  // M12 matching
          if (matches[idx] && st){ var picks=st.picks||[];
            if (picks.length){
              Array.prototype.slice.call(matches[idx].querySelectorAll(".nv-match-item")).forEach(function(li,n){
                var p=li.querySelector(".nv-match-pick"); if(p&&picks[n]!=null) p.value=picks[n]; });
              lockMatch(matches[idx], idx);
            } else {
              markMatchDone(matches[idx], idx, st);     // picks were dropped to fit suspend_data
            }
          } });
        Object.keys(resumed.sq||{}).forEach(function(qk){ var idx=+qk.slice(2), st=resumed.sq[qk];  // M12 sequencing
          if (sequences[idx] && st){ var picks=st.picks||[];
            if (picks.length){
              Array.prototype.slice.call(sequences[idx].querySelectorAll(".nv-seq-item")).forEach(function(li,n){
                var p=li.querySelector(".nv-seq-pick"); if(p&&picks[n]!=null) p.value=picks[n]; });
              lockSeq(sequences[idx], idx);
            } else {
              markSeqDone(sequences[idx], idx, st);     // picks were dropped to fit suspend_data
            }
          } });
        Object.keys(resumed.fl||{}).forEach(function(fk){ var idx=+fk.slice(2), st=resumed.fl[fk];  // M12 fill-in-the-blank
          if (fills[idx] && st){ var inputs=st.inputs||[];
            if (inputs.length){
              Array.prototype.slice.call(fills[idx].querySelectorAll(".nv-fill-input")).forEach(function(inp,n){
                if(inputs[n]!=null) inp.value=inputs[n]; });
              lockFill(fills[idx], idx);
            } else {
              markFillDone(fills[idx], idx, st);        // inputs were dropped to fit suspend_data
            }
          } });
        Object.keys(resumed.dd||{}).forEach(function(dk){ var idx=+dk.slice(2), st=resumed.dd[dk];  // dragDrop
          if (drags[idx] && st){ var picks=st.picks||[];
            if (picks.length){
              Array.prototype.slice.call(drags[idx].querySelectorAll(".nv-drag-item")).forEach(function(li,n){
                li.setAttribute("data-cid","c"+n);
                var p=li.querySelector(".nv-drag-pick"); if(p&&picks[n]!=null){ p.value=picks[n]; placeChip(drags[idx], li, picks[n]); } });
              lockDrag(drags[idx], idx);
            } else {
              markDragDone(drags[idx], idx, st);        // picks were dropped to fit suspend_data
            }
          } });
        Object.keys(resumed.ws||{}).forEach(function(wk){ var idx=+wk.slice(2), st=resumed.ws[wk];  // wordSearch
          if (wordsearches[idx] && st){ markWsDone(wordsearches[idx], idx, st); } });   // grid paths aren't stored → re-mark found words + lock
        Object.keys(resumed.cw||{}).forEach(function(ck){ var idx=+ck.slice(2), st=resumed.cw[ck];  // crossword
          if (crosswords[idx] && st){ markCwDone(crosswords[idx], idx, st); } });   // refill surviving letters (or blank under byte pressure) + lock
        Object.keys(resumed.gs||{}).forEach(function(gk){ var idx=+gk.slice(2), st=resumed.gs[gk];  // gameShow
          if (gameshows[idx] && st && gameshows[idx].__gsRestore){ gameshows[idx].__gsRestore(st); } });   // per-slice marks (or just the tally under byte pressure) + lock
        Object.keys(resumed.qb||{}).forEach(function(qk){ var idx=+qk.slice(2), st=resumed.qb[qk];  // quizBoard
          if (quizboards[idx] && st && quizboards[idx].__qbRestore){ quizboards[idx].__qbRestore(st); } });   // per-tile marks (or just the tally under byte pressure) + lock
        Object.keys(resumed.ss||{}).forEach(function(sk){ var idx=+sk.slice(2), st=resumed.ss[sk];  // speedStreak
          if (speedstreaks[idx] && st && speedstreaks[idx].__ssRestore){ speedstreaks[idx].__ssRestore(st); } });   // per-round marks (or just the tally under byte pressure) + lock
        Object.keys(resumed.rf||{}).forEach(function(fk){ var idx=+fk.slice(2), st=resumed.rf[fk];  // C7 reflection
          if (reflections[idx] && st && reflections[idx].__rfRestore){ reflections[idx].__rfRestore(st); } });   // re-fill the typed text (dropped under byte pressure), reveal the model answer + lock
        loc = resumed.loc || null; restoring = false;
        if (loc){ var tgt = loc.t==="g"?gates[loc.i]:(loc.t==="kc"?kcs[loc.i]:null); if(tgt) try{ tgt.scrollIntoView({block:"start"}); }catch(e){} }
      }

      updateProgress();
      window.addEventListener("pagehide", function(){ if (RT) RT.quit(); });
      window.addEventListener("beforeunload", function(){ if (RT) RT.quit(); });
    });
  });

  /* =========================== Entrance animations =========================== */
  /* Named entrance effects as each top-level block enters the viewport: simple
     blocks rotate through a tasteful palette ('up' = Float In dominant, with
     occasional Slide In From Left/Right); grouped blocks (cards, comparison
     panels, timeline, infographic items) fade their shell and CASCADE their
     children with a stagger. Purely presentational and independent of the LMS
     runtime. We add the classes ONLY when animations are on (body[data-anim] !=
     "0"), IntersectionObserver is available, and motion is allowed — so a no-JS,
     no-observer, reduced-motion, or animations-off visitor always sees fully-
     visible content. Gated blocks (their own reveal) and modals are skipped. */
  if (HAS_DOM) ready(function () {
    if (document.body.getAttribute("data-anim") === "0") return;
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || !("IntersectionObserver" in window)) return;
    var blocks = Array.prototype.slice.call(document.querySelectorAll(".nv-main .nv-block"))
      .filter(function (el) { return el.closest && !el.closest(".nv-gated") && !el.closest(".nv-modal"); });
    if (!blocks.length) return;
    var DIRS = ["up", "left", "up", "right"];   // Float In dominant; both slide sides appear
    var GROUP_ITEMS = ".nv-card, .nv-tl-item, .nv-cmp-panel, .nv-ig-card, .nv-ig-goal";
    var si = 0;                                 // advance the palette per simple block only,
                                                // so grouped blocks don't starve the slide-ins
    blocks.forEach(function (el) {
      var kids = Array.prototype.slice.call(el.querySelectorAll(GROUP_ITEMS));
      if (kids.length > 1) {                    // grouped block: fade shell, cascade items
        el.classList.add("nv-anim", "nv-anim-fade");
        kids.forEach(function (k, j) {
          k.classList.add("nv-anim", "nv-anim-up", "nv-anim-kid");
          k.style.setProperty("--nv-anim-delay", Math.min(0.08 + j * 0.11, 0.8).toFixed(2) + "s");
        });
      } else {                                  // simple block: one directional effect
        el.classList.add("nv-anim", "nv-anim-" + DIRS[si++ % DIRS.length]);
      }
    });
    var ro = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        e.target.classList.add("nv-in");
        var kids = e.target.querySelectorAll(".nv-anim-kid");
        Array.prototype.slice.call(kids).forEach(function (k) { k.classList.add("nv-in"); });
        ro.unobserve(e.target);
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    blocks.forEach(function (el) { ro.observe(el); });
  });

  // Node-only: expose the pure helpers for unit tests (no-op in the browser,
  // where `module` is undefined). The DOM bootstrap above is HAS_DOM-guarded, so
  // requiring this file under node defines + exports without touching the DOM.
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { utf8len: utf8len, packSorts: packSorts, packKcs: packKcs,
      fitSuspend: fitSuspend, multiAllCorrect: multiAllCorrect, kcLocks: kcLocks,
      scorePct: scorePct, parseMultiSel: parseMultiSel, resolveScene: resolveScene,
      aggregateScore: aggregateScore, packSeen: packSeen, tallyExact: tallyExact,
      normFill: normFill, fillScore: fillScore,
      makeRng: makeRng, seededShuffle: seededShuffle, drawPool: drawPool, packBank: packBank,
      ssScore: ssScore, ssCombo: ssCombo, celebrateAllowed: celebrateAllowed,
      xpCat: xpCat, xpWeight: xpWeight, xpForResult: xpForResult, xpTotals: xpTotals, tierFor: tierFor };
  }
})();
