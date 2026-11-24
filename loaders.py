"""Load LRC recordings using the bundled Windows x64 LRCRecording.dll."""

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
        3D thermography cube (H, W, T)
    time_axes : np.ndarray
        Float64 time vector in seconds.

    Notes
    -----
    Requires Windows x64 and a 64-bit Python interpreter. The entire recording
    is loaded into memory. Temperature units and calibration are provided by
    the DLL and are not independently verified here.
    The DLL API is undocumented; calls retain the established conventions.
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

    # Encode file path as bytes for ctypes
    file_path_bytes = os.path.abspath(file_path).encode("utf-8")

    # Open file
    if LRC_lib.Open(ctypes.c_char_p(file_path_bytes)) != 0:
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
        LRC_lib.GetTemperatureData.restype = ctypes.POINTER(ctypes.c_float)

        for frame_idx in range(frame_count):
            pointer_to_frame = LRC_lib.GetTemperatureData()
            if not pointer_to_frame:
                raise RuntimeError(f"No temperature data for frame {frame_idx}")
            frame = np.ctypeslib.as_array(pointer_to_frame, shape=(height, width))
            # Assignment copies the DLL buffer before advancing to the next frame.
            frames[:, :, frame_idx] = frame
            time_axes[frame_idx] = LRC_lib.GetTimeFromBeginning() / 1000.0
            # Preserve the established API convention; its status is undocumented.
            LRC_lib.NextFrame()
    finally:
        LRC_lib.Close(ctypes.c_char_p(file_path_bytes))

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
        "(unit not reported by the LRC interface)"
    )

    return frames, time_axes
