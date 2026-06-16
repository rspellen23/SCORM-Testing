# Responsible Use of AI — Example Microlearning Script

> Shareable gold example for the Course Builder drafter. Authored from the
> TeleTracking "Responsible Use of AI" set (Module 3) and converted to the
> current engine `.md` grammar. It is the canonical OUTPUT shape: Slide 1 =
> Learning Objectives + `*Visual:*`, `*Section:*` bands, inline `*Visual:*`
> slots, a knowledge check, and `> GAP:` notes flagging things for the SME.

---

## Microlearning 1: LLMs Are Not Actually Factual (Hallucination)

**Slide 1 — Learning Objectives**

*Section:* green

*Visual:* graphic · Learning objectives for this microlearning · slot: objectives.png · side: right

By the end of this microlearning, you will be able to:

- Define AI hallucination and explain why it occurs
- Identify common types of hallucinated content
- Explain why hallucination is inherent to how LLMs work, not a fixable bug

*Section:* end

**Slide 2 — What is Hallucination?**

Hallucination is when an AI model confidently produces incorrect, fabricated, or nonsensical information. The output reads as though it is factual — well-structured, detailed, authoritative — but some or all of it is made up.

This is not the AI "lying." It has no concept of truth or falsehood. It is generating the most statistically probable sequence of text based on its training data. Sometimes that sequence happens to be accurate. Sometimes it does not.

**Slide 3 — Real Examples of Hallucination**

*Visual:* graphic · Card set — each card reveals what the AI produced vs. what was actually true · slot: hallucination-examples.png

| What the AI Produced | What Was Actually True |
|---------------------|----------------------|
| Cited three legal cases by name, including case numbers and rulings | None of the cases existed — a lawyer submitted them to a court and was sanctioned |
| Provided a URL to a peer-reviewed research paper with a plausible title and author | The paper, the URL, and the journal did not exist |
| Reported a specific statistic — "42% of healthcare workers reported…" — with an attributed source | The statistic was fabricated; the source had never published that figure |
| Generated a confident biography of a living person with invented career details | The person confirmed the biography was largely fictional |

These are not edge cases. Hallucination happens routinely, across all major LLMs, and it can be difficult to detect because the output looks credible.

> GAP: Only the legal-cases example (Mata v. Avianca, 2023) is a verified incident. Confirm or replace the other three with documented cases, or label them as representative.

**Slide 4 — Why This Happens**

*Visual:* graphic · Callback to next-token prediction: plausible text, not verified facts · slot: token-prediction.png · side: left

Recall that LLMs generate text by predicting the most probable next token. They are not retrieving verified facts — they are producing text that *resembles* factual content because factual-sounding text appeared frequently in their training data.

When an LLM "cites" a source, it is not looking up a citation — it is generating text that looks like a citation. When it provides a statistic, it is not retrieving data — it is producing a number that fits the pattern of how statistics typically appear in text.

This is why hallucination is **not a bug that will be fixed.** It is a fundamental consequence of how probability-based text generation works. Models will improve, but the underlying mechanism — predicting likely text, not verifying truth — remains the same.

> GAP: Some researchers argue retrieval-augmented generation (RAG) materially reduces hallucination. Consider acknowledging that nuance so the "won't be fixed" claim stays defensible.

**Slide 5 — Why It Matters at TeleTracking**

*Visual:* graphic · Four healthcare-context risk callouts · slot: healthcare-risk.png

In a healthcare technology environment, hallucinated content carries real risk:

- A fabricated statistic in a report could inform a business decision based on false data
- An invented product specification could be shared with a customer or partner
- A hallucinated policy reference could lead to a compliance violation
- A made-up citation in training material could undermine credibility with learners

The more authoritative the output sounds, the more dangerous the hallucination — because it is harder to catch.

**Slide 6 — The Risk You Do Not See**

Hallucination is the risk you can catch — if you verify. But there is a subtler risk: when AI consistently produces polished, confident output, it becomes easy to stop checking altogether.

Research shows that frequent AI users tend to **overestimate their own capability** — because they mistake the quality of AI's output for their own understanding. If you cannot explain *why* an output is correct without AI's help, the understanding may not be yours.

This is not about doubting yourself. It is about staying honest about what you know versus what AI generated for you. The habit of verification is about maintaining your own judgment.

**Slide 7 — The Takeaway**

AI-generated content is a **draft**, not a deliverable. Every output must be verified before it is used, shared, or relied upon. This is not a temporary limitation you can wait out — it is a permanent feature of how these systems work.

**Slide 8 — Knowledge Check**

*Question:* Why is hallucination considered an inherent feature of LLMs rather than a bug that will eventually be fixed?

- A) Because AI companies have not invested enough resources in fixing the problem
- B) Because LLMs generate text based on statistical probability, not factual verification — and that core mechanism does not change
- C) Because hallucination only happens with older models that are no longer supported
- D) Because LLMs are designed to be creative rather than accurate

*Correct Answer:* B

*Feedback — Correct:* That's right. LLMs predict the most statistically probable next token; they do not verify truth. That core mechanism is what makes hallucination an inherent characteristic, not a temporary bug.

*Feedback — Incorrect:* Not quite. Hallucination occurs because LLMs generate text by statistical probability, not factual verification. Since that is the fundamental mechanism, hallucination persists even as models improve.
