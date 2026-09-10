import { ContentVault } from "./vault.js";
import { createGraphModel, sortedTheses } from "./graph-model.js";
import { createTranscriptView, transcriptUrl } from "./transcripts.js";
import { createSymbolBrowser } from "./symbols.js";

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

function probabilityText(value) {
  return value === null ? "—" : value.toFixed(3);
}

function initialize() {
  const vault = new ContentVault(root.dataset.manifest);
  const content = root.querySelector("[data-map-content]");
  const list = root.querySelector("[data-thesis-list]");
  const rows = root.querySelector("[data-thesis-rows]");
  const search = root.querySelector("[data-thesis-search]");
  const sort = root.querySelector("[data-thesis-sort]");
  const sessions = root.querySelector("[data-session-list]");
  const sessionRows = root.querySelector("[data-session-rows]");
  const transcriptSection = root.querySelector("[data-transcript-view]");
  const symbolSection = root.querySelector("[data-symbol-list]");
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
  let frames = [];
  let popupVersion = 0;
  let meaningsBack = null;
  let model = null;
  const siteTitle = document.title.split(" | ").slice(1).join(" | ");
  const transcripts = createTranscriptView(root.querySelector("[data-transcript-body]"),
    document.querySelector("[data-transcript-menu]"), vault, id => openProposition(id));
  const symbols = createSymbolBrowser(root.querySelector("[data-symbol-rows]"), root.querySelector("[data-symbol-sort]"),
    document.querySelector("[data-symbol-menu]"), (symbol, meanings, list) => {
      for (const meaning of meanings) appendMeaning(meaning.id, list, () => showSymbolMeanings(symbol));
    });

  function setPage(discussions) {
    const symbolPage = location.pathname === "/symbols-and-meaning/";
    const title = discussions ? "Discussions" : symbolPage ? "Symbols and Meaning" : "Structural Map";
    root.querySelector("[data-archive-title]").textContent = title;
    root.querySelector("[data-archive-description]").textContent = discussions
      ? "Read our session transcripts and follow passages into the structural map."
      : symbolPage ? "Explore our symbols, their meanings, and the passages that define them."
      : "Follow our theses, the arguments around them, and what we mean by our words.";
    document.title = `${title} | ${siteTitle}`;
    document.querySelectorAll(".site-nav a").forEach(link => {
      if (link.pathname === location.pathname) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    const notes = document.querySelector("[data-public-discussions]");
    if (notes) notes.hidden = !discussions || location.hash.includes("source=");
  }

  function navigate(url) {
    if (location.pathname + location.hash !== url) history.pushState(null, "", url);
    route();
  }

  function route() {
    const discussions = location.pathname === "/discussions/";
    setPage(discussions);
    if (!kb) return;
    closePopup();
    preview.hidden = true;
    transcripts.clear();
    symbols.clear();
    list.hidden = graph.hidden = sessions.hidden = transcriptSection.hidden = symbolSection.hidden = true;
    root.classList.remove("is-exploring");
    frames = [];
    if (location.pathname === "/symbols-and-meaning/") {
      symbolSection.hidden = false;
      symbols.show(kb);
    } else if (discussions) {
      const params = new URLSearchParams(location.hash.slice(1));
      const source = index.sources.get(params.get("source"));
      if (source) {
        root.classList.add("is-exploring");
        transcriptSection.hidden = false;
        const offset = name => params.has(name) && /^\d+$/.test(params.get(name)) ? Number(params.get(name)) : params.has(name) ? NaN : null;
        transcripts.show(source, model, offset("start"), offset("stop"));
      } else {
        sessions.hidden = false;
        renderSessions();
        if (params.has("source")) sessionRows.prepend(element("p", "That transcript is not in this archive.", "map-error"));
      }
    } else {
      let requested = "";
      try { requested = decodeURIComponent(location.hash.slice(1)); } catch { /* Invalid fragment: show the index. */ }
      if (index.propositions.has(requested)) renderProposition(requested);
      else { list.hidden = false; renderList(); }
    }
  }

  function renderSessions() {
    sessionRows.replaceChildren();
    const ordered = [...kb.sessions].sort((a, b) =>
      (b.date || "").localeCompare(a.date || "") || a.title.localeCompare(b.title) || a.id.localeCompare(b.id));
    for (const session of ordered) for (const id of session.source_ids) {
      const source = index.sources.get(id);
      const link = element("a", session.title, "writing-row session-row");
      link.href = transcriptUrl(id);
      archiveLink(link);
      sessionRows.append(link);
    }
    if (!kb.sessions.length) sessionRows.append(element("p", "No session transcripts have been added yet.", "empty-state"));
  }

  function archiveLink(link) {
    link.addEventListener("click", event => {
      if (event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault(); navigate(link.pathname + link.hash);
    });
  }
  document.querySelectorAll('.site-nav a[href="/discussions/"], .site-nav a[href="/structural-map/"], .site-nav a[href="/symbols-and-meaning/"]').forEach(link => {
    link.addEventListener("click", event => {
      if (!kb || event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault(); navigate(link.pathname); root.scrollIntoView({ block: "start" });
    });
  });
  window.addEventListener("popstate", route);
  window.addEventListener("hashchange", route);
  root.querySelector("[data-sessions-back]").addEventListener("click", () => navigate("/discussions/"));

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
    transcripts.clear();
    symbols.clear();
    model = null;
    kb = null;
    index = {};
    incoming.clear();
    frames = [];
    [rows, grid, context, breadcrumbs, sessionRows].forEach(node => node.replaceChildren());
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
      for (const name of ["propositions", "symbols", "meanings", "arguments", "sessions", "sources"]) {
        index[name] = new Map(kb[name].map(item => [item.id, item]));
      }
      model = createGraphModel(kb);
      incoming = model.incoming;
      form.hidden = true;
      content.hidden = false;
      route();
      if (!list.hidden) search.focus();
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
    const theses = sortedTheses(kb.propositions.filter(p => p.thesis && `${p.text} ${p.topics.join(" ")}`.toLocaleLowerCase().includes(query)), sort.value, model);
    for (const thesis of theses) {
      const row = button("", () => openProposition(thesis.id), "writing-row thesis-row");
      row.dataset.thesis = thesis.id;
      row.append(element("span", thesis.text, "writing-title"));
      const counts = model.descendants(thesis.id);
      const meta = element("span", undefined, "writing-meta clause-counts");
      meta.append(element("span", `${counts.support} support`, "support-key"), document.createTextNode(" · "),
        element("span", `${counts.refute} refute`, "refute-key"), document.createTextNode(` · ${counts.sessions.size} sessions`));
      const probability = element("span", `P = ${probabilityText(model.probability(thesis.id))}`, "thesis-probability");
      probability.title = "Model probability of this thesis. Select its circle’s probability to view the assumptions.";
      meta.append(document.createTextNode(" · "), probability);
      row.append(meta);
      row.append(element("span", thesis.topics.join(" · "), "writing-summary"));
      rows.append(row);
    }
    if (!theses.length) rows.append(element("p", query ? "No theses match your search." : "No theses have been mapped yet. They will appear here as our sessions are added.", "empty-state"));
  }

  search.addEventListener("input", renderList);
  sort.addEventListener("change", renderList);

  function showList() {
    navigate("/structural-map/");
  }

  function openProposition(id, negated = false) {
    navigate(`/structural-map/#${encodeURIComponent(id)}`);
    if (negated) renderProposition(id, negated);
    root.scrollIntoView({ block: "start" });
  }

  function renderProposition(id, negated = false) {
    const proposition = index.propositions.get(id);
    frames = [{ label: proposition.text, literals: [{ proposition_id: id, negated }] }];
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
      const note = element("details", undefined, "reconstruction-note");
      note.append(element("summary", argument.explicitness === "reconstructed" ? "Reconstruction note" : "Extraction note"),
        element("p", "This explains how the exchange was mapped. It is not an extra premise or evidence of validity.", "map-note"),
        element("p", argument.explanation, "argument-explanation"),
        element("p", "Inference context records the connection made between claims; each atom’s passages record that assertion separately.", "map-note"),
        button("Inference context ↗", () => showEvidence("Inference context — why these claims are connected", argument.origins)));
      context.append(note);
      const conclusion = index.propositions.get(argument.conclusion.proposition_id);
      context.append(element("p", `All ${argument.premises.length} premise${argument.premises.length === 1 ? "" : "s"} below jointly ⇒ ${argument.conclusion.negated ? "¬(" : ""}${conclusion.text}${argument.conclusion.negated ? ")" : ""}`, "clause-heading"));
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
    card.append(statement);
    const induced = proposition.evidence_status === "induced";
    card.classList.toggle("induced-atom", induced);
    if (induced) {
      card.append(element("p", "Induced · unsubstantiated", "induced-badge"),
        element("p", "A necessary missing commitment, not an assertion found in the transcripts.", "map-note"));
      const explanation = element("details", undefined, "induction-reason");
      explanation.append(element("summary", "Why this premise is needed"), element("p", proposition.induction.rationale),
        button("Reconstruction context ↗", () => showEvidence("Reconstruction context — not assertion evidence", proposition.induction.context_origins)));
      card.append(explanation);
    }
    const origins = model.assertionOrigins(proposition.id);
    if (origins.length) {
      const sourceButton = button(induced ? "Recorded challenges ↗" : "Passages ↗", () => showEvidence("Statement passages", origins, proposition), "statement-source");
      sourceButton.setAttribute("aria-label", `Passages for: ${proposition.text}`);
      sourceButton.setAttribute("aria-haspopup", "dialog");
      card.append(sourceButton);
    }
    const previous = frames.slice(0, -1).findIndex(frame => frame.literals.some(p => p.proposition_id === proposition.id));
    const argumentsHere = incoming.get(proposition.id) || [];
    const wheel = element("div", undefined, "argument-wheel");
    const center = element("div", undefined, "atom-center");
    const probability = model.probability(proposition.id, literal.negated);
    const estimate = button("", () => showProbability(proposition, literal.negated), "atom-probability");
    estimate.append(element("span", literal.negated ? "P(¬atom)" : "P(atom)", "probability-caption"),
      element("span", probabilityText(probability), "probability-value"));
    estimate.setAttribute("aria-label", `Model probability of this ${literal.negated ? "negated " : ""}assertion: ${probabilityText(probability)}. Show assumptions`);
    estimate.setAttribute("aria-haspopup", "dialog");
    center.append(estimate);
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
    const uses = model.otherTheses(proposition.id, frames[0]?.literals[0].proposition_id);
    if (uses.length) {
      const details = element("details", undefined, "other-uses");
      details.append(element("summary", `Also used in ${uses.length} ${uses.length === 1 ? "thesis" : "theses"}`));
      for (const thesis of uses) details.append(button(thesis.text, () => openProposition(thesis.id)));
      card.append(details);
    }
    // Legacy/unclassified questions are hidden until their session origin has
    // been reviewed. Extraction context is not testimony that a question arose.
    const questions = kb.questions.filter(q => q.origin_kind === "session" && q.proposition_ids.includes(proposition.id));
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
    symbols.close();
    preview.hidden = true;
    popupTitle.textContent = title;
    meaningsBack = back;
    popupBack.hidden = !back;
    if (!dialog.open) dialog.showModal();
    return popupVersion;
  }

  function showProbability(proposition, negated) {
    beginPopup("Model probability");
    const probability = model.probability(proposition.id, negated);
    popupBody.append(element("p", `${negated ? "¬(" : ""}${proposition.text}${negated ? ")" : ""}`),
      element("p", `${negated ? "P(¬atom)" : "P(atom)"} = ${probabilityText(probability)}`, "probability-detail"));
    if (probability === null) {
      popupBody.append(element("p", "No computed probability is included in this archive. This is not a probability of zero."));
      return;
    }
    const prior = kb.inference.priors[proposition.id];
    const group = kb.inference.components.find(c => c.atom_ids.includes(proposition.id));
    const description = prior === "substantiated-leaf"
      ? "Substantiated leaf premise: Beta(5, 2), a soft prior whose mode is 0.8."
      : prior === "induced-leaf"
        ? "Induced leaf premise: Beta(1, 1), a flat prior with no preference."
        : "No explicit atom prior. This probability is derived from the whole connected component.";
    popupBody.append(element("p", description),
      element("p", "Every support and refutation clause uses Beta(7.2, 1). Joint entropy has weight 1; priors are applied once per unique leaf premise, not once per use."),
      element("p", `Exact variable elimination over ${group.atom_ids.length} atoms and ${group.clause_ids.length} clauses. The numerical optimization’s duality gap is ${group.duality_gap.toExponential(1)}.`),
      element("p", "These are model-derived estimates under the agreed priors, not proof or measured truth frequencies. A substantiating passage records an assertion; it does not establish that the assertion is true.", "map-note"));
    if (negated) popupBody.append(element("p", `The circle shows the negated assertion: 1 − P(atom), where P(atom) = ${probabilityText(model.probability(proposition.id))}.`));
  }

  function showMeanings(binding) {
    const symbol = index.symbols.get(binding.symbol_id);
    beginPopup(symbol.label);
    const back = () => showMeanings(binding);
    const selected = element("ul", undefined, "meaning-list");
    const addMeaning = (id, parent, excluded = false) => appendMeaning(id, parent, back, excluded);
    binding.meaning_ids.forEach(id => addMeaning(id, selected));
    popupBody.append(element("p", binding.selection === "ambiguous" ? "The intended meaning remains ambiguous among these alternatives." : binding.selection === "collective" ? "These meanings were deliberately used together." : "Meaning used in this statement.", "map-note"), selected);
    if (binding.origins.length) popupBody.append(button("Interpretation passages ↗", () => showEvidence("Why these meanings apply", binding.origins, null, back)));
    else popupBody.append(element("p", "This usage was reconstructed; no assertion passage substantiates it.", "map-note"));
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

  function appendMeaning(id, parent, back, excluded = false) {
    const meaning = index.meanings.get(id);
    const row = element("li");
    const text = `${excluded ? "Explicitly excluded: " : ""}${meaning.definition}`;
    if (meaning.kind === "normative") {
      row.append(element("span", text), element("p", "No definition was declared. Assumed societal usage is risky: shared understanding has not been established.", "meaning-warning"));
    } else row.append(button(text, () => showEvidence(meaning.definition, meaning.origins, null, back)));
    parent.append(row);
  }

  function showSymbolMeanings(symbol) {
    beginPopup(symbol.label);
    const list = element("ul", undefined, "meaning-list");
    for (const meaning of kb.meanings.filter(m => m.symbol_id === symbol.id)) {
      appendMeaning(meaning.id, list, () => showSymbolMeanings(symbol));
    }
    popupBody.append(list);
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
        const citation = element("a", `${label} · Open in transcript ↗`, "passage-label");
        citation.href = transcriptUrl(source.id, passage.start_char, passage.stop_char);
        archiveLink(citation);
        citation.title = `${passage.file_name}:${passage.start_char}-${passage.stop_char}`;
        citation.dataset.readerSkip = "";
        const text = element("p", undefined, "passage-text");
        const passageLink = element("a", passage.text, "passage-transcript-link");
        passageLink.href = citation.href;
        archiveLink(passageLink);
        text.append(passageLink);
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
