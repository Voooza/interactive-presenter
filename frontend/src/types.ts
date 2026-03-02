/** Domain types matching the backend API models. */

export interface Presentation {
  id: string;
  title: string;
}

export interface Slide {
  index: number;
  title: string;
  content: string;
}
