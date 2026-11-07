# ARCHITECTURE.md — System Architecture Overview
**Pattern:** Modular Monolith  
**Runtime:** Python 3.11+ / FastAPI on Render  
**Frontend:** React 18 / Vite / TypeScript on Vercel  
**Database:** Supabase Managed PostgreSQL 15+  

---

## 1. High-Level Topology
```
┌────────────────────────────────────────────────────────┐
│            CLIENT TIER: React 18 + Vite (SPA)          │
│     TypeScript + Tailwind CSS + shadcn/ui + Zustand    │
└───────────────────────────┬────────────────────────────┘
                            │ HTTPS / REST (Supabase JWT Bearer)
                            ▼
┌────────────────────────────────────────────────────────┐
│         API GATEWAY & SECURITY MIDDLEWARE (Render)     │
│   FastAPI Core │ CORS Whitelist │ Leaky-Bucket Limiter │
└───────────────────────────┬────────────────────────────┘
                            │ Validated SecurityContext(user, workspace, client)
                            ▼
┌────────────────────────────────────────────────────────┐
│            FASTAPI MODULAR MONOLITH BACKEND            │
│  ├── auth                 ├── orchestrator             │
│  ├── workspaces           ├── engine_terminology       │
│  ├── clients              ├── engine_factual           │
│  ├── documents            ├── engine_visual            │
│  ├── memory               ├── remediation              │
│  └── assets               └── reviews                  │
└───────┬───────────────────┬────────────────────┬───────┘
        │                   │                    │
        ▼                   ▼                    ▼
┌──────────────┐    ┌──────────────┐     ┌──────────────┐
│ Pillow/NumPy │    │ Google Gemini│     │ Supabase Cloud│
│ Visual Math  │    │ Flash API    │     │ PostgreSQL 15+│
│ (CIEDE2000)  │    │ (NLI Logic)  │     │ (Auth/Storage)│
└──────────────┘    └──────────────┘     └──────────────┘
```

## 2. Monolith Module Boundaries
* `core`: Configuration, DB engine, JWT verification, exception handlers.
* `modules.auth`: IAM, user profile, workspace/client authorization dependency gates.
* `modules.workspaces`: Agency tenant settings, team membership, seat limits.
* `modules.clients`: Client brand provisioning, metadata, active memory pointers.
* `modules.documents`: Upload handling, magic-byte checks, archive limits, text extraction.
* `modules.memory`: Living Brand Memory, rule revisions, JSONB snapshot compilation.
* `modules.assets`: Collateral intake, version sequence management, version forking.
* `modules.orchestrator`: 3-tier audit execution coordinator, `asyncio.gather` runner, heartbeat recovery.
* `modules.engine_terminology`: Regex pattern compiler, Unicode NFC normalizer, linter.
* `modules.engine_factual`: Sentence segmenter, atomic claim extractor, Gemini NLI verifier.
* `modules.engine_visual`: Pillow downsampler, linear-light alpha blender, CIEDE2000 calculator.
* `modules.remediation`: Minimal-edit correction prompt generator, visual diff calculator.
* `modules.reviews`: Brand Manager review queue, advisory acknowledgments, compliance history.
