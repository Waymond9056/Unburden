# Build Unburden — AI-Powered Prior Authorization Evidence Engine

## Project overview

We are building Unburden, a healthcare hackathon project that helps pulmonology practices prepare prior authorization documentation for insurance providers.

**The problem:** Insurance companies require specific medical evidence before approving certain treatments. Unfortunately, that evidence is often scattered across different hospitals, EHR systems, prescriptions, laboratory reports, and clinical notes. Clinicians and administrative staff spend significant time finding, interpreting, and assembling the appropriate documents.

**Our solution:** Given an insurance policy and a collection of patient medical documents, Unburden automatically identifies supporting evidence, determines which documentation requirements are not yet established, and assembles an optimized, source-verifiable evidence packet for clinician review.

The application's primary innovation is its **insurance evidence retrieval, verification, and selection engine**, not medical summarization.

This is a hackathon MVP. Prioritize a functional, technically credible end-to-end demonstration over production infrastructure or unnecessary features.

## 1. Technology stack

Use:

- Frontend: Next.js, React, TypeScript, Tailwind CSS, shadcn/ui.
- Backend: Python, FastAPI, Pydantic.
- Storage: SQLite for structured data, local filesystem for original PDFs.
- PDF processing: PyMuPDF.
- AI: A configurable LLM API with structured JSON output.
- Testing: pytest for backend logic.

Keep the frontend and backend separate and communicate through REST endpoints.

Use simple, maintainable architecture. Don't introduce microservices, graph databases, agent frameworks, or complex infrastructure unless necessary.

## 2. MVP scope

We will initially support:

- One synthetic patient.
- One fictional, illustrative pulmonary prior authorization policy.
- PDF document uploads.
- Unstructured clinical note extraction.
- Evidence retrieval and policy evaluation.
- Evidence packet generation.
- Incremental updates when new documents arrive.
- A simple clinician-facing dashboard.

The policy should represent a hypothetical severe-asthma treatment authorization, with requirements such as a documented diagnosis, prior controller therapy, and qualifying laboratory or clinical history evidence.

**Important:** Clearly label the sample policy as fictional. Its criteria must not be represented as the actual requirements of any insurer.

Design the policy schema so that real, verified insurance policies can be added later.

Do not implement Chert, FaceTime, actual EHR connections, authentication, or insurance submissions yet.

## 3. Document ingestion

Build a simple document upload interface supporting multiple PDFs.

When a document is uploaded:

1. Store the original document.
2. Extract its text, preserving page boundaries.
3. Extract clinically relevant structured observations with an LLM.
4. Store those observations with their source document, page, and supporting text.
5. Make the observations available to the evidence engine.

Clinical observations might include diagnoses, medications, previous treatment trials, laboratory measurements, hospital visits, and relevant dates.

Represent each observation with a schema containing:

- Clinical concept or event type.
- Extracted value and units, where relevant.
- Date or applicable time interval.
- Document identifier.
- Source page.
- Exact supporting quotation.
- Extraction uncertainty or review status.

Do not treat extracted text as automatically verified clinical truth.

Preserve original documents even when their information overlaps. We are not building global medical history reconciliation or deduplication for this MVP.

## 4. The core innovation: Evidence engine

This is the most important component of the project.

The engine receives:

**Input A:** A structured insurance policy containing documentation requirements.

**Input B:** A patient's available medical documents and extracted clinical observations.

It produces:

- The requirements supported by available evidence.
- Supporting clinical observations and exact document citations.
- Requirements not established by available records.
- Ambiguous or contradictory evidence requiring review.
- A proposed selection of documents for an insurance evidence packet.

### 4.1 Policy representation

Represent insurance requirements as structured conditions rather than relying entirely on a single LLM prompt.

Support:

- AND / OR relationships between requirements.
- Clinical concept matching.
- Temporal restrictions, such as evidence within the last 12 months.
- Numerical comparisons where needed.
- Acceptable documentation types.
- Required evidence counts for simple cases.

The MVP policy can be manually encoded in JSON.

Do not build automatic insurance policy parsing in the initial version.

### 4.2 Evidence retrieval

For each policy requirement, retrieve potentially relevant clinical observations from all available documents.

Use semantic matching where appropriate, but make sure evidence is not accepted merely because it contains related keywords.

For example, documentation that a medication was prescribed is not necessarily proof that the patient took it.

Separate candidate retrieval from final requirement verification.

Every accepted evidence match must retain a source citation.

### 4.3 Evidence verification

Evaluate candidate evidence against the policy conditions.

The engine should check:

- Whether the medical concept actually satisfies the requirement.
- Whether the event date falls within the relevant time window.
- Whether the document type is acceptable.
- Whether the supporting quotation can be found in the original extracted text.
- Whether contradictory or ambiguous information requires human review.

Use three primary statuses:

- SUPPORTED: Available, source-linked evidence establishes the documentation requirement under the configured rules.
- NOT_ESTABLISHED: The available records do not establish the requirement.
- NEEDS_REVIEW: Evidence is ambiguous, conflicting, or cannot be reliably verified.

Never assume that missing documentation means the patient does not clinically meet a criterion.

Never invent evidence or citations.

An LLM may propose evidence matches, but structured policy constraints and source verification should determine whether they can be accepted.

### 4.4 Evidence packet optimization

Once supporting evidence is identified, select a compact set of documents covering the supported documentation requirements.

We want to avoid sending dozens of redundant documents when a small set provides the necessary evidence.

Model document selection as a weighted set-cover problem.

For the MVP, use a simple exact search for a small number of documents or a greedy approximation.

Prioritize:

1. Covering as many established requirements as possible.
2. Selecting verified, source-backed evidence.
3. Minimizing redundant documents.
4. Minimizing unnecessary page count.

Do not let optimization override evidence correctness.

Store which requirements each selected document supports.

### 4.5 Missing-evidence identification

For requirements not established by the available records, generate an actionable explanation.

For example:

"Recent laboratory documentation is required by this example policy, but no qualifying report was located in the uploaded documents."

Suggest the kind of document that might help establish the requirement.

Do not assume an unknown external document exists.

## 5. Incremental updates

When another document is uploaded:

1. Extract and store the new observations.
2. Reevaluate the affected policy requirements.
3. Update the evidence matches and proposed packet.
4. Show which requirements changed status.
5. Preserve previous sources and review decisions.

For the MVP, reevaluating the whole small policy is acceptable. Avoid unnecessary complexity around incremental graph algorithms.

## 6. Clinician dashboard

Build a polished but simple interface.

The main dashboard should include:

**Document library**
- Uploaded documents.
- Source name and upload date.
- PDF preview.
- Extracted clinical observations.

**Insurance requirements**
- A list of documentation requirements.
- Supported / Not Established / Needs Review statuses.
- Supporting observations.
- Clickable source citations linking to the original PDF page.

**Evidence packet**
- Automatically selected documents.
- Requirements covered by each.
- Ability to preview the supporting material.
- Ability to export a human-reviewable summary.

**Missing information**
- Requirements without adequate documentation.
- Suggested additional document types.
- Status changes after new uploads.

Build the UI so the value is immediately understandable to someone who knows nothing about prior authorization.

## 7. Synthetic demo dataset

Create synthetic PDFs and a small labeled evaluation dataset.

Include three test scenarios:

**Scenario A — Complete evidence**

The uploaded documents contain adequate supporting documentation for every requirement in the example policy.

Expected behavior: all requirements are supported, with valid citations.

**Scenario B — Missing evidence**

One required laboratory report is absent.

Expected behavior: the relevant requirement is NOT_ESTABLISHED, and the system recommends obtaining that type of record.

When the missing report is uploaded, the checklist updates appropriately.

**Scenario C — Overlapping and misleading evidence**

Several documents repeat the same medical information, while another contains similar but nonqualifying evidence.

Expected behavior: the system avoids selecting unnecessary documents, does not mistake mere relevance for qualifying evidence, and flags ambiguities where necessary.

Use obviously fictional patient identities and medical information.

No real patient data.

## 8. Evaluation and technical demonstration

We want to prove that the evidence engine does more than summarize PDFs.

Create automated tests for:

- Structured policy evaluation.
- Temporal constraints.
- AND / OR requirement logic.
- Evidence selection.
- Unsupported-evidence rejection.
- Source citation verification.
- Missing-document handling.
- Packet optimization.

Prioritize correctness, auditability, and repeatability.

## 9. Required API

Start with these conceptual endpoints, adjusting the implementation if needed:

- POST /patients/{id}/documents
- GET /patients/{id}/documents
- GET /patients/{id}/observations
- GET /patients/{id}/policy-evaluation
- POST /patients/{id}/evaluate
- GET /patients/{id}/evidence-packet

Make the ingestion API independent of the upload UI. Later, an external FaceTime agent should be able to submit documents through the same backend.

## 10. Out of scope

Do not build:

- Chert / FaceTime integration yet.
- Global clinical event reconciliation.
- A complete medical knowledge graph.
- An insurance approval prediction model.
- Automatic submissions to insurance companies.
- A general-purpose medical chatbot.
- Real EHR synchronization.
- Support for every insurance provider.
- Production patient authentication infrastructure.

This is an evidence-preparation prototype, not a clinical decision-maker or autonomous insurance agent.

## 11. Implementation sequence

Implement in this order:

**Milestone 1:** Project scaffolding, database schema, PDF upload, text extraction, and synthetic seed documents.

**Milestone 2:** Structured clinical observation extraction with persistent source citations.

**Milestone 3:** Structured insurance policy representation and evidence retrieval/verification engine.

**Milestone 4:** Document selection optimization and missing-evidence checklist.

**Milestone 5:** Functional clinician dashboard and PDF previews.

**Milestone 6:** Automated evaluation, end-to-end demo testing, and UI polish.

Make sure each milestone runs independently before proceeding.

## 12. Definition of done

The MVP is complete when we can:

1. Upload a collection of synthetic patient medical documents.
2. Select the example insurance policy.
3. Automatically identify supported, missing, and ambiguous documentation requirements.
4. Click a supporting finding to see its original document and page.
5. Generate a compact, source-backed evidence packet.
6. Upload an additional relevant document.
7. Watch the insurance evidence checklist update correctly.
8. Run automated tests demonstrating the system's behavior.

The system must not claim that insurance coverage has been approved or that the selected packet guarantees authorization.

## Start now

First inspect the existing repository, if any.

Provide a concise implementation plan and proposed directory structure, then begin Milestone 1.

Do not attempt to build every component simultaneously.

Prioritize a working backend and evidence engine over visual polish. Avoid implementing unnecessary abstractions or libraries.

Use environment variables for model API credentials, provide an .env.example, and include clear local setup instructions.

If no LLM credentials are configured, make the synthetic fixtures usable through deterministic pre-extracted observations so the demo and core algorithm remain testable.

The most important principle:

**We are not building an AI that summarizes medical records. We are building an evidence engine that converts messy medical documentation into a verifiable insurance evidence packet.**