/**
 * Custom React hook for managing poll state from WebSocket messages.
 *
 * Tracks the currently active poll (options, results, user vote status)
 * and provides a local vote handler that marks the user as having voted.
 * The caller is responsible for sending the actual WebSocket message.
 */

import { useCallback, useState } from 'react';

import type { ServerMessage } from '../types';

export interface PollState {
  slideIndex: number;
  options: string[];
  results: number[];
  hasVoted: boolean;
  votedOption: number | null;
  isOpen: boolean;
}

export interface UsePollsReturn {
  /** The currently active poll, or null if no poll is active. */
  activePoll: PollState | null;
  /** Mark a vote locally (does not send a WS message). */
  markVoted: (slideIndex: number, optionIndex: number) => void;
  /** Handle incoming server messages to update poll state. */
  handleMessage: (message: ServerMessage) => void;
}

export function usePolls(): UsePollsReturn {
  const [activePoll, setActivePoll] = useState<PollState | null>(null);

  const handleMessage = useCallback((message: ServerMessage) => {
    if (message.type === 'poll_opened') {
      setActivePoll((prev) => ({
        slideIndex: message.slide_index,
        options: message.options,
        results: message.results,
        // Preserve vote status if reconnecting to the same poll.
        hasVoted: prev?.slideIndex === message.slide_index ? prev.hasVoted : false,
        votedOption: prev?.slideIndex === message.slide_index ? prev.votedOption : null,
        isOpen: true,
      }));
    } else if (message.type === 'poll_results') {
      setActivePoll((prev) => {
        if (prev === null || prev.slideIndex !== message.slide_index) return prev;
        return {
          ...prev,
          results: message.results,
        };
      });
    } else if (message.type === 'poll_closed') {
      setActivePoll((prev) => {
        if (prev === null || prev.slideIndex !== message.slide_index) return prev;
        return {
          ...prev,
          results: message.results,
          isOpen: false,
        };
      });
    }
  }, []);

  const markVoted = useCallback((slideIndex: number, optionIndex: number) => {
    setActivePoll((prev) => {
      if (prev === null || prev.slideIndex !== slideIndex) return prev;
      return {
        ...prev,
        hasVoted: true,
        votedOption: optionIndex,
      };
    });
  }, []);

  return { activePoll, markVoted, handleMessage };
}
