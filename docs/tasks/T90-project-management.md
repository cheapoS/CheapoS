# Plan: Improved Project Management UX (T90)

## Problem
Currently, adding a new project to CheapoS requires the user to manually enter the directory path, which is poor UX.

## Goal
Improve the project management experience so users can:
1.  **Open an existing project**: Navigate the file system to select a project directory.
2.  **Create a new project**: Guidance for creating a new directory and initializing it.

## Approach

### 1. Backend Enhancement
- Add an API endpoint `GET /api/list-directories` that allows the backend to explore the local file system. This will support the "browse to find project" requirement.
- Ensure the backend securely restricts access to allowed directories.

### 2. Frontend Enhancement (UI)
- Add a new "Project Manager" modal or view accessible from the main interface.
- **Open Project**: Implement a directory selector UI that lists subdirectories of the current or home path, allowing the user to drill down to the desired project root.
- **Create Project**: Provide a simple input for the new project name and, optionally, a template selection or path specification for the creation.

### 3. Workflow Integration
- Update the application startup/initialization to use this new UI instead of the raw text input for path.
- Ensure seamless transition to the selected/created project.

## Implementation Steps
1.  Define the API for directory listing and project creation in the backend (`cheapos/server.py` and potentially `cheapos/workspace.py` or a new handler).
2.  Update the frontend `dist/index.html` and `dist/app.js` to incorporate the new "Project Manager" interface.
3.  Test the workflow by ensuring projects can be opened and created correctly.

## Reviews
- [ ] Backend API design
- [ ] Frontend UI/UX
- [ ] Integrated workflow
