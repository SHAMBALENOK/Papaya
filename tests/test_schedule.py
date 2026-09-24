"""Фаза 2 «Этапы и даты»: вычисление статусов и валидация расписания.

Первый блок — юнит-тесты app/core/schedule.py с фиксированным ``now``, чтобы
статусы не зависели от «реального» времени запуска прогона. Второй блок —
API-контракт: создание/правка олимпиады с расписанием (JSONB), вычисленные
поля в ответе и 422-валидации.
"""

from datetime import datetime, timedelta, timezone

from app.core.schedule import (
    compute_schedule_state,
    enrich_olympiad,
    stage_status,
)
from tests.conftest import promote_role, register_user

NOW = datetime(2026, 2, 10, 12, 0, tzinfo=timezone.utc)


def _stage(type_, start, end=None, **extra):
    base = {
        'id': type_.lower(),
        'name': type_,
        'type': type_,
        'start_at': start,
        'end_at': end,
    }
    base.update(extra)
    return base


def _iso(days):
    return (NOW + timedelta(days=days)).isoformat()


def _rel(days):
    """ISO-строка относительно текущего времени (для API-тестов)."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


class TestStageStatus:
    def test_upcoming(self):
        stage = _stage('REGISTRATION', _iso(30), _iso(45))
        assert stage_status(stage, NOW) == 'UPCOMING'

    def test_active(self):
        stage = _stage('QUALIFICATION', _iso(-2), _iso(3))
        assert stage_status(stage, NOW) == 'ACTIVE'

    def test_finished(self):
        stage = _stage('QUALIFICATION', _iso(-20), _iso(-10))
        assert stage_status(stage, NOW) == 'FINISHED'

    def test_results_without_end_finished_after_start(self):
        """Этап «Результаты» без end_at завершается сразу после start_at."""
        stage = _stage('RESULTS', _iso(-1))
        assert stage_status(stage, NOW) == 'FINISHED'

    def test_results_without_end_upcoming(self):
        stage = _stage('RESULTS', _iso(5))
        assert stage_status(stage, NOW) == 'UPCOMING'

    def test_naive_datetime_is_invalid(self):
        stage = {'start_at': '2026-09-01T00:00:00'}
        assert stage_status(stage, NOW) is None

    def test_missing_start_is_invalid(self):
        stage = {'id': 'x', 'name': 'x', 'type': 'QUALIFICATION'}
        assert stage_status(stage, NOW) is None


class TestComputeScheduleState:
    def test_registration_active(self):
        schedule = {
            'season': '2026/27',
            'stages': [
                _stage('REGISTRATION', _iso(-5), _iso(5)),
                _stage('QUALIFICATION', _iso(10), _iso(20)),
            ],
        }
        state = compute_schedule_state(schedule, NOW)
        assert state['current_status'] == 'REGISTRATION_OPEN'
        assert state['current_stage']['id'] == 'registration'
        assert state['stages'][0]['status'] == 'ACTIVE'
        assert state['stages'][1]['status'] == 'UPCOMING'
        # Ближайший дедлайн — конец открытой регистрации.
        assert state['next_deadline'] == _iso(5)

    def test_qualification_active(self):
        schedule = {
            'stages': [
                _stage('REGISTRATION', _iso(-30), _iso(-20)),
                _stage('QUALIFICATION', _iso(-3), _iso(3)),
            ],
        }
        state = compute_schedule_state(schedule, NOW)
        assert state['current_status'] == 'QUALIFICATION'
        assert state['current_stage']['id'] == 'qualification'
        assert state['next_deadline'] == _iso(3)

    def test_overlap_priority_final_wins(self):
        """При активных Регистрации и Финале статус — FINAL (приоритет типа)."""
        schedule = {
            'stages': [
                _stage('REGISTRATION', _iso(-10), _iso(10)),
                _stage('FINAL', _iso(-1), _iso(5)),
            ],
        }
        state = compute_schedule_state(schedule, NOW)
        assert state['current_status'] == 'FINAL'
        assert state['current_stage']['id'] == 'final'

    def test_all_upcoming_is_registration_closed(self):
        """Ничего не идёт, но этапы есть — регистрация ещё не открыта."""
        schedule = {
            'stages': [
                _stage('REGISTRATION', _iso(10), _iso(20)),
                _stage('QUALIFICATION', _iso(25)),
            ],
        }
        state = compute_schedule_state(schedule, NOW)
        assert state['current_status'] == 'REGISTRATION_CLOSED'
        assert state['current_stage'] is None
        assert state['next_deadline'] == _iso(10)

    def test_all_finished(self):
        schedule = {
            'stages': [
                _stage('REGISTRATION', _iso(-40), _iso(-30)),
                _stage('QUALIFICATION', _iso(-20), _iso(-10)),
                _stage('FINAL', _iso(-8), _iso(-3)),
                _stage('RESULTS', _iso(-2)),
            ],
        }
        state = compute_schedule_state(schedule, NOW)
        assert state['current_status'] == 'FINISHED'
        assert state['current_stage'] is None
        assert state['next_deadline'] is None
        assert all(s['status'] == 'FINISHED' for s in state['stages'])

    def test_empty_stages(self):
        state = compute_schedule_state({'season': '2026/27', 'stages': []}, NOW)
        assert state['current_status'] is None
        assert state['current_stage'] is None
        assert state['next_deadline'] is None

    def test_results_active(self):
        schedule = {
            'stages': [
                _stage('REGISTRATION', _iso(-40), _iso(-30)),
                _stage('RESULTS', _iso(-1), _iso(2)),
            ],
        }
        state = compute_schedule_state(schedule, NOW)
        assert state['current_status'] == 'RESULTS'


class TestEnrichOlympiad:
    def test_enriches_with_schedule(self):
        oly = {
            'id': '1',
            'schedule': {
                'season': '2026/27',
                'stages': [_stage('REGISTRATION', _iso(-5), _iso(5))],
            },
        }
        out = enrich_olympiad(oly, NOW)
        assert out['current_status'] == 'REGISTRATION_OPEN'
        assert out['current_stage']['id'] == 'registration'
        assert out['next_deadline'] == _iso(5)
        assert out['schedule']['stages'][0]['status'] == 'ACTIVE'

    def test_backward_compat_null_schedule(self):
        oly = {'id': '2', 'schedule': None}
        out = enrich_olympiad(oly, NOW)
        assert out['schedule'] is None
        assert out['current_status'] is None
        assert out['current_stage'] is None
        assert out['next_deadline'] is None

    def test_backward_compat_missing_schedule(self):
        oly = {'id': '3'}
        out = enrich_olympiad(oly, NOW)
        assert out['schedule'] is None
        assert out['current_status'] is None

    def test_backward_compat_bad_schedule_shape(self):
        oly = {'id': '4', 'schedule': {'season': '2026/27'}}  # без stages
        out = enrich_olympiad(oly, NOW)
        assert out['schedule'] is None
        assert out['current_status'] is None


class TestScheduleApi:
    async def _create_admin(self, client, email):
        user = await register_user(client, email=email)
        await promote_role(user['id'], 'ADMIN')
        return user

    def _schedule_payload(self):
        return {
            'season': '2026/27',
            'stages': [
                {
                    'id': 'registration_1',
                    'name': 'Регистрация',
                    'type': 'REGISTRATION',
                    'start_at': _rel(-10),
                    'end_at': _rel(10),
                },
                {
                    'id': 'qualification_2',
                    'name': 'Отборочный этап',
                    'type': 'QUALIFICATION',
                    'start_at': _rel(15),
                    'end_at': _rel(25),
                },
            ],
        }

    async def test_create_with_schedule(self, client):
        await self._create_admin(client, 'sched_admin@example.com')
        response = await client.post(
            '/api/v1/olympiads',
            json={'name': 'Олимпиада с этапами', 'schedule': self._schedule_payload()},
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data['schedule']['season'] == '2026/27'
        assert len(data['schedule']['stages']) == 2
        statuses = {s['status'] for s in data['schedule']['stages']}
        assert statuses == {'ACTIVE', 'UPCOMING'}
        assert data['current_status'] == 'REGISTRATION_OPEN'

    async def test_get_returns_computed_fields(self, client):
        await self._create_admin(client, 'sched_get@example.com')
        created = await client.post(
            '/api/v1/olympiads',
            json={'name': 'С этапами', 'schedule': self._schedule_payload()},
        )
        oly_id = created.json()['id']
        response = await client.get(f'/api/v1/olympiads/{oly_id}')
        assert response.status_code == 200
        data = response.json()
        assert data['current_stage']['id'] == 'registration_1'
        assert data['next_deadline']

    async def test_update_schedule(self, client):
        await self._create_admin(client, 'sched_upd@example.com')
        created = await client.post(
            '/api/v1/olympiads',
            json={'name': 'Обновление расписания'},
        )
        oly_id = created.json()['id']
        response = await client.patch(
            f'/api/v1/olympiads/{oly_id}',
            json={'schedule': self._schedule_payload()},
        )
        assert response.status_code == 200
        assert response.json()['schedule']['season'] == '2026/27'

    async def test_clear_schedule_by_sending_null(self, client):
        await self._create_admin(client, 'sched_clear@example.com')
        created = await client.post(
            '/api/v1/olympiads',
            json={'name': 'Очистка', 'schedule': self._schedule_payload()},
        )
        oly_id = created.json()['id']
        response = await client.patch(
            f'/api/v1/olympiads/{oly_id}',
            json={'schedule': None},
        )
        assert response.status_code == 200
        data = response.json()
        assert data['schedule'] is None
        assert data['current_status'] is None

    async def test_naive_datetime_is_422(self, client):
        await self._create_admin(client, 'sched_naive@example.com')
        schedule = self._schedule_payload()
        schedule['stages'][0]['start_at'] = '2026-09-01T00:00:00'
        response = await client.post(
            '/api/v1/olympiads',
            json={'name': 'Naive', 'schedule': schedule},
        )
        assert response.status_code == 422

    async def test_start_after_end_is_422(self, client):
        await self._create_admin(client, 'sched_range@example.com')
        schedule = self._schedule_payload()
        schedule['stages'][0]['start_at'] = _rel(10)
        schedule['stages'][0]['end_at'] = _rel(-10)
        response = await client.post(
            '/api/v1/olympiads',
            json={'name': 'Range', 'schedule': schedule},
        )
        assert response.status_code == 422
        assert 'start_at must not be later than end_at' in response.text

    async def test_unknown_stage_type_is_422(self, client):
        await self._create_admin(client, 'sched_type@example.com')
        schedule = self._schedule_payload()
        schedule['stages'][0]['type'] = 'OLYMPIAD'
        response = await client.post(
            '/api/v1/olympiads',
            json={'name': 'Type', 'schedule': schedule},
        )
        assert response.status_code == 422

    async def test_duplicate_stage_ids_is_422(self, client):
        await self._create_admin(client, 'sched_dup@example.com')
        schedule = self._schedule_payload()
        schedule['stages'][1]['id'] = 'registration_1'
        response = await client.post(
            '/api/v1/olympiads',
            json={'name': 'Dup', 'schedule': schedule},
        )
        assert response.status_code == 422
        assert 'duplicate stage id' in response.text

    async def test_old_olympiad_without_schedule_still_works(self, client):
        await self._create_admin(client, 'sched_old@example.com')
        created = await client.post(
            '/api/v1/olympiads',
            json={'name': 'Старая олимпиада'},
        )
        assert created.status_code == 201
        data = created.json()
        assert data['schedule'] is None
        assert data['current_status'] is None
        listed = await client.get('/api/v1/olympiads')
        assert listed.status_code == 200
        match = [o for o in listed.json() if o['id'] == data['id']]
        assert match