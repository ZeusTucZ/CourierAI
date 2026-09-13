# ElevenLabs route log narration

The demo can read short, recorded route-event summaries aloud in English. It narrates new rain, road-closure, and order-delay events during normal playback. It does not narrate historical events when reopening a session or any events revealed by **Simulate shift**. This feature does not affect routing, decisions, or Gemini.

Put `ELEVENLABS_API_KEY=...` in `.env.elevenlabs.local` (a commented placeholder is already there). The local file is gitignored. Load it into the backend process together with `.env.gemini.local`, then restart the backend. The browser never receives the API key. `ELEVENLABS_VOICE_ID` and `ELEVENLABS_MODEL_ID` are optional; the defaults are George and `eleven_multilingual_v2`.

The backend accepts only IDs of route events already visible in the current demo session. It constructs the spoken summary from those recorded events and sends it to ElevenLabs using its streaming text-to-speech endpoint. The voice feature stays silent if no key is configured or if browser audio playback is blocked.
