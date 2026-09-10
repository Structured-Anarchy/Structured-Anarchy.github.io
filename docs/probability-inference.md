# Probability inference: maximum entropy over connected components

This implements the model agreed in the design discussion for [issue #2](https://github.com/Structured-Anarchy/Structured-Anarchy.github.io/issues/2). It is a derived model of the extracted argument graph, not a truth verdict, an extraction step, or a statistical estimate from speaker counts. The initial parameter choices are fixed assumptions, not learned confidence values.

## Model decision

Each unique proposition is one Boolean variable, regardless of how often it occurs or whether it is also a thesis entry point. Negation is the complement of that variable, not another independent proposition. A support or refutation clause is a material implication from its signed antecedent conjunction to its signed consequent.

For a joint distribution \(p\), let \(s_j=P_p(S_j)\) be the probability of a whole clause. For \(S_j=E_j\Rightarrow C_j\), this is \(1-P_p(E_j\land\neg C_j)\), not the conditional probability \(P_p(C_j\mid E_j)\). An unlikely antecedent can make a clause highly satisfied. Antecedent length and dependence therefore affect results; no independence assumption is made within a connected component.

The objective, with natural logarithms and entropy weight one, is

\[
\max_p H(p)+6.2\sum_j\log s_j+
\sum_{i\in L_{\mathrm{subst}}}\left[4\log P_p(X_i)+\log(1-P_p(X_i))\right],
\qquad p\ge0,\quad\sum_xp_x=1.
\]

The log terms are Beta-shaped soft preferences:

| Item | Fixed preference |
| --- | --- |
| Every whole clause, support or refutation | Beta(7.2, 1) |
| Induced leaf premise | Beta(1, 1), contributing no term |
| Substantiated leaf premise | Beta(5, 2) |
| Non-leaf atom, or isolated assertion not used as a premise | No explicit atom-prior term |

A leaf premise is an atom used in at least one antecedent with **no incoming clause of either sign**. A refutation alone makes an atom non-leaf. A sourced leaf is identified by assertion origins and a non-induced evidence status. An induced atom's reconstruction context or recorded objections do not count as substantiation. Classification is recomputed when packing; adding a clause can change which atoms receive a leaf prior.

Each prior is applied once per unique eligible atom. A thesis that is also used as a leaf premise follows the same rule; the thesis flag does not create a second variable or a second prior. Evidence occurrences, additional citations, recursive visits and shared paths never multiply a factor. Duplicate clauses are rejected by knowledge validation before inference.

Beta(7.2, 1) has mean approximately 0.878 and mode 1; Beta(5, 2) has mean approximately 0.714 and mode 0.8. The objective favors densities, not those means as constraints. The computed values are regularized point estimates, **not** a Bayesian posterior over joint tables or uncertainty intervals. All constraints in this initial model are soft. Normative assertions use the same explicit model assumptions; the result is conditional on the recorded interpretations and does not resolve ambiguous meanings or distinguish worldviews automatically.

The distribution is inferred jointly, not by one-way bottom-up propagation. Conclusions and competing arguments can revise premise probabilities and their dependence. Components containing only cycles can still be solved without leaf priors. An isolated atom with no prior has probability 0.5 from maximum entropy; that is not evidence for or against it. Numeric estimates must remain visibly identified as model-derived, with assumptions accessible from each atom circle.

## Connected components and exact computation

Components are undirected connected components of the atom–clause factor graph: all variables in a clause belong together. In particular, two theses sharing a premise must be solved together, even if neither thesis appears in the other's ancestor tree. The model has no factors between components. Entropy is maximal when these disconnected components are independent, so solving them separately is equivalent to solving the global objective.

Every log term can be written as \(c_k\log\mathbb{E}_p[f_k]\), where \(f_k\) is a Boolean indicator. Clauses have coefficient 6.2; eligible leaves have indicators for truth and falsity with coefficients 4 and 1. For positive dual weights \(w_k\),

\[
p_w(x)=Z(w)^{-1}\exp\!\left(\sum_k w_k f_k(x)\right).
\]

The strictly convex dual is minimized:

\[
D(w)=\log Z(w)-\sum_k c_k\log w_k+\sum_k c_k(\log c_k-1),
\qquad \nabla_kD=\mathbb{E}_{p_w}[f_k]-c_k/w_k.
\]

The optimum has \(w_k=c_k/\mathbb{E}[f_k]\ge c_k\). L-BFGS-B optimizes within these bounds using exact expectations. Min-fill variable elimination computes the partition function in log space. A reverse pass through the elimination program computes all feature and atom marginals. Zero unary potentials recover atoms without adding priors. No joint table of size \(2^n\), sampling, mean-field approximation, or cycle unrolling is used.

The exponential cost is in elimination width, not just component size. Before allocating tables, inference enforces a maximum of 262,144 states per factor and 4,194,304 total planned states. An oversized component fails explicitly; it is never split across dependencies or silently approximated.

For each component, the stored dual weights permit independent reevaluation of the marginals and the primal–dual gap:

\[
D(w)-F(p_w)=\sum_k c_k\big[r_k-1-\log r_k\big],
\qquad r_k=w_k\mathbb{E}_{p_w}[f_k]/c_k.
\]

Publishing requires a finite gap at most \(10^{-10}\). This certifies numerical objective accuracy under exact marginal inference, not epistemic certainty. The solver's success flag is not sufficient by itself. Tests compare factor evaluation and gradients against complete enumeration, reproduce the fictional opposing-clause examples, and exercise cycles, signed premises, shared atoms, disconnected components, resource limits and failed convergence.

## Private export and display

`conda run -n structured_anarchy_py python scripts/knowledge.py infer` validates the knowledge base and writes an inspectable report to ignored `data/knowledge/inference.json`. It does not edit source text, extracted assertions, source pointers, or the published archive.

`pack` always recomputes and verifies inference before modifying the encrypted export; it does not trust that local report as a cache. The derived report is a separate authenticated ciphertext resource referenced by an optional `inference` entry in the version-1 encrypted catalog. The knowledge schema and authoring TOML remain unchanged. The report records model version, priors, complete component membership, numeric marginals, dual weights, and diagnostics, and is bound to the exact rendered graph's SHA-256. Verification decrypts it, recomputes marginals and certificates, and rejects stale, incomplete or invalid results. Legacy archives without the optional entry still restore.

The browser loads the report only after unlocking and checks graph binding, model configuration, coverage and probability ranges. It never computes, stores or publishes readable results in public HTML or browser storage. Locking clears displayed results and the in-memory archive. Older archives show an unavailable value, not an invented zero or 0.5.

The thesis list shows `P` beside its existing counts and supports highest/lowest probability sorting. Sorting uses full numeric precision, with alphabetical ties; unavailable estimates are last in either direction. Atom circles show probabilities rounded to three decimal places. Negated circles show \(1-P(X)\), clearly labelled `P(¬atom)`. Selecting a circle's value opens its prior classification, component method and model assumptions without adding another explanatory paragraph to the list.

No frontend inference backend, external service, tracking, giscus or deployment configuration is introduced. NumPy and SciPy are authoring/test dependencies; the site remains static and the browser uses the existing authenticated archive.
