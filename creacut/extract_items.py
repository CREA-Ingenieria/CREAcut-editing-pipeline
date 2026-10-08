"""Stage 6 — Extract list items via LLM (Ollama → Claude → regex fallback)."""

import hashlib
import json
import re
from pathlib import Path

from .common import (
    CutSentence,
    GuionSentence,
    ListDetection,
    ListItem,
    ListOverlay,
    normalize,
)

_STOPWORDS = {
    "la", "el", "de", "en", "y", "a", "los", "las", "un", "una", "es",
    "para", "por", "con", "se", "su", "que", "del", "al", "o", "no",
    "son", "fue", "han", "hay", "como", "pero", "si", "ya", "más",
}

_PROMPT_TEMPLATE = """\
Eres un asistente analizando un guion educativo en español.
El siguiente extracto contiene una lista enumerada de elementos. Extrae los items.

Texto:
---
{excerpt}
---

Responde SOLO con JSON válido (sin markdown, sin explicación):
{{"intro": "frase introductoria breve de la lista", "items": [{{"label": "etiqueta corta (2-5 palabras)", "description": "texto completo del item"}}]}}
"""


def extract_list_items(
    detections: list[ListDetection],
    sentences: list[GuionSentence],
    guion_path: Path,
    cut_sentences: list[CutSentence],
    config: dict,
    segments: list[dict] | None = None,
    clean_ranges: list[tuple[float, float]] | None = None,
    verbose: bool = False,
    enable_images: bool = False,
) -> list[ListOverlay]:
    if not detections:
        return []

    cache_path = guion_path.with_suffix(".lists.json")
    cache = _load_cache(cache_path)
    cut_map = {(cs.paragraph_idx, cs.sentence_idx): cs for cs in cut_sentences}

    overlays: list[ListOverlay] = []
    cache_dirty = False

    for det in detections:
        excerpt = _build_excerpt(sentences, det)
        cache_key = hashlib.md5(excerpt.encode()).hexdigest()[:12]

        if cache_key in cache:
            raw = cache[cache_key]
            if verbose:
                print(f"    [cache] {cache_key}: {len(raw.get('items', []))} items")
        else:
            raw = _extract_via_llm(excerpt, config, verbose)
            if raw and raw.get("items"):
                cache[cache_key] = raw
                cache_dirty = True

        if not raw or not raw.get("items"):
            if verbose:
                print(f"    [skip] no items extracted for sent {det.trigger_sentence_idx}")
            continue

        overlay = _build_overlay(raw, det, sentences, cut_map, segments, clean_ranges, guion_path, enable_images, verbose)
        if overlay:
            overlays.append(overlay)
            if verbose:
                print(f"    [overlay] \"{overlay.intro}\" — {len(overlay.items)} items, "
                      f"{overlay.cut_start:.1f}s–{overlay.cut_end:.1f}s")

    if cache_dirty:
        _save_cache(cache_path, cache)

    return overlays


def _build_excerpt(
    sentences: list[GuionSentence],
    det: ListDetection,
) -> str:
    parts = []
    for i in range(det.trigger_sentence_idx, det.end_sentence_idx + 1):
        if i < len(sentences):
            parts.append(sentences[i].text)
    return " ".join(parts)


def _extract_via_llm(excerpt: str, config: dict, verbose: bool) -> dict | None:
    provider = config["overlays"]["lists"].get("llm_provider", "auto")

    if provider == "ollama":
        return _try_ollama(excerpt, config, verbose) or _try_regex(excerpt, verbose)
    if provider == "claude":
        return _try_claude(excerpt, config, verbose) or _try_regex(excerpt, verbose)
    if provider == "regex":
        return _try_regex(excerpt, verbose)

    # "auto" (default): try providers in order, fall back to regex
    return (
        _try_ollama(excerpt, config, verbose)
        or _try_claude(excerpt, config, verbose)
        or _try_regex(excerpt, verbose)
    )


def _try_ollama(excerpt: str, config: dict, verbose: bool) -> dict | None:
    try:
        import ollama
    except ImportError:
        if verbose:
            print("    [ollama] package not installed, skipping")
        return None

    model = config["overlays"]["lists"]["ollama_model"]
    prompt = _PROMPT_TEMPLATE.format(excerpt=excerpt)
    try:
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            format="json",
            options={"temperature": 0.1},
        )
        text = response["message"]["content"]
        result = json.loads(text)
        if verbose:
            print(f"    [ollama] extracted {len(result.get('items', []))} items")
        return result
    except Exception as e:
        if verbose:
            print(f"    [ollama] failed: {e}")
        return None


def _try_claude(excerpt: str, config: dict, verbose: bool) -> dict | None:
    try:
        import anthropic
    except ImportError:
        if verbose:
            print("    [claude] anthropic package not installed, skipping")
        return None

    model = config["overlays"]["lists"]["claude_model"]
    prompt = _PROMPT_TEMPLATE.format(excerpt=excerpt)
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            if verbose:
                print(f"    [claude] extracted {len(result.get('items', []))} items")
            return result
    except Exception as e:
        if verbose:
            print(f"    [claude] failed: {e}")
    return None


def _try_regex(excerpt: str, verbose: bool) -> dict | None:
    ordinal_re = re.compile(
        r"(?:(?:La\s+)?(?:primera?|segund[oa]|tercer[oa]?|cuart[oa]|quint[oa])"
        r"|Finalmente|Por último|Por ultimo)\b",
        re.IGNORECASE,
    )
    parts = ordinal_re.split(excerpt)
    markers = ordinal_re.findall(excerpt)

    if len(markers) >= 2:
        items = []
        for i, marker in enumerate(markers):
            text = parts[i + 1].strip() if i + 1 < len(parts) else ""
            text = re.sub(r"[.;,]\s*$", "", text[:200]).strip()
            label = text[:60].split(",")[0].split(";")[0].strip()
            if text:
                items.append({"label": label, "description": text})
        if items:
            intro_text = parts[0].strip()[-80:] if parts[0].strip() else ""
            if verbose:
                print(f"    [regex-ordinal] extracted {len(items)} items")
            return {"intro": intro_text, "items": items}

    phase_re = re.compile(
        r"(?:La sesión (?:se abre|comienza)|Comenzamos con|"
        r"A continuación|Continuamos con|Pasamos a|Pase ahora|"
        r"Entramos entonces|Naturalmente,? llegamos|"
        r"(?:El|La) siguiente|constituye el siguiente|"
        r"se pasa a la fase|Finalmente|Por último)\b",
        re.IGNORECASE,
    )
    phase_markers = phase_re.findall(excerpt)
    if len(phase_markers) >= 3:
        phase_parts = phase_re.split(excerpt)
        items = []
        for k, marker in enumerate(phase_markers):
            text = phase_parts[k + 1].strip() if k + 1 < len(phase_parts) else ""
            text = re.sub(r"[.;]\s*$", "", text[:200]).strip()
            label = text[:60].split(".")[0].split(",")[0].strip()
            if label:
                items.append({"label": f"{marker.strip()} {label}", "description": text})
        if items:
            intro_text = phase_parts[0].strip()[-80:] if phase_parts[0].strip() else ""
            if verbose:
                print(f"    [regex-phase] extracted {len(items)} items")
            return {"intro": intro_text, "items": items}

    colon_match = re.search(r":\s*(.+)", excerpt)
    if colon_match:
        after_colon = colon_match.group(1)
        semicolon_parts = re.split(r";\s*(?:y\s+)?", after_colon)
        if len(semicolon_parts) >= 2:
            items = []
            for part in semicolon_parts:
                part = part.strip().rstrip(".")
                if not part:
                    continue
                comma_split = part.split(",", 1)
                label = comma_split[0].strip()[:60]
                items.append({"label": label, "description": part})
            if len(items) >= 2:
                intro = excerpt[:excerpt.index(":")].strip()
                intro = intro.split(".")[-1].strip() if "." in intro else intro
                if verbose:
                    print(f"    [regex-semicolon] extracted {len(items)} items")
                return {"intro": intro[-80:], "items": items}

    if ":" in excerpt:
        after_last_colon = excerpt.rsplit(":", 1)[1]
        capitalized = re.findall(
            r"\b(?:la|el)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)", after_last_colon,
        )
        if len(capitalized) >= 2:
            items = [{"label": c, "description": c} for c in capitalized]
            intro = excerpt.split(":")[0].strip()
            intro = intro.split(".")[-1].strip() if "." in intro else intro
            if verbose:
                print(f"    [regex-capital] extracted {len(items)} items")
            return {"intro": intro[-80:], "items": items}

    if verbose:
        print("    [regex] not enough markers found")
    return None


def _in_clean_range(t: float, clean_ranges: list[tuple[float, float]]) -> bool:
    for start, end in clean_ranges:
        if start - 0.15 <= t <= end + 0.15:
            return True
    return False


def find_segment_time(
    segments: list[dict],
    phrase: str,
    raw_start: float,
    raw_end: float,
    clean_ranges: list[tuple[float, float]] | None = None,
) -> float | None:
    """Return the raw-video start time of the segment that best matches phrase.

    Searches within [raw_start, raw_end] ± 1s. Uses keyword overlap scoring
    to handle transcript/guion wording differences, with a word-level pass
    when word data is available. When clean_ranges is provided, only considers
    segments within those ranges (skips discarded retakes).
    """
    norm_phrase = normalize(phrase)
    phrase_words = set(norm_phrase.split()) - _STOPWORDS
    if not phrase_words:
        return None

    # Word-level pass (only if cache has word data)
    all_words: list[dict] = []
    for seg in segments:
        if seg["end"] < raw_start - 1.0 or seg["start"] > raw_end + 1.0:
            continue
        if clean_ranges and not _in_clean_range(seg["start"], clean_ranges):
            continue
        for w in seg.get("words", []):
            if raw_start - 1.0 <= w["start"] <= raw_end + 1.0:
                all_words.append(w)

    if all_words:
        norm_word_texts = [normalize(w["word"]) for w in all_words]
        n = len(list(phrase_words))
        best_score = 0.0
        best_time = None
        for i in range(len(norm_word_texts)):
            window = norm_word_texts[i:i + max(n, 1)]
            overlap = len(phrase_words & set(window)) / len(phrase_words)
            if overlap > best_score:
                best_score = overlap
                best_time = all_words[i]["start"]
        if best_score >= 0.5 and best_time is not None:
            return best_time

    # Segment-level pass (keyword overlap)
    best_score = 0.0
    best_time = None
    for seg in segments:
        if seg["end"] < raw_start - 1.0 or seg["start"] > raw_end + 1.0:
            continue
        if clean_ranges and not _in_clean_range(seg["start"], clean_ranges):
            continue
        norm_text = normalize(seg["text"])
        text_words = set(norm_text.split())
        overlap = len(phrase_words & text_words) / len(phrase_words)
        if overlap > best_score:
            best_score = overlap
            best_time = seg["start"]

    return best_time if best_score >= 0.3 else None


def raw_to_cut(t: float, clean_ranges: list[tuple[float, float]]) -> float | None:
    """Map a raw-video timestamp to the cut-video timeline."""
    cumulative = 0.0
    for start, end in clean_ranges:
        if start - 0.15 <= t <= end + 0.15:
            return round(max(0.0, (t - start) + cumulative), 3)
        cumulative += end - start
    return None


def _timestamps_from_sentences(
    det,
    sentences: list[GuionSentence],
    cut_map: dict[tuple[int, int], CutSentence],
    n: int,
    fallback_start: float,
    fallback_end: float,
) -> list[float]:
    """Return item timestamps using ordinal-sentence cut_start values.

    Uses the sentences that introduce each item (identified by ordinal/terminal markers
    in detect_lists.py). Falls back to even distribution when markers are insufficient.
    """
    indices = det.item_sentence_indices
    if indices:
        ts = []
        for flat_idx in indices[:n]:
            if flat_idx < len(sentences):
                gs = sentences[flat_idx]
                cs = cut_map.get((gs.paragraph_idx, gs.sentence_idx))
                if cs:
                    ts.append(round(cs.cut_start, 3))
        if len(ts) == n:
            return ts
        if ts:
            last = ts[-1]
            remaining = n - len(ts)
            step = (fallback_end - last) / (remaining + 1)
            for k in range(remaining):
                ts.append(round(last + step * (k + 1), 3))
            return ts

    # Even distribution fallback (original behavior)
    duration = fallback_end - fallback_start
    if duration > 0:
        interval = duration / (n + 1)
        return [round(fallback_start + interval * (k + 1), 3) for k in range(n)]
    return []


def _build_overlay(
    raw: dict,
    det: ListDetection,
    sentences: list[GuionSentence],
    cut_map: dict[tuple[int, int], CutSentence],
    segments: list[dict] | None = None,
    clean_ranges: list[tuple[float, float]] | None = None,
    guion_path: Path | None = None,
    enable_images: bool = False,
    verbose: bool = False,
) -> ListOverlay | None:
    trigger_sent = sentences[det.trigger_sentence_idx]
    end_sent = sentences[det.end_sentence_idx]

    trigger_key = (trigger_sent.paragraph_idx, trigger_sent.sentence_idx)
    end_key = (end_sent.paragraph_idx, end_sent.sentence_idx)

    cs_trigger = cut_map.get(trigger_key)
    cs_end = cut_map.get(end_key)

    if not cs_trigger or not cs_end:
        return None

    items: list[ListItem] = []
    for i, raw_item in enumerate(raw["items"]):
        image_path = ""
        if enable_images:
            image_rel = raw_item.get("image", "")
            if image_rel and guion_path:
                resolved = (guion_path.parent / image_rel).resolve()
                if resolved.exists():
                    image_path = str(resolved)
                elif verbose:
                    print(f"    [warn] image not found: {resolved}")

        items.append(ListItem(
            label=raw_item["label"],
            description=raw_item.get("description", ""),
            sentence_idx=det.trigger_sentence_idx + i,
            image_path=image_path,
        ))

    n = len(items)
    intro_text = raw.get("intro", "")

    # Use Whisper segment timestamps for precise speaker-sync when available
    cut_start = cs_trigger.cut_start
    item_timestamps: list[float] = []

    if segments and clean_ranges:
        raw_window_start = cs_trigger.raw_start
        raw_window_end = cs_end.raw_end

        # Overlay appears when the speaker says the intro/title phrase
        if intro_text:
            raw_intro_time = find_segment_time(
                segments, intro_text, raw_window_start, raw_window_end,
                clean_ranges=clean_ranges,
            )
            if raw_intro_time is not None:
                cut_intro = raw_to_cut(raw_intro_time, clean_ranges)
                if cut_intro is not None:
                    cut_start = cut_intro

        manual_ts = raw.get("item_timestamps")
        if manual_ts is not None and len(manual_ts) == n:
            item_timestamps = [round(t, 3) for t in manual_ts]
        else:
            # Each item appears when the speaker says its label
            used_raw_times: set[float] = set()
            for item in items:
                search_from = max(
                    raw_window_start,
                    max(used_raw_times, default=raw_window_start),
                )
                raw_item_time = find_segment_time(
                    segments, item.label, search_from, raw_window_end,
                    clean_ranges=clean_ranges,
                )
                if raw_item_time is not None and raw_item_time not in used_raw_times:
                    cut_item = raw_to_cut(raw_item_time, clean_ranges)
                    if cut_item is not None:
                        item_timestamps.append(round(cut_item, 3))
                        used_raw_times.add(raw_item_time)

    # Fill any missing item timestamps with sentence-level or even-distribution fallback
    if len(item_timestamps) < n:
        item_timestamps = _timestamps_from_sentences(
            det, sentences, cut_map, n,
            fallback_start=cut_start,
            fallback_end=cs_end.cut_end,
        )

    cut_end = cs_end.cut_end
    manual_end = raw.get("cut_end")
    if manual_end is not None:
        cut_end = float(manual_end)

    return ListOverlay(
        intro=intro_text,
        items=items,
        cut_start=cut_start,
        cut_end=cut_end,
        item_timestamps=item_timestamps,
    )


def _load_cache(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_cache(path: Path, cache: dict) -> None:
    path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
