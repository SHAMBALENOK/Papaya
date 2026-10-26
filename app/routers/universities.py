"""Каталог университетов, программы и правила льгот.

Сценарий Papaya: школьник открывает каталог, находит свой университет и видит
олимпиады с условиями льгот. Поэтому чтение каталога публично (регистрация не
нужна), а запись каталога — только у администратора. Университеты создаёт
администратор: РСОШ — источник каталога **олимпиад**, а не университетов.

Представитель университета (``EDITOR`` + ``university_id``) ведёт правила
льгот и программы **своего** университета: создаёт и правит правила,
загружает документы, публикует, смотрит историю и восстанавливает версии.
Новую олимпиаду, сезон или профиль он не создаёт (для этого есть запрос
администратору), проверку Papaya не выставляет.
"""

import logging
import uuid
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel

from app import database, schemas
from app.core import audit, deps, rate_limit
from app.database.users import ROLE_ADMIN
from app.models.benefit_rules import BENEFIT_TYPES, VERIFICATION_STATUSES
from app.routers.docs import document_file_response, store_uploaded_document

universities_page = APIRouter(
    prefix='/universities',
    tags=['universities'],
)

logger = logging.getLogger('papaya.universities')


class UniversityListItem(BaseModel):
    id: str | None = None
    name: str | None = None
    short_name: str | None = None
    description: str | None = None
    website: str | None = None
    preview_image: str | None = None
    image: str | None = None


class UniversitiesResponse(BaseModel):
    universities: List[UniversityListItem]
    # Всего вузов под фильтром — для постраничной выдачи (ТЗ §10.1).
    total: int = 0


def _serialize(university: dict) -> dict:
    return {
        'id': university.get('id'),
        'name': university.get('name'),
        'short_name': university.get('short_name'),
        'description': university.get('description'),
        'website': university.get('website'),
        'preview_image': university.get('preview_image'),
        'image': university.get('image'),
    }


@universities_page.get(
    '',
    response_model=UniversitiesResponse,
    responses={
        200: {'description': 'Каталог университетов'},
        500: {'description': 'Internal server error'},
    },
)
async def list_universities(
    search: str | None = Query(
        default=None,
        description='Поиск по названию, краткому названию и описанию',
    ),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Каталог университетов — публичное чтение без авторизации."""
    try:
        universities = await database.universities.list_universities(
            search=search,
            limit=limit,
            offset=offset,
        )
        total = await database.universities.count_universities(search=search)
        return {
            'universities': [_serialize(item) for item in universities],
            'total': total,
        }
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.get(
    '/{university_id}',
    response_model=schemas.universities.UniversityPublicResponse,
    responses={
        200: {'description': 'University details'},
        404: {'description': 'University not found'},
        500: {'description': 'Internal server error'},
    },
)
async def university_details(university_id: uuid.UUID):
    """Страница университета."""
    try:
        university = await database.universities.get_university(university_id)
        if not university:
            raise HTTPException(status_code=404, detail='University not found')
        return university
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.get(
    '/{university_id}/programs',
    response_model=schemas.programs.UniversityProgramsResponse,
    responses={
        200: {'description': 'Образовательные программы университета'},
        404: {'description': 'University not found'},
        500: {'description': 'Internal server error'},
    },
)
async def university_programs(university_id: uuid.UUID):
    """Образовательные программы университета (ТЗ §4.1).

    Список публичный: по нему видно, на какие направления вуз принимает и
    в каких областях действуют его льготы. У каждой программы — число правил,
    где она используется: такую программу нельзя удалить, не убрав из правил.
    """
    try:
        university = await database.universities.get_university(university_id)
        if not university:
            raise HTTPException(status_code=404, detail='University not found')
        programs = await database.programs.list_programs(university_id)
        return {'programs': programs, 'total': len(programs)}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.put(
    '/{university_id}/programs',
    response_model=schemas.programs.UniversityProgramsResponse,
    responses={
        200: {'description': 'Набор программ обновлён'},
        401: {'description': 'Access token missing'},
        403: {'description': 'You can only manage your own university'},
        404: {'description': 'University not found'},
        409: {'description': 'Часть программ используется в правилах и не удалена'},
        500: {'description': 'Internal server error'},
    },
)
async def update_university_programs(
    university_id: uuid.UUID,
    body: schemas.programs.UniversityProgramsUpdate,
    current_user: deps.ManageUniversity = None,
):
    """Заменить набор образовательных программ (ТЗ §4.1).

    Набор задаётся целиком. Право есть у представителя своего вуза и у
    администратора; чужие программы менять нельзя. Программы, используемые в
    правилах льгот, не удаляются — ответ 409 перечисляет их.
    """
    try:
        university = await database.universities.get_university(university_id)
        if not university:
            raise HTTPException(status_code=404, detail='University not found')
        try:
            programs = await database.programs.replace_programs(
                university_id, body.programs
            )
        except database.programs.ProgramError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        return {'programs': programs, 'total': len(programs)}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.post(
    '/{university_id}/programs',
    response_model=schemas.programs.UniversityProgramItem,
    status_code=201,
    responses={
        201: {'description': 'Программа добавлена'},
        401: {'description': 'Access token missing'},
        403: {'description': 'You can only manage your own university'},
        404: {'description': 'University not found'},
        409: {'description': 'Программа с таким названием уже есть'},
        500: {'description': 'Internal server error'},
    },
)
async def add_university_program(
    university_id: uuid.UUID,
    body: schemas.programs.UniversityProgramCreate,
    current_user: deps.ManageUniversity = None,
):
    """Добавить одну программу (из формы правила: «новая программа»)."""
    try:
        university = await database.universities.get_university(university_id)
        if not university:
            raise HTTPException(status_code=404, detail='University not found')
        program = await database.programs.add_program(
            university_id, body.name, body.description
        )
        if program is None:
            raise HTTPException(
                status_code=409, detail='Программа с таким названием уже есть'
            )
        return program
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.delete(
    '/{university_id}/programs/{program_id}',
    status_code=204,
    responses={
        204: {'description': 'Программа удалена'},
        401: {'description': 'Access token missing'},
        403: {'description': 'You can only manage your own university'},
        404: {'description': 'Программа не найдена'},
        409: {'description': 'Программа используется в правилах льгот'},
        500: {'description': 'Internal server error'},
    },
)
async def delete_university_program(
    university_id: uuid.UUID,
    program_id: uuid.UUID,
    current_user: deps.ManageUniversity = None,
):
    """Удалить программу, если на неё не ссылаются правила льгот."""
    try:
        try:
            removed = await database.programs.remove_program(university_id, program_id)
        except database.programs.ProgramError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        if not removed:
            raise HTTPException(status_code=404, detail='Program not found')
        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


# --- Видимость правил: публично — только опубликованные и не отклонённые -----


def _rule_scope(current_user, university_id, include_drafts: bool) -> dict:
    """Фильтры видимости для списков правил.

    Гость и обычный пользователь видят опубликованные правила без отклонённых.
    Черновики и архив (``include_drafts=true``) — представителю своего вуза и
    администратору; чужому — 403, а не пустой список, чтобы не маскировать
    ошибку прав.
    """
    if not include_drafts:
        return {'public_only': True}
    if not current_user:
        raise HTTPException(
            status_code=401, detail='Access token required to view drafts'
        )
    if not deps.can_manage_university(current_user, university_id):
        raise HTTPException(
            status_code=403,
            detail='You can only view drafts of your own university',
        )
    return {'public_only': False}


def _parse_statuses(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    values = [item.strip() for item in raw.split(',') if item.strip()]
    for value in values:
        if value not in schemas.benefit_rules.RULE_STATUSES:
            raise HTTPException(
                status_code=422,
                detail='status must be one of '
                + ', '.join(schemas.benefit_rules.RULE_STATUSES),
            )
    return values or None


def _validate_filters(benefit_type, verification_status) -> None:
    if benefit_type is not None and benefit_type not in BENEFIT_TYPES:
        raise HTTPException(
            status_code=422,
            detail='benefit_type must be one of ' + ', '.join(BENEFIT_TYPES),
        )
    if verification_status is not None and verification_status not in VERIFICATION_STATUSES:
        raise HTTPException(
            status_code=422,
            detail='verification_status must be one of ' + ', '.join(VERIFICATION_STATUSES),
        )


@universities_page.get(
    '/{university_id}/olympiads',
    response_model=schemas.benefit_rules.OlympiadsWithRulesResponse,
    responses={
        200: {'description': 'Олимпиады с правилами льгот в университете'},
        401: {'description': 'Access token required to view drafts'},
        403: {'description': 'Drafts are visible to own university only'},
        404: {'description': 'University not found'},
        500: {'description': 'Internal server error'},
    },
)
async def university_olympiads(
    university_id: uuid.UUID,
    include_drafts: bool = Query(
        default=False, description='Показать черновики и архив (свой вуз/админ)'
    ),
    benefit_type: str | None = Query(default=None, description='Фильтр по виду льготы'),
    subject: str | None = Query(default=None, description='Фильтр по предмету'),
    program_id: uuid.UUID | None = Query(default=None, description='Фильтр по программе'),
    season_id: uuid.UUID | None = Query(default=None, description='Фильтр по сезону'),
    verification_status: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: deps.OptionalUser = None,
):
    """Олимпиады, по которым у вуза есть правила льгот, вместе с правилами.

    Фильтры по виду льготы, предмету, программе и сезону комбинируются и
    применяются на сервере до постраничной выдачи. Страница считается по
    олимпиадам: карточка каталога — олимпиада со списком её условий.

    Архивные олимпиады остаются в списке с ``is_historical``: университет давал
    льготу, пока олимпиада была в перечне РСОШ, и эта история не должна
    выглядеть как действующая льгота.
    """
    try:
        university = await database.universities.get_university(university_id)
        if not university:
            raise HTTPException(status_code=404, detail='University not found')
        _validate_filters(benefit_type, verification_status)
        scope = _rule_scope(current_user, university_id, include_drafts)
        filters = dict(
            benefit_type=benefit_type,
            subject=subject,
            program_id=program_id,
            season_id=season_id,
            verification_status=verification_status,
            **scope,
        )
        olympiads = await database.benefit_rules.list_olympiads_for_university(
            university_id, limit=limit, offset=offset, **filters
        )
        total = await database.benefit_rules.count_olympiads_for_university(
            university_id, **filters
        )
        return {'olympiads': olympiads, 'total': total}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')



@universities_page.post(
    '/add_university',
    response_model=schemas.universities.UniversityResponse,
    status_code=201,
    responses={
        201: {'description': 'University created'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        409: {'description': 'University with this name already exists'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def add_university(
    university: schemas.universities.UniversityCreate,
    current_user: deps.AdminUser = None,
):
    """Создать университет (вручную, администратором)."""
    try:
        created = await database.universities.add_university(university.model_dump())
        if not created:
            raise HTTPException(
                status_code=409,
                detail='University with this name already exists',
            )
        return created
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.post(
    '/edit_university/{university_id}',
    response_model=schemas.universities.UniversityResponse,
    responses={
        200: {'description': 'University updated'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'University not found'},
        409: {'description': 'University with this name already exists'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def edit_university(
    university_id: uuid.UUID,
    university: schemas.universities.UniversityUpdate,
    current_user: deps.AdminUser = None,
):
    """Изменить университет (администратором)."""
    try:
        update_data = university.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail='No fields to update')
        updated = await database.universities.edit_university(
            university_id,
            update_data,
        )
        if not updated:
            existing = await database.universities.get_university(university_id)
            if not existing:
                raise HTTPException(status_code=404, detail='University not found')
            raise HTTPException(
                status_code=409,
                detail='University with this name already exists',
            )
        return updated
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


# --- Правила льгот: список, создание, правка, публикация, проверка, версии ---


async def _require_university(university_id) -> dict:
    university = await database.universities.get_university(university_id)
    if not university:
        raise HTTPException(status_code=404, detail='University not found')
    return university


def _raise_rule_error(exc: database.benefit_rules.BenefitRuleError):
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@universities_page.get(
    '/{university_id}/benefit-rules',
    response_model=schemas.benefit_rules.BenefitRulesResponse,
    responses={
        200: {'description': 'Правила льгот университета'},
        401: {'description': 'Access token required to view drafts'},
        403: {'description': 'Drafts are visible to own university only'},
        404: {'description': 'University not found'},
        500: {'description': 'Internal server error'},
    },
)
async def list_benefit_rules(
    university_id: uuid.UUID,
    include_drafts: bool = Query(default=False, description='Черновики и архив (свой вуз/админ)'),
    status: str | None = Query(default=None, description='draft,published,archived (через запятую)'),
    olympiad_id: uuid.UUID | None = Query(default=None),
    season_id: uuid.UUID | None = Query(default=None),
    program_id: uuid.UUID | None = Query(default=None),
    benefit_type: str | None = Query(default=None),
    subject: str | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: deps.OptionalUser = None,
):
    """Плоский список правил вуза с фильтрами и постраничной выдачей (ТЗ §4.5)."""
    try:
        await _require_university(university_id)
        _validate_filters(benefit_type, verification_status)
        scope = _rule_scope(current_user, university_id, include_drafts)
        filters = dict(
            university_id=university_id,
            olympiad_id=olympiad_id,
            season_id=season_id,
            program_id=program_id,
            benefit_type=benefit_type,
            subject=subject,
            verification_status=verification_status,
            statuses=_parse_statuses(status) if include_drafts else None,
            **scope,
        )
        rules = await database.benefit_rules.list_rules(limit=limit, offset=offset, **filters)
        total = await database.benefit_rules.count_rules(**filters)
        return {'rules': rules, 'total': total}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.get(
    '/{university_id}/benefit-rules/facets',
    response_model=schemas.benefit_rules.BenefitRuleFacets,
    responses={
        200: {'description': 'Значения фильтров по правилам вуза'},
        404: {'description': 'University not found'},
        500: {'description': 'Internal server error'},
    },
)
async def benefit_rule_facets(
    university_id: uuid.UUID,
    include_drafts: bool = Query(default=False),
    current_user: deps.OptionalUser = None,
):
    """Виды льгот, предметы, программы и сезоны для фильтров страницы вуза."""
    try:
        await _require_university(university_id)
        scope = _rule_scope(current_user, university_id, include_drafts)
        return await database.benefit_rules.rule_facets(
            university_id=university_id, public_only=scope['public_only']
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.post(
    '/{university_id}/benefit-rules',
    response_model=schemas.benefit_rules.BenefitRuleItem,
    status_code=201,
    responses={
        201: {'description': 'Правило создано (версия 1)'},
        400: {'description': 'Сезон/профиль/программа не относятся к этой олимпиаде или вузу'},
        401: {'description': 'Access token missing'},
        403: {'description': 'You can only manage your own university'},
        404: {'description': 'Университет, олимпиада, сезон или профиль не найдены'},
        409: {'description': 'Олимпиада в архиве или такое правило уже есть'},
        422: {'description': 'Validation error'},
        500: {'description': 'Internal server error'},
    },
)
async def create_benefit_rule(
    university_id: uuid.UUID,
    body: schemas.benefit_rules.BenefitRuleCreate,
    request: Request,
    current_user: deps.ManageUniversity = None,
):
    """Создать правило льготы (представитель своего вуза или администратор).

    Правило ссылается на существующие олимпиаду, сезон, профиль и программы;
    создать олимпиаду отсюда нельзя. ``publish=true`` публикует сразу — правило
    появляется в каталоге с пометкой «Не проверено Papaya».
    """
    try:
        await _require_university(university_id)
        is_admin = current_user.get('role') == ROLE_ADMIN
        data = body.model_dump(exclude_unset=True)
        publish = bool(data.pop('publish', False))
        reason = data.pop('reason', None)
        try:
            rule = await database.benefit_rules.create_rule(
                university_id,
                data=data,
                created_by=current_user.get('id'),
                admin=is_admin,
                publish=publish,
                reason=reason,
            )
        except database.benefit_rules.BenefitRuleError as exc:
            _raise_rule_error(exc)
        await audit.audit(
            'benefit_rule_create',
            actor_id=current_user.get('id'),
            target_type='benefit_rule',
            target_id=rule['id'],
            ip=rate_limit.client_ip(request),
            university_id=str(university_id),
            olympiad_id=str(body.olympiad_id),
            status=rule.get('status'),
        )
        return rule
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


async def _visible_rule(rule_id, university_id, current_user) -> dict:
    """Правило по id с проверкой видимости.

    Посетителю доступны только опубликованные и не отклонённые проверкой
    правила; черновики, архив и отклонённые — представителю своего вуза и
    администратору. Чужой черновик неотличим от несуществующего правила.
    """
    rule = await database.benefit_rules.get_rule(rule_id, university_id=university_id)
    if rule is None:
        raise HTTPException(status_code=404, detail='Benefit rule not found')
    public = (
        rule['status'] == 'published'
        and rule['verification_status'] != 'rejected'
    )
    if not public and not deps.can_manage_university(current_user, university_id):
        raise HTTPException(status_code=404, detail='Benefit rule not found')
    return rule


@universities_page.get(
    '/{university_id}/benefit-rules/{rule_id}',
    response_model=schemas.benefit_rules.BenefitRuleItem,
    responses={
        200: {'description': 'Правило льготы'},
        404: {'description': 'Benefit rule not found'},
        500: {'description': 'Internal server error'},
    },
)
async def get_benefit_rule(
    university_id: uuid.UUID,
    rule_id: uuid.UUID,
    current_user: deps.OptionalUser = None,
):
    """Карточка правила: опубликованные — публично, черновики — своим."""
    try:
        return await _visible_rule(rule_id, university_id, current_user)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.put(
    '/{university_id}/benefit-rules/{rule_id}',
    response_model=schemas.benefit_rules.BenefitRuleItem,
    responses={
        200: {'description': 'Правило обновлено, создана версия'},
        400: {'description': 'Недопустимое значение поля'},
        401: {'description': 'Access token missing'},
        403: {'description': 'You can only manage your own university'},
        404: {'description': 'Правило не найдено'},
        409: {'description': 'Версия устарела, дубликат или архивное правило'},
        500: {'description': 'Internal server error'},
    },
)
async def update_benefit_rule(
    university_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: schemas.benefit_rules.BenefitRuleUpdate,
    request: Request,
    current_user: deps.ManageUniversity = None,
):
    """Изменить правило и записать версию (ТЗ §4.3, §8).

    Представитель правит содержимое правил своего вуза; статус проверки и
    привязку документа по id меняет только администратор. Любое содержательное
    изменение сбрасывает проверку Papaya. ``expected_version`` защищает от
    перезаписи параллельных правок (409).
    """
    try:
        is_admin = current_user.get('role') == ROLE_ADMIN
        updates = body.model_dump(exclude_unset=True)
        reason = updates.pop('reason', None)
        expected_version = updates.pop('expected_version', None)
        if not updates:
            raise HTTPException(status_code=400, detail='No fields to update')
        try:
            rule = await database.benefit_rules.update_rule(
                rule_id,
                university_id=university_id,
                updates=updates,
                changed_by=current_user.get('id'),
                admin=is_admin,
                reason=reason,
                expected_version=expected_version,
            )
        except database.benefit_rules.BenefitRuleError as exc:
            _raise_rule_error(exc)
        if rule is None:
            raise HTTPException(status_code=404, detail='Benefit rule not found')
        if rule.get('changed'):
            await audit.audit(
                'benefit_rule_update',
                actor_id=current_user.get('id'),
                target_type='benefit_rule',
                target_id=rule_id,
                ip=rate_limit.client_ip(request),
                version=rule.get('version'),
                fields=sorted(updates),
            )
        return rule
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.post(
    '/{university_id}/benefit-rules/{rule_id}/status',
    response_model=schemas.benefit_rules.BenefitRuleItem,
    responses={
        200: {'description': 'Состояние изменено'},
        401: {'description': 'Access token missing'},
        403: {'description': 'You can only manage your own university'},
        404: {'description': 'Правило не найдено'},
        409: {'description': 'Версия устарела или олимпиада в архиве'},
        500: {'description': 'Internal server error'},
    },
)
async def set_benefit_rule_status(
    university_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: schemas.benefit_rules.BenefitRuleStatusRequest,
    request: Request,
    current_user: deps.ManageUniversity = None,
):
    """Опубликовать, снять с публикации или архивировать правило.

    Публикация делает правило видимым сразу — с пометкой «Не проверено Papaya»
    до решения администратора. Архив сохраняет историю.
    """
    try:
        try:
            rule = await database.benefit_rules.set_rule_status(
                rule_id,
                university_id=university_id,
                status=body.status,
                changed_by=current_user.get('id'),
                reason=body.reason,
                expected_version=body.expected_version,
            )
        except database.benefit_rules.BenefitRuleError as exc:
            _raise_rule_error(exc)
        if rule is None:
            raise HTTPException(status_code=404, detail='Benefit rule not found')
        if rule.get('changed'):
            await audit.audit(
                'benefit_rule_' + body.status,
                actor_id=current_user.get('id'),
                target_type='benefit_rule',
                target_id=rule_id,
                ip=rate_limit.client_ip(request),
                version=rule.get('version'),
            )
        return rule
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.delete(
    '/{university_id}/benefit-rules/{rule_id}',
    status_code=204,
    responses={
        204: {'description': 'Черновик удалён'},
        401: {'description': 'Access token missing'},
        403: {'description': 'You can only manage your own university'},
        404: {'description': 'Правило не найдено'},
        409: {'description': 'Удалить можно только черновик'},
        500: {'description': 'Internal server error'},
    },
)
async def delete_benefit_rule(
    university_id: uuid.UUID,
    rule_id: uuid.UUID,
    request: Request,
    current_user: deps.ManageUniversity = None,
):
    """Удалить черновик. Опубликованное правило переводится в архив."""
    try:
        try:
            removed = await database.benefit_rules.delete_rule(
                rule_id, university_id=university_id
            )
        except database.benefit_rules.BenefitRuleError as exc:
            _raise_rule_error(exc)
        if not removed:
            raise HTTPException(status_code=404, detail='Benefit rule not found')
        await audit.audit(
            'benefit_rule_delete',
            actor_id=current_user.get('id'),
            target_type='benefit_rule',
            target_id=rule_id,
            ip=rate_limit.client_ip(request),
        )
        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.post(
    '/{university_id}/benefit-rules/{rule_id}/verification',
    response_model=schemas.benefit_rules.BenefitRuleItem,
    responses={
        200: {'description': 'Решение проверки записано'},
        400: {'description': 'Нет причины отклонения'},
        401: {'description': 'Access token missing'},
        403: {'description': 'Admin role required'},
        404: {'description': 'Правило не найдено'},
        409: {'description': 'Для verified нужны документ и ссылка на источник'},
        500: {'description': 'Internal server error'},
    },
)
async def verify_benefit_rule(
    university_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: schemas.benefit_rules.BenefitRuleVerificationRequest,
    request: Request,
    current_user: deps.AdminUser = None,
):
    """Проверка Papaya (ТЗ §9): ``verified`` / ``rejected`` / ``unverified``.

    Только администратор. ``verified`` невозможен без официального документа и
    ссылки на источник; ``rejected`` — без причины. Подтверждение вузом
    (``university_confirmed``) на это решение не влияет.
    """
    try:
        existing = await database.benefit_rules.get_rule(rule_id, university_id=university_id)
        if existing is None:
            raise HTTPException(status_code=404, detail='Benefit rule not found')
        try:
            rule = await database.benefit_rules.set_verification(
                rule_id,
                status=body.status,
                note=body.note,
                admin_id=current_user.get('id'),
                expected_version=body.expected_version,
            )
        except database.benefit_rules.BenefitRuleError as exc:
            _raise_rule_error(exc)
        await audit.audit(
            'benefit_rule_verification',
            actor_id=current_user.get('id'),
            target_type='benefit_rule',
            target_id=rule_id,
            ip=rate_limit.client_ip(request),
            status=body.status,
            note=body.note,
            version=rule.get('version'),
        )
        return rule
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.post(
    '/{university_id}/benefit-rules/{rule_id}/document',
    response_model=schemas.benefit_rules.BenefitRuleItem,
    responses={
        200: {'description': 'Документ загружен и привязан к правилу'},
        400: {'description': 'Unsupported file format or empty file'},
        401: {'description': 'Access token missing'},
        403: {'description': 'You can only manage your own university'},
        404: {'description': 'Правило не найдено'},
        413: {'description': 'File too large'},
        500: {'description': 'Internal server error'},
    },
)
async def upload_benefit_rule_document(
    university_id: uuid.UUID,
    rule_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    current_user: deps.ManageUniversity = None,
):
    """Загрузить официальный документ вуза (приказ/правила приёма) к правилу.

    Файл проходит те же проверки, что и документы администратора (формат,
    сигнатура, размер, безопасное имя). Привязка документа — новая версия
    правила; проверка Papaya при этом снимается.
    """
    try:
        rule = await database.benefit_rules.get_rule(rule_id, university_id=university_id)
        if rule is None:
            raise HTTPException(status_code=404, detail='Benefit rule not found')
        doc = await store_uploaded_document(
            file,
            doc_type='UNIVERSITY_ORDER',
            name=name,
            metadata={
                'kind': 'benefit_rule_document',
                'university_id': str(university_id),
                'benefit_rule_id': str(rule_id),
                'uploaded_by': str(current_user.get('id')),
            },
        )
        updated = await database.benefit_rules.attach_document(
            rule_id,
            university_id=university_id,
            doc_id=doc['id'],
            changed_by=current_user.get('id'),
        )
        if updated is None:
            raise HTTPException(status_code=404, detail='Benefit rule not found')
        await audit.audit(
            'benefit_rule_document',
            actor_id=current_user.get('id'),
            target_type='benefit_rule',
            target_id=rule_id,
            ip=rate_limit.client_ip(request),
            doc_id=doc['id'],
        )
        return updated
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.get(
    '/{university_id}/benefit-rules/{rule_id}/document',
    responses={
        200: {'description': 'Файл официального документа'},
        404: {'description': 'Правило или файл не найдены'},
        500: {'description': 'Internal server error'},
    },
)
async def download_benefit_rule_document(
    university_id: uuid.UUID,
    rule_id: uuid.UUID,
    current_user: deps.OptionalUser = None,
):
    """Скачать официальный документ правила (публично для опубликованных)."""
    try:
        rule = await _visible_rule(rule_id, university_id, current_user)
        if not rule.get('source_doc_id'):
            raise HTTPException(status_code=404, detail='Rule has no document')
        doc = await database.docs.get_doc(rule['source_doc_id'])
        if not doc:
            raise HTTPException(status_code=404, detail='Document not found')
        return document_file_response(doc)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.get(
    '/{university_id}/benefit-rules/{rule_id}/versions',
    response_model=schemas.benefit_rules.BenefitRuleVersionsResponse,
    responses={
        200: {'description': 'История версий правила'},
        401: {'description': 'Access token missing'},
        403: {'description': 'You can only manage your own university'},
        404: {'description': 'Правило не найдено'},
        500: {'description': 'Internal server error'},
    },
)
async def benefit_rule_versions(
    university_id: uuid.UUID,
    rule_id: uuid.UUID,
    current_user: deps.ManageUniversity = None,
):
    """История версий — представителю своего вуза и администратору (ТЗ §8)."""
    try:
        rule = await database.benefit_rules.get_rule(rule_id, university_id=university_id)
        if rule is None:
            raise HTTPException(status_code=404, detail='Benefit rule not found')
        versions = await database.benefit_rules.list_versions(rule_id)
        return {'versions': versions, 'current_version': rule.get('version') or 0}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.post(
    '/{university_id}/benefit-rules/{rule_id}/rollback',
    response_model=schemas.benefit_rules.BenefitRuleItem,
    responses={
        200: {'description': 'Правило откатано: создана новая версия'},
        401: {'description': 'Access token missing'},
        403: {'description': 'You can only manage your own university'},
        404: {'description': 'Правило или версия не найдены'},
        409: {'description': 'Версия устарела или откат создаёт дубликат'},
        500: {'description': 'Internal server error'},
    },
)
async def rollback_benefit_rule(
    university_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: schemas.benefit_rules.BenefitRuleRollbackRequest,
    request: Request,
    current_user: deps.ManageUniversity = None,
):
    """Восстановить содержимое выбранной версии новой версией (ТЗ §8).

    Промежуточные версии не удаляются. Восстановленное правило всегда
    ``unverified``: проверка Papaya относится к конкретному содержимому и
    автоматически не возвращается.
    """
    try:
        try:
            rule = await database.benefit_rules.rollback_rule(
                rule_id,
                university_id=university_id,
                version=body.version,
                changed_by=current_user.get('id'),
                reason=body.reason,
                expected_version=body.expected_version,
            )
        except database.benefit_rules.BenefitRuleError as exc:
            _raise_rule_error(exc)
        if rule is None:
            raise HTTPException(status_code=404, detail='Benefit rule or version not found')
        await audit.audit(
            'benefit_rule_rollback',
            actor_id=current_user.get('id'),
            target_type='benefit_rule',
            target_id=rule_id,
            ip=rate_limit.client_ip(request),
            restored_version=body.version,
            version=rule.get('version'),
        )
        return rule
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.post(
    '/{university_id}/benefit-rules/{rule_id}/university-confirmation',
    response_model=schemas.benefit_rules.BenefitRuleItem,
    responses={
        200: {'description': 'Отметка подтверждения вузом обновлена'},
        401: {'description': 'Access token missing'},
        403: {'description': 'You can only manage your own university'},
        404: {'description': 'Правило не найдено'},
        500: {'description': 'Internal server error'},
    },
)
async def confirm_benefit_rule_by_university(
    university_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: schemas.benefit_rules.UniversityConfirmationRequest,
    current_user: deps.ManageUniversity = None,
):
    """Подтвердить/снять подтверждение правила со стороны вуза (ТЗ §9).

    Подтверждение вуза — независимая характеристика, отдельная от проверки
    администрацией Papaya: оно не делает правило «проверенным».
    """
    try:
        rule = await database.benefit_rules.set_university_confirmation(
            rule_id,
            university_id=university_id,
            confirmed=body.confirmed,
            changed_by=current_user.get('id'),
        )
        if rule is None:
            raise HTTPException(status_code=404, detail='Benefit rule not found')
        return rule
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


# --- Запросы о пополнении каталога --------------------------------------------


@universities_page.post(
    '/{university_id}/catalog-requests',
    response_model=schemas.catalog_requests.CatalogRequestItem,
    status_code=201,
    responses={
        201: {'description': 'Запрос отправлен администратору'},
        401: {'description': 'Access token missing'},
        403: {'description': 'You can only manage your own university'},
        404: {'description': 'University or olympiad not found'},
        500: {'description': 'Internal server error'},
    },
)
async def submit_catalog_request(
    university_id: uuid.UUID,
    body: schemas.catalog_requests.CatalogRequestCreate,
    current_user: deps.ManageUniversity = None,
):
    """Представитель просит добавить олимпиаду/сезон/профиль в каталог.

    Сам он записи каталога не создаёт (их ведёт администратор по перечню
    РСОШ), но запрос фиксируется в системе и виден в панели администратора.
    """
    try:
        await _require_university(university_id)
        if body.olympiad_id is not None:
            olympiad = await database.olympiads.get_olympiad(body.olympiad_id)
            if not olympiad:
                raise HTTPException(status_code=404, detail='Olympiad not found')
        return await database.catalog_requests.submit_request(
            university_id,
            user_id=current_user.get('id'),
            kind=body.kind,
            text=body.text,
            olympiad_id=body.olympiad_id,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@universities_page.get(
    '/{university_id}/catalog-requests',
    response_model=schemas.catalog_requests.CatalogRequestsResponse,
    responses={
        200: {'description': 'Запросы вуза о пополнении каталога'},
        401: {'description': 'Access token missing'},
        403: {'description': 'You can only manage your own university'},
        500: {'description': 'Internal server error'},
    },
)
async def list_university_catalog_requests(
    university_id: uuid.UUID,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: deps.ManageUniversity = None,
):
    try:
        requests = await database.catalog_requests.list_requests(
            status=status, university_id=university_id, limit=limit, offset=offset
        )
        total = await database.catalog_requests.count_requests(
            status=status, university_id=university_id
        )
        return {'requests': requests, 'total': total}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')
