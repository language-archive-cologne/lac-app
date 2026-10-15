"""Check that audio derivatives work in the player, with small S3 reads only.

No file is downloaded. Each check reads a HEAD response or a short byte range:
the first 4 KB of a WAV file (plus a 24-byte chunk header when a large
metadata chunk comes first), the 6-byte spectrogram header, the 14-byte
pitch header and the last bytes of the peaks file.
"""

import re
import struct

from lacos.storage.services.media_processing_service import FFT_SAMPLES
from lacos.storage.services.media_processing_service import HOP_DIVISOR
from lacos.storage.services.media_processing_service import N_MELS
from lacos.storage.services.media_processing_service import TARGET_SAMPLE_RATE

WAV_HEADER_BYTES = 4096
# A chunk header (8 bytes) plus the fmt fields up to the byte rate.
CHUNK_HEADER_BYTES = 24
MAX_WAV_CHUNKS = 32
PEAKS_TAIL_BYTES = 512
SPECTROGRAM_HEADER_BYTES = 6
PITCH_HEADER_BYTES = 14
# Largest difference between the audio and a derivative before the player
# visibly drifts. Peaks store the ffprobe duration; spectrogram frames round
# the duration down to one hop.
DURATION_TOLERANCE_SECONDS = 0.5

_PEAKS_DURATION = re.compile(rb'"duration"\s*:\s*([0-9.]+)')


def read_range(s3_client, bucket: str, key: str, byte_range: str) -> bytes:
    response = s3_client.get_object(Bucket=bucket, Key=key, Range=f"bytes={byte_range}")
    return response["Body"].read()


def wav_duration(read, content_length: int) -> float | None:
    """Return the duration of a WAV file from its chunk headers, or None.

    ``read(start, end)`` returns the bytes in an inclusive range. The first
    4 KB hold the chunk list of most files. Metadata chunks such as LIST can be
    larger; then only the next 24-byte chunk header is read, never the chunk.
    """
    header = read(0, WAV_HEADER_BYTES - 1)
    if (
        len(header) < 12
        or header[:4] not in (b"RIFF", b"RF64")
        or header[8:12] != b"WAVE"
    ):
        return None

    byte_rate = None
    position = 12
    for _ in range(MAX_WAV_CHUNKS):
        if position + 8 > content_length:
            return None
        chunk = header[position : position + CHUNK_HEADER_BYTES]
        # Read again only when the chunk header, or the fmt fields, lie beyond
        # the bytes already read.
        if len(chunk) < 8 or (chunk[:4] == b"fmt " and len(chunk) < 20):
            chunk = read(position, position + CHUNK_HEADER_BYTES - 1)
        if len(chunk) < 8:
            return None
        chunk_id = chunk[:4]
        chunk_size = struct.unpack_from("<I", chunk, 4)[0]
        if chunk_id == b"fmt " and len(chunk) >= 20:
            byte_rate = struct.unpack_from("<I", chunk, 16)[0]
        if chunk_id == b"data":
            if not byte_rate:
                return None
            data_size = content_length - (position + 8)
            if 0 < chunk_size < data_size:
                data_size = chunk_size
            return data_size / byte_rate
        position += 8 + chunk_size + (chunk_size % 2)
    return None


def peaks_duration(tail: bytes) -> float | None:
    match = _PEAKS_DURATION.search(tail)
    return float(match.group(1)) if match else None


def spectrogram_duration(n_frames: int) -> float:
    hop_size = max(64, FFT_SAMPLES // HOP_DIVISOR)
    return ((n_frames - 1) * hop_size + FFT_SAMPLES) / TARGET_SAMPLE_RATE


def _duration_problem(name: str, value: float, audio: float | None) -> str | None:
    if audio is None or abs(value - audio) <= DURATION_TOLERANCE_SECONDS:
        return None
    return f"{name} covers {value:.1f} s, the audio is {audio:.1f} s"


def check_player_files(
    s3_client, bucket: str, source: dict, keys: dict, heads: dict
) -> dict:
    """Return the problems that stop the player from showing correct files.

    ``source`` is the HEAD response of the audio file. ``heads`` holds the HEAD
    response of each derivative in ``keys`` (peaks, spectrogram, pitch).
    """
    problems: list[str] = []
    notes: list[str] = []

    audio = None
    if keys["source"].lower().endswith((".wav", ".wave")):

        def read(start: int, end: int) -> bytes:
            return read_range(s3_client, bucket, keys["source"], f"{start}-{end}")

        audio = wav_duration(read, source.get("ContentLength", 0))
    if audio is None:
        notes.append("duration not checked (not a readable WAV header)")

    peaks = heads["peaks"]
    if not peaks.get("ContentLength"):
        problems.append("peaks file is empty")
    else:
        tail = read_range(s3_client, bucket, keys["peaks"], f"-{PEAKS_TAIL_BYTES}")
        duration = peaks_duration(tail)
        if duration is None:
            problems.append("peaks file has no duration")
        elif problem := _duration_problem("waveform", duration, audio):
            problems.append(problem)

    spectrogram = heads["spectrogram"]
    if spectrogram.get("ContentEncoding"):
        problems.append(f"spectrogram is {spectrogram['ContentEncoding']}-encoded")
    else:
        header = read_range(
            s3_client,
            bucket,
            keys["spectrogram"],
            f"0-{SPECTROGRAM_HEADER_BYTES - 1}",
        )
        if len(header) < SPECTROGRAM_HEADER_BYTES:
            problems.append("spectrogram header is incomplete")
        else:
            n_frames, n_bins = struct.unpack("<IH", header)
            expected = SPECTROGRAM_HEADER_BYTES + n_frames * n_bins
            if n_bins != N_MELS or spectrogram.get("ContentLength") != expected:
                problems.append("spectrogram header does not match the file size")
            elif problem := _duration_problem(
                "spectrogram",
                spectrogram_duration(n_frames),
                audio,
            ):
                problems.append(problem)

    pitch = heads.get("pitch")
    if pitch is not None:
        header = read_range(
            s3_client, bucket, keys["pitch"], f"0-{PITCH_HEADER_BYTES - 1}"
        )
        if len(header) < PITCH_HEADER_BYTES:
            problems.append("pitch header is incomplete")
        else:
            n_frames = struct.unpack_from("<I", header)[0]
            if pitch.get("ContentLength") != PITCH_HEADER_BYTES + 4 * n_frames:
                problems.append("pitch header does not match the file size")

    return {"problems": problems, "notes": notes, "audio_duration": audio}
