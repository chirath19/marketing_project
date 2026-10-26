/* Preserve a failed chat draft and report transport errors in the workspace. */
(function () {
  "use strict";
  function feedback(event, text) {
    var form = event.detail.elt;
    if (!form || !form.matches("[data-chat-form]")) return;
    var status = form.querySelector("[data-chat-feedback]");
    if (status) status.textContent = text;
  }
  document.addEventListener("htmx:beforeRequest", function (event) { feedback(event, "Sending…"); });
  document.addEventListener("htmx:responseError", function (event) {
    feedback(event, "Your message could not be confirmed. Your draft is still here; please try again.");
  });
  document.addEventListener("htmx:sendError", function (event) {
    feedback(event, "Connection lost. Your draft is still here; reconnect and try again.");
  });
}());

/* Read-only polling keeps badges current without reloading forms or marking work read. */
(function () {
  "use strict";
  var bell = document.querySelector("[data-notification-bell]");
  if (!bell) return;
  var pending = false;
  var latest = null;
  var timer;
  function apply(data) {
    document.querySelectorAll("[data-unread-kind]").forEach(function (element) {
      var count = Number(data[element.dataset.unreadKind]) || 0;
      element.classList.toggle("has-unread", count > 0);
      var badge = element.querySelector("[data-unread-count]");
      if (badge) { badge.textContent = count > 99 ? "99+" : String(count); badge.hidden = !count; }
      if (element.hasAttribute("data-notification-bell")) {
        element.setAttribute("aria-label", "Notifications" + (count ? ", " + count + " unread" : ", no unread updates"));
      }
    });
    document.querySelectorAll("[data-message-thread]").forEach(function (element) {
      var count = (data.message_threads || {})[element.dataset.messageThread] || 0;
      element.classList.toggle("unread-highlight", count > 0);
      var label = element.querySelector("[data-thread-label]");
      var badge = element.querySelector("[data-thread-count]");
      if (label) label.hidden = !count;
      if (badge) badge.textContent = String(count);
    });
    if (latest !== null && data.latest_id > latest) {
      var announcement = document.querySelector("[data-activity-announcement]");
      if (announcement) announcement.textContent = "New activity. " + data.notifications + " unread notifications.";
    }
    latest = data.latest_id || 0;
  }
  async function refresh() {
    if (pending || document.visibilityState !== "visible") return;
    pending = true;
    var controller = new AbortController();
    var timeout = setTimeout(function () { controller.abort(); }, 8000);
    try {
      var response = await fetch(bell.dataset.summaryUrl, {credentials: "same-origin", cache: "no-store", signal: controller.signal, headers: {"Accept": "application/json"}});
      if (response.ok && !response.redirected) apply(await response.json());
    } catch (_) { /* Keep the last verified counts during a network interruption. */ }
    finally { clearTimeout(timeout); pending = false; }
  }
  document.addEventListener("visibilitychange", refresh);
  window.addEventListener("focus", refresh);
  document.addEventListener("htmx:afterSwap", refresh);
  window.addEventListener("pagehide", function () { clearInterval(timer); });
  window.addEventListener("pageshow", function () {
    clearInterval(timer); timer = setInterval(refresh, 10000); refresh();
  });
  refresh();
}());

/* All conversation surfaces use the same controls and scoped refresh behavior. */
(function () {
  "use strict";
  var snapshots = new Map();
  function bottom(feed) { if (feed) feed.scrollTo({top: feed.scrollHeight, behavior: "instant"}); }
  function search(chat) {
    var input = chat.querySelector("[data-chat-search]");
    var query = input.value.trim().toLocaleLowerCase();
    var rows = chat.querySelectorAll("[data-chat-entry]");
    var matches = 0;
    rows.forEach(function (row) {
      var visible = !query || row.textContent.toLocaleLowerCase().includes(query);
      row.hidden = !visible;
      if (visible) matches++;
    });
    chat.querySelectorAll(".chat-divider, .chat-empty").forEach(function (el) { el.hidden = !!query; });
    chat.querySelector("[data-chat-search-status]").textContent = query ?
      (matches ? matches + " matching entries in loaded messages." : "No matches in loaded messages. Try another search or load older messages.") : "";
  }
  function mode(form) {
    var checked = form.querySelector("[data-chat-mode]:checked");
    var note = checked && checked.value === "note";
    var input = form.querySelector("[data-chat-input]");
    form.classList.toggle("is-note", !!note);
    form.querySelector("[data-chat-note-notice]").hidden = !note;
    input.placeholder = note ? input.dataset.placeholderNote : "Write a message…";
    form.querySelector("[data-chat-send-label]").textContent = note ? "Save note" : "Send";
    form.querySelector("button[type=submit]").setAttribute("aria-label", note ? "Save internal note" : "Send message");
  }
  function wire(chat, initial) {
    var feed = chat.querySelector("[data-chat-feed]");
    if (initial && feed) {
      var unread = feed.querySelector("[data-chat-unread]");
      if (unread) feed.scrollTop = unread.offsetTop - feed.offsetTop - 16;
      else bottom(feed);
    }
    var input = chat.querySelector("[data-chat-input]");
    if (!input || input.dataset.chatWired) return;
    input.dataset.chatWired = "1";
    var form = input.form;
    function resize() {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 160) + "px";
      var counter = form.querySelector("[data-chat-count]");
      counter.textContent = input.value.length + " / " + input.maxLength;
      counter.classList.toggle("is-near", input.value.length > input.maxLength * .9);
    }
    input.addEventListener("input", resize);
    input.addEventListener("keydown", function (event) {
      if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
      event.preventDefault();
      if (input.value.trim() && !form.querySelector("button[type=submit]").disabled) form.requestSubmit();
    });
    form.addEventListener("submit", function (event) {
      if (!input.value.trim()) {
        event.preventDefault();
        form.querySelector("[data-chat-feedback]").textContent = "Write a message before sending.";
        input.focus();
      }
    });
    mode(form);
    resize();
  }
  document.addEventListener("input", function (event) {
    if (event.target.matches("[data-chat-search]")) search(event.target.closest("[data-chat]"));
    if (event.target.matches("[data-chat-contact-search]")) {
      var query = event.target.value.trim().toLocaleLowerCase();
      var visible = 0;
      document.querySelectorAll("[data-chat-contact]").forEach(function (row) {
        row.hidden = !row.textContent.toLocaleLowerCase().includes(query);
        if (!row.hidden) visible++;
      });
      document.querySelector("[data-chat-contact-status]").textContent = query ?
        (visible ? visible + " matching clients" : "No clients match your search.") : "";
    }
  });
  document.addEventListener("change", function (event) {
    if (event.target.matches("[data-chat-mode]")) {
      mode(event.target.form);
      event.target.form.querySelector("[data-chat-input]").focus();
    }
  });
  document.addEventListener("click", async function (event) {
    var control = event.target.closest("[data-chat-latest], [data-chat-expand], [data-chat-copy]");
    if (!control) return;
    var chat = control.closest("[data-chat]");
    if (control.matches("[data-chat-latest]")) {
      chat.querySelector("[data-chat-search]").value = "";
      search(chat);
      bottom(chat.querySelector("[data-chat-feed]"));
    } else if (control.matches("[data-chat-expand]")) {
      var expanded = chat.classList.toggle("is-expanded");
      control.setAttribute("aria-pressed", String(expanded));
      control.setAttribute("aria-label", expanded ? "Reduce conversation" : "Expand conversation");
      control.title = expanded ? "Reduce conversation" : "Expand conversation";
    } else {
      try {
        await navigator.clipboard.writeText(control.closest(".chat-bubble").querySelector(".chat-body").textContent);
        chat.querySelector("[data-chat-search-status]").textContent = "Message copied.";
      } catch (_) {
        chat.querySelector("[data-chat-search-status]").textContent = "Copy is unavailable. Select the message text to copy it.";
      }
    }
  });
  document.addEventListener("htmx:beforeSwap", function (event) {
    var target = event.detail.target;
    var chat = target && target.closest("[data-chat]");
    if (!chat) return;
    var feed = chat.querySelector("[data-chat-feed]");
    var request = event.detail.requestConfig;
    if (request && request.verb === "get" && event.detail.xhr.status === 200) {
      var incoming = new DOMParser().parseFromString(event.detail.xhr.responseText, "text/html").getElementById(feed.id);
      function content(element) {
        var copy = element.cloneNode(true);
        copy.querySelectorAll("[data-chat-entry], .chat-divider, .chat-empty").forEach(function (row) {
          row.removeAttribute("hidden");
        });
        return copy.innerHTML;
      }
      if (incoming && content(incoming) === content(feed)) {
        event.detail.shouldSwap = false;
        return;
      }
    }
    snapshots.set(chat.id, {
      sent: event.detail.requestConfig && event.detail.requestConfig.verb === "post",
      stick: feed.scrollHeight - feed.scrollTop - feed.clientHeight < 96,
      top: feed.scrollTop, count: feed.querySelectorAll("[data-chat-entry]").length,
      expanded: chat.classList.contains("is-expanded")
    });
  });
  document.addEventListener("htmx:afterSwap", function () {
    snapshots.forEach(function (state, id) {
      var chat = document.getElementById(id);
      if (!chat) return;
      var feed = chat.querySelector("[data-chat-feed]");
      wire(chat, false);
      if (state.expanded) {
        chat.classList.add("is-expanded");
        var expand = chat.querySelector("[data-chat-expand]");
        expand.setAttribute("aria-pressed", "true");
        expand.setAttribute("aria-label", "Reduce conversation");
      }
      search(chat);
      if (state.sent) {
        bottom(feed);
        var input = chat.querySelector("[data-chat-input]");
        if (input) input.focus({preventScroll: true});
      } else if (state.stick) bottom(feed);
      else {
        feed.scrollTop = state.top;
        if (!chat.querySelector("[data-chat-search]").value && feed.querySelectorAll("[data-chat-entry]").length > state.count) {
          chat.querySelector("[data-chat-search-status]").textContent = "New messages below. Choose Latest to read them.";
        }
      }
    });
    snapshots.clear();
  });
  function init() { document.querySelectorAll("[data-chat]").forEach(function (chat) { wire(chat, true); }); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
}());

/* Open the invoice editor from its primary action, including direct fragment links. */
(function () {
  function open(id) {
    var panel = document.getElementById(id);
    if (panel && panel.tagName === "DETAILS") panel.open = true;
  }
  document.addEventListener("click", function (event) {
    var link = event.target.closest("[data-billing-open]");
    if (link) open(link.dataset.billingOpen);
  });
  if (location.hash) open(location.hash.slice(1));
}());
