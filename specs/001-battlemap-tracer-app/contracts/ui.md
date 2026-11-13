# Contract: the page

What the user sees and can do. One Gradio page; `app/main.py` only wires these controls to
`app/service.py`.

## Controls

| Control | Content | Enabled when |
| --- | --- | --- |
| Upload | Accepts `.png`, `.jpg`/`.jpeg`, `.webp`, up to 20 MB. Notice beside it: "Your image is sent to Anthropic, a third-party AI provider, for analysis." | Always |
| Map width, map height | Whole numbers 1 to 200, pre-filled 25 and 25 | Always |
| Detect map size from the image | Checkbox, on for every new upload; turns off when the user types a size or a size is detected | Always |
| Map size note | "Detected from the image", "No grid found: check the map size", or the proportions warning | Shown when it applies |
| Suggest walls | Label includes the expected time and cost from the config, e.g. "about 25 s, about $0.10" | An image is loaded and no pass is running |
| Deeper examination | Label includes the expected time and cost from the config, e.g. "about 70 s, about $0.32" | A mask is on screen and no pass is running |
| Deep-pass note | "The fast pass handles ordinary buildings well but often misses cave outlines and doors in castles and other complex structures. The deeper examination fixes most of that." | Always visible |
| Preview | The map with walls, portals and lights drawn over it in three distinct colors, with a legend | Shows the upload alone until a mask exists |
| Progress | "Working… 23 s", updated about once a second | While a pass runs |
| Status line | "Sonnet 5.5 (medium) · 21 s · about $0.08 · 14 walls, 6 portals, 3 lights", then the model's note | After a successful pass |
| Message area | Upload, map-size and failure messages | When there is one |
| File type | `.dd2vtt` or `.uvtt` | Always |
| Accept mask | Downloads the mask on screen | A mask is on screen (also while a pass runs) |

## Messages

Upload and input (no model call is made):

| Case | Message |
| --- | --- |
| Wrong file type | "That file type isn't supported. Upload a PNG, JPEG or WebP image." |
| Over 20 MB | "That file is larger than 20 MB. Upload a smaller image." The server's upload limit (`max_file_size`) refuses such a file first, with Gradio's own wording; it is kept so a huge upload never reaches memory. The app's check stays as the second guard |
| Not a readable image | "That file couldn't be opened as an image. Try exporting it again." |
| Map size out of range | "Map width and height must be whole numbers from 1 to 200." |
| Size does not match the image's proportions | "With this map size the grid squares would not be square. Check the width and height." (warning; does not block) |
| Empty mask | "Nothing was found on this map: no walls, doors, windows or lights." |
| No grid found | "No grid was found in the image, so the map size shown was used. Check it and correct it if needed; that costs nothing." |

Pass failures (`FailureKind` -> message). Each ends with "Your earlier mask is still here."
when one is on screen.

| Kind | Cause | Message |
| --- | --- | --- |
| `refusal` | Stop reason `refusal` | "The model declined to analyse this image. Try a different image." |
| `output_limit` | Stop reason `max_tokens` | "The map was too detailed for one answer. Try the other pass, or crop the map into parts." |
| `pass_limit` | The loop's turn or cost limit, with no answer | "The pass used up its allowance before finishing. Try again." |
| `rate_limit` | `RateLimitError` | "The AI provider's usage or rate limit was reached. Wait a minute and try again." |
| `provider_busy` | Other provider status errors (for example overloaded) | "The AI provider is having trouble right now. Try again in a few minutes." |
| `auth` | `AuthenticationError`, `PermissionDeniedError` | "The API key was not accepted. The person running the app needs to check the key in its settings." |
| `missing_key` | `ANTHROPIC_API_KEY` not set | "No API key is set up. The person running the app needs to add one to its settings." |
| `network` | `APIConnectionError` | "Couldn't reach the AI provider. Check the internet connection and try again." |
| `timeout` | Deadline passed or `APITimeoutError` | "The pass took too long and was stopped. Try again." |
| `unreadable` | Answer failed validation, or none was submitted | "The model's answer couldn't be read. Try again." |
| `unexpected` | Anything else | "Something went wrong. Try again." (details go to the log) |

A failed pass is never shown in the status line as a result with a cost. The status line
keeps showing the last successful pass.

## Behaviour rules

- A new upload clears the image, mask, status and messages, turns the detect option on,
  resets the map size to 25 x 25 and drops the result of any pass still running.
- While a pass runs, both pass buttons are disabled; the mask on screen stays and can be
  accepted.
- Changing the map size with a mask on screen redraws the preview and rebuilds the download
  at once, with no pass.
- No stack trace, raw error or key ever appears on the page.
