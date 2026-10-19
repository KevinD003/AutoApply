from tests.conftest import Api


def test_register_login_logout_cycle():
    a = Api()
    a.register(email="Synthetic@Example.com")
    assert a.get("/auth/me").json()["email"] == "synthetic@example.com"
    assert a.post("/auth/logout").status_code == 204
    assert a.get("/auth/me").status_code == 401

    r = a.client.post(
        "/auth/login", json={"email": "synthetic@example.com", "password": "correct-horse-1"}
    )
    assert r.status_code == 200


def test_duplicate_registration_rejected():
    a = Api()
    a.register()
    r = Api().client.post(
        "/auth/register",
        json={"email": "synthetic.user@example.com", "password": "correct-horse-1"},
    )
    assert r.status_code == 409


def test_wrong_password_and_rate_limit():
    a = Api()
    a.register()
    codes = [
        a.client.post(
            "/auth/login",
            json={"email": "synthetic.user@example.com", "password": "wrong-password-x"},
        ).status_code
        for _ in range(12)
    ]
    assert codes[0] == 401
    assert 429 in codes


def test_unsafe_methods_require_csrf(api):
    r = api.client.put("/profile", json={"full_name": "Test Person"})
    assert r.status_code == 403
    r = api.client.put(
        "/profile", json={"full_name": "Test Person"}, headers={"X-CSRF-Token": "wrong"}
    )
    assert r.status_code == 403
    assert api.put("/profile", json={"full_name": "Test Person"}).status_code == 200


def test_unauthenticated_requests_denied():
    a = Api()
    for path in ("/profile", "/jobs", "/documents", "/applications"):
        assert a.get(path).status_code == 401
