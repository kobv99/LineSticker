# Klaus MCP integration for LineSticker

This repository now has a **Klaus-first command bridge**. It does not require Claude
and does not modify, replace, or register a new Klaus MCP server. The existing
Klaus_Patched_R2_Test MCP shell executes the local CLI and returns structured
JSON when the task completes. Source image processing remains Python/Pillow.

## Architecture

User/ChatGPT or your own AI host
  -> Klaus MCP shell (tool action, task ID and permission boundary)
  -> D:\LineSticker\tools\klaus_line_studio.py
  -> existing generation/composition/validators
  -> local image previews and flat LINE ZIPs
  -> Klaus read_file for user review

Klaus does **not** independently create the art direction or prompt JSON. The
AI host supplies those through permitted Klaus file tools. An output ZIP passing
local validation is not yet an approved LINE Creators Market submission.

## First-time setup on your known Windows installation

Repo: D:\LineSticker
Workspace: obtain the LineSticker workspace ID from Klaus workspace_list
Python: D:\LineSticker\.venv\Scripts\python.exe
Bridge: D:\LineSticker\tools\klaus_line_studio.py

Run from PowerShell on the Windows machine, once:

    cd D:\LineSticker
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    .\.venv\Scripts\python.exe tools\klaus_line_studio.py doctor

If the output says api_key_configured=false, use an *interactive local terminal*
to configure it; do not enter the key into ChatGPT, an MCP argument, or a prompt:

    .\.venv\Scripts\python.exe skills\line-character-studio\scripts\set_api_key.py

The doctor command checks presence only, not validity or billing. The key remains
stored locally. Windows ACLs must protect the key file. For Thai captions,
install a licensed Thai font and ensure the Pillow RAQM/HarfBuzz engine is
available; the bridge doctor reports the shaping capability.

## Running via your existing Klaus MCP tools

In the conversation, the AI host calls mcp__Klaus_Patched_R2_Test__shell:

    workspaceId = registered LineSticker workspace ID
    cwd = D:\LineSticker
    executable = D:\LineSticker\.venv\Scripts\python.exe
    arguments = ["tools/klaus_line_studio.py", "doctor"]

Klaus shell execution is asynchronous: a task_id means *started*, not success.
Follow with shell(operation="wait", task_id=...) until terminal; inspect exit_code
and the single JSON output. Image preview paths can be accessed using the Klaus
read_file tool. All file changes must use Klaus write_file/apply_patch/edit_file,
rather than treating shell as a file editor.

## Workflow example: eight Thai stickers

1. User supplies local mascot PNG path and choices (8 stickers, Thai captions).
2. Host reads existing SKILL.md for art steps and references/line-specs.md for
   format rules, but ignores the Claude-specific invocation instructions.
3. Host makes output folder and two-pose pilot prompts JSON using Klaus file tools.
4. Host tests parameters without billing:

    .\.venv\Scripts\python.exe tools\klaus_line_studio.py generate --prompts work\pilot.json --out work\raw --image work\mascot.png --background transparent --dry-run

5. After obtaining explicit user approval for that paid batch, run:

    .\.venv\Scripts\python.exe tools\klaus_line_studio.py generate --prompts work\pilot.json --out work\raw --image work\mascot.png --background transparent --approve-cost

6. The host reviews returned PNGs, revises pilot prompts if necessary, and
   seeks separate approval before any additional paid batch.
7. Clean generated images:

    .\.venv\Scripts\python.exe tools\klaus_line_studio.py clean --out work\poses --images work\raw\hello.png work\raw\thanks.png

8. Host builds sticker_spec.json from chosen captions and approved images.
   Run deterministic steps (these do not call the paid image API):

    .\.venv\Scripts\python.exe tools\klaus_line_studio.py compose-stickers --spec work\sticker_spec.json --out work\build
    .\.venv\Scripts\python.exe tools\klaus_line_studio.py pack-stickers --source work\build --out-dir work\stickers --zip work\stickers-upload.zip
    .\.venv\Scripts\python.exe tools\klaus_line_studio.py preview-stickers --source work\stickers --out work\preview.png --theme dark

9. Host reads the preview through Klaus and delivers preview, ZIP, and notes.
   Theme and Emoji flows use the commands below.

## Other commands

    python tools/klaus_line_studio.py doctor
    python tools/klaus_line_studio.py build-theme --source work\theme-src --out-dir work\theme
    python tools/klaus_line_studio.py pack-theme --source work\theme --zip work\theme.zip
    python tools/klaus_line_studio.py preview-theme --source work\theme --out work\theme-preview.png
    python tools/klaus_line_studio.py make-emoji --source work\emoji-src --out-dir work\emoji --zip work\emoji.zip --preview work\emoji-preview.png
    python tools/klaus_line_studio.py build-skill

Use --help on the CLI or a subcommand to see complete argument contracts.
Every finished invocation emits a JSON object: ok, action, exit_code (for
mutations), stdout/stderr (sanitized) and output paths when applicable.

## Limits and security model

- No standalone MCP tool or extra network listener is installed.
- All subprocesses use an argument array, never shell command interpolation.
- Paid generation refuses requests without --approve-cost; --dry-run is free.
- Approval is per batch, not a permanent account-level authorization.
- The user manages secrets locally; no key belongs in ChatGPT or source control.
- A 429/5xx retry can incur another charge if the first POST was billed.
- Creators Market acceptance and live image billing are separate E2E tests.
