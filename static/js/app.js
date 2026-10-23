(function () {
  "use strict";

  // Language switcher: submit on change without inline handlers (CSP-safe).
  document.querySelectorAll("select[data-auto-submit]").forEach(function (select) {
    select.addEventListener("change", function () {
      if (select.form) select.form.submit();
    });
  });

  // Cookie notice (functional only; no tracking).
  var banner = document.getElementById("cookie-banner");
  if (banner) {
    var KEY = "forum-cookie-ack";
    var stored = null;
    try { stored = window.localStorage.getItem(KEY); } catch (err) { stored = null; }
    if (!stored) banner.hidden = false;
    var dismiss = banner.querySelector("[data-cookie-dismiss]");
    if (dismiss) {
      dismiss.addEventListener("click", function () {
        try { window.localStorage.setItem(KEY, "1"); } catch (err) { /* private mode */ }
        banner.hidden = true;
      });
    }
  }

  // Prevent accidental double submits (and duplicate topics/replies).
  document.querySelectorAll("form").forEach(function (form) {
    if ((form.method || "").toLowerCase() !== "post") return;
    form.addEventListener("submit", function () {
      var button = form.querySelector('button[type="submit"]');
      if (!button) return;
      window.setTimeout(function () {
        button.disabled = true;
        button.classList.add("is-busy");
      }, 0);
    });
  });

  // Keep long reply boxes usable.
  document.querySelectorAll("textarea").forEach(function (area) {
    area.addEventListener("input", function () {
      area.style.height = "auto";
      area.style.height = Math.min(area.scrollHeight + 2, 520) + "px";
    });
  });
})();
