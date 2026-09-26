# Handoff — Cognitive Memory Phase F2 → Phase G

Date: 2026-09-26

## Start point

Use the Phase F2 freeze commit produced by the F2.6 freeze script as the formal parent for future work.

Previous frozen baseline:

- F1: `61ee4ff4fc29649ef60ec778b6c539e9256b0685`

## What is now working

Cognitive Memory can now:

- retrieve relevant historical memories through F1;
- construct compact SilentMemoryContext objects;
- preserve temporal semantics;
- mark imported DeepSeek history as historical;
- hide source/provenance details from model-visible memory text;
- enforce general vs roleplay/fiction boundaries;
- attach memory to the existing internal model context;
- fail open if memory context construction/injection fails;
- conservatively suppress explicit current-vs-old value conflicts;
- retain useful historical context when there is no explicit conflict.

## Important architectural rule

Priority remains:

current explicit user statement
> current-session evidence
> native/current HoneyOS memory
> newer Cognitive Memory
> old external DeepSeek history

Imported DeepSeek history is external historical context. It must not silently become equivalent to current/native/shared experience.

## Phase G objective

Phase G should improve how Honey behaves as a companion without destabilizing the memory runtime.

Do not start by expanding Cognitive Memory retrieval.

Focus on conversation behavior:

### G1 Natural Chat Output
- shorter everyday replies
- allow 1–3 natural message bubbles
- reduce essay/report behavior
- avoid unnecessary summaries

### G2 Assistant-habit / defensive-writing audit
Reduce:
- "根据历史记录..."
- "记忆库显示..."
- "我查到..."
- unnecessary caveats
- repeated "我理解你"
- excessive advice
- excessive clarification questions
- over-explaining internal reasoning or retrieval

### G3 Compact Honey identity
Keep identity/personality instructions small and stable rather than building a giant personality prompt.

### G4 Positive style-example learning
When the user likes a Honey reply:
- store context + liked reply as a style example;
- retrieve a small number of relevant positive examples later;
- use them to influence HOW Honey speaks, not WHAT Honey believes.

Style examples must remain separate from factual memory.

### G5 Honey reactions / shared notes
Support distinct objects such as:
- User Memory
- Shared Note
- Interesting Quote
- Style Example

### G6 Shared reading / quote memory
Allow Honey and the user to retain interesting passages/ideas without treating every quote as a personal fact.

## Unified context routing audit

A major Phase G engineering task should expose, per turn, which context channels contributed model input:

- current conversation history
- native HoneyOS memory
- Cognitive Memory
- external context
- shared experiences/notes
- roleplay/fiction context

This is necessary because final replies can contain information from other existing HoneyOS memory systems even when Cognitive Memory correctly injects nothing.

Do not infer source leakage from final prose alone.

## Known UX observations from F2.5

Cognitive Memory itself did not expose source IDs, source keys, or DeepSeek labels.

However, Honey can still use retrieval-style wording such as:
- "我目前保留的记忆..."
- "能查到的历史..."
- "我找到三条..."

These phrases can originate from existing HoneyOS prompts/context paths. Treat them as Phase G behavior work, not an F2 retrieval failure.

## Retrieval quality note

F1 lexical retrieval occasionally returns weakly related memories due to token/number overlap. Example: a Pomodoro-change query retrieved unrelated study/animal-experiment memories.

This did not block F2 because:
- payload is small;
- current explicit user statements remain dominant;
- F2.4 avoids overblocking;
- model responses remained correct in the live gate.

If retrieval precision is improved later, do it as a separate tested change rather than mixing it into conversational style work.

## Git / worktree safety

The repository contains unrelated dirty and untracked work.

Do not use:
- `git reset --hard`
- `git clean -fd`
- blind `git add .`

Shared files such as `honeyos/agent/turn_context.py` may contain unrelated working-tree changes. Isolate future commits carefully.

## Suggested first Phase G task

Start with a read-only audit of:
1. all current system/developer/personality prompts;
2. native memory prefetch/injection;
3. Cognitive Memory injection;
4. conversation-history construction;
5. assistant wording rules.

Produce a turn-context map before changing tone/personality behavior.
