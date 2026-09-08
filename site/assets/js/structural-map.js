import { ContentVault } from "./vault.js";

const root = document.querySelector("[data-structural-map]");
const form = root?.querySelector("[data-unlock-form]");
if (form) initialize();

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function button(text, action, className) {
  const node = element("button", text, className);
  node.type = "button";
  node.addEventListener("click", action);
  return node;
}

function initialize() {
  const vault = new ContentVault(root.dataset.manifest);
  const content = root.querySelector("[data-map-content]");
  const list = root.querySelector("[data-thesis-list]");
  const rows = root.querySelector("[data-thesis-rows]");
  const search = root.querySelector("[data-thesis-search]");
  const graph = root.querySelector("[data-graph-view]");
  const grid = root.querySelector("[data-atom-grid]");
  const context = root.querySelector("[data-argument-context]");
  const breadcrumbs = root.querySelector("[data-breadcrumbs]");
  const preview = document.querySelector("[data-meaning-preview]");
  const dialog = document.querySelector("[data-evidence-dialog]");
  const popupTitle = dialog.querySelector("h2");
  const popupBody = dialog.querySelector("[data-evidence-body]");
  const passageSource = dialog.querySelector("[data-passage-source]");
  const popupBack = dialog.querySelector("[data-evidence-back]");
  const status = root.querySelector("#vault-status");
  const input = form.querySelector("input");
  let kb = null;
  let index = {};
  let incoming = new Map();
  let outgoing = new Map();
  let frames = [];
  let popupVersion = 0;
  let meaningsBack = null;

  function resetReader() {
    document.dispatchEvent(new CustomEvent("sa:reader-source"));
  }

  function closePopup() {
    if (dialog.open) dialog.close();
  }

  function clearPopup() {
    popupVersion += 1;
    popupBody.replaceChildren();
    passageSource.replaceChildren();
    resetReader();
  }

  function lock() {
    root.classList.remove("is-exploring");
    closePopup();
    clearPopup();
    popupTitle.textContent = "";
    meaningsBack = null;
    preview.replaceChildren();
    preview.hidden = true;
    vault.lock();
    kb = null;
    index = {};
    incoming.clear();
    outgoing.clear();
    frames = [];
    [rows, grid, context, breadcrumbs].forEach(node => node.replaceChildren());
    search.value = "";
    content.hidden = true;
    form.hidden = false;
    status.textContent = "";
    input.value = "";
  }

  root.querySelector("[data-lock]").addEventListener("click", () => { lock(); input.focus(); });
  window.addEventListener("pagehide", lock);
  dialog.querySelector("[data-evidence-close]").addEventListener("click", closePopup);
  dialog.addEventListener("close", clearPopup);
  popupBack.addEventListener("click", () => meaningsBack?.());
  dialog.addEventListener("click", event => {
    const rect = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) closePopup();
  });
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const submit = form.querySelector("button");
    submit.disabled = true;
    status.textContent = "Opening the archive…";
    try {
      kb = await vault.open(input.value);
      input.value = "";
      for (const name of ["propositions", "symbols", "meanings", "arguments", "sessions"]) {
        index[name] = new Map(kb[name].map(item => [item.id, item]));
      }
      for (const argument of kb.arguments) {
        const target = argument.conclusion.proposition_id;
        if (!incoming.has(target)) incoming.set(target, []);
        incoming.get(target).push(argument);
        for (const premise of argument.premises) {
          if (!outgoing.has(premise.proposition_id)) outgoing.set(premise.proposition_id, []);
          outgoing.get(premise.proposition_id).push(argument);
        }
      }
      form.hidden = true;
      content.hidden = false;
      const requested = decodeURIComponent(location.hash.slice(1));
      showList();
      if (index.propositions.has(requested)) openProposition(requested);
      else search.focus();
    } catch (error) {
      status.textContent = error.message || "The archive could not be opened. Please try again.";
      input.focus();
    } finally {
      submit.disabled = false;
    }
  });

  function renderList() {
    rows.replaceChildren();
    const query = search.value.trim().toLocaleLowerCase();
    const theses = kb.propositions.filter(p => p.thesis && `${p.text} ${p.topics.join(" ")}`.toLocaleLowerCase().includes(query));
    for (const thesis of theses) {
      const row = button("", () => openProposition(thesis.id), "writing-row thesis-row");
      row.append(element("span", thesis.text, "writing-title"));
      const sessions = new Set(kb.occurrences.filter(o => o.target_type === "proposition" && o.target_id === thesis.id).map(o => o.session_id));
      row.append(element("span", `${(incoming.get(thesis.id) || []).length} arguments · ${sessions.size} sessions`, "writing-meta"));
      row.append(element("span", thesis.topics.join(" · "), "writing-summary"));
      rows.append(row);
    }
    if (!theses.length) rows.append(element("p", query ? "No theses match your search." : "No theses have been mapped yet. They will appear here as our sessions are added.", "empty-state"));
  }

  search.addEventListener("input", renderList);

  function showList() {
    root.classList.remove("is-exploring");
    frames = [];
    list.hidden = false;
    graph.hidden = true;
    closePopup();
    history.replaceState(null, "", location.pathname);
    renderList();
  }

  function openProposition(id, negated = false) {
    const proposition = index.propositions.get(id);
    frames = [{ label: proposition.text, literals: [{ proposition_id: id, negated }] }];
    history.replaceState(null, "", `#${encodeURIComponent(id)}`);
    renderGraph();
  }

  function goToFrame(i) {
    frames = frames.slice(0, i + 1);
    renderGraph();
  }

  root.querySelector("[data-map-up]").addEventListener("click", () => {
    if (frames.length <= 1) showList();
    else goToFrame(frames.length - 2);
  });

  function renderGraph() {
    root.classList.add("is-exploring");
    closePopup();
    preview.hidden = true;
    list.hidden = true;
    graph.hidden = false;
    const frame = frames.at(-1);
    breadcrumbs.replaceChildren(button("All theses", showList));
    frames.forEach((item, i) => {
      breadcrumbs.append(element("span", " / "), button(i === 0 ? "Thesis" : `Argument ${i}`, () => goToFrame(i)));
    });
    context.replaceChildren();
    if (frame.argument) {
      const argument = frame.argument;
      context.append(element("p", argument.explanation, "argument-explanation"));
      context.append(element("p", argument.explicitness === "reconstructed" ? "Reconstructed from context" : "Expressed in the session", "map-note"));
      context.append(button("Argument passages ↗", () => showEvidence("Argument passages", argument.origins)));
      const conclusion = index.propositions.get(argument.conclusion.proposition_id);
      context.append(element("p", `Together these premises point to: ${argument.conclusion.negated ? "¬(" : ""}${conclusion.text}${argument.conclusion.negated ? ")" : ""}`, "map-note"));
    }
    grid.replaceChildren();
    grid.classList.toggle("single-atom", frame.literals.length === 1);
    for (const literal of frame.literals) grid.append(renderAtom(literal));
  }

  function renderAtom(literal) {
    const proposition = index.propositions.get(literal.proposition_id);
    const card = element("article", undefined, "atom-card");
    card.dataset.proposition = proposition.id;
    const statement = element("h2", undefined, "atom-statement");
    if (literal.negated) statement.append(document.createTextNode("¬("));
    const chars = Array.from(proposition.text);
    let start = 0;
    for (const binding of [...proposition.bindings].sort((a, b) => a.start_char - b.start_char)) {
      statement.append(document.createTextNode(chars.slice(start, binding.start_char).join("")));
      const word = chars.slice(binding.start_char, binding.stop_char).join("");
      const symbol = button("", () => showMeanings(binding), "statement-symbol");
      symbol.append(element("span", word), element("sup", `(${binding.meaning_ids.length})`));
      symbol.setAttribute("aria-label", `${word}: ${binding.meaning_ids.length} meanings`);
      symbol.setAttribute("aria-haspopup", "dialog");
      symbol.addEventListener("pointerenter", event => { if (event.pointerType !== "touch") previewMeanings(symbol, binding); });
      symbol.addEventListener("pointerleave", () => { preview.hidden = true; });
      symbol.addEventListener("blur", () => { preview.hidden = true; });
      statement.append(symbol);
      start = binding.stop_char;
    }
    statement.append(document.createTextNode(chars.slice(start).join("")));
    if (literal.negated) statement.append(document.createTextNode(")"));
    const sourceButton = button("↗", () => showEvidence("Statement passages", proposition.origins, proposition), "statement-source");
    sourceButton.setAttribute("aria-label", `Passages for: ${proposition.text}`);
    statement.append(document.createTextNode(" "), sourceButton);
    card.append(statement);
    const previous = frames.slice(0, -1).findIndex(frame => frame.literals.some(p => p.proposition_id === proposition.id));
    const argumentsHere = incoming.get(proposition.id) || [];
    const wheel = element("div", undefined, "argument-wheel");
    const center = element("div", undefined, "atom-center");
    center.append(element("span", literal.negated ? "¬" : "·", "atom-mark"));
    center.append(element("span", argumentsHere.length ? `${argumentsHere.length} argument${argumentsHere.length === 1 ? "" : "s"}` : "An open premise", "map-note"));
    wheel.append(center);
    if (previous >= 0) {
      card.append(wheel, button("Already on this path — return ↑", () => goToFrame(previous), "cycle-return"));
    } else {
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 240 240");
      svg.setAttribute("aria-label", "Supporting and refuting arguments");
      argumentsHere.forEach((argument, i) => {
        const support = argument.conclusion.negated === literal.negated;
        const angle = 360 / argumentsHere.length;
        const begin = -90 + i * angle + Math.min(3, angle / 8);
        const end = -90 + (i + 1) * angle - Math.min(3, angle / 8);
        const path = document.createElementNS(svg.namespaceURI, "path");
        path.setAttribute("d", ringSegment(begin, end));
        path.setAttribute("class", support ? "support-segment" : "refute-segment");
        path.setAttribute("role", "button");
        path.setAttribute("tabindex", "0");
        const label = `${support ? "Supports" : "Refutes"}: ${argument.premises.map(p => `${p.negated ? "¬ " : ""}${index.propositions.get(p.proposition_id).text}`).join(" AND ")}`;
        path.setAttribute("aria-label", label);
        const title = document.createElementNS(svg.namespaceURI, "title");
        title.textContent = label;
        path.append(title);
        const open = () => {
          frames.push({ label, literals: argument.premises, argument });
          renderGraph();
          root.querySelector("[data-map-up]").focus();
        };
        path.addEventListener("click", open);
        path.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); } });
        svg.append(path);
        const point = polar((begin + end) / 2, 100);
        const sign = document.createElementNS(svg.namespaceURI, "text");
        sign.setAttribute("x", point[0]);
        sign.setAttribute("y", point[1] + 5);
        sign.setAttribute("text-anchor", "middle");
        sign.setAttribute("aria-hidden", "true");
        sign.textContent = support ? "+" : "−";
        svg.append(sign);
      });
      wheel.append(svg);
      card.append(wheel);
    }
    const uses = [...new Set((outgoing.get(proposition.id) || []).map(a => a.conclusion.proposition_id))];
    if (uses.length) {
      const details = element("details", undefined, "other-uses");
      details.append(element("summary", `Also used in ${uses.length} statement${uses.length === 1 ? "" : "s"}`));
      for (const id of uses) details.append(button(index.propositions.get(id).text, () => openProposition(id)));
      card.append(details);
    }
    const questions = kb.questions.filter(q => q.proposition_ids.includes(proposition.id));
    for (const question of questions) card.append(button(`Open question: ${question.text}`, () => showEvidence("Open question", question.origins), "open-question"));
    return card;
  }

  function previewMeanings(anchor, binding) {
    if (dialog.open) return;
    preview.replaceChildren();
    const items = element("ul");
    for (const id of binding.meaning_ids) items.append(element("li", index.meanings.get(id).definition));
    preview.append(items);
    preview.hidden = false;
    const rect = anchor.getBoundingClientRect();
    preview.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - preview.offsetWidth - 8))}px`;
    const below = rect.bottom + 8;
    preview.style.top = `${below + preview.offsetHeight < innerHeight ? below : Math.max(8, rect.top - preview.offsetHeight - 8)}px`;
  }

  function beginPopup(title, back = null) {
    clearPopup();
    preview.hidden = true;
    popupTitle.textContent = title;
    meaningsBack = back;
    popupBack.hidden = !back;
    if (!dialog.open) dialog.showModal();
    return popupVersion;
  }

  function showMeanings(binding) {
    const symbol = index.symbols.get(binding.symbol_id);
    beginPopup(symbol.label);
    const back = () => showMeanings(binding);
    const selected = element("ul", undefined, "meaning-list");
    const addMeaning = (id, parent, excluded = false) => {
      const meaning = index.meanings.get(id);
      const row = element("li");
      const text = `${excluded ? "Explicitly excluded: " : ""}${meaning.definition}`;
      if (meaning.kind === "normative") {
        row.append(element("span", text), element("p", "No definition was declared. Assumed societal usage is risky: shared understanding has not been established.", "meaning-warning"));
      } else row.append(button(text, () => showEvidence(meaning.definition, meaning.origins, null, back)));
      parent.append(row);
    };
    binding.meaning_ids.forEach(id => addMeaning(id, selected));
    popupBody.append(element("p", binding.selection === "ambiguous" ? "The intended meaning remains ambiguous among these alternatives." : binding.selection === "collective" ? "These meanings were deliberately used together." : "Meaning used in this statement.", "map-note"), selected);
    popupBody.append(button("Interpretation passages ↗", () => showEvidence("Why these meanings apply", binding.origins, null, back)));
    const others = kb.meanings.filter(m => m.symbol_id === symbol.id && !binding.meaning_ids.includes(m.id));
    if (others.length) {
      const details = element("details", undefined, "other-meanings");
      details.append(element("summary", `Other meanings (${others.length})`), element("p", "A meaning not selected here was not necessarily rejected.", "map-note"));
      const unselected = element("ul", undefined, "meaning-list");
      others.forEach(meaning => addMeaning(meaning.id, unselected, binding.excluded_meaning_ids.includes(meaning.id)));
      details.append(unselected);
      popupBody.append(details);
    }
  }

  async function showEvidence(title, origins, proposition = null, back = null) {
    const version = beginPopup(title, back);
    popupBody.append(element("p", "Loading passages…", "map-note"));
    try {
      const passages = await passageUnion(origins);
      if (version !== popupVersion || !dialog.open) return;
      popupBody.replaceChildren();
      if (proposition) {
        popupBody.append(element("p", proposition.scope, "map-note"));
        const occurrences = kb.occurrences.filter(o => o.target_type === "proposition" && o.target_id === proposition.id);
        const historyList = element("ul", undefined, "occurrence-list");
        for (const occurrence of occurrences) {
          const session = index.sessions.get(occurrence.session_id);
          historyList.append(element("li", `${session.title}: ${occurrence.stance}${occurrence.attribution ? ` · ${occurrence.attribution}` : ""}`));
        }
        popupBody.append(historyList);
      }
      for (const passage of passages) {
        const article = element("article", undefined, "source-passage");
        const source = kb.sources.find(s => s.file_name === passage.file_name);
        const label = `${source?.label || passage.file_name} · ${passage.start_char}–${passage.stop_char}`;
        article.dataset.passageLabel = label;
        const citation = element("div", label, "passage-label");
        citation.title = `${passage.file_name}:${passage.start_char}-${passage.stop_char}`;
        citation.dataset.readerSkip = "";
        const text = element("p", passage.text, "passage-text");
        article.append(citation, text);
        passageSource.append(article);
      }
      resetReader();
    } catch (error) {
      if (version !== popupVersion || !dialog.open) return;
      popupBody.replaceChildren(element("p", error.message, "map-error"), button("Try again", () => showEvidence(title, origins, proposition, back)));
    }
  }

  async function passageUnion(origins) {
    const files = [...new Set(origins.map(p => p.file_name))];
    const texts = new Map(await Promise.all(files.map(async name => [name, Array.from(await vault.source(name))])));
    for (const origin of origins) {
      const chars = texts.get(origin.file_name);
      const passage = chars.slice(origin.start_char, origin.stop_char);
      if (origin.start_char < 0 || origin.stop_char > chars.length || origin.start_char >= origin.stop_char ||
          passage.slice(0, 6).join("") !== origin.first_6_chars || passage.slice(-6).join("") !== origin.last_6_chars) {
        throw new Error("A passage reference no longer matches its transcript.");
      }
    }
    const order = new Map(kb.sources.map((source, i) => [source.file_name, i]));
    const sorted = [...origins].sort((a, b) => (order.get(a.file_name) - order.get(b.file_name)) || a.start_char - b.start_char);
    const union = [];
    for (const origin of sorted) {
      const last = union.at(-1);
      if (last && last.file_name === origin.file_name && origin.start_char <= last.stop_char) last.stop_char = Math.max(last.stop_char, origin.stop_char);
      else union.push({ file_name: origin.file_name, start_char: origin.start_char, stop_char: origin.stop_char });
    }
    return union.map(p => ({ ...p, text: texts.get(p.file_name).slice(p.start_char, p.stop_char).join("") }));
  }
}

function polar(angle, radius) {
  const radians = angle * Math.PI / 180;
  return [120 + radius * Math.cos(radians), 120 + radius * Math.sin(radians)];
}

function ringSegment(start, end) {
  const a = polar(start, 114), b = polar(end, 114), c = polar(end, 85), d = polar(start, 85);
  const large = end - start > 180 ? 1 : 0;
  return `M ${a} A 114 114 0 ${large} 1 ${b} L ${c} A 85 85 0 ${large} 0 ${d} Z`;
}
