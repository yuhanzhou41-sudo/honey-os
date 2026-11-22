# User acceptance checklist

Use this only after an isolated release is prepared and the user explicitly
authorizes real data/model access. Do not clear or seed the real memory store.

1. Open **记忆 → Honey 的理解**. Confirm category, scope, grade, state,
   revision, and evidence lineage are understandable. A source marked “当前有效性待来源复核”
   must not be presented as currently verified.
2. Edit one harmless synthetic/test understanding. Refresh the page and verify
   the text persists, grade remains `low`, and a `user_edit` version exists.
3. Suppress it. Start a new request and verify its derived text is absent.
   Restore it and verify it returns as `needs_reassessment + low`, not its old
   confidence. Logically forget it and verify original chat is not deleted.
4. In an authorized test conversation, ask a question related to one allowed
   memory and one unrelated question. Relevant context may be used cautiously;
   the unrelated turn must not force a graph label into the reply.
5. Provide new information contradicting an old understanding. The current turn
   must respect the new statement; after the next eligible distillation, inspect
   that support and counterevidence coexist and the label becomes disputed/low.
6. Create a harmless user diary entry with AI-view permission and have one
   same-day conversation. Verify the generated diary uses only allowed same-day
   diary/conversation facts. U2 or momentary state must not appear as factual
   diary input under the current implementation.
7. State a clearly incorrect belief, for example “I believe X is proven,” in a
   safe non-medical synthetic scenario. Honey may acknowledge or care about the
   belief, but must not say X is verified merely because the user believes it.
8. Close and restart the isolated Gateway with a prepared `response_saved` U2
   job. Verify the worker completes it once with zero model calls. Withdraw its
   source before a second prepared run and verify it stays blocked.

Record screenshots only with synthetic data. Stop immediately if a prohibited
source appears, and switch understanding mode to `off`; do not delete the real
database as a rollback technique.
