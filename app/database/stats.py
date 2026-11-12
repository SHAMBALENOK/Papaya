"""Сводные счётчики для панели администратора.

Один запрос на каждую сущность вместо выгрузки каталогов в память: панель
открывается часто, а каталог может быть большим. Счётчики не кэшируются:
администратору нужны актуальные цифры после модерации.
"""

from sqlalchemy import func, select

from app.database.database import AsyncSessionLocal
from app.models.benefits import BenefitRule
from app.models.docs import Docs
from app.models.imports import ImportJob
from app.models.olympiads import Olympiads
from app.models.programs import UniversityProgram
from app.models.representative import RepresentativeApplication
from app.models.seasons import OlympiadSeason
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
            'programs': await count(UniversityProgram),
            'programs_archived': await count(
                UniversityProgram, UniversityProgram.is_archived.is_(True)
            ),
            'seasons': await count(OlympiadSeason),
            'seasons_archived': await count(
                OlympiadSeason, OlympiadSeason.is_archived.is_(True)
            ),
            'benefits': await count(BenefitRule),
            'benefits_by_status': benefit_by_status,
            'benefits_published': await count(
                BenefitRule,
                BenefitRule.is_published.is_(True),
                BenefitRule.verification_status == 'verified',
            ),
            'docs': await count(Docs),
            'representative_applications_pending': await count(
                RepresentativeApplication,
                RepresentativeApplication.status == 'pending',
            ),
            'imports_running': await count(
                ImportJob, ImportJob.status == 'PROCESSING'
            ),
        }
