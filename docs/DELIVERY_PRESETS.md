# Delivery Presets

X-Alpha25 declares 1500 seconds, X-Alpha45 declares 2700 seconds, and
Diagnostic 60s declares 60 seconds. Each references X-Alpha Standard and a
default playback intensity of 0.80.

Playback intensity is a post-calibration linear scalar in delivery/playback
metadata. It is not a waveform LeverSet value and is never baked into future
WAV data. The engine validates defaults from 0.00 through 1.00 as a conservative
metadata safety range, not as a new waveform authority claim.

Session selection is explicit at run time. Exact seven-session-to-four-stereo-
file assembly remains unresolved and is not invented here.
