// The board: keeps itself fresh, counts the clocks down, sends the three actions,
// and pulses a card once when a second report joins it (the only animation on the page).
// No framework and no build step. The page is complete without this script.
(function () {
  "use strict";
  var board = document.getElementById("board");
  var message = document.getElementById("board-message");
  var announcer = document.getElementById("board-announcer");
  var offset = 0; // server clock minus this screen's clock, in milliseconds

  function settings() {
    var holder = document.querySelector("[data-now]");
    if (!holder) { return; }
    offset = new Date(holder.getAttribute("data-now")).getTime() - Date.now();
    // The size of the type is set on the operator page, for the hall.
    if (holder.getAttribute("data-scale")) {
      document.documentElement.style.setProperty("--board-scale", holder.getAttribute("data-scale"));
    }
  }

  function two(n) { return (n < 10 ? "0" : "") + n; }

  function tick() {
    var now = Date.now() + offset;
    var clocks = document.querySelectorAll(".countdown");
    for (var i = 0; i < clocks.length; i++) {
      var left = Math.round((new Date(clocks[i].getAttribute("data-due")).getTime() - now) / 1000);
      var late = left < 0;
      var s = Math.abs(left);
      var text = (s >= 3600 ? Math.floor(s / 3600) + ":" : "") + two(Math.floor((s % 3600) / 60)) + ":" + two(s % 60);
      clocks[i].textContent = late ? clocks[i].getAttribute("data-late") + " " + text : text;
      clocks[i].classList.toggle("late", late);
    }
    var clock = document.getElementById("clock");
    if (clock) { var d = new Date(now); clock.textContent = two(d.getHours()) + ":" + two(d.getMinutes()); }
  }

  function say(text) {
    if (!message) { return; }
    message.textContent = text || "";
    message.hidden = !text;
  }

  // What is on the board now: case number -> state, report count, and what a screen reader is told.
  function snapshot() {
    var seen = {};
    var cases = board.querySelectorAll("article[data-case]");
    for (var i = 0; i < cases.length; i++) {
      seen[cases[i].getAttribute("data-case")] = {
        state: cases[i].getAttribute("data-state"), label: cases[i].getAttribute("aria-label"),
        stateLabel: cases[i].getAttribute("data-state-label"), count: Number(cases[i].getAttribute("data-count"))
      };
    }
    return seen;
  }

  // Only what changed is announced: a new case, or a case that moved to another state.
  function announce(before, after) {
    if (!announcer) { return; }
    var news = [];
    for (var id in after) {
      if (!before[id]) { news.push(window.RASD.newCase + ": " + after[id].label); }
      else if (before[id].state !== after[id].state) { news.push(after[id].label + ". " + window.RASD.movedTo + " " + after[id].stateLabel); }
    }
    if (news.length) { announcer.textContent = news.join(". "); }
  }

  // The merge moment: a card whose report count just grew pulses once. The stamp itself is in the page.
  function pulse(before, after) {
    for (var id in after) {
      if (before[id] && after[id].count > before[id].count) {
        var card = board.querySelector('article[data-case="' + id + '"]');
        if (card) { card.classList.add("just-merged"); }
      }
    }
  }

  var lastDrawn = null;
  var pressing = false; // a finger or the mouse is down on the board: do not re-draw under it

  function refresh() {
    if (!board || pressing) { return; }
    fetch("/board/fragment").then(function (r) { return r.text(); }).then(function (html) {
      if (message && message.textContent === window.RASD.connectionLost) { say(""); }
      var stable = html.replace(/data-now="[^"]*"/, "").replace(/<time id="clock"[^<]*<\/time>/, "");
      if (stable === lastDrawn || pressing) { return; } // nothing changed: leave the page alone
      lastDrawn = stable;
      // Keep the keyboard where it was: the same button of the same case gets the focus back.
      var active = document.activeElement;
      var keep = active && board.contains(active) && active.getAttribute("data-case")
        ? 'button[data-case="' + active.getAttribute("data-case") + '"][data-action="' + active.getAttribute("data-action") + '"]'
        : null;
      var before = snapshot();
      board.innerHTML = html;
      if (keep && board.querySelector(keep)) { board.querySelector(keep).focus(); }
      var after = snapshot();
      announce(before, after);
      pulse(before, after);
      settings();
      tick();
    }).catch(function () { say(window.RASD.connectionLost); });
  }

  if (board) {
    // The name that signs an action is written once on the operator page; the server knows it.
    board.addEventListener("click", function (event) {
      var button = event.target.closest("button[data-action]");
      if (!button) { return; }
      button.disabled = true;
      fetch("/api/cases/" + button.getAttribute("data-case") + "/" + button.getAttribute("data-action"), { method: "POST" })
        .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
        .then(function (result) {
          say(result.ok ? "" : ((result.data && result.data.message) || window.RASD.wrong));
          button.disabled = false;
          refresh();
        })
        .catch(function () { say(window.RASD.connectionLost); button.disabled = false; });
    });
    board.addEventListener("pointerdown", function () {
      pressing = true;
      setTimeout(function () { pressing = false; }, 3000); // a finger that never lifts must not stop the board
    });
    document.addEventListener("pointerup", function () { pressing = false; });
    document.addEventListener("pointercancel", function () { pressing = false; });
    setInterval(refresh, (window.RASD && window.RASD.refreshMs) || 1000);
  }
  settings();
  tick();
  setInterval(tick, 1000);
})();
