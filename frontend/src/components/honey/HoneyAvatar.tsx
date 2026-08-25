import { useEffect, useState } from "react";

import {
  companionAvatarUrl,
  getCompanionAvatarStatus,
} from "../../api/companion";
import { cn } from "../../lib/utils";
import {
  getHoneyAvatarImage,
  HONEYOS_AVATAR_EVENT,
  notifyHoneyAvatarChanged,
  type HoneyAvatarSurface,
} from "./avatar-storage";

type HoneyAvatarProps = {
  name: string;
  className?: string;
  surface?: HoneyAvatarSurface;
};

export function HoneyAvatar({ name, className, surface = "companion" }: HoneyAvatarProps) {
  const [localImage, setLocalImage] = useState(() => getHoneyAvatarImage(surface));
  const [serverVersion, setServerVersion] = useState("");
  const initial = Array.from(name.trim())[0] || "H";

  useEffect(() => {
    let active = true;
    let retryTimer: number | undefined;
    const update = () => setLocalImage(getHoneyAvatarImage(surface));
    const onAvatar = (event: Event) => {
      const detail = (event as CustomEvent<{ surface?: HoneyAvatarSurface; version?: string }>).detail;
      if (detail?.surface && detail.surface !== surface) return;
      update();
      if (surface === "companion") setServerVersion(detail?.version || String(Date.now()));
    };
    const loadServerAvatar = (attempt = 0) => {
      void getCompanionAvatarStatus().then((status) => {
        if (!active) return;
        const version = status.exists ? status.version : "";
        setServerVersion(version);
        if (version) notifyHoneyAvatarChanged("companion", version);
      }).catch(() => {
        if (!active || attempt >= 2) return;
        retryTimer = window.setTimeout(() => loadServerAvatar(attempt + 1), 1_000 * (attempt + 1));
      });
    };
    if (surface === "companion") loadServerAvatar();
    window.addEventListener(HONEYOS_AVATAR_EVENT, onAvatar);
    window.addEventListener("storage", update);
    update();
    return () => {
      active = false;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      window.removeEventListener(HONEYOS_AVATAR_EVENT, onAvatar);
      window.removeEventListener("storage", update);
    };
  }, [surface]);

  const image = surface === "companion" && serverVersion
    ? companionAvatarUrl(serverVersion)
    : localImage;

  return (
    <span
      className={cn(
        "relative inline-grid size-11 shrink-0 place-items-center overflow-hidden rounded-[var(--radius-md)] bg-[var(--foreground)] text-sm font-semibold text-[var(--background)] shadow-[0_10px_30px_rgba(56,48,39,0.14)]",
        className,
      )}
      aria-hidden="true"
    >
      {image ? (
        <img
          src={image}
          alt=""
          className="absolute inset-0 h-full w-full object-cover"
          onError={() => {
            if (surface === "companion" && serverVersion) setServerVersion("");
            else setLocalImage("");
          }}
        />
      ) : initial}
    </span>
  );
}
