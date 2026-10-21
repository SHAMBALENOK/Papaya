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
        'preview_image': olympiad.preview_image,
        'image': olympiad.image,
        'source_doc_id': str(olympiad.source_doc_id) if olympiad.source_doc_id else None,
        'status': olympiad.status,
        'archive_reason': olympiad.archive_reason,
        'createdAt': _iso(olympiad.createdAt),
        'updatedAt': _iso(olympiad.updatedAt),
    }


def bvi_link_to_dict(link) -> dict:
    """UniversityBvi (ORM) -> словарь правила льготы.

    Связь — это правило льготы: кроме пары (университет, олимпиада) и статуса
    заявки оно несёт вид льготы, требуемый результат, предмет, программы,
    ссылку на источник, срок действия и независимый статус проверки. Поля
    проверки и подтверждения вузом — разные характеристики, обе отдаются
    вызывающему.
    """
    return {
        'id': str(link.id),
        'university_id': str(link.university_id),
        'olympiad_id': str(link.olympiad_id),
        'status': link.status,
        'createdBy': str(link.createdBy) if link.createdBy else None,
        'confirmedBy': str(link.confirmedBy) if link.confirmedBy else None,
        'source_doc_id': str(link.source_doc_id) if link.source_doc_id else None,
        'source_meta': link.source_meta,
        'benefit_type': link.benefit_type,
        'result_requirement': link.result_requirement,
        'subject': link.subject,
        'programs': link.programs,
        'extra_requirements': link.extra_requirements,
        'source_url': link.source_url,
        'valid_until': _iso(link.valid_until),
        'verification_status': link.verification_status,
        'verified_by': str(link.verified_by) if link.verified_by else None,
        'verified_at': _iso(link.verified_at),
        'university_confirmed': bool(link.university_confirmed),
        'university_confirmed_at': _iso(link.university_confirmed_at),
        'createdAt': _iso(link.createdAt),
        'updatedAt': _iso(link.updatedAt),
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
        'link_id': str(version.link_id),
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
