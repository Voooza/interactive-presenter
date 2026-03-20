/**
 * Hook that manages a queue of floating reaction particles for the presenter view.
 *
 * Particles are added via `addReaction` and automatically removed after `ttlMs`
 * milliseconds (default 3000 ms — matches the CSS animation duration).
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export interface ReactionParticle {
  /** Unique identifier for this particle. */
  id: string;
  /** The emoji character to display. */
  emoji: string;
  /**
   * Horizontal position as a percentage (5–95) of the container width.
   * Randomised at spawn time to spread particles across the screen.
   */
  xPercent: number;
}

export interface UseReactionsReturn {
  particles: ReactionParticle[];
  /** Call this when a reaction_broadcast message arrives. */
  addReaction: (emoji: string) => void;
}

const DEFAULT_TTL_MS = 3000;

export function useReactions(ttlMs: number = DEFAULT_TTL_MS): UseReactionsReturn {
  const [particles, setParticles] = useState<ReactionParticle[]>([]);

  // Track pending timeouts so we can clear them on unmount.
  const timeoutsRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  // Clean up all pending timeouts on unmount.
  useEffect(() => {
    return () => {
      for (const t of timeoutsRef.current) {
        clearTimeout(t);
      }
      timeoutsRef.current = [];
    };
  }, []);

  const addReaction = useCallback(
    (emoji: string) => {
      const id = crypto.randomUUID();
      // Keep particle away from very edges: random float in [5, 95].
      const xPercent = 5 + Math.random() * 90;

      const particle: ReactionParticle = { id, emoji, xPercent };

      setParticles((prev) => [...prev, particle]);

      // Schedule removal after the animation completes.
      const t = setTimeout(() => {
        setParticles((prev) => prev.filter((p) => p.id !== id));
        timeoutsRef.current = timeoutsRef.current.filter((x) => x !== t);
      }, ttlMs);

      timeoutsRef.current.push(t);
    },
    [ttlMs],
  );

  return { particles, addReaction };
}
