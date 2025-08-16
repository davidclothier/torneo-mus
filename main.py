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
import os

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
    try:
        print(f"Starting up with DATABASE_URL: {os.getenv('DATABASE_URL', 'sqlite:///./torneo_mus.db')[:50]}...")
        
        # For PostgreSQL, we need to handle the case where columns might not exist yet
        DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./torneo_mus.db")
        if DATABASE_URL.startswith("postgres"):
            # Create base tables only, migration will add missing columns
            from sqlalchemy import create_engine, text
            engine = create_engine(DATABASE_URL)
            
            # Create tables without the new columns first
            with engine.connect() as conn:
                # Create basic tables structure
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS teams (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR NOT NULL,
                        player1 VARCHAR NOT NULL,
                        player2 VARCHAR NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS matches (
                        id SERIAL PRIMARY KEY,
                        team1_id INTEGER REFERENCES teams(id),
                        team2_id INTEGER REFERENCES teams(id),
                        status VARCHAR DEFAULT 'pending',
                        winner_id INTEGER REFERENCES teams(id),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP
                    )
                """))
                
                conn.commit()
                print("Base tables created for PostgreSQL")
        else:
            # For SQLite, use normal table creation
            create_tables()
            
        print("Database startup completed successfully")
    except Exception as e:
        print(f"Error during startup: {e}")
        # Don't raise the error, let the app start so migration can run
        print("Continuing startup despite error - migration may be needed")

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
    try:
        teams_count = db.query(Team).count()
        matches = db.query(Match).all()
        matches_count = len(matches)
        
        # Calculate completed matches based on games won (3 or more wins)
        completed_matches = 0
        try:
            for match in matches:
                if hasattr(match, 'team1_games_won') and hasattr(match, 'team2_games_won'):
                    if match.team1_games_won >= 3 or match.team2_games_won >= 3:
                        completed_matches += 1
                elif match.status == MatchStatus.COMPLETED:
                    # Fallback for old data structure
                    completed_matches += 1
        except:
            # If there's an error accessing the columns, use status instead
            completed_matches = db.query(Match).filter(Match.status == MatchStatus.COMPLETED).count()
        
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
    except Exception as e:
        # If database access fails completely, show error page
        return HTMLResponse(f"""
        <html><body>
        <h1>Database Migration Required</h1>
        <p>The application needs to be migrated. Please go to <a href="/admin/migrate">/admin/migrate</a></p>
        <p>Error: {str(e)}</p>
        </body></html>
        """, status_code=500)

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

# Health check endpoint
@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        # Test database connection
        teams_count = db.query(Team).count()
        matches_count = db.query(Match).count()
        
        return JSONResponse({
            "status": "healthy",
            "database": "connected",
            "teams_count": teams_count,
            "matches_count": matches_count,
            "database_url": os.getenv("DATABASE_URL", "sqlite:///./torneo_mus.db")[:50] + "..."
        })
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "database": "failed",
            "error": str(e),
            "database_url": os.getenv("DATABASE_URL", "sqlite:///./torneo_mus.db")[:50] + "..."
        }, status_code=500)

# Migration page
@app.get("/admin/migrate", response_class=HTMLResponse)
def migrate_page(request: Request):
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Database Migration</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 50px; }
            .container { max-width: 500px; margin: 0 auto; }
            input, button { padding: 10px; margin: 5px; width: 100%; }
            .result { margin-top: 20px; padding: 10px; border-radius: 5px; }
            .success { background: #d4edda; color: #155724; }
            .error { background: #f8d7da; color: #721c24; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Database Migration</h1>
            <p>Este endpoint agrega las columnas <code>team1_games_won</code> y <code>team2_games_won</code> a la tabla matches.</p>
            
            <form id="migrateForm">
                <input type="password" id="password" placeholder="Admin password" required>
                <button type="submit">Migrate Database</button>
            </form>
            
            <div id="result"></div>
        </div>
        
        <script>
            document.getElementById('migrateForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const password = document.getElementById('password').value;
                const result = document.getElementById('result');
                
                try {
                    const formData = new FormData();
                    formData.append('password', password);
                    
                    const response = await fetch('/admin/migrate-db', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        result.innerHTML = `<div class="result success">
                            <strong>Success!</strong> ${data.message}
                            ${data.added_columns ? '<br>Added columns: ' + data.added_columns.join(', ') : ''}
                            ${data.existing_columns ? '<br>Existing columns: ' + data.existing_columns.join(', ') : ''}
                        </div>`;
                    } else {
                        result.innerHTML = `<div class="result error">
                            <strong>Error:</strong> ${data.error}
                        </div>`;
                    }
                } catch (error) {
                    result.innerHTML = `<div class="result error">
                        <strong>Error:</strong> ${error.message}
                    </div>`;
                }
            });
        </script>
    </body>
    </html>
    """)

# Database migration endpoint
@app.post("/admin/migrate-db")
def migrate_database(password: str = Form(...), db: Session = Depends(get_db)):
    if password != "gallegos":
        return JSONResponse({"success": False, "error": "Invalid password"}, status_code=401)
    
    try:
        # Check if migration is needed
        result = db.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'matches' AND column_name IN ('team1_games_won', 'team2_games_won')")
        existing_columns = [row[0] for row in result.fetchall()]
        
        if len(existing_columns) == 2:
            return JSONResponse({"success": True, "message": "Migration already completed", "existing_columns": existing_columns})
        
        # Add missing columns
        if "team1_games_won" not in existing_columns:
            db.execute("ALTER TABLE matches ADD COLUMN team1_games_won INTEGER DEFAULT 0")
            
        if "team2_games_won" not in existing_columns:
            db.execute("ALTER TABLE matches ADD COLUMN team2_games_won INTEGER DEFAULT 0")
        
        db.commit()
        
        return JSONResponse({
            "success": True, 
            "message": "Migration completed successfully",
            "added_columns": ["team1_games_won", "team2_games_won"]
        })
        
    except Exception as e:
        db.rollback()
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

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