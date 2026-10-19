# Project Instructions

## Goal
Build an original 2D sandbox game in Python using Pygame, inspired by Growtopia's gameplay mechanics, interactions, animations, and visual design.

Prioritize functional implementation, responsiveness, maintainability, and efficient development.

## Development Approach
- **Implementation first:** When requirements are clear, begin coding after minimal necessary inspection.
- Inspect only files directly relevant to the requested task.
- Reuse existing architecture, functions, and documented decisions.
- Do not repeatedly analyze the entire project before making changes.
- Avoid lengthy planning, excessive reasoning, and unnecessary explanations.
- Make reasonable implementation decisions independently when the risk is low.
- Ask questions only when essential information is missing or a decision could significantly affect the project.
- Do not stop at analysis or planning when implementation has been requested.

## Gameplay References
- Use existing specifications and documented observations before examining raw references.
- Consult `references/GAMEPLAY_ANALYSIS.md` for previously analyzed gameplay behavior.
- Inspect screenshots, videos, or extracted frames only when required for the current task.
- Do not reprocess entire recordings when relevant evidence already exists.
- Distinguish verified observations from assumptions.
- Never invent exact mechanics, physics values, or animation timings without sufficient evidence.
- Use reasonable temporary values when necessary and keep them configurable.

## Implementation Standards
- Preserve existing functionality, controls, physics, and save compatibility.
- Keep movement, collisions, animations, inventory, rendering, and world logic modular.
- Maintain the existing fixed timestep simulation unless changes are explicitly necessary.
- Reuse existing code rather than introducing duplicate systems.
- Avoid unnecessary refactoring, new dependencies, and architectural complexity.
- Modify only what is necessary to complete the requested task.
- Use original or properly licensed visual and audio assets.
- Keep implementations simple, efficient, and extensible.

## Asset and Animation Workflow
- Reuse existing assets and animation systems whenever practical.
- Support original AI generated assets through a consistent asset pipeline.
- Preserve correct sprite proportions, transparency, alignment, and pixel art scaling.
- Keep animation timing and frame sequences configurable.
- Do not regenerate or replace working assets without a clear reason.
- Generate visual previews only when needed to verify visual changes.

## Verification
- Run focused tests for the functionality being modified.
- Run the full test suite only for major changes, shared system modifications, or meaningful regression risks.
- Perform rendering checks when changes affect visible behavior.
- Do not repeatedly generate screenshots or test reports without necessity.
- Never claim a manual playtest was completed unless it actually occurred.
- Fix directly related issues discovered during implementation.
- Preserve existing save files and avoid destructive operations.

## Documentation
- Update specifications only when significant gameplay behavior or architecture changes.
- Avoid creating unnecessary planning documents, reports, or duplicate explanations.
- Keep project documentation concise and relevant.
- Treat existing reference analyses as reusable knowledge rather than work to repeat.

## Task Completion
For every implementation request:

1. Identify the relevant code and requirements.
2. Implement the requested changes directly.
3. Run appropriate verification.
4. Fix issues introduced by the changes.
5. Provide a brief completion summary.

The completion summary should include:
- Features implemented or bugs fixed.
- Files modified.
- Tests performed and their results.
- Important limitations, if any.

## Efficiency Rules
- Prefer action over repeated deliberation.
- Do not perform full project audits for isolated tasks.
- Avoid unnecessarily broad file searches and repeated tool calls.
- Do not overengineer simple features.
- Do not introduce unrelated improvements without permission.
- Do not sacrifice correctness or working functionality for speed.
- **Default behavior: inspect minimally, implement directly, verify appropriately, and finish concisely.**