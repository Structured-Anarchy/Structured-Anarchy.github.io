function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  if (className) result.className = className;
  return result;
}

export function transcriptUrl(sourceId, start, stop) {
  const params = new URLSearchParams({ source: sourceId });
  if (Number.isInteger(start)) params.set("start", start);
  if (Number.isInteger(stop)) params.set("stop", stop);
  return `/discussions/#${params}`;
}

function timestampPrefix(line) {
  // Only treat standalone timecodes and bracketed leading timecodes as
  // annotations. Times mentioned within spoken sentences remain readable.
  return line.match(/^[ \t]*(?:\[~?\d{2,}:[0-5]\d(?::[0-5]\d)?\](?:[ \t]+|(?=\r?$))|~?\d{2,}:[0-5]\d(?::[0-5]\d)?[ \t\r]*$)/)?.[0] || "";
}

export function createTranscriptView(container, popup, vault, onThesis) {
  let version = 0, observer = null, trigger = null, closeTimer = null;
  function closeMenu() {
    clearTimeout(closeTimer);
    trigger?.setAttribute("aria-expanded", "false");
    popup.hidden = true;
    popup.replaceChildren();
    trigger = null;
  }
  function clear() {
    version += 1;
    observer?.disconnect();
    observer = null;
    closeMenu();
    container.replaceChildren();
    document.dispatchEvent(new CustomEvent("sa:reader-source"));
  }
  function showMenu(button, theses) {
    closeMenu();
    trigger = button;
    button.setAttribute("aria-expanded", "true");
    popup.append(node("p", "Theses using this passage", "map-note"));
    const list = node("ul");
    for (const thesis of theses) {
      const item = node("li"), link = node("a", thesis.text);
      link.href = `/structural-map/#${encodeURIComponent(thesis.id)}`;
      link.addEventListener("click", event => {
        if (event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault(); closeMenu(); onThesis(thesis.id);
      });
      item.append(link); list.append(item);
    }
    popup.append(list);
    popup.style.maxHeight = "";
    popup.hidden = false;
    const rect = button.getBoundingClientRect();
    const fitsBeside = rect.right + 16 + popup.offsetWidth <= innerWidth;
    popup.style.left = `${fitsBeside ? rect.right + 8 : Math.max(8, innerWidth - popup.offsetWidth - 8)}px`;
    if (fitsBeside) popup.style.top = `${Math.max(8, Math.min(rect.top, innerHeight - popup.offsetHeight - 8))}px`;
    else {
      const below = innerHeight - rect.bottom - 16, above = rect.top - 16;
      popup.style.maxHeight = `${Math.max(40, Math.max(above, below))}px`;
      popup.style.top = `${below >= above ? rect.bottom + 8 : Math.max(8, rect.top - popup.offsetHeight - 8)}px`;
    }
  }
  popup.addEventListener("pointerenter", () => clearTimeout(closeTimer));
  popup.addEventListener("pointerleave", () => { closeTimer = setTimeout(closeMenu, 180); });
  document.addEventListener("click", event => { if (!popup.contains(event.target) && !trigger?.contains(event.target)) closeMenu(); });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !popup.hidden) { const previous = trigger; closeMenu(); previous?.focus(); }
  });
  window.addEventListener("scroll", closeMenu, { passive: true });
  window.addEventListener("resize", closeMenu);

  async function show(source, model, start = null, stop = null) {
    clear();
    const current = version;
    container.append(node("p", "Loading the session transcript…", "map-note"));
    try {
      const text = await vault.source(source.file_name);
      if (current !== version) return;
      const chars = Array.from(text);
      if (start !== null && stop === null) stop = start + 1;
      if (start !== null && (!Number.isInteger(start) || start < 0 || start >= chars.length ||
          (stop !== null && (!Number.isInteger(stop) || stop <= start || stop > chars.length)))) {
        throw new Error("This transcript position is outside the source text.");
      }
      container.replaceChildren();
      container.append(node("h2", source.label, "transcript-title"),
        node("p", "Timestamps sit in the margin and are skipped during speed reading; ~ marks an estimated time. Margin markers link to theses using a passage as assertion evidence, including premises and objections. A citation records what was said; it does not prove it true.", "map-note"));
      const body = node("div", undefined, "transcript-lines");
      body.dataset.transcriptSource = source.id;
      body.dataset.passageLabel = source.label;
      const markers = model.transcriptMarkers(source.file_name), positions = [];
      let markerIndex = 0, lineStart = 0, target = null;
      for (let end = 0; end <= chars.length; end += 1) {
        if (end < chars.length && chars[end] !== "\n") continue;
        const row = node("div", undefined, "transcript-line"), content = node("div", undefined, "transcript-text");
        row.dataset.start = lineStart;
        const line = chars.slice(lineStart, end).join(""), prefix = timestampPrefix(line);
        const timestampEnd = lineStart + Array.from(prefix).length;
        let timestamp = null;
        if (prefix) {
          body.classList.add("has-timestamps");
          timestamp = node("span", undefined, "transcript-timestamp");
          timestamp.dataset.readerSkip = "";
          content.append(timestamp);
          // A standalone timestamp shares the following text row's margin.
          // Keep an isolated or consecutive timecode on its own row instead.
          const nextEnd = chars.indexOf("\n", end + 1);
          const nextLine = chars.slice(end + 1, nextEnd < 0 ? chars.length : nextEnd).join("");
          if (!line.slice(prefix.length).trim() && nextLine.trim() && !timestampPrefix(nextLine)) {
            row.classList.add("transcript-time-row");
          }
        }
        const here = [];
        while (markerIndex < markers.length && markers[markerIndex].start <= end) here.push(markers[markerIndex++]);
        const cuts = new Set([lineStart, end, ...here.map(m => m.start)]);
        if (timestamp) cuts.add(timestampEnd);
        if (start !== null && start >= lineStart && start <= end) cuts.add(start);
        if (stop !== null && stop > lineStart && stop < end) cuts.add(stop);
        const ordered = [...cuts].sort((a, b) => a - b);
        for (let i = 0; i < ordered.length; i += 1) {
          const at = ordered[i];
          const destination = timestamp && at < timestampEnd ? timestamp : content;
          const marker = here.find(m => m.start === at);
          if (marker || at === start) {
            const anchor = node("span", undefined, "transcript-anchor");
            anchor.dataset.char = at;
            anchor.setAttribute("aria-hidden", "true");
            destination.append(anchor);
            if (at === start) target = anchor;
            if (marker) {
              const button = node("button", "◈", "transcript-marker");
              button.type = "button";
              button.dataset.passageStart = at;
              button.setAttribute("aria-label", `${marker.theses.length} theses using the passage at character ${at}`);
              button.setAttribute("aria-expanded", "false");
              button.setAttribute("aria-controls", popup.id);
              const position = { row, anchor, button, theses: marker.theses, grouped: marker.theses };
              button.addEventListener("click", () => showMenu(button, position.grouped));
              button.addEventListener("pointerenter", event => { if (event.pointerType !== "touch") showMenu(button, position.grouped); });
              button.addEventListener("pointerleave", () => { closeTimer = setTimeout(closeMenu, 180); });
              row.append(button);
              positions.push(position);
            }
          }
          if (i + 1 < ordered.length) {
            const segment = chars.slice(at, ordered[i + 1]).join("");
            // Keep timestamp highlights out of the reader's passage-start
            // selector, so a cited turn starts at its first spoken word.
            if (start !== null && at >= start && at < (stop ?? start + 1)) destination.append(node("mark", segment,
              destination === timestamp ? "transcript-time-highlight" : "transcript-highlight"));
            else destination.append(document.createTextNode(segment));
          }
        }
        row.append(content); body.append(row);
        lineStart = end + 1;
      }
      container.append(body);
      document.dispatchEvent(new CustomEvent("sa:reader-source"));
      function positionMarkers() {
        const groups = new Map();
        const bodyTop = body.getBoundingClientRect().top;
        const lineHeight = parseFloat(getComputedStyle(body).lineHeight);
        for (const position of positions) {
          const { row, anchor, button } = position;
          const rowTop = row.getBoundingClientRect().top;
          const top = anchor.closest(".transcript-timestamp") ? 0 :
            Math.floor(Math.max(0, anchor.getBoundingClientRect().top - rowTop) / lineHeight) * lineHeight;
          // A timestamp-only source line can share a visual row with speech.
          // Group by visual position so their evidence buttons do not overlap.
          const key = Math.round(rowTop - bodyTop + top);
          const group = groups.get(key);
          button.hidden = Boolean(group);
          if (group) group.theses.push(...position.theses);
          else groups.set(key, { position, top, theses: [...position.theses] });
        }
        for (const { position, top, theses } of groups.values()) {
          position.grouped = [...new Map(theses.map(t => [t.id, t])).values()];
          position.button.style.top = `${top}px`;
          position.button.setAttribute("aria-label", `${position.grouped.length} theses using passages starting on this row`);
        }
      }
      observer = new ResizeObserver(positionMarkers);
      observer.observe(body);
      positionMarkers();
      await document.fonts.ready;
      if (current !== version) return;
      positionMarkers();
      if (target) target.scrollIntoView({ block: "center" });
      else container.scrollIntoView({ block: "start" });
    } catch (error) {
      if (current !== version) return;
      container.replaceChildren(node("p", error.message, "map-error"));
    }
  }
  return { show, clear, closeMenu };
}
