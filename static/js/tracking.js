/*
 * Consent and agency website event tracking.
 *
 * Two jobs, kept in one small file because they are genuinely coupled —
 * neither a tag nor an event beacon may fire before consent is recorded.
 *
 * Consent is stored in localStorage only: a per-browser convenience, not
 * data this platform reads back or relies on server-side. Nothing here
 * is sent anywhere until a category is accepted. Necessary cookies (the
 * session, CSRF) are not covered by this and are never gated — the same
 * way they are not gated anywhere else on the web.
 *
 * `window.hgConsent` is the small public surface other scripts (a GTM
 * container, if one is loaded) can check: `hgConsent.has('analytics')`.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "hg_consent_v1";
  var CATEGORIES = ["analytics", "advertising"];

  function readConsent() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function writeConsent(value) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    } catch (e) {
      /* Private browsing or a blocked store: consent simply is not
         remembered between visits, and the banner asks again. That is a
         safe failure — it cannot mean tracking without consent. */
    }
  }

  var consent = readConsent();

  window.hgConsent = {
    has: function (category) {
      return !!(consent && consent[category]);
    },
    decided: function () {
      return consent !== null;
    },
    set: function (value) {
      consent = value;
      writeConsent(consent);
      document.dispatchEvent(new CustomEvent("hg:consent-changed", { detail: consent }));
    },
    acceptAll: function () {
      var value = {};
      CATEGORIES.forEach(function (c) { value[c] = true; });
      this.set(value);
    },
    rejectAll: function () {
      var value = {};
      CATEGORIES.forEach(function (c) { value[c] = false; });
      this.set(value);
    },
  };

  /* --- the funnel event beacon -------------------------------------- */

  function utmParam(name) {
    try {
      return new URLSearchParams(window.location.search).get(name) || "";
    } catch (e) {
      return "";
    }
  }

  function send(eventName, context) {
    if (!window.hgConsent.has("analytics")) return;

    var body = JSON.stringify({
      event: eventName,
      path: window.location.pathname,
      referrer: document.referrer || "",
      utm_source: utmParam("utm_source"),
      utm_medium: utmParam("utm_medium"),
      utm_campaign: utmParam("utm_campaign"),
      context: context || "",
    });

    var endpoint = "/t/event/";
    if (navigator.sendBeacon) {
      navigator.sendBeacon(endpoint, new Blob([body], { type: "application/json" }));
    } else {
      fetch(endpoint, { method: "POST", body: body, keepalive: true,
        headers: { "Content-Type": "application/json" } });
    }
  }

  window.hgTrack = send;

  document.addEventListener("DOMContentLoaded", function () {
    send("page_view");

    document.querySelectorAll("[data-hg-event]").forEach(function (el) {
      el.addEventListener("click", function () {
        send(el.getAttribute("data-hg-event"), el.getAttribute("data-hg-context") || "");
      }, { passive: true });
    });
  });

  /* A visitor who accepts analytics mid-visit still gets this page's view
     counted, rather than waiting for their next page load. */
  document.addEventListener("hg:consent-changed", function () {
    if (window.hgConsent.has("analytics")) send("page_view");
  });
})();
