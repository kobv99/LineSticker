# LineSticker project agent guidance (Klaus MCP first)

This repository is operated through the already installed Klaus_Patched_R2_Test MCP
server. Do not assume Claude, Claude Code or a separate custom MCP server exists.

Read klaus/PLAYBOOK.md for the end-user pipeline and klaus/manifest.json for the
command catalogue. Invoke tools/klaus_line_studio.py via Klaus shell with explicit
workspace, cwd, executable and argument array. Shell tasks complete asynchronously:
poll the returned task_id and inspect the final exit_code before reporting success.

Use Klaus write_file / edit_file / apply_patch for text-file changes rather than
shell scripts that rewrite files. Use Klaus read_file for image previews where available.

Security boundaries:
- Never request, expose, echo or commit OPENAI_API_KEY.
- Generation is billable. Use --dry-run first. Only pass --approve-cost after
  explicit user authorization for that particular batch.
- Run packaging validation; never bypass checks to force an upload-ready ZIP.
- Read references/line-specs.md before changing LINE package requirements.
- Thai captions require a Thai-glyph-capable licensed font and Pillow RAQM.
- Do not claim LINE Creators Market approved a package before external verification.

Scripts beneath skills/line-character-studio/scripts are the implementation.
The Klaus bridge delegates to them. Preserve Claude-compatible SKILL.md and the
optional .skill distribution, but do not make Claude a runtime dependency.

For code changes: inspect, implement minimally, run python -m pytest -q,
verify compileall and the GitHub Actions matrix, then report commit and limits.
