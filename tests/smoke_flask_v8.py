# -*- coding: utf-8 -*-
"""Dependency-level smoke test for the v8 team/report/E2EE API surface.

The fake SQL connection validates placeholder counts and route control flow
without touching the configured SQL Server or its connection string.
"""
import hashlib
import io
import pathlib
import sys


from _paths import ROOT, SRC, project_file  # noqa: E402

from smoke_flask_v7 import FakeConnection, FakeCursor, taskhub  # noqa: E402


class V8Cursor(FakeCursor):
    def execute(self, sql, *params):
        super().execute(sql, *params)
        if "SELECT TOP 1 id,jalali_year,title,annual_target" in sql:
            self.description = [
                ("id",), ("jalali_year",), ("title",), ("annual_target",),
                ("version_no",), ("status",),
            ]
        elif "SELECT 1 AS ok FROM Projects p JOIN TeamProjectTypes" in sql:
            self.description = [("ok",)]
        elif "SELECT co.id,co.project_id" in sql and "effective_price" in sql:
            self.description = [("id",), ("project_id",), ("effective_price",)]
        elif "SELECT id,team_id FROM ProjectTeams WHERE id=?" in sql:
            self.description = [("id",), ("team_id",)]
        elif "SELECT c.id,c.kind,c.title,c.team_id,c.key_version" in sql:
            self.description = [
                ("id",), ("kind",), ("title",), ("team_id",),
                ("key_version",), ("needs_key_rotation",),
                ("member_role",), ("can_post",),
            ]
        elif "SELECT d.id FROM ChatDevices d" in sql and "ChatConversationKeys" in sql:
            self.description = [("id",)]
        elif "SELECT m.id,m.sender_user_id,m.conversation_id" in sql:
            self.description = [
                ("id",), ("sender_user_id",), ("conversation_id",),
                ("created_by",),
            ]
        elif "SELECT ISNULL(SUM(annual_target),0) AS total" in sql:
            self.description = [("total",)]
        elif "SELECT key_version FROM ChatConversations" in sql:
            self.description = [("key_version",)]
        elif "SELECT COUNT(*) AS cnt FROM ChatDevices" in sql:
            self.description = [("cnt",)]
        elif "SELECT id FROM ChatDevices" in sql and "user_id=? AND is_active=1" in sql:
            self.description = [("id",)]
        elif "SELECT rotation_owner_device_id,rotation_claim_hash" in sql:
            self.description = [("rotation_owner_device_id",), ("rotation_claim_hash",)]
        elif "SELECT key_version,needs_key_rotation" in sql and "ChatConversations" in sql:
            self.description = [("key_version",), ("needs_key_rotation",)]
        return self

    def fetchone(self):
        if "SELECT TOP 1 id,jalali_year,title,annual_target" in self.sql:
            return (1, 1405, "هدف شرکت", 36_000_000_000, 1, "active")
        if "SELECT 1 AS ok FROM Projects p JOIN TeamProjectTypes" in self.sql:
            return (1,)
        if "SELECT co.id,co.project_id" in self.sql and "effective_price" in self.sql:
            return (1, 1, 1_000_000)
        if "SELECT id,team_id FROM ProjectTeams WHERE id=?" in self.sql:
            return (1, 1)
        if "SELECT c.id,c.kind,c.title,c.team_id,c.key_version" in self.sql:
            return (1, "group", "گروه تست", None, 1, 0, "owner", 1)
        if "SELECT d.id FROM ChatDevices d" in self.sql and "ChatConversationKeys" in self.sql:
            return (101,)
        if "SELECT m.id,m.sender_user_id,m.conversation_id" in self.sql:
            return (101, 1, 1, 1)
        if "SELECT ISNULL(SUM(annual_target),0) AS total" in self.sql:
            return (0,)
        if "SELECT key_version FROM ChatConversations" in self.sql:
            return (2,)
        if "SELECT COUNT(*) AS cnt FROM ChatDevices" in self.sql:
            return (0,)
        if "SELECT id FROM ChatDevices" in self.sql and "user_id=? AND is_active=1" in self.sql:
            return (101,)
        if "SELECT rotation_owner_device_id,rotation_claim_hash" in self.sql:
            return (101, hashlib.sha256(b"smoke-claim").hexdigest())
        if "SELECT key_version,needs_key_rotation" in self.sql and "ChatConversations" in self.sql:
            return (1, 0)
        return super().fetchone()

    def fetchall(self):
        if self.sql.strip() == "SELECT id FROM Teams WHERE is_active=1":
            return [(1,)]
        if "SELECT id,role FROM Users WHERE id IN" in self.sql:
            requested = sorted({int(x) for x in self.params})
            return [(x, "manager" if x == 1 else "support")
                    for x in requested]
        if "SELECT id FROM Users WHERE id IN" in self.sql:
            requested = sorted({int(x) for x in self.params})
            return [(x,) for x in requested]
        if "SELECT id FROM ProjectTypes WHERE id IN" in self.sql:
            requested = sorted({int(x) for x in self.params})
            return [(x,) for x in requested]
        if "SELECT d.id FROM ChatDevices d JOIN ChatMembers" in self.sql:
            return [(101,)]
        return super().fetchall()


class V8Connection(FakeConnection):
    def cursor(self):
        return V8Cursor()


def post(client, endpoint, payload=None, role="admin"):
    response = client.post(
        endpoint, json=payload or {}, headers={"X-Token": "role:" + role}
    )
    assert response.status_code == 200, (
        endpoint, response.status_code, response.data[:500]
    )
    result = response.get_json()
    assert result.get("ok") is True, (endpoint, result)
    return result


def main():
    taskhub._conn = V8Connection()
    client = taskhub.flask_app.test_client()
    headers = {"X-Token": "role:admin"}

    assert client.get("/assets/v8_ui.js").status_code == 200
    assert client.get("/assets/v8_ui.css").status_code == 200
    assert client.get("/manifest.webmanifest").status_code == 200
    assert client.get("/service-worker.js").status_code == 200

    # Read surfaces.
    for endpoint, payload in [
        ("/api/v8/context", {}),
        ("/api/v8/teams", {}),
        ("/api/v8/contract_teams", {"contract_id": 1}),
        ("/api/v8/team_financial_plan", {"year": 1405}),
        ("/api/v8/reports", {"kind": "dashboard"}),
        ("/api/v8/reports", {"kind": "contribution"}),
        ("/api/v8/reports", {"kind": "capacity"}),
        ("/api/v8/reports", {"kind": "shared_projects"}),
        ("/api/v8/reports", {"kind": "data_quality"}),
        ("/api/v8/chat/users", {}),
        ("/api/v8/chat/conversations", {"device_id": 101}),
        ("/api/v8/contract_task_weights", {"action": "read"}),
        ("/api/v8/financial_attribution", {}),
    ]:
        post(client, endpoint, payload)

    # Core team and finance writes.
    assert post(client, "/api/v8/team_save", {"name": "تیم تست"})["id"] == 101
    post(client, "/api/v8/team_members_save", {
        "team_id": 1,
        "members": [{"user_id": 1, "team_role": "manager"}],
    })
    post(client, "/api/v8/team_types_save", {
        "team_id": 1,
        "project_types": [{"project_type_id": 1, "assignment_role": "primary"}],
    })
    assert post(client, "/api/v8/project_team_save", {
        "project_id": 1, "team_id": 1, "is_primary": True,
    })["id"] == 101
    post(client, "/api/v8/contract_teams_save", {
        "contract_id": 1,
        "project_teams": [{"project_team_id": 1, "allocation_amount": 500_000}],
    })
    post(client, "/api/v8/team_financial_plan", {
        "action": "save", "year": 1405, "team_id": 1,
        "annual_target": 12_000_000_000,
        "periods": [
            {"month_no": x, "target_amount": 1_000_000_000,
             "allocation_mode": "amount"} for x in range(1, 13)
        ],
    })

    # Duplicate dimensions must never silently overwrite or double-count.
    invalid_payloads = [
        ("/api/v8/team_types_save", {
            "team_id": 1,
            "project_types": [
                {"project_type_id": 1, "assignment_role": "primary"},
                {"project_type_id": 1, "assignment_role": "collaborator"},
            ],
        }),
        ("/api/v8/contract_teams_save", {
            "contract_id": 1,
            "project_teams": [
                {"project_team_id": 1, "allocation_amount": 200_000},
                {"project_team_id": 1, "allocation_amount": 200_000},
            ],
        }),
        ("/api/v8/team_financial_plan", {
            "action": "save", "year": 1405, "team_id": 1,
            "annual_target": 12_000_000_000,
            "periods": [
                {"month_no": 1, "target_amount": 1_000_000_000,
                 "allocation_mode": "amount"} for _ in range(12)
            ],
        }),
        ("/api/v8/team_members_save", {
            "team_id": 1,
            "members": [
                {"user_id": 1, "team_role": "manager"},
                {"user_id": 2, "team_role": "manager"},
            ],
        }),
    ]
    for endpoint, payload in invalid_payloads:
        rejected = client.post(endpoint, json=payload, headers=headers)
        assert rejected.status_code == 200
        assert rejected.get_json().get("ok") is False

    # Export uses exactly the same report scope.
    exported = client.post(
        "/api/v8/report_export", json={"kind": "dashboard", "format": "pdf"}, headers=headers
    )
    assert exported.status_code == 200 and len(exported.data) > 1000
    attribution_pdf = client.post(
        "/api/v8/financial_attribution_export",
        json={"format": "pdf"}, headers=headers,
    )
    assert attribution_pdf.status_code == 200 and len(attribution_pdf.data) > 1000
    attribution_xlsx = client.post(
        "/api/v8/financial_attribution_export",
        json={"format": "xlsx"}, headers=headers,
    )
    assert attribution_xlsx.status_code == 200 and len(attribution_xlsx.data) > 1000

    # E2EE metadata/ciphertext routes. No plaintext or private key is sent.
    public_jwk = {"kty": "RSA", "n": "test-modulus", "e": "AQAB"}
    assert post(client, "/api/v8/chat/device", {
        "device_uuid": "smoke-device", "public_key_jwk": public_jwk,
    })["device_id"] == 101
    assert post(client, "/api/v8/chat/conversation_create", {
        "kind": "group", "title": "گروه تست", "member_ids": [2],
    })["id"] == 101
    claim = post(client, "/api/v8/chat/key_rotation_claim", {
        "conversation_id": 1, "device_id": 101,
    })
    assert claim.get("ready") is True
    post(client, "/api/v8/chat/keys_save", {
        "conversation_id": 1, "key_version": 1, "device_id": 101,
        "claim_token": "smoke-claim",
        "envelopes": [{"device_id": 101, "wrapped_key": "wrapped-only"}],
    })
    assert post(client, "/api/v8/chat/message_send", {
        "conversation_id": 1, "device_id": 101, "key_version": 1,
        "message_kind": "text", "ciphertext": "ciphertext-only",
        "iv": "nonce", "aad": "taskhub:v8:test",
        "client_message_id": "smoke-message",
    })["id"] == 101
    post(client, "/api/v8/chat/messages", {
        "conversation_id": 1, "device_id": 101,
    })
    post(client, "/api/v8/chat/read", {
        "conversation_id": 1, "message_id": 101,
    })
    post(client, "/api/v8/chat/message_delete", {"id": 101})

    before = set((ROOT / "taskhub_data" / "chat_cipher").glob("*"))
    uploaded = client.post(
        "/api/v8/chat/file_upload",
        data={
            "conversation_id": "1", "key_version": "1", "device_id": "101",
            "encrypted_meta": "smoke",
            "file": (io.BytesIO(b"encrypted-file-bytes"), "cipher.bin"),
        },
        headers=headers, content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200 and uploaded.get_json().get("ok") is True
    after = set((ROOT / "taskhub_data" / "chat_cipher").glob("*"))
    for path in after - before:
        path.unlink()

    # Server-side permission checks, not merely hidden UI.
    forbidden = client.post(
        "/api/v8/team_save", json={"name": "غیرمجاز"},
        headers={"X-Token": "role:manager"},
    )
    assert forbidden.status_code == 403
    support_dashboard = client.post(
        "/api/v8/reports", json={"kind": "dashboard"},
        headers={"X-Token": "role:support"},
    ).get_json()
    assert support_dashboard.get("financial_visible") is False
    assert "sent_amount" not in support_dashboard.get("totals", {})
    for kind in ("capacity", "shared_projects", "data_quality"):
        blocked = client.post(
            "/api/v8/reports", json={"kind": kind},
            headers={"X-Token": "role:support"},
        )
        assert blocked.status_code == 403
        blocked_export = client.post(
            "/api/v8/report_export", json={"kind": kind},
            headers={"X-Token": "role:support"},
        )
        assert blocked_export.status_code == 403
    blocked_target = client.post(
        "/api/v8/team_financial_plan", json={"year": 1405},
        headers={"X-Token": "role:support"},
    )
    assert blocked_target.status_code == 403
    blocked_attribution = client.post(
        "/api/v8/financial_attribution", json={},
        headers={"X-Token": "role:support"},
    )
    assert blocked_attribution.status_code == 403
    blocked_attribution_export = client.post(
        "/api/v8/financial_attribution_export", json={"format": "pdf"},
        headers={"X-Token": "role:support"},
    )
    assert blocked_attribution_export.status_code == 403

    print(
        "flask_v8_smoke_ok reads=13 team_writes=6 exports=3 "
        "chat_flows=9 permissions=10 validation_rejections=4"
    )


if __name__ == "__main__":
    main()
