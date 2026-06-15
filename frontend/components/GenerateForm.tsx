'use client'
import { useState } from 'react'

interface Props {
  onCreated: (videoId: string) => void
}

export default function GenerateForm({ onCreated }: Props) {
  const [topic, setTopic] = useState('')
  const [format, setFormat] = useState<'short' | 'long'>('short')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const res = await fetch('/api/videos/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic, format }),
      })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      const { id } = await res.json()
      onCreated(id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <label htmlFor="topic" style={{ display: 'block', marginBottom: 4 }}>
          Video Topic
        </label>
        <input
          id="topic"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="e.g. How to learn TypeScript in 2026"
          required
          style={{ width: '100%', padding: '8px 12px', fontSize: 16, boxSizing: 'border-box' }}
        />
      </div>

      <div>
        <label htmlFor="format" style={{ display: 'block', marginBottom: 4 }}>
          Format
        </label>
        <select
          id="format"
          value={format}
          onChange={(e) => setFormat(e.target.value as 'short' | 'long')}
          style={{ padding: '8px 12px', fontSize: 16 }}
        >
          <option value="short">Short — TikTok / Reels / Shorts (up to 60s)</option>
          <option value="long">Long — YouTube (3–15 min)</option>
        </select>
      </div>

      {error && <p style={{ color: '#c00', margin: 0 }}>{error}</p>}

      <button
        type="submit"
        disabled={loading || !topic.trim()}
        style={{ padding: '10px 24px', fontSize: 16, cursor: loading ? 'wait' : 'pointer' }}
      >
        {loading ? 'Starting generation...' : 'Generate Video'}
      </button>
    </form>
  )
}
