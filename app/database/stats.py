"""Сводные показатели для админ-панели.

Считаются только реально существующие сущности: панель не должна показывать
«примерные» или демонстрационные числа.
"""

from sqlalchemy import func, select

from app.database.database import AsyncSessionLocal
from app.models.benefits import BenefitEgeRequirement, BenefitRule
from app.models.docs import Docs
from app.models.entity_requests import EntityRequest
from app.models.imports import ImportJob
from app.models.olympiads import Olympiads
from app.models.programs import UniversityProgram
from app.models.representative import RepresentativeApplication
from app.models.seasons import OlympiadSeason, SeasonProfile
from app.models.universities import Universities
from app.models.users import Users


async def dashboard_stats() -> dict:
    async with AsyncSessionLocal() as session:
        async def count(model, *where):
            stmt = select(func.count()).select_from(model)
            if where:
                stmt = stmt.where(*where)
            return int((await session.execute(stmt)).scalar_one())

        benefit_by_status = {
            status: int(count_value)
            for status, count_value in (
                await session.execute(
                    select(
                        BenefitRule.verification_status, func.count()
                    ).group_by(BenefitRule.verification_status)
                )
            ).all()
        }
        return {
            'users': await count(Users),
            'users_active': await count(Users, Users.isActive.is_(True)),
            'universities': await count(Universities),
            'universities_archived': await count(
                Universities, Universities.is_archived.is_(True)
            ),
            'olympiads': await count(Olympiads),
            'olympiads_archived': await count(
                Olympiads, Olympiads.status == 'ARCHIVED'
            ),
            'seasons': await count(OlympiadSeason),
            'seasons_archived': await count(
                OlympiadSeason, OlympiadSeason.is_archived.is_(True)
            ),
            'profiles': await count(SeasonProfile),
            'profiles_rsosh': await count(
                SeasonProfile, SeasonProfile.rsosh_level.is_not(None)
            ),
            'benefits': await count(BenefitRule),
            'benefits_by_status': benefit_by_status,
            'benefits_published': await count(
                BenefitRule,
                BenefitRule.is_published.is_(True),
                BenefitRule.verification_status != 'rejected',
            ),
            'benefits_needs_review': await count(
                BenefitRule, BenefitRule.needs_review.is_(True)
            ),
            'benefits_with_ege': await count(BenefitEgeRequirement),
            'docs': await count(Docs),
            'docs_rsosh': await count(Docs, Docs.type == 'RSOSH_LIST'),
            'docs_university': await count(Docs, Docs.type == 'UNIVERSITY_ORDER'),
            'programs': await count(UniversityProgram),
            'programs_archived': await count(
                UniversityProgram, UniversityProgram.is_archived.is_(True)
            ),
            'representative_applications_pending': await count(
                RepresentativeApplication,
                RepresentativeApplication.status == 'pending',
            ),
            'entity_requests_pending': await count(
                EntityRequest, EntityRequest.status == 'pending'
            ),
            'imports_running': await count(
                ImportJob, ImportJob.status == 'PROCESSING'
            ),
        }
