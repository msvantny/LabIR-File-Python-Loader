"""Simple interactive viewer for LRC thermography arrays."""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider


def show_sequence_slider(cube, time_axes=None, cmap="inferno"):
    """
    Display a thermography sequence with an interactive slider.

    Parameters
    ----------
    cube : np.ndarray
        3D array of thermograms (H, W, T)
    time_axes : np.ndarray, optional
        Time of each frame in seconds. If provided, it is shown in the title.
    cmap : str, optional
        Colormap to use (default is "inferno")

    Returns
    -------
    matplotlib.figure.Figure
        Figure containing the image and slider. Requires an interactive backend.
    """
    if not isinstance(cube, np.ndarray) or cube.ndim != 3:
        raise ValueError("cube must be a NumPy array with shape (height, width, frames)")
    if any(size == 0 for size in cube.shape):
        raise ValueError("cube must contain at least one non-empty frame")
    H, W, T = cube.shape

    if time_axes is not None:
        time_axes = np.asarray(time_axes)
        if time_axes.ndim != 1 or time_axes.size != T:
            raise ValueError("time_axes must contain one value for each frame")

    fig, ax = plt.subplots()
    plt.subplots_adjust(bottom=0.25)

    # Scale the colors to the minimum and maximum of the currently visible frame.
    first_frame = cube[:, :, 0]
    img = ax.imshow(
        first_frame,
        cmap=cmap,
        vmin=np.nanmin(first_frame),
        vmax=np.nanmax(first_frame),
    )
    cbar = plt.colorbar(img, ax=ax)
    cbar.set_label("Temperature value\n(dynamic min-max scale)")

    def frame_title(frame_index):
        title = f"Frame {frame_index + 1} of {T}"
        if time_axes is not None:
            title += f" | time {time_axes[frame_index]:.4f} s"
        return title

    ax.set_title(frame_title(0))
    ax.axis("off")

    # A single-frame recording uses a disabled slider with a non-zero range.
    ax_slider = plt.axes([0.2, 0.1, 0.6, 0.03])
    slider = Slider(
        ax=ax_slider,
        label="Frame index",
        valmin=0,
        valmax=max(1, T - 1),
        valinit=0,
        valstep=1
    )

    def update(val):
        t = int(slider.val)
        current_frame = cube[:, :, t]
        img.set_data(current_frame)
        img.set_clim(np.nanmin(current_frame), np.nanmax(current_frame))
        ax.set_title(frame_title(t))
        fig.canvas.draw_idle()

    if T > 1:
        slider.on_changed(update)
    else:
        slider.set_active(False)

    # Store the widget on the figure so it remains active after this function returns.
    fig._frame_slider = slider

    plt.show()
    return fig
