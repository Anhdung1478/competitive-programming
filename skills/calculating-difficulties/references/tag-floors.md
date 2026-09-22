# Prerequisite floors

The hardest technique a solution **requires** sets a floor: the level below which the
problem cannot land, whatever the code looks like. A floor is not an estimate — Pass C
produces the estimate.

A technique that merely appears does not count. Ask whether a solver who does not know it
can still solve the problem within the constraints. If yes, it is not a prerequisite.

| Technique | Floor |
|---|---|
| two pointers, prefix sums, sorting + greedy | 1200 |
| DSU, basic graph traversal with a twist, binary search on answer | 1400 |
| segment tree / BIT, standard DP over one dimension, shortest paths | 1700 |
| digit DP, bitmask DP over subsets, tree DP with rerooting | 1900 |
| lazy propagation, SOS DP, matrix exponentiation, flows | 2000 |
| FFT/NTT, convex hull trick, heavy-light decomposition | 2100 |
| centroid decomposition, link-cut-free offline tricks, Mo's on trees | 2200 |
| suffix automaton, suffix tree, advanced string automata | 2300 |

Nothing on the list required ⇒ floor `1100`.

Two techniques from the same row do not stack: take the single hardest, then let Pass D
charge at most `+200` for the extra independent insights they represent.

<!-- Calibration: tuning round 2 shifted this column down by 200 as one constant and made
both MAE and bias worse on a 24-problem blind eval, so round 3 restored the drafted values.
The floors are not the binding constraint on the estimate; Pass C's anchor placement is.
Row order has never changed. -->
