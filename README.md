# Doc intelligence

AI-powered structured data extraction from private equity documents.

## Setup

### Backend (Python)
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # Add your API keys
uvicorn main:app --reload
```

### Frontend (React)
```bash
cd frontend
npm install
npm run dev
```

## Environment Variables
```
ANTHROPIC_API_KEY=your_key_here
AZURE_DOC_INTEL_KEY=your_key_here (optional)
```

## Tech Stack

- Frontend: React + Vite + Tailwind
- Backend: FastAPI + Python 3.11
- AI: Claude Sonnet 4.5
- Deployment: Vercel (frontend) + Railway (backend)

## Status

MVP - Active Development
