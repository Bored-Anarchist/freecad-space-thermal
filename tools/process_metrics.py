# SPDX-License-Identifier: MIT OR Apache-2.0
"""Aggregate Windows build-tree accounting; never emit process identities or paths."""
import ctypes
from ctypes import wintypes
import os
import subprocess


class BasicLimits(ctypes.Structure):
    _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD), ("min_working", ctypes.c_size_t),
                ("max_working", ctypes.c_size_t), ("active", wintypes.DWORD),
                ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in
                ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [("basic", BasicLimits), ("io", IoCounters), ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]


class Accounting(ctypes.Structure):
    _fields_ = [("user", ctypes.c_int64), ("kernel", ctypes.c_int64),
                ("period_user", ctypes.c_int64), ("period_kernel", ctypes.c_int64),
                ("page_faults", wintypes.DWORD), ("total_processes", wintypes.DWORD),
                ("active_processes", wintypes.DWORD), ("terminated_processes", wintypes.DWORD)]


def run_tracked(command, directory, output, env, timeout, resources):
    """Capture kernel-maintained peaks/CPU for a fresh job including exited children.

    No CPU, memory or process-count limit is imposed. Kill-on-close confines timeout
    cleanup to this invocation. Start suspended, as the existing worker boundary
    does, so descendants cannot escape accounting before job assignment.
    """
    if os.name != "nt":
        raise OSError("build_accounting_platform")
    resources.clear()
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    api.CreateJobObjectW.restype = wintypes.HANDLE
    api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    api.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    native = ctypes.WinDLL("ntdll")
    native.NtResumeProcess.argtypes = [wintypes.HANDLE]
    native.NtResumeProcess.restype = ctypes.c_long
    job = api.CreateJobObjectW(None, None)
    if not job:
        raise OSError("build_accounting_unavailable")
    process = None
    try:
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE only.
        if not api.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise OSError("build_accounting_unavailable")
        # Reusable MSBuild nodes can predate this job and share another stage's
        # temporary directory. Keep this command's workers inside its own tree.
        stage_env = dict(os.environ if env is None else env)
        stage_env["MSBUILDDISABLENODEREUSE"] = "1"
        process = subprocess.Popen(command, cwd=directory, stdout=output, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, env=stage_env, creationflags=0x4 | 0x08000000)
        handle = wintypes.HANDLE(int(process._handle))
        if not api.AssignProcessToJobObject(job, handle) or native.NtResumeProcess(handle) < 0:
            raise OSError("build_accounting_unavailable")
        returncode = process.wait(timeout=timeout)
        accounting = Accounting()
        if (not api.QueryInformationJobObject(job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None)
                or not api.QueryInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits), None)):
            raise OSError("build_accounting_unavailable")
        resources.update(cpu_seconds=round((accounting.user + accounting.kernel) / 10_000_000, 6),
                         peak_process_commit_bytes=limits.peak_process, peak_job_commit_bytes=limits.peak_job,
                         total_processes=accounting.total_processes)
        return subprocess.CompletedProcess(command, returncode)
    finally:
        api.CloseHandle(job)
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
