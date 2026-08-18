from app.webhooks.signatures import sign_body, verify_signature

SECRET = "super-secret"
BODY = b'{"ok":true}'


def test_valid_signature() -> None:
    header = sign_body(secret=SECRET, body=BODY)
    assert verify_signature(secret=SECRET, body=BODY, header=header)


def test_invalid_signature() -> None:
    header = sign_body(secret=SECRET, body=BODY)
    assert not verify_signature(secret="other", body=BODY, header=header)


def test_missing_header() -> None:
    assert not verify_signature(secret=SECRET, body=BODY, header=None)


def test_wrong_prefix() -> None:
    assert not verify_signature(secret=SECRET, body=BODY, header="sha1=abcd")
