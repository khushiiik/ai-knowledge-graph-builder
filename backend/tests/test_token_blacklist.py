from app.core.security import (
    blacklist_token,
    is_token_blacklisted,
    create_access_token,
    decode_access_token,
)


def test_token_blacklist():
    token = create_access_token({"sub": "test@example.com"})
    assert is_token_blacklisted(token) is False
    assert decode_access_token(token) is not None

    blacklist_token(token)
    assert is_token_blacklisted(token) is True
    assert decode_access_token(token) is None
    print("ALL TOKEN BLACKLIST TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_token_blacklist()
