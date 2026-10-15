# Diplomacie – agent instructions

## Project
Online asynchronous Diplomacy-like web application.

Backend:
- Django
- Django REST Framework
- SimpleJWT
- Python

Frontend:
- React
- Vite
- Axios

## Working style
- Before changing code, inspect the existing implementation.
- Do not duplicate functionality that already exists.
- Diagnose the exact cause of a bug before editing multiple files.
- Prefer small, testable changes.
- Preserve existing working behavior.
- After changes, run relevant tests.
- Do not introduce temporary hacks unless explicitly requested.

## Imports
- `backend` is not a Python package.
- Use imports such as:
  `from apps.maps.models import Province`
- Do not use:
  `from backend.apps...`

## Game rules
Current backend supports:
- HOLD
- MOVE
- SUPPORT HOLD
- SUPPORT MOVE
- retreats
- supply-center ownership
- winter adjustments
- automatic deadline processing

Not implemented:
- CONVOY

Do not enable convoy in the frontend until backend adjudication and tests exist.

## Frontend map
The map is:
`frontend/public/maps/standard.svg`

Special SVG aliases:
- MAO -> mid
- NAO -> nat
- NWG -> nrg
- TYS -> tyn

Multi-coast provinces:
- SPA: nc, sc
- STP: nc, sc
- BUL: ec, sc

Saved valid orders are visualized on the map.
Do not replace the existing map interaction model without a reason.

## Development priority
Work toward a complete playable game loop.

When modifying order UI:
1. inspect current GameMap.jsx
2. inspect gameDetail.jsx
3. inspect backend serializer/API
4. only then edit

Never assume a feature is missing without checking the existing code.