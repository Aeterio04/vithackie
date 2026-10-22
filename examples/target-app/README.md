# TaskBoard Demo Target App

A lightweight Express web application with 9 deliberately planted bugs for AI QA benchmarking.

## How to Run
```bash
npm install
npm start
```
The server runs by default on `http://localhost:4000` (configurable via `PORT`).

## Seed User Credentials
- **Email:** `qa.tester@example.com`
- **Password:** `Passw0rd!23`

## Bug Switch (BUGS_OFF)
Toggle planted bugs with the `BUGS_OFF` environment variable:
- `BUGS_OFF=all npm start` runs the application strictly following `spec.md` with zero planted bugs.
- `BUGS_OFF=GT01,GT07 npm start` disables specific bugs by ID.
- Check active bugs at `GET /__bugs` or reset state via `GET|POST /__reset`.
