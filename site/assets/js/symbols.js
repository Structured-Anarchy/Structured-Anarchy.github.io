export function createSymbolBrowser(rows, sort, popup, renderMeanings) {
  let symbols = [], meanings = new Map(), trigger = null, closeTimer = null, openTimer = null;
  function close() {
    clearTimeout(closeTimer);
    trigger?.setAttribute("aria-expanded", "false");
    trigger = null;
    popup.hidden = true;
    popup.replaceChildren();
  }
  function clear() {
    clearTimeout(openTimer);
    close();
    symbols = [];
    meanings.clear();
    rows.replaceChildren();
  }
  function show(button, symbol, focus = false) {
    clearTimeout(openTimer);
    close();
    trigger = button;
    button.setAttribute("aria-expanded", "true");
    const dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.textContent = "×";
    dismiss.setAttribute("aria-label", "Close meanings");
    dismiss.addEventListener("click", () => { close(); button.focus({ preventScroll: true }); });
    const heading = document.createElement("h2");
    heading.textContent = symbol.label;
    const list = document.createElement("ul");
    list.className = "meaning-list";
    renderMeanings(symbol, meanings.get(symbol.id) || [], list);
    popup.append(dismiss, heading, list);
    popup.style.maxHeight = `${Math.max(100, Math.min(520, innerHeight - 16))}px`;
    popup.hidden = false;
    const rect = button.getBoundingClientRect();
    const left = rect.right + 8 + popup.offsetWidth <= innerWidth ? rect.right + 8 : Math.max(8, innerWidth - popup.offsetWidth - 8);
    popup.style.left = `${left}px`;
    popup.style.top = `${Math.max(8, Math.min(rect.top, innerHeight - popup.offsetHeight - 8))}px`;
    if (focus) dismiss.focus({ preventScroll: true });
  }
  function render() {
    clearTimeout(openTimer);
    close();
    rows.replaceChildren();
    const ordered = [...symbols].sort((a, b) =>
      (sort.value === "meanings" ? (meanings.get(b.id)?.length || 0) - (meanings.get(a.id)?.length || 0) : 0) ||
      a.label.localeCompare(b.label, "en", { sensitivity: "base" }) || a.id.localeCompare(b.id));
    for (const symbol of ordered) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "writing-row thesis-row symbol-row";
      button.dataset.symbol = symbol.id;
      button.setAttribute("aria-haspopup", "dialog");
      button.setAttribute("aria-expanded", "false");
      button.setAttribute("aria-controls", popup.id);
      const label = document.createElement("span"), count = document.createElement("span");
      label.className = "writing-title";
      label.textContent = symbol.label;
      count.className = "writing-meta";
      const total = meanings.get(symbol.id)?.length || 0;
      count.textContent = `${total} meaning${total === 1 ? "" : "s"}`;
      button.append(label, count);
      button.addEventListener("click", () => show(button, symbol, true));
      button.addEventListener("pointerenter", event => {
        // Let automatic scrolling settle before placing a hover popup.
        if (event.pointerType !== "touch" && !popup.contains(document.activeElement)) openTimer = setTimeout(() => {
          if (!popup.contains(document.activeElement) && !document.querySelector("dialog[open]")) show(button, symbol);
        }, 120);
      });
      button.addEventListener("pointerleave", () => {
        clearTimeout(openTimer);
        if (!popup.contains(document.activeElement)) closeTimer = setTimeout(close, 200);
      });
      rows.append(button);
    }
    if (!ordered.length) rows.textContent = "No symbols have been added yet.";
  }
  sort.addEventListener("change", render);
  popup.addEventListener("pointerenter", () => clearTimeout(closeTimer));
  popup.addEventListener("pointerleave", () => {
    if (!popup.contains(document.activeElement)) closeTimer = setTimeout(close, 200);
  });
  document.addEventListener("click", event => { if (!popup.contains(event.target) && !trigger?.contains(event.target)) close(); });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !popup.hidden) {
      const previous = trigger;
      close(); previous?.focus({ preventScroll: true });
    }
  });
  window.addEventListener("scroll", close, { passive: true });
  window.addEventListener("resize", close);
  return { clear, close, show(kb) {
    symbols = kb.symbols;
    meanings.clear();
    for (const meaning of kb.meanings) {
      if (!meanings.has(meaning.symbol_id)) meanings.set(meaning.symbol_id, []);
      meanings.get(meaning.symbol_id).push(meaning);
    }
    render();
  } };
}
