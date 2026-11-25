// The board: keeps the page fresh, counts the clocks down, and sends the three actions.
// No framework and no build step. Works without it too: the page is complete when first loaded.
(function () {
  "use strict";
  var board = document.getElementById("board");
  var message = document.getElementById("board-message");
  var who = document.getElementById("who");
  var announcer = document.getElementById("board-announcer");
  var offset = 0; // server clock minus this device's clock, in milliseconds

  function setOffset() {
    var holder = document.querySelector("[data-now]");
    if (holder) { offset = new Date(holder.getAttribute("data-now")).getTime() - Date.now(); }
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
  }

  function say(text) {
    if (!message) { return; }
    message.textContent = text || "";
    message.hidden = !text;
  }

  // What is on the board now: case number -> [state, what a screen reader is told about the case].
  function snapshot() {
    var seen = {};
    var cases = board.querySelectorAll("article[data-case]");
    for (var i = 0; i < cases.length; i++) {
      seen[cases[i].getAttribute("data-case")] = [
        cases[i].getAttribute("data-state"), cases[i].getAttribute("aria-label"), cases[i].getAttribute("data-state-label")
      ];
    }
    return seen;
  }

  // Only what changed is announced: a new case, or a case that moved to another column.
  function announce(before, after) {
    if (!announcer) { return; }
    var news = [];
    for (var id in after) {
      if (!before[id]) { news.push(window.RASD.newCase + ": " + after[id][1]); }
      else if (before[id][0] !== after[id][0]) { news.push(after[id][1] + ". " + window.RASD.movedTo + " " + after[id][2]); }
    }
    if (news.length) { announcer.textContent = news.join(". "); }
  }

  var lastDrawn = null;
  var pressing = false; // a finger or the mouse is down on the board: do not re-draw under it

  function refresh() {
    if (!board || pressing) { return; }
    fetch("/board/fragment").then(function (r) { return r.text(); }).then(function (html) {
      if (message && message.textContent === window.RASD.connectionLost) { say(""); }
      var stable = html.replace(/data-now="[^"]*"/, "");
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
      announce(before, snapshot());
      setOffset();
      tick();
    }).catch(function () { say(window.RASD.connectionLost); });
  }

  // The size of the type, for the hall: the operator sets it once and the browser remembers it.
  var scale = 1;
  function setScale(value) {
    scale = Math.min(2, Math.max(0.7, Math.round(value * 10) / 10));
    document.documentElement.style.setProperty("--board-scale", scale);
    try { localStorage.setItem("rasd-board-scale", scale); } catch (e) { /* private mode */ }
  }
  try { if (localStorage.getItem("rasd-board-scale")) { setScale(parseFloat(localStorage.getItem("rasd-board-scale")) || 1); } } catch (e) { /* private mode */ }
  var larger = document.getElementById("larger");
  var smaller = document.getElementById("smaller");
  if (larger) { larger.addEventListener("click", function () { setScale(scale + 0.1); }); }
  if (smaller) { smaller.addEventListener("click", function () { setScale(scale - 0.1); }); }

  if (who) {
    try { who.value = localStorage.getItem("rasd-who") || ""; } catch (e) { /* private mode */ }
    who.addEventListener("change", function () {
      try { localStorage.setItem("rasd-who", who.value); } catch (e) { /* private mode */ }
    });
  }

  if (board) {
    board.addEventListener("click", function (event) {
      var button = event.target.closest("button[data-action]");
      if (!button) { return; }
      if (!who.value.trim()) { say(window.RASD.nameNeeded); who.focus(); return; }
      button.disabled = true;
      var body = new FormData();
      body.append("who", who.value.trim());
      fetch("/api/cases/" + button.getAttribute("data-case") + "/" + button.getAttribute("data-action"), { method: "POST", body: body })
        .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
        .then(function (result) { say(result.ok ? "" : result.data.message); button.disabled = false; refresh(); })
        .catch(function () { say(window.RASD.connectionLost); button.disabled = false; });
    });
    board.addEventListener("pointerdown", function () { pressing = true; });
    document.addEventListener("pointerup", function () { pressing = false; });
    document.addEventListener("pointercancel", function () { pressing = false; });
    setInterval(refresh, 2000);
  }
  setOffset();
  tick();
  setInterval(tick, 1000);
})();
