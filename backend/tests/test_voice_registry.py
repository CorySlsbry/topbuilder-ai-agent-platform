"""Phone-voice registry — pure tests for the 3-voice catalog the booking agent answers with."""
from __future__ import annotations

from app.voice import voices


def test_exactly_three_branded_voices():
    assert set(voices.VOICES) == {"riley", "marcus", "jade"}
    assert voices.DEFAULT_VOICE == "riley"
    assert voices.is_valid(voices.DEFAULT_VOICE)


def test_every_voice_well_formed_and_distinct():
    ids = {v.elevenlabs_voice_id for v in voices.VOICES.values()}
    assert len(ids) == 3  # three distinct underlying voices
    for v in voices.VOICES.values():
        assert v.label and v.description and v.elevenlabs_voice_id


def test_lookup_normalizes_and_fails_closed():
    assert voices.get_voice(" Riley ").key == "riley"
    assert voices.get_voice("MARCUS").key == "marcus"
    assert voices.get_voice("alexa") is None
    assert not voices.is_valid("")


def test_as_list_shape_for_api():
    items = voices.as_list()
    assert len(items) == 3
    for item in items:
        assert set(item) == {"key", "label", "description", "preview_url"}
        assert item["preview_url"] == f"/voices/{item['key']}.mp3"
