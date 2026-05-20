# Vox AI Input UI Style Guide

## Product Feel
- Quiet desktop utility, not a marketing page.
- Warm audio-tool feel: focused, compact, and calm, with a little glow only around active/connected states.
- The interface should feel like a small control room: clear groups, low noise, useful status.

## Visual Rules
- Prefer deep graphite surfaces over saturated purple panels.
- Use one bright cyan accent for active navigation, connection status, and primary actions.
- Use green only for success/ready states, yellow for warnings, red for destructive states.
- Avoid decorative gradients, large hero areas, and stacked cards inside cards.
- Avoid emoji section headers; use text hierarchy, spacing, and small status pills.

## Layout Rules
- Left rail is for major areas only.
- Horizontal tabs refine the selected major area.
- Keep Save/Cancel fixed at the bottom.
- Put frequently changed controls near the top of each tab.
- A section should have a title, optional one-line explanation, then controls.

## Component Rules
- Navigation: slim rail items with a subtle active fill, not chunky buttons.
- Tabs: segmented controls, compact and horizontally aligned.
- Cards/sections: flat graphite panels with thin border, not large floating cards.
- History rows: timeline-like list items with metadata, text preview, and one copy action.
- Empty states should be quiet and concrete, not explanatory paragraphs.

## Tkinter Constraints
- Use stable dimensions and conservative typography.
- Simulate borders with `highlightthickness=1` and `highlightbackground`.
- Avoid relying on rounded corners unless switching GUI framework.
- Keep text labels short because Tkinter wrapping is not elegant.
