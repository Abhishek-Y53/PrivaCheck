from argon2 import extract_parameters

from backend.security.passwords import hash_password, password_hash_needs_rehash, verify_password


def test_password_is_stored_as_argon2id_hash_not_plaintext():
    password = "a-long-passphrase-123"
    password_hash = hash_password(password)

    assert password_hash.startswith("$argon2id$")
    assert password not in password_hash
    assert verify_password(password, password_hash) is True
    assert verify_password("a-different-passphrase", password_hash) is False
    assert password_hash_needs_rehash(password_hash) is False


def test_password_policy_rejects_short_and_overlong_values():
    for password in ("short", "x" * 129):
        try:
            hash_password(password)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid password length was accepted")
