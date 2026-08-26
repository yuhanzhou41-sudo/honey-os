type ChatEnterInput = {
  key: string;
  shiftKey: boolean;
  isComposing: boolean;
  coarsePointer: boolean;
};

export function shouldSubmitChatOnEnter(input: ChatEnterInput): boolean {
  return input.key === "Enter"
    && !input.shiftKey
    && !input.isComposing
    && !input.coarsePointer;
}
