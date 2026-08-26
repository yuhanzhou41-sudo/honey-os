import {
  BookOpenIcon,
  ChatCircleIcon,
  HeartIcon,
  SlidersHorizontalIcon,
  SparkleIcon,
} from "@phosphor-icons/react";
import { useEffect, useState, type CSSProperties } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { HoneyAvatar } from "../components/honey/HoneyAvatar";
import { cn } from "../lib/utils";
import { useHoneyStore } from "../runtime/honey-store";

const navigation = [
  { to: "/", label: "聊天", icon: ChatCircleIcon, end: true },
  { to: "/stories", label: "Story", icon: BookOpenIcon },
  { to: "/memories", label: "记得的事", icon: SparkleIcon },
  { to: "/relationship", label: "我们", icon: HeartIcon },
  { to: "/settings", label: "设置", icon: SlidersHorizontalIcon },
];

function isTextEntry(element: Element | null): boolean {
  if (!(element instanceof HTMLElement)) return false;
  if (element instanceof HTMLTextAreaElement) return true;
  if (element instanceof HTMLInputElement) {
    return !["button", "checkbox", "file", "hidden", "radio", "range", "reset", "submit"].includes(element.type);
  }
  return element.isContentEditable;
}

function useMobileKeyboardLayout() {
  const [textEntryFocused, setTextEntryFocused] = useState(false);
  const [viewportHeight, setViewportHeight] = useState<number | null>(null);

  useEffect(() => {
    const viewport = window.visualViewport;
    const updateViewport = () => setViewportHeight(viewport ? Math.round(viewport.height) : null);
    const updateFocus = () => setTextEntryFocused(isTextEntry(document.activeElement));
    const handleFocusIn = (event: FocusEvent) => setTextEntryFocused(isTextEntry(event.target as Element | null));
    const handleFocusOut = () => window.setTimeout(updateFocus, 0);

    updateViewport();
    document.addEventListener("focusin", handleFocusIn);
    document.addEventListener("focusout", handleFocusOut);
    viewport?.addEventListener("resize", updateViewport);
    viewport?.addEventListener("scroll", updateViewport);
    return () => {
      document.removeEventListener("focusin", handleFocusIn);
      document.removeEventListener("focusout", handleFocusOut);
      viewport?.removeEventListener("resize", updateViewport);
      viewport?.removeEventListener("scroll", updateViewport);
    };
  }, []);

  return { textEntryFocused, viewportHeight };
}

function PortraitNavigation() {
  return (
    <nav
      className="grid w-fit grid-cols-5 gap-1 rounded-[var(--radius-lg)] border border-white/15 bg-[#171a21]/88 p-1.5 shadow-[0_18px_50px_rgba(10,12,18,0.28)] backdrop-blur-xl"
      aria-label="主要页面"
    >
      {navigation.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          aria-label={label}
          title={label}
          className={({ isActive }) => cn(
            "grid size-12 place-items-center rounded-[var(--radius-md)] text-white/72 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white",
            isActive && "bg-white text-[#202128] hover:bg-white hover:text-[#202128]",
          )}
        >
          <Icon size={23} weight="regular" />
        </NavLink>
      ))}
    </nav>
  );
}

function MobileNavigation() {
  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-5 border-t border-[var(--border)] bg-[color-mix(in_srgb,var(--surface-raised)_94%,transparent)] px-2 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden"
      aria-label="主要页面"
    >
      {navigation.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) => cn(
            "flex min-h-[4rem] flex-col items-center justify-center gap-1 text-[10px] font-medium text-[var(--foreground-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--focus)]",
            isActive && "text-[var(--accent)]",
          )}
        >
          <Icon size={22} weight="regular" />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

export function AppShell() {
  const name = useHoneyStore((state) => state.name);
  const status = useHoneyStore((state) => state.status);
  const { textEntryFocused, viewportHeight } = useMobileKeyboardLayout();
  const shellStyle = viewportHeight
    ? { "--honey-viewport-height": `${viewportHeight}px` } as CSSProperties
    : undefined;

  return (
    <div
      className="honey-app-shell grid h-[var(--honey-viewport-height,100dvh)] min-h-0 grid-cols-1 overflow-hidden bg-[var(--background)] lg:grid-cols-[clamp(22rem,32vw,38rem)_minmax(0,1fr)]"
      data-keyboard-open={textEntryFocused}
      style={shellStyle}
    >
      <aside className="relative hidden h-[100dvh] min-w-0 overflow-hidden bg-[#25282f] lg:flex lg:flex-col">
        <HoneyAvatar
          name={name}
          className="absolute inset-0 !h-full !w-full !rounded-none bg-[#25282f] text-8xl shadow-none"
        />
        <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(13,15,20,0.18)_0%,rgba(13,15,20,0.02)_38%,rgba(13,15,20,0.72)_100%)]" />

        <NavLink
          to="/"
          className="relative z-[1] m-6 w-fit rounded-[var(--radius-sm)] px-2 py-1 text-sm font-semibold tracking-[-0.02em] text-white drop-shadow-[0_2px_8px_rgba(0,0,0,0.35)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
        >
          HoneyOS
        </NavLink>

        <div className="relative z-[1] mt-auto p-7 text-white">
          <div className="mb-5 drop-shadow-[0_2px_10px_rgba(0,0,0,0.4)]">
            <h1 className="text-3xl font-semibold tracking-[-0.035em]">{name}</h1>
            <p className="mt-1 text-sm text-white/72">{status}</p>
          </div>
          <PortraitNavigation />
        </div>
      </aside>

      <main className={cn(
        "h-full min-h-0 min-w-0 overflow-y-auto lg:pb-0",
        textEntryFocused ? "pb-0" : "pb-[calc(4rem+env(safe-area-inset-bottom))]",
      )}>
        <Outlet />
      </main>

      {textEntryFocused ? null : <MobileNavigation />}
    </div>
  );
}
