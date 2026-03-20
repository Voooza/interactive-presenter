/**
 * Custom React hook for managing Q&A state from WebSocket messages.
 *
 * Tracks submitted questions, provides a submit handler for audience members,
 * and processes incoming question-related server messages. The caller is
 * responsible for sending the actual WebSocket message via the `send` callback.
 */

import { useCallback, useState } from 'react';

import type { QuestionData, ServerMessage } from '../types';

export interface UseQuestionsReturn {
  /** All questions received so far (for presenter). */
  questions: QuestionData[];
  /** The most recently confirmed question from this audience member. */
  lastConfirmed: QuestionData | null;
  /** Handle incoming server messages to update question state. */
  handleMessage: (message: ServerMessage) => void;
}

export function useQuestions(): UseQuestionsReturn {
  const [questions, setQuestions] = useState<QuestionData[]>([]);
  const [lastConfirmed, setLastConfirmed] = useState<QuestionData | null>(null);

  const handleMessage = useCallback((message: ServerMessage) => {
    if (message.type === 'questions_list') {
      setQuestions(message.questions);
    } else if (message.type === 'question_notify') {
      setQuestions((prev) => {
        // Avoid duplicates (in case of reconnection).
        if (prev.some((q) => q.id === message.question.id)) return prev;
        return [...prev, message.question];
      });
    } else if (message.type === 'question_received') {
      setLastConfirmed(message.question);
    }
  }, []);

  return { questions, lastConfirmed, handleMessage };
}
