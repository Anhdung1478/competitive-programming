# Predictions — round 7 (era correction, recency preference removed)

Blind: the predicting agents saw the statement text and the runtime references, never
a true rating and never the calibration directory. The eval prompt is verbatim from the
2026-09-16 generation, unchanged since round 1.

Varies against **round 6**: Pass D.1 (de-compression) deleted, and the `prefer the more
recent anchor` sentence deleted from Pass C. The era discount arithmetic is unchanged.
`tag-floors.md` and the anchor set are identical to rounds 4 and 6.

All 24 rows cite only real anchor ids, and no eval problem appears as an anchor.

| slot | predicted | floor | anchors used |
|---|---|---|---|
| eval-01 | 1900 | 1100 | 1656D, 2173D, 1612D |
| eval-02 | 2400 | 1700 | 2002D2, 1743F, 1295E |
| eval-03 | 2200 | 1700 | 1292C, 1265E, 2133D |
| eval-04 | 2100 | 1200 | 1905D, 1943B, 1453D |
| eval-05 | 1800 | 1200 | 1656D, 1717D, 1612D |
| eval-06 | 1400 | 1100 | 1797C, 1455D, 1463B |
| eval-07 | 1200 | 1100 | 1775B, 2253B, 1221B |
| eval-08 | 1900 | 1200 | 1867E1, 1717D, 1327E |
| eval-09 | 2100 | 1700 | 1292C, 1187E, 2133D |
| eval-10 | 1400 | 1100 | 1612D, 2084C, 1207B |
| eval-11 | 1400 | 1100 | 1797C, 980B, 2092C |
| eval-12 | 2000 | 1400 | 1987E, 1370D, 1923D |
| eval-13 | 1500 | 1100 | 1797C, 2152B, 2092C |
| eval-14 | 1800 | 1700 | 1905D, 2133D, 1995C |
| eval-15 | 2200 | 1100 | 1656D, 1453D, 1758D |
| eval-16 | 1700 | 1200 | 1923D, 2112D, 1993C |
| eval-17 | 1600 | 1200 | 1995C, 1612D, 1832C |
| eval-18 | 1300 | 1100 | 2084C, 1775B, 2253B |
| eval-19 | 2300 | 1200 | 2103D, 1943B, 1453D |
| eval-20 | 1600 | 1200 | 1797C, 1299A, 1832C |
| eval-21 | 1700 | 1100 | 1797C, 2205D, 1612D |
| eval-22 | 2000 | 1200 | 1995C, 1758D, 1814B |
| eval-23 | 2400 | 1700 | 2209E, 1743F, 1905D |
| eval-24 | 1200 | 1100 | 2119B, 2084C, 2253B |
