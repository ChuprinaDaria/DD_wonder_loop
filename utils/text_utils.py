import re

def clean_surrogates(text: str) -> str:
    """Надійне очищення сурогатів та невалідних символів"""
    return text.encode('utf-8', 'ignore').decode('utf-8', 'ignore')
