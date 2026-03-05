# mapper.py

import numpy as np
from PyQt6.QtGui import QColor
from config import MIN_FIELD, MAX_FIELD


def map_to_millitesla(adc_values):
    adjusted = np.clip(adc_values - 50, 0, 1650)

    lower = adjusted < 600
    middle = (adjusted >= 600) & (adjusted <= 850)
    upper = adjusted > 850

    result = np.zeros_like(adjusted, dtype=float)

    result[lower] = -45 - (adjusted[lower] / 600) * 45
    result[middle] = -90
    result[upper] = -90 - ((adjusted[upper] - 850) / (1650 - 850)) * 45

    return result


def value_to_color(value):
    clamped = np.clip(value, MIN_FIELD, MAX_FIELD)
    ratio = (MAX_FIELD - clamped) / (MAX_FIELD - MIN_FIELD)
    hue = int((1 - ratio) * 240)
    return QColor.fromHsv(hue, 255, 255)