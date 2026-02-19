import json
from unittest.mock import MagicMock, patch

from PIL import Image

from lacos.storage.services.media_processing_service import (
    MediaProcessingService,
    SPECTROGRAM_HEIGHT,
    SPECTROGRAM_WIDTH,
)


def test_transform_spectrogram_for_wavesurfer_flips_frequency_axis(tmp_path):
    image_path = tmp_path / "spectrogram.png"
    output_path = tmp_path / "spectrogram.json"

    image = Image.new("L", (SPECTROGRAM_WIDTH, SPECTROGRAM_HEIGHT), color=0)
    pixels = image.load()
    pixels[0, 0] = 15  # top (high freq)
    pixels[0, SPECTROGRAM_HEIGHT - 1] = 220  # bottom (low freq)
    image.save(image_path)

    service = MediaProcessingService(bucket_service=MagicMock())
    payload = service._transform_spectrogram_for_wavesurfer(image_path, output_path)
    matrix = json.loads(payload.decode("utf-8"))

    assert len(matrix) == SPECTROGRAM_WIDTH
    assert len(matrix[0]) == SPECTROGRAM_HEIGHT
    assert matrix[0][0] == 220
    assert matrix[0][-1] == 15


def test_derivatives_current_requires_spectrogram_data_sidecar():
    service = MediaProcessingService(bucket_service=MagicMock())

    with (
        patch.object(service, "_get_source_etag", return_value="etag-1"),
        patch.object(service, "_artifact_is_current", return_value=True),
        patch.object(service, "_spectrogram_is_current", return_value=True),
        patch.object(service, "_spectrogram_data_is_current", return_value=False),
    ):
        assert service.derivatives_current("bucket", "audio.wav") is False


def test_spectrogram_data_key_suffix():
    service = MediaProcessingService(bucket_service=MagicMock())
    assert service._spectrogram_data_key("folder/audio.wav") == "folder/audio.wav.spectrogram.json"
