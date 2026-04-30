Position audio cue folders
==========================

Put one or more prerecorded audio files inside the matching state folder.
The backend plays the first audio file alphabetically when the detected
person enters a `mid_*` or `near_*` state. `far_*` states are kept for the
complete nine-state naming scheme, but they do not trigger playback.

State folders:

- `far_left`
- `far_center`
- `far_right`
- `mid_left`
- `mid_center`
- `mid_right`
- `near_left`
- `near_center`
- `near_right`

Supported file extensions are `.wav`, `.mp3`, `.m4a`, and `.ogg`.
On Windows, the built-in playback backend supports `.wav` files.
