from pydantic import BaseModel, HttpUrl

class RepositoryRequest(BaseModel):
    repository_url: HttpUrl
    