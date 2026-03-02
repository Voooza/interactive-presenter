import { BrowserRouter, Route, Routes } from 'react-router-dom';

import PresentationList from './components/PresentationList';
import SlideViewer from './components/SlideViewer';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<PresentationList />} />
        <Route path="/presentations/:id" element={<SlideViewer />} />
      </Routes>
    </BrowserRouter>
  );
}
