import numpy as np
from scipy import ndimage


def threshold_anomaly(data, sensitivity=2.0):
    """
    Flags tiles that deviate beyond `sensitivity` standard deviations
    from the mean. Returns a boolean mask of anomalous tiles.
    """
    mean = np.mean(data)
    std = np.std(data)
    if std == 0:
        return np.zeros_like(data, dtype=bool)
    return np.abs(data - mean) > sensitivity * std


def gradient_edge(data, threshold=0.3):
    """
    Computes the spatial gradient magnitude across the grid.
    Returns a float mask (0.0–1.0) normalized gradient strength.
    Tiles above `threshold` indicate sharp field transitions.
    """
    gy, gx = np.gradient(data)
    magnitude = np.sqrt(gx**2 + gy**2)
    max_val = magnitude.max()
    if max_val == 0:
        return np.zeros_like(data, dtype=float)
    normalized = magnitude / max_val
    return normalized > threshold


def local_variance(data, threshold=0.3):
    """
    Highlights regions where neighboring tiles have high local variance.
    Uses a 3x3 neighborhood. Returns a boolean mask.
    """
    mean_local = ndimage.uniform_filter(data, size=3)
    mean_sq_local = ndimage.uniform_filter(data**2, size=3)
    variance = mean_sq_local - mean_local**2
    max_var = variance.max()
    if max_var == 0:
        return np.zeros_like(data, dtype=bool)
    normalized = variance / max_var
    return normalized > threshold


def blob_detection(data, sensitivity=2.0, min_size=2):
    """
    Identifies contiguous regions of abnormal field strength using
    connected-component labeling. Returns a labeled integer mask
    where each unique nonzero value is a distinct blob.
    """
    mean = np.mean(data)
    std = np.std(data)
    if std == 0:
        return np.zeros_like(data, dtype=int)
    anomaly_mask = np.abs(data - mean) > sensitivity * std
    labeled, num_features = ndimage.label(anomaly_mask)
    # Remove blobs smaller than min_size
    for label_id in range(1, num_features + 1):
        if np.sum(labeled == label_id) < min_size:
            labeled[labeled == label_id] = 0
    return labeled


def zscore_spatial(data, neighborhood=3, threshold=2.0):
    """
    Computes a rolling z-score across local neighborhoods.
    Suppresses background noise while surfacing localized defects.
    Returns a boolean mask of detected defects.
    """
    local_mean = ndimage.uniform_filter(data, size=neighborhood)
    local_mean_sq = ndimage.uniform_filter(data**2, size=neighborhood)
    local_std = np.sqrt(np.maximum(local_mean_sq - local_mean**2, 0))
    with np.errstate(divide='ignore', invalid='ignore'):
        z = np.where(local_std > 0, np.abs(data - local_mean) / local_std, 0)
    return z > threshold


# Registry: name -> (function, param_label, param_min, param_max, param_default)
ALGORITHMS = {
    "Threshold Anomaly":   (threshold_anomaly,  "Sensitivity (σ)", 0.5, 5.0, 2.0),
    "Gradient Edge":       (gradient_edge,       "Threshold",       0.1, 1.0, 0.3),
    "Local Variance":      (local_variance,      "Threshold",       0.1, 1.0, 0.3),
    "Blob Detection":      (blob_detection,      "Sensitivity (σ)", 0.5, 5.0, 2.0),
    "Z-Score Spatial":     (zscore_spatial,      "Threshold (σ)",   0.5, 5.0, 2.0),
}