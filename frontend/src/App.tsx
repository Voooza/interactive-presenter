import { BrowserRouter, Route, Routes } from 'react-router-dom';

import AudienceView from './components/AudienceView';
import PresentationList from './components/PresentationList';
import SlideViewer from './components/SlideViewer';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<PresentationList />} />
        <Route path="/presentations/:id" element={<SlideViewer />} />
        <Route path="/presentations/:id/audience" element={<AudienceView />} />
      </Routes>
    </BrowserRouter>
  );
}
