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

    def test_results_without_end_active_on_publication_day(self):
        """«Результаты» без end_at активны в день публикации (до конца суток)."""
        stage = _stage('RESULTS', _iso(0))
        assert stage_status(stage, NOW) == 'ACTIVE'

    def test_results_without_end_finished_after_publication_day(self):
        """После дня публикации результатов этап без end_at завершён."""
        stage = _stage('RESULTS', _iso(-1))
        assert stage_status(stage, NOW) == 'FINISHED'

    def test_results_without_end_upcoming(self):
        stage = _stage('RESULTS', _iso(5))
        assert stage_status(stage, NOW) == 'UPCOMING'

    def test_results_with_end_finished(self):
        """Результаты с явным end_at подчиняются обычным правилам интервала."""
        stage = _stage('RESULTS', _iso(-4), _iso(-1))
        assert stage_status(stage, NOW) == 'FINISHED'

    def test_open_ended_stage_without_end_is_active(self):
        """Этап без end_at (кроме RESULTS) считается длящимся, пока не конец."""
        stage = _stage('QUALIFICATION', _iso(-1))
        assert stage_status(stage, NOW) == 'ACTIVE'

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

    def test_gap_after_registration_is_registration_closed(self):
        """«Между этапами»: регистрация кончилась, следующий этап ещё впереди."""
        schedule = {
            'stages': [
                _stage('REGISTRATION', _iso(-30), _iso(-20)),
                _stage('QUALIFICATION', _iso(10)),
            ],
        }
        state = compute_schedule_state(schedule, NOW)
        assert state['current_status'] == 'REGISTRATION_CLOSED'
        assert state['current_stage'] is None
        # Ближайшая релевантная дата — старт следующего этапа.
        assert state['next_deadline'] == _iso(10)

    def test_all_upcoming_is_upcoming(self):
        """Ничего ещё не началось — регистрация «ещё не открыта», а не закрыта."""
        schedule = {
            'stages': [
                _stage('REGISTRATION', _iso(10), _iso(20)),
                _stage('QUALIFICATION', _iso(25)),
            ],
        }
        state = compute_schedule_state(schedule, NOW)
        assert state['current_status'] == 'UPCOMING'
        assert state['current_stage'] is None
        assert state['next_deadline'] == _iso(10)

    def test_single_upcoming_registration(self):
        """CASE 1: сейчас до регистрации → регистрация ещё не началась."""
        schedule = {
            'stages': [_stage('REGISTRATION', _iso(10), _iso(20))],
        }
        state = compute_schedule_state(schedule, NOW)
        assert state['current_status'] == 'UPCOMING'
        assert state['current_stage'] is None

    def test_final_active(self):
        """CASE 5: финал идёт → FINAL."""
        schedule = {
            'stages': [
                _stage('REGISTRATION', _iso(-40), _iso(-30)),
                _stage('QUALIFICATION', _iso(-20), _iso(-5)),
                _stage('FINAL', _iso(-1), _iso(3)),
            ],
        }
        state = compute_schedule_state(schedule, NOW)
        assert state['current_status'] == 'FINAL'
        assert state['current_stage']['id'] == 'final'
        assert state['next_deadline'] == _iso(3)

    def test_results_publication_day_active(self):
        """CASE 6: день публикации результатов (без end_at) → RESULTS."""
        schedule = {
            'stages': [
                _stage('REGISTRATION', _iso(-40), _iso(-30)),
                _stage('QUALIFICATION', _iso(-20), _iso(-10)),
                _stage('FINAL', _iso(-8), _iso(-3)),
                _stage('RESULTS', _iso(0)),
            ],
        }
        state = compute_schedule_state(schedule, NOW)
        assert state['current_status'] == 'RESULTS'
        assert state['current_stage']['id'] == 'results'

    def test_overlap_same_type_first_in_array_wins(self):
        """Два активных этапа одного типа — побеждает первый в массиве."""
        schedule = {
            'stages': [
                _stage('QUALIFICATION', _iso(-2), _iso(2)),
                _stage('QUALIFICATION', _iso(-1), _iso(1)),
            ],
        }
        state = compute_schedule_state(schedule, NOW)
        assert state['current_stage']['id'] == 'qualification'
        assert state['current_status'] == 'QUALIFICATION'

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


class TestNextDeadline:
    """next_deadline — ближайшая РЕЛЕВАНТНАЯ будущая дата, без прошедших."""

    def test_before_first_stage_returns_stage_start(self):
        schedule = {
            'stages': [
                _stage('REGISTRATION', _iso(10), _iso(20)),
                _stage('QUALIFICATION', _iso(25), _iso(35)),
            ],
        }
        state = compute_schedule_state(schedule, NOW)
        assert state['next_deadline'] == _iso(10)

    def test_during_stage_returns_stage_end(self):
        schedule = {
            'stages': [
                _stage('REGISTRATION', _iso(-40), _iso(-30)),
                _stage('QUALIFICATION', _iso(-2), _iso(3)),
            ],
        }
        state = compute_schedule_state(schedule, NOW)
        assert state['next_deadline'] == _iso(3)

    def test_between_stages_returns_next_start(self):
        schedule = {
            'stages': [
                _stage('REGISTRATION', _iso(-30), _iso(-20)),
                _stage('RESULTS', _iso(10)),
            ],
        }
        state = compute_schedule_state(schedule, NOW)
        assert state['next_deadline'] == _iso(10)

    def test_all_finished_returns_none(self):
        schedule = {
            'stages': [
                _stage('QUALIFICATION', _iso(-20), _iso(-10)),
                _stage('RESULTS', _iso(-2)),
            ],
        }
        state = compute_schedule_state(schedule, NOW)
        assert state['next_deadline'] is None

    def test_upcoming_only_never_past_dates(self):
        """Из all-upcoming берётся старт первого этапа, а не его конец."""
        schedule = {
            'stages': [
                _stage('REGISTRATION', _iso(10), _iso(20)),
                _stage('QUALIFICATION', _iso(25), _iso(35)),
            ],
        }
        state = compute_schedule_state(schedule, NOW)
        deadline = state['next_deadline']
        assert deadline == _iso(10)


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

    def test_upcoming_schedule_enriched(self):
        oly = {
            'id': '5',
            'schedule': {
                'season': '2026/27',
                'stages': [_stage('REGISTRATION', _iso(10), _iso(20))],
            },
        }
        out = enrich_olympiad(oly, NOW)
        assert out['current_status'] == 'UPCOMING'
        assert out['current_stage'] is None
        assert out['next_deadline'] == _iso(10)

    def test_results_publication_day_enriched(self):
        oly = {
            'id': '6',
            'schedule': {
                'stages': [_stage('RESULTS', _iso(0))],
            },
        }
        out = enrich_olympiad(oly, NOW)
        assert out['current_status'] == 'RESULTS'

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

    async def test_all_upcoming_schedule_status_via_api(self, client):
        """CASE 1 через API: регистрация в будущем → UPCOMING, не CLOSED."""
        await self._create_admin(client, 'sched_pre@example.com')
        schedule = {
            'season': '2026/27',
            'stages': [
                {
                    'id': 'registration_1',
                    'name': 'Регистрация',
                    'type': 'REGISTRATION',
                    'start_at': _rel(10),
                    'end_at': _rel(20),
                },
                {
                    'id': 'qualification_2',
                    'name': 'Отборочный этап',
                    'type': 'QUALIFICATION',
                    'start_at': _rel(25),
                    'end_at': _rel(35),
                },
            ],
        }
        created = await client.post(
            '/api/v1/olympiads',
            json={'name': 'До регистрации', 'schedule': schedule},
        )
        assert created.status_code == 201
        data = created.json()
        assert data['current_status'] == 'UPCOMING'
        assert data['current_stage'] is None
        # Повторный GET после записи (кэш/PATCH-цикл) отдаёт тот же статус.
        again = await client.get(f"/api/v1/olympiads/{data['id']}")
        assert again.status_code == 200
        assert again.json()['current_status'] == 'UPCOMING'

    async def test_results_publication_day_via_api(self, client):
        """CASE 6 через API: «Результаты» без end_at в день публикации → RESULTS."""
        await self._create_admin(client, 'sched_res@example.com')
        schedule = {
            'stages': [
                {
                    'id': 'results_1',
                    'name': 'Результаты',
                    'type': 'RESULTS',
                    # Старт сегодня (текущий момент) — день публикации ещё идёт.
                    'start_at': datetime.now(timezone.utc).isoformat(),
                },
            ],
        }
        created = await client.post(
            '/api/v1/olympiads',
            json={'name': 'Результаты опубликованы', 'schedule': schedule},
        )
        assert created.status_code == 201
        data = created.json()
        assert data['current_status'] == 'RESULTS'
        assert data['current_stage']['id'] == 'results_1'
        assert data['schedule']['stages'][0]['status'] == 'ACTIVE'

    async def test_patch_schedule_persists_and_reload_keeps_dates(self, client):
        """Правится дата этапа → данные сохраняются между GET-запросами."""
        await self._create_admin(client, 'sched_persist@example.com')
        schedule = {
            'season': '2026/27',
            'stages': [
                {
                    'id': 'registration_1',
                    'name': 'Регистрация',
                    'type': 'REGISTRATION',
                    'start_at': _rel(10),
                    'end_at': _rel(20),
                },
                {
                    'id': 'qualification_2',
                    'name': 'Отборочный этап',
                    'type': 'QUALIFICATION',
                    'start_at': _rel(25),
                    'end_at': _rel(35),
                },
            ],
        }
        created = await client.post(
            '/api/v1/olympiads',
            json={'name': 'Персистентность', 'schedule': schedule},
        )
        oly_id = created.json()['id']

        # Меняем даты и удаляем первый этап (как в frontend-редакторе).
        updated_schedule = {
            'season': '2026/27',
            'stages': [
                {
                    'id': 'qualification_2',
                    'name': 'Отборочный этап',
                    'type': 'QUALIFICATION',
                    'start_at': _rel(30),
                    'end_at': _rel(40),
                },
            ],
        }
        patched = await client.patch(
            f'/api/v1/olympiads/{oly_id}',
            json={'schedule': updated_schedule},
        )
        assert patched.status_code == 200
        patched_stages = patched.json()['schedule']['stages']
        assert len(patched_stages) == 1
        # Дата сдвинулась на 30 дней вперёд (сверка по дню, без дрейфа микросекунд).
        assert patched_stages[0]['start_at'].startswith(_rel(30)[:10])

        # «Перезагрузка»: свежий GET отдаёт сохранённые даты (без дрейфа секунд).
        reloaded = await client.get(f'/api/v1/olympiads/{oly_id}')
        assert reloaded.status_code == 200
        stages = reloaded.json()['schedule']['stages']
        assert len(stages) == 1
        assert stages[0]['start_at'] == patched_stages[0]['start_at']
        assert stages[0]['end_at'] == patched_stages[0]['end_at']