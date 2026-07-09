"""Pre-filtro energetico per rilevare l'assenza di parlato in un audio."""

import numpy as np

from calliope.settings import settings


def detect_silence(audio: np.ndarray, sr: float, threshold: int | None = None) -> bool:
    """Determina se l'audio è (essenzialmente) muto, cioè non contiene parlato.

    Scandisce l'**intero** audio in finestre da 1 secondo e ne calcola l'energia
    (somma delle ampiezze assolute). Se nessuna finestra supera la soglia,
    l'audio è considerato muto. È un pre-filtro energetico economico: serve a
    evitare l'inferenza su clip senza parlato.

    Args:
        audio: campioni audio come array NumPy (mono).
        sr: frequenza di campionamento in Hz (dimensione della finestra da 1 s).
        threshold: energia minima per considerare una finestra "con parlato".
            Se ``None`` usa ``settings.silence_threshold``.

    Returns:
        ``True`` se l'audio è muto (nessuna finestra sopra la soglia),
        ``False`` se almeno una finestra contiene parlato.
    """
    if threshold is None:
        threshold = settings.silence_threshold

    window = int(sr)
    if window <= 0 or len(audio) == 0:
        return True

    for start in range(0, len(audio), window):
        window_energy = np.abs(audio[start : start + window]).sum()
        if window_energy >= threshold:
            return False  # trovata una finestra con parlato

    return True  # nessuna finestra sopra la soglia → audio muto
