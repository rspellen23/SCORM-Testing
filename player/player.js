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
  // Return the largest representation of `state` that fits the 1.2 byte budget.
  function fitSuspend(state){
    var rungs = [
      state,                                                                              // full (incl. loc)
      { g:state.g, k:state.k, m:state.m, o:state.o, s:state.s },                          // drop cosmetic resume pointer
      { g:state.g, k:state.k, m:state.m, o:state.o, s:packSorts(state.s) },               // drop sort picks
      { g:state.g, k:packKcs(state.k), m:state.m, o:state.o, s:packSorts(state.s) }       // drop KC option detail
    ];
    var last = "";
    for (var i=0;i<rungs.length;i++){ last = JSON.stringify(rungs[i]); if (utf8len(last) <= SUSPEND_BUDGET) return last; }
    return last;   // smallest rung; still valid JSON even if a pathological course exceeds the budget
  }

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
         terminated:"http://adlnet.gov/expapi/verbs/terminated" }
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
          sendStmt(stmt(score.passed?CMI5.V.passed:CMI5.V.failed, score.passed?"passed":"failed",
                    { success:!!score.passed, score:sc, duration:dur }, true)); }
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

  ready(function () {
    makeRuntime().then(function (sel) {
      var RT = sel.rt, resumed = sel.info && sel.info.resumed;

      var gates = Array.prototype.slice.call(document.querySelectorAll(".nv-continue"));
      var kcs   = Array.prototype.slice.call(document.querySelectorAll(".nv-kc"));
      var media = Array.prototype.slice.call(document.querySelectorAll("[data-require='1']"));
      var reqOpens = Array.prototype.slice.call(document.querySelectorAll('[data-require-open="1"]'));
      var sorts = Array.prototype.slice.call(document.querySelectorAll("[data-sort]"));
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
      var lessonIdx = parseInt(document.body.getAttribute("data-lesson") || "1", 10);
      var lessonCount = parseInt(document.body.getAttribute("data-lessons") || "1", 10);
      var notLast = lessonCount > 1 && lessonIdx < lessonCount;

      var hasInteractive = gates.length + kcs.length + media.length + reqOpens.length + sorts.length > 0;
      var kcSeen = {}, kcTries = {}, mediaSeen = {}, openSeen = {}, sortSeen = {}, reachedEnd = false, loc = null;
      var completed = !!(sel.info && sel.info.finished);
      var restoring = false;

      function save(){ if (!restoring && RT) RT.save({ g:gates.reduce(function(a,g,i){ if(g.dataset.passed==="1")a.push(i); return a; },[]),
        k:kcSeen, m:Object.keys(mediaSeen), o:Object.keys(openSeen), s:sortSeen, loc:loc }); }
      function gradedScore(){ var correct=0; Object.keys(kcSeen).forEach(function(i){ if(kcSeen[i]&&kcSeen[i].ok) correct++; });
        var raw = kcs.length ? Math.round(correct/kcs.length*100) : 0;
        return { raw:raw, min:0, max:100, scaled:(raw/100).toFixed(2), passed: raw>=passMark }; }

      function enableEndButton(){
        if (!exitBtn) return;
        exitBtn.disabled = false;
        // SCORM 1.2 has no next-SCO API, so a multi-SCO "lesson" can't navigate
        // onward from here — don't promise it. Exit cleanly; the LMS menu drives
        // sequencing.
        exitBtn.textContent = notLast ? "Lesson complete — continue from the menu" : "Finish course";
      }
      function updateProgress(){
        var total = gates.length + kcs.length + media.length + reqOpens.length + sorts.length || 1;
        var done = gates.filter(function(g){return g.dataset.passed==="1";}).length
          + Object.keys(kcSeen).length + Object.keys(mediaSeen).length + Object.keys(openSeen).length
          + Object.keys(sortSeen).length;
        var pct = Math.min(100, Math.round(done/total*100));
        if (bar) bar.style.width = pct + "%";
        if (prog) prog.setAttribute("aria-valuenow", pct);
        save(); maybeComplete();
      }
      function maybeComplete(){
        if (completed) { enableEndButton(); return; }
        var ok = gates.every(function(g){return g.dataset.passed==="1";})
          && kcs.length===Object.keys(kcSeen).length && media.length===Object.keys(mediaSeen).length
          && reqOpens.length===Object.keys(openSeen).length && sorts.length===Object.keys(sortSeen).length
          && (hasInteractive || reachedEnd);
        if (!ok) return;
        // A graded course that the learner FAILED must not complete (cmi5
        // CompletedAndPassed would never satisfy → they'd be stuck). Offer a
        // retry instead and hold completion until they reach the pass mark.
        if (graded && kcs.length && !gradedScore().passed) { offerRetry(); return; }
        completed = true; if (RT) RT.complete(graded ? gradedScore() : null);
        if (graded && RT && RT.interaction) { var n=0; kcs.forEach(function(kc,i){ var r=kcSeen[i]; if(r) RT.interaction(n++, kc.getAttribute("data-kc-id")||("kc"+i), String(r.opt), r.ok); }); }
        if (bar) bar.style.width = "100%"; if (prog) prog.setAttribute("aria-valuenow", 100); enableEndButton();
      }

      // Graded retry: clear quiz state so the learner can re-attempt to reach mastery.
      var retryBtn = null;
      function resetQuiz(){
        Object.keys(kcSeen).forEach(function(k){ delete kcSeen[k]; });
        Object.keys(kcTries).forEach(function(k){ delete kcTries[k]; });
        Object.keys(sortSeen).forEach(function(k){ delete sortSeen[k]; });
        kcs.forEach(function(kc){
          Array.prototype.slice.call(kc.querySelectorAll(".nv-kc-opt")).forEach(function(o){ o.classList.remove("correct","incorrect","is-disabled"); });
          var fb=kc.querySelector(".nv-kc-fb"); if(fb){ fb.classList.remove("show","ok","no"); fb.innerHTML=""; }
        });
        sorts.forEach(function(sort){
          Array.prototype.slice.call(sort.querySelectorAll(".nv-sort-item")).forEach(function(li){ li.classList.remove("correct","incorrect","is-locked"); });
          Array.prototype.slice.call(sort.querySelectorAll(".nv-sort-pick")).forEach(function(p){ p.disabled=false; p.value=""; });
          var b=sort.querySelector(".nv-sort-check"); if(b)b.disabled=false;
          var fb=sort.querySelector(".nv-sort-fb"); if(fb){ fb.classList.remove("show","ok","no"); fb.innerHTML=""; }
        });
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
      // terminal KC render: mark choice, reveal correct if wrong, lock, show feedback, record.
      function lockKc(kc,i,oi,ok){ var opts=Array.prototype.slice.call(kc.querySelectorAll(".nv-kc-opt")), fb=kc.querySelector(".nv-kc-fb"), opt=opts[oi];
        if(opt) opt.classList.add(ok?"correct":"incorrect");
        if(!ok) opts.forEach(function(o){ if(o.dataset.correct==="1")o.classList.add("correct"); });
        opts.forEach(function(o){ o.classList.add("is-disabled"); });
        if(fb){ var m = ok?fb.getAttribute("data-fb-correct"):fb.getAttribute("data-fb-incorrect");
          fb.innerHTML='<span class="nv-sr-only">'+(ok?"Correct. ":"Incorrect. ")+'</span>'+(m||""); fb.classList.remove("ok","no"); fb.classList.add("show", ok?"ok":"no"); }
        kcSeen[i]={opt:oi,ok:ok}; loc={t:"kc",i:i}; }

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
        opts.forEach(function(opt,oi){ opt.addEventListener("click", function(){
          if (kcSeen[i] || opt.classList.contains("is-disabled")) return;        // terminal, or an eliminated wrong choice
          kcTries[i] = (kcTries[i]||0) + 1;
          var ok = opt.dataset.correct === "1";
          if (ok || !maxTries || kcTries[i] >= maxTries) { lockKc(kc,i,oi,ok); updateProgress(); }   // terminal
          else {                                                                  // retry: eliminate this choice, prompt again
            opt.classList.add("incorrect","is-disabled");
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
        Object.keys(resumed.k||{}).forEach(function(ki){ var r=resumed.k[ki]; if(kcs[ki]&&r) lockKc(kcs[ki],+ki,r.opt,r.ok); });
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
  ready(function () {
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
})();
