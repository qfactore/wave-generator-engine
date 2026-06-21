# Calibration Preflight

Calibration policy resolves the 1.1 reference multiplier, 0.80 post-calibration
playback metadata, no per-motif or per-session normalization, no default limiter,
relative-amplitude preservation, float64 diagnostic intermediate, −3 dBFS
future ceiling, 3 dB reserve, and provisional 24-bit delivery.

Preflight calculates raw and projected motif peaks and RMS values in detached
float64 diagnostic memory. It applies neither playback intensity nor Focus Role,
normalization, limiting, or persistence. Frozen samples remain unchanged.

Motif-only calculations cannot certify a final render because event gain,
overlap, and scheduling do not exist. The status is:

`not_assessable_without_event_gain_and_overlap_plan`
