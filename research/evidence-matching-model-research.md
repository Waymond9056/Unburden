# Research: BERT-family models for requirement↔evidence matching

Status: research only — no production code changed. Scope: evaluate whether a
BERT-based model (and specifically PubMedBERT + MedNLI) is the right next step
for Unburden's evidence engine, and lay out a concrete build plan.

## 1. How requirements, policies, and evidence are represented today

Source: `backend/app/services/policy.py`, `evidence_retrieval.py`,
`evidence_verification.py`, `backend/app/policies/fictional_severe_asthma_pa.json`.

- **Policy/requirement schema** (`RequirementDefinition`): each requirement is a
  structured object with `title`, `description`, `retrieval_terms`,
  `acceptable_document_types`, `must_match_any`, `reject_if_quote_matches_any`,
  `ambiguous_if_quote_matches_any`, optional `temporal` (within N months),
  optional `numeric` (min value + unit substring), `require_interval_days_min`,
  and `min_accepted_candidates`. This is hand-authored JSON, not learned.
- **Retrieval** (`evidence_retrieval.py`): per document page, split into sentence
  spans, keep the best-scoring span per requirement where "best" = most
  `retrieval_terms` substrings matched (plain lowercase substring search — no
  embeddings, no ML). `relevance_score = min(1.0, 0.35 + 0.2 * num_terms)`, a
  hand-picked heuristic. One candidate is kept per page/requirement.
- **Verification** (`evidence_verification.py`): a deterministic rule engine.
  For each `EvidenceCandidate` it checks, in order: quote-is-verbatim-in-source
  page text → acceptable document type → `reject_if_quote_matches_any` phrase
  list → `ambiguous_if_quote_matches_any` phrase list → `must_match_any` phrase
  list → temporal window math → interval-days math → numeric threshold math.
  Output is `ACCEPTED` / `REJECTED` / `NEEDS_REVIEW` per candidate, rolled up to
  `SUPPORTED` / `NOT_ESTABLISHED` / `NEEDS_REVIEW` per requirement.
- **No ML or LLM is wired in yet.** `backend/app/core/config.py` has
  `llm_api_key` / `llm_base_url` (defaults to x.ai's Grok, OpenAI-compatible)
  and the README says it is "optional and reserved for later candidate
  verification" — but nothing currently calls it. `requirements.txt` has no
  `torch`/`transformers`/`sentence-transformers`. `onnxruntime` is present only
  as a transitive dependency of `pymupdf_layout`'s layout-detection model —
  unrelated to this problem, but it does mean ONNX Runtime is already in the
  dependency tree if we want CPU-optimized inference later.
- **`EvidenceCandidate.relevance_score`** (float) and `verification_status`
  (string) already exist in the DB/schema (`backend/app/models/schemas.py`) and
  are shown on the requirements checklist
  (`frontend/src/components/RequirementsChecklist.tsx`), including an NLI match
  percentage. This is a ready-made integration point for a calibrated confidence
  score.
- **MVP.md's explicit design constraint** (section 4.3): "An LLM may propose
  evidence matches, but structured policy constraints and source verification
  should determine whether they can be accepted." The project is deliberately
  anti-hallucination: dates, numeric thresholds, document types, and verbatim
  quote checks are code, not model output, and must stay that way.

**Implication:** the open problem is *not* "replace the rule engine with a
model." It's "replace three specific hand-maintained phrase lists
(`must_match_any`, `reject_if_quote_matches_any`, `ambiguous_if_quote_matches_any`)
with a general semantic-support judgment," plus optionally improving recall in
retrieval. Any model we add is a new *signal* that feeds the existing
pipeline — numeric/temporal/doc-type/quote-verbatim logic stays exactly as is.

## 2. Model comparison

I verified checkpoint availability, pipeline types, and label mappings live
against the Hugging Face Hub API (not just recalled from memory) — details
below so you can reproduce the checks.

| Approach | Verified facts | Fit for Unburden |
|---|---|---|
| **PubMedBERT + MedNLI** (`pritamdeka/PubMedBERT-MNLI-MedNLI`) | Exists, `BertForSequenceClassification`, confirmed `id2label = {0: contradiction, 1: entailment, 2: neutral}`. Only ~6.8K downloads / 6 likes — a single community fine-tune, not an official/heavily-vetted checkpoint. Base model `microsoft/BiomedNLP-PubMedBERT-...` was renamed by Microsoft to **BiomedBERT** (old name 307-redirects). | **Domain mismatch risk:** PubMedBERT is pretrained on PubMed *abstracts/full text* (research-paper register), not clinical notes/pharmacy records/ED summaries, which is what Unburden actually ingests. MedNLI itself is built from MIMIC-III clinical premises, so pairing it with a clinical-note-pretrained encoder (Bio_ClinicalBERT) is more internally consistent than PubMedBERT. MedNLI is also small (14,049 train examples) and narrow (radiology/discharge-summary style). Reported MedNLI test accuracy across BERT/BioBERT/ClinicalBERT/PubMedBERT fine-tunes clusters ~80–84% — no strong published evidence PubMedBERT specifically wins for short declarative clinical sentences like ours. |
| **General DeBERTa-v3 NLI** (`MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`, `cross-encoder/nli-deberta-v3-base`, `-small`, `-xsmall`) | All confirmed to exist. Trained on MNLI+FEVER+ANLI(+SNLI), hundreds of thousands of examples including adversarially mined ones (ANLI). DeBERTa-v3's disentangled attention + ELECTRA-style pretraining gives it materially stronger entailment reasoning than BERT-base/BioBERT architectures (MNLI matched accuracy ~90%+ vs. ~84% MedNLI for the BERT-family checkpoints above). No biomedical vocabulary, but our premises are plain clinical sentences ("Absolute eosinophil count: 420 cells/µL"), not PubMed-abstract jargon — general NLI handles this fine once numeric/date comparison is left to code. | **My recommendation (see §3).** Available in base/small/xsmall sizes to trade accuracy for CPU latency. Zero-shot, no fine-tuning or labeled data required to start. |
| **BGE Reranker v2 M3** (`BAAI/bge-reranker-v2-m3`) | Confirmed, 14.6M downloads — extremely popular general cross-encoder *reranker*. | Great for "is this passage relevant to this query," not "does this passage satisfy this clinical criterion." It outputs a relevance logit, not an entailment/contradiction judgment, so it can't distinguish "mentions eosinophils" from "eosinophils meet the ≥300 threshold" — exactly the failure mode MVP.md warns against ("a medication was prescribed is not proof the patient took it"). Useful for **retrieval**, not verification. |
| **MedCPT** (`ncbi/MedCPT-Cross-Encoder`, `-Query-Encoder`) | Confirmed, 513K downloads. NIH/NLM-trained on real PubMed query↔article click logs. | Same category as BGE: a strong biomedical **retrieval** re-ranker, not a support/entailment classifier. Good candidate if lexical keyword retrieval starts missing paraphrased passages, per MVP.md's own guidance ("add embeddings only if evaluation shows relevant passages are being missed") — but that's a different problem from the one asked about here. |
| **MedGemma 1.5** | Confirmed to exist (`google/medgemma-4b-it`); multimodal, instruction-tuned, several-billion parameters. | Flexible and can reason about numbers/dates in natural language, but heavier (GPU-oriented, slower cold start), harder to get a stable calibrated 0–100 score out of (needs constrained decoding or extra calibration work), and is overkill for what is really a short-sentence entailment subtask once structured checks stay in code. Not worth the integration cost for a hackathon. |
| **LLM evidence verifier** (reuse the already-configured Grok/x.ai or any OpenAI-compatible API) | Infra already stubbed in `config.py`/README ("reserved for later candidate verification"). | Fastest to prototype — no new Python ML deps, can return structured JSON `{status, confidence, rationale}` directly. But: (1) non-deterministic unless pinned to temp=0; (2) verbalized LLM confidence is well known to be poorly calibrated without extra calibration work; (3) it's a network call with per-request cost/latency; (4) MVP.md explicitly wants the demo to "remain testable" and deterministic **when no LLM credentials are configured** — making an LLM the *primary* verifier breaks that fallback requirement. Good as an optional secondary signal (e.g., human-readable rationale text) layered on top of a local model's score, not as the sole classifier. |
| **Interpretable logistic regression over explicit features** | N/A (would be built, not downloaded). | Right idea for the *calibration* step (see §3), wrong idea as a standalone model — Unburden's labeled data (6 seed PDFs × 4 requirements) is far too small to train a classifier from scratch. Best used as a tiny Platt-scaling layer on top of a pretrained NLI model's probabilities, which is standard practice and needs only ~30–50 labeled pairs, not thousands. |

### Direct answer on the pasted claim

**PubMedBERT + MedNLI is not clearly the best choice here**, for three concrete
reasons surfaced by the checks above:
1. **Domain mismatch** — PubMedBERT's pretraining corpus is PubMed research
   literature; Unburden's documents are clinical notes, pharmacy records, lab
   reports, and ED summaries — the register MedNLI itself and Bio_ClinicalBERT
   were built from, not PubMedBERT's.
2. **Checkpoint provenance** — the only ready MedNLI fine-tune of PubMedBERT I
   found (`pritamdeka/PubMedBERT-MNLI-MedNLI`) is a single community upload
   with very low usage; its label ordering happens to check out, but there's
   no official/widely-vetted equivalent.
3. **No accuracy edge for this task** — published MedNLI numbers put
   BERT/BioBERT/ClinicalBERT/PubMedBERT fine-tunes within a few points of each
   other (~80–84%), while modern general-purpose DeBERTa-v3 NLI models are
   trained on far more data (including adversarial examples) and are
   structurally stronger at entailment — with no fine-tuning required at all.

This doesn't mean biomedical pretraining is worthless — it means for *this*
specific subtask (short-sentence support/contradiction/neutral judgment, with
numeric/date/doc-type reasoning deliberately kept out of the model), a strong
general NLI model is the better default, with a MedNLI-tuned model as an
optional second opinion rather than the primary engine.

## 3. Recommendation

**Primary: zero-shot general-domain DeBERTa-v3 NLI cross-encoder**, e.g.
`MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` (184M params) or
`cross-encoder/nli-deberta-v3-small`/`-xsmall` if CPU latency is tight.

- **Input:** `premise = candidate.supporting_quote`, `hypothesis` = a short
  natural-language statement of the requirement. The repo already carries
  human-readable `title`/`description` per `RequirementDefinition` — start by
  templating hypotheses from those (e.g. "This document establishes a
  documented severe persistent asthma diagnosis."), hand-tune wording per
  requirement for grammaticality (4 requirements today — trivial to write by
  hand).
- **Output:** softmax over {entailment, neutral, contradiction}. Map to a
  0–100 score (details below).
- **No training required to start** — this is the single biggest hackathon-fit
  factor. No PhysioNet data-use-agreement, no GPU, no fine-tuning loop.
- **Runs offline/CPU**, consistent with MVP.md's requirement that the demo stay
  deterministic and testable without external API credentials. A DeBERTa-v3-base
  forward pass on one short premise/hypothesis pair is tens of milliseconds on
  CPU; batch all candidates for a requirement into one forward pass for more
  headroom.
- **Feeds, not replaces, the rule engine:**
  - Use the contradiction class to generalize `reject_if_quote_matches_any`
    (today a hand-maintained phrase list) to catch paraphrased negations.
  - Use low max-probability / high neutral-probability to generalize
    `ambiguous_if_quote_matches_any` → `NEEDS_REVIEW`.
  - Use the entailment probability (after calibration) to populate
    `relevance_score` / a new `support_confidence` field for the UI and for
    `strength_score` in packet optimization.
  - Keep date math, unit/threshold math, document-type allow-lists, and
    verbatim-quote verification exactly as they are today — neural NLI models
    are known to be unreliable at precise numeric/temporal reasoning, and
    MVP.md explicitly wants that logic in code.

**Optional stretch/ensemble:** add a MedNLI-tuned biomedical model (prefer
`emilyalsentzer/Bio_ClinicalBERT` fine-tuned on MedNLI over PubMedBERT, since
Bio_ClinicalBERT's MIMIC-III pretraining matches the clinical-note register;
or pragmatically reuse `pritamdeka/PubMedBERT-MNLI-MedNLI` as-is) as a second
opinion. When the general DeBERTa-v3 model and the biomedical model disagree
on label, route to `NEEDS_REVIEW` — this fits Unburden's existing philosophy of
routing ambiguity to a human rather than guessing. This is a nice-to-have, not
required for a working demo.

**Not recommended as the primary mechanism:** BGE/MedCPT alone (retrieval
relevance ≠ clinical support — don't let a relevance score masquerade as
proof), MedGemma (heavier than the subtask needs), a pure LLM verifier as the
*only* signal (breaks the offline/deterministic fallback), and training a
classifier from scratch (no data for it).

### Calibrating 0–100% confidence

1. Start with `score = 100 * p_entailment` from the zero-shot model as a
   baseline — already roughly monotonic and usable for ranking/UI.
2. Hand-label a small dev set (~30–50 premise/hypothesis pairs; see §4) with
   gold labels `support` / `contradict` / `neutral`.
3. Fit a simple **Platt scaling** (`sklearn.linear_model.LogisticRegression`
   on the model's raw entailment logit, or `sklearn.isotonic.IsotonicRegression`
   for a monotonic non-parametric fit) against the gold labels. This needs
   only tens of examples, not thousands, because you're calibrating one
   scalar, not training a classifier.
4. Bake the fitted scaler's constants into the service module (no live
   retraining needed); re-fit only if you add more requirements or see
   drift.
5. Report calibration quality with a reliability diagram or Brier score on a
   held-out slice of the dev set, not just raw accuracy.

## 4. Small evaluation plan

Grounded in the **existing synthetic seed documents**
(`backend/app/services/seed.py`) so it's reproducible without new data:

| # | Requirement | Passage (source) | Gold label | Why it's a good test |
|---|---|---|---|---|
| 1 | `documented_severe_asthma` | "Assessment: Severe persistent asthma, ICD-10 J45.50…" (`pulmonary_consult_note.pdf`) | **Support** | Canonical positive; current rule engine already passes this via `must_match_any`. |
| 2 | `qualifying_eosinophil_result` | "Absolute eosinophil count: 420 cells/µL (reference range 0–500). Result qualifies…" (`lab_eosinophils.pdf`) | **Support** (concept only — numeric threshold stays in code) | Confirms the model isn't asked to do the ≥300 comparison itself. |
| 3 | `recent_exacerbation_history` | "Treated for severe asthma exacerbation with nebulized bronchodilators and systemic corticosteroids…" (`exacerbation_er_note.pdf`) | **Support** | Positive with paraphrased terms not in `must_match_any` verbatim list ("treated for … with … systemic corticosteroids" vs. the literal phrase "systemic corticosteroid"). |
| 4 | `prior_controller_therapy` | "Documented high-dose inhaled corticosteroid / long-acting beta agonist trial: fluticasone-salmeterol 500/50 mcg twice daily from 2024-11-01 through 2025-09-30…" (`medication_history.pdf`) | **Support** (concept only — duration math stays in code) | Tests that dose/date noise doesn't confuse the entailment judgment. |
| 5 | `recent_exacerbation_history` | "No systemic corticosteroid exacerbation treatment occurred at this visit." (`misleading_allergy_note.pdf`) | **Contradict** | Today this only works because of a hand-authored `reject_if_quote_matches_any` phrase that matches this exact wording. Key generalization test: does the model's contradiction class catch *paraphrases* of this negation that aren't in the list? |
| 6 | `documented_severe_asthma` | "Patient has seasonal allergic rhinitis. Inhaled corticosteroid spray for nasal symptoms was discussed." (`misleading_allergy_note.pdf`) | **Neutral/reject** | Keyword overlap trap ("inhaled corticosteroid") with no actual asthma diagnosis — directly tests the MVP's stated concern that a prescribed/discussed medication is not proof of the clinical fact. |
| 7 | `qualifying_eosinophil_result` | "Eosinophils mentioned qualitatively as 'borderline elevated historically' without a dated quantitative laboratory value." (`misleading_allergy_note.pdf`) | **Neutral → NEEDS_REVIEW** | Currently caught by an `ambiguous_if_quote_matches_any` phrase; tests whether the model recognizes "mentioned but not quantified" as insufficient without that exact phrase. |
| 8 | `prior_controller_therapy` | A paraphrase like "Biologic step-up therapy was discussed; controller trial not yet confirmed." (new, author by hand) | **Neutral → NEEDS_REVIEW** | Tests generalization of the `discussed`/`considered` ambiguity pattern to wording not in the current list. |
| 9 | `documented_severe_asthma` | "Possible asthma, further workup pending." (new, author by hand) | **Neutral → NEEDS_REVIEW** | Hedged-diagnosis language; already an explicit ambiguous phrase for a different requirement — reuse the pattern as an out-of-list paraphrase. |
| 10 | `recent_exacerbation_history` | "Diagnosis reiterated: severe persistent asthma… No new laboratory values." (`duplicate_consult_summary.pdf`) | **Neutral/no relevant claim** | Negative-by-irrelevance control — passage is about diagnosis, not exacerbation; checks the model doesn't over-trigger entailment on topical overlap. |

Build to ~20–30 pairs by adding a few more hand-written paraphrases per
requirement (2–3 positive paraphrases, 1–2 negations, 1–2 hedges each) — small
enough to label in under an hour, large enough to fit a Platt-scaling
calibrator and catch obvious regressions.

**Metrics to report:**
- 3-way accuracy/F1 (support/contradict/neutral) vs. gold labels.
- Agreement rate with the *current* rule-based `verification_status` on the
  existing seed corpus (flag any disagreement for manual review — don't let
  the new signal silently flip an already-correct rule-based verdict).
- Calibration: reliability diagram or Brier score on the 0–100 output.
- Latency: p50/p95 per-candidate inference time on CPU, batched per requirement.

## 5. Build/train walkthrough

### Path A — recommended for the hackathon: zero-shot, no training

1. **Dependencies:** add `transformers` and a CPU build of `torch` to
   `backend/requirements.txt` (optionally `optimum[onnxruntime]` later for
   faster CPU inference, since `onnxruntime` is already pulled in transitively).
2. **New module** `backend/app/services/nli_support.py` (mirrors the existing
   `services/` pattern): load the tokenizer/model once (module-level or
   `lru_cache`, like `policy.load_policy`), expose
   `score_support(premise: str, hypothesis: str) -> SupportScore` returning
   `(label, p_entail, p_neutral, p_contra, confidence_0_100)`.
3. **Hypotheses:** add a `nli_hypothesis` field per requirement in
   `fictional_severe_asthma_pa.json` (or derive one programmatically from
   `description` as a fallback) so hypotheses live in policy data, not code.
4. **Wire into `evidence_verification.verify_candidate`:** call the scorer on
   `(candidate.supporting_quote, requirement.nli_hypothesis)` as an *additional*
   check, not a replacement:
   - contradiction above a threshold → `CANDIDATE_REJECTED` (generalizes
     `reject_if_quote_matches_any`);
   - low max-probability / neutral-dominant → `CANDIDATE_NEEDS_REVIEW`
     (generalizes `ambiguous_if_quote_matches_any`);
   - otherwise fall through to the existing `must_match_any`/temporal/numeric/
     doc-type checks unchanged.
   - Store the calibrated 0–100 score in `relevance_score` (or a new column)
     so it's available to the UI and to `evidence_packet.py`'s
     `strength_score`.
5. **Calibrate** per §3 using the eval set from §4; keep the fitted constants
   as plain Python constants in the module (no live retraining needed for a
   hackathon).
6. **Tests:** add `backend/tests/test_nli_support.py` mirroring the style of
   `test_evidence_verification.py`, using the §4 pairs as fixtures; assert
   label and rough score bucket (not exact floats — HF models are
   deterministic given fixed weights/eval mode, but don't hardcode floats to
   many decimal places).
7. **Keep an escape hatch:** gate the new check behind a settings flag (e.g.
   `USE_NLI_SUPPORT`, mirroring how the app already falls back to deterministic
   behavior when no LLM key is configured) so CI/offline runs aren't forced to
   download ~500MB–700MB of model weights.

### Path B — optional: fine-tune or reuse a MedNLI-tuned biomedical model (stretch/ensemble only)

1. Prefer `emilyalsentzer/Bio_ClinicalBERT` as the base encoder over
   PubMedBERT, since MedNLI's premises are MIMIC-III clinical notes, not
   PubMed abstracts.
2. MedNLI's **official** distribution is credentialed via PhysioNet (data use
   agreement); several uncredentialed HF mirrors exist (e.g.
   `bigbio/mednli`, `presencesw/mednli`) but their license compliance is
   unclear — for a hackathon it's both faster and safer to **reuse an
   existing fine-tuned checkpoint** (e.g. `pritamdeka/PubMedBERT-MNLI-MedNLI`,
   confirmed `id2label = {0: contradiction, 1: entailment, 2: neutral}`)
   rather than redistributing/training on the raw dataset yourselves.
3. If you do fine-tune from scratch (only worth it outside hackathon time
   constraints): standard HF `Trainer` recipe — tokenize premise+hypothesis
   pairs with `[SEP]`, 3-way classification head, ~3 epochs, batch size 16–32,
   lr 2e-5, MedNLI's ~14K train examples train in well under an hour on a
   single free-tier GPU. Evaluate on the official MedNLI test split first
   (sanity check, expect ~80–84% accuracy) **and separately** on the §4 eval
   set, since MedNLI accuracy doesn't guarantee transfer to Unburden's actual
   requirement-matching task.
4. Integrate identically to Path A steps 2–7, just swapping the model id —
   and always spot-check `id2label` ordering before trusting output, since
   community checkpoints aren't guaranteed to use a consistent label order.
5. Use agreement/disagreement between Path A's general model and Path B's
   biomedical model as an extra `NEEDS_REVIEW` trigger if you build both.

## 6. Summary

- Current engine is 100% deterministic (lexical retrieval + rule-based
  verification); there is no ML in the loop yet, and the architecture is
  explicitly designed to keep numeric/temporal/doc-type/quote logic in code.
- The open problem is generalizing three hand-maintained phrase lists
  (`must_match_any`, `reject_if_quote_matches_any`, `ambiguous_if_quote_matches_any`)
  into a semantic support/contradiction/neutral judgment, with a calibrated
  0–100 score as a side benefit.
- **PubMedBERT + MedNLI is not the strongest option** for this: domain
  mismatch (PubMed abstracts vs. clinical notes), a thin/unvetted available
  checkpoint, and no accuracy edge over modern general NLI models for this
  kind of short declarative sentence.
- **Recommended: zero-shot general-domain DeBERTa-v3 NLI** (e.g.
  `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`), calibrated with a small
  Platt-scaling layer on ~30–50 hand-labeled pairs drawn from the existing
  seed corpus. No training, no GPU, no new data-access friction, CPU latency
  in the tens-of-milliseconds range, and it plugs into the existing
  `EvidenceCandidate.relevance_score`/`verification_status` fields without
  disturbing the deterministic checks the project is built around.
- A MedNLI-tuned biomedical model (Bio_ClinicalBERT preferred over PubMedBERT)
  is a reasonable optional second opinion/ensemble member, not a primary
  replacement.

## 7. Refinement from early testing: NLI failure modes and mitigations

Early hands-on testing against the zero-shot DeBERTa-v3 approach surfaced three
failure modes worth designing around explicitly. None of them change the
architecture conclusion in §3/§6 — they sharpen it.

1. **Arithmetic/date comparisons ("420 ≥ 300", "≥90 day interval") are not
   reliable NLI tasks, medical-tuned or not.** This confirms the original
   design boundary: DeBERTa is a support/contradiction *signal*, never the
   arbiter of numeric thresholds or temporal windows — that logic stays in
   `evidence_verification.py` exactly as today.

2. **Long/compound, policy-style hypotheses push clear supports into
   "neutral."** Entailment models score against the whole hypothesis; a
   premise that fully supports the clinical fact but doesn't restate every
   incidental clause (document type, time window, count) will often fail to
   reach "entailment." This is a hypothesis-framing problem, not a missing-
   medical-pretraining problem. **Mitigation:** write one atomic clinical
   proposition per requirement as the NLI hypothesis (e.g. "The patient has
   severe persistent asthma"), and keep acceptable-document-type/temporal/
   count conditions as separate code-side AND terms — reusing the policy
   schema's existing `logic: AND/OR` combinator pattern instead of inventing a
   new one.

3. **Unrelated or incomplete text is often mislabeled "contradiction" instead
   of "neutral."** This is a documented general-domain NLI artifact (training-
   data shortcuts/hypothesis-only bias; negation cues and unrelated content
   getting pulled toward "contradiction" in stress-test evaluations), not a
   biomedical-vocabulary gap. **Mitigations to build into Path A:**
   - **Asymmetric contradiction threshold:** only accept the contradiction
     label (→ `CANDIDATE_REJECTED`) when `p_contra` wins the argmax *and*
     clears a conservative margin over `p_entail`/`p_neutral`, tuned on the
     §4 calibration set; otherwise fall through to `NEEDS_REVIEW`. A false
     contradiction silently discards real evidence, which is the costlier
     error for this product.
   - **On-topic gating:** candidates only reach NLI scoring after passing
     requirement-specific retrieval, so irrelevance is already partly
     filtered — but if retrieval is ever loosened (e.g. semantic retrieval
     per §2's MedCPT/BGE option), an irrelevant passage should fall through
     to "no evidence" (`NOT_ESTABLISHED`), never get labeled `REJECTED` via a
     spurious contradiction call.

**On domain nuance:** the two cases most likely to need biomedical-specific
understanding — nasal ICS spray vs. pulmonary controller therapy, and
"borderline elevated historically" eosinophils — are already handled today by
hand-authored `reject_if_quote_matches_any`/`ambiguous_if_quote_matches_any`
entries in `fictional_severe_asthma_pa.json`. A biomedical-tuned ensemble
member's real value is catching *new, unenumerated* confusable pairs beyond
what's already hand-listed, which keeps it a legitimate stretch goal rather
than a baseline requirement.

**Net effect on the plan:** DeBERTa-v3 remains a generalized negation/
ambiguity signal feeding `NEEDS_REVIEW`/`REJECTED` routing and the calibrated
confidence score — using atomic (not compound) per-requirement hypotheses and
conservative, asymmetric thresholds against false contradiction — while all
quantitative, temporal, and document-type logic stays exactly where Milestone
3 already put it.
