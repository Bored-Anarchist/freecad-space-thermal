# Optional platform stretch references

macOS and Linux development, CI, FreeCAD host integration, packaging and qualification
are uncommitted stretch goals outside all work packages and release gates.

`CMakePresets.multiplatform.json` preserves the earlier build definitions and
`host-profile.linux.json` preserves the previously tested Linux bundle pin. Neither
is an active build or host profile. Select and qualify actual versions again when
separately scoped platform work starts; there is no selected macOS profile yet.

Historical Linux results in `plans/evidence/foundation-profiles.json` remain
engineering history. They do not make Linux a current delivery target or add a
Linux prerequisite to Windows releases. Active scope is `plans/delivery-scope.json`.
