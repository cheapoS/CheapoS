# MarkdownDeck

MarkdownDeck is a lightweight, zero‑dependency tool for turning a plain Markdown file into a single‑file HTML slide deck.  It is useful for quick presentations, demos or documentation that can be shared as a single file.

## Features

* **Slide separator** – `---` splits the document into individual slides.
* **Presenter notes** – Comments in the form `<!-- note: ... -->` are extracted and shown in the notes pane.
* **Keyboard navigation** – Left/Right arrow keys, Space, Home/End jump between slides.
* **Fullscreen toggle** – Press `F` to enter/exit fullscreen mode.
* **Theme toggle** – Press `T` to switch between light and dark themes.

All resources (CSS & JavaScript) are embedded inline, so the output file is self‑contained.

## Usage

The command line interface offers three sub‑commands:

```bash
# Build a deck from a Markdown file
markdown-deck build <source.md> [output.html]

# Alias that writes the output next to the source
markdown-deck export <source.md>

# Serve a directory that contains deck files
markdown-deck serve [directory] [--port PORT]
```

If `output.html` is omitted the file will be written as `index.html` in the current working directory.

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| Left / Right arrows | Previous / next slide |
| Space | Next slide |
| Home | First slide |
| End | Last slide |
| F | Toggle fullscreen |
| T | Toggle theme (light/dark) |

## Example

```bash
# Create the deck
markdown-deck build examples/markdown-deck/sample.md

# Serve it locally
markdown-deck serve
```

Open `http://localhost:8000/index.html` (or the filename you chose) in a browser.

---

Happy presenting!
