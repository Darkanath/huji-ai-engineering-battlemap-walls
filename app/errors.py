"""Every way a pass or an input can fail, and the plain-language message the user sees.

A failed model call never reaches the page as a stack trace: `app.tracer.run_pass` turns each
cause into a `PassFailure` with a `FailureKind`, and `message()` gives its text. Input problems
raise `UploadRejected` or `MapSizeInvalid` before any model call. The texts are the ones in
`specs/001-battlemap-tracer-app/contracts/ui.md`.
"""

from enum import StrEnum

from pydantic import BaseModel

from app.domain import PassKind, Usage

EARLIER_MASK = "Your earlier mask is still here."


class FailureKind(StrEnum):
    """Why a pass ended without a usable answer."""

    refusal = "refusal"
    output_limit = "output_limit"
    pass_limit = "pass_limit"
    rate_limit = "rate_limit"
    provider_busy = "provider_busy"
    auth = "auth"
    missing_key = "missing_key"
    network = "network"
    timeout = "timeout"
    unreadable = "unreadable"
    unexpected = "unexpected"


MESSAGES = {
    FailureKind.refusal: "The model declined to analyse this image. Try a different image.",
    FailureKind.output_limit: (
        "The map was too detailed for one answer. Try the other pass, or crop the map into parts."
    ),
    FailureKind.pass_limit: "The pass used up its allowance before finishing. Try again.",
    FailureKind.rate_limit: (
        "The AI provider's usage or rate limit was reached. Wait a minute and try again."
    ),
    FailureKind.provider_busy: (
        "The AI provider is having trouble right now. Try again in a few minutes."
    ),
    FailureKind.auth: (
        "The API key was not accepted. The person running the app needs to check the key in "
        "its settings."
    ),
    FailureKind.missing_key: (
        "No API key is set up. The person running the app needs to add one to its settings."
    ),
    FailureKind.network: (
        "Couldn't reach the AI provider. Check the internet connection and try again."
    ),
    FailureKind.timeout: "The pass took too long and was stopped. Try again.",
    FailureKind.unreadable: "The model's answer couldn't be read. Try again.",
    FailureKind.unexpected: "Something went wrong. Try again.",
}


class PassFailure(BaseModel):
    """A pass that ended without a usable answer. `detail` is for the log, never the page."""

    kind: FailureKind
    kind_of_pass: PassKind
    elapsed_s: float = 0.0
    usage: Usage | None = None
    cost_usd: float | None = None
    detail: str = ""


def message(kind: FailureKind, has_earlier_mask: bool = False) -> str:
    """The user-facing text for a failure, with a reminder when the earlier mask is kept."""
    text = MESSAGES[kind]
    return f"{text} {EARLIER_MASK}" if has_earlier_mask else text


class UploadRejected(Exception):
    """An upload that is refused before any model call; carries its message."""

    MESSAGES = {
        "wrong_type": "That file type isn't supported. Upload a PNG, JPEG or WebP image.",
        "too_large": "That file is larger than 20 MB. Upload a smaller image.",
        "not_an_image": "That file couldn't be opened as an image. Try exporting it again.",
    }

    def __init__(self, reason: str, limit_mb: float = 20):
        """`reason` is wrong_type, too_large or not_an_image; `limit_mb` fills the size text."""
        self.reason = reason
        self.message = self.MESSAGES[reason].replace("20 MB", f"{limit_mb:g} MB")
        super().__init__(self.message)


class MapSizeInvalid(Exception):
    """A map width or height outside the allowed range; carries its message."""

    def __init__(self, low: int = 1, high: int = 200):
        """`low` and `high` are the allowed range of each side, in squares."""
        self.message = f"Map width and height must be whole numbers from {low} to {high}."
        super().__init__(self.message)


EMPTY_MASK = "Nothing was found on this map: no walls, doors, windows or lights."
NO_GRID = (
    "No grid was found in the image, so the map size shown was used. Check it and correct it "
    "if needed; that costs nothing."
)
DETECTED = (
    "Detected from the image: {width} x {height} squares, {px:g} px per square. "
    "Check this against the map's grid; correcting it costs nothing."
)


def detected_note(width: int, height: int, image_width: int) -> str:
    """The note for a detected size, with the square size it implies, so a wrong count
    (for example 40 px squares on a 64 px grid) is easy to spot."""
    return DETECTED.format(width=width, height=height, px=round(image_width / width, 1))


NOT_SQUARE = "With this map size the grid squares would not be square. Check the width and height."
