import { useQuery } from '@tanstack/react-query'

type Page<T> = { count: number; next?: string | null; results: T[] }

const MAX_PAGES = 40 // 2,000 rows at the API's 50 per page; list pages filter and page in the browser

/**
 * Every page of a paginated list endpoint, as one result shaped like a single page.
 * List screens search, filter, sort and page on the client, so they need all the rows.
 */
export function useAllPages<T>(key: readonly unknown[], fetchPage: (page: number) => Promise<Page<T>>, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['all-pages', ...key],
    enabled: options?.enabled ?? true,
    queryFn: async (): Promise<Page<T>> => {
      const results: T[] = []
      let count = 0
      for (let page = 1; page <= MAX_PAGES; page += 1) {
        const data = await fetchPage(page)
        results.push(...data.results)
        count = data.count
        if (!data.next) break
      }
      return { count, results, next: null }
    },
  })
}
