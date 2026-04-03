# DocuBot Model Card

This model card summarizes the current DocuBot behavior across three modes:

1. Naive LLM over full docs
2. Retrieval only
3. RAG (retrieval plus LLM)

---

## 1. System Overview

**What is DocuBot trying to do?**  
DocuBot helps developers answer project documentation questions using local docs in the docs folder. It supports retrieval only and retrieval augmented generation (RAG), with an explicit refusal policy when evidence is weak.

**What inputs does DocuBot take?**  
- User question text  
- Markdown and text files in docs  
- Optional GEMINI_API_KEY for LLM modes

**What outputs does DocuBot produce?**
- Mode 1: free form LLM answer  
- Mode 2: retrieved snippets (or refusal)  
- Mode 3: grounded LLM answer from retrieved snippets (or refusal)

---

## 2. Retrieval Design

**How does your retrieval system work?**  
- Documents are split into paragraph like sections using blank lines.  
- Retrieval units are section sized chunks labeled like FILE.md (section N).  
- A small inverted index maps normalized tokens to section labels.  
- Query and section scoring use exact token matches with lightweight normalization (for example users and user map together).  
- Query tokens are filtered by a stopword list before evidence checks.  
- Top sections are chosen by score descending.

**What tradeoffs did you make?**  
I prioritized simple and readable Python over advanced ranking. This makes behavior easy to reason about, but it still misses semantic matches and can be sensitive to phrasing.

---

## 3. Use of the LLM (Gemini)

**When does DocuBot call the LLM and when does it not?**
- Naive LLM mode: always calls the LLM directly, without retrieval evidence.  
- Retrieval only mode: never calls the LLM.  
- RAG mode: calls retrieval first, then calls the LLM only if evidence is meaningful.

**What instructions do you give the LLM to keep it grounded?**  
The prompt says to answer only from provided snippets, refuse with exactly "I do not know based on the docs I have." when evidence is insufficient, and mention source files when answering.

---

## 4. Experiments and Comparisons

All comparisons below used identical wording for each query across modes.

| Query | Naive LLM: helpful or harmful? | Retrieval only: helpful or harmful? | RAG: helpful or harmful? | Notes |
|------|---------------------------------|--------------------------------------|---------------------------|-------|
| Which endpoint lists all users? | Harmful: confident generic REST answer, not doc specific | Helpful but hard to interpret: returns relevant fragments | Helpful: concise grounded answer with file evidence | Good example where RAG balances clarity and evidence better than mode 2 |
| Maybe its time for me to take a break now | Harmful: confident advice unrelated to docs | Helpful: now correctly refuses | Helpful: correctly refuses | This was a key guardrail regression that was fixed |
| How does a client refresh an access token? | Harmful: long OAuth tutorial not supported by docs | Mixed: gives token related snippets, but not a direct refresh flow | Mixed or failed: one run refused, another run failed due API quota error | RAG still has failure modes from limited evidence and external quota limits |
| What environment variables are required for authentication? | Harmful: generic cloud auth variables not doc specific | Mixed: relevant section headers, not very actionable | Mixed: refused in observed run due conservative evidence gate | Demonstrates precision vs recall tension in refusal thresholds |

**What patterns did you notice?**
- Naive mode often sounds high quality while inventing details not present in project docs.
- Retrieval only mode is often evidence correct, but users must manually synthesize snippets.
- RAG is best when retrieval contains a clear answer chunk, but can be too conservative if evidence is fragmented.

---

## 5. Failure Cases and Guardrails

**Describe at least two concrete failure cases you observed.**

Failure case 1:  
Question: Maybe its time for me to take a break now  
Observed: retrieval only initially returned unrelated auth and API snippets.  
Expected: refusal.

Failure case 2:  
Question: Which endpoint lists all users?  
Observed: RAG initially refused because guardrail checked only the top snippet instead of any retrieved snippet.  
Expected: answer from relevant API snippet.

Failure case 3:  
Question: How does a client refresh an access token?  
Observed: RAG run hit Gemini quota limit (429 RESOURCE_EXHAUSTED).  
Expected: graceful handling or retry message, not a traceback.

**When should DocuBot say “I do not know based on the docs I have”?**
- When no section has enough query token overlap.  
- When query terms are too generic or off topic relative to docs.  
- When retrieval only finds weak heading level matches without answer content.

**What guardrails did you implement?**
- Section level retrieval instead of whole document retrieval.  
- Exact token scoring instead of substring counting.  
- Stopword filtering for evidence decisions.  
- Lightweight token normalization for singular and plural matching.  
- Explicit meaningful evidence check before retrieval only or RAG answers.  
- Refusal default: "I do not know based on these docs." when evidence is weak.

---

## 6. Limitations and Future Improvements

**Current limitations**
1. Token overlap retrieval is still lexical and misses semantic similarity.
2. Ranking quality is limited; some heading snippets outrank better answer snippets.
3. RAG mode currently does not gracefully handle external LLM quota errors.

**Future improvements**
1. Add BM25 or embedding based retrieval for better relevance ranking.
2. Add section level metadata and confidence scores in outputs.
3. Add robust LLM error handling and fallback responses for 429 and network failures.

---

## 7. Responsible Use

**Where could this system cause real world harm if used carelessly?**  
Users may trust fluent but unsupported answers in naive mode, especially for security, authentication, or operational decisions.

**What instructions would you give real developers who want to use DocuBot safely?**
- Prefer retrieval only or RAG over naive mode for factual questions.  
- Treat unsupported confident answers as suspect until verified in docs.  
- Keep refusal behavior enabled; do not force answers when evidence is weak.  
- Validate critical security and production decisions against source documentation.

---

## TF Summary
The core concept students need to understand is how the three modes work and understanding the overall system like reading the documents in the docs directory. A lot of the difficulty comes from ambiguity, especially when a query uses common words that can create weak matches, so students have to learn the difference between surface overlap and real evidence in the docs. That is where mode 2 can be tricky, because retrieval may look convincing even when the snippets are only loosely related or matched by common terms rather than actual answer content. AI was helpful when it has a clear plan and specific examples to work from, but vague prompts usually led to generic or overconfident responses that did not help much. If I were guiding a student, I would walk them through a few examples from each mode and ask them to track exactly what each mode returned and why. From there, they could identify where the issue is and see how the retrieval logic succeeds or fails.