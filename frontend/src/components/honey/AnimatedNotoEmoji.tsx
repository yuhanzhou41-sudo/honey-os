import { useEffect, useState } from "react";

import { notoAnimatedEmojiUrls } from "../../runtime/animated-emoji";

export function AnimatedNotoEmoji({ emoji }: { emoji: string }) {
  const urls = notoAnimatedEmojiUrls(emoji);
  const [sourceIndex, setSourceIndex] = useState(0);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setSourceIndex(0);
    setFailed(false);
  }, [emoji]);

  if (!urls.length || failed) {
    return (
      <span className="block select-none text-[3rem] leading-none" role="img" aria-label={emoji}>
        {emoji}
      </span>
    );
  }

  return (
    <img
      src={urls[sourceIndex]}
      alt={emoji}
      className="block size-16 select-none object-contain"
      loading="lazy"
      decoding="async"
      onError={() => {
        if (sourceIndex + 1 < urls.length) setSourceIndex((current) => current + 1);
        else setFailed(true);
      }}
    />
  );
}
