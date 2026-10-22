"""Pydantic schemas for the application map discovered during exploration."""

from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class FieldInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: str
    label: str
    type: str
    name: str
    required: bool = False


class FormInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    action: str = ""
    method: str = "GET"
    submitText: Optional[str] = None
    fields: List[FieldInfo] = Field(default_factory=list)


class HeadingInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    level: int
    text: str


class LinkInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str
    href: str


class ButtonInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str


class PageInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    url: str
    path: str
    title: str
    status: int
    requiresAuth: bool = False
    headings: List[HeadingInfo] = Field(default_factory=list)
    links: List[LinkInfo] = Field(default_factory=list)
    buttons: List[ButtonInfo] = Field(default_factory=list)
    forms: List[FormInfo] = Field(default_factory=list)
    consoleErrors: List[str] = Field(default_factory=list)


class Feature(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    description: str
    pages: List[str] = Field(default_factory=list)


class LoginInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    attempted: bool = False
    success: bool = False
    url: Optional[str] = None
    note: Optional[str] = None


class AppMapStats(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pagesVisited: int = 0
    durationSeconds: float = 0.0
    budgetHit: Optional[Literal["pages", "time"]] = None


class AppMap(BaseModel):
    model_config = ConfigDict(extra="ignore")
    baseUrl: str
    generatedAt: str
    login: LoginInfo = Field(default_factory=LoginInfo)
    pages: List[PageInfo] = Field(default_factory=list)
    summary: str = ""
    features: List[Feature] = Field(default_factory=list)
    stats: AppMapStats = Field(default_factory=AppMapStats)
    error: Optional[str] = None
