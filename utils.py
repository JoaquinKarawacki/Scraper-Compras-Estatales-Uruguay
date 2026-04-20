"""
utils.py
--------
Funciones utilitarias sin dependencias internas.
Separado para evitar importaciones circulares.
"""

import re


ACCENT_MAP = str.maketrans(
    "áéíóúàèìòùäëïöüÁÉÍÓÚÀÈÌÒÙÄËÏÖÜ",
    "aeiouaeiouaeiouAEIOUAEIOUAEIOU"
)


def normalize(text: str) -> str:
    """Quita tildes y pone en minúsculas para comparación."""
    return text.translate(ACCENT_MAP).lower()
