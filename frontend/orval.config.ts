import { defineConfig } from 'orval'

// Typed API client and TanStack Query hooks, generated from the DRF OpenAPI schema.
// `make schema` writes openapi.yaml; `npm run api` regenerates src/shared/api/generated.
export default defineConfig({
  hr: {
    input: './openapi.yaml',
    output: {
      mode: 'tags-split',
      target: 'src/shared/api/generated',
      schemas: 'src/shared/api/generated/model',
      client: 'react-query',
      httpClient: 'fetch',
      clean: true,
      override: {
        mutator: { path: 'src/shared/api/http.ts', name: 'apiFetch' },
        fetch: { includeHttpResponseReturnType: false },
        query: { useQuery: true, useMutation: true, signal: false },
      },
    },
  },
})
