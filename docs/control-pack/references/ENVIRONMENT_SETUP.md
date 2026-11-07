# Environment Setup

## Required accounts/services
- Supabase project for PostgreSQL, Auth and private Storage.
- Google AI/Gemini API project and key.
- GitHub repository.
- Vercel frontend project.
- Render backend service.

## Local prerequisites
- Git.
- Node.js LTS version verified against selected Vite/tooling dependencies.
- Python 3.11+; pin exact patch/runtime in project configuration.
- Package managers and lockfiles committed.

## Secrets
Keep backend-only values in local ignored `.env` and hosting secret stores: database connection string for the least-privilege runtime role, Supabase URL/JWKS configuration, Gemini API key, storage configuration and allowed origins. Never commit secrets or put them in Vite `VITE_*` variables.

Create `.env.example` with names and safe placeholders only. Verify `.gitignore` before creating local secrets. Do not use a Supabase service-role key as the normal application database identity.
