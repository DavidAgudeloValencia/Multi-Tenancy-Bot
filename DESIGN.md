---
name: BotManager Admin
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#444653'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#747684'
  outline-variant: '#c4c5d5'
  surface-tint: '#3456c1'
  primary: '#00216e'
  on-primary: '#ffffff'
  primary-container: '#0033a0'
  on-primary-container: '#8ea6ff'
  inverse-primary: '#b6c4ff'
  secondary: '#735c00'
  on-secondary: '#ffffff'
  secondary-container: '#fecc00'
  on-secondary-container: '#6e5700'
  tertiary: '#180090'
  on-tertiary: '#ffffff'
  tertiary-container: '#2a12c5'
  on-tertiary-container: '#a3a0ff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dce1ff'
  primary-fixed-dim: '#b6c4ff'
  on-primary-fixed: '#001550'
  on-primary-fixed-variant: '#133ca8'
  secondary-fixed: '#ffe089'
  secondary-fixed-dim: '#f0c100'
  on-secondary-fixed: '#241a00'
  on-secondary-fixed-variant: '#574500'
  tertiary-fixed: '#e2dfff'
  tertiary-fixed-dim: '#c3c0ff'
  on-tertiary-fixed: '#0f0069'
  on-tertiary-fixed-variant: '#3323cc'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  title-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  container-max: 1440px
  gutter: 24px
  margin-mobile: 16px
  margin-desktop: 40px
---

## Brand & Style
The design system is engineered for a high-stakes B2B insurance environment, balancing the institutional stability of Sura with the forward-leaning intelligence of AI. The aesthetic is **Corporate Modern** with **Technical Minimalism**, prioritizing speed of cognition and professional trust.

The UI should evoke a sense of "Augmented Expertise"—where the agent feels empowered, not replaced, by technology. We achieve this through generous whitespace, a structured systematic layout, and a "Techy Indigo" signature that denotes AI-driven insights. The interface is crisp and disciplined, avoiding unnecessary decoration to ensure that complex data remains the focal point.

## Colors
This design system utilizes a high-contrast palette to drive institutional authority and functional clarity.

- **Primary (Sura Blue):** Used for navigation, primary actions, and headers to establish brand presence and trust.
- **Secondary (Sura Yellow):** Used sparingly as a high-visibility accent for highlights or "New" badges. Never used for primary buttons to ensure AAA accessibility.
- **AI Accent (Indigo):** Specifically reserved for AI features, bot status, and automated insights. This separates human-generated data from machine-generated suggestions.
- **Success Green:** Dedicated to lead status, positive financial indicators, and completed uploads.
- **Neutral/Background:** A foundation of Slate and Cool Grey ensures the interface feels airy and professional, reducing eye strain during long working sessions.

## Modo oscuro (tema activo)

El panel de administración usa **modo oscuro** (aplicado con la skill
`dark-mode-design`). El YAML de arriba es la referencia clara; la paleta
activa es la siguiente:

**Principios (dark-mode-design):**
- Reducir la luminancia total para aliviar la fatiga visual.
- Jerarquía de superficies por **tonos más claros**, no por sombras.
- Primario desaturado 10-20 % y aclarado para contrastar sobre fondo oscuro.
- Texto *off-white* (`#e6e8ee`), nunca blanco puro.
- Bordes blancos de baja opacidad.
- Contraste mínimo **4.5:1** para texto corporal.

**Tokens oscuros:**

| Token | Valor | Uso |
|---|---|---|
| `--bg` | `#0d1425` | Fondo (lo más oscuro) |
| `--surface` | `#131c33` | Superficie 1: tarjetas |
| `--surface-dim` | `#1a2540` | Superficie 2: inputs, celdas |
| `--surface-3` | `#202c4d` | Superficie 3: tooltips, modales |
| `--nav-bg` | `#0a1a3d` | Sidebar (Azul Sura profundo) |
| `--border` | `rgba(255,255,255,.08)` | Bordes (blanco baja opacidad) |
| `--outline` | `rgba(255,255,255,.16)` | Campos, contornos |
| `--primary` | `#4d8df7` | Acciones principales (Sura blue desaturado) |
| `--primary-hover` | `#6ba3f9` | Hover de acciones principales |
| `--on-primary` | `#0b1c30` | Texto sobre `--primary` (contraste alto) |
| `--secondary` | `#fecc00` | Acentos puntuales (Sura Yellow) |
| `--ai` | `#6366f1` | IA: botones y acentos (Indigo) |
| `--ai-container` | `rgba(129,140,248,.15)` | Fondo de chips/etiquetas IA |
| `--on-ai` | `#c7d2fe` | Texto sobre fondo IA |
| `--success` | `#4ade80` | Éxito / activo |
| `--success-container` | `rgba(34,197,94,.14)` | Chips de estado activo |
| `--error` | `#f87171` | Errores / texto de error |
| `--danger` | `#dc4c4c` | Botones destructivos (blanco legible) |
| `--error-container` | `rgba(239,68,68,.14)` | Chips de estado desactivado |
| `--text` | `#e6e8ee` | Texto principal (off-white) |
| `--text-muted` | `#9aa7bd` | Texto secundario |

**Elevación:** en oscuro las sombras son ambientales y sutiles
(`0 1px 3px rgba(0,0,0,.45)`); la jerarquía la dan las superficies más
claras, no las sombras.

## Typography
We use **Inter** across all levels for its exceptional legibility in data-dense environments. 

The type scale is strictly hierarchical. **Display and Headline** styles use tighter letter spacing and heavier weights to feel "architectural" and grounded. **Body** text is optimized for reading long-form policy details and lead notes. **Label** styles are used for metadata and table headers, often utilizing a slight tracking increase for readability at small sizes. All numerical data in tables should use tabular figures if available to ensure columns align perfectly.

## Layout & Spacing
The design system employs a **12-column fluid grid** for the main content area, with a persistent sidebar for primary navigation. 

- **Desktop:** 12 columns, 24px gutters, 40px external margins.
- **Tablet:** 8 columns, 16px gutters, 24px external margins.
- **Mobile:** 4 columns, 16px gutters, 16px external margins.

The spacing rhythm is based on a **8px square grid**. Component padding should always be a multiple of 8 (e.g., 16px, 24px, 32px) to maintain visual harmony. Large-scale layouts for Agent Dashboards use a "Pinned" left navigation to allow the content area to breathe and expand.

## Elevation & Depth
Hierarchy is established through **Tonal Layering** and **Soft Ambient Shadows**. 

The background uses the neutral `#F8FAFC`, while the primary containers (cards, data tables) use pure `#FFFFFF`. This "Level 1" elevation is supported by a very subtle 1px border (`#E2E8F0`) and a diffused shadow: `0px 4px 6px -1px rgba(0, 0, 0, 0.05)`.

- **Resting State:** Low elevation, 1px border.
- **Hover/Active State:** Increased shadow depth to indicate interactivity.
- **Modals/Overlays:** Significant backdrop blur (12px) and a "Level 3" shadow to focus the agent's attention on the task at hand (e.g., PDF upload).

## Shapes
We use a **Rounded** shape language to soften the corporate tone and make the platform feel modern and accessible.

Standard components like buttons and input fields utilize a **8px (0.5rem)** radius. Larger structural elements like Dashboard Cards or Policy Detail Containers use **16px (1rem)** for a more distinct, sophisticated look. This consistency in rounding ensures that even data-heavy screens feel approachable rather than intimidating.

## Components
- **Data Tables:** Clean, row-based layouts with no vertical dividers. Use a subtle zebra-striping on hover. The first column (usually Lead Name) should be semi-bold in Sura Blue.
- **Lead Status Chips:** Small, pill-shaped indicators. Use a light background tint with a dark text color (e.g., Success Green background at 10% opacity with 100% opacity text).
- **Primary Buttons:** Solid Sura Blue with white text, 8px radius. Secondary buttons should use a Sura Blue outline with no fill.
- **AI Bot Configuration Cards:** These should feature an Indigo border-top (3px) and an icon-led header to distinguish them from standard management cards.
- **File Upload Zones:** A dashed border in neutral-300 with a large "Cloud" icon. Upon drag-over, the border transitions to Sura Blue.
- **Inputs:** Standardized height of 44px for professional feel. Focus states must use a 2px Sura Blue ring.
- **Agent Management Cards:** Use a vertical layout with a small avatar, name in title-md, and a grid of 2x2 metadata (Active Leads, Commission, etc.) for quick scanning.