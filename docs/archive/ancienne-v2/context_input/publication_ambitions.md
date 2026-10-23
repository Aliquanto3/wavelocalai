# Publication ambitions

> Translated from the owner's French research notes (source: personal ambition statement, 2026-09). Kept as source material for AIDD framing, not a spec.

I work with Claude Code on two local-AI projects.

There is a "small" ambition behind this work: I would like to publish a short research paper to help other people who want to run local AI on personal computers anticipate the results for a large number of models. Dedicated work on this seems relatively uncommon — at least it still was a few months ago.

I would also like this paper to serve my work as a consultant, building a reference point around AI, and to help me get a foothold in academia, which interests me (for example I am curious about options for a PhD or for teaching in higher education — though that is more secondary).

For this, I want to run my benchmark on at least 3 PCs:
- my gaming tower: Ryzen 5 7600, 32 GB DDR5-6000 RAM, RTX 3050 8 GB VRAM
- my gaming laptop: Ryzen 7 5800H, 32 GB DDR4-3200 RAM, RTX 3060 Laptop 6 GB VRAM (current dev machine)
- my professional PC: 16 GB RAM, no GPU

Model sizes need to be fitted per machine. For example, Granite 350M will suit the professional PC well, while I can go up to Gemma-4-class models on the tower.

This benchmark should make it possible to anticipate:

- capabilities on standard actions such as categorisation, translation, typo correction
- answer writing in RAG pipelines, and even RAG orchestration in a Refrag or agentic-RAG architecture
- capabilities on more complex actions, such as tool calling, agentic orchestration, or code writing (including result quality, but also task duration, number of tokens required, energy consumed...)
- mastery of different languages, and even programming languages
- the various speed metrics around token generation
- energy consumption and carbon impact

It should also make it possible to draw conclusions on the best frameworks and libraries to use for SLMs (llama.cpp or Ollama? LangGraph or smolagents? and others), and even the best harnesses to use for agentic use cases (or the best combination of an SLM and a harness for a given task).

An additional point that has held my attention for several months: what are the best prompt-compression techniques? Do they let SLMs gain in precision and speed, particularly in agentic work? I am thinking in particular of the DSL (Domain Specific Language) technique that I explored for Copilot Studio when I was limited on prompt tokens. Or, more recently, the "Caveman" skill.

Incidentally, this work can also serve as a lessons-learned (REX) on the use of Claude Code, as well as the SpecKit and AIDD frameworks I have tested for implementing these GitHub repos (still ongoing). **This lessons-learned ambition is out of scope for this repository.**

As a bonus, in my Budget_Tags project, it should make it possible to compare SLM results against other tagging techniques, such as business rules or KNN — for example by running each method alone on the full dataset and then comparing against combinations of these methods (both in answer precision and in energy consumption or execution speed).
