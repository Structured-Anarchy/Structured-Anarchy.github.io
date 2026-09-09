// Shared graph traversal: count each clause once, never unroll cycles as evidence.
export function createGraphModel(kb) {
  const propositions = new Map(kb.propositions.map(p => [p.id, p]));
  const incoming = new Map(), outgoing = new Map(), assertions = new Map();
  const sessionsByFile = new Map();
  const sources = new Map(kb.sources.map(s => [s.id, s]));
  for (const session of kb.sessions) for (const id of session.source_ids) {
    const name = sources.get(id)?.file_name;
    if (!sessionsByFile.has(name)) sessionsByFile.set(name, new Set());
    sessionsByFile.get(name).add(session.id);
  }
  function addOrigins(id, origins) {
    if (!assertions.has(id)) assertions.set(id, new Map());
    for (const origin of origins) assertions.get(id).set(`${origin.file_name}:${origin.start_char}:${origin.stop_char}`, origin);
  }
  kb.propositions.forEach(p => addOrigins(p.id, p.origins));
  for (const occurrence of kb.occurrences) {
    if (occurrence.target_type === "proposition") addOrigins(occurrence.target_id, occurrence.origins);
  }
  for (const argument of kb.arguments) {
    const id = argument.conclusion.proposition_id;
    if (!incoming.has(id)) incoming.set(id, []);
    incoming.get(id).push(argument);
    for (const literal of [...argument.premises, argument.conclusion]) addOrigins(literal.proposition_id, literal.origins);
    for (const literal of argument.premises) {
      if (!outgoing.has(literal.proposition_id)) outgoing.set(literal.proposition_id, []);
      outgoing.get(literal.proposition_id).push(argument);
    }
  }
  const memo = new Map();
  function descendants(id) {
    if (memo.has(id)) return memo.get(id);
    const atoms = new Set(), clauses = new Map(), sessions = new Set(), pending = [id];
    while (pending.length) {
      const next = pending.pop();
      if (atoms.has(next)) continue;
      atoms.add(next);
      for (const origin of assertions.get(next)?.values() || []) {
        for (const sid of sessionsByFile.get(origin.file_name) || []) sessions.add(sid);
      }
      for (const argument of incoming.get(next) || []) {
        clauses.set(argument.id, argument);
        pending.push(...argument.premises.map(p => p.proposition_id));
      }
    }
    const refute = [...clauses.values()].filter(a => a.conclusion.negated).length;
    const result = { atoms, clauses, sessions, support: clauses.size - refute, refute };
    memo.set(id, result);
    return result;
  }
  function transcriptMarkers(fileName) {
    const related = new Map();
    for (const thesis of kb.propositions.filter(p => p.thesis)) {
      for (const pid of descendants(thesis.id).atoms) {
        for (const origin of assertions.get(pid)?.values() || []) {
          if (origin.file_name !== fileName) continue;
          if (!related.has(origin.start_char)) related.set(origin.start_char, new Set());
          related.get(origin.start_char).add(thesis.id);
        }
      }
    }
    return [...related].sort((a, b) => a[0] - b[0]).map(([start, ids]) => ({ start, theses: [...ids].map(id => propositions.get(id)) }));
  }
  return { incoming, outgoing, descendants, transcriptMarkers,
    assertionOrigins: id => [...(assertions.get(id)?.values() || [])] };
}

export function sortedTheses(theses, mode, model) {
  const alphabetical = (a, b) => a.text.localeCompare(b.text) || a.id.localeCompare(b.id);
  return [...theses].sort((a, b) => mode === "support" || mode === "refute"
    ? model.descendants(b.id)[mode] - model.descendants(a.id)[mode] || alphabetical(a, b)
    : a.topics.join(" · ").localeCompare(b.topics.join(" · ")) || alphabetical(a, b));
}
