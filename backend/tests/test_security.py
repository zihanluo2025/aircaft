from app.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_roundtrip():
    stored = hash_password("correct horse battery")
    assert stored.startswith("pbkdf2_sha256$")
    assert verify_password("correct horse battery", stored)
    assert not verify_password("wrong", stored)
    assert hash_password("same") != hash_password("same")  # random salt


def test_bad_hash_is_rejected():
    assert not verify_password("x", "garbage")
    assert not verify_password("x", "md5$1$2$3")


def test_token_roundtrip():
    token = create_access_token("lead")
    assert decode_access_token(token) == "lead"
    assert decode_access_token(token + "x") is None
    assert decode_access_token("not-a-token") is None
