from sqlalchemy import Column, Integer, String, ForeignKey, Enum, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()

class MatchStatus(enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

class Team(Base):
    __tablename__ = "teams"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    player1 = Column(String)
    player2 = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    matches_as_team1 = relationship("Match", foreign_keys="[Match.team1_id]", back_populates="team1")
    matches_as_team2 = relationship("Match", foreign_keys="[Match.team2_id]", back_populates="team2")
    won_matches = relationship("Match", foreign_keys="[Match.winner_id]", back_populates="winner")

class Match(Base):
    __tablename__ = "matches"
    
    id = Column(Integer, primary_key=True, index=True)
    team1_id = Column(Integer, ForeignKey("teams.id"))
    team2_id = Column(Integer, ForeignKey("teams.id"))
    status = Column(Enum(MatchStatus), default=MatchStatus.PENDING)
    winner_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    team1_games_won = Column(Integer, default=0)  # Partidas ganadas por team1
    team2_games_won = Column(Integer, default=0)  # Partidas ganadas por team2
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    team1 = relationship("Team", foreign_keys=[team1_id], back_populates="matches_as_team1")
    team2 = relationship("Team", foreign_keys=[team2_id], back_populates="matches_as_team2")
    winner = relationship("Team", foreign_keys=[winner_id], back_populates="won_matches")

