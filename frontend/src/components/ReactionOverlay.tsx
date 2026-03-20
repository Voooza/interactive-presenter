/**
 * Renders floating emoji particles on the presenter screen.
 *
 * The overlay fills the viewport with pointer-events disabled so it never
 * interferes with slide navigation. Each particle's rise and fade-out are
 * driven entirely by CSS animation — no JS requestAnimationFrame needed.
 */

import type { ReactionParticle } from '../hooks/useReactions';

interface ReactionOverlayProps {
  particles: ReactionParticle[];
}

export default function ReactionOverlay({ particles }: ReactionOverlayProps) {
  return (
    <div className="reaction-overlay">
      {particles.map((particle) => (
        <span
          key={particle.id}
          className="reaction-particle"
          style={{ left: `${particle.xPercent}%` }}
          aria-hidden="true"
        >
          {particle.emoji}
        </span>
      ))}
    </div>
  );
}
