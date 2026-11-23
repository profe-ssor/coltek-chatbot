# Coltek Website Chatbot

AI chatbot for [website name], built with the OpenAI Agents SDK and ChatKit.

## Stack
OpenAI Agents SDK · ChatKit Python SDK · FastAPI · Uvicorn

## Setup

```bash
git clone <repo-url>
cd coltek-chatbot
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then fill in your keys
```

## Run locally

```bash
uvicorn server.main:app --reload --port 8000
```

## Project layout
- `chatbot/` – agents, tools, guardrails (no web code)
- `server/` – ChatKit server, storage, FastAPI endpoint
- `knowledge/` – files uploaded to the vector store
- `notebooks/` – Parts 1–5 experiments
- `deploy/` – Docker, Nginx, systemd

## Environment variables
See `.env.example` for the full list.

## Progress
- [ ] Part 1: Environment setup
- [ ] Part 2: First agent
- [ ] Part 3: Knowledge
- [ ] Part 4: Orchestration
- [ ] Part 5: Guardrails
- [ ] Part 6: Backend server
- [ ] Part 7: Website embed
- [ ] Part 8: Deployment
- [ ] Part 9: Testing & monitoring