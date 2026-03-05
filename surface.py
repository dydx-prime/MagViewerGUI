# surface.py

import numpy as np


def generate_snail_positions(rows, cols):
    positions = []
    left, right = 0, cols - 1
    top, bottom = 0, rows - 1

    while left <= right and top <= bottom:

        for r in range(bottom, top - 1, -1):
            positions.append((r, left))
        left += 1

        for c in range(left, right + 1):
            positions.append((top, c))
        top += 1

        if left <= right:
            for r in range(top, bottom + 1):
                positions.append((r, right))
            right -= 1

        if top <= bottom:
            for c in range(right, left - 1, -1):
                positions.append((bottom, c))
            bottom -= 1

    return positions


def build_full_surface(blocks, grid_rows, grid_cols):
    if not blocks:
        return None

    block_size = blocks[0].shape[0]

    full = np.full((grid_rows * block_size,
                    grid_cols * block_size), np.nan)

    positions = generate_snail_positions(grid_rows, grid_cols)

    for idx, block in enumerate(blocks):
        if idx >= len(positions):
            break

        r, c = positions[idx]
        sr = r * block_size
        sc = c * block_size

        full[sr:sr + block_size,
             sc:sc + block_size] = block

    return full