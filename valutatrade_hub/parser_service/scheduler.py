"""Планировщик периодического запуска обновления курсов валют."""

from __future__ import annotations

import threading
import time

from valutatrade_hub.parser_service.updater import RatesUpdater


class RatesScheduler:
    """Фоновый планировщик периодического опроса API."""

    def __init__(self, updater: RatesUpdater | None = None, interval_seconds: int = 300) -> None:
        """Инициализирует планировщик с заданным интервалом в секундах."""
        self.updater = updater or RatesUpdater()
        self.interval_seconds = max(10, int(interval_seconds))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start_background(self) -> None:
        """Запускает фоновый поток периодического обновления."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Останавливает фоновый поток."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run_loop(self) -> None:
        """Внутренний цикл выполнения обновлений по таймеру."""
        while not self._stop_event.is_set():
            self.updater.run_update()
            if self._stop_event.wait(self.interval_seconds):
                break

    def run_blocking(self, max_iterations: int | None = None) -> None:
        """Запускает цикл обновления в текущем потоке."""
        iteration = 0
        while True:
            print(self.updater.run_update())
            iteration += 1
            if max_iterations is not None and iteration >= max_iterations:
                break
            time.sleep(self.interval_seconds)
