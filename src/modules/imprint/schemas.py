"""The imprint's details as kept in its source and answered by the API (SPEC 5.13)."""

from pydantic import BaseModel, ConfigDict, Field

from src.models.users import EMAIL_PATTERN


class ImprintDetails(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, description='Who runs the app', examples=['Klara Himmel'])
    street: str = Field(min_length=1, description='Street and number', examples=['Musterstraße 1'])
    city: str = Field(min_length=1, description='Postcode and city', examples=['10115 Berlin'])
    country: str = Field(min_length=1, examples=['Deutschland'])
    email: str = Field(pattern=EMAIL_PATTERN, examples=['klara.himmel@example.com'])
