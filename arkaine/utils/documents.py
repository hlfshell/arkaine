import re
from typing import List


def isolate_sentences(text: str) -> List[str]:
    sentences = []
    current_sentence = ""
    for word in text.split():
        current_sentence += word.strip() + " "
        if word.endswith(".") or word.endswith("?") or word.endswith("!"):
            sentences.append(current_sentence.strip())
            current_sentence = ""

    return sentences


def chunk_text_by_sentences(
    text: str,
    sentences_per: int,
    overlap: int = 0,
    isolate_paragraphs: bool = False,
):
    if isolate_paragraphs:
        paragraphs = re.split(r"\n{2,}", text)
        text = [p.strip() for p in paragraphs if p.strip()]
    else:
        text = [text]

    chunks = []

    for paragraph in text:
        sentences = isolate_sentences(paragraph)
        while len(sentences) > 0:
            chunks.append(" ".join(sentences[0:sentences_per]))
            sentences = sentences[sentences_per + 1 - overlap :]

    return chunks
