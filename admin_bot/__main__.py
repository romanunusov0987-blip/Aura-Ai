"""Позволяет запускать административного бота командой `python -m admin_bot`."""
from .bot import main

if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
