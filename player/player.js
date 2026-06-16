/* Nova Course Player runtime.
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
      var e = lastErr(); if (e && e!=="0") console.warn("[nova] SetValue rejected", k, "=", v, "err", e); return ok;
    } catch(e){ console.warn("[nova] SetValue threw", k, e); return false; } }
    function commit(){ try { ver==="2004" ? api.Commit("") : api.LMSCommit(""); } catch(e){} }
    function fmtTime(ms){ var s=Math.max(0,Math.round(ms/1000)), h=Math.floor(s/3600), m=Math.floor((s%3600)/60), sec=s%60;
      if (ver==="2004") return "PT"+(h?h+"H":"")+(m?m+"M":"")+sec+"S";
      function p(n){return (n<10?"0":"")+n;} return p(h)+":"+p(m)+":"+p(sec)+".00"; }

    return {
      kind: function(){ return ver ? "scorm "+ver : "scorm"; },
      init: function () {
        if (!locate()) { console.info("[nova] no SCORM LMS"); return Promise.resolve(null); }
        started = Date.now();
        try { ver==="2004" ? api.Initialize("") : api.LMSInitialize(""); } catch(e){ console.warn("[nova] init", e); }
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
        var s = JSON.stringify(state);
        if (ver!=="2004" && s.length>4000) s = JSON.stringify({g:state.g,k:state.k,m:state.m,o:state.o});
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
          ver==="2004" ? api.Terminate("") : api.LMSFinish(""); } catch(e){ console.warn("[nova] quit", e); }
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
        .catch(function(e){ console.warn("[nova] LRS " + method + " " + path, e); });
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
            console.error("[nova] cmi5 fetch returned no auth-token — relaunch with a FRESH registration. Response:", j);
            throw new Error("cmi5: no auth-token");
          }
          token = /^(Basic|Bearer)\s/i.test(t) ? t : ("Basic "+t);          // SCORM Cloud & most LRS: "Basic <token>"
          return lrs("GET", "activities/state", stateParams("LMS.LaunchData"));
        }).then(function(r){ return r && r.ok ? r.json() : {}; }).then(function(ld){
          ctxT = ld.contextTemplate || {}; mode = ld.launchMode || "Normal";
          mastery = (typeof ld.masteryScore==="number") ? ld.masteryScore : null; returnURL = ld.returnURL || null;
          return lrs("GET", "activities/state", stateParams("nova.progress"));
        }).then(function(r){ return r && r.ok ? r.json().catch(function(){return null;}) : null; }).then(function(prog){
          finished = !!(prog && prog.done); lastState = prog && prog.state || null;
          return sendStmt(stmt(CMI5.V.init, "initialized")).then(function(){ return { resumed:lastState, finished:finished }; });
        }).catch(function(e){ console.warn("[nova] cmi5 init failed", e); return { resumed:null, finished:false }; });
      },
      isFinished: function(){ return finished; },
      returnURL: function(){ return returnURL; },
      save: function (state) { lastState = state;
        lrs("PUT", "activities/state", stateParams("nova.progress"), { state:state, done:finished }); },
      complete: function (score) {
        if (mode !== "Normal" || completedSent) return; completedSent = true; finished = true;
        var dur = isoDur(Date.now()-started);
        sendStmt(stmt(CMI5.V.completed, "completed", { completion:true, duration:dur }, true));
        if (score) { var sc = { scaled:Number(score.scaled), raw:score.raw, min:score.min, max:score.max };
          sendStmt(stmt(score.passed?CMI5.V.passed:CMI5.V.failed, score.passed?"passed":"failed",
                    { success:!!score.passed, score:sc, duration:dur }, true)); }
        lrs("PUT", "activities/state", stateParams("nova.progress"), { state:lastState, done:true });
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
      var bar   = document.querySelector(".nv-progress > span");
      var endEl = document.querySelector(".nv-course-end");
      var exitBtn = document.querySelector(".nv-exit");

      var graded = document.body.getAttribute("data-graded") === "1";
      var passMark = parseInt(document.body.getAttribute("data-pass") || "80", 10);
      var maxTries = parseInt(document.body.getAttribute("data-retry") || "0", 10);  // 0 = one-shot
      var lessonIdx = parseInt(document.body.getAttribute("data-lesson") || "1", 10);
      var lessonCount = parseInt(document.body.getAttribute("data-lessons") || "1", 10);
      var notLast = lessonCount > 1 && lessonIdx < lessonCount;

      var hasInteractive = gates.length + kcs.length + media.length + reqOpens.length > 0;
      var kcSeen = {}, kcTries = {}, mediaSeen = {}, openSeen = {}, reachedEnd = false, loc = null;
      var completed = !!(sel.info && sel.info.finished);
      var restoring = false;

      function save(){ if (!restoring && RT) RT.save({ g:gates.reduce(function(a,g,i){ if(g.dataset.passed==="1")a.push(i); return a; },[]),
        k:kcSeen, m:Object.keys(mediaSeen), o:Object.keys(openSeen), loc:loc }); }
      function gradedScore(){ var correct=0; Object.keys(kcSeen).forEach(function(i){ if(kcSeen[i]&&kcSeen[i].ok) correct++; });
        var raw = kcs.length ? Math.round(correct/kcs.length*100) : 0;
        return { raw:raw, min:0, max:100, scaled:(raw/100).toFixed(2), passed: raw>=passMark }; }

      function enableEndButton(){
        if (!exitBtn) return;
        exitBtn.disabled = false;
        exitBtn.textContent = notLast ? "Next lesson →" : "Finish course";
      }
      function updateProgress(){
        var total = gates.length + kcs.length + media.length + reqOpens.length || 1;
        var done = gates.filter(function(g){return g.dataset.passed==="1";}).length
          + Object.keys(kcSeen).length + Object.keys(mediaSeen).length + Object.keys(openSeen).length;
        if (bar) bar.style.width = Math.min(100, Math.round(done/total*100)) + "%";
        save(); maybeComplete();
      }
      function maybeComplete(){
        if (completed) { enableEndButton(); return; }
        var ok = gates.every(function(g){return g.dataset.passed==="1";})
          && kcs.length===Object.keys(kcSeen).length && media.length===Object.keys(mediaSeen).length
          && reqOpens.length===Object.keys(openSeen).length && (hasInteractive || reachedEnd);
        if (ok) { completed = true; if (RT) RT.complete(graded ? gradedScore() : null);
          if (graded && RT && RT.interaction) { var n=0; kcs.forEach(function(kc,i){ var r=kcSeen[i]; if(r) RT.interaction(n++, kc.getAttribute("data-kc-id")||("kc"+i), String(r.opt), r.ok); }); }
          if (bar) bar.style.width = "100%"; enableEndButton(); }
      }

      function revealAfter(gate){ var r = gate.nextElementSibling;
        while (r){ if (r.classList && r.classList.contains("nv-gated")){ r.classList.add("revealed"); break; } r = r.nextElementSibling; } return r; }
      function passGate(gate,i){ gate.dataset.passed="1"; var b=gate.querySelector(".nv-btn"); if(b)b.disabled=true; revealAfter(gate); loc={t:"g",i:i}; }
      // terminal KC render: mark choice, reveal correct if wrong, lock, show feedback, record.
      function lockKc(kc,i,oi,ok){ var opts=Array.prototype.slice.call(kc.querySelectorAll(".nv-kc-opt")), fb=kc.querySelector(".nv-kc-fb"), opt=opts[oi];
        if(opt) opt.classList.add(ok?"correct":"incorrect");
        if(!ok) opts.forEach(function(o){ if(o.dataset.correct==="1")o.classList.add("correct"); });
        opts.forEach(function(o){ o.classList.add("is-disabled"); });
        if(fb){ var m = ok?fb.getAttribute("data-fb-correct"):fb.getAttribute("data-fb-incorrect"); fb.innerHTML=m||""; fb.classList.remove("ok","no"); fb.classList.add("show", ok?"ok":"no"); }
        kcSeen[i]={opt:oi,ok:ok}; loc={t:"kc",i:i}; }

      /* Modals */
      var modals = {}, lastFocus = null;
      Array.prototype.slice.call(document.querySelectorAll(".nv-modal")).forEach(function(m){ modals[m.id]=m; });
      function openModal(id){ var m=modals[id]; if(!m)return; lastFocus=document.activeElement; m.hidden=false; document.body.classList.add("nv-modal-open"); var c=m.querySelector(".nv-modal-close"); if(c)c.focus(); }
      function closeModal(m){ if(!m||m.hidden)return; m.hidden=true; if(!document.querySelector(".nv-modal:not([hidden])"))document.body.classList.remove("nv-modal-open");
        var av=m.querySelector("video, audio"); if(av){try{av.pause();}catch(e){}} if(lastFocus){try{lastFocus.focus();}catch(e){}} }
      Array.prototype.slice.call(document.querySelectorAll("[data-modal]")).forEach(function(t){ t.addEventListener("click", function(){ var id=t.getAttribute("data-modal"); openModal(id); if(t.getAttribute("data-require-open")==="1"){ openSeen[id]=true; updateProgress(); } }); });
      Object.keys(modals).forEach(function(id){ var m=modals[id]; m.addEventListener("click", function(e){ if(e.target===m)closeModal(m); });
        var c=m.querySelector(".nv-modal-close"); if(c)c.addEventListener("click", function(){ closeModal(m); });
        m.addEventListener("keydown", function(e){ if(e.key!=="Tab")return; var f=m.querySelectorAll("button, a[href], video, audio, [tabindex]"); if(!f.length)return; var first=f[0],last=f[f.length-1];
          if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();} else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();} }); });
      document.addEventListener("keydown", function(e){ if(e.key==="Escape")closeModal(document.querySelector(".nv-modal:not([hidden])")); });

      media.forEach(function(el,i){ el.addEventListener("ended", function(){ mediaSeen["m"+i]=true; updateProgress(); }); });
      gates.forEach(function(gate,i){ var b=gate.querySelector(".nv-btn"); if(!b)return; b.addEventListener("click", function(){ passGate(gate,i); var r=revealAfter(gate); updateProgress(); (r||gate).scrollIntoView({behavior:"smooth",block:"start"}); }); });
      kcs.forEach(function(kc,i){ var opts=Array.prototype.slice.call(kc.querySelectorAll(".nv-kc-opt")), fb=kc.querySelector(".nv-kc-fb");
        opts.forEach(function(opt,oi){ opt.addEventListener("click", function(){
          if (kcSeen[i] || opt.classList.contains("is-disabled")) return;        // terminal, or an eliminated wrong choice
          kcTries[i] = (kcTries[i]||0) + 1;
          var ok = opt.dataset.correct === "1";
          if (ok || !maxTries || kcTries[i] >= maxTries) { lockKc(kc,i,oi,ok); updateProgress(); }   // terminal
          else {                                                                  // retry: eliminate this choice, prompt again
            opt.classList.add("incorrect","is-disabled");
            if (fb){ var left = maxTries - kcTries[i];
              fb.innerHTML = (fb.getAttribute("data-fb-incorrect") || "Not quite.") +
                ' <em class="nv-kc-retry">Try again — ' + left + ' attempt' + (left===1?'':'s') + ' left.</em>';
              fb.classList.remove("ok"); fb.classList.add("show","no"); }
          }
        }); }); });

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
        loc = resumed.loc || null; restoring = false;
        if (loc){ var tgt = loc.t==="g"?gates[loc.i]:(loc.t==="kc"?kcs[loc.i]:null); if(tgt) try{ tgt.scrollIntoView({block:"start"}); }catch(e){} }
      }

      updateProgress();
      window.addEventListener("pagehide", function(){ if (RT) RT.quit(); });
      window.addEventListener("beforeunload", function(){ if (RT) RT.quit(); });
    });
  });
})();
