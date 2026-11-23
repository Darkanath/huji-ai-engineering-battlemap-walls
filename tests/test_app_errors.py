"""Failure kinds and input problems each have a plain-language message."""

import pytest

from app.errors import (
    EARLIER_MASK,
    LIMIT,
    SEAMS_NOT_CHECKED,
    FailureKind,
    MapSizeInvalid,
    UploadRejected,
    message,
    partial_message,
    short_reason,
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


@pytest.mark.parametrize("kind", list(FailureKind))
def test_every_failure_kind_has_a_short_reason_and_a_why(kind):
    """The agent table and the partial message have words for every kind."""
    assert short_reason(kind.value)
    assert partial_message([2], 4, kind.value).startswith("Part 2 of 4 could not be traced (")


def test_partial_message_names_each_part_and_the_total():
    """FR-012: the parts by number, as in the preview and the table."""
    text = partial_message([4, 2], 4, "timeout")
    assert text.startswith("Parts 2 and 4 of 4 could not be traced (it took too long).")
    assert "Parts 1, 2 and 3 of 9" in partial_message([1, 2, 3], 9, None)
    assert "time or cost limit" in partial_message([1], 4, LIMIT)


def test_skipped_parts_and_no_failure_read_plainly():
    """A skipped part says why; a finished one has no reason."""
    assert short_reason(LIMIT) == "skipped: limit reached"
    assert short_reason(None) == ""
    assert "borders between the parts" in SEAMS_NOT_CHECKED
