"""
Windows Service wrapper for the FastAPI backend.
Install:   python win_service.py install
Start:     python win_service.py start
Stop:      python win_service.py stop
Remove:    python win_service.py remove
"""

import sys
import os
import subprocess

try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
except ImportError:
    print("ERROR: pywin32 is required.  pip install pywin32")
    sys.exit(1)


class AIDashboardService(win32serviceutil.ServiceFramework):
    _svc_name_ = "AIDashboardBackend"
    _svc_display_name_ = "AI Dashboard - FastAPI Backend"
    _svc_description_ = "Runs the local AI Dashboard Python API (Uvicorn/FastAPI)."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.process = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        if self.process:
            self.process.terminate()

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
        self.process = subprocess.Popen(
            [sys.executable, "run.py"],
            cwd=backend_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Wait until stop signal
        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(AIDashboardService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(AIDashboardService)
