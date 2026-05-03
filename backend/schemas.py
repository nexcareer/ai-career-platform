from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    role: str


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class StudentProfileRequest(BaseModel):
    university: Optional[str] = None
    major: Optional[str] = None
    year_of_study: Optional[int] = None
    gpa: Optional[float] = None
    career_goal: Optional[str] = None


class ProfessionalProfileRequest(BaseModel):
    current_position: Optional[str] = None
    experience_level: Optional[str] = None
    years_experience: Optional[int] = None
    target_role: Optional[str] = None


class EmployerProfileRequest(BaseModel):
    company_name: Optional[str] = None
    industry: Optional[str] = None
    recruiter_position: Optional[str] = None


class JobCreateRequest(BaseModel):
    title: str
    company: str
    description: str
    required_skills: str
    location: Optional[str] = None
    salary: Optional[str] = None


class AssessmentSubmitRequest(BaseModel):
    answers: List[int]
    test_title: str = "Technical Readiness Assessment"


class MatchJobRequest(BaseModel):
    job_description: str
    job_title: Optional[str] = None
