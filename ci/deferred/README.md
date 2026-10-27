# Deferred platform references

macOS and Linux development, CI, FreeCAD host integration, packaging and qualification
belong to WP-22 at POST-Q2, after Windows WP-21 is complete.

`CMakePresets.multiplatform.json` preserves the earlier build definitions and
`host-profile.linux.json` preserves the previously tested Linux bundle pin. Neither
is an active build or host profile. Select and qualify actual versions again when
WP-22 starts; there is no selected macOS profile yet.

Historical Linux results in `plans/evidence/foundation-profiles.json` remain
engineering history. They do not make Linux a current delivery target or add a
Linux prerequisite to Windows releases. Active scope is `plans/delivery-scope.json`.
