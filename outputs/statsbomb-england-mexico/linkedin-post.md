Knowledge Graphs are becoming one of the biggest areas of conversation when organisations talk about the right intelligence layer for enterprise AI adoption.

Usually that conversation sounds like this:

- How do we connect structured and unstructured data?
- How do we give AI systems context without dumping everything into a prompt?
- How do we make relationships, provenance and reasoning paths visible?
- How do we stop AI from becoming a clever interface over disconnected silos?

But knowledge graphs are not just for enterprise architecture diagrams.

They can also be used for football analysis.

I built a small football knowledge graph using open StatsBomb World Cup event data, Neo4j and a GPT-assisted analysis layer. No paid/live feed here, and the public data is historical rather than current, so the sensible way to analyse it is not "which named player from 2018 or 2022 is the answer?"

The better question is:

What event patterns keep showing up?

The graph links teams, matches, events, shots, passes, carries, receivers, possession chains, shot zones and xG. That means the analysis can move from isolated events to connected patterns:

- what happened before a shot
- where the shot came from
- whether the chance came from a carry, a final pass, a multi-pass move, a cutback-style entry or a second phase
- which defensive zones repeatedly gave up value

The fun bit: I used it to ask what England might need to do to beat Mexico.

Based on the knowledge graph, the more useful takeaways are event-driven rather than player-driven:

1. Attack Mexico's central box, not just the wide areas.
Across the historical open-data sample, Mexico's biggest conceded-shot value came from the central lane inside the box and six-yard zone: 50 shots, 10.15 xG, around 0.20 xG per shot.

2. Prioritise possessions that end with a central-box action.
The strongest England patterns were not just "keep the ball"; they were possessions that turned passes/carries into a shot inside the high-value central zone.

3. Use rotations to create the final action, but do not over-index on the historical player names.
Some chains in the graph involve familiar names, but the transferable signal is the event shape: a connector receives, a runner attacks the box, and the final action turns into a high-xG shot.

4. Look for cutback and second-phase moments.
Mexico's higher-value conceded chances often came when opponents re-entered central spaces after combinations, rebounds or quick re-circulation.

5. Separate possession from penetration.
This is where the graph is useful. It can distinguish "lots of passes" from "connected actions that actually produce xG."

That is also why knowledge graphs matter for enterprise AI.

They give AI a memory of relationships.
They make context navigable.
They allow reasoning to be traced.
They expose the difference between raw activity and connected evidence.

Whether the domain is insurance, telecoms, supply chains, customer operations or football tactics, the principle is the same:

AI gets much more useful when it can reason over how things are connected.

#KnowledgeGraphs #EnterpriseAI #GraphAI #Neo4j #FootballAnalytics #GenAI #DataStrategy
