"""PTO years endpoints: /api/pto-years and /api/pto-years/{year} (read, enter, delete)."""

import falcon
from spectree import Response

from src.models.pto import PtoYear, PtoYearInput
from src.modules.storage.database import Database
from src.modules.storage.pto_years import PtoYearRepository
from src.utils.spec import spec

TAGS = ['PTO years']
YEAR_PARAMETER = {'year': 'Year, e.g. 2026'}


class PtoYearCollection:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(resp=Response(HTTP_200=list[PtoYear]), tags=TAGS)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Every year with PTO days entered, oldest first."""
        with self._database.transaction() as conn:
            resp.media = PtoYearRepository(conn).all()


class PtoYearItem:
    def __init__(self, database: Database) -> None:
        self._database = database

    @spec.validate(resp=Response('HTTP_404', HTTP_200=PtoYear), tags=TAGS, path_parameter_descriptions=YEAR_PARAMETER)
    def on_get(self, req: falcon.Request, resp: falcon.Response, year: int) -> None:
        """The PTO days of one year."""
        with self._database.transaction() as conn:
            resp.media = PtoYearRepository(conn).get(year)

    @spec.validate(json=PtoYearInput, resp=Response(HTTP_200=PtoYear), tags=TAGS, path_parameter_descriptions=YEAR_PARAMETER)
    def on_put(self, req: falcon.Request, resp: falcon.Response, year: int, json: PtoYearInput) -> None:
        """Enter the PTO days of a year (insert or replace)."""
        with self._database.transaction() as conn:
            resp.media = PtoYearRepository(conn).save(PtoYear(year=year, **json.model_dump()))

    @spec.validate(resp=Response('HTTP_204', 'HTTP_404'), tags=TAGS, path_parameter_descriptions=YEAR_PARAMETER)
    def on_delete(self, req: falcon.Request, resp: falcon.Response, year: int) -> None:
        """Delete the PTO days of a year; the year then has no PTO account."""
        with self._database.transaction() as conn:
            PtoYearRepository(conn).delete(year)
        resp.status = falcon.HTTP_204
