# Engine Architecture

WGE-0 imports and validates authority. It has no behavior engine.

Future flow:

`Source Profile → Validated SessionPackPlan → SessionPlan → RenderPlan → Exporter`

The types are inert seams. No plan can currently be built or executed.
