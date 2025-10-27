"""Простейшая точка входа для быстрого старта проектов Aura."""

from pathlib import Path


def main() -> None:
    """Выводит подсказку по настройке собственного скрипта."""
    project_root = Path(__file__).resolve().parent
    print("Привет! Это шаблон Aura для быстрого запуска.")
    print("Вы можете добавить собственную логику в функцию main().")
    print("Текущая директория:", project_root)


if __name__ == "__main__":
    main()
