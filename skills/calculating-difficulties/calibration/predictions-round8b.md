# Predictions — round 8B (anchor selection freed from the floor)

Blind: the predicting agents saw the statement text and the runtime references, never
a true rating and never the calibration directory. The eval prompt is verbatim from the
2026-09-16 generation, unchanged since round 1.

Varies against **8A** in exactly one thing: Pass C searches the whole anchor table by match
quality instead of the window `[floor, floor+600]`, and the floor is left to the Pass E clamp
it already was. Pass B's ceiling paragraph, the "two categories are enough" rule and the
widening rule move with it — they were all statements about the window. Anchor set,
`tag-floors.md`, Pass C.1 and Pass D arithmetic identical to 8A.

Batch 1 cited four anchors per slot where the rubric asks for 2-3; the extra citation does
not enter the score, which reads column 2 only.

| slot | predicted | floor | anchors used |
|---|---|---|---|
| eval-01 | 2000 | 1100 | 976D, 1453D, 1758D, 1207B |
| eval-02 | 2400 | 1700 | 1301E, 1743F, 2025E, 1513D |
| eval-03 | 2200 | 1700 | 1691F, 1594E2, 1292C, 1187E |
| eval-04 | 2300 | 1200 | 1556F, 1909F1, 1265E, 1824B1 |
| eval-05 | 1900 | 1100 | 979D, 1656D, 1612D, 1242A |
| eval-06 | 1400 | 1100 | 995A, 2084C, 1207B |
| eval-07 | 1200 | 1100 | 1513B, 2092C, 1762B |
| eval-08 | 1800 | 1200 | 2025E, 1717D, 1513B |
| eval-09 | 2000 | 1700 | 1594E2, 2133D, 2018C |
| eval-10 | 1300 | 1100 | 1758D, 2084C, 1140D |
| eval-11 | 1400 | 1100 | 1207B, 2084C, 1758D |
| eval-12 | 2000 | 1400 | 1923D, 990E, 2025E |
| eval-13 | 1300 | 1100 | 919C, 2152B, 1841E |
| eval-14 | 1800 | 1700 | 1993C, 2133D, 2025E |
| eval-15 | 2100 | 1100 | 2084C, 995A, 976D |
| eval-16 | 1900 | 1200 | 1905D, 1995C, 1993C |
| eval-17 | 1600 | 1200 | 1513D, 1612D, 1242A |
| eval-18 | 1500 | 1100 | 1924A, 2127C, 2211C1 |
| eval-19 | 2300 | 1200 | 2002D2, 1909F1, 932D |
| eval-20 | 1800 | 1200 | 979D, 2140C, 2160C |
| eval-21 | 1800 | 1100 | 1114E, 1797C, 2152B |
| eval-22 | 2000 | 1100 | 1981D, 1513D, 1228C |
| eval-23 | 2400 | 1700 | 1188C, 2025E, 1265E |
| eval-24 | 1100 | 1100 | 1059B, 1355A, 955A |
