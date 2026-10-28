"""대화 기록 — 저장 · 목록(messages 제외) · 불러오기 · 삭제 · 검증."""

MSGS = [{"role": "user", "content": "  가장 높았던 때는 언제였고 그때 무슨 일이 있었는지 메모까지 함께 알려줘  "},
        {"role": "assistant", "content": "2026-06-07 주에 100으로 최고점이었습니다."}]


def test_save_list_load_delete(client):
    r = client.post("/api/conversations", json={"messages": MSGS})
    assert r.status_code == 201
    conv = r.json()
    assert len(conv["title"]) == 30 and conv["title"].endswith("…")           # 제목 = 첫 질문 앞 30자
    assert conv["message_count"] == 2 and conv["messages"][0]["content"].startswith("가장")
    assert conv["preview"].startswith("2026-06-07") and conv["messages"][0]["created_at"]

    client.post("/api/conversations", json={"title": "두 번째", "messages": MSGS[:1]})
    listed = client.get("/api/conversations").json()
    assert listed["count"] == 2 and listed["items"][0]["title"] == "두 번째"   # 최근 수정 순
    assert all("messages" not in item for item in listed["items"])

    loaded = client.get(f"/api/conversations/{conv['id']}").json()
    assert [m["role"] for m in loaded["messages"]] == ["user", "assistant"]

    assert client.delete(f"/api/conversations/{conv['id']}").json()["deleted"] is True
    assert client.get(f"/api/conversations/{conv['id']}").status_code == 404
    assert client.get("/api/conversations", params={"limit": 1}).json()["count"] == 1


def test_validation(client):
    bad = [
        {"messages": []},
        {"messages": [{"role": "system", "content": "x"}]},
        {"messages": [{"role": "user", "content": "   "}]},
        {"title": "x" * 101, "messages": MSGS},
    ]
    for body in bad:
        assert client.post("/api/conversations", json=body).status_code == 422, body
    assert client.delete("/api/conversations/없는-id").status_code == 422     # ID 형식
    assert client.delete("/api/conversations/missing").status_code == 404
