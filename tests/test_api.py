"""API 集成测试（需要安装 fastapi / httpx，使用临时数据库文件）。

运行方式：python3 -m pytest tests/test_api.py
"""

import os
import tempfile

# 须在导入 app 之前设置数据库路径，避免污染本地数据
_tmpdir = tempfile.mkdtemp(prefix="phase-api-test-")
os.environ["DATABASE_PATH"] = os.path.join(_tmpdir, "test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

VALID_PAYLOAD = {
    "capacities": {"A": 100, "B": 100, "C": 100},
    "devices": [
        {"id": "D1", "power": 10, "allowed_phases": ["A", "B", "C"]},
        {"id": "D2", "power": 20, "allowed_phases": ["A", "B", "C"]},
        {"id": "D3", "power": 30, "allowed_phases": ["A", "B", "C"]},
    ],
}


def test_create_calculation_feasible():
    resp = client.post("/api/v1/calculations", json=VALID_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    assert body["feasible"] is True
    assert body["imbalance"] == 20
    assert body["loads"] == {"A": 10, "B": 20, "C": 30}
    assert body["assignments"] == [
        {"device_id": "D1", "phase": "A"},
        {"device_id": "D2", "phase": "B"},
        {"device_id": "D3", "phase": "C"},
    ]
    assert body["id"] >= 1


def test_create_calculation_infeasible():
    payload = {
        "capacities": {"A": 5, "B": 0, "C": 0},
        "devices": [{"id": "BIG", "power": 50, "allowed_phases": ["A", "B", "C"]}],
    }
    resp = client.post("/api/v1/calculations", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["feasible"] is False
    assert body["imbalance"] is None
    assert body["loads"] is None
    assert body["assignments"] == []
    assert "无可行" in body["message"]


def test_list_and_get_detail():
    created = client.post("/api/v1/calculations", json=VALID_PAYLOAD).json()
    calc_id = created["id"]

    listing = client.get("/api/v1/calculations").json()
    assert any(item["id"] == calc_id for item in listing)

    detail = client.get(f"/api/v1/calculations/{calc_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["feasible"] is True
    assert body["loads"] == {"A": 10, "B": 20, "C": 30}
    assert {d["device_id"] for d in body["devices"]} == {"D1", "D2", "D3"}
    for device in body["devices"]:
        assert device["assigned_phase"] in ("A", "B", "C")


def test_get_not_found():
    resp = client.get("/api/v1/calculations/999999")
    assert resp.status_code == 404


def test_validation_duplicate_ids():
    payload = {
        "capacities": {"A": 10, "B": 10, "C": 10},
        "devices": [
            {"id": "D1", "power": 5, "allowed_phases": ["A"]},
            {"id": "D1", "power": 5, "allowed_phases": ["B"]},
        ],
    }
    assert client.post("/api/v1/calculations", json=payload).status_code == 422


def test_validation_too_many_devices():
    payload = {
        "capacities": {"A": 1000, "B": 1000, "C": 1000},
        "devices": [
            {"id": f"D{i}", "power": 1, "allowed_phases": ["A"]} for i in range(13)
        ],
    }
    assert client.post("/api/v1/calculations", json=payload).status_code == 422


def test_validation_empty_allowed_phases():
    payload = {
        "capacities": {"A": 10, "B": 10, "C": 10},
        "devices": [{"id": "D1", "power": 5, "allowed_phases": []}],
    }
    assert client.post("/api/v1/calculations", json=payload).status_code == 422


def test_validation_non_positive_power():
    payload = {
        "capacities": {"A": 10, "B": 10, "C": 10},
        "devices": [{"id": "D1", "power": 0, "allowed_phases": ["A"]}],
    }
    assert client.post("/api/v1/calculations", json=payload).status_code == 422


def test_validation_invalid_phase():
    payload = {
        "capacities": {"A": 10, "B": 10, "C": 10},
        "devices": [{"id": "D1", "power": 5, "allowed_phases": ["D"]}],
    }
    assert client.post("/api/v1/calculations", json=payload).status_code == 422


def test_allowed_phases_deduplicated():
    payload = {
        "capacities": {"A": 10, "B": 10, "C": 10},
        "devices": [{"id": "D1", "power": 5, "allowed_phases": ["C", "A", "C"]}],
    }
    resp = client.post("/api/v1/calculations", json=payload)
    assert resp.status_code == 201
    detail = client.get(f"/api/v1/calculations/{resp.json()['id']}").json()
    assert detail["devices"][0]["allowed_phases"] == ["A", "C"]


def test_health():
    assert client.get("/health").json() == {"status": "ok"}
