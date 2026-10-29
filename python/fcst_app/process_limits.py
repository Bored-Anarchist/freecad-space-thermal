# SPDX-License-Identifier: MIT OR Apache-2.0
"""Windows worker containment: descendants die when the scheduler handle closes."""
import ctypes
from ctypes import wintypes
import os


class WorkerLimits:
    def __init__(self, process, memory_mb=256):
        self.handle = None
        if os.name != "nt":
            raise OSError("unsupported_worker_platform")
        class Basic(ctypes.Structure):
            _fields_ = [("process_time",ctypes.c_int64),("job_time",ctypes.c_int64),
                        ("flags",wintypes.DWORD),("min_working",ctypes.c_size_t),
                        ("max_working",ctypes.c_size_t),("active",wintypes.DWORD),
                        ("affinity",ctypes.c_size_t),("priority",wintypes.DWORD),("scheduling",wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name,ctypes.c_uint64) for name in ("read_ops","write_ops","other_ops","read_bytes","write_bytes","other_bytes")]
        class Extended(ctypes.Structure):
            _fields_ = [("basic",Basic),("io",IO),("process_memory",ctypes.c_size_t),
                        ("job_memory",ctypes.c_size_t),("peak_process",ctypes.c_size_t),("peak_job",ctypes.c_size_t)]
        self.api = ctypes.WinDLL("kernel32",use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p,wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE,wintypes.HANDLE]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.api.CreateJobObjectW(None,None)
        info = Extended()
        info.basic.flags = 0x2000 | 0x200 | 0x8  # kill on close, tree memory, active process count
        info.basic.active = 8
        info.process_memory = int(memory_mb * 1024 * 1024)
        info.job_memory = info.process_memory
        if (not self.handle or not self.api.SetInformationJobObject(self.handle,9,ctypes.byref(info),ctypes.sizeof(info))
                or not self.api.AssignProcessToJobObject(self.handle,wintypes.HANDLE(int(process._handle)))):
            self.close()
            raise OSError("worker_containment_unavailable")
        # Popen starts suspended so no descendant can escape before assignment.
        native = ctypes.WinDLL("ntdll")
        native.NtResumeProcess.argtypes = [wintypes.HANDLE]
        native.NtResumeProcess.restype = ctypes.c_long
        if native.NtResumeProcess(wintypes.HANDLE(int(process._handle))) < 0:
            self.close()
            raise OSError("worker_resume_unavailable")

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None
