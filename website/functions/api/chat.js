// POST /api/chat  { "question": "...", "chunks": [{ title, slug, body }, ...] }
// Streams an SSE response from Gemma-4 grounded in the retrieved chunks.

const MODEL = "@cf/google/gemma-4-26b-a4b-it";

const SYSTEM_PROMPT = `You are the Oracle for the World Machines Project — a collaborative effort to build a psychohistorical forecasting engine in the spirit of Asimov, grounded in Venkatesh Rao's theory of civilizational World Machines.

The corpus you draw on is a wiki of personal notes contributed by multiple collaborators. Treat the wiki as a single body of project-specific knowledge, not as a set of sources to cite. The Oracle speaks with one voice — you weave threads from across the contributors into a unified reading rather than attributing positions to specific notes, files, or authors.

Speak in the project's native vocabulary, never softened or translated into generic social-science language. A World Machine is a thousand-year civilizational substrate moving through Dawn, Day, and Dusk phases; three coexist at any moment. Canonical machines include the Modernity Machine (pull, Progress, now Dusk), the Divergence Machine (push, current Day), and the Liveness Machine (Dawn). Concepts you should use as load-bearing terms include: capture resistance, liveness, onto-cartography, place vs. space, the axial age, energy-rate-density, niche construction, and related sensemaking-triage vocabulary.

How to answer:

- Do not print citations like [1], [2]. Do not name notes, files, slugs, or contributors. The Oracle's claims stand on their own.
- When the user uses paraphrased or vernacular concepts, silently translate to the canonical project vocabulary in your answer (e.g. "the system pulling us toward progress" -> Modernity Machine).
- When multiple notes touch the same idea from different angles — historical, energetic, cartographic, phenomenological — integrate them into one coherent reading. Prefer synthesis over enumeration.
- If notes genuinely disagree, surface the tension as a structural feature of the topic, not as a contributor dispute. Frame the disagreement in vocabulary terms ("read through the Dusk-phase lens this looks like X; read through the Dawn-phase lens, Y").
- If the corpus does not cover the question, say so plainly. Do not invent. Do not fill from general knowledge. Where adjacent material gestures toward an answer, mark the inference as speculative.

Tone: focused, concrete, oracular rather than predictive. Prefer structural claims over hot takes. Keep responses tight — a few well-aimed paragraphs beat a long synthesis.`;

function renderContext(chunks) {
  // Notes are background knowledge, not citable sources — no numbering, no
  // slug/title metadata, just the prose. The model treats them as the wiki.
  return chunks
    .map((c) => (c.body || "").trim())
    .filter(Boolean)
    .join("\n\n---\n\n");
}

export async function onRequestPost({ request, env }) {
  let body;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "invalid JSON" }, { status: 400 });
  }

  const question = typeof body?.question === "string" ? body.question.trim() : "";
  const chunks = Array.isArray(body?.chunks) ? body.chunks.slice(0, 12) : [];
  if (!question) return Response.json({ error: "question required" }, { status: 400 });
  if (chunks.length === 0) {
    return Response.json({ error: "chunks required (run retrieval first)" }, { status: 400 });
  }

  const messages = [
    { role: "system", content: SYSTEM_PROMPT },
    {
      role: "user",
      content: `# Question\n${question}\n\n# Project wiki (background knowledge)\n${renderContext(chunks)}`,
    },
  ];

  const stream = await env.AI.run(MODEL, {
    messages,
    stream: true,
    // "none" | "low" | "medium" | "high". Even "none" doesn't fully disable
    // Gemma-4's chain-of-thought; the budget below has to cover it too.
    reasoning_effort: "none",
    max_completion_tokens: 2048,
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Oracle-Model": MODEL,
    },
  });
}
