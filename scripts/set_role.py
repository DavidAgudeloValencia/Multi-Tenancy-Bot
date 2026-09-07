"""Cambia el rol de un usuario de la plataforma (admin | supervisor | agent).

Uso:
    python -m scripts.set_role <email> <rol>
Ej.:
    python -m scripts.set_role ana@x.com admin

El usuario debe existir (haber iniciado sesión con Google al menos una vez).
En Railway se ejecuta desde la consola/Shell del servicio.
"""

import argparse
import asyncio

from sqlalchemy import select

from app.db import get_session_factory, init_db
from app.models import User


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Cambia el rol de un usuario")
    parser.add_argument("email", help="Email del usuario (Google)")
    parser.add_argument("role", choices=["admin", "supervisor", "agent"])
    args = parser.parse_args()

    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        user = (
            await session.execute(select(User).where(User.email == args.email))
        ).scalar_one_or_none()
        if user is None:
            print(
                f"Usuario '{args.email}' no encontrado. "
                "Debe haber iniciado sesión con Google al menos una vez."
            )
            return
        user.role = args.role
        await session.commit()
        print(f"Rol de '{args.email}' actualizado a '{args.role}'.")


if __name__ == "__main__":
    asyncio.run(_main())
