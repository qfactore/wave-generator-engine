# Output Architecture

Future WAV and playback JSON exporters will be siblings consuming the same
validated plan. Individual session artifacts come first; assembled four-stereo-
WAV delivery comes later and may not contain independent session logic. A
one-session, 60-second preview will be the future development default. Full
duration or all-session output will require an explicit request. WGE-0 has no
exporter and creates no output payload.
