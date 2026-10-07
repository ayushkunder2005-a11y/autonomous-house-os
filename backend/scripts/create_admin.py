import argparse
import asyncio
import getpass

from app.database.session import SessionFactory, create_schema
from app.models.domain import Role, User
from app.security.auth import hash_password
from app.security.bootstrap import seed_security
from sqlalchemy import select


async def create_admin(email: str, display_name: str, password: str) -> None:
    await create_schema()
    async with SessionFactory() as db:
        await seed_security(db)
        if await db.scalar(select(User).where(User.email == email.lower())):
            raise SystemExit("A user with that email already exists")
        role = await db.scalar(select(Role).where(Role.name == "admin"))
        db.add(
            User(
                email=email.lower(),
                display_name=display_name,
                password_hash=hash_password(password),
                role=role,
            )
        )
        await db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a House OS administrator")
    parser.add_argument("email")
    parser.add_argument("--name", default="Administrator")
    args = parser.parse_args()
    secret = getpass.getpass("Password (minimum 12 characters): ")
    if len(secret) < 12:
        raise SystemExit("Password is too short")
    asyncio.run(create_admin(args.email, args.name, secret))
