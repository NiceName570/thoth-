import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import { getEdgeVoices } from '@/hermes'

export const EDGE_VOICE_KEY = 'tts.edge.voice'

export interface EdgeVoiceOptions {
  labels: Record<string, string> | undefined
  options: string[] | undefined
}

/** The full Edge voice catalog for the `tts.edge.voice` picker. Both fields stay undefined until the
 *  list loads (or when the backend can't reach it), so the curated suggestions show meanwhile. */
export function useEdgeVoices(enabled = true): EdgeVoiceOptions {
  const { data } = useQuery({
    enabled,
    queryFn: getEdgeVoices,
    queryKey: ['edge-voices'],
    staleTime: Infinity
  })

  return useMemo(() => {
    if (!data?.available || data.voices.length === 0) {
      return { labels: undefined, options: undefined }
    }

    return {
      labels: Object.fromEntries(data.voices.map(voice => [voice.voice_id, voice.label])),
      options: data.voices.map(voice => voice.voice_id)
    }
  }, [data])
}
