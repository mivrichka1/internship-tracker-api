import pytest
from pydantic import ValidationError

from app.main import VacancyIn


def test_salary_range_validation():
    with pytest.raises(ValidationError):
        VacancyIn(
            company_id="00000000-0000-0000-0000-000000000001",
            title="Intern",
            salary_min=100,
            salary_max=50,
        )


def test_salary_min_must_be_nonnegative():
    with pytest.raises(ValidationError):
        VacancyIn(company_id="00000000-0000-0000-0000-000000000001", title="Intern", salary_min=-1)
