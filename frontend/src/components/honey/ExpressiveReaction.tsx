import { useEffect, useState } from "react";

import { listStickers, markStickerUsed, stickerMediaUrl, type StickerItem } from "../../api/stickers";
import { reactionForEmoji, stableStickerIndex } from "../../runtime/sticker-reactions";
import { AnimatedNotoEmoji } from "./AnimatedNotoEmoji";

const markedLiveReactions = new Set<string>();

export function ExpressiveReaction({
  emoji,
  messageId = "",
}: {
  emoji: string;
  messageId?: string;
}) {
  const [sticker, setSticker] = useState<StickerItem | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const reaction = reactionForEmoji(emoji);
    setSticker(null);
    setFailed(false);
    if (!reaction) return () => { cancelled = true; };

    void listStickers({ tag: reaction, sort: "least_used", limit: 24 })
      .then(({ stickers }) => {
        if (cancelled || !stickers.length) return;
        const selected = stickers[stableStickerIndex(`${messageId}:${emoji}`, stickers.length)];
        setSticker(selected);
        const usageKey = `${messageId}:${selected.id}`;
        if (messageId.startsWith("live-") && !markedLiveReactions.has(usageKey)) {
          markedLiveReactions.add(usageKey);
          void markStickerUsed(selected.id).catch(() => markedLiveReactions.delete(usageKey));
        }
      })
      .catch(() => undefined);

    return () => { cancelled = true; };
  }, [emoji, messageId]);

  if (!sticker || failed) return <AnimatedNotoEmoji emoji={emoji} />;

  return (
    <img
      src={stickerMediaUrl(sticker.id)}
      alt={emoji}
      title={sticker.original_name}
      className="block size-24 select-none object-contain"
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
    />
  );
}
