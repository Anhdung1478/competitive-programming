# Predictions — round 8A (shipped configuration re-measured)

Blind: the predicting agents saw the statement text and the runtime references, never
a true rating and never the calibration directory. The eval prompt is verbatim from the
2026-09-16 generation, unchanged since round 1.

Varies against **round 7**: the recency preference removed from `references/anchors.md`
(round 7 deleted it from SKILL.md only), Pass B's floor-`1100` lower-bound rule, Pass C's
verbatim anchor copy, Pass C.1's level-shift statement, Pass E's anchor-id check and
interval-coverage requirement, and `Calibration status` compressed. The anchor set,
`tag-floors.md` and every arithmetic rule are identical to rounds 4, 6 and 7.

This arm shares a model with 8B and is 8B's control; it is not directly comparable to
rounds 1-7, which ran on an earlier model.

| slot | predicted | floor | anchors used |
|---|---|---|---|
| eval-01 | 2000 | 1200 | 1943B, 1453D, 1612D |
| eval-02 | 2500 | 1700 | 1497E2, 1743F, 1295E |
| eval-03 | 2200 | 1700 | 1594E2, 1909F1, 1265E |
| eval-04 | 2100 | 1200 | 1943B, 1717D, 1327E |
| eval-05 | 1900 | 1100 | 2165B, 1656D, 1612D |
| eval-06 | 1400 | 1100 | 1406C, 980B, 1207B |
| eval-07 | 1200 | 1100 | 1463B, 2092C, 1762B |
| eval-08 | 1900 | 1200 | 1867E1, 1717D, 1327E |
| eval-09 | 2200 | 1700 | 2025E, 1987E, 2018C |
| eval-10 | 1400 | 1100 | 1481C, 2084C, 1207B |
| eval-11 | 1400 | 1100 | 2084C, 1775B, 1762B |
| eval-12 | 1900 | 1400 | 1987E, 1380D, 1923D |
| eval-13 | 1400 | 1100 | 1797C, 2152B, 1257C |
| eval-14 | 1900 | 1700 | 1905D, 2133D, 1995C |
| eval-15 | 2100 | 1400 | 2209E, 1695D1, 1453D |
| eval-16 | 1800 | 1200 | 1923D, 1709C, 1073D |
| eval-17 | 1400 | 1200 | 1228C, 1993C, 1792B |
| eval-18 | 1800 | 1200 | 1824B1, 2112D, 1455D |
| eval-19 | 2200 | 1200 | 1943B, 1513D, 1717D |
| eval-20 | 1600 | 1200 | 2112D, 2140C, 2119B |
| eval-21 | 1900 | 1100 | 2165B, 1453D, 1797C |
| eval-22 | 2100 | 1200 | 1987E, 1656D, 1513D |
| eval-23 | 2300 | 1700 | 1743F, 1295E, 1905D |
| eval-24 | 1100 | 1100 | 2092C, 2253B, 1207B |
