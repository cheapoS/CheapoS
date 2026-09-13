# The CheapoS presentation kit

[← Project README](../../README.md)

**Relay** is the repository's visual theme: graphite surfaces, mint for implementation, lavender for review, amber for the final human decision. It extends the app's existing [Relay icon](../../dist/brand-icon.svg), whose opposing brackets pass a square of work between them.

The front page tells one story: **promise → product → capabilities → workflow → quick start → evidence → origin → contribution**. Keep the quick start short and move operational detail into the [user guide](../USER_GUIDE.md).

## Files you can change

| File | Purpose |
| --- | --- |
| [theme.json](theme.json) | Shared palette, display name, hero copy, and workflow copy |
| [templates/hero.svg](templates/hero.svg) | The cover layout and worker/reviewer Relay graphic |
| [templates/workflow.svg](templates/workflow.svg) | The five-stage workflow strip |
| [../../scripts/render_readme_assets.py](../../scripts/render_readme_assets.py) | Dependency-free SVG renderer and freshness check |
| [../assets/](../assets/) | Checked-in SVGs and genuine app screenshots displayed by GitHub |
| [../../README.md](../../README.md) | Accessible text, navigation, feature cards, evidence, and calls to action |
| [../../scripts/readme_demo.py](../../scripts/readme_demo.py) | Disposable scripted app session for screenshot refreshes |

All repository links and asset paths are relative. Renaming the local project folder does not break this kit. If the **GitHub repository** is renamed later, update the clone command and GitHub issue URL in the README and user guide as well. Keep the display name **CheapoS**; Python imports and storage identifiers remain `cheapos`.

## Change the theme or headline

Edit `tokens` in [theme.json](theme.json), then run these commands from the repository root:

```sh
python3 -B scripts/render_readme_assets.py
python3 -B scripts/render_readme_assets.py --check
```

The renderer substitutes XML-escaped tokens into every SVG in `templates/`, validates the XML, and writes the matching filename into `docs/assets/`. It resolves paths from its own location, so it also works from another working directory. The Relay mark is derived from the current app icon's paths.

Edit the templates, not the generated SVGs. Keep the headline lines short (about 20 characters each at the current type size). Template geometry does not auto-wrap text: visually inspect every copy change. Update the README's image alt text when the meaning changes.

| Token | Default | Use |
| --- | --- | --- |
| `background` | `#111816` | Main graphite surface |
| `surface` | `#1B2420` | Raised panels |
| `foreground` | `#F1F5EF` | Main text |
| `muted` | `#B3C4B8` | Supporting text |
| `mint` | `#A1DFBE` | Worker, checks, primary emphasis |
| `lavender` | `#C2B2E7` | Reviewer and revision return |
| `amber` | `#E7C38D` | Human decision |
| `border` | `#35463E` | Rules and connectors |

Typography uses system sans-serif fallbacks. Assets are self-contained: no downloaded fonts, external images, scripts, or animation. Opaque backgrounds preserve their contrast in both GitHub themes. The graphics repeat information available as selectable README text; they are not the only way to understand the product.

## Add a capability

Keep the first six cards focused on the strongest outcomes. Add a smaller capability to the expandable “Explore the full feature set” list, or copy a pair of table cells for a major new feature:

```html
<tr>
<td width="50%" valign="top">
<h3>07 · A concrete user outcome</h3>
<p>Explain the working behavior in two short sentences. Describe what the user can do and how CheapoS supports it.</p>
<a href="docs/USER_GUIDE.md#relevant-section">Explore the workflow →</a>
</td>
<td width="50%" valign="top">
<h3>08 · Another concrete outcome</h3>
<p>Use the same structure and a similar amount of text. Link to a guide with details.</p>
<a href="docs/USER_GUIDE.md#relevant-section">Learn more →</a>
</td>
</tr>
```

Replace the example headings, prose, and links before inserting. Use native Markdown, HTML tables, `details`, and `img` elements. GitHub strips custom styles and scripts, so do not rely on flexbox, JavaScript, or embedded interactive widgets.

For a larger feature, add a Markdown section with one sentence explaining the outcome, one real screenshot with descriptive alt text, and a guide link. Present task-list capabilities in Features and link to their implementation guides. Keep feature descriptions separate from validation claims; a planned check or research experiment is not a passing test or a proven savings result. Do not add unmeasured savings percentages, uptime claims, or static badges that look like live CI results.

## Refresh the screenshots

Run the dedicated fixture server from the repository root:

```sh
python3 -B scripts/readme_demo.py
```

It uses a new temporary data directory, creates a tiny fixture repository, runs the existing scripted demo through real edits and tests, and serves the actual app at `http://127.0.0.1:5186/`. It does not invoke gateway startup, a greeting, or live inference. Do not configure providers or start a real task in this screenshot session. Stop it with Ctrl+C to remove its temporary task data.

1. Use a fresh browser session at **1440 × 940**, 100% zoom. Select the completed task under **Local demo**.
2. For `workspace.png`, select **Activity**, show session details, and keep the sidebar around 220 px and details around 310 px. Wait for the current checks and review to appear.
3. For `changes.png`, hide session details and select **Changes**. Wait for the final preview to finish loading, collapse **Final diff**, then scroll the content pane until the commit controls and per-file diff are both visible. Do not click commit.
4. Save the browser viewport directly into `docs/assets/`. Use real state; do not retouch statuses or invent a patch. Check that there are no personal task names, credentials, or unrelated project paths.
5. Retain the README caption identifying the model responses as scripted. The screenshots are product demonstrations, not live-model benchmarks.

Current screenshots were captured on 2026-09-13. The actual UI still uses the earlier `cheapoS` casing; the repository presentation uses **CheapoS**.

## Review before committing

```sh
python3 -B scripts/render_readme_assets.py --check
git diff --check
```

Preview the rendered Markdown at typical desktop and narrow mobile widths, in light and dark themes. Confirm the images load, the cover text fits, the feature grid wraps, and no layout causes page-wide horizontal scrolling. GitHub-compatible rendering matters more than how raw Markdown looks in an editor. Check local links and heading anchors, especially after moving documentation. View both screenshots at full size.

Commit the generated assets alongside their sources. No app dependency or build step is needed to display the README. A screenshot or theme update does not require the full runtime test suite; validate the documentation and any capture tooling you change.

## Reference board

Inspected on 2026-09-13. These are presentation references, not endorsements or claims of feature parity. All artwork in this kit is original to CheapoS or derived from its existing icon.

| Reference | Pattern that informed this design |
| --- | --- |
| [OmniRoute](https://github.com/diegosouzapw/OmniRoute) | Lead with the product, use purpose-built diagrams, and link impressive claims to their methodology. |
| [OpenRouter's GitHub profile](https://github.com/OpenRouterTeam) and [homepage](https://openrouter.ai/) | State one clear value proposition, group benefits, then provide a short path to getting started. OpenRouter's public organization and examples were inspected; its hosted service is not being described as an open-source repo. |
| [OpenRouter examples](https://github.com/OpenRouterTeam/openrouter-examples) | Put usable examples beside the feature and organize deeper instructions by the user's task. |
| [Cline](https://github.com/cline/cline) | Use GitHub-compatible feature cells and direct documentation links to make a broad product easy to scan. |
| [Ghostty](https://github.com/ghostty-org/ghostty) | Give the identity space, keep navigation compact, and distinguish current capabilities from future work. |

The project's original motivation is [Irushi's post about trading speed for usage](https://x.com/Im_IrushiK/status/2098809262302720347). The maintainer supplied the screenshot and direct link; the short quote in the README is transcribed from that screenshot. This is an origin credit, not an endorsement by the author.
