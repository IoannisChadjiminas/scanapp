export function expansionDrive(action, payload = {}) {
  function skip(text, value) {
    const label = String(text || "").trim().toLowerCase();
    const raw = String(value || "").trim().toLowerCase();
    return (!label && !raw) || label === "all" || raw === "all" || raw === "-1" || raw === "0";
  }

  function expansionSelect() {
    return document.querySelector(
      'select[name="idExpansion"], select#idExpansion, select[name*="xpansion" i], select[id*="xpansion" i]',
    );
  }

  function categoryValue() {
    const node = document.querySelector(
      'select[name="idCategory"], input[name="idCategory"], select#idCategory',
    );
    return node?.value ? String(node.value) : "";
  }

  function expansionUrl(id) {
    const locale = location.pathname.split("/").filter(Boolean)[0] || "en";
    const url = new URL(`/${locale}/Pokemon/Products/Singles`, location.origin);
    const category = categoryValue();
    if (category && category !== "-1" && category !== "0") {
      url.searchParams.set("idCategory", category);
    }
    url.searchParams.set("idExpansion", String(id));
    return url.toString();
  }

  function listFromSelect(select) {
    const expansions = [];
    if (!select) {
      return expansions;
    }
    for (const opt of Array.from(select.options || [])) {
      const value = String(opt.value || "").trim();
      const name = String(opt.textContent || opt.label || "").trim().replace(/\s+/g, " ");
      if (skip(name, value) || !/^\d+$/.test(value)) {
        continue;
      }
      expansions.push({ id: value, name, url: expansionUrl(value) });
    }
    return expansions;
  }

  function listFromOptions() {
    const expansions = [];
    for (const node of document.querySelectorAll('[role="option"][data-value], [data-expansion-id]')) {
      const value = String(
        node.getAttribute("data-value") || node.getAttribute("data-expansion-id") || "",
      ).trim();
      const name = String(node.textContent || "").trim().replace(/\s+/g, " ");
      if (skip(name, value) || !/^\d+$/.test(value)) {
        continue;
      }
      expansions.push({ id: value, name, url: expansionUrl(value) });
    }
    return expansions;
  }

  function expansionTrigger() {
    const labelled = document.querySelector(
      '[aria-label*="xpansion" i], [aria-controls*="xpansion" i], button[aria-haspopup="listbox"]',
    );
    if (labelled) {
      return labelled;
    }
    for (const el of document.querySelectorAll("label, dt, th, span, div, p")) {
      if ((el.textContent || "").trim() !== "Expansion") {
        continue;
      }
      const row = el.closest("div, li, tr, section, form") || el.parentElement;
      return (
        row?.querySelector("select, button, [role='combobox'], [role='button'], input") ||
        el.nextElementSibling
      );
    }
    return null;
  }

  if (action === "list") {
    const select = expansionSelect();
    const expansions = listFromSelect(select);
    return {
      expansions: expansions.length ? expansions : listFromOptions(),
      method: select ? "select" : "options",
    };
  }

  if (action === "open") {
    const select = expansionSelect();
    if (select) {
      try {
        select.focus();
        select.click();
      } catch {
        /* ignore */
      }
      return { ok: true, method: "select" };
    }
    const trigger = expansionTrigger();
    if (trigger && typeof trigger.click === "function") {
      trigger.click();
      return { ok: true, method: "click" };
    }
    return { ok: false };
  }

  if (action === "apply") {
    const id = String(payload.id || "").trim();
    const name = String(payload.name || "").trim();
    const select = expansionSelect();
    if (select && id) {
      select.value = id;
      select.dispatchEvent(new Event("input", { bubbles: true }));
      select.dispatchEvent(new Event("change", { bubbles: true }));
      const form = select.form || select.closest("form");
      if (form) {
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
        } else {
          form.submit();
        }
        return { ok: true, method: "form" };
      }
    }
    if (name) {
      const opt = Array.from(document.querySelectorAll('[role="option"]')).find(
        (el) => String(el.textContent || "").trim().replace(/\s+/g, " ") === name,
      );
      if (opt && typeof opt.click === "function") {
        opt.click();
        return { ok: true, method: "option-click" };
      }
    }
    if (payload.url) {
      location.assign(String(payload.url));
      return { ok: true, method: "url" };
    }
    if (id) {
      location.assign(expansionUrl(id));
      return { ok: true, method: "location" };
    }
    return { ok: false };
  }

  return { ok: false };
}
