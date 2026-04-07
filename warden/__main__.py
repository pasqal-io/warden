#!/usr/bin/env python3
"""
Start Warden API and Scheduler as separate processes
"""

import logging
import multiprocessing
import signal
import sys
import time
from typing import Optional

from warden.api.main import main as api_process
from warden.lib.config.config import Config
from warden.scheduler.main import main as scheduler_process

logger = logging.getLogger("warden")


class WardenProcessError(Exception): ...


class Warden:
    """Manages API and Scheduler as separate processes"""

    def __init__(self):
        self.api_process: Optional[multiprocessing.Process] = None
        self.scheduler_process: Optional[multiprocessing.Process] = None
        self.shutdown_requested = False

    def start(self):
        """Start both processes"""
        logger.info("Starting Warden API and scheduler...")

        # Start API process
        self.api_process = multiprocessing.Process(
            target=api_process, name="warden-api"
        )
        self.api_process.start()
        logger.info(f"API process started with PID: {self.api_process.pid}")

        # Start scheduler process
        self.scheduler_process = multiprocessing.Process(
            target=scheduler_process, name="warden-scheduler"
        )
        self.scheduler_process.start()
        logger.info(f"Scheduler process started with PID: {self.scheduler_process.pid}")

    def wait_for_processes(self):
        """Wait for processes to complete or shutdown signal"""
        while not self.shutdown_requested:
            # Check if any process has died
            if self.api_process and not self.api_process.is_alive():
                logger.error("API process died")
                raise WardenProcessError

            if self.scheduler_process and not self.scheduler_process.is_alive():
                logger.error("Scheduler process died")
                raise WardenProcessError

            time.sleep(1)

    def shutdown(self):
        """Shutdown both processes"""
        self.shutdown_requested = True
        logger.info("Shutting down Warden processes...")

        # Terminate processes gracefully
        for process in [self.api_process, self.scheduler_process]:
            if process and process.is_alive():
                logger.info(f"Terminating process {process.name} (PID: {process.pid})")
                process.terminate()
                process.join(timeout=10)

                # Force kill if still alive
                if process.is_alive():
                    logger.warning(f"Force killing process {process.name}")
                    process.kill()
                    process.join()

        logger.info("All processes terminated")


def setup_signal_handlers(warden: Warden):
    """Setup signal handlers"""

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        warden.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def main():
    """Start Warden API and Scheduler as separate processes

    Wait for termination signal and terminates each process gracefully.
    Process restarts should be handled by external process managers (systemd, Docker, etc.)
    """
    # Setup logging
    config = Config()
    logging.config.dictConfig(config=config.logging)
    warden = Warden()

    setup_signal_handlers(warden)

    try:
        warden.start()
        warden.wait_for_processes()
    except Exception as e:
        logger.error(f"Shutting down warden: {e}")
        warden.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn")  # For cross-platform compatibility
    main()
