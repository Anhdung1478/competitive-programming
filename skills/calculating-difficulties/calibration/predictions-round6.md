# Predictions — round 6 (era correction + de-compression)

Blind: the predicting agents saw the statement text and the runtime references, never
a true rating and never the calibration directory. The eval prompt is verbatim from the
2026-09-16 generation, unchanged since round 1.

Varies against **round 4** (not round 5, whose tag-floors extension was rejected):
`tag-floors.md` is byte-identical to its round-4 state and the anchor set is unchanged,
so this round varies exactly the SKILL.md passes — Pass C.1 (era correction), Pass D.1
(de-compression), a `year` column in `anchors.md`, and the English output template.

All 24 rows cite only real anchor ids, and no eval problem appears as an anchor.

| slot | predicted | floor | anchors used |
|---|---|---|---|
| eval-01 | 1800 | 1100 | 2205D, 2112D, 1797C |
| eval-02 | 2700 | 1700 | 2248F, 1301E, 1743F |
| eval-03 | 2200 | 1700 | 1594E2, 2025E, 2133D |
| eval-04 | 2200 | 1200 | 2140D, 1943B, 1824B1 |
| eval-05 | 1700 | 1100 | 2205D, 2182D, 2160C |
| eval-06 | 1200 | 1100 | 1612D, 2211C1, 2253B |
| eval-07 | 1100 | 1100 | 2084C, 2092C, 2253B |
| eval-08 | 2000 | 1200 | 1905D, 1717D, 1814B |
| eval-09 | 2300 | 1700 | 2025E, 1987E, 2133D |
| eval-10 | 1400 | 1100 | 1481C, 2084C, 2092C |
| eval-11 | 1300 | 1100 | 2253B, 2245C, 2140C |
| eval-12 | 2000 | 1400 | 2027C, 1923D, 1987E |
| eval-13 | 1500 | 1100 | 2253B, 1804C, 1797C |
| eval-14 | 1800 | 1700 | 2018C, 2133D, 2025E |
| eval-15 | 2500 | 1400 | 1987E, 2209E, 2025E |
| eval-16 | 1800 | 1200 | 1923D, 2018C, 2127C |
| eval-17 | 1400 | 1200 | 2164C, 2127C, 2092C |
| eval-18 | 1800 | 1200 | 1923D, 2112D, 2164C |
| eval-19 | 2200 | 1200 | 1943B, 1867E1, 1656D |
| eval-20 | 1300 | 1100 | 2164C, 2160C, 2092C |
| eval-21 | 1600 | 1100 | 2205D, 1797C, 2067C |
| eval-22 | 2300 | 1100 | 1656D, 2173D, 1228C |
| eval-23 | 2400 | 1700 | 2002D2, 2209E, 2133D |
| eval-24 | 1200 | 1100 | 2127C, 1463B, 2253B |
