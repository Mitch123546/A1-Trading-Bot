import app.auth as auth


class FakeSecret:
    def __init__(self, value: str):
        self.value = value

    def get_secret_value(self) -> str:
        return self.value


class FakeSettings:
    dashboard_password = FakeSecret("a-strong-test-password")
    session_secret = FakeSecret("x" * 48)


def test_signed_session_round_trip(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: FakeSettings())
    token = auth.create_session_token()
    assert auth.validate_session(token)
    assert not auth.validate_session(token + "tampered")
    assert auth.verify_password("a-strong-test-password")
