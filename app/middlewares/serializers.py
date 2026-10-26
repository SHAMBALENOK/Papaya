"""Сериализация ORM-объектов в словари для хранения в Redis-кэше.

Redis умеет хранить только bytes/str/int/float, поэтому складывать
SQLAlchemy-объекты напрямую нельзя (иначе:
"Invalid input of type: 'Users'. Convert to a bytes, string, int or float first.").
Вместо этого объекты превращаются в JSON-совместимые словари.
"""
from typing import Any, Optional


def _iso(value: Any) -> Optional[str]:
    """datetime -> ISO-строка, None -> None"""
    return value.isoformat() if value else None


def user_to_dict(user) -> dict:
    """
    Users (ORM) -> dict для кэша.

    Пароль в кэш не попадает: он нигде не читается из кэша,
    а хранить хэш пароля лишний раз не стоит.
    """
    return {
        'id': str(user.id),
        'email': user.email,
        'name': user.name,
        'surname': user.surname,
        'gender': user.gender,
        'bday': user.bday,
        'bio': user.bio,
        'phone': user.phone,
        'country': user.country,
        'region': user.region,
        'status': user.status,
        'role': user.role,
        'university_id': str(user.university_id) if user.university_id else None,
        'isActive': user.isActive,
        'createdAt': _iso(user.createdAt),
        'updatedAt': _iso(user.updatedAt),
    }


def university_to_dict(university) -> dict:
    """Universities (ORM) -> словарь каталога."""
    return {
        'id': str(university.id),
        'name': university.name,
        'name_norm': university.name_norm,
        'short_name': university.short_name,
        'description': university.description,
        'website': university.website,
        'preview_image': university.preview_image,
        'image': university.image,
        'createdAt': _iso(university.createdAt),
        'updatedAt': _iso(university.updatedAt),
    }


def olympiad_to_dict(olympiad) -> dict:
    """Olympiads (ORM) -> словарь каталога."""
    return {
        'id': str(olympiad.id),
        'name': olympiad.name,
        'name_norm': olympiad.name_norm,
        'description': olympiad.description,
        'official_url': olympiad.official_url,
        'organizer': olympiad.organizer,
        'preview_image': olympiad.preview_image,
        'image': olympiad.image,
        'source_doc_id': str(olympiad.source_doc_id) if olympiad.source_doc_id else None,
        'status': olympiad.status,
        'archive_reason': olympiad.archive_reason,
        'createdAt': _iso(olympiad.createdAt),
        'updatedAt': _iso(olympiad.updatedAt),
    }


def benefit_rule_to_dict(rule) -> dict:
    """BenefitRule (ORM) -> словарь правила льготы (без связанных сущностей).

    Правило — отдельная сущность: пара (университет, олимпиада), сезон и
    профиль, вид льготы, требуемый результат, предмет, доп. требования,
    документ и ссылка на источник, срок действия, публикационное состояние и
    независимый статус проверки Papaya. Программы и названия связанных
    сущностей подтягивает слой данных (``database.benefit_rules``).
    """
    return {
        'id': str(rule.id),
        'university_id': str(rule.university_id),
        'olympiad_id': str(rule.olympiad_id),
        'season_id': str(rule.season_id) if rule.season_id else None,
        'profile_id': str(rule.profile_id) if rule.profile_id else None,
        'status': rule.status,
        'createdBy': str(rule.createdBy) if rule.createdBy else None,
        'published_by': str(rule.published_by) if rule.published_by else None,
        'published_at': _iso(rule.published_at),
        'source_doc_id': str(rule.source_doc_id) if rule.source_doc_id else None,
        'source_meta': rule.source_meta,
        'benefit_type': rule.benefit_type,
        'result_requirement': rule.result_requirement,
        'subject': rule.subject,
        'extra_requirements': rule.extra_requirements,
        'source_url': rule.source_url,
        'valid_until': _iso(rule.valid_until),
        'verification_status': rule.verification_status,
        'verified_by': str(rule.verified_by) if rule.verified_by else None,
        'verified_at': _iso(rule.verified_at),
        'verification_note': rule.verification_note,
        'university_confirmed': bool(rule.university_confirmed),
        'university_confirmed_at': _iso(rule.university_confirmed_at),
        'version': rule.version or 0,
        'createdAt': _iso(rule.createdAt),
        'updatedAt': _iso(rule.updatedAt),
    }


def doc_to_dict(doc) -> dict:
    """Docs (ORM) -> словарь документа-источника."""
    return {
        'id': str(doc.id),
        'name': doc.name,
        'type': doc.type,
        'storage_key': doc.storage_key,
        'mime_type': doc.mime_type,
        'source_url': doc.source_url,
        'checksum': doc.checksum,
        'status': doc.status,
        'availability': getattr(doc, 'availability', 'unknown'),
        'availability_checked_at': _iso(getattr(doc, 'availability_checked_at', None)),
        'processedAt': _iso(doc.processedAt),
        'metadata': doc.meta,
        'note': doc.note,
        'createdAt': _iso(doc.createdAt),
        'updatedAt': _iso(doc.updatedAt),
    }


def season_to_dict(season) -> dict:
    """OlympiadSeason (ORM) -> словарь сезона."""
    return {
        'id': str(season.id),
        'olympiad_id': str(season.olympiad_id),
        'year': season.year,
        'label': season.label or str(season.year),
        'rsoh_level': season.rsoh_level,
        'state': season.state,
        'dates': season.dates,
        'description': season.description,
        'source_url': season.source_url,
        'source_doc_id': str(season.source_doc_id) if season.source_doc_id else None,
        'createdAt': _iso(season.createdAt),
        'updatedAt': _iso(season.updatedAt),
    }


def profile_to_dict(profile) -> dict:
    """OlympiadProfile (ORM) -> словарь профиля сезона."""
    return {
        'id': str(profile.id),
        'season_id': str(profile.season_id),
        'name': profile.name,
        'name_norm': profile.name_norm,
        'subject': profile.subject,
        'description': profile.description,
        'createdAt': _iso(profile.createdAt),
        'updatedAt': _iso(profile.updatedAt),
    }


def program_to_dict(program) -> dict:
    """UniversityProgram (ORM) -> словарь программы вуза."""
    return {
        'id': str(program.id),
        'university_id': str(program.university_id),
        'name': program.name,
        'name_norm': program.name_norm,
        'description': program.description,
        'createdAt': _iso(program.createdAt),
        'updatedAt': _iso(program.updatedAt),
    }


def application_to_dict(application) -> dict:
    """RepresentativeApplication (ORM) -> словарь заявки представителя."""
    return {
        'id': str(application.id),
        'user_id': str(application.user_id),
        'university_id': str(application.university_id),
        'motivation': application.motivation,
        'status': application.status,
        'reviewed_by': str(application.reviewed_by) if application.reviewed_by else None,
        'reviewed_at': _iso(application.reviewed_at),
        'decision_note': application.decision_note,
        'createdAt': _iso(application.createdAt),
        'updatedAt': _iso(application.updatedAt),
    }


def benefit_version_to_dict(version) -> dict:
    """BenefitRuleVersion (ORM) -> словарь версии правила."""
    return {
        'id': str(version.id),
        'rule_id': str(version.rule_id),
        'version': version.version,
        'snapshot': version.snapshot,
        'changed_by': str(version.changed_by) if version.changed_by else None,
        'changed_at': _iso(version.changed_at),
        'reason': version.reason,
        'verification_status': version.verification_status,
        'source_doc_id': str(version.source_doc_id) if version.source_doc_id else None,
        'source_meta': version.source_meta,
        'is_rollback': bool(version.is_rollback),
    }


def audit_event_to_dict(event) -> dict:
    """AuditEvent (ORM) -> словарь события аудита."""
    return {
        'id': str(event.id),
        'action': event.action,
        'actor_id': str(event.actor_id) if event.actor_id else None,
        'target_type': event.target_type,
        'target_id': event.target_id,
        'details': event.details,
        'ip': event.ip,
        'request_id': event.request_id,
        'createdAt': _iso(event.createdAt),
    }


def catalog_request_to_dict(request) -> dict:
    """CatalogRequest (ORM) -> словарь запроса о пополнении каталога."""
    return {
        'id': str(request.id),
        'university_id': str(request.university_id),
        'user_id': str(request.user_id) if request.user_id else None,
        'kind': request.kind,
        'olympiad_id': str(request.olympiad_id) if request.olympiad_id else None,
        'text': request.text,
        'status': request.status,
        'admin_note': request.admin_note,
        'resolved_by': str(request.resolved_by) if request.resolved_by else None,
        'resolved_at': _iso(request.resolved_at),
        'createdAt': _iso(request.createdAt),
        'updatedAt': _iso(request.updatedAt),
    }
