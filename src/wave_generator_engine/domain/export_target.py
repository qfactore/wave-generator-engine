from enum import StrEnum


class ExportTarget(StrEnum):
    DIAGNOSTIC_WAV = "diagnostic_wav"
    PLAYBACK_JSON = "playback_json"
    ANALYSIS_REPORT = "analysis_report"
    ASSEMBLED_STEREO_WAV_PACK = "assembled_stereo_wav_pack"
