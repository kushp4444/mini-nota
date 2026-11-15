# Mini-Nota Almanac UI revamp

## Design direction

Design for a visitor who wants to understand a completed imaging run without a statistics background, and a technical reviewer who wants to inspect the evidence. The primary actions are **Run analysis** on Patients and **View completed example** when exploring the demo. Use the existing curated run, its CT overlay, survival chart, and recorded decisions as the design material.

Use Hallmark Almanac at app-screen scope. The reference is a ruled sheet on cool slate stock, with blue-black ink and a small, deep magenta accent for the primary action, active selection, and primary chart series. Use Hanken Grotesk for headings, Newsreader for prose and labels, and IBM Plex Mono with tabular numerals for figures. Use two rule weights, square surfaces, compact controls, and immediate focus rings. Distinguish chart groups with labels and line styles as well as color. Use no decorative motion.

The signature is the **run record**: a plain-language finding, the chart or scan that supports it, and access to the recorded decision. Style this shared surface consistently across Analysis, Examples, and Run History.

## Screens

| Screen | Layout and priority |
| --- | --- |
| Patients | Lead with the patient index and a selection toolbar. Keep the selected count, selection controls, and Run analysis together. Keep the curated example easy to find. Use a ruled table and a distinct selected-row treatment. |
| Analysis | Put run status and the relevant action at the top. Use a stage index next to a single, wide reading sheet. Each result leads with its finding, then its evidence and optional details. Give the survival chart the full reading width and keep the fixed test group separate from the selected patients. |
| Examples | Keep the completed and failure examples available without starting a run. Use the same reading sheet as Analysis and make the example identity and any deliberately introduced faults visible. |
| Run History | Present saved runs as a ruled index with identifiers, timestamps, and status. Open the same result sheet, including saved evidence, interrupted stages, and the record of approvals. |
| Agent panel | Present the existing event sequence as a ruled log with clear event labels, timestamps, and details. Keep active approvals and recovery actions in the main flow where people need them. |

## Interaction and responsive layout

Keep the four existing destinations. At wide widths, place the run sheet and Agent panel side by side. At narrow widths, stack the log after the main task and contain wide tables in their own scroll regions. Keep the primary action within reach and preserve keyboard order. Style loading, empty, error, waiting-for-approval, canceled, and completed states using the existing behavior and visible recovery actions.

Preserve the compact feature table. Keep units and ⓘ tooltips in the patient detail list, with hover and keyboard access. Keep percentage labels, dotted drop guides, and exact day labels in the survival chart. Keep raw scores, model information, and structured records in their current disclosures.

## Planned changes and verification

- Edit the app shell and stylesheet for the navigation, responsive layout, and Almanac tokens. Update the existing result, history, and approval components in place where markup needs to support that layout. Keep existing routes, controls, audit events, and data contracts.
- Implement the shared run sheet first against the completed and failure examples. Then apply the same visual system to Patients, live Analysis, Run History, and the Agent panel.
- Put the running frontend in front of the user for manual review. Show Patients, the completed and failure examples, and Run History at desktop and narrow widths. Iterate on feedback until the user approves the design.
- After approval, decide what automated coverage the final design needs. Existing Playwright flows are the starting point. Defer writing or updating tests until then.

## HTML review workflow

The standalone mockup in mockups/almanac is now the design review surface. Lead with a concise finding, chart, and patient comparison. Collapse supporting explanations and detailed measurements. Iterate in HTML until the user approves, then adapt the Next.js worktree to match. Use Hallmark audits during mockup iteration. Automated test development follows user approval.
