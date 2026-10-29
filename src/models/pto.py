"""PTO per year: the allowance, extra days granted and an optional fixed carry-over."""

from decimal import Decimal
from typing import Annotated

from pydantic import Field, PlainSerializer

from src.lib.balances import PtoTerms
from src.models.base import DomainModel

PtoDays = Annotated[Decimal, Field(decimal_places=1), PlainSerializer(float, return_type=float)]


class PtoYearInput(DomainModel):
    allowance: Annotated[PtoDays, Field(ge=0)] = Field(description='Regular PTO days of the year', examples=[30])
    extra_days: Annotated[PtoDays, Field(ge=0)] = Field(default=Decimal(0), description='Days granted on top')
    carried_over: PtoDays | None = Field(
        default=None, description='Fixed carry-over, e.g. as stated by HR; null: the remainder of the year before',
    )
    note: str = Field(default='', max_length=200, examples=['one extra day granted'])


class PtoYear(PtoYearInput):
    year: int = Field(ge=2000, le=2100)

    def terms(self) -> PtoTerms:
        return PtoTerms(self.allowance, self.extra_days, self.carried_over)
