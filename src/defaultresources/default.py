import falcon
from falcon import Request, Response, HTTP_200
from pydantic import BaseModel
from spectree import Response as SpecResponse

from src.utils.spec import spec


class DefaultResponse(BaseModel):
    status_code: str = HTTP_200
    message: str = 'Work Tracker - All systems operational.'


class Default:
    @spec.validate(
        tags=['Maintenance'],
        resp=SpecResponse('HTTP_200', HTTP_403=None),
        security={},
    )
    def on_get(self, req: Request, resp: Response) -> None:
        """ Handles GET requests. Responds with plain text, not JSON. """
        resp.status = DefaultResponse().status_code
        resp.content_type = falcon.MEDIA_TEXT
        resp.text = DefaultResponse().message
