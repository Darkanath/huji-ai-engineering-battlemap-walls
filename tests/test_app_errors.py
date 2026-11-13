"""Failure kinds and input problems each have a plain-language message."""

import pytest

from app.errors import (
    EARLIER_MASK,
    FailureKind,
    MapSizeInvalid,
    UploadRejected,
    message,
)


@pytest.mark.parametrize("kind", list(FailureKind))
def test_every_failure_kind_has_a_plain_message(kind):
    """Each kind has text, and none of it looks like a raw error."""
    text = message(kind)
    assert text
    for raw in ("Traceback", "Error:", "Exception", "anthropic."):
        assert raw not in text
    assert EARLIER_MASK not in text


def test_earlier_mask_sentence_only_when_asked():
    """The reminder is appended only when a mask is still on screen."""
    assert message(FailureKind.network, has_earlier_mask=True).endswith(EARLIER_MASK)
    assert not message(FailureKind.network).endswith(EARLIER_MASK)


@pytest.mark.parametrize(
    ("reason", "text"),
    [
        ("wrong_type", "That file type isn't supported. Upload a PNG, JPEG or WebP image."),
        ("too_large", "That file is larger than 20 MB. Upload a smaller image."),
        ("not_an_image", "That file couldn't be opened as an image. Try exporting it again."),
    ],
)
def test_upload_rejections_have_their_message(reason, text):
    """Each rejection reason carries the text from the UI contract."""
    assert UploadRejected(reason).message == text


def test_map_size_invalid_has_the_range_message():
    """The map-size message names the range."""
    assert MapSizeInvalid().message == "Map width and height must be whole numbers from 1 to 200."
