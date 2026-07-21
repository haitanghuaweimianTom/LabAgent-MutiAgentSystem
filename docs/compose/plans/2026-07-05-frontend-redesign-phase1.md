# Frontend Redesign Phase 1: Infrastructure + Design System

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up Tailwind CSS v4 + shadcn/ui + Framer Motion + Lucide React, configure dark mode design system, create base components, and restructure root layout to three-column layout.

**Architecture:** Migrate from CSS Modules to Tailwind CSS v4 with shadcn/ui components. Keep existing component logic intact, replace styling layer. Dark mode first with light mode support.

**Tech Stack:** Next.js 14.1, React 18.2, Tailwind CSS v4, shadcn/ui, Framer Motion, Lucide React, Zustand

## Global Constraints

- Next.js 14.1.0 (App Router) — no upgrade
- React 18.2 — no upgrade
- Existing backend API contracts unchanged
- Existing Zustand store unchanged (useAppStore.ts)
- All existing functionality must continue to work after each task
- Dark mode is default, light mode is secondary
- Font: Inter (English) + Noto Sans SC (Chinese) + JetBrains Mono (code)
- Color scheme per spec: Primary #3B82F6, Secondary #6366F1, Background #0F172A

---

## Task 1: Install Dependencies and Configure Tailwind

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/postcss.config.js`
- Modify: `frontend/src/app/globals.css`

**Steps:**

- [ ] **Step 1: Install core dependencies**

```bash
cd /home/tomgame/projects/MathModel-MutiAgentSystem/frontend
npm install tailwindcss @tailwindcss/postcss postcss autoprefixer
npm install framer-motion lucide-react
npm install class-variance-authority clsx tailwind-merge
```

- [ ] **Step 2: Install shadcn/ui**

```bash
npx shadcn@latest init
# Select: New York style, Slate base color, CSS variables: yes
```

- [ ] **Step 3: Configure postcss.config.js**

```js
// frontend/postcss.config.js
module.exports = {
  plugins: {
    '@tailwindcss/postcss': {},
    autoprefixer: {},
  },
}
```

- [ ] **Step 4: Configure tailwind.config.ts**

```ts
// frontend/tailwind.config.ts
import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: [
    './src/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        background: '#0F172A',
        foreground: '#F8FAFC',
        primary: {
          DEFAULT: '#3B82F6',
          foreground: '#FFFFFF',
        },
        secondary: {
          DEFAULT: '#6366F1',
          foreground: '#FFFFFF',
        },
        muted: {
          DEFAULT: '#1E293B',
          foreground: '#94A3B8',
        },
        border: 'rgba(148, 163, 184, 0.12)',
        card: 'rgba(30, 41, 59, 0.6)',
      },
      fontFamily: {
        sans: ['Inter', 'Noto Sans SC', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        lg: '8px',
        '2xl': '16px',
        '3xl': '24px',
      },
      boxShadow: {
        glow: '0 0 40px rgba(59, 130, 246, 0.08)',
        'glow-lg': '0 0 60px rgba(59, 130, 246, 0.15)',
      },
      backdropBlur: {
        xl: '24px',
      },
    },
  },
  plugins: [],
}
export default config
```

- [ ] **Step 5: Update globals.css with Tailwind directives**

Replace current `globals.css` content with Tailwind v4 imports + custom design tokens.

- [ ] **Step 6: Verify build**

```bash
npm run build
```

Expected: Build succeeds with no Tailwind errors.

---

## Task 2: Create Base UI Components

**Files:**
- Create: `frontend/src/components/ui/glass-card.tsx`
- Create: `frontend/src/components/ui/glow-button.tsx`
- Create: `frontend/src/components/ui/agent-badge.tsx`
- Create: `frontend/src/components/ui/status-dot.tsx`
- Create: `frontend/src/lib/utils.ts`

**Steps:**

- [ ] **Step 1: Create utils.ts**

```ts
// frontend/src/lib/utils.ts
import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

- [ ] **Step 2: Create GlassCard component**

A glassmorphism card with backdrop-blur, semi-transparent background, subtle border, and glow on hover.

```tsx
// frontend/src/components/ui/glass-card.tsx
'use client'

import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'

interface GlassCardProps {
  children: React.ReactNode
  className?: string
  hover?: boolean
  onClick?: () => void
}

export function GlassCard({ children, className, hover = true, onClick }: GlassCardProps) {
  return (
    <motion.div
      whileHover={hover ? { scale: 1.01, boxShadow: '0 0 60px rgba(59, 130, 246, 0.12)' } : undefined}
      className={cn(
        'rounded-2xl border border-border bg-card backdrop-blur-xl p-6',
        hover && 'cursor-pointer transition-colors',
        className
      )}
      onClick={onClick}
    >
      {children}
    </motion.div>
  )
}
```

- [ ] **Step 3: Create GlowButton component**

A button with gradient background, glow effect on hover, and click animation.

- [ ] **Step 4: Create AgentBadge component**

An agent status badge with colored dot, agent name, and optional pulse animation for active agents.

- [ ] **Step 5: Create StatusDot component**

A small colored dot for status indicators (green=running, blue=pending, red=failed, gray=idle).

---

## Task 3: Update Root Layout to Three-Column Structure

**Files:**
- Modify: `frontend/src/app/layout.tsx`
- Create: `frontend/src/components/layout/Sidebar.tsx`
- Create: `frontend/src/components/layout/MainWorkspace.tsx`
- Create: `frontend/src/components/layout/TopBar.tsx`

**Steps:**

- [ ] **Step 1: Create Sidebar component**

Left sidebar (260px) with:
- Logo + system name
- New task button (gradient, glow)
- Project list (current task history)
- Bottom: settings link + theme toggle

- [ ] **Step 2: Create TopBar component**

Top bar with breadcrumb navigation, search, and user info.

- [ ] **Step 3: Create MainWorkspace component**

Main content area that renders the active tab's content.

- [ ] **Step 4: Update layout.tsx**

Replace current layout with three-column structure. Keep existing `<html>` and `<body>` structure, add sidebar and main workspace wrapper.

- [ ] **Step 5: Verify layout renders correctly**

```bash
npm run dev
```

Expected: Three-column layout visible, sidebar on left, main content in center.

---

## Task 4: Migrate Dashboard Tab

**Files:**
- Modify: `frontend/src/app/page.tsx` (tab routing logic)
- Create: `frontend/src/components/dashboard/StatCard.tsx`
- Create: `frontend/src/components/dashboard/ActivityTimeline.tsx`

**Steps:**

- [ ] **Step 1: Create StatCard component**

A glassmorphism stat card with icon, label, value, and optional mini chart.

- [ ] **Step 2: Create ActivityTimeline component**

A timeline showing recent agent execution records with timestamps and status.

- [ ] **Step 3: Update page.tsx dashboard tab**

Replace current dashboard tab content with new components. Keep all existing state management and API calls intact.

- [ ] **Step 4: Verify dashboard renders**

Expected: Dashboard shows stat cards and activity timeline with proper dark theme styling.

---

## Task 5: Migrate Generate Tab (Task Creation)

**Files:**
- Create: `frontend/src/components/task/TaskInput.tsx`
- Create: `frontend/src/components/task/AgentChip.tsx`

**Steps:**

- [ ] **Step 1: Create TaskInput component**

Large central input area with:
- Text input for research topic
- Template selector dropdown
- Submit button with gradient + loading animation

- [ ] **Step 2: Create AgentChip component**

Selectable chip for choosing which agents participate. Shows agent icon + name, toggleable.

- [ ] **Step 3: Update page.tsx generate tab**

Replace current ProblemInput with new TaskInput. Keep all API integration.

- [ ] **Step 4: Verify task creation works**

Expected: Can type a topic, select template, submit task. All existing functionality preserved.

---

## Task 6: Migrate Remaining Tabs (Quick Pass)

**Files:**
- Modify: Existing component files (SystemStatusClient, TaskHistory, AgentManager, etc.)

**Steps:**

- [ ] **Step 1: Update SystemStatusClient styles**

Replace CSS Module classes with Tailwind classes. Keep component logic.

- [ ] **Step 2: Update TaskHistory styles**

Same approach — Tailwind classes, keep logic.

- [ ] **Step 3: Update AgentManager, FileManager, SettingsPage, etc.**

Batch update all remaining tab components.

- [ ] **Step 4: Verify all tabs work**

Expected: All 10 tabs render correctly with new design system.

---

## Task 7: Add Framer Motion Animations

**Files:**
- Modify: Various component files

**Steps:**

- [ ] **Step 1: Add page transition animations**

AnimatePresence for tab switching.

- [ ] **Step 2: Add staggered list animations**

Task history, agent list, file list — items appear with stagger.

- [ ] **Step 3: Add hover micro-interactions**

Cards glow, buttons float, status dots pulse.

- [ ] **Step 4: Verify animations are smooth**

Expected: 60fps animations, no jank.

---

## Task 8: Light Mode Support + Final Polish

**Files:**
- Modify: `tailwind.config.ts`
- Modify: `globals.css`
- Create: `frontend/src/hooks/useTheme.ts`

**Steps:**

- [ ] **Step 1: Create useTheme hook**

Toggle between dark and light mode, persist to localStorage.

- [ ] **Step 2: Add light mode color overrides**

CSS variables for light mode: background #F8FAFC, foreground #0F172A, etc.

- [ ] **Step 3: Add theme toggle to sidebar**

Sun/Moon icon toggle in sidebar bottom.

- [ ] **Step 4: Final build verification**

```bash
npm run build
```

Expected: Clean build, all tabs work in both themes.
