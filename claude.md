# Torneo de Mus

  ## Descripción del Proyecto
  Aplicación web para gestionar un torneo de Mus con sistema round-robin entre parejas.

  ## Reglas del Mus y Torneo

  ### Estructura del juego:
  - **Partida individual**: Juego hasta 40 puntos (gana quien llegue primero a 40)
  - **Vaca**: Al mejor de 3 partidas individuales (quien gane 3 partidas primero gana la vaca)
  - **Enfrentamiento**: Una vaca entre 2 parejas específicas
  - **Torneo**: Round-robin donde cada pareja juega contra todas las demás

  ### Sistema de Ranking (orden de prioridad):
  1. **Vacas ganadas** (enfrentamientos ganados)
  2. **Diferencia de partidas** (partidas ganadas - partidas perdidas)
  3. **Diferencia de puntos** (puntos a favor - puntos en contra)

  ### Ejemplo de cálculo:
  **Enfrentamiento: Pareja A vs Pareja B**
  - Partida 1: A gana 40-25 → A: +1 partida, +15 puntos
  - Partida 2: A gana 40-30 → A: +1 partida, +10 puntos
  - Partida 3: B gana 40-35 → B: +1 partida, +5 puntos
  - Partida 4: A gana 40-20 → A: +1 partida, +20 puntos

  **Resultado:** A gana la vaca 3-1
  - **Pareja A**: +1 vaca, diferencia partidas: +2, diferencia puntos: +10
  - **Pareja B**: +0 vacas, diferencia partidas: -2, diferencia puntos: -10

  ## Tech Stack
  - **Backend**: FastAPI + PostgreSQL
  - **Frontend**: Jinja2 + Tailwind CSS (CDN) + Alpine.js
  - **Hosting**: Fly.io
  - **Desarrollo**: 2 horas máximo, enfoque MVP

  ## Flujo de la Aplicación

  ### 1. Registro de parejas
  - Formulario para añadir parejas (nombre de la pareja, jugadores)
  - Lista de parejas registradas
  - Posibilidad de editar/eliminar antes de crear round-robin

  ### 2. Generación del round-robin
  - Botón para generar todos los enfrentamientos automáticamente
  - Con N parejas = N×(N-1)÷2 enfrentamientos totales
  - Estado: "Pendiente", "En progreso", "Completado"

  ### 3. Registro de resultados por enfrentamiento
  - Seleccionar enfrentamiento pendiente
  - Registrar partidas individuales una por una
  - Input: puntos Pareja A - puntos Pareja B (ej: 40-30)
  - La app detecta automáticamente cuando una pareja llega a 3 partidas ganadas
  - Marcar enfrentamiento como completado

  ### 4. Ranking en tiempo real
  - Tabla responsive con:
    - Posición
    - Nombre de pareja
    - Vacas ganadas
    - Diferencia de partidas
    - Diferencia de puntos
    - Enfrentamientos jugados/totales

  ## Estructura de Base de Datos

  ### Tabla: teams (parejas)
  - id: PK
  - name: VARCHAR
  - player1: VARCHAR
  - player2: VARCHAR
  - created_at: TIMESTAMP

  ### Tabla: matches (enfrentamientos)
  - id: PK
  - team1_id: FK
  - team2_id: FK
  - status: ENUM ('pending', 'in_progress', 'completed')
  - winner_id: FK (nullable)
  - created_at: TIMESTAMP
  - completed_at: TIMESTAMP

  ### Tabla: games (partidas individuales)
  - id: PK
  - match_id: FK
  - team1_score: INT
  - team2_score: INT
  - winner_id: FK
  - game_number: INT
  - created_at: TIMESTAMP

  ## Comandos de desarrollo
  ```bash
  # Crear entorno virtual
  python -m venv venv
  source venv/bin/activate  # Linux/Mac
  # venv\Scripts\activate   # Windows

  # Instalar dependencias
  pip install fastapi uvicorn sqlalchemy psycopg2-binary python-multipart jinja2

  # Ejecutar en desarrollo
  uvicorn main:app --reload --port 8000

  # Acceder a la aplicación
  # http://localhost:8000

  Estructura del proyecto

  /
  ├── main.py              # FastAPI app
  ├── models.py            # SQLAlchemy models
  ├── database.py          # DB connection
  ├── templates/           # Jinja2 templates
  │   ├── base.html
  │   ├── index.html
  │   ├── teams.html
  │   ├── matches.html
  │   └── ranking.html
  ├── static/
  │   └── style.css        # Custom CSS if needed
  ├── requirements.txt
  └── README.md

  Funcionalidades MVP (2 horas)

  1. ✅ Registro de parejas
  2. ✅ Generación automática de enfrentamientos
  3. ✅ Registro de resultados de partidas
  4. ✅ Cálculo automático de ranking
  5. ✅ Interfaz responsive básica
  6. ✅ Deploy a Fly.io

  Notas para Claude

  - Proyecto de desarrollo rápido (2h máximo)
  - Enfoque en funcionalidad core sobre pulimiento visual
  - Usar Tailwind CDN para rapidez (no build process)
  - PostgreSQL desde el principio (para deploy directo)
  - Responsive design obligatorio
  - Alpine.js para interactividad mínima