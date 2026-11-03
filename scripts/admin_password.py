"""Generate an admin password hash interactively; never print the password or session key.

Run from the project root: .venv/Scripts/python.exe -m scripts.admin_password
"""
from getpass import getpass

from app.admin_auth import hash_password


def main():
    password = getpass("Administrator password (at least 14 characters): ")
    if password != getpass("Confirm administrator password: "):
        raise SystemExit("Passwords do not match.")
    try:
        encoded = hash_password(password)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    print("Store this value as ADMIN_PASSWORD_HASH in the backend environment:")
    print(encoded)


if __name__ == "__main__":
    main()
