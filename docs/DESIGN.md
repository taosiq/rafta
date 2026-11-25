# Design system

Calm and neutral, in the spirit of the Linear, Stripe and Vercel dashboards. All tokens live in [web/src/app/globals.css](../web/src/app/globals.css).

## Principles

* **Neutral by default.** White (light) or near-black (dark) surfaces, grey text, and **one accent colour (violet)** for primary actions, focus and the selected model.
* **Colour only where it means something.** Status colours are reserved, and **every status also carries an icon and a label**, so colour is never the only cue:

  | Status | Colour | Icon | Label |
  |---|---|---|---|
  | Stock-out risk | red `#d03b3b` | triangle | "Stock-out risk" |
  | Reorder soon | amber `#fab219` | clock | "Reorder soon" |
  | Healthy | green `#0ca30c` | check | "Healthy" |

* **Fixed class colours**, used identically on badges, the matrix, the logo and charts: **A blue `#2a78d6`, B orange `#eb6834`, C aqua `#1baf7a`** (dark mode: `#3987e5`, `#d95926`, `#199e70`). These are the first three slots of a CVD-validated categorical palette and pass all-pairs checks in both modes: worst colour-blind ΔE 9.2 light and 9.4 dark, against a target of ≥ 8. Badges always print the letter too.
* **Simulation policies** use their own validated set (violet, yellow, magenta), so they are never confused with classes. The uniform frontier is a neutral dashed reference line.
* **One font: Geist**, with tabular numbers (`.num`) and **right-aligned numbers** in every table.
* **An 8px spacing grid**, 1px borders instead of heavy shadows, generous white space.
* **Dark mode from day one.** It is class-based, with a separately chosen dark palette rather than an automatic inversion. An inline `<head>` script applies the saved theme before first paint, so the page never flashes the wrong theme. Light, dark and system modes are supported.

## Charts

* 2px lines and ≥ 8px markers with a 2px surface ring. Bars are at most 24px thick with 4px rounded data ends and a 2px surface gap between stacked segments.
* Recessive hairline grid; axis labels in muted ink. Text never takes on the series colour.
* A hover tooltip on every chart: one tooltip lists every series at that point, the value comes first, and the series key is a line stroke.
* A legend whenever there are two or more series; single-series charts are named by their title. Each chart has a table view nearby, which also provides the contrast relief the validator requires for lighter hues.
* No dual axes. Cost-vs-service is shown as a scatter on the frontier rather than as two y-scales.

## Accessibility

* Focus rings are visible (2px accent outline). Segmented controls are `radiogroup`s. Icon-only buttons have `aria-label`s.
* Assistant replies are announced through `aria-live`. Its markdown is rendered without `dangerouslySetInnerHTML`.
* Reduced motion is honoured.
