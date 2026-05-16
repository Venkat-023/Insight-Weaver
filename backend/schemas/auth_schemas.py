from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class LoginUser(BaseModel):
    username: str
    display_name: str
    role: str = "researcher"


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: LoginUser
