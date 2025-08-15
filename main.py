from fastapi import FastAPI, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from database import get_db, create_tables
from models import Team, Match, Game, MatchStatus
from sqlalchemy import func
import itertools
import qrcode
import io
import base64

app = FastAPI(title="Torneo de Mus")

# Mount static files (only if directory exists)
import os
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Create tables on startup
@app.on_event("startup")
def startup():
    create_tables()

# Generate QR code
def generate_qr_code(url: str) -> str:
    """Generate QR code as base64 encoded image"""
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    return base64.b64encode(buffer.getvalue()).decode()

# Home page
@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    teams_count = db.query(Team).count()
    matches = db.query(Match).all()
    matches_count = len(matches)
    
    # Calculate completed matches based on games won (3 or more wins)
    completed_matches = 0
    for match in matches:
        team1_wins = db.query(Game).filter(
            Game.match_id == match.id,
            Game.winner_id == match.team1_id
        ).count()
        team2_wins = db.query(Game).filter(
            Game.match_id == match.id,
            Game.winner_id == match.team2_id
        ).count()
        
        if team1_wins >= 3 or team2_wins >= 3:
            completed_matches += 1
    
    # Calculate progress percentage
    progress_percentage = round((completed_matches / matches_count * 100) if matches_count > 0 else 0, 1)
    
    # Generate QR code for the app URL
    app_url = "https://torneo-mus.onrender.com/"
    qr_code_base64 = generate_qr_code(app_url)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "teams_count": teams_count,
        "matches_count": matches_count,
        "completed_matches": completed_matches,
        "progress_percentage": progress_percentage,
        "qr_code": qr_code_base64,
        "app_url": app_url
    })

# Teams routes
@app.get("/teams", response_class=HTMLResponse)
def teams_page(request: Request, db: Session = Depends(get_db)):
    teams = db.query(Team).all()
    return templates.TemplateResponse("teams.html", {
        "request": request,
        "teams": teams
    })

@app.post("/teams")
def create_team(
    name: str = Form(...),
    player1: str = Form(...),
    player2: str = Form(...),
    db: Session = Depends(get_db)
):
    # Check if team name exists
    existing_team = db.query(Team).filter(Team.name == name).first()
    if existing_team:
        raise HTTPException(status_code=400, detail="Team name already exists")
    
    team = Team(name=name, player1=player1, player2=player2)
    db.add(team)
    db.commit()
    return RedirectResponse(url="/teams", status_code=303)

# Generate round-robin matches
@app.post("/generate-matches")
def generate_matches(db: Session = Depends(get_db)):
    teams = db.query(Team).all()
    if len(teams) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 teams")
    
    # Clear existing matches
    db.query(Match).delete()
    db.commit()
    
    # Generate all combinations
    for team1, team2 in itertools.combinations(teams, 2):
        match = Match(team1_id=team1.id, team2_id=team2.id)
        db.add(match)
    
    db.commit()
    return RedirectResponse(url="/matches", status_code=303)

# Matches routes
@app.get("/matches", response_class=HTMLResponse)
def matches_page(request: Request, db: Session = Depends(get_db)):
    matches = db.query(Match).all()
    return templates.TemplateResponse("matches.html", {
        "request": request,
        "matches": matches
    })

# Match detail page
@app.get("/matches/{match_id}", response_class=HTMLResponse)
def match_detail(match_id: int, request: Request, db: Session = Depends(get_db)):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    games = db.query(Game).filter(Game.match_id == match_id).order_by(Game.game_number).all()
    
    return templates.TemplateResponse("match_detail.html", {
        "request": request,
        "match": match,
        "games": games
    })

# Add game result
@app.post("/matches/{match_id}/add-game")
def add_game_result(
    match_id: int,
    team1_score: int = Form(...),
    team2_score: int = Form(...),
    db: Session = Depends(get_db)
):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    # Allow adding games even if match appears completed (might change with new game)
    
    # Validate scores
    if team1_score < 0 or team2_score < 0:
        raise HTTPException(status_code=400, detail="Scores cannot be negative")
    
    if team1_score != 40 and team2_score != 40:
        raise HTTPException(status_code=400, detail="One team must reach 40 points")
    
    if team1_score == 40 and team2_score == 40:
        raise HTTPException(status_code=400, detail="Both teams cannot reach 40 points")
    
    # Update match status
    if match.status == MatchStatus.PENDING:
        match.status = MatchStatus.IN_PROGRESS
    
    # Determine winner
    winner_id = match.team1_id if team1_score == 40 else match.team2_id
    
    # Get current game number
    current_games = db.query(Game).filter(Game.match_id == match_id).count()
    game_number = current_games + 1
    
    # Create new game
    game = Game(
        match_id=match_id,
        team1_score=team1_score,
        team2_score=team2_score,
        winner_id=winner_id,
        game_number=game_number
    )
    db.add(game)
    
    # Check if match is completed (first to 3 wins)
    team1_wins = db.query(Game).filter(
        Game.match_id == match_id,
        Game.winner_id == match.team1_id
    ).count()
    
    team2_wins = db.query(Game).filter(
        Game.match_id == match_id,
        Game.winner_id == match.team2_id
    ).count()
    
    # Add current game win
    if winner_id == match.team1_id:
        team1_wins += 1
    else:
        team2_wins += 1
    
    # Check if someone reached 3 wins
    if team1_wins >= 3:
        match.status = MatchStatus.COMPLETED
        match.winner_id = match.team1_id
        match.completed_at = func.now()
    elif team2_wins >= 3:
        match.status = MatchStatus.COMPLETED
        match.winner_id = match.team2_id
        match.completed_at = func.now()
    
    db.commit()
    return RedirectResponse(url=f"/matches/{match_id}", status_code=303)

# Edit game result
@app.post("/matches/{match_id}/edit-game/{game_id}")
def edit_game_result(
    match_id: int,
    game_id: int,
    team1_score: int = Form(...),
    team2_score: int = Form(...),
    db: Session = Depends(get_db)
):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    game = db.query(Game).filter(Game.id == game_id, Game.match_id == match_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    # Validate scores
    if team1_score < 0 or team2_score < 0:
        raise HTTPException(status_code=400, detail="Scores cannot be negative")
    
    if team1_score != 40 and team2_score != 40:
        raise HTTPException(status_code=400, detail="One team must reach 40 points")
    
    if team1_score == 40 and team2_score == 40:
        raise HTTPException(status_code=400, detail="Both teams cannot reach 40 points")
    
    # Update game
    game.team1_score = team1_score
    game.team2_score = team2_score
    game.winner_id = match.team1_id if team1_score == 40 else match.team2_id
    
    # Recalculate match status
    recalculate_match_status(match, db)
    
    db.commit()
    return RedirectResponse(url=f"/matches/{match_id}", status_code=303)

# Delete game result
@app.post("/matches/{match_id}/delete-game/{game_id}")
def delete_game_result(
    match_id: int,
    game_id: int,
    db: Session = Depends(get_db)
):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    game = db.query(Game).filter(Game.id == game_id, Game.match_id == match_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    db.delete(game)
    
    # Recalculate match status
    recalculate_match_status(match, db)
    
    db.commit()
    return RedirectResponse(url=f"/matches/{match_id}", status_code=303)

def recalculate_match_status(match: Match, db: Session):
    """Recalculate match status based on current games"""
    games = db.query(Game).filter(Game.match_id == match.id).all()
    
    if not games:
        match.status = MatchStatus.PENDING
        match.winner_id = None
        match.completed_at = None
        return
    
    # Count wins for each team
    team1_wins = sum(1 for game in games if game.winner_id == match.team1_id)
    team2_wins = sum(1 for game in games if game.winner_id == match.team2_id)
    
    # Update match status
    if team1_wins >= 3:
        match.status = MatchStatus.COMPLETED
        match.winner_id = match.team1_id
        match.completed_at = func.now()
    elif team2_wins >= 3:
        match.status = MatchStatus.COMPLETED
        match.winner_id = match.team2_id
        match.completed_at = func.now()
    else:
        match.status = MatchStatus.IN_PROGRESS
        match.winner_id = None
        match.completed_at = None

# Ranking page
@app.get("/ranking", response_class=HTMLResponse)
def ranking_page(request: Request, db: Session = Depends(get_db)):
    # Calculate ranking stats for each team
    teams = db.query(Team).all()
    ranking_data = []
    
    for team in teams:
        # Vacas ganadas
        vacas_ganadas = db.query(Match).filter(
            Match.winner_id == team.id,
            Match.status == MatchStatus.COMPLETED
        ).count()
        
        # Partidas ganadas y perdidas
        partidas_ganadas = db.query(Game).filter(Game.winner_id == team.id).count()
        partidas_perdidas = db.query(Game).filter(
            ((Game.match.has(Match.team1_id == team.id)) | 
             (Game.match.has(Match.team2_id == team.id))),
            Game.winner_id != team.id
        ).count()
        
        # Puntos a favor y en contra
        puntos_favor = 0
        puntos_contra = 0
        
        # Games where team was team1
        games_as_team1 = db.query(Game).join(Match).filter(Match.team1_id == team.id).all()
        for game in games_as_team1:
            puntos_favor += game.team1_score
            puntos_contra += game.team2_score
        
        # Games where team was team2
        games_as_team2 = db.query(Game).join(Match).filter(Match.team2_id == team.id).all()
        for game in games_as_team2:
            puntos_favor += game.team2_score
            puntos_contra += game.team1_score
        
        # Enfrentamientos jugados
        enfrentamientos_jugados = db.query(Match).filter(
            ((Match.team1_id == team.id) | (Match.team2_id == team.id)),
            Match.status == MatchStatus.COMPLETED
        ).count()
        
        enfrentamientos_totales = db.query(Match).filter(
            (Match.team1_id == team.id) | (Match.team2_id == team.id)
        ).count()
        
        ranking_data.append({
            "team": team,
            "vacas_ganadas": vacas_ganadas,
            "diferencia_partidas": partidas_ganadas - partidas_perdidas,
            "diferencia_puntos": puntos_favor - puntos_contra,
            "enfrentamientos": f"{enfrentamientos_jugados}/{enfrentamientos_totales}"
        })
    
    # Sort by ranking criteria
    ranking_data.sort(
        key=lambda x: (x["vacas_ganadas"], x["diferencia_partidas"], x["diferencia_puntos"]),
        reverse=True
    )
    
    return templates.TemplateResponse("ranking.html", {
        "request": request,
        "ranking": ranking_data
    })

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8002))
    uvicorn.run(app, host="0.0.0.0", port=port)