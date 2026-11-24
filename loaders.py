"""Load LRC recordings using the bundled Windows x64 LRCRecording.dll.

Adapted from Python/LRC_loading.py (2023) by Lukáš Mužika (LukasM).
Upstream: https://github.com/labirthermal/lrc-recording/tree/v2.1
Library release DOI: https://doi.org/10.5281/zenodo.24165802
Copyright (c) University of West Bohemia 2026. MIT License; see LICENSE.
"""

import ctypes
import os
import sys
import warnings

import numpy as np


def load_lrc(file_path: str):
    """
    Load LRC thermography recording via LRCRecording.dll

    Parameters
    ----------
    file_path : str or os.PathLike
        Absolute or relative path to the .lrc file

    Returns
    -------
    frames : np.ndarray
        3D recorded-value cube (H, W, T); units are not returned by this API
    time_axes : np.ndarray
        Float64 time vector in seconds.

    Notes
    -----
    Requires Windows x64 and a 64-bit Python interpreter. The entire recording
    is loaded into memory. Values are decoded by the DLL; this Python layer
    does not assume degrees Celsius or apply additional unit conversion or
    radiometric correction. LRC v2 defines stream-unit codes, but the C wrapper
    used here does not expose that code. Confirm units from recording/camera
    metadata rather than inferring them from numeric values.
    C signatures follow LRCRecording/LRCRecordingWrapper.h in upstream v2.1;
    the file format is documented in docs/LRC-FORMAT.md in that repository.
    Concurrent or nested calls are not supported because the DLL uses a
    process-wide recording interface.
    """
    file_path = os.path.abspath(os.fspath(file_path))
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"LRC file not found: {file_path}")
    if sys.platform != "win32" or ctypes.sizeof(ctypes.c_void_p) != 8:
        raise RuntimeError("LRCRecording.dll requires Windows x64 and 64-bit Python")

    # Find the DLL next to this module, independently of the working directory.
    script_directory = os.path.dirname(os.path.abspath(__file__))
    dll_path = os.path.join(script_directory, "LRCRecording.dll")
    if not os.path.isfile(dll_path):
        raise FileNotFoundError(f"LRC DLL not found: {dll_path}")

    # Load DLL
    try:
        LRC_lib = ctypes.CDLL(dll_path)
    except OSError as exc:
        raise RuntimeError(
            f"Failed to load DLL: {dll_path}. Check the Microsoft Visual C++ "
            "x64 runtime dependencies."
        ) from exc

    # C API signatures: upstream v2.1 LRCRecording/LRCRecordingWrapper.h.
    LRC_lib.Open.argtypes = [ctypes.c_char_p]
    LRC_lib.Open.restype = ctypes.c_int
    LRC_lib.Close.argtypes = []
    LRC_lib.Close.restype = None
    for name in ("GetFrameCount", "GetWidth", "GetHeight"):
        function = getattr(LRC_lib, name)
        function.argtypes = []
        function.restype = ctypes.c_int
    LRC_lib.GetTemperatureData.argtypes = []
    LRC_lib.GetTemperatureData.restype = ctypes.POINTER(ctypes.c_float)
    LRC_lib.GetTimeFromBeginning.argtypes = []
    LRC_lib.GetTimeFromBeginning.restype = ctypes.c_uint64
    LRC_lib.NextFrame.argtypes = []
    LRC_lib.NextFrame.restype = None

    # Encode file path as bytes for ctypes
    file_path_bytes = os.path.abspath(file_path).encode("utf-8")

    # Open file
    if LRC_lib.Open(ctypes.c_char_p(file_path_bytes)) != 0:
        LRC_lib.Close()
        raise RuntimeError(f"Failed to open LRC file: {file_path}")

    try:
        frame_count = LRC_lib.GetFrameCount()
        width = LRC_lib.GetWidth()
        height = LRC_lib.GetHeight()
        if frame_count <= 0 or width <= 0 or height <= 0:
            raise ValueError(
                f"Invalid LRC dimensions or frame count: {width} x {height}, "
                f"{frame_count} frames"
            )

        frames = np.empty((height, width, frame_count), dtype=np.float32)
        time_axes = np.empty(frame_count, dtype=np.float64)
        # The documented buffer is acquired once and updated by NextFrame().
        pointer_to_frame = LRC_lib.GetTemperatureData()
        if not pointer_to_frame:
            raise RuntimeError("No temperature data for the first frame")
        frame = np.ctypeslib.as_array(pointer_to_frame, shape=(height, width))

        for frame_idx in range(frame_count):
            # Copy the shared DLL buffer before it is updated for the next frame.
            frames[:, :, frame_idx] = frame
            time_axes[frame_idx] = LRC_lib.GetTimeFromBeginning() / 1000.0
            if frame_idx + 1 < frame_count:
                LRC_lib.NextFrame()
    finally:
        LRC_lib.Close()

    # Derive timing information from the timestamps returned by the recording.
    positive_intervals = np.diff(time_axes)
    if np.any(positive_intervals <= 0):
        warnings.warn(
            "Recording timestamps are not strictly increasing; the frame-rate "
            "estimate uses only positive intervals.",
            RuntimeWarning,
            stacklevel=2,
        )
    positive_intervals = positive_intervals[positive_intervals > 0]
    frame_interval = float(np.median(positive_intervals)) if positive_intervals.size else None
    sampling_frequency = 1.0 / frame_interval if frame_interval else None
    recorded_time_span = float(time_axes[-1] - time_axes[0]) if frame_count > 1 else 0.0

    # Print a compact metadata report without changing the function's return values.
    absolute_file_path = os.path.abspath(file_path)
    file_size_bytes = os.path.getsize(absolute_file_path)
    print("LRC recording metadata")
    print("----------------------")
    print(f"File name:           {os.path.basename(absolute_file_path)}")
    print(f"File path:           {absolute_file_path}")
    print(f"File size:           {file_size_bytes / (1024 ** 2):.3f} MiB ({file_size_bytes:,} bytes)")
    print(f"Resolution:          {width} x {height} pixels (width x height)")
    print(f"Number of frames:    {frame_count}")
    print(f"Array shape:         {frames.shape} (height, width, frames)")
    print(f"Data type:           {frames.dtype}")
    if frame_interval is not None:
        print(f"Frame interval:      {frame_interval * 1000:.3f} ms")
        print(f"Sampling frequency:  {sampling_frequency:.3f} Hz")
    else:
        print("Frame interval:      unavailable")
        print("Sampling frequency:  unavailable")
    print(f"Recorded time span:  {recorded_time_span:.6f} s")
    print(
        f"Temperature range:   {np.min(frames):.3f} to {np.max(frames):.3f} "
        "(stream unit not exposed by the DLL C API)"
    )

    return frames, time_axes
