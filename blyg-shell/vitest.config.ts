import { cloudflareTest } from '@cloudflare/vitest-pool-workers';
import { defineConfig } from 'vitest/config';

// Unit tests run in workerd (HTMLRewriter is a runtime API) and call the
// handler with a stub STUDIO binding; no wrangler config, so no real service.
export default defineConfig({
  plugins: [
    cloudflareTest({
      miniflare: {
        compatibilityDate: '2026-07-01',
        outboundService: () => new Response('no network in tests', { status: 503 }),
      },
    }),
  ],
});
