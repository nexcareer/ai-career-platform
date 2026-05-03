from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    cv_records = relationship("CVRecord", back_populates="user", cascade="all, delete")
    match_results = relationship("MatchResult", back_populates="user", cascade="all, delete")
    assessments = relationship("Assessment", back_populates="user", cascade="all, delete")
    learning_roadmaps = relationship("LearningRoadmap", back_populates="user", cascade="all, delete")


class CVRecord(Base):
    __tablename__ = "cv_records"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String(255))
    raw_text = Column(Text)
    extracted_skills = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="cv_records")
    match_results = relationship("MatchResult", back_populates="cv_record")


class StudentProfile(Base):
    __tablename__ = "student_profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    university = Column(String(255))
    major = Column(String(255))
    year_of_study = Column(Integer)
    gpa = Column(Float)
    transcript_text = Column(Text)
    career_goal = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)


class ProfessionalProfile(Base):
    __tablename__ = "professional_profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    current_position = Column(String(255))
    experience_level = Column(String(50))
    years_experience = Column(Integer)
    target_role = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)


class EmployerProfile(Base):
    __tablename__ = "employer_profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    company_name = Column(String(255))
    industry = Column(String(255))
    recruiter_position = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True, index=True)
    employer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    title = Column(String(255))
    company = Column(String(255))
    description = Column(Text)
    required_skills = Column(Text)
    location = Column(String(255))
    salary = Column(String(255))
    source = Column(String(100), default="internal")
    external_url = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)


class MatchResult(Base):
    __tablename__ = "match_results"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    cv_record_id = Column(Integer, ForeignKey("cv_records.id"), nullable=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True)
    job_query = Column(String(255))
    match_score = Column(Float)
    matched_skills = Column(Text)
    missing_skills = Column(Text)
    results_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="match_results")
    cv_record = relationship("CVRecord", back_populates="match_results")


class Assessment(Base):
    __tablename__ = "assessments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role_type = Column(String(50))
    test_title = Column(String(255))
    score = Column(Float)
    readiness_level = Column(String(50))
    feedback = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="assessments")


class LearningRoadmap(Base):
    __tablename__ = "learning_roadmaps"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    target_role = Column(String(255))
    missing_skills = Column(Text)
    recommended_steps = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="learning_roadmaps")
class TelegramJob(Base):
    __tablename__ = "telegram_jobs"
    id = Column(Integer, primary_key=True, index=True)
    channel = Column(String(255), index=True)
    message_id = Column(BigInteger, nullable=True)
    date = Column(String(50), nullable=True)
    views = Column(Integer, default=0)
    telegram_url = Column(String(500), nullable=True)
    position = Column(String(255), nullable=True)
    company = Column(String(255), nullable=True)
    city = Column(String(255), nullable=True)
    salary = Column(String(255), nullable=True)
    work_format = Column(String(100), nullable=True)
    experience = Column(String(100), nullable=True)
    url = Column(String(500), nullable=True)
    text = Column(Text, nullable=True)
    extracted_skills = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
