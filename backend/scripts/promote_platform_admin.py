"""Operator tool: grants platform-admin privileges (nodes/regions management) to a
registered user. Not exposed via the public API on purpose — bootstrapping the very
first platform admin has no "logged in as an existing admin" state to check against.

Usage:
    python -m scripts.promote_platform_admin someone@example.com
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.user import User


async def promote(email: str) -> None:
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            print(f"No user registered with email {email!r}", file=sys.stderr)
            raise SystemExit(1)
        user.is_platform_admin = True
        await db.commit()
        print(f"{email} is now a platform admin.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.promote_platform_admin <email>", file=sys.stderr)
        raise SystemExit(1)
    asyncio.run(promote(sys.argv[1]))
