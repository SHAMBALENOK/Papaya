"""Публичная карточка правила льготы (ТЗ §5.4).

Отдельный маршрут по id правила: ссылка на конкретное условие должна жить
независимо от того, с какой страницы (вуз или олимпиада) на неё пришли.
Опубликованное правило видно всем; черновик и архив — представителю своего
вуза и администратору. Отклонённое проверкой правило для посетителя не
существует (404) — так же, как оно не появляется в списках каталога;
представитель и администратор видят его со статусом ``rejected``.
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException

from app import database, schemas
from app.core import deps
from app.routers.docs import document_file_response

benefit_rules_page = APIRouter(
    prefix='/benefit-rules',
    tags=['benefit-rules'],
)

logger = logging.getLogger('papaya.benefit_rules')


async def _visible_rule(rule_id, current_user) -> dict:
    rule = await database.benefit_rules.get_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail='Benefit rule not found')
    public = (
        rule['status'] == 'published'
        and rule['verification_status'] != 'rejected'
    )
    if not public and not deps.can_manage_university(
        current_user, rule['university_id']
    ):
        raise HTTPException(status_code=404, detail='Benefit rule not found')
    return rule


@benefit_rules_page.get(
    '/{rule_id}',
    response_model=schemas.benefit_rules.BenefitRuleItem,
    responses={
        200: {'description': 'Правило льготы со связанными сущностями'},
        404: {'description': 'Benefit rule not found'},
        500: {'description': 'Internal server error'},
    },
)
async def benefit_rule_details(rule_id: uuid.UUID, current_user: deps.OptionalUser = None):
    """Карточка правила: университет, олимпиада, сезон, профиль, программы,
    документ, источник и статусы."""
    try:
        return await _visible_rule(rule_id, current_user)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Unhandled error')
        raise HTTPException(status_code=500, detail='Internal server error')


@benefit_rules_page.get(
    '/{rule_id}/document',
    responses={
        200: {'description': 'Файл официального документа'},
        404: {'description': 'Правило или файл не найдены'},
        500: {'description': 'Internal server error'},
    },
)
async def benefit_rule_document(rule_id: uuid.UUID, current_user: deps.OptionalUser = None):
    """Скачать официальный документ правила."""
    try:
        rule = await _visible_rule(rule_id, current_user)
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
