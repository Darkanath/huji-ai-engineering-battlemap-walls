# Contract: the downloaded file

One JSON file in the Universal VTT format. `.dd2vtt` and `.uvtt` hold the same bytes; only
the name differs. The file name is the uploaded image's base name plus the chosen extension.

## Shape

```json
{
  "format": 0.3,
  "resolution": {
    "map_origin": {"x": 0, "y": 0},
    "map_size": {"x": 25, "y": 25},
    "pixels_per_grid": 70
  },
  "line_of_sight": [[{"x": 3.0, "y": 3.0}, {"x": 23.0, "y": 3.0}]],
  "objects_line_of_sight": [],
  "portals": [
    {
      "position": {"x": 5.5, "y": 7.0},
      "bounds": [{"x": 5.0, "y": 7.0}, {"x": 6.0, "y": 7.0}],
      "rotation": 0.0,
      "closed": true,
      "freestanding": false
    }
  ],
  "lights": [
    {
      "position": {"x": 11.0, "y": 18.5},
      "range": 16.0,
      "intensity": 1.0,
      "color": "ffeccd8b",
      "shadows": true
    }
  ],
  "environment": {"baked_lighting": true, "ambient_light": "ffffffff"},
  "image": "<base64 JPEG>"
}
```

## Rules

| Field | Rule |
| --- | --- |
| `resolution.map_size` | The map size on screen at the moment of accepting |
| `resolution.pixels_per_grid` | Always 70 |
| Coordinates | Grid squares, origin top-left, y down: `x = fx * map_width`, `y = fy * map_height`, from the stored image fractions |
| `line_of_sight` | One polyline per wall, at least 2 points each; curves are polylines with a point about every 5 degrees |
| `portals` | One entry per door or window. `bounds` are its two ends, `position` their midpoint, `rotation` the segment's angle in radians. No door/window type. `closed` true, `freestanding` false |
| `lights` | One entry per light. `range` and `intensity` come from the tier table in the config, never from the image |
| `image` | The upload resized to exactly `map_width * 70` by `map_height * 70` px, JPEG quality 90, base64 |
| `objects_line_of_sight` | Always empty |

## What a test checks

- The file loads with `data.rasterize.load_uvtt`.
- `pixels_per_grid` is 70, `map_size` is the size given, and the decoded image is
  `map_size * 70` px on each side.
- A wall at fractions (0.2, 0.4)–(0.6, 0.4) on a 20 x 10 map comes out at (4, 4)–(12, 4);
  on a 40 x 20 map at (8, 8)–(24, 8).
- Each tier writes the `range` and `intensity` from the table.
- `.dd2vtt` and `.uvtt` exports of the same session are byte-identical.
- Golden file: a fixture result and image give the committed expected JSON (the `image`
  field compared by decoded size, since JPEG bytes can vary between library versions).
- An empty mask writes a valid file with empty lists.

## Roll20

Imported with Page Menu -> Upload Background. Roll20 places the image at native scale
(70 px per square), turns `line_of_sight` into walls, every portal into a door, and each
light into a light with its `range`. Checked by hand; it is the owner's step in
[../quickstart.md](../quickstart.md).
