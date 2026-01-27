"""Subprocess-based monitor management for web control."""

import queue
import subprocess
import sys
import threading
from collections.abc import Generator


class MonitorManager:
    """Manages the monitor subprocess for web control."""

    _instance: "MonitorManager | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "MonitorManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self) -> None:
        """Initialize instance state."""
        self._process: subprocess.Popen | None = None
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._reader_thread: threading.Thread | None = None
        self._stop_reader = threading.Event()

    def _read_output(self) -> None:
        """Read process output in a background thread."""
        if self._process is None or self._process.stdout is None:
            return

        while not self._stop_reader.is_set():
            try:
                line = self._process.stdout.readline()
                if line:
                    self._log_queue.put(line.strip())
                elif self._process.poll() is not None:
                    break
            except Exception:
                break

    def start(self) -> bool:
        """Start the monitor subprocess."""
        if self.is_running():
            return False

        try:
            self._stop_reader.clear()
            self._process = subprocess.Popen(
                [sys.executable, "-m", "tgmon", "run-all"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            self._reader_thread = threading.Thread(
                target=self._read_output, daemon=True
            )
            self._reader_thread.start()

            return True
        except Exception as e:
            self._log_queue.put(f"Failed to start: {e}")
            return False

    def stop(self) -> bool:
        """Stop the monitor subprocess."""
        if not self.is_running():
            return False

        try:
            self._stop_reader.set()
            if self._process:
                self._process.terminate()
                self._process.wait(timeout=5)
                self._process = None
            return True
        except subprocess.TimeoutExpired:
            if self._process:
                self._process.kill()
                self._process = None
            return True
        except Exception:
            return False

    def is_running(self) -> bool:
        """Check if monitor is running."""
        return self._process is not None and self._process.poll() is None

    def restart(self) -> bool:
        """Restart the monitor subprocess."""
        was_running = self.is_running()
        if was_running:
            self.stop()
        return self.start() if was_running else False

    def get_logs(self) -> Generator[str, None, None]:
        """Get logs as a generator for SSE."""
        while True:
            try:
                log = self._log_queue.get(timeout=1.0)
                yield log
            except queue.Empty:
                if not self.is_running():
                    break
                yield ""  # Keep connection alive


def get_monitor_manager() -> MonitorManager:
    """Get the singleton monitor manager instance."""
    return MonitorManager()
