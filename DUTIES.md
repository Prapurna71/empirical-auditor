# Duties

## Coordinator

- Reads experiment manifests and schedules the workflow.
- Creates file-based tasks for worker and auditor stages.
- Stores coordination outcomes in repository artifacts only.

## Worker

- Executes the experiment using Python from script interfaces.
- Writes measured metrics back to experiment YAML.
- Never bypasses schema or required metadata checks.

## Auditor

- Compares baseline and current outputs.
- Flags divergence and blocks approval when thresholds are exceeded.
- Produces structured markdown reports and a simulated replication PR record.

## Execution Model

All collaboration is simulated using repository files only.
No external orchestration service is required.
