# NORE - Production Real-Time Voice Intelligence Platform

A production-grade, real-time voice intelligence platform powered by **ElevenLabs** neural voice synthesis, **FastAPI**, **SQLAlchemy**, **WebSockets**, and **JWT RBAC**.

---

## 1. System Architecture

```text
                                    +-----------------------------------------+
                                    |         CLIENT / WEB BROWSER            |
                                    |  - Web Audio API Recording (Mic)        |
                                    |  - Dynamic Canvas Waveform Visualizer   |
                                    |  - Live Token Transcript Streaming      |
                                    |  - Instant Interruption Handler         |
                                    +--------------------+--------------------+
                                                         |
                                 HTTPS REST / Auth       |   WebSocket (/ws/voice?token=...)
                             Authorization: Bearer <JWT> |   Full-Duplex Audio & Control
                                                         v
+---------------------------------------------------------------------------------------------------------------+
|                                      FASTAPI BACKEND SECURITY BOUNDARY                                        |
|                                                                                                               |
|  [Security & Identity]               [Real-Time Voice Engine]                 [Persistence & Telemetry]       |
|   - Argon2id Password Hashing         - Audio Chunking & Format Normalizer     - Async SQLAlchemy 2.0         |
|   - JWT Access & Refresh Rotation     - Conversational Persona Orchestrator    - SQLite (Dev) / Postgres      |
|   - RBAC: ADMIN | USER | AUDITOR      - Instant Interruption Dispatcher        - Alembic Schema Migrations    |
|   - Sliding-Window Rate Limiter       - Streaming Audio Queue Buffer           - Audit Logs & Usage Tracking  |
|                                                                                                               |
|  [ElevenLabs Bridge Service]                                                                                  |
|   - Streaming TTS (/v1/text-to-speech/{voice_id}/stream)                                                      |
|   - Speech-to-Speech (/v1/speech-to-speech/{voice_id}/stream)                                                 |
|   - Speech-to-Text (/v1/speech-to-text)                                                                       |
|   - Scoped Permission & Quota Error Normalizer                                                                |
+-------------------------------------------------------+-------------------------------------------------------+
                                                        |
                                                        | xi-api-key: <SERVER_SECRET_ONLY>
                                                        v
                                            +-----------------------+
                                            |    ELEVENLABS API     |
                                            +-----------------------+
```

---

## 2. Core Security & Secret Rules

> [!IMPORTANT]
> **Zero Client-Side Exposure**:
> The ElevenLabs API key is a strictly server-side secret.
>
> - The client communicates **only** with the Python FastAPI backend via authenticated JWT sessions and WebSockets.
> - The ElevenLabs API key is **never** sent to the client, logged, or embedded in static files.
> - Automated CI/CD scans enforce zero secret leaks across code, responses, and git history.

### Automated Secret Scanning

Run the built-in automated scanner before every deployment or git commit:

```bash
python scripts/scan_secrets.py
```

This utility inspects all project files, verifies regex patterns against API keys, cloud credentials, tokens, and private keys, and returns exit code `0` only when the codebase is clean.

---

## 3. Quickstart (Local Development)

### Prerequisites

- Python 3.11+
- Virtual environment (`venv`)

### Step 1: Clone and Configure Environment

```bash
# Copy example environment configuration
cp .env.example .env

# Edit .env and configure your ELEVENLABS_API_KEY
# Ensure your ElevenLabs key has permissions: text_to_speech, voices_read, models_read, user_read
```

### Step 2: Install Dependencies

```bash
python -m venv .venv
# On Windows:
.\.venv\Scripts\pip install -r requirements.txt
# On Linux/macOS:
source .venv/bin/activate && pip install -r requirements.txt
```

### Step 3: Run the Development Server

```bash
# On Windows:
.\.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# On Linux/macOS:
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Step 4: Access the Application

Open your browser to:

- **Web Application**: `http://localhost:8000`
- **Interactive API Documentation (Swagger)**: `http://localhost:8000/docs`

#### Initial Administrator Credentials

On first boot, the system automatically provisions the initial admin account configured in `.env`:

- **Email**: `admin@voiceassistant.io` (or value of `ADMIN_INITIAL_EMAIL`)
- **Password**: `ChangeThisPasswordInProduction!123` (or value of `ADMIN_INITIAL_PASSWORD`)

---

## 4. Running the Automated Test Suite

The test suite covers Authentication, RBAC, ElevenLabs fallback resilience, persistent conversation sessions, WebSockets, and automated secret leak prevention:

```bash
# Run all tests
python -m pytest -v tests/
```

---

## 5. Real-Time WebSocket Protocol (`/ws/voice`)

Connect over WebSocket with authentication:
`ws://localhost:8000/ws/voice?token=<ACCESS_TOKEN_JWT>`

### Client Messages

1. **Start Turn / Message**:

   ```json
   {
     "type": "start_turn",
     "text": "Hello, how does the voice engine work?",
     "session_id": 1,
     "persona_id": "executive",
     "voice_id": "CwhRBWXzGAHq8TQ4Fs17"
   }
   ```

2. **Instant Interruption**:

   ```json
   {
     "type": "interrupt"
   }
   ```

3. **Heartbeat**:

   ```json
   {
     "type": "ping"
   }
   ```

### Server Responses

- `{"type": "ready", "user": { ... }}`
- `{"type": "turn_start", "session_id": 1, "user_message_id": 4}`
- `{"type": "text_response", "content": "Full response text..."}`
- **Binary Frames**: Raw MP3 audio chunks streamed sequentially from ElevenLabs with ultra-low latency.
- `{"type": "turn_complete", "latency_ms": 280, "chunks_sent": 14, "characters": 120}`
- `{"type": "interrupted", "message": "Voice synthesis cancelled."}`

---

## 6. Production Deployment Guides

### Option A: Docker Compose (Full Stack)

Includes Backend, PostgreSQL 16, and Redis:

```bash
# 1. Configure environment variables in .env
# Set ELEVENLABS_API_KEY, JWT_SECRET_KEY, and strong POSTGRES_PASSWORD

# 2. Build and start containers
docker compose up -d --build

# 3. Check container health
docker compose ps
```

---

### Option B: Railway Deployment

1. Connect your GitHub repository to Railway.
2. In the Railway dashboard, add a **PostgreSQL** service and a **Redis** service.
3. Add the Web Service pointing to your repository.
4. Set Environment Variables in Railway:
   - `APP_ENV=production`
   - `ELEVENLABS_API_KEY=<your-secret-key>`
   - `JWT_SECRET_KEY=<generate-64-char-hex>`
   - `DATABASE_URL=${{Postgres.DATABASE_URL}}`
   - `REDIS_URL=${{Redis.REDIS_URL}}`
   - `ADMIN_INITIAL_EMAIL=admin@yourdomain.com`
   - `ADMIN_INITIAL_PASSWORD=<strong-password>`
5. Railway automatically builds using the included `Dockerfile` and monitors the `/api/admin/health` health check.

---

### Option C: Render Deployment

1. Create a **New Web Service** from your repository.
2. Select **Docker** as the runtime.
3. Attach a Render **PostgreSQL** database.
4. Set Environment Variables:
   - `APP_ENV=production`
   - `ELEVENLABS_API_KEY=<your-secret-key>`
   - `JWT_SECRET_KEY=<secure-random-key>`
   - `DATABASE_URL=<Render-Internal-Database-URL>`
5. Health Check Path: `/api/admin/health`.

---

### Option D: Fly.io Deployment

1. Install `flyctl` and log in:

   ```bash
   fly auth login
   ```

2. Initialize app:

   ```bash
   fly launch --no-deploy
   ```

3. Set secrets in Fly:

   ```bash
   fly secrets set ELEVENLABS_API_KEY="your-secret-key" JWT_SECRET_KEY="secure-hex-string" ADMIN_INITIAL_PASSWORD="your-strong-password"
   ```

4. Attach Fly Postgres:

   ```bash
   fly postgres create
   fly postgres attach <postgres-app-name>
   ```

5. Deploy:

   ```bash
   fly deploy
   ```

---

### Option E: AWS (ECS Fargate + RDS PostgreSQL)

1. Push Docker image to AWS Elastic Container Registry (ECR):

   ```bash
   aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account_id>.dkr.ecr.<region>.amazonaws.com
   docker build -t voice-assistant:latest .
   docker tag voice-assistant:latest <account_id>.dkr.ecr.<region>.amazonaws.com/voice-assistant:latest
   docker push <account_id>.dkr.ecr.<region>.amazonaws.com/voice-assistant:latest
   ```

2. Store `ELEVENLABS_API_KEY` and `JWT_SECRET_KEY` in **AWS Secrets Manager**.
3. Create an ECS Task Definition referencing the ECR image, inject secrets from Secrets Manager, and deploy behind an Application Load Balancer with HTTPS enabled.

---

## 7. Secret Leak Incident Response Protocol

If an ElevenLabs API key or server credential is ever accidentally exposed or leaked:

1. **REVOKE IMMEDIATELY**: Log in to [ElevenLabs API Keys Console](https://elevenlabs.io/app/settings/api-keys) and revoke the compromised key.
2. **GENERATE NEW KEY**: Generate a new API key with the exact permissions required (`text_to_speech`, `voices_read`, `models_read`, `user_read`).
3. **UPDATE HOSTING SECRETS**: Update the environment variable in your production hosting manager (Railway, Render, AWS Secrets Manager, etc.).
4. **PURGE GIT HISTORY**: If committed to Git, use `git filter-repo` or BFG Repo-Cleaner to permanently excise the commit from history.
5. **RUN SECURITY SCAN**:

   ```bash
   python scripts/scan_secrets.py
   ```

6. Verify clean scan status before resuming production traffic.

