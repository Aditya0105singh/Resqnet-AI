Seeds 1–10, 180 ticks each, all strategies share the same seeds, events, cost function and safety shield. Mean ± sd.


### normal

| strategy | mean TTS (min) | urgent misses | unmet people | idle w/ demand | fairness (Jain) | route violations | messages | coord. ms |
|---|---|---|---|---|---|---|---|---|
| decentralized | 26.047 ± 5.985 | 2.2 ± 1.549 | 14.0 ± 5.518 | 424.1 ± 253.892 | 0.795 ± 0.052 | 0.0 ± 0.0 | 1174.5 ± 320.58 | 141.601 ± 60.21 |
| centralized | 24.91 ± 5.055 | 1.9 ± 1.37 | 14.9 ± 7.233 | 484.1 ± 264.427 | 0.764 ± 0.098 | 0.0 ± 0.0 | 1553.4 ± 464.645 | 142.594 ± 61.395 |
| greedy | 27.516 ± 4.229 | 1.4 ± 1.647 | 15.2 ± 6.861 | 510.9 ± 286.928 | 0.828 ± 0.092 | 0.0 ± 0.0 | 1663.8 ± 622.988 | 155.536 ± 79.873 |

Paired (decentralized − centralized): mean_time_to_service +1.137 ± 1.996, deadline_misses +0.3 ± 0.949, unmet_people -0.9 ± 2.644, fairness_jain +0.031 ± 0.075, idle_with_demand_ticks -60.0 ± 149.518, negotiation_messages -378.9 ± 277.854

### contradictory

| strategy | mean TTS (min) | urgent misses | unmet people | idle w/ demand | fairness (Jain) | route violations | messages | coord. ms |
|---|---|---|---|---|---|---|---|---|
| decentralized | 24.022 ± 4.843 | 2.4 ± 1.265 | 14.4 ± 6.293 | 611.5 ± 193.882 | 0.776 ± 0.08 | 0.0 ± 0.0 | 1329.4 ± 220.547 | 239.829 ± 98.027 |
| centralized | 20.818 ± 3.89 | 2.4 ± 1.35 | 10.9 ± 7.203 | 630.5 ± 240.752 | 0.75 ± 0.069 | 0.0 ± 0.0 | 1704.7 ± 390.567 | 169.027 ± 69.858 |
| greedy | 24.605 ± 5.851 | 2.0 ± 1.333 | 16.2 ± 5.245 | 587.6 ± 184.699 | 0.828 ± 0.076 | 0.0 ± 0.0 | 1735.1 ± 327.46 | 162.297 ± 44.48 |

Paired (decentralized − centralized): mean_time_to_service +3.204 ± 3.473, deadline_misses +0.0 ± 1.054, unmet_people +3.5 ± 5.622, fairness_jain +0.027 ± 0.045, idle_with_demand_ticks -19.0 ± 159.94, negotiation_messages -375.3 ± 295.999

### triple_failure

| strategy | mean TTS (min) | urgent misses | unmet people | idle w/ demand | fairness (Jain) | route violations | messages | coord. ms |
|---|---|---|---|---|---|---|---|---|
| decentralized | 27.983 ± 3.974 | 3.1 ± 1.101 | 28.8 ± 11.774 | 408.7 ± 150.975 | 0.792 ± 0.099 | 0.0 ± 0.0 | 1578.7 ± 247.543 | 130.56 ± 52.773 |
| centralized | 27.197 ± 4.622 | 2.6 ± 1.174 | 28.2 ± 7.983 | 360.3 ± 133.343 | 0.791 ± 0.079 | 0.0 ± 0.0 | 1704.5 ± 314.007 | 102.682 ± 44.468 |
| greedy | 31.205 ± 5.842 | 2.0 ± 1.633 | 29.0 ± 6.667 | 429.5 ± 159.035 | 0.838 ± 0.067 | 0.0 ± 0.0 | 1899.9 ± 343.116 | 119.423 ± 46.09 |

Paired (decentralized − centralized): mean_time_to_service +0.786 ± 2.337, deadline_misses +0.5 ± 1.434, unmet_people +0.6 ± 11.177, fairness_jain +0.001 ± 0.097, idle_with_demand_ticks +48.4 ± 139.811, negotiation_messages -125.8 ± 491.263

### resource_shortage

| strategy | mean TTS (min) | urgent misses | unmet people | idle w/ demand | fairness (Jain) | route violations | messages | coord. ms |
|---|---|---|---|---|---|---|---|---|
| decentralized | 43.963 ± 4.565 | 4.7 ± 1.418 | 34.7 ± 11.767 | 125.5 ± 81.211 | 0.821 ± 0.064 | 0.0 ± 0.0 | 1164.4 ± 359.298 | 81.69 ± 36.853 |
| centralized | 42.13 ± 5.262 | 4.5 ± 1.509 | 29.8 ± 10.675 | 135.7 ± 72.858 | 0.791 ± 0.066 | 0.0 ± 0.0 | 1179.6 ± 449.635 | 72.16 ± 24.394 |
| greedy | 46.023 ± 6.213 | 2.6 ± 1.955 | 33.1 ± 10.159 | 112.7 ± 71.173 | 0.839 ± 0.076 | 0.0 ± 0.0 | 1031.7 ± 389.329 | 68.656 ± 24.12 |

Paired (decentralized − centralized): mean_time_to_service +1.833 ± 2.939, deadline_misses +0.2 ± 0.422, unmet_people +4.9 ± 11.377, fairness_jain +0.029 ± 0.041, idle_with_demand_ticks -10.2 ± 56.627, negotiation_messages -15.2 ± 171.724
