"""Stage 5 — Detect enumerated lists in guion sentences."""

import re

from .common import GuionSentence, ListDetection, normalize


# ── Patterns ────────────────────────────────────────────────────────────────

_NUMS = {
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
}

_COUNT_NOUNS = (
    r"momentos|dimensiones|etapas|fases|pasos|principios|variables|"
    r"rutas|aspectos|niveles|elementos|componentes|partes|bloques|ejes|"
    r"estrategias|criterios|categorías|categorias|preguntas|ventajas|secciones"
)

COUNT_RE = re.compile(
    rf"\b({'|'.join(_NUMS)})\s+({_COUNT_NOUNS})\b",
    re.IGNORECASE,
)

ORDINAL_RES = [
    (re.compile(r"\b(?:la\s+)?primera?\b", re.I), 1),
    (re.compile(r"\b(?:la\s+)?segund[oa]\b", re.I), 2),
    (re.compile(r"\b(?:la\s+)?tercer[oa]?\b", re.I), 3),
    (re.compile(r"\b(?:la\s+)?cuart[oa]\b", re.I), 4),
    (re.compile(r"\b(?:la\s+)?quint[oa]\b", re.I), 5),
]

STRUCTURAL_RE = re.compile(
    r"\b(?:la primera (?:es|fue|será|consiste)|"
    r"la segunda (?:es|fue|será|consiste)|"
    r"la tercera (?:es|fue|será|consiste))\b",
    re.IGNORECASE,
)

_LIST_NOUNS = (
    r"estrategia|paso|bloque|fase|etapa|momento|ruta|"
    r"dimensión|dimension|principio|elemento|parte|aspecto|nivel|componente"
)

ORDINAL_NOUN_RE = re.compile(
    r"\b(?:como\s+(?:(?:el|la)\s+)?|(?:el|la)\s+)"
    r"(?:primer[oa]?|segund[oa]|tercer[oa]?|cuart[oa]|quint[oa])\s+"
    rf"(?:{_LIST_NOUNS})\b",
    re.IGNORECASE,
)

TERMINAL_RE = re.compile(
    r"\b(?:finalmente|por último|por ultimo)\b", re.IGNORECASE,
)

CONTRAST_OPEN_RE = re.compile(r"\bpor un lado\b", re.IGNORECASE)
CONTRAST_CLOSE_RE = re.compile(r"\bpor (?:el )?otro lado\b", re.IGNORECASE)

SEQUENTIAL_RE = re.compile(
    r"\b(?:continuamos con|pasamos a|entramos entonces)\b", re.IGNORECASE,
)

INLINE_LIST_RE = re.compile(r"[:;]", re.IGNORECASE)

LEVEL_OPEN_RE = re.compile(
    r"^(?:En (?:el|la)\s+(?:nivel|caso|contexto|etapa)?\s*(?:de\s+)?)",
    re.IGNORECASE,
)

PARALLEL_RE = re.compile(
    r"^Con\s+[a-záéíóúñ]+(?:\s+[a-záéíóúñ]+){0,2},\s+(?:puede|se puede|podemos|podría)",
    re.IGNORECASE,
)

PHASE_OPEN_RE = re.compile(
    r"\b(?:la sesión se abre|la sesión comienza|la actividad (?:se inicia|comienza)|"
    r"comenzamos con)\b",
    re.IGNORECASE,
)

PHASE_CONTINUE_RE = re.compile(
    r"\b(?:a continuación|continuamos con|pasamos a|pase ahora|"
    r"entramos entonces|naturalmente,? llegamos|"
    r"(?:el|la) siguiente (?:paso|bloque|elemento|momento|fase|etapa)|"
    r"constituye el siguiente|se pasa a la fase)\b",
    re.IGNORECASE,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _is_ordinal_marker(text: str) -> bool:
    return (any(p.search(text) for p, _ in ORDINAL_RES)
            or bool(ORDINAL_NOUN_RE.search(text)))


# ── Scanner ─────────────────────────────────────────────────────────────────

def detect_lists(
    sentences: list[GuionSentence],
    verbose: bool = False,
) -> list[ListDetection]:
    detections: list[ListDetection] = []
    used: set[int] = set()

    for i, sent in enumerate(sentences):
        if i in used:
            continue

        # --- Count trigger: "tres momentos clave" ---
        cm = COUNT_RE.search(sent.text)
        if cm:
            word = cm.group(1).lower()
            n = _NUMS.get(word, 0)
            if n > 0:
                end = _find_list_end(sentences, i, n, used)
                if end >= i:
                    is_inline = (end == i and len(sent.text) > 150
                                 and INLINE_LIST_RE.search(sent.text))
                    if end > i or is_inline:
                        marker = "count-inline" if is_inline else "count"
                        item_idxs = _find_item_sentence_indices(sentences, i, end)
                        det = ListDetection(i, end, marker, n, item_sentence_indices=item_idxs)
                        detections.append(det)
                        used.update(range(i, end + 1))
                        if verbose:
                            print(f"    [{marker}] sent {i}–{end}: "
                                  f"\"{sent.text[:60]}...\" ({n} items)")
                        continue

        # --- Structural ordinal: "La primera es..." / "Como primera estrategia..." ---
        if STRUCTURAL_RE.search(sent.text) or ORDINAL_NOUN_RE.search(sent.text):
            end = _find_ordinal_end(sentences, i, used)
            if end > i:
                n = _count_ordinals(sentences, i, end)
                item_idxs = _find_item_sentence_indices(sentences, i, end)
                det = ListDetection(i, end, "structural", n, item_sentence_indices=item_idxs)
                detections.append(det)
                used.update(range(i, end + 1))
                if verbose:
                    print(f"    [structural] sent {i}–{end}: "
                          f"\"{sent.text[:60]}...\" ({n} items)")
                continue

        # --- Contrast: "Por un lado... por otro lado" ---
        if CONTRAST_OPEN_RE.search(sent.text):
            for j in range(i + 1, min(i + 8, len(sentences))):
                if j in used:
                    continue
                if CONTRAST_CLOSE_RE.search(sentences[j].text):
                    det = ListDetection(i, j, "contrast", 2)
                    detections.append(det)
                    used.update(range(i, j + 1))
                    if verbose:
                        print(f"    [contrast] sent {i}–{j}")
                    break

        # --- Phase sequence: "La sesión comienza..." + continuation markers ---
        if PHASE_OPEN_RE.search(sent.text) and i not in used:
            continuations = [i]
            for j in range(i + 1, min(i + 30, len(sentences))):
                if j in used:
                    continue
                text_j = sentences[j].text
                if PHASE_CONTINUE_RE.search(text_j) or TERMINAL_RE.search(text_j):
                    continuations.append(j)
                    if TERMINAL_RE.search(text_j):
                        break
            if len(continuations) >= 3:
                end = continuations[-1]
                for k in range(end + 1, min(end + 3, len(sentences))):
                    if k in used:
                        break
                    if sentences[k].paragraph_idx == sentences[end].paragraph_idx:
                        end = k
                    else:
                        break
                det = ListDetection(
                    i, end, "phase-sequence", len(continuations),
                    item_sentence_indices=continuations,
                )
                detections.append(det)
                used.update(range(i, end + 1))
                if verbose:
                    print(f"    [phase-sequence] sent {i}–{end}: "
                          f"\"{sent.text[:60]}...\" ({len(continuations)} phases)")
                continue

        # --- Parallel structure: "Con matemáticas, puede... Con física, puede..." ---
        if PARALLEL_RE.match(sent.text) and i not in used:
            parallels = [i]
            for j in range(i + 1, min(i + 12, len(sentences))):
                if j in used:
                    continue
                if PARALLEL_RE.match(sentences[j].text):
                    parallels.append(j)
            if len(parallels) >= 3:
                end = parallels[-1]
                for k in range(end + 1, min(end + 3, len(sentences))):
                    if k in used:
                        break
                    if sentences[k].paragraph_idx == sentences[end].paragraph_idx:
                        end = k
                    else:
                        break
                det = ListDetection(
                    i, end, "parallel", len(parallels),
                    item_sentence_indices=parallels,
                )
                detections.append(det)
                used.update(range(i, end + 1))
                if verbose:
                    print(f"    [parallel] sent {i}–{end}: "
                          f"\"{sent.text[:60]}...\" ({len(parallels)} items)")
                continue

        # --- Terminal scan-back: "Finalmente..." without prior coverage ---
        if TERMINAL_RE.search(sent.text) and i not in used:
            start = _scan_back_for_list_start(sentences, i, used)
            if start is not None:
                end = i
                for k in range(i + 1, min(i + 3, len(sentences))):
                    if k in used:
                        break
                    if sentences[k].paragraph_idx == sentences[i].paragraph_idx:
                        end = k
                    else:
                        break
                det = ListDetection(start, end, "terminal-back", None)
                detections.append(det)
                used.update(range(start, end + 1))
                if verbose:
                    print(f"    [terminal-back] sent {start}–{end}: "
                          f"\"{sentences[start].text[:60]}...\"")

    return detections


def _find_list_end(
    sentences: list[GuionSentence],
    trigger_idx: int,
    expected_items: int,
    used: set[int],
) -> int:
    ordinals_found = 0
    last_hit = trigger_idx
    terminal_found = False

    for j in range(trigger_idx, min(trigger_idx + expected_items * 4 + 2, len(sentences))):
        if j in used and j != trigger_idx:
            continue
        text = sentences[j].text

        if _is_ordinal_marker(text):
            ordinals_found += 1
            last_hit = j

        if SEQUENTIAL_RE.search(text):
            last_hit = j

        if TERMINAL_RE.search(text):
            terminal_found = True
            last_hit = j
            break

    if terminal_found or ordinals_found >= 2:
        end_idx = last_hit
        for k in range(last_hit + 1, min(last_hit + 3, len(sentences))):
            if k in used:
                break
            if sentences[k].paragraph_idx == sentences[last_hit].paragraph_idx:
                end_idx = k
            elif not _is_ordinal_marker(sentences[k].text):
                break
        return end_idx

    return trigger_idx


def _find_ordinal_end(
    sentences: list[GuionSentence],
    start_idx: int,
    used: set[int],
) -> int:
    last_hit = start_idx
    for j in range(start_idx + 1, min(start_idx + 20, len(sentences))):
        if j in used:
            continue
        text = sentences[j].text
        is_ordinal = _is_ordinal_marker(text)
        is_terminal = bool(TERMINAL_RE.search(text))
        if is_ordinal or is_terminal:
            last_hit = j
            if is_terminal:
                break

    if last_hit == start_idx:
        return start_idx

    end_idx = last_hit
    for k in range(last_hit + 1, min(last_hit + 3, len(sentences))):
        if k in used:
            break
        if sentences[k].paragraph_idx == sentences[last_hit].paragraph_idx:
            end_idx = k
        else:
            break
    return end_idx


def _scan_back_for_list_start(
    sentences: list[GuionSentence],
    terminal_idx: int,
    used: set[int],
) -> int | None:
    paragraph_starts: list[int] = []
    for j in range(max(0, terminal_idx - 20), terminal_idx):
        if j in used:
            continue
        if sentences[j].sentence_idx == 0:
            paragraph_starts.append(j)

    if len(paragraph_starts) < 2:
        return None

    level_starts = [
        j for j in paragraph_starts
        if LEVEL_OPEN_RE.match(sentences[j].text)
    ]
    if len(level_starts) >= 1:
        return level_starts[0]

    return None


def _count_ordinals(
    sentences: list[GuionSentence],
    start: int,
    end: int,
) -> int:
    count = 0
    for j in range(start, end + 1):
        if _is_ordinal_marker(sentences[j].text):
            count += 1
    return count


def _find_item_sentence_indices(
    sentences: list[GuionSentence],
    trigger_idx: int,
    end_idx: int,
) -> list[int]:
    """Return flat sentence indices that introduce list items (ordinal/terminal markers)."""
    indices = []
    for j in range(trigger_idx, end_idx + 1):
        text = sentences[j].text
        if _is_ordinal_marker(text) or TERMINAL_RE.search(text):
            indices.append(j)
    return indices
