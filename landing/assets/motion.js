/* ============================================================================
   motion.js — Top Builder OS site-wide motion engine (2026-08-13)

   Companion to motion.css. Progressive enhancement only: every page reads
   perfectly with this file missing, blocked, or on a reduced-motion device.
   The reduced/no-JS experience is always the FINISHED state.
   ========================================================================== */
(function () {
  "use strict";
  var docEl = document.documentElement;
  docEl.classList.add("js-motion"); // gates the icon draw-in dasharray in CSS

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- reveal engine (idempotent beside any per-page engine) ------ */
  // Stagger: siblings that reveal together rise 70ms apart instead of as one
  // block. Delay is assigned once, from DOM order, never from timers.
  var reveals = Array.prototype.slice.call(document.querySelectorAll(".reveal"));
  reveals.forEach(function (el, i) {
    if (!el.style.transitionDelay) {
      var sibs = el.parentElement
        ? Array.prototype.filter.call(el.parentElement.children, function (c) {
            return c.classList && c.classList.contains("reveal");
          })
        : [el];
      var idx = sibs.indexOf(el);
      if (idx > 0) el.style.transitionDelay = Math.min(idx * 70, 420) + "ms";
    }
  });
  if (!reduced && "IntersectionObserver" in window) {
    var io = new IntersectionObserver(
      function (entries, obs) {
        entries.forEach(function (e) {
          if (e.isIntersecting) { e.target.classList.add("in"); obs.unobserve(e.target); }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
    );
    reveals.forEach(function (el) { io.observe(el); });
  } else {
    reveals.forEach(function (el) { el.classList.add("in"); });
  }

  /* ---------- proof marquee (homepage opt-in: <body data-marquee>) ------- */
  var mqHost = document.body.hasAttribute("data-marquee") &&
               (document.querySelector(".hero .wrap") || document.querySelector(".hero"));
  if (mqHost && !document.querySelector(".mq")) {
    var items =
      "<span>One bill replaces the stack</span><span>Field + books on one ledger</span>" +
      "<span>Migration verified to the penny</span><span>30-day money-back guarantee</span>" +
      "<span>Your CPA’s seat is free</span><span>Month-to-month, export forever</span>";
    var mq = document.createElement("div");
    mq.className = "mq";
    mq.setAttribute("aria-hidden", "true");
    // content doubled for the seamless -50% wrap
    mq.innerHTML = '<div class="mq-track">' + items + items + "</div>";
    mqHost.appendChild(mq);
  }

  /* ---------- count-up for demo money tiles ------------------------------ */
  function countUp(el, ms) {
    var target = parseInt(el.getAttribute("data-count"), 10);
    if (isNaN(target)) return;
    var prefix = el.getAttribute("data-prefix") || "";
    if (reduced) { el.textContent = prefix + target.toLocaleString("en-US"); return; }
    var t0 = null;
    function frame(t) {
      if (!t0) t0 = t;
      var k = Math.min((t - t0) / ms, 1);
      k = 1 - Math.pow(1 - k, 3); // easeOutCubic
      el.textContent = prefix + Math.round(target * k).toLocaleString("en-US");
      if (k < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  /* ---------- the platform demo sequencer -------------------------------- */
  // Phases are cumulative on .demo-stage:
  //   p1: a booked job lands on dispatch
  //   p2: the money rail counts up
  //   p3: the invoice flips to PAID + toast
  //   p4: the bank line arrives already matched
  // The demo is INTERACTIVE: the .demo-steps rail below the frame both
  // indicates the running phase and, on click, jumps the story there and
  // pauses the auto-loop for the rest of the visit (a reader mid-thought
  // must never have the story advance out from under them).
  // Reduced motion: no sequencing — CSS shows the finished story; the rail
  // still highlights the clicked explanation.
  var stage = document.querySelector(".demo-stage");
  if (stage) {
    var phases = ["p1", "p2", "p3", "p4"];
    var stepBtns = document.querySelectorAll(".demo-steps .dstep");
    var STEP = 2600, HOLD = 3800, i = 0, timer = null, counted = false, paused = false;

    // one state-setter: the stage shows exactly phases 1..n
    function applyPhases(n) {
      phases.forEach(function (p, idx) { stage.classList.toggle(p, idx < n); });
      if (n >= 2 && !counted) {
        counted = true;
        Array.prototype.forEach.call(stage.querySelectorAll("[data-count]"), function (el) {
          countUp(el, 1400);
        });
      } else if (n < 2 && counted) {
        counted = false;
        Array.prototype.forEach.call(stage.querySelectorAll("[data-count]"), function (el) {
          el.textContent = (el.getAttribute("data-prefix") || "") + "0";
        });
      }
      Array.prototype.forEach.call(stepBtns, function (b, idx) {
        var on = idx === n - 1;
        b.classList.toggle("on", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });
    }

    Array.prototype.forEach.call(stepBtns, function (b, idx) {
      b.addEventListener("click", function () {
        paused = true;
        if (timer) { clearTimeout(timer); timer = null; }
        i = idx + 1;
        applyPhases(i);
      });
    });

    if (!reduced) {
      var tick = function () {
        if (i < phases.length) {
          i++;
          applyPhases(i);
          timer = setTimeout(tick, i === phases.length ? HOLD : STEP);
        } else {
          // hold the finished story, then restart the loop
          i = 0;
          applyPhases(0);
          timer = setTimeout(tick, 900);
        }
      };
      // run only while visible; pause (and freeze cleanly) off screen
      var seen = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) { if (!timer && !paused) timer = setTimeout(tick, 500); }
          else if (timer) { clearTimeout(timer); timer = null; }
        });
      }, { threshold: 0.35 });
      seen.observe(stage);
    } else {
      Array.prototype.forEach.call(stage.querySelectorAll("[data-count]"), function (el) {
        countUp(el, 0);
      });
    }
  }
})();
