/**
 * AMT coding extension example frontend.
 *
 * This file is loaded into the frontend extension hub.  It demonstrates how
 * a coding extension can expose a small UI affordance without mutating the
 * global coding tool surface.
 */
(function () {
  "use strict";

  function init(ctx) {
    if (!ctx || !ctx.ui || typeof ctx.ui.flash !== "function") {
      console.warn("amt-coding-example: ctx.ui.flash is missing");
      return;
    }
    ctx.ui.flash("AMT coding example extension loaded");
  }

  window.AMTCodingExample = { init };
})();
