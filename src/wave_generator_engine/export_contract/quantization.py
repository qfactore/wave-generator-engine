import numpy as np

from wave_generator_engine.errors import ValidationFailure

PCM16_SCALE = 32768.0
PCM16_MIN = -32768
PCM16_MAX = 32767
PCM16_MAX_INPUT = PCM16_MAX / PCM16_SCALE
PCM16_MAX_ERROR = 0.5 / PCM16_SCALE


def quantize_pcm16(values: np.ndarray) -> np.ndarray:
    """Synthetic/reference quantizer only; WGE-4B1 does not write audio."""
    source = np.asarray(values)
    if source.dtype != np.float64:
        raise ValidationFailure("Diagnostic PCM16 quantizer requires float64 input")
    if not np.all(np.isfinite(source)):
        raise ValidationFailure("Diagnostic PCM16 quantizer rejects NaN and infinity")
    if np.any(source < -1.0) or np.any(source > PCM16_MAX_INPUT):
        raise ValidationFailure("Diagnostic PCM16 quantizer input exceeds legal range")
    codes = np.rint(source * PCM16_SCALE)
    if np.any(codes < PCM16_MIN) or np.any(codes > PCM16_MAX):
        raise ValidationFailure("Diagnostic PCM16 quantizer overflow")
    return codes.astype("<i2")


def decode_pcm16(codes: np.ndarray) -> np.ndarray:
    source = np.asarray(codes)
    if source.dtype.kind != "i" or source.dtype.itemsize != 2:
        raise ValidationFailure("PCM16 decode reference requires signed 16-bit codes")
    return source.astype(np.float64) / PCM16_SCALE
