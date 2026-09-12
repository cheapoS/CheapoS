# CheapOS

**Cheap models work. Smart models check.**

A functional, dependency-free prototype of a desktop AI coding workspace. Economy mode uses a cheap worker for coding and testing and sends compact checkpoints to a premium reviewer.

## Run locally

```sh
python3 -m http.server 5173 --bind 127.0.0.1 --directory dist
```

Open http://127.0.0.1:5173 in your browser. No installation or build step is required.

## Explore

- Replay the complete worker → review → revise → approve workflow.
- Inspect unified and split code diffs and copy a patch.
- Compare the failing test run with two successful runs.
- Open the reviewer checkpoint to see the information sent for review.
- Search task history with ⌘/Ctrl K and create a sample task with ⌘/Ctrl N.
- Set mode, worker, reviewer, checkpoint frequency, token budget, iteration cap, and tool permissions. Preferences stay on this device; new tasks and messages stay for the current visit.

All model activity, code changes, test output, and costs are simulated. No model APIs or local execution tools are connected. The 81% savings figure is an illustrative estimate, not measured billing. The files shown inside the prototype are sample data.

## Structure

- `dist/index.html`: workspace shell and sample activity.
- `dist/styles.css`: theme, layout, responsive behavior, and dialogs.
- `dist/app.js`: local state, sample data, diffing, interactions, and optional WebMCP navigation.

Designed as a frontend that can later sit inside a native desktop shell and connect to a real execution engine.
