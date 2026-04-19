# Screenshots

The README embeds four images from this folder. Capture them in this order for minimum friction:

| # | Filename | What to capture | State needed |
|---|---|---|---|
| 1 | `01-hero.png` | Full app window, all three panes visible at once | Empty or lightly populated — goal is to show structure |
| 2 | `02-shipping-bin.png` | Shipping Bin pane, ideally mid-classification modal | Empty drop zone OR staged approval modal |
| 3 | `03-year-types.png` | "+ New Year" wizard showing past / current / future picker | Fresh wizard, no data |
| 4 | `04-wizards-tower.png` | Wizard's Tower terminal with a short staged conversation | Type a generic question; screenshot the answer |

## Capture notes

- **Use CleanShot X or Shottr** — both have irreversible blur if you need it.
- **Resize to 1600–2000px wide** after capture. Anything bigger bloats the repo; anything smaller looks fuzzy on GitHub.
- **PNG, not JPEG** — screenshots compress poorly as JPEG and look muddy.
- **Aim for <500KB per shot.** If one is over 1MB, run it through [ImageOptim](https://imageoptim.com/).

## What must NOT appear in any shot

- Real dollar amounts
- Your real name in Profile.md
- Any real issuer/employer/brokerage name
- Any real filename (W-2s with "Acme Corp (2024).pdf" etc.)
- Account numbers, SSN fragments, addresses

If any of the above slips in, pixelate with CleanShot's redact tool **before** saving.

## Optional fifth shot

`05-profile.png` — a `Profile.md` fresh from the template, full of `TBD` placeholders. Useful to show the "markdown as database" philosophy in concrete form. Not wired into the README yet; add a reference if you capture it.

## Optional GIF

A 30–60 second Kap recording of the full happy path (drop document → modal → approve → quest check → ship to CPA) belongs at the top of the README. If you capture one, save as `docs/screenshots/00-demo.gif`, target <8MB, and swap it in for `01-hero.png` at the top of README.md.
