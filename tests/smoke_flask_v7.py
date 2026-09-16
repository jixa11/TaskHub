# -*- coding: utf-8 -*-
"""Dependency-level smoke test for route registration and empty-data pages.

Run with the same environment used to build the application.  The fake
connection is deliberately read-only: this validates Flask wiring, auth,
parameter counts, empty database handling, and both report renderers without
touching a real SQL Server or its connection configuration.
"""
import datetime
import io
import pathlib
import sys
import types


from _paths import ROOT, SRC, project_file  # noqa: E402
sys.modules['pyodbc'] = types.SimpleNamespace(connect=lambda *a, **k: None)

import taskhub  # noqa: E402


class FakeCursor:
    def __init__(self):
        self.sql = ''
        self.params = ()
        self.description = None
        self.rowcount = 0

    def execute(self, sql, *params):
        if len(params) == 1 and isinstance(params[0], (list, tuple)):
            params = tuple(params[0])
        assert sql.count('?') == len(params), (sql[:120], sql.count('?'), len(params))
        self.sql = sql
        self.params = params
        self.description = None
        if 'SELECT id FROM Contracts WHERE id=? AND is_active=1' in sql:
            self.description = [('id',)]
        elif 'SELECT id,project_id FROM Contracts WHERE id=? AND is_active=1' in sql:
            self.description = [('id',), ('project_id',)]
        elif 'SELECT id,contract_id,business_status' in sql:
            self.description = [('id',), ('contract_id',), ('business_status',)]
        elif 'SELECT 1 AS ok' in sql and 'ContractProjectTeams' in sql:
            self.description = [('ok',)]
        elif 'SELECT id FROM ProjectTeams WHERE project_id=?' in sql:
            self.description = [('id',)]
        elif 'SELECT pt.id,pt.team_id FROM ProjectTeams pt' in sql:
            self.description = [('id',), ('team_id',)]
        elif 'SELECT project_team_id FROM ContractProjectTeams' in sql:
            self.description = [('project_team_id',)]
        elif ('SELECT pt.id,pt.team_id' in sql
              and 'FROM ContractProjectTeams' in sql):
            self.description = [('id',), ('team_id',)]
        elif 'SELECT project_id,project_team_id,created_by,staff_id' in sql:
            self.description = [('project_id',), ('project_team_id',),
                                ('created_by',), ('staff_id',)]
        elif 'SELECT id FROM FileBlobs WHERE sha256=?' in sql:
            self.description = [('id',)]
        elif 'SELECT e.*,et.name AS extension_type_name' in sql:
            self.description = [('id',), ('row_version',), ('title',),
                                ('extension_type_name',), ('contract_title',)]
        elif 'SELECT s.*,st.name AS statement_type_name' in sql:
            self.description = [('id',), ('row_version',), ('title',),
                                ('statement_type_name',), ('contract_title',)]
        elif 'SELECT TOP 1 id,jalali_year,title,annual_target,version_no' in sql:
            self.description = [('id',), ('jalali_year',), ('title',),
                                ('annual_target',), ('version_no',)]
        elif ('SELECT business_status,requested_without_vat' in sql
              and 'AS scope_percent' in sql):
            self.description = [('business_status',), ('requested_without_vat',),
                                ('requested_price',), ('confirmed_without_vat',),
                                ('confirmed_price',), ('sent_at',),
                                ('employer_decision_at',), ('statement_date',),
                                ('scope_percent',)]
        elif 'SELECT s.id,s.contract_id,s.title,s.statement_number' in sql:
            self.description = [('id',), ('contract_id',), ('title',),
                                ('statement_number',), ('statement_date',),
                                ('statement_date_fa',), ('period_year',),
                                ('period_month',), ('business_status',),
                                ('requested_price',), ('requested_without_vat',),
                                ('confirmed_price',), ('confirmed_without_vat',),
                                ('sent_at',), ('employer_decision_at',),
                                ('statement_type_name',), ('contract_title',),
                                ('contract_number',), ('project_id',),
                                ('project_name',), ('project_type_id',),
                                ('project_type_name',), ('city_id',), ('city_name',),
                                ('scope_percent',)]
        elif 'SELECT cst.statement_id,cst.project_team_id' in sql:
            self.description = [('statement_id',), ('project_team_id',),
                                ('allocation_percent',), ('team_id',),
                                ('team_name',)]
        elif 'SELECT project_team_id,allocation_percent' in sql:
            self.description = [('project_team_id',), ('allocation_percent',)]
        elif 'SELECT id FROM ProjectTypes WHERE id=?' in sql:
            self.description = [('id',)]
        elif 'AS sent_count' in sql and 'AS approved_count' in sql:
            self.description = [('sent_amount',), ('approved_amount',),
                                ('sent_count',), ('approved_count',)]
        self.rowcount = 0
        return self

    def fetchone(self):
        if 'FROM Sessions s JOIN Users u' in self.sql:
            token = str(self.params[0]) if self.params else 'role:admin'
            role = token.split(':', 1)[1] if token.startswith('role:') else 'admin'
            project_id = 1 if role == 'employer' else None
            return (1, role, role, 'کاربر تست', project_id, None, None, 1,
                    datetime.datetime.now() + datetime.timedelta(hours=1))
        if self.sql.strip().upper() == 'SELECT 1':
            return (1,)
        if 'OUTPUT INSERTED.id' in self.sql:
            return (101,)
        if 'SELECT id FROM Contracts WHERE id=? AND is_active=1' in self.sql:
            return (1,)
        if 'SELECT id,project_id FROM Contracts WHERE id=? AND is_active=1' in self.sql:
            return (1, 1)
        if 'SELECT id,contract_id,business_status' in self.sql:
            return (12, 1, 'employer_approved')
        if 'SELECT 1 AS ok' in self.sql and 'ContractProjectTeams' in self.sql:
            return (1,)
        if 'SELECT id FROM ProjectTeams WHERE project_id=?' in self.sql:
            return (1,)
        if 'SELECT pt.id,pt.team_id FROM ProjectTeams pt' in self.sql:
            return (1, 1)
        if 'SELECT project_team_id FROM ContractProjectTeams' in self.sql:
            return (1,)
        if ('SELECT pt.id,pt.team_id' in self.sql
                and 'FROM ContractProjectTeams' in self.sql):
            return (1, 1)
        if 'SELECT project_id,project_team_id,created_by,staff_id' in self.sql:
            return (1, 1, 1, 1)
        if 'SELECT id FROM FileBlobs WHERE sha256=?' in self.sql:
            return (9,)
        if 'SELECT ISNULL(MAX(version_no),0)+1 FROM Attachments' in self.sql:
            return (1,)
        if 'SELECT TOP 1 id,jalali_year,title,annual_target,version_no' in self.sql:
            return (1, 1405, 'هدف تست', 36000000000, 1)
        if 'SELECT id FROM ProjectTypes WHERE id=?' in self.sql:
            return (1,)
        if 'AS sent_count' in self.sql and 'AS approved_count' in self.sql:
            return (6000000000, 3000000000, 2, 1)
        return None

    def fetchall(self):
        if 'SELECT e.*,et.name AS extension_type_name' in self.sql:
            return [(11, b'\x00\x01', 'الحاقیه تست', 'الحاقیه زمانی قرارداد', 'قرارداد تست')]
        if 'SELECT s.*,st.name AS statement_type_name' in self.sql:
            return [(12, b'\x00\x02', 'صورت وضعیت تست', 'صورت وضعیت موقت', 'قرارداد تست')]
        if ('SELECT business_status,requested_without_vat' in self.sql
                and 'AS scope_percent' in self.sql):
            now = datetime.datetime.now()
            return [('employer_approved', 6000000000, 6600000000,
                     3000000000, 3300000000, now, now, now.date(), 100)]
        if 'SELECT s.id,s.contract_id,s.title,s.statement_number' in self.sql:
            now = datetime.datetime.now()
            return [(12, 1, 'صورت وضعیت تست', 'S-1', now.date(), '1405/04/31',
                     1405, 4, 'employer_approved', 6600000000, 6000000000,
                     3300000000, 3000000000, now, now, 'صورت وضعیت موقت',
                     'قرارداد تست', 'C-1', 1, 'پروژه تست', 1, 'CMS', 1, 'تهران',
                     100)]
        if 'SELECT cst.statement_id,cst.project_team_id' in self.sql:
            return [(12, 1, 100, 1, 'تیم تست')]
        if 'SELECT project_team_id,allocation_percent' in self.sql:
            return [(1, 100)]
        return []


class FakeConnection:
    def cursor(self):
        return FakeCursor()

    def commit(self):
        pass

    def close(self):
        pass


def main():
    taskhub._conn = FakeConnection()
    rules = list(taskhub.flask_app.url_map.iter_rules())
    paths = [str(x) for x in rules]
    assert len(paths) == len(set(paths)), 'duplicate Flask route'

    client = taskhub.flask_app.test_client()
    assert client.get('/').status_code == 200
    assert client.get('/assets/v7_ui.js').status_code == 200
    assert client.get('/assets/v7_ui.css').status_code == 200
    headers = {'X-Token': 'smoke'}
    roles = ('admin', 'manager', 'planner', 'finance', 'reporter',
             'support', 'supervisor', 'employer')
    for role in roles:
        response = client.post('/api/core_data', json={}, headers={'X-Token': 'role:' + role})
        assert response.status_code == 200, (role, response.status_code, response.data[:300])
        result = response.get_json()
        assert result.get('ok') is True and isinstance(result.get('tasks'), list), (role, result)

    for endpoint, payload in [
        ('/api/core_data', {}), ('/api/users', {}), ('/api/contracts', {}),
        ('/api/contract_lookups', {}), ('/api/extensions', {}),
        ('/api/statements', {}), ('/api/financial_plan', {'year': 1405}),
        ('/api/financial_dashboard', {}),
        ('/api/project_financial_report', {'year': 1405}),
        ('/api/project_work_report', {}), ('/api/dashboard_reports', {}),
        ('/api/contract_recommendations', {}), ('/api/storage_stats', {}),
    ]:
        response = client.post(endpoint, json=payload, headers=headers)
        assert response.status_code == 200, (endpoint, response.status_code, response.data[:300])
        result = response.get_json()
        assert result.get('ok') is True, (endpoint, result)
        if endpoint in ('/api/extensions', '/api/statements'):
            assert result['rows'][0]['row_version'] in ('0001', '0002'), (endpoint, result)
        if endpoint == '/api/financial_dashboard':
            assert int(result['plan']['annual_target']) == 36000000000
            assert int(result['sent_amount']) == 6000000000 and result['approved_count'] == 1
        if endpoint == '/api/project_financial_report':
            assert int(result['totals']['sent_amount']) == 6000000000, result
            assert int(result['totals']['approved_amount']) == 3000000000, result
            assert result['types'][0]['project_type_name'] == 'CMS', result

    for endpoint, payload in [
        ('/api/master_save', {'kind': 'project', 'name': 'پروژه تست',
                              'city_id': 1, 'project_type_id': 1}),
        ('/api/task_save', {'title': 'تست', 'project_id': 1, 'project_team_id': 1}),
        ('/api/contract_save', {'title': 'قرارداد تست'}),
        ('/api/extension_save', {'contract_id': 1, 'title': 'تمدید تست',
                                 'extension_type_id': 1, 'end_date': '2027-01-01'}),
        ('/api/statement_save', {'contract_id': 1, 'statement_type_id': 1,
                                 'statement_number': 'S-1', 'title': 'صورت وضعیت تست',
                                 'requested_without_vat': 100, 'project_team_id': 1}),
        ('/api/financial_plan_save', {'year': 1405, 'annual_target': 36000000000,
                                      'title': 'هدف تست'}),
    ]:
        response = client.post(endpoint, json=payload, headers=headers)
        assert response.status_code == 200, (endpoint, response.status_code, response.data[:300])
        result = response.get_json()
        assert result.get('ok') is True, (endpoint, result)
        if endpoint in ('/api/contract_save', '/api/extension_save', '/api/statement_save'):
            assert result.get('id') == 101, (endpoint, result)

    response = client.post('/api/master_save', json={'kind': 'project', 'name': 'بدون نوع',
                           'city_id': 1}, headers=headers)
    assert response.status_code == 200 and response.get_json().get('ok') is False

    response = client.post('/api/statement_save', json={
        'contract_id': 1, 'statement_type_id': 1,
        'statement_number': 'S-JOINT', 'title': 'صورت وضعیت مشترک',
        'requested_without_vat': 100,
        'statement_teams': [
            {'project_team_id': 1, 'allocation_percent': 60},
            {'project_team_id': 2, 'allocation_percent': 40},
        ],
    }, headers=headers)
    assert response.status_code == 200 and response.get_json().get('ok') is True
    response = client.post('/api/statement_save', json={
        'contract_id': 1, 'statement_type_id': 1,
        'statement_number': 'S-BAD', 'title': 'تقسیم نامعتبر',
        'statement_teams': [
            {'project_team_id': 1, 'allocation_percent': 60},
            {'project_team_id': 2, 'allocation_percent': 30},
        ],
    }, headers=headers)
    assert response.status_code == 200 and response.get_json().get('ok') is False
    response = client.post('/api/statement_teams_save', json={
        'id': 12,
        'statement_teams': [
            {'project_team_id': 1, 'allocation_percent': 55},
            {'project_team_id': 2, 'allocation_percent': 45},
        ],
    }, headers=headers)
    assert response.status_code == 200 and response.get_json().get('ok') is True

    # Permission checks are enforced by the server, not merely hidden buttons.
    finance_headers = {'X-Token': 'role:finance'}
    planner_headers = {'X-Token': 'role:planner'}
    support_headers = {'X-Token': 'role:support'}
    assert client.post('/api/master_save', json={'kind': 'city', 'name': 'غیرمجاز'},
                       headers=finance_headers).status_code == 403
    assert client.post('/api/contract_save', json={'title': 'مجاز برای مالی'},
                       headers=finance_headers).get_json().get('ok') is True
    assert client.post('/api/contract_save', json={'title': 'غیرمجاز برای پلنر'},
                       headers=planner_headers).status_code == 403
    assert client.post('/api/project_financial_report', json={},
                       headers=planner_headers).get_json().get('ok') is True
    assert client.post('/api/project_financial_report', json={},
                       headers=support_headers).status_code == 403
    assert client.post('/api/project_work_report', json={'user_id': 999},
                       headers=support_headers).get_json().get('filters', {}).get('user_id') == 1

    for kind in ('contracts', 'extensions', 'statements', 'plans', 'attachments',
                 'project_revenue', 'work_share'):
        response = client.post('/api/v7_export', json={'kind': kind, 'format': 'xlsx'}, headers=headers)
        assert response.status_code == 200, (kind, response.data[:300])
        assert len(response.data) > 1000, kind
    response = client.post('/api/v7_export', json={'kind': 'contracts', 'format': 'pdf'}, headers=headers)
    assert response.status_code == 200 and response.data.startswith(b'%PDF')

    from PIL import Image
    raw = io.BytesIO(); Image.new('RGB', (2400, 1800), '#4477aa').save(raw, 'JPEG', quality=95); raw.seek(0)
    response = client.post('/api/attachment_upload', data={
        'entity_type': 'task', 'entity_id': '1', 'caption': 'نمونه',
        'file': (raw, 'guide.jpg', 'image/jpeg')}, headers=headers,
        content_type='multipart/form-data')
    result = response.get_json()
    assert response.status_code == 200 and result.get('ok') is True, result
    assert result.get('deduplicated') is True and result.get('size', 0) > 0
    print('flask_smoke_ok routes=%d role_core=%d writes=8 validation_rejections=2 permissions=6 exports=8 image_upload=1' %
          (len(rules), len(roles)))


if __name__ == '__main__':
    main()
