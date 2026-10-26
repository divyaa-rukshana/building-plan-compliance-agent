# Section 4.1 case: passages and test values (Member 2)

Case: *residential building on a small plot abutting a narrow road.*
Page numbers are the printed ones. For the bye-laws, printed page = PDF page. For the RMP 2015 zoning regulations, PDF page = printed page + 1. `verify_41.py` checks every row below against the PDFs.

## A. Passages the case depends on

### BBMP Building Bye-Laws 2003 (`bbmp_bylaws_2003.pdf`)

| Ref | Page | Text (short) | What it decides |
|---|---|---|---|
| 2.70 | 7 | "road width" = distance between road boundaries incl. footways and drains, measured at right angles to the centre of the plot; service roads are added for FAR and number of floors | How the input `road_width_m` is defined |
| 2.46 | 5 | high-rise = ground floor plus four or more floors | When 9.3.x applies |
| 9.2 | 21 | setbacks, coverage, FAR, floors and heights are set out in Tables 4, 5 and 6 | Entry point; note the tables contain no height column |
| Table 4 | 22 | Residential setbacks up to 9.5 m: front/rear by site depth, left/right by site width | Setbacks, low-rise |
| Table 5 | 23 | Above 9.5 m: one setback all round by building height (4.5 m for 9.5-12 m, 5.0 for 12-15, 6.0 for 15-18 ...) | Setbacks, taller |
| Table 6 | 24 | Coverage and FAR by plot area, separately for areas A, B, C; last column is road width | FAR and coverage |
| Note 3 | 25 | (a) front/rear use depth, (b) left/right use width, (c) above 9.5 m take the higher of Tables 4 and 5 | How to read Tables 4 and 5 |
| 9.3.2, 9.3.3 | 26 | High-rise needs a site dimension of at least 21 m and a road of at least 12 m | Narrow-road restriction on tall buildings |
| 9.10.1 | 27 | Area A, B or C is set by a BDA map | `area_class` must be an input |
| 9.10.4 | 28 | If the site does not face the road width listed against its row, the FAR for the corresponding road width applies | **Road width lowers FAR** |
| 9.10.5 | 29 | If the site faces a wider road than its row, FAR is limited to the plot-area row | Cap in the other direction |
| 9.10.7 | 29 | Setbacks and coverage are determined irrespective of road width | Coverage does not follow road width |
| 15.1 | 33 | Height is governed by FAR, coverage, setbacks and street width "as stipulated in the respective tables" | No number: height is derived, not looked up |

### BDA Zoning Regulations, Revised Master Plan 2015 (`bda_zoning_regs_rmp2015.pdf`)

| Ref | Page | Text (short) | What it decides |
|---|---|---|---|
| 4.1.2(ii)(b) | 27 | If road width is less than 9.0 m, maximum height is 11.5 m or Stilt+GF+2 floors, whichever is less, irrespective of FAR | **The explicit road-width height cap** |
| 4.1.2(ii)(c) | 27 | Apartments only on plots above 360 sq m (Rings I, II) or 750 sq m (Ring III), and road wider than 9.0 m | Narrow road excludes apartments |
| Table 10 | 27 | Residential (Main): plot up to 360 sq m, 75% coverage, FAR 1.75, road up to 12 m | Conflicts with bye-law Table 6 (see B) |
| Table 8 | 19 | Setbacks up to 11.5 m as % of depth/width (1.0 m all round for width 6-9 m; 12% front, 8% rear/sides above 9 m) | Conflicts with bye-law Table 4 |
| Table 9, 3.2 | 20 | Setbacks above 11.5 m; road width definition | Taller buildings |

Not usable as-is: `bda_zoning_amendments_feb2015.pdf` (notification dated 20/03/2015, 3 pages) has **no text layer**; it needs OCR (tesseract) before indexing. It amends ancillary commercial use in residential zones and does not change the numbers above. `bbmp_violation_procedure_2007.pdf` is about complaints and occupancy certificates; keep it out of the index (useful as an out-of-corpus test).

## B. Two documents disagree: decide before Tuesday

For the same small plot the two documents give different numbers.

| Quantity (9 m x 12 m, 108 sq m, road 6 m) | Bye-laws 2003 | RMP 2015 |
|---|---|---|
| FAR | 0.75 (Table 6, area A) | 1.75 (Table 10) |
| Coverage | 65% | 75% |
| Front / rear setback | 1.50 / 1.50 m | 12% of 12 m = 1.44 m / 8% = 0.96 m |
| Height | no number (15.1) | 11.5 m or Stilt+GF+2 (4.1.2(ii)(b)) |

The brief (F7) says to escalate when provisions conflict. Proposed reference behaviour: the agent cites both, reports each value, flags the FAR/coverage/setback conflict, and routes to **specialist-review**, while still applying the height cap and the 9.10.4 reduction as findings. Confirm this with the faculty at Evaluation 1.

## C. Test values (run `python eval1_member2/verify_41.py`)

Inputs: `area_class`, `plot_width_m`, `plot_depth_m`, `road_width_m`, `height_m`, `storeys`, `use`.

| Case | Input | Expected from bye-laws |
|---|---|---|
| EX1 | A, 9 x 12 m, road 6 m, 7.5 m, 2 storeys | Setbacks F1.50 R1.50 L1.00 R1.00; coverage 65%; FAR 0.75 (81 sq m) |
| EX2 (road-width effect) | A, 20 x 30 m = 600 sq m, road 6 m, 7.5 m | Plot row says FAR 1.00, road row says 0.75; **FAR 0.75** (9.10.4); coverage **60%**, not 65% (9.10.7); max floor area 450 sq m |
| EX3 | A, 9 x 12 m, road 6 m, 13 m, 4 storeys | Setbacks 5.0 m all round (Table 5, 12-15 m); 13 m exceeds the RMP 11.5 m cap |
| EX4 | A, 20 x 30 m, road 6 m, 16 m, 5 storeys | High-rise; fails road >= 12 m (9.3.3) and site >= 21 m (9.3.2); setbacks 6.0 m |

Correction to the team plan: for EX2 the plan gives FAR only. Coverage must be 60% from the plot-area row, because 9.10.7 says coverage ignores road width, whereas the 6 m road row would suggest 65%.
