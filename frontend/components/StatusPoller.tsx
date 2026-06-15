'use client'
import { useEffect, useState } from 'react'

interface VideoStatus {
  id: string
  topic: string
  format: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  video_path: string | null
  error: string | null
}

interface Props {
  videoId: string
  onReset: () => void
}

export default function StatusPoller({ videoId, onReset }: Props) {
  const [data, setData] = useState<VideoStatus | null>(null)

  useEffect(() => {
    let cancelled = false
    async function poll() {
      try {
        const res = await fetch(`/api/videos/${videoId}/status`)
        const json: VideoStatus = await res.json()
        if (!cancelled) setData(json)
        if (!cancelled && json.status !== 'completed' && json.status !== 'failed') {
          setTimeout(poll, 3000)
        }
      } catch {
        if (!cancelled) setTimeout(poll, 5000)
      }
    }
    poll()
    return () => { cancelled = true }
  }, [videoId])

  if (!data) return <p>Connecting...</p>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <p><strong>Topic:</strong> {data.topic}</p>
      <p><strong>Format:</strong> {data.format}</p>
      <p><strong>Status:</strong> {data.status}</p>

      {(data.status === 'pending' || data.status === 'processing') && (
        <p style={{ color: '#555' }}>Generating your video — this takes 1–5 minutes...</p>
      )}

      {data.status === 'completed' && (
        <div>
          <p style={{ color: 'green' }}>Your video is ready!</p>
          <a href={`/api/videos/${videoId}/download`} download>
            <button style={{ padding: '10px 24px', fontSize: 16 }}>Download MP4</button>
          </a>
        </div>
      )}

      {data.status === 'failed' && (
        <p style={{ color: '#c00' }}>Generation failed: {data.error}</p>
      )}

      <button
        onClick={onReset}
        style={{ padding: '8px 16px', marginTop: 8, cursor: 'pointer' }}
      >
        Generate Another Video
      </button>
    </div>
  )
}
