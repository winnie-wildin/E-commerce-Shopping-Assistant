# Setup

## Option A: Docker (Recommended)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

### 1. Clone and configure

```bash
git clone <repo-url>
cd livelike
```

Create `backend/.env`:
```
OPENAI_API_KEY=sk-your-key-here
```

Create `frontend/.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=any-random-string
```

> Google OAuth credentials: [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → Create OAuth client ID → Web application → Add `http://localhost:3000/api/auth/callback/google` as authorized redirect URI. Google auth is optional — the app works without it (carts are per-conversation instead of per-user).

### 2. Build and run

```bash
docker compose up --build
```

That's it. Backend on http://localhost:8000, frontend on http://localhost:3000.

### Stop

```bash
docker compose down
```

---

## Option B: Manual Setup

### Prerequisites
- Python 3.13+
- Node.js 20+

### Backend

```bash
cd backend
python -m venv venv
```

Activate the virtual environment:

```bash
# Windows PowerShell
.\venv\Scripts\Activate.ps1

# Windows CMD
venv\Scripts\activate.bat

# Mac/Linux
source venv/bin/activate
```

Install dependencies and configure:

```bash
pip install -r requirements.txt
```

Create `backend/.env`:
```
OPENAI_API_KEY=sk-your-key-here
```

Run:

```bash
uvicorn app.main:app --reload --port 8000
```

Verify: http://localhost:8000/health

### Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=any-random-string
```

Run:

```bash
npm run dev
```

Open: http://localhost:3000

### Run Tests

```bash
cd backend
pytest tests/ -v
```

---

## Troubleshooting

**PowerShell activation fails:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Port already in use:**
```bash
uvicorn app.main:app --reload --port 8001
```
Then update `NEXT_PUBLIC_API_URL` in `frontend/.env.local` to `http://localhost:8001`.

**`python` not found:** Try `python3` instead, or ensure Python is in your PATH.
