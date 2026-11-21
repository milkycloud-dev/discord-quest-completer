import sys
import os
import shutil
import tempfile
import re
import subprocess
import time
from logger import log
from rpc_presence import RpcPresence

class SpoofEngine:
    """
    Engine responsible for creating a sandbox and launching a spoofed process 
    that Discord recognizes as a game. Designed to run entirely in the background 
    without any visible windows across platforms.
    """
    def __init__(self, metadata):
        """
        Initialize the spoof engine.
        
        Args:
            metadata (dict): Game metadata containing 'id', 'title', and 'exes'.
        """
        self.meta = metadata
        self.active_proc = None
        self.rpc = None
        self.workspace_dir = None
        self.start_time = None
        self.chosen_exe = None
        self.window_title = metadata.get('title', 'Game')

    def clean_path(self, raw_str):
        """
        Sanitize a string to be used safely as a folder name.
        """
        return re.sub(r'[/\\:*?"<>|]', '_', raw_str)

    def start(self, chosen_exe=None, window_title=None):
        """
        Start the spoofed background process.
        
        Args:
            chosen_exe (str, optional): The specific executable name to launch.
            window_title (str, optional): Custom window title for Discord detection.
        Returns:
            bool: True if started successfully, False otherwise.
        """
        if self.active_proc or self.rpc:
            self.stop()
            
        app_title = self.meta.get('title', 'Unknown')
        execs = self.meta.get('exes', ["game.exe"])
        
        if not chosen_exe:
            chosen_exe = execs[0]
            
        chosen_exe = chosen_exe.strip()
            
        self.chosen_exe = chosen_exe
        if window_title is not None:
            self.window_title = window_title
            
        if self.meta.get('no_exe'):
            return self._start_rpc(app_title)

        folder_prefix = self.clean_path(app_title)
        app_ident = self.meta.get('id', '0')
        sys_temp = tempfile.gettempdir()
        self.workspace_dir = os.path.join(sys_temp, "DCRunnerCache", f"{folder_prefix}_{app_ident}_{int(time.time())}")
        
        try:
            os.makedirs(self.workspace_dir, exist_ok=True)
            rel_parts = [p for p in chosen_exe.lstrip(">").replace("\\", "/").split("/") if p not in ("", ".", "..")]
            if not rel_parts:
                rel_parts = ["game.exe"]
            final_exe_path = os.path.join(self.workspace_dir, *rel_parts)
            os.makedirs(os.path.dirname(final_exe_path), exist_ok=True)
            
            # Find the runner executable
            if sys.platform == "win32":
                runner_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runner.exe")
                if not os.path.exists(runner_src):
                    log("log_spoof_fail_err", app_title, "runner.exe not found.")
                    return False
                args = [final_exe_path, self.window_title]
            else:
                # For Linux, Discord scans /proc for executable names.
                runner_src = shutil.which("perl")
                if runner_src:
                    args = [final_exe_path, "-e", "$p = getppid(); sleep 2 while getppid() == $p;"]
                else:
                    runner_src = "/bin/sleep"
                    args = [final_exe_path, "10000000"]

            shutil.copy(runner_src, final_exe_path)
        except Exception as e:
            log("log_spoof_fail_err", app_title, str(e))
            return False
        
        kwargs = {
            'cwd': self.workspace_dir,
            'stdout': subprocess.DEVNULL,
            'stderr': subprocess.DEVNULL,
            'stdin': subprocess.DEVNULL
        }
        
        if sys.platform == "win32":
            # No CREATE_NO_WINDOW so it pops up visually, but we can avoid console window? 
            # Tkinter opens its own window. If we want to hide the console, pythonw.exe is better.
            # But sys.executable is usually python.exe. We will just use it normally.
            pass
        else:
            kwargs['preexec_fn'] = os.setpgrp
        
        try:
            self.active_proc = subprocess.Popen(args, **kwargs)
            self.start_time = time.time()
            log("log_spoof_start", app_title, chosen_exe)
            return True
        except Exception as e:
            log("log_spoof_fail_err", app_title, str(e))
            return False

    def _start_rpc(self, app_title):
        rpc = RpcPresence(self.meta.get('id'))
        if not rpc.start():
            log("log_spoof_fail_err", app_title, rpc.error or "RPC failed")
            return False
        self.rpc = rpc
        self.start_time = time.time()
        log("log_spoof_start", app_title, "RPC")
        return True

    def stop(self):
        if self.rpc:
            self.rpc.stop()
            self.rpc = None
            self.start_time = None
            log("log_spoof_stop", self.meta.get('title', 'Unknown'))
            return
        """
        Terminate the spoofed background process and clean up the sandbox.
        """
        if self.active_proc:
            try:
                self.active_proc.terminate()
                self.active_proc.wait(timeout=2)
            except:
                try:
                    self.active_proc.kill()
                except:
                    pass
            self.active_proc = None
            log("log_spoof_stop", self.meta.get('title', 'Unknown'))
            
        self.start_time = None
        
        if self.workspace_dir and os.path.exists(self.workspace_dir):
            try:
                shutil.rmtree(self.workspace_dir, ignore_errors=True)
            except:
                pass
                
    def is_running(self):
        """
        Check if the spoofed process is currently active.
        """
        if self.rpc:
            return self.rpc.is_alive()
        if not self.active_proc:
            return False
        return self.active_proc.poll() is None
        
    def get_runtime_str(self):
        if not self.start_time or not self.is_running():
            return "00:00"
        diff = int(time.time() - self.start_time)
        m, s = divmod(diff, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
