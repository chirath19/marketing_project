/* Public-site enhancements. Native links, disclosures and forms work without JS. */
(function () {
  "use strict";
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  function frame(fn) {
    var queued = false;
    return function () {
      if (queued) return;
      queued = true;
      requestAnimationFrame(function () { queued = false; fn(); });
    };
  }
  function start() {
    var header = document.querySelector("[data-site-header]");
    var progress = document.querySelector("[data-site-progress]");
    var update = frame(function () {
      if (header) header.dataset.scrolled = window.scrollY > 12 ? "true" : "false";
      if (progress) {
        var article = document.querySelector(".site-article-body");
        var start = article ? article.offsetTop : 0;
        var length = article ? article.offsetHeight - innerHeight : document.documentElement.scrollHeight - innerHeight;
        var ratio = length > 0 ? (scrollY - start) / length : 1;
        progress.style.setProperty("--progress", Math.min(1, Math.max(0, ratio)));
      }
    });
    update();
    window.addEventListener("scroll", update, {passive: true});
    window.addEventListener("resize", update, {passive: true});

    // Content is visible before, during and after a failed script load.
    // One entrance translation per element; no perpetual ambient animation.
    if (!reduced.matches && "IntersectionObserver" in window) {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-entering");
          entry.target.addEventListener("animationend", function () {
            entry.target.classList.remove("is-entering");
          }, {once: true});
          observer.unobserve(entry.target);
        });
      }, {threshold: 0.08});
      document.querySelectorAll("[data-reveal]").forEach(function (el) { observer.observe(el); });
      reduced.addEventListener("change", function (event) {
        if (event.matches) observer.disconnect();
      });
    }

    // --- Hero motion -----------------------------------------------------
    // Two enhancements on the home stage, both of which the page is
    // complete without: the glass stack leans towards the pointer and
    // drifts on scroll, and the proof figures count up the first time
    // they are seen. Everything writes a CSS custom property and lets
    // the compositor do the work; neither runs under reduced motion.
    if (!reduced.matches) {
      var stack = document.querySelector("[data-parallax]");
      if (stack) {
        var stage = stack.closest(".site-hero-stage") || stack;
        var tilt = frame(function () {
          stack.style.setProperty("--tilt-x", tilt.x.toFixed(3));
          stack.style.setProperty("--tilt-y", tilt.y.toFixed(3));
        });
        tilt.x = 0;
        tilt.y = 0;
        stage.addEventListener("pointermove", function (event) {
          if (event.pointerType !== "mouse") return;
          var box = stage.getBoundingClientRect();
          // −1 … 1 from the centre of the stage, so the lean is
          // proportional however wide the viewport is.
          tilt.x = (event.clientX - box.left) / box.width * 2 - 1;
          tilt.y = (event.clientY - box.top) / box.height * 2 - 1;
          tilt();
        }, {passive: true});
        stage.addEventListener("pointerleave", function () {
          tilt.x = 0; tilt.y = 0; tilt();
        }, {passive: true});

        var drift = frame(function () {
          // Clamped so the picture cannot wander off its own frame on a
          // long page or a short one.
          var ratio = Math.min(1, Math.max(0, window.scrollY / (innerHeight || 1)));
          stack.style.setProperty("--parallax", ratio.toFixed(3));
        });
        drift();
        window.addEventListener("scroll", drift, {passive: true});
      }

      // A light that follows the pointer across a dark card. One
      // delegated listener for the whole page rather than one per card:
      // the catalogue puts twenty-eight of these on screen at once.
      var spotlit = null;
      var spot = frame(function () {
        if (spotlit) {
          spotlit.el.style.setProperty("--mx", spotlit.x + "%");
          spotlit.el.style.setProperty("--my", spotlit.y + "%");
        }
      });
      document.addEventListener("pointermove", function (event) {
        if (event.pointerType !== "mouse") return;
        var card = event.target.closest && event.target.closest(".site-cell");
        if (!card) { spotlit = null; return; }
        var box = card.getBoundingClientRect();
        spotlit = {
          el: card,
          x: Math.round((event.clientX - box.left) / box.width * 100),
          y: Math.round((event.clientY - box.top) / box.height * 100)
        };
        spot();
      }, {passive: true});

      var counters = document.querySelectorAll("[data-count-to]");
      if (counters.length && "IntersectionObserver" in window) {
        var countWatcher = new IntersectionObserver(function (entries) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            countWatcher.unobserve(entry.target);
            var target = parseInt(entry.target.dataset.countTo, 10);
            if (!isFinite(target) || target <= 0) return;
            var started = null;
            var step = function (now) {
              if (started === null) started = now;
              var t = Math.min(1, (now - started) / 900);
              // Ease out, so it decelerates into the real figure
              // rather than stopping dead on it.
              var eased = 1 - Math.pow(1 - t, 3);
              entry.target.textContent = String(Math.round(target * eased));
              if (t < 1) requestAnimationFrame(step);
              else entry.target.textContent = String(target);
            };
            requestAnimationFrame(step);
          });
        }, {threshold: 0.4});
        counters.forEach(function (el) { countWatcher.observe(el); });
      }
    }

    // Non-modal native disclosure: keyboard and no-JS navigation are built in.
    var menu = document.querySelector("[data-site-menu]");
    if (menu) {
      var summary = menu.querySelector("summary");
      document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && menu.open) { menu.open = false; summary.focus(); }
      });
      document.addEventListener("click", function (event) {
        if (!menu.contains(event.target)) menu.open = false;
      });
      menu.addEventListener("focusout", function () {
        setTimeout(function () { if (!menu.contains(document.activeElement)) menu.open = false; }, 0);
      });
      menu.querySelectorAll("a").forEach(function (link) {
        link.addEventListener("click", function () { menu.open = false; });
      });
      window.matchMedia("(min-width: 1024px)").addEventListener("change", function (event) {
        if (event.matches) menu.open = false;
      });
    }

    document.querySelectorAll(".site-form form, form.site-form").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (event.defaultPrevented) return;
        if (form.dataset.submitting === "true") { event.preventDefault(); return; }
        form.dataset.submitting = "true";
        var button = event.submitter || form.querySelector('button[type="submit"]');
        if (button) { button.classList.add("is-busy"); button.setAttribute("aria-busy", "true"); }
      });
    });

    var quoteForms = document.querySelectorAll("[data-quote-add]");
    var quoteStatus = document.querySelector("[data-quote-status]");
    var quoteBusy = false;
    function applyQuote(state) {
      quoteForms.forEach(function (form) {
        var selected = Object.prototype.hasOwnProperty.call(state.selection, form.dataset.service) &&
          (!form.dataset.package || state.selection[form.dataset.service] === form.dataset.package);
        var button = form.querySelector("[data-quote-button]");
        button.dataset.selected = String(selected);
        button.disabled = selected;
        form.querySelector("[data-quote-label]").textContent = selected ? button.dataset.addedLabel : button.dataset.idleLabel;
        form.querySelector("[data-quote-icon]").textContent = selected ? "✓" : "+";
        form.querySelector("[data-quote-review]").hidden = !selected;
      });
      document.querySelectorAll("[data-quote-count]").forEach(function (badge) {
        badge.textContent = state.count;
        badge.hidden = !state.count;
        badge.setAttribute("aria-label", state.count + " in your quote");
      });
    }
    quoteForms.forEach(function (form) {
      form.addEventListener("submit", async function (event) {
        event.preventDefault();
        var button = form.querySelector("[data-quote-button]");
        if (quoteBusy || button.dataset.selected === "true") return;
        // Session writes must finish before another card can change the quote.
        quoteBusy = true;
        quoteForms.forEach(function (other) { other.querySelector("[data-quote-button]").disabled = true; });
        button.setAttribute("aria-busy", "true");
        var error = form.querySelector("[data-quote-error]");
        error.hidden = true;
        quoteStatus.textContent = "";
        try {
          var response = await fetch(form.action, {
            method: "POST", body: new FormData(form), credentials: "same-origin",
            headers: {Accept: "application/json"}
          });
          if (response.status !== 409 && !response.ok) throw new Error("Request failed");
          var state = await response.json();
          applyQuote(state);
          if (!response.ok) {
            error.textContent = state.message;
            error.hidden = false;
          } else {
            quoteStatus.textContent = state.message;
          }
        } catch (_) {
          error.textContent = "We could not confirm this change. Please try again or check your quote.";
          error.hidden = false;
        } finally {
          quoteBusy = false;
          button.removeAttribute("aria-busy");
          quoteForms.forEach(function (other) {
            var control = other.querySelector("[data-quote-button]");
            control.disabled = control.dataset.selected === "true";
          });
        }
      });
    });
    // Back/forward navigation can restore HTML from before an item was removed.
    window.addEventListener("pageshow", function (event) {
      if (!event.persisted || !quoteStatus) return;
      fetch(quoteStatus.dataset.stateUrl, {
        headers: {Accept: "application/json"}, credentials: "same-origin", cache: "no-store"
      }).then(function (response) {
        if (!response.ok) throw new Error("Request failed");
        return response.json();
      }).then(applyQuote).catch(function () { /* The normal POST remains usable. */ });
    });
  }
  // A browser's back/forward cache retains the submitting state unless reset.
  window.addEventListener("pageshow", function () {
    document.querySelectorAll('[data-submitting="true"]').forEach(function (form) {
      delete form.dataset.submitting;
      form.querySelectorAll(".is-busy").forEach(function (button) {
        button.classList.remove("is-busy"); button.removeAttribute("aria-busy");
      });
    });
  });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
}());
