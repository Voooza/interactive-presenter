import type { Presentation, Slide } from './types';

const API_BASE_URL = 'http://localhost:8000';

export async function fetchPresentations(): Promise<Presentation[]> {
  const response = await fetch(`${API_BASE_URL}/api/presentations`);
  if (!response.ok) {
    throw new Error(`Failed to fetch presentations: ${response.statusText}`);
  }
  return response.json() as Promise<Presentation[]>;
}

export async function fetchSlides(id: string): Promise<Slide[]> {
  const response = await fetch(`${API_BASE_URL}/api/presentations/${encodeURIComponent(id)}/slides`);
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(`Presentation "${id}" not found`);
    }
    throw new Error(`Failed to fetch slides: ${response.statusText}`);
  }
  return response.json() as Promise<Slide[]>;
}
