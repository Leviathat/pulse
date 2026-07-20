"""Enrichment step: augment a raw article with derived fields (currently language)."""

from langdetect import DetectorFactory, LangDetectException, detect

from processor.models import Article, EnrichedArticle

# Make langdetect deterministic across runs (it is randomized by default).
DetectorFactory.seed = 0


def detect_lang(text: str) -> str:
    """Best-effort ISO 639-1 language code; 'unknown' when detection fails."""
    text = text.strip()
    if not text:
        return "unknown"
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


def enrich(article: Article) -> EnrichedArticle:
    """Produce an EnrichedArticle. Monitor matching is added in stage 2."""
    lang = detect_lang(f"{article.title}\n{article.body}")
    return EnrichedArticle(**article.model_dump(), lang=lang)
