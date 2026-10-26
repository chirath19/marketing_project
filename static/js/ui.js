/*
 * Design-system behaviour.
 *
 * Alpine handles local UI state; this file supplies the few behaviours
 * that are too easy to get wrong by hand — focus trapping, returning
 * focus on close, scroll locking and a single toast region.
 *
 * Loaded before alpine.min.js so the `alpine:init` listener is registered
 * before Alpine starts. Both are deferred, which preserves document order.
 *
 * Opening is declarative: any element carrying `data-ui-open="<id>"`
 * opens the overlay with that id, and `data-ui-close` closes the overlay
 * it sits inside. Templates therefore need no inline JavaScript.
 */
(function () {
  "use strict";

  var FOCUSABLE = [
    "a[href]", "button:not([disabled])", "input:not([disabled]):not([type=hidden])",
    "select:not([disabled])", "textarea:not([disabled])", "[tabindex]:not([tabindex='-1'])"
  ].join(",");

  function focusable(root) {
    return Array.prototype.filter.call(
      root.querySelectorAll(FOCUSABLE),
      function (el) { return el.offsetParent !== null || el === document.activeElement; }
    );
  }

  /* Count open overlays so closing a dialog opened from a drawer does not
     unlock the page while the drawer is still showing. */
  var openCount = 0;

  function lockScroll() {
    openCount += 1;
    document.documentElement.style.overflow = "hidden";
  }

  function unlockScroll() {
    openCount = Math.max(0, openCount - 1);
    if (openCount === 0) document.documentElement.style.overflow = "";
  }

  /*
   * Declarative triggers.
   *
   * Django template tags only accept identifier keyword arguments, so
   * `x-on:click` cannot be passed through a component tag. Routing these
   * three actions through data attributes keeps templates free of inline
   * JavaScript and keeps the component tags usable for all of them.
   */
  document.addEventListener("click", function (event) {
    var opener = event.target.closest("[data-ui-open]");
    if (opener) {
      event.preventDefault();
      window.dispatchEvent(new CustomEvent("ui-open", {
        detail: { id: opener.getAttribute("data-ui-open") }
      }));
      return;
    }

    var closer = event.target.closest("[data-ui-close]");
    if (closer) {
      event.preventDefault();
      window.dispatchEvent(new CustomEvent("ui-close", {
        detail: { id: closer.getAttribute("data-ui-close") }
      }));
      return;
    }

    var toaster = event.target.closest("[data-ui-toast]");
    if (toaster) {
      window.dispatchEvent(new CustomEvent("ui-toast", {
        detail: {
          message: toaster.getAttribute("data-ui-toast"),
          tone: toaster.getAttribute("data-ui-toast-tone") || "info"
        }
      }));
    }
  });

  document.addEventListener("alpine:init", function () {

    /* --- modal and drawer ------------------------------------------- */

    Alpine.data("uiOverlay", function (id) {
      return {
        id: id,
        open: false,
        returnFocusTo: null,

        openFromEvent: function (event) {
          if (event.detail && event.detail.id !== this.id) return;
          this.show();
        },

        closeFromEvent: function (event) {
          if (event.detail && event.detail.id && event.detail.id !== this.id) return;
          this.close();
        },

        show: function () {
          if (this.open) return;
          this.returnFocusTo = document.activeElement;
          this.open = true;
          lockScroll();
          var panel = this.$refs.panel;
          this.$nextTick(function () {
            var targets = focusable(panel);
            (targets[0] || panel).focus();
          });
        },

        close: function () {
          if (!this.open) return;
          this.open = false;
          unlockScroll();
          /* Returning focus to the control that opened the dialog is what
             stops a keyboard user being dumped at the top of the page. */
          if (this.returnFocusTo && this.returnFocusTo.focus) {
            this.returnFocusTo.focus();
          }
        },

        /* Keep Tab inside the dialog while it is open. */
        trap: function (event) {
          if (!this.open || event.key !== "Tab") return;
          var targets = focusable(this.$refs.panel);
          if (!targets.length) return;

          var first = targets[0];
          var last = targets[targets.length - 1];

          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
          }
        }
      };
    });

    /* --- dropdown ---------------------------------------------------- */

    Alpine.data("uiDisclosure", function () {
      return {
        open: false,
        toggle: function () { this.open = !this.open; },
        close: function () {
          if (!this.open) return;
          this.open = false;
          if (this.$refs.trigger) this.$refs.trigger.focus();
        },
        /* Down-arrow from the trigger moves into the menu, which is what a
           keyboard user expects from a menu button. */
        first: function () {
          var self = this;
          this.open = true;
          this.$nextTick(function () {
            var targets = focusable(self.$refs.menu);
            if (targets.length) targets[0].focus();
          });
        }
      };
    });

    /* --- toasts ------------------------------------------------------ */

    Alpine.data("uiToasts", function () {
      return {
        items: [],
        seq: 0,

        add: function (detail) {
          if (!detail || !detail.message) return;
          var id = ++this.seq;
          this.items.push({
            id: id,
            message: detail.message,
            tone: detail.tone || "info",
            title: detail.title || ""
          });
          var self = this;
          var ms = detail.timeout === 0 ? 0 : (detail.timeout || 6000);
          if (ms) setTimeout(function () { self.dismiss(id); }, ms);
        },

        dismiss: function (id) {
          this.items = this.items.filter(function (item) { return item.id !== id; });
        }
      };
    });

    /* --- file upload -------------------------------------------------- */

    Alpine.data("uiFileUpload", function () {
      return {
        dragging: false,
        names: [],

        pick: function (event) {
          this.names = Array.prototype.map.call(event.target.files, function (f) {
            return f.name;
          });
        },

        drop: function (event) {
          this.dragging = false;
          var input = this.$refs.input;
          if (!event.dataTransfer || !input) return;
          input.files = event.dataTransfer.files;
          input.dispatchEvent(new Event("change", { bubbles: true }));
        }
      };
    });
  });
})();
