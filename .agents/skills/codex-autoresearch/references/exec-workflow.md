# Exec Workflow Disabled

`Mode: exec` and `codex exec` are disabled in this project-local Windows Codex
App adapter.

Do not use this file as an execution workflow. If the user asks for CI-style or
background automation through `$codex-autoresearch`, decline that mode and offer
a foreground run in the current Codex App session.

The upstream exec helper files remain in the bundle only so the original code
copy is preserved and Python unit tests can cover helper behavior.
