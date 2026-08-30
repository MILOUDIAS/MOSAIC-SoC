# integration/

The Chipathon D15 tapeout: the files the integrator gave us, and the run we
ship. Everything here is either someone else's input or our deliverable.

`experimental/` next door holds runs we invented to answer our own questions.
The split is the point. A directory of twenty margin-ladder experiments is a bad
place to keep the one artifact that becomes silicon.

## What is here

```
D15/project_defs/A/     the integrator's padframe files, from @d-m-bailey
  D15_A.def               167 pins, 1110 x 1110 um, consumed via FP_DEF_TEMPLATE
  D15_A_interface.yaml    generates our wrapper port list and pad settings
  D15_A_pad_map.yaml      user pin -> pad slot
  D15_A_padring.{cfg,def,v,svg}
D15/project_defs/D15_selected_variants.json
runs/blocka_padframe_def/   the signed-off run
final_blocka_padframe_def/  its saved views (gds, def, lef, lib, nl)
.generated_mosaic_block_a.yaml   derived hardening config
```

## The DEF

```
sha256 10420952b5f682f1c5a36127ef6f879a7a58134597dc64c090c973c329427185
```

Received 2026-08-25, reissued 2026-08-30 **byte-identical**. The 30 August drop
changed only `D15_A_interface.yaml` and `D15_A_pad_map.yaml`, and only the case
of the two power pins, `vdd`/`vss` to `VDD`/`VSS`, matching the labels in our
GDS. Regenerating the wrapper port list from the new interface produces a
byte-identical result, so the reissue required no re-harden.

`D15_selected_variants.json` did change materially: its `top_cell_text` went
from 24 GDS labels to 169, because the integrator re-read our 167-terminal
macro rather than the earlier 22-port one.

## Running here

`run_signoff.sh` writes wherever `MOSAIC_WORK_DIR` points, defaulting to
`experimental/`. For an integration run:

```bash
cd flow/librelane/experimental
MOSAIC_WORK_DIR=flow/librelane/integration \
MOSAIC_PIN_TEMPLATE="dir::D15/project_defs/A/D15_A.def" \
MOSAIC_HARDEN_FROM_SOC=configs/mosaic_tapeout_ultra.yaml \
MOSAIC_HARDEN_DESIGN=mosaic_block_a \
MOSAIC_HARDEN_UTIL=0.823 \
MOSAIC_CFG="$PWD/../../../configs/mosaic_tapeout_ultra.yaml" \
MOSAIC_MANIFEST=<bundle>/manifest.json \
  ./run_signoff.sh <tag>
```

Note the pin template is `dir::D15/...` here and `dir::../project_defs/D15/...`
was the experimental form. `dir::` resolves against the directory holding the
resolved config, which is now this one.

## One copy, on purpose

`signoff_library_limits.sdc` stays in `experimental/` and the shared template
reaches it as `dir::../experimental/signoff_library_limits.sdc`, which resolves
correctly from both directories. A second copy of a signoff SDC is a second
thing to keep in step, and the two would disagree the first time one was edited.

The DEF exists once, here. Two copies of an integration input is how a run gets
hardened against a file nobody is looking at.
