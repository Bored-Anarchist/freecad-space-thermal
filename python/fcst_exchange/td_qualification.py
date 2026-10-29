# SPDX-License-Identifier: MIT OR Apache-2.0
"""Qualification never follows from parser, SDK-shim or external-run success."""
from .opentd import PROFILE

REQUIRED=('runtime_exact','licensed_host_policy','dependency_closure','unchanged_reopen_run',
          'controlled_edit_reopen_run','independent_source_native_edits','source_results',
          'owned_thermal_comparison','owned_radiation_comparison','owned_environment_comparison','paired_esa_qualification')


def assess(evidence,*,candidate,profile=PROFILE):
    """All gate records must identify the same immutable candidate/profile.

    Owned comparisons must carry native/backend identity and independent source
    evidence. A mock/shim, external fallback or a stale record cannot qualify Q1.
    """
    problems=[];by_id={}
    for record in evidence:
        name=record.get('id')
        if name in by_id:problems.append('duplicate_qualification_case')
        by_id[name]=record
    for name in REQUIRED:
        record=by_id.get(name)
        if (not record or record.get('status')!='passed' or record.get('candidate')!=candidate or record.get('profile')!=profile
                or record.get('fixture_kind') in {'sdk-shim','parser-only','upstream-output'}):
            problems.append(name);continue
        if name.startswith('owned_'):
            if (record.get('execution_mode')!='fcst_native' or not record.get('native_engine_sha256') or not record.get('source_reference_sha256')
                    or not record.get('criteria_sha256') or not record.get('observations_sha256')):problems.append(name)
        if name=='independent_source_native_edits' and not record.get('independent_edit_receipt_sha256'):problems.append(name)
    return {'profile':profile,'candidate':candidate,'status':'blocked' if problems else 'passed',
            'qualified':not problems,'missing_or_invalid':sorted(set(problems)),
            'scope':'Q1 Thermal Desktop/SINDA qualification; implemented adapter support is recorded separately'}
