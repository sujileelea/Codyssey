"""데이터 CRUD — 정상 흐름 · 검증 실패 · 없는 ID · 날짜 중복."""


def add(client, date="2026-01-04", value=10, memo=""):
    return client.post("/api/data", json={"date": date, "value": value, "memo": memo})


def test_create_list_update_delete(client):
    r = add(client, memo="  첫 값  ")
    assert r.status_code == 201
    row = r.json()
    assert row["date"] == "2026-01-04" and row["value"] == 10 and row["memo"] == "첫 값"   # 앞뒤 공백 제거

    add(client, "2026-01-11", 20)
    body = client.get("/api/data").json()
    assert body["count"] == 2 and [x["date"] for x in body["items"]] == ["2026-01-04", "2026-01-11"]

    r = client.put(f"/api/data/{row['id']}", json={"date": "2026-01-04", "value": 12.5, "memo": "수정"})
    assert r.status_code == 200 and r.json()["value"] == 12.5 and r.json()["memo"] == "수정"

    assert client.delete(f"/api/data/{row['id']}").json() == {"id": row["id"], "deleted": True}
    assert client.get("/api/data").json()["count"] == 1


def test_list_filters(client):
    for i, d in enumerate(["2026-01-04", "2026-01-11", "2026-01-18", "2026-01-25"]):
        add(client, d, i)
    body = client.get("/api/data", params={"start": "2026-01-10", "end": "2026-01-20", "order": "desc"}).json()
    assert [x["date"] for x in body["items"]] == ["2026-01-18", "2026-01-11"]
    assert body["total"] == 4
    assert client.get("/api/data", params={"limit": 1}).json()["count"] == 1


def test_validation_errors(client):
    cases = [
        {"date": "2026-13-01", "value": 1},                 # 없는 날짜
        {"date": "1999-12-31", "value": 1},                 # 범위 밖
        {"date": "2026-01-04", "value": "많음"},            # 숫자가 아님
        {"date": "2026-01-04"},                             # value 누락
        {"date": "2026-01-04", "value": 1, "memo": "x" * 201},
        {"date": "2026-01-04", "value": 1, "extra": 1},     # 모르는 필드
    ]
    for body in cases:
        r = client.post("/api/data", json=body)
        assert r.status_code == 422, body
        assert r.json()["detail"]["code"] == "VALIDATION_ERROR"
        assert r.json()["detail"]["message"].startswith("입력값을 확인해 주세요")
    assert client.get("/api/data", params={"limit": 0}).status_code == 422


def test_duplicate_date_conflict(client):
    a = add(client, "2026-01-04").json()
    b = add(client, "2026-01-11").json()
    r = add(client, "2026-01-04")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "DUPLICATE_DATE"
    # 다른 행의 날짜로 바꾸는 수정도 막는다. 같은 행의 날짜 유지는 허용
    assert client.put(f"/api/data/{b['id']}", json={"date": "2026-01-04", "value": 1}).status_code == 409
    assert client.put(f"/api/data/{a['id']}", json={"date": "2026-01-04", "value": 99}).status_code == 200


def test_missing_or_bad_id(client):
    assert client.put("/api/data/nope", json={"date": "2026-01-04", "value": 1}).status_code == 404
    r = client.delete("/api/data/nope")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "NOT_FOUND"
    assert client.delete("/api/data/bad%20id!").status_code == 422


def test_validation_messages_are_korean(client):
    r = client.post("/api/data", json={"date": "2026-02-30", "value": "많음", "memo": "x" * 201, "extra": 1})
    msg = r.json()["detail"]["message"]
    for text in ("날짜: 올바른 날짜(YYYY-MM-DD)가 아닙니다", "값: 숫자가 아닙니다", "메모: 200자 이하로 입력해 주세요", "extra: 알 수 없는 항목입니다"):
        assert text in msg, msg
    r = client.post("/api/data", json={"date": "1999-01-01", "value": 1})
    assert "2000-01-01 부터 1년 뒤까지의 날짜만 받습니다" in r.json()["detail"]["message"]
    assert "필수 항목입니다" in client.post("/api/data", json={"date": "2026-01-04"}).json()["detail"]["message"]
