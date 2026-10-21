"""Synthetic battlemap generator internals.

The generator works in three steps, one module each:

- `layout`: rooms and corridors on the square grid, walls on the grid lines, and the openings
  in them (doors, windows, doorless gaps).
- `dress`: furniture, light sources and unlit fixtures placed on the layout's cells.
- `render`: the map image, from procedural textures and drawn sprites, plus image effects.

`data/generator.py` ties them together and writes one .dd2vtt per map.
"""
