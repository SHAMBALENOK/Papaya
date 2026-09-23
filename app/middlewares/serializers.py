"""
Сериализация ORM-объектов в словари для хранения в Redis-кэше.

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
    data = {
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
        'isActive': user.isActive,
        'createdAt': _iso(user.createdAt),
        'updatedAt': _iso(user.updatedAt),
    }
    if getattr(user, 'organization_id', None) is not None:
        data['organization_id'] = str(user.organization_id)
    else:
        data['organization_id'] = None
    data['metadata'] = user.metadata_ or {}
    return data


def organization_to_dict(org) -> dict:
    """Organizations (ORM) -> dict для кэша и API."""
    return {
        'id': str(org.id),
        'name': org.name,
        'short_name': org.short_name,
        'type': org.type,
        'description': org.description,
        'website': org.website,
        'logo': org.logo,
        'contacts': org.contacts or {},
        'metadata': org.metadata_ or {},
        'created_at': _iso(org.created_at),
        'updated_at': _iso(org.updated_at),
    }


def olympiad_to_dict(olympiad) -> dict:
    """Olympiads (ORM) -> dict для кэша и API."""
    return {
        'id': str(olympiad.id),
        'name': olympiad.name,
        'organizer_ids': list(olympiad.organizer_ids or []),
        'description': olympiad.description,
        'subjects': list(olympiad.subjects or []),
        'levels': list(olympiad.levels or []),
        'years': list(olympiad.years or []),
        'profiles': list(olympiad.profiles or []),
        'bvi_organizations': list(olympiad.bvi_organizations or []),
        'registration_url': olympiad.registration_url,
        'official_url': olympiad.official_url,
        'status': olympiad.status,
        'metadata': olympiad.metadata_ or {},
        'created_at': _iso(olympiad.created_at),
        'updated_at': _iso(olympiad.updated_at),
    }


def doc_to_dict(doc) -> dict:
    """Docs (ORM) -> dict для кэша и API."""
    return {
        'id': str(doc.id),
        'name': doc.name,
        'type': doc.type,
        'storage_key': doc.storage_key,
        'mime_type': doc.mime_type,
        'source_url': doc.source_url,
        'organization_id': str(doc.organization_id) if doc.organization_id else None,
        'olympiad_id': str(doc.olympiad_id) if doc.olympiad_id else None,
        'uploaded_by': str(doc.uploaded_by) if doc.uploaded_by else None,
        'checksum': doc.checksum,
        'status': doc.status,
        'metadata': doc.metadata_ or {},
        'created_at': _iso(doc.created_at),
        'updated_at': _iso(doc.updated_at),
    }