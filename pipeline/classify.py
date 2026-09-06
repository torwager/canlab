"""Tag a paper record with the LLM (tags on three axes, one-sentence summary, free keywords).

Provider: Anthropic when ANTHROPIC_API_KEY is set, otherwise OpenAI (OPENAI_API_KEY). Override with CANLAB_LLM_PROVIDER / CANLAB_LLM_MODEL.
"""
import os
import time
from .llm_client import Classifier, PROMPT_VERSION, load_taxonomy

_clf = None


def get_classifier():
    global _clf
    if _clf is None:
        provider = os.environ.get("CANLAB_LLM_PROVIDER") or ("anthropic" if (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")) else "openai")
        model = os.environ.get("CANLAB_LLM_MODEL") or {"anthropic": "claude-sonnet-5", "openai": "gpt-5-mini"}[provider]
        _clf = Classifier(provider=provider, model=model, effort=os.environ.get("CANLAB_LLM_EFFORT", "medium"))
    return _clf


def apply(rec, data, model, input_mode, confidence=None):
    """Write a tagging result (the JSON object from the model or from a manual batch) into a paper record."""
    tags = data.get("tags") or {}
    rec["tags"] = {"topic": list(dict.fromkeys(tags.get("topic") or [])), "approach": list(dict.fromkeys(tags.get("approach") or [])), "type": [tags["type"]] if tags.get("type") else []}
    rec["summary"] = (data.get("summary") or "").strip()
    rec["key_finding"] = (data.get("key_finding") or "").strip() or None
    rec["free_keywords"] = [k.strip() for k in (data.get("free_keywords") or []) if k and k.strip()][:10]
    rec["classification"] = {"taxonomy_version": load_taxonomy()["taxonomy_version"], "prompt_version": PROMPT_VERSION, "model": model, "input_mode": input_mode,
                             "confidence": data.get("confidence"), "notes": data.get("notes") or None, "classified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    return rec


def classify_record(rec, full_text=None):
    clf = get_classifier()
    res = clf.classify(rec, full_text=full_text)
    apply(rec, res.data, f"{res.provider}:{res.model}", res.input_mode)
    rec["classification"]["usage"] = {**res.usage, "cost_usd": round(res.cost_usd, 5)}
    return rec
