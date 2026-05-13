// GET /api/notes-parquet
// Streams the notes Parquet from the private R2 bucket. DuckDB-WASM in the
// browser issues HTTP Range requests to fetch only the footer + relevant row
// groups, so this handler honors Range headers and replies with 206 Partial
// Content when a range is supplied.

const OBJECT_KEY = "notes.parquet";

function parseRange(header, size) {
  // `bytes=START-END`, `bytes=START-`, or `bytes=-SUFFIX`
  const m = /^bytes=(\d*)-(\d*)$/.exec(header);
  if (!m) return null;
  let start, end;
  if (m[1] === "" && m[2] !== "") {
    const suffix = Number(m[2]);
    start = Math.max(0, size - suffix);
    end = size - 1;
  } else if (m[1] !== "") {
    start = Number(m[1]);
    end = m[2] === "" ? size - 1 : Math.min(Number(m[2]), size - 1);
  } else {
    return null;
  }
  if (start > end || start >= size) return { invalid: true };
  return { start, end, length: end - start + 1 };
}

export async function onRequest({ request, env }) {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response("Method Not Allowed", { status: 405 });
  }

  const head = await env.NOTES.head(OBJECT_KEY);
  if (!head) return new Response("Not Found", { status: 404 });

  const headers = new Headers();
  head.writeHttpMetadata(headers);
  headers.set("etag", head.httpEtag);
  headers.set("Accept-Ranges", "bytes");
  headers.set("Cache-Control", "private, max-age=300");
  headers.set("Content-Type", "application/vnd.apache.parquet");

  const rangeHeader = request.headers.get("Range");
  if (rangeHeader) {
    const range = parseRange(rangeHeader, head.size);
    if (!range || range.invalid) {
      headers.set("Content-Range", `bytes */${head.size}`);
      return new Response("Range Not Satisfiable", { status: 416, headers });
    }
    const partial = await env.NOTES.get(OBJECT_KEY, {
      range: { offset: range.start, length: range.length },
    });
    if (!partial) return new Response("Not Found", { status: 404 });
    headers.set("Content-Length", String(range.length));
    headers.set("Content-Range", `bytes ${range.start}-${range.end}/${head.size}`);
    return new Response(request.method === "HEAD" ? null : partial.body, {
      status: 206,
      headers,
    });
  }

  headers.set("Content-Length", String(head.size));
  if (request.method === "HEAD") return new Response(null, { headers });

  const full = await env.NOTES.get(OBJECT_KEY);
  if (!full) return new Response("Not Found", { status: 404 });
  return new Response(full.body, { headers });
}
