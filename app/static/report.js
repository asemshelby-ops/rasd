// The reporting page: a chat with Rasd. Text, voice note, a photo of the pilgrim, the mock card.
// No framework and no build step.
(function () {
  "use strict";
  var T = window.RASD;
  var chat = document.getElementById("chat");
  var form = document.getElementById("composer");
  var text = document.getElementById("text");
  var hotel = document.getElementById("hotel");
  var photo = document.getElementById("pilgrim-photo");
  var card = document.getElementById("card-photo");
  var cardButton = document.getElementById("card-button");
  var record = document.getElementById("record");
  var message = document.getElementById("report-message");
  var lastCase = null;

  function say(words) { message.textContent = words || ""; message.hidden = !words; }

  function bubble(words, mine) {
    var li = document.createElement("li");
    li.className = "bubble " + (mine ? "mine" : "theirs");
    li.setAttribute("dir", "auto");
    li.textContent = words;
    chat.appendChild(li);
    li.scrollIntoView({ block: "end" });
    return li;
  }

  function post(url, body) {
    return fetch(url, { method: "POST", body: body }).then(function (r) {
      return r.json().then(function (data) { return { ok: r.ok, data: data }; });
    });
  }

  function show(result, retry) {
    if (!result.ok) { say(result.data.message); return; }
    say("");
    var data = result.data;
    if (data.heard) { bubble(T.heard + ": " + data.heard, true); }
    var reply = bubble(data.message, false);
    if (data.identified) { cardButton.hidden = true; return; }
    if (data.case_id) { lastCase = data.case_id; }
    if (data.type === "lost_pilgrim") { cardButton.hidden = false; }
    if (data.question) { ask(reply, data); }
  }

  function ask(reply, data) {
    var box = document.createElement("div");
    box.className = "options";
    var question = document.createElement("strong");
    question.textContent = data.question.text;
    reply.appendChild(document.createElement("br"));
    reply.appendChild(question);
    function send(value) {
      var body = new FormData();
      body.append("reply", value);
      bubble(value, true);
      box.remove();
      post("/api/reports/" + data.report_id + "/answer", body).then(show).catch(failed);
    }
    if (data.question.options.length) {
      data.question.options.forEach(function (option) {
        var button = document.createElement("button");
        button.type = "button";
        button.textContent = option;
        button.addEventListener("click", function () { send(option); });
        box.appendChild(button);
      });
    } else {
      var input = document.createElement("input");
      input.type = "text";
      input.setAttribute("aria-label", data.question.text);
      var ok = document.createElement("button");
      ok.type = "button";
      ok.textContent = "أرسل الرد";
      ok.addEventListener("click", function () { if (input.value.trim()) { send(input.value.trim()); } });
      box.appendChild(input);
      box.appendChild(ok);
    }
    reply.appendChild(box);
  }

  function failed() { say(T.sendFailed); }

  // A phone photo is several megabytes: too slow over a hotspot and too large for the card reader.
  // It is made smaller on the phone before it is sent. If that cannot be done, the photo goes as it is.
  function shrink(file, done) {
    var limit = 1600;
    if (!window.URL || !URL.createObjectURL || !/^image\//.test(file.type)) { done(file); return; }
    var picture = new Image();
    var address = URL.createObjectURL(file);
    picture.onerror = function () { URL.revokeObjectURL(address); done(file); };
    picture.onload = function () {
      URL.revokeObjectURL(address);
      var scale = Math.min(1, limit / Math.max(picture.width, picture.height));
      var canvas = document.createElement("canvas");
      canvas.width = Math.round(picture.width * scale);
      canvas.height = Math.round(picture.height * scale);
      try {
        canvas.getContext("2d").drawImage(picture, 0, 0, canvas.width, canvas.height);
        canvas.toBlob(function (small) { done(small || file); }, "image/jpeg", 0.85);
      } catch (e) { done(file); }
    };
    picture.src = address;
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var words = text.value.trim();
    var file = photo.files[0];
    if (!words && !file) { say(T.empty); text.focus(); return; }
    var body = new FormData();
    body.append("text", words);
    body.append("hotel", hotel.value);
    bubble((file ? "📷 " : "") + words, true);
    text.value = "";
    photo.value = "";
    if (!file) { post("/api/reports", body).then(show).catch(failed); return; }
    shrink(file, function (small) {
      body.append("pilgrim_photo", small, "photo.jpg");
      post("/api/reports", body).then(show).catch(failed);
    });
  });

  card.addEventListener("change", function () {
    if (!card.files[0] || !lastCase) { return; }
    var chosen = card.files[0];
    bubble("📷 " + T.mockCard, true);
    card.value = "";
    shrink(chosen, function (small) {
      var body = new FormData();
      body.append("photo", small, "card.jpg");
      post("/api/cases/" + lastCase + "/card", body).then(function (result) {
        show(result);
        if (result.ok && result.data.notification) { bubble(result.data.notification, false); }
      }).catch(failed);
    });
  });

  // Voice: a phone browser only lets a page record on a secure connection. When it does not,
  // the button says so and the sender types instead.
  var recorder = null;
  var pieces = [];
  record.addEventListener("click", function () {
    if (recorder) { recorder.stop(); return; }
    if (!navigator.mediaDevices || !window.MediaRecorder) { say(T.micBlocked); return; }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      pieces = [];
      recorder = new MediaRecorder(stream);
      recorder.ondataavailable = function (e) { pieces.push(e.data); };
      recorder.onstop = function () {
        stream.getTracks().forEach(function (track) { track.stop(); });
        var body = new FormData();
        body.append("hotel", hotel.value);
        body.append("audio", new Blob(pieces, { type: recorder.mimeType }), "note.webm");
        recorder = null;
        record.textContent = T.record;
        bubble("🎤 …", true);
        post("/api/voice", body).then(show).catch(failed);
      };
      recorder.start();
      record.textContent = T.stopAndSend;
    }).catch(function () { say(T.micBlocked); });
  });

  // Used by the demo panel (stage 4) to send a saved voice note or the mock card.
  window.rasdShow = show;
  window.rasdBubble = bubble;
  window.rasdCase = function () { return lastCase; };
})();
