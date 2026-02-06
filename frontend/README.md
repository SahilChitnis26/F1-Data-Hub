# F1 Race Analyzer — React Dashboard

React dashboard for the F1 Race Analyzer using **shadcn** project structure, **Tailwind CSS**, **TypeScript**, and **Recharts**.

## Stack

- **Vite** + **React 18** + **TypeScript**
- **Tailwind CSS v4** (via `@tailwindcss/vite`)
- **shadcn/ui** (components in `src/components/ui`)
- **Recharts** for charts (e.g. pace delta)

## Default component path: `src/components/ui`

shadcn installs UI primitives (Button, Card, Select, etc.) under **`src/components/ui`**, configured in `components.json` as `aliases.ui: "@/components/ui"`. Keeping this path:

- Ensures `npx shadcn@latest add <component>` places files in a single, predictable location.
- Separates reusable UI primitives from feature components (e.g. `src/components/charts`).
- Matches shadcn docs and CLI behavior.

If your project does not have `src/components/ui`, create it and set `aliases.ui` to `@/components/ui` in `components.json`.

## Setup from scratch (if you need to recreate the frontend)

If you are setting up a new project to match this stack:

1. **Create Vite + React + TypeScript project**
   ```bash
   npm create vite@latest . -- --template react-ts
   ```

2. **Install Tailwind CSS v4**
   ```bash
   npm add tailwindcss @tailwindcss/vite
   ```
   In `vite.config.ts`, add the Tailwind plugin and path alias:
   ```ts
   import tailwindcss from "@tailwindcss/vite";
   import path from "path";
   // ...
   plugins: [react(), tailwindcss()],
   resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
   ```
   In `src/index.css`, replace content with:
   ```css
   @import "tailwindcss";
   ```

3. **Configure TypeScript path alias**  
   In `tsconfig.json` and `tsconfig.app.json`, add under `compilerOptions`:
   ```json
   "baseUrl": ".",
   "paths": { "@/*": ["./src/*"] }
   ```

4. **Initialize shadcn**
   ```bash
   npx shadcn@latest init
   ```
   When prompted, choose style (e.g. **New York**), base color (e.g. **Neutral**), and confirm **CSS variables** for theming. This creates `components.json` and sets the default component path (e.g. `@/components/ui` → `src/components/ui`).

5. **Install Recharts**
   ```bash
   npm add recharts
   ```

6. **Add shadcn components as needed**
   ```bash
   npx shadcn@latest add card
   npx shadcn@latest add button
   npx shadcn@latest add chart
   ```

## Quick start (this repo)

Dependencies and config are already in place.

1. From repo root, start the API:
   ```bash
   python api.py
   ```

2. From repo root:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

3. Open **http://localhost:5173**. The dev server proxies `/api` to `http://127.0.0.1:8000`.

## Scripts

- `npm run dev` — start Vite dev server (port 5173)
- `npm run build` — TypeScript check + production build
- `npm run preview` — serve production build locally

## Project layout

- `src/components/ui` — shadcn UI primitives (Card, Button, etc.)
- `src/components/charts` — Recharts-based charts (e.g. `PaceDeltaChart.tsx`)
- `src/lib/utils.ts` — `cn()` and other helpers used by shadcn
- `components.json` — shadcn CLI config (style, aliases, Tailwind paths)
