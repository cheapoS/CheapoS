# Agent Role Mappings (T89)

Allow users to define specific models for planner, worker, and reviewer roles in settings.
- Implement per-project overrides in "work setup".
- Enforce the rule: Worker must be distinct from planner and reviewer models.
- Ensure explicit mappings are clear in the UI and settings.
- Operator consent is required for all changes; no implicit budget or permission escalation.

Role mappings are labeled with their source: '**operator**' for defaults configured in Settings, and '**user**' for explicit per-project overrides configured in chat work setup.
