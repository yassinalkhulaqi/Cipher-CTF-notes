# Motion system

RedScribe treats motion as interface feedback, not decoration. Every animation
explains where a surface came from, where it went, or what changed. The system is
small, dependency-free, and runs entirely on the client.

## Design principles

1. **Motion explains.** Page changes cross-fade with a short rise, rows glide to
   their new positions, and modals arrive from the surface behind them. Nothing
   moves without a reason.
2. **Springs over linear curves.** Spatial motion uses damped springs; opacity
   and colour use short eased transitions. Linear timing is reserved for spinners
   and progress.
3. **Fast by default.** Most feedback completes in 140–220 ms. Hero entrances cap
   at 520 ms. Nothing blocks input.
4. **One preference, everywhere.** `System`, `Full`, `Subtle`, and `Off` are
   available in **Settings → Motion** and in the **Motion lab**. The choice is
   stored locally and applied before the first animation frame.
5. **Compositor-friendly.** Animated properties are limited to `transform`,
   `opacity`, `filter`, and CSS custom properties. Layout-affecting animations
   are avoided; height changes use the grid-track technique in `Collapse`.

## Modes

| Mode   | Resolved level  | Behaviour                                                              |
| ------ | --------------- | ---------------------------------------------------------------------- |
| System | `off` or `full` | Follows `prefers-reduced-motion`.                                      |
| Full   | `full`          | Springs, tilt, parallax, stagger, and ambient fields.                  |
| Subtle | `subtle`        | Shorter travel, softer tilt, no ambient pointer glow.                  |
| Off    | `off`           | Transitions collapse to sub-millisecond durations; ambience is hidden. |

The preference lives in `localStorage` under `redscribe.motion.mode`. Unknown
values fall back to `system`, so a stale or hand-edited value cannot break the
interface.

`MotionProvider` writes the resolved state to the document:

```html
<html
  data-motion="full"
  data-motion-mode="system"
  data-motion-ready="true"
  style="--motion-scale: 1"
></html>
```

CSS keys off those attributes. JavaScript reads the same values through
`useMotion()` (React) or `motionEnabled()` / `motionScale()` (outside React).

## Tokens

`src/styles/motion-tokens.css` defines the shared vocabulary:

- `--motion-duration-instant` through `--motion-duration-cinematic`
- `--motion-ease-out`, `--motion-ease-out-soft`, `--motion-ease-in-out`,
  `--motion-ease-spring`, `--motion-ease-sharp`
- `--motion-distance`, `--motion-stagger-step`
- `--motion-press-scale`, `--motion-lift`, `--motion-glow-opacity`

`html[data-motion="subtle"]` scales durations and travel down without changing
the interaction model. `html[data-motion="off"]` removes movement and ambient
layers.

The TypeScript mirror lives in `src/motion/config.ts` (`DURATION`, `EASE`,
`SPRING`, `STAGGER`, `DISTANCE`, `SCALE`). Keep the two files in sync when tuning.

## Engine

| Module                       | Purpose                                                                                                   |
| ---------------------------- | --------------------------------------------------------------------------------------------------------- |
| `MotionProvider.tsx`         | Resolves the mode, writes document attributes, exposes `useMotion`, `useMotionLevel`, `useReducedMotion`. |
| `math.ts`                    | Clamp, lerp, damp, spring integration, settle checks, stagger, velocity sampling.                         |
| `useSpring.ts`               | Spring value driven by `requestAnimationFrame`.                                                           |
| `useRaf.ts`                  | Shared animation-frame helper.                                                                            |
| `usePresence.ts`             | Tracks exit windows for presence-style components.                                                        |
| `AnimatePresence.tsx`        | Keeps removed items mounted until their exit animation finishes.                                          |
| `useFlipList.ts`             | FLIP animation for `[data-node-id]` rows when order or expansion changes.                                 |
| `useFloatingSelection.ts`    | Measures the selected tree row so one indicator can slide between rows.                                   |
| `useCardTilt.ts`             | Pointer tilt and spotlight for `[data-tilt]` surfaces.                                                    |
| `useMagnetic.ts`             | Spring-based magnetic offset for a specific element.                                                      |
| `useGlobalRipple.ts`         | Delegated ripple on buttons and interactive rows.                                                         |
| `useScrollReveal.ts`         | Reveals `[data-reveal]` elements once they enter the viewport.                                            |
| `useInView.ts`               | IntersectionObserver wrapper used by `Reveal`.                                                            |
| `CursorGlow.tsx`             | Damped ambient glow that follows a fine pointer.                                                          |
| `Aurora.tsx`                 | Three slow drifting colour fields behind the workspace.                                                   |
| `AnimatedNumber.tsx`         | Spring-interpolated counters with tabular figures.                                                        |
| `Skeleton.tsx`               | Shimmer placeholder lines.                                                                                |
| `ScrollProgress.tsx`         | Thin reading-progress bar for the editor.                                                                 |
| `Reveal.tsx` / `Stagger.tsx` | Declarative entrance helpers.                                                                             |
| `Collapse.tsx`               | Grid-track height transition.                                                                             |
| `Confetti.tsx`               | Short canvas burst when a flag is copied.                                                                 |

`Confetti` is intentionally canvas-based and time-boxed. It is disabled in
subtle and off modes and never intercepts pointer events.

## Motion map

| Surface     | Behaviour                                                                                 |
| ----------- | ----------------------------------------------------------------------------------------- |
| Boot        | Orbiting rings, breathing mark, indeterminate progress, staged copy.                      |
| Page switch | `.motion-page` rises and fades when the dashboard or a note mounts.                       |
| Sidebar     | Rows stagger in, FLIP on expand/filter, one sliding selection indicator, drag/drop pulse. |
| Top bar     | Brand tilt, ambient vault dot, command-trigger sweep, theme view transition.              |
| Dashboard   | Counters spring, panels tilt with a spotlight, work rows stagger, flags burst on copy.    |
| Editor      | Reading progress, focus glow on the title, view-switch spring, pane cross-fade.           |
| Modals      | Backdrop and dialog enter/exit, settings sections stagger, palette rows cascade.          |
| Toasts      | Spring entrance, progress bar, presence-managed exit.                                     |
| Menus       | Origin-aware scale from the pointer, row cascade.                                         |
| Theme       | Circular `clip-path` reveal via the View Transitions API when available.                  |

## Accessibility contract

- `System` mode honours `prefers-reduced-motion: reduce`; animations collapse and
  reveal elements become visible immediately.
- `Full` mode lets a user opt back in even when the OS requests reduced motion.
- `Off` mode is an explicit kill switch for every animation, transition, and
  ambient layer, including pseudo-elements.
- Focus outlines are never animated away. Closing dialogs stop trapping focus.
- Motion never carries meaning alone: status, selection, and save state also have
  text, icons, or colour.
- The Motion lab shows the current preference and states when motion is paused.

## Performance rules

- Do not animate `width`, `height`, `top`, or `left`; use transforms or the
  `Collapse` grid track.
- Each element should have one owner for its transform. FLIP and tilt both write
  `transform`, so do not put `data-tilt` on tree rows.
- Use `will-change` only on elements that animate repeatedly, and remove it when
  idle.
- Canvas particles are capped and cleaned up on unmount and resize.
- Ambient layers are disabled on coarse pointers and in subtle mode.

## Testing

```bash
cd frontend
npm test
```

The test command runs the TypeScript check, bundles the motion tests, and runs
them with `node:test`. Coverage includes interpolation, spring settling,
stagger caps, preference normalization, reduced-motion resolution, duration
ordering, and the presence of motion tokens, keyframes, and kill switches.

### Manual checklist

1. Open **Settings → Motion** and switch between all four modes.
2. Open the **Motion lab** and replay the stagger, counter, collapse, and burst.
3. Expand, collapse, and filter the tree; the selection indicator should glide.
4. Copy a captured flag from the dashboard; the burst should respect the mode.
5. Toggle the theme from the top bar on a Chromium browser; the circular reveal
   should originate at the button.
6. Enable the OS reduced-motion setting with mode set to **System**; all movement
   should stop.
7. Set mode to **Off** and confirm no ambient glow, confetti, or transitions
   remain.

## Adding motion

1. Prefer a CSS transition with the shared tokens for simple hover/focus states.
2. Use `useSpringValue` for values that need physical interpolation.
3. Use `useFlipList` for reordered lists; give rows stable `data-node-id` keys.
4. Use `AnimatePresence` when a removed element needs an exit animation.
5. Add the selector to the reduced-motion and off-mode audits in
   `motion-accessibility.css` if it introduces a new animation pattern.
6. Update this document and the Motion lab when adding a new primitive.
