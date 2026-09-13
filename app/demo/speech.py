"""Optional ElevenLabs narration for recorded route events."""
import os

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response


router = APIRouter(prefix='/demo/speech')
VOICE_ID = 'JBFqnCBsd6RMkjVDRZzb'  # George, ElevenLabs example voice.
EVENT_NAMES = {'rain': 'Rain', 'closure': 'Road closure', 'delay': 'Order delay'}


def enabled() -> bool:
    return bool(os.getenv('ELEVENLABS_API_KEY'))


def event_summary(shock: dict) -> str:
    smart_detours = shock['detours']['smart']
    smart_update = 'Smart route updated.' if smart_detours else 'Smart route unchanged.'
    return f"{EVENT_NAMES[shock['shock_type']]}. {smart_update}"


@router.get('/status')
async def speech_status():
    return {'enabled': enabled()}


@router.post('/simulations/{identifier}/route-events/{event_id}')
async def speak_route_event(identifier: str, event_id: str, request: Request):
    if not enabled():
        raise HTTPException(503, 'ElevenLabs speech is not configured')
    try:
        current = request.app.state.demo.get(identifier).state()
    except KeyError as exc:
        raise HTTPException(404, 'Demo session not found') from exc
    if current['status'] == 'completed':
        raise HTTPException(409, 'Speech is disabled for completed shifts')
    shock = next((item for item in current['shocks'] if item['id'] == event_id), None)
    if not shock or shock['shock_type'] not in EVENT_NAMES:
        raise HTTPException(404, 'Route event not found in this playback')

    voice_id = os.getenv('ELEVENLABS_VOICE_ID', VOICE_ID)
    model_id = os.getenv('ELEVENLABS_MODEL_ID', 'eleven_multilingual_v2')
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            result = await client.post(
                f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream',
                params={'output_format': 'mp3_44100_128'},
                headers={'xi-api-key': os.environ['ELEVENLABS_API_KEY']},
                json={'text': event_summary(shock), 'model_id': model_id},
            )
        result.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, 'ElevenLabs speech request failed') from exc
    return Response(result.content, media_type='audio/mpeg', headers={'Cache-Control': 'no-store'})
