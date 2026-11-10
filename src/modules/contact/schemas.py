"""A message as entered on the contact page (SPEC 5.14)."""

from pydantic import BaseModel, ConfigDict, Field

from src.models.users import EMAIL_PATTERN


class ContactInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100, description="A logged-in user's account name is used instead",
                      examples=['Klara Himmel'])
    email: str = Field(pattern=EMAIL_PATTERN, max_length=200,
                       description="To answer to; a logged-in user's account address is used instead",
                       examples=['klara.himmel@example.com'])
    subject: str = Field(min_length=1, max_length=200, examples=['The export stops'])
    text: str = Field(min_length=1, max_length=5000, description='The message')
    website: str = Field(default='', max_length=200, description='Leave empty: a field hidden from people, which bots '
                                                                 'fill in; such a message is dropped')
