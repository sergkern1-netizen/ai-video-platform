'use client'
import { useState } from 'react'
import GenerateForm from '@/components/GenerateForm'
import StatusPoller from '@/components/StatusPoller'

export default function Home() {
  const [videoId, setVideoId] = useState<string | null>(null)

  return (
    <main style={{ maxWidth: 600, margin: '60px auto', padding: '0 24px', fontFamily: 'sans-serif' }}>
      <h1 style={{ marginBottom: 32 }}>AI Video Generator</h1>
      {videoId === null ? (
        <GenerateForm onCreated={setVideoId} />
      ) : (
        <StatusPoller videoId={videoId} onReset={() => setVideoId(null)} />
      )}
    </main>
  )
}
