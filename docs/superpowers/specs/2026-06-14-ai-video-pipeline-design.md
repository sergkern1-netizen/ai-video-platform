# AI Video Pipeline — Design Spec

**Date:** 2026-06-14
**Scope:** Script generation → Voice synthesis → Video rendering (MP4)
**Out of scope:** Social media publishing, scheduling dashboard (future sub-projects)

---

## Overview

A TypeScript CLI pipeline that takes a topic and format as input and produces a finished MP4 video with voice-over, subtitles, and background footage.

**Tech stack:**
- Script: GPT-4o-mini (OpenAI)
- Voice: OpenAI TTS
- Background footage: Pexels API (free)
- Video rendering: Remotion (React-based, local render, free)

**Estimated cost per video:**
- Short (60s): ~$0.01
- Long (10 min): ~$0.12

---

## Pipeline

```
[CLI input: topic + format]
        │
        ▼
[ScriptGenerator]  ◄── GPT-4o-mini
  Output: title, body, keywords, durationSec
        │
        ▼
[VoiceSynthesizer] ◄── OpenAI TTS    [AssetFetcher] ◄── Pexels API
  Output: MP3 + word timings          Output: video clips
        │                                    │
        └─────────────┬──────────────────────┘
                      ▼
              [VideoRenderer]  ◄── Remotion
                Output: MP4
```

`VoiceSynthesizer` and `AssetFetcher` run in parallel after script generation.

---

## Formats

| Format | Aspect ratio | Duration | Target |
|--------|-------------|----------|--------|
| short  | 9:16        | up to 60s | TikTok, Reels, YouTube Shorts |
| long   | 16:9        | 3–15 min  | YouTube |

User selects format via CLI flag at runtime.

---

## Data Interfaces

```typescript
interface PipelineInput {
  topic: string;
  format: 'short' | 'long';
}

interface Script {
  title: string;
  body: string;
  keywords: string[];
  durationSec: number;
}

interface VoiceOutput {
  audioPath: string;
  wordTimings: Array<{ word: string; startSec: number; endSec: number }>;
}

interface Assets {
  videoClips: Array<{ path: string; durationSec: number }>;
}

interface RenderOutput {
  videoPath: string;
  format: 'short' | 'long';
}
```

---

## Project Structure

```
ai-video-platform/
├── src/
│   ├── pipeline.ts
│   ├── cli.ts
│   ├── modules/
│   │   ├── script-generator.ts
│   │   ├── voice-synthesizer.ts
│   │   ├── asset-fetcher.ts
│   │   └── video-renderer.ts
│   ├── remotion/
│   │   ├── compositions/
│   │   │   ├── ShortVideo.tsx
│   │   │   └── LongVideo.tsx
│   │   └── Root.tsx
│   └── types.ts
├── output/
├── temp/
├── .env
└── package.json
```

**CLI usage:**
```bash
npx ts-node src/cli.ts --topic "How to learn TypeScript" --format short
npx ts-node src/cli.ts --topic "History of Rome" --format long
```

---

## Error Handling

- **OpenAI rate limit:** surface clear message, suggest retry after 60s
- **Pexels returns no results:** fall back to gradient background — pipeline does not stop
- **Remotion render failure:** preserve already-generated script and audio in `temp/` to avoid re-paying for API calls on retry

---

## Testing

| Type | What is tested |
|------|---------------|
| Unit | `ScriptGenerator` — output shape, correct duration target per format |
| Unit | `AssetFetcher` — gradient fallback when Pexels returns empty |
| Integration | Full pipeline run with mocked OpenAI and Pexels APIs |

Real APIs are never called in tests — all external calls are mocked.
