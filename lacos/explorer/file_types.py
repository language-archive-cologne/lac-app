from pathlib import Path

FILE_TYPE_AAC = "aac"
FILE_TYPE_AIF = "aif"
FILE_TYPE_AIFF = "aiff"
FILE_TYPE_AVI = "avi"
FILE_TYPE_CHAT = "cha"
FILE_TYPE_CMDI = "cmdi"
FILE_TYPE_CSV = "csv"
FILE_TYPE_DOC = "doc"
FILE_TYPE_DOCX = "docx"
FILE_TYPE_ELAN = "eaf"
FILE_TYPE_FLAC = "flac"
FILE_TYPE_IMDI = "imdi"
FILE_TYPE_JPEG = "jpeg"
FILE_TYPE_JPG = "jpg"
FILE_TYPE_JSON = "json"
FILE_TYPE_JSONLD = "jsonld"
FILE_TYPE_M4A = "m4a"
FILE_TYPE_MKV = "mkv"
FILE_TYPE_MOV = "mov"
FILE_TYPE_MP3 = "mp3"
FILE_TYPE_MP4 = "mp4"
FILE_TYPE_ODT = "odt"
FILE_TYPE_OGG = "ogg"
FILE_TYPE_PDF = "pdf"
FILE_TYPE_PNG = "png"
FILE_TYPE_RTF = "rtf"
FILE_TYPE_SUBTITLE_SRT = "srt"
FILE_TYPE_TEXTGRID = "textgrid"
FILE_TYPE_TRANSCRIBER = "trs"
FILE_TYPE_TSV = "tsv"
FILE_TYPE_TXT = "txt"
FILE_TYPE_SUBTITLE_VTT = "vtt"
FILE_TYPE_WAV = "wav"
FILE_TYPE_WEBM = "webm"
FILE_TYPE_XML = "xml"
FILE_TYPE_YAML = "yaml"
FILE_TYPE_YML = "yml"

FILE_TYPE_LABELS = {
    FILE_TYPE_AAC: "AAC",
    FILE_TYPE_AIF: "AIF",
    FILE_TYPE_AIFF: "AIFF",
    FILE_TYPE_AVI: "AVI",
    FILE_TYPE_CHAT: "CHAT",
    FILE_TYPE_CMDI: "CMDI",
    FILE_TYPE_CSV: "CSV",
    FILE_TYPE_DOC: "DOC",
    FILE_TYPE_DOCX: "DOCX",
    FILE_TYPE_ELAN: "ELAN",
    FILE_TYPE_FLAC: "FLAC",
    FILE_TYPE_IMDI: "IMDI",
    FILE_TYPE_JPEG: "JPEG",
    FILE_TYPE_JPG: "JPG",
    FILE_TYPE_JSON: "JSON",
    FILE_TYPE_JSONLD: "JSON-LD",
    FILE_TYPE_M4A: "M4A",
    FILE_TYPE_MKV: "MKV",
    FILE_TYPE_MOV: "MOV",
    FILE_TYPE_MP3: "MP3",
    FILE_TYPE_MP4: "MP4",
    FILE_TYPE_ODT: "ODT",
    FILE_TYPE_OGG: "OGG",
    FILE_TYPE_PDF: "PDF",
    FILE_TYPE_PNG: "PNG",
    FILE_TYPE_RTF: "RTF",
    FILE_TYPE_SUBTITLE_SRT: "SRT subtitles",
    FILE_TYPE_TEXTGRID: "TextGrid",
    FILE_TYPE_TRANSCRIBER: "Transcriber",
    FILE_TYPE_TSV: "TSV",
    FILE_TYPE_TXT: "TXT",
    FILE_TYPE_SUBTITLE_VTT: "WebVTT subtitles",
    FILE_TYPE_WAV: "WAV",
    FILE_TYPE_WEBM: "WebM",
    FILE_TYPE_XML: "XML",
    FILE_TYPE_YAML: "YAML",
    FILE_TYPE_YML: "YML",
}

EXTENSION_FILE_TYPES = {
    ".aac": FILE_TYPE_AAC,
    ".aif": FILE_TYPE_AIF,
    ".aiff": FILE_TYPE_AIFF,
    ".avi": FILE_TYPE_AVI,
    ".cha": FILE_TYPE_CHAT,
    ".cmdi": FILE_TYPE_CMDI,
    ".csv": FILE_TYPE_CSV,
    ".doc": FILE_TYPE_DOC,
    ".docx": FILE_TYPE_DOCX,
    ".eaf": FILE_TYPE_ELAN,
    ".flac": FILE_TYPE_FLAC,
    ".imdi": FILE_TYPE_IMDI,
    ".jpeg": FILE_TYPE_JPEG,
    ".jpg": FILE_TYPE_JPG,
    ".json": FILE_TYPE_JSON,
    ".jsonld": FILE_TYPE_JSONLD,
    ".m4a": FILE_TYPE_M4A,
    ".mkv": FILE_TYPE_MKV,
    ".mov": FILE_TYPE_MOV,
    ".mp3": FILE_TYPE_MP3,
    ".mp4": FILE_TYPE_MP4,
    ".odt": FILE_TYPE_ODT,
    ".ogg": FILE_TYPE_OGG,
    ".pdf": FILE_TYPE_PDF,
    ".png": FILE_TYPE_PNG,
    ".rtf": FILE_TYPE_RTF,
    ".srt": FILE_TYPE_SUBTITLE_SRT,
    ".textgrid": FILE_TYPE_TEXTGRID,
    ".trs": FILE_TYPE_TRANSCRIBER,
    ".tsv": FILE_TYPE_TSV,
    ".txt": FILE_TYPE_TXT,
    ".vtt": FILE_TYPE_SUBTITLE_VTT,
    ".wav": FILE_TYPE_WAV,
    ".webm": FILE_TYPE_WEBM,
    ".xml": FILE_TYPE_XML,
    ".yaml": FILE_TYPE_YAML,
    ".yml": FILE_TYPE_YML,
}
MIME_FILE_TYPES = {
    "application/csv": FILE_TYPE_CSV,
    "application/cmdi+xml": FILE_TYPE_CMDI,
    "application/msword": FILE_TYPE_DOC,
    "application/json": FILE_TYPE_JSON,
    "application/ld+json": FILE_TYPE_JSONLD,
    "application/ogg": FILE_TYPE_OGG,
    "application/oda": FILE_TYPE_ODT,
    "application/pdf": FILE_TYPE_PDF,
    "application/rtf": FILE_TYPE_RTF,
    "application/vnd.oasis.opendocument.text": FILE_TYPE_ODT,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": FILE_TYPE_DOCX,
    "application/xml": FILE_TYPE_XML,
    "audio/aac": FILE_TYPE_AAC,
    "audio/aiff": FILE_TYPE_AIFF,
    "audio/flac": FILE_TYPE_FLAC,
    "audio/m4a": FILE_TYPE_M4A,
    "audio/mp4": FILE_TYPE_M4A,
    "audio/mpeg": FILE_TYPE_MP3,
    "audio/ogg": FILE_TYPE_OGG,
    "audio/wav": FILE_TYPE_WAV,
    "audio/wave": FILE_TYPE_WAV,
    "audio/x-aiff": FILE_TYPE_AIFF,
    "audio/x-flac": FILE_TYPE_FLAC,
    "audio/x-m4a": FILE_TYPE_M4A,
    "audio/x-wav": FILE_TYPE_WAV,
    "image/jpeg": FILE_TYPE_JPG,
    "image/png": FILE_TYPE_PNG,
    "text/cha": FILE_TYPE_CHAT,
    "text/csv": FILE_TYPE_CSV,
    "text/plain": FILE_TYPE_TXT,
    "text/tab-separated-values": FILE_TYPE_TSV,
    "text/vtt": FILE_TYPE_SUBTITLE_VTT,
    "text/xml": FILE_TYPE_XML,
    "video/mp4": FILE_TYPE_MP4,
    "video/quicktime": FILE_TYPE_MOV,
    "video/webm": FILE_TYPE_WEBM,
    "video/x-matroska": FILE_TYPE_MKV,
    "video/x-msvideo": FILE_TYPE_AVI,
}


def file_type_for_resource(mime_type: str | None, file_name: str | None) -> str | None:
    """Return a concrete explorer file-format facet value for one resource."""
    normalized_mime = (mime_type or "").strip().lower()
    extension = Path(file_name or "").suffix.lower()

    extension_type = _file_type_from_extension(extension)
    if extension_type:
        return extension_type

    return _file_type_from_mime(normalized_mime)


def _file_type_from_mime(mime_type: str) -> str | None:
    return MIME_FILE_TYPES.get(mime_type)


def _file_type_from_extension(extension: str) -> str | None:
    return EXTENSION_FILE_TYPES.get(extension)
