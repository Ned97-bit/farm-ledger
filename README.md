# Farm Ledger 🌾

**Guided tax filing, locally, with memory.**

A macOS workspace that organizes your tax documents year after year — flags what's missing, cleans up filenames, remembers your whole history, and outputs one clean package for your CPA or for filing it yourself.

*A personal project by **Nigel Edward**.*

![Farm Ledger — three-pane UI](docs/screenshots/01-hero.png)

---

## What it does

- 📥 **Drop docs, AI organizes them** — Claude classifies every document (W-2, 1099-B, 1098-E, …), renames it with a consistent convention, and files it into the right year folder.
- 🎯 **Know what's missing** — a personalized quest list per year flags the docs you haven't uploaded yet, one per employer, one per brokerage, one per benefit.
- 🔄 **Cross-year memory** — wash-sale disallowed losses, capital-loss carryforwards, prior-year AGI, last year's filing status — all travel with you instead of being re-entered every April.
- 🧙 **Four AI personas, four jobs** — Merlin routes your ask, Gandalf reasons about your tax profile, Morgana drills into open questions, the Ancient One reviews the full package like a senior CPA.
- 📊 **Cross-year analytics** — AGI, tax liability, tax paid, refund, investment net gain/loss, trended across every year you've tracked.
- 📦 **One package, your choice** — ship a clean dated ZIP to your CPA, or use it as the source of truth for filing it yourself.
- 🔒 **Local-only, no cloud** — the app binds to `127.0.0.1`. Your SSN, income, and account numbers never leave your machine.
- 🎨 **Stardew-inspired UI** — because tax software shouldn't be soul-sucking.

## Screenshots

### Drop a doc, Claude classifies it and proposes everything it'll change

![Shipping Bin mid-classification](docs/screenshots/02-shipping-bin.png)

### Three year-types with different behaviors — past years aren't nagged for "missing" docs

![Year-type picker](docs/screenshots/03-year-types.png)

### A Claude Code terminal inside the UI, with four specialist personas

![Wizard's Tower with Merlin / Gandalf / Morgana tabs](docs/screenshots/04-wizards-tower.png)

## Get started

1. `git clone` this repo
2. `brew bundle` from the repo root (installs python, node, ttyd)
3. `npm install -g @anthropic-ai/claude-code` then `claude` (one-time sign-in)
4. Double-click **`Launch Taxes.command`** — the UI opens at `http://127.0.0.1:5173`

Full instructions in [First run](#first-run) below.

---

## Why I built this

Tax tools today are built for one of two people:

- **Filers who DIY in TurboTax** — a wizard that funnels you to e-filing, not to understanding your situation.
- **Accountants with pro software** — for batch client management, not a single filer.

**The person who works _with_ a CPA, or wants to DIY properly, has no tool at all.** They end up in a loop of PDF exports, Dropbox links, and "Re: Re: Re: tax follow-up" email threads. Every year starts from scratch. Every question lives in a different place.

Farm Ledger is built for that gap: the handoff workspace. Its end goal is never a specific filing path — it's a **clean, organized, auditable, cross-year package** that you, your CPA, or any future tax software can open and use.

## Design decisions (and the tradeoffs)

A few choices worth calling out, because they're not the obvious defaults:

### 1. Markdown files as the database

There is no SQLite, no JSON blob, no server-side schema. Every fact about your tax life lives in a plain `.md` file you can open in any editor.

- **Why**: Longevity (readable in 20 years), transparency (no black-box state), delegation-friendly (an AI agent reads and edits markdown the same way a human does).
- **The tradeoff**: No queries, no joins. Fine for a single-user workspace with dozens of files; wrong for multi-tenant SaaS.

### 2. Local-only, no cloud sync

The app binds to `127.0.0.1`. No server, no account, no upload path.

- **Why**: Tax documents contain SSNs, income history, and bank account numbers. "Trust us, it's encrypted" is the wrong pitch for that data.
- **The tradeoff**: No cross-device access. Sync via encrypted iCloud Drive or USB if you need it.

### 3. AI as interface, not as source of truth

Claude reads your files, proposes changes, and drafts the next edit — but every write goes through a confirmation modal or a slash command the user invokes. The AI never silently commits a number to your profile.

- **Why**: Tax documents are legal records. An AI that "helpfully" decides your filing status is a liability, not a feature.
- **The tradeoff**: More clicks than a fully autonomous workflow. Acceptable, because the cost of a wrong number is real money.

### 4. Years as first-class, not tabs

Each tax year is its own folder — its own profile, documents, open questions. Facts from year N do **not** auto-propagate to year N+1.

- **Why**: Marital status, state of residency, employer, dependents all shift. A tool that silently carries last year's answer forward will produce quietly wrong filings.
- **The tradeoff**: Some duplication. Worth it.

### 5. Three year-types with different behaviors

`past` / `current` / `future` each get a different template, a different quest checklist, and different AI prompts.

- **Why**: A past year exists to answer questions ("how much did I contribute to the HSA in 2023?") — it shouldn't nag you for missing docs. A future year is about quarterly estimates, not W-2s. Treating every year identically means treating none of them well.

### 6. Four specialist personas, not one generalist assistant

Merlin (the default) routes asks; Gandalf owns the Tax Profile; Morgana reconciles Open Questions; the Ancient One runs a senior-partner review.

- **Why**: A single "do-everything" AI blurs the line between brainstorming (cheap), data entry (needs confirmation), and review (needs full context). Separating them by job lets each one have the right guardrails, prompts, and scope.
- **The tradeoff**: More complexity up front. Users have to learn the roster. The payoff is that no single persona ever does something outside its lane.

## Roadmap

Rough priorities, not commitments:

- **90-second demo GIF** — higher-leverage than any more text.
- **Fictional-persona demo mode** — so a reviewer can clone the repo and see a populated workspace without their own tax docs.
- **Windows / Linux launcher parity** — currently Mac-only.
- **Cross-year delta view** — "what changed between 2024 and 2025" as a first-class screen.
- **Two-way CPA channel** — export format the CPA can annotate and send back, closing the loop.

---

## Requirements

- **macOS** (the `.app` bundle + LaunchServices integration are Mac-specific)
- **Homebrew** for the three runtime dependencies

## First run

1. Clone this repo anywhere on disk.
2. **Install system dependencies** — from the repo root:
   ```
   brew bundle
   ```
   Installs `python@3.12`, `node`, and `ttyd`.
3. **Install the Claude Code CLI** (published on npm):
   ```
   npm install -g @anthropic-ai/claude-code
   ```
4. **Authenticate the Claude CLI** (one-time):
   ```
   claude
   ```
   The Wizard's Tower pane and the document classifier both call this CLI — they won't work until it's authenticated.
5. **Launch the app** — preferred: double-click **`Launch Taxes.command`**. Terminal flashes briefly and closes on its own.
   - Alternative: double-click **`Farm Ledger.app`**. On first launch macOS Gatekeeper will refuse to open it because the bundle isn't notarized; **right-click → Open → Open** in the confirmation dialog, once.
6. The browser opens to `http://127.0.0.1:5173` and a welcome wizard runs — asks for your name, filing status, residency, dependents, and creates your first year folder.
7. Start dropping documents into the Shipping Bin and/or chatting with Claude in the Wizard's Tower pane.

Delete any markdown file and the app regenerates it from templates on next launch.

## What lives where

```
Farm Ledger/                  App code (Flask + static assets).
  app.py
  checklist.py                ← Edit to customize which documents your checklist expects.
  CLAUDE.md.template          Master copy restored if root CLAUDE.md is removed.
  static/ templates/
  requirements.txt
  YearData/                   All user data (gitignored). Created on first launch.
    MDDocs/
      Profile.md              Cross-year identity.
      Analytics.md            Auto-generated cross-year dashboard.
    <YEAR>/                   One folder per filing year.
      Profile.md, Files.md, OpenQuestions.md, _meta.json, input/

CLAUDE.md                     Instructions the Wizard's Tower Claude reads.
.claude/commands/*.md         Slash commands available in the Wizard's Tower.
Farm Ledger.app               Double-clickable launcher.
Launch Taxes.command          Fallback terminal launcher.
```

## Configuration

- `FARM_LEDGER_DATA_ROOT` — override the data directory. Defaults to `Farm Ledger/YearData/`. Useful for Docker volume mounts, encrypted disks, or test fixtures.

## Customizing the checklist

`Farm Ledger/checklist.py` ships with generic slots (W-2, 1099-B, 1098-E, etc.). Edit it to match your actual employers, brokerages, and benefits — the filenames you drop in will match slot names automatically.

## Privacy

- **Your tax documents never leave your machine.** The app binds to `127.0.0.1` only; `input/` files are read, classified, and renamed entirely on your local filesystem.
- **Document classification is done by the Claude CLI you're already signed into** — no separate API key is stored, no third-party service sees your documents beyond what Anthropic normally receives when you use Claude Code.
- **The UI is fully self-contained.** All assets — fonts, icons, styles — are served from the local Flask server. No CDN calls, no analytics, no telemetry.
- **The only outbound network traffic** comes from the `claude` CLI (model inference against Anthropic's API, authenticated as you) and from Homebrew when installing dependencies.

## Acknowledgements

- UI typefaces: [Press Start 2P](https://fonts.google.com/specimen/Press+Start+2P) and [VT323](https://fonts.google.com/specimen/VT323), SIL Open Font License.
- Visual inspiration: Stardew Valley by ConcernedApe.
- Built with Claude Code.

## License

MIT © 2026 Nigel Edward. See [`LICENSE`](LICENSE).

---

Built by **Nigel Edward**.
