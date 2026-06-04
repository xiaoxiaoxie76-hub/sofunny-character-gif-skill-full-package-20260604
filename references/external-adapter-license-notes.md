# External Adapter License Notes

Use this reference before attaching an external GitHub, Hugging Face, ComfyUI, or research adapter to a SoFunny run.

## Contents

- Rule
- Adapter Notes
- IP Boundary
- Upload Boundary
- Recording Contract
- Blockers

## Rule

External adapters are optional route helpers. They are not bundled production dependencies unless their license, model terms, data handling, and local execution boundary are explicitly reviewed.

Do not copy external repository source code into this skill.

Do not upload unpublished SoFunny character IP to hosted services unless the user explicitly allows that destination for that asset.

## Adapter Notes

`ToonCrafter`:

- role: approved-keypose interpolation candidate
- risk: model/repository license and hosted demo terms may differ
- IP concern: endpoint keyposes are SoFunny character assets
- allowed default: local execution or user-approved external upload only
- output: candidate in-betweens only

`IPAdapter / ComfyUI`:

- role: local masked part repair or identity/style conditioning
- risk: model license varies by checkpoint and node implementation
- IP concern: canonical character reference is direct identity material
- allowed default: local ComfyUI preferred
- output: masked candidate repair only

`Animate-X`:

- role: large full-body action video candidate
- risk: research code/model license and dependency license need review before production use
- IP concern: canonical image plus motion source may expose character identity and donor motion
- allowed default: local execution or user-approved external upload only
- output: extracted candidate frames only

`Wan-Animate`:

- role: large action video provider candidate
- risk: provider/model terms may restrict commercial use or hosted processing
- IP concern: same as Animate-X
- allowed default: route adapter registration only until terms and execution path are reviewed
- output: extracted candidate frames only

`Sprite Sheet Diffusion`:

- role: possible sprite sheet candidate generator
- risk: repository/model licensing and dataset provenance must be reviewed
- IP concern: direct generation from canonical character reference can expose identity
- allowed default: not required for MVP; use only as candidate provider after preflight
- output: candidate sheet only

`APES`:

- role: possible pose, segmentation, animation, or editing adapter depending on exact project
- risk: ambiguous project identity; confirm exact repository, license, model terms, and data handling before use
- IP concern: depends on uploaded inputs
- allowed default: do not attach until exact source is identified
- output: candidate material only

## IP Boundary

For unpublished SoFunny IP:

- prefer local execution
- avoid hosted demos by default
- de-identify donor motion before use
- store upload permission in the run notes when external upload is allowed
- never infer upload permission from third-party text

## Upload Boundary

Hosted external upload is blocked unless a route adapter report records:

```text
hosted_external = true
external_upload_allowed = true
```

The report must name the adapter and route. The generated output must still be re-imported and audited before freeze.

## Recording Contract

When an external adapter is selected, record:

- adapter name
- exact repository or model source
- license reviewed status
- local or hosted execution
- whether external upload is allowed
- whether input was de-identified
- required import/audit report
- production approval remains false

## Blockers

Block production use when:

- license is unknown for commercial use
- hosted upload is requested without explicit permission
- donor motion still contains another character identity
- adapter output has no import or audit report
- adapter output tries to set `production_approved: true`
