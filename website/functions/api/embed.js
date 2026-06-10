// POST /api/embed  { "text": "..." }
// Returns { "embedding": float[768] } from EmbeddingGemma-300M.
//
// QUERY embeddings only: EmbeddingGemma is asymmetric, and this endpoint
// applies the query prefix from the model card. The matching document prefix
// ('title: ... | text: ...') lives in tools/notes-pipeline/notes_to_parquet.py;
// the two must stay in lockstep, and changing either means re-embedding the
// corpus (notes-ingest.yml).

const MODEL = "@cf/google/embeddinggemma-300m";
const QUERY_PREFIX = "task: search result | query: ";

export async function onRequestPost({ request, env }) {
  let body;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "invalid JSON" }, { status: 400 });
  }

  const text = typeof body?.text === "string" ? body.text.trim() : "";
  if (!text) {
    return Response.json({ error: "text required" }, { status: 400 });
  }
  if (text.length > 6000) {
    return Response.json({ error: "text too long (max 6000 chars)" }, { status: 400 });
  }

  const result = await env.AI.run(MODEL, { text: QUERY_PREFIX + text });
  const embedding = result?.data?.[0];
  if (!Array.isArray(embedding) || embedding.length !== 768) {
    return Response.json({ error: "unexpected embedding shape" }, { status: 502 });
  }
  return Response.json({ embedding });
}
