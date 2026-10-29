# SPDX-License-Identifier: MIT OR Apache-2.0
"""Product qualification requires independent file codecs and vendor-absent runs."""
import re

PROFILE='td-independent/1'

REQUIRED=('runtime_exact','dependency_closure','unchanged_reopen_run',
          'controlled_edit_reopen_run','independent_source_native_edits','source_results',
          'vendor_absent_import_export','independent_td_class_coverage','new_model_export_reopen',
          'owned_thermal_comparison','owned_radiation_comparison','owned_environment_comparison','paired_esa_qualification')
FILE_CASES={'runtime_exact','dependency_closure','unchanged_reopen_run','controlled_edit_reopen_run',
            'independent_source_native_edits','vendor_absent_import_export','independent_td_class_coverage','new_model_export_reopen'}


def assess(evidence,*,candidate,profile=PROFILE):
    """All gate records must identify the same immutable candidate/profile.

    Optional OpenTD evidence cannot satisfy the independent product profile.
    Reference licenses and source-tool installations are not product gates.
    """
    problems=[];by_id={}
    if profile!=PROFILE:problems.append('independent_product_profile_required')
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
        if name in FILE_CASES:
            hashes=('codec_sha256','input_sha256','output_sha256','criteria_sha256','observations_sha256')
            if (record.get('execution_mode')!='fcst_independent_file_codec' or record.get('vendor_absent') is not True
                    or any(not isinstance(record.get(k),str) or not re.fullmatch('[0-9a-f]{64}',record[k]) for k in hashes)):
                problems.append(name)
        if name=='vendor_absent_import_export' and (type(record.get('vendor_call_attempts')) is not int or record['vendor_call_attempts']!=0):
            problems.append(name)
        if name=='independent_td_class_coverage' and (type(record.get('unresolved_required')) is not int or record['unresolved_required']!=0):
            problems.append(name)
    return {'profile':profile,'candidate':candidate,'status':'blocked' if problems else 'passed',
            'qualified':not problems,'missing_or_invalid':sorted(set(problems)),
            'vendor_runtime_required':False,
            'scope':'Independent TD/SINDA product qualification; OpenTD is optional external reference tooling only'}
