export function boundedFetch(fetchImpl = fetch, timeoutMs = 8000) {
  return (url, options = {}) => fetchImpl(url, {
    ...options,
    signal: options.signal ? AbortSignal.any([options.signal, AbortSignal.timeout(timeoutMs)]) : AbortSignal.timeout(timeoutMs)
  });
}
