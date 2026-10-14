"""Create a leading hand login, or reset the password of an existing one.

    python -m scripts.create_user lead 'a long password' --name "Zihan" --shift morning
"""
import argparse

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import User
from app.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("username")
    parser.add_argument("password")
    parser.add_argument("--name", default="")
    parser.add_argument("--shift", choices=["morning", "night"], default="morning")
    args = parser.parse_args()
    if len(args.password) < 8:
        parser.error("use a password of at least 8 characters")

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == args.username))
        if user is None:
            user = User(username=args.username, password_hash=hash_password(args.password))
            db.add(user)
            action = "Created"
        else:
            user.password_hash = hash_password(args.password)
            action = "Updated"
        user.display_name = args.name or user.display_name or args.username
        user.default_shift = args.shift
        db.commit()
    print(f"{action} user {args.username}")


if __name__ == "__main__":
    main()
