from fastapi import FastAPI, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from database import get_db, create_tables
from models import Team, Match, MatchStatus
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
        if match.team1_games_won >= 3 or match.team2_games_won >= 3:
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
    
    return templates.TemplateResponse("match_detail.html", {
        "request": request,
        "match": match
    })

# Set match result (direct final score)
@app.post("/matches/{match_id}/set-result")
def set_match_result(
    match_id: int,
    team1_games: int = Form(...),
    team2_games: int = Form(...),
    db: Session = Depends(get_db)
):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    # Validate result
    if team1_games < 0 or team2_games < 0:
        raise HTTPException(status_code=400, detail="Games won cannot be negative")
    
    if team1_games == team2_games:
        raise HTTPException(status_code=400, detail="Cannot have a tie")
    
    # One team must have 3 wins, the other between 0-2
    if not ((team1_games == 3 and 0 <= team2_games <= 2) or 
            (team2_games == 3 and 0 <= team1_games <= 2)):
        raise HTTPException(status_code=400, detail="One team must win 3 games, the other 0-2")
    
    # Update match
    match.team1_games_won = team1_games
    match.team2_games_won = team2_games
    match.status = MatchStatus.COMPLETED
    match.winner_id = match.team1_id if team1_games == 3 else match.team2_id
    match.completed_at = func.now()
    
    db.commit()
    return RedirectResponse(url="/matches", status_code=303)

# Edit match result (same logic but for editing)
@app.post("/matches/{match_id}/edit-result")
def edit_match_result(
    match_id: int,
    team1_games: int = Form(...),
    team2_games: int = Form(...),
    db: Session = Depends(get_db)
):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    # Validate result (same validation as set_result)
    if team1_games < 0 or team2_games < 0:
        raise HTTPException(status_code=400, detail="Games won cannot be negative")
    
    if team1_games == team2_games:
        raise HTTPException(status_code=400, detail="Cannot have a tie")
    
    if not ((team1_games == 3 and 0 <= team2_games <= 2) or 
            (team2_games == 3 and 0 <= team1_games <= 2)):
        raise HTTPException(status_code=400, detail="One team must win 3 games, the other 0-2")
    
    # Update match
    match.team1_games_won = team1_games
    match.team2_games_won = team2_games
    match.status = MatchStatus.COMPLETED
    match.winner_id = match.team1_id if team1_games == 3 else match.team2_id
    match.completed_at = func.now()
    
    db.commit()
    return RedirectResponse(url="/matches", status_code=303)

# Admin authentication route
@app.post("/admin/auth")
def admin_auth(password: str = Form(...)):
    if password == "gallegos":
        return JSONResponse({"success": True})
    else:
        return JSONResponse({"success": False}, status_code=401)

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
        
        # Partidas ganadas y perdidas (en enfrentamientos completados)
        partidas_ganadas = 0
        partidas_perdidas = 0
        
        # Matches where team was team1
        matches_as_team1 = db.query(Match).filter(
            Match.team1_id == team.id,
            Match.status == MatchStatus.COMPLETED
        ).all()
        for match in matches_as_team1:
            partidas_ganadas += match.team1_games_won
            partidas_perdidas += match.team2_games_won
        
        # Matches where team was team2
        matches_as_team2 = db.query(Match).filter(
            Match.team2_id == team.id,
            Match.status == MatchStatus.COMPLETED
        ).all()
        for match in matches_as_team2:
            partidas_ganadas += match.team2_games_won
            partidas_perdidas += match.team1_games_won
        
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
            "enfrentamientos": f"{enfrentamientos_jugados}/{enfrentamientos_totales}"
        })
    
    # Sort by ranking criteria (removed diferencia_puntos)
    ranking_data.sort(
        key=lambda x: (x["vacas_ganadas"], x["diferencia_partidas"]),
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