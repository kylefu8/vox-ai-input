# Vox AI Input UI Style Guide

## Product Feel

- Compact Windows utility, not a marketing page.
- Quiet, fast, and legible: the app should feel like a small tool that stays out
  of the way until the user records.
- The floating mic is the most visible surface; polish it before adding new
  explanatory UI.
- Settings, tray, floating mic, result preview, and hotkey feedback should feel
  like one product and share the same state model.

## Current UI Surfaces

- Settings and log windows use Tkinter, guarded by `src/tk_runtime.py`.
- Floating mic and result preview use Windows layered windows with per-pixel
  alpha; Tk is only a fallback path.
- Countdown overlay also uses a Windows layered window with Tk fallback.
- Shared theme tokens live in `src/ui_theme.py`; do not add independent dark or
  light palettes inside floating-window modules.

## Visual Rules

- Use restrained graphite surfaces in dark mode and light gray surfaces in light
  mode; avoid pure white for always-on-top floating capsules.
- Use cyan for primary/active states, gold for processing, red for recording or
  destructive actions, and green only for success/ready states.
- Avoid decorative gradients, hero layouts, nested cards, and emoji section
  headers.
- Keep floating controls crisp: draw offscreen at high scale, downsample, and
  preserve per-pixel alpha.
- Rounded floating windows should be native layered windows on Windows; Tk
  `-transparentcolor` is fallback only because it produces rough edges.

## Layout Rules

- Left rail is for major settings areas only.
- Horizontal tabs refine the selected major area.
- Save and Cancel stay fixed at the bottom of the settings window.
- Put frequently changed controls near the top of each tab.
- A settings section should have a short title, optional one-line explanation,
  then controls.
- Do not place UI cards inside other cards.

## Component Rules

- Use icon buttons for repeated tool actions and text buttons for global actions
  such as Save, Cancel, Validate, and Record.
- Tabs should look like compact segmented controls.
- History rows should be scan-friendly list items with metadata, text preview,
  and one copy action.
- Empty states should be concrete and short.
- Theme switching should update existing surfaces in place; color-only changes
  should not destroy and rebuild the whole settings window.

## Floating UI Rules

- Idle state is a small 42px floating circle.
- Hover, recording, processing, and short status messages expand into a capsule.
- Expanded capsules anchor from the idle circle's right edge so returning to idle
  does not jump after dragging.
- The result preview capsule belongs below the mic capsule when an anchor is
  available; otherwise it falls back to the lower screen area.
- The mic capsule handles recording control and immediate state; the result
  preview handles transcript/result text and fallback warnings.
