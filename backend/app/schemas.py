from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str
    remember: bool = False


class LoginResponse(BaseModel):
    token: str
    username: str
    inverter_count: int
    remembered: bool = False
