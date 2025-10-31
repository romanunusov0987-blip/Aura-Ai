"""Утилита для одновременного запуска всех основных сервисов Aura-Ai.

Запускает основной Telegram-бот, административного бота и FastAPI-сервис
реферальной системы единым процессом. Скрипт предназначен для разработки и
локального тестирования: он перезапускает все процессы при остановке одного и
корректно завершает остальные сервисы при получении сигнала Ctrl+C.

Использование:
    python run_all.py

Дополнительные переменные окружения:
    REFERRAL_API_HOST — хост для uvicorn (по умолчанию 0.0.0.0)
    REFERRAL_API_PORT — порт для uvicorn (по умолчанию 8000)
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Sequence, Tuple


ROOT_DIR = Path(__file__).resolve().parent
PYTHON_EXECUTABLE = sys.executable


Command = Tuple[str, List[str]]


def build_commands() -> List[Command]:
    """Собирает список процессов, которые нужно запустить."""

    referral_host = os.environ.get("REFERRAL_API_HOST", "0.0.0.0")
    referral_port = os.environ.get("REFERRAL_API_PORT", "8000")

    return [
        (
            "telegram-bot",
            [PYTHON_EXECUTABLE, "Aura_Psycholog_bot.py"],
        ),
        (
            "admin-bot",
            [PYTHON_EXECUTABLE, "-m", "admin_bot"],
        ),
        (
            "referral-api",
            [
                PYTHON_EXECUTABLE,
                "-m",
                "uvicorn",
                "Aura_Psycholog_bot:referral_api",
                "--host",
                referral_host,
                "--port",
                str(referral_port),
            ],
        ),
    ]


def launch_process(command: Sequence[str], name: str) -> subprocess.Popen[bytes]:
    """Запускает процесс и возвращает объект Popen."""

    env = os.environ.copy()
    try:
        process = subprocess.Popen(command, cwd=ROOT_DIR, env=env)
    except FileNotFoundError as exc:  # uvicorn может быть не установлен
        print(f"[run_all] Не удалось запустить {name}: {exc}")
        raise
    print(f"[run_all] Запущен {name}: {' '.join(command)}")
    return process


def terminate_process(process: subprocess.Popen[bytes], name: str) -> None:
    """Останавливает процесс, если он ещё не завершился."""

    if process.poll() is not None:
        return

    print(f"[run_all] Останавливаю {name}...")
    process.terminate()

    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        print(f"[run_all] {name} не завершился вовремя, отправляю SIGKILL")
        process.kill()


def main() -> int:
    commands = build_commands()
    processes: List[Tuple[str, subprocess.Popen[bytes]]] = []
    shutting_down = False

    def shutdown(signum: int | None = None, _frame: object | None = None) -> None:
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True

        if signum in (signal.SIGINT, signal.SIGTERM):
            print("\n[run_all] Получен сигнал остановки, завершаю процессы...")

        for proc_name, proc in processes:
            terminate_process(proc, proc_name)

    for name, command in commands:
        try:
            proc = launch_process(command, name)
        except FileNotFoundError:
            shutdown()
            return 1
        processes.append((name, proc))

    try:
        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)
    except ValueError:
        # На некоторых платформах (например, Windows в потоках) сигнал может быть недоступен.
        pass

    exit_code = 0

    try:
        while not shutting_down:
            for proc_name, proc in processes:
                retcode = proc.poll()
                if retcode is not None:
                    exit_code = retcode
                    print(
                        f"[run_all] Процесс {proc_name} завершился с кодом {retcode}. Останавливаю остальные..."
                    )
                    shutdown()
                    break
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown(signal.SIGINT)

    for proc_name, proc in processes:
        proc.wait()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
