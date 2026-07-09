"""Test del pre-filtro di silenzio con audio sintetico."""

import numpy as np

from calliope.media.silence import detect_silence

SR = 16000


def test_all_silent_is_true():
    audio = np.zeros(SR * 3, dtype=np.float32)
    assert detect_silence(audio, SR, threshold=70) is True


def test_all_speech_is_false():
    # ampiezza piena su tutto l'audio → energia per finestra >> soglia
    audio = np.ones(SR * 3, dtype=np.float32)
    assert detect_silence(audio, SR, threshold=70) is False


def test_speech_only_in_tail_is_not_silent():
    audio = np.zeros(SR * 3, dtype=np.float32)
    audio[-SR:] = 1.0  # parlato solo nell'ultimo secondo
    assert detect_silence(audio, SR, threshold=70) is False


def test_speech_only_at_head_is_not_silent():
    audio = np.zeros(SR * 3, dtype=np.float32)
    audio[:SR] = 1.0  # parlato solo nel primo secondo
    assert detect_silence(audio, SR, threshold=70) is False


def test_empty_audio_is_silent():
    assert detect_silence(np.array([], dtype=np.float32), SR) is True


def test_threshold_boundary():
    # una finestra con energia esattamente pari alla soglia NON è silenzio (>=)
    audio = np.zeros(SR, dtype=np.float32)
    audio[:70] = 1.0  # somma delle ampiezze assolute = 70
    assert detect_silence(audio, SR, threshold=70) is False
    assert detect_silence(audio, SR, threshold=71) is True


def test_threshold_from_settings(monkeypatch):
    # threshold=None usa settings.silence_threshold
    import calliope.media.silence as silence_mod

    monkeypatch.setattr(silence_mod.settings, "silence_threshold", 10)
    audio = np.zeros(SR, dtype=np.float32)
    audio[:20] = 1.0  # energia 20 > 10
    assert detect_silence(audio, SR) is False
