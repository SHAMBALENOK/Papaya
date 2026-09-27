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
        'image': olympiad.image,
        'source_url': olympiad.source_url,
        'source_doc_id': str(olympiad.source_doc_id) if olympiad.source_doc_id else None,
        'status': olympiad.status,
        'createdAt': _iso(olympiad.createdAt),
        'updatedAt': _iso(olympiad.updatedAt),
    }


def bvi_link_to_dict(link) -> dict:
    """UniversityBvi (ORM) -> словарь связи «университет даёт БВИ»."""
    return {
        'id': str(link.id),
        'university_id': str(link.university_id),
        'olympiad_id': str(link.olympiad_id),
        'status': link.status,
        'createdBy': str(link.createdBy) if link.createdBy else None,
        'confirmedBy': str(link.confirmedBy) if link.confirmedBy else None,
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
        'processedAt': _iso(doc.processedAt),
        'metadata': doc.meta,
        'note': doc.note,
        'createdAt': _iso(doc.createdAt),
        'updatedAt': _iso(doc.updatedAt),
    }
