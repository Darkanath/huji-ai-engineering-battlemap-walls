# Reference maps

Four labeled maps used to score the tracer (`python -m llm.run --reference`). Each is one of
the project owner's own Dungeondraft exports, copied from `data/raw/dungeondraft/`, so they
may be committed. Labels come only from these `.dd2vtt` files: the walls, portals and lights
in each file are the ground truth, and the image embedded in it is the map the model sees.

| File | Map | Role |
| --- | --- | --- |
| `dd04_a.dd2vtt` | Tavern | An ordinary building |
| `dd06_a.dd2vtt` | Mine | A cave: irregular rock walls |
| `dd07_a.dd2vtt` | Castle keep | A complex structure with many doors and curved walls |
| `dd04_d.dd2vtt` | Tavern, exported with no grid | The "no grid found" case for map-size detection |

Thresholds for each map are in `specs/001-battlemap-tracer-app/quickstart.md` section 4.
