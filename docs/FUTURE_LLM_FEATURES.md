# Future LLM Features & Techniques

Notes on techniques we may adopt as the platform grows. Not committed work — reference material for when a relevant need comes up.

## 1. Fine-tuning for behavior (not facts)

Fine-tuning = taking a pretrained model and continuing its training on our own examples, which adjusts the model's internal weights permanently. Expensive and slower to iterate than prompting, so it's reached for only when prompting genuinely can't get the job done.

Use it when we need the model to consistently do something structural across every response — not "know a fact" but "behave a certain way":

- Always output a specific JSON schema, no matter how the input is phrased
- Match a specific tone/brand voice reliably (a support bot that always sounds like our company, not generic-AI-polite)
- Perform a niche task pattern the base model wasn't trained on well (e.g., converting legal clauses to plain English in a specific style)

**Why not just prompt it?** We can often get 90% of this with a good system prompt + few-shot examples. Fine-tuning is for last-mile consistency when prompting alone still drifts — e.g., support answers where the format needs to be identical every time, at high volume, cheaply (a fine-tuned small model can outperform prompting a bigger general model, and costs less per call since fewer instruction tokens are repeated every prompt).

**Real-world example:** GitHub Copilot's earlier code-completion models were fine-tuned on code specifically — not just prompted GPT — because the behavior needed (completing code mid-line, matching a codebase's style) needed to be baked in at the weight level, not re-explained every request.

## 2. Direct context for small data

The simplest option, and often correct, which is why it's worth naming as a real alternative rather than defaulting to RAG. If reference material is small enough to fit in the context window (a few pages, a small FAQ, a handful of config files), just paste it directly into the prompt every time. No vector DB, no embeddings, no retrieval step that might miss the right chunk.

When this wins over RAG:

- Total reference data is small and stable (doesn't change every request)
- We want zero risk of retrieval missing something — direct context guarantees the model sees everything, whereas RAG only shows top-k "most similar" chunks and can miss a relevant piece phrased differently
- Simpler to build and debug — no indexing pipeline, no re-embedding when docs update

**Example:** if the platform has a small "system config" doc (say, 2 pages) that every agent workflow needs, just always include it in the system prompt rather than running it through embeddings/retrieval — running it through RAG would be over-engineering for a stable, static doc.

## 3. Structured queries for exhaustive/aggregate answers

RAG's semantic search finds the most similar chunks — not all chunks that match some exact criteria, and definitely not aggregates. If someone asks "how many invoices did we send in Q3" or "list every customer who churned last month," similarity search is the wrong tool entirely — there's no "semantic similarity" to a count or a sum.

For these, the right move is to have the LLM act as a translator to a real query, not a retriever of text:

- The LLM converts the natural-language question into a SQL query (or calls a tool/function that runs one)
- The actual database does the counting/summing/filtering — exact, not approximate
- The LLM then explains or formats the result back to the user in natural language

This is often called "text-to-SQL," or more broadly tool calling / function calling — the LLM decides which structured tool to invoke (query the DB, call an API) rather than reasoning over raw text.

## 4. Cost/latency optimization techniques

- **Prompt caching** — many providers (Anthropic, OpenAI) let us cache a static prefix (system prompt, few-shot examples) so repeated calls don't re-charge full price for that unchanged portion. Big win if a prompt has a large fixed chunk (e.g. the workflow engine's system instructions) and only a small variable part changes per call.
- **Two-stage filtering** — mirrors the LinkedIn automation pattern: run a cheap/small model first to filter, only send the expensive model the stuff that survived. Already have a production example of this in the platform.
- **Retrieve fewer/smaller chunks** — in RAG, tune `top_k` down and chunk size down if quality allows; every chunk stuffed into context is tokens paid for whether the model uses it or not.
- **Summarize instead of truncate** for long conversation history — truncating just drops old context (can lose important info); summarizing compresses it into fewer tokens while keeping the gist. Tradeoff: summarizing costs its own LLM call, so it's not free, just cheaper than keeping full history forever.

## 5. Vector similarity metric & indexing (current decisions, revisit at scale)

Current state: `ChunkEmbedding.embedding.cosine_distance(embedding)` in `app/repositories/retrieval.py`, no ANN index — an exact scan over `chunk_embeddings` (146 rows as of writing). `EMBEDDING_DIM=768` is fixed intentionally; the platform is not meant to support mixed dimensions. Provider chain: `openrouter,gemini,ollama` (`app/core/config.py`).

**Cosine distance vs. dot product.** Dot product is cheaper (no normalization step) but only gives the same ranking as cosine if every stored vector is already unit-length. We can't assume that across a multi-provider chain (OpenRouter, Gemini, Ollama's `nomic-embed-text`) without verifying normalization per provider _and_ per model version — and if a vector isn't normalized, dot product silently ranks by vector magnitude instead of semantic similarity, which is a hard bug to notice (no error, just quietly wrong retrieval). Revisit only if we consolidate to a single provider/model we've explicitly confirmed emits normalized vectors, we normalize ourselves at write time in `app/services/embedding.py`, and retrieval latency is actually profiled as a bottleneck — not before.

**Exact scan vs. ANN index (`ivfflat`/`hnsw`).** At current scale (hundreds of rows) an exact `cosine_distance` scan is sub-millisecond; adding an approximate index now would trade retrieval accuracy for a speedup that doesn't exist yet. Revisit once `chunk_embeddings` reaches roughly the tens-of-thousands-of-rows range, or retrieval latency shows up in profiling. When that happens, prefer `hnsw` with `vector_cosine_ops` over `ivfflat` — it matches the existing `cosine_distance()` calls, has no training/retraining step as data grows, and handles inserts more gracefully; `ivfflat`'s clustering is built on a snapshot of the data distribution and degrades as a small/changing table grows past it.
