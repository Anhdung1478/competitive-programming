# Predictions — round 9B (whole-table anchor selection, fresh held-out set)

Blind: statements from `blind2/`, runtime references only, never a true rating and never
the calibration directory. Eval prompt verbatim from the 2026-09-16 generation.

Varies against **9A** in exactly one thing: Pass C searches the whole anchor table by match
quality instead of the window `[floor, floor+600]`, with the floor left to the Pass E clamp.
Pass B's ceiling paragraph, the "two categories" rule and the widening rule move with it.
Anchor set, `tag-floors.md`, Pass C.1 and Pass D arithmetic identical to 9A.

| slot | predicted | floor | anchors used |
|---|---|---|---|
| fresh-01 | 1200 | 1200 | 1166C, 1257C, 955A |
| fresh-02 | 1400 | 1200 | 1389B, 2111D, 1130B |
| fresh-03 | 1200 | 1100 | 1242A, 1076C, 1140D |
| fresh-04 | 1300 | 1100 | 1299A, 1775B, 1207B |
| fresh-05 | 2000 | 1100 | 1943B, 1656D, 1804C |
| fresh-06 | 1100 | 1100 | 1140D, 934B, 955A |
| fresh-07 | 1400 | 1200 | 1995C, 1993C, 1832C |
| fresh-08 | 1500 | 1400 | 1370D, 1989C, 1923B |
| fresh-09 | 1600 | 1100 | 1656D, 1804C, 2092C |
| fresh-10 | 1700 | 1200 | 1379C, 1478C, 1166C |
| fresh-11 | 2300 | 1200 | 2248F, 2210D, 1656D |
| fresh-12 | 1700 | 1100 | 1513E, 1188A1, 1051A |
| fresh-13 | 1500 | 1100 | 1758D, 2084C, 1207B |
| fresh-14 | 1300 | 1100 | 1612D, 1804C, 1541B |
| fresh-15 | 1200 | 1100 | 1313C1, 1775B, 1051A |
| fresh-16 | 1600 | 1400 | 2112D, 1481C, 1993C |
| fresh-17 | 1500 | 1100 | 1656D, 2084C, 2092C |
| fresh-18 | 1400 | 1100 | 1327E, 2160C, 1257C |
| fresh-19 | 1600 | 1200 | 1120A, 1073D, 1166C |
| fresh-20 | 1600 | 1100 | 1379C, 1129A2, 1481C |
| fresh-21 | 1600 | 1100 | 2173D, 2245C, 1775B |
| fresh-22 | 2100 | 1100 | 1282D, 1114E, 1797C |
| fresh-23 | 1800 | 1400 | 1987E, 2112D, 1406C |
| fresh-24 | 1700 | 1200 | 1513D, 1612D, 2019B |
| fresh-25 | 2100 | 1100 | 1282D, 1114E, 1797C |
| fresh-26 | 1900 | 1700 | 1841E, 1905D, 1478C |
| fresh-27 | 2100 | 1100 | 1848D, 2140D, 1717D |
| fresh-28 | 2200 | 1100 | 1860E, 979D, 1004C |
| fresh-29 | 2300 | 1200 | 1446D1, 1428E, 1481C |
| fresh-30 | 2200 | 1100 | 2002D2, 1909F1, 1327E |
| fresh-31 | 2000 | 1400 | 1634E, 1131D, 2027C |
| fresh-32 | 2100 | 1400 | 2002D2, 2103D, 2205D |
| fresh-33 | 1900 | 1700 | 939F, 1278D, 2205D |
| fresh-34 | 2100 | 1700 | 1107G, 1295E, 2133D |
| fresh-35 | 2200 | 1200 | 1905F, 1943B, 1709C |
| fresh-36 | 2700 | 1700 | 2231F, 1439B, 980E |
| fresh-37 | 2400 | 1700 | 1218C, 1860E, 1142B |
| fresh-38 | 2000 | 1100 | 1656D, 1848D, 2231F |
| fresh-39 | 2500 | 2000 | 920G, 1497E2, 1895F |
| fresh-40 | 2900 | 1100 | 920G, 1895F, 2231F |
| fresh-41 | 2900 | 1100 | 995A, 1599J, 2231F |
| fresh-42 | 2400 | 1100 | 1327E, 2025E, 1895F |
| fresh-43 | 2700 | 1900 | 2231F, 1895F, 1556F |
| fresh-44 | 2300 | 1100 | 1188C, 1909F1, 1717D |
| fresh-45 | 2100 | 1400 | 1634E, 1131D, 2027C |
| fresh-46 | 2400 | 1700 | 1497E2, 1743F, 979D |
| fresh-47 | 2800 | 1700 | 2231F, 1895F, 976D |
| fresh-48 | 2900 | 2000 | 2231F, 1895F, 1743F |
