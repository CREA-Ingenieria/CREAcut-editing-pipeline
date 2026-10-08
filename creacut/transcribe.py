"""Stage 1 — Whisper transcription with caching and ghost-word patching."""

import json
import subprocess
from pathlib import Path

from .media import ffmpeg_executable

WHISPER_SAMPLE_RATE = 16000


class WhisperDeviceError(RuntimeError):
    """A CUDA-capable Whisper run could not safely continue on its GPU."""


def _select_whisper_device() -> tuple[str, str, bool]:
    """Return device, human-readable diagnostics and the safe FP16 setting.

    Torch is intentionally imported only when transcription is needed, so
    already-cached projects remain usable in inspection-only installations.
    """
    try:
        import torch
    except ImportError:
        return "cpu", "CPU - CUDA unavailable (PyTorch no está instalado)", False

    if torch.cuda.is_available():
        try:
            name = torch.cuda.get_device_name(0)
        except Exception:
            name = "GPU NVIDIA"
        return "cuda", f"CUDA - {name}", True
    return "cpu", "CPU - CUDA unavailable", False


def _is_cuda_oom(error: BaseException) -> bool:
    text = str(error).lower()
    return "cuda" in text and ("out of memory" in text or "memory allocation" in text)


def _release_cuda_memory() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        # Diagnostic cleanup must never hide the original Whisper exception.
        pass


def _gpu_fallback_model(model_name: str) -> str | None:
    """Use a smaller GPU model only after a verified large-model VRAM OOM."""
    return "medium" if model_name.startswith("large") else None


def _load_audio(path: str | Path):
    """Decode audio exactly like ``whisper.audio.load_audio``, with CREAcut's FFmpeg.

    Whisper runs ``ffmpeg`` by name from PATH. Environments installed from PyPI
    (the Windows installer and the macOS first-run setup) only ship
    imageio-ffmpeg's binary, which has a different name, so Whisper receives
    the decoded samples instead of a path.
    """
    import numpy as np

    command = [
        ffmpeg_executable(), "-nostdin", "-threads", "0", "-i", str(path),
        "-f", "s16le", "-ac", "1", "-acodec", "pcm_s16le",
        "-ar", str(WHISPER_SAMPLE_RATE), "-",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, check=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "replace").strip()[-400:]
        raise RuntimeError(f"FFmpeg no pudo leer el audio de {Path(path).name}: {detail}") from exc
    return np.frombuffer(completed.stdout, np.int16).flatten().astype(np.float32) / 32768.0


def _load_whisper_model(
    whisper,
    model_name: str,
    *,
    device: str,
    verbose: bool,
) -> tuple[object, str]:
    """Load the requested model, preserving GPU use across a VRAM retry."""
    try:
        return whisper.load_model(model_name, device=device), model_name
    except RuntimeError as exc:
        fallback = _gpu_fallback_model(model_name)
        if device != "cuda" or not _is_cuda_oom(exc) or fallback is None:
            raise

        _release_cuda_memory()
        if verbose:
            print(
                f"  Whisper GPU memory exhausted loading {model_name}; "
                f"retrying on CUDA with {fallback}."
            )
        try:
            return whisper.load_model(fallback, device="cuda"), fallback
        except RuntimeError as fallback_exc:
            if _is_cuda_oom(fallback_exc):
                raise WhisperDeviceError(
                    "Whisper agotó la VRAM incluso con el modelo medium en CUDA. "
                    "Cierra aplicaciones que usen la GPU o configura un modelo más "
                    "pequeño; CREAcut no cambiará silenciosamente a CPU."
                ) from fallback_exc
            raise


def _transcribe_with_gpu_fallback(
    model,
    *,
    model_name: str,
    requested_model_name: str,
    device: str,
    audio,
    language: str,
    prompt: str,
    fp16: bool,
    beam_size: int,
    verbose: bool,
) -> tuple[dict, object, str]:
    """Run Whisper while keeping a GPU VRAM retry observable and bounded."""
    kwargs = {
        "language": language,
        "word_timestamps": True,
        "initial_prompt": prompt,
        "condition_on_previous_text": False,
        "fp16": fp16,
        "beam_size": beam_size,
    }
    try:
        return model.transcribe(audio, **kwargs), model, model_name
    except RuntimeError as exc:
        fallback = _gpu_fallback_model(requested_model_name)
        if (
            device != "cuda"
            or not _is_cuda_oom(exc)
            or model_name != requested_model_name
            or fallback is None
        ):
            if device == "cuda" and _is_cuda_oom(exc):
                raise WhisperDeviceError(
                    "Whisper agotó la VRAM durante la transcripción en CUDA. "
                    "CREAcut conserva CUDA en lugar de cambiar silenciosamente a CPU; "
                    "prueba un modelo más pequeño o libera VRAM."
                ) from exc
            raise
        _release_cuda_memory()
        if verbose:
            print(
                f"  Whisper GPU memory exhausted transcribing {requested_model_name}; "
                f"retrying on CUDA with {fallback}."
            )
        import whisper

        retry_model, retry_name = _load_whisper_model(
            whisper, fallback, device="cuda", verbose=verbose
        )
        try:
            return retry_model.transcribe(audio, **kwargs), retry_model, retry_name
        except RuntimeError as retry_exc:
            if _is_cuda_oom(retry_exc):
                raise WhisperDeviceError(
                    "Whisper agotó la VRAM incluso con el modelo medium en CUDA. "
                    "Cierra aplicaciones que usen la GPU o configura un modelo más pequeño."
                ) from retry_exc
            raise


def _patch_whisper_dtw() -> None:
    # whisper.timing.dtw calls x.double() while the tensor is still on MPS.
    # MPS doesn't support float64, so we patch dtw to move to CPU first.
    # Using x.float() (float32) is safe: dtw_cpu only needs real-valued numpy input.
    try:
        import whisper.timing as _t
    except ImportError:
        return

    _dtw_cpu = _t.dtw_cpu
    _dtw_cuda = getattr(_t, "dtw_cuda", None)

    def _safe_dtw(x):
        if x.is_cuda and _dtw_cuda is not None:
            try:
                return _dtw_cuda(x)
            except Exception:
                pass
        return _dtw_cpu(x.float().cpu().numpy())

    _t.dtw = _safe_dtw


_patch_whisper_dtw()


def transcribe(
    video_path: Path,
    config: dict,
    verbose: bool = False,
    model=None,
    fp16: bool = True,
    beam_size: int = 5,
) -> dict:
    whisper_cfg = config.get("whisper", {})
    model_name = whisper_cfg.get("model", "large-v3")
    language = whisper_cfg.get("language", "es")
    prompt = whisper_cfg.get("prompt", "")

    cache_path = video_path.with_suffix(".whisper.json")
    if cache_path.exists():
        if verbose:
            print(f"  Cached transcription: {cache_path}")
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)

    device, device_label, cuda_fp16 = _select_whisper_device()
    effective_fp16 = bool(fp16 and cuda_fp16)
    if model is None:
        import whisper

        if verbose:
            print(f"  Whisper device: {device_label}")
            print(f"  Loading Whisper {model_name} on {device}...")
        model, active_model_name = _load_whisper_model(
            whisper, model_name, device=device, verbose=verbose
        )
    else:
        active_model_name = model_name
        if verbose:
            print(f"  Whisper device: {device_label} (modelo proporcionado)")

    if verbose and fp16 and not effective_fp16:
        print("  Whisper precision: FP32 (FP16 solo se usa con CUDA)")

    if verbose:
        print(f"  Transcribing {video_path.name}...")
    audio = _load_audio(video_path)
    result, _model, active_model_name = _transcribe_with_gpu_fallback(
        model,
        model_name=active_model_name,
        requested_model_name=model_name,
        device=device,
        audio=audio,
        language=language,
        prompt=prompt,
        fp16=effective_fp16,
        beam_size=beam_size,
        verbose=verbose,
    )
    if verbose and active_model_name != model_name:
        print(f"  Whisper active model: {active_model_name} (GPU VRAM fallback)")

    serializable = {
        "text": result["text"],
        "segments": [
            {
                "start": s["start"],
                "end": s["end"],
                "text": s["text"],
                "no_speech_prob": s.get("no_speech_prob", 0),
                "words": [
                    {"word": w["word"], "start": w["start"], "end": w["end"]}
                    for w in s.get("words", [])
                ],
            }
            for s in result["segments"]
        ],
    }

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    if verbose:
        print(f"  Cached → {cache_path}")

    return serializable


# ── Ghost-word patching ─────────────────────────────────────────────────


def _detect_speech_onset(
    audio_path: str,
    t_start: float,
    t_end: float,
    window_sec: float = 0.1,
    silence_db: float = -45.0,
    min_silence_dur: float = 0.3,
) -> float | None:
    """Find the first speech onset after a sustained silence gap."""
    import array
    import math
    import subprocess

    cmd = [
        ffmpeg_executable(), "-hide_banner", "-loglevel", "error",
        "-i", str(audio_path),
        "-ss", str(t_start), "-to", str(t_end),
        "-ac", "1", "-ar", "16000", "-f", "s16le", "-",
    ]
    raw = subprocess.run(cmd, capture_output=True).stdout
    if not raw:
        return None

    samples = array.array("h", raw)
    sr = 16000
    window = int(window_sec * sr)
    min_win = int(min_silence_dur / window_sec)
    silence_count = 0
    had_silence = False

    for idx in range(0, len(samples) - window, window):
        chunk = samples[idx : idx + window]
        rms = math.sqrt(sum(x * x for x in chunk) / len(chunk))
        db = 20 * math.log10(max(rms, 1) / 32768)
        if db < silence_db:
            silence_count += 1
            if silence_count >= min_win:
                had_silence = True
        else:
            if had_silence:
                return t_start + (idx / sr)
            silence_count = 0
    return None


def _transcribe_range(
    model,
    audio_path: str,
    t_start: float,
    t_end: float,
    language: str = "es",
    prompt: str = "",
    fp16: bool = False,
    beam_size: int = 5,
) -> list[dict]:
    """Transcribe a time range and return segments with absolute timestamps."""
    import os
    import subprocess
    import tempfile

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        subprocess.run(
            [
                ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(audio_path),
                "-ss", str(t_start), "-to", str(t_end),
                "-ac", "1", "-ar", "16000", tmp.name,
            ],
            check=True,
        )
        result = model.transcribe(
            _load_audio(tmp.name),
            language=language,
            word_timestamps=True,
            condition_on_previous_text=False,
            fp16=fp16,
            beam_size=beam_size,
            initial_prompt=prompt,
        )
    finally:
        os.unlink(tmp.name)

    segments = []
    for s in result.get("segments", []):
        segments.append(
            {
                "start": round(s["start"] + t_start, 2),
                "end": round(s["end"] + t_start, 2),
                "text": s["text"],
                "no_speech_prob": s.get("no_speech_prob", 0),
                "words": [
                    {
                        "word": w["word"],
                        "start": round(w["start"] + t_start, 2),
                        "end": round(w["end"] + t_start, 2),
                    }
                    for w in s.get("words", [])
                ],
            }
        )
    return segments


def patch_ghost_words(
    audio_path,
    cache_path=None,
    config: dict | None = None,
    model=None,
    verbose: bool = False,
    fp16: bool | None = None,
    beam_size: int = 5,
):
    """Scan cached transcription for ghost words hiding speech, re-transcribe.

    Returns (segments, patched) — patched is True if any ghost words were fixed.
    Loads Whisper model on demand only if recoverable ghost words are found.
    """
    if config is None:
        from .config import DEFAULTS

        config = DEFAULTS

    audio_path = Path(audio_path)
    if cache_path is None:
        cache_path = audio_path.with_suffix(".whisper.json")
    else:
        cache_path = Path(cache_path)

    if not cache_path.exists():
        return [], False

    max_word_gap = config["retakes"]["max_word_gap"]
    whisper_cfg = config.get("whisper", {})
    model_name = whisper_cfg.get("model", "large-v3")
    language = whisper_cfg.get("language", "es")
    prompt = whisper_cfg.get("prompt", "")

    with open(cache_path, encoding="utf-8") as f:
        data = json.load(f)

    segments = data["segments"]

    ghosts = []
    for seg_idx, seg in enumerate(segments):
        for w_idx, w in enumerate(seg.get("words", [])):
            if w["end"] - w["start"] > max_word_gap:
                ghosts.append((seg_idx, w_idx, w))

    if not ghosts:
        return segments, False

    recoverable = []
    for seg_idx, w_idx, w in ghosts:
        onset = _detect_speech_onset(str(audio_path), w["start"], w["end"])
        if onset is not None:
            recoverable.append((seg_idx, w_idx, w, onset))
            if verbose:
                print(
                    f"  [patch] Ghost '{w['word'].strip()}' "
                    f"[{w['start']:.1f}–{w['end']:.1f}] → "
                    f"speech onset at {onset:.1f}s"
                )
        elif verbose:
            print(
                f"  [patch] Ghost '{w['word'].strip()}' "
                f"[{w['start']:.1f}–{w['end']:.1f}] — no hidden speech"
            )

    if not recoverable:
        return segments, False

    device, device_label, cuda_fp16 = _select_whisper_device()
    effective_fp16 = cuda_fp16 if fp16 is None else bool(fp16 and cuda_fp16)
    if model is None:
        import whisper

        if verbose:
            print(f"  [patch] Whisper device: {device_label}")
            print(f"  [patch] Loading Whisper {model_name} on {device}...")
        model, _active_model_name = _load_whisper_model(
            whisper, model_name, device=device, verbose=verbose
        )

    patched = False
    for seg_idx, w_idx, ghost_w, onset in reversed(recoverable):
        retranscribe_start = max(ghost_w["start"], onset - 0.5)
        new_segs = _transcribe_range(
            model, str(audio_path),
            retranscribe_start, ghost_w["end"],
            language=language, prompt=prompt,
            fp16=effective_fp16, beam_size=beam_size,
        )
        if not new_segs:
            if verbose:
                print(
                    f"  [patch] No segments from re-transcription "
                    f"[{retranscribe_start:.1f}–{ghost_w['end']:.1f}]"
                )
            continue

        if verbose:
            for ns in new_segs:
                print(
                    f"  [patch] Re-transcribed "
                    f"[{ns['start']:.1f}–{ns['end']:.1f}]: "
                    f"{ns['text'][:70]}..."
                )

        seg = segments[seg_idx]
        words = seg.get("words", [])
        pre_words = words[:w_idx]
        post_words = words[w_idx + 1 :]

        replacement = []

        if pre_words:
            replacement.append(
                {
                    "start": seg["start"],
                    "end": pre_words[-1]["end"],
                    "text": "".join(w["word"] for w in pre_words),
                    "no_speech_prob": seg["no_speech_prob"],
                    "words": pre_words,
                }
            )

        replacement.extend(new_segs)

        if post_words:
            replacement.append(
                {
                    "start": post_words[0]["start"],
                    "end": seg["end"],
                    "text": "".join(w["word"] for w in post_words),
                    "no_speech_prob": seg["no_speech_prob"],
                    "words": post_words,
                }
            )

        segments[seg_idx : seg_idx + 1] = replacement
        patched = True

    if patched:
        data["segments"] = segments
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if verbose:
            print(f"  [patch] Cache updated: {cache_path}")

    return segments, patched
