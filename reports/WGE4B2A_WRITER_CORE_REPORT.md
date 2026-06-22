# WGE-4B2A Deterministic PCM16 Writer Core

Status: `WGE4B2A_WRITER_CORE_READY`

- Starting checkpoint: `eb7e117ba853126238624b4265da1b0a4732541e`
- Contract: `diagnostic_wav_export_contract_v1`
- Writer: contract-bound standard RIFF/WAVE PCM16 byte writer
- Quantizer: float64 ×32768, nearest ties-to-even, fail-closed bounds
- Tie fixture codes: `[-32768, -2, -2, 0, 0, 0, 2, 2, 32767]`
- Stereo layout: `L0, R0, L1, R1`
- Container: 44-byte header, PCM code 1, stereo, 48 kHz, 16-bit,
  192,000-byte/s rate, four-byte alignment
- Readback: independent chunk parser and independent reference quantization
- Synthetic fixture frames: 9
- Synthetic fixture data bytes: 36
- Synthetic WAV SHA-256:
  `9e79bddda640825b08e534b9ab2614538fb91dc4fd08444e29ace0c8d86b10fe`
- Synthetic data SHA-256:
  `1e75325d6e1715b6961044fb3437aee75114acb990159b6c340e517fb714d230`
- Maximum fixture quantization error: `1/65536`
- Repeated bytes: identical across working directory and environment changes
- WGE-4B2B authorization: true

No qualified plan was rendered, no frozen motif sample was accessed, and no
real or persistent WAV was created.
